"""Saved investigation behaviour, immutable snapshots and real scoped MariaDB FKs."""

import asyncio
import copy
import hashlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from test_history import enable_demo, finished, seed, start

from inspector.persistence.investigation_models import InvestigationBookmark, SavedInvestigation
from inspector.persistence.models import HistoryEvent

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]
ROOT = Path(__file__).resolve().parents[3]
EXACT = json.loads((ROOT / "fixtures/expected/correlation-exact.json").read_text("utf-8"))
FROM = EXACT["from"]
TO = EXACT["to"]
FILTER = {"include": [], "include_mode": "any", "exclude": [], "case_sensitive": True}
QUERY = {"process_ids": EXACT["process_ids"], "from": FROM, "to": TO, "filter": FILTER}


def saved_payload(revision=0, **overrides):
    return {
        "expected_revision": revision,
        "title": "REQ-0042 incident",
        **QUERY,
        "per_process_filters": {},
        "layout": "split",
        "notes": "Private annotation <script>literal text</script>",
        "pinned": False,
        **overrides,
    }


def bookmark_payload(event_id, revision=0, **overrides):
    return {
        "expected_revision": revision,
        "event_id": event_id,
        "annotation": "Observed at source",
        "before": 3,
        "after": 3,
        "pin_context": True,
        "from": FROM,
        "to": TO,
        "filter": {**FILTER, "include": ["REQ-0042"]},
        "per_process_filters": {},
        **overrides,
    }


async def capture(foundation, tmp_path, client, project=None):
    project = project or foundation.project_a
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as administrator:
        await seed(administrator, project)
    created, _, _ = await start(client, project)
    result = await finished(client, project, created["job_id"])
    assert result["status"] == "completed", result
    return f"/api/v1/projects/{project}/investigations/{created['job_id']}", created


