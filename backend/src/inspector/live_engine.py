"""Bounded supervised live capture; authorization and durable ownership live above it.

Filters belong to subscriptions. A shared collector only owns unfiltered source
bytes. Every reuse key includes the complete immutable authorized source context.
No remote command is constructed or executed by this module.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

import asyncssh

from inspector.errors import DomainError
from inspector.log_engine import (
    LiteralFilter,
    ParserConfig,
    canonical_utc,
    event_id,
    event_sort_key,
    parse_timestamp,
)
from inspector.ssh_files import RemoteFiles, _regular
from inspector.ssh_transport import Endpoint, live_sftp_session

Event = dict[str, Any]
Guard = Callable[[], Awaitable[None]]
Recorder = Callable[[str, list[Event]], Awaitable[None]]


@dataclass(frozen=True)
class LiveLimits:
    poll_seconds: float = 0.75
    merge_seconds: float = 0.5
    max_raw_events: int = 20_000
    max_raw_bytes: int = 32 * 1024 * 1024
    max_line_bytes: int = 256 * 1024
    max_read_bytes: int = 1024 * 1024
    max_batch_events: int = 1000
    max_seed_bytes: int = 8 * 1024 * 1024
    max_seed_lines: int = 50_000
    seed_seconds: float = 5.0
    max_view_events: int = 2500
    max_replay_frames: int = 128
    max_replay_events: int = 5000
    reconnect_max_seconds: float = 15.0
    heartbeat_seconds: float = 1.0
    max_stopped_sessions: int = 32
    max_stopped_snapshot_bytes: int = 1024 * 1024
    max_snapshot_bytes: int = 1024 * 1024
    max_frame_bytes: int = 2 * 1024 * 1024
    max_replay_bytes: int = 8 * 1024 * 1024

    def __post_init__(self) -> None:
        if any(value <= 0 for value in vars(self).values()):
            raise ValueError("Live limits must be positive.")


@dataclass(frozen=True)
class LiveSource:
    project_id: str
    owner_user_id: str
    process_id: str
    config_revision: int
    access_signature: str
    remote_path: str
    root: str
    target: Endpoint = field(repr=False)
    jump: Endpoint | None = field(default=None, repr=False)
    parser: ParserConfig = field(default_factory=ParserConfig)
    encoding: str = "utf-8"
    server_id: str = ""
    process_name: str = ""
    server_name: str = ""
    allow_loopback: bool = False

    @property
    def key(self) -> tuple[Any, ...]:
        # Endpoint includes its approved key and authentication material. Neither
        # the key nor its repr is ever returned in snapshots or diagnostics.
        return (
            self.project_id,
            self.owner_user_id,
            self.process_id,
            self.config_revision,
            self.access_signature,
            self.remote_path,
            self.root,
            self.target,
            self.jump,
            self.parser,
            self.encoding,
        )


class ReadHandle(Protocol):
    async def read(self, size: int, offset: int) -> bytes: ...

    async def size(self) -> int: ...


class SourceReader(Protocol):
    handle: ReadHandle

    async def named(self) -> ReadHandle: ...

    async def replace(self, handle: ReadHandle) -> None: ...

    async def release(self, handle: ReadHandle) -> None: ...


ReaderOpener = Callable[[LiveSource], Any]


class _SFTPHandle:
    def __init__(self, handle: asyncssh.SFTPClientFile) -> None:
        self.handle = handle

    async def read(self, size: int, offset: int) -> bytes:
        value = await self.handle.read(size, offset)
        if not isinstance(value, bytes):
            raise DomainError("SOURCE_READ_FAILED", "The source did not return bytes.", 422)
        return value

    async def size(self) -> int:
        attrs = await self.handle.stat()
        if not _regular(attrs) or attrs.size is None or attrs.size < 0:
            raise DomainError("SOURCE_NOT_REGULAR", "Only regular log files are supported.", 422)
        return attrs.size


class _SFTPReader:
    def __init__(self, files: RemoteFiles, source: LiveSource) -> None:
        self.files, self.source = files, source
        self.stack = AsyncExitStack()
        self.handle: ReadHandle
        self.handles: dict[int, Any] = {}

    async def named(self) -> ReadHandle:
        await self.files._validated(self.source.remote_path, self.source.root)
        context = self.files._open(self.source.remote_path)
        raw = await context.__aenter__()
        handle = _SFTPHandle(raw)
        self.handles[id(handle)] = context
        await handle.size()
        # Revalidate after opening: SFTP cannot offer atomic open-beneath.
        await self.files._validated(self.source.remote_path, self.source.root)
        return handle

    async def replace(self, handle: ReadHandle) -> None:
        if hasattr(self, "handle"):
            await self.release(self.handle)
        self.handle = handle

    async def release(self, handle: ReadHandle) -> None:
        context = self.handles.pop(id(handle), None)
        if context is not None:
            await context.__aexit__(None, None, None)

    async def close(self) -> None:
        for context in list(self.handles.values()):
            await context.__aexit__(None, None, None)
        self.handles.clear()


@asynccontextmanager
async def sftp_reader(source: LiveSource) -> AsyncIterator[SourceReader]:
    async with live_sftp_session(
        source.target, source.jump, allow_loopback=source.allow_loopback
    ) as sftp:
        files = RemoteFiles(
            sftp,
            max_candidates=1,
            max_listing_entries=1,
            max_listing_bytes=4096,
            max_estimated_bytes=2**63 - 1,
            max_probe_bytes=2**63 - 1,
        )
        reader = _SFTPReader(files, source)
        try:
            await reader.replace(await reader.named())
            yield reader
        finally:
            await reader.close()


def _public(event: Event) -> Event:
    return {key: value for key, value in event.items() if not key.startswith("_")}


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _bounded_view(events: list[Event], budget: int) -> tuple[list[Event], int]:
    selected: list[Event] = []
    used = 2
    for event in reversed(events):
        public = _public(event)
        size = _json_size(public) + 1
        if used + size > budget:
            break
        selected.append(public)
        used += size
    selected.reverse()
    return selected, used


def _sort(event: Event) -> tuple[Any, ...]:
    if event["timestamp_us"] is None:
        return (
            1,
            event["process_id"],
            event["source"]["source_revision_id"],
            event["source"]["byte_start"],
        )
    return (0, *event_sort_key(event))


def _matches(
    event: Event, global_filter: LiteralFilter, per_process: dict[str, LiteralFilter]
) -> bool:
    # A bounded preview cannot establish a full-line predicate.
    if event["parse_status"] in {"oversized_line", "decode_error"}:
        return False
    return global_filter.matches(event["raw_line"]) and per_process.get(
        event["process_id"], LiteralFilter()
    ).matches(event["raw_line"])


@dataclass
class _Collector:
    source: LiveSource
    limits: LiveLimits
    generation: str = field(default_factory=lambda: str(uuid4()))
    raw: deque[Event] = field(default_factory=deque)
    raw_bytes: int = 0
    received: int = 0
    evicted: int = 0
    offset: int = 0
    observed_size: int = 0
    pending_start: int = 0
    pending: bytes = b""
    pending_length: int = 0
    pending_hash: Any = field(default_factory=hashlib.sha256)
    anchors: list[tuple[int, bytes]] = field(default_factory=list)
    consumers: set[str] = field(default_factory=set)
    state: str = "starting"
    warnings: list[str] = field(default_factory=lambda: ["SFTP_CONTINUITY_NOT_PROVABLE"])
    error: str | None = None
    seed_status: str = "seeding"
    seed_start: int = 0
    seed_boundary: int = 0
    earliest_offset: int = 0
    gaps: int = 0
    reconnects: int = 0
    task: asyncio.Task[None] | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    reader: SourceReader | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def event(
        self,
        data: bytes,
        start: int,
        end: int,
        *,
        oversized: bool = False,
        checksum: str | None = None,
    ) -> Event:
        content = data[:-1] if data.endswith(b"\n") else data
        if content.endswith(b"\r"):
            content = content[:-1]
        try:
            text = content.decode(self.source.encoding, errors="strict")
            decode_error = False
        except UnicodeDecodeError:
            text = content.decode(self.source.encoding, errors="replace")
            decode_error = True
        parsed = parse_timestamp(text, self.source.parser)
        status = (
            "oversized_line"
            if oversized
            else "decode_error"
            if decode_error
            else "ok"
            if parsed.micros is not None
            else "invalid_timestamp"
        )
        timestamp = parsed.micros if not oversized and not decode_error else None
        return {
            "schema_version": "1.0",
            "event_id": event_id(self.source.process_id, self.generation, None, None, start, end),
            "project_id": self.source.project_id,
            "process_id": self.source.process_id,
            "server_id": self.source.server_id,
            "process_name_snapshot": self.source.process_name or self.source.process_id,
            "server_name_snapshot": self.source.server_name or self.source.server_id,
            "raw_line": text,
            "timestamp_original": parsed.original,
            "timestamp_utc": parsed.utc if timestamp is not None else None,
            "timestamp_us": timestamp,
            "received_at": canonical_utc(datetime.now(UTC)),
            "parse_status": status,
            "metadata": {"preview_truncated": "true"} if oversized else {},
            "source": {
                "source_revision_id": self.generation,
                "remote_path": self.source.remote_path,
                "archive_member": None,
                "member_ordinal": None,
                "byte_start": start,
                "byte_end": end,
                "line_number": None,
                "content_sha256": checksum or hashlib.sha256(data).hexdigest(),
            },
            "late_arrival": False,
            "_raw_bytes": data,
            "_received_mono": time.monotonic(),
        }

    def retain(self, events: list[Event], *, older: bool = False) -> None:
        # Deduplicate only an identical proven generation and physical range.
        known = {event["event_id"] for event in self.raw}
        for event in reversed(events) if older else events:
            if event["event_id"] in known:
                continue
            known.add(event["event_id"])
            if older:
                self.raw.appendleft(event)
            else:
                self.raw.append(event)
            self.raw_bytes += len(event["_raw_bytes"])
            self.received += 1
        while self.raw and (
            len(self.raw) > self.limits.max_raw_events or self.raw_bytes > self.limits.max_raw_bytes
        ):
            old = self.raw.popleft()
            self.raw_bytes -= len(old["_raw_bytes"])
            self.evicted += 1
        if self.raw:
            self.earliest_offset = self.raw[0]["source"]["byte_start"]

    def feed(self, data: bytes) -> list[Event]:
        events: list[Event] = []
        # Split byte records before decoding. A UTF-8 code point can span polls.
        parts = data.split(b"\n")
        for index, content in enumerate(parts):
            part = content + b"\n" if index < len(parts) - 1 else content
            if not part:
                continue
            self.pending_hash.update(part)
            self.pending_length += len(part)
            room = max(0, self.limits.max_line_bytes - len(self.pending))
            self.pending += part[:room]
            self.offset += len(part)
            if part.endswith(b"\n"):
                oversized = self.pending_length > self.limits.max_line_bytes
                events.append(
                    self.event(
                        self.pending,
                        self.pending_start,
                        self.offset,
                        oversized=oversized,
                        checksum=self.pending_hash.hexdigest(),
                    )
                )
                self.pending_start = self.offset
                self.pending = b""
                self.pending_length = 0
                self.pending_hash = hashlib.sha256()
        return events

    async def proven(self, handle: ReadHandle) -> bool:
        size = await handle.size()
        if size < self.offset:
            return False
        anchors = tuple(self.anchors)
        actual = await asyncio.gather(
            *(handle.read(len(data), offset) for offset, data in anchors),
            return_exceptions=True,
        )
        for (_, expected), observed in zip(anchors, actual, strict=True):
            if isinstance(observed, BaseException):
                raise observed
            if observed != expected:
                return False
        return True

    async def anchor(self, handle: ReadHandle, *, reuse_proven_prefix: bool = False) -> None:
        prefix = next(
            (data for offset, data in self.anchors if offset == 0 and len(data) == 4096), None
        )
        positions = [
            (offset, length)
            for offset, length in (
                (0, min(self.offset, 4096)),
                (max(0, self.offset - 4096), min(self.offset, 4096)),
            )
            if length
        ]
        reads = [
            (offset, length)
            for offset, length in positions
            if not (reuse_proven_prefix and prefix is not None and (offset, length) == (0, 4096))
        ]
        actual = await asyncio.gather(
            *(handle.read(length, offset) for offset, length in reads), return_exceptions=True
        )
        refreshed: list[bytes] = []
        for observed in actual:
            if isinstance(observed, BaseException):
                raise observed
            refreshed.append(observed)
        observed_reads = iter(refreshed)
        self.anchors = [
            (
                offset,
                prefix
                if reuse_proven_prefix and prefix is not None and (offset, length) == (0, 4096)
                else next(observed_reads),
            )
            for offset, length in positions
        ]

    def status(self) -> dict[str, Any]:
        return dict(
            process_id=self.source.process_id,
            source_revision_id=self.generation,
            state=self.state,
            error=self.error,
            seed_status=self.seed_status,
            seed_boundary=self.seed_boundary,
            scanned_from=self.seed_start,
            cursor=self.offset,
            observed_size=self.observed_size,
            backlog_bytes=max(0, self.observed_size - self.offset),
            poll_interval_ms=round(self.limits.poll_seconds * 1000),
            pending_bytes=self.pending_length,
            received=self.received,
            retained=len(self.raw),
            evicted=self.evicted,
            retained_bytes=self.raw_bytes,
            earliest_retained_offset=self.earliest_offset,
            gaps=self.gaps,
            reconnects=self.reconnects,
            warnings=list(self.warnings),
        )


@dataclass
class LiveSession:
    session_id: str
    sources: list[_Collector]
    requested_rows: int
    global_filter: LiteralFilter
    per_process: dict[str, LiteralFilter]
    mode: str
    guard: Guard | None = field(default=None, repr=False)
    on_events: Recorder | None = field(default=None, repr=False)
    rows_by_process: dict[str, int] = field(default_factory=dict)
    recording_enabled: bool = True
    filter_version: int = 1
    seq: int = 0
    stopped: bool = False
    error: str | None = None
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    arrived: asyncio.Event = field(default_factory=asyncio.Event)
    replay: deque[dict[str, Any]] = field(default_factory=deque)
    replay_events: int = 0
    replay_bytes: int = 0
    pending: list[Event] = field(default_factory=list)
    published_max_timestamp: int | None = None
    recorded: set[str] = field(default_factory=set)
    record_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    late_event_ids: set[str] = field(default_factory=set)
    task: asyncio.Task[None] | None = None
    terminal_snapshot: dict[str, Any] | None = None


class LiveEngine:
    def __init__(
        self, limits: LiveLimits | None = None, opener: ReaderOpener | None = None
    ) -> None:
        self.limits = limits or LiveLimits()
        self.opener = opener or self._pooled_reader
        self.collectors: dict[tuple[Any, ...], _Collector] = {}
        self.sessions: dict[str, LiveSession] = {}
        self.lock = asyncio.Lock()
        self.host_lock = asyncio.Lock()
        self.hosts: dict[tuple[Any, ...], tuple[Any, asyncssh.SFTPClient, int]] = {}

    @asynccontextmanager
    async def _pooled_reader(self, source: LiveSource) -> AsyncIterator[SourceReader]:
        key = (
            source.project_id,
            source.owner_user_id,
            source.config_revision,
            source.access_signature,
            source.target,
            source.jump,
            source.allow_loopback,
        )
        async with self.host_lock:
            entry = self.hosts.get(key)
            if entry is None:
                context = live_sftp_session(
                    source.target, source.jump, allow_loopback=source.allow_loopback
                )
                sftp = await context.__aenter__()
                self.hosts[key] = (context, sftp, 1)
            else:
                context, sftp, references = entry
                self.hosts[key] = (context, sftp, references + 1)
        files = RemoteFiles(
            sftp,
            max_candidates=1,
            max_listing_entries=1,
            max_listing_bytes=4096,
            max_estimated_bytes=2**63 - 1,
            max_probe_bytes=2**63 - 1,
        )
        reader = _SFTPReader(files, source)
        try:
            await reader.replace(await reader.named())
            yield reader
        finally:
            await reader.close()
            async with self.host_lock:
                context, sftp, references = self.hosts[key]
                if references == 1:
                    self.hosts.pop(key)
                    await context.__aexit__(None, None, None)
                else:
                    self.hosts[key] = (context, sftp, references - 1)

    async def start(
        self,
        session_id: str,
        sources: list[LiveSource],
        requested_rows: int,
        global_filter: LiteralFilter | None = None,
        per_process: dict[str, LiteralFilter] | None = None,
        mode: str = "merged",
        guard: Guard | None = None,
        on_events: Recorder | None = None,
        seed_rows_by_process: dict[str, int] | None = None,
        recording_enabled: bool = True,
    ) -> dict[str, Any]:
        if not sources or len({(s.project_id, s.owner_user_id) for s in sources}) != 1:
            raise ValueError("A live session requires sources from exactly one project and owner.")
        if len({s.process_id for s in sources}) != len(sources) or mode not in {"merged", "split"}:
            raise ValueError("Invalid live process selection or pane mode.")
        if set(per_process or {}) - {s.process_id for s in sources}:
            raise ValueError("Per-process filters must belong to the selected processes.")
        if set(seed_rows_by_process or {}) - {s.process_id for s in sources} or any(
            type(rows) is not int or not 1 <= rows <= 500
            for rows in (seed_rows_by_process or {}).values()
        ):
            raise ValueError("Per-process seed rows must be selected processes with 1–500 rows.")
        if guard:
            await guard()
        async with self.lock:
            if session_id in self.sessions:
                raise ValueError("Session already exists.")
            selected: list[_Collector] = []
            created: set[tuple[Any, ...]] = set()
            for source in sources:
                collector = self.collectors.get(source.key)
                if collector is None:
                    collector = _Collector(source, self.limits)
                    self.collectors[source.key] = collector
                    created.add(source.key)
                collector.consumers.add(session_id)
                selected.append(collector)
            session = LiveSession(
                session_id,
                selected,
                max(1, min(500, requested_rows)),
                global_filter or LiteralFilter(),
                per_process or {},
                mode,
                guard,
                on_events,
                dict(seed_rows_by_process or {}),
                recording_enabled,
            )
            self.sessions[session_id] = session
            session.task = asyncio.create_task(self._supervise(session))
            for collector in selected:
                if collector.task is None:
                    collector.task = asyncio.create_task(self._collect(collector, session))
        try:
            await asyncio.gather(*(collector.ready.wait() for collector in selected))
            if session.stopped:
                raise DomainError(session.error or "CANCELLED", "The live session stopped.", 409)
            if guard:
                await guard()
            # A second window's predicate may need older retained candidates;
            # it never mutates the shared collector's acquisition predicate.
            for collector in selected:
                async with collector.lock:
                    count = sum(
                        event["timestamp_us"] is not None
                        and _matches(event, session.global_filter, session.per_process)
                        for event in collector.raw
                    )
                    requested = (
                        session.rows_by_process.get(
                            collector.source.process_id, session.requested_rows
                        )
                        if session.mode == "split"
                        else session.requested_rows
                    )
                    if (
                        collector.source.key not in created
                        and count < requested
                        and collector.reader
                        and collector.seed_start
                    ):
                        older = await self._seed(
                            collector, session, collector.seed_start, initial=False
                        )
                        await self._record_shared(collector, older)
                        collector.retain(older, older=True)
            if on_events:
                await self._record(session, self.retained_events(session_id))
            timestamps = [
                event["timestamp_us"]
                for event in self.retained_events(session_id)
                if event["timestamp_us"] is not None
                and _matches(event, session.global_filter, session.per_process)
            ]
            session.published_max_timestamp = max(timestamps, default=None)
            self._frame(session, "snapshot", self.snapshot(session_id))
            return self.snapshot(session_id)
        except BaseException:
            await self.stop(session_id)
            raise

    def retained_events(self, session_id: str) -> list[Event]:
        """Internal recording input includes exact `_raw_bytes`, never JSON serialize it."""
        return sorted(
            (event for source in self.sessions[session_id].sources for event in source.raw),
            key=_sort,
        )

    def snapshot(self, session_id: str) -> dict[str, Any]:
        session = self.sessions[session_id]
        if session.terminal_snapshot is not None:
            return session.terminal_snapshot
        raw = self.retained_events(session_id)
        matching = [
            event for event in raw if _matches(event, session.global_filter, session.per_process)
        ]
        valid = [event for event in matching if event["timestamp_us"] is not None]
        diagnostics = [event for event in raw if event["timestamp_us"] is None]
        if session.mode == "split":
            chosen = {
                event["event_id"]
                for source in session.sources
                for event in [
                    event for event in valid if event["process_id"] == source.source.process_id
                ][-session.rows_by_process.get(source.source.process_id, session.requested_rows) :]
            }
            valid = [event for event in valid if event["event_id"] in chosen]
        else:
            valid = valid[-session.requested_rows :]
        snapshot_budget = min(
            self.limits.max_snapshot_bytes, max(0, self.limits.max_frame_bytes - 16_384)
        )
        public_valid, used = _bounded_view(
            valid[-self.limits.max_view_events :], snapshot_budget // 2
        )
        public_diagnostics, _ = _bounded_view(diagnostics[-500:], snapshot_budget - used - 16_384)
        for event in public_valid + public_diagnostics:
            event["late_arrival"] = event["event_id"] in session.late_event_ids
        counters = dict(
            received=sum(source.received for source in session.sources),
            matched=len(matching),
            matching=len(matching),
            filtered=len(raw) - len(matching),
            retained=len(raw),
            evicted=sum(source.evicted for source in session.sources),
            rendered=len(public_valid),
            visible=len(public_valid),
            diagnostic=len(diagnostics),
        )
        return dict(
            session_id=session_id,
            filter_version=session.filter_version,
            seq=session.seq,
            state="stopped" if session.stopped else "following",
            error=session.error,
            events=public_valid,
            diagnostics=public_diagnostics,
            counters=counters,
            sources=[source.status() for source in session.sources],
            mode=session.mode,
            requested_rows=session.requested_rows,
            coverage=dict(
                view_limit_reached=len(public_valid) < len(valid)
                or len(public_diagnostics) < min(500, len(diagnostics)),
                raw_retention_limited=any(source.evicted for source in session.sources),
                max_snapshot_bytes=self.limits.max_snapshot_bytes,
            ),
        )

    def _frame(self, session: LiveSession, kind: str, payload: dict[str, Any]) -> None:
        session.seq += 1
        frame: dict[str, Any] = dict(
            type=kind,
            seq=session.seq,
            filter_version=session.filter_version,
            sent_at=canonical_utc(datetime.now(UTC)),
            payload=payload,
        )
        size = _json_size(frame)
        if size > self.limits.max_frame_bytes:
            frame["type"] = "resync_required"
            frame["payload"] = dict(
                reason="FRAME_BYTE_LIMIT", snapshot=self.snapshot(session.session_id)
            )
            size = _json_size(frame)
            if size > self.limits.max_frame_bytes:
                frame["payload"] = dict(reason="FRAME_BYTE_LIMIT", retained_snapshot_available=True)
                size = _json_size(frame)
        session.replay.append(frame)
        session.replay_events += len(frame["payload"].get("events", []))
        session.replay_bytes += size
        while (
            len(session.replay) > self.limits.max_replay_frames
            or session.replay_events > self.limits.max_replay_events
            or session.replay_bytes > self.limits.max_replay_bytes
        ):
            old = session.replay.popleft()
            session.replay_events -= len(old["payload"].get("events", []))
            session.replay_bytes -= _json_size(old)
        session.changed.set()

    def frames_since(self, session_id: str, seq: int, filter_version: int) -> list[dict[str, Any]]:
        session = self.sessions[session_id]
        first = session.replay[0]["seq"] if session.replay else session.seq + 1
        if filter_version != session.filter_version or seq < first - 1 or seq > session.seq:
            return [
                dict(
                    type="resync_required",
                    seq=session.seq,
                    filter_version=session.filter_version,
                    sent_at=canonical_utc(datetime.now(UTC)),
                    payload=dict(reason="REPLAY_EXPIRED", snapshot=self.snapshot(session_id)),
                )
            ]
        return [frame for frame in session.replay if frame["seq"] > seq]

    async def refilter(
        self,
        session_id: str,
        global_filter: LiteralFilter,
        per_process: dict[str, LiteralFilter] | None = None,
    ) -> dict[str, Any]:
        session = self.sessions[session_id]
        if set(per_process or {}) - {source.source.process_id for source in session.sources}:
            raise ValueError("Per-process filters must belong to the selected processes.")
        if session.guard:
            await session.guard()
        session.global_filter, session.per_process = global_filter, per_process or {}
        session.filter_version += 1
        session.pending.clear()
        session.replay.clear()
        session.replay_events = 0
        session.replay_bytes = 0
        self._frame(session, "filter_applied", dict(filter_version=session.filter_version))
        snapshot = self.snapshot(session_id)
        self._frame(session, "snapshot", snapshot)
        return snapshot

    async def load_older(self, session_id: str, rows: int) -> dict[str, Any]:
        session = self.sessions[session_id]
        if session.guard:
            await session.guard()
        session.requested_rows = max(session.requested_rows, min(500, max(1, rows)))
        session.rows_by_process = {
            process: max(count, min(500, max(1, rows)))
            for process, count in session.rows_by_process.items()
        }
        for collector in session.sources:
            async with collector.lock:
                if collector.reader and collector.seed_start > 0:
                    events = await self._seed(
                        collector, session, collector.seed_start, initial=False
                    )
                    await self._record_shared(collector, events)
                    collector.retain(events, older=True)
        snapshot = self.snapshot(session_id)
        self._frame(session, "snapshot", snapshot)
        return snapshot

    async def _record(self, session: LiveSession, events: list[Event]) -> None:
        if session.recording_enabled and session.on_events:
            async with session.record_lock:
                fresh = [event for event in events if event["event_id"] not in session.recorded]
                if fresh:
                    await session.on_events(session.session_id, fresh)
                    session.recorded.update(event["event_id"] for event in fresh)
                    retained = {
                        event["event_id"] for source in session.sources for event in source.raw
                    }
                    session.recorded.intersection_update(
                        retained | {event["event_id"] for event in fresh}
                    )

    async def _seed(
        self, collector: _Collector, session: LiveSession, boundary: int, *, initial: bool = True
    ) -> list[Event]:
        assert collector.reader is not None
        handle = collector.reader.handle
        start, data = boundary, b""
        deadline = time.monotonic() + self.limits.seed_seconds
        events: dict[int, Event] = {}
        matches = 0
        requested = (
            session.rows_by_process.get(collector.source.process_id, session.requested_rows)
            if session.mode == "split"
            else session.requested_rows
        )
        processed = 0
        while (
            start > 0
            and len(data) < self.limits.max_seed_bytes
            and len(events) < self.limits.max_seed_lines
            and time.monotonic() < deadline
        ):
            amount = min(65_536, start, self.limits.max_seed_bytes - len(data))
            start -= amount
            chunk = await handle.read(amount, start)
            if len(chunk) != amount:
                raise DomainError("SOURCE_CHANGED", "The source changed during live seeding.", 409)
            data = chunk + data
            parts = data.split(b"\n")
            position = start + len(data) - len(parts[-1])
            for index in range(len(parts) - 2, -1, -1):
                part = parts[index]
                end = position
                position -= len(part) + 1
                if len(events) >= self.limits.max_seed_lines:
                    break
                if (start == 0 or index > 0) and end not in events:
                    raw = part + b"\n"
                    event = collector.event(
                        raw[: self.limits.max_line_bytes],
                        position,
                        end,
                        oversized=len(raw) > self.limits.max_line_bytes,
                        checksum=hashlib.sha256(raw).hexdigest(),
                    )
                    # Oversized records retain only an explicitly marked preview.
                    events[end] = event
                    matches += int(
                        event["timestamp_us"] is not None
                        and _matches(event, session.global_filter, session.per_process)
                    )
                    processed += 1
                    if processed % 500 == 0:
                        await asyncio.sleep(0)
            if matches >= requested:
                break
            await asyncio.sleep(0)
        # Backfill boundaries must be complete physical-record boundaries,
        # otherwise a split first line would disappear between scan windows.
        collector.seed_start = min(
            (event["source"]["byte_start"] for event in events.values()), default=start
        )
        collector.seed_status = (
            "source_exhausted"
            if collector.seed_start == 0
            else "filled"
            if matches >= requested
            else "seed_limit_reached"
        )
        if initial:
            collector.seed_boundary = boundary
            collector.offset = boundary
            pending_start = start + data.rfind(b"\n") + 1 if b"\n" in data else start
            pending = data[pending_start - start :]
            collector.pending_start = pending_start
            collector.pending = pending[: self.limits.max_line_bytes]
            collector.pending_length = len(pending)
            collector.pending_hash = hashlib.sha256(pending)
            if pending_start == start and start > 0:
                # The partial line began before this bounded scan. Its original
                # byte start is unknown, so never publish an invented range.
                collector.warnings.append("PARTIAL_LINE_START_OUTSIDE_SCAN")
                raise DomainError(
                    "LINE_LENGTH_LIMIT", "The pending live line exceeds the scan limit.", 413
                )
        return sorted(events.values(), key=lambda event: event["source"]["byte_start"])

    async def _collect(self, collector: _Collector, initial: LiveSession) -> None:
        attempt = 0
        while collector.consumers:
            try:
                async with self.opener(collector.source) as reader:
                    collector.reader = reader
                    async with collector.lock:
                        if collector.state == "starting":
                            collector.state = "seeding"
                            boundary = await reader.handle.size()
                            events = await self._seed(collector, initial, boundary)
                            collector.retain(events)
                            await collector.anchor(reader.handle)
                        elif not await collector.proven(reader.handle):
                            self._generation(collector, "RECONNECT_CONTINUITY_UNPROVEN")
                        else:
                            # A new transport establishes full fingerprints;
                            # prefix reuse is limited to proven ongoing polls.
                            await collector.anchor(reader.handle)
                        collector.state, collector.error = "following", None
                        collector.ready.set()
                    attempt = 0
                    while collector.consumers:
                        poll_started = time.monotonic()
                        async with collector.lock, asyncio.timeout(5.0):
                            await self._poll(collector)
                        # The configured interval is start-to-start. SFTP,
                        # authorization and durable recording work consume this
                        # budget instead of extending every source's cadence.
                        # An overrun yields once and starts a new bounded poll;
                        # missed intervals never become queued catch-up work.
                        await asyncio.sleep(
                            max(0.0, self.limits.poll_seconds - (time.monotonic() - poll_started))
                        )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                code = (
                    exc.code
                    if isinstance(exc, DomainError)
                    else "SOURCE_PERMISSION_DENIED"
                    if isinstance(exc, asyncssh.SFTPPermissionDenied)
                    else "HOST_KEY_CHANGED"
                    if isinstance(exc, asyncssh.HostKeyNotVerifiable)
                    else "SSH_AUTH_FAILED"
                    if isinstance(exc, asyncssh.PermissionDenied)
                    else "SOURCE_NOT_FOUND"
                    if isinstance(exc, (asyncssh.SFTPNoSuchFile, asyncssh.SFTPNoSuchPath))
                    else "SOURCE_READ_FAILED"
                    if isinstance(exc, asyncssh.SFTPError)
                    and not isinstance(exc, asyncssh.SFTPConnectionLost)
                    else "SSH_CONNECT_FAILED"
                )
                collector.error = code
                collector.ready.set()
                if (
                    not isinstance(exc, (DomainError, asyncssh.Error, OSError, TimeoutError))
                    or code
                    in {
                        "HOST_KEY_UNKNOWN",
                        "HOST_KEY_CHANGED",
                        "HOST_KEY_REQUIRED",
                        "SSH_AUTH_FAILED",
                        "SOURCE_PERMISSION_DENIED",
                        "SOURCE_ROOT_DENIED",
                        "SOURCE_SYMLINK_DENIED",
                        "SOURCE_NOT_REGULAR",
                        "LINE_LENGTH_LIMIT",
                    }
                    or isinstance(
                        exc,
                        (
                            asyncssh.PermissionDenied,
                            asyncssh.SFTPPermissionDenied,
                            asyncssh.HostKeyNotVerifiable,
                        ),
                    )
                ):
                    collector.state = "blocked"
                    self._notice(collector, "status", dict(reason=code))
                    break
                collector.state = "reconnecting"
                collector.gaps += 1
                collector.reconnects += 1
                self._notice(
                    collector,
                    "gap",
                    dict(reason="TRANSPORT_DISCONNECTED", recovery="proven_offsets_only"),
                )
                attempt += 1
                await asyncio.sleep(
                    min(self.limits.reconnect_max_seconds, 0.5 * 2 ** min(attempt, 5))
                    * random.uniform(0.8, 1.0)
                )
            finally:
                collector.reader = None
        if collector.state != "blocked":
            collector.state = "stopped"

    def _generation(self, collector: _Collector, reason: str) -> None:
        if collector.pending_length:
            if "INCOMPLETE_LINE_AT_GENERATION_END" not in collector.warnings:
                collector.warnings.append("INCOMPLETE_LINE_AT_GENERATION_END")
        collector.generation = str(uuid4())
        collector.offset = collector.pending_start = 0
        collector.pending = b""
        collector.pending_length = 0
        collector.pending_hash = hashlib.sha256()
        collector.anchors.clear()
        collector.gaps += 1
        if reason not in collector.warnings:
            collector.warnings.append(reason)
        self._notice(collector, "gap", dict(reason=reason, continuity="uncertain"))

    async def _read_appends(self, collector: _Collector, handle: ReadHandle) -> list[Event]:
        size = await handle.size()
        collector.observed_size = size
        amount = min(self.limits.max_read_bytes, max(0, size - collector.offset))
        if not amount:
            return []
        data = await handle.read(amount, collector.offset)
        if not data:
            raise DomainError("SOURCE_CHANGED", "The live source changed while reading.", 409)
        # A byte budget alone permits a million empty-line objects in one
        # request. Leave unconsumed bytes on the remote handle for the next
        # bounded poll instead of allocating an unbounded event burst.
        cursor = 0
        for _ in range(self.limits.max_batch_events):
            newline = data.find(b"\n", cursor)
            if newline < 0:
                break
            cursor = newline + 1
        else:
            data = data[:cursor]
        return collector.feed(data)

    async def _poll(self, collector: _Collector) -> None:
        assert collector.reader is not None
        reader = collector.reader
        named = await reader.named()
        events: list[Event] = []
        try:
            pinned_proof, named_proof = await asyncio.gather(
                collector.proven(reader.handle),
                collector.proven(named),
                return_exceptions=True,
            )
            if isinstance(pinned_proof, BaseException):
                raise pinned_proof
            if not pinned_proof:
                self._generation(collector, "COPYTRUNCATE_OR_REWRITE")
                await reader.replace(named)
                named = reader.handle
            elif isinstance(named_proof, BaseException):
                raise named_proof
            elif not named_proof:
                # The pinned old object still matches; drain it before adopting
                # the newly named object. Drain is deliberately bounded.
                deadline = time.monotonic() + 2.0
                drained = 0
                while drained < self.limits.max_read_bytes and time.monotonic() < deadline:
                    old_offset = collector.offset
                    events.extend(await self._read_appends(collector, reader.handle))
                    drained += collector.offset - old_offset
                    if collector.offset == await reader.handle.size():
                        break
                if collector.offset < await reader.handle.size():
                    if "ROTATED_DRAIN_LIMIT" not in collector.warnings:
                        collector.warnings.append("ROTATED_DRAIN_LIMIT")
                await self._deliver(collector, events)
                events = []
                self._generation(collector, "RENAME_ROTATION_OBSERVED")
                await reader.replace(named)
                named = reader.handle
            before_read = collector.offset
            events.extend(await self._read_appends(collector, reader.handle))
            if collector.offset != before_read or not collector.anchors:
                await collector.anchor(reader.handle, reuse_proven_prefix=True)
        finally:
            if named is not reader.handle:
                await reader.release(named)
        await self._deliver(collector, events)

    async def _record_shared(self, collector: _Collector, events: list[Event]) -> None:
        # Durable subscribers commit exact source bytes before any publication.
        processed: set[str] = set()
        budget = max(32, len(collector.consumers) * 2)
        deadline = asyncio.get_running_loop().time() + 5.0
        while True:
            # A peer's awaited callback can overlap Save activation or a new
            # subscriber. Recheck after each peer, and return only when no
            # enabled recorder remains. Retain/publication then run without an
            # intervening await, so activation cannot slip through that fence.
            candidates = [
                session
                for identifier in collector.consumers
                if identifier not in processed
                and (session := self.sessions.get(identifier)) is not None
                and not session.stopped
                and session.recording_enabled
                and session.on_events is not None
            ]
            if not candidates:
                return
            if len(processed) >= budget:
                raise DomainError(
                    "SUBSCRIBER_CHURN_LIMIT",
                    "Live subscribers changed too often during capture.",
                    429,
                )
            session = candidates[0]
            processed.add(session.session_id)
            # Each peer shares one absolute deadline, including Load Older.
            # Exit this context before the next candidate check, so the final
            # empty check through raw retention has no suspension point.
            async with asyncio.timeout_at(deadline):
                try:
                    if session.guard:
                        await session.guard()
                    await self._record(session, events)
                except Exception as exc:
                    session.error = exc.code if isinstance(exc, DomainError) else "RECORDING_FAILED"
                    self._frame(session, "error", dict(code=session.error))
                    await self.stop(session.session_id)

    async def _deliver(self, collector: _Collector, events: list[Event]) -> None:
        if not events:
            return
        await self._record_shared(collector, events)
        collector.retain(events)
        for session_id in list(collector.consumers):
            session = self.sessions.get(session_id)
            if session and not session.stopped:
                session.pending.extend(events)
                session.arrived.set()
                # Slow clients cannot expand this bounded acquisition queue.
                if (
                    len(session.pending) > self.limits.max_raw_events
                    or sum(len(event["_raw_bytes"]) for event in session.pending)
                    > self.limits.max_raw_bytes
                ):
                    session.pending.clear()
                    self._frame(
                        session,
                        "resync_required",
                        dict(reason="CLIENT_QUEUE_LIMIT", snapshot=self.snapshot(session_id)),
                    )

    def _notice(self, collector: _Collector, kind: str, payload: dict[str, Any]) -> None:
        for session_id in list(collector.consumers):
            session = self.sessions.get(session_id)
            if session and not session.stopped:
                self._frame(session, kind, dict(process_id=collector.source.process_id, **payload))

    async def _supervise(self, session: LiveSession) -> None:
        last_status = time.monotonic()
        next_guard = last_status
        try:
            while not session.stopped:
                # Clear immediately before inspecting pending records. Arrival
                # sets this independently of the outbound changed notification.
                session.arrived.clear()
                now = time.monotonic()
                ready_to_publish = any(
                    now - event["_received_mono"] >= self.limits.merge_seconds
                    for event in session.pending
                )
                if ready_to_publish or now >= next_guard:
                    # An arrival-only wakeup publishes nothing. Retain the
                    # 500ms background check schedule, and always validate
                    # freshly immediately before publishing ready records.
                    next_guard = now + 0.5
                    if session.guard:
                        await session.guard()
                    now = time.monotonic()
                ready = [
                    event
                    for event in session.pending
                    if now - event["_received_mono"] >= self.limits.merge_seconds
                ]
                session.pending = [
                    event
                    for event in session.pending
                    if now - event["_received_mono"] < self.limits.merge_seconds
                ]
                if ready:
                    selected = sorted(
                        (
                            dict(event)
                            for event in ready
                            if _matches(event, session.global_filter, session.per_process)
                        ),
                        key=_sort,
                    )
                    for event in selected:
                        timestamp = event["timestamp_us"]
                        event["late_arrival"] = (
                            timestamp is not None
                            and session.published_max_timestamp is not None
                            and timestamp < session.published_max_timestamp
                        )
                        if event["late_arrival"]:
                            session.late_event_ids.add(event["event_id"])
                        if timestamp is not None:
                            session.published_max_timestamp = max(
                                timestamp, session.published_max_timestamp or timestamp
                            )
                    batch: list[Event] = []
                    batch_bytes = 256
                    for event in selected:
                        public = _public(event)
                        size = _json_size(public) + 1
                        if batch and (
                            len(batch) >= 500
                            or batch_bytes + size > self.limits.max_frame_bytes - 1024
                        ):
                            self._frame(session, "events", dict(events=batch))
                            batch, batch_bytes = [], 256
                        batch.append(public)
                        batch_bytes += size
                    if batch:
                        self._frame(session, "events", dict(events=batch))
                    snapshot = self.snapshot(session.session_id)
                    session.late_event_ids.intersection_update(
                        event["event_id"] for source in session.sources for event in source.raw
                    )
                    self._frame(
                        session,
                        "counters",
                        dict(counters=snapshot["counters"], sources=snapshot["sources"]),
                    )
                    last_status = now
                elif now - last_status >= self.limits.heartbeat_seconds:
                    snapshot = self.snapshot(session.session_id)
                    self._frame(
                        session,
                        "counters",
                        dict(counters=snapshot["counters"], sources=snapshot["sources"]),
                    )
                    last_status = now
                # Wake at the oldest record's receipt deadline, rather than
                # rounding a 500ms hold up to the next 500ms polling cycle.
                # Silent sessions still check authorization at least twice/s.
                wake_at = min(
                    next_guard,
                    last_status + self.limits.heartbeat_seconds,
                    *(
                        event["_received_mono"] + self.limits.merge_seconds
                        for event in session.pending
                    ),
                )
                try:
                    async with asyncio.timeout(max(0.001, wake_at - time.monotonic())):
                        await session.arrived.wait()
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            session.error = exc.code if isinstance(exc, DomainError) else "LIVE_GUARD_FAILED"
            self._frame(session, "error", dict(code=session.error))
            await self.stop(session.session_id)

    async def stop(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if session is None or session.stopped:
            return
        session.stopped = True
        terminal = self.snapshot(session_id)
        terminal["state"] = "stopped"
        # Completed monitors keep a bounded status snapshot, not references to
        # shared collectors or all retained source bytes indefinitely.
        events = terminal["events"][-500:]
        diagnostics = terminal["diagnostics"][-100:]
        size = sum(len(event["raw_line"].encode("utf-8")) for event in events + diagnostics)
        while size > self.limits.max_stopped_snapshot_bytes and (events or diagnostics):
            old = diagnostics.pop(0) if diagnostics else events.pop(0)
            size -= len(old["raw_line"].encode("utf-8"))
        terminal["events"], terminal["diagnostics"] = events, diagnostics
        session.terminal_snapshot = terminal
        pending: list[asyncio.Task[None]] = []
        current = asyncio.current_task()
        if session.task is not None and session.task is not current:
            session.task.cancel()
            pending.append(session.task)
        async with self.lock:
            for collector in session.sources:
                collector.consumers.discard(session_id)
                if not collector.consumers:
                    self.collectors.pop(collector.source.key, None)
                    if collector.task is not None and collector.task is not current:
                        collector.task.cancel()
                        pending.append(collector.task)
                    collector.state = "stopped"
                    collector.ready.set()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        session.pending.clear()
        session.sources.clear()
        session.recorded.clear()
        session.late_event_ids.clear()
        session.guard = session.on_events = None
        session.replay.clear()
        session.replay_events = 0
        session.replay_bytes = 0
        self._frame(session, "stopped", dict(reason=session.error or "STOPPED"))
        terminal["seq"] = session.seq
        stopped = [key for key, value in self.sessions.items() if value.stopped]
        for key in stopped[: -self.limits.max_stopped_sessions]:
            self.sessions.pop(key, None)

    async def close(self) -> None:
        await asyncio.gather(*(self.stop(session_id) for session_id in list(self.sessions)))
