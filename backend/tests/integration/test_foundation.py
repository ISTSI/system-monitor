"""Application behavior against actual MariaDB; no simulated persistence.

HTTP clients below share opaque account cookies to exercise backend page scope.
They do not substitute for the still-required same-browser Playwright tests.
"""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from inspector import auth, services
from inspector.app import CSRF_COOKIE, SESSION_COOKIE, create_app
from inspector.database import supervisor_guard
from inspector.domain import ProjectContext
from inspector.errors import DomainError
from inspector.persistence.models import Audit, AuthSession, Project, User, Workspace
from inspector.security import issue_token, token_hash

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


def validate_response_contract(name, value):
    path = Path(__file__).resolve().parents[3] / "contracts" / name
    Draft202012Validator(json.loads(path.read_text(encoding="utf-8"))).validate(value)


async def test_migrations_runtime_grants_and_concurrent_first_administrator(database):
    assert database.bootstrap_outcomes == ("success", "BOOTSTRAP_CLOSED")
    async with database.sessions() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(User).where(User.role == "administrator")
            )
            == 1
        )
        grants = (await session.execute(text("SHOW GRANTS FOR CURRENT_USER"))).scalars().all()
        permitted = ("SELECT", "INSERT", "UPDATE", "DELETE", "USAGE")
        # Do not print grants: a server may include authentication metadata.
        assert grants, "Runtime account must have explicit grants."
        for grant in grants:
            privileges = str(grant).split(" ON ", 1)[0].removeprefix("GRANT ")
            assert all(privilege.strip() in permitted for privilege in privileges.split(",")), (
                "Runtime account has unexpected privileges."
            )
        with pytest.raises(DomainError) as denied:
            await auth.bootstrap_admin(
                session, f"second-{uuid4()}", "Second", "synthetic-password-only"
            )
        assert denied.value.code == "BOOTSTRAP_CLOSED"


async def test_login_requires_csrf_exact_origin_and_secure_cookies(foundation):
    async with foundation.database.sessions() as session:
        initial_denials = await session.scalar(
            select(func.count())
            .select_from(Audit)
            .where(Audit.action == "auth.login", Audit.outcome == "denied")
        )
    async with foundation.client() as client:
        assert (await client.get("/api/v1/health/ready")).status_code == 200
        assert (await client.get("/api/v1/projects")).status_code == 401
        payload = {"username": foundation.alice.username, "password": foundation.alice.password}
        assert (await client.post("/api/v1/auth/login", json=payload)).status_code == 403
        preflight = await client.get("/api/v1/auth/csrf")
        csrf = preflight.json()["csrf_token"]
        assert (
            await client.post(
                "/api/v1/auth/login",
                json=payload,
                headers={"Origin": "https://unexpected.invalid", "x-csrf-token": csrf},
            )
        ).status_code == 403
        invalid = await client.post(
            "/api/v1/auth/login",
            json={**payload, "password": "wrong-password"},
            headers={"x-csrf-token": csrf},
        )
        assert invalid.status_code == 401
        assert invalid.json()["error"]["code"] == "INVALID_CREDENTIALS"
        assert payload["username"] not in invalid.text
        csrf = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
        response = await client.post(
            "/api/v1/auth/login", json=payload, headers={"x-csrf-token": csrf}
        )
        assert response.status_code == 200
        assert set(response.json()) == {
            "user_id",
            "role",
            "csrf_token",
            "username",
            "display_name",
            "must_change_password",
        }
        assert response.json()["username"] == foundation.alice.username
        assert response.json()["display_name"] == "Synthetic Alice"
        assert response.json()["must_change_password"] is False
        cookies = response.headers.get_list("set-cookie")
        for cookie_name in (SESSION_COOKIE, CSRF_COOKIE):
            header = next(cookie for cookie in cookies if cookie.startswith(cookie_name + "="))
            assert (
                "Secure" in header
                and "HttpOnly" in header
                and "SameSite=strict" in header
                and "Path=/" in header
            )
        assert foundation.alice.password not in response.text
        assert (
            await client.get("/api/v1/projects", headers={"Host": "unexpected.invalid"})
        ).status_code == 400
    async with foundation.database.sessions() as session:
        denials = await session.scalar(
            select(func.count())
            .select_from(Audit)
            .where(Audit.action == "auth.login", Audit.outcome == "denied")
        )
        assert denials == initial_denials + 1


