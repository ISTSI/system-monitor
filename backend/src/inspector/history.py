"""Approved SSH captures, MariaDB indexes and private historical snapshot queries.

The labelled local adapter requires a deployment opt-in. Both transports feed
the same bounded parser; requests select configured processes, never paths.
"""

import asyncio
import copy
import fnmatch
import hashlib
import json
import time
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, func, insert, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.responses import StreamingResponse

from inspector import auth, services
from inspector.config import Config
from inspector.domain import ID_PATTERN, Principal, ProjectContext, server_connection_id
from inspector.errors import DomainError
from inspector.history_cache import READ_CACHE
from inspector.persistence.models import (
    AuthSession,
    HistoryCursor,
    HistoryDownload,
    HistoryEvent,
    HistoryJob,
    HistorySource,
    LiveSession,
    Project,
    TopologyState,
    User,
    Workspace,
)
from inspector.security import authorize, issue_token, token_hash

NONTERMINAL = ("queued", "planning", "collecting", "indexing", "cancel_requested")
TERMINAL = ("completed", "partial", "cancelled", "failed", "interrupted")
UTC_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
UTC_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
PAGE_RAW_BYTES = 8_388_608


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class HistoricalFilter(StrictInput):
    include: list[Annotated[str, Field(max_length=512)]] = Field(
        default_factory=list, max_length=20
    )
    include_mode: Literal["any", "all"] = "any"
    exclude: list[Annotated[str, Field(max_length=512)]] = Field(
        default_factory=list, max_length=20
    )
    case_sensitive: bool = True

    def predicate(self) -> Any:
        from inspector.log_engine import LiteralFilter

        return LiteralFilter(
            tuple(self.include), tuple(self.exclude), self.include_mode, self.case_sensitive
        )


def canonical_time(value: str) -> int:
    from inspector.log_engine import utc_microseconds

    try:
        return utc_microseconds(value)
    except ValueError:
        raise DomainError("INVALID_TIME", "Use a valid canonical UTC timestamp.", 422) from None


def format_time(value: int) -> str:
    return (datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=value)).strftime(UTC_FORMAT)


class HistoricalScopeInput(StrictInput):
    workspace_id: str = Field(pattern=ID_PATTERN)
    transport: Literal["ssh", "local_demo"] | None = None
    process_ids: list[Annotated[str, Field(pattern=ID_PATTERN)]] = Field(
        min_length=1, max_length=200
    )
    from_: str = Field(alias="from", pattern=UTC_PATTERN)
    to: str = Field(pattern=UTC_PATTERN)

    @model_validator(mode="after")
    def valid_interval(self) -> "HistoricalScopeInput":
        if canonical_time(self.from_) >= canonical_time(self.to):
            raise ValueError("The exclusive end must follow the inclusive start.")
        if len(set(self.process_ids)) != len(self.process_ids):
            raise ValueError("Select each process once.")
        return self


class HistoricalCorrelation(StrictInput):
    mode: Literal["exact", "literal"]
    field: str = Field(default="request_id", min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=512)


class HistoricalQueryInput(StrictInput):
    process_ids: list[Annotated[str, Field(pattern=ID_PATTERN)]] = Field(
        min_length=1, max_length=200
    )
    from_: str = Field(alias="from", pattern=UTC_PATTERN)
    to: str = Field(pattern=UTC_PATTERN)
    filter: HistoricalFilter = Field(default_factory=HistoricalFilter)
    per_process_filters: dict[str, HistoricalFilter] = Field(default_factory=dict, max_length=200)
    limit: int = Field(default=200, ge=1, le=1000)
    cursor: str | None = Field(default=None, max_length=128)
    lane: Literal["events", "diagnostic"] = "events"
    correlation: HistoricalCorrelation | None = None

    @model_validator(mode="after")
    def valid_interval(self) -> "HistoricalQueryInput":
        if canonical_time(self.from_) >= canonical_time(self.to):
            raise ValueError("The exclusive end must follow the inclusive start.")
        if len(set(self.process_ids)) != len(self.process_ids):
            raise ValueError("Select each process once.")
        if not set(self.per_process_filters) <= set(self.process_ids):
            raise ValueError("Per-process filters must belong to the selection.")
        return self


class HistoricalContextInput(StrictInput):
    before: int = Field(default=5, ge=0, le=100)
    after: int = Field(default=5, ge=0, le=100)
    from_: str = Field(alias="from", pattern=UTC_PATTERN)
    to: str = Field(pattern=UTC_PATTERN)
    filter: HistoricalFilter = Field(default_factory=HistoricalFilter)
    per_process_filters: dict[str, HistoricalFilter] = Field(default_factory=dict, max_length=200)

    @model_validator(mode="after")
    def valid_interval(self) -> "HistoricalContextInput":
        if canonical_time(self.from_) >= canonical_time(self.to):
            raise ValueError("The exclusive end must follow the inclusive start.")
        return self


class HistoricalSourceProvenance(StrictInput):
    source_revision_id: str
    remote_path: str
    archive_member: str | None
    member_ordinal: int | None
    byte_start: int
    byte_end: int
    line_number: int | None
    content_sha256: str


class HistoricalEvent(StrictInput):
    schema_version: Literal["1.0"]
    project_id: str
    event_id: str
    process_id: str
    server_id: str
    process_name_snapshot: str
    server_name_snapshot: str
    raw_line: str
    timestamp_original: str | None
    timestamp_utc: str | None
    timestamp_us: int | None
    received_at: str
    parse_status: str
    metadata: dict[str, str]
    source: HistoricalSourceProvenance


class HistoricalPlanSource(StrictInput):
    source_revision_id: str
    process_id: str
    remote_path: str
    kind: str
    estimated_bytes: int


class HistoricalPlanResponse(StrictInput):
    project_id: str
    demo_mode: bool
    process_ids: list[str]
    from_: str = Field(alias="from")
    to: str
    source_count: int
    estimated_bytes: int
    sources: list[HistoricalPlanSource]
    warnings: list[str]


class HistoricalCoverage(StrictInput):
    source_revision_id: str
    process_id: str
    remote_path: str
    status: str
    events: int
    bytes: int
    expanded_bytes: int
    error_code: str | None
    checksum: str | None
    byte_start: int
    byte_end: int


class HistoricalJobResponse(StrictInput):
    project_id: str
    job_id: str
    investigation_id: str
    workspace_id: str
    process_ids: list[str]
    from_: str = Field(alias="from")
    to: str
    status: str
    demo_mode: bool
    source_snapshot_revision: int
    source_count: int
    scanned_sources: int
    event_count: int
    parse_issue_count: int
    downloaded_bytes: int
    expanded_bytes: int
    coverage_status: str
    coverage: list[HistoricalCoverage]
    errors: list[str]


class HistoricalListResponse(StrictInput):
    project_id: str
    items: list[HistoricalJobResponse]


class HistoricalQueryResponse(StrictInput):
    project_id: str
    items: list[HistoricalEvent]
    next_cursor: str | None
    matched_count: int | None
    parse_issue_count: int
    source_snapshot_revision: int
    partial: bool
    coverage: list[HistoricalCoverage]
    availability: Literal["retained", "partial", "unavailable"] = "retained"


class HistoricalContextItem(StrictInput):
    event: HistoricalEvent
    outside_time_bounds: bool
    matches_filter: bool | None
    is_anchor: bool


class HistoricalContextResponse(StrictInput):
    project_id: str
    event_id: str
    items: list[HistoricalContextItem]


class HistoricalDownloadResponse(StrictInput):
    project_id: str
    download_id: str
    url: str


class HistoricalDeleteResponse(StrictInput):
    project_id: str
    investigation_id: str
    cache_cleanup_pending: bool = False


class HistoricalAdministrativeCancelResponse(StrictInput):
    project_id: str
    job_id: str
    status: str


class EmptyInput(StrictInput):
    pass


def not_found() -> DomainError:
    return DomainError("NOT_FOUND", "Resource not found.", 404)


