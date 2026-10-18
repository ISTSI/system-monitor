"""Sanitized exchange, owner/project/session grants and offline-only MariaDB data."""

import asyncio
import hashlib
import io
import json
import threading
import zipfile

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from test_history import EVENTS, FROM, TO, enable_demo, finished, seed, start
from test_investigations import QUERY, bookmark_payload, capture, raw_checksums, saved_payload

from inspector.investigation_bundles import encoded, pack_bundle
from inspector.persistence.bundle_models import (
    BundleDownload,
    BundlePreview,
    OfflineAnalysis,
    OfflineCursor,
    OfflineInvestigation,
)
from inspector.persistence.models import HistoryEvent, HistoryJob, HistorySource

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


async def preview_export(client, project, job, **kwargs):
    response = await client.post(
        f"/api/v1/projects/{project}/bundles/export/preview",
        json={"investigation_id": job, "redact_terms": [], **kwargs},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def download_export(client, project, preview):
    response = await client.post(
        f"/api/v1/projects/{project}/bundles/export", json={"preview_id": preview["preview_id"]}
    )
    assert response.status_code == 200, response.text
    download = await client.get(response.json()["url"])
    assert download.status_code == 200, download.text
    return download.content, response.json()["url"]


async def import_preview(client, project, data):
    return await client.post(
        f"/api/v1/projects/{project}/bundles/import/preview",
        content=data,
        headers={"Content-Type": "application/zip"},
    )


async def test_collection_bounds_survive_display_edits_export_import_and_reexport(
    foundation, tmp_path
):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    async with foundation.client(foundation.alice) as alice:
        collection_from = "2026-10-16T12:00:00.000000Z"
        collection_to = "2026-10-16T12:00:02.000000Z"
        created, _, _ = await start(
            alice, foundation.project_a, from_=collection_from, to=collection_to
        )
        job = await finished(alice, foundation.project_a, created["job_id"])
        assert job["status"] == "completed", job
        base = f"/api/v1/projects/{foundation.project_a}/investigations/{created['job_id']}"
        display_from = "2026-10-16T12:00:01.000000Z"
        saved = await alice.patch(base + "/workspace", json=saved_payload(**{"from": display_from}))
        assert saved.status_code == 200, saved.text
        preview = await preview_export(alice, foundation.project_a, created["job_id"])
        origin = preview["document"]["origin"]
        assert origin["collection_from"] == collection_from
        assert origin["collection_to"] == collection_to
        assert preview["document"]["selection"]["from"] == display_from
        blob, _ = await download_export(alice, foundation.project_a, preview)
        staged = await import_preview(alice, foundation.project_b, blob)
        assert staged.status_code == 200, staged.text
        imported = await alice.post(
            f"/api/v1/projects/{foundation.project_b}/bundles/import",
            json={"preview_id": staged.json()["preview_id"]},
        )
        assert imported.status_code == 201, imported.text
        offline = imported.json()
        offline_base = (
            f"/api/v1/projects/{foundation.project_b}/bundle-investigations/"
            + offline["investigation_id"]
        )
        assert offline["job"]["from"] == collection_from
        assert offline["job"]["to"] == collection_to
        listing = await alice.get(f"/api/v1/projects/{foundation.project_b}/bundle-investigations")
        listed = next(
            item
            for item in listing.json()["items"]
            if item["investigation_id"] == offline["investigation_id"]
        )
        assert listed["job"]["from"] == collection_from
        assert listed["job"]["to"] == collection_to
        wide = {"process_ids": QUERY["process_ids"], "from": FROM, "to": TO, "limit": 200}
        response = await alice.post(offline_base + "/query", json=wide)
        assert response.status_code == 200, response.text
        expected = {
            event["event_id"]
            for event in EVENTS
            if event["timestamp_utc"] is not None
            and collection_from <= event["timestamp_utc"] < collection_to
        }
        assert {event["event_id"] for event in response.json()["items"]} == expected
        trace = await alice.post(
            offline_base + "/correlation",
            json={**wide, "mode": "exact", "field": "request_id", "value": "REQ-0042"},
        )
        assert trace.status_code == 200, trace.text
        assert trace.json()["items"]
        assert all(
            collection_from <= event["timestamp_utc"] < collection_to
            for event in trace.json()["items"]
        )
        changed = await alice.patch(
            offline_base + "/workspace", json=saved_payload(0, **{"from": FROM, "to": TO})
        )
        assert changed.status_code == 200, changed.text
        reexported = await preview_export(alice, foundation.project_b, offline["investigation_id"])
        assert reexported["document"]["origin"] == origin
        assert reexported["document"]["selection"]["from"] == FROM


@pytest.mark.parametrize("role", ["administrator", "inspector"])
async def test_both_roles_redacted_exchange_context_and_foreign_import_never_connects(
    foundation, tmp_path, monkeypatch, role
):
    account = foundation.database.administrator if role == "administrator" else foundation.alice
    async with foundation.client(account) as client:
        base, created = await capture(foundation, tmp_path, client)
        original = raw_checksums(tmp_path / "cache")
        saved = await client.patch(
            base + "/workspace", json=saved_payload(notes="REQ-0042 private note")
        )
        assert saved.status_code == 200, saved.text
        query = await client.post(base + "/query", json=QUERY)
        assert query.status_code == 200
        anchor = query.json()["items"][0]
        bookmark = await client.post(
            base + "/bookmarks",
            json=bookmark_payload(
                anchor["event_id"],
                revision=saved.json()["revision"],
                annotation="REQ-0042 annotation",
            ),
        )
        assert bookmark.status_code == 201, bookmark.text
        preview = await preview_export(
            client, foundation.project_a, created["job_id"], redact_terms=["REQ-0042"]
        )
        assert b"REQ-0042" not in encoded(preview["document"])
        assert preview["document"]["bookmarks"][0]["context"]["items"]
        assert "connections" not in preview["document"]["topology"]
        assert all(
            "connection_id" not in server for server in preview["document"]["topology"]["servers"]
        )
        blob, _url = await download_export(client, foundation.project_a, preview)
        assert original == raw_checksums(tmp_path / "cache")

        async def prohibited(*_args, **_kwargs):
            pytest.fail("Import/replay must never connect to a host.")

        monkeypatch.setattr(foundation.app.state.history, "launch", prohibited)
        async with foundation.database.sessions() as session:
            before = [
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.project_id == foundation.project_b)
                )
                for model in (HistoryJob, HistorySource, HistoryEvent)
            ]
        # Target B intentionally has no topology: foreign IDs are provenance only.
        imported_preview = await import_preview(client, foundation.project_b, blob)
        assert imported_preview.status_code == 200, imported_preview.text
        imported = await client.post(
            f"/api/v1/projects/{foundation.project_b}/bundles/import",
            json={"preview_id": imported_preview.json()["preview_id"]},
        )
        assert imported.status_code == 201, imported.text
        offline = imported.json()
        assert offline["offline"] and offline["project_id"] == foundation.project_b
        assert offline["document"]["origin"]["project_id"] == foundation.project_a
        assert offline["document"]["selection"]["notes"] == "[REDACTED] private note"
        offline_base = f"/api/v1/projects/{foundation.project_b}/bundle-investigations/{offline['investigation_id']}"
        replay = await client.post(offline_base + "/query", json={**QUERY, "limit": 2})
        assert replay.status_code == 200, replay.text
        assert all(event["project_id"] == foundation.project_b for event in replay.json()["items"])
        assert replay.json()["next_cursor"]
        page2 = await client.post(
            offline_base + "/query",
            json={**QUERY, "cursor": replay.json()["next_cursor"], "limit": 2},
        )
        assert page2.status_code == 200
        assert not {event["event_id"] for event in replay.json()["items"]} & {
            event["event_id"] for event in page2.json()["items"]
        }
        context = await client.post(
            offline_base + f"/events/{anchor['event_id']}/context",
            json={"from": QUERY["from"], "to": QUERY["to"], "filter": {"include": ["unmatched"]}},
        )
        assert context.status_code == 200, context.text
        assert any(not item["matches_filter"] for item in context.json()["items"])
        assert (await client.get(offline_base)).json()["document"] == offline["document"]
        async with foundation.database.sessions() as session:
            after = [
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.project_id == foundation.project_b)
                )
                for model in (HistoryJob, HistorySource, HistoryEvent)
            ]
        assert before == after


