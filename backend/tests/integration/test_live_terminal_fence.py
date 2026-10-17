"""A stale maintenance intent must not relabel a completed explicit Stop."""

import asyncio

import pytest
from sqlalchemy import func, select
from test_live import (
    PROCESSES,
    Socket,
    append,
    base,
    create_payload,
    start,
    status,
    synthetic,
    workspace,
)

from inspector import services
from inspector.errors import DomainError
from inspector.persistence.models import LiveSubscription, Workspace

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


async def test_stale_maintenance_stop_preserves_explicit_terminal_state_and_other_monitor(
    foundation, tmp_path, monkeypatch
):
    async with synthetic(foundation, tmp_path) as (paths, _captured):
        async with foundation.client(foundation.alice) as client:
            project = foundation.project_a
            work = await workspace(client, project)
            other_work = await workspace(client, project)
            target = await start(client, project, work, PROCESSES[:1])
            other = await start(client, project, other_work, PROCESSES[1:2])
            manager = foundation.app.state.live
            original_stop = manager.engine.stop
            original_apply = manager._apply_maintenance
            engine_stopped, stale_collected = asyncio.Event(), asyncio.Event()
            release_stop, release_maintenance = asyncio.Event(), asyncio.Event()
            maintenance_applied = asyncio.Event()

            async def pause_after_engine_stop(identifier):
                await original_stop(identifier)
                if identifier == target["session_id"] and not engine_stopped.is_set():
                    engine_stopped.set()
                    await release_stop.wait()

            async def pause_stale_intent(selected_project, identifier, terminal, error):
                if identifier == target["session_id"] and terminal == "interrupted":
                    assert selected_project == project and error == "SOURCE_STOPPED"
                    stale_collected.set()
                    await release_maintenance.wait()
                    try:
                        return await original_apply(selected_project, identifier, terminal, error)
                    finally:
                        maintenance_applied.set()
                return await original_apply(selected_project, identifier, terminal, error)

            monkeypatch.setattr(manager.engine, "stop", pause_after_engine_stop)
            monkeypatch.setattr(manager, "_apply_maintenance", pause_stale_intent)
            async with Socket(foundation.app, client, project, other) as healthy:
                assert healthy.handshake["type"] == "websocket.accept"
                await healthy.hello()
                await healthy.frame("snapshot")
                pending = asyncio.create_task(
                    client.post(
                        f"{base(project)}/{target['session_id']}/stop",
                        json={
                            "workspace_id": work,
                            "lease_revision": target["lease_revision"],
                        },
                    )
                )
                try:
                    await asyncio.wait_for(engine_stopped.wait(), 4)
                    await asyncio.wait_for(stale_collected.wait(), 4)
                    # Maintenance has observed ACTIVE + engine.stopped. Let the
                    # explicit HTTP operation commit its intended terminal state
                    # before the stale intent is allowed to acquire its lock.
                    release_stop.set()
                    stopped = await asyncio.wait_for(pending, 4)
                    assert stopped.status_code == 200, stopped.text
                    assert stopped.json()["status"] == "stopped"
                    assert stopped.json()["error_code"] is None
                    release_maintenance.set()
                    await asyncio.wait_for(maintenance_applied.wait(), 4)
                    final = await status(client, project, target["session_id"])
                    assert final["status"] == "stopped" and final["error_code"] is None
                    append(
                        paths[PROCESSES[1]],
                        b"2026-10-16T12:00:52Z HEALTHY-AFTER-STALE-STOP\n",
                    )
                    async with asyncio.timeout(4):
                        while True:
                            frame = await healthy.frame("events")
                            if any(
                                "HEALTHY-AFTER-STALE-STOP" in event["raw_line"]
                                for event in frame["payload"]["items"]
                            ):
                                break
                    assert frame["filter_version"] == other["filter_version"]
                    assert (await status(client, project, other["session_id"]))[
                        "status"
                    ] == "following"
                finally:
                    release_stop.set()
                    release_maintenance.set()
                    await asyncio.wait_for(pending, 5)


