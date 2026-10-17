"""Scoped web application with explicit, Administrator-controlled SSH tests."""

import asyncio
import hmac
import re
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from inspector import auth, foundation, services
from inspector.accounts import build_account_router
from inspector.config import Config, load_config
from inspector.database import create_engine, local_state_lock, supervisor_guard
from inspector.domain import ID_PATTERN, Principal, ProjectContext
from inspector.errors import DomainError
from inspector.history import NONTERMINAL, HistoryManager, build_history_router
from inspector.security import issue_token, require_admin, token_hash
from inspector.source_access import SourceAccess, build_source_access_router
from inspector.ssh_access import SSHAccess, build_ssh_access_router
from inspector.topology import build_topology_router, initialize_legacy_documents

SESSION_COOKIE = "__Host-si-session"
CSRF_COOKIE = "__Host-si-csrf"
PRE_CSRF_COOKIE = "__Host-si-pre-csrf"


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginInput(EmptyInput):
    username: str = Field(min_length=1, max_length=128)
    password: SecretStr = Field(min_length=1, max_length=1024)


class ProjectInput(EmptyInput):
    name: str = Field(min_length=1, max_length=256, pattern=r"\S")
    description: str = Field(default="", max_length=10000)


class MetadataInput(ProjectInput):
    expected_revision: int = Field(ge=1)


class RevisionInput(EmptyInput):
    expected_revision: int = Field(ge=1)


class WorkspaceInput(EmptyInput):
    project_id: str | None = Field(default=None, pattern=ID_PATTERN)


class SessionResponse(EmptyInput):
    user_id: str
    role: Literal["administrator", "inspector"]
    username: str
    display_name: str
    must_change_password: bool


class LoginResponse(SessionResponse):
    csrf_token: str


class CatalogueEntry(EmptyInput):
    project_id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(max_length=10000)
    revision: int = Field(ge=1)
    archived: bool
    own_live_sessions: int = Field(ge=0)


class CatalogueResponse(EmptyInput):
    items: list[CatalogueEntry] = Field(max_length=1000)


class WorkspaceResponse(EmptyInput):
    schema_version: Literal["1.0"]
    workspace_id: str = Field(pattern=ID_PATTERN)
    project_id: str = Field(pattern=ID_PATTERN)
    owner_user_id: str = Field(pattern=ID_PATTERN)
    revision: int = Field(ge=1)
    state: Literal["active", "detached", "expired"]
    live_session_ids: list[str] = Field(max_length=200)


class ProjectMutationResponse(EmptyInput):
    project_id: str = Field(pattern=ID_PATTERN)
    revision: int = Field(ge=1)


