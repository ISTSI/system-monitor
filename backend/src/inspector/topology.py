"""Revisioned topology transactions and safe scoped read/import projections.

Configuration addresses and root lists are proposals only. This module creates
no vault bindings, trust records, target approvals, SSH connections or jobs.
"""

import asyncio
import copy
import hashlib
import json
import weakref
from collections.abc import Callable
from typing import Annotated, Any, Literal
from uuid import uuid4

import yaml
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inspector import project_config, services
from inspector.domain import ID_PATTERN, Principal, ProjectContext
from inspector.errors import DomainError
from inspector.persistence.models import (
    ConfigPreview,
    ConnectionProfile,
    DemoSnapshot,
    EntityIdentity,
    EntityNameSnapshot,
    Flow,
    HistoryJob,
    HistorySource,
    ParserProfile,
    Process,
    Project,
    ProjectRevision,
    Server,
    SharedView,
    Subsystem,
    TopologySnapshot,
    TopologyState,
    ViewFlow,
    ViewNode,
)
from inspector.security import authorize

COLLECTIONS = {
    "subsystems": ("subsystem", Subsystem),
    "connections": ("connection", ConnectionProfile),
    "parsers": ("parser", ParserProfile),
    "servers": ("server", Server),
    "processes": ("process", Process),
    "flows": ("flow", Flow),
    "views": ("view", SharedView),
}
PREVIEW_LEASE_US = 900_000_000
HISTORY_LIMIT = 100
_CPU_LIMITS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)


async def cpu_work[Result](operation: Callable[[], Result]) -> Result:
    """Bound config parsing/validation workers, including cancelled requests."""
    loop = asyncio.get_running_loop()
    limit = _CPU_LIMITS.setdefault(loop, asyncio.Semaphore(2))
    async with limit:
        task = asyncio.create_task(asyncio.to_thread(operation))
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


def validated_size(config: dict) -> int:
    project_config.validate_project(config)
    return len(json.dumps(config, ensure_ascii=False, allow_nan=False).encode("utf-8"))


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RevisionInput(StrictInput):
    expected_revision: int = Field(ge=1, le=2_147_483_646)


class TopologyInput(RevisionInput):
    config: dict[str, Any]
    confirmed_deletions: bool = False
    reparent: bool = False


class PreviewInput(RevisionInput):
    content: str = Field(max_length=10_485_760)
    format: Literal["json", "yaml"]


class CommitInput(RevisionInput):
    preview_id: str = Field(pattern=ID_PATTERN)
    confirmed_deletions: bool = False
    reparent: bool = False
    confirm_project_remap: bool = False


class DeleteInput(StrictInput):
    kind: Literal["subsystem", "server", "process", "flow", "connection", "parser", "view"]
    id: str = Field(pattern=ID_PATTERN)


class SearchInput(StrictInput):
    q: str = Field(min_length=1, max_length=256)


class TopologyResponse(StrictInput):
    project_id: str
    revision: int
    archived: bool
    editable: bool
    can_undo: bool
    can_redo: bool
    config: dict[str, Any]


class SearchResult(StrictInput):
    kind: str
    id: str
    name: str
    view_id: str | None


class SearchResponse(StrictInput):
    project_id: str
    results: list[SearchResult]


class ExportResponse(StrictInput):
    project_id: str
    format: Literal["json", "yaml"]
    content: str


class PreviewResponse(StrictInput):
    preview_id: str
    project_id: str
    expected_revision: int
    expires_us: str
    warnings: list[str]
    source_project_id: str
    target_project_id: str
    changes: dict[str, list[dict[str, str]]]
    requires_delete_confirmation: bool
    requires_reparent_confirmation: bool


class DeleteResponse(StrictInput):
    project_id: str
    revision: int
    entities: list[dict[str, str]]
    flows: list[str]
    views: list[str]
    investigations: list[str]
    active_sessions: list[str]


