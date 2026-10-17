"""Explicit account HTTP models and routes; authentication is injected by the app."""

from collections.abc import Callable
from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from inspector import auth
from inspector.domain import ID_PATTERN, Principal

Role = Literal["administrator", "inspector"]
AccountId = Annotated[str, Path(pattern=ID_PATTERN)]


class AccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AccountResponse(AccountInput):
    user_id: str = Field(pattern=ID_PATTERN)
    username: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    role: Role
    enabled: bool
    auth_version: int = Field(ge=1)
    must_change_password: bool


class AccountListResponse(AccountInput):
    items: list[AccountResponse] = Field(max_length=1000)


class CreateAccountInput(AccountInput):
    username: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    password: SecretStr = Field(min_length=12, max_length=1024)
    role: Role = "inspector"
    must_change_password: bool = False


class AccountVersionInput(AccountInput):
    expected_auth_version: int = Field(ge=1)


class UpdateAccountInput(AccountVersionInput):
    enabled: bool | None = None
    role: Role | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if self.enabled is None and self.role is None:
            raise ValueError("Choose an account change.")
        if any(
            getattr(self, name) is None
            for name in ("enabled", "role")
            if name in self.model_fields_set
        ):
            raise ValueError("Account fields cannot be null.")
        return self


class ResetPasswordInput(AccountVersionInput):
    password: SecretStr = Field(min_length=12, max_length=1024)
    must_change_password: bool = True


class ChangePasswordInput(AccountInput):
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=12, max_length=1024)


class PasswordChangedResponse(AccountInput):
    status: Literal["password_changed"]
    sign_in_required: Literal[True]


def build_account_router(
    session_dependency: Callable[..., Any],
    actor_dependency: Callable[..., Any],
    writer_dependency: Callable[..., Any],
) -> APIRouter:
    """Use the application's one transaction and its CSRF-protected writer dependency."""
    router = APIRouter(prefix="/api/v1", tags=["accounts"])

    @router.get(
        "/admin/users",
        response_model=AccountListResponse,
        openapi_extra={"x-permission": "users.manage"},
    )
    async def list_accounts(
        session: AsyncSession = Depends(session_dependency, scope="function"),
        principal: Principal = Depends(actor_dependency),
    ) -> dict:
        return await auth.list_users(session, principal)

    @router.post(
        "/admin/users",
        status_code=201,
        response_model=AccountResponse,
        openapi_extra={"x-permission": "users.manage"},
    )
    async def create_account(
        payload: CreateAccountInput,
        session: AsyncSession = Depends(session_dependency, scope="function"),
        principal: Principal = Depends(writer_dependency),
    ) -> dict:
        user = await auth.create_user(
            session,
            principal,
            payload.username,
            payload.display_name,
            payload.password.get_secret_value(),
            payload.role,
            must_change_password=payload.must_change_password,
        )
        return auth.account_response(user)

    @router.patch(
        "/admin/users/{user_id}",
        response_model=AccountResponse,
        openapi_extra={"x-permission": "users.manage"},
    )
    async def update_account(
        user_id: AccountId,
        payload: UpdateAccountInput,
        session: AsyncSession = Depends(session_dependency, scope="function"),
        principal: Principal = Depends(writer_dependency),
    ) -> dict:
        user = await auth.update_user(
            session,
            principal,
            user_id,
            payload.expected_auth_version,
            enabled=payload.enabled,
            role=payload.role,
        )
        return auth.account_response(user)

    @router.post(
        "/admin/users/{user_id}/reset-password",
        response_model=AccountResponse,
        openapi_extra={"x-permission": "users.manage"},
    )
    async def reset_account_password(
        user_id: AccountId,
        payload: ResetPasswordInput,
        session: AsyncSession = Depends(session_dependency, scope="function"),
        principal: Principal = Depends(writer_dependency),
    ) -> dict:
        user = await auth.reset_password(
            session,
            principal,
            user_id,
            payload.expected_auth_version,
            payload.password.get_secret_value(),
            must_change_password=payload.must_change_password,
        )
        return auth.account_response(user)

    @router.post(
        "/admin/users/{user_id}/revoke-sessions",
        response_model=AccountResponse,
        openapi_extra={"x-permission": "users.manage"},
    )
    async def revoke_account_sessions(
        user_id: AccountId,
        payload: AccountVersionInput,
        session: AsyncSession = Depends(session_dependency, scope="function"),
        principal: Principal = Depends(writer_dependency),
    ) -> dict:
        user = await auth.revoke_sessions(
            session, principal, user_id, payload.expected_auth_version
        )
        return auth.account_response(user)

    @router.post(
        "/me/password",
        response_model=PasswordChangedResponse,
        openapi_extra={"x-permission": "self.password.change"},
    )
    async def change_own_password(
        payload: ChangePasswordInput,
        session: AsyncSession = Depends(session_dependency, scope="function"),
        principal: Principal = Depends(writer_dependency),
    ) -> JSONResponse:
        await auth.change_password(
            session,
            principal,
            payload.current_password.get_secret_value(),
            payload.new_password.get_secret_value(),
        )
        response = JSONResponse({"status": "password_changed", "sign_in_required": True})
        for cookie in ("__Host-si-session", "__Host-si-csrf", "__Host-si-pre-csrf"):
            response.delete_cookie(cookie, path="/", secure=True, httponly=True, samesite="strict")
        return response

    return router
