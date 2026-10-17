"""Transactional local accounts and opaque server-side sessions.

Callers own the transaction and must commit successful operations. There is no
project/current-system field on an account session. Authentication failures are
nonrevealing; callers may commit a failed login's audit-only transaction.

This foundation serializes short authenticated transactions with SecurityState
before locking account/session rows. Account updates and workspace reservations
use that same order. Future long-running operations must leave the transaction
before doing file/SSH work, and revalidate on their next dispatch.
"""

from __future__ import annotations

import hmac
import time
from dataclasses import dataclass, field
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inspector.domain import Principal
from inspector.errors import DomainError
from inspector.persistence.models import Audit, AuthSession, SecurityState, User, Workspace
from inspector.security import (
    ROLES,
    authorize,
    hash_password,
    issue_token,
    normalize_username,
    require_admin,
    token_hash,
    validate_new_password,
    verify_password,
)


@dataclass(frozen=True)
class SessionCredentials:
    token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    principal: Principal
    expires_us: int


def _audit(
    session: AsyncSession,
    action: str,
    now_us: int,
    *,
    principal: Principal | None = None,
    target_id: str | None = None,
    outcome: str = "success",
) -> None:
    session.add(
        Audit(
            id=str(uuid4()),
            actor_user_id=principal.user_id if principal else None,
            actor_role=principal.role if principal else None,
            action=action,
            project_id=None,
            target_id=target_id,
            created_us=now_us,
            outcome=outcome,
        )
    )


async def _security_lock(session: AsyncSession) -> None:
    guard = await session.scalar(
        select(SecurityState).where(SecurityState.id == 1).with_for_update()
    )
    if guard is None:
        raise DomainError("SECURITY_NOT_READY", "Security state is not initialized.", 503)


def _principal(user: User) -> Principal:
    return Principal(
        user_id=user.id,
        role=user.role,
        auth_version=user.auth_version,
        must_change_password=bool(user.must_change_password),
        display_name=user.display_name,
        username=user.username_key,
    )


async def _current_user(
    session: AsyncSession, principal: Principal, *, allow_password_change: bool = False
) -> User:
    """Security singleton precedes every account/session lock, including direct services."""
    await _security_lock(session)
    user = await session.get(User, principal.user_id, with_for_update=True, populate_existing=True)
    if (
        user is None
        or not user.enabled
        or user.role not in ROLES
        or user.auth_version != principal.auth_version
    ):
        raise DomainError("AUTH_REQUIRED", "Authentication is required.", 401)
    if user.must_change_password and not allow_password_change:
        raise DomainError(
            "PASSWORD_CHANGE_REQUIRED", "Change your password before continuing.", 403
        )
    return user


async def _revoke_user(session: AsyncSession, user: User, now_us: int) -> None:
    """No live jobs exist in Stage 01; expire their future page ownership now."""
    user.auth_version += 1
    await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    await session.execute(
        update(Workspace)
        .where(Workspace.owner_user_id == user.id, Workspace.state != "expired")
        .values(state="expired", expires_us=now_us, revision=Workspace.revision + 1)
    )


