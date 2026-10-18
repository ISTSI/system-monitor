"""Private live control leases, bounded delivery and durable retained recordings."""

import asyncio
import copy
import logging
import os
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from pydantic import Field, ValidationError, model_validator
from sqlalchemy import and_, case, delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from inspector import auth, services
from inspector.domain import ID_PATTERN, Principal, ProjectContext, server_connection_id
from inspector.errors import DomainError
from inspector.history import (
    HistoricalEvent,
    HistoricalFilter,
    StrictInput,
    format_time,
    persist_event_batch,
)
from inspector.persistence.models import (
    Audit,
    AuthSession,
    HistoryJob,
    HistorySource,
    LiveSession,
    LiveSubscription,
    SecurityState,
    TopologyState,
    User,
    Workspace,
)
from inspector.security import authorize, token_hash

ACTIVE = ("starting", "following", "reconnecting", "blocked")
LEASE_US = 300_000_000
_LOGGER = logging.getLogger(__name__)


class LiveControlInput(StrictInput):
    workspace_id: str = Field(pattern=ID_PATTERN)
    lease_revision: int = Field(ge=1)


class LiveHistoryInput(LiveControlInput):
    requested_rows: int | None = Field(default=None, ge=1, le=500)


class LiveViewInput(StrictInput):
    global_filter: HistoricalFilter = Field(default_factory=HistoricalFilter)
    per_process_filters: dict[str, HistoricalFilter] = Field(default_factory=dict, max_length=200)
    requested_rows: int = Field(default=30, ge=1, le=500)
    layout: Literal["merged", "split"] = "merged"
    seed_rows_by_process: dict[str, Annotated[int, Field(ge=1, le=500)]] = Field(
        default_factory=dict, max_length=200
    )


class LiveCreateInput(LiveViewInput):
    model_config = {
        "extra": "forbid",
        "strict": True,
        "populate_by_name": False,
        "validate_by_alias": True,
        "validate_by_name": False,
    }
    project_id: str = Field(pattern=ID_PATTERN)
    project_revision: int = Field(ge=1)
    workspace_id: str = Field(pattern=ID_PATTERN)
    process_ids: list[Annotated[str, Field(pattern=ID_PATTERN)]] = Field(
        min_length=1, max_length=200
    )
    global_filter: HistoricalFilter = Field(alias="filter")
    per_process_filters: dict[str, HistoricalFilter] = Field(max_length=200)
    requested_rows: int = Field(alias="seed_rows", ge=1, le=500)
    seed_rows_by_process: dict[str, Annotated[int, Field(ge=1, le=500)]] = Field(max_length=200)
    layout: Literal["merged", "split"] = Field(alias="mode")
    recording: bool = Field(alias="record")

    @model_validator(mode="after")
    def selection(self) -> "LiveCreateInput":
        if len(set(self.process_ids)) != len(self.process_ids):
            raise ValueError("Select each process once.")
        if not set(self.per_process_filters) <= set(self.process_ids):
            raise ValueError("Per-process filters must belong to the selection.")
        if not set(self.seed_rows_by_process) <= set(self.process_ids):
            raise ValueError("Per-process seed requests must belong to the selection.")
        return self


class LiveFilterInput(LiveViewInput, LiveControlInput):
    expected_filter_version: int = Field(ge=1)


class LiveAttachInput(StrictInput):
    workspace_id: str = Field(pattern=ID_PATTERN)
    expected_lease_revision: int = Field(ge=1)


class LiveEvent(HistoricalEvent):
    late_arrival: bool = False


class LiveSnapshot(StrictInput):
    events: list[LiveEvent] = Field(default_factory=list)
    diagnostics: list[LiveEvent] = Field(default_factory=list)
    counters: dict[str, int] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)
    filter_version: int = 1
    seq: int = 0


class LiveSessionResponse(StrictInput):
    project_id: str
    session_id: str
    workspace_id: str
    lease_revision: int
    filter_version: int
    status: str
    process_ids: list[str]
    recording: bool
    investigation_id: str | None
    layout: Literal["merged", "split"]
    global_filter: HistoricalFilter
    per_process_filters: dict[str, HistoricalFilter]
    requested_rows: int
    seed_rows_by_process: dict[str, int] = Field(default_factory=dict)
    detached: bool
    error_code: str | None = None
    snapshot: LiveSnapshot


class LiveListResponse(StrictInput):
    project_id: str
    items: list[LiveSessionResponse]


class LiveUsageResponse(StrictInput):
    project_id: str
    workspace_id: str | None
    counts: dict[str, int]
    limits: dict[str, int]


class LiveFrame(StrictInput):
    protocol_version: Literal[2] = 2
    type: Literal[
        "snapshot",
        "events",
        "status",
        "filter_applied",
        "gap",
        "resync_required",
        "counters",
        "heartbeat",
        "error",
        "stopped",
    ]
    project_id: str = Field(pattern=ID_PATTERN)
    workspace_id: str = Field(pattern=ID_PATTERN)
    session_id: str = Field(pattern=ID_PATTERN)
    filter_version: int = Field(ge=1)
    seq: int = Field(ge=1)
    sent_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
    payload: dict[str, Any]


class ClientFrame(StrictInput):
    protocol_version: Literal[2]
    type: Literal["hello", "ack"]
    project_id: str = Field(pattern=ID_PATTERN)
    workspace_id: str = Field(pattern=ID_PATTERN)
    session_id: str = Field(pattern=ID_PATTERN)
    filter_version: int = Field(ge=1)
    payload: dict[str, Any]


class HelloInput(StrictInput):
    csrf_token: str = Field(max_length=128)
    lease_revision: int = Field(ge=1)
    last_seq: int | None = Field(default=None, ge=0)


class AckInput(StrictInput):
    last_seq: int = Field(ge=0)


def missing() -> DomainError:
    return DomainError("NOT_FOUND", "Resource not found.", 404)