async def test_guessed_export_import_preview_download_offline_and_context_routes(
    foundation, tmp_path
):
    async with foundation.client(foundation.alice) as alice:
        base, created = await capture(foundation, tmp_path, alice)
        preview = await preview_export(alice, foundation.project_a, created["job_id"])
        blob, url = await download_export(alice, foundation.project_a, preview)
        uploaded = await import_preview(alice, foundation.project_a, blob)
        assert uploaded.status_code == 200
        import_id = uploaded.json()["preview_id"]
        async with foundation.client(foundation.bob) as bob:
            for client in (bob,):
                assert (
                    await client.post(
                        f"/api/v1/projects/{foundation.project_a}/bundles/export/preview",
                        json={"investigation_id": created["job_id"]},
                    )
                ).status_code == 404
                assert (
                    await client.post(
                        f"/api/v1/projects/{foundation.project_a}/bundles/export",
                        json={"preview_id": preview["preview_id"]},
                    )
                ).status_code == 404
                assert (
                    await client.post(
                        f"/api/v1/projects/{foundation.project_a}/bundles/import",
                        json={"preview_id": import_id},
                    )
                ).status_code == 404
                assert (await client.get(url)).status_code == 404
        for path, payload in (
            ("export/preview", {"investigation_id": created["job_id"]}),
            ("export", {"preview_id": preview["preview_id"]}),
            ("import", {"preview_id": import_id}),
        ):
            assert (
                await alice.post(
                    f"/api/v1/projects/{foundation.project_b}/bundles/{path}", json=payload
                )
            ).status_code == 404
        assert (
            await alice.get(url.replace(foundation.project_a, foundation.project_b))
        ).status_code == 404
        imported = await alice.post(
            f"/api/v1/projects/{foundation.project_a}/bundles/import",
            json={"preview_id": import_id},
        )
        assert imported.status_code == 201
        offline_id = imported.json()["investigation_id"]
        event_id = preview["document"]["events"][0]["event_id"]
        async with (
            foundation.client(foundation.bob) as bob,
            foundation.client(foundation.database.administrator) as admin,
        ):
            for client in (bob, admin):
                offline_base = (
                    f"/api/v1/projects/{foundation.project_a}/bundle-investigations/{offline_id}"
                )
                assert (await client.get(offline_base)).status_code == 404
                assert (await client.post(offline_base + "/query", json=QUERY)).status_code == 404
                assert (
                    await client.post(
                        offline_base + f"/events/{event_id}/context",
                        json={"from": QUERY["from"], "to": QUERY["to"]},
                    )
                ).status_code == 404
                assert (
                    await client.get(
                        f"/api/v1/projects/{foundation.project_a}/bundle-investigations"
                    )
                ).json()["items"] == []
        wrong_base = f"/api/v1/projects/{foundation.project_b}/bundle-investigations/{offline_id}"
        assert (await alice.get(wrong_base)).status_code == 404
        assert (await alice.post(wrong_base + "/query", json=QUERY)).status_code == 404
        # Same account, different authenticated session cannot consume preview/ticket.
        async with foundation.client(foundation.alice) as second_login:
            assert (await second_login.get(url)).status_code == 404
            assert (
                await second_login.post(
                    f"/api/v1/projects/{foundation.project_a}/bundles/export",
                    json={"preview_id": preview["preview_id"]},
                )
            ).status_code == 404


