"""Parsing workers stay bounded even when their HTTP request is cancelled."""

import asyncio
import threading

import pytest

from inspector.topology import cpu_work


async def test_cancelled_config_work_keeps_its_permit_until_worker_finishes():
    loop = asyncio.get_running_loop()
    started = [asyncio.Event() for _ in range(3)]
    releases = [threading.Event() for _ in range(3)]
    counter_lock = threading.Lock()
    active = peak = 0

    def parse(index):
        nonlocal active, peak
        with counter_lock:
            active += 1
            peak = max(peak, active)
        loop.call_soon_threadsafe(started[index].set)
        try:
            if not releases[index].wait(timeout=5):
                raise RuntimeError("Synthetic parse worker timed out.")
            return index
        finally:
            with counter_lock:
                active -= 1

    first = asyncio.create_task(cpu_work(lambda: parse(0)))
    second = asyncio.create_task(cpu_work(lambda: parse(1)))
    tasks = [first, second]
    try:
        await asyncio.wait_for(asyncio.gather(started[0].wait(), started[1].wait()), timeout=2)
        first.cancel()
        third = asyncio.create_task(cpu_work(lambda: parse(2)))
        tasks.append(third)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(started[2].wait(), timeout=0.1)
        assert not first.done(), "Cancellation released capacity while parsing still ran."
        releases[0].set()
        with pytest.raises(asyncio.CancelledError):
            await first
        await asyncio.wait_for(started[2].wait(), timeout=2)
        releases[2].set()
        assert await third == 2
        releases[1].set()
        assert await second == 1
        assert peak == 2 and active == 0
    finally:
        for release in releases:
            release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_worker_error_propagates_and_leaves_capacity_available():
    def invalid_config():
        raise ValueError("Synthetic invalid config.")

    with pytest.raises(ValueError, match="Synthetic invalid config"):
        await cpu_work(invalid_config)
    assert await cpu_work(lambda: "next validated config") == "next validated config"
