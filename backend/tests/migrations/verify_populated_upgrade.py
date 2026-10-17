"""Opt-in verification of a populated Stage 01 schema upgrading to Stage 02.

Run directly, never against an existing schema. The required schema name is
inspector_test_s2_upgrade_<suffix>. No drop, downgrade or remote SSH is used.
Only safe counts and boolean results are printed; account verifiers stay in RAM.
"""

import asyncio
import copy
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from inspector import auth
from inspector.app import create_app
from inspector.config import Config, parse_config
from inspector.database import SCHEMA_REVISION, check_schema, create_engine
from inspector.domain import Principal
from inspector.persistence.models import (
    ApplicationSetting,
    DemoSnapshot,
    EntityIdentity,
    EntityNameSnapshot,
    Flow,
    Process,
    Project,
    ProjectRevision,
    Server,
    TopologySnapshot,
    TopologyState,
    User,
    UserPreference,
    Workspace,
)
from inspector.security import verify_password

BACKEND = Path(__file__).resolve().parents[2]
STAGE_ONE = "0002_foundation_preferences"


def guarded_configuration() -> tuple[Config, Config, dict[str, str]]:
    if os.environ.get("SI_TEST_DISPOSABLE_MARIADB") != "1":
        raise RuntimeError("Explicit disposable MariaDB opt-in is required.")
    config_path = os.environ.get("INSPECTOR_TEST_CONFIG")
    migration_user = os.environ.get("SI_MIGRATION_DB_USERNAME")
    migration_file = os.environ.get("SI_MIGRATION_DB_PASSWORD_FILE")
    if not config_path or not migration_user or not migration_file:
        raise RuntimeError("Runtime configuration and separate migration identity are required.")
    raw = Path(config_path).read_bytes()
    runtime = parse_config(raw, environment={})
    migration_environment = {
        "SI_MIGRATION_DB_USERNAME": migration_user,
        "SI_MIGRATION_DB_PASSWORD_FILE": migration_file,
    }
    migrator = parse_config(raw, environment=migration_environment, migration=True)
    if not re.fullmatch(r"inspector_test_s2_upgrade_[a-z0-9_]+", runtime.database.name):
        raise RuntimeError("A newly provisioned inspector_test_s2_upgrade_ schema is required.")
    if (
        runtime.database.username == migration_user
        or Path(runtime.database.password_file).resolve() == Path(migration_file).resolve()
    ):
        raise RuntimeError("Runtime and migration identities must be separate.")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SI_DB_") and not key.startswith("SI_MIGRATION_DB_")
    }
    environment.update(migration_environment)
    environment["INSPECTOR_CONFIG_FILE"] = str(Path(config_path).resolve())
    return runtime, migrator, environment


async def require_empty_mariadb(config: Config) -> None:
    engine = create_engine(config.database, dedicated=True)
    try:
        async with engine.connect() as connection:
            version = str(await connection.scalar(text("SELECT VERSION()")))
            if "mariadb" not in version.lower():
                raise RuntimeError("The disposable endpoint must be MariaDB.")
            count = await connection.scalar(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=:name"),
                {"name": config.database.name},
            )
            if count:
                raise RuntimeError("Disposable schema is not empty; no migration was attempted.")
    finally:
        await engine.dispose()


