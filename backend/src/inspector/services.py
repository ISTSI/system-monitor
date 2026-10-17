"""Scoped operations; callers own short MariaDB transactions."""

import time
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inspector.domain import Principal, ProjectContext
from inspector.errors import DomainError
from inspector.persistence.models import (
    Audit,
    Project,
    ProjectRevision,
    SecurityState,
    User,
    Workspace,
)
from inspector.security import authorize

WORKSPACE_LEASE_US = 300_000_000


def utc_now_us() -> int:
    return time.time_ns() // 1000


def validate_metadata(name: str, description: str) -> None:
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name) > 256
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
        or not isinstance(description, str)
        or len(description) > 10000
    ):
        raise DomainError("INVALID_REQUEST", "Invalid system metadata.", 422)


async def current_actor(session: AsyncSession, principal: Principal) -> Principal:
    guard = await session.scalar(
        select(SecurityState).where(SecurityState.id == 1).with_for_update()
    )
    if guard is None:
        raise DomainError("NOT_READY", "Security state is unavailable.", 503)
    user = await session.get(User, principal.user_id, with_for_update=True, populate_existing=True)
    if (
        user is None
        or not user.enabled
        or user.auth_version != principal.auth_version
        or user.role not in {"administrator", "inspector"}
    ):
        raise DomainError("AUTH_REQUIRED", "Authentication is required.", 401)
    if user.must_change_password:
        raise DomainError(
            "PASSWORD_CHANGE_REQUIRED", "Change your password before continuing.", 403
        )
    return Principal(
        user.id,
        user.role,
        user.auth_version,
        user.must_change_password,
        user.display_name,
        user.username_key,
    )


async def project_in_context(
    session: AsyncSession, context: ProjectContext, *, lock: bool = False
) -> Project:
    query = select(Project).where(Project.id == context.project_id)
    if lock:
        query = query.with_for_update()
    project = await session.scalar(query)
    if project is None:
        raise DomainError("NOT_FOUND", "Resource not found.", 404)
    return project


def audit(
    session: AsyncSession,
    principal: Principal,
    action: str,
    project_id: str,
    target_id: str,
    now_us: int,
) -> None:
    session.add(
        Audit(
            id=str(uuid4()),
            actor_user_id=principal.user_id,
            actor_role=principal.role,
            action=action,
            project_id=project_id,
            target_id=target_id,
            created_us=now_us,
            outcome="success",
        )
    )


async def list_projects(
    session: AsyncSession, principal: Principal, *, include_archived: bool = False
) -> dict:
    principal = await current_actor(session, principal)
    authorize(principal, "system.list")
    query = select(Project).order_by(Project.id).limit(1001)
    if not include_archived:
        query = query.where(Project.archived.is_(False))
    projects = (await session.scalars(query)).all()
    if len(projects) > 1000:
        raise DomainError("LIMIT_REACHED", "Catalogue exceeds supported page size.", 413)
    return {
        "items": [
            dict(
                project_id=p.id,
                name=p.name,
                description=p.description,
                revision=p.revision,
                archived=p.archived,
                own_live_sessions=0,
            )
            for p in projects
        ]
    }


async def create_project(
    session: AsyncSession,
    principal: Principal,
    name: str,
    description: str,
    *,
    project_id: str | None = None,
) -> Project:
    principal = await current_actor(session, principal)
    authorize(principal, "system.create")
    validate_metadata(name, description)
    identifier = project_id if project_id is not None else str(uuid4())
    ProjectContext(identifier, principal.user_id)
    project = Project(id=identifier, name=name, description=description, revision=1, archived=False)
    session.add(project)
    await session.flush()
    session.add(
        ProjectRevision(project_id=identifier, revision=1, name=name, description=description)
    )
    audit(session, principal, "system.create", identifier, identifier, utc_now_us())
    await session.flush()
    from inspector.topology import initialize_document

    await initialize_document(session, project)
    return project


async def rename_project(
    session: AsyncSession,
    principal: Principal,
    project_id: str,
    name: str,
    description: str,
    expected_revision: int,
) -> Project:
    principal = await current_actor(session, principal)
    authorize(principal, "system.metadata.write")
    validate_metadata(name, description)
    project = await project_in_context(
        session, ProjectContext(project_id, principal.user_id), lock=True
    )
    if project.revision != expected_revision:
        raise DomainError("REVISION_CONFLICT", "System has changed; reload before saving.", 409)
    if project.archived:
        raise DomainError("PROJECT_ARCHIVED", "Archived system is read-only.", 409)
    project.name, project.description = name, description
    project.revision += 1
    session.add(
        ProjectRevision(
            project_id=project.id, revision=project.revision, name=name, description=description
        )
    )
    audit(session, principal, "system.metadata.write", project_id, project_id, utc_now_us())
    await session.flush()
    from inspector.topology import sync_metadata

    await sync_metadata(session, project, record_undo=True)
    await session.flush()
    return project


