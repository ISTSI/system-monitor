"""Real copy/index cancellation at controlled I/O and commit boundaries."""

import asyncio
import copy
import hashlib
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session as SyncSession
from test_history import CASES, enable_demo, seed, start

from inspector import history, log_engine
from inspector.persistence.models import HistoryEvent, HistoryJob

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


def generated_source(foundation, tmp_path, monkeypatch):
    source = copy.deepcopy(
        next(
            item
            for item in history.local_manifest(foundation.app.state.config)
            if item["source_revision_id"] == "src-ingest-plain-00"
        )
    )
    path = tmp_path / "controlled-source.log"
    with path.open("wb") as stream:
        for number in range(10_000):
            stream.write(
                (
                    f"2026-10-16T12:00:00.123456Z INFO sequence={number:05d} payload="
                    + "x" * 400
                    + "\n"
                ).encode()
            )
    with path.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    source.update(local_path=str(path), file_sha256=checksum, estimated_bytes=path.stat().st_size)
    monkeypatch.setattr(history, "local_manifest", lambda config: [source])
    return path


async def assert_no_later_indexing(foundation, project_id, job_id, count):
    async with foundation.database.sessions() as session:
        rows = await session.scalar(
            select(func.count())
            .select_from(HistoryEvent)
            .where(HistoryEvent.project_id == project_id, HistoryEvent.job_id == job_id)
        )
        persisted = await session.get(HistoryJob, (project_id, job_id))
        assert rows == count == persisted.event_count
        assert persisted.status == "cancelled"


async def test_cancel_during_partial_copy_counts_bytes_and_cleans_temporary_file(
    foundation, tmp_path, monkeypatch
):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    origin = generated_source(foundation, tmp_path, monkeypatch)
    manager = foundation.app.state.history
    paused = threading.Event()
    release = threading.Event()
    original_open = Path.open

    class ControlledCopy:
        def __init__(self, stream):
            self.stream = stream
            self.reads = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def read(self, size):
            if self.reads == 1:
                paused.set()
                if not release.wait(5):
                    raise RuntimeError("Controlled copy was not released.")
                # Resume the real worker with its server-owned cancellation
                # token before the next I/O operation obtains more source bytes.
                next(
                    token
                    for (project_id, _), token in manager.tokens.items()
                    if project_id == foundation.project_a
                ).check()
            self.reads += 1
            return self.stream.read(size)

    def controlled_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        mode = args[0] if args else kwargs.get("mode", "r")
        return ControlledCopy(stream) if path == origin and mode == "rb" else stream

    monkeypatch.setattr(Path, "open", controlled_open)
    async with foundation.client(foundation.alice) as alice:
        created, _, _ = await start(alice, foundation.project_a, ["p-ingest-a"])
        task = manager.tasks[(foundation.project_a, created["job_id"])]
        try:
            assert await asyncio.to_thread(paused.wait, 2)
            partial_files = list((tmp_path / "cache").rglob("*.part"))
            assert len(partial_files) == 1 and partial_files[0].stat().st_size == 65_536
            began = time.perf_counter()
            response = await alice.post(
                f"/api/v1/projects/{foundation.project_a}/jobs/{created['job_id']}/cancel", json={}
            )
            assert response.status_code == 200, response.text
            release.set()
            await asyncio.wait_for(asyncio.shield(task), 2)
            assert time.perf_counter() - began < 2
        finally:
            manager.cancel(foundation.project_a, created["job_id"])
            release.set()
            await asyncio.wait_for(asyncio.shield(task), 5)
        stopped = (
            await alice.get(f"/api/v1/projects/{foundation.project_a}/jobs/{created['job_id']}")
        ).json()
        assert stopped["status"] == "cancelled" and stopped["event_count"] == 0
        assert stopped["downloaded_bytes"] == 65_536 < origin.stat().st_size
        assert stopped["expanded_bytes"] == 0
        assert stopped["coverage"][0]["bytes"] == 65_536
        assert stopped["coverage"][0]["status"] == "partial"
        assert stopped["coverage"][0]["error_code"] == "CANCELLED"
        assert not list((tmp_path / "cache").rglob("*.part"))
        assert not [path for path in (tmp_path / "cache").rglob("*") if path.is_file()]
        await assert_no_later_indexing(foundation, foundation.project_a, created["job_id"], 0)


