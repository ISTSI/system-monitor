"""Caller cancellation cannot strand the committed recording activation."""

import asyncio

import pytest

from inspector.domain import Principal
from inspector.errors import DomainError
from inspector.live import LiveControlInput, LiveManager


@pytest.mark.parametrize("failure", [False, True])
async def test_cancelled_save_settles_its_worker_even_after_repeated_cancellation(failure):
    manager = object.__new__(LiveManager)
    activated, release = asyncio.Event(), asyncio.Event()
    settled = []

    async def save_worker(*args):
        activated.set()
        await release.wait()
        settled.append("partial" if failure else "backfilled")
        if failure:
            raise DomainError("RECORDING_BYTE_LIMIT", "The recording limit was reached.", 413)
        return {"recording": True}

    manager._save = save_worker
    caller = asyncio.create_task(
        manager.save(
            Principal("owner", "inspector", 1),
            "project",
            "monitor",
            LiveControlInput(workspace_id="page", lease_revision=1),
            "actual-cookie",
        )
    )
    await activated.wait()
    caller.cancel()
    await asyncio.sleep(0)
    caller.cancel()
    await asyncio.sleep(0)
    assert not caller.done() and not settled
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert settled == ["partial" if failure else "backfilled"]
