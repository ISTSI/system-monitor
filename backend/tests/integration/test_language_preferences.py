"""Language persistence and account/default boundaries against real MariaDB."""

from dataclasses import replace

import pytest
from sqlalchemy import delete, select

from inspector.foundation import initialize_settings
from inspector.persistence.models import ApplicationSetting, Audit, UserPreference

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]
PREFERENCES = "/api/v1/me/preferences"
SETTINGS = "/api/v1/admin/settings"
BOOTSTRAP = "/api/v1/ui/bootstrap"


async def patch(client, path, **changes):
    current = (await client.get(path)).json()
    response = await client.patch(path, json={"expected_revision": current["revision"], **changes})
    assert response.status_code == 200, response.text
    return response.json()


async def test_new_settings_honor_configured_language_and_restart_preserves_it(database):
    # An isolated transaction simulates the fresh-install settings table and is
    # always rolled back, preserving the suite's shared synthetic settings.
    async with database.sessions() as session:
        try:
            await session.execute(delete(ApplicationSetting))
            initialized = await initialize_settings(
                session, replace(database.config, default_language="pl")
            )
            assert initialized.default_language == "pl"
            assert initialized.revision == 1
            restarted = await initialize_settings(
                session, replace(database.config, default_language="en")
            )
            assert restarted.default_language == "pl"
        finally:
            await session.rollback()


async def test_language_is_personal_revisioned_and_partial_theme_updates_preserve_it(foundation):
    async with foundation.client(foundation.alice) as alice:
        async with foundation.client(foundation.bob) as bob:
            workspaces = []
            for project_id in (foundation.project_a, foundation.project_b):
                response = await alice.post(f"/api/v1/projects/{project_id}/workspaces", json={})
                assert response.status_code == 201
                workspaces.append((project_id, response.json()))
            initial = (await alice.get(PREFERENCES)).json()
            assert initial == {"revision": 1, "theme_mode": "default", "language": "default"}
            language = await patch(alice, PREFERENCES, language="pl")
            assert language == {"revision": 2, "theme_mode": "default", "language": "pl"}
            theme = await patch(alice, PREFERENCES, theme_mode="light")
            assert theme == {"revision": 3, "theme_mode": "light", "language": "pl"}
            async with foundation.client(cookies=alice.cookies) as same_account_window:
                assert (await same_account_window.get(PREFERENCES)).json() == theme
                stale = await same_account_window.patch(
                    PREFERENCES, json={"expected_revision": 2, "language": "en"}
                )
                assert stale.status_code == 409
                assert stale.json()["error"]["code"] == "REVISION_CONFLICT"
            assert (await bob.get(PREFERENCES)).json() == initial
            restored = await patch(alice, PREFERENCES, language="default")
            assert restored["theme_mode"] == "light" and restored["language"] == "default"
            for project_id, workspace in workspaces:
                retained = (
                    await alice.get(
                        f"/api/v1/projects/{project_id}/workspaces/{workspace['workspace_id']}"
                    )
                ).json()
                assert {
                    field: retained[field]
                    for field in ("project_id", "workspace_id", "state", "revision")
                } == {
                    field: workspace[field]
                    for field in ("project_id", "workspace_id", "state", "revision")
                }
    async with foundation.database.sessions() as session:
        value = await session.get(UserPreference, foundation.alice.principal.user_id)
        assert value.language == "default" and value.theme_mode == "light"
        audit = (
            await session.scalars(
                select(Audit).where(
                    Audit.action == "preference.write",
                    Audit.actor_user_id == foundation.alice.principal.user_id,
                )
            )
        ).all()
        assert len(audit) == 3


async def test_shared_language_is_admin_only_and_bootstrap_tracks_durable_default(foundation):
    async with foundation.client(foundation.database.administrator) as admin:
        original = (await admin.get(SETTINGS)).json()
        try:
            changed = await patch(admin, SETTINGS, default_language="pl")
            assert {
                key: value
                for key, value in changed.items()
                if key not in {"revision", "default_language"}
            } == {
                key: value
                for key, value in original.items()
                if key not in {"revision", "default_language"}
            }
            assert changed["default_language"] == "pl"
            # Older clients still sending branding/theme preserve the saved language.
            legacy = await patch(
                admin, SETTINGS, branding=changed["branding"], default_theme_mode="light"
            )
            assert legacy["default_language"] == "pl"
            assert (
                legacy["additional_security_measures"] == original["additional_security_measures"]
            )
            stale = await admin.patch(
                SETTINGS, json={"expected_revision": original["revision"], "default_language": "en"}
            )
            assert stale.status_code == 409
            async with foundation.client() as signed_out:
                assert (await signed_out.get(BOOTSTRAP)).json()["default_language"] == "pl"
                assert (await signed_out.get(PREFERENCES)).status_code == 401
            async with foundation.client(foundation.alice) as inspector:
                assert (await inspector.get(SETTINGS)).status_code == 403
                assert (
                    await inspector.patch(
                        SETTINGS,
                        json={"expected_revision": legacy["revision"], "default_language": "en"},
                    )
                ).status_code == 403
                assert (await inspector.get(PREFERENCES)).json()["language"] == "default"
                await patch(inspector, PREFERENCES, language="en")
                assert (await inspector.get(BOOTSTRAP)).json()["default_language"] == "pl"
            await patch(admin, PREFERENCES, language="pl")
            async with foundation.database.sessions.begin() as session:
                settings = await session.get(ApplicationSetting, 1)
                assert settings.default_language == "pl"
                restarted = await initialize_settings(
                    session, replace(foundation.config, default_language="en")
                )
                assert restarted.default_language == "pl"
        finally:
            await patch(
                admin,
                SETTINGS,
                branding=original["branding"],
                default_theme_mode=original["default_theme_mode"],
                default_language=original["default_language"],
                additional_security_measures=original["additional_security_measures"],
            )


async def test_language_updates_reject_csrf_invalid_values_and_mass_assignment(foundation):
    async with foundation.client(foundation.alice) as inspector:
        async with foundation.client(foundation.database.administrator) as admin:
            for client, path, field in (
                (inspector, PREFERENCES, "language"),
                (admin, SETTINGS, "default_language"),
            ):
                original = (await client.get(path)).json()
                payload = {"expected_revision": original["revision"], field: "pl"}
                csrf = client.headers.pop("x-csrf-token")
                try:
                    assert (await client.patch(path, json=payload)).status_code == 403
                finally:
                    client.headers["x-csrf-token"] = csrf
                for invalid in (None, "PL", "de", "", True, 1, [], {}):
                    rejected = await client.patch(path, json={**payload, field: invalid})
                    assert rejected.status_code == 422, (invalid, rejected.text)
                for injection in (
                    {"role": "administrator"},
                    {"owner_user_id": foundation.bob.principal.user_id},
                    {"database": {"host": "forged"}},
                ):
                    assert (
                        await client.patch(path, json={**payload, **injection})
                    ).status_code == 422
                assert (
                    await client.patch(path, json={"expected_revision": original["revision"]})
                ).status_code == 422
                assert (await client.get(path)).json() == original
