"""Live behavioral scenarios use mutable byte objects, not message-text deduplication."""

import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager
from dataclasses import replace

import pytest

from inspector.errors import DomainError
from inspector.live_engine import LiveEngine, LiveLimits, LiveSource
from inspector.log_engine import LiteralFilter
from inspector.ssh_transport import Endpoint


class BytesFile:
    def __init__(self, data=b""):
        self.data = data

    async def read(self, size, offset):
        return self.data[offset : offset + size]

    async def size(self):
        return len(self.data)


class Files:
    def __init__(self, data=b""):
        self.file = BytesFile(data)
        self.opens = 0
        self.fail = False
        self.on_read = None

    @asynccontextmanager
    async def open(self, source):
        if self.fail:
            raise OSError("synthetic transport disconnected")
        self.opens += 1
        outer = self

        class Reader:
            handle = outer.file

            async def named(self):
                if outer.fail:
                    raise OSError("synthetic transport disconnected")
                return outer.file

            async def replace(self, handle):
                self.handle = handle

            async def release(self, handle):
                pass

        yield Reader()


def source(**changes):
    return replace(
        LiveSource(
            "project",
            "owner",
            "process",
            1,
            "approved-context",
            "/logs/app.log",
            "/logs",
            Endpoint("test.invalid", 22, "reader", "password", "key"),
        ),
        **changes,
    )


def line(message, second=0):
    return f"2026-10-17T12:00:{second:02d}Z {message}\n".encode()


async def until(predicate, seconds=2):
    async with asyncio.timeout(seconds):
        while not predicate():  # noqa: ASYNC110 - bounded assertion polling of the independent collector
            await asyncio.sleep(0.005)


@pytest.fixture
def limits():
    return LiveLimits(poll_seconds=0.01, merge_seconds=0.015, reconnect_max_seconds=0.02)


async def test_partial_utf8_and_seed_boundary_append_preserve_bytes(limits):
    initial = line("seed") + b"2026-10-17T12:00:01Z caf\xc3"
    files = Files(initial)
    engine = LiveEngine(limits, files.open)
    recorded = []

    async def record(session_id, events):
        recorded.extend(events)

    try:
        state = await engine.start("one", [source()], 20, on_events=record)
        assert [event["raw_line"] for event in state["events"]] == ["2026-10-17T12:00:00Z seed"]
        files.file.data += b"\xa9"
        await asyncio.sleep(0.04)
        assert engine.snapshot("one")["counters"]["received"] == 1
        files.file.data += b"\r\n"
        await until(lambda: engine.snapshot("one")["counters"]["received"] == 2)
        event = engine.snapshot("one")["events"][-1]
        assert event["raw_line"].endswith("café")
        assert event["source"]["byte_start"] == len(line("seed"))
        assert event["source"]["byte_end"] == len(files.file.data)
        assert recorded[-1]["_raw_bytes"].endswith(b"caf\xc3\xa9\r\n")
        assert (
            event["source"]["content_sha256"]
            == hashlib.sha256(recorded[-1]["_raw_bytes"]).hexdigest()
        )
        assert "_raw_bytes" not in event
    finally:
        await engine.close()


async def test_refilter_reveals_retained_hidden_events_without_reconnect(limits):
    files = Files(line("Straße") + line("hidden") + line("Straße"))
    engine = LiveEngine(limits, files.open)
    try:
        state = await engine.start(
            "one", [source()], 2, LiteralFilter(include=("STRASSE",), case_sensitive=False)
        )
        assert len(state["events"]) == 2
        assert len({event["event_id"] for event in state["events"]}) == 2
        old_ids = {event["event_id"] for event in state["events"]}
        state = await engine.refilter("one", LiteralFilter())
        assert len(state["events"]) == 2
        assert any(event["raw_line"].endswith("hidden") for event in state["events"])
        assert old_ids <= {event["event_id"] for event in engine.retained_events("one")}
        assert state["filter_version"] == 2
        assert files.opens == 1
        assert engine.frames_since("one", 1, 1)[0]["type"] == "resync_required"
    finally:
        await engine.close()