async def test_stale_note_revision_and_preview_expiry_reject_old_grants(foundation, tmp_path):
    async with foundation.client(foundation.alice) as alice:
        base, created = await capture(foundation, tmp_path, alice)
        preview = await preview_export(alice, foundation.project_a, created["job_id"])
        _data, url = await download_export(alice, foundation.project_a, preview)
        changed = await alice.patch(base + "/workspace", json=saved_payload(notes="new note"))
        assert changed.status_code == 200
        grant = await alice.post(
            f"/api/v1/projects/{foundation.project_a}/bundles/export",
            json={"preview_id": preview["preview_id"]},
        )
        assert grant.status_code == 409, grant.text
        assert (await alice.get(url)).status_code == 409
        newer = await preview_export(alice, foundation.project_a, created["job_id"])
        async with foundation.database.sessions.begin() as session:
            await session.execute(
                update(BundlePreview)
                .where(
                    BundlePreview.project_id == foundation.project_a,
                    BundlePreview.id == newer["preview_id"],
                )
                .values(expires_us=0)
            )
        expired = await alice.post(
            f"/api/v1/projects/{foundation.project_a}/bundles/export",
            json={"preview_id": newer["preview_id"]},
        )
        assert expired.status_code == 410


async def test_corrupt_unsafe_or_future_bundle_rejected_without_private_commit(
    foundation, tmp_path
):
    async with foundation.client(foundation.alice) as alice:
        _base, created = await capture(foundation, tmp_path, alice)
        preview = await preview_export(alice, foundation.project_a, created["job_id"])
        valid = pack_bundle(preview["document"], 10_000_000)
        malformed = [valid[:-10], b"not a zip"]
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("../unsafe.json", "outside")
            archive.writestr("investigation.json", encoded(preview["document"]))
        malformed.append(stream.getvalue())
        preview["document"]["schema_version"] = "999"
        malformed.append(pack_bundle(preview["document"], 10_000_000))
        preview["document"]["schema_version"] = "1.0"
        preview["document"]["selection"]["notes"] = "\ud800"
        invalid_unicode = json.dumps(preview["document"], ensure_ascii=True).encode("ascii")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("investigation.json", invalid_unicode)
            archive.writestr(
                "manifest.json",
                encoded(
                    {
                        "schema_version": "1.0",
                        "files": [
                            {
                                "path": "investigation.json",
                                "bytes": len(invalid_unicode),
                                "sha256": hashlib.sha256(invalid_unicode).hexdigest(),
                            }
                        ],
                    }
                ),
            )
        malformed.append(stream.getvalue())
        async with foundation.database.sessions() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(OfflineInvestigation)
                .where(OfflineInvestigation.project_id == foundation.project_a)
            )
        for value in malformed:
            response = await import_preview(alice, foundation.project_a, value)
            assert response.status_code == 422, response.text
            assert response.json()["error"]["code"] == "INVALID_BUNDLE"
        async with foundation.database.sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(OfflineInvestigation)
                    .where(OfflineInvestigation.project_id == foundation.project_a)
                )
                == count
            )


