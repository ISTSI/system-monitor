"""Rollback-only checks for the explicitly approved temporary MariaDB schema.

These tests use a migration identity, never start the application, and verify
that this identity is refused for serving. They do not replace integration tests
using a restricted runtime identity. Apply the explicit migration first. Set
SI_TEST_APPROVED_SCHEMA to the exact approved schema and
INSPECTOR_VM_MIGRATION_CONFIG to its ignored local
deployment file. No database, account, or schema is created by this module.
"""

import os
from collections.abc import Awaitable
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from inspector import auth, services
from inspector.config import Config, parse_config
from inspector.database import check_runtime_grants, check_schema, create_engine, migration_guard
from inspector.domain import Principal, ProjectContext
from inspector.errors import DomainError
from inspector.persistence.models import Base, Project, User, Workspace
from inspector.security import issue_token, normalize_username

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio]


@pytest.fixture
def approved_vm_config() -> Config:
    if os.environ.get("SI_TEST_APPROVED_SCHEMA") != "system-monitor":
        pytest.skip("Temporary VM checks require SI_TEST_APPROVED_SCHEMA=system-monitor.")
    config_path = os.environ.get("INSPECTOR_VM_MIGRATION_CONFIG")
    if not config_path:
        pytest.skip("Temporary VM checks require INSPECTOR_VM_MIGRATION_CONFIG.")
    # Process-wide runtime overrides cannot redirect this narrowly approved test.
    config = parse_config(Path(config_path).read_bytes(), environment={}, migration=True)
    if (
        config.database.name != "system-monitor"
        or config.database.host != "127.0.0.1"
        or config.database.port != 13306
    ):
        pytest.fail("Temporary VM configuration differs from the approved tunnel/schema.")
    return config


async def _counts(connection: AsyncConnection) -> dict[str, int]:
    return {
        table.name: int(await connection.scalar(select(func.count()).select_from(table)) or 0)
        for table in Base.metadata.sorted_tables
    }


async def _denied(operation: Awaitable[object], code: str, status: int) -> None:
    with pytest.raises(DomainError) as rejected:
        await operation
    assert rejected.value.code == code
    assert rejected.value.status == status


async def test_vm_migration_uses_innodb_binary_columns_and_exact_schema(approved_vm_config):
    engine = create_engine(approved_vm_config.database, dedicated=True)
    try:
        assert engine.echo is False
        assert engine.sync_engine.hide_parameters is True
        async with engine.connect() as connection:
            await check_schema(connection)
            version = str(await connection.scalar(text("SELECT VERSION()")))
            assert version.startswith("12.3.") and "mariadb" in version.lower()
            tables = (
                await connection.execute(
                    text(
                        "SELECT TABLE_NAME, ENGINE, TABLE_COLLATION "
                        "FROM information_schema.tables WHERE table_schema = :schema"
                    ),
                    {"schema": approved_vm_config.database.name},
                )
            ).all()
            expected_tables = set(Base.metadata.tables)
            assert {name for name, _, _ in tables} == expected_tables | {"alembic_version"}
            assert all(
                storage == "InnoDB" and collation == "utf8mb4_bin"
                for name, storage, collation in tables
                if name in expected_tables
            )
            columns = (
                await connection.execute(
                    text(
                        "SELECT TABLE_NAME, COLUMN_NAME, COLLATION_NAME "
                        "FROM information_schema.columns WHERE table_schema = :schema"
                    ),
                    {"schema": approved_vm_config.database.name},
                )
            ).all()
            collations = {(table, name): collation for table, name, collation in columns}
            assert collations[("users", "username_key")] == "utf8mb4_bin"
            assert collations[("projects", "name")] == "utf8mb4_bin"
            assert collations[("workspaces", "id")] == "ascii_bin"
            assert collations[("workspaces", "project_id")] == "ascii_bin"
            assert all(
                collation in {None, "ascii_bin", "utf8mb4_bin"}
                for table, _, collation in columns
                if table in expected_tables
            )
    finally:
        await engine.dispose()


async def test_vm_scoped_services_constraints_and_authentication_rollback(approved_vm_config):
    engine = create_engine(approved_vm_config.database, dedicated=True)
    try:
        async with engine.connect() as connection:
            await check_schema(connection)
            before = await _counts(connection)
            # This is a freshly migrated project schema, not a general data test.
            assert before == {
                name: 1 if name == "security_state" else 0 for name in Base.metadata.tables
            }, "VM smoke writes require the approved schema to contain no application data."
            assert (await connection.scalars(text("SELECT id FROM security_state"))).all() == [1]
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                await session.begin()
                try:
                    await _exercise_scoped_services(session)
                finally:
                    # Never commit a synthetic user, session, project, audit, or workspace.
                    await session.rollback()
        finally:
            # A separate connection sees committed state after the rollback.
            async with engine.connect() as connection:
                assert await _counts(connection) == before
                assert (await connection.scalars(text("SELECT id FROM security_state"))).all() == [
                    1
                ]
    finally:
        await engine.dispose()