async def test_shared_cookie_pages_have_distinct_scoped_workspaces(foundation):
    async with foundation.client(foundation.alice) as page_a:
        async with foundation.client(cookies=page_a.cookies) as page_b:
            assert page_a.cookies[SESSION_COOKIE] == page_b.cookies[SESSION_COOKIE]
            catalogue = await page_a.get("/api/v1/projects")
            assert catalogue.status_code == 200
            validate_response_contract("system-catalog.schema.json", catalogue.json())
            items = {item["project_id"]: item for item in catalogue.json()["items"]}
            assert items[foundation.project_a]["name"] == items[foundation.project_b]["name"]
            assert set(items[foundation.project_a]) == {
                "project_id",
                "name",
                "description",
                "revision",
                "archived",
                "own_live_sessions",
            }
            responses = await asyncio.gather(
                page_a.post(f"/api/v1/projects/{foundation.project_a}/workspaces", json={}),
                page_b.post(f"/api/v1/projects/{foundation.project_b}/workspaces", json={}),
            )
            assert [response.status_code for response in responses] == [201, 201]
            workspace_a, workspace_b = [response.json() for response in responses]
            for workspace in (workspace_a, workspace_b):
                validate_response_contract("workspace.schema.json", workspace)
            assert workspace_a["workspace_id"] != workspace_b["workspace_id"]
            same_project = await page_b.post(
                f"/api/v1/projects/{foundation.project_a}/workspaces", json={}
            )
            assert same_project.status_code == 201
            validate_response_contract("workspace.schema.json", same_project.json())
            assert same_project.json()["workspace_id"] not in {
                workspace_a["workspace_id"],
                workspace_b["workspace_id"],
            }
            assert (
                await page_a.get(
                    f"/api/v1/projects/{foundation.project_b}/workspaces/{workspace_a['workspace_id']}"
                )
            ).status_code == 404
            detached = await page_a.post(
                f"/api/v1/projects/{foundation.project_a}/workspaces/{workspace_a['workspace_id']}/detach",
                json={},
            )
            assert detached.status_code == 200 and detached.json()["state"] == "detached"
            validate_response_contract("workspace.schema.json", detached.json())
            for project, workspace in (
                (foundation.project_b, workspace_b),
                (foundation.project_a, same_project.json()),
            ):
                other = await page_b.get(
                    f"/api/v1/projects/{project}/workspaces/{workspace['workspace_id']}"
                )
                assert other.status_code == 200 and other.json()["state"] == "active"
                validate_response_contract("workspace.schema.json", other.json())
    async with foundation.database.sessions() as session:
        record = await session.get(AuthSession, token_hash(page_a.cookies[SESSION_COOKIE]))
        assert record is not None
        assert not hasattr(record, "project_id")


async def test_forged_owner_project_and_unknown_fields_are_rejected(foundation):
    async with foundation.client(foundation.alice) as alice:
        created = await alice.post(f"/api/v1/projects/{foundation.project_a}/workspaces", json={})
        assert created.status_code == 201
        workspace = created.json()["workspace_id"]
        for payload in (
            {"project_id": foundation.project_b},
            {"owner_user_id": foundation.bob.principal.user_id},
            {"current_project": foundation.project_b},
        ):
            denied = await alice.post(
                f"/api/v1/projects/{foundation.project_a}/workspaces", json=payload
            )
            assert denied.status_code == 422
        assert (
            await alice.post(
                f"/api/v1/projects/{foundation.project_a}/workspaces",
                json={},
                headers={"x-csrf-token": issue_token()},
            )
        ).status_code == 403
        mass_assignment = await alice.post(
            "/api/v1/auth/login",
            json={
                "username": "ignored",
                "password": foundation.alice.password,
                "role": "administrator",
            },
        )
        assert mass_assignment.status_code == 422
        assert foundation.alice.password not in mass_assignment.text
        assert (await alice.post("/api/v1/workspaces", json={})).status_code == 404
    for account in (foundation.bob, foundation.database.administrator):
        async with foundation.client(account) as other:
            assert (
                await other.get(f"/api/v1/projects/{foundation.project_a}/workspaces/{workspace}")
            ).status_code == 404
            assert (
                await other.post(
                    f"/api/v1/projects/{foundation.project_a}/workspaces/{workspace}/detach",
                    json={},
                )
            ).status_code == 404


