"""Persisted appearance/settings and safe, explicitly synthetic viewer data."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inspector import services
from inspector.config import Config
from inspector.domain import ID_PATTERN, Principal, ProjectContext
from inspector.errors import DomainError
from inspector.persistence.models import (
    ApplicationSetting,
    DemoSnapshot,
    TopologyState,
    UserPreference,
)
from inspector.security import authorize, require_admin

Theme = Literal["light", "dark", "system"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PreferenceResponse(StrictModel):
    revision: int = Field(ge=1)
    theme_mode: Literal["default", "light", "dark", "system"]


class PreferenceInput(StrictModel):
    expected_revision: int = Field(ge=1)
    theme_mode: Literal["default", "light", "dark", "system"]


class SettingsResponse(StrictModel):
    revision: int = Field(ge=1)
    branding: str = Field(min_length=1, max_length=128)
    default_theme_mode: Theme


class SettingsInput(StrictModel):
    expected_revision: int = Field(ge=1)
    branding: str = Field(min_length=1, max_length=128, pattern=r"\S")
    default_theme_mode: Theme


class BootstrapResponse(StrictModel):
    branding: str
    default_theme_mode: Theme
    demo_mode: bool


class DemoProcess(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(max_length=256)
    description: str = Field(max_length=10000)
    log_path: str | None = None


class DemoServer(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(max_length=256)
    description: str = Field(max_length=10000)
    processes: list[DemoProcess] = Field(max_length=5000)


class DemoSubsystem(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(max_length=256)
    description: str = Field(max_length=10000)
    servers: list[DemoServer] = Field(max_length=5000)


class ProjectViewerResponse(StrictModel):
    project_id: str = Field(pattern=ID_PATTERN)
    name: str
    description: str
    revision: int
    archived: bool
    demo: bool
    subsystems: list[DemoSubsystem] = Field(max_length=5000)


async def initialize_settings(session: AsyncSession, config: Config) -> ApplicationSetting:
    from inspector.auth import _security_lock

    await _security_lock(session)
    settings = await session.get(ApplicationSetting, 1)
    if settings is None:
        settings = ApplicationSetting(
            id=1,
            revision=1,
            branding="System Inspector",
            default_theme_mode=config.default_theme_mode,
        )
        session.add(settings)
        await session.flush()
    return settings


async def settings_value(session: AsyncSession) -> ApplicationSetting:
    settings = await session.get(ApplicationSetting, 1)
    if settings is None:
        raise DomainError("NOT_READY", "Application settings are unavailable.", 503)
    return settings


def settings_response(settings: ApplicationSetting) -> dict:
    return {
        "revision": settings.revision,
        "branding": settings.branding,
        "default_theme_mode": settings.default_theme_mode,
    }


async def bootstrap(session: AsyncSession) -> dict:
    settings = await settings_value(session)
    # Do not expose inventory, account IDs, counts, addresses or auth state.
    return {
        "branding": settings.branding,
        "default_theme_mode": settings.default_theme_mode,
        "demo_mode": bool(await session.scalar(select(func.count()).select_from(DemoSnapshot))),
    }


async def preferences(session: AsyncSession, actor: Principal) -> dict:
    actor = await services.current_actor(session, actor)
    authorize(actor, "preference.read", owner_user_id=actor.user_id)
    value = await session.get(UserPreference, actor.user_id)
    return (
        {"revision": value.revision, "theme_mode": value.theme_mode}
        if value
        else {"revision": 1, "theme_mode": "default"}
    )


async def update_preferences(
    session: AsyncSession, actor: Principal, payload: PreferenceInput
) -> dict:
    actor = await services.current_actor(session, actor)
    authorize(actor, "preference.write", owner_user_id=actor.user_id)
    value = await session.get(UserPreference, actor.user_id, with_for_update=True)
    revision = value.revision if value else 1
    if revision != payload.expected_revision:
        raise DomainError(
            "REVISION_CONFLICT", "Appearance changed in another window; reload and retry.", 409
        )
    if value is None:
        value = UserPreference(user_id=actor.user_id, revision=revision, theme_mode="default")
        session.add(value)
    value.theme_mode = payload.theme_mode
    value.revision += 1
    from inspector.auth import _audit

    _audit(
        session, "preference.write", services.utc_now_us(), principal=actor, target_id=actor.user_id
    )
    await session.flush()
    return {"revision": value.revision, "theme_mode": value.theme_mode}


async def get_settings(session: AsyncSession, actor: Principal) -> dict:
    actor = await services.current_actor(session, actor)
    require_admin(actor)
    return settings_response(await settings_value(session))


async def update_settings(session: AsyncSession, actor: Principal, payload: SettingsInput) -> dict:
    from inspector.auth import _audit

    actor = await services.current_actor(session, actor)
    require_admin(actor)
    if not payload.branding.strip() or any(ord(c) < 32 or ord(c) == 127 for c in payload.branding):
        raise DomainError("INVALID_REQUEST", "Invalid product name.", 422)
    value = await settings_value(session)
    if value.revision != payload.expected_revision:
        raise DomainError("REVISION_CONFLICT", "Settings changed; reload and retry.", 409)
    value.branding = payload.branding.strip()
    value.default_theme_mode = payload.default_theme_mode
    value.revision += 1
    _audit(session, "settings.write", services.utc_now_us(), principal=actor)
    await session.flush()
    return settings_response(value)


async def project_viewer(session: AsyncSession, actor: Principal, project_id: str) -> dict:
    actor = await services.current_actor(session, actor)
    authorize(actor, "topology.read")
    project = await services.project_in_context(session, ProjectContext(project_id, actor.user_id))
    demo = await session.get(DemoSnapshot, project_id)
    state = await session.get(TopologyState, project_id)
    if state is None:
        raise DomainError("NOT_READY", "Topology initialization is required before serving.", 503)
    config = state.config
    subsystems = []
    for part in config["subsystems"]:
        servers = []
        for host in config["servers"]:
            if host["subsystem_id"] != part["id"]:
                continue
            processes = [
                {key: process[key] for key in ("id", "name", "description")} | {"log_path": None}
                for process in config["processes"]
                if process["server_id"] == host["id"]
            ]
            servers.append(
                {key: host[key] for key in ("id", "name", "description")} | {"processes": processes}
            )
        subsystems.append(
            {key: part[key] for key in ("id", "name", "description")} | {"servers": servers}
        )
    return ProjectViewerResponse(
        project_id=project.id,
        name=project.name,
        description=project.description,
        revision=project.revision,
        archived=project.archived,
        demo=demo is not None,
        subsystems=[DemoSubsystem.model_validate(item) for item in subsystems],
    ).model_dump()


async def seed_demo(session: AsyncSession, actor: Principal) -> None:
    """Protected CLI/test fixture only. Preserve all existing project IDs/data."""
    actor = await services.current_actor(session, actor)
    require_admin(actor)
    for index, label in enumerate(("Payments", "Orders")):
        project_id = f"demo-foundation-{'a' if index == 0 else 'b'}"
        from inspector.persistence.models import Project

        existing = await session.get(Project, project_id)
        if existing is not None:
            if await session.get(DemoSnapshot, project_id) is None:
                raise DomainError(
                    "DEMO_CONFLICT",
                    "Demo identity is already in use; existing data preserved.",
                    409,
                )
            continue
        project = await services.create_project(
            session,
            actor,
            f"[Synthetic demo] {label}",
            "Synthetic documentation only. No targets or live collection are configured.",
            project_id=project_id,
        )
        payload: dict[str, Any] = {"subsystems": []}
        for part, title in enumerate(("Gateway", "Processing")):
            # IDs intentionally repeat in the other project's snapshot.
            payload["subsystems"].append(
                {
                    "id": f"subsystem-{part}",
                    "name": f"{label} {title}",
                    "description": "Synthetic documentation. Health is unknown; no monitoring probes exist.",
                    "servers": [
                        {
                            "id": f"server-{part}",
                            "name": f"demo-{title.lower()}-01",
                            "description": "Synthetic server; no connection profile or credentials.",
                            "processes": [
                                {
                                    "id": f"process-{part}",
                                    "name": f"{title} service",
                                    "description": f"{label} synthetic process documentation. Collection is unavailable in this foundation stage.",
                                    "log_path": f"/var/log/demo/{title.lower()}.log",
                                }
                            ],
                        }
                    ],
                }
            )
        # Validate bounded presentation before persistence; this is never an uploaded config.
        safe = [DemoSubsystem.model_validate(item).model_dump() for item in payload["subsystems"]]
        session.add(DemoSnapshot(project_id=project.id, payload={"subsystems": safe}))
        await session.flush()
        # The explicit synthetic seed is now a real editable topology; this all
        # occurs within the original create transaction before revision 1 exists
        # for any external reader. Legacy presentation remains for old clients.
        from inspector.persistence.models import TopologySnapshot, TopologyState
        from inspector.topology import demo_config, normalize_rows, record_names, sync_identities

        value = demo_config(project, {"subsystems": safe})
        state = await session.get(TopologyState, project.id)
        snapshot = await session.get(TopologySnapshot, (project.id, project.revision))
        assert state is not None and snapshot is not None
        state.config, snapshot.config = value, value
        await sync_identities(session, project.id, value)
        await record_names(session, project.id, project.revision, None, value)
        await normalize_rows(session, project.id, value)