def _display_name(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise DomainError("INVALID_ACCOUNT", "Invalid account details.", 422)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise DomainError("INVALID_ACCOUNT", "Invalid account details.", 422)
    return value.strip()


async def bootstrap_admin(
    session: AsyncSession,
    username: str,
    display_name: str,
    password: str,
    *,
    now_us: int | None = None,
) -> User:
    """Server-side CLI only; the migration creates the singleton lock row."""
    username_key = normalize_username(username)
    safe_display_name = _display_name(display_name)
    verifier = await hash_password(password)
    await _security_lock(session)
    existing_admin = await session.scalar(
        select(User.id).where(User.enabled.is_(True), User.role == "administrator").limit(1)
    )
    if existing_admin is not None:
        raise DomainError("BOOTSTRAP_CLOSED", "An enabled Administrator already exists.", 409)
    if await session.scalar(select(User.id).where(User.username_key == username_key)) is not None:
        raise DomainError("ACCOUNT_EXISTS", "Account already exists.", 409)
    user = User(
        id=str(uuid4()),
        username_key=username_key,
        display_name=safe_display_name,
        password_hash=verifier,
        role="administrator",
        enabled=True,
        auth_version=1,
        must_change_password=False,
    )
    session.add(user)
    await session.flush()
    _audit(
        session,
        "auth.bootstrap",
        time.time_ns() // 1000 if now_us is None else now_us,
        principal=_principal(user),
        target_id=user.id,
    )
    await session.flush()
    return user


async def create_user(
    session: AsyncSession,
    actor: Principal,
    username: str,
    display_name: str,
    password: str,
    role: str = "inspector",
    *,
    must_change_password: bool = False,
    now_us: int | None = None,
) -> User:
    authorize(actor, "users.manage")
    if role not in ROLES:
        raise DomainError("INVALID_ACCOUNT", "Invalid account details.", 422)
    if type(must_change_password) is not bool:
        raise DomainError("INVALID_ACCOUNT", "Invalid account details.", 422)
    username_key = normalize_username(username)
    safe_display_name = _display_name(display_name)
    verifier = await hash_password(password)
    current_actor = await _current_user(session, actor)
    require_admin(_principal(current_actor))
    if await session.scalar(select(User.id).where(User.username_key == username_key)) is not None:
        raise DomainError("ACCOUNT_EXISTS", "Account already exists.", 409)
    user = User(
        id=str(uuid4()),
        username_key=username_key,
        display_name=safe_display_name,
        password_hash=verifier,
        role=role,
        enabled=True,
        auth_version=1,
        must_change_password=must_change_password,
    )
    session.add(user)
    await session.flush()
    _audit(
        session,
        "auth.account.create",
        time.time_ns() // 1000 if now_us is None else now_us,
        principal=actor,
        target_id=user.id,
    )
    await session.flush()
    return user


async def login(
    session: AsyncSession,
    username: str,
    password: str,
    now_us: int,
    idle_timeout_us: int,
    absolute_timeout_us: int,
) -> SessionCredentials:
    if idle_timeout_us <= 0 or absolute_timeout_us <= 0:
        raise ValueError("Session timeouts must be positive.")
    try:
        username_key = normalize_username(username)
    except DomainError:
        username_key = ""
    user = await session.scalar(
        select(User)
        .where(User.username_key == username_key)
        .execution_options(populate_existing=True)
    )
    verifier = (
        user.password_hash if user is not None and user.enabled and user.role in ROLES else None
    )
    if (
        not await verify_password(verifier, password)
        or user is None
        or not user.enabled
        or user.role not in ROLES
    ):
        _audit(session, "auth.login", now_us, outcome="denied")
        await session.flush()
        raise DomainError("INVALID_CREDENTIALS", "Invalid username or password.", 401)
    # Password work leaves the event loop available. Recheck the account under a
    # row lock so a concurrent reset/disable cannot issue a fresh stale session.
    authenticated_version = user.auth_version
    authenticated_verifier = user.password_hash
    await _security_lock(session)
    user = await session.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        user is None
        or not user.enabled
        or user.role not in ROLES
        or user.auth_version != authenticated_version
        or user.password_hash != authenticated_verifier
    ):
        _audit(session, "auth.login", now_us, outcome="denied")
        await session.flush()
        raise DomainError("INVALID_CREDENTIALS", "Invalid username or password.", 401)
    token, csrf = issue_token(), issue_token()
    session.add(
        AuthSession(
            token_hash=token_hash(token),
            user_id=user.id,
            auth_version=user.auth_version,
            csrf_hash=token_hash(csrf),
            created_us=now_us,
            last_seen_us=now_us,
            expires_us=now_us + absolute_timeout_us,
        )
    )
    principal = _principal(user)
    _audit(session, "auth.login", now_us, principal=principal)
    await session.flush()
    return SessionCredentials(token, csrf, principal, now_us + absolute_timeout_us)