async def set_project_archived(
    session: AsyncSession,
    principal: Principal,
    project_id: str,
    expected_revision: int,
    *,
    archived: bool,
) -> Project:
    principal = await current_actor(session, principal)
    action = "system.archive" if archived else "system.restore"
    authorize(principal, action)
    project = await project_in_context(
        session, ProjectContext(project_id, principal.user_id), lock=True
    )
    if project.revision != expected_revision or project.archived == archived:
        raise DomainError("REVISION_CONFLICT", "System has changed; reload before saving.", 409)
    project.archived = archived
    project.revision += 1
    session.add(
        ProjectRevision(
            project_id=project.id,
            revision=project.revision,
            name=project.name,
            description=project.description,
        )
    )
    if archived:
        await session.execute(
            update(Workspace)
            .where(Workspace.project_id == project_id, Workspace.state == "active")
            .values(state="detached", revision=Workspace.revision + 1)
        )
    audit(session, principal, action, project_id, project_id, utc_now_us())
    await session.flush()
    from inspector.topology import sync_metadata

    await sync_metadata(session, project)
    await session.flush()
    return project


def workspace_response(workspace: Workspace) -> dict:
    return dict(
        schema_version="1.0",
        workspace_id=workspace.id,
        project_id=workspace.project_id,
        owner_user_id=workspace.owner_user_id,
        revision=workspace.revision,
        state=workspace.state,
        live_session_ids=[],
    )


async def create_workspace(
    session: AsyncSession,
    principal: Principal,
    context: ProjectContext,
    *,
    max_per_user: int,
    max_global: int,
    now_us: int,
) -> dict:
    principal = await current_actor(session, principal)
    authorize(principal, "workspace.create")
    if context.user_id != principal.user_id:
        raise DomainError("NOT_FOUND", "Resource not found.", 404)
    # One bounded deployment-wide critical section makes quota check + reserve atomic.
    guard = await session.scalar(
        select(SecurityState).where(SecurityState.id == 1).with_for_update()
    )
    if guard is None:
        raise DomainError("NOT_READY", "Security state is unavailable.", 503)
    project = await project_in_context(session, context, lock=True)
    if project.archived:
        raise DomainError("PROJECT_ARCHIVED", "Archived system is read-only.", 409)
    await session.execute(
        update(Workspace)
        .where(Workspace.state != "expired", Workspace.expires_us <= now_us)
        .values(state="expired", revision=Workspace.revision + 1)
    )
    own = await session.scalar(
        select(func.count())
        .select_from(Workspace)
        .where(Workspace.owner_user_id == principal.user_id, Workspace.state != "expired")
    )
    total = await session.scalar(
        select(func.count()).select_from(Workspace).where(Workspace.state != "expired")
    )
    if (own or 0) >= max_per_user or (total or 0) >= max_global:
        raise DomainError(
            "LIMIT_REACHED",
            "Workspace limit reached; close or wait for an old workspace to expire.",
            429,
        )
    workspace = Workspace(
        project_id=context.project_id,
        id=str(uuid4()),
        owner_user_id=principal.user_id,
        opened_revision=project.revision,
        revision=1,
        state="active",
        created_us=now_us,
        expires_us=now_us + WORKSPACE_LEASE_US,
    )
    session.add(workspace)
    await session.flush()
    return workspace_response(workspace)


async def get_workspace(
    session: AsyncSession,
    principal: Principal,
    context: ProjectContext,
    workspace_id: str,
    *,
    now_us: int,
    detach: bool = False,
) -> dict:
    principal = await current_actor(session, principal)
    if context.user_id != principal.user_id:
        raise DomainError("NOT_FOUND", "Resource not found.", 404)
    workspace = await session.scalar(
        select(Workspace)
        .where(
            Workspace.project_id == context.project_id,
            Workspace.id == workspace_id,
            Workspace.owner_user_id == principal.user_id,
        )
        .with_for_update()
    )
    if workspace is None:
        raise DomainError("NOT_FOUND", "Resource not found.", 404)
    authorize(
        principal,
        "workspace.detach" if detach else "workspace.read",
        owner_user_id=workspace.owner_user_id,
    )
    if workspace.state != "expired" and workspace.expires_us <= now_us:
        workspace.state = "expired"
        workspace.revision += 1
    elif detach and workspace.state == "active":
        workspace.state = "detached"
        workspace.expires_us = now_us + WORKSPACE_LEASE_US
        workspace.revision += 1
    elif workspace.state == "active":
        workspace.expires_us = now_us + WORKSPACE_LEASE_US
    await session.flush()
    return workspace_response(workspace)
