"""Verify populated 0015 -> 0016 and rollback without inventing server connections."""

import asyncio
import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from verify_populated_upgrade import migrate, require_empty_mariadb
from verify_stage7_upgrade import seed

from inspector.config import parse_config
from inspector.database import SCHEMA_REVISION, check_schema, create_engine

LEGACY = "0015_remember_login"
BACKEND = Path(__file__).resolve().parents[2]


def guarded_configuration():
    if os.environ.get("SI_TEST_DISPOSABLE_MARIADB") != "1":
        raise RuntimeError("Explicit disposable MariaDB opt-in is required.")
    config_path = os.environ.get("INSPECTOR_TEST_CONFIG")
    migration_user = os.environ.get("SI_MIGRATION_DB_USERNAME")
    migration_file = os.environ.get("SI_MIGRATION_DB_PASSWORD_FILE")
    if not config_path or not migration_user or not migration_file:
        raise RuntimeError("Separate runtime and migration identities are required.")
    raw = Path(config_path).read_bytes()
    runtime = parse_config(raw, environment={})
    if not re.fullmatch(r"inspector_test_opt_upgrade_[a-z0-9_]+", runtime.database.name):
        raise RuntimeError("A fresh optional-connection upgrade disposable schema is required.")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("SI_DB_", "SI_MIGRATION_DB_"))
    }
    environment.update(
        SI_MIGRATION_DB_USERNAME=migration_user,
        SI_MIGRATION_DB_PASSWORD_FILE=migration_file,
        INSPECTOR_CONFIG_FILE=str(Path(config_path).resolve()),
    )
    migrator = parse_config(raw, environment=environment, migration=True)
    if (
        runtime.database.username == migration_user
        or Path(runtime.database.password_file).resolve() == Path(migration_file).resolve()
    ):
        raise RuntimeError("Runtime and migration identities must differ.")
    return runtime, migrator, environment


async def snapshot(config):
    engine = create_engine(config.database)
    try:
        async with async_sessionmaker(engine).begin() as session:
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
                rows = (await session.execute(text(f"SELECT * FROM `{name}`"))).mappings().all()
                result[name] = copy.deepcopy(
                    sorted([dict(row) for row in rows], key=lambda row: repr(sorted(row.items())))
                )
            return result
    finally:
        await engine.dispose()


async def verify_schema(config, *, nullable, head):
    engine = create_engine(config.database)
    try:
        async with engine.connect() as connection:
            if head:
                await check_schema(connection)
            value = await connection.scalar(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema=DATABASE() AND table_name='servers' "
                    "AND column_name='connection_id'"
                )
            )
            assert value == ("YES" if nullable else "NO")
            constraint = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.table_constraints "
                    "WHERE table_schema=DATABASE() AND table_name='servers' "
                    "AND constraint_name='fk_servers_scoped_connection' "
                    "AND constraint_type='FOREIGN KEY'"
                )
            )
            assert constraint == 1
    finally:
        await engine.dispose()


async def change_connection(config, value):
    engine = create_engine(config.database)
    try:
        async with async_sessionmaker(engine).begin() as session:
            await session.execute(
                text(
                    "UPDATE servers SET connection_id=:connection "
                    "WHERE project_id='retained-a' AND id='h-ingest-a'"
                ),
                {"connection": value},
            )
    finally:
        await engine.dispose()


def downgrade(environment):
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "downgrade", LEGACY],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        timeout=120,
        check=False,
    )


def main():
    phase = "guard"
    try:
        runtime, migrator, environment = guarded_configuration()
        asyncio.run(require_empty_mariadb(migrator))
        phase = "seed_populated_legacy_schema"
        migrate(LEGACY, environment)
        asyncio.run(seed(runtime, LEGACY))
        before = asyncio.run(snapshot(runtime))
        connection = next(
            row["connection_id"]
            for row in before["servers"]
            if row["project_id"] == "retained-a" and row["id"] == "h-ingest-a"
        )
        phase = "upgrade_preserves_all_existing_rows"
        migrate("head", environment)
        asyncio.run(verify_schema(runtime, nullable=True, head=True))
        assert asyncio.run(snapshot(runtime)) == before
        phase = "downgrade_refuses_unconnected_server_without_data_change"
        asyncio.run(change_connection(runtime, None))
        disconnected = asyncio.run(snapshot(runtime))
        assert disconnected != before
        refused = downgrade(environment)
        assert refused.returncode != 0
        assert b"Assign connections to all servers" in refused.stderr
        asyncio.run(verify_schema(runtime, nullable=True, head=True))
        assert asyncio.run(snapshot(runtime)) == disconnected
        phase = "explicit_assignment_then_safe_downgrade"
        asyncio.run(change_connection(runtime, connection))
        assert asyncio.run(snapshot(runtime)) == before
        assert downgrade(environment).returncode == 0
        asyncio.run(verify_schema(runtime, nullable=False, head=False))
        assert asyncio.run(snapshot(runtime)) == before
        phase = "reupgrade"
        migrate("head", environment)
        asyncio.run(verify_schema(runtime, nullable=True, head=True))
        assert asyncio.run(snapshot(runtime)) == before
        print(
            json.dumps(
                {
                    "passed": True,
                    "from_revision": LEGACY,
                    "to_revision": SCHEMA_REVISION,
                    "existing_tables_preserved": len(before),
                    "scoped_foreign_key_preserved": True,
                    "null_connection_accepted": True,
                    "downgrade_refusal_preserves_data": True,
                    "explicit_assignment_downgrade_reupgrade_verified": True,
                }
            )
        )
    except Exception:
        print(
            json.dumps(
                {"passed": False, "failed_phase": phase, "reason": "Disposable schema retained."}
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