async def authenticate(
    session: AsyncSession,
    token: str,
    now_us: int,
    idle_timeout_us: int,
    *,
    renew_idle: bool = True,
    allow_password_change: bool = False,
) -> Principal:
    if idle_timeout_us <= 0:
        raise ValueError("Session idle timeout must be positive.")
    verifier = token_hash(token)
    if verifier is None:
        raise DomainError("AUTH_REQUIRED", "Authentication is required.", 401)
    await _security_lock(session)
    record = (
        await session.execute(
            select(AuthSession, User)
            .join(User, AuthSession.user_id == User.id)
            .where(AuthSession.token_hash == verifier)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).first()
    if record is None:
        raise DomainError("AUTH_REQUIRED", "Authentication is required.", 401)
    auth_session, user = record
    if (
        not user.enabled
        or user.role not in ROLES
        or user.auth_version != auth_session.auth_version
        or now_us < auth_session.created_us
        or now_us >= auth_session.expires_us
        or now_us - auth_session.last_seen_us >= idle_timeout_us
    ):
        raise DomainError("AUTH_REQUIRED", "Authentication is required.", 401)
    if renew_idle:
        auth_session.last_seen_us = max(auth_session.last_seen_us, now_us)
    if user.must_change_password and not allow_password_change:
        raise DomainError(
            "PASSWORD_CHANGE_REQUIRED", "Change your password before continuing.", 403
        )
    return _principal(user)


async def verify_csrf(session: AsyncSession, token: str, csrf: str) -> None:
    session_verifier, csrf_verifier = token_hash(token), token_hash(csrf)
    if session_verifier is None or csrf_verifier is None:
        raise DomainError("CSRF_FAILED", "Request verification failed.", 403)
    expected = await session.scalar(
        select(AuthSession.csrf_hash)
        .join(User, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == session_verifier,
            User.enabled.is_(True),
            User.auth_version == AuthSession.auth_version,
        )
    )
    if expected is None or not hmac.compare_digest(expected, csrf_verifier):
        raise DomainError("CSRF_FAILED", "Request verification failed.", 403)


async def logout(session: AsyncSession, principal: Principal, now_us: int) -> None:
    """Logout is deliberately account-wide across every browser workspace."""
    user = await _current_user(session, principal, allow_password_change=True)
    await _revoke_user(session, user, now_us)
    _audit(session, "auth.logout", now_us, principal=principal, target_id=principal.user_id)
    await session.flush()


def account_response(user: User) -> dict:
    """The explicit account allowlist excludes every password/session verifier."""
    return {
        "user_id": user.id,
        "username": user.username_key,
        "display_name": user.display_name,
        "role": user.role,
        "enabled": user.enabled,
        "auth_version": user.auth_version,
        "must_change_password": user.must_change_password,
    }


async def list_users(session: AsyncSession, actor: Principal) -> dict:
    current = await _current_user(session, actor)
    authorize(_principal(current), "users.manage")
    users = (
        await session.scalars(select(User).order_by(User.username_key, User.id).limit(1001))
    ).all()
    if len(users) > 1000:
        raise DomainError("LIMIT_REACHED", "Account list exceeds supported page size.", 413)
    return {"items": [account_response(user) for user in users]}


async def _account_target(
    session: AsyncSession, actor: Principal, user_id: str, expected_auth_version: int
) -> tuple[Principal, User]:
    current = await _current_user(session, actor)
    actor = _principal(current)
    authorize(actor, "users.manage")
    user = await session.get(User, user_id, with_for_update=True, populate_existing=True)
    if user is None:
        raise DomainError("NOT_FOUND", "Resource not found.", 404)
    if user.auth_version != expected_auth_version:
        raise DomainError("REVISION_CONFLICT", "Account has changed; reload before saving.", 409)
    return actor, user


async def update_user(
    session: AsyncSession,
    actor: Principal,
    user_id: str,
    expected_auth_version: int,
    *,
    enabled: bool | None = None,
    role: str | None = None,
    now_us: int | None = None,
) -> User:
    if enabled is None and role is None:
        raise DomainError("INVALID_ACCOUNT", "Choose an account change.", 422)
    if (enabled is not None and type(enabled) is not bool) or (
        role is not None and role not in ROLES
    ):
        raise DomainError("INVALID_ACCOUNT", "Invalid account details.", 422)
    actor, user = await _account_target(session, actor, user_id, expected_auth_version)
    next_enabled = user.enabled if enabled is None else enabled
    next_role = user.role if role is None else role
    if (
        user.enabled
        and user.role == "administrator"
        and (not next_enabled or next_role != "administrator")
    ):
        another_admin = await session.scalar(
            select(User.id)
            .where(User.enabled.is_(True), User.role == "administrator", User.id != user.id)
            .limit(1)
        )
        if another_admin is None:
            raise DomainError(
                "LAST_ADMIN_REQUIRED", "Keep at least one enabled Administrator.", 409
            )
    if next_enabled == user.enabled and next_role == user.role:
        return user
    user.enabled, user.role = next_enabled, next_role
    now = time.time_ns() // 1000 if now_us is None else now_us
    await _revoke_user(session, user, now)
    _audit(session, "auth.account.update", now, principal=actor, target_id=user.id)
    await session.flush()
    return user


async def reset_password(
    session: AsyncSession,
    actor: Principal,
    user_id: str,
    expected_auth_version: int,
    password: str,
    *,
    must_change_password: bool = True,
    now_us: int | None = None,
) -> User:
    authorize(actor, "users.manage")
    if type(must_change_password) is not bool:
        raise DomainError("INVALID_ACCOUNT", "Invalid account details.", 422)
    verifier = await hash_password(password)
    actor, user = await _account_target(session, actor, user_id, expected_auth_version)
    user.password_hash, user.must_change_password = verifier, must_change_password
    now = time.time_ns() // 1000 if now_us is None else now_us
    await _revoke_user(session, user, now)
    _audit(session, "auth.password.reset", now, principal=actor, target_id=user.id)
    await session.flush()
    return user


async def revoke_sessions(
    session: AsyncSession,
    actor: Principal,
    user_id: str,
    expected_auth_version: int,
    *,
    now_us: int | None = None,
) -> User:
    actor, user = await _account_target(session, actor, user_id, expected_auth_version)
    now = time.time_ns() // 1000 if now_us is None else now_us
    await _revoke_user(session, user, now)
    _audit(session, "auth.sessions.revoke", now, principal=actor, target_id=user.id)
    await session.flush()
    return user


async def change_password(
    session: AsyncSession,
    actor: Principal,
    current_password: str,
    new_password: str,
    *,
    now_us: int | None = None,
) -> None:
    validate_new_password(new_password)
    user = await _current_user(session, actor, allow_password_change=True)
    authorize(_principal(user), "self.password.change", owner_user_id=user.id)
    if not await verify_password(user.password_hash, current_password):
        raise DomainError("INVALID_CURRENT_PASSWORD", "Current password is incorrect.", 403)
    user.password_hash = await hash_password(new_password)
    user.must_change_password = False
    now = time.time_ns() // 1000 if now_us is None else now_us
    await _revoke_user(session, user, now)
    _audit(session, "auth.password.change", now, principal=actor, target_id=user.id)
    await session.flush()
