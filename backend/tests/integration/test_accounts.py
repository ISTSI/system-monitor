"""Account lifecycle against actual MariaDB and the serving HTTP dependencies."""

import asyncio

import pytest
from sqlalchemy import delete, func, select, text, update

from inspector import auth, services
from inspector.domain import Principal
from inspector.errors import DomainError
from inspector.persistence.models import Audit, AuthSession, User, Workspace
from inspector.security import issue_token

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


async def test_inspector_cannot_manage_accounts_and_denied_requests_have_no_effect(foundation):
    bob_id = foundation.bob.principal.user_id
    async with foundation.client(foundation.alice) as inspector:
        assert (await inspector.get("/api/v1/admin/users")).status_code == 403
        assert (
            await inspector.post(
                "/api/v1/admin/users",
                json={
                    "username": "forbidden-account",
                    "display_name": "Forbidden",
                    "password": issue_token(),
                },
            )
        ).status_code == 403
        mutations = (
            (
                "patch",
                f"/api/v1/admin/users/{bob_id}",
                {"expected_auth_version": 1, "role": "administrator"},
            ),
            (
                "post",
                f"/api/v1/admin/users/{bob_id}/reset-password",
                {"expected_auth_version": 1, "password": issue_token()},
            ),
            ("post", f"/api/v1/admin/users/{bob_id}/revoke-sessions", {"expected_auth_version": 1}),
        )
        for method, path, payload in mutations:
            response = await inspector.request(method, path, json=payload)
            assert response.status_code == 403
    async with foundation.database.sessions() as session:
        bob = await session.get(User, bob_id)
        assert (bob.role, bob.enabled, bob.auth_version) == ("inspector", True, 1)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.username_key == "forbidden-account")
            )
            == 0
        )
        denials = (
            await session.scalars(
                select(Audit).where(
                    Audit.actor_user_id == foundation.alice.principal.user_id,
                    Audit.action == "authorization.denied",
                )
            )
        ).all()
        assert len(denials) == 5


async def test_admin_create_forced_change_and_safe_user_projection(foundation):
    password, replacement = issue_token(), issue_token()
    username = f"created-{issue_token()}"
    async with foundation.client(foundation.database.administrator) as admin:
        created = await admin.post(
            "/api/v1/admin/users",
            json={
                "username": username,
                "display_name": "Synthetic forced change",
                "password": password,
                "must_change_password": True,
            },
        )
        assert created.status_code == 201
        user = created.json()
        assert user["role"] == "inspector" and user["must_change_password"] is True
        duplicate = await admin.post(
            "/api/v1/admin/users",
            json={"username": username.upper(), "display_name": "Duplicate", "password": password},
        )
        assert duplicate.status_code == 409
        listed = await admin.get("/api/v1/admin/users")
        assert listed.status_code == 200
        assert user in listed.json()["items"]
        for response in (created, listed, duplicate):
            assert password not in response.text
            assert "password_hash" not in response.text
    # Use the fixture's Account shape without embedding any public seed credentials.
    account = type(foundation.alice)(username, password, Principal(user["user_id"], "inspector", 1))
    async with foundation.client(account) as restricted:
        info = await restricted.get("/api/v1/auth/session")
        assert info.status_code == 200 and info.json()["must_change_password"] is True
        assert (await restricted.get("/api/v1/projects")).status_code == 403
        assert (
            await restricted.post(f"/api/v1/projects/{foundation.project_a}/workspaces", json={})
        ).status_code == 403
        rejected = await restricted.post(
            "/api/v1/me/password",
            json={"current_password": issue_token(), "new_password": replacement},
        )
        assert rejected.status_code == 403
        assert password not in rejected.text and replacement not in rejected.text
        async with foundation.database.sessions() as session:
            unchanged = await session.get(User, user["user_id"])
            assert unchanged.auth_version == 1 and unchanged.must_change_password is True
        changed = await restricted.post(
            "/api/v1/me/password",
            json={
                "current_password": password,
                "new_password": replacement,
            },
        )
        assert changed.status_code == 200 and changed.json()["sign_in_required"] is True
        assert password not in changed.text and replacement not in changed.text
        assert (await restricted.get("/api/v1/auth/session")).status_code == 401
    account = type(account)(username, replacement, Principal(user["user_id"], "inspector", 2))
    async with foundation.client(account) as changed_account:
        assert (await changed_account.get("/api/v1/projects")).status_code == 200
        info = await changed_account.get("/api/v1/auth/session")
        assert info.json()["must_change_password"] is False
    async with foundation.database.sessions() as session:
        audits = (
            await session.scalars(select(Audit).where(Audit.target_id == user["user_id"]))
        ).all()
        assert {audit.action for audit in audits} >= {"auth.account.create", "auth.password.change"}
        assert all(
            password not in str(audit.__dict__) and replacement not in str(audit.__dict__)
            for audit in audits
        )


