"""Atomic owned pin groups, independent retention and offline exchange in MariaDB."""

import copy

import pytest
from test_investigation_bundles import download_export, import_preview, preview_export
from test_investigations import EXACT, FROM, TO, bookmark_payload, capture, saved_payload

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


def pin_payload(revision=0, *, ids=None, description="Shared pin description"):
    return dict(
        expected_revision=revision,
        description=description,
        events=[
            {
                "event_id": event_id,
                "from": FROM,
                "to": TO,
                "filter": {"include": ["different query literal"]},
            }
            for event_id in (ids or EXACT["expected_event_ids"][:2])
        ],
    )


async def test_group_creation_is_atomic_scoped_revisioned_and_survives_expiry(foundation, tmp_path):
    async with foundation.client(foundation.alice) as alice:
        base, created = await capture(foundation, tmp_path, alice)
        standalone = await alice.post(
            base + "/bookmarks", json=bookmark_payload(EXACT["expected_event_ids"][2])
        )
        assert standalone.status_code == 201, standalone.text
        independent_id = standalone.json()["items"][0]["bookmark_id"]
        pinned = await alice.post(base + "/pins", json=pin_payload(1))
        assert pinned.status_code == 201, pinned.text
        result = pinned.json()
        assert result["revision"] == 2 and len(result["items"]) == 3
        group = result["pin_groups"][0]
        assert group["description"] == "Shared pin description" and len(group["bookmark_ids"]) == 2
        assert independent_id not in group["bookmark_ids"]
        by_id = {item["bookmark_id"]: item for item in result["items"]}
        rows = [by_id[bookmark_id] for bookmark_id in group["bookmark_ids"]]
        assert [row["event_id"] for row in rows] == EXACT["expected_event_ids"][:2]
        assert all(row["annotation"] == "" and row["pin_context"] for row in rows)
        assert all(
            len(row["context"]["items"]) == 1 and row["context"]["items"][0]["is_anchor"]
            for row in rows
        )
        assert all(row["context"]["items"][0]["matches_filter"] is False for row in rows)
        assert (await alice.post(base + "/pins", json=pin_payload(1))).status_code == 409
        partial = await alice.post(
            base + "/pins",
            json=pin_payload(2, ids=[EXACT["expected_event_ids"][3], "missing-event"]),
        )
        assert partial.status_code == 404, partial.text
        assert (await alice.get(base + "/bookmarks")).json() == result
        wrong = base.replace(foundation.project_a, foundation.project_b)
        assert (await alice.post(wrong + "/pins", json=pin_payload(2))).status_code == 404
        assert (
            await alice.patch(
                wrong + f"/pins/{group['id']}",
                json={"expected_revision": 2, "description": "forged"},
            )
        ).status_code == 404
        assert (
            await alice.post(wrong + f"/pins/{group['id']}/delete", json={"expected_revision": 2})
        ).status_code == 404
        for account in [foundation.bob, foundation.database.administrator]:
            async with foundation.client(account) as denied:
                assert (await denied.get(base + "/bookmarks")).status_code == 404
                assert (await denied.post(base + "/pins", json=pin_payload(2))).status_code == 404
                assert (
                    await denied.patch(
                        base + f"/pins/{group['id']}",
                        json={"expected_revision": 2, "description": "forged"},
                    )
                ).status_code == 404
                assert (
                    await denied.post(
                        base + f"/pins/{group['id']}/delete", json={"expected_revision": 2}
                    )
                ).status_code == 404
        forbidden = await alice.post(
            base + "/pins", json=pin_payload(2), headers={"x-csrf-token": "invalid"}
        )
        assert forbidden.status_code == 403
        saved = await alice.patch(base + "/workspace", json=saved_payload(2))
        assert saved.status_code == 200 and saved.json()["pin_groups"] == [group]
        edited = await alice.patch(
            base + f"/pins/{group['id']}",
            json={"expected_revision": 3, "description": "One updated description"},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["pin_groups"][0]["description"] == "One updated description"
        assert edited.json()["items"] == result["items"]
        expired = await alice.post(base + "/expire", json={"expected_revision": 4})
        assert expired.status_code == 200, expired.text
        retained = (await alice.get(base + "/bookmarks")).json()
        assert (
            retained["items"] == result["items"]
            and retained["pin_groups"] == edited.json()["pin_groups"]
        )
        removed = await alice.post(
            base + f"/bookmarks/{group['bookmark_ids'][0]}/delete", json={"expected_revision": 5}
        )
        assert removed.status_code == 200, removed.text
        assert removed.json()["pin_groups"][0]["bookmark_ids"] == group["bookmark_ids"][1:]
        deleted = await alice.post(
            base + f"/pins/{group['id']}/delete", json={"expected_revision": 6}
        )
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["pin_groups"] == []
        assert [item["bookmark_id"] for item in deleted.json()["items"]] == [independent_id]


async def test_group_export_import_offline_edit_and_reexport_preserve_evidence(
    foundation, tmp_path
):
    async with foundation.client(foundation.alice) as alice:
        base, created = await capture(foundation, tmp_path, alice)
        response = await alice.post(
            base + "/pins", json=pin_payload(description="Sensitive shared description")
        )
        assert response.status_code == 201, response.text
        source_group = response.json()["pin_groups"][0]
        exported = await preview_export(
            alice, foundation.project_a, created["job_id"], redact_terms=["Sensitive"]
        )
        assert (
            exported["document"]["pin_groups"][0]["description"] == "[REDACTED] shared description"
        )
        blob, _ = await download_export(alice, foundation.project_a, exported)
        staged = await import_preview(alice, foundation.project_b, blob)
        assert staged.status_code == 200, staged.text
        imported = await alice.post(
            f"/api/v1/projects/{foundation.project_b}/bundles/import",
            json={"preview_id": staged.json()["preview_id"]},
        )
        assert imported.status_code == 201, imported.text
        original = copy.deepcopy(imported.json()["document"])
        offline_id = imported.json()["investigation_id"]
        offline = f"/api/v1/projects/{foundation.project_b}/bundle-investigations/{offline_id}"
        restored = (await alice.get(offline + "/bookmarks")).json()
        assert restored["pin_groups"] == original["pin_groups"]
        assert all(
            item["context"]["project_id"] == foundation.project_b for item in restored["items"]
        )
        added = await alice.post(offline + "/pins", json=pin_payload(description="Offline group"))
        assert added.status_code == 201, added.text
        assert len(added.json()["pin_groups"]) == 2 and len(added.json()["items"]) == 4
        new_group = next(
            group for group in added.json()["pin_groups"] if group["id"] != source_group["id"]
        )
        missing = await alice.post(
            offline + "/pins",
            json=pin_payload(1, ids=[EXACT["expected_event_ids"][3], "missing-event"]),
        )
        assert missing.status_code == 404
        assert (await alice.get(offline + "/bookmarks")).json() == added.json()
        saved = await alice.patch(offline + "/workspace", json=saved_payload(1))
        assert saved.status_code == 200 and saved.json()["pin_groups"] == added.json()["pin_groups"]
        edited = await alice.patch(
            offline + f"/pins/{new_group['id']}",
            json={"expected_revision": 2, "description": "Offline shared update"},
        )
        assert edited.status_code == 200, edited.text
        reexported = await preview_export(alice, foundation.project_b, offline_id)
        assert reexported["document"]["pin_groups"] == edited.json()["pin_groups"]
        assert "pin_groups" not in reexported["document"]["selection"]
        assert reexported["document"]["events"] == original["events"]
        await download_export(alice, foundation.project_b, reexported)
        removed = await alice.post(
            offline + f"/bookmarks/{new_group['bookmark_ids'][0]}/delete",
            json={"expected_revision": 3},
        )
        assert removed.status_code == 200, removed.text
        assert (
            next(group for group in removed.json()["pin_groups"] if group["id"] == new_group["id"])[
                "bookmark_ids"
            ]
            == new_group["bookmark_ids"][1:]
        )
        deleted = await alice.post(
            offline + f"/pins/{new_group['id']}/delete", json={"expected_revision": 4}
        )
        assert deleted.status_code == 200 and len(deleted.json()["pin_groups"]) == 1
        assert deleted.json()["pin_groups"][0]["id"] == source_group["id"]


@pytest.mark.parametrize("offline", [False, True])
async def test_pin_selection_replacement_is_atomic_and_keeps_group_identity(
    foundation, tmp_path, offline
):
    async with foundation.client(foundation.alice) as alice:
        base, created = await capture(foundation, tmp_path, alice)
        independent = await alice.post(
            base + "/bookmarks", json=bookmark_payload(EXACT["expected_event_ids"][3])
        )
        assert independent.status_code == 201, independent.text
        independent_id = independent.json()["items"][0]["bookmark_id"]
        response = await alice.post(base + "/pins", json=pin_payload(1))
        assert response.status_code == 201, response.text
        if offline:
            exported = await preview_export(alice, foundation.project_a, created["job_id"])
            blob, _ = await download_export(alice, foundation.project_a, exported)
            staged = await import_preview(alice, foundation.project_b, blob)
            assert staged.status_code == 200, staged.text
            imported = await alice.post(
                f"/api/v1/projects/{foundation.project_b}/bundles/import",
                json={"preview_id": staged.json()["preview_id"]},
            )
            assert imported.status_code == 201, imported.text
            base = (
                f"/api/v1/projects/{foundation.project_b}/bundle-investigations/"
                + imported.json()["investigation_id"]
            )
        before = (await alice.get(base + "/bookmarks")).json()
        group = before["pin_groups"][0]
        revision = before["revision"]
        url = base + f"/pins/{group['id']}"
        replacement_ids = list(reversed(EXACT["expected_event_ids"][1:4]))
        payload = pin_payload(revision, ids=replacement_ids, description="Changed selection")
        invalid = copy.deepcopy(payload)
        invalid["events"][-1]["event_id"] = "missing-selected-event"
        rejected = await alice.patch(url, json=invalid)
        assert rejected.status_code == 404, rejected.text
        assert (await alice.get(base + "/bookmarks")).json() == before
        # Every replacement has the same owner, project and CSRF protections.
        wrong_project = foundation.project_a if offline else foundation.project_b
        wrong = url.replace(
            f"/projects/{foundation.project_b if offline else foundation.project_a}/",
            f"/projects/{wrong_project}/",
        )
        assert (await alice.patch(wrong, json=payload)).status_code == 404
        async with foundation.client(foundation.bob) as bob:
            assert (await bob.patch(url, json=payload)).status_code == 404
        assert (
            await alice.patch(url, json=payload, headers={"x-csrf-token": "invalid"})
        ).status_code == 403
        updated = await alice.patch(url, json=payload)
        assert updated.status_code == 200, updated.text
        after = updated.json()
        assert after["revision"] == revision + 1 and len(after["pin_groups"]) == 1
        changed = after["pin_groups"][0]
        assert changed["id"] == group["id"] and changed["created_us"] == group["created_us"]
        assert changed["description"] == "Changed selection"
        assert not set(group["bookmark_ids"]) & set(changed["bookmark_ids"])
        assert len(after["items"]) == 4
        by_id = {item["bookmark_id"]: item for item in after["items"]}
        assert [by_id[key]["event_id"] for key in changed["bookmark_ids"]] == replacement_ids
        assert by_id[independent_id] == next(
            item for item in before["items"] if item["bookmark_id"] == independent_id
        )
        assert all(
            len(by_id[key]["context"]["items"]) == 1
            and by_id[key]["context"]["items"][0]["is_anchor"]
            for key in changed["bookmark_ids"]
        )
        assert (await alice.patch(url, json=payload)).status_code == 409
        assert (await alice.get(base + "/bookmarks")).json() == after
        if not offline:
            expired = await alice.post(
                base + "/expire", json={"expected_revision": after["revision"]}
            )
            assert expired.status_code == 200, expired.text
            retained = (await alice.get(base + "/bookmarks")).json()
            missing = await alice.patch(
                url, json={**payload, "expected_revision": retained["revision"]}
            )
            assert missing.status_code == 404
            assert (await alice.get(base + "/bookmarks")).json() == retained
            edited = await alice.patch(
                url,
                json={"expected_revision": retained["revision"], "description": "After expiry"},
            )
            assert edited.status_code == 200, edited.text
            assert edited.json()["items"] == retained["items"]
            assert edited.json()["pin_groups"][0] == {**changed, "description": "After expiry"}
        else:
            reexported = await preview_export(
                alice, foundation.project_b, imported.json()["investigation_id"]
            )
            assert reexported["document"]["pin_groups"] == after["pin_groups"]
            assert len(reexported["document"]["bookmarks"]) == 4
