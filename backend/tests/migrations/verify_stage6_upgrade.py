"""Verify a populated 0009_live -> head upgrade in a new isolated MariaDB schema."""

import asyncio
import copy
import hashlib
import json
import os
import re
import secrets
import tempfile
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from verify_populated_upgrade import migrate, require_empty_mariadb

from inspector import auth, services, topology
from inspector.config import parse_config
from inspector.database import SCHEMA_REVISION, check_schema, create_engine
from inspector.domain import Principal
from inspector.persistence.models import (
    HistoryEvent,
    HistoryJob,
    HistorySource,
    TopologyState,
    Workspace,
)

ROOT = Path(__file__).resolve().parents[3]
STAGE_FIVE = "0009_live"


def guarded_configuration():
    if os.environ.get("SI_TEST_DISPOSABLE_MARIADB") != "1":
        raise RuntimeError("Explicit disposable MariaDB opt-in is required.")
    path = os.environ.get("INSPECTOR_TEST_CONFIG")
    migration_user = os.environ.get("SI_MIGRATION_DB_USERNAME")
    migration_file = os.environ.get("SI_MIGRATION_DB_PASSWORD_FILE")
    if not path or not migration_user or not migration_file:
        raise RuntimeError("Separate runtime and migration identities are required.")
    raw = Path(path).read_bytes()
    runtime = parse_config(raw, environment={})
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SI_DB_") and not key.startswith("SI_MIGRATION_DB_")
    }
    environment.update(
        SI_MIGRATION_DB_USERNAME=migration_user,
        SI_MIGRATION_DB_PASSWORD_FILE=migration_file,
        INSPECTOR_CONFIG_FILE=str(Path(path).resolve()),
    )
    migrator = parse_config(raw, environment=environment, migration=True)
    if not re.fullmatch(r"inspector_test_s6_upgrade_[a-z0-9_]+", runtime.database.name):
        raise RuntimeError("A newly provisioned Stage 06 upgrade schema is required.")
    if (
        runtime.database.username == migration_user
        or Path(runtime.database.password_file).resolve() == Path(migration_file).resolve()
    ):
        raise RuntimeError("Runtime and migration identities must differ.")
    return runtime, migrator, environment


async def snapshot(session, tables=None):
    if tables is None:
        tables = (
            await session.scalars(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema=DATABASE() AND table_name <> 'alembic_version' "
                    "ORDER BY table_name"
                )
            )
        ).all()
    result = {}
    for name in tables:
        if not re.fullmatch(r"[a-z][a-z0-9_]+", name):
            raise RuntimeError("Unexpected table identity.")
        # Compare the full legacy shape; additive language columns are asserted separately.
        columns = {
            "application_settings": "id, revision, branding, default_theme_mode, additional_security_measures",
            "user_preferences": "user_id, revision, theme_mode",
        }.get(name, "*")
        rows = (await session.execute(text(f"SELECT {columns} FROM `{name}`"))).mappings().all()
        result[name] = copy.deepcopy(
            sorted([dict(row) for row in rows], key=lambda row: repr(sorted(row.items())))
        )
    return result