async def _exercise_scoped_services(session: AsyncSession) -> None:
    suffix = uuid4().hex
    password = issue_token()
    administrator = await auth.bootstrap_admin(
        session, f"vm-admin-{suffix}", "Synthetic VM Administrator", password
    )
    actor = Principal(administrator.id, administrator.role, administrator.auth_version)
    literal_username = f"Straße_%.[x].a.*b-{suffix}"
    alice = await auth.create_user(session, actor, literal_username, "Synthetic Alice", password)
    bob = await auth.create_user(session, actor, f"vm-bob-{suffix}", "Synthetic Bob", password)
    alice_actor = Principal(alice.id, alice.role, alice.auth_version)
    bob_actor = Principal(bob.id, bob.role, bob.auth_version)

    # Unicode casefold canonicalization preserves literal wildcard-looking text.
    assert alice.username_key == normalize_username(literal_username)
    assert "strasse_%.[x].a.*b-" in alice.username_key
    credentials = await auth.login(session, literal_username.upper(), password, 100, 1000, 10_000)
    authenticated = await auth.authenticate(session, credentials.token, 101, 1000)
    assert authenticated.user_id == alice.id and authenticated.role == "inspector"
    await auth.verify_csrf(session, credentials.token, credentials.csrf_token)
    await _denied(auth.verify_csrf(session, credentials.token, issue_token()), "CSRF_FAILED", 403)
    await _denied(
        auth.create_user(session, actor, literal_username.upper(), "Duplicate", password),
        "ACCOUNT_EXISTS",
        409,
    )
    await _denied(
        auth.login(session, literal_username.replace("_%", "ZZ"), password, 102, 1000, 10_000),
        "INVALID_CREDENTIALS",
        401,
    )
    assert await session.scalar(select(func.count()).select_from(User)) == 3

    project_a = await services.create_project(session, actor, "VM collision system", "A")
    project_b = await services.create_project(session, actor, "VM collision system", "B")
    assert project_a.id != project_b.id and project_a.name == project_b.name
    now = 9_007_199_254_740_993  # Deliberately beyond exact binary64 integer range.
    repeated_id = f"repeated-workspace-{suffix}"
    for project in (project_a, project_b):
        await session.execute(
            insert(Workspace).values(
                project_id=project.id,
                id=repeated_id,
                owner_user_id=alice.id,
                opened_revision=1,
                revision=1,
                state="active",
                created_us=now,
                expires_us=now + services.WORKSPACE_LEASE_US,
            )
        )
    rows = (await session.scalars(select(Workspace).where(Workspace.id == repeated_id))).all()
    assert {row.project_id for row in rows} == {project_a.id, project_b.id}
    assert all(row.created_us == now for row in rows)
    assert not (
        await session.scalars(select(Workspace).where(Workspace.id == repeated_id.upper()))
    ).all()
    context_a = ProjectContext(project_a.id, alice.id)
    unique = await services.create_workspace(
        session,
        alice_actor,
        context_a,
        max_per_user=8,
        max_global=64,
        now_us=now,
    )
    owned = await services.get_workspace(
        session, alice_actor, context_a, unique["workspace_id"], now_us=now
    )
    assert owned["project_id"] == project_a.id and owned["owner_user_id"] == alice.id
    for other_actor in (bob_actor, actor):
        await _denied(
            services.get_workspace(
                session,
                other_actor,
                ProjectContext(project_a.id, other_actor.user_id),
                unique["workspace_id"],
                now_us=now,
            ),
            "NOT_FOUND",
            404,
        )
    await _denied(
        services.get_workspace(
            session,
            alice_actor,
            ProjectContext(project_b.id, alice.id),
            unique["workspace_id"],
            now_us=now,
        ),
        "NOT_FOUND",
        404,
    )
    await _denied(services.create_project(session, alice_actor, "Forbidden", ""), "FORBIDDEN", 403)
    await _denied(
        services.list_projects(session, Principal(alice.id, alice.role, alice.auth_version + 1)),
        "AUTH_REQUIRED",
        401,
    )
    await services.rename_project(session, actor, project_b.id, "B revision two", "B", 1)
    assert project_b.revision == 2 and project_a.revision == 1
    await _denied(
        services.rename_project(session, actor, project_b.id, "Stale", "", 1),
        "REVISION_CONFLICT",
        409,
    )
    assert (await session.get(Project, project_b.id)).name == "B revision two"
    assert (await session.get(Project, project_a.id)).name == "VM collision system"

    # B has revision 2; A does not. A single unpaired revision FK would accept it.
    for statement in (
        insert(Workspace).values(
            project_id=project_a.id,
            id=f"invalid-{suffix}",
            owner_user_id=alice.id,
            opened_revision=2,
            revision=1,
            state="active",
            created_us=now,
            expires_us=now + services.WORKSPACE_LEASE_US,
        ),
        update(Workspace)
        .where(Workspace.project_id == project_a.id, Workspace.id == repeated_id)
        .values(opened_revision=2),
    ):
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(statement)
    preserved = await session.get(Workspace, (project_a.id, repeated_id), populate_existing=True)
    assert preserved is not None and preserved.opened_revision == 1
    assert preserved.created_us == now


async def test_vm_competing_migration_lock_is_refused_and_released(approved_vm_config):
    engine = create_engine(approved_vm_config.database, dedicated=True)
    contender = create_engine(approved_vm_config.database, dedicated=True)
    try:
        async with migration_guard(engine):
            with pytest.raises(RuntimeError, match="Another migration or serving process"):
                async with migration_guard(contender):
                    pytest.fail("Competing migration connection acquired the same lock.")
        # The first lock was released; a later migration connection can acquire it.
        async with migration_guard(contender) as connection:
            await check_schema(connection)
    finally:
        await contender.dispose()
        await engine.dispose()


async def test_vm_migration_account_is_refused_for_serving(approved_vm_config):
    engine = create_engine(approved_vm_config.database, dedicated=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(RuntimeError) as rejected:
                await check_runtime_grants(connection)
            # The rejection must not disclose SHOW GRANTS authentication metadata.
            assert str(rejected.value) == (
                "Runtime database account must have exact-schema DML-only privileges."
            )
    finally:
        await engine.dispose()