def raw_checksums(cache):
    return {
        str(path.relative_to(cache)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in cache.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("role", ["administrator", "inspector"])
async def test_both_roles_save_reopen_revision_and_exact_five_process_trace(
    foundation, tmp_path, role
):
    account = foundation.database.administrator if role == "administrator" else foundation.alice
    async with foundation.client(account) as client:
        base, created = await capture(foundation, tmp_path, client)
        defaults = await client.get(base + "/workspace")
        assert defaults.status_code == 200, defaults.text
        assert defaults.json()["revision"] == 0 and not defaults.json()["saved"]
        original = raw_checksums(tmp_path / "cache")
        assert original
        saved = await client.patch(base + "/workspace", json=saved_payload())
        assert saved.status_code == 200, saved.text
        state = saved.json()
        assert state["saved"] and state["revision"] == 1 and state["availability"] == "retained"
        assert state["collection_references"] == [created["job_id"]]
        assert state["layout"] == "split" and state["notes"] == saved_payload()["notes"]
        stale = await client.patch(base + "/workspace", json=saved_payload())
        assert stale.status_code == 409 and stale.json()["error"]["code"] == "REVISION_CONFLICT"
        invalid_scope = await client.patch(
            base + "/workspace", json=saved_payload(1, process_ids=["foreign-process"])
        )
        assert invalid_scope.status_code == 404
        exact = await client.post(
            base + "/correlation",
            json={**QUERY, "mode": "exact", "field": "request_id", "value": "REQ-0042"},
        )
        assert exact.status_code == 200, exact.text
        trace = exact.json()
        assert [item["event_id"] for item in trace["items"]] == EXACT["expected_event_ids"]
        assert {item["process_id"] for item in trace["items"]} == set(EXACT["process_ids"])
        assert [item["timestamp_us"] for item in trace["items"]] == sorted(
            item["timestamp_us"] for item in trace["items"]
        )
        assert trace["deltas"][0]["delta_us"] is None
        for previous, current, delta in zip(
            trace["items"][:-1], trace["items"][1:], trace["deltas"][1:], strict=True
        ):
            assert delta["event_id"] == current["event_id"]
            assert delta["delta_us"] == current["timestamp_us"] - previous["timestamp_us"]
        assert trace["warning"]
        literal = await client.post(
            base + "/correlation",
            json={**QUERY, "mode": "literal", "field": "request_id", "value": "REQ-0042"},
        )
        assert literal.status_code == 200, literal.text
        assert any("request_id=REQ-00420" in item["raw_line"] for item in literal.json()["items"])
        assert not any("request_id=REQ-00420" in item["raw_line"] for item in trace["items"])
        assert raw_checksums(tmp_path / "cache") == original
    # Closing the HTTP client and creating a new login restores state from MariaDB.
    async with foundation.client(account) as reopened:
        assert (await reopened.get(base + "/workspace")).json() == state


async def test_bookmark_source_context_pin_expiry_and_immutable_names(foundation, tmp_path):
    async with foundation.client(foundation.alice) as client:
        base, created = await capture(foundation, tmp_path, client)
        event_id = EXACT["expected_event_ids"][0]
        original = raw_checksums(tmp_path / "cache")
        marked = await client.post(
            base + "/bookmarks", json=bookmark_payload(event_id, to="2026-10-16T12:00:00.000001Z")
        )
        assert marked.status_code == 201, marked.text
        state = marked.json()
        item = state["items"][0]
        assert state["revision"] == 1 and item["pin_context"]
        assert item["event_id"] == event_id and item["process_name_snapshot"] == "ingest-instance-a"
        context = item["context"]["items"]
        assert sum(row["is_anchor"] for row in context) == 1
        assert any(row["outside_time_bounds"] for row in context)
        assert any(row["matches_filter"] is False for row in context)
        source_positions = [
            (row["event"]["source"]["member_ordinal"] or 0, row["event"]["source"]["byte_start"])
            for row in context
        ]
        assert source_positions == sorted(source_positions)
        source_id = next(
            row["event"]["source"]["source_revision_id"] for row in context if row["is_anchor"]
        )
        details = await client.get(base + f"/sources/{source_id}/provenance")
        assert details.status_code == 200, details.text
        assert details.json()["raw_bytes_available"] and details.json()["retained_event_count"] > 0
        assert details.json()["checksum"] and details.json()["observed_from"]
        assert details.json()["limitations"]
        assert raw_checksums(tmp_path / "cache") == original
        # Shared topology and parser changes do not alter retained event/name snapshots.
        async with foundation.client(foundation.database.administrator) as administrator:
            current = (
                await administrator.get(f"/api/v1/projects/{foundation.project_a}/topology")
            ).json()
            document = copy.deepcopy(current["config"])
            document["processes"][0]["name"] = "Renamed after capture"
            document["parsers"][0]["name"] = "Parser renamed after capture"
            changed = await administrator.put(
                f"/api/v1/projects/{foundation.project_a}/topology",
                json={"expected_revision": current["revision"], "config": document},
            )
            assert changed.status_code == 200, changed.text
        assert (await client.get(base + "/bookmarks")).json()["items"][0] == item
        pinned = await client.patch(base + "/workspace", json=saved_payload(1, pinned=True))
        assert pinned.status_code == 200, pinned.text
        blocked = await client.post(base + "/expire", json={"expected_revision": 2})
        assert blocked.status_code == 409
        assert (await client.delete(base)).status_code == 409
        assert raw_checksums(tmp_path / "cache") == original
        unpinned = await client.patch(base + "/workspace", json=saved_payload(2, pinned=False))
        assert unpinned.status_code == 200, unpinned.text
        expired = await client.post(base + "/expire", json={"expected_revision": 3})
        assert expired.status_code == 200, expired.text
        assert expired.json()["availability"] == "unavailable"
        details = await client.get(base + f"/sources/{source_id}/provenance")
        assert details.status_code == 200, details.text
        assert (
            not details.json()["raw_bytes_available"]
            and details.json()["retained_event_count"] == 0
        )
        restored = (await client.get(base + "/bookmarks")).json()["items"][0]
        assert restored["context"] == item["context"] and restored["availability"] == "retained"
        workspace = (await client.get(base + "/workspace")).json()
        assert (
            workspace["availability"] == "unavailable"
            and workspace["notes"] == saved_payload()["notes"]
        )
        query = await client.post(base + "/query", json=QUERY)
        assert query.status_code == 200, query.text
        assert query.json()["partial"] and not query.json()["items"]
        assert all(source["status"] == "unavailable" for source in query.json()["coverage"])
        assert (
            await client.patch(
                base + "/workspace", json=saved_payload(workspace["revision"], pinned=True)
            )
        ).status_code == 410
        assert not raw_checksums(tmp_path / "cache")
        assert (await client.delete(base)).status_code == 409
        removed = await client.post(
            base + f"/bookmarks/{item['bookmark_id']}/delete",
            json={"expected_revision": workspace["revision"]},
        )
        assert removed.status_code == 200 and removed.json()["items"] == []
        assert (await client.delete(base)).status_code == 200


async def test_every_personal_content_route_rejects_wrong_owner_system_and_csrf(
    foundation, tmp_path
):
    async with foundation.client(foundation.alice) as alice:
        base, created = await capture(foundation, tmp_path, alice)
        marked = await alice.post(
            base + "/bookmarks", json=bookmark_payload(EXACT["expected_event_ids"][0])
        )
        assert marked.status_code == 201, marked.text
        bookmark = marked.json()["items"][0]["bookmark_id"]
        source = marked.json()["items"][0]["context"]["items"][0]["event"]["source"][
            "source_revision_id"
        ]
        routes = [
            ("GET", "/workspace", None),
            ("GET", f"/sources/{source}/provenance", None),
            ("PATCH", "/workspace", saved_payload(1)),
            ("GET", "/bookmarks", None),
            ("POST", "/bookmarks", bookmark_payload(EXACT["expected_event_ids"][0], 1)),
            (
                "PATCH",
                f"/bookmarks/{bookmark}",
                {"expected_revision": 1, "annotation": "forged", "pin_context": False},
            ),
            ("POST", f"/bookmarks/{bookmark}/delete", {"expected_revision": 1}),
            ("POST", "/expire", {"expected_revision": 1}),
            ("POST", "/correlation", {**QUERY, "value": "REQ-0042"}),
        ]
        wrong = f"/api/v1/projects/{foundation.project_b}/investigations/{created['job_id']}"
        for method, suffix, payload in routes:
            response = await alice.request(method, wrong + suffix, json=payload)
            assert response.status_code == 404, (method, suffix, response.text)
        for account in (foundation.bob, foundation.database.administrator):
            async with foundation.client(account) as stranger:
                for method, suffix, payload in routes:
                    response = await stranger.request(method, base + suffix, json=payload)
                    assert response.status_code == 404, (
                        account.principal.role,
                        method,
                        suffix,
                        response.text,
                    )
        csrf = alice.headers.pop("x-csrf-token")
        response = await alice.patch(base + "/workspace", json=saved_payload(1))
        assert response.status_code == 403
        alice.headers["x-csrf-token"] = csrf


async def test_exact_correlation_json_field_paths_preserve_punctuation_quotes_and_unicode(
    foundation, tmp_path
):
    async with foundation.client(foundation.alice) as client:
        base, created = await capture(foundation, tmp_path, client)
        identity = EXACT["expected_event_ids"][0]
        keys = ["request.id", 'quote"field', "pole-ż"]
        async with foundation.database.sessions.begin() as session:
            event = await session.get(
                HistoryEvent, (foundation.project_a, created["job_id"], identity)
            )
            payload = copy.deepcopy(event.payload)
            payload["metadata"].update({key: "punctuation-value" for key in keys})
            payload["metadata"][r"pole-\u017c"] = "literal-sequence-value"
            event.payload = payload
        for key in keys:
            result = await client.post(
                base + "/correlation",
                json={**QUERY, "mode": "exact", "field": key, "value": "punctuation-value"},
            )
            assert result.status_code == 200, (key, result.text)
            assert [item["event_id"] for item in result.json()["items"]] == [identity], key
        for key, expected in [("pole-ż", []), (r"pole-\u017c", [identity])]:
            result = await client.post(
                base + "/correlation",
                json={**QUERY, "mode": "exact", "field": key, "value": "literal-sequence-value"},
            )
            assert result.status_code == 200, result.text
            assert [item["event_id"] for item in result.json()["items"]] == expected, key


async def test_mariadb_bookmark_owner_event_project_constraints_and_stale_edits(
    foundation, tmp_path
):
    async with foundation.client(foundation.alice) as client:
        base, created = await capture(foundation, tmp_path, client)
        result = await client.post(
            base + "/bookmarks", json=bookmark_payload(EXACT["expected_event_ids"][0])
        )
        assert result.status_code == 201, result.text
        identity = result.json()["items"][0]["bookmark_id"]
        async with foundation.database.sessions() as session:
            row = await session.get(
                InvestigationBookmark, (foundation.project_a, created["job_id"], identity)
            )
            values = {
                column.key: copy.deepcopy(getattr(row, column.key))
                for column in InvestigationBookmark.__table__.columns
            }
        for overrides in (
            {"owner_user_id": foundation.bob.principal.user_id},
            {"project_id": foundation.project_b},
            {"reference_event_id": "foreign-event"},
        ):
            async with foundation.database.sessions() as session:
                with pytest.raises(IntegrityError):
                    await session.execute(
                        insert(InvestigationBookmark).values(
                            **{**values, "id": str(uuid4()), **overrides}
                        )
                    )
                    await session.commit()
                await session.rollback()
        for overrides in (
            {"owner_user_id": foundation.bob.principal.user_id},
            {"project_id": foundation.project_b},
            {"reference_event_id": "foreign-event"},
        ):
            async with foundation.database.sessions() as session:
                with pytest.raises(IntegrityError):
                    await session.execute(
                        update(InvestigationBookmark)
                        .where(
                            InvestigationBookmark.project_id == foundation.project_a,
                            InvestigationBookmark.job_id == created["job_id"],
                            InvestigationBookmark.id == identity,
                        )
                        .values(**overrides)
                    )
                    await session.commit()
                await session.rollback()
        async with foundation.database.sessions() as session:
            with pytest.raises(IntegrityError):
                await session.execute(
                    update(SavedInvestigation)
                    .where(
                        SavedInvestigation.project_id == foundation.project_a,
                        SavedInvestigation.job_id == created["job_id"],
                    )
                    .values(owner_user_id=foundation.bob.principal.user_id)
                )
                await session.commit()
            await session.rollback()
        updates = await asyncio.gather(
            *(
                client.patch(
                    base + f"/bookmarks/{identity}",
                    json={"expected_revision": 1, "annotation": text, "pin_context": True},
                )
                for text in ("left", "right")
            )
        )
        assert sorted(response.status_code for response in updates) == [200, 409]
        assert (await client.get(base + "/bookmarks")).json()["revision"] == 2


async def test_saved_analysis_survives_backend_restart_without_remote_dispatch(
    database, tmp_path, monkeypatch
):
    from dataclasses import replace

    import asyncssh
    from conftest import Foundation

    from inspector import services
    from inspector.app import create_app

    account = database.administrator
    async with database.sessions.begin() as session:
        project = await services.create_project(
            session, account.principal, "Restart evidence", "Synthetic retained capture"
        )
    config = replace(
        database.config,
        state_dir=str(tmp_path / "state"),
        cache_dir=str(tmp_path / "cache"),
        local_history_demo=True,
    )
    first = create_app(config)
    fixture = Foundation(database, config, first, account, account, project.id, project.id)
    async with first.router.lifespan_context(first):
        async with fixture.client(account) as client:
            base, created = await capture(fixture, tmp_path, client)
            response = await client.patch(base + "/workspace", json=saved_payload())
            assert response.status_code == 200, response.text
            marked = await client.post(
                base + "/bookmarks", json=bookmark_payload(EXACT["expected_event_ids"][0], 1)
            )
            assert marked.status_code == 201, marked.text
            stored = marked.json()
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Offline reopening attempted SSH.")

    monkeypatch.setattr(asyncssh, "connect", forbidden)
    reopened = create_app(config)
    fixture.app = reopened
    async with reopened.router.lifespan_context(reopened):
        async with fixture.client(account) as client:
            restored = await client.get(base + "/workspace")
            assert restored.status_code == 200, restored.text
            assert restored.json()["notes"] == saved_payload()["notes"]
            query = await client.post(base + "/query", json=QUERY)
            assert query.status_code == 200 and query.json()["items"], query.text
            assert (await client.get(base + "/bookmarks")).json() == stored
    assert calls == []


async def test_live_capture_saved_with_context_and_export_after_host_disconnection(
    foundation, tmp_path, monkeypatch
):
    import asyncssh
    from test_live import base as live_base
    from test_live import rows, synthetic, until, workspace
    from test_live import start as live_start

    async with synthetic(foundation, tmp_path) as (_paths, remote):
        async with foundation.client(foundation.alice) as client:
            work = await workspace(client, foundation.project_a)
            monitor = await live_start(
                client, foundation.project_a, work, EXACT["process_ids"], global_filter=FILTER
            )
            current = await until(
                client,
                foundation.project_a,
                monitor["session_id"],
                lambda value: len({row["process_id"] for row in rows(value)}) == 5,
            )
            control = {"workspace_id": work, "lease_revision": current["lease_revision"]}
            saved = await client.post(
                live_base(foundation.project_a) + f"/{monitor['session_id']}/save", json=control
            )
            assert saved.status_code == 200, saved.text
            investigation = saved.json()["investigation_id"]
            stopped = await client.post(
                live_base(foundation.project_a) + f"/{monitor['session_id']}/stop", json=control
            )
            assert stopped.status_code == 200, stopped.text
            assert not remote.commands and not remote.mutations
    # The synthetic listener and all active connections are now closed.
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Retained live investigation attempted SSH.")

    monkeypatch.setattr(asyncssh, "connect", forbidden)
    original = raw_checksums(tmp_path / "remote-cache")
    assert original
    async with foundation.client(foundation.alice) as client:
        base = f"/api/v1/projects/{foundation.project_a}/investigations/{investigation}"
        saved = await client.patch(base + "/workspace", json=saved_payload())
        assert saved.status_code == 200, saved.text
        response = await client.post(base + "/query", json=QUERY)
        assert response.status_code == 200, response.text
        assert {row["process_id"] for row in response.json()["items"]} == set(EXACT["process_ids"])
        event = response.json()["items"][0]
        marked = await client.post(base + "/bookmarks", json=bookmark_payload(event["event_id"], 1))
        assert marked.status_code == 201, marked.text
        assert marked.json()["items"][0]["context"]
        preview = await client.post(
            f"/api/v1/projects/{foundation.project_a}/bundles/export/preview",
            json={"investigation_id": investigation, "redact_terms": ["REQ-0042"]},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["document"]["events"]
        assert "REQ-0042" not in json.dumps(preview.json()["document"])
        assert raw_checksums(tmp_path / "remote-cache") == original
    assert calls == []


@pytest.mark.parametrize("operation", ["bookmarks", "expire"])
async def test_logout_while_capture_guard_blocked_prevents_private_mutation(
    foundation, tmp_path, monkeypatch, operation
):
    async with foundation.client(foundation.alice) as client:
        base, created = await capture(foundation, tmp_path, client)
        original = raw_checksums(tmp_path / "cache")
        manager = foundation.app.state.history
        enter, release = asyncio.Event(), asyncio.Event()
        original_guard = manager.use_capture

        @asynccontextmanager
        async def blocked_guard(project, job):
            enter.set()
            await release.wait()
            async with original_guard(project, job):
                yield

        monkeypatch.setattr(manager, "use_capture", blocked_guard)
        payload = (
            bookmark_payload(EXACT["expected_event_ids"][0])
            if operation == "bookmarks"
            else {"expected_revision": 0}
        )
        pending = asyncio.create_task(client.post(base + "/" + operation, json=payload))
        try:
            await asyncio.wait_for(enter.wait(), timeout=3)
            logout = await asyncio.wait_for(client.post("/api/v1/auth/logout", json={}), timeout=2)
            assert logout.status_code == 200, logout.text
        finally:
            release.set()
        denied = await asyncio.wait_for(pending, timeout=3)
        assert denied.status_code == 401, denied.text
        assert raw_checksums(tmp_path / "cache") == original
        async with foundation.database.sessions() as session:
            assert (
                await session.get(SavedInvestigation, (foundation.project_a, created["job_id"]))
                is None
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(InvestigationBookmark)
                    .where(
                        InvestigationBookmark.project_id == foundation.project_a,
                        InvestigationBookmark.job_id == created["job_id"],
                    )
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(HistoryEvent)
                    .where(
                        HistoryEvent.project_id == foundation.project_a,
                        HistoryEvent.job_id == created["job_id"],
                    )
                )
                == 38
            )