async def transaction(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        try:
            yield session
        except DomainError as error:
            if error.code == "INVALID_CREDENTIALS":
                await session.commit()  # Auth denial audit only; never commit a denied mutation.
            else:
                await session.rollback()
            raise
        else:
            await session.commit()


Session = Annotated[AsyncSession, Depends(transaction, scope="function")]


async def authenticated(request: Request, session: Session) -> Principal:
    principal = await auth.authenticate(
        session,
        request.cookies.get(SESSION_COOKIE, ""),
        services.utc_now_us(),
        request.app.state.config.idle_timeout_us,
        renew_idle=request.method != "GET",
        allow_password_change=True,
    )
    request.state.principal = principal
    if principal.must_change_password and request.url.path not in {
        "/api/v1/auth/session",
        "/api/v1/me/password",
        "/api/v1/auth/logout",
    }:
        raise DomainError(
            "PASSWORD_CHANGE_REQUIRED", "Change your password before continuing.", 403
        )
    return principal


Actor = Annotated[Principal, Depends(authenticated)]


async def protected_write(request: Request, session: Session, principal: Actor) -> Principal:
    await auth.verify_csrf(
        session, request.cookies.get(SESSION_COOKIE, ""), request.headers.get("x-csrf-token", "")
    )
    return principal


Writer = Annotated[Principal, Depends(protected_write)]


def _cookie(response: JSONResponse, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name, value, max_age=max_age, secure=True, httponly=True, samesite="strict", path="/"
    )


def create_app(config: Config | None = None) -> FastAPI:
    config = config if config is not None else load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(config.database)
        lock_engine = create_engine(config.database, dedicated=True)
        app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            with local_state_lock(config.state_dir):
                async with AsyncExitStack() as stack:
                    async with asyncio.timeout(config.database.startup_timeout_seconds):
                        supervisor = await stack.enter_async_context(supervisor_guard(lock_engine))
                    app.state.supervisor = supervisor
                    # Restart never resumes collection or claims any old page's workspace.
                    from sqlalchemy import update

                    from inspector.persistence.models import HistoryJob, HistorySource, Workspace

                    async with app.state.sessions.begin() as session:
                        await foundation.initialize_settings(session, config)
                        await initialize_legacy_documents(session)
                        await session.execute(
                            update(Workspace)
                            .where(Workspace.state == "active")
                            .values(state="detached", revision=Workspace.revision + 1)
                        )
                        await session.execute(
                            update(HistoryJob)
                            .where(HistoryJob.status.in_(NONTERMINAL))
                            .values(status="interrupted")
                        )
                        await session.execute(
                            update(HistorySource)
                            .where(HistorySource.status.in_(["queued", "collecting"]))
                            .values(status="partial", error_code="BACKEND_RESTART")
                        )
                    app.state.ssh_access = SSHAccess(config, app.state.sessions, supervisor)
                    app.state.source_access = SourceAccess(app.state.ssh_access)
                    app.state.history = HistoryManager(
                        config, app.state.sessions, supervisor, app.state.source_access
                    )
                    try:
                        yield
                    finally:
                        await app.state.history.close()
        finally:
            app.state.supervisor = None
            await lock_engine.dispose()
            await engine.dispose()

    app = FastAPI(
        title="System Inspector",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.config = config
    app.state.supervisor = None
    login_attempts: deque[float] = deque(maxlen=10)
    credential_attempts: deque[float] = deque(maxlen=30)
    authority = urlsplit(config.public_origin).netloc.lower()

    def error_response(error: DomainError) -> JSONResponse:
        response = JSONResponse(
            status_code=error.status,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": {},
                    "request_id": str(uuid4()),
                }
            },
        )
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError) -> JSONResponse:
        principal = getattr(request.state, "principal", None)
        if principal is not None and error.status in {403, 404}:
            from inspector.persistence.models import Audit

            target = request.path_params.get("workspace_id") or request.path_params.get(
                "project_id"
            )
            target = (
                target if isinstance(target, str) and re.fullmatch(ID_PATTERN, target) else None
            )
            try:
                async with app.state.sessions.begin() as denied_session:
                    denied_session.add(
                        Audit(
                            id=str(uuid4()),
                            actor_user_id=principal.user_id,
                            actor_role=principal.role,
                            action="authorization.denied",
                            project_id=None,
                            target_id=target,
                            created_us=services.utc_now_us(),
                            outcome="denied",
                        )
                    )
            except SQLAlchemyError:
                return error_response(
                    DomainError("DATABASE_UNAVAILABLE", "Database operation unavailable.", 503)
                )
        return error_response(error)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request: Request, _error: SQLAlchemyError) -> JSONResponse:
        return error_response(
            DomainError("DATABASE_UNAVAILABLE", "Database operation unavailable.", 503)
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError) -> JSONResponse:
        # Pydantic errors can contain submitted passwords or config values.
        return error_response(DomainError("INVALID_REQUEST", "Invalid request fields.", 422))

    @app.middleware("http")
    async def boundary(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.headers.get("host", "").lower() != authority:
            return error_response(DomainError("INVALID_HOST", "Unexpected request host.", 400))
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") != config.public_origin:
                return error_response(DomainError("CSRF_FAILED", "Unexpected request origin.", 403))
            topology_upload = bool(
                re.fullmatch(
                    r"/api/v1/projects/[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}/(?:topology|config/preview)",
                    request.url.path,
                )
            )
            history_query = bool(
                re.fullmatch(
                    r"/api/v1/projects/[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}/investigations/[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}/(?:query|events/[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}/context)",
                    request.url.path,
                )
            )
            maximum_body = (
                config.config_upload_bytes * 6 + 512
                if topology_upload
                else 25_624_576
                if history_query
                else 16384
            )
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > maximum_body:
                    return error_response(
                        DomainError("PAYLOAD_TOO_LARGE", "Request exceeds limit.", 413)
                    )
                chunks.append(chunk)
            request._body = b"".join(chunks)
            if request.url.path == "/api/v1/me/password" or request.url.path.startswith(
                "/api/v1/admin/users"
            ):
                now = time.monotonic()
                while credential_attempts and credential_attempts[0] <= now - 60:
                    credential_attempts.popleft()
                if len(credential_attempts) >= 30:
                    return error_response(
                        DomainError(
                            "LIMIT_REACHED",
                            "Account operation rate limit reached; retry later.",
                            429,
                        )
                    )
                credential_attempts.append(now)
        if request.url.path not in {"/api/v1/health/live", "/api/v1/health/ready"}:
            supervisor = app.state.supervisor
            if supervisor is None or not await supervisor.healthy():
                return error_response(DomainError("NOT_READY", "Supervisor is unavailable.", 503))
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
                "Referrer-Policy": "no-referrer",
            }
        )
        return response

    @app.get("/api/v1/health/live")
    async def live() -> dict:
        return {"status": "alive"}

    @app.get("/api/v1/health/ready")
    async def ready() -> JSONResponse:
        supervisor = app.state.supervisor
        healthy = supervisor is not None and await supervisor.healthy()
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={"status": "ready" if healthy else "unavailable"},
        )

    @app.get("/api/v1/auth/csrf")
    async def csrf(request: Request, session: Session) -> JSONResponse:
        if SESSION_COOKIE in request.cookies:
            try:
                await auth.authenticate(
                    session,
                    request.cookies[SESSION_COOKIE],
                    services.utc_now_us(),
                    config.idle_timeout_us,
                    renew_idle=False,
                    allow_password_change=True,
                )
            except DomainError as error:
                if error.code != "AUTH_REQUIRED":
                    raise
                # A stale cookie may start a fresh login; a late response must
                # never delete a newer HttpOnly session cookie set elsewhere.
            else:
                value = request.cookies.get(CSRF_COOKIE, "")
                await auth.verify_csrf(session, request.cookies[SESSION_COOKIE], value)
                return JSONResponse({"csrf_token": value})
        value = issue_token()
        response = JSONResponse({"csrf_token": value})
        _cookie(response, PRE_CSRF_COOKIE, value, 600)
        return response

    @app.post("/api/v1/auth/login", response_model=LoginResponse)
    async def login(request: Request, payload: LoginInput, session: Session) -> JSONResponse:
        candidate = request.headers.get("x-csrf-token", "")
        expected = request.cookies.get(PRE_CSRF_COOKIE, "")
        if (
            token_hash(expected) is None
            or token_hash(candidate) is None
            or not hmac.compare_digest(candidate, expected)
        ):
            raise DomainError("CSRF_FAILED", "Request verification failed.", 403)
        now = time.monotonic()
        while login_attempts and login_attempts[0] <= now - 60:
            login_attempts.popleft()
        if len(login_attempts) >= 10:
            raise DomainError("LIMIT_REACHED", "Login rate limit reached; retry later.", 429)
        login_attempts.append(now)
        credentials = await auth.login(
            session,
            payload.username,
            payload.password.get_secret_value(),
            services.utc_now_us(),
            config.idle_timeout_us,
            config.absolute_timeout_us,
        )
        response = JSONResponse(
            {
                "user_id": credentials.principal.user_id,
                "role": credentials.principal.role,
                "csrf_token": credentials.csrf_token,
                "username": credentials.principal.username,
                "display_name": credentials.principal.display_name,
                "must_change_password": credentials.principal.must_change_password,
            }
        )
        _cookie(
            response, SESSION_COOKIE, credentials.token, config.absolute_timeout_us // 1_000_000
        )
        _cookie(
            response, CSRF_COOKIE, credentials.csrf_token, config.absolute_timeout_us // 1_000_000
        )
        response.delete_cookie(
            PRE_CSRF_COOKIE, path="/", secure=True, httponly=True, samesite="strict"
        )
        return response

    @app.get("/api/v1/auth/session", response_model=SessionResponse)
    async def session_info(principal: Actor) -> dict:
        return {
            "user_id": principal.user_id,
            "role": principal.role,
            "username": principal.username,
            "display_name": principal.display_name,
            "must_change_password": principal.must_change_password,
        }

    @app.post("/api/v1/auth/logout")
    async def logout(payload: EmptyInput, principal: Writer, session: Session) -> JSONResponse:
        await auth.logout(session, principal, services.utc_now_us())
        response = JSONResponse({"status": "logged_out"})
        for cookie in (SESSION_COOKIE, CSRF_COOKIE, PRE_CSRF_COOKIE):
            response.delete_cookie(cookie, path="/", secure=True, httponly=True, samesite="strict")
        return response

    @app.get(
        "/api/v1/projects",
        response_model=CatalogueResponse,
        openapi_extra={"x-permission": "system.list"},
    )
    async def catalogue(principal: Actor, session: Session, include_archived: bool = False) -> dict:
        return await services.list_projects(session, principal, include_archived=include_archived)

    @app.post(
        "/api/v1/projects",
        status_code=201,
        response_model=ProjectMutationResponse,
        openapi_extra={"x-permission": "system.create"},
    )
    async def create_project(payload: ProjectInput, principal: Writer, session: Session) -> dict:
        project = await services.create_project(
            session, principal, payload.name, payload.description
        )
        return {"project_id": project.id, "revision": project.revision}

    @app.patch(
        "/api/v1/projects/{project_id}/metadata",
        response_model=ProjectMutationResponse,
        openapi_extra={"x-permission": "system.metadata.write"},
    )
    async def metadata(
        project_id: str, payload: MetadataInput, principal: Writer, session: Session
    ) -> dict:
        project = await services.rename_project(
            session,
            principal,
            project_id,
            payload.name,
            payload.description,
            payload.expected_revision,
        )
        return {"project_id": project.id, "revision": project.revision}

    @app.post(
        "/api/v1/projects/{project_id}/workspaces",
        response_model=WorkspaceResponse,
        status_code=201,
        openapi_extra={"x-permission": "workspace.create"},
    )
    async def create_workspace(
        project_id: str, payload: WorkspaceInput, principal: Writer, session: Session
    ) -> dict:
        if payload.project_id is not None and payload.project_id != project_id:
            raise DomainError("PROJECT_MISMATCH", "Route and body project must agree.", 422)
        return await services.create_workspace(
            session,
            principal,
            ProjectContext(project_id, principal.user_id),
            max_per_user=config.max_workspaces_per_user,
            max_global=config.max_workspaces_global,
            now_us=services.utc_now_us(),
        )

    @app.post(
        "/api/v1/projects/{project_id}/archive",
        response_model=ProjectMutationResponse,
        openapi_extra={"x-permission": "system.archive"},
    )
    async def archive_project(
        project_id: str, payload: RevisionInput, principal: Writer, session: Session
    ) -> dict:
        value = await services.set_project_archived(
            session, principal, project_id, payload.expected_revision, archived=True
        )
        return {"project_id": value.id, "revision": value.revision}

    @app.post(
        "/api/v1/projects/{project_id}/restore",
        response_model=ProjectMutationResponse,
        openapi_extra={"x-permission": "system.restore"},
    )
    async def restore_project(
        project_id: str, payload: RevisionInput, principal: Writer, session: Session
    ) -> dict:
        value = await services.set_project_archived(
            session, principal, project_id, payload.expected_revision, archived=False
        )
        return {"project_id": value.id, "revision": value.revision}

    @app.get(
        "/api/v1/projects/{project_id}/workspaces/{workspace_id}",
        response_model=WorkspaceResponse,
        openapi_extra={"x-permission": "workspace.read"},
    )
    async def workspace(
        project_id: str, workspace_id: str, principal: Actor, session: Session
    ) -> dict:
        return await services.get_workspace(
            session,
            principal,
            ProjectContext(project_id, principal.user_id),
            workspace_id,
            now_us=services.utc_now_us(),
        )

    @app.post(
        "/api/v1/projects/{project_id}/workspaces/{workspace_id}/detach",
        response_model=WorkspaceResponse,
        openapi_extra={"x-permission": "workspace.detach"},
    )
    async def detach(
        project_id: str, workspace_id: str, payload: EmptyInput, principal: Writer, session: Session
    ) -> dict:
        return await services.get_workspace(
            session,
            principal,
            ProjectContext(project_id, principal.user_id),
            workspace_id,
            now_us=services.utc_now_us(),
            detach=True,
        )

    @app.get(
        "/api/v1/ui/bootstrap",
        response_model=foundation.BootstrapResponse,
        openapi_extra={"x-permission": "public.bootstrap"},
    )
    async def bootstrap(session: Session) -> dict:
        return {
            **await foundation.bootstrap(session),
            "historical_demo_enabled": config.local_history_demo,
        }

    @app.get(
        "/api/v1/me/preferences",
        response_model=foundation.PreferenceResponse,
        openapi_extra={"x-permission": "preference.read"},
    )
    async def preferences(principal: Actor, session: Session) -> dict:
        return await foundation.preferences(session, principal)

    @app.patch(
        "/api/v1/me/preferences",
        response_model=foundation.PreferenceResponse,
        openapi_extra={"x-permission": "preference.write"},
    )
    async def update_preferences(
        payload: foundation.PreferenceInput, principal: Writer, session: Session
    ) -> dict:
        return await foundation.update_preferences(session, principal, payload)

    @app.get(
        "/api/v1/admin/settings",
        response_model=foundation.SettingsResponse,
        openapi_extra={"x-permission": "settings.read"},
    )
    async def settings(principal: Actor, session: Session) -> dict:
        return await foundation.get_settings(session, principal)

    @app.patch(
        "/api/v1/admin/settings",
        response_model=foundation.SettingsResponse,
        openapi_extra={"x-permission": "settings.write"},
    )
    async def update_settings(
        payload: foundation.SettingsInput, principal: Writer, session: Session
    ) -> dict:
        return await foundation.update_settings(session, principal, payload)

    @app.get("/api/v1/admin/database/status", openapi_extra={"x-permission": "settings.read"})
    async def database_status(principal: Actor, session: Session) -> dict:
        principal = await services.current_actor(session, principal)
        require_admin(principal)
        from inspector.database import SCHEMA_REVISION

        return {
            "host": config.database.host,
            "port": config.database.port,
            "database": config.database.name,
            "server_version": await session.scalar(text("SELECT VERSION()")),
            "schema_revision": SCHEMA_REVISION,
            "ready": True,
            "transport": config.database.topology,
            "restart_required_to_change_endpoint": True,
        }

    @app.get("/api/v1/admin/audit", openapi_extra={"x-permission": "audit.read"})
    async def audit_events(principal: Actor, session: Session) -> dict:
        principal = await services.current_actor(session, principal)
        require_admin(principal)
        from inspector.persistence.models import Audit

        rows = (
            await session.scalars(
                select(Audit).order_by(Audit.created_us.desc(), Audit.id).limit(200)
            )
        ).all()
        return {
            "items": [
                {
                    "id": row.id,
                    "actor_user_id": row.actor_user_id,
                    "actor_role": row.actor_role,
                    "action": row.action,
                    "project_id": row.project_id,
                    "target_id": row.target_id,
                    "created_us": str(row.created_us),
                    "outcome": row.outcome,
                }
                for row in rows
            ]
        }

    @app.get(
        "/api/v1/projects/{project_id}",
        response_model=foundation.ProjectViewerResponse,
        openapi_extra={"x-permission": "topology.read"},
    )
    async def project_viewer(project_id: str, principal: Actor, session: Session) -> dict:
        return await foundation.project_viewer(session, principal, project_id)

    app.include_router(build_account_router(transaction, authenticated, protected_write))
    app.include_router(build_topology_router(transaction, authenticated, protected_write))
    app.include_router(build_history_router(transaction, authenticated, protected_write))
    app.include_router(build_ssh_access_router(transaction, authenticated, protected_write))
    app.include_router(build_source_access_router(transaction, authenticated, protected_write))
    bundled = Path(__file__).parent / "web"
    frontend = (
        bundled
        if (bundled / "index.html").is_file()
        else Path(__file__).resolve().parents[3] / "frontend/dist"
    )
    if (frontend / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    @app.get("/login", include_in_schema=False)
    @app.get("/settings", include_in_schema=False)
    @app.get("/users", include_in_schema=False)
    @app.get("/systems/{project_id}", include_in_schema=False)
    @app.get("/systems/{project_id}/topology", include_in_schema=False)
    @app.get("/systems/{project_id}/logs", include_in_schema=False)
    @app.get("/systems/{project_id}/investigations/{investigation_id}", include_in_schema=False)
    async def browser_shell(
        project_id: str | None = None, investigation_id: str | None = None
    ) -> Response:
        if (
            (project_id is not None and not re.fullmatch(ID_PATTERN, project_id))
            or not (frontend / "index.html").is_file()
            or (investigation_id is not None and not re.fullmatch(ID_PATTERN, investigation_id))
        ):
            return JSONResponse(
                {"error": {"code": "NOT_FOUND", "message": "Page not found."}}, status_code=404
            )
        return FileResponse(frontend / "index.html", media_type="text/html")

    return app