async def test_metadata_permissions_and_independent_optimistic_revisions(foundation):
    endpoint = f"/api/v1/projects/{foundation.project_a}/metadata"
    payload = {"name": "Revised A", "description": "Synthetic metadata", "expected_revision": 1}
    async with foundation.client(foundation.alice) as inspector:
        assert (await inspector.patch(endpoint, json=payload)).status_code == 403
        assert (
            await inspector.post("/api/v1/projects", json={"name": "Forbidden"})
        ).status_code == 403
    async with foundation.database.sessions() as session:
        denied_audits = (
            await session.scalars(
                select(Audit).where(
                    Audit.actor_user_id == foundation.alice.principal.user_id,
                    Audit.action == "authorization.denied",
                )
            )
        ).all()
        assert len(denied_audits) == 2
        assert all(
            event.actor_role == "inspector" and event.outcome == "denied" and event.created_us > 0
            for event in denied_audits
        )
        original = await session.get(Project, foundation.project_a)
        assert original.name == "Collision system" and original.revision == 1
        assert (
            await session.scalar(
                select(func.count()).select_from(Project).where(Project.name == "Forbidden")
            )
            == 0
        )
    async with foundation.client(foundation.database.administrator) as administrator:
        first = await administrator.patch(endpoint, json=payload)
        assert first.status_code == 200 and first.json()["revision"] == 2
        stale = await administrator.patch(endpoint, json={**payload, "name": "Must not overwrite"})
        assert stale.status_code == 409
        items = {
            item["project_id"]: item
            for item in (await administrator.get("/api/v1/projects")).json()["items"]
        }
        assert items[foundation.project_a]["revision"] == 2
        assert items[foundation.project_a]["name"] == "Revised A"
        assert items[foundation.project_b]["revision"] == 1
        assert items[foundation.project_b]["name"] == "Collision system"


async def test_mariadb_composite_fk_rejects_cross_project_insert_and_update(foundation):
    now = 9_007_199_254_740_993  # Exceeds binary64's exact integer range.
    repeated_id = "repeated-workspace-id"
    owner = foundation.alice.principal.user_id
    async with foundation.database.sessions.begin() as session:
        await services.rename_project(
            session,
            foundation.database.administrator.principal,
            foundation.project_b,
            "B revision two",
            "",
            1,
        )
        for project in (foundation.project_a, foundation.project_b):
            await session.execute(
                insert(Workspace).values(
                    project_id=project,
                    id=repeated_id,
                    owner_user_id=owner,
                    opened_revision=1,
                    revision=1,
                    state="active",
                    created_us=now,
                    expires_us=now + 300_000_000,
                )
            )
    async with foundation.database.sessions() as session:
        rows = (
            await session.scalars(
                select(Workspace).where(
                    Workspace.id == repeated_id,
                    Workspace.project_id.in_([foundation.project_a, foundation.project_b]),
                )
            )
        ).all()
        assert {row.project_id for row in rows} == {foundation.project_a, foundation.project_b}
        assert all(row.created_us == now for row in rows)
    # Revision 2 exists in B only. An unpaired revision FK would accept this.
    for statement in (
        insert(Workspace).values(
            project_id=foundation.project_a,
            id=str(uuid4()),
            owner_user_id=owner,
            opened_revision=2,
            revision=1,
            state="active",
            created_us=now,
            expires_us=now + 300_000_000,
        ),
        update(Workspace)
        .where(Workspace.project_id == foundation.project_a, Workspace.id == repeated_id)
        .values(opened_revision=2),
    ):
        async with foundation.database.sessions() as session:
            with pytest.raises(IntegrityError):
                await session.execute(statement)
                await session.commit()
            await session.rollback()
    async with foundation.database.sessions() as session:
        preserved = await session.get(Workspace, (foundation.project_a, repeated_id))
        assert preserved.opened_revision == 1


