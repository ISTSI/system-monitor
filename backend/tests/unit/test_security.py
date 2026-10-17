import asyncio
import threading

import pytest

from inspector.auth import SessionCredentials
from inspector.domain import Principal
from inspector.errors import DomainError
from inspector.security import (
    Passwords,
    authorize,
    issue_token,
    normalize_username,
    require_admin,
    token_hash,
    valid_login_password,
    validate_new_password,
)


def test_username_casefold_and_invalid_input_do_not_reflect_values() -> None:
    assert normalize_username("  StraSSe  ") == normalize_username("Straße")
    for invalid in ("", "\n", "bad\x00name", "x" * 129):
        with pytest.raises(DomainError) as error:
            normalize_username(invalid)
        assert error.value.status == 422
        assert error.value.message == "Invalid account details."


@pytest.mark.parametrize("password", ["short", "a" * 1025, "ą" * 513, "\ud800" * 12])
def test_password_rejects_overlong_or_short_without_echo(password: str) -> None:
    with pytest.raises(DomainError) as error:
        validate_new_password(password)
    assert error.value.code == "INVALID_PASSWORD"
    assert password not in error.value.message


def test_password_login_byte_bound_and_minimum_creation() -> None:
    validate_new_password("é" * 512)
    assert valid_login_password("old")
    assert not valid_login_password("")
    assert not valid_login_password("é" * 513)
    assert not valid_login_password("\ud800")


async def test_real_argon2_passwords_and_nonexistent_account() -> None:
    service = Passwords()
    password = "correct horse battery staple"
    first = await service.hash(password)
    second = await service.hash(password)
    assert first.startswith("$argon2id$")
    assert first != second
    assert await service.verify(first, password)
    assert not await service.verify(first, "incorrect password")
    assert not await service.verify(None, password)
    assert not await service.verify("malformed verifier", password)


async def test_repeated_cancellation_keeps_password_worker_reserved() -> None:
    service = Passwords(workers=1)
    first_started, second_started, release_first = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )

    def first_work() -> str:
        first_started.set()
        if not release_first.wait(timeout=3):
            raise TimeoutError("Test did not release the worker.")
        return "first"

    def second_work() -> str:
        second_started.set()
        return "second"

    first = asyncio.create_task(service._run(first_work))
    second = None
    try:
        assert await asyncio.to_thread(first_started.wait, 1)
        first.cancel()
        await asyncio.sleep(0)
        first.cancel()
        second = asyncio.create_task(service._run(second_work))
        await asyncio.sleep(0.02)
        assert not second_started.is_set()
    finally:
        release_first.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        if second is not None:
            assert await second == "second"


def test_tokens_are_opaque_distinct_verifier_only_secrets() -> None:
    first, second = issue_token(), issue_token()
    assert len(first) == 43
    assert first != second
    assert token_hash(first) != first
    assert token_hash(first) != token_hash(second)
    assert len(token_hash(first) or "") == 64
    assert token_hash("unexpected.token") is None
    assert token_hash("x" * 44) is None
    assert token_hash("é" * 43) is None
    assert token_hash("a" * 43 + "\n") is None


def test_session_repr_excludes_credentials_and_contains_no_project_scope() -> None:
    credentials = SessionCredentials(
        issue_token(), issue_token(), Principal("user-a", "inspector", 1), 10
    )
    assert credentials.token not in repr(credentials)
    assert credentials.csrf_token not in repr(credentials)
    assert not hasattr(credentials, "project_id")


def test_role_denials_unknown_actions_and_private_owner_checks() -> None:
    inspector = Principal("inspector-a", "inspector", 1)
    admin = Principal("admin-a", "administrator", 1)
    require_admin(admin)
    authorize(inspector, "system.list")
    authorize(inspector, "workspace.read", owner_user_id=inspector.user_id)
    for principal in (inspector, admin):
        authorize(principal, "investigation.delete", owner_user_id=principal.user_id)
        with pytest.raises(DomainError) as error:
            authorize(principal, "workspace.read", owner_user_id="another-user")
        assert error.value.status == 404
        with pytest.raises(DomainError) as error:
            authorize(principal, "investigation.delete", owner_user_id="another-user")
        assert error.value.status == 404
    for action in ("system.create", "users.manage", "invented.future.action"):
        with pytest.raises(DomainError) as error:
            authorize(inspector, action)
        assert error.value.status == 403
    with pytest.raises(DomainError) as error:
        authorize(admin, "invented.future.action")
    assert error.value.status == 403
    with pytest.raises(DomainError):
        authorize(Principal("forged", "root", 1), "system.list")
