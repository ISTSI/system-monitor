"""Unconnected topology servers persist in MariaDB and cannot start acquisition."""

import copy
import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from test_live import create_payload
from test_topology import config_for

from inspector.persistence.models import HistoryJob, LiveSession, Server

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


async def test_unconnected_server_roundtrip_assignment_undo_and_scoped_reference(foundation):
    project_id = foundation.project_a
    base = f"/api/v1/projects/{project_id}"
    document = config_for(project_id)
    server = document["servers"][0]
    original_connection = server["connection_id"]
    server["connection_id"] = None
    async with foundation.client(foundation.database.administrator) as client:
        response = await client.put(
            base + "/topology", json={"expected_revision": 1, "config": document}
        )
        assert response.status_code == 200, response.text
        assert response.json()["config"]["servers"][0]["connection_id"] is None
        exported = await client.get(base + "/config/export")
        assert exported.status_code == 200
        assert json.loads(exported.json()["content"])["servers"][0]["connection_id"] is None

        assigned = copy.deepcopy(response.json()["config"])
        assigned["servers"][0]["connection_id"] = original_connection
        response = await client.put(
            base + "/topology", json={"expected_revision": 2, "config": assigned}
        )
        assert response.status_code == 200, response.text
        undone = await client.post(base + "/topology/undo", json={"expected_revision": 3})
        assert undone.status_code == 200, undone.text
        assert undone.json()["config"]["servers"][0]["connection_id"] is None

    async with foundation.database.sessions.begin() as session:
        stored = await session.get(Server, (project_id, server["id"]))
        assert stored.connection_id is None
        # Optional does not weaken the project's foreign key for supplied IDs.
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    update(Server)
                    .where(Server.project_id == project_id, Server.id == server["id"])
                    .values(connection_id="missing-in-this-system")
                )


async def test_unconnected_process_rejects_http_collection_and_live_without_remote_access(
    foundation, monkeypatch
):
    project_id = foundation.project_a
    base = f"/api/v1/projects/{project_id}"
    document = config_for(project_id)
    for server in document["servers"]:
        server["connection_id"] = None
    document["connections"] = []
    async with foundation.client(foundation.database.administrator) as admin:
        saved = await admin.put(
            base + "/topology", json={"expected_revision": 1, "config": document}
        )
        assert saved.status_code == 200, saved.text

    remote = AsyncMock(side_effect=AssertionError("Map-only servers must not request access."))
    monkeypatch.setattr(foundation.app.state.live.access, "prepare_in_transaction", remote)
    monkeypatch.setattr(foundation.app.state.history.remote.access, "prepare", remote)
    async with foundation.client(foundation.alice) as client:
        workspace = await client.post(base + "/workspaces", json={})
        assert workspace.status_code == 201, workspace.text
        workspace_id = workspace.json()["workspace_id"]
        process_id = document["processes"][0]["id"]
        payload = {
            "workspace_id": workspace_id,
            "transport": "ssh",
            "process_ids": [process_id],
            "from": "2026-10-13T00:00:00.000000Z",
            "to": "2026-10-17T00:00:00.000000Z",
        }
        for suffix in ("/collections/plan", "/collections"):
            result = await client.post(base + suffix, json=payload)
            assert result.status_code == 409, result.text
            assert result.json()["error"]["code"] == "SERVER_NOT_CONNECTED"
        live = await client.post(
            base + "/live-sessions",
            json=await create_payload(client, project_id, workspace_id, [process_id]),
        )
        assert live.status_code == 409, live.text
        assert live.json()["error"]["code"] == "SERVER_NOT_CONNECTED"
        remote.assert_not_awaited()
    async with foundation.database.sessions() as session:
        assert not (
            await session.scalars(select(HistoryJob).where(HistoryJob.project_id == project_id))
        ).all()
        assert not (
            await session.scalars(select(LiveSession).where(LiveSession.project_id == project_id))
        ).all()