async def seed(config):
    engine = create_engine(config.database)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
            assert (
                await session.scalar(text("SELECT version_num FROM alembic_version")) == STAGE_FIVE
            )
            administrator = await auth.bootstrap_admin(
                session,
                "upgrade-administrator",
                "Synthetic retained administrator",
                secrets.token_urlsafe(32),
            )
            actor = Principal(administrator.id, administrator.role, administrator.auth_version)
            inspector = await auth.create_user(
                session,
                actor,
                "upgrade-inspector",
                "Synthetic retained inspector",
                secrets.token_urlsafe(32),
            )
            await session.execute(
                text(
                    "INSERT INTO application_settings "
                    "(id, revision, branding, default_theme_mode, additional_security_measures) "
                    "VALUES (1, 1, 'System Inspector', :theme, 0)"
                ),
                {"theme": config.default_theme_mode},
            )
            await session.execute(
                text(
                    "INSERT INTO user_preferences (user_id, revision, theme_mode) "
                    "VALUES (:user_id, 4, 'light')"
                ),
                {"user_id": inspector.id},
            )
            now = time.time_ns() // 1000
            for project_id in ("retained-a", "retained-b"):
                project = await services.create_project(
                    session, actor, project_id, "Retained notes", project_id=project_id
                )
                document = json.loads((ROOT / "examples/project.example.json").read_text("utf-8"))
                document["project"].update(id=project_id, name=project_id, revision=1)
                state = await session.get(TopologyState, project_id)
                await topology.save(
                    session,
                    actor,
                    project,
                    state,
                    document,
                    confirmed_deletions=False,
                    reparent=False,
                )
                session.add(
                    Workspace(
                        project_id=project_id,
                        id="retained-workspace",
                        owner_user_id=inspector.id,
                        opened_revision=2,
                        revision=1,
                        state="detached",
                        created_us=now,
                        expires_us=now + 300_000_000,
                    )
                )
                await session.flush()
                session.add(
                    HistoryJob(
                        project_id=project_id,
                        id="retained-capture",
                        workspace_id="retained-workspace",
                        owner_user_id=inspector.id,
                        auth_version=inspector.auth_version,
                        auth_session_hash="0" * 64,
                        config_revision=2,
                        config_snapshot=document,
                        process_ids=["p-ingest-a"],
                        from_us=0,
                        to_us=2_000_000,
                        status="completed",
                        snapshot_revision=1,
                        event_count=1,
                        parse_issue_count=0,
                        downloaded_bytes=5,
                        expanded_bytes=5,
                        created_us=now,
                        errors=[],
                    )
                )
                await session.flush()
                session.add(
                    HistorySource(
                        project_id=project_id,
                        job_id="retained-capture",
                        id="retained-source",
                        process_id="p-ingest-a",
                        remote_path="/var/log/inspector-demo/ingest/app.log",
                        kind="plain",
                        cache_name="retained-cache",
                        checksum=hashlib.sha256(b"data\n").hexdigest(),
                        status="completed",
                        event_count=1,
                        downloaded_bytes=5,
                        expanded_bytes=5,
                        manifest={"retained": True},
                    )
                )
                await session.flush()
                session.add(
                    HistoryEvent(
                        project_id=project_id,
                        job_id="retained-capture",
                        event_id="retained-event",
                        process_id="p-ingest-a",
                        source_revision_id="retained-source",
                        capture_seq=1,
                        timestamp_us=1_000_000,
                        member_order=0,
                        byte_start=0,
                        raw_line="data",
                        payload={"project_id": project_id, "retained": True},
                    )
                )
            await session.flush()
            return await snapshot(session)
    finally:
        await engine.dispose()


async def verify(config, before):
    engine = create_engine(config.database)
    try:
        async with engine.connect() as connection:
            await check_schema(connection)
        async with async_sessionmaker(engine)() as session:
            assert await snapshot(session, before) == before
            assert await session.scalar(text("SELECT COUNT(*) FROM history_events")) == 2
            assert await session.scalar(text("SELECT COUNT(*) FROM users")) == 2
            assert (
                await session.scalar(text("SELECT default_language FROM application_settings"))
                == "en"
            )
            assert await session.scalar(text("SELECT language FROM user_preferences")) == "default"
    finally:
        await engine.dispose()


def main():
    phase = "configuration_guard"
    try:
        runtime, migrator, environment = guarded_configuration()
        phase = "empty_mariadb_guard"
        asyncio.run(require_empty_mariadb(migrator))
        phase = "migrate_stage_five"
        migrate(STAGE_FIVE, environment)
        phase = "seed_populated_stage_five"
        before = asyncio.run(seed(runtime))
        with tempfile.TemporaryDirectory(prefix="si-s6-upgrade-") as directory:
            cache = Path(directory) / "retained-cache"
            cache.write_bytes(b"data\n")
            phase = "upgrade_to_head"
            migrate("head", environment)
            phase = "verify_all_existing_rows_and_raw_bytes"
            asyncio.run(verify(runtime, before))
            assert cache.read_bytes() == b"data\n"
        print(
            json.dumps(
                {
                    "passed": True,
                    "from_revision": STAGE_FIVE,
                    "to_revision": SCHEMA_REVISION,
                    "existing_tables_preserved": len(before),
                    "projects_preserved": 2,
                    "accounts_preserved": 2,
                    "scoped_identical_event_ids_preserved": 2,
                    "all_existing_rows_preserved": True,
                    "raw_bytes_unchanged": True,
                }
            )
        )
    except Exception:
        print(
            json.dumps(
                {
                    "passed": False,
                    "failed_phase": phase,
                    "reason": "Guard, migration or preservation assertion failed; synthetic schema retained.",
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