async def test_shared_capture_has_independent_filters_stop_and_scope(limits):
    files = Files(line("alpha") + line("beta"))
    engine = LiveEngine(limits, files.open)
    try:
        await engine.start("one", [source()], 2, LiteralFilter(include=("alpha",)))
        await engine.start("two", [source()], 2, LiteralFilter(include=("beta",)))
        assert files.opens == 1
        assert len(engine.collectors) == 1
        await engine.refilter("one", LiteralFilter())
        assert len(engine.snapshot("two")["events"]) == 1
        await engine.stop("one")
        files.file.data += line("beta 2", 1)
        await until(lambda: engine.snapshot("two")["counters"]["received"] == 3)
        assert engine.snapshot("two")["state"] == "following"
        await engine.start("three", [source(project_id="other")], 2)
        assert files.opens == 2
        assert len(engine.collectors) == 2
    finally:
        await engine.close()


async def test_raw_eviction_replay_expiry_and_slow_reader_are_visible(limits):
    files = Files(line("first"))
    engine = LiveEngine(replace(limits, max_raw_events=3, max_replay_frames=3), files.open)
    try:
        await engine.start("one", [source()], 2)
        for index in range(1, 8):
            files.file.data += line(str(index), index)
            await until(
                lambda index=index: engine.snapshot("one")["counters"]["received"] == index + 1
            )
            await asyncio.sleep(0.025)
        state = engine.snapshot("one")
        assert state["counters"]["received"] == 8
        assert state["counters"]["retained"] == 3
        assert state["counters"]["evicted"] == 5
        assert state["sources"][0]["earliest_retained_offset"] > 0
        assert len(engine.sessions["one"].replay) <= 3
        replay = engine.frames_since("one", 0, 1)
        assert replay[0]["type"] == "resync_required"
        assert replay[0]["payload"]["snapshot"]["counters"]["evicted"] == 5
    finally:
        await engine.close()


async def test_rename_drains_old_object_and_copytruncate_resets_generation(limits):
    files = Files(line("initial"))
    engine = LiveEngine(limits, files.open)
    try:
        await engine.start("one", [source()], 2)
        old_generation = engine.snapshot("one")["sources"][0]["source_revision_id"]
        old = files.file
        old.data += line("old drain", 1)
        files.file = BytesFile(line("new file", 2))
        await until(lambda: engine.snapshot("one")["counters"]["received"] == 3)
        state = engine.snapshot("one")
        assert "RENAME_ROTATION_OBSERVED" in state["sources"][0]["warnings"]
        assert state["sources"][0]["source_revision_id"] != old_generation
        assert any(event["raw_line"].endswith("old drain") for event in state["events"])
        files.file.data = line("rewrite", 3)
        await until(
            lambda: "COPYTRUNCATE_OR_REWRITE" in engine.snapshot("one")["sources"][0]["warnings"]
        )
        await until(lambda: engine.snapshot("one")["counters"]["received"] == 4)
        assert engine.snapshot("one")["sources"][0]["gaps"] == 2
    finally:
        await engine.close()


async def test_seed_scans_matching_rows_under_limits_and_loads_older(limits):
    content = b"".join(
        line(("match" if index % 7 == 0 else "other") + str(index)) for index in range(12_000)
    )
    files = Files(content)
    engine = LiveEngine(replace(limits, max_seed_bytes=65_536), files.open)
    try:
        state = await engine.start("one", [source()], 400, LiteralFilter(include=("match",)))
        assert state["sources"][0]["seed_status"] == "seed_limit_reached"
        assert state["sources"][0]["scanned_from"] > 0
        before = len(state["events"])
        state = await engine.load_older("one", 500)
        assert len(state["events"]) > before
        assert files.opens == 1
        raw = sorted(engine.retained_events("one"), key=lambda event: event["source"]["byte_start"])
        assert all(
            first["source"]["byte_end"] == second["source"]["byte_start"]
            for first, second in zip(raw, raw[1:], strict=False)
        )
    finally:
        await engine.close()