def indexed(config: dict) -> dict[str, tuple[str, dict]]:
    return {
        item["id"]: (kind, item)
        for collection, (kind, _model) in COLLECTIONS.items()
        for item in config[collection]
    }


def canonical_bytes(config: dict) -> bytes:
    return json.dumps(
        config, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def response(project: Project, state: TopologyState, actor: Principal) -> dict:
    config = copy.deepcopy(state.config)
    if actor.role != "administrator":
        # Explicit safe projection; full interchange is never an Inspector response.
        config = {
            "schema_version": config["schema_version"],
            "project": config["project"],
            "subsystems": config["subsystems"],
            "servers": [
                {k: item[k] for k in ("id", "name", "subsystem_id", "description", "tags")}
                for item in config["servers"]
            ],
            "processes": [
                {
                    k: item[k]
                    for k in ("id", "name", "server_id", "pcs_resource_name", "description", "tags")
                }
                for item in config["processes"]
            ],
            "flows": config["flows"],
            "views": config["views"],
        }
    editable = actor.role == "administrator" and not project.archived
    return dict(
        project_id=project.id,
        revision=project.revision,
        archived=project.archived,
        editable=editable,
        can_undo=editable and bool(state.undo_stack),
        can_redo=editable and bool(state.redo_stack),
        config=config,
    )


async def normalize_rows(session: AsyncSession, project_id: str, config: dict) -> None:
    """Replace the constrained current projection in the caller's transaction.

    Immutable identities and snapshots are retained independently. No private or
    historical records reference these replaceable current-layout rows.
    """
    for child_model in (ViewFlow, ViewNode, SharedView, Flow, Process, Server):
        await session.execute(delete(child_model).where(child_model.project_id == project_id))
    await session.execute(
        update(ConnectionProfile)
        .where(ConnectionProfile.project_id == project_id)
        .values(jump_connection_id=None)
    )
    for parent_model in (ParserProfile, ConnectionProfile, Subsystem):
        await session.execute(delete(parent_model).where(parent_model.project_id == project_id))
    for collection, (_kind, model) in COLLECTIONS.items():
        for item in config[collection]:
            fields: dict[str, Any] = dict(
                project_id=project_id,
                id=item["id"],
                name=item["name"],
                name_key=hashlib.sha256(item["name"].casefold().encode("utf-8")).hexdigest(),
                payload=item,
            )
            if collection == "connections":
                fields["jump_connection_id"] = None
            elif collection == "servers":
                fields.update(
                    subsystem_id=item["subsystem_id"], connection_id=item["connection_id"]
                )
            elif collection == "processes":
                fields.update(
                    server_id=item["server_id"], parser_id=item["log_source"]["parser_id"]
                )
            elif collection == "flows":
                fields.update(
                    source_process_id=item["source_process_id"],
                    target_process_id=item["target_process_id"],
                )
            session.add(model(**fields))
        await session.flush()
    for item in config["connections"]:
        if item["jump_connection_id"]:
            await session.execute(
                update(ConnectionProfile)
                .where(
                    ConnectionProfile.project_id == project_id, ConnectionProfile.id == item["id"]
                )
                .values(jump_connection_id=item["jump_connection_id"])
            )
    for view in config["views"]:
        session.add_all(
            [
                ViewNode(
                    project_id=project_id,
                    view_id=view["id"],
                    element_id=node["element_id"],
                    geometry=node,
                )
                for node in view["nodes"]
            ]
        )
        session.add_all(
            [
                ViewFlow(project_id=project_id, view_id=view["id"], flow_id=flow_id)
                for flow_id in view["flow_ids"]
            ]
        )
    await session.flush()


async def sync_identities(
    session: AsyncSession, project_id: str, config: dict, *, allow_restore: bool = False
) -> None:
    identities = {
        row.id: row
        for row in (
            await session.scalars(
                select(EntityIdentity).where(EntityIdentity.project_id == project_id)
            )
        ).all()
    }
    entries = indexed(config)
    for identifier, (kind, item) in entries.items():
        row = identities.get(identifier)
        if row is not None and (row.kind != kind or (row.deleted and not allow_restore)):
            raise DomainError(
                "IMMUTABLE_ID",
                "An existing or deleted identity cannot be reused; use a new ID.",
                422,
            )
        if row is None:
            session.add(
                EntityIdentity(
                    project_id=project_id,
                    id=identifier,
                    kind=kind,
                    name=item["name"],
                    deleted=False,
                )
            )
        else:
            row.name, row.deleted = item["name"], False
    for identifier, row in identities.items():
        if identifier not in entries:
            row.deleted = True
    await session.flush()


async def initialize_document(
    session: AsyncSession, project: Project, config: dict | None = None
) -> TopologyState:
    existing = await session.get(TopologyState, project.id)
    if existing is not None:
        return existing
    value = (
        config
        if config is not None
        else project_config.empty_project(
            project.id, project.name, project.description, project.revision
        )
    )
    await cpu_work(lambda: project_config.validate_project(value))
    state = TopologyState(project_id=project.id, config=value, undo_stack=[], redo_stack=[])
    session.add(state)
    await session.flush()
    await sync_identities(session, project.id, value)
    await normalize_rows(session, project.id, value)
    session.add(TopologySnapshot(project_id=project.id, revision=project.revision, config=value))
    await record_names(session, project.id, project.revision, None, value)
    await session.flush()
    return state


def demo_config(project: Project, payload: dict) -> dict:
    """Upgrade the labelled persisted foundation demo without generating targets."""
    value = project_config.empty_project(
        project.id, project.name, project.description, project.revision
    )
    value["parsers"] = [
        {
            "id": "parser-demo",
            "name": "Synthetic ISO UTC",
            "timestamp": {"kind": "iso8601_prefix", "naive_timezone": "UTC"},
            "correlation_markers": [],
        }
    ]
    nodes = []
    process_ids = []
    for index, part in enumerate(payload["subsystems"]):
        value["subsystems"].append(
            {k: part[k] for k in ("id", "name", "description")} | {"tags": ["synthetic"]}
        )
        nodes.append(
            dict(element_id=part["id"], x=index * 560, y=0, width=520, height=440, collapsed=False)
        )
        for host_index, host in enumerate(part["servers"]):
            connection_id = f"connection-{host['id']}"
            value["connections"].append(
                dict(
                    id=connection_id,
                    name=host["name"],
                    host=f"192.0.2.{20 + index + host_index}",
                    port=22,
                    username="unresolved-log-reader",
                    credential_ref=f"unresolved-{host['id']}",
                    jump_connection_id=None,
                    allowed_log_roots=["/var/log/demo"],
                )
            )
            value["servers"].append(
                {k: host[k] for k in ("id", "name", "description")}
                | dict(subsystem_id=part["id"], connection_id=connection_id, tags=["synthetic"])
            )
            nodes.append(
                dict(
                    element_id=host["id"],
                    x=24,
                    y=60 + host_index * 320,
                    width=470,
                    height=340,
                    collapsed=False,
                )
            )
            for process_index, process in enumerate(host["processes"]):
                value["processes"].append(
                    {k: process[k] for k in ("id", "name", "description")}
                    | dict(
                        server_id=host["id"],
                        pcs_resource_name=None,
                        tags=["synthetic"],
                        log_source=dict(
                            active_path=process.get("log_path") or "/var/log/demo/app.log",
                            rotated_patterns=[],
                            archives=[],
                            parser_id="parser-demo",
                            encoding="utf-8",
                            allow_symlink=False,
                        ),
                    )
                )
                nodes.append(
                    dict(
                        element_id=process["id"],
                        x=24,
                        y=70 + process_index * 100,
                        width=410,
                        height=80,
                        collapsed=False,
                    )
                )
                process_ids.append(process["id"])
    for index, (source, target) in enumerate(zip(process_ids, process_ids[1:], strict=False)):
        value["flows"].append(
            dict(
                id=f"flow-demo-{index}",
                name=f"Documented transfer {index + 1}",
                source_process_id=source,
                target_process_id=target,
                protocol="Documented only",
                description="A possible synthetic transfer; this does not establish causality.",
            )
        )
    value["views"] = [
        dict(
            id="view-overview",
            name="System overview",
            nodes=nodes,
            flow_ids=[item["id"] for item in value["flows"]],
        )
    ]
    return value


async def initialize_legacy_documents(session: AsyncSession) -> None:
    for project in (await session.scalars(select(Project))).all():
        if await session.get(TopologyState, project.id) is None:
            demo = await session.get(DemoSnapshot, project.id)
            await initialize_document(
                session, project, demo_config(project, demo.payload) if demo else None
            )


async def sync_metadata(
    session: AsyncSession, project: Project, *, record_undo: bool = False
) -> None:
    state = await session.get(TopologyState, project.id)
    if state is None:
        await initialize_document(session, project)
        return
    config = copy.deepcopy(state.config)
    config["project"].update(
        name=project.name, description=project.description, revision=project.revision
    )
    await cpu_work(lambda: project_config.validate_project(config))
    if record_undo:
        state.undo_stack = (state.undo_stack + [project.revision - 1])[-HISTORY_LIMIT:]
    state.config = config
    state.redo_stack = []
    await session.flush()
    session.add(TopologySnapshot(project_id=project.id, revision=project.revision, config=config))
    await prune_snapshots(session, project, state)


async def record_names(
    session: AsyncSession, project_id: str, revision: int, old: dict | None, new: dict
) -> None:
    before, after = indexed(old) if old is not None else {}, indexed(new)
    for identifier in before.keys() | after.keys():
        previous = before.get(identifier)
        current = after.get(identifier)
        if (
            previous is not None
            and current is not None
            and previous[1]["name"] == current[1]["name"]
        ):
            continue
        source = current or previous
        assert source is not None
        session.add(
            EntityNameSnapshot(
                project_id=project_id,
                id=identifier,
                revision=revision,
                name=source[1]["name"],
                deleted=current is None,
            )
        )


async def prune_snapshots(session: AsyncSession, project: Project, state: TopologyState) -> None:
    keep = set(state.undo_stack + state.redo_stack + [project.revision])
    await session.execute(
        delete(TopologySnapshot).where(
            TopologySnapshot.project_id == project.id, TopologySnapshot.revision.not_in(keep)
        )
    )


async def context(
    session: AsyncSession, actor: Principal, project_id: str, action: str, *, writable: bool = False
) -> tuple[Principal, Project, TopologyState]:
    actor = await services.current_actor(session, actor)
    authorize(actor, action)
    project = await services.project_in_context(
        session, ProjectContext(project_id, actor.user_id), lock=writable
    )
    if writable and project.archived:
        raise DomainError("PROJECT_ARCHIVED", "Archived system is read-only.", 409)
    state = await session.get(TopologyState, project_id, with_for_update=writable)
    if state is None:
        raise DomainError("NOT_READY", "Topology initialization is required before serving.", 503)
    return actor, project, state


def check_revision(project: Project, expected: int) -> None:
    if project.revision != expected:
        raise DomainError("REVISION_CONFLICT", "System has changed; reload before saving.", 409)


def changes(old: dict, new: dict) -> dict:
    before, after = indexed(old), indexed(new)

    def entry(identifier: str, source: dict) -> dict:
        kind, item = source[identifier]
        return dict(kind=kind, id=identifier, name=item["name"])

    return dict(
        added=[entry(i, after) for i in sorted(after.keys() - before.keys())],
        removed=[entry(i, before) for i in sorted(before.keys() - after.keys())],
        updated=[
            entry(i, after) for i in sorted(after.keys() & before.keys()) if after[i] != before[i]
        ],
    )


def has_reparent(old: dict, new: dict) -> bool:
    for collection, key in (("servers", "subsystem_id"), ("processes", "server_id")):
        before = {item["id"]: item[key] for item in old[collection]}
        if any(
            item["id"] in before and before[item["id"]] != item[key] for item in new[collection]
        ):
            return True
    return False


async def save(
    session: AsyncSession,
    actor: Principal,
    project: Project,
    state: TopologyState,
    config: dict,
    *,
    confirmed_deletions: bool,
    reparent: bool,
    history: Literal["edit", "undo", "redo"] = "edit",
    already_validated: bool = False,
) -> dict:
    if not already_validated:
        await cpu_work(lambda: project_config.validate_project(config))
    if config["project"]["id"] != project.id:
        raise DomainError("PROJECT_MISMATCH", "Route and config project must agree.", 422)
    if history == "edit" and config["project"]["revision"] != project.revision:
        raise DomainError(
            "REVISION_CONFLICT",
            "Configuration export is stale; preview against the current revision.",
            409,
        )
    delta = changes(state.config, config)
    if delta["removed"] and not confirmed_deletions:
        raise DomainError(
            "DELETE_CONFIRMATION_REQUIRED",
            "Preview deletion impact and explicitly confirm affected entities.",
            409,
        )
    if has_reparent(state.config, config) and not reparent:
        raise DomainError(
            "REPARENT_CONFIRMATION_REQUIRED",
            "Moving an existing entity requires explicit reparent confirmation.",
            409,
        )
    await sync_identities(session, project.id, config, allow_restore=history != "edit")
    old_revision = project.revision
    if old_revision >= 2_147_483_646:
        raise DomainError("LIMIT_REACHED", "System revision limit reached.", 409)
    old_config = state.config
    if history == "edit":
        state.undo_stack = (state.undo_stack + [old_revision])[-HISTORY_LIMIT:]
        state.redo_stack = []
    elif history == "undo":
        state.undo_stack = state.undo_stack[:-1]
        state.redo_stack = (state.redo_stack + [old_revision])[-HISTORY_LIMIT:]
    else:
        state.redo_stack = state.redo_stack[:-1]
        state.undo_stack = (state.undo_stack + [old_revision])[-HISTORY_LIMIT:]
    project.revision += 1
    value = copy.deepcopy(config)
    value["project"]["revision"] = project.revision
    project.name, project.description = value["project"]["name"], value["project"]["description"]
    state.config = value
    session.add(
        ProjectRevision(
            project_id=project.id,
            revision=project.revision,
            name=project.name,
            description=project.description,
        )
    )
    await session.flush()
    await normalize_rows(session, project.id, value)
    session.add(TopologySnapshot(project_id=project.id, revision=project.revision, config=value))
    await record_names(session, project.id, project.revision, old_config, value)
    await prune_snapshots(session, project, state)
    services.audit(
        session, actor, f"topology.{history}", project.id, project.id, services.utc_now_us()
    )
    await session.flush()
    return response(project, state, actor)


def deletion_impact(config: dict, kind: str, identifier: str) -> dict:
    entries = indexed(config)
    if identifier not in entries or entries[identifier][0] != kind:
        raise DomainError("NOT_FOUND", "Resource not found.", 404)
    affected = {identifier}
    while True:
        prior = len(affected)
        for collection, key in (
            ("servers", "subsystem_id"),
            ("servers", "connection_id"),
            ("processes", "server_id"),
            ("connections", "jump_connection_id"),
        ):
            affected.update(item["id"] for item in config[collection] if item[key] in affected)
        affected.update(
            item["id"]
            for item in config["processes"]
            if item["log_source"]["parser_id"] in affected
        )
        affected.update(
            item["id"]
            for item in config["flows"]
            if item["source_process_id"] in affected or item["target_process_id"] in affected
        )
        if len(affected) == prior:
            break
    return dict(
        entities=[
            dict(kind=entries[i][0], id=i, name=entries[i][1]["name"]) for i in sorted(affected)
        ],
        flows=[i for i in sorted(affected) if entries[i][0] == "flow"],
        views=[
            view["id"]
            for view in config["views"]
            if view["id"] in affected
            or any(n["element_id"] in affected for n in view["nodes"])
            or any(i in affected for i in view["flow_ids"])
        ],
        investigations=[],
        active_sessions=[],
    )


def build_topology_router(transaction: Any, authenticated: Any, protected_write: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}")
    Session = Annotated[AsyncSession, Depends(transaction, scope="function")]
    Actor = Annotated[Principal, Depends(authenticated)]
    Writer = Annotated[Principal, Depends(protected_write)]

    @router.get(
        "/topology",
        response_model=TopologyResponse,
        openapi_extra={"x-permission": "topology.read"},
    )
    async def read(project_id: str, actor: Actor, session: Session) -> dict:
        actor, project, state = await context(session, actor, project_id, "topology.read")
        return response(project, state, actor)

    @router.get(
        "/config",
        response_model=TopologyResponse,
        openapi_extra={"x-permission": "project_config.read"},
    )
    async def full_config(project_id: str, actor: Actor, session: Session) -> dict:
        actor, project, state = await context(session, actor, project_id, "project_config.read")
        return response(project, state, actor)

    @router.put(
        "/topology",
        response_model=TopologyResponse,
        openapi_extra={"x-permission": "topology.write"},
    )
    async def write(
        project_id: str, payload: TopologyInput, actor: Writer, session: Session, request: Request
    ) -> dict:
        actor, project, state = await context(
            session, actor, project_id, "topology.write", writable=True
        )
        check_revision(project, payload.expected_revision)
        normalized_size = await cpu_work(lambda: validated_size(payload.config))
        if normalized_size > request.app.state.config.config_upload_bytes:
            raise DomainError(
                "LIMIT_REACHED", "Configuration exceeds the configured upload byte limit.", 413
            )
        return await save(
            session,
            actor,
            project,
            state,
            payload.config,
            confirmed_deletions=payload.confirmed_deletions,
            reparent=payload.reparent,
            already_validated=True,
        )

    @router.post(
        "/topology/delete-preview",
        response_model=DeleteResponse,
        openapi_extra={"x-permission": "topology.write"},
    )
    async def delete_preview(
        project_id: str, payload: DeleteInput, actor: Writer, session: Session
    ) -> dict:
        actor, project, state = await context(
            session, actor, project_id, "topology.write", writable=True
        )
        impact = deletion_impact(state.config, payload.kind, payload.id)
        processes = [item["id"] for item in impact["entities"] if item["kind"] == "process"]
        if processes:
            jobs = (
                await session.scalars(
                    select(HistoryJob)
                    .where(
                        HistoryJob.project_id == project_id,
                        HistoryJob.id.in_(
                            select(HistorySource.job_id).where(
                                HistorySource.project_id == project_id,
                                HistorySource.process_id.in_(processes),
                            )
                        ),
                    )
                    .limit(1001)
                )
            ).all()
            if len(jobs) > 1000:
                raise DomainError(
                    "LIMIT_REACHED", "Deletion affects too many captures to preview.", 413
                )
            # Reveal only the caller's private investigation IDs. Active job
            # identifiers are operational metadata available to Administrators.
            impact["investigations"] = [
                job.id for job in jobs if job.owner_user_id == actor.user_id
            ]
            impact["active_sessions"] = [
                job.id
                for job in jobs
                if job.status
                in {"queued", "planning", "collecting", "indexing", "cancel_requested"}
            ]
        return dict(
            project_id=project.id,
            revision=project.revision,
            **impact,
        )

    @router.post(
        "/topology/undo",
        response_model=TopologyResponse,
        openapi_extra={"x-permission": "topology.write"},
    )
    async def undo(
        project_id: str, payload: RevisionInput, actor: Writer, session: Session
    ) -> dict:
        return await apply_history(session, actor, project_id, payload, "undo")

    @router.post(
        "/topology/redo",
        response_model=TopologyResponse,
        openapi_extra={"x-permission": "topology.write"},
    )
    async def redo(
        project_id: str, payload: RevisionInput, actor: Writer, session: Session
    ) -> dict:
        return await apply_history(session, actor, project_id, payload, "redo")

    @router.post(
        "/search", response_model=SearchResponse, openapi_extra={"x-permission": "topology.search"}
    )
    async def search(
        project_id: str, payload: SearchInput, actor: Writer, session: Session
    ) -> dict:
        _actor, project, state = await context(session, actor, project_id, "topology.search")
        needle = payload.q.casefold()
        results = []
        for collection in ("subsystems", "servers", "processes", "flows"):
            kind = COLLECTIONS[collection][0]
            for item in state.config[collection]:
                text = "\n".join(
                    [
                        item["name"],
                        item.get("description", ""),
                        item.get("pcs_resource_name") or "",
                        *item.get("tags", []),
                    ]
                )
                if needle in text.casefold():
                    view = next(
                        (
                            view["id"]
                            for view in state.config["views"]
                            if any(node["element_id"] == item["id"] for node in view["nodes"])
                            or item["id"] in view["flow_ids"]
                        ),
                        None,
                    )
                    results.append(dict(kind=kind, id=item["id"], name=item["name"], view_id=view))
        return dict(project_id=project.id, results=results)

    @router.post(
        "/config/preview",
        response_model=PreviewResponse,
        openapi_extra={"x-permission": "project_config.import"},
    )
    async def preview(
        project_id: str, payload: PreviewInput, actor: Writer, session: Session, request: Request
    ) -> dict:
        actor, project, state = await context(
            session, actor, project_id, "project_config.import", writable=True
        )
        check_revision(project, payload.expected_revision)
        try:
            content_bytes = payload.content.encode("utf-8")
        except UnicodeEncodeError:
            raise DomainError(
                "INVALID_PROJECT", "Configuration must contain valid Unicode text.", 422
            ) from None
        if len(content_bytes) > request.app.state.config.config_upload_bytes:
            raise DomainError(
                "LIMIT_REACHED", "Configuration exceeds the configured upload byte limit.", 413
            )
        value, warnings = await cpu_work(
            lambda: project_config.parse_config(payload.content, payload.format)
        )
        source_id = value["project"]["id"]
        if source_id == project.id and value["project"]["revision"] != project.revision:
            raise DomainError(
                "REVISION_CONFLICT",
                "Configuration export is stale; reconcile its content and revision before preview.",
                409,
            )
        value["project"]["id"] = project.id
        value["project"]["revision"] = project.revision
        await cpu_work(lambda: project_config.validate_project(value))
        now = services.utc_now_us()
        await session.execute(delete(ConfigPreview).where(ConfigPreview.expires_us <= now))
        count = await session.scalar(
            select(func.count())
            .select_from(ConfigPreview)
            .where(ConfigPreview.owner_user_id == actor.user_id)
        )
        if (count or 0) >= 10:
            raise DomainError(
                "LIMIT_REACHED", "Too many unexpired configuration previews; wait for expiry.", 429
            )
        pending = ConfigPreview(
            project_id=project.id,
            id=str(uuid4()),
            owner_user_id=actor.user_id,
            auth_version=actor.auth_version,
            expected_revision=project.revision,
            source_project_id=source_id,
            digest=hashlib.sha256(canonical_bytes(value)).hexdigest(),
            config=value,
            expires_us=now + PREVIEW_LEASE_US,
        )
        session.add(pending)
        delta = changes(state.config, value)
        warnings = list(warnings) + [
            "Imported connections and log roots are proposals. Credentials remain unresolved; no target or host key is approved."
        ]
        if source_id != project.id:
            warnings.append(
                "The source project ID will be explicitly remapped to the selected target system at commit."
            )
        await session.flush()
        return dict(
            preview_id=pending.id,
            project_id=project.id,
            expected_revision=project.revision,
            expires_us=str(pending.expires_us),
            warnings=warnings,
            source_project_id=source_id,
            target_project_id=project.id,
            changes=delta,
            requires_delete_confirmation=bool(delta["removed"]),
            requires_reparent_confirmation=has_reparent(state.config, value),
        )

    @router.post(
        "/config/commit",
        response_model=TopologyResponse,
        openapi_extra={"x-permission": "project_config.import"},
    )
    async def commit(
        project_id: str, payload: CommitInput, actor: Writer, session: Session
    ) -> dict:
        actor, project, state = await context(
            session, actor, project_id, "project_config.import", writable=True
        )
        pending = await session.scalar(
            select(ConfigPreview)
            .where(
                ConfigPreview.project_id == project.id,
                ConfigPreview.id == payload.preview_id,
                ConfigPreview.owner_user_id == actor.user_id,
            )
            .with_for_update()
        )
        if pending is None:
            raise DomainError("NOT_FOUND", "Resource not found.", 404)
        if pending.expires_us <= services.utc_now_us():
            raise DomainError(
                "PREVIEW_EXPIRED", "Configuration preview expired; preview again.", 410
            )
        if pending.auth_version != actor.auth_version:
            raise DomainError("REVISION_CONFLICT", "Authorization changed; preview again.", 409)
        check_revision(project, payload.expected_revision)
        if (
            pending.expected_revision != project.revision
            or pending.digest != hashlib.sha256(canonical_bytes(pending.config)).hexdigest()
        ):
            raise DomainError(
                "REVISION_CONFLICT", "Preview no longer matches the selected system revision.", 409
            )
        if pending.source_project_id != project.id and not payload.confirm_project_remap:
            raise DomainError(
                "PROJECT_REMAP_CONFIRMATION_REQUIRED",
                "Explicitly confirm importing into the selected target system.",
                409,
            )
        result = await save(
            session,
            actor,
            project,
            state,
            pending.config,
            confirmed_deletions=payload.confirmed_deletions,
            reparent=payload.reparent,
        )
        await session.delete(pending)
        return result

    @router.get(
        "/config/export",
        response_model=ExportResponse,
        openapi_extra={"x-permission": "project_config.export"},
    )
    async def export(
        project_id: str, actor: Actor, session: Session, format: Literal["json", "yaml"] = "json"
    ) -> dict:
        _actor, project, state = await context(session, actor, project_id, "project_config.export")
        content = await cpu_work(
            lambda: (
                json.dumps(state.config, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
                if format == "json"
                else yaml.safe_dump(state.config, allow_unicode=True, sort_keys=False)
            )
        )
        return dict(project_id=project.id, format=format, content=content)

    return router


async def apply_history(
    session: AsyncSession,
    actor: Principal,
    project_id: str,
    payload: RevisionInput,
    direction: Literal["undo", "redo"],
) -> dict:
    actor, project, state = await context(
        session, actor, project_id, "topology.write", writable=True
    )
    check_revision(project, payload.expected_revision)
    stack = state.undo_stack if direction == "undo" else state.redo_stack
    if not stack:
        raise DomainError("HISTORY_EMPTY", "No saved topology change is available.", 409)
    snapshot = await session.get(TopologySnapshot, (project.id, stack[-1]))
    if snapshot is None:
        raise DomainError("NOT_READY", "Required topology history is unavailable.", 503)
    return await save(
        session,
        actor,
        project,
        state,
        snapshot.config,
        confirmed_deletions=True,
        reparent=True,
        history=direction,
    )
