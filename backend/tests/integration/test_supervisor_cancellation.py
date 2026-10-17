"""Real MariaDB lock connection survives cancellation of a health-check caller."""

import asyncio

import pytest
from sqlalchemy import text

from inspector.database import _lock_name

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


async def test_cancelled_readiness_waiter_does_not_poison_supervisor_connection(
    foundation, monkeypatch
):
    supervisor = foundation.app.state.supervisor
    original_probe = supervisor._healthy_locked
    started = asyncio.Event()
    probe_calls = 0

    async def delayed_probe():
        nonlocal probe_calls
        probe_calls += 1
        started.set()
        # This is actual in-flight MariaDB driver I/O on the lock connection,
        # not a substitute persistence implementation or a metadata-only test.
        await supervisor.connection.scalar(text("SELECT SLEEP(0.2)"))
        return await original_probe()

    monkeypatch.setattr(supervisor, "_healthy_locked", delayed_probe)
    waiter = asyncio.create_task(supervisor.healthy())
    await asyncio.wait_for(started.wait(), 1)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert await asyncio.wait_for(supervisor.healthy(), 1)
    assert probe_calls == 1
    assert not supervisor.connection.invalidated and not supervisor.failed
    observed_id = await supervisor.connection.scalar(text("SELECT CONNECTION_ID()"))
    await supervisor.connection.commit()
    assert observed_id == supervisor.connection_id
    async with foundation.client() as client:
        ready = await client.get("/api/v1/health/ready")
        assert ready.status_code == 200, ready.text
    # Fixture shutdown must drain/release this same valid connection cleanly.


async def test_lost_supervisor_lock_fails_closed_without_reacquisition(foundation):
    supervisor = foundation.app.state.supervisor
    name = _lock_name(supervisor.connection, "supervisor")
    assert (
        await supervisor.connection.scalar(text("SELECT RELEASE_LOCK(:name)"), {"name": name}) == 1
    )
    await supervisor.connection.commit()
    assert not await supervisor.healthy()
    assert supervisor.failed
    assert not await supervisor.healthy()
    async with foundation.client() as client:
        ready = await client.get("/api/v1/health/ready")
        assert ready.status_code == 503
    assert (
        await supervisor.connection.scalar(text("SELECT IS_USED_LOCK(:name)"), {"name": name})
        is None
    )
    await supervisor.connection.commit()
