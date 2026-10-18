"""Bounded, previewed bundle exchange into independent private offline data.

The two ZIP members are streamed, never extracted. Explicit typed projections
exclude active configuration. Imported identity strings are provenance only.
"""

import asyncio
import copy
import hashlib
import heapq
import io
import json
import re
import stat
import tempfile
import time
import zipfile
import zlib
from collections.abc import AsyncIterator, Callable
from functools import partial
from typing import Annotated, Any, BinaryIO, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import Field, ValidationError, model_validator
from sqlalchemy import delete, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer
from starlette.responses import StreamingResponse

from inspector import services
from inspector.domain import ID_PATTERN, Principal, ProjectContext
from inspector.errors import DomainError
from inspector.history import (
    EmptyInput,
    HistoricalContextInput,
    HistoricalContextResponse,
    HistoricalCoverage,
    HistoricalEvent,
    HistoricalFilter,
    HistoricalJobResponse,
    HistoricalQueryInput,
    HistoricalQueryResponse,
    StrictInput,
    canonical_time,
    checked_job,
    event_payload,
    format_time,
    job_response,
    not_found,
)
from inspector.investigations import (
    BookmarkCreate,
    BookmarkResponse,
    BookmarkUpdate,
    CorrelationInput,
    CorrelationResponse,
    RevisionInput,
    SavedWorkspaceInput,
    SavedWorkspaceResponse,
)
from inspector.log_engine import CancellationToken, EngineLimits, ScanProgress
from inspector.log_engine.reader import _Budget, _zip_preflight
from inspector.persistence.bundle_models import (
    BundleDownload,
    BundlePreview,
    OfflineAnalysis,
    OfflineCursor,
    OfflineInvestigation,
)
from inspector.persistence.investigation_models import InvestigationBookmark, SavedInvestigation
from inspector.persistence.models import AuthSession, HistoryEvent, HistoryJob, Project, User
from inspector.security import authorize, issue_token, token_hash

PREVIEW_US = 900_000_000
WARNING = "Review every field: literal redaction cannot identify every sensitive value. Original cached data is unchanged."
MAX_EVENTS = 1_000_000
MAX_SAFE_INTEGER = 9_007_199_254_740_991


async def bundle_work[Result](request: Request, operation: Callable[[], Result]) -> Result:
    """Share the configured archive executor, retaining slots on cancellation."""
    manager = request.app.state.history
    async with manager.slots:
        task = asyncio.get_running_loop().run_in_executor(manager.executor, operation)
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        if cancelled:
            if not task.cancelled():
                task.exception()
            raise asyncio.CancelledError
        return task.result()


class BundleOrigin(StrictInput):
    project_id: str = Field(max_length=128)
    investigation_id: str = Field(max_length=128)
    config_revision: int = Field(ge=1)
    snapshot_revision: int = Field(ge=0)


class BundleSelection(StrictInput):
    title: str = Field(max_length=512)
    process_ids: list[str] = Field(min_length=1, max_length=200)
    from_: str = Field(alias="from")
    to: str
    filter: HistoricalFilter = Field(default_factory=HistoricalFilter)
    per_process_filters: dict[str, HistoricalFilter] = Field(default_factory=dict, max_length=200)
    layout: Literal["merged", "split"] = "merged"
    notes: str = Field(default="", max_length=10000)

    @model_validator(mode="after")
    def validate_scope(self) -> "BundleSelection":
        if canonical_time(self.from_) >= canonical_time(self.to):
            raise ValueError("Invalid exclusive interval.")
        if len(set(self.process_ids)) != len(self.process_ids):
            raise ValueError("Duplicate process identities.")
        if not set(self.per_process_filters) <= set(self.process_ids):
            raise ValueError("Unexpected per-process filter.")
        return self


class SnapshotNode(StrictInput):
    id: str = Field(max_length=128)
    name: str = Field(max_length=512)
    description: str = Field(default="", max_length=100_000)
    tags: list[str] = Field(default_factory=list, max_length=200)
    subsystem_id: str | None = Field(default=None, max_length=128)
    server_id: str | None = Field(default=None, max_length=128)
    pcs_resource_name: str | None = Field(default=None, max_length=512)


class SnapshotFlow(StrictInput):
    id: str = Field(max_length=128)
    source_process_id: str = Field(max_length=128)
    target_process_id: str = Field(max_length=128)
    label: str = Field(default="", max_length=512)
    protocol: str = Field(default="", max_length=512)
    description: str = Field(default="", max_length=100_000)


class TopologySnapshot(StrictInput):
    project: SnapshotNode
    subsystems: list[SnapshotNode] = Field(max_length=5000)
    servers: list[SnapshotNode] = Field(max_length=5000)
    processes: list[SnapshotNode] = Field(max_length=200)
    flows: list[SnapshotFlow] = Field(max_length=10000)


class BundleBookmark(StrictInput):
    id: str = Field(max_length=128)
    event_id: str = Field(max_length=128)
    annotation: str = Field(max_length=10000)
    pin_context: bool
    context: HistoricalContextResponse | None
    process_name_snapshot: str = Field(max_length=512)
    server_name_snapshot: str = Field(max_length=512)
    created_at: str


class Redaction(StrictInput):
    applied: bool
    term_count: int = Field(ge=0, le=20)
    replacement: str = Field(max_length=128)
    warning: str


class BundleDocument(StrictInput):
    schema_version: Literal["1.0"]
    origin: BundleOrigin
    selection: BundleSelection
    topology: TopologySnapshot
    sources: list[HistoricalCoverage] = Field(max_length=10000)
    events: list[HistoricalEvent] = Field(max_length=MAX_EVENTS)
    bookmarks: list[BundleBookmark] = Field(max_length=10000)
    coverage_status: str = Field(max_length=64)
    errors: list[str] = Field(max_length=10000)
    redaction: Redaction

    @model_validator(mode="after")
    def validate_identities(self) -> "BundleDocument":
        topology = self.topology

        def valid_id(value: str) -> None:
            if re.fullmatch(ID_PATTERN, value) is None:
                raise ValueError(
                    "Bundle identities must remain usable by scoped investigation routes."
                )

        valid_id(self.origin.project_id)
        valid_id(self.origin.investigation_id)
        valid_id(topology.project.id)

        def nodes(values: list[SnapshotNode]) -> dict[str, SnapshotNode]:
            for node in values:
                valid_id(node.id)
            output = {node.id: node for node in values}
            if len(output) != len(values):
                raise ValueError("Duplicate topology identities.")
            return output

        processes, servers, subsystems = (
            nodes(topology.processes),
            nodes(topology.servers),
            nodes(topology.subsystems),
        )
        if topology.project.id != self.origin.project_id or set(processes) != set(
            self.selection.process_ids
        ):
            raise ValueError("Topology/selection origin mismatch.")
        if any(process.server_id not in servers for process in processes.values()) or any(
            server.subsystem_id not in subsystems for server in servers.values()
        ):
            raise ValueError("Invalid topology containment.")
        if any(
            flow.source_process_id not in processes or flow.target_process_id not in processes
            for flow in topology.flows
        ):
            raise ValueError("Invalid flow endpoints.")
        source_ids = {s.source_revision_id: s for s in self.sources}
        for flow in topology.flows:
            valid_id(flow.id)
        for source in self.sources:
            valid_id(source.source_revision_id)
        if len(source_ids) != len(self.sources):
            raise ValueError("Duplicate source identities.")
        if any(source.process_id not in processes for source in self.sources):
            raise ValueError("Unexpected source process.")
        observed: dict[str, HistoricalEvent] = {}

        def validate_event(event: HistoricalEvent) -> None:
            valid_id(event.event_id)
            source = source_ids.get(event.source.source_revision_id)
            if source is None or source.process_id != event.process_id:
                raise ValueError("Event/source identity mismatch.")
            if (
                event.process_id not in processes
                or processes[event.process_id].server_id != event.server_id
            ):
                raise ValueError("Event/topology identity mismatch.")
            if event.project_id != self.origin.project_id:
                raise ValueError("Event origin mismatch.")
            if event.timestamp_us is not None and (
                abs(event.timestamp_us) > MAX_SAFE_INTEGER
                or event.timestamp_utc != format_time(event.timestamp_us)
            ):
                raise ValueError("Invalid exact event timestamp.")
            if event.timestamp_us is None and event.timestamp_utc is not None:
                raise ValueError("Unknown event time must remain unknown.")
            if event.source.byte_start < 0 or event.source.byte_end < event.source.byte_start:
                raise ValueError("Invalid source byte interval.")
            if event.event_id in observed and observed[event.event_id] != event:
                raise ValueError("Conflicting event copies.")
            observed[event.event_id] = event

        seen: set[str] = set()
        for event in self.events:
            if event.event_id in seen:
                raise ValueError("Duplicate event identities.")
            seen.add(event.event_id)
            validate_event(event)
        bookmark_ids: set[str] = set()
        for bookmark in self.bookmarks:
            valid_id(bookmark.id)
            valid_id(bookmark.event_id)
            if bookmark.id in bookmark_ids:
                raise ValueError("Duplicate bookmark identities.")
            bookmark_ids.add(bookmark.id)
            context = bookmark.context
            if context is None:
                continue
            if (
                context.project_id != self.origin.project_id
                or context.event_id != bookmark.event_id
                or len(context.items) > 201
            ):
                raise ValueError("Context origin/anchor mismatch.")
            anchors = [item.event for item in context.items if item.is_anchor]
            if len(anchors) != 1 or anchors[0].event_id != bookmark.event_id:
                raise ValueError("Context requires one genuine anchor.")
            anchor = anchors[0]
            positions = []
            for item in context.items:
                validate_event(item.event)
                event = item.event
                if (
                    event.source.source_revision_id != anchor.source.source_revision_id
                    or event.source.member_ordinal != anchor.source.member_ordinal
                    or event.process_id != anchor.process_id
                ):
                    raise ValueError("Context must stay in one source/member.")
                positions.append((event.source.byte_start, event.event_id))
            if positions != sorted(positions) or len(set(positions)) != len(positions):
                raise ValueError("Context source order mismatch.")
        return self