async def test_role_disable_enable_reset_and_revoke_invalidate_sessions_and_workspaces(foundation):
    bob_id = foundation.bob.principal.user_id
    password = issue_token()
    async with foundation.client(foundation.bob) as bob:
        workspace = await bob.post(f"/api/v1/projects/{foundation.project_a}/workspaces", json={})
        assert workspace.status_code == 201
        async with foundation.client(foundation.database.administrator) as admin:
            endpoint = f"/api/v1/admin/users/{bob_id}"
            changed = await admin.patch(
                endpoint, json={"expected_auth_version": 1, "role": "administrator"}
            )
            assert changed.status_code == 200 and changed.json()["auth_version"] == 2
            assert (await bob.get("/api/v1/projects")).status_code == 401
            stale = await admin.patch(endpoint, json={"expected_auth_version": 1, "enabled": False})
            assert stale.status_code == 409
            disabled = await admin.patch(
                endpoint, json={"expected_auth_version": 2, "enabled": False}
            )
            assert disabled.status_code == 200 and disabled.json()["auth_version"] == 3
            reset = await admin.post(
                endpoint + "/reset-password",
                json={
                    "expected_auth_version": 3,
                    "password": password,
                    "must_change_password": False,
                },
            )
            assert reset.status_code == 200 and reset.json()["auth_version"] == 4
            enabled = await admin.patch(
                endpoint, json={"expected_auth_version": 4, "enabled": True}
            )
            assert enabled.status_code == 200 and enabled.json()["auth_version"] == 5
            account = type(foundation.bob)(
                foundation.bob.username, password, Principal(bob_id, "administrator", 5)
            )
            async with foundation.client(account) as enabled_bob:
                assert (await enabled_bob.get("/api/v1/admin/users")).status_code == 200
                revoked = await admin.post(
                    endpoint + "/revoke-sessions", json={"expected_auth_version": 5}
                )
                assert revoked.status_code == 200 and revoked.json()["auth_version"] == 6
                assert (await enabled_bob.get("/api/v1/admin/users")).status_code == 401
    async with foundation.database.sessions() as session:
        retained = await session.get(
            Workspace, (foundation.project_a, workspace.json()["workspace_id"])
        )
        assert retained.state == "expired" and retained.revision == 2
        assert (
            await session.scalar(
                select(func.count()).select_from(AuthSession).where(AuthSession.user_id == bob_id)
            )
            == 0
        )
    # Preserve the fixture's one-Administrator baseline and synthetic history.
    async with foundation.database.sessions.begin() as session:
        await auth.update_user(
            session,
            foundation.database.administrator.principal,
            bob_id,
            6,
            role="inspector",
        )


