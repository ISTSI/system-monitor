"""Verify additive language migration on a populated disposable Stage 07 schema."""

import asyncio
import json
import os
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from verify_populated_upgrade import migrate, require_empty_mariadb
from verify_stage7_upgrade import seed, snapshot

from inspector.config import parse_config
from inspector.database import SCHEMA_REVISION, check_schema, create_engine
from inspector.foundation import initialize_settings

STAGE_SEVEN = "0013_inventory"
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
    if not re.fullmatch(r"inspector_test_lang_upgrade_[a-z0-9_]+", runtime.database.name):
        raise RuntimeError("A fresh language-upgrade disposable schema is required.")
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


async def verify(config, before, *, head):
    engine = create_engine(config.database)
    try:
        async with engine.connect() as connection:
            if head:
                await check_schema(connection)
        async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
            assert await snapshot(session, before) == before
            if not head:
                return
            assert (
                await session.scalar(text("SELECT default_language FROM application_settings"))
                == "en"
            )
            assert await session.scalar(text("SELECT language FROM user_preferences")) == "default"
            # Startup never reapplies bootstrap language over the persisted default.
            initialized = await initialize_settings(session, replace(config, default_language="pl"))
            assert initialized.default_language == "en"
            for table, field, invalid in (
                ("application_settings", "default_language", "default"),
                ("application_settings", "default_language", "PL"),
                ("user_preferences", "language", "de"),
                ("user_preferences", "language", "PL"),
            ):
                try:
                    async with session.begin_nested():
                        await session.execute(
                            text(f"UPDATE {table} SET {field}=:invalid"), {"invalid": invalid}
                        )
                except DBAPIError:
                    pass
                else:
                    raise AssertionError("MariaDB accepted an unsupported language.")
    finally:
        await engine.dispose()


def downgrade(environment):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(BACKEND / "alembic.ini"),
            "downgrade",
            STAGE_SEVEN,
        ],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Disposable downgrade failed; protected diagnostics suppressed.")


def main():
    phase = "guard"
    try:
        runtime, migrator, environment = guarded_configuration()
        asyncio.run(require_empty_mariadb(migrator))
        phase = "seed_populated_stage_seven"
        migrate(STAGE_SEVEN, environment)
        before = asyncio.run(seed(runtime, STAGE_SEVEN))
        phase = "upgrade_preserves_rows_and_checks_language_constraints"
        migrate("head", environment)
        asyncio.run(verify(runtime, before, head=True))
        phase = "downgrade_preserves_original_rows"
        downgrade(environment)
        asyncio.run(verify(runtime, before, head=False))
        phase = "reupgrade"
        migrate("head", environment)
        asyncio.run(verify(runtime, before, head=True))
        print(
            json.dumps(
                {
                    "passed": True,
                    "from_revision": STAGE_SEVEN,
                    "to_revision": SCHEMA_REVISION,
                    "existing_tables_preserved": len(before),
                    "existing_rows_preserved": True,
                    "language_constraints_verified": True,
                    "downgrade_and_reupgrade_verified": True,
                }
            )
        )
    except Exception:
        print(
            json.dumps(
                {
                    "passed": False,
                    "failed_phase": phase,
                    "reason": "Disposable migration check failed; schema retained.",
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
