"""Existing system/account lifecycle preserves and isolates new historical captures."""

import copy

import pytest
from sqlalchemy import select
from test_history import enable_demo, finished, seed, start

from inspector.persistence.models import HistoryJob, Project

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


async def test_archive_blocks_only_its_own_active_collection_and_logout_requests_stop(
    foundation, tmp_path, monkeypatch
):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
        await seed(admin, foundation.project_b)

        async def leave_queued(*_args):
            pass

        monkeypatch.setattr(foundation.app.state.history, "launch", leave_queued)
        async with foundation.client(foundation.alice) as alice:
            capture, _, _ = await start(alice, foundation.project_a, ["p-ingest-a"])
            blocked = await admin.post(
                f"/api/v1/projects/{foundation.project_a}/archive", json={"expected_revision": 2}
            )
            assert blocked.status_code == 409
            assert blocked.json()["error"]["code"] == "COLLECTION_ACTIVE"
            other = await admin.post(
                f"/api/v1/projects/{foundation.project_b}/archive", json={"expected_revision": 2}
            )
            assert other.status_code == 200
            async with foundation.database.sessions.begin() as session:
                active_project = await session.get(Project, foundation.project_a)
                assert active_project is not None and not active_project.archived
            logout = await alice.post("/api/v1/auth/logout", json={})
            assert logout.status_code == 200
        async with foundation.database.sessions.begin() as session:
            job = await session.get(HistoryJob, (foundation.project_a, capture["job_id"]))
            assert job is not None and job.status == "cancel_requested"
        await foundation.app.state.history._collect(foundation.project_a, capture["job_id"])
        async with foundation.database.sessions.begin() as session:
            job = await session.get(HistoryJob, (foundation.project_a, capture["job_id"]))
            assert job is not None and job.status == "cancelled"
        archived = await admin.post(
            f"/api/v1/projects/{foundation.project_a}/archive", json={"expected_revision": 2}
        )
        assert archived.status_code == 200


async def test_delete_preview_lists_own_capture_and_preserves_original_event_names(
    foundation, tmp_path
):
    enable_demo(foundation, tmp_path)
    project_id = foundation.project_a
    base = f"/api/v1/projects/{project_id}"
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, project_id)
        capture, _, _ = await start(admin, project_id, ["p-ingest-a"])
        job = await finished(admin, project_id, capture["job_id"])
        assert job["status"] == "completed"
        impact = await admin.post(
            base + "/topology/delete-preview", json={"kind": "process", "id": "p-ingest-a"}
        )
        assert impact.status_code == 200
        assert impact.json()["investigations"] == [capture["job_id"]]
        current = (await admin.get(base + "/topology")).json()
        configuration = copy.deepcopy(current["config"])
        configuration["processes"] = [
            p for p in configuration["processes"] if p["id"] != "p-ingest-a"
        ]
        configuration["flows"] = [
            f
            for f in configuration["flows"]
            if "p-ingest-a" not in (f["source_process_id"], f["target_process_id"])
        ]
        allowed_flows = {flow["id"] for flow in configuration["flows"]}
        for view in configuration["views"]:
            view["nodes"] = [node for node in view["nodes"] if node["element_id"] != "p-ingest-a"]
            view["flow_ids"] = [flow for flow in view["flow_ids"] if flow in allowed_flows]
        changed = await admin.put(
            base + "/topology",
            json={"expected_revision": 2, "config": configuration, "confirmed_deletions": True},
        )
        assert changed.status_code == 200, changed.text
        response = await admin.post(
            base + f"/investigations/{capture['job_id']}/query",
            json={
                "process_ids": ["p-ingest-a"],
                "from": "2026-10-16T12:00:00.000000Z",
                "to": "2026-10-16T12:00:02.000000Z",
            },
        )
        assert response.status_code == 200
        assert response.json()["items"]
        assert all(
            event["process_name_snapshot"] == "ingest-instance-a"
            for event in response.json()["items"]
        )
        # Historical source FKs refer to typed immutable identities, preserving
        # collected bytes and notes' future targets after shared model deletion.
        async with foundation.database.sessions.begin() as session:
            preserved = await session.scalar(
                select(HistoryJob).where(HistoryJob.id == capture["job_id"])
            )
            assert preserved is not None and preserved.event_count > 0