async def test_idle_sources_do_not_hold_merge_and_late_arrivals_are_marked(limits):
    files = {str(index): Files() for index in range(5)}

    @asynccontextmanager
    async def opener(item):
        async with files[item.process_id].open(item) as reader:
            yield reader

    engine = LiveEngine(limits, opener)
    try:
        await engine.start("one", [source(process_id=str(index)) for index in range(5)], 20)
        files["0"].file.data += line("later", 9)
        await until(
            lambda: any(frame["type"] == "events" for frame in engine.sessions["one"].replay)
        )
        files["0"].file.data += line("earlier", 1)
        await until(
            lambda: any(
                event.get("late_arrival")
                for frame in engine.sessions["one"].replay
                for event in frame["payload"].get("events", [])
            )
        )
        state = engine.snapshot("one")
        assert state["counters"]["received"] == 2
        assert state["events"][0]["raw_line"].endswith("earlier")
        assert state["events"][0]["late_arrival"]
        assert all(item["state"] == "following" for item in state["sources"])
    finally:
        await engine.close()


async def test_reconnect_recovers_only_proven_offset_and_reports_gap(limits):
    files = Files(line("before"))
    engine = LiveEngine(limits, files.open)
    try:
        await engine.start("one", [source()], 10)
        files.fail = True
        await until(lambda: engine.snapshot("one")["sources"][0]["state"] == "reconnecting")
        files.file.data += line("during disconnect", 1)
        files.fail = False
        await until(lambda: engine.snapshot("one")["counters"]["received"] == 2)
        state = engine.snapshot("one")
        assert state["sources"][0]["gaps"] >= 1
        assert len({event["source"]["source_revision_id"] for event in state["events"]}) == 1
        assert files.opens >= 2
    finally:
        await engine.close()


async def test_guard_revocation_stops_silent_source_fail_closed(limits):
    files = Files()
    engine = LiveEngine(limits, files.open)
    denied = False

    async def guard():
        if denied:
            raise DomainError("SESSION_REVOKED", "The session was revoked.", 401)

    try:
        await engine.start("one", [source()], 10, guard=guard)
        denied = True
        await until(lambda: engine.snapshot("one")["state"] == "stopped")
        assert engine.snapshot("one")["error"] == "SESSION_REVOKED"
        assert not engine.collectors
    finally:
        await engine.close()


async def test_recording_failure_stops_only_affected_consumer(limits):
    files = Files()
    engine = LiveEngine(limits, files.open)

    async def failing_recorder(session_id, events):
        raise DomainError("DATABASE_UNAVAILABLE", "Database unavailable.", 503)

    try:
        await engine.start("one", [source()], 10, on_events=failing_recorder)
        await engine.start("two", [source()], 10)
        files.file.data += line("test")
        await until(lambda: engine.snapshot("one")["state"] == "stopped")
        await until(lambda: engine.snapshot("two")["counters"]["received"] == 1)
        assert engine.snapshot("one")["error"] == "DATABASE_UNAVAILABLE"
        assert engine.snapshot("two")["state"] == "following"
    finally:
        await engine.close()


async def test_disabled_recording_skips_callbacks_and_activation_backfills_original_bytes(limits):
    seed = line("seed")
    files = Files(seed)
    engine = LiveEngine(limits, files.open)
    recorded = []

    async def recorder(identifier, events):
        recorded.extend(event["_raw_bytes"] for event in events)

    try:
        await engine.start("one", [source()], 10, on_events=recorder, recording_enabled=False)
        first = line("before-save").replace(b"\n", b"\r\n")
        files.file.data += first
        await until(lambda: engine.snapshot("one")["counters"]["received"] == 2)
        assert not recorded
        session = engine.sessions["one"]
        session.recording_enabled = True
        await engine._record(session, engine.retained_events("one"))
        assert recorded == [seed, first]
        second = line("after-save")
        files.file.data += second
        await until(lambda: engine.snapshot("one")["counters"]["received"] == 3)
        assert recorded == [seed, first, second]
    finally:
        await engine.close()