async def test_cancel_after_committed_index_batch_preserves_partial_snapshot(
    foundation, tmp_path, monkeypatch
):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    origin = generated_source(foundation, tmp_path, monkeypatch)
    manager = foundation.app.state.history
    paused = threading.Event()
    release = threading.Event()
    committed = asyncio.Event()
    committed_counts = []
    original_iter = log_engine.iter_source_events

    def controlled_records(*args, **kwargs):
        for number, record in enumerate(original_iter(*args, **kwargs), 1):
            yield record
            if number == 3000:
                paused.set()
                if not release.wait(5):
                    raise RuntimeError("Controlled source was not released.")
                kwargs["cancellation"].check()

    def after_commit(session):
        for resource in session.identity_map.values():
            if (
                isinstance(resource, HistoryJob)
                and resource.project_id == foundation.project_a
                and resource.event_count > 0
            ):
                committed_counts.append(resource.event_count)
                committed.set()

    monkeypatch.setattr(log_engine, "iter_source_events", controlled_records)
    event.listen(SyncSession, "after_commit", after_commit)
    try:
        async with foundation.client(foundation.alice) as alice:
            created, _, _ = await start(alice, foundation.project_a, ["p-ingest-a"])
            task = manager.tasks[(foundation.project_a, created["job_id"])]
            try:
                assert await asyncio.to_thread(paused.wait, 2)
                await asyncio.wait_for(committed.wait(), 2)
                assert any(count >= 1000 for count in committed_counts)
                query = {
                    **CASES[0]["request"],
                    "process_ids": ["p-ingest-a"],
                    "filter": {"include": []},
                    "limit": 100,
                }
                first = await alice.post(
                    f"/api/v1/projects/{foundation.project_a}/investigations/{created['job_id']}/query",
                    json=query,
                )
                assert first.status_code == 200, first.text
                assert first.json()["items"] and first.json()["next_cursor"]
                assert first.json()["partial"] and first.json()["matched_count"] is None
                began = time.perf_counter()
                response = await alice.post(
                    f"/api/v1/projects/{foundation.project_a}/jobs/{created['job_id']}/cancel",
                    json={},
                )
                assert response.status_code == 200, response.text
                count_at_cancel = response.json()["event_count"]
                release.set()
                await asyncio.wait_for(asyncio.shield(task), 2)
                assert time.perf_counter() - began < 2
            finally:
                manager.cancel(foundation.project_a, created["job_id"])
                release.set()
                await asyncio.wait_for(asyncio.shield(task), 5)
            stopped = (
                await alice.get(f"/api/v1/projects/{foundation.project_a}/jobs/{created['job_id']}")
            ).json()
            assert stopped["status"] == "cancelled" and stopped["coverage_status"] == "partial"
            assert 1000 <= stopped["event_count"] == count_at_cancel <= 3000
            assert stopped["downloaded_bytes"] == origin.stat().st_size
            assert 0 < stopped["expanded_bytes"] <= origin.stat().st_size
            assert stopped["coverage"][0]["events"] == stopped["event_count"]
            assert stopped["coverage"][0]["bytes"] == stopped["downloaded_bytes"]
            assert stopped["coverage"][0]["status"] == "partial"
            assert not list((tmp_path / "cache").rglob("*.part"))
            next_page = await alice.post(
                f"/api/v1/projects/{foundation.project_a}/investigations/{created['job_id']}/query",
                json={**query, "cursor": first.json()["next_cursor"]},
            )
            assert next_page.status_code == 200, next_page.text
            assert (
                next_page.json()["source_snapshot_revision"]
                == first.json()["source_snapshot_revision"]
            )
            assert next_page.json()["partial"]
            assert not {row["event_id"] for row in first.json()["items"]} & {
                row["event_id"] for row in next_page.json()["items"]
            }
            await assert_no_later_indexing(
                foundation, foundation.project_a, created["job_id"], stopped["event_count"]
            )
    finally:
        event.remove(SyncSession, "after_commit", after_commit)