async def test_atomic_workspace_quota_rejection_preserves_existing_workspaces(foundation):
    async def reserve(account, project):
        try:
            async with foundation.database.sessions.begin() as session:
                return await services.create_workspace(
                    session,
                    account.principal,
                    ProjectContext(project, account.principal.user_id),
                    max_per_user=2,
                    max_global=1,
                    now_us=services.utc_now_us(),
                )
        except DomainError as error:
            return error

    results = await asyncio.gather(
        reserve(foundation.alice, foundation.project_a),
        reserve(foundation.bob, foundation.project_b),
    )
    accepted = [result for result in results if isinstance(result, dict)]
    rejected = [result for result in results if isinstance(result, DomainError)]
    assert len(accepted) == len(rejected) == 1
    assert rejected[0].status == 429 and rejected[0].code == "LIMIT_REACHED"
    async with foundation.database.sessions() as session:
        retained = await session.get(
            Workspace, (accepted[0]["project_id"], accepted[0]["workspace_id"])
        )
        assert retained is not None and retained.state == "active" and retained.revision == 1


async def test_global_logout_invalidates_all_account_sessions_and_other_page_cookies(foundation):
    async with foundation.client(foundation.alice) as first:
        async with foundation.client(foundation.alice) as independently_logged_in:
            async with foundation.client(cookies=first.cookies) as same_cookie_page:
                assert (
                    first.cookies[SESSION_COOKIE] != independently_logged_in.cookies[SESSION_COOKIE]
                )
                assert (await first.post("/api/v1/auth/logout", json={})).status_code == 200
                for other in (independently_logged_in, same_cookie_page):
                    assert (await other.get("/api/v1/projects")).status_code == 401
    async with foundation.database.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.user_id == foundation.alice.principal.user_id)
            )
            == 0
        )
        user = await session.get(User, foundation.alice.principal.user_id)
        assert user.auth_version == foundation.alice.principal.auth_version + 1


async def test_disabled_or_version_stale_account_fails_next_dispatch(foundation):
    async with foundation.client(foundation.alice) as first:
        async with foundation.client(cookies=first.cookies) as second:
            async with foundation.database.sessions.begin() as session:
                await session.execute(
                    update(User)
                    .where(User.id == foundation.alice.principal.user_id)
                    .values(enabled=False, auth_version=User.auth_version + 1)
                )
            for client in (first, second):
                response = await client.get("/api/v1/projects")
                assert response.status_code == 401


async def test_exact_idle_and_absolute_expiry_with_deliberate_activity(foundation):
    base = 1_700_000_000_000_001

    async def sign_in(idle_timeout, absolute_timeout):
        async with foundation.database.sessions.begin() as session:
            return await auth.login(
                session,
                foundation.alice.username,
                foundation.alice.password,
                base,
                idle_timeout,
                absolute_timeout,
            )

    async def dispatch(credentials, offset, idle_timeout, renew_idle=False):
        async with foundation.database.sessions.begin() as session:
            return await auth.authenticate(
                session, credentials.token, base + offset, idle_timeout, renew_idle=renew_idle
            )

    idle = await sign_in(10, 1000)
    assert (await dispatch(idle, 9, 10)).user_id == foundation.alice.principal.user_id
    with pytest.raises(DomainError) as idle_expired:
        await dispatch(idle, 10, 10)
    assert idle_expired.value.code == "AUTH_REQUIRED"

    renewed = await sign_in(10, 1000)
    await dispatch(renewed, 9, 10, renew_idle=True)
    await dispatch(renewed, 18, 10)
    with pytest.raises(DomainError) as renewed_expired:
        await dispatch(renewed, 19, 10)
    assert renewed_expired.value.code == "AUTH_REQUIRED"

    absolute = await sign_in(100, 30)
    await dispatch(absolute, 29, 100, renew_idle=True)
    with pytest.raises(DomainError) as absolute_expired:
        await dispatch(absolute, 30, 100)
    assert absolute_expired.value.code == "AUTH_REQUIRED"
    async with foundation.database.sessions() as session:
        record = await session.get(AuthSession, token_hash(absolute.token))
        assert record.last_seen_us == base + 29
        assert record.expires_us == base + 30