async def test_shared_recording_activation_during_blocked_peer_commits_before_visibility(limits):
    files = Files()
    engine = LiveEngine(limits, files.open)
    peer_entered, peer_release = asyncio.Event(), asyncio.Event()
    late_entered, late_release = asyncio.Event(), asyncio.Event()
    persisted = []
    raw = line("save-during-peer").replace(b"\n", b"\r\n")

    async def peer_recorder(identifier, events):
        peer_entered.set()
        await peer_release.wait()

    async def late_recorder(identifier, events):
        assert [event["_raw_bytes"] for event in events] == [raw]
        late_entered.set()
        await late_release.wait()
        assert engine.snapshot("late")["counters"]["received"] == 0
        persisted.extend(event["_raw_bytes"] for event in events)

    try:
        await engine.start("peer", [source()], 10, on_events=peer_recorder)
        await engine.start("late", [source()], 10, on_events=late_recorder, recording_enabled=False)
        files.file.data += raw
        await asyncio.wait_for(peer_entered.wait(), 1)
        # Save commits its DB row before this synchronous flag change. The
        # in-flight batch is not retained yet, so retained backfill is empty.
        engine.sessions["late"].recording_enabled = True
        assert engine.retained_events("late") == []
        peer_release.set()
        await asyncio.wait_for(late_entered.wait(), 1)
        assert engine.snapshot("late")["counters"]["received"] == 0
        assert not persisted
        late_release.set()
        await until(lambda: engine.snapshot("late")["counters"]["received"] == 1)
        assert persisted == [raw]
        await engine.stop("peer")
        assert engine.snapshot("late")["state"] == "following"
    finally:
        peer_release.set()
        late_release.set()
        await engine.close()


async def test_oversized_partial_record_is_bounded_and_diagnostic(limits):
    files = Files()
    engine = LiveEngine(replace(limits, max_line_bytes=64), files.open)
    try:
        await engine.start("one", [source()], 10)
        files.file.data += line("x" * 200)[:-1]
        await until(lambda: engine.snapshot("one")["sources"][0]["pending_bytes"] > 64)
        collector = engine.sessions["one"].sources[0]
        assert len(collector.pending) == 64
        assert engine.snapshot("one")["counters"]["received"] == 0
        files.file.data += b"\n"
        await until(lambda: engine.snapshot("one")["counters"]["received"] == 1)
        state = engine.snapshot("one")
        assert not state["events"]
        assert state["diagnostics"][0]["parse_status"] == "oversized_line"
        assert state["diagnostics"][0]["timestamp_us"] is None
    finally:
        await engine.close()


async def test_session_rejects_cross_project_owner_and_filter_process(limits):
    engine = LiveEngine(limits, Files().open)
    with pytest.raises(ValueError):
        await engine.start("one", [source(), source(project_id="other", process_id="two")], 10)
    with pytest.raises(ValueError):
        await engine.start("two", [source()], 10, per_process={"other": LiteralFilter()})
    assert not engine.collectors


async def test_actual_serialized_byte_limits_and_stopped_retention(limits):
    files = Files()
    limits = replace(
        limits,
        max_line_bytes=1024,
        max_snapshot_bytes=32_768,
        max_frame_bytes=16_384,
        max_replay_bytes=40_000,
        max_stopped_sessions=2,
    )
    engine = LiveEngine(limits, files.open)
    try:
        await engine.start("one", [source()], 500)
        files.file.data += b"".join(line("\x01" * 900, index % 60) for index in range(100))
        await until(lambda: engine.snapshot("one")["counters"]["received"] == 100)
        await until(
            lambda: any(frame["type"] == "events" for frame in engine.sessions["one"].replay)
        )
        state = engine.snapshot("one")
        assert state["coverage"]["view_limit_reached"]
        assert len(json.dumps(state, ensure_ascii=False).encode()) < limits.max_snapshot_bytes
        assert engine.sessions["one"].replay_bytes <= limits.max_replay_bytes
        for frame in engine.sessions["one"].replay:
            assert (
                len(json.dumps(frame, ensure_ascii=False, separators=(",", ":")).encode())
                <= limits.max_frame_bytes
            )
        await engine.stop("one")
        assert not engine.sessions["one"].sources
        assert not engine.collectors
        assert engine.snapshot("one")["state"] == "stopped"
        await engine.start("two", [source()], 10)
        await engine.stop("two")
        await engine.start("three", [source()], 10)
        await engine.stop("three")
        assert set(engine.sessions) == {"two", "three"}
    finally:
        await engine.close()