async def test_stale_maintenance_detach_preserves_explicit_attach_and_new_controller(
    foundation, tmp_path, monkeypatch
):
    async with synthetic(foundation, tmp_path) as (paths, _captured):
        async with foundation.client(foundation.alice) as client:
            project = foundation.project_a
            previous_work = await workspace(client, project)
            next_work = await workspace(client, project)
            live = await start(client, project, previous_work)
            manager = foundation.app.state.live
            original_apply = manager._apply_maintenance
            stale_collected, release, applied = asyncio.Event(), asyncio.Event(), asyncio.Event()

            async def pause_detach(selected_project, identifier, terminal, error):
                if identifier == live["session_id"] and terminal == "detach":
                    assert selected_project == project
                    stale_collected.set()
                    await release.wait()
                    try:
                        return await original_apply(selected_project, identifier, terminal, error)
                    finally:
                        applied.set()
                return await original_apply(selected_project, identifier, terminal, error)

            monkeypatch.setattr(manager, "_apply_maintenance", pause_detach)
            async with foundation.database.sessions.begin() as session:
                expired = await session.get(
                    Workspace, (project, previous_work), with_for_update=True
                )
                expired.state = "expired"
                expired.expires_us = services.utc_now_us() - 1
            try:
                await asyncio.wait_for(stale_collected.wait(), 4)
                attached = await client.post(
                    f"{base(project)}/{live['session_id']}/attach",
                    json={
                        "workspace_id": next_work,
                        "expected_lease_revision": live["lease_revision"],
                    },
                )
                assert attached.status_code == 200, attached.text
                transferred = attached.json()
                assert transferred["workspace_id"] == next_work
                assert transferred["lease_revision"] == live["lease_revision"] + 1
                assert transferred["detached"] is False
                release.set()
                await asyncio.wait_for(applied.wait(), 4)
                final = await status(client, project, live["session_id"])
                assert final["workspace_id"] == next_work
                assert final["lease_revision"] == transferred["lease_revision"]
                assert final["detached"] is False and final["status"] == "following"
                async with Socket(foundation.app, client, project, transferred) as controller:
                    assert controller.handshake["type"] == "websocket.accept"
                    await controller.hello()
                    await controller.frame("snapshot")
                    append(
                        paths[PROCESSES[0]],
                        b"2026-10-16T12:00:53Z ATTACHED-AFTER-STALE-DETACH\n",
                    )
                    async with asyncio.timeout(4):
                        while True:
                            frame = await controller.frame("events")
                            if any(
                                "ATTACHED-AFTER-STALE-DETACH" in event["raw_line"]
                                for event in frame["payload"]["items"]
                            ):
                                break
                    assert frame["workspace_id"] == next_work
                    assert frame["filter_version"] == transferred["filter_version"]
            finally:
                release.set()


@pytest.mark.parametrize("late_outcome", ["returns", "raises"])
async def test_explicit_stop_during_startup_preserves_terminal_state_and_other_monitor(
    foundation, tmp_path, monkeypatch, late_outcome
):
    async with synthetic(foundation, tmp_path) as (paths, _captured):
        async with foundation.client(foundation.alice) as client:
            project = foundation.project_a
            work = await workspace(client, project)
            other_work = await workspace(client, project)
            other = await start(client, project, other_work, PROCESSES[1:2])
            manager = foundation.app.state.live
            original_start = manager.engine.start
            entered, release = asyncio.Event(), asyncio.Event()
            captured_identity = []

            async def pause_start(identifier, *args, **kwargs):
                result = await original_start(identifier, *args, **kwargs)
                captured_identity.append(identifier)
                entered.set()
                await release.wait()
                if late_outcome == "raises":
                    raise DomainError("CANCELLED", "Synthetic late startup cancellation.", 409)
                return result

            monkeypatch.setattr(manager.engine, "start", pause_start)
            async with Socket(foundation.app, client, project, other) as healthy:
                assert healthy.handshake["type"] == "websocket.accept"
                await healthy.hello()
                await healthy.frame("snapshot")
                pending = asyncio.create_task(
                    client.post(base(project), json=await create_payload(client, project, work))
                )
                try:
                    await asyncio.wait_for(entered.wait(), 4)
                    listing = await client.get(base(project))
                    assert listing.status_code == 200, listing.text
                    target = next(
                        item for item in listing.json()["items"] if item["workspace_id"] == work
                    )
                    assert target["session_id"] == captured_identity[0]
                    assert target["status"] == "starting" and target["lease_revision"] == 1
                    stopped = await client.post(
                        f"{base(project)}/{target['session_id']}/stop",
                        json={"workspace_id": work, "lease_revision": 1},
                    )
                    assert stopped.status_code == 200, stopped.text
                    assert stopped.json()["status"] == "stopped"
                    assert stopped.json()["error_code"] is None
                    release.set()
                    creation = await asyncio.wait_for(pending, 5)
                    assert creation.status_code == 409, creation.text
                    assert creation.json()["error"]["code"] == "CANCELLED"
                    final = await status(client, project, target["session_id"])
                    assert final["status"] == "stopped" and final["error_code"] is None
                    async with foundation.database.sessions() as session:
                        subscriptions = await session.scalar(
                            select(func.count())
                            .select_from(LiveSubscription)
                            .where(
                                LiveSubscription.project_id == project,
                                LiveSubscription.session_id == target["session_id"],
                            )
                        )
                    assert subscriptions == 0
                    token = f"HEALTHY-AFTER-STARTUP-{late_outcome}"
                    append(
                        paths[PROCESSES[1]],
                        f"2026-10-16T12:00:54Z {token}\n".encode("ascii"),
                    )
                    async with asyncio.timeout(4):
                        while True:
                            frame = await healthy.frame("events")
                            if any(
                                token in event["raw_line"] for event in frame["payload"]["items"]
                            ):
                                break
                    assert (await status(client, project, other["session_id"]))[
                        "status"
                    ] == "following"
                finally:
                    release.set()
                    await asyncio.wait_for(pending, 5)
