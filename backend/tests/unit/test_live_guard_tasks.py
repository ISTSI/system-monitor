"""Concurrent live readers share only in-flight validation, never completed grants."""

import asyncio

import pytest

from inspector.domain import Principal
from inspector.errors import DomainError
from inspector.live import LiveManager


async def test_concurrent_guards_coalesce_and_one_cancel_cannot_cancel_other_readers():
    manager = object.__new__(LiveManager)
    manager.guard_tasks = {}
    entered, release, other_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = 0

    async def fresh(*args):
        nonlocal calls
        calls += 1
        entered.set()
        if args[1] == "other-project":
            other_entered.set()
        await release.wait()

    manager._fresh_guard = fresh
    actor = Principal("owner", "inspector", 1)
    args = (actor, "project", "live", {}, 1, "session-verifier")
    readers = [asyncio.create_task(manager._guard(*args)) for _ in range(6)]
    await entered.wait()
    assert calls == 1 and len(manager.guard_tasks) == 1
    other = asyncio.create_task(
        manager._guard(actor, "other-project", "live", {}, 1, "session-verifier")
    )
    await other_entered.wait()
    assert calls == 2
    assert set(manager.guard_tasks) == {("project", "live"), ("other-project", "live")}
    readers[0].cancel()
    with pytest.raises(asyncio.CancelledError):
        await readers[0]
    assert not next(iter(manager.guard_tasks.values())).cancelled()
    release.set()
    await asyncio.gather(*readers[1:], other)
    assert not manager.guard_tasks
    await manager._guard(*args)
    assert calls == 3  # The completed authorization is not cached.


async def test_failed_shared_guard_denies_every_waiter_and_cleans_its_task():
    manager = object.__new__(LiveManager)
    manager.guard_tasks = {}
    entered, release = asyncio.Event(), asyncio.Event()

    async def fresh(*args):
        entered.set()
        await release.wait()
        raise DomainError("DATABASE_UNAVAILABLE", "Persistence is unavailable.", 503)

    manager._fresh_guard = fresh
    actor = Principal("owner", "inspector", 1)
    readers = [
        asyncio.create_task(manager._guard(actor, "project", "live", {}, 1, "session-verifier"))
        for _ in range(3)
    ]
    await entered.wait()
    release.set()
    failures = await asyncio.gather(*readers, return_exceptions=True)
    assert all(
        isinstance(error, DomainError) and error.code == "DATABASE_UNAVAILABLE"
        for error in failures
    )
    assert not manager.guard_tasks