class LiveManager:
    def __init__(
        self, config: Any, sessions: Any, supervisor: Any, source_access: Any, history: Any
    ) -> None:
        from inspector.live_engine import LiveEngine, LiveLimits

        self.config, self.sessions, self.supervisor = config, sessions, supervisor
        self.access, self.history = source_access, history
        limits = config.history_limits
        frame_bytes = max(1, min(2_097_152, limits.get("max_ws_frame_bytes", 1_048_576)) - 4096)
        self.engine = LiveEngine(
            LiveLimits(
                max_raw_events=min(20_000, limits.get("live_buffer_events_per_process", 20_000)),
                max_raw_bytes=min(
                    33_554_432, limits.get("live_buffer_bytes_per_process", 33_554_432)
                ),
                max_line_bytes=min(262_144, limits.get("max_line_bytes", 262_144)),
                max_seed_bytes=min(
                    20_971_520, limits.get("live_seed_max_scan_bytes_per_process", 20_971_520)
                ),
                max_seed_lines=min(
                    200_000, limits.get("live_seed_max_scan_lines_per_process", 200_000)
                ),
                seed_seconds=min(10, limits.get("live_seed_timeout_seconds", 10)),
                max_replay_frames=min(100, limits.get("ws_queue_max_frames_per_client", 100)),
                max_frame_bytes=frame_bytes,
                max_snapshot_bytes=min(524_288, max(1, frame_bytes // 2)),
            )
        )
        self.lease_us = min(300, limits.get("live_reconnect_lease_seconds", 300)) * 1_000_000
        self.locks: dict[str, tuple[asyncio.Lock, int]] = {}
        self.lock_owners: dict[str, asyncio.Task | None] = {}
        self.sockets: dict[str, WebSocket] = {}
        self.guard_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self.closed = False
        self.failed_closed = False
        self.maintenance = asyncio.create_task(self._maintain())

    @asynccontextmanager
    async def _use_session(self, identifier: str) -> Any:
        task = asyncio.current_task()
        if self.lock_owners.get(identifier) is task and task is not None:
            yield
            return
        lock, users = self.locks.get(identifier, (asyncio.Lock(), 0))
        self.locks[identifier] = lock, users + 1
        try:
            async with lock:
                self.lock_owners[identifier] = task
                try:
                    yield
                finally:
                    self.lock_owners.pop(identifier, None)
        finally:
            _, users = self.locks[identifier]
            if users == 1:
                del self.locks[identifier]
            else:
                self.locks[identifier] = lock, users - 1

    async def _principal(self, session: Any, cookie: str, *, lock: bool = True) -> Principal:
        return await auth.authenticate(
            session,
            cookie,
            services.utc_now_us(),
            self.config.idle_timeout_us,
            renew_idle=False,
            lock=lock,
        )

    async def _row(
        self,
        session: Any,
        actor: Principal,
        project: str,
        identifier: str,
        *,
        action: str = "live.read",
        control: LiveControlInput | None = None,
        lock: bool = True,
    ) -> LiveSession:
        actor = await services.current_actor(session, actor, lock=lock)
        return await self._row_for_actor(
            session, actor, project, identifier, action=action, control=control, lock=lock
        )

    async def _socket_row(
        self,
        session: Any,
        cookie: str,
        project: str,
        identifier: str,
        control: LiveControlInput,
        *,
        renew_workspace: bool = False,
    ) -> tuple[Principal, LiveSession]:
        verifier = token_hash(cookie)
        if verifier is None:
            raise DomainError("AUTH_REQUIRED", "Authentication is required.", 401)
        # One fresh read, with no grant cache: all joined identities are pinned
        # by the login verifier and composite project/session/workspace keys.
        query = (
            select(SecurityState, AuthSession, User, LiveSession, Workspace)
            .select_from(SecurityState)
            .outerjoin(AuthSession, AuthSession.token_hash == verifier)
            .outerjoin(User, User.id == AuthSession.user_id)
            .outerjoin(
                LiveSession,
                and_(
                    # SecurityState(id1) gates this project's read. The explicit
                    # dependency also gives MySQL's nested-join linter its edge.
                    LiveSession.project_id == case((SecurityState.id == 1, project), else_=None),
                    LiveSession.id == identifier,
                ),
            )
            .outerjoin(
                Workspace,
                and_(
                    Workspace.project_id == LiveSession.project_id,
                    Workspace.id == LiveSession.workspace_id,
                ),
            )
            .where(SecurityState.id == 1)
            .execution_options(populate_existing=True)
        )
        record = (await session.execute(query)).first()
        if record is None:
            raise DomainError("SECURITY_NOT_READY", "Security state is not initialized.", 503)
        _, login, user, row, workspace = record
        actor = auth._validated_authentication(
            login, user, services.utc_now_us(), self.config.idle_timeout_us
        )
        row = self._validated_row(actor, row, action="live.read", control=control)
        workspace = self._validated_workspace(actor, workspace)
        self._active_workspace(row, workspace)
        if renew_workspace:
            workspace.expires_us = services.utc_now_us() + LEASE_US
            row.detached_until_us = None
        return actor, row

    async def _row_for_actor(
        self,
        session: Any,
        actor: Principal,
        project: str,
        identifier: str,
        *,
        action: str,
        control: LiveControlInput | None,
        lock: bool,
    ) -> LiveSession:
        row = await session.get(
            LiveSession, (project, identifier), populate_existing=True, with_for_update=lock
        )
        row = self._validated_row(actor, row, action=action, control=control)
        if control is not None and not (
            action == "live.stop"
            and actor.role == "administrator"
            and row.owner_user_id != actor.user_id
        ):
            workspace = await self._workspace(
                session, actor, project, control.workspace_id, lock=lock
            )
            self._active_workspace(row, workspace)
        return row

    @staticmethod
    def _validated_row(
        actor: Principal,
        row: LiveSession | None,
        *,
        action: str,
        control: LiveControlInput | None,
    ) -> LiveSession:
        if row is None:
            raise missing()
        authorize(actor, action, owner_user_id=row.owner_user_id)
        if control is not None and not (
            action == "live.stop"
            and actor.role == "administrator"
            and row.owner_user_id != actor.user_id
        ):
            if row.workspace_id != control.workspace_id:
                raise missing()
            if row.lease_revision != control.lease_revision:
                raise DomainError("REVISION_CONFLICT", "This monitor's control lease changed.", 409)
        return row

    @staticmethod
    def _active_workspace(row: LiveSession, workspace: Workspace) -> None:
        if workspace.state != "active" or row.detached_until_us is not None:
            raise DomainError("WORKSPACE_IN_USE", "Resume this detached monitor explicitly.", 409)

    async def _workspace(
        self, session: Any, actor: Principal, project: str, workspace_id: str, *, lock: bool = True
    ) -> Workspace:
        workspace = await session.get(
            Workspace, (project, workspace_id), populate_existing=True, with_for_update=lock
        )
        return self._validated_workspace(actor, workspace)

    @staticmethod
    def _validated_workspace(actor: Principal, workspace: Workspace | None) -> Workspace:
        if workspace is None or workspace.owner_user_id != actor.user_id:
            raise missing()
        if workspace.state == "expired" or workspace.expires_us <= services.utc_now_us():
            raise DomainError("WORKSPACE_EXPIRED", "Reload this page to open a new workspace.", 409)
        return workspace

    def response(self, row: LiveSession, workspace: Workspace | None = None) -> dict:
        snapshot = self.engine.snapshot(row.id) if row.id in self.engine.sessions else {}
        allowed = LiveSnapshot.model_fields
        snapshot = {key: value for key, value in snapshot.items() if key in allowed}
        return dict(
            project_id=row.project_id,
            session_id=row.id,
            workspace_id=row.workspace_id,
            lease_revision=row.lease_revision,
            filter_version=row.filter_version,
            status=row.status,
            process_ids=row.process_ids,
            recording=row.recording,
            investigation_id=row.investigation_id,
            **row.view,
            detached=row.detached_until_us is not None
            or (workspace is not None and workspace.state != "active"),
            error_code=row.error_code,
            snapshot=LiveSnapshot.model_validate(snapshot).model_dump(),
        )

    async def _guard(
        self,
        actor: Principal,
        project: str,
        identifier: str,
        snapshots: dict[str, Any],
        revision: int,
        session_hash: str,
    ) -> None:
        # Several collectors can poll together. Share only a validation which is
        # still running; completed grants are never cached or reused.
        key = (project, identifier)
        task = self.guard_tasks.get(key)
        if task is None or task.done():
            task = asyncio.create_task(
                self._fresh_guard(actor, project, identifier, snapshots, revision, session_hash)
            )
            self.guard_tasks[key] = task

            def completed(finished: asyncio.Task[None]) -> None:
                if self.guard_tasks.get(key) is finished:
                    self.guard_tasks.pop(key, None)
                if not finished.cancelled():
                    finished.exception()

            task.add_done_callback(completed)
        try:
            await asyncio.shield(task)
        finally:
            if task.done() and self.guard_tasks.get(key) is task:
                self.guard_tasks.pop(key, None)

    async def _fresh_guard(
        self,
        actor: Principal,
        project: str,
        identifier: str,
        snapshots: dict[str, Any],
        revision: int,
        session_hash: str,
    ) -> None:
        if self.closed or self.failed_closed:
            raise DomainError(
                "DATABASE_UNAVAILABLE", "Live collection requires a fresh explicit start.", 503
            )
        began = time.monotonic()
        phase = "supervisor"
        try:
            async with asyncio.timeout(1):
                await self.access._healthy()
                phase = "source_access"
                async with self.sessions.begin() as session:
                    currents = await self.access.prepare_many_in_transaction(
                        session, actor, project, list(snapshots), revision, session_hash
                    )
                    for connection_id, previous in snapshots.items():
                        if currents[connection_id].signature != previous.signature:
                            raise DomainError(
                                "REVISION_CONFLICT",
                                "Source access changed; start a new monitor.",
                                409,
                            )
                    phase = "account_and_session"
                    row = await session.get(
                        LiveSession, (project, identifier), populate_existing=True
                    )
                    if row is None or row.status not in ACTIVE:
                        raise DomainError("CANCELLED", "Live collection stopped.", 409)
                    if row.investigation_id:
                        recording = await session.get(HistoryJob, (project, row.investigation_id))
                        if recording is None or recording.status != "collecting":
                            raise DomainError("CANCELLED", "Live recording was stopped.", 409)
                    if (
                        row.detached_until_us is not None
                        and row.detached_until_us <= services.utc_now_us()
                    ):
                        raise DomainError("CANCELLED", "The reconnect lease expired.", 409)
        except (TimeoutError, SQLAlchemyError) as error:
            self.failed_closed = True
            bind = getattr(self.sessions, "kw", {}).get("bind")
            pool = bind.pool.status() if bind is not None else "unavailable"
            _LOGGER.warning(
                "Live guard failed closed: project=%s session=%s phase=%s error=%s elapsed_seconds=%.3f pool=%s",
                project,
                identifier,
                phase,
                type(error).__name__,
                time.monotonic() - began,
                pool,
            )
            raise DomainError(
                "DATABASE_UNAVAILABLE",
                "Live collection stopped because persistence could not be verified.",
                503,
            ) from None

    async def create(
        self, actor: Principal, project: str, payload: LiveCreateInput, cookie: str
    ) -> dict:
        from inspector.live_engine import LiveSource
        from inspector.log_engine import ParserConfig

        if payload.project_id != project:
            raise DomainError(
                "INVALID_REQUEST", "The request system must match the route system.", 422
            )

        if self.failed_closed:
            raise DomainError(
                "DATABASE_UNAVAILABLE",
                "Restart the backend before explicitly starting collection.",
                503,
            )
        if self.config.history_limits.get("max_ws_frame_bytes", 1_048_576) < 32768:
            raise DomainError(
                "LIMIT_REACHED",
                "The configured WebSocket byte limit is too small for live scope and status frames (minimum 32768).",
                413,
            )
        session_hash = token_hash(cookie)
        if session_hash is None:
            raise missing()
        identifier = str(uuid4())
        async with self.sessions.begin() as session:
            actor = await self._principal(session, cookie)
            authorize(actor, "live.create")
            workspace = await self._workspace(session, actor, project, payload.workspace_id)
            if workspace.state != "active":
                raise DomainError("WORKSPACE_IN_USE", "Open a fresh page workspace.", 409)
            configuration = await services.project_in_context(
                session, ProjectContext(project, actor.user_id), lock=True
            )
            if configuration.archived:
                raise DomainError(
                    "PROJECT_ARCHIVED", "Archived systems cannot start collection.", 409
                )
            if configuration.revision != payload.project_revision:
                raise DomainError(
                    "REVISION_CONFLICT",
                    "System configuration changed; reload before monitoring.",
                    409,
                )
            document = copy.deepcopy((await session.get(TopologyState, project)).config)
            processes = {entry["id"]: entry for entry in document["processes"]}
            servers = {entry["id"]: entry for entry in document["servers"]}
            parsers = {entry["id"]: entry for entry in document["parsers"]}
            if not set(payload.process_ids) <= processes.keys():
                raise missing()
            process_connections = {
                process_id: server_connection_id(servers[processes[process_id]["server_id"]])
                for process_id in payload.process_ids
            }
            usage = await self.usage(session, actor, project, payload.workspace_id)
            for scope, count in usage["counts"].items():
                if count + len(payload.process_ids) > usage["limits"][scope]:
                    raise DomainError(
                        "LIMIT_REACHED",
                        f"Live {scope.rstrip('_')} subscription capacity reached ({count}/{usage['limits'][scope]}).",
                        429,
                    )
            snapshots = {}
            sources = []
            for process_id in payload.process_ids:
                process = processes[process_id]
                server = servers[process["server_id"]]
                connection_id = process_connections[process_id]
                if connection_id not in snapshots:
                    snapshots[connection_id] = await self.access.prepare_in_transaction(
                        session, actor, project, connection_id, configuration.revision, session_hash
                    )
                snapshot = snapshots[connection_id]
                path = process["log_source"]["active_path"]
                root = next(
                    (
                        root
                        for root in snapshot.roots
                        if PurePosixPath(path).is_relative_to(PurePosixPath(root))
                    ),
                    None,
                )
                if root is None:
                    raise DomainError(
                        "ACCESS_DENIED", "The active source lies outside approved roots.", 403
                    )
                sources.append(
                    LiveSource(
                        project_id=project,
                        owner_user_id=actor.user_id,
                        process_id=process_id,
                        config_revision=configuration.revision,
                        access_signature=snapshot.signature,
                        remote_path=path,
                        root=root,
                        target=snapshot.target,
                        jump=snapshot.jump,
                        parser=ParserConfig(
                            **parsers[process["log_source"]["parser_id"]]["timestamp"]
                        ),
                        encoding=process["log_source"]["encoding"],
                        server_id=server["id"],
                        process_name=process["name"],
                        server_name=server["name"],
                        allow_loopback=self.config.ssh_allow_loopback,
                    )
                )
            row = LiveSession(
                project_id=project,
                id=identifier,
                workspace_id=workspace.id,
                owner_user_id=actor.user_id,
                auth_version=actor.auth_version,
                auth_session_hash=session_hash,
                config_revision=configuration.revision,
                config_snapshot=document,
                process_ids=payload.process_ids,
                lease_revision=1,
                filter_version=1,
                status="starting",
                view=LiveViewInput.model_validate(
                    {key: getattr(payload, key) for key in LiveViewInput.model_fields}
                ).model_dump(),
                recording=False,
                investigation_id=None,
                created_us=services.utc_now_us(),
                detached_until_us=None,
                error_code=None,
            )
            session.add(row)
            await session.flush()
            session.add_all(
                [
                    LiveSubscription(
                        project_id=project,
                        session_id=identifier,
                        owner_user_id=actor.user_id,
                        process_id=p,
                        process_kind="process",
                    )
                    for p in payload.process_ids
                ]
            )
            services.audit(
                session, actor, "live.create", project, identifier, services.utc_now_us()
            )
            revision = row.config_revision
        try:
            await self.engine.start(
                identifier,
                sources,
                payload.requested_rows,
                payload.global_filter.predicate(),
                {key: value.predicate() for key, value in payload.per_process_filters.items()},
                payload.layout,
                guard=lambda: self._guard(
                    actor, project, identifier, snapshots, revision, session_hash
                ),
                on_events=self.record_events,
                seed_rows_by_process=payload.seed_rows_by_process,
                recording_enabled=False,
            )
            async with self._use_session(identifier):
                async with self.sessions.begin() as session:
                    row = await session.get(
                        LiveSession, (project, identifier), with_for_update=True
                    )
                    starting = row is not None and row.status == "starting"
                    if starting:
                        row.status = "following"
                if not starting:
                    await self.engine.stop(identifier)
                    raise DomainError("CANCELLED", "This monitor was stopped during startup.", 409)
            if payload.recording:
                await self.save(
                    actor,
                    project,
                    identifier,
                    LiveControlInput(workspace_id=payload.workspace_id, lease_revision=1),
                    cookie,
                )
            return await self.get(actor, project, identifier, cookie)
        except BaseException:
            async with self._use_session(identifier):
                async with self.sessions.begin() as session:
                    row = await session.get(
                        LiveSession, (project, identifier), with_for_update=True
                    )
                    active = row is not None and row.status in ACTIVE
                if active:
                    await self._terminate(project, identifier, "failed", "START_FAILED")
                else:
                    # A concurrent explicit control or failed recording owns
                    # the durable terminal outcome; only release stale capture.
                    await self.engine.stop(identifier)
            raise

    async def usage(
        self, session: Any, actor: Principal, project: str, workspace: str | None = None
    ) -> dict:
        # current_actor's singleton security lock serializes quota reservation.
        limits = self.config.history_limits
        global_limit = limits.get("max_live_processes_global", 10)
        user_limit = min(global_limit, limits.get("max_live_processes_per_user", 10))
        ceilings = dict(
            global_=global_limit,
            user=user_limit,
            project=min(global_limit, limits.get("max_live_processes_per_project", 10)),
            workspace=min(user_limit, limits.get("max_live_processes_per_workspace", 5)),
        )
        base = select(func.count()).select_from(LiveSubscription)
        counts = dict(
            global_=int(await session.scalar(base) or 0),
            user=int(
                await session.scalar(base.where(LiveSubscription.owner_user_id == actor.user_id))
                or 0
            ),
            project=int(
                await session.scalar(base.where(LiveSubscription.project_id == project)) or 0
            ),
        )
        counts["workspace"] = int(
            await session.scalar(
                base.join(
                    LiveSession,
                    (LiveSubscription.project_id == LiveSession.project_id)
                    & (LiveSubscription.session_id == LiveSession.id),
                ).where(
                    LiveSession.project_id == project,
                    LiveSession.workspace_id == workspace,
                    LiveSession.owner_user_id == actor.user_id,
                )
            )
            or 0
        )
        return {
            "project_id": project,
            "workspace_id": workspace,
            "counts": counts,
            "limits": ceilings,
        }

    async def get(self, actor: Principal, project: str, identifier: str, cookie: str) -> dict:
        async with self.sessions.begin() as session:
            actor = await self._principal(session, cookie)
            row = await self._row(session, actor, project, identifier)
            workspace = await session.get(Workspace, (project, row.workspace_id))
            return self.response(row, workspace)

    async def listing(self, actor: Principal, project: str, cookie: str) -> dict:
        async with self.sessions.begin() as session:
            actor = await self._principal(session, cookie)
            await services.project_in_context(session, ProjectContext(project, actor.user_id))
            rows = (
                await session.scalars(
                    select(LiveSession)
                    .where(
                        LiveSession.project_id == project,
                        LiveSession.owner_user_id == actor.user_id,
                    )
                    .order_by(LiveSession.created_us.desc())
                    .limit(100)
                )
            ).all()
            return {
                "project_id": project,
                "items": [
                    self.response(row, await session.get(Workspace, (project, row.workspace_id)))
                    for row in rows
                ],
            }

    async def filters(
        self, actor: Principal, project: str, identifier: str, payload: LiveFilterInput, cookie: str
    ) -> dict:
        async with self._use_session(identifier):
            async with self.sessions.begin() as session:
                actor = await self._principal(session, cookie)
                row = await self._row(
                    session, actor, project, identifier, action="live.filter", control=payload
                )
                if row.status not in ACTIVE or identifier not in self.engine.sessions:
                    raise DomainError(
                        "RESYNC_REQUIRED", "Start a new monitor after interruption.", 409
                    )
                if row.filter_version != payload.expected_filter_version:
                    raise DomainError(
                        "REVISION_CONFLICT", "Filters changed; reload this monitor.", 409
                    )
                if not set(payload.per_process_filters) <= set(row.process_ids):
                    raise DomainError(
                        "INVALID_REQUEST", "Per-process filters must belong to this monitor.", 422
                    )
                if not set(payload.seed_rows_by_process) <= set(row.process_ids):
                    raise DomainError(
                        "INVALID_REQUEST",
                        "Per-process seed requests must belong to this monitor.",
                        422,
                    )
                row.view = {key: payload.model_dump()[key] for key in LiveViewInput.model_fields}
                row.filter_version += 1
            state = self.engine.sessions[identifier]
            state.requested_rows = payload.requested_rows
            state.mode = payload.layout
            state.rows_by_process = payload.seed_rows_by_process
            await self.engine.refilter(
                identifier,
                payload.global_filter.predicate(),
                {key: value.predicate() for key, value in payload.per_process_filters.items()},
            )
        return await self.get(actor, project, identifier, cookie)

    async def history_rows(
        self,
        actor: Principal,
        project: str,
        identifier: str,
        control: LiveHistoryInput,
        cookie: str,
    ) -> dict:
        async with self._use_session(identifier):
            return await self._history_rows(actor, project, identifier, control, cookie)

    async def _history_rows(
        self,
        actor: Principal,
        project: str,
        identifier: str,
        control: LiveHistoryInput,
        cookie: str,
    ) -> dict:
        async with self.sessions.begin() as session:
            actor = await self._principal(session, cookie)
            row = await self._row(
                session, actor, project, identifier, action="live.history", control=control
            )
            if row.status not in ACTIVE or identifier not in self.engine.sessions:
                raise DomainError(
                    "RESYNC_REQUIRED", "This monitor has no active retained history.", 409
                )
            rows = control.requested_rows or row.view["requested_rows"]
        await self.engine.load_older(identifier, rows)
        return await self.get(actor, project, identifier, cookie)

    async def attach(
        self, actor: Principal, project: str, identifier: str, payload: LiveAttachInput, cookie: str
    ) -> dict:
        async with self._use_session(identifier):
            async with self.sessions.begin() as session:
                actor = await self._principal(session, cookie)
                row = await self._row(
                    session, actor, project, identifier, action="workspace.attach"
                )
                workspace = await self._workspace(session, actor, project, payload.workspace_id)
                previous = await session.get(Workspace, (project, row.workspace_id))
                if row.lease_revision != payload.expected_lease_revision:
                    raise DomainError("REVISION_CONFLICT", "The control lease changed.", 409)
                detached = (
                    row.detached_until_us is not None
                    or previous.state != "active"
                    or previous.expires_us <= services.utc_now_us()
                )
                if not detached or workspace.state != "active":
                    raise DomainError(
                        "WORKSPACE_IN_USE", "This monitor still has an active controller.", 409
                    )
                if identifier not in self.engine.sessions or row.status not in ACTIVE:
                    raise DomainError(
                        "RESYNC_REQUIRED",
                        "Backend interruption requires an explicit new monitor.",
                        409,
                    )
                usage = await self.usage(session, actor, project, payload.workspace_id)
                additional = len(row.process_ids) if row.workspace_id != payload.workspace_id else 0
                if usage["counts"]["workspace"] + additional > usage["limits"]["workspace"]:
                    raise DomainError(
                        "LIMIT_REACHED",
                        "The target workspace has no free live subscription capacity.",
                        429,
                    )
                if (
                    row.detached_until_us is not None
                    and row.detached_until_us <= services.utc_now_us()
                ):
                    raise DomainError(
                        "RESYNC_REQUIRED", "The reconnect lease expired; start a new monitor.", 409
                    )
                row.workspace_id = workspace.id
                row.lease_revision += 1
                row.detached_until_us = None
                services.audit(
                    session, actor, "workspace.attach", project, identifier, services.utc_now_us()
                )
            # Old socket checks the persisted lease before any further dispatch.
        return await self.get(actor, project, identifier, cookie)

    async def stop(
        self,
        actor: Principal,
        project: str,
        identifier: str,
        control: LiveControlInput,
        cookie: str,
    ) -> dict:
        async with self._use_session(identifier):
            return await self._stop(actor, project, identifier, control, cookie)

    async def _stop(
        self,
        actor: Principal,
        project: str,
        identifier: str,
        control: LiveControlInput,
        cookie: str,
    ) -> dict:
        async with self.sessions.begin() as session:
            actor = await self._principal(session, cookie)
            row = await self._row(
                session, actor, project, identifier, action="live.stop", control=control
            )
            own = row.owner_user_id == actor.user_id
            services.audit(session, actor, "live.stop", project, identifier, services.utc_now_us())
        await self._terminate(project, identifier, "stopped", None)
        # The operational exception returns no content or filter metadata.
        return (
            await self.get(actor, project, identifier, cookie)
            if own
            else {"project_id": project, "session_id": identifier, "status": "stopped"}
        )

    async def _terminate(
        self, project: str, identifier: str, status: str, error: str | None
    ) -> None:
        await self.engine.stop(identifier)
        async with self.sessions.begin() as session:
            row = await session.get(LiveSession, (project, identifier), with_for_update=True)
            if row:
                row.status, row.error_code = status, error
                await session.execute(
                    delete(LiveSubscription).where(
                        LiveSubscription.project_id == project,
                        LiveSubscription.session_id == identifier,
                    )
                )
                if row.investigation_id:
                    job = await session.get(
                        HistoryJob, (project, row.investigation_id), with_for_update=True
                    )
                    if job:
                        job.status = (
                            "cancelled"
                            if job.status == "cancel_requested"
                            else "partial"
                            if job.status == "collecting"
                            else job.status
                        )
                        job.errors = list(
                            dict.fromkeys(
                                [*job.errors, "LIVE_RETAINED_RANGES", *([error] if error else [])]
                            )
                        )
                        sources = (
                            await session.scalars(
                                select(HistorySource).where(
                                    HistorySource.project_id == project,
                                    HistorySource.job_id == job.id,
                                )
                            )
                        ).all()
                        for source in sources:
                            source.status = "partial"

    async def save(
        self,
        actor: Principal,
        project: str,
        identifier: str,
        control: LiveControlInput,
        cookie: str,
    ) -> dict:
        operation = asyncio.create_task(self._save(actor, project, identifier, control, cookie))
        try:
            return await asyncio.shield(operation)
        except asyncio.CancelledError:
            # A disconnected HTTP caller cannot interrupt commit between the
            # durable activation and its in-memory flag/exact-byte backfill.
            while not operation.done():
                try:
                    await asyncio.shield(operation)
                except asyncio.CancelledError:
                    continue
                except BaseException:
                    break
            try:
                operation.result()
            except BaseException:
                pass  # The worker already settled failure into visible partial state.
            raise

    async def _save(
        self,
        actor: Principal,
        project: str,
        identifier: str,
        control: LiveControlInput,
        cookie: str,
    ) -> dict:
        async with self._use_session(identifier):
            owned_activation = False
            try:
                async with self.sessions.begin() as session:
                    actor = await self._principal(session, cookie)
                    row = await self._row(
                        session, actor, project, identifier, action="live.save", control=control
                    )
                    if row.status not in ACTIVE or identifier not in self.engine.sessions:
                        raise DomainError(
                            "RESYNC_REQUIRED", "Record an active monitor before stopping.", 409
                        )
                    owned_activation = True
                    if not row.recording:
                        job_id = str(uuid4())
                        session.add(
                            HistoryJob(
                                project_id=project,
                                id=job_id,
                                workspace_id=row.workspace_id,
                                owner_user_id=row.owner_user_id,
                                auth_version=row.auth_version,
                                auth_session_hash=row.auth_session_hash,
                                config_revision=row.config_revision,
                                config_snapshot=row.config_snapshot,
                                process_ids=row.process_ids,
                                from_us=services.utc_now_us(),
                                to_us=services.utc_now_us() + 1,
                                status="collecting",
                                snapshot_revision=0,
                                event_count=0,
                                parse_issue_count=0,
                                downloaded_bytes=0,
                                expanded_bytes=0,
                                created_us=services.utc_now_us(),
                                errors=["LIVE_RETAINED_RANGES"],
                            )
                        )
                        await session.flush()
                        row.recording, row.investigation_id = True, job_id
                        services.audit(
                            session, actor, "live.save", project, identifier, services.utc_now_us()
                        )
                # Save holds the same lock as recording callbacks. Enable only
                # after commit, then settle retained backfill before releasing it.
                self.engine.sessions[identifier].recording_enabled = True
                await self._record_events(identifier, self.engine.retained_events(identifier))
            except BaseException as error:
                if owned_activation:
                    code = error.code if isinstance(error, DomainError) else "RECORDING_FAILED"
                    try:
                        await self._terminate(project, identifier, "failed", code)
                    except BaseException as cleanup_error:
                        _LOGGER.warning(
                            "Live recording failure cleanup could not persist: error=%s",
                            type(cleanup_error).__name__,
                        )
                raise
        return await self.get(actor, project, identifier, cookie)

    async def record_events(self, identifier: str, events: list[dict]) -> None:
        async with self._use_session(identifier):
            await self._record_events(identifier, events)

    async def _record_events(self, identifier: str, events: list[dict]) -> None:
        written: list[tuple[Path, int]] = []
        try:
            await self._record_events_transaction(identifier, events, written)
        except BaseException:
            for path, size in reversed(written):
                await _file_work(_restore_recording, path, size)
            raise

    async def _record_events_transaction(
        self, identifier: str, events: list[dict], written: list[tuple[Path, int]]
    ) -> None:
        if not events:
            return
        project = events[0]["project_id"]
        async with self.sessions.begin() as session:
            row = await session.get(LiveSession, (project, identifier), with_for_update=True)
            if not row or not row.recording or not row.investigation_id:
                return
            job = await session.get(
                HistoryJob, (project, row.investigation_id), with_for_update=True
            )
            if not job or job.status != "collecting":
                raise DomainError("RECORDING_STOPPED", "Recording is no longer active.", 409)
            for offset in range(0, len(events), 500):
                batch = events[offset : offset + 500]
                from inspector.persistence.models import HistoryEvent

                present = set(
                    (
                        await session.scalars(
                            select(HistoryEvent.event_id).where(
                                HistoryEvent.project_id == project,
                                HistoryEvent.job_id == job.id,
                                HistoryEvent.event_id.in_([event["event_id"] for event in batch]),
                            )
                        )
                    ).all()
                )
                groups: dict[str, list[dict]] = defaultdict(list)
                for event in batch:
                    if event["project_id"] != project or event["process_id"] not in row.process_ids:
                        raise missing()
                    if event["event_id"] not in present:
                        groups[event["source"]["source_revision_id"]].append(event)
                for source_id, members in groups.items():
                    if any(event["parse_status"] == "oversized_line" for event in members):
                        raise DomainError(
                            "RECORDING_LINE_LIMIT",
                            "An oversized line cannot be recorded as a complete source range.",
                            413,
                        )
                    source = await session.get(HistorySource, (project, job.id, source_id))
                    if source is None:
                        source = HistorySource(
                            project_id=project,
                            job_id=job.id,
                            id=source_id,
                            process_id=members[0]["process_id"],
                            process_kind="process",
                            remote_path=members[0]["source"]["remote_path"],
                            kind="plain",
                            cache_name=str(uuid4()),
                            checksum=None,
                            status="collecting",
                            error_code=None,
                            event_count=0,
                            downloaded_bytes=0,
                            expanded_bytes=0,
                            manifest={
                                "transport": "live_sftp",
                                "captured_ranges": [],
                                "partial": True,
                            },
                        )
                        session.add(source)
                        await session.flush()
                    raw = [event["_raw_bytes"] for event in members]
                    count = sum(len(value) for value in raw)
                    if job.event_count + len(members) > 200_000:
                        raise DomainError(
                            "RECORDING_LIMIT",
                            "Recording reached its 200000-event cap; capture stopped visibly.",
                            413,
                        )
                    if job.downloaded_bytes + count > self.config.history_limits.get(
                        "max_download_bytes_per_collection", 536_870_912
                    ):
                        raise DomainError(
                            "RECORDING_LIMIT",
                            "Recording byte budget reached; capture stopped visibly.",
                            413,
                        )
                    path = self.history.cache_path(project, job.id, source.cache_name)
                    written.append((path, source.downloaded_bytes))
                    await _file_work(_append_recording, path, raw, source.downloaded_bytes)
                    ranges = list(source.manifest["captured_ranges"])
                    local_offset = source.downloaded_bytes
                    for event, value in zip(members, raw, strict=True):
                        captured_range = {
                            "byte_start": event["source"]["byte_start"],
                            "byte_end": event["source"]["byte_end"],
                            "cache_start": local_offset,
                            "cache_end": local_offset + len(value),
                        }
                        if (
                            ranges
                            and ranges[-1]["byte_end"] == captured_range["byte_start"]
                            and ranges[-1]["cache_end"] == captured_range["cache_start"]
                        ):
                            ranges[-1] = {
                                **ranges[-1],
                                "byte_end": captured_range["byte_end"],
                                "cache_end": captured_range["cache_end"],
                            }
                        else:
                            ranges.append(captured_range)
                        local_offset += len(value)
                    # Bounded by the recording byte limit and physical-line minimum.
                    source.manifest = {**source.manifest, "captured_ranges": ranges}
                    source.downloaded_bytes += count
                    source.expanded_bytes += count
                    job.downloaded_bytes += count
                    job.expanded_bytes += count
                    times = [
                        event["timestamp_us"]
                        for event in members
                        if event["timestamp_us"] is not None
                    ]
                    if times:
                        job.from_us = min(job.from_us, min(times))
                        job.to_us = max(job.to_us, max(times) + 1)
                    await persist_event_batch(session, job, source, members)

    async def _maintain(self) -> None:
        expected = time.monotonic()
        while not self.closed:
            lag = time.monotonic() - expected
            if lag > 0.1:
                _LOGGER.warning("Live event-loop scheduling delay: seconds=%.3f", lag)
            try:
                async with self.sessions.begin() as session:
                    rows = (
                        await session.scalars(
                            select(LiveSession).where(LiveSession.status.in_(ACTIVE))
                        )
                    ).all()
                    terminate: list[tuple[str, str, str, str | None]] = []
                    now = services.utc_now_us()
                    for row in rows:
                        workspace = await session.get(Workspace, (row.project_id, row.workspace_id))
                        if (
                            workspace.state != "active" or workspace.expires_us <= now
                        ) and row.detached_until_us is None:
                            terminate.append((row.project_id, row.id, "detach", None))
                        if row.detached_until_us is not None and row.detached_until_us <= now:
                            terminate.append((row.project_id, row.id, "stopped", "LEASE_EXPIRED"))
                        elif row.id in self.engine.sessions:
                            state = self.engine.sessions[row.id]
                            if getattr(state, "stopped", False):
                                terminate.append(
                                    (
                                        row.project_id,
                                        row.id,
                                        "interrupted",
                                        state.error or "SOURCE_STOPPED",
                                    )
                                )
                for args in terminate:
                    await self._apply_maintenance(*args)
            except (SQLAlchemyError, TimeoutError, DomainError):
                self.failed_closed = True
                await self.engine.close()
            expected = time.monotonic() + 0.5
            await asyncio.sleep(0.5)

    async def _apply_maintenance(
        self, project: str, identifier: str, status: str, error: str | None
    ) -> None:
        """Apply a collected intent only while its current control state permits it.

        Explicit Stop holds this same lock across engine closure and the durable
        terminal update. A maintenance scan can observe that intermediate
        engine state, but must never overwrite the completed control afterward.
        """
        async with self._use_session(identifier):
            async with self.sessions.begin() as session:
                row = await session.get(LiveSession, (project, identifier), with_for_update=True)
                if row is None or row.status not in ACTIVE:
                    return
                if status == "detach":
                    workspace = await session.get(Workspace, (project, row.workspace_id))
                    if row.detached_until_us is None and (
                        workspace is None
                        or workspace.state != "active"
                        or workspace.expires_us <= services.utc_now_us()
                    ):
                        row.detached_until_us = services.utc_now_us() + self.lease_us
                    return
                if error == "LEASE_EXPIRED":
                    if (
                        row.detached_until_us is None
                        or row.detached_until_us > services.utc_now_us()
                    ):
                        return
                else:
                    state = self.engine.sessions.get(identifier)
                    if state is None or not state.stopped:
                        return
                    error = state.error or "SOURCE_STOPPED"
            await self._terminate(project, identifier, status, error)

    async def disconnected(self, project: str, identifier: str, workspace: str, lease: int) -> None:
        try:
            async with self.sessions.begin() as session:
                row = await session.get(LiveSession, (project, identifier), with_for_update=True)
                if (
                    row
                    and row.workspace_id == workspace
                    and row.lease_revision == lease
                    and row.status in ACTIVE
                ):
                    row.detached_until_us = services.utc_now_us() + self.lease_us
        except SQLAlchemyError:
            self.failed_closed = True
            await self.engine.close()

    async def close(self) -> None:
        self.closed = True
        self.maintenance.cancel()
        await asyncio.gather(self.maintenance, return_exceptions=True)
        await self.engine.close()
        guards = tuple(self.guard_tasks.values())
        for task in guards:
            task.cancel()
        await asyncio.gather(*guards, return_exceptions=True)
        self.guard_tasks.clear()
        await asyncio.gather(
            *(_close_socket(socket, 1012) for socket in tuple(self.sockets.values()))
        )


async def _close_socket(socket: WebSocket, code: int) -> None:
    try:
        async with asyncio.timeout(0.25):
            await socket.close(code=code)
    except (RuntimeError, TimeoutError):
        pass


async def _audit_socket_denial(manager: Any, actor: Principal | None, identifier: str) -> None:
    # Never delay fail-closed socket shutdown or retain rejected frame contents.
    try:
        async with asyncio.timeout(0.25):
            async with manager.sessions.begin() as session:
                session.add(
                    Audit(
                        id=str(uuid4()),
                        actor_user_id=actor.user_id if actor else None,
                        actor_role=actor.role if actor else None,
                        action="authorization.denied",
                        project_id=None,
                        target_id=identifier if re.fullmatch(ID_PATTERN, identifier) else None,
                        created_us=services.utc_now_us(),
                        outcome="denied",
                    )
                )
    except (SQLAlchemyError, TimeoutError):
        pass


async def _file_work(operation: Any, *args: Any) -> Any:
    task = asyncio.create_task(asyncio.to_thread(operation, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        task.result()
        raise


def _restore_recording(path: Path, size: int) -> None:
    import stat

    from inspector.history_retention import checked_stat

    try:
        if not stat.S_ISREG(checked_stat(path).st_mode):
            raise DomainError("CACHE_UNSAFE", "Recording cache is unavailable.", 503)
    except FileNotFoundError:
        return
    with path.open("r+b") as stream:
        stream.truncate(size)
        stream.flush()
        os.fsync(stream.fileno())


def _append_recording(path: Path, blocks: list[bytes], expected_size: int) -> None:
    import stat

    from inspector.history_retention import checked_directory, checked_stat

    checked_directory(path.parent, path.parents[3])
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not checked_directory(path.parent, path.parents[3]):
        raise DomainError("CACHE_UNSAFE", "Recording cache is unavailable.", 503)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    try:
        if not stat.S_ISREG(checked_stat(path).st_mode):
            raise DomainError("CACHE_UNSAFE", "Recording cache is unavailable.", 503)
    except FileNotFoundError:
        pass
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "ab") as stream:
        if os.fstat(stream.fileno()).st_size != expected_size:
            raise DomainError("CACHE_CHANGED", "Recording cache size changed unexpectedly.", 409)
        for block in blocks:
            stream.write(block)
        stream.flush()
        os.fsync(stream.fileno())


def build_live_router(transaction: Any, authenticated: Any, protected_write: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["live"])
    Session = Annotated[Any, Depends(transaction, scope="function")]
    Actor = Annotated[Principal, Depends(authenticated)]
    Writer = Annotated[Principal, Depends(protected_write)]

    async def invoke(
        request: Request, session: Any, method: str, actor: Principal, project: str, *args: Any
    ) -> Any:
        await session.commit()
        return await getattr(request.app.state.live, method)(
            actor, project, *args, request.cookies.get("__Host-si-session", "")
        )

    @router.post(
        "/live-sessions",
        response_model=LiveSessionResponse,
        status_code=202,
        openapi_extra={"x-permission": "live.create"},
    )
    async def create(
        project_id: str, payload: LiveCreateInput, request: Request, session: Session, actor: Writer
    ) -> dict:
        return await invoke(request, session, "create", actor, project_id, payload)

    @router.get(
        "/live-sessions",
        response_model=LiveListResponse,
        openapi_extra={"x-permission": "live.read"},
    )
    async def listing(project_id: str, request: Request, session: Session, actor: Actor) -> dict:
        return await invoke(request, session, "listing", actor, project_id)

    @router.get(
        "/live-sessions/{identifier}",
        response_model=LiveSessionResponse,
        openapi_extra={"x-permission": "live.read"},
    )
    async def get(
        project_id: str, identifier: str, request: Request, session: Session, actor: Actor
    ) -> dict:
        return await invoke(request, session, "get", actor, project_id, identifier)

    @router.put(
        "/live-sessions/{identifier}/filters",
        response_model=LiveSessionResponse,
        openapi_extra={"x-permission": "live.filter"},
    )
    async def filters(
        project_id: str,
        identifier: str,
        payload: LiveFilterInput,
        request: Request,
        session: Session,
        actor: Writer,
    ) -> dict:
        return await invoke(request, session, "filters", actor, project_id, identifier, payload)

    @router.post(
        "/live-sessions/{identifier}/history",
        response_model=LiveSessionResponse,
        openapi_extra={"x-permission": "live.history"},
    )
    async def history_rows(
        project_id: str,
        identifier: str,
        payload: LiveHistoryInput,
        request: Request,
        session: Session,
        actor: Writer,
    ) -> dict:
        return await invoke(
            request, session, "history_rows", actor, project_id, identifier, payload
        )

    @router.post(
        "/live-sessions/{identifier}/save",
        response_model=LiveSessionResponse,
        openapi_extra={"x-permission": "live.save"},
    )
    async def save(
        project_id: str,
        identifier: str,
        payload: LiveControlInput,
        request: Request,
        session: Session,
        actor: Writer,
    ) -> dict:
        return await invoke(request, session, "save", actor, project_id, identifier, payload)

    @router.post(
        "/live-sessions/{identifier}/attach",
        response_model=LiveSessionResponse,
        openapi_extra={"x-permission": "workspace.attach"},
    )
    async def attach(
        project_id: str,
        identifier: str,
        payload: LiveAttachInput,
        request: Request,
        session: Session,
        actor: Writer,
    ) -> dict:
        return await invoke(request, session, "attach", actor, project_id, identifier, payload)

    @router.post("/live-sessions/{identifier}/stop", openapi_extra={"x-permission": "live.stop"})
    async def stop(
        project_id: str,
        identifier: str,
        payload: LiveControlInput,
        request: Request,
        session: Session,
        actor: Writer,
    ) -> dict:
        return await invoke(request, session, "stop", actor, project_id, identifier, payload)

    @router.get(
        "/usage", response_model=LiveUsageResponse, openapi_extra={"x-permission": "live.read"}
    )
    async def usage(
        project_id: str,
        request: Request,
        session: Session,
        actor: Actor,
        workspace_id: str | None = None,
    ) -> dict:
        actor = await services.current_actor(session, actor)
        await services.project_in_context(session, ProjectContext(project_id, actor.user_id))
        if workspace_id:
            await request.app.state.live._workspace(session, actor, project_id, workspace_id)
        return await request.app.state.live.usage(session, actor, project_id, workspace_id)

    @router.websocket("/live-sessions/{identifier}/stream")
    async def stream(socket: WebSocket, project_id: str, identifier: str) -> None:
        await live_stream(socket, project_id, identifier)

    return router


async def _wait_live_input(incoming: asyncio.Task[str], changed: asyncio.Event) -> bool:
    """Wake for output without cancelling the socket's one pending ACK read."""
    notification = asyncio.create_task(changed.wait())
    try:
        await asyncio.wait(
            (incoming, notification), timeout=0.25, return_when=asyncio.FIRST_COMPLETED
        )
        return incoming.done()
    finally:
        notification.cancel()
        await asyncio.gather(notification, return_exceptions=True)


async def live_stream(socket: WebSocket, project: str, identifier: str) -> None:
    manager: LiveManager = socket.app.state.live
    cookie = socket.cookies.get("__Host-si-session", "")
    control = None
    registered = False
    actor: Principal | None = None
    incoming: asyncio.Task[str] | None = None
    try:
        if (
            socket.headers.get("origin") != manager.config.public_origin
            or socket.headers.get("host", "").lower()
            != urlsplit(manager.config.public_origin).netloc.lower()
        ):
            await socket.close(code=4403)
            await _audit_socket_denial(manager, actor, identifier)
            return
        async with asyncio.timeout(1):
            async with manager.sessions.begin() as session:
                actor = await manager._principal(session, cookie)
                await manager._row(session, actor, project, identifier)
        await socket.accept()
        async with asyncio.timeout(5):
            data = await socket.receive_text()
            if len(data.encode("utf-8")) > 16_384:
                raise ValueError
            hello = ClientFrame.model_validate_json(data)
            proof = HelloInput.model_validate(hello.payload)
            if hello.type != "hello" or (hello.project_id, hello.session_id) != (
                project,
                identifier,
            ):
                raise ValueError
        control = LiveControlInput(
            workspace_id=hello.workspace_id, lease_revision=proof.lease_revision
        )
        async with asyncio.timeout(1):
            async with manager.sessions.begin() as session:
                actor = await manager._principal(session, cookie)
                await auth.verify_csrf(session, cookie, proof.csrf_token)
                reconnecting = await manager._row(session, actor, project, identifier)
                if (reconnecting.workspace_id, reconnecting.lease_revision) == (
                    control.workspace_id,
                    control.lease_revision,
                ) and identifier not in manager.sockets:
                    if (
                        reconnecting.detached_until_us is not None
                        and reconnecting.detached_until_us <= services.utc_now_us()
                    ):
                        raise DomainError("RESYNC_REQUIRED", "The reconnect lease expired.", 409)
                    reconnecting.detached_until_us = None
                    await session.flush()
                row = await manager._row(session, actor, project, identifier, control=control)
                if row.status not in ACTIVE or identifier not in manager.engine.sessions:
                    raise DomainError("RESYNC_REQUIRED", "This monitor was interrupted.", 409)
                if hello.filter_version != row.filter_version:
                    raise DomainError("RESYNC_REQUIRED", "Reload current filter state.", 409)
                if identifier in manager.sockets:
                    raise DomainError(
                        "WORKSPACE_IN_USE", "This monitor already has an active socket.", 409
                    )
                manager.sockets[identifier] = socket
                registered = True
        last_seq = proof.last_seq
        last_version = hello.filter_version
        incoming_times: deque[float] = deque()
        acknowledged = last_seq or 0
        fresh = True
        frames: list[dict[str, Any]]
        incoming = asyncio.create_task(socket.receive_text())
        while True:
            async with asyncio.timeout(1):
                await manager.access._healthy()
                async with manager.sessions.begin() as session:
                    actor, row = await manager._socket_row(
                        session, cookie, project, identifier, control, renew_workspace=True
                    )
                    version, status = row.filter_version, row.status
            if status not in ACTIVE:
                state = manager.engine.sessions.get(identifier)
                stopped_seq = max((state.seq if state is not None else 0), (last_seq or 0) + 1)
                async with asyncio.timeout(1):
                    terminal = LiveFrame(
                        type="stopped",
                        project_id=project,
                        workspace_id=control.workspace_id,
                        session_id=identifier,
                        filter_version=version,
                        seq=stopped_seq,
                        sent_at=format_time(services.utc_now_us()),
                        payload={"reason": status},
                    )
                    await socket.send_text(terminal.model_dump_json())
                    await socket.close(code=1000)
                break
            state = manager.engine.sessions[identifier]
            # There is no await between clearing this notification and peeking
            # replay. Any later frame sets it again while authorization/sends run.
            state.changed.clear()
            coherent = state.filter_version == version
            if not coherent:
                # HTTP commits the new version before the awaited engine
                # refilter. Never label the previous view with that new version.
                # Keep the ordinary input/watchdog path while waiting for its
                # changed notification, preserving ACK validation and cursors.
                frames = []
            elif fresh or version != last_version:
                replay = (
                    manager.engine.frames_since(identifier, last_seq, version)
                    if last_seq is not None and version == last_version
                    else None
                )
                if replay is None:
                    snap = manager.engine.snapshot(identifier)
                    seq = int(snap.get("seq", 0))
                    frames = [
                        {
                            "type": "snapshot",
                            "payload": {
                                key: value
                                for key, value in snap.items()
                                if key in LiveSnapshot.model_fields
                            },
                            "seq": seq,
                            "filter_version": version,
                        }
                    ]
                else:
                    frames = replay
                fresh = False
            else:
                frames = manager.engine.frames_since(identifier, last_seq or 0, version)
                if frames is None:
                    snap = manager.engine.snapshot(identifier)
                    frames = [
                        {
                            "type": "resync_required",
                            "payload": {"reason": "REPLAY_EXPIRED"},
                            "seq": int(snap.get("seq", 0)),
                            "filter_version": version,
                        },
                        {
                            "type": "snapshot",
                            "payload": snap,
                            "seq": int(snap.get("seq", 0)),
                            "filter_version": version,
                        },
                    ]
            for frame in frames:
                # Recheck every protected dispatch, including replay after queue waits.
                async with asyncio.timeout(1):
                    async with manager.sessions.begin() as session:
                        actor, current = await manager._socket_row(
                            session, cookie, project, identifier, control
                        )
                        if (
                            current.status not in ACTIVE
                            or current.filter_version != frame["filter_version"]
                        ):
                            break
                    payload = frame["payload"]
                    if frame["type"] == "events":
                        payload = {
                            "items": [
                                {
                                    **{
                                        key: value
                                        for key, value in event.items()
                                        if key != "late_arrival"
                                    },
                                    "metadata": {
                                        **event["metadata"],
                                        "late_arrival": "true"
                                        if event.get("late_arrival")
                                        else "false",
                                    },
                                }
                                for event in payload["events"]
                            ]
                        }
                    envelope = LiveFrame(
                        type=frame["type"],
                        project_id=project,
                        workspace_id=control.workspace_id,
                        session_id=identifier,
                        filter_version=frame["filter_version"],
                        seq=frame["seq"],
                        sent_at=format_time(services.utc_now_us()),
                        payload=payload,
                    )
                    encoded = envelope.model_dump_json()
                    if len(encoded.encode("utf-8")) > manager.config.history_limits.get(
                        "max_ws_frame_bytes", 1_048_576
                    ):
                        raise DomainError(
                            "LIMIT_REACHED", "Live frame exceeds the configured byte limit.", 413
                        )
                    await socket.send_text(encoded)
                last_seq = frame["seq"]
            if coherent:
                last_version = version
            # A single bounded receiver persists across output wakeups. Silent
            # sockets retain the 250ms fresh-authorization watchdog.
            if not await _wait_live_input(incoming, state.changed):
                continue
            data = incoming.result()
            incoming = asyncio.create_task(socket.receive_text())
            now_mono = time.monotonic()
            while incoming_times and incoming_times[0] < now_mono - 1:
                incoming_times.popleft()
            if len(data.encode("utf-8")) > 16_384 or len(incoming_times) >= 100:
                raise ValueError
            incoming_times.append(now_mono)
            client_frame = ClientFrame.model_validate_json(data)
            if (
                client_frame.type,
                client_frame.project_id,
                client_frame.workspace_id,
                client_frame.session_id,
            ) != (
                "ack",
                project,
                control.workspace_id,
                identifier,
            ):
                raise ValueError
            ack = AckInput.model_validate(client_frame.payload)
            async with asyncio.timeout(1):
                async with manager.sessions.begin() as session:
                    actor, latest = await manager._socket_row(
                        session, cookie, project, identifier, control
                    )
                    current_filter = latest.filter_version
            # HTTP resets can commit while compatible old ACKs are queued.
            # They acknowledge an obsolete view and cannot alter the new one.
            if client_frame.filter_version < current_filter:
                continue
            if client_frame.filter_version != current_filter:
                raise ValueError
            if ack.last_seq < acknowledged or ack.last_seq > (last_seq or 0):
                raise ValueError
            acknowledged = ack.last_seq
    except WebSocketDisconnect:
        pass
    except (
        DomainError,
        SQLAlchemyError,
        TimeoutError,
        ValidationError,
        ValueError,
        RuntimeError,
        KeyError,
    ):
        await _close_socket(socket, 4403)
        await _audit_socket_denial(manager, actor, identifier)
    finally:
        if incoming is not None:
            incoming.cancel()
            await asyncio.gather(incoming, return_exceptions=True)
        if registered:
            manager.sockets.pop(identifier, None)
            if control:
                await manager.disconnected(
                    project, identifier, control.workspace_id, control.lease_revision
                )
