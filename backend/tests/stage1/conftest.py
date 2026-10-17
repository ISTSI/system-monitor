"""Explicit, non-destructive API checks of the approved temporary VM.

This fixture never migrates, creates database users, deletes history, or changes
the tunnel/VPN. It uses the already provisioned DML identity and privately reads
the synthetic fixture credentials. Every test gets fresh application users and
projects; cleanup expires only those users' page workspaces.
"""

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from inspector import auth, services
from inspector.app import create_app
from inspector.config import Config, parse_config
from inspector.database import check_runtime_grants, check_schema, create_engine
from inspector.domain import Principal
from inspector.persistence.models import Project, User, Workspace
from inspector.security import issue_token, normalize_username, verify_password

ROOT = Path(__file__).resolve().parents[3]


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


@pytest.fixture(scope="session")
def approved_files() -> tuple[Config, Path]:
    if os.environ.get("SI_TEST_APPROVED_SCHEMA") != "system-monitor":
        pytest.skip("Stage 01 VM API checks require SI_TEST_APPROVED_SCHEMA=system-monitor.")
    config_file = os.environ.get("INSPECTOR_STAGE1_CONFIG")
    accounts_file = os.environ.get("INSPECTOR_E2E_ACCOUNTS")
    if not config_file or not accounts_file:
        pytest.skip(
            "Stage 01 VM API checks require INSPECTOR_STAGE1_CONFIG and INSPECTOR_E2E_ACCOUNTS."
        )
    config_path, accounts_path = Path(config_file).resolve(), Path(accounts_file).resolve()
    if config_path != (ROOT / "deploy/vm-mariadb/application.local.yaml").resolve():
        pytest.fail("Stage 01 checks refuse an unexpected runtime configuration path.")
    if accounts_path != (ROOT / ".secrets/vm-mariadb/stage1-browser-accounts.json").resolve():
        pytest.fail("Stage 01 checks refuse an unexpected private synthetic-account fixture path.")
    try:
        config = parse_config(config_path.read_bytes(), environment={})
    except (OSError, ValueError):
        pytest.fail(
            "Stage 01 runtime configuration is unavailable or invalid; no connection attempted."
        )
    db = config.database
    if (db.host, db.port, db.name, db.username, db.topology) != (
        "127.0.0.1",
        13306,
        "system-monitor",
        "system-monitor-app",
        "ssh_tunnel",
    ):
        pytest.fail("Stage 01 runtime endpoint/identity differs from the approved VM scope.")
    return config, accounts_path


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def database(approved_files: tuple[Config, Path]) -> AsyncIterator[Database]:
    config, accounts_path = approved_files
    try:
        document = json.loads(accounts_path.read_text(encoding="utf-8"))
        credentials = document["administrator"]
        username, password = credentials["username"], credentials["password"]
        if (
            not isinstance(username, str)
            or not username.startswith("stage1-administrator-")
            or not isinstance(password, str)
        ):
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        pytest.fail("Private Stage 01 synthetic Administrator fixture is unavailable or invalid.")
    engine = create_engine(config.database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.connect() as connection:
            await check_schema(connection)
            await check_runtime_grants(connection)
        async with sessions() as session:
            user = await session.scalar(
                select(User).where(User.username_key == normalize_username(username))
            )
            assert user is not None, "Synthetic Stage 01 Administrator was not provisioned."
            assert user.enabled and user.role == "administrator" and not user.must_change_password
            assert await verify_password(user.password_hash, password), (
                "Private synthetic fixture credentials do not match."
            )
            administrator = Account(username, password, auth._principal(user))
        # Preserve previous synthetic history without cluttering the active catalogue.
        async with sessions.begin() as session:
            previous = (
                await session.scalars(
                    select(Project).where(
                        Project.id.startswith("stage1-api-", autoescape=True),
                        Project.archived.is_(False),
                    )
                )
            ).all()
            for project in previous:
                await services.set_project_archived(
                    session, administrator.principal, project.id, project.revision, archived=True
                )
        yield Database(config, sessions, administrator)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def foundation(database: Database, tmp_path: Path) -> AsyncIterator[Foundation]:
    config = replace(database.config, state_dir=str(tmp_path / "stage1-api-state"))
    app = create_app(config)
    accounts: list[Account] = []
    project_ids: list[str] = []
    try:
        async with app.router.lifespan_context(app):
            async with database.sessions.begin() as session:
                for label in ("alice", "bob"):
                    username, password = f"stage1-api-{label}-{uuid4().hex}", issue_token()
                    user = await auth.create_user(
                        session,
                        database.administrator.principal,
                        username,
                        f"Synthetic Stage 01 {label.title()}",
                        password,
                    )
                    accounts.append(Account(username, password, auth._principal(user)))
                for label in ("a", "b"):
                    project = await services.create_project(
                        session,
                        database.administrator.principal,
                        "Collision system",
                        f"Synthetic {label.upper()}",
                        project_id=f"stage1-api-{label}-{uuid4().hex}",
                    )
                    project_ids.append(project.id)
            yield Foundation(database, config, app, accounts[0], accounts[1], *project_ids)
    finally:
        if accounts:
            async with database.sessions.begin() as session:
                await session.execute(
                    update(Workspace)
                    .where(
                        Workspace.owner_user_id.in_(
                            [account.principal.user_id for account in accounts]
                        )
                    )
                    .values(state="expired")
                )
                for project_id in project_ids:
                    project = await session.get(Project, project_id)
                    if project is not None and not project.archived:
                        await services.set_project_archived(
                            session,
                            database.administrator.principal,
                            project_id,
                            project.revision,
                            archived=True,
                        )
