"""The shared fresh-row validator preserves exact account/session boundaries."""

import pytest

from inspector.app import LoginInput
from inspector.auth import REMEMBER_SESSION_US, _validated_authentication
from inspector.errors import DomainError
from inspector.persistence.models import AuthSession, User


def records():
    return (
        AuthSession(
            user_id="owner", auth_version=2, created_us=100, last_seen_us=500, expires_us=1000
        ),
        User(
            id="owner",
            role="inspector",
            auth_version=2,
            enabled=True,
            must_change_password=False,
            display_name="Synthetic inspector",
            username_key="owner",
        ),
    )


@pytest.mark.parametrize(
    "change",
    ["missing_login", "missing_user", "disabled", "role", "version", "future", "expired", "idle"],
)
def test_fresh_authentication_rejects_revoked_or_out_of_bounds_records(change):
    login, user = records()
    now = 600
    if change == "missing_login":
        login = None
    elif change == "missing_user":
        user = None
    elif change == "disabled":
        user.enabled = False
    elif change == "role":
        user.role = "unrecognized"
    elif change == "version":
        user.auth_version += 1
    elif change == "future":
        now = 99
    elif change == "expired":
        now = 1000
    elif change == "idle":
        now = 700  # Exactly last_seen + idle timeout is excluded.
    with pytest.raises(DomainError) as denied:
        _validated_authentication(login, user, now, 200)
    assert denied.value.code == "AUTH_REQUIRED"


@pytest.mark.parametrize("renew", [False, True])
def test_fresh_authentication_preserves_idle_renewal_policy(renew):
    login, user = records()
    actor = _validated_authentication(login, user, 699, 200, renew_idle=renew)
    assert actor.user_id == "owner" and actor.auth_version == 2
    assert login.last_seen_us == (699 if renew else 500)


def test_fresh_authentication_requires_password_change_unless_explicitly_allowed():
    login, user = records()
    user.must_change_password = True
    with pytest.raises(DomainError) as denied:
        _validated_authentication(login, user, 600, 200)
    assert denied.value.code == "PASSWORD_CHANGE_REQUIRED"
    assert _validated_authentication(
        login, user, 600, 200, allow_password_change=True
    ).must_change_password


def test_fresh_authentication_rejects_nonpositive_idle_budget():
    login, user = records()
    with pytest.raises(ValueError):
        _validated_authentication(login, user, 600, 0)


def test_remembered_session_survives_idle_but_never_renews_its_thirty_day_end():
    login, user = records()
    login.remember_me = True
    login.expires_us = login.created_us + REMEMBER_SESSION_US
    before_end = login.expires_us - 1
    actor = _validated_authentication(login, user, before_end, 200, renew_idle=True)
    assert actor.user_id == user.id
    assert login.last_seen_us == before_end
    assert login.expires_us == login.created_us + REMEMBER_SESSION_US
    with pytest.raises(DomainError) as expired:
        _validated_authentication(login, user, login.expires_us, 200)
    assert expired.value.code == "AUTH_REQUIRED"


@pytest.mark.parametrize("change", ["disabled", "role", "version", "future"])
def test_remembered_session_never_bypasses_account_or_creation_checks(change):
    login, user = records()
    login.remember_me = True
    if change == "disabled":
        user.enabled = False
    elif change == "role":
        user.role = "unrecognized"
    elif change == "version":
        user.auth_version += 1
    now = 99 if change == "future" else 800
    with pytest.raises(DomainError) as expired:
        _validated_authentication(login, user, now, 200)
    assert expired.value.code == "AUTH_REQUIRED"


def test_ordinary_thirty_day_config_still_uses_the_configured_idle_policy():
    login, user = records()
    login.remember_me = False
    login.expires_us = login.created_us + REMEMBER_SESSION_US
    with pytest.raises(DomainError):
        _validated_authentication(login, user, 700, 200)


@pytest.mark.parametrize("choice", [True, False])
def test_login_remember_choice_is_optional_and_strictly_boolean(choice):
    assert LoginInput(username="user", password="secret").remember_me is False
    assert LoginInput(username="user", password="secret", remember_me=choice).remember_me is choice


@pytest.mark.parametrize("choice", ["true", "false", 1, 0, None, [], {}])
def test_login_rejects_coerced_or_malformed_remember_choice(choice):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LoginInput(username="user", password="secret", remember_me=choice)
