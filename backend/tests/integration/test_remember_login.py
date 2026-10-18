"""Actual MariaDB sessions retain an explicit opt-in without weakening revocation."""

import pytest

from inspector import auth, services
from inspector.app import CSRF_COOKIE, SESSION_COOKIE
from inspector.persistence.models import AuthSession
from inspector.security import token_hash

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


async def sign_in(client, account, **choice):
    csrf = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": account.username, "password": account.password, **choice},
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 200
    client.headers["x-csrf-token"] = response.json()["csrf_token"]
    return response


@pytest.mark.parametrize("choice", [{}, {"remember_me": False}, {"remember_me": True}])
async def test_cookie_and_persisted_session_lifetimes_follow_explicit_choice(
    foundation, monkeypatch, choice
):
    now = services.utc_now_us()
    monkeypatch.setattr(services, "utc_now_us", lambda: now)
    remembered = choice.get("remember_me", False)
    lifetime = auth.REMEMBER_SESSION_US if remembered else foundation.config.absolute_timeout_us
    async with foundation.client() as client:
        response = await sign_in(client, foundation.alice, **choice)
        for name in (SESSION_COOKIE, CSRF_COOKIE):
            cookie = next(
                item
                for item in response.headers.get_list("set-cookie")
                if item.startswith(name + "=")
            )
            assert f"Max-Age={lifetime // 1_000_000}" in cookie
            assert all(flag in cookie for flag in ("HttpOnly", "Secure", "SameSite=strict"))
        verifier = token_hash(client.cookies.get(SESSION_COOKIE))
        async with foundation.database.sessions() as session:
            record = await session.get(AuthSession, verifier)
            assert record.remember_me is remembered
            assert record.created_us == now and record.last_seen_us == now
            assert record.expires_us == now + lifetime
        # A fresh client has no in-memory CSRF token, as after a browser restart.
        cookies = client.cookies
        now += foundation.config.idle_timeout_us
        if not remembered:
            assert (await client.get("/api/v1/auth/session")).status_code == 401
            return
        async with foundation.client(cookies=cookies) as restarted:
            assert (await restarted.get("/api/v1/auth/session")).status_code == 200
            assert (
                await restarted.post(
                    "/api/v1/projects",
                    json={"name": "Rejected without CSRF"},
                    headers={"x-csrf-token": "wrong"},
                )
            ).status_code == 403
            now = record.expires_us - 1
            assert (await restarted.get("/api/v1/auth/session")).status_code == 200
            preferences = (await restarted.get("/api/v1/me/preferences")).json()
            assert (
                await restarted.patch(
                    "/api/v1/me/preferences",
                    json={"expected_revision": preferences["revision"], "theme_mode": "dark"},
                )
            ).status_code == 200
            async with foundation.database.sessions() as session:
                retained = await session.get(AuthSession, verifier)
                assert retained.last_seen_us == now
                assert retained.expires_us == record.expires_us
            now += 1
            assert (await restarted.get("/api/v1/auth/session")).status_code == 401


@pytest.mark.parametrize("action", ["logout", "administrator_revoke"])
async def test_remembered_login_revocation_affects_every_page(foundation, action):
    async with foundation.client() as first:
        await sign_in(first, foundation.alice, remember_me=True)
        async with foundation.client(cookies=first.cookies) as second:
            if action == "logout":
                assert (await first.post("/api/v1/auth/logout", json={})).status_code == 200
            else:
                async with foundation.client(foundation.database.administrator) as administrator:
                    response = await administrator.post(
                        f"/api/v1/admin/users/{foundation.alice.principal.user_id}/revoke-sessions",
                        json={"expected_auth_version": foundation.alice.principal.auth_version},
                    )
                    assert response.status_code == 200
            for client in (first, second):
                assert (await client.get("/api/v1/auth/session")).status_code == 401