async def test_last_administrator_cannot_disable_or_demote_self(foundation):
    async with foundation.database.sessions() as session:
        enabled_admins = (
            await session.scalars(
                select(User.id).where(User.enabled.is_(True), User.role == "administrator")
            )
        ).all()
    assert enabled_admins == [foundation.database.administrator.principal.user_id]
    actor = foundation.database.administrator
    async with foundation.client(actor) as admin:
        endpoint = f"/api/v1/admin/users/{actor.principal.user_id}"
        for change in ({"enabled": False}, {"role": "inspector"}):
            response = await admin.patch(
                endpoint, json={"expected_auth_version": actor.principal.auth_version, **change}
            )
            assert (
                response.status_code == 409
                and response.json()["error"]["code"] == "LAST_ADMIN_REQUIRED"
            )
        assert (await admin.get("/api/v1/admin/users")).status_code == 200


async def test_concurrent_account_mutations_serialize_expected_auth_version(foundation):
    async def mutate():
        try:
            async with foundation.database.sessions.begin() as session:
                await auth.update_user(
                    session,
                    foundation.database.administrator.principal,
                    foundation.bob.principal.user_id,
                    1,
                    enabled=False,
                    now_us=services.utc_now_us(),
                )
            return "success"
        except DomainError as error:
            return error.code

    assert sorted(await asyncio.gather(mutate(), mutate())) == ["REVISION_CONFLICT", "success"]


async def test_concurrent_last_administrator_changes_keep_one_enabled(foundation):
    """Temporarily isolate two synthetic Administrators in a disposable schema only."""
    config = foundation.database.config
    if not config.database.name.startswith("inspector_test_"):
        pytest.skip(
            "Concurrent last-Administrator isolation requires the guarded disposable schema."
        )
    administrator = foundation.database.administrator.principal
    created_ids = []
    original = None
    try:
        async with foundation.database.sessions.begin() as session:
            assert await session.scalar(text("SELECT DATABASE()")) == config.database.name
            enabled = (
                await session.scalars(
                    select(User.id).where(User.enabled.is_(True), User.role == "administrator")
                )
            ).all()
            assert enabled == [administrator.user_id]
            user = await session.get(User, administrator.user_id)
            original = (user.role, user.enabled, user.auth_version)
            actors = []
            for number in range(2):
                created = await auth.create_user(
                    session,
                    administrator,
                    f"concurrent-admin-{issue_token()}",
                    f"Synthetic concurrent Administrator {number}",
                    issue_token(),
                    "administrator",
                )
                created_ids.append(created.id)
                actors.append(Principal(created.id, created.role, created.auth_version))
            # Restore the exact known synthetic bootstrap fields even on failure.
            await session.execute(
                update(User).where(User.id == administrator.user_id).values(enabled=False)
            )

        async def demote_self(actor):
            try:
                async with foundation.database.sessions.begin() as session:
                    await auth.update_user(session, actor, actor.user_id, 1, role="inspector")
                return "success"
            except DomainError as error:
                return error.code

        assert sorted(await asyncio.gather(*(demote_self(actor) for actor in actors))) == [
            "LAST_ADMIN_REQUIRED",
            "success",
        ]
        async with foundation.database.sessions() as session:
            remaining = (
                await session.scalars(
                    select(User).where(User.enabled.is_(True), User.role == "administrator")
                )
            ).all()
            assert len(remaining) == 1 and remaining[0].id in created_ids
    finally:
        async with foundation.database.sessions.begin() as session:
            assert config.database.name.startswith("inspector_test_")
            assert await session.scalar(text("SELECT DATABASE()")) == config.database.name
            if original is not None:
                role, enabled, version = original
                await session.execute(
                    update(User)
                    .where(User.id == administrator.user_id)
                    .values(role=role, enabled=enabled, auth_version=version)
                )
            if created_ids:
                await session.execute(
                    delete(AuthSession).where(AuthSession.user_id.in_(created_ids))
                )
                await session.execute(
                    update(User)
                    .where(User.id.in_(created_ids))
                    .values(enabled=False, role="inspector")
                )