async def test_unexpected_opener_failure_cannot_leave_start_waiting(limits):
    @asynccontextmanager
    async def broken(source):
        raise RuntimeError("internal synthetic error")
        yield

    engine = LiveEngine(limits, broken)
    try:
        async with asyncio.timeout(1):
            state = await engine.start("one", [source()], 10)
        assert state["sources"][0]["state"] == "blocked"
        assert state["sources"][0]["error"] == "SSH_CONNECT_FAILED"
    finally:
        await engine.close()


async def test_short_line_flood_consumes_bounded_batches_without_dropping_ranges(limits):
    files = Files()
    engine = LiveEngine(replace(limits, max_batch_events=100, max_raw_events=1500), files.open)
    try:
        await engine.start("one", [source()], 500)
        files.file.data = b"\n" * 1000
        await until(lambda: engine.snapshot("one")["counters"]["received"] > 0)
        assert engine.snapshot("one")["counters"]["received"] <= 200
        await until(lambda: engine.snapshot("one")["counters"]["received"] == 1000)
        assert {event["source"]["byte_start"] for event in engine.retained_events("one")} == set(
            range(1000)
        )
        assert engine.snapshot("one")["sources"][0]["cursor"] == 1000
    finally:
        await engine.close()


async def test_split_seed_uses_each_pane_row_count_and_bounded_matching_scan(limits):
    files = Files(
        b"".join(line(f"{'match' if index % 7 == 0 else 'other'} {index}") for index in range(6000))
    )
    engine = LiveEngine(limits, files.open)
    try:
        state = await engine.start(
            "one",
            [source(process_id="tall"), source(process_id="short")],
            10,
            LiteralFilter(include=("match",)),
            mode="split",
            seed_rows_by_process={"tall": 500, "short": 5},
        )
        assert sum(event["process_id"] == "tall" for event in state["events"]) == 500
        assert sum(event["process_id"] == "short" for event in state["events"]) == 5
        states = {item["process_id"]: item for item in state["sources"]}
        assert states["tall"]["scanned_from"] < states["short"]["scanned_from"]
        assert all(item["seed_status"] == "filled" for item in state["sources"])
        await engine.load_older("one", 20)
        assert engine.sessions["one"].rows_by_process == {"tall": 500, "short": 20}
    finally:
        await engine.close()


@pytest.mark.parametrize(
    "rows", [{"unselected": 5}, {"process": 0}, {"process": 501}, {"process": True}]
)
async def test_per_process_seed_row_scope_and_bounds(limits, rows):
    engine = LiveEngine(limits, Files().open)
    with pytest.raises(ValueError):
        await engine.start("one", [source()], 10, seed_rows_by_process=rows)
    assert not engine.collectors


async def test_seed_line_limit_keeps_newest_contiguous_records_and_reports_limit(limits):
    files = Files(b"".join(line(str(index)) for index in range(10)))
    engine = LiveEngine(replace(limits, max_seed_lines=5), files.open)
    try:
        state = await engine.start("one", [source()], 10)
        assert [event["raw_line"].split(" ", 1)[1] for event in state["events"]] == [
            "5",
            "6",
            "7",
            "8",
            "9",
        ]
        assert state["sources"][0]["seed_status"] == "seed_limit_reached"
        assert state["sources"][0]["scanned_from"] == sum(
            len(line(str(index))) for index in range(5)
        )
        await engine.load_older("one", 10)
        assert engine.snapshot("one")["sources"][0]["seed_status"] == "source_exhausted"
        assert len(engine.snapshot("one")["events"]) == 10
    finally:
        await engine.close()


async def test_merge_deadline_is_not_rounded_to_an_extra_half_second(limits):
    files = Files()
    cycle = asyncio.Event()

    async def guard():
        cycle.set()

    engine = LiveEngine(replace(limits, merge_seconds=0.5), files.open)
    try:
        await engine.start("one", [source()], 10, guard=guard)
        cycle.clear()
        # Arrive just after an idle authorization/supervisor cycle. Fixed 500ms
        # sleeps formerly inspected this at age ~490ms, then waited 500ms more.
        async with asyncio.timeout(1):
            await cycle.wait()
        files.file.data += line("deadline")
        await until(lambda: bool(engine.retained_events("one")))
        received = engine.retained_events("one")[0]["_received_mono"]
        await until(
            lambda: any(frame["type"] == "events" for frame in engine.sessions["one"].replay)
        )
        held = time.monotonic() - received
        assert 0.5 <= held < 0.6, f"Reorder hold was {held:.4f}s for a 500ms deadline"
    finally:
        await engine.close()


