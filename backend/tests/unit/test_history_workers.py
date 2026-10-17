"""Administrator worker ceilings apply to actual file work and job admission."""

import asyncio
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from inspector.config import parse_config
from inspector.history import HistoryManager


@pytest.fixture
def history_config():
    root = Path(__file__).resolve().parents[3]
    return parse_config((root / "examples/deployment-policy.example.yaml").read_bytes(), {})


async def test_reduced_archive_worker_ceiling_is_preserved(history_config):
    config = history_config
    config = replace(
        config, history_limits={**config.history_limits, "concurrent_archive_tasks": 1}
    )
    manager = HistoryManager(config, None, None)
    loop = asyncio.get_running_loop()
    first_started, second_started = asyncio.Event(), asyncio.Event()
    release_first = threading.Event()

    def first():
        loop.call_soon_threadsafe(first_started.set)
        assert release_first.wait(timeout=5)
        return "first"

    def second():
        loop.call_soon_threadsafe(second_started.set)
        return "second"

    jobs = []
    try:
        await manager.slots.acquire()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(manager.slots.acquire(), timeout=0.05)
        manager.slots.release()
        jobs.append(loop.run_in_executor(manager.executor, first))
        await asyncio.wait_for(first_started.wait(), timeout=2)
        jobs.append(loop.run_in_executor(manager.executor, second))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(second_started.wait(), timeout=0.05)
        release_first.set()
        assert await asyncio.gather(*jobs) == ["first", "second"]
    finally:
        release_first.set()
        await asyncio.gather(*jobs, return_exceptions=True)
        await manager.close()
