"""A committed live filter version cannot label an unapplied engine snapshot."""

import asyncio
import json
import time

import pytest
from sqlalchemy import select
from test_live import PROCESSES, Socket, append, base, predicate, start, synthetic, workspace

from inspector.persistence.models import LiveSession

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


async def acknowledge(socket, version, sequence):
    await socket.incoming.put(
        {
            "type": "websocket.receive",
            "text": json.dumps(
                {
                    "protocol_version": 2,
                    "type": "ack",
                    "project_id": socket.project,
                    "workspace_id": socket.session["workspace_id"],
                    "session_id": socket.session["session_id"],
                    "filter_version": version,
                    "payload": {"last_seq": sequence},
                }
            ),
        }
    )


async def test_committed_filter_version_waits_for_engine_reset_before_snapshot_dispatch(
    foundation, tmp_path, monkeypatch
):
    async with synthetic(foundation, tmp_path) as (paths, captured):
        path = paths[PROCESSES[0]]
        path.write_bytes(
            b"2026-10-16T12:00:00Z OLD-FILTER-FENCE\n2026-10-16T12:00:01Z NEW-FILTER-FENCE\n"
        )
        async with foundation.client(foundation.alice) as client:
            work = await workspace(client, foundation.project_a)
            live = await start(
                client,
                foundation.project_a,
                work,
                global_filter=predicate("OLD-FILTER-FENCE"),
            )
            manager = foundation.app.state.live
            original = manager.engine.refilter
            entered, release = asyncio.Event(), asyncio.Event()

            async def delayed_reset(*args, **kwargs):
                entered.set()
                await release.wait()
                return await original(*args, **kwargs)

            monkeypatch.setattr(manager.engine, "refilter", delayed_reset)
            async with Socket(foundation.app, client, foundation.project_a, live) as socket:
                assert socket.handshake["type"] == "websocket.accept"
                await socket.hello()
                first = await socket.frame("snapshot")
                assert first["filter_version"] == 1
                assert len(first["payload"]["events"]) == 1
                assert "OLD-FILTER-FENCE" in first["payload"]["events"][0]["raw_line"]
                connections = frozenset(captured.connections)
                pending = asyncio.create_task(
                    client.put(
                        f"{base(foundation.project_a)}/{live['session_id']}/filters",
                        json={
                            "workspace_id": work,
                            "lease_revision": live["lease_revision"],
                            "expected_filter_version": 1,
                            "global_filter": predicate("NEW-FILTER-FENCE"),
                            "per_process_filters": {},
                            "requested_rows": 30,
                            "layout": "merged",
                        },
                    )
                )
                premature = []
                try:
                    await asyncio.wait_for(entered.wait(), 3)
                    async with foundation.database.sessions() as session:
                        committed = await session.scalar(
                            select(LiveSession.filter_version).where(
                                LiveSession.project_id == foundation.project_a,
                                LiveSession.id == live["session_id"],
                            )
                        )
                    assert committed == 2
                    assert manager.engine.sessions[live["session_id"]].filter_version == 1
                    # A legitimate old ACK may have been queued before commit.
                    await acknowledge(socket, 1, first["seq"])
                    deadline = time.monotonic() + 0.65
                    while (remaining := deadline - time.monotonic()) > 0:
                        try:
                            message = await socket.receive_raw(remaining)
                        except TimeoutError:
                            break
                        assert message["type"] == "websocket.send", message
                        frame = json.loads(message["text"])
                        if frame["filter_version"] != 1:
                            premature.append(frame)
                            break
                finally:
                    release.set()
                    response = await asyncio.wait_for(pending, 5)
                assert response.status_code == 200, response.text
                assert not premature, "The committed version labelled data before engine reset."
                replacement = await socket.frame("snapshot")
                assert replacement["filter_version"] == 2
                assert len(replacement["payload"]["events"]) == 1
                assert "NEW-FILTER-FENCE" in replacement["payload"]["events"][0]["raw_line"]
                await acknowledge(socket, 2, replacement["seq"])
                append(path, b"2026-10-16T12:00:02Z NEW-FILTER-FENCE AFTER-RESET-ACK\n")
                async with asyncio.timeout(4):
                    while True:
                        received = await socket.frame("events")
                        if any(
                            "AFTER-RESET-ACK" in event["raw_line"]
                            for event in received["payload"]["items"]
                        ):
                            break
                assert received["filter_version"] == 2
                assert not socket.task.done()
                assert frozenset(captured.connections) == connections