def migrate(target: str, environment: dict[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "upgrade", target],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Disposable schema migration failed; protected diagnostics suppressed.")


def payload(label: str) -> dict:
    return {
        "subsystems": [
            {
                "id": "shared-subsystem",
                "name": f"Retained subsystem {label}",
                "description": f"Preserved **subsystem** documentation {label}.",
                "servers": [
                    {
                        "id": "shared-server",
                        "name": "repeated-host-name",
                        "description": f"Preserved server documentation {label}.",
                        "processes": [
                            {
                                "id": f"shared-process-{index}",
                                "name": f"Repeated process {index}",
                                "description": f"## Retained process {index}\nPrivate to synthetic system {label}.",
                                "log_path": f"/var/log/demo/{label.lower()}/process-{index}.log",
                            }
                            for index in (1, 2)
                        ],
                    }
                ],
            }
        ]
    }


async def table_snapshot(session: AsyncSession, model: Any, *order: Any) -> list[dict]:
    rows = (await session.scalars(select(model).order_by(*order))).all()
    return [
        copy.deepcopy({column.key: getattr(row, column.key) for column in model.__table__.columns})
        for row in rows
    ]


async def original_state(session: AsyncSession) -> dict:
    # Snapshot only columns present in Stage 01. The current ORM model also has
    # columns introduced by later migrations and cannot query the old schema.
    settings = await session.execute(
        text(
            "SELECT id, revision, branding, default_theme_mode "
            "FROM application_settings ORDER BY id"
        )
    )
    return {
        "users": await table_snapshot(session, User, User.id),
        "preferences": await table_snapshot(session, UserPreference, UserPreference.user_id),
        "settings": copy.deepcopy([dict(row) for row in settings.mappings()]),
        "projects": await table_snapshot(session, Project, Project.id),
        "revisions": await table_snapshot(
            session, ProjectRevision, ProjectRevision.project_id, ProjectRevision.revision
        ),
        "demos": await table_snapshot(session, DemoSnapshot, DemoSnapshot.project_id),
        "workspaces": await table_snapshot(session, Workspace, Workspace.project_id, Workspace.id),
    }


async def seed_stage_one(config: Config) -> tuple[dict, dict[str, str]]:
    engine = create_engine(config.database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    passwords: dict[str, str] = {}
    try:
        async with sessions.begin() as session:
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
            assert revision == STAGE_ONE
            password = secrets.token_urlsafe(32)
            admin = await auth.bootstrap_admin(
                session, f"upgrade-admin-{uuid4()}", "Retained synthetic Administrator", password
            )
            passwords[admin.id] = password
            actor = Principal(admin.id, admin.role, admin.auth_version)
            password = secrets.token_urlsafe(32)
            inspector = await auth.create_user(
                session,
                actor,
                f"upgrade-inspector-{uuid4()}",
                "Retained synthetic Inspector",
                password,
            )
            passwords[inspector.id] = password
            session.add_all(
                [
                    UserPreference(user_id=admin.id, revision=5, theme_mode="light"),
                    UserPreference(user_id=inspector.id, revision=9, theme_mode="system"),
                ]
            )
            await session.execute(
                text(
                    "INSERT INTO application_settings "
                    "(id, revision, branding, default_theme_mode) "
                    "VALUES (:id, :revision, :branding, :default_theme_mode)"
                ),
                {
                    "id": 1,
                    "revision": 4,
                    "branding": "Retained Synthetic Inspector",
                    "default_theme_mode": "light",
                },
            )
            now = time.time_ns() // 1000
            for label in ("A", "B"):
                project_id = f"retained-project-{label.lower()}-{uuid4()}"
                session.add(
                    Project(
                        id=project_id,
                        name=f"Retained system {label}",
                        description=f"Preserved project documentation {label}.",
                        revision=2,
                        archived=False,
                    )
                )
                await session.flush()
                session.add_all(
                    [
                        ProjectRevision(
                            project_id=project_id,
                            revision=1,
                            name=f"Original system {label}",
                            description=f"Original description {label}.",
                        ),
                        ProjectRevision(
                            project_id=project_id,
                            revision=2,
                            name=f"Retained system {label}",
                            description=f"Preserved project documentation {label}.",
                        ),
                        DemoSnapshot(project_id=project_id, payload=payload(label)),
                    ]
                )
                await session.flush()
                session.add(
                    Workspace(
                        project_id=project_id,
                        id="repeated-workspace",
                        owner_user_id=inspector.id,
                        opened_revision=1,
                        revision=7,
                        state="active",
                        created_us=now,
                        expires_us=now + 300_000_000,
                    )
                )
            await session.flush()
            before = await original_state(session)
        return before, passwords
    finally:
        await engine.dispose()


async def verify_upgraded(config: Config, before: dict, passwords: dict[str, str]) -> dict:
    engine = create_engine(config.database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.connect() as connection:
            await check_schema(connection)
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(TopologyState)) == 0
            settings = await session.get(ApplicationSetting, 1)
            assert settings is not None and settings.additional_security_measures is True
        with tempfile.TemporaryDirectory(prefix="si-s2-upgrade-") as state_dir:
            app = create_app(replace(config, state_dir=state_dir))
            async with app.router.lifespan_context(app):
                async with sessions() as session:
                    after = await original_state(session)
                    for key in (
                        "users",
                        "preferences",
                        "settings",
                        "projects",
                        "revisions",
                        "demos",
                    ):
                        assert after[key] == before[key]
                    settings = await session.get(ApplicationSetting, 1)
                    assert settings is not None and settings.additional_security_measures is True
                    expected_workspaces = copy.deepcopy(before["workspaces"])
                    for workspace in expected_workspaces:
                        workspace.update(state="detached", revision=workspace["revision"] + 1)
                    assert after["workspaces"] == expected_workspaces
                    for row in after["users"]:
                        assert await verify_password(row["password_hash"], passwords[row["id"]])
                    project_ids = {row["id"] for row in before["projects"]}
                    states = (
                        await session.scalars(
                            select(TopologyState).order_by(TopologyState.project_id)
                        )
                    ).all()
                    assert {state.project_id for state in states} == project_ids
                    for state in states:
                        source = next(
                            row for row in before["demos"] if row["project_id"] == state.project_id
                        )["payload"]
                        assert state.config["project"]["revision"] == 2
                        assert state.undo_stack == [] and state.redo_stack == []
                        assert (
                            state.config["subsystems"][0]["description"]
                            == source["subsystems"][0]["description"]
                        )
                        assert (
                            state.config["servers"][0]["description"]
                            == source["subsystems"][0]["servers"][0]["description"]
                        )
                        host = await session.get(Server, (state.project_id, "shared-server"))
                        assert host is not None and host.subsystem_id == "shared-subsystem"
                        for index in (1, 2):
                            process = await session.get(
                                Process, (state.project_id, f"shared-process-{index}")
                            )
                            assert process is not None and process.server_id == "shared-server"
                            original = source["subsystems"][0]["servers"][0]["processes"][index - 1]
                            assert process.payload["description"] == original["description"]
                            assert (
                                process.payload["log_source"]["active_path"] == original["log_path"]
                            )
                        flow = await session.get(Flow, (state.project_id, "flow-demo-0"))
                        assert flow is not None and (
                            flow.source_process_id,
                            flow.target_process_id,
                        ) == ("shared-process-1", "shared-process-2")
                        snapshot = await session.get(TopologySnapshot, (state.project_id, 2))
                        assert snapshot is not None and snapshot.config == state.config
                    assert (
                        states[0].config["processes"][0]["description"]
                        != states[1].config["processes"][0]["description"]
                    )
                    counts = {}
                    for model in (
                        EntityIdentity,
                        EntityNameSnapshot,
                        Process,
                        Server,
                        TopologySnapshot,
                    ):
                        counts[model.__tablename__] = await session.scalar(
                            select(func.count()).select_from(model)
                        )
                    assert counts == {
                        "entity_identities": 16,
                        "topology_entity_names": 16,
                        "processes": 4,
                        "servers": 2,
                        "topology_snapshots": 2,
                    }
        return {
            "passed": True,
            "from_revision": STAGE_ONE,
            "to_revision": SCHEMA_REVISION,
            "projects_preserved": 2,
            "accounts_preserved": 2,
            "workspaces_detached": 2,
            "scoped_counts": counts,
            "password_verification_preserved": True,
            "preferences_preserved": True,
            "setting_default_preserved": True,
            "metadata_and_documentation_preserved": True,
        }
    finally:
        await engine.dispose()


def main() -> None:
    phase = "configuration_guard"
    try:
        runtime, migrator, environment = guarded_configuration()
        phase = "empty_mariadb_guard"
        asyncio.run(require_empty_mariadb(migrator))
        phase = "migrate_stage_one"
        migrate(STAGE_ONE, environment)
        phase = "seed_stage_one"
        before, passwords = asyncio.run(seed_stage_one(runtime))
        phase = "upgrade_to_head"
        migrate("head", environment)
        phase = "verify_preservation_and_startup"
        result = asyncio.run(verify_upgraded(runtime, before, passwords))
    except Exception:
        # Neither driver exception parameters nor account snapshots may appear
        # in terminal output. Retain the schema for explicit operator diagnosis.
        print(
            json.dumps(
                {
                    "passed": False,
                    "failed_phase": phase,
                    "reason": "Guard, migration or populated-upgrade assertion failed; schema retained.",
                }
            )
        )
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