async def test_slow_sftp_work_consumes_the_poll_interval_instead_of_extending_it(limits):
    files = Files()
    starts = []

    @asynccontextmanager
    async def slow_reader(source):
        async with files.open(source) as reader:
            named = reader.named

            async def slow_named():
                starts.append(time.monotonic())
                await asyncio.sleep(0.055)
                return await named()

            reader.named = slow_named
            yield reader

    engine = LiveEngine(replace(limits, poll_seconds=0.08), slow_reader)
    try:
        await engine.start("one", [source()], 10)
        await until(lambda: len(starts) >= 5)
        intervals = [later - earlier for earlier, later in zip(starts, starts[1:], strict=False)]
        assert all(0.07 <= interval < 0.115 for interval in intervals), intervals
        files.file.data += line("slow-reader")
        await until(lambda: bool(engine.snapshot("one")["events"]))
        assert engine.snapshot("one")["events"][0]["raw_line"].endswith("slow-reader")
    finally:
        await engine.close()


async def test_poll_overlaps_proofs_skips_idle_reanchoring_and_anchors_partial_bytes(limits):
    files = Files(b"".join(line(f"seed-{index:03d}") for index in range(250)))
    engine = LiveEngine(replace(limits, poll_seconds=10), files.open)
    reads = []
    active = peak = 0
    read = files.file.read

    async def measured_read(size, offset):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        reads.append((offset, size))
        try:
            await asyncio.sleep(0.015)
            return await read(size, offset)
        finally:
            active -= 1

    try:
        await engine.start("one", [source()], 10)
        collector = engine.sessions["one"].sources[0]
        async with collector.lock:
            files.file.read = measured_read
            anchors = list(collector.anchors)
            await engine._poll(collector)
            assert 2 <= peak <= 4 and active == 0
            assert len(reads) == 4  # Two windows on each handle; no idle reanchor.
            assert collector.anchors == anchors
            reads.clear()
            partial = b"2026-10-17T12:00:00Z partial caf\xc3"
            files.file.data += partial
            await engine._poll(collector)
            assert len(reads) == 6  # Four proof reads, append, new tail only.
            assert sum(offset == 0 for offset, _ in reads) == 2
            assert collector.anchors[0] == anchors[0]
            assert collector.anchors[-1][1].endswith(partial)
            assert collector.offset == len(files.file.data)
            assert collector.received == 250  # A partial record still advances its anchor.
            files.file.data += b"\xa9\r\n"
            await engine._poll(collector)
            assert collector.received == 251
            assert any(event["raw_line"].endswith("café") for event in collector.raw)
    finally:
        await engine.close()


@pytest.mark.parametrize("failure", ["cancel", "read_error"])
async def test_parallel_proof_reads_are_drained_before_error_or_cancellation_returns(
    limits, failure
):
    files = Files(b"".join(line(f"seed-{index:03d}") for index in range(250)))
    engine = LiveEngine(replace(limits, poll_seconds=10), files.open)
    entered, release = asyncio.Event(), asyncio.Event()
    active = started = finished = 0
    read = files.file.read
    polling = None

    async def blocked_read(size, offset):
        nonlocal active, started, finished
        active += 1
        started += 1
        index = started
        if started == 4:
            entered.set()
        try:
            if failure == "read_error" and index == 1:
                raise DomainError("SOURCE_PERMISSION_DENIED", "Synthetic denied read.", 409)
            await release.wait()
            return await read(size, offset)
        finally:
            active -= 1
            finished += 1

    try:
        await engine.start("one", [source()], 10)
        collector = engine.sessions["one"].sources[0]
        async with collector.lock:
            files.file.read = blocked_read
            polling = asyncio.create_task(engine._poll(collector))
            await asyncio.wait_for(entered.wait(), 1)
            assert not polling.done()  # A peer error must wait for other in-flight reads.
            if failure == "cancel":
                polling.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await polling
            else:
                release.set()
                with pytest.raises(DomainError) as denied:
                    await polling
                assert denied.value.code == "SOURCE_PERMISSION_DENIED"
            assert active == 0 and finished == started == 4
    finally:
        release.set()
        if polling is not None:
            polling.cancel()
            await asyncio.gather(polling, return_exceptions=True)
        await engine.close()