async def test_real_composite_bundle_owner_foreign_keys_reject_forgery(foundation, tmp_path):
    async with foundation.client(foundation.alice) as alice:
        _base, created = await capture(foundation, tmp_path, alice)
        preview = await preview_export(alice, foundation.project_a, created["job_id"])
        blob, _url = await download_export(alice, foundation.project_a, preview)
        uploaded = await import_preview(alice, foundation.project_a, blob)
        imported = await alice.post(
            f"/api/v1/projects/{foundation.project_a}/bundles/import",
            json={"preview_id": uploaded.json()["preview_id"]},
        )
        assert imported.status_code == 201
        data = dict(
            token_hash="a" * 64,
            project_id=foundation.project_a,
            owner_user_id=foundation.bob.principal.user_id,
            auth_version=1,
            expires_us=9999999999999999,
        )
        statements = [
            insert(BundleDownload).values(
                **data, preview_id=preview["preview_id"], auth_session_hash="b" * 64
            ),
            insert(OfflineCursor).values(
                **data,
                investigation_id=imported.json()["investigation_id"],
                query_hash="c" * 64,
                row_offset=0,
            ),
            insert(OfflineAnalysis).values(
                project_id=foundation.project_a,
                investigation_id=imported.json()["investigation_id"],
                owner_user_id=foundation.bob.principal.user_id,
                revision=1,
                state={},
                bookmarks=[],
            ),
            insert(OfflineAnalysis).values(
                project_id=foundation.project_b,
                investigation_id=imported.json()["investigation_id"],
                owner_user_id=foundation.alice.principal.user_id,
                revision=1,
                state={},
                bookmarks=[],
            ),
        ]
        for statement in statements:
            with pytest.raises(IntegrityError):
                async with foundation.database.sessions.begin() as session:
                    await session.execute(statement)
        offline_id = imported.json()["investigation_id"]
        saved = await alice.patch(
            f"/api/v1/projects/{foundation.project_a}/bundle-investigations/{offline_id}/workspace",
            json=saved_payload(),
        )
        assert saved.status_code == 200
        with pytest.raises(IntegrityError):
            async with foundation.database.sessions.begin() as session:
                await session.execute(
                    update(OfflineAnalysis)
                    .where(
                        OfflineAnalysis.project_id == foundation.project_a,
                        OfflineAnalysis.investigation_id == offline_id,
                    )
                    .values(owner_user_id=foundation.bob.principal.user_id)
                )


