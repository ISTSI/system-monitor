"""Account input/output boundaries without a fake persistence implementation."""

import json

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from inspector import auth
from inspector.accounts import (
    AccountVersionInput,
    ChangePasswordInput,
    CreateAccountInput,
    ResetPasswordInput,
    UpdateAccountInput,
    build_account_router,
)
from inspector.persistence.models import User


def test_account_and_password_payloads_forbid_authority_mass_assignment():
    payloads = (
        (
            CreateAccountInput,
            {"username": "someone", "display_name": "Someone", "password": "temporary-password"},
        ),
        (UpdateAccountInput, {"expected_auth_version": 1, "enabled": False}),
        (ResetPasswordInput, {"expected_auth_version": 1, "password": "temporary-password"}),
        (AccountVersionInput, {"expected_auth_version": 1}),
        (
            ChangePasswordInput,
            {"current_password": "temporary-password", "new_password": "replacement-password"},
        ),
    )
    for model, payload in payloads:
        for forbidden in ("owner_user_id", "password_hash", "auth_version", "project_id"):
            with pytest.raises(ValidationError):
                model.model_validate({**payload, forbidden: "forged"})
    for model, payload in payloads[-2:]:
        with pytest.raises(ValidationError):
            model.model_validate({**payload, "role": "administrator"})


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_auth_version": 1},
        {"expected_auth_version": 1, "enabled": "false"},
        {"expected_auth_version": True, "enabled": False},
        {"expected_auth_version": 0, "enabled": False},
        {"expected_auth_version": 1, "enabled": None, "role": "inspector"},
        {"expected_auth_version": 1, "role": "root"},
    ],
)
def test_account_update_requires_typed_revision_and_explicit_valid_change(payload):
    with pytest.raises(ValidationError):
        UpdateAccountInput.model_validate(payload)


def test_password_models_hide_secrets_and_new_accounts_default_to_inspector():
    password = "sensitive-temporary-password"
    created = CreateAccountInput(username="new", display_name="New", password=password)
    assert created.role == "inspector"
    assert created.must_change_password is False
    assert password not in repr(created)
    reset = ResetPasswordInput(expected_auth_version=1, password=password)
    assert reset.must_change_password is True
    assert password not in repr(reset)


def test_account_projection_cannot_include_password_or_session_verifiers():
    user = User(
        id="user-a",
        username_key="alice",
        display_name="Alice",
        role="inspector",
        password_hash="secret-hash",
        enabled=True,
        auth_version=3,
        must_change_password=True,
    )
    user.extra_secret = "future-private-field"
    projected = auth.account_response(user)
    assert set(projected) == {
        "user_id",
        "username",
        "display_name",
        "role",
        "enabled",
        "auth_version",
        "must_change_password",
    }
    assert "secret-hash" not in json.dumps(projected)
    assert "future-private-field" not in json.dumps(projected)
    assert auth._principal(user).must_change_password is True
    assert auth._principal(user).username == "alice"


def test_account_openapi_declares_permissions_and_write_only_passwords():
    async def unused():
        raise AssertionError("OpenAPI generation must not access the database.")

    app = FastAPI()
    app.include_router(build_account_router(unused, unused, unused))
    schema = app.openapi()
    for path, operations in schema["paths"].items():
        for operation in operations.values():
            expected = "self.password.change" if path == "/api/v1/me/password" else "users.manage"
            assert operation["x-permission"] == expected
    models = schema["components"]["schemas"]
    for model, names in (
        ("CreateAccountInput", ("password",)),
        ("ResetPasswordInput", ("password",)),
        ("ChangePasswordInput", ("current_password", "new_password")),
    ):
        for name in names:
            assert models[model]["properties"][name]["writeOnly"] is True
    assert "password" not in models["AccountResponse"]["properties"]