class ExportInput(StrictInput):
    investigation_id: str = Field(pattern=ID_PATTERN)
    redact_terms: list[Annotated[str, Field(min_length=1, max_length=512)]] = Field(
        default_factory=list, max_length=20
    )
    replacement: str = Field(default="[REDACTED]", min_length=1, max_length=128)


class PreviewInput(StrictInput):
    preview_id: str = Field(pattern=ID_PATTERN)


class BundlePreviewResponse(StrictInput):
    project_id: str
    preview_id: str
    expires_at: str
    digest: str
    document: BundleDocument
    warnings: list[str]


class BundleDownloadResponse(StrictInput):
    project_id: str
    download_id: str
    url: str


class BundleCancelResponse(StrictInput):
    project_id: str
    preview_id: str
    cancelled: Literal[True]


class OfflineResponse(StrictInput):
    project_id: str
    investigation_id: str
    offline: Literal[True]
    document: BundleDocument
    created_at: str
    job: HistoricalJobResponse


class OfflineListResponse(StrictInput):
    project_id: str
    items: list["OfflineSummaryResponse"]


class OfflineSummaryResponse(StrictInput):
    project_id: str
    investigation_id: str
    offline: Literal[True]
    created_at: str
    job: HistoricalJobResponse


def encoded(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except UnicodeError:
        raise DomainError(
            "INVALID_BUNDLE", "Bundle text must contain valid UTF-8 Unicode.", 422
        ) from None


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


class _RedactionBudget:
    def __init__(self, maximum: int, nodes: int, deadline: float) -> None:
        self.remaining = maximum
        self.nodes = nodes
        self.deadline = deadline

    def consume(self, size: int = 0, *, node: bool = False) -> None:
        if time.monotonic() > self.deadline:
            raise DomainError("BUNDLE_TIMEOUT", "Redaction exceeded its time budget.", 408)
        self.remaining -= size
        self.nodes -= int(node)
        if self.remaining < 0:
            raise DomainError(
                "BUNDLE_BYTE_LIMIT", "Redacted output exceeds the configured byte budget.", 413
            )
        if self.nodes < 0:
            raise DomainError(
                "BUNDLE_NODE_LIMIT", "Redacted output exceeds the structural budget.", 413
            )


def _json_text_bytes(text: str) -> int:
    """Exact ensure_ascii=False JSON string payload size, excluding quotes.

    Callers supply at most 64 KiB spans, avoiding a large temporary encoding.
    Control escapes, quotes and backslashes count before any output allocation.
    """
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        raise DomainError("INVALID_TEXT", "Unsupported Unicode text in bundle data.", 422) from None
    return (
        size
        + text.count('"')
        + text.count("\\")
        + sum(
            text.count(chr(code)) * (1 if code in {8, 9, 10, 12, 13} else 5) for code in range(32)
        )
    )


def redact(
    value: Any,
    terms: list[str],
    replacement: str,
    *,
    max_bytes: int = 134217728,
    max_nodes: int = 3_000_000,
    deadline: float | None = None,
) -> Any:
    """A bounded literal pass, including metadata keys, with cached next matches.

    Each absent term is searched once per string. A term's next position only
    advances when consumed, so frequent matches cannot repeatedly scan suffixes
    for absent terms. Budget checks precede every output write/container append.
    """
    budget = _RedactionBudget(
        max_bytes, max_nodes, time.monotonic() + 120 if deadline is None else deadline
    )
    ordered = sorted({term for term in terms if term}, key=lambda item: (-len(item), item))
    replacement_size = 0
    for start in range(0, len(replacement), 65536):
        budget.consume()
        replacement_size += _json_text_bytes(replacement[start : start + 65536])
        if replacement_size > max_bytes:
            break  # Any occurrence already cannot fit; do not scan a huge replacement.

    def text(value: str) -> str:
        budget.consume(2, node=True)
        # Unchanged strings stay immutable; count them without allocating copies.
        if not ordered:
            for start in range(0, len(value), 65536):
                budget.consume(_json_text_bytes(value[start : start + 65536]))
            return value
        positions: list[tuple[int, int, int]] = []
        for index, term in enumerate(ordered):
            budget.consume()
            position = value.find(term)
            if position >= 0:
                heapq.heappush(positions, (position, -len(term), index))
        if not positions:
            for start in range(0, len(value), 65536):
                budget.consume(_json_text_bytes(value[start : start + 65536]))
            return value
        output = io.StringIO()

        def span(start: int, end: int) -> None:
            for offset in range(start, end, 65536):
                chunk = value[offset : min(end, offset + 65536)]
                budget.consume(_json_text_bytes(chunk))
                output.write(chunk)

        offset = 0
        while positions:
            budget.consume()
            position, _length, index = heapq.heappop(positions)
            term = ordered[index]
            if position < offset:
                position = value.find(term, offset)
                if position >= 0:
                    heapq.heappush(positions, (position, -len(term), index))
                continue
            span(offset, position)
            budget.consume(replacement_size)
            output.write(replacement)
            offset = position + len(term)
            following = value.find(term, offset)
            if following >= 0:
                heapq.heappush(positions, (following, -len(term), index))
        span(offset, len(value))
        return output.getvalue()

    def walk(value: Any, depth: int = 0) -> Any:
        if depth > 32:
            raise DomainError(
                "BUNDLE_NODE_LIMIT", "Redacted output exceeds the nesting budget.", 413
            )
        if isinstance(value, str):
            return text(value)
        if isinstance(value, list):
            budget.consume(2, node=True)
            result = []
            for index, item in enumerate(value):
                budget.consume(int(index != 0))
                result.append(walk(item, depth + 1))
            return result
        if isinstance(value, dict):
            budget.consume(2, node=True)
            mapping = {}
            for index, (key, item) in enumerate(value.items()):
                budget.consume(1 + int(index != 0))
                safe_key = text(key)
                if safe_key in mapping:
                    raise DomainError(
                        "REDACTION_COLLISION",
                        "Redaction collapses distinct metadata keys; choose narrower terms.",
                        422,
                    )
                mapping[safe_key] = walk(item, depth + 1)
            return mapping
        budget.consume(len(encoded(value)), node=True)
        return value

    return walk(value)


def safe_topology(config: dict, selected: list[str]) -> dict:
    """Construct fields from a deep allowlist; no connection/parser/source config."""
    processes = [p for p in config.get("processes", []) if p["id"] in selected]
    servers = [
        s for s in config.get("servers", []) if s["id"] in {p["server_id"] for p in processes}
    ]
    subsystems = [
        s for s in config.get("subsystems", []) if s["id"] in {h["subsystem_id"] for h in servers}
    ]

    def node(value: dict) -> dict:
        return {key: copy.deepcopy(value[key]) for key in SnapshotNode.model_fields if key in value}

    flows = [
        f
        for f in config.get("flows", [])
        if f["source_process_id"] in selected and f["target_process_id"] in selected
    ]
    return dict(
        project=node(config["project"]),
        processes=[node(p) for p in processes],
        servers=[node(s) for s in servers],
        subsystems=[node(s) for s in subsystems],
        flows=[
            {key: copy.deepcopy(f[key]) for key in SnapshotFlow.model_fields if key in f}
            for f in flows
        ],
    )


def bundle_limits(request: Request) -> tuple[int, int, int, int]:
    policy = request.app.state.config.history_limits
    return (
        policy.get("max_download_bytes_per_collection", 536_870_912),
        policy.get("max_expanded_member_bytes", 134_217_728),
        policy.get("max_compression_ratio", 500),
        policy.get("archive_task_timeout_seconds", 120),
    )


def pack_bundle(document: dict, maximum: int) -> bytes:
    data = encoded(document)
    manifest = encoded(
        {
            "schema_version": "1.0",
            "files": [
                {
                    "path": "investigation.json",
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            ],
        }
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("manifest.json", manifest)
        archive.writestr("investigation.json", data)
    result = stream.getvalue()
    if len(result) > maximum:
        raise DomainError(
            "BUNDLE_BYTE_LIMIT", "The bundle exceeds the configured byte budget.", 413
        )
    return result


def load_json(data: bytes, *, max_nodes: int = 3_000_000) -> Any:
    # Bound structural depth before the recursive JSON decoder sees the input.
    depth, quoted, escaped, primitive, nodes = 0, False, False, False, 0
    for value in data:
        if quoted:
            if escaped:
                escaped = False
            elif value == 92:
                escaped = True
            elif value == 34:
                quoted = False
        elif value == 34:
            quoted = True
            primitive = False
            nodes += 1
        elif value in (91, 123):
            primitive = False
            nodes += 1
            depth += 1
            if depth > 32:
                raise ValueError("JSON nesting budget exceeded.")
        elif value in (93, 125):
            primitive = False
            depth -= 1
        elif value in b" \t\r\n,:":
            primitive = False
        elif not primitive and value in b"-0123456789tfn":
            primitive = True
            nodes += 1
        if nodes > max_nodes:
            raise ValueError("JSON structural budget exceeded.")

    def pairs(items: list[tuple[str, Any]]) -> dict:
        output = {}
        for key, value in items:
            if key in output:
                raise ValueError("Duplicate JSON key.")
            output[key] = value
        return output

    return json.loads(
        data,
        object_pairs_hook=pairs,
        parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("Invalid number.")),
    )


def unpack_bundle(
    data: bytes | BinaryIO,
    maximum: int,
    member_maximum: int,
    ratio: int,
    timeout: int,
    line_maximum: int = 262144,
) -> dict:
    """Validate actual bytes, types, duplicate names, CRC and cryptographic hashes."""
    if isinstance(data, bytes) and len(data) > maximum:
        raise DomainError(
            "BUNDLE_BYTE_LIMIT", "The bundle exceeds the configured byte budget.", 413
        )
    started = time.monotonic()
    try:
        handle = io.BytesIO(data) if isinstance(data, bytes) else data
        _zip_preflight(
            handle,
            _Budget(
                EngineLimits(max_members=2, wall_seconds=timeout),
                CancellationToken(),
                ScanProgress(),
            ),
            metadata_limit=65536,
            allowed_names=frozenset({b"manifest.json", b"investigation.json"}),
        )
        with zipfile.ZipFile(handle) as archive:
            members = archive.infolist()
            if len(members) != 2 or {member.filename for member in members} != {
                "manifest.json",
                "investigation.json",
            }:
                raise ValueError("Unexpected or duplicate archive members.")
            contents = {}
            actual_total = 0
            for member in members:
                if member.orig_filename != member.filename:
                    raise ValueError("NUL archive filename.")
                mode = member.external_attr >> 16
                if (
                    member.is_dir()
                    or (stat.S_IFMT(mode) and not stat.S_ISREG(mode))
                    or member.flag_bits & 1
                    or member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                ):
                    raise ValueError("Unsupported archive member.")
                if (
                    member.file_size > member_maximum
                    or member.file_size > max(1, member.compress_size) * ratio
                ):
                    raise ValueError("Archive member exceeds limits.")
                chunks, actual = [], 0
                with archive.open(member) as source:
                    while chunk := source.read(65536):
                        actual += len(chunk)
                        actual_total += len(chunk)
                        if (
                            actual > member_maximum
                            or actual_total > maximum
                            or time.monotonic() - started > timeout
                        ):
                            raise ValueError("Actual expanded byte/time budget exceeded.")
                        chunks.append(chunk)
                if actual != member.file_size:
                    raise ValueError("Archive size mismatch.")
                contents[member.filename] = b"".join(chunks)
            manifest = load_json(contents["manifest.json"])
            content = contents["investigation.json"]
            expected = {
                "schema_version": "1.0",
                "files": [
                    {
                        "path": "investigation.json",
                        "bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                ],
            }
            if manifest != expected:
                raise ValueError("Invalid manifest or checksum.")
            document = BundleDocument.model_validate(load_json(content)).model_dump(
                mode="json", by_alias=True
            )
            event_copies = [
                *document["events"],
                *(
                    item["event"]
                    for bookmark in document["bookmarks"]
                    for item in (bookmark["context"] or {}).get("items", [])
                ),
            ]
            if any(len(event["raw_line"].encode("utf-8")) > line_maximum for event in event_copies):
                raise ValueError("An event exceeds the physical-line budget.")
            return document
    except (
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        RecursionError,
        zipfile.BadZipFile,
        zlib.error,
        EOFError,
        NotImplementedError,
        RuntimeError,
    ) as error:
        if isinstance(error, DomainError):
            raise
        raise DomainError(
            "INVALID_BUNDLE",
            "The bundle is corrupt, unsafe, unsupported or exceeds its limits.",
            422,
        ) from None


async def content_revision(session: AsyncSession, job: HistoryJob) -> str:
    saved = await session.get(SavedInvestigation, (job.project_id, job.id))
    return digest(
        [
            job.snapshot_revision,
            job.status,
            job.event_count,
            None if saved is None else [saved.revision, saved.expired],
        ]
    )


async def export_document(
    session: AsyncSession, actor: Principal, project_id: str, job_id: str, maximum: int
) -> tuple[dict, str]:
    offline = await session.scalar(
        select(OfflineInvestigation).where(
            OfflineInvestigation.project_id == project_id,
            OfflineInvestigation.id == job_id,
            OfflineInvestigation.owner_user_id == actor.user_id,
        )
    )
    if offline is not None:
        actor = await services.current_actor(session, actor)
        authorize(actor, "bundle.export", owner_user_id=offline.owner_user_id)
        analysis = await session.get(OfflineAnalysis, (project_id, job_id))
        document = effective_document(offline, analysis)
        selected = set(document["selection"]["process_ids"])
        document["events"] = [
            event for event in document["events"] if event["process_id"] in selected
        ]
        document["sources"] = [
            source for source in document["sources"] if source["process_id"] in selected
        ]
        document["topology"] = safe_topology(document["topology"], list(selected))
        event_processes = {
            event["event_id"]: event["process_id"] for event in offline.document["events"]
        }
        document["bookmarks"] = [
            bookmark
            for bookmark in document["bookmarks"]
            if event_processes.get(bookmark["event_id"]) in selected
        ]
        if len(encoded(document)) > maximum:
            raise DomainError(
                "BUNDLE_BYTE_LIMIT", "The bundle exceeds the configured byte budget.", 413
            )
        return document, offline_revision(offline, analysis)
    job = await checked_job(session, actor, project_id, job_id, lock=True, action="bundle.export")
    if job.status not in {"completed", "partial", "cancelled", "failed", "interrupted"}:
        raise DomainError(
            "CAPTURE_BUSY", "Stop collection before preparing an immutable export.", 409
        )
    saved = await session.get(SavedInvestigation, (project_id, job_id))
    state = saved.state if saved else {}
    selection = {
        "title": state.get("title", "Saved investigation"),
        "process_ids": state.get("process_ids", job.process_ids),
        "from": state.get("from", format_time(job.from_us)),
        "to": state.get("to", format_time(job.to_us)),
        "filter": state.get("filter", {}),
        "per_process_filters": state.get("per_process_filters", {}),
        "layout": state.get("layout", "merged"),
        "notes": state.get("notes", ""),
    }
    count, size = (
        await session.execute(
            select(
                func.count(), func.coalesce(func.sum(func.octet_length(HistoryEvent.raw_line)), 0)
            ).where(HistoryEvent.project_id == project_id, HistoryEvent.job_id == job_id)
        )
    ).one()
    if count > MAX_EVENTS or size > maximum:
        raise DomainError(
            "BUNDLE_BYTE_LIMIT", "The capture exceeds the configured bundle budget.", 413
        )
    events = [
        event_payload(row)
        for row in (
            await session.scalars(
                select(HistoryEvent)
                .where(HistoryEvent.project_id == project_id, HistoryEvent.job_id == job_id)
                .order_by(HistoryEvent.capture_seq)
            )
        ).all()
    ]
    bookmarks = (
        await session.scalars(
            select(InvestigationBookmark)
            .where(
                InvestigationBookmark.project_id == project_id,
                InvestigationBookmark.job_id == job_id,
            )
            .order_by(InvestigationBookmark.created_us, InvestigationBookmark.id)
        )
    ).all()
    response = await job_response(session, job)
    event_processes = {event["event_id"]: event["process_id"] for event in events}

    def selected_bookmark(bookmark: InvestigationBookmark) -> bool:
        process_id = event_processes.get(bookmark.event_id)
        if process_id is None and bookmark.context:
            process_id = next(
                (
                    item["event"]["process_id"]
                    for item in bookmark.context["items"]
                    if item["is_anchor"]
                ),
                None,
            )
        return process_id is None or process_id in selection["process_ids"]

    document = dict(
        schema_version="1.0",
        origin=dict(
            project_id=project_id,
            investigation_id=job_id,
            config_revision=job.config_revision,
            snapshot_revision=job.snapshot_revision,
        ),
        selection=selection,
        topology=safe_topology(job.config_snapshot, selection["process_ids"]),
        sources=[
            source
            for source in response["coverage"]
            if source["process_id"] in selection["process_ids"]
        ],
        events=[event for event in events if event["process_id"] in selection["process_ids"]],
        bookmarks=[
            dict(
                id=b.id,
                event_id=b.event_id,
                annotation=b.annotation,
                pin_context=b.pin_context,
                context=b.context or None,
                process_name_snapshot=b.process_name_snapshot,
                server_name_snapshot=b.server_name_snapshot,
                created_at=format_time(b.created_us),
            )
            for b in bookmarks
            if selected_bookmark(b)
        ],
        coverage_status="unavailable" if saved and saved.expired else response["coverage_status"],
        errors=response["errors"],
        redaction=dict(applied=False, term_count=0, replacement="[REDACTED]", warning=WARNING),
    )
    return document, await content_revision(session, job)


async def checked_preview(
    session: AsyncSession,
    actor: Principal,
    project_id: str,
    preview_id: str,
    login_hash: str,
    direction: str,
    *,
    include_document: bool = True,
) -> BundlePreview:
    actor = await services.current_actor(session, actor)
    query = select(BundlePreview)
    if not include_document:
        query = query.options(defer(BundlePreview.document))
    preview = await session.scalar(
        query.where(
            BundlePreview.project_id == project_id, BundlePreview.id == preview_id
        ).with_for_update()
    )
    if (
        preview is None
        or preview.owner_user_id != actor.user_id
        or preview.auth_version != actor.auth_version
        or preview.auth_session_hash != login_hash
        or preview.direction != direction
    ):
        raise not_found()
    if preview.expires_us <= services.utc_now_us():
        raise DomainError("BUNDLE_PREVIEW_EXPIRED", "Prepare a new bundle preview.", 410)
    project = await session.get(Project, project_id)
    if project is None or project.revision != preview.project_revision:
        raise DomainError(
            "BUNDLE_PREVIEW_STALE", "The system changed; prepare a new bundle preview.", 409
        )
    if direction == "export" and (preview.source_job_id or "").startswith("offline:"):
        offline = await checked_offline(
            session, actor, project_id, (preview.source_job_id or "")[8:]
        )
        analysis = await session.get(OfflineAnalysis, (project_id, offline.id))
        if offline_revision(offline, analysis) != preview.content_revision:
            raise DomainError(
                "BUNDLE_PREVIEW_STALE",
                "The investigation changed; prepare a new bundle preview.",
                409,
            )
    elif direction == "export":
        job = await checked_job(session, actor, project_id, preview.source_job_id or "")
        if await content_revision(session, job) != preview.content_revision:
            raise DomainError(
                "BUNDLE_PREVIEW_STALE",
                "The investigation changed; prepare a new bundle preview.",
                409,
            )
    authorize(
        actor,
        "bundle.export" if direction == "export" else "bundle.import",
        owner_user_id=preview.owner_user_id,
    )
    return preview


def preview_response(preview: BundlePreview) -> dict:
    return dict(
        project_id=preview.project_id,
        preview_id=preview.id,
        expires_at=format_time(preview.expires_us),
        digest=preview.digest,
        document=preview.document,
        warnings=[WARNING],
    )


async def checked_offline(
    session: AsyncSession, actor: Principal, project_id: str, investigation_id: str
) -> OfflineInvestigation:
    actor = await services.current_actor(session, actor)
    ProjectContext(project_id, actor.user_id)
    row = await session.get(OfflineInvestigation, (project_id, investigation_id))
    if row is None or row.owner_user_id != actor.user_id:
        raise not_found()
    authorize(actor, "investigation.read", owner_user_id=row.owner_user_id)
    return row


def offline_response(row: OfflineInvestigation) -> dict:
    document = row.document
    selection, sources = document["selection"], document["sources"]
    job = dict(
        project_id=row.project_id,
        job_id=row.id,
        investigation_id=row.id,
        workspace_id="offline",
        process_ids=selection["process_ids"],
        **{"from": selection["from"]},
        to=selection["to"],
        status="completed"
        if document["coverage_status"] == "complete_for_scanned_candidates"
        else "partial",
        demo_mode=False,
        source_snapshot_revision=1,
        source_count=len(sources),
        scanned_sources=len(sources),
        event_count=len(document["events"]),
        parse_issue_count=sum(event["timestamp_us"] is None for event in document["events"]),
        downloaded_bytes=sum(source["bytes"] for source in sources),
        expanded_bytes=sum(source["expanded_bytes"] for source in sources),
        coverage_status=document["coverage_status"],
        coverage=sources,
        errors=document["errors"],
    )
    return dict(
        project_id=row.project_id,
        investigation_id=row.id,
        offline=True,
        document=document,
        created_at=format_time(row.created_us),
        job=job,
    )


def offline_revision(row: OfflineInvestigation, analysis: OfflineAnalysis | None) -> str:
    return digest([row.digest, analysis.revision if analysis else 0])


def offline_bookmarks(row: OfflineInvestigation, analysis: OfflineAnalysis | None) -> list[dict]:
    if analysis is not None:
        return copy.deepcopy(analysis.bookmarks)
    output = []
    for bookmark in row.document["bookmarks"]:
        context = copy.deepcopy(bookmark["context"])
        if context:
            context["project_id"] = row.project_id
            for item in context["items"]:
                item["event"]["project_id"] = row.project_id
        output.append(
            dict(
                bookmark_id=bookmark["id"],
                event_id=bookmark["event_id"],
                annotation=bookmark["annotation"],
                pin_context=bookmark["pin_context"],
                context=context,
                process_name_snapshot=bookmark["process_name_snapshot"],
                server_name_snapshot=bookmark["server_name_snapshot"],
                created_us=canonical_time(bookmark["created_at"]),
                availability="retained" if context else "unavailable",
            )
        )
    return output


def effective_document(row: OfflineInvestigation, analysis: OfflineAnalysis | None) -> dict:
    document = copy.deepcopy(row.document)
    if analysis is not None:
        document["selection"] = copy.deepcopy(analysis.state)
    bookmarks = []
    for bookmark in offline_bookmarks(row, analysis):
        context = copy.deepcopy(bookmark["context"])
        if context:
            context["project_id"] = document["origin"]["project_id"]
            for item in context["items"]:
                item["event"]["project_id"] = document["origin"]["project_id"]
        bookmarks.append(
            dict(
                id=bookmark["bookmark_id"],
                event_id=bookmark["event_id"],
                annotation=bookmark["annotation"],
                pin_context=bookmark["pin_context"],
                context=context,
                process_name_snapshot=bookmark["process_name_snapshot"],
                server_name_snapshot=bookmark["server_name_snapshot"],
                created_at=format_time(bookmark["created_us"]),
            )
        )
    document["bookmarks"] = bookmarks
    return document


async def revise_offline(
    session: AsyncSession, row: OfflineInvestigation, expected: int
) -> OfflineAnalysis:
    await session.scalar(
        select(OfflineInvestigation.id)
        .where(OfflineInvestigation.project_id == row.project_id, OfflineInvestigation.id == row.id)
        .with_for_update()
    )
    analysis = await session.get(OfflineAnalysis, (row.project_id, row.id), populate_existing=True)
    if expected != (analysis.revision if analysis else 0):
        raise DomainError(
            "REVISION_CONFLICT", "Saved analysis changed; reload it before saving.", 409
        )
    if analysis is None:
        analysis = OfflineAnalysis(
            project_id=row.project_id,
            investigation_id=row.id,
            owner_user_id=row.owner_user_id,
            revision=1,
            state=copy.deepcopy(row.document["selection"]),
            bookmarks=offline_bookmarks(row, None),
        )
        session.add(analysis)
    else:
        analysis.revision += 1
    return analysis


def event_order(event: dict) -> tuple:
    return (
        event["timestamp_us"] if event["timestamp_us"] is not None else 0,
        event["process_id"],
        event["source"]["source_revision_id"],
        event["source"]["member_ordinal"] if event["source"]["member_ordinal"] is not None else -1,
        event["source"]["byte_start"],
        event["event_id"],
    )


def matching_events(document: dict, payload: HistoricalQueryInput) -> list[dict]:
    start, end = canonical_time(payload.from_), canonical_time(payload.to)
    global_filter = payload.filter.predicate()
    per_process = {key: value.predicate() for key, value in payload.per_process_filters.items()}
    output = []
    for event in document["events"]:
        timestamp = event["timestamp_us"]
        if event["process_id"] not in payload.process_ids:
            continue
        if payload.lane == "diagnostic":
            if timestamp is not None:
                continue
        elif timestamp is None or not start <= timestamp < end:
            continue
        if (
            payload.correlation is not None
            and payload.correlation.mode == "exact"
            and event["metadata"].get(payload.correlation.field) != payload.correlation.value
        ):
            continue
        oversized = event["parse_status"] == "oversized_line"
        if (
            not oversized
            and payload.correlation is not None
            and payload.correlation.mode == "literal"
        ):
            text, term = event["raw_line"], payload.correlation.value
            if not payload.filter.case_sensitive:
                text, term = text.casefold(), term.casefold()
            if term not in text:
                continue
        if (
            oversized
            or global_filter.matches(event["raw_line"])
            and (
                event["process_id"] not in per_process
                or per_process[event["process_id"]].matches(event["raw_line"])
            )
        ):
            output.append(event)
    return sorted(output, key=event_order)


def build_bundle_router(
    transaction: Callable, authenticated: Callable, protected_write: Callable
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}")
    Session = Annotated[AsyncSession, Depends(transaction, scope="function")]
    Actor = Annotated[Principal, Depends(authenticated)]
    Writer = Annotated[Principal, Depends(protected_write)]

    def login_hash(request: Request) -> str:
        return token_hash(request.cookies.get("__Host-si-session", "")) or ""

    async def save_preview(
        session: AsyncSession,
        actor: Principal,
        request: Request,
        project_id: str,
        document: dict,
        direction: str,
        job_id: str | None,
        revision: str,
        expected_project_revision: int,
    ) -> dict:
        actor = await services.current_actor(session, actor)
        await session.scalar(select(User.id).where(User.id == actor.user_id).with_for_update())
        project = await session.get(Project, project_id)
        if project is None:
            raise not_found()
        if project.revision != expected_project_revision:
            raise DomainError(
                "BUNDLE_PREVIEW_STALE", "The system changed; prepare a new preview.", 409
            )
        if direction == "export":
            if (job_id or "").startswith("offline:"):
                source = await checked_offline(session, actor, project_id, (job_id or "")[8:])
                source_analysis = await session.get(OfflineAnalysis, (project_id, source.id))
                current = offline_revision(source, source_analysis)
            else:
                source_job = await checked_job(session, actor, project_id, job_id or "", lock=True)
                current = await content_revision(session, source_job)
            if revision != current:
                raise DomainError(
                    "BUNDLE_PREVIEW_STALE", "The investigation changed; prepare a new preview.", 409
                )
        authorize(
            actor,
            "bundle.export" if direction == "export" else "bundle.import",
            owner_user_id=actor.user_id,
        )
        now = services.utc_now_us()
        # Bound persisted staging per owner; expiry never removes another owner's data.
        valid_login = (
            select(AuthSession.token_hash)
            .where(
                AuthSession.token_hash == BundlePreview.auth_session_hash,
                AuthSession.user_id == actor.user_id,
                AuthSession.auth_version == actor.auth_version,
                AuthSession.expires_us > now,
                AuthSession.last_seen_us > now - request.app.state.config.idle_timeout_us,
            )
            .correlate(BundlePreview)
            .exists()
        )
        stale_scope = (
            BundlePreview.owner_user_id == actor.user_id,
            or_(
                BundlePreview.expires_us <= now,
                BundlePreview.auth_version != actor.auth_version,
                ~valid_login,
            ),
        )
        stale = select(BundlePreview.project_id, BundlePreview.id).where(*stale_scope)
        await session.execute(
            delete(BundleDownload).where(
                BundleDownload.owner_user_id == actor.user_id,
                tuple_(BundleDownload.project_id, BundleDownload.preview_id).in_(stale),
            )
        )
        await session.execute(
            delete(BundlePreview).where(
                *stale_scope,
            )
        )
        active = await session.scalar(
            select(func.count())
            .select_from(BundlePreview)
            .where(BundlePreview.owner_user_id == actor.user_id, BundlePreview.expires_us > now)
        )
        if active is not None and active >= 4:
            raise DomainError(
                "BUNDLE_PREVIEW_LIMIT",
                "At most four pending bundle previews per account are allowed; wait for expiry.",
                429,
            )
        preview = BundlePreview(
            project_id=project_id,
            id=str(uuid4()),
            owner_user_id=actor.user_id,
            auth_version=actor.auth_version,
            auth_session_hash=login_hash(request),
            direction=direction,
            source_job_id=job_id,
            project_revision=project.revision,
            content_revision=revision,
            digest=digest(document),
            document=document,
            created_us=now,
            expires_us=now + PREVIEW_US,
        )
        session.add(preview)
        await session.flush()
        return preview_response(preview)

    @router.post(
        "/bundles/export/preview",
        response_model=BundlePreviewResponse,
        openapi_extra={"x-permission": "bundle.export"},
    )
    async def export_preview(
        project_id: str, payload: ExportInput, request: Request, actor: Writer, session: Session
    ) -> dict:
        maximum, member_maximum, _ratio, _timeout = bundle_limits(request)
        project = await session.get(Project, project_id)
        if project is None:
            raise not_found()
        expected_project_revision = project.revision
        document, revision = await export_document(
            session, actor, project_id, payload.investigation_id, min(maximum, member_maximum)
        )

        def prepare() -> dict:
            deadline = time.monotonic() + _timeout
            projected = redact(
                document,
                payload.redact_terms,
                payload.replacement,
                max_bytes=min(maximum, member_maximum),
                deadline=deadline,
            )
            projected["redaction"] = dict(
                applied=bool(payload.redact_terms) or document["redaction"]["applied"],
                term_count=len(payload.redact_terms),
                replacement=payload.replacement,
                warning=WARNING,
            )
            try:
                result = BundleDocument.model_validate(projected).model_dump(
                    mode="json", by_alias=True
                )
            except (ValidationError, ValueError):
                raise DomainError(
                    "INVALID_REDACTION",
                    "These terms alter required identity/time fields; choose narrower redaction terms.",
                    422,
                ) from None
            if len(encoded(result)) > min(maximum, member_maximum):
                raise DomainError(
                    "BUNDLE_BYTE_LIMIT", "The bundle exceeds the configured byte budget.", 413
                )
            if time.monotonic() > deadline:
                raise DomainError("BUNDLE_TIMEOUT", "Redaction exceeded its time budget.", 408)
            return result

        offline = await session.get(OfflineInvestigation, (project_id, payload.investigation_id))
        source_id = (
            "offline:" + payload.investigation_id
            if offline is not None
            else payload.investigation_id
        )
        await session.commit()
        prepared = await bundle_work(request, prepare)
        actor = await authenticated(request, session)
        return await save_preview(
            session,
            actor,
            request,
            project_id,
            prepared,
            "export",
            source_id,
            revision,
            expected_project_revision,
        )

    @router.post(
        "/bundles/export",
        response_model=BundleDownloadResponse,
        openapi_extra={"x-permission": "bundle.export"},
    )
    async def grant_export(
        project_id: str, payload: PreviewInput, request: Request, actor: Writer, session: Session
    ) -> dict:
        preview = await checked_preview(
            session, actor, project_id, payload.preview_id, login_hash(request), "export"
        )
        opaque = issue_token()
        await session.execute(
            delete(BundleDownload).where(
                BundleDownload.project_id == project_id, BundleDownload.preview_id == preview.id
            )
        )
        session.add(
            BundleDownload(
                token_hash=token_hash(opaque),
                project_id=project_id,
                preview_id=preview.id,
                owner_user_id=actor.user_id,
                auth_version=actor.auth_version,
                auth_session_hash=login_hash(request),
                expires_us=min(preview.expires_us, services.utc_now_us() + 60_000_000),
            )
        )
        services.audit(
            session, actor, "bundle.export", project_id, preview.id, services.utc_now_us()
        )
        return dict(
            project_id=project_id,
            download_id=opaque,
            url=f"/api/v1/projects/{project_id}/bundle-downloads/{opaque}",
        )

    @router.post(
        "/bundles/previews/{preview_id}/cancel",
        response_model=BundleCancelResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def cancel_preview(
        project_id: str,
        preview_id: str,
        payload: EmptyInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        actor = await services.current_actor(session, actor)
        preview = await session.get(BundlePreview, (project_id, preview_id))
        if (
            preview is None
            or preview.owner_user_id != actor.user_id
            or preview.auth_version != actor.auth_version
            or preview.auth_session_hash != login_hash(request)
        ):
            raise not_found()
        await session.execute(
            delete(BundleDownload).where(
                BundleDownload.project_id == project_id,
                BundleDownload.preview_id == preview_id,
                BundleDownload.owner_user_id == actor.user_id,
            )
        )
        await session.delete(preview)
        return dict(project_id=project_id, preview_id=preview_id, cancelled=True)

    @router.get("/bundle-downloads/{opaque_id}", openapi_extra={"x-permission": "download.read"})
    async def download(
        project_id: str, opaque_id: str, request: Request, actor: Actor, session: Session
    ) -> StreamingResponse:
        grant_hash = token_hash(opaque_id) or ""
        grant = await session.get(BundleDownload, grant_hash)
        if (
            grant is None
            or grant.project_id != project_id
            or grant.owner_user_id != actor.user_id
            or grant.auth_version != actor.auth_version
            or grant.auth_session_hash != login_hash(request)
            or grant.expires_us <= services.utc_now_us()
        ):
            raise not_found()
        preview = await checked_preview(
            session, actor, project_id, grant.preview_id, login_hash(request), "export"
        )
        maximum, _member, _ratio, _timeout = bundle_limits(request)
        document = preview.document
        preview_id = preview.id
        await session.commit()
        content = await bundle_work(request, lambda: pack_bundle(document, maximum))
        actor = await authenticated(request, session)
        await checked_preview(
            session,
            actor,
            project_id,
            preview_id,
            login_hash(request),
            "export",
            include_document=False,
        )
        await session.commit()

        async def chunks() -> AsyncIterator[bytes]:
            for offset in range(0, len(content), 262144):
                async with request.app.state.sessions.begin() as check:
                    now = services.utc_now_us()
                    current = await check.get(BundleDownload, grant_hash)
                    login = await check.get(AuthSession, login_hash(request))
                    user = await check.get(User, actor.user_id)
                    if (
                        current is None
                        or current.expires_us <= now
                        or login is None
                        or user is None
                        or not user.enabled
                        or user.auth_version != actor.auth_version
                        or login.expires_us <= now
                        or now - login.last_seen_us > request.app.state.config.idle_timeout_us
                        or not await request.app.state.supervisor.healthy()
                    ):
                        return
                    try:
                        await checked_preview(
                            check,
                            actor,
                            project_id,
                            current.preview_id,
                            login_hash(request),
                            "export",
                            include_document=False,
                        )
                    except DomainError:
                        return
                yield content[offset : offset + 262144]

        return StreamingResponse(
            chunks(),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="investigation.zip"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    @router.post(
        "/bundles/import/preview",
        response_model=BundlePreviewResponse,
        openapi_extra={
            "x-permission": "bundle.import",
            "requestBody": {
                "required": True,
                "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
            },
        },
    )
    async def import_preview(
        project_id: str, request: Request, actor: Writer, session: Session
    ) -> dict:
        actor = await services.current_actor(session, actor)
        project = await session.get(Project, project_id)
        if project is None:
            raise not_found()
        expected_project_revision = project.revision
        maximum, member, ratio, timeout = bundle_limits(request)
        await session.commit()
        upload_slots = request.app.state.history.bundle_upload_slots
        if upload_slots.locked():
            raise DomainError(
                "BUNDLE_UPLOAD_LIMIT", "The bounded bundle upload slots are busy; retry later.", 429
            )
        await upload_slots.acquire()
        try:
            size = 0
            with tempfile.SpooledTemporaryFile(max_size=1_048_576, mode="w+b") as uploaded:
                try:
                    async with asyncio.timeout(timeout):
                        async for chunk in request.stream():
                            size += len(chunk)
                            if size > maximum:
                                raise DomainError(
                                    "BUNDLE_BYTE_LIMIT",
                                    "The uploaded bundle exceeds the byte budget.",
                                    413,
                                )
                            await bundle_work(request, partial(uploaded.write, chunk))
                        await bundle_work(request, lambda: uploaded.seek(0))
                        document = await bundle_work(
                            request,
                            lambda: unpack_bundle(
                                cast(BinaryIO, uploaded),
                                maximum,
                                member,
                                ratio,
                                timeout,
                                request.app.state.config.history_limits.get(
                                    "max_line_bytes", 262144
                                ),
                            ),
                        )
                except TimeoutError:
                    raise DomainError(
                        "BUNDLE_TIMEOUT",
                        "The bundle upload/validation exceeded its time budget.",
                        408,
                    ) from None
        finally:
            upload_slots.release()
        actor = await authenticated(request, session)
        return await save_preview(
            session,
            actor,
            request,
            project_id,
            document,
            "import",
            None,
            digest(document),
            expected_project_revision,
        )

    @router.post(
        "/bundles/import",
        response_model=OfflineResponse,
        status_code=201,
        openapi_extra={"x-permission": "bundle.import"},
    )
    async def import_commit(
        project_id: str, payload: PreviewInput, request: Request, actor: Writer, session: Session
    ) -> dict:
        preview = await checked_preview(
            session, actor, project_id, payload.preview_id, login_hash(request), "import"
        )
        document = preview.document
        await session.commit()
        verified_digest = await bundle_work(request, lambda: digest(document))
        actor = await authenticated(request, session)
        preview = await checked_preview(
            session, actor, project_id, payload.preview_id, login_hash(request), "import"
        )
        if verified_digest != preview.digest:
            raise DomainError("BUNDLE_PREVIEW_STALE", "The bundle preview changed.", 409)
        row = OfflineInvestigation(
            project_id=project_id,
            id=str(uuid4()),
            owner_user_id=actor.user_id,
            digest=preview.digest,
            document=copy.deepcopy(preview.document),
            created_us=services.utc_now_us(),
        )
        session.add(row)
        await session.flush()
        await session.delete(preview)
        services.audit(session, actor, "bundle.import", project_id, row.id, services.utc_now_us())
        return offline_response(row)

    @router.get(
        "/bundle-investigations",
        response_model=OfflineListResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def listing(project_id: str, actor: Actor, session: Session) -> dict:
        actor = await services.current_actor(session, actor)
        if await session.get(Project, project_id) is None:
            raise not_found()
        rows = (
            await session.execute(
                select(
                    OfflineInvestigation.id,
                    OfflineInvestigation.created_us,
                    func.json_extract(OfflineInvestigation.document, "$.selection").label(
                        "selection"
                    ),
                    func.json_unquote(
                        func.json_extract(OfflineInvestigation.document, "$.coverage_status")
                    ).label("coverage"),
                    func.json_length(OfflineInvestigation.document, "$.events").label(
                        "event_count"
                    ),
                    func.json_length(OfflineInvestigation.document, "$.sources").label(
                        "source_count"
                    ),
                )
                .where(
                    OfflineInvestigation.project_id == project_id,
                    OfflineInvestigation.owner_user_id == actor.user_id,
                )
                .order_by(OfflineInvestigation.created_us.desc())
                .limit(100)
            )
        ).all()
        items = []
        for row in rows:
            selection = (
                json.loads(row.selection) if isinstance(row.selection, str) else row.selection
            )
            job = dict(
                project_id=project_id,
                job_id=row.id,
                investigation_id=row.id,
                workspace_id="offline",
                process_ids=selection["process_ids"],
                **{"from": selection["from"]},
                to=selection["to"],
                status="completed"
                if row.coverage == "complete_for_scanned_candidates"
                else "partial",
                demo_mode=False,
                source_snapshot_revision=1,
                source_count=row.source_count,
                scanned_sources=row.source_count,
                event_count=row.event_count,
                parse_issue_count=0,
                downloaded_bytes=0,
                expanded_bytes=0,
                coverage_status=row.coverage,
                coverage=[],
                errors=[],
            )
            items.append(
                dict(
                    project_id=project_id,
                    investigation_id=row.id,
                    offline=True,
                    created_at=format_time(row.created_us),
                    job=job,
                )
            )
        return dict(project_id=project_id, items=items)

    @router.get(
        "/bundle-investigations/{investigation_id}",
        response_model=OfflineResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def read(project_id: str, investigation_id: str, actor: Actor, session: Session) -> dict:
        return offline_response(await checked_offline(session, actor, project_id, investigation_id))

    @router.post(
        "/bundle-investigations/{investigation_id}/query",
        response_model=HistoricalQueryResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def query(
        project_id: str,
        investigation_id: str,
        payload: HistoricalQueryInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        row = await checked_offline(session, actor, project_id, investigation_id)
        if not set(payload.process_ids) <= set(row.document["selection"]["process_ids"]):
            raise not_found()
        identity = payload.model_dump(mode="json", by_alias=True, exclude={"cursor", "limit"})
        query_hash = digest(identity)
        offset = 0
        if payload.cursor:
            cursor = await session.get(OfflineCursor, token_hash(payload.cursor) or "")
            if (
                cursor is None
                or cursor.project_id != project_id
                or cursor.investigation_id != investigation_id
                or cursor.owner_user_id != actor.user_id
                or cursor.auth_version != actor.auth_version
                or cursor.expires_us <= services.utc_now_us()
            ):
                raise not_found()
            if cursor.query_hash != query_hash:
                raise DomainError("CURSOR_MISMATCH", "The query changed; start a new page.", 409)
            offset = cursor.row_offset
        await session.commit()
        matches = await bundle_work(request, lambda: matching_events(row.document, payload))
        actor = await authenticated(request, session)
        await checked_offline(session, actor, project_id, investigation_id)
        page: list[dict] = []
        page_bytes = 0
        for event in matches[offset : offset + payload.limit]:
            size = len(event["raw_line"].encode("utf-8"))
            if page and page_bytes + size > 8_388_608:
                break
            page.append(event)
            page_bytes += size
        next_cursor = None
        if offset + len(page) < len(matches):
            next_cursor = issue_token()
            await session.execute(
                delete(OfflineCursor).where(OfflineCursor.expires_us <= services.utc_now_us())
            )
            session.add(
                OfflineCursor(
                    token_hash=token_hash(next_cursor),
                    project_id=project_id,
                    investigation_id=investigation_id,
                    owner_user_id=actor.user_id,
                    auth_version=actor.auth_version,
                    query_hash=query_hash,
                    row_offset=offset + len(page),
                    expires_us=services.utc_now_us() + PREVIEW_US,
                )
            )
        return dict(
            project_id=project_id,
            items=[{**event, "project_id": project_id} for event in page],
            next_cursor=next_cursor,
            matched_count=None
            if row.document["coverage_status"] == "unavailable"
            or any(event["parse_status"] == "oversized_line" for event in matches)
            else len(matches),
            parse_issue_count=sum(e["timestamp_us"] is None for e in row.document["events"]),
            source_snapshot_revision=1,
            partial=row.document["coverage_status"] != "complete_for_scanned_candidates",
            coverage=row.document["sources"],
            availability="unavailable"
            if row.document["coverage_status"] == "unavailable"
            else "partial"
            if row.document["coverage_status"] != "complete_for_scanned_candidates"
            else "retained",
        )

    @router.post(
        "/bundle-investigations/{investigation_id}/events/{event_id}/context",
        response_model=HistoricalContextResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def context(
        project_id: str,
        investigation_id: str,
        event_id: str,
        payload: HistoricalContextInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        row = await checked_offline(session, actor, project_id, investigation_id)
        analysis = await session.get(OfflineAnalysis, (project_id, investigation_id))
        retained_bookmarks = offline_bookmarks(row, analysis)
        await session.commit()

        def prepare() -> dict:
            events = row.document["events"]
            anchor = next((event for event in events if event["event_id"] == event_id), None)
            if anchor is None:
                # Pinned context survives unavailable original captures.
                for bookmark in retained_bookmarks:
                    if bookmark["event_id"] == event_id and bookmark["context"]:
                        events = [item["event"] for item in bookmark["context"]["items"]]
                        anchor = next(
                            (event for event in events if event["event_id"] == event_id), None
                        )
                        break
            if anchor is None:
                raise not_found()
            source_events = sorted(
                [
                    event
                    for event in events
                    if event["source"]["source_revision_id"]
                    == anchor["source"]["source_revision_id"]
                    and event["source"]["member_ordinal"] == anchor["source"]["member_ordinal"]
                ],
                key=lambda event: (event["source"]["byte_start"], event["event_id"]),
            )
            index = next(
                i for i, event in enumerate(source_events) if event["event_id"] == event_id
            )
            start, end = canonical_time(payload.from_), canonical_time(payload.to)
            global_filter = payload.filter.predicate()
            per_process = {
                key: value.predicate() for key, value in payload.per_process_filters.items()
            }
            items = []
            actual_bytes = 0
            for event in source_events[max(0, index - payload.before) : index + payload.after + 1]:
                actual_bytes += len(event["raw_line"].encode("utf-8"))
                if actual_bytes > 8_388_608:
                    raise DomainError(
                        "CONTEXT_BYTE_LIMIT",
                        "Narrow the context to stay within the eight-MiB byte budget.",
                        413,
                    )
                timestamp = event["timestamp_us"]
                predicate = per_process.get(event["process_id"])
                items.append(
                    dict(
                        event={**event, "project_id": project_id},
                        outside_time_bounds=timestamp is None or not start <= timestamp < end,
                        matches_filter=None
                        if event["parse_status"] == "oversized_line"
                        else global_filter.matches(event["raw_line"])
                        and (predicate is None or predicate.matches(event["raw_line"])),
                        is_anchor=event["event_id"] == event_id,
                    )
                )
            return dict(project_id=project_id, event_id=event_id, items=items)

        result = await bundle_work(request, prepare)
        actor = await authenticated(request, session)
        await checked_offline(session, actor, project_id, investigation_id)
        return result

    async def analysis_response(session: AsyncSession, row: OfflineInvestigation) -> dict:
        analysis = await session.get(OfflineAnalysis, (row.project_id, row.id))
        selection = analysis.state if analysis else row.document["selection"]
        return dict(
            project_id=row.project_id,
            investigation_id=row.id,
            revision=analysis.revision if analysis else 0,
            saved=True,
            **selection,
            pinned=True,
            collection_references=[row.id],
            availability="unavailable"
            if row.document["coverage_status"] == "unavailable"
            else "partial"
            if row.document["coverage_status"] != "complete_for_scanned_candidates"
            else "retained",
            source_snapshot_revision=1,
        )

    async def bookmarks_response(session: AsyncSession, row: OfflineInvestigation) -> dict:
        analysis = await session.get(OfflineAnalysis, (row.project_id, row.id))
        return dict(
            project_id=row.project_id,
            investigation_id=row.id,
            revision=analysis.revision if analysis else 0,
            items=offline_bookmarks(row, analysis),
        )

    @router.get(
        "/bundle-investigations/{investigation_id}/workspace",
        response_model=SavedWorkspaceResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def read_workspace(
        project_id: str, investigation_id: str, actor: Actor, session: Session
    ) -> dict:
        return await analysis_response(
            session, await checked_offline(session, actor, project_id, investigation_id)
        )

    @router.patch(
        "/bundle-investigations/{investigation_id}/workspace",
        response_model=SavedWorkspaceResponse,
        openapi_extra={"x-permission": "investigation.write"},
    )
    async def save_workspace(
        project_id: str,
        investigation_id: str,
        payload: SavedWorkspaceInput,
        actor: Writer,
        session: Session,
    ) -> dict:
        row = await checked_offline(session, actor, project_id, investigation_id)
        authorize(actor, "investigation.write", owner_user_id=row.owner_user_id)
        if not set(payload.process_ids) <= set(row.document["selection"]["process_ids"]):
            raise DomainError(
                "INVALID_SELECTION", "Select processes retained in this imported bundle.", 422
            )
        analysis = await revise_offline(session, row, payload.expected_revision)
        analysis.state = payload.model_dump(
            mode="json", by_alias=True, exclude={"expected_revision", "pinned"}
        )
        await session.flush()
        return await analysis_response(session, row)

    @router.get(
        "/bundle-investigations/{investigation_id}/bookmarks",
        response_model=BookmarkResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def read_bookmarks(
        project_id: str, investigation_id: str, actor: Actor, session: Session
    ) -> dict:
        return await bookmarks_response(
            session, await checked_offline(session, actor, project_id, investigation_id)
        )

    @router.post(
        "/bundle-investigations/{investigation_id}/bookmarks",
        response_model=BookmarkResponse,
        status_code=201,
        openapi_extra={"x-permission": "bookmark.write"},
    )
    async def create_bookmark(
        project_id: str,
        investigation_id: str,
        payload: BookmarkCreate,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        row = await checked_offline(session, actor, project_id, investigation_id)
        authorize(actor, "bookmark.write", owner_user_id=row.owner_user_id)
        context_input = HistoricalContextInput.model_validate(
            payload.model_dump(
                by_alias=True,
                exclude={"expected_revision", "event_id", "annotation", "pin_context"},
            )
        )
        expanded = await context(
            project_id, investigation_id, payload.event_id, context_input, request, actor, session
        )
        anchor = next(item["event"] for item in expanded["items"] if item["is_anchor"])
        analysis = await revise_offline(session, row, payload.expected_revision)
        if len(analysis.bookmarks) >= 1000:
            raise DomainError(
                "BOOKMARK_LIMIT", "At most 1000 bookmarks per investigation are allowed.", 429
            )
        analysis.bookmarks = [
            *analysis.bookmarks,
            dict(
                bookmark_id=str(uuid4()),
                event_id=payload.event_id,
                annotation=payload.annotation,
                pin_context=payload.pin_context,
                context=expanded if payload.pin_context else None,
                process_name_snapshot=anchor["process_name_snapshot"],
                server_name_snapshot=anchor["server_name_snapshot"],
                created_us=services.utc_now_us(),
                availability="retained" if payload.pin_context else "unavailable",
            ),
        ]
        if len(encoded(analysis.bookmarks)) > 33_554_432:
            raise DomainError(
                "BOOKMARK_BYTE_LIMIT",
                "Pinned bookmark context exceeds the 32-MiB investigation budget.",
                413,
            )
        await session.flush()
        return await bookmarks_response(session, row)

    @router.patch(
        "/bundle-investigations/{investigation_id}/bookmarks/{bookmark_id}",
        response_model=BookmarkResponse,
        openapi_extra={"x-permission": "bookmark.write"},
    )
    async def update_bookmark(
        project_id: str,
        investigation_id: str,
        bookmark_id: str,
        payload: BookmarkUpdate,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        row = await checked_offline(session, actor, project_id, investigation_id)
        authorize(actor, "bookmark.write", owner_user_id=row.owner_user_id)
        existing = await session.get(OfflineAnalysis, (project_id, investigation_id))
        bookmarks = offline_bookmarks(row, existing)
        bookmark = next((item for item in bookmarks if item["bookmark_id"] == bookmark_id), None)
        if bookmark is None:
            raise not_found()
        if payload.pin_context and not bookmark["context"]:
            state = existing.state if existing else row.document["selection"]
            context_input = HistoricalContextInput.model_validate(
                {
                    "from": state["from"],
                    "to": state["to"],
                    "filter": state["filter"],
                    "per_process_filters": state["per_process_filters"],
                }
            )
            bookmark["context"] = await context(
                project_id,
                investigation_id,
                bookmark["event_id"],
                context_input,
                request,
                actor,
                session,
            )
        bookmark.update(annotation=payload.annotation, pin_context=payload.pin_context)
        if not payload.pin_context:
            bookmark["context"] = None
        bookmark["availability"] = "retained" if bookmark["context"] else "unavailable"
        if len(encoded(bookmarks)) > 33_554_432:
            raise DomainError(
                "BOOKMARK_BYTE_LIMIT",
                "Pinned bookmark context exceeds the 32-MiB investigation budget.",
                413,
            )
        analysis = await revise_offline(session, row, payload.expected_revision)
        analysis.bookmarks = bookmarks
        await session.flush()
        return await bookmarks_response(session, row)

    @router.post(
        "/bundle-investigations/{investigation_id}/bookmarks/{bookmark_id}/delete",
        response_model=BookmarkResponse,
        openapi_extra={"x-permission": "bookmark.write"},
    )
    @router.delete(
        "/bundle-investigations/{investigation_id}/bookmarks/{bookmark_id}",
        response_model=BookmarkResponse,
        openapi_extra={"x-permission": "bookmark.write"},
    )
    async def delete_bookmark(
        project_id: str,
        investigation_id: str,
        bookmark_id: str,
        payload: RevisionInput,
        actor: Writer,
        session: Session,
    ) -> dict:
        row = await checked_offline(session, actor, project_id, investigation_id)
        authorize(actor, "bookmark.write", owner_user_id=row.owner_user_id)
        analysis = await revise_offline(session, row, payload.expected_revision)
        retained = [item for item in analysis.bookmarks if item["bookmark_id"] != bookmark_id]
        if len(retained) == len(analysis.bookmarks):
            raise not_found()
        analysis.bookmarks = retained
        await session.flush()
        return await bookmarks_response(session, row)

    @router.post(
        "/bundle-investigations/{investigation_id}/correlation",
        response_model=CorrelationResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def correlation(
        project_id: str,
        investigation_id: str,
        payload: CorrelationInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        query_input = HistoricalQueryInput.model_validate(
            {
                **payload.model_dump(by_alias=True, exclude={"mode", "field", "value"}),
                "correlation": {
                    "mode": payload.mode,
                    "field": payload.field,
                    "value": payload.value,
                },
            }
        )
        result = await query(project_id, investigation_id, query_input, request, actor, session)
        row = await checked_offline(session, actor, project_id, investigation_id)
        await session.commit()

        def trace() -> list[dict]:
            previous, deltas = None, []
            source_stamps: dict[tuple, int] = {}
            inversions = set()
            for event in sorted(
                row.document["events"],
                key=lambda e: (
                    e["source"]["source_revision_id"],
                    e["source"]["member_ordinal"]
                    if e["source"]["member_ordinal"] is not None
                    else -1,
                    e["source"]["byte_start"],
                ),
            ):
                stamp = event["timestamp_us"]
                if stamp is None:
                    continue
                key = (event["source"]["source_revision_id"], event["source"]["member_ordinal"])
                if key in source_stamps and stamp < source_stamps[key]:
                    inversions.add(event["event_id"])
                source_stamps[key] = stamp
            for event in result["items"]:
                stamp = event["timestamp_us"]
                deltas.append(
                    dict(
                        event_id=event["event_id"],
                        delta_us=stamp - previous
                        if stamp is not None and previous is not None
                        else None,
                        source_time_inversion=event["event_id"] in inversions,
                    )
                )
                previous = stamp
            return deltas

        deltas = await bundle_work(request, trace)
        actor = await authenticated(request, session)
        await checked_offline(session, actor, project_id, investigation_id)
        return {
            **result,
            "deltas": deltas,
            "warning": "Observed time differences do not prove network latency or causality.",
        }

    return router
