"""Exercise populated 0014 -> 0015, ordinary-session preservation and safe rollback."""

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from verify_populated_upgrade import migrate, require_empty_mariadb
from verify_stage7_upgrade import seed, snapshot

from inspector.config import parse_config
from inspector.database import SCHEMA_REVISION, check_schema, create_engine

LEGACY = "0014_languages"
BACKEND = Path(__file__).resolve().parents[2]
SESSION_COLUMNS = (
    "token_hash, user_id, auth_version, csrf_hash, created_us, last_seen_us, expires_us"
)


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
    if not re.fullmatch(r"inspector_test_rem_upgrade_[a-z0-9_]+", runtime.database.name):
        raise RuntimeError("A fresh remember-login upgrade disposable schema is required.")
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


async def seed_legacy_login(config):
    # The current ORM intentionally requires the new schema. Seed legacy columns
    # directly to verify a real pre-upgrade session rather than a current-model row.
    engine = create_engine(config.database)
    try:
        async with async_sessionmaker(engine).begin() as session:
            user_id = await session.scalar(text("SELECT id FROM users ORDER BY id LIMIT 1"))
            now = time.time_ns() // 1000
            await session.execute(
                text(
                    f"INSERT INTO auth_sessions ({SESSION_COLUMNS}) "
                    "VALUES (:token, :user, 1, :csrf, :created, :seen, :expires)"
                ),
                {
                    "token": "a" * 64,
                    "user": user_id,
                    "csrf": "b" * 64,
                    "created": now,
                    "seen": now + 1,
                    "expires": now + 28_800_000_000,
                },
            )
            return dict(
                (await session.execute(text(f"SELECT {SESSION_COLUMNS} FROM auth_sessions")))
                .mappings()
                .one()
            )
    finally:
        await engine.dispose()


async def verify(config, before, legacy, *, head):
    engine = create_engine(config.database)
    try:
        async with engine.connect() as connection:
            if head:
                await check_schema(connection)
        async with async_sessionmaker(engine).begin() as session:
            # The original topology/accounts/preferences/investigations remain exact.
            assert await snapshot(session, before) == before
            rows = (
                (await session.execute(text(f"SELECT {SESSION_COLUMNS} FROM auth_sessions")))
                .mappings()
                .all()
            )
            assert [dict(row) for row in rows] == [legacy]
            if not head:
                return
            assert await session.scalar(text("SELECT remember_me FROM auth_sessions")) == 0
            try:
                async with session.begin_nested():
                    await session.execute(text("UPDATE auth_sessions SET remember_me=2"))
            except DBAPIError:
                pass
            else:
                raise AssertionError("MariaDB accepted a nonboolean remember choice.")
    finally:
        await engine.dispose()


async def add_remembered_login(config, legacy):
    engine = create_engine(config.database)
    try:
        async with async_sessionmaker(engine).begin() as session:
            await session.execute(
                text(
                    f"INSERT INTO auth_sessions ({SESSION_COLUMNS}, remember_me) "
                    "VALUES (:token_hash, :user_id, :auth_version, :csrf_hash, "
                    ":created_us, :last_seen_us, :expires_us, 1)"
                ),
                {**legacy, "token_hash": "c" * 64},
            )
    finally:
        await engine.dispose()


def downgrade(environment):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "downgrade", LEGACY],
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
        phase = "seed_populated_legacy_schema"
        migrate(LEGACY, environment)
        before = asyncio.run(seed(runtime, LEGACY))
        # Keep the original tables' snapshot, adding the legacy session separately.
        before.pop("auth_sessions")
        legacy = asyncio.run(seed_legacy_login(runtime))
        phase = "upgrade_preserves_ordinary_sessions"
        migrate("head", environment)
        asyncio.run(verify(runtime, before, legacy, head=True))
        asyncio.run(add_remembered_login(runtime, legacy))
        phase = "downgrade_revokes_only_remembered_sessions"
        downgrade(environment)
        asyncio.run(verify(runtime, before, legacy, head=False))
        phase = "reupgrade"
        migrate("head", environment)
        asyncio.run(verify(runtime, before, legacy, head=True))
        print(
            json.dumps(
                {
                    "passed": True,
                    "from_revision": LEGACY,
                    "to_revision": SCHEMA_REVISION,
                    "existing_rows_preserved": True,
                    "legacy_session_policy_preserved": True,
                    "remember_constraint_verified": True,
                    "downgrade_revocation_verified": True,
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