async def checked_job(
    session: AsyncSession,
    actor: Principal,
    project_id: str,
    job_id: str,
    *,
    lock: bool = False,
    action: str = "investigation.read",
) -> HistoryJob:
    actor = await services.current_actor(session, actor)
    ProjectContext(project_id, actor.user_id)
    query = select(HistoryJob).where(
        HistoryJob.project_id == project_id,
        HistoryJob.id == job_id,
        HistoryJob.owner_user_id == actor.user_id,
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    job = await session.scalar(query)
    if job is None:
        raise not_found()
    authorize(actor, action, owner_user_id=job.owner_user_id)
    return job


async def job_response(session: AsyncSession, job: HistoryJob) -> dict:
    sources = (
        await session.scalars(
            select(HistorySource)
            .where(HistorySource.project_id == job.project_id, HistorySource.job_id == job.id)
            .order_by(HistorySource.id)
        )
    ).all()
    return dict(
        project_id=job.project_id,
        job_id=job.id,
        investigation_id=job.id,
        workspace_id=job.workspace_id,
        process_ids=job.process_ids,
        **{"from": format_time(job.from_us)},
        to=format_time(job.to_us),
        status=job.status,
        demo_mode=all(s.manifest.get("transport", "local_demo") == "local_demo" for s in sources),
        source_snapshot_revision=job.snapshot_revision,
        source_count=len(sources),
        scanned_sources=sum(s.status in {"completed", "failed", "partial"} for s in sources),
        event_count=job.event_count,
        parse_issue_count=job.parse_issue_count,
        downloaded_bytes=job.downloaded_bytes,
        expanded_bytes=job.expanded_bytes,
        coverage_status=(
            "complete_for_scanned_candidates"
            if job.status == "completed" and all(s.status == "completed" for s in sources)
            else "partial"
            if job.event_count and any(s.status in {"completed", "partial"} for s in sources)
            else "unavailable"
            if job.status in TERMINAL
            else "unknown_candidate_coverage"
        ),
        coverage=[
            dict(
                source_revision_id=s.id,
                process_id=s.process_id,
                remote_path=s.remote_path,
                status=s.status,
                events=s.event_count,
                bytes=s.downloaded_bytes,
                expanded_bytes=s.expanded_bytes,
                error_code=s.error_code,
                checksum=s.checksum,
                byte_start=0,
                byte_end=s.downloaded_bytes,
            )
            for s in sources
        ],
        errors=job.errors,
    )


def local_manifest(config: Config) -> list[dict]:
    if not config.local_history_demo:
        raise DomainError(
            "LOCAL_TRANSPORT_DISABLED",
            "Local fixture collection requires the deployment's labelled synthetic demo mode.",
            409,
        )
    root = Path(__file__).resolve().parents[3]
    try:
        manifest = json.loads((root / "fixtures/source-manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise DomainError(
            "LOCAL_FIXTURES_UNAVAILABLE", "Synthetic fixture data is unavailable.", 503
        ) from None
    result = []
    for entry in manifest["sources"]:
        original = root / entry["fixture_path"]
        path = original.resolve()
        if (
            not path.is_relative_to((root / "fixtures").resolve())
            or any(
                part.is_symlink() for part in [original, *original.parents] if part != root.parent
            )
            or not path.is_file()
        ):
            raise DomainError(
                "LOCAL_FIXTURES_UNAVAILABLE", "Synthetic fixture data is unavailable.", 503
            )
        result.append({**entry, "local_path": str(path), "estimated_bytes": path.stat().st_size})
    return result


def approved_candidates(config: Config, document: dict, selection: list[str]) -> list[dict]:
    processes = {p["id"]: p for p in document["processes"]}
    if not set(selection) <= processes.keys():
        raise not_found()
    servers = {s["id"]: s for s in document["servers"]}
    connections = {c["id"]: c for c in document["connections"]}
    for process_id in selection:
        server_connection_id(servers[processes[process_id]["server_id"]])
    candidates = []
    for entry in local_manifest(config):
        if entry["process_id"] not in selection:
            continue
        process = processes[entry["process_id"]]
        source = process["log_source"]
        remote_path = entry["remote_path"]
        server = servers[process["server_id"]]
        roots = connections[server_connection_id(server)]["allowed_log_roots"]
        if not any(
            PurePosixPath(remote_path).is_relative_to(PurePosixPath(root)) for root in roots
        ):
            continue
        if entry["kind"] == "plain":
            allowed = remote_path == source["active_path"] or any(
                fnmatch.fnmatchcase(remote_path, pattern) for pattern in source["rotated_patterns"]
            )
        else:
            allowed = any(
                fnmatch.fnmatchcase(remote_path, archive["path_pattern"])
                and any(
                    fnmatch.fnmatchcase(entry["archive_member"], pattern)
                    for pattern in archive["member_patterns"]
                )
                for archive in source["archives"]
            )
        if allowed:
            candidates.append(entry)
    if not candidates or set(selection) != {item["process_id"] for item in candidates}:
        raise DomainError(
            "SOURCE_NOT_APPROVED",
            "Every selected process must have an approved configured synthetic local source.",
            409,
        )
    return candidates


async def planning_context(
    session: AsyncSession,
    actor: Principal,
    project_id: str,
    payload: HistoricalScopeInput,
    config: Config,
    remote: Any = None,
    session_hash: str | None = None,
) -> tuple[Project, dict, list[dict]]:
    actor = await services.current_actor(session, actor)
    authorize(actor, "collection.create")
    project = await services.project_in_context(
        session, ProjectContext(project_id, actor.user_id), lock=True
    )
    if project.archived:
        raise DomainError("PROJECT_ARCHIVED", "Archived systems cannot start collections.", 409)
    workspace = await session.get(Workspace, (project_id, payload.workspace_id))
    if workspace is None or workspace.owner_user_id != actor.user_id:
        raise not_found()
    if workspace.state != "active" or workspace.expires_us <= services.utc_now_us():
        raise DomainError("WORKSPACE_EXPIRED", "Reload this page to open a new workspace.", 409)
    state = await session.get(TopologyState, project_id)
    if state is None:
        raise not_found()
    document = copy.deepcopy(state.config)
    revision = project.revision
    use_demo = payload.transport == "local_demo" or (
        payload.transport is None and config.local_history_demo
    )
    if use_demo:
        candidates = await asyncio.to_thread(
            approved_candidates, config, document, payload.process_ids
        )
    else:
        # End the request transaction before DNS, SSH, directory scans or reads.
        await session.commit()
        if remote is None:
            raise DomainError("SSH_UNAVAILABLE", "SSH collection is unavailable.", 503)
        candidates = await remote.plan(
            actor, project_id, revision, document, payload.process_ids, session_hash
        )
        actor = await services.current_actor(session, actor)
        project = await services.project_in_context(
            session, ProjectContext(project_id, actor.user_id), lock=True
        )
        await session.refresh(project)
        if project.revision != revision or project.archived:
            raise DomainError("REVISION_CONFLICT", "System changed during source planning.", 409)
        workspace = await session.get(
            Workspace, (project_id, payload.workspace_id), populate_existing=True
        )
        if workspace is None or workspace.owner_user_id != actor.user_id:
            raise not_found()
        if workspace.state != "active" or workspace.expires_us <= services.utc_now_us():
            raise DomainError("WORKSPACE_EXPIRED", "Reload this page to open a new workspace.", 409)
        # Revalidate under the reservation transaction, so an approval change
        # cannot race a successfully accepted plan/start.
        for connection_id in dict.fromkeys(item["connection_id"] for item in candidates):
            snapshot = await remote.access.prepare_in_transaction(
                session, actor, project_id, connection_id, revision, session_hash
            )
            if any(
                item["access_signature"] != snapshot.signature
                for item in candidates
                if item["connection_id"] == connection_id
            ):
                raise DomainError(
                    "REVISION_CONFLICT", "Source access changed during planning.", 409
                )
    maximum = config.history_limits.get("max_download_bytes_per_collection", 536_870_912)
    if sum(s["estimated_bytes"] for s in candidates) > maximum:
        raise DomainError(
            "DOWNLOAD_LIMIT", "The collection exceeds the configured download budget.", 413
        )
    return project, document, candidates


def plan_response(project_id: str, payload: HistoricalScopeInput, candidates: list[dict]) -> dict:
    demo = all(s.get("transport", "local_demo") == "local_demo" for s in candidates)
    return dict(
        project_id=project_id,
        demo_mode=demo,
        process_ids=payload.process_ids,
        **{"from": payload.from_},
        to=payload.to,
        source_count=len(candidates),
        estimated_bytes=sum(s["estimated_bytes"] for s in candidates),
        sources=[
            dict(
                source_revision_id=s["source_revision_id"],
                process_id=s["process_id"],
                remote_path=s["remote_path"],
                kind=s["kind"],
                estimated_bytes=s["estimated_bytes"],
            )
            for s in candidates
        ],
        warnings=[
            "Synthetic local fixture transport. No SSH connection is opened."
            if demo
            else "Read-only SSH/SFTP. Candidates are pinned snapshots; changed files fail visibly. SFTP cannot prove all same-size replacements or continuous coverage.",
            "All configured candidates are scanned regardless of filename dates; observed timestamp boundaries do not prove continuous coverage.",
            *dict.fromkeys(warning for s in candidates for warning in s.get("warnings", [])),
        ],
    )


def event_payload(row: HistoryEvent) -> dict:
    # Canonical identity/order fields have one stored authority. Retained older
    # full payloads remain readable; indexed columns always supply these values.
    return {
        **row.payload,
        "schema_version": "1.0",
        "project_id": row.project_id,
        "event_id": row.event_id,
        "process_id": row.process_id,
        "timestamp_us": row.timestamp_us,
        "timestamp_utc": format_time(row.timestamp_us) if row.timestamp_us is not None else None,
        "raw_line": row.raw_line,
        "source": {
            **row.payload["source"],
            "source_revision_id": row.source_revision_id,
            "member_ordinal": None if row.member_order == -1 else row.member_order,
            "byte_start": row.byte_start,
        },
    }


def compact_event_payload(event: dict) -> dict:
    """Preserve nonindexed provenance without duplicating canonical key columns."""
    return {
        **{
            key: event[key]
            for key in (
                "server_id",
                "process_name_snapshot",
                "server_name_snapshot",
                "timestamp_original",
                "received_at",
                "parse_status",
                "metadata",
            )
        },
        "source": {
            key: event["source"][key]
            for key in (
                "remote_path",
                "archive_member",
                "byte_end",
                "line_number",
                "content_sha256",
            )
        },
    }


async def persist_event_batch(
    session: AsyncSession, job: HistoryJob, source: HistorySource, events: list[dict]
) -> None:
    """The production bounded bulk-index primitive, also used by the local benchmark."""
    if len(events) > 1000:
        raise ValueError("Index batches are limited to 1000 events.")
    rows = []
    for event in events:
        if (event["project_id"], event["process_id"], event["source"]["source_revision_id"]) != (
            job.project_id,
            source.process_id,
            source.id,
        ) or (source.project_id, source.job_id) != (job.project_id, job.id):
            raise ValueError("Event source scope does not match the authorized capture.")
        job.event_count += 1
        rows.append(
            dict(
                project_id=job.project_id,
                job_id=job.id,
                event_id=event["event_id"],
                process_id=event["process_id"],
                source_revision_id=source.id,
                capture_seq=job.event_count,
                timestamp_us=event["timestamp_us"],
                member_order=event["source"]["member_ordinal"]
                if event["source"]["member_ordinal"] is not None
                else -1,
                byte_start=event["source"]["byte_start"],
                raw_line=event["raw_line"],
                payload=compact_event_payload(event),
            )
        )
    if rows:
        # All columns are explicit; Core binds retain JSON/BIGINT/charset types
        # while avoiding ORM bulk-mapping work for these immutable records.
        await session.execute(insert(HistoryEvent.metadata.tables["history_events"]), rows)
    job.parse_issue_count += sum(event["timestamp_us"] is None for event in events)
    source.event_count += len(events)
    job.snapshot_revision += 1


def order_columns(*, diagnostic: bool = False) -> tuple:
    return (
        func.coalesce(HistoryEvent.timestamp_us, 0) if diagnostic else HistoryEvent.timestamp_us,
        HistoryEvent.process_id,
        HistoryEvent.source_revision_id,
        HistoryEvent.member_order,
        HistoryEvent.byte_start,
        HistoryEvent.event_id,
    )


def row_key(row: HistoryEvent) -> list:
    return [
        row.timestamp_us if row.timestamp_us is not None else 0,
        row.process_id,
        row.source_revision_id,
        row.member_order,
        row.byte_start,
        row.event_id,
    ]


async def candidate_batches(
    session: AsyncSession,
    conditions: list,
    ordering: tuple,
    payload: HistoricalQueryInput,
    fresh_reader: Callable,
    cache_key: tuple,
) -> AsyncIterator[list[tuple]]:
    """Enumerate the complete scoped snapshot in one-MiB immutable text batches."""
    with READ_CACHE.lease(cache_key) as cached:
        if cached is not None:
            batch: list[tuple] = []
            batch_bytes = 0
            for row in cached.rows:
                if batch and (batch_bytes + row[8] > 1_048_576 or len(batch) == 4096):
                    await fresh_reader()
                    yield batch
                    batch, batch_bytes = [], 0
                batch.append(row)
                batch_bytes += row[8]
            if batch:
                await fresh_reader()
                yield batch
            return
    builder = READ_CACHE.builder(cache_key)
    try:
        scan_key = None
        columns = (
            HistoryEvent.event_id,
            HistoryEvent.timestamp_us,
            HistoryEvent.process_id,
            HistoryEvent.source_revision_id,
            HistoryEvent.member_order,
            HistoryEvent.byte_start,
            func.octet_length(HistoryEvent.raw_line).label("raw_bytes"),
        )
        while True:
            await fresh_reader()
            query = select(*columns).where(*conditions).order_by(*ordering).limit(4096)
            if scan_key is not None:
                query = query.where(tuple_(*ordering) > tuple(scan_key))
                if payload.lane == "events":
                    query = query.where(HistoryEvent.timestamp_us >= scan_key[0])
            candidates = (await session.execute(query)).all()
            if not candidates:
                break
            prefix = []
            batch_bytes = 0
            for candidate in candidates:
                if batch_bytes + candidate.raw_bytes > 1_048_576:
                    break
                prefix.append(candidate)
                batch_bytes += candidate.raw_bytes
            if not prefix:
                raise DomainError(
                    "RESULT_BYTE_LIMIT", "A record exceeds the scan byte budget.", 413
                )
            raw_rows = (
                await session.execute(
                    select(
                        HistoryEvent.event_id,
                        HistoryEvent.raw_line,
                        func.json_unquote(
                            func.json_extract(HistoryEvent.payload, "$.parse_status")
                        ).label("parse_status"),
                    ).where(
                        HistoryEvent.project_id == cache_key[0],
                        HistoryEvent.job_id == cache_key[2],
                        HistoryEvent.event_id.in_([candidate.event_id for candidate in prefix]),
                    )
                )
            ).all()
            by_id = {row.event_id: row for row in raw_rows}
            batch = []
            for candidate in prefix:
                text = by_id[candidate.event_id]
                compact = (
                    candidate.timestamp_us if candidate.timestamp_us is not None else 0,
                    candidate.process_id,
                    candidate.source_revision_id,
                    candidate.member_order,
                    candidate.byte_start,
                    candidate.event_id,
                    text.raw_line,
                    text.parse_status == "oversized_line",
                    candidate.raw_bytes,
                )
                builder.add(compact)
                batch.append(compact)
            yield batch
            scan_key = list(batch[-1][:6])
            if len(candidates) < 4096 and len(prefix) == len(candidates):
                break
        # Publish only a fully enumerated immutable scope after a fresh grant check.
        await fresh_reader()
        builder.publish()
    finally:
        builder.abort()


async def historical_query(
    session: AsyncSession,
    actor: Principal,
    project_id: str,
    job_id: str,
    payload: HistoricalQueryInput,
    *,
    supervisor: Any = None,
    login_hash: str | None = None,
    idle_timeout_us: int = 1_800_000_000,
) -> dict:
    job = await checked_job(session, actor, project_id, job_id)
    if not set(payload.process_ids) <= set(job.process_ids):
        raise not_found()
    digest_input = payload.model_dump(by_alias=True, exclude={"cursor", "limit"})
    digest = hashlib.sha256(
        json.dumps(digest_input, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    snapshot = job.snapshot_revision
    max_seq = job.event_count
    after_key = None
    ordering = order_columns(diagnostic=payload.lane == "diagnostic")
    if payload.cursor is not None:
        cursor = await session.get(HistoryCursor, token_hash(payload.cursor) or "")
        if cursor is None or (
            cursor.project_id,
            cursor.job_id,
            cursor.owner_user_id,
            cursor.auth_version,
        ) != (project_id, job_id, actor.user_id, actor.auth_version):
            raise not_found()
        if cursor.query_hash != digest:
            raise DomainError(
                "CURSOR_QUERY_MISMATCH",
                "The cursor belongs to another query; run the query again.",
                409,
            )
        if cursor.expires_us <= services.utc_now_us():
            raise DomainError(
                "CURSOR_EXPIRED", "The query cursor expired; run the query again.", 409
            )
        snapshot, max_seq, after_key = cursor.snapshot_revision, cursor.max_seq, cursor.after_key
    response = await job_response(session, job)
    captured_status = job.status
    captured_revision = job.snapshot_revision
    # Authentication uses short write locks. Release them before any retained
    # text scan so another page/logout can make progress independently.
    await session.commit()
    last_freshness_check = time.monotonic()
    freshness_sessions = async_sessionmaker(session.bind, expire_on_commit=False)

    async def fresh_reader() -> None:
        nonlocal last_freshness_check
        # Candidate batches are materialized before this call. Return their
        # read connection before checking freshness, including a one-slot pool.
        await session.commit()
        async with freshness_sessions.begin() as freshness:
            state = (
                await freshness.execute(
                    select(
                        User.enabled, User.auth_version, User.role, User.must_change_password
                    ).where(User.id == actor.user_id)
                )
            ).one_or_none()
            login = await freshness.get(AuthSession, login_hash) if login_hash is not None else None
            now = services.utc_now_us()
            if login_hash is not None and (
                login is None
                or login.user_id != actor.user_id
                or login.auth_version != actor.auth_version
                or auth.session_expired(login, now, idle_timeout_us)
            ):
                raise DomainError("AUTH_REQUIRED", "Authentication is required.", 401)
        if (
            state is None
            or not state.enabled
            or state.auth_version != actor.auth_version
            or state.role != actor.role
            or state.must_change_password
        ):
            raise DomainError("AUTH_REQUIRED", "Authentication is required.", 401)
        if supervisor is not None and not await supervisor.healthy():
            raise DomainError(
                "DATABASE_UNAVAILABLE", "Historical queries require available persistence.", 503
            )
        last_freshness_check = time.monotonic()

    await fresh_reader()
    conditions = [
        HistoryEvent.project_id == project_id,
        HistoryEvent.job_id == job_id,
        HistoryEvent.capture_seq <= max_seq,
        HistoryEvent.process_id.in_(payload.process_ids),
    ]
    if payload.lane == "diagnostic":
        conditions.append(HistoryEvent.timestamp_us.is_(None))
    else:
        conditions.extend(
            [
                HistoryEvent.timestamp_us >= max(canonical_time(payload.from_), job.from_us),
                HistoryEvent.timestamp_us < min(canonical_time(payload.to), job.to_us),
            ]
        )
    if payload.correlation is not None and payload.correlation.mode == "exact":
        # MariaDB matches escaped JSON object-key representations. Quote with
        # the same ASCII escaping as SQLAlchemy's persisted JSON serializer.
        conditions.append(
            func.binary(
                func.json_unquote(
                    func.json_extract(
                        HistoryEvent.payload,
                        "$.metadata." + json.dumps(payload.correlation.field, ensure_ascii=True),
                    )
                )
            )
            == payload.correlation.value.encode("utf-8")
        )
    predicate = payload.filter.predicate()
    per_process = {p: f.predicate() for p, f in payload.per_process_filters.items()}
    no_filter = not any(payload.filter.include + payload.filter.exclude) and not any(
        any(f.include + f.exclude) for f in payload.per_process_filters.values()
    )
    if payload.correlation is not None and payload.correlation.mode == "literal":
        no_filter = False
    ids: list[str] = []
    last = None
    matched = 0
    has_more = False
    unknown_filter = False
    if no_filter:
        matched = int(
            await session.scalar(select(func.count()).select_from(HistoryEvent).where(*conditions))
            or 0
        )
        query = (
            select(
                HistoryEvent.event_id,
                HistoryEvent.timestamp_us,
                HistoryEvent.process_id,
                HistoryEvent.source_revision_id,
                HistoryEvent.member_order,
                HistoryEvent.byte_start,
                func.octet_length(HistoryEvent.raw_line).label("raw_bytes"),
            )
            .where(*conditions)
            .order_by(*ordering)
            .limit(payload.limit + 1)
        )
        if after_key is not None:
            query = query.where(tuple_(*ordering) > tuple(after_key))
            if payload.lane == "events":
                query = query.where(HistoryEvent.timestamp_us >= after_key[0])
        candidates = (await session.execute(query)).all()
        used_bytes = 0
        for candidate in candidates:
            row = candidate._mapping
            if len(ids) == payload.limit or used_bytes + row["raw_bytes"] > PAGE_RAW_BYTES:
                has_more = True
                break
            ids.append(row["event_id"])
            used_bytes += row["raw_bytes"]
            last = [
                row["timestamp_us"] if row["timestamp_us"] is not None else 0,
                row["process_id"],
                row["source_revision_id"],
                row["member_order"],
                row["byte_start"],
                row["event_id"],
            ]
        if candidates and not ids:
            raise DomainError("RESULT_BYTE_LIMIT", "A record exceeds the page byte budget.", 413)
        selected = (
            (
                await session.scalars(
                    select(HistoryEvent).where(
                        HistoryEvent.project_id == project_id,
                        HistoryEvent.job_id == job_id,
                        HistoryEvent.event_id.in_(ids),
                    )
                )
            ).all()
            if ids
            else []
        )
        by_id = {row.event_id: row for row in selected}
        items = [event_payload(by_id[identifier]) for identifier in ids]
    else:
        used_bytes = 0
        page_full = False
        cache_key = (
            project_id,
            actor.user_id,
            job_id,
            max_seq,
            snapshot,
            job.config_revision,
            actor.auth_version,
            tuple(sorted(payload.process_ids)),
            canonical_time(payload.from_),
            canonical_time(payload.to),
            payload.lane,
            (payload.correlation.mode, payload.correlation.field, payload.correlation.value)
            if payload.correlation
            else None,
        )
        async with asyncio.timeout(120):
            async for batch in candidate_batches(
                session, conditions, ordering, payload, fresh_reader, cache_key
            ):
                for cached_row in batch:
                    if time.monotonic() - last_freshness_check >= 0.25:
                        await fresh_reader()
                    process_id = cached_row[1]
                    oversized = cached_row[7]
                    if oversized:
                        unknown_filter = True
                    if not oversized and (
                        not predicate.matches(cached_row[6])
                        or (
                            process_id in per_process
                            and not per_process[process_id].matches(cached_row[6])
                        )
                    ):
                        continue
                    if (
                        not oversized
                        and payload.correlation is not None
                        and payload.correlation.mode == "literal"
                    ):
                        text, term = cached_row[6], payload.correlation.value
                        if not payload.filter.case_sensitive:
                            text, term = text.casefold(), term.casefold()
                        if term not in text:
                            continue
                    matched += 1
                    key = list(cached_row[:6])
                    if after_key is None or key > after_key:
                        if (
                            not page_full
                            and len(ids) < payload.limit
                            and used_bytes + cached_row[8] <= PAGE_RAW_BYTES
                        ):
                            ids.append(cached_row[5])
                            used_bytes += cached_row[8]
                            last = key
                        else:
                            page_full = True
                            has_more = True
        selected_rows = (
            (
                await session.scalars(
                    select(HistoryEvent).where(
                        HistoryEvent.project_id == project_id,
                        HistoryEvent.job_id == job_id,
                        HistoryEvent.event_id.in_(ids),
                    )
                )
            ).all()
            if ids
            else []
        )
        by_id = {row.event_id: row for row in selected_rows}
        items = [event_payload(by_id[event_id]) for event_id in ids]
    # A revocation while scanning must prevent the final page and cursor from
    # being dispatched, including a scan which finished between periodic checks.
    await fresh_reader()
    await services.current_actor(session, actor)
    next_cursor = None
    if has_more and last is not None:
        next_cursor = issue_token()
        await session.execute(
            delete(HistoryCursor).where(HistoryCursor.expires_us <= services.utc_now_us())
        )
        session.add(
            HistoryCursor(
                token_hash=token_hash(next_cursor),
                project_id=project_id,
                job_id=job_id,
                owner_user_id=actor.user_id,
                auth_version=actor.auth_version,
                query_hash=digest,
                snapshot_revision=snapshot,
                max_seq=max_seq,
                after_key=last,
                expires_us=services.utc_now_us() + 900_000_000,
            )
        )
    issues = await session.scalar(
        select(func.count())
        .select_from(HistoryEvent)
        .where(
            HistoryEvent.project_id == project_id,
            HistoryEvent.job_id == job_id,
            HistoryEvent.capture_seq <= max_seq,
            HistoryEvent.timestamp_us.is_(None),
        )
    )
    return dict(
        project_id=project_id,
        items=items,
        next_cursor=next_cursor,
        matched_count=matched
        if captured_status in TERMINAL
        and not unknown_filter
        and response["coverage_status"] != "unavailable"
        else None,
        parse_issue_count=issues,
        source_snapshot_revision=snapshot,
        partial=response["coverage_status"] != "complete_for_scanned_candidates"
        or snapshot != captured_revision,
        coverage=response["coverage"],
        availability="unavailable"
        if response["coverage_status"] == "unavailable"
        else "retained"
        if response["coverage_status"] == "complete_for_scanned_candidates"
        else "partial",
    )


async def historical_context(
    session: AsyncSession,
    actor: Principal,
    project_id: str,
    job_id: str,
    event_id: str,
    payload: HistoricalContextInput,
) -> dict:
    job = await checked_job(session, actor, project_id, job_id)
    if not set(payload.per_process_filters) <= set(job.process_ids):
        raise not_found()
    anchor = await session.get(HistoryEvent, (project_id, job_id, event_id))
    if anchor is None:
        raise not_found()
    conditions = [
        HistoryEvent.project_id == project_id,
        HistoryEvent.job_id == job_id,
        HistoryEvent.source_revision_id == anchor.source_revision_id,
        HistoryEvent.member_order == anchor.member_order,
    ]
    position_columns = (
        HistoryEvent.event_id,
        func.octet_length(HistoryEvent.raw_line).label("raw_bytes"),
    )
    before_positions = (
        await session.execute(
            select(*position_columns)
            .where(*conditions, HistoryEvent.byte_start < anchor.byte_start)
            .order_by(HistoryEvent.byte_start.desc())
            .limit(payload.before)
        )
    ).all()
    after_positions = (
        await session.execute(
            select(*position_columns)
            .where(*conditions, HistoryEvent.byte_start > anchor.byte_start)
            .order_by(HistoryEvent.byte_start)
            .limit(payload.after)
        )
    ).all()
    if (
        len(anchor.raw_line.encode("utf-8"))
        + sum(row.raw_bytes for row in [*before_positions, *after_positions])
        > PAGE_RAW_BYTES
    ):
        raise DomainError(
            "CONTEXT_BYTE_LIMIT",
            "Context exceeds the byte budget; request fewer before/after lines.",
            413,
        )
    positions = [*reversed(before_positions), *after_positions]
    records = (
        (
            await session.scalars(
                select(HistoryEvent).where(
                    HistoryEvent.project_id == project_id,
                    HistoryEvent.job_id == job_id,
                    HistoryEvent.event_id.in_([row.event_id for row in positions]),
                )
            )
        ).all()
        if positions
        else []
    )
    by_id = {row.event_id: row for row in records}
    before = [by_id[row.event_id] for row in before_positions]
    after = [by_id[row.event_id] for row in after_positions]
    start, end = canonical_time(payload.from_), canonical_time(payload.to)
    if start >= end:
        raise DomainError("INVALID_TIME", "The exclusive end must follow the inclusive start.", 422)
    predicate = payload.filter.predicate()
    local = payload.per_process_filters.get(anchor.process_id, HistoricalFilter()).predicate()
    return dict(
        project_id=project_id,
        event_id=event_id,
        items=[
            dict(
                event=event_payload(row),
                outside_time_bounds=row.timestamp_us is None or not start <= row.timestamp_us < end,
                matches_filter=None
                if row.payload.get("parse_status") == "oversized_line"
                else predicate.matches(row.raw_line) and local.matches(row.raw_line),
                is_anchor=row.event_id == anchor.event_id,
            )
            for row in [*reversed(before), anchor, *after]
        ],
    )


class HistoryManager:
    """Two bounded file workers with bounded batches and DB dispatch checks."""

    def __init__(
        self,
        config: Config,
        sessions: async_sessionmaker[AsyncSession],
        supervisor: Any,
        source_access: Any = None,
    ) -> None:
        self.config, self.sessions, self.supervisor = config, sessions, supervisor
        from inspector.history_remote import RemoteHistory

        self.remote = RemoteHistory(source_access, config) if source_access else None
        workers = min(2, config.history_limits.get("concurrent_archive_tasks", 2))
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="history")
        self.slots = asyncio.Semaphore(workers)
        self.bundle_upload_slots = asyncio.Semaphore(workers)
        self.tasks: dict[tuple[str, str], asyncio.Task] = {}
        self.tokens: dict[tuple[str, str], Any] = {}
        self.resource_locks: dict[tuple[str, str], tuple[asyncio.Lock, int]] = {}
        self.closed = False

    @asynccontextmanager
    async def use_capture(self, project_id: str, job_id: str) -> AsyncIterator[None]:
        """Serialize capture deletion against bounded local reads, never SSH work."""
        key = (project_id, job_id)
        lock, users = self.resource_locks.get(key, (asyncio.Lock(), 0))
        self.resource_locks[key] = lock, users + 1
        try:
            async with lock:
                yield
        finally:
            _, users = self.resource_locks[key]
            if users == 1:
                self.resource_locks.pop(key)
            else:
                self.resource_locks[key] = lock, users - 1

    async def delete_capture(
        self, session: AsyncSession, actor: Principal, project_id: str, job_id: str
    ) -> dict:
        # Authentication may have opened a transaction before waiting for the
        # capture guard. Release its locks before another query checks auth.
        await session.commit()
        operation = asyncio.create_task(self._delete_capture(session, actor, project_id, job_id))
        try:
            return await asyncio.shield(operation)
        except asyncio.CancelledError:
            # Renaming runs in a thread. Finish commit/restore and unlink before
            # the request dependency closes this session, even on disconnect.
            while not operation.done():
                try:
                    await asyncio.shield(operation)
                except asyncio.CancelledError:
                    continue
            operation.result()
            raise

    async def _delete_capture(
        self, session: AsyncSession, actor: Principal, project_id: str, job_id: str
    ) -> dict:
        from inspector.history_retention import stage_cache
        from inspector.persistence.investigation_models import (
            InvestigationBookmark,
            SavedInvestigation,
        )

        async with self.use_capture(project_id, job_id):
            job = await checked_job(session, actor, project_id, job_id, lock=True)
            authorize(actor, "investigation.delete", owner_user_id=job.owner_user_id)
            if job.status not in TERMINAL:
                raise DomainError(
                    "COLLECTION_ACTIVE", "Stop the collection before deleting it.", 409
                )
            saved = await session.get(SavedInvestigation, (project_id, job_id))
            bookmarks = await session.scalar(
                select(func.count())
                .select_from(InvestigationBookmark)
                .where(
                    InvestigationBookmark.project_id == project_id,
                    InvestigationBookmark.job_id == job_id,
                )
            )
            if (saved and saved.pinned) or bookmarks:
                raise DomainError(
                    "INVESTIGATION_PINNED",
                    "Unpin the investigation and remove its bookmarks before deleting it.",
                    409,
                )
            path = self.cache_path(project_id, job_id, "unused").parent
            source_count = await session.scalar(
                select(func.count())
                .select_from(HistorySource)
                .where(HistorySource.project_id == project_id, HistorySource.job_id == job_id)
            )
            staged = await asyncio.to_thread(
                stage_cache, path, Path(self.config.cache_dir), max(1, (source_count or 0) * 2)
            )
            try:
                # Scoped SQL deletes avoid materializing each retained event.
                await session.execute(
                    update(LiveSession)
                    .where(
                        LiveSession.project_id == project_id,
                        LiveSession.investigation_id == job_id,
                        LiveSession.owner_user_id == actor.user_id,
                    )
                    .values(investigation_id=None, recording=False)
                )
                for model in (
                    SavedInvestigation,
                    HistoryDownload,
                    HistoryCursor,
                    HistoryEvent,
                    HistorySource,
                ):
                    await session.execute(
                        delete(model).where(model.project_id == project_id, model.job_id == job_id)
                    )
                await session.execute(
                    delete(HistoryJob).where(
                        HistoryJob.project_id == project_id,
                        HistoryJob.id == job_id,
                        HistoryJob.owner_user_id == actor.user_id,
                    )
                )
                services.audit(
                    session,
                    actor,
                    "investigation.delete",
                    project_id,
                    job_id,
                    services.utc_now_us(),
                )
                await session.commit()
            except BaseException:
                try:
                    await session.rollback()
                finally:
                    if staged is not None:
                        await asyncio.to_thread(staged.restore)
                raise
            READ_CACHE.invalidate(project_id, job_id)
            cleanup_pending = False
            if staged is not None:
                try:
                    await asyncio.to_thread(staged.remove)
                except (OSError, DomainError):
                    # The private index and original path have been removed.
                    # Report remaining detached bytes without presenting this
                    # committed deletion as a retryable failed operation.
                    cleanup_pending = True
            return dict(
                project_id=project_id,
                investigation_id=job_id,
                cache_cleanup_pending=cleanup_pending,
            )

    async def launch(self, project_id: str, job_id: str) -> None:
        if not self.closed:
            key = (project_id, job_id)
            task = asyncio.create_task(self._collect(*key))
            self.tasks[key] = task
            task.add_done_callback(lambda done: self.tasks.pop(key, None))

    def cancel(self, project_id: str, job_id: str) -> None:
        token = self.tokens.get((project_id, job_id))
        if token is not None:
            token.cancel()

    async def close(self) -> None:
        self.closed = True
        for token in self.tokens.values():
            token.cancel()
        if self.tasks:
            await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
        self.executor.shutdown(wait=True, cancel_futures=True)

    async def _dispatch(self, session: AsyncSession, project_id: str, job_id: str) -> HistoryJob:
        if self.supervisor is None or not await self.supervisor.healthy():
            raise DomainError(
                "DATABASE_UNAVAILABLE",
                "Collection interrupted because persistence is unavailable.",
                503,
            )
        job = await session.get(
            HistoryJob, (project_id, job_id), with_for_update=True, populate_existing=True
        )
        if job is None:
            raise not_found()
        if job.status == "cancel_requested":
            raise DomainError("CANCELLED", "Collection cancellation requested.", 409)
        # Keep the authoritative job lock separate. A single nonlocking read
        # verifies current account/session/project grants without ORM snapshots
        # or a lock-order inversion against account revocation.
        state = (
            await session.execute(
                select(
                    User.enabled,
                    User.auth_version,
                    AuthSession.auth_version.label("session_auth_version"),
                    AuthSession.expires_us,
                    AuthSession.created_us,
                    AuthSession.last_seen_us,
                    AuthSession.remember_me,
                    Project.archived,
                )
                .select_from(HistoryJob)
                .join(User, User.id == HistoryJob.owner_user_id)
                .join(
                    AuthSession,
                    (AuthSession.token_hash == HistoryJob.auth_session_hash)
                    & (AuthSession.user_id == User.id),
                )
                .join(Project, Project.id == HistoryJob.project_id)
                .where(HistoryJob.project_id == project_id, HistoryJob.id == job_id)
            )
        ).one_or_none()
        now = services.utc_now_us()
        if (
            state is None
            or not state.enabled
            or state.auth_version != job.auth_version
            or state.session_auth_version != job.auth_version
            or state.expires_us <= now
            or now < state.created_us
            or (not state.remember_me and now - state.last_seen_us >= self.config.idle_timeout_us)
            or state.archived
        ):
            raise DomainError(
                "AUTH_REVOKED", "Collection stopped because authorization expired.", 401
            )
        return job

    def cache_path(self, project_id: str, job_id: str, cache_name: str) -> Path:
        # Components are server-generated opaque IDs; never use a remote/member name.
        namespace = hashlib.sha256(project_id.encode()).hexdigest()
        return Path(self.config.cache_dir) / "historical" / namespace / job_id / cache_name

    async def _collect(self, project_id: str, job_id: str) -> None:
        from inspector.log_engine import CancellationToken

        token = CancellationToken()
        key = (project_id, job_id)
        self.tokens[key] = token
        try:
            async with self.slots:
                async with self.sessions.begin() as session:
                    job = await self._dispatch(session, *key)
                    job.status = "planning"
                    document = copy.deepcopy(job.config_snapshot)
                    sources = (
                        await session.scalars(
                            select(HistorySource)
                            .where(
                                HistorySource.project_id == project_id,
                                HistorySource.job_id == job_id,
                            )
                            .order_by(HistorySource.id)
                        )
                    ).all()
                    manifests = [(s.id, s.cache_name, copy.deepcopy(s.manifest)) for s in sources]
                    owner = await session.get(User, job.owner_user_id)
                    assert owner is not None
                    actor = Principal(owner.id, owner.role, job.auth_version)
                    revision, session_hash = job.config_revision, job.auth_session_hash
                if manifests and manifests[0][2].get("transport") == "ssh":
                    await self._remote_sources(
                        project_id,
                        job_id,
                        manifests,
                        document,
                        token,
                        actor,
                        revision,
                        session_hash,
                    )
                else:
                    for source_id, cache_name, manifest in manifests:
                        token.check()
                        await self._source(
                            project_id, job_id, source_id, cache_name, manifest, document, token
                        )
                async with self.sessions.begin() as session:
                    job = await self._dispatch(session, *key)
                    job.status = "partial" if job.errors else "completed"
                    job.snapshot_revision += 1
        except Exception as error:
            token.cancel()
            code = getattr(error, "code", "COLLECTION_FAILED")
            try:
                async with self.sessions.begin() as session:
                    interrupted_job = await session.get(HistoryJob, key, with_for_update=True)
                    if interrupted_job is not None:
                        job = interrupted_job
                        job.status = (
                            "cancelled"
                            if code in {"CANCELLED", "AUTH_REVOKED"}
                            else "partial"
                            if job.event_count
                            else "failed"
                        )
                        job.errors = list(dict.fromkeys([*job.errors, code]))
                        job.snapshot_revision += 1
                        await session.execute(
                            update(HistorySource)
                            .where(
                                HistorySource.project_id == project_id,
                                HistorySource.job_id == job_id,
                                HistorySource.status.in_(["collecting", "queued"]),
                            )
                            .values(status="partial", error_code=code)
                        )
            except Exception:
                # Readiness/auth fail closed; startup marks nonterminal jobs interrupted.
                pass
        finally:
            self.tokens.pop(key, None)

    async def _remote_sources(
        self,
        project_id: str,
        job_id: str,
        manifests: list,
        document: dict,
        token: Any,
        actor: Principal,
        revision: int,
        session_hash: str | None,
    ) -> None:
        from inspector.ssh_files import open_files

        assert self.remote is not None
        remote_history = self.remote
        groups: dict[str, list] = {}
        for item in manifests:
            groups.setdefault(item[2]["connection_id"], []).append(item)
        for connection_id, group in groups.items():
            snapshot = await remote_history.access.prepare(
                actor, project_id, connection_id, revision, session_hash
            )
            if any(manifest["access_signature"] != snapshot.signature for _, _, manifest in group):
                raise DomainError(
                    "REVISION_CONFLICT", "Source approval changed before dispatch.", 409
                )

            async def operation(snapshot: Any = snapshot, group: list = group) -> None:
                async with (
                    remote_history.host_slots,
                    open_files(
                        snapshot.target,
                        snapshot.jump,
                        allow_loopback=self.config.ssh_allow_loopback,
                        # Per-operation cap includes every file and parsing/indexing.
                        timeout_seconds=self.config.history_limits.get(
                            "archive_task_timeout_seconds", 120
                        ),
                        **remote_history.file_limits(),
                    ) as remote,
                ):
                    for source_id, cache_name, manifest in group:
                        token.check()
                        await self._source(
                            project_id,
                            job_id,
                            source_id,
                            cache_name,
                            manifest,
                            document,
                            token,
                            remote=remote,
                        )

            async def guarded_operation() -> None:
                async def watch_job() -> None:
                    while True:
                        token.check()
                        async with asyncio.timeout(1), self.sessions.begin() as session:
                            await self._dispatch(session, project_id, job_id)
                        await asyncio.sleep(0.25)

                work, watch = asyncio.create_task(operation()), asyncio.create_task(watch_job())
                try:
                    done, _ = await asyncio.wait((work, watch), return_when=asyncio.FIRST_COMPLETED)
                    if watch in done:
                        await watch
                    await work
                finally:
                    for task in (work, watch):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(work, watch, return_exceptions=True)

            await remote_history.access.watched(
                actor,
                project_id,
                connection_id,
                revision,
                session_hash,
                snapshot,
                guarded_operation,
            )

    async def _source(
        self,
        project_id: str,
        job_id: str,
        source_id: str,
        cache_name: str,
        manifest: dict,
        document: dict,
        token: Any,
        remote: Any = None,
    ) -> None:
        from inspector.log_engine import (
            CorrelationMarker,
            EngineError,
            EngineLimits,
            LocalSource,
            ParserConfig,
            ScanProgress,
            iter_source_events,
        )

        async with self.sessions.begin() as session:
            job = await self._dispatch(session, project_id, job_id)
            job.status = "collecting"
            source = await session.get(HistorySource, (project_id, job_id, source_id))
            assert source is not None
            source.status = "collecting"
            remaining_download = (
                self.config.history_limits.get("max_download_bytes_per_collection", 536_870_912)
                - job.downloaded_bytes
            )
            remaining_expanded = (
                self.config.history_limits.get("max_expanded_bytes_per_collection", 1_073_741_824)
                - job.expanded_bytes
            )
        processes = {p["id"]: p for p in document["processes"]}
        servers = {s["id"]: s for s in document["servers"]}
        parsers = {p["id"]: p for p in document["parsers"]}
        process = processes[manifest["process_id"]]
        server = servers[process["server_id"]]
        parser = parsers[process["log_source"]["parser_id"]]
        destination = self.cache_path(project_id, job_id, cache_name)
        limits = EngineLimits(
            max_download_bytes=max(1, remaining_download),
            max_expanded_bytes=max(1, remaining_expanded),
            max_member_bytes=self.config.history_limits.get(
                "max_expanded_member_bytes", 134_217_728
            ),
            max_members=self.config.history_limits.get("max_archive_members", 10_000),
            max_compression_ratio=self.config.history_limits.get("max_compression_ratio", 500),
            max_line_bytes=self.config.history_limits.get("max_line_bytes", 262_144),
            wall_seconds=self.config.history_limits.get("archive_task_timeout_seconds", 120),
        )
        progress = ScanProgress()
        captured_checksum = None
        captured_bytes = 0
        if remote is not None:
            from inspector.ssh_files import RemoteFile

            temporary = destination.with_suffix(".part")
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                if remaining_download <= 0 or remaining_expanded <= 0:
                    raise DomainError(
                        "COLLECTION_BUDGET", "The remaining collection budget is exhausted.", 413
                    )
                with temporary.open("xb") as outgoing:
                    temporary.chmod(0o600)
                    result = await remote.copy(
                        RemoteFile(**manifest["remote_file"]),
                        outgoing,
                        max_bytes=max(0, remaining_download),
                    )
                captured_checksum, captured_bytes = result.checksum, result.bytes
                temporary.replace(destination)
            except BaseException as error:
                copied_bytes = temporary.stat().st_size if temporary.exists() else 0
                temporary.unlink(missing_ok=True)
                try:
                    async with asyncio.timeout(0.5), self.sessions.begin() as cleanup:
                        stopped_job = await cleanup.get(
                            HistoryJob, (project_id, job_id), with_for_update=True
                        )
                        stopped_source = await cleanup.get(
                            HistorySource, (project_id, job_id, source_id), with_for_update=True
                        )
                        if stopped_job is not None and stopped_source is not None:
                            code = getattr(
                                error,
                                "code",
                                "CANCELLED"
                                if isinstance(error, asyncio.CancelledError)
                                else "SOURCE_UNAVAILABLE",
                            )
                            stopped_source.downloaded_bytes = copied_bytes
                            stopped_source.error_code = code
                            stopped_source.status = "failed"
                            stopped_job.downloaded_bytes += copied_bytes
                            stopped_job.errors = list(dict.fromkeys([*stopped_job.errors, code]))
                except Exception:
                    pass
                if isinstance(error, DomainError):
                    return  # A per-source SFTP failure remains visible; other files can be scanned.
                raise
        queue: asyncio.Queue = asyncio.Queue(maxsize=2)
        loop = asyncio.get_running_loop()

        def put(value: Any) -> None:
            import concurrent.futures

            pending = asyncio.run_coroutine_threadsafe(queue.put(value), loop)
            while True:
                try:
                    pending.result(timeout=0.1)
                    break
                except concurrent.futures.TimeoutError:
                    try:
                        token.check()
                    except Exception:
                        pending.cancel()
                        raise

        def worker() -> None:
            temporary = destination.with_suffix(".part")
            copied = captured_bytes if remote is not None else 0
            try:
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                # Capture immutable fixture bytes into a separate generated project/job namespace.
                digest = hashlib.sha256()
                if remaining_download <= 0 or remaining_expanded <= 0:
                    raise EngineError("COLLECTION_BUDGET")
                if remote is None:
                    origin = Path(manifest["local_path"])
                    with origin.open("rb") as incoming, temporary.open("xb") as outgoing:
                        temporary.chmod(0o600)
                        while block := incoming.read(65_536):
                            token.check()
                            copied += len(block)
                            if copied > remaining_download:
                                raise EngineError("DOWNLOAD_LIMIT")
                            digest.update(block)
                            outgoing.write(block)
                    if digest.hexdigest() != manifest["file_sha256"]:
                        raise EngineError("SOURCE_CHANGED")
                    temporary.replace(destination)
                else:
                    copied = captured_bytes
                    progress.source_sha256 = captured_checksum
                source = LocalSource(
                    project_id=project_id,
                    process_id=process["id"],
                    source_revision_id=source_id,
                    path=destination,
                    remote_path=manifest["remote_path"],
                    kind=manifest["kind"],
                    archive_member=manifest["archive_member"],
                    member_ordinal=manifest["member_ordinal"],
                    server_id=server["id"],
                    process_name=process["name"],
                    server_name=server["name"],
                    parser=ParserConfig(**parser["timestamp"]),
                    encoding=process["log_source"]["encoding"],
                    member_globs=tuple(manifest.get("member_patterns") or ["*"]),
                    correlation_markers=tuple(
                        CorrelationMarker(**marker)
                        for marker in parser.get("correlation_markers", [])
                    ),
                )
                batch: list[dict] = []
                batch_bytes = 0
                for event in iter_source_events(
                    source, limits=limits, cancellation=token, progress=progress
                ):
                    event_bytes = len(event["raw_line"].encode("utf-8"))
                    if batch and batch_bytes + event_bytes > 1_048_576:
                        put((batch, None))
                        batch = []
                        batch_bytes = 0
                    batch.append(event)
                    batch_bytes += event_bytes
                    if len(batch) == 1000:
                        put((batch, None))
                        batch = []
                        batch_bytes = 0
                if batch:
                    put((batch, None))
                put((None, None))
            except Exception as error:
                temporary.unlink(missing_ok=True)
                progress.downloaded_bytes = max(progress.downloaded_bytes, copied)
                try:
                    put((None, getattr(error, "code", "SOURCE_UNAVAILABLE")))
                except Exception:
                    pass

        future = loop.run_in_executor(self.executor, worker)
        source_error = None
        last_download = last_expanded = 0
        terminal_pending = False
        try:
            while True:
                if terminal_pending:
                    break
                try:
                    batch, source_error = await asyncio.wait_for(queue.get(), timeout=0.25)
                except TimeoutError:
                    # Re-check auth/revocation/DB availability within two seconds even while a worker is busy.
                    async with self.sessions.begin() as session:
                        await self._dispatch(session, project_id, job_id)
                    if future.done() and queue.empty():
                        source_error = "CANCELLED"
                        break
                    continue
                if batch is None:
                    break
                async with self.sessions.begin() as session:
                    job = await self._dispatch(session, project_id, job_id)
                    source = await session.get(
                        HistorySource, (project_id, job_id, source_id), with_for_update=True
                    )
                    assert source is not None
                    # File parsing can fill the second bounded queue slot while
                    # the first INSERT is in flight. Coalesce only that ready
                    # batch, preserving a <=2000-event / 2-MiB transaction.
                    with session.no_autoflush:
                        await persist_event_batch(session, job, source, batch)
                        try:
                            extra, extra_error = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                        else:
                            if extra is None:
                                source_error = extra_error
                                terminal_pending = True
                            else:
                                if (
                                    len(batch) + len(extra) > 2000
                                    or sum(
                                        len(event["raw_line"].encode("utf-8"))
                                        for event in [*batch, *extra]
                                    )
                                    > 2_097_152
                                ):
                                    raise DomainError(
                                        "INDEX_BATCH_LIMIT",
                                        "The bounded index batch exceeds its policy.",
                                        413,
                                    )
                                await persist_event_batch(session, job, source, extra)
                    # Progress is a monotonic worker snapshot; counts can lead committed rows but never invent events.
                    downloaded, expanded = progress.downloaded_bytes, progress.expanded_bytes
                    job.downloaded_bytes += downloaded - last_download
                    job.expanded_bytes += expanded - last_expanded
                    source.downloaded_bytes = downloaded
                    source.expanded_bytes = expanded
                    last_download, last_expanded = downloaded, expanded
                    job.snapshot_revision += 1
            await asyncio.shield(future)
            async with self.sessions.begin() as session:
                job = await self._dispatch(session, project_id, job_id)
                source = await session.get(
                    HistorySource, (project_id, job_id, source_id), with_for_update=True
                )
                assert source is not None
                source.downloaded_bytes = progress.downloaded_bytes
                source.expanded_bytes = progress.expanded_bytes
                source.checksum = progress.source_sha256
                source.status = (
                    "completed"
                    if source_error is None
                    else "partial"
                    if source.event_count
                    else "failed"
                )
                source.error_code = source_error
                job.downloaded_bytes += progress.downloaded_bytes - last_download
                job.expanded_bytes += progress.expanded_bytes - last_expanded
                if source_error:
                    job.errors = list(dict.fromkeys([*job.errors, source_error]))
                job.snapshot_revision += 1
        except BaseException:
            token.cancel()
            await asyncio.shield(future)
            try:
                # Cleanup records actual captured bytes even when the protected
                # dispatch was revoked before its first complete event batch.
                async with asyncio.timeout(0.5), self.sessions.begin() as cleanup:
                    stopped_job = await cleanup.get(
                        HistoryJob, (project_id, job_id), with_for_update=True
                    )
                    stopped_source = await cleanup.get(
                        HistorySource, (project_id, job_id, source_id), with_for_update=True
                    )
                    if stopped_job is not None and stopped_source is not None:
                        stopped_job.downloaded_bytes += max(
                            0, progress.downloaded_bytes - stopped_source.downloaded_bytes
                        )
                        stopped_job.expanded_bytes += max(
                            0, progress.expanded_bytes - stopped_source.expanded_bytes
                        )
                        stopped_source.downloaded_bytes = max(
                            stopped_source.downloaded_bytes, progress.downloaded_bytes
                        )
                        stopped_source.expanded_bytes = max(
                            stopped_source.expanded_bytes, progress.expanded_bytes
                        )
                        stopped_source.checksum = progress.source_sha256
                        stopped_source.status = "partial"
                        stopped_source.error_code = "CANCELLED"
                        stopped_job.snapshot_revision += 1
            except Exception:
                pass  # An unavailable database cannot authorize further data dispatch.
            raise


def build_history_router(
    transaction: Callable, authenticated: Callable, protected_write: Callable
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}")
    Session = Annotated[AsyncSession, Depends(transaction, scope="function")]
    Actor = Annotated[Principal, Depends(authenticated)]
    Writer = Annotated[Principal, Depends(protected_write)]

    @router.post(
        "/collections/plan",
        response_model=HistoricalPlanResponse,
        openapi_extra={"x-permission": "collection.create"},
    )
    async def plan(
        project_id: str,
        payload: HistoricalScopeInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        _project, _document, candidates = await planning_context(
            session,
            actor,
            project_id,
            payload,
            request.app.state.config,
            request.app.state.history.remote,
            token_hash(request.cookies.get("__Host-si-session", "")),
        )
        return plan_response(project_id, payload, candidates)

    @router.post(
        "/collections",
        response_model=HistoricalJobResponse,
        status_code=202,
        openapi_extra={"x-permission": "collection.create"},
    )
    async def start(
        project_id: str,
        payload: HistoricalScopeInput,
        request: Request,
        background: BackgroundTasks,
        actor: Writer,
        session: Session,
    ) -> dict:
        config = request.app.state.config
        project, document, candidates = await planning_context(
            session,
            actor,
            project_id,
            payload,
            config,
            request.app.state.history.remote,
            token_hash(request.cookies.get("__Host-si-session", "")),
        )
        # current_actor's security lock serializes reservation with every start/revocation.
        active = select(HistoryJob).where(HistoryJob.status.in_(NONTERMINAL))
        global_count = await session.scalar(select(func.count()).select_from(active.subquery()))
        own_count = await session.scalar(
            select(func.count()).select_from(
                active.where(HistoryJob.owner_user_id == actor.user_id).subquery()
            )
        )
        project_count = await session.scalar(
            select(func.count()).select_from(
                active.where(HistoryJob.project_id == project_id).subquery()
            )
        )
        if (
            global_count >= config.history_limits.get("max_collection_jobs_global", 4)
            or own_count >= config.history_limits.get("max_collection_jobs_per_user", 2)
            or project_count >= config.history_limits.get("max_collection_jobs_per_project", 2)
        ):
            raise DomainError(
                "LIMIT_REACHED", "The collection concurrency limit has been reached.", 429
            )
        from inspector.app import SESSION_COOKIE

        job_id = str(uuid4())
        job = HistoryJob(
            project_id=project_id,
            id=job_id,
            workspace_id=payload.workspace_id,
            owner_user_id=actor.user_id,
            auth_version=actor.auth_version,
            auth_session_hash=token_hash(request.cookies.get(SESSION_COOKIE, "")),
            config_revision=project.revision,
            config_snapshot=copy.deepcopy(document),
            process_ids=payload.process_ids,
            from_us=canonical_time(payload.from_),
            to_us=canonical_time(payload.to),
            status="queued",
            snapshot_revision=0,
            event_count=0,
            parse_issue_count=0,
            downloaded_bytes=0,
            expanded_bytes=0,
            created_us=services.utc_now_us(),
            errors=list(
                dict.fromkeys(
                    warning for candidate in candidates for warning in candidate.get("warnings", [])
                )
            ),
        )
        session.add(job)
        await session.flush()
        for candidate in candidates:
            session.add(
                HistorySource(
                    project_id=project_id,
                    job_id=job_id,
                    id=candidate["source_revision_id"],
                    process_id=candidate["process_id"],
                    remote_path=candidate["remote_path"],
                    kind=candidate["kind"],
                    cache_name=str(uuid4()),
                    checksum=None,
                    status="queued",
                    error_code=None,
                    event_count=0,
                    downloaded_bytes=0,
                    expanded_bytes=0,
                    manifest=candidate,
                )
            )
        services.audit(
            session, actor, "collection.create", project_id, job_id, services.utc_now_us()
        )
        await session.flush()
        background.add_task(request.app.state.history.launch, project_id, job_id)
        return await job_response(session, job)

    @router.get(
        "/jobs/{job_id}",
        response_model=HistoricalJobResponse,
        openapi_extra={"x-permission": "collection.read"},
    )
    @router.get(
        "/investigations/{job_id}",
        response_model=HistoricalJobResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def read_job(project_id: str, job_id: str, actor: Actor, session: Session) -> dict:
        return await job_response(session, await checked_job(session, actor, project_id, job_id))

    @router.get(
        "/investigations",
        response_model=HistoricalListResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def investigations(project_id: str, actor: Actor, session: Session) -> dict:
        actor = await services.current_actor(session, actor)
        await services.project_in_context(session, ProjectContext(project_id, actor.user_id))
        authorize(actor, "investigation.read", owner_user_id=actor.user_id)
        jobs = (
            await session.scalars(
                select(HistoryJob)
                .where(
                    HistoryJob.project_id == project_id, HistoryJob.owner_user_id == actor.user_id
                )
                .order_by(HistoryJob.created_us.desc())
                .limit(100)
            )
        ).all()
        return dict(project_id=project_id, items=[await job_response(session, job) for job in jobs])

    @router.post(
        "/jobs/{job_id}/cancel",
        response_model=HistoricalJobResponse | HistoricalAdministrativeCancelResponse,
        openapi_extra={"x-permission": "collection.cancel"},
    )
    async def cancel(
        project_id: str,
        job_id: str,
        payload: EmptyInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        actor = await services.current_actor(session, actor)
        job = await session.scalar(
            select(HistoryJob)
            .where(HistoryJob.project_id == project_id, HistoryJob.id == job_id)
            .with_for_update()
        )
        if job is None:
            raise not_found()
        authorize(actor, "collection.cancel", owner_user_id=job.owner_user_id)
        if job.status in NONTERMINAL:
            job.status = "cancel_requested"
            request.app.state.history.cancel(project_id, job_id)
            services.audit(
                session, actor, "collection.cancel", project_id, job_id, services.utc_now_us()
            )
        if job.owner_user_id != actor.user_id:
            return dict(project_id=project_id, job_id=job_id, status=job.status)
        return await job_response(session, job)

    @router.delete(
        "/investigations/{investigation_id}",
        response_model=HistoricalDeleteResponse,
        openapi_extra={"x-permission": "investigation.delete"},
    )
    async def delete_investigation(
        project_id: str,
        investigation_id: str,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        return await request.app.state.history.delete_capture(
            session, actor, project_id, investigation_id
        )

    @router.post(
        "/investigations/{job_id}/query",
        response_model=HistoricalQueryResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def query(
        project_id: str,
        job_id: str,
        payload: HistoricalQueryInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        from inspector.app import SESSION_COOKIE

        await session.commit()
        async with request.app.state.history.use_capture(project_id, job_id):
            result = await historical_query(
                session,
                actor,
                project_id,
                job_id,
                payload,
                supervisor=request.app.state.supervisor,
                login_hash=token_hash(request.cookies.get(SESSION_COOKIE, "")),
                idle_timeout_us=request.app.state.config.idle_timeout_us,
            )
            await session.commit()
            return result

    @router.post(
        "/investigations/{job_id}/events/{event_id}/context",
        response_model=HistoricalContextResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def context(
        project_id: str,
        job_id: str,
        event_id: str,
        payload: HistoricalContextInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        await session.commit()
        async with request.app.state.history.use_capture(project_id, job_id):
            result = await historical_context(session, actor, project_id, job_id, event_id, payload)
            await session.commit()
            return result

    @router.post(
        "/investigations/{job_id}/sources/{source_id}/download",
        response_model=HistoricalDownloadResponse,
        openapi_extra={"x-permission": "download.read"},
    )
    async def grant_download(
        project_id: str,
        job_id: str,
        source_id: str,
        payload: EmptyInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        await session.commit()
        async with request.app.state.history.use_capture(project_id, job_id):
            result = await create_download_grant(project_id, job_id, source_id, actor, session)
            await session.commit()
            return result

    async def create_download_grant(
        project_id: str,
        job_id: str,
        source_id: str,
        actor: Principal,
        session: AsyncSession,
    ) -> dict:
        job = await checked_job(session, actor, project_id, job_id)
        source = await session.get(HistorySource, (project_id, job_id, source_id))
        if source is None:
            raise not_found()
        if source.status != "completed":
            raise DomainError(
                "SOURCE_INCOMPLETE",
                "A complete retained source is required for a raw download.",
                409,
            )
        opaque = issue_token()
        await session.execute(
            delete(HistoryDownload).where(HistoryDownload.expires_us <= services.utc_now_us())
        )
        session.add(
            HistoryDownload(
                token_hash=token_hash(opaque),
                project_id=project_id,
                job_id=job_id,
                owner_user_id=actor.user_id,
                source_revision_id=source_id,
                auth_version=actor.auth_version,
                expires_us=services.utc_now_us() + 60_000_000,
            )
        )
        services.audit(session, actor, "download.create", project_id, job.id, services.utc_now_us())
        return dict(
            project_id=project_id,
            download_id=opaque,
            url=f"/api/v1/projects/{project_id}/downloads/{opaque}",
        )

    @router.get("/downloads/{opaque_id}", openapi_extra={"x-permission": "download.read"})
    async def download(
        project_id: str, opaque_id: str, request: Request, actor: Actor, session: Session
    ) -> StreamingResponse:
        grant = await session.get(HistoryDownload, token_hash(opaque_id) or "")
        if (
            grant is None
            or grant.project_id != project_id
            or grant.owner_user_id != actor.user_id
            or grant.auth_version != actor.auth_version
            or grant.expires_us <= services.utc_now_us()
        ):
            raise not_found()
        await checked_job(session, actor, project_id, grant.job_id)
        source = await session.get(
            HistorySource, (project_id, grant.job_id, grant.source_revision_id)
        )
        if source is None or source.status != "completed":
            raise not_found()
        path = request.app.state.history.cache_path(project_id, grant.job_id, source.cache_name)
        if not path.is_file() or path.is_symlink():
            raise DomainError("SOURCE_EXPIRED", "The captured source is unavailable.", 410)
        from inspector.app import SESSION_COOKIE
        from inspector.history_retention import read_download_chunk

        login_hash = token_hash(request.cookies.get(SESSION_COOKIE, ""))
        job_id, grant_hash = grant.job_id, grant.token_hash
        await session.commit()

        async def chunks() -> AsyncIterator[bytes]:
            # Revalidate in separate short transactions; do not retain a grant through logout/outage.
            offset = 0
            while True:
                async with request.app.state.history.use_capture(project_id, job_id):
                    async with request.app.state.sessions.begin() as check:
                        now = services.utc_now_us()
                        login = await check.get(AuthSession, login_hash or "")
                        user = await check.get(User, actor.user_id)
                        retained_grant = await check.get(HistoryDownload, grant_hash)
                        if (
                            login is None
                            or user is None
                            or retained_grant is None
                            or not user.enabled
                            or user.auth_version != actor.auth_version
                            or auth.session_expired(
                                login, now, request.app.state.config.idle_timeout_us
                            )
                            or not await request.app.state.supervisor.healthy()
                        ):
                            return
                    # Close each bounded read before releasing the guard. A
                    # deletion can then unlink safely on Windows or Linux and
                    # the next iteration observes the removed download grant.
                    data = await asyncio.to_thread(
                        read_download_chunk, path, Path(request.app.state.config.cache_dir), offset
                    )
                if not data:
                    break
                offset += len(data)
                yield data

        return StreamingResponse(
            chunks(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": 'attachment; filename="captured-source.bin"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    return router