async def test_workspace_expiry_releases_only_that_pages_capacity(foundation):
    principal = foundation.alice.principal
    context = ProjectContext(foundation.project_a, principal.user_id)
    base = services.utc_now_us()

    async def create(now):
        async with foundation.database.sessions.begin() as session:
            return await services.create_workspace(
                session,
                principal,
                context,
                max_per_user=2,
                max_global=foundation.config.max_workspaces_global,
                now_us=now,
            )

    async def read(workspace, now, detach=False):
        async with foundation.database.sessions.begin() as session:
            response = await services.get_workspace(
                session, principal, context, workspace["workspace_id"], now_us=now, detach=detach
            )
            validate_response_contract("workspace.schema.json", response)
            return response

    first, second = await create(base), await create(base)
    detached = await read(first, base + 1, detach=True)
    assert detached["state"] == "detached" and detached["revision"] == 2
    await read(second, base + services.WORKSPACE_LEASE_US - 1)
    expired = await read(first, base + services.WORKSPACE_LEASE_US + 1)
    assert expired["state"] == "expired" and expired["revision"] == 3
    surviving = await read(second, base + services.WORKSPACE_LEASE_US + 1)
    assert surviving["state"] == "active" and surviving["revision"] == 1
    replacement = await create(base + services.WORKSPACE_LEASE_US + 1)
    assert replacement["workspace_id"] not in {first["workspace_id"], second["workspace_id"]}
    assert (await read(second, base + services.WORKSPACE_LEASE_US + 1))["state"] == "active"


async def test_competing_server_supervisor_is_refused_without_changing_workspaces(foundation):
    async with foundation.client(foundation.alice) as client:
        old = await client.post(f"/api/v1/projects/{foundation.project_a}/workspaces", json={})
        assert old.status_code == 201
    # A second server process must be refused while this fixture's server lives.
    from inspector.database import create_engine

    engine = create_engine(foundation.config.database, dedicated=True)
    try:
        with pytest.raises(RuntimeError, match="Another migration or serving process"):
            async with supervisor_guard(engine):
                pytest.fail("Competing serving supervisor was allowed.")
    finally:
        await engine.dispose()
    async with foundation.database.sessions() as session:
        preserved = await session.get(Workspace, (foundation.project_a, old.json()["workspace_id"]))
        assert preserved.state == "active" and preserved.revision == 1


async def test_cold_application_restart_keeps_two_systems_and_detaches_pages(database, tmp_path):
    first_config = replace(database.config, state_dir=str(tmp_path / "restart-state"))
    first_app = create_app(first_config)
    context = ProjectContext(str(uuid4()), database.administrator.principal.user_id)
    second_project = str(uuid4())
    async with database.sessions.begin() as session:
        await services.create_project(
            session,
            database.administrator.principal,
            "Retained A",
            "",
            project_id=context.project_id,
        )
        await services.create_project(
            session, database.administrator.principal, "Retained B", "", project_id=second_project
        )
    async with first_app.router.lifespan_context(first_app):
        async with database.sessions.begin() as session:
            workspace = await services.create_workspace(
                session,
                database.administrator.principal,
                context,
                max_per_user=first_config.max_workspaces_per_user,
                max_global=first_config.max_workspaces_global,
                now_us=services.utc_now_us(),
            )
    second_app = create_app(first_config)
    try:
        async with second_app.router.lifespan_context(second_app):
            async with database.sessions() as session:
                old = await session.get(Workspace, (context.project_id, workspace["workspace_id"]))
                assert old.state == "detached" and old.revision == 2
                assert (await session.get(Project, context.project_id)).name == "Retained A"
                assert (await session.get(Project, second_project)).name == "Retained B"
    finally:
        async with database.sessions.begin() as session:
            await session.execute(
                update(Workspace)
                .where(
                    Workspace.project_id == context.project_id,
                    Workspace.id == workspace["workspace_id"],
                )
                .values(state="expired")
            )