async def test_imported_personal_edits_bookmarks_trace_and_reexport_preserve_original(
    foundation, tmp_path
):
    async with foundation.client(foundation.alice) as alice:
        _base, created = await capture(foundation, tmp_path, alice)
        preview = await preview_export(alice, foundation.project_a, created["job_id"])
        blob, _url = await download_export(alice, foundation.project_a, preview)
        staged = await import_preview(alice, foundation.project_b, blob)
        assert staged.status_code == 200
        imported = await alice.post(
            f"/api/v1/projects/{foundation.project_b}/bundles/import",
            json={"preview_id": staged.json()["preview_id"]},
        )
        assert imported.status_code == 201, imported.text
        offline = imported.json()
        original = offline["document"]
        offline_id = offline["investigation_id"]
        base = f"/api/v1/projects/{foundation.project_b}/bundle-investigations/{offline_id}"
        defaults = await alice.get(base + "/workspace")
        assert defaults.status_code == 200 and defaults.json()["revision"] == 0
        saved = await alice.patch(
            base + "/workspace",
            json=saved_payload(notes="Offline follow-up note", title="Follow-up"),
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["revision"] == 1 and saved.json()["notes"] == "Offline follow-up note"
        stale_preview = await preview_export(alice, foundation.project_b, offline_id)
        anchor = original["events"][0]
        bookmark = await alice.post(
            base + "/bookmarks",
            json=bookmark_payload(anchor["event_id"], revision=1, annotation="Offline annotation"),
        )
        assert bookmark.status_code == 201, bookmark.text
        bookmark_id = bookmark.json()["items"][0]["bookmark_id"]
        assert bookmark.json()["items"][0]["context"]["project_id"] == foundation.project_b
        assert (
            await alice.post(
                f"/api/v1/projects/{foundation.project_b}/bundles/export",
                json={"preview_id": stale_preview["preview_id"]},
            )
        ).status_code == 409
        updated = await alice.patch(
            base + f"/bookmarks/{bookmark_id}",
            json={
                "expected_revision": 2,
                "annotation": "Updated offline note",
                "pin_context": True,
            },
        )
        assert updated.status_code == 200 and updated.json()["revision"] == 3
        trace = await alice.post(
            base + "/correlation",
            json={**QUERY, "mode": "exact", "field": "request_id", "value": "REQ-0042"},
        )
        assert trace.status_code == 200, trace.text
        assert trace.json()["items"] and all(
            event["metadata"]["request_id"] == "REQ-0042" for event in trace.json()["items"]
        )
        assert all(event["project_id"] == foundation.project_b for event in trace.json()["items"])
        assert len(trace.json()["deltas"]) == len(trace.json()["items"])
        reexport = await preview_export(alice, foundation.project_b, offline_id)
        assert reexport["document"]["origin"] == original["origin"]
        assert reexport["document"]["events"] == original["events"]
        assert reexport["document"]["selection"]["notes"] == "Offline follow-up note"
        assert reexport["document"]["bookmarks"][0]["annotation"] == "Updated offline note"
        await download_export(alice, foundation.project_b, reexport)
        async with foundation.database.sessions() as session:
            evidence = await session.get(OfflineInvestigation, (foundation.project_b, offline_id))
            assert evidence.document == original
        deleted = await alice.request(
            "DELETE", base + f"/bookmarks/{bookmark_id}", json={"expected_revision": 3}
        )
        assert deleted.status_code == 200 and deleted.json()["items"] == []
        async with (
            foundation.client(foundation.bob) as bob,
            foundation.client(foundation.database.administrator) as admin,
        ):
            for client, denied_base in (
                (bob, base),
                (admin, base),
                (alice, base.replace(foundation.project_b, foundation.project_a)),
            ):
                assert (await client.get(denied_base + "/workspace")).status_code == 404
                assert (
                    await client.patch(denied_base + "/workspace", json=saved_payload())
                ).status_code == 404
                assert (await client.get(denied_base + "/bookmarks")).status_code == 404
                assert (
                    await client.post(
                        denied_base + "/bookmarks", json=bookmark_payload(anchor["event_id"])
                    )
                ).status_code == 404
                assert (
                    await client.patch(
                        denied_base + f"/bookmarks/{bookmark_id}",
                        json={"expected_revision": 0, "annotation": "forged", "pin_context": False},
                    )
                ).status_code == 404
                assert (
                    await client.request(
                        "DELETE",
                        denied_base + f"/bookmarks/{bookmark_id}",
                        json={"expected_revision": 0},
                    )
                ).status_code == 404
                assert (
                    await client.post(
                        denied_base + "/correlation",
                        json={**QUERY, "mode": "exact", "field": "request_id", "value": "REQ-0042"},
                    )
                ).status_code == 404

                assert (
                    await client.post(
                        denied_base + f"/bookmarks/{bookmark_id}/delete",
                        json={"expected_revision": 0},
                    )
                ).status_code == 404
                denied_project = denied_base.split("/")[4]
                assert (
                    await client.post(
                        f"/api/v1/projects/{denied_project}/bundles/export/preview",
                        json={"investigation_id": offline_id},
                    )
                ).status_code == 404


async def test_logout_while_bundle_worker_blocked_releases_auth_locks_and_denies_preview(
    foundation, tmp_path, monkeypatch
):
    import inspector.investigation_bundles as bundles

    async with foundation.client(foundation.alice) as alice:
        _base, created = await capture(foundation, tmp_path, alice)
        entered, release = threading.Event(), threading.Event()
        original = bundles.redact

        def blocked(*args, **kwargs):
            entered.set()
            assert release.wait(10)
            return original(*args, **kwargs)

        monkeypatch.setattr(bundles, "redact", blocked)
        task = asyncio.create_task(
            alice.post(
                f"/api/v1/projects/{foundation.project_a}/bundles/export/preview",
                json={"investigation_id": created["job_id"]},
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            logout = await asyncio.wait_for(alice.post("/api/v1/auth/logout", json={}), timeout=2)
            assert logout.status_code == 200, logout.text
        finally:
            release.set()
        denied = await asyncio.wait_for(task, timeout=5)
        assert denied.status_code == 401, denied.text
        async with foundation.database.sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(BundlePreview)
                    .where(
                        BundlePreview.project_id == foundation.project_a,
                        BundlePreview.owner_user_id == foundation.alice.principal.user_id,
                    )
                )
                == 0
            )


async def test_upload_admission_rejects_before_receiving_when_global_slots_busy(
    foundation, tmp_path
):
    async with foundation.client(foundation.alice) as alice:
        _base, created = await capture(foundation, tmp_path, alice)
        preview = await preview_export(alice, foundation.project_a, created["job_id"])
        blob = pack_bundle(preview["document"], 10_000_000)
        slots = foundation.app.state.history.bundle_upload_slots
        held = 0
        try:
            while not slots.locked():
                await slots.acquire()
                held += 1
            denied = await asyncio.wait_for(
                import_preview(alice, foundation.project_b, blob), timeout=2
            )
            assert denied.status_code == 429
            assert denied.json()["error"]["code"] == "BUNDLE_UPLOAD_LIMIT"
        finally:
            for _ in range(held):
                slots.release()
        accepted = await import_preview(alice, foundation.project_b, blob)
        assert accepted.status_code == 200, accepted.text


async def test_preview_cancel_ownership_active_session_quota_and_revoked_session_cleanup(
    foundation, tmp_path
):
    async with foundation.client(foundation.alice) as first:
        _base, created = await capture(foundation, tmp_path, first)
        previews = [
            await preview_export(first, foundation.project_a, created["job_id"]) for _ in range(4)
        ]
        cancel_path = f"/api/v1/projects/{foundation.project_a}/bundles/previews/{previews[0]['preview_id']}/cancel"
        async with foundation.client(foundation.alice) as second:
            full = await second.post(
                f"/api/v1/projects/{foundation.project_a}/bundles/export/preview",
                json={"investigation_id": created["job_id"]},
            )
            assert full.status_code == 429  # Other still-active login previews remain intact.
            assert (await second.post(cancel_path, json={})).status_code == 404
            assert (
                await first.post(
                    cancel_path.replace(foundation.project_a, foundation.project_b), json={}
                )
            ).status_code == 404
            async with (
                foundation.client(foundation.bob) as bob,
                foundation.client(foundation.database.administrator) as admin,
            ):
                assert (await bob.post(cancel_path, json={})).status_code == 404
                assert (await admin.post(cancel_path, json={})).status_code == 404
            assert (await first.post(cancel_path, json={})).status_code == 200
            await preview_export(second, foundation.project_a, created["job_id"])
        assert (await first.post("/api/v1/auth/logout", json={})).status_code == 200
    async with foundation.client(foundation.alice) as third:
        fresh = await preview_export(third, foundation.project_a, created["job_id"])
        assert fresh["preview_id"] not in {item["preview_id"] for item in previews}
        async with foundation.database.sessions() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(BundlePreview)
                .where(BundlePreview.owner_user_id == foundation.alice.principal.user_id)
            )
            assert count == 1
