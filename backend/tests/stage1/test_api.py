"""Real Stage 01 API evidence for the approved schema and restricted identity.

The original disposable-schema suite keeps its safeguards. Applicable behavior
helpers are reused here under the separate explicit VM fixture; fresh migration
and concurrent first-account provisioning remain distinct release checks.
"""

import asyncio
import importlib.util
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, update

from inspector import auth, services
from inspector.app import CSRF_COOKIE, SESSION_COOKIE, create_app
from inspector.domain import ProjectContext
from inspector.errors import DomainError
from inspector.persistence.models import (
    Audit,
    DemoSnapshot,
    Project,
    ProjectRevision,
    User,
    Workspace,
)
from inspector.security import issue_token

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]
ROOT = Path(__file__).resolve().parents[3]


def _load_helpers(filename):
    specification = importlib.util.spec_from_file_location(
        f"stage1_helpers_{filename}", ROOT / "backend/tests/integration" / filename
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


_accounts = _load_helpers("test_accounts.py")
_foundation = _load_helpers("test_foundation.py")

# These are the same actual-route checks, run under the distinct approved-VM
# fixture rather than weakening the original disposable-schema prerequisites.
test_inspector_account_writes_are_denied_without_effects = (
    _accounts.test_inspector_cannot_manage_accounts_and_denied_requests_have_no_effect
)
test_created_account_has_restricted_forced_change_flow = (
    _accounts.test_admin_create_forced_change_and_safe_user_projection
)
test_account_lifecycle_revokes_sessions_and_workspaces = (
    _accounts.test_role_disable_enable_reset_and_revoke_invalidate_sessions_and_workspaces
)
test_last_administrator_is_retained = (
    _accounts.test_last_administrator_cannot_disable_or_demote_self
)
test_concurrent_account_updates_reject_stale_version = (
    _accounts.test_concurrent_account_mutations_serialize_expected_auth_version
)
test_same_cookie_pages_create_separate_scoped_workspaces = (
    _foundation.test_shared_cookie_pages_have_distinct_scoped_workspaces
)
test_forged_owners_projects_and_fields_are_rejected = (
    _foundation.test_forged_owner_project_and_unknown_fields_are_rejected
)
test_roles_and_per_system_revisions_are_independent = (
    _foundation.test_metadata_permissions_and_independent_optimistic_revisions
)
test_mariadb_rejects_cross_project_insert_and_update = (
    _foundation.test_mariadb_composite_fk_rejects_cross_project_insert_and_update
)
test_logout_invalidates_all_account_windows = (
    _foundation.test_global_logout_invalidates_all_account_sessions_and_other_page_cookies
)
test_disabled_accounts_and_stale_versions_fail_dispatch = (
    _foundation.test_disabled_or_version_stale_account_fails_next_dispatch
)
test_idle_and_absolute_expiry_are_exact = (
    _foundation.test_exact_idle_and_absolute_expiry_with_deliberate_activity
)
test_workspace_expiry_preserves_other_pages = (
    _foundation.test_workspace_expiry_releases_only_that_pages_capacity
)
test_competing_server_cannot_change_workspaces = (
    _foundation.test_competing_server_supervisor_is_refused_without_changing_workspaces
)


async def test_actual_login_csrf_cookie_flags_and_unauthenticated_bootstrap(foundation):
    async with foundation.client() as client:
        public = await client.get("/api/v1/ui/bootstrap")
        assert public.status_code == 200
        assert set(public.json()) == {"branding", "default_theme_mode", "demo_mode"}
        assert public.json()["demo_mode"] is True
        assert (await client.get("/api/v1/auth/session")).status_code == 401
        payload = {"username": foundation.alice.username, "password": foundation.alice.password}
        assert (await client.post("/api/v1/auth/login", json=payload)).status_code == 403
        preflight = await client.get("/api/v1/auth/csrf")
        csrf = preflight.json()["csrf_token"]
        assert (
            await client.post(
                "/api/v1/auth/login",
                json=payload,
                headers={
                    "Origin": "https://unexpected.invalid",
                    "x-csrf-token": csrf,
                },
            )
        ).status_code == 403
        denied = await client.post(
            "/api/v1/auth/login",
            json={**payload, "password": issue_token()},
            headers={"x-csrf-token": csrf},
        )
        assert denied.status_code == 401 and denied.json()["error"]["code"] == "INVALID_CREDENTIALS"
        csrf = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
        response = await client.post(
            "/api/v1/auth/login", json=payload, headers={"x-csrf-token": csrf}
        )
        assert response.status_code == 200
        assert set(response.json()) == {
            "user_id",
            "username",
            "display_name",
            "role",
            "must_change_password",
            "csrf_token",
        }
        assert (
            response.json()["role"] == "inspector"
            and response.json()["must_change_password"] is False
        )
        for name in (SESSION_COOKIE, CSRF_COOKIE):
            cookie = next(
                value
                for value in response.headers.get_list("set-cookie")
                if value.startswith(name + "=")
            )
            assert all(
                flag in cookie for flag in ("Secure", "HttpOnly", "SameSite=strict", "Path=/")
            )
        assert foundation.alice.password not in response.text


async def test_personal_appearance_revisions_and_mass_assignment(foundation):
    async with foundation.client(foundation.alice) as alice:
        async with foundation.client(foundation.bob) as bob:
            original = (await alice.get("/api/v1/me/preferences")).json()
            assert original == {"revision": 1, "theme_mode": "default"}
            for injected in (
                {"role": "administrator"},
                {"owner_user_id": foundation.bob.principal.user_id},
                {"default_theme_mode": "dark"},
                {"database": {"host": "forged"}},
            ):
                denied = await alice.patch(
                    "/api/v1/me/preferences",
                    json={"expected_revision": 1, "theme_mode": "dark", **injected},
                )
                assert denied.status_code == 422
            changed = await alice.patch(
                "/api/v1/me/preferences", json={"expected_revision": 1, "theme_mode": "dark"}
            )
            assert changed.status_code == 200 and changed.json() == {
                "revision": 2,
                "theme_mode": "dark",
            }
            assert (
                await alice.patch(
                    "/api/v1/me/preferences", json={"expected_revision": 1, "theme_mode": "light"}
                )
            ).status_code == 409
            assert (await alice.get("/api/v1/me/preferences")).json()["theme_mode"] == "dark"
            assert (await bob.get("/api/v1/me/preferences")).json() == {
                "revision": 1,
                "theme_mode": "default",
            }
            for mode in ("light", "system", "default"):
                current = (await alice.get("/api/v1/me/preferences")).json()
                assert (
                    await alice.patch(
                        "/api/v1/me/preferences",
                        json={"expected_revision": current["revision"], "theme_mode": mode},
                    )
                ).status_code == 200


async def test_successful_personal_appearance_write_has_redacted_audit(foundation):
    actor = foundation.alice.principal
    before_us = services.utc_now_us()
    async with foundation.client(foundation.alice) as alice:
        changed = await alice.patch(
            "/api/v1/me/preferences",
            json={"expected_revision": 1, "theme_mode": "dark"},
        )
        assert changed.status_code == 200
    async with foundation.database.sessions() as session:
        events = (
            await session.scalars(
                select(Audit).where(
                    Audit.action == "preference.write",
                    Audit.actor_user_id == actor.user_id,
                )
            )
        ).all()
        assert len(events) == 1
        event = events[0]
        assert event.actor_role == "inspector" and event.target_id == actor.user_id
        assert event.project_id is None and event.outcome == "success"
        assert event.created_us >= before_us
        recorded = {column.name: getattr(event, column.name) for column in Audit.__table__.columns}
        assert set(recorded) == {
            "id",
            "actor_user_id",
            "actor_role",
            "action",
            "project_id",
            "target_id",
            "created_us",
            "outcome",
        }
        assert foundation.alice.password not in json.dumps(recorded)
        assert "theme_mode" not in recorded and "password_hash" not in recorded


async def test_stale_cookie_csrf_bootstrap_allows_relogin_without_generic_cookie_deletion(
    foundation,
):
    async with foundation.client(foundation.alice) as alice:
        old_token = alice.cookies[SESSION_COOKIE]
        async with foundation.client(foundation.database.administrator) as admin:
            revoked = await admin.post(
                f"/api/v1/admin/users/{foundation.alice.principal.user_id}/revoke-sessions",
                json={"expected_auth_version": foundation.alice.principal.auth_version},
            )
            assert revoked.status_code == 200
        expired = await alice.get("/api/v1/auth/session")
        assert expired.status_code == 401
        assert not any(
            value.startswith(SESSION_COOKIE + "=")
            for value in expired.headers.get_list("set-cookie")
        )
        assert alice.cookies[SESSION_COOKIE] == old_token
        preflight = await alice.get("/api/v1/auth/csrf")
        assert preflight.status_code == 200
        assert not any(
            value.startswith(SESSION_COOKIE + "=")
            for value in preflight.headers.get_list("set-cookie")
        )
        logged_in = await alice.post(
            "/api/v1/auth/login",
            json={"username": foundation.alice.username, "password": foundation.alice.password},
            headers={"x-csrf-token": preflight.json()["csrf_token"]},
        )
        assert logged_in.status_code == 200
        assert alice.cookies[SESSION_COOKIE] != old_token
        assert (await alice.get("/api/v1/auth/session")).status_code == 200
        assert (await alice.get("/api/v1/projects")).status_code == 200


async def test_shared_settings_require_admin_and_preserve_revision(foundation):
    async with foundation.client(foundation.database.administrator) as admin:
        original = (await admin.get("/api/v1/admin/settings")).json()
        async with foundation.client(foundation.alice) as inspector:
            assert (await inspector.get("/api/v1/admin/settings")).status_code == 403
            assert (
                await inspector.patch(
                    "/api/v1/admin/settings",
                    json={
                        "expected_revision": original["revision"],
                        "branding": "Forbidden",
                        "default_theme_mode": "dark",
                    },
                )
            ).status_code == 403
            assert (await inspector.get("/api/v1/admin/database/status")).status_code == 403
            assert (await inspector.get("/api/v1/admin/audit")).status_code == 403
        for extra in (
            {"role": "administrator"},
            {"database": {"name": "forged"}},
            {"max_workspaces_global": 99999},
        ):
            assert (
                await admin.patch(
                    "/api/v1/admin/settings",
                    json={
                        "expected_revision": original["revision"],
                        "branding": original["branding"],
                        "default_theme_mode": original["default_theme_mode"],
                        **extra,
                    },
                )
            ).status_code == 422
        try:
            changed = await admin.patch(
                "/api/v1/admin/settings",
                json={
                    "expected_revision": original["revision"],
                    "branding": "System Inspector synthetic settings test",
                    "default_theme_mode": "dark",
                },
            )
            assert (
                changed.status_code == 200
                and changed.json()["revision"] == original["revision"] + 1
            )
            assert (
                await admin.patch(
                    "/api/v1/admin/settings",
                    json={
                        "expected_revision": original["revision"],
                        "branding": "Stale overwrite",
                        "default_theme_mode": "light",
                    },
                )
            ).status_code == 409
            public = (await admin.get("/api/v1/ui/bootstrap")).json()
            assert (
                public["branding"] == "System Inspector synthetic settings test"
                and public["default_theme_mode"] == "dark"
            )
        finally:
            current = (await admin.get("/api/v1/admin/settings")).json()
            restored = await admin.patch(
                "/api/v1/admin/settings",
                json={
                    "expected_revision": current["revision"],
                    "branding": original["branding"],
                    "default_theme_mode": original["default_theme_mode"],
                },
            )
            assert restored.status_code == 200
        summary = await admin.get("/api/v1/admin/database/status")
        assert summary.status_code == 200 and summary.json()["ready"] is True
        assert not {"password", "password_file", "username", "vault_key_file"} & set(summary.json())


async def test_demo_viewer_has_safe_projection_in_both_roles(foundation):
    snapshots = []
    for account in (foundation.alice, foundation.database.administrator):
        async with foundation.client(account) as client:
            for project in ("demo-foundation-a", "demo-foundation-b"):
                response = await client.get(f"/api/v1/projects/{project}")
                assert response.status_code == 200
                value = response.json()
                assert value["project_id"] == project and value["demo"] is True
                assert (
                    value["name"].startswith("[Synthetic demo]") and len(value["subsystems"]) == 2
                )
                assert set(value) == {
                    "project_id",
                    "name",
                    "description",
                    "revision",
                    "archived",
                    "demo",
                    "subsystems",
                }
                serialized = json.dumps(value).lower()
                for forbidden in (
                    "credential_id",
                    "username",
                    "password",
                    "jump_host",
                    "known_hosts",
                    "allowed_roots",
                    "connection_id",
                    "approved",
                    "max_live_processes",
                ):
                    assert forbidden not in serialized
                snapshots.append(value)
            own_new = await client.get(f"/api/v1/projects/{foundation.project_a}")
            assert (
                own_new.status_code == 200
                and own_new.json()["demo"] is False
                and own_new.json()["subsystems"] == []
            )
    assert snapshots[:2] == snapshots[2:]


async def test_atomic_workspace_cap_respects_existing_vm_state(foundation):
    async with foundation.database.sessions() as session:
        now = services.utc_now_us()
        initial = await session.scalar(
            select(func.count())
            .select_from(Workspace)
            .where(Workspace.state != "expired", Workspace.expires_us > now)
        )
    assert initial < foundation.config.max_workspaces_global, (
        "Existing VM workspaces leave no capacity for one isolated quota reservation."
    )

    async def reserve(account, project):
        try:
            async with foundation.database.sessions.begin() as session:
                return await services.create_workspace(
                    session,
                    account.principal,
                    ProjectContext(project, account.principal.user_id),
                    max_per_user=2,
                    max_global=initial + 1,
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
    assert len(accepted) == len(rejected) == 1 and rejected[0].code == "LIMIT_REACHED"
    async with foundation.database.sessions() as session:
        row = await session.get(Workspace, (accepted[0]["project_id"], accepted[0]["workspace_id"]))
        assert row.state == "active" and row.revision == 1


async def test_archive_restore_is_revisioned_and_affects_only_target_system(foundation):
    project_a, project_b = foundation.project_a, foundation.project_b
    async with foundation.client(foundation.alice) as inspector:
        opened = [
            (await inspector.post(f"/api/v1/projects/{project}/workspaces", json={})).json()
            for project in (project_a, project_b)
        ]
        assert (
            await inspector.post(
                f"/api/v1/projects/{project_a}/archive", json={"expected_revision": 1}
            )
        ).status_code == 403
        async with foundation.client(foundation.database.administrator) as admin:
            archived = await admin.post(
                f"/api/v1/projects/{project_a}/archive", json={"expected_revision": 1}
            )
            assert archived.status_code == 200 and archived.json()["revision"] == 2
            assert (
                await admin.post(
                    f"/api/v1/projects/{project_a}/archive", json={"expected_revision": 1}
                )
            ).status_code == 409
            denied_edit = await admin.patch(
                f"/api/v1/projects/{project_a}/metadata",
                json={"expected_revision": 2, "name": "Forbidden archived edit", "description": ""},
            )
            assert (
                denied_edit.status_code == 409
                and denied_edit.json()["error"]["code"] == "PROJECT_ARCHIVED"
            )
            denied_start = await inspector.post(f"/api/v1/projects/{project_a}/workspaces", json={})
            assert (
                denied_start.status_code == 409
                and denied_start.json()["error"]["code"] == "PROJECT_ARCHIVED"
            )
            visible = {
                item["project_id"]
                for item in (await inspector.get("/api/v1/projects")).json()["items"]
            }
            assert project_a not in visible and project_b in visible
            all_items = {
                item["project_id"]: item
                for item in (await inspector.get("/api/v1/projects?include_archived=true")).json()[
                    "items"
                ]
            }
            assert (
                all_items[project_a]["archived"] is True and all_items[project_b]["revision"] == 1
            )
            cached = await inspector.get(f"/api/v1/projects/{project_a}")
            assert cached.status_code == 200 and cached.json()["archived"] is True
            for index, state in ((0, "detached"), (1, "active")):
                workspace = opened[index]
                response = await inspector.get(
                    f"/api/v1/projects/{workspace['project_id']}/workspaces/{workspace['workspace_id']}"
                )
                assert response.status_code == 200 and response.json()["state"] == state
            restored = await admin.post(
                f"/api/v1/projects/{project_a}/restore", json={"expected_revision": 2}
            )
            assert restored.status_code == 200 and restored.json()["revision"] == 3
            old = await inspector.get(
                f"/api/v1/projects/{project_a}/workspaces/{opened[0]['workspace_id']}"
            )
            assert old.json()["state"] == "detached" and old.json()["live_session_ids"] == []
            fresh = await inspector.post(f"/api/v1/projects/{project_a}/workspaces", json={})
            assert (
                fresh.status_code == 201
                and fresh.json()["workspace_id"] != opened[0]["workspace_id"]
            )
    async with foundation.database.sessions() as session:
        snapshots = (
            await session.scalars(
                select(ProjectRevision)
                .where(ProjectRevision.project_id == project_a)
                .order_by(ProjectRevision.revision)
            )
        ).all()
        assert [snapshot.revision for snapshot in snapshots] == [1, 2, 3]
        assert all(snapshot.name == "Collision system" for snapshot in snapshots)
        actions = set(
            (await session.scalars(select(Audit.action).where(Audit.project_id == project_a))).all()
        )
        assert actions >= {"system.archive", "system.restore"}


@asynccontextmanager
async def _client(app, config, account):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=config.public_origin,
        headers={"Origin": config.public_origin},
    ) as client:
        token = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
        logged = await client.post(
            "/api/v1/auth/login",
            json={"username": account.username, "password": account.password},
            headers={"x-csrf-token": token},
        )
        assert logged.status_code == 200
        client.headers["x-csrf-token"] = logged.json()["csrf_token"]
        yield client


async def test_cold_app_restart_preserves_users_preferences_systems_and_demo(database, tmp_path):
    config = replace(
        database.config,
        state_dir=str(tmp_path / "stage1-api-cold-state"),
        default_theme_mode="light",
    )
    project_id = f"stage1-api-cold-{uuid4().hex}"
    username, password = f"stage1-api-cold-user-{uuid4().hex}", issue_token()
    account = None
    try:
        first_app = create_app(config)
        async with first_app.router.lifespan_context(first_app):
            async with database.sessions.begin() as session:
                user = await auth.create_user(
                    session,
                    database.administrator.principal,
                    username,
                    "Synthetic cold restart",
                    password,
                )
                account = type(database.administrator)(username, password, auth._principal(user))
                await services.create_project(
                    session,
                    database.administrator.principal,
                    "Synthetic cold retained",
                    "Restart persistence",
                    project_id=project_id,
                )
                demo_before = {
                    row.project_id: row.payload
                    for row in (await session.scalars(select(DemoSnapshot))).all()
                }
            async with _client(first_app, config, account) as client:
                assert (
                    await client.patch(
                        "/api/v1/me/preferences",
                        json={"expected_revision": 1, "theme_mode": "dark"},
                    )
                ).status_code == 200
                created = await client.post(f"/api/v1/projects/{project_id}/workspaces", json={})
                assert created.status_code == 201
                old_workspace = created.json()
                default_before = (await client.get("/api/v1/ui/bootstrap")).json()
        second_app = create_app(replace(config, default_theme_mode="dark"))
        async with second_app.router.lifespan_context(second_app):
            async with _client(second_app, config, account) as client:
                assert (await client.get("/api/v1/me/preferences")).json() == {
                    "revision": 2,
                    "theme_mode": "dark",
                }
                assert (await client.get("/api/v1/ui/bootstrap")).json() == default_before
                viewer = await client.get(f"/api/v1/projects/{project_id}")
                assert (
                    viewer.status_code == 200 and viewer.json()["name"] == "Synthetic cold retained"
                )
                old = await client.get(
                    f"/api/v1/projects/{project_id}/workspaces/{old_workspace['workspace_id']}"
                )
                assert (
                    old.status_code == 200
                    and old.json()["state"] == "detached"
                    and old.json()["revision"] == 2
                )
                fresh = await client.post(f"/api/v1/projects/{project_id}/workspaces", json={})
                assert (
                    fresh.status_code == 201
                    and fresh.json()["workspace_id"] != old_workspace["workspace_id"]
                )
                async with database.sessions() as session:
                    assert (await session.get(User, account.principal.user_id)).enabled is True
                    assert (await session.get(Project, project_id)).revision == 1
                    demo_after = {
                        row.project_id: row.payload
                        for row in (await session.scalars(select(DemoSnapshot))).all()
                    }
                    assert demo_after == demo_before and set(demo_after) >= {
                        "demo-foundation-a",
                        "demo-foundation-b",
                    }
    finally:
        if account is not None:
            async with database.sessions.begin() as session:
                await session.execute(
                    update(Workspace)
                    .where(Workspace.owner_user_id == account.principal.user_id)
                    .values(state="expired")
                )
                project = await session.get(Project, project_id)
                if project is not None and not project.archived:
                    await services.set_project_archived(
                        session,
                        database.administrator.principal,
                        project_id,
                        project.revision,
                        archived=True,
                    )
