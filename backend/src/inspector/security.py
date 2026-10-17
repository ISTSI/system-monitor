"""Small, deny-by-default security primitives with no request-owned authority."""

from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import weakref
from collections.abc import Callable
from typing import TypeVar

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type

from inspector.domain import Principal
from inspector.errors import DomainError

ROLES = frozenset({"administrator", "inspector"})
MAX_PASSWORD_BYTES = 1024
_OPAQUE_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z", re.ASCII)
_Result = TypeVar("_Result")


def normalize_username(username: str) -> str:
    """Keep username comparison independent of MariaDB's collation."""
    if not isinstance(username, str):
        raise DomainError("INVALID_ACCOUNT", "Invalid account details.", 422)
    key = username.strip().casefold()
    if not key or len(key) > 128 or any(ord(char) < 32 or ord(char) == 127 for char in key):
        raise DomainError("INVALID_ACCOUNT", "Invalid account details.", 422)
    return key


def validate_new_password(password: str) -> None:
    if not isinstance(password, str) or not 12 <= len(password) <= MAX_PASSWORD_BYTES:
        raise DomainError(
            "INVALID_PASSWORD",
            "Password must contain at least 12 characters and at most 1024 UTF-8 bytes.",
            422,
        )
    try:
        acceptable = len(password.encode("utf-8")) <= MAX_PASSWORD_BYTES
    except UnicodeEncodeError:
        acceptable = False
    if not acceptable:
        raise DomainError(
            "INVALID_PASSWORD",
            "Password must contain at least 12 characters and at most 1024 UTF-8 bytes.",
            422,
        )


def valid_login_password(password: str) -> bool:
    if not isinstance(password, str) or not password or len(password) > MAX_PASSWORD_BYTES:
        return False
    try:
        return len(password.encode("utf-8")) <= MAX_PASSWORD_BYTES
    except UnicodeEncodeError:
        return False


class Passwords:
    """Argon2id work stays off the loop, with two concurrent hashes per loop.

    The application has one ASGI event loop. Weak loop keys also allow isolated
    unit tests/CLI invocations without reusing a semaphore from a closed loop.
    """

    def __init__(self, workers: int = 2) -> None:
        if not 1 <= workers <= 2:
            raise ValueError("Password worker count must be one or two.")
        self._workers = workers
        self._limits: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
            weakref.WeakKeyDictionary()
        )
        self._hasher = PasswordHasher(
            time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, salt_len=16, type=Type.ID
        )
        self._dummy_hash: str | None = None

    async def _run(self, operation: Callable[[], _Result]) -> _Result:
        loop = asyncio.get_running_loop()
        limit = self._limits.setdefault(loop, asyncio.Semaphore(self._workers))
        async with limit:
            # Cancellation must not release the semaphore while native Argon2 is
            # still running, which would bypass the concurrency/memory bound.
            task = asyncio.create_task(asyncio.to_thread(operation))
            cancelled = False
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    cancelled = True
            if cancelled:
                # Retrieve a worker exception before preserving cancellation.
                if not task.cancelled():
                    task.exception()
                raise asyncio.CancelledError
            return task.result()

    async def hash(self, password: str) -> str:
        validate_new_password(password)
        return await self._run(lambda: self._hasher.hash(password))

    async def verify(self, password_hash: str | None, password: str) -> bool:
        if not valid_login_password(password):
            return False

        def verify_sync() -> bool:
            # A dummy verifier gives nonexistent/disabled accounts the same
            # expensive password operation without keeping a fake account.
            if self._dummy_hash is None:
                self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))
            verifier = password_hash if password_hash is not None else self._dummy_hash
            try:
                matched = self._hasher.verify(verifier, password)
            except (InvalidHashError, VerificationError):
                return False
            return matched and password_hash is not None

        return await self._run(verify_sync)


passwords = Passwords()


async def hash_password(password: str) -> str:
    return await passwords.hash(password)


async def verify_password(password_hash: str | None, password: str) -> bool:
    return await passwords.verify(password_hash, password)


def issue_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str | None:
    if not isinstance(token, str) or _OPAQUE_TOKEN.fullmatch(token) is None:
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def require_admin(principal: Principal) -> None:
    if principal.role != "administrator":
        raise DomainError("FORBIDDEN", "This action requires an Administrator.", 403)


_READ_ACTIONS = frozenset(
    {"system.list", "topology.read", "topology.search", "workspace.create", "collection.create"}
)
_ADMIN_ACTIONS = frozenset(
    {
        "system.create",
        "system.metadata.write",
        "system.archive",
        "system.restore",
        "users.manage",
        "topology.write",
        "project_config.read",
        "project_config.import",
        "project_config.export",
    }
)
_OWN_ACTIONS = frozenset(
    {
        "workspace.read",
        "workspace.detach",
        "preference.read",
        "preference.write",
        "self.password.change",
        "collection.read",
        "collection.cancel",
        "investigation.read",
        "download.read",
    }
)


def authorize(principal: Principal, action: str, *, owner_user_id: str | None = None) -> None:
    """Only implemented actions are permitted; scope checks remain mandatory."""
    if principal.must_change_password and action != "self.password.change":
        raise DomainError(
            "PASSWORD_CHANGE_REQUIRED", "Change your password before continuing.", 403
        )
    if principal.role not in ROLES:
        raise DomainError("FORBIDDEN", "This action is not permitted.", 403)
    if action in _ADMIN_ACTIONS:
        require_admin(principal)
    elif action in _OWN_ACTIONS:
        if action == "collection.cancel" and principal.role == "administrator":
            return
        if owner_user_id is None or owner_user_id != principal.user_id:
            raise DomainError("NOT_FOUND", "Resource not found.", 404)
    elif action not in _READ_ACTIONS:
        raise DomainError("FORBIDDEN", "This action is not permitted.", 403)
