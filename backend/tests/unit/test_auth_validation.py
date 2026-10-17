"""The shared fresh-row validator preserves exact account/session boundaries."""

import pytest

from inspector.auth import _validated_authentication
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
