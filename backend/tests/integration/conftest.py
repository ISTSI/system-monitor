"""Real MariaDB tests, gated before any connection or migration is attempted.

Provision an EMPTY schema named inspector_test_<suffix>, restricted runtime
credentials, and a separate migration account. Set SI_TEST_DISPOSABLE_MARIADB=1,
INSPECTOR_TEST_CONFIG, SI_MIGRATION_DB_USERNAME and
SI_MIGRATION_DB_PASSWORD_FILE. This suite never drops a schema or existing data.
An already populated schema is refused; use a newly provisioned disposable one
for a later run. Missing opt-in/configuration is reported as a skip, not a pass.
"""

import asyncio
import os
import secrets
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from inspector import auth, services
from inspector.app import create_app
from inspector.config import Config, parse_config
from inspector.database import check_schema, create_engine
from inspector.domain import Principal
from inspector.errors import DomainError
from inspector.persistence.models import Workspace

BACKEND = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Account:
    username: str
    password: str = field(repr=False)
    principal: Principal


@dataclass
class Database:
    config: Config
    sessions: async_sessionmaker[AsyncSession]
    administrator: Account
    bootstrap_outcomes: tuple[str, ...]


@dataclass
class Foundation:
    database: Database
    config: Config
    app: FastAPI
    alice: Account
    bob: Account
    project_a: str
    project_b: str

    @asynccontextmanager
    async def client(
        self, account: Account | None = None, *, cookies: httpx.Cookies | None = None
    ) -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url=self.config.public_origin,
            headers={"Origin": self.config.public_origin},
            cookies=cookies,
        ) as client:
            if account is not None:
                preflight = await client.get("/api/v1/auth/csrf")
                assert preflight.status_code == 200
                response = await client.post(
                    "/api/v1/auth/login",
                    json={"username": account.username, "password": account.password},
                    headers={"x-csrf-token": preflight.json()["csrf_token"]},
                )
                assert response.status_code == 200
                client.headers["x-csrf-token"] = response.json()["csrf_token"]
            elif cookies is not None:
                response = await client.get("/api/v1/auth/csrf")
                assert response.status_code == 200
                client.headers["x-csrf-token"] = response.json()["csrf_token"]
            yield client


async def _require_empty_mariadb(config: Config) -> None:
    engine = create_engine(config.database, dedicated=True)
    try:
        async with engine.connect() as connection:
            version = str(await connection.scalar(text("SELECT VERSION()")))
            if "mariadb" not in version.lower():
                pytest.fail("Integration endpoint is not MariaDB; no migration was attempted.")
            count = await connection.scalar(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = :schema"),
                {"schema": config.database.name},
            )
            if count:
                pytest.fail(
                    "Disposable integration schema is not empty; no existing tables/data were changed. "
                    "Provision a new empty inspector_test_ schema."
                )
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def migrated_config() -> Config:
    if os.environ.get("SI_TEST_DISPOSABLE_MARIADB") != "1":
        pytest.skip(
            "Actual MariaDB integration not run: SI_TEST_DISPOSABLE_MARIADB=1 opt-in is absent."
        )
    config_path = os.environ.get("INSPECTOR_TEST_CONFIG")
    if not config_path:
        pytest.skip("Actual MariaDB integration not run: INSPECTOR_TEST_CONFIG is absent.")
    migration_user = os.environ.get("SI_MIGRATION_DB_USERNAME")
    migration_password_file = os.environ.get("SI_MIGRATION_DB_PASSWORD_FILE")
    if not migration_user or not migration_password_file:
        pytest.skip(
            "Actual MariaDB integration not run: separate SI_MIGRATION_DB_USERNAME and "
            "SI_MIGRATION_DB_PASSWORD_FILE are required."
        )
    raw = Path(config_path).read_bytes()
    # Unrelated process-wide runtime overrides must never redirect a test.
    runtime = parse_config(raw, environment={})
    migration_environment = {
        "SI_MIGRATION_DB_USERNAME": migration_user,
        "SI_MIGRATION_DB_PASSWORD_FILE": migration_password_file,
    }
    migrator = parse_config(raw, environment=migration_environment, migration=True)
    if not runtime.database.name.startswith("inspector_test_"):
        pytest.fail("Refusing integration schema without the required inspector_test_ prefix.")
    if migration_user == runtime.database.username:
        pytest.fail("Integration runtime and migration database users must be distinct.")
    if Path(migration_password_file).resolve() == Path(runtime.database.password_file).resolve():
        pytest.fail("Integration runtime and migration password files must be distinct.")
    asyncio.run(_require_empty_mariadb(migrator))
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SI_DB_") and not key.startswith("SI_MIGRATION_DB_")
    }
    environment.update(migration_environment)
    environment["INSPECTOR_CONFIG_FILE"] = str(Path(config_path).resolve())
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "upgrade", "head"],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        # Database exception text may contain protected endpoint/account details.
        pytest.fail(f"Explicit disposable MariaDB migration failed (exit {result.returncode}).")
    return runtime


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def database(migrated_config: Config) -> AsyncIterator[Database]:
    engine = create_engine(migrated_config.database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.connect() as connection:
            await check_schema(connection)

        async def attempt_first_administrator() -> Account | str:
            username, password = f"admin-{uuid4()}", secrets.token_urlsafe(24)
            try:
                async with sessions.begin() as session:
                    user = await auth.bootstrap_admin(
                        session, username, "Synthetic Administrator", password
                    )
                    return Account(
                        username, password, Principal(user.id, user.role, user.auth_version)
                    )
            except DomainError as error:
                return error.code

        attempts = await asyncio.gather(
            attempt_first_administrator(), attempt_first_administrator()
        )
        successes = [attempt for attempt in attempts if isinstance(attempt, Account)]
        denials = [attempt for attempt in attempts if isinstance(attempt, str)]
        assert len(successes) == 1, "Concurrent bootstrap must produce exactly one Administrator."
        assert denials == ["BOOTSTRAP_CLOSED"]
        yield Database(migrated_config, sessions, successes[0], ("success", *denials))
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def foundation(database: Database, tmp_path: Path) -> AsyncIterator[Foundation]:
    accounts = []
    async with database.sessions.begin() as session:
        for label in ("Alice", "Bob"):
            username, password = f"{label.lower()}-{uuid4()}", secrets.token_urlsafe(24)
            user = await auth.create_user(
                session, database.administrator.principal, username, f"Synthetic {label}", password
            )
            accounts.append(
                Account(username, password, Principal(user.id, user.role, user.auth_version))
            )
        project_a = await services.create_project(
            session, database.administrator.principal, "Collision system", "Synthetic A"
        )
        project_b = await services.create_project(
            session, database.administrator.principal, "Collision system", "Synthetic B"
        )
    config = replace(database.config, state_dir=str(tmp_path / "state"))
    app = create_app(config)
    try:
        async with app.router.lifespan_context(app):
            yield Foundation(
                database, config, app, accounts[0], accounts[1], project_a.id, project_b.id
            )
    finally:
        # Keep synthetic history. Expire only resources owned by this test's
        # newly created users so later tests have their full quota available.
        async with database.sessions.begin() as session:
            await session.execute(
                update(Workspace)
                .where(
                    Workspace.owner_user_id.in_([account.principal.user_id for account in accounts])
                )
                .values(state="expired")
            )