async def test_idle_rewrite_after_proof_is_not_silently_adopted_as_a_new_anchor(limits):
    original = b"".join(line(f"old-{index:03d}") for index in range(250))
    files = Files(original)
    engine = LiveEngine(replace(limits, poll_seconds=10), files.open)
    size = files.file.size
    calls = 0

    async def rewrite_after_proofs():
        nonlocal calls
        calls += 1
        if calls == 3:  # Both handle proofs completed; the no-append size read follows.
            files.file.data = original.replace(b"old-", b"new-")
        return await size()

    try:
        await engine.start("one", [source()], 10)
        collector = engine.sessions["one"].sources[0]
        async with collector.lock:
            anchors, generation = list(collector.anchors), collector.generation
            files.file.size = rewrite_after_proofs
            await engine._poll(collector)
            assert collector.offset == len(original) and collector.anchors == anchors
            await engine._poll(collector)
            assert collector.generation != generation
            assert "COPYTRUNCATE_OR_REWRITE" in collector.warnings
            assert any(b"new-" in event["_raw_bytes"] for event in collector.raw)
    finally:
        await engine.close()


async def test_arrival_only_wake_keeps_idle_watchdog_and_fresh_publication_guard(limits):
    files = Files()
    starts, completed, published = [], [], []
    revoked = False
    engine = LiveEngine(replace(limits, merge_seconds=0.5), files.open)

    async def guard():
        session = engine.sessions.get("one")
        if session is not None and asyncio.current_task() is session.task:
            starts.append(time.monotonic())
            await asyncio.sleep(0.04)
            if revoked:
                raise DomainError("AUTH_REQUIRED", "Access revoked.", 401)
            completed.append(time.monotonic())

    frame = engine._frame

    def observe(session, kind, payload):
        if kind == "events":
            published.append(time.monotonic() - completed[-1])
        frame(session, kind, payload)

    engine._frame = observe
    try:
        await engine.start("one", [source()], 10, guard=guard)
        await until(lambda: len(completed) >= 2)
        assert 0.45 <= starts[1] - starts[0] < 0.55
        before_arrival = len(starts)
        files.file.data += line("guarded-publication")
        await until(lambda: bool(engine.retained_events("one")))
        await asyncio.sleep(0.05)
        # An arrival with no ready records is not another protected dispatch.
        assert len(starts) == before_arrival
        await until(lambda: bool(published))
        assert all(0 <= elapsed < 0.02 for elapsed in published)
        revoked = True
        await until(lambda: engine.sessions["one"].stopped, seconds=0.6)
        assert engine.sessions["one"].error == "AUTH_REQUIRED"
    finally:
        await engine.close()


async def test_diagnostic_tail_does_not_satisfy_timestamped_viewport_seed(limits):
    valid = b"".join(
        line(f"{'wanted' if index % 2 == 0 else 'other'} {index}") for index in range(50)
    )
    unknown = b"unknown diagnostic wanted\n" * 4000
    assert len(unknown) > 65_536
    files = Files(valid + unknown)
    engine = LiveEngine(limits, files.open)
    try:
        state = await engine.start("one", [source()], 12, LiteralFilter(include=("wanted",)))
        assert len(state["events"]) == 12
        assert all(
            event["timestamp_us"] is not None and "wanted" in event["raw_line"]
            for event in state["events"]
        )
        assert len(state["diagnostics"]) == 500
        assert all(event["timestamp_us"] is None for event in state["diagnostics"])
        assert state["counters"]["received"] == 4050
        assert state["sources"][0]["scanned_from"] == 0
        # A second window's matching row count also excludes diagnostics.
        second = await engine.start("two", [source()], 20, LiteralFilter(include=("wanted",)))
        assert len(second["events"]) == 20
        assert files.opens == 1
    finally:
        await engine.close()
