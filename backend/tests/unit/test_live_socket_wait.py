"""Output wakeups retain one pending input and fresh socket authorization."""

import asyncio
import time
import warnings
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects.mysql import asyncmy
from sqlalchemy.exc import SAWarning
from sqlalchemy.sql import FROM_LINTING

from inspector.domain import Principal
from inspector.errors import DomainError
from inspector.live import LEASE_US, LiveControlInput, LiveManager, _wait_live_input
from inspector.persistence.models import AuthSession, LiveSession, SecurityState, User, Workspace
from inspector.security import token_hash


async def test_output_wakeups_preserve_pending_ack_without_waiting_for_watchdog():
    release, changed = asyncio.Event(), asyncio.Event()
    reads = 0

    async def receive():
        nonlocal reads
        reads += 1
        await release.wait()
        return "ack"

    incoming = asyncio.create_task(receive())
    try:
        for _ in range(3):
            changed.set()
            began = time.monotonic()
            assert not await _wait_live_input(incoming, changed)
            assert time.monotonic() - began < 0.1
            assert not incoming.done() and reads == 1
            changed.clear()
        release.set()
        assert await _wait_live_input(incoming, changed)
        assert incoming.result() == "ack" and reads == 1
    finally:
        incoming.cancel()
        await asyncio.gather(incoming, return_exceptions=True)


async def test_watchdog_and_cancelled_output_wait_do_not_cancel_the_input_read():
    release = asyncio.Event()

    async def receive():
        await release.wait()
        return "ack-after-watchdog"

    incoming = asyncio.create_task(receive())
    try:
        began = time.monotonic()
        assert not await _wait_live_input(incoming, asyncio.Event())
        assert 0.24 <= time.monotonic() - began < 0.4
        waiting = asyncio.create_task(_wait_live_input(incoming, asyncio.Event()))
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        assert not incoming.done()
        release.set()
        assert await incoming == "ack-after-watchdog"
    finally:
        incoming.cancel()
        await asyncio.gather(incoming, return_exceptions=True)


async def test_each_socket_check_authenticates_freshly_in_its_scoped_row_transaction(monkeypatch):
    manager = object.__new__(LiveManager)
    manager.config = SimpleNamespace(idle_timeout_us=200)
    actor = Principal("owner", "inspector", 1)
    user = User(
        id="owner",
        role="inspector",
        auth_version=1,
        enabled=True,
        must_change_password=False,
        display_name="",
        username_key="",
    )
    login = AuthSession(
        user_id="owner", auth_version=1, created_us=100, last_seen_us=500, expires_us=1000
    )
    row = LiveSession(owner_user_id="owner", workspace_id="page", lease_revision=2)
    row.detached_until_us = None
    workspace = Workspace(owner_user_id="owner", state="active", expires_us=1000)
    checked = []
    cookie = "a" * 43

    class Session:
        async def execute(self, query):
            parameters = query.compile().params
            assert all(
                value in parameters.values() for value in ("project", "monitor", token_hash(cookie))
            )
            assert query._for_update_arg is None
            with warnings.catch_warnings():
                warnings.simplefilter("error", SAWarning)
                query.compile(dialect=asyncmy.dialect(), linting=FROM_LINTING)
            checked.append(query)
            return SimpleNamespace(first=lambda: (SecurityState(id=1), login, user, row, workspace))

    session = Session()

    async def duplicate_account_read(*args, **kwargs):
        pytest.fail("The freshly authenticated socket repeated its account SELECTs")

    manager._principal = duplicate_account_read
    monkeypatch.setattr("inspector.live.services.current_actor", duplicate_account_read)
    monkeypatch.setattr("inspector.live.services.utc_now_us", lambda: 600)
    control = LiveControlInput(workspace_id="page", lease_revision=2)
    for _ in range(2):
        assert await manager._socket_row(session, cookie, "project", "monitor", control) == (
            actor,
            row,
        )
    assert len(checked) == 2  # Exactly one fresh joined SELECT for each protected check.
    await manager._socket_row(session, cookie, "project", "monitor", control, renew_workspace=True)
    assert workspace.expires_us == 600 + LEASE_US and len(checked) == 3
    user.auth_version += 1
    with pytest.raises(DomainError) as revoked:
        await manager._socket_row(session, cookie, "project", "monitor", control)
    assert revoked.value.code == "AUTH_REQUIRED" and len(checked) == 4


@pytest.mark.parametrize(
    "change,code",
    [
        ("security", "SECURITY_NOT_READY"),
        ("login", "AUTH_REQUIRED"),
        ("row", "NOT_FOUND"),
        ("owner", "NOT_FOUND"),
        ("workspace_id", "NOT_FOUND"),
        ("lease", "REVISION_CONFLICT"),
        ("workspace", "NOT_FOUND"),
        ("workspace_owner", "NOT_FOUND"),
        ("workspace_expiry", "WORKSPACE_EXPIRED"),
        ("workspace_state", "WORKSPACE_IN_USE"),
        ("detached", "WORKSPACE_IN_USE"),
    ],
)
async def test_joined_socket_snapshot_preserves_scope_lease_and_missing_record_errors(
    monkeypatch, change, code
):
    manager = object.__new__(LiveManager)
    manager.config = SimpleNamespace(idle_timeout_us=200)
    login = AuthSession(
        user_id="owner", auth_version=1, created_us=100, last_seen_us=500, expires_us=1000
    )
    user = User(
        id="owner", role="inspector", auth_version=1, enabled=True, must_change_password=False
    )
    row = LiveSession(owner_user_id="owner", workspace_id="page", lease_revision=2)
    row.detached_until_us = None
    workspace = Workspace(owner_user_id="owner", state="active", expires_us=1000)
    if change == "login":
        login = None
    elif change == "row":
        row = None
    elif change == "owner":
        row.owner_user_id = "another-owner"
    elif change == "workspace_id":
        row.workspace_id = "another-page"
    elif change == "lease":
        row.lease_revision += 1
    elif change == "workspace":
        workspace = None
    elif change == "workspace_owner":
        workspace.owner_user_id = "another-owner"
    elif change == "workspace_expiry":
        workspace.expires_us = 600
    elif change == "workspace_state":
        workspace.state = "detached"
    elif change == "detached":
        row.detached_until_us = 700

    class Session:
        async def execute(self, query):
            record = (
                None if change == "security" else (SecurityState(id=1), login, user, row, workspace)
            )
            return SimpleNamespace(first=lambda: record)

    monkeypatch.setattr("inspector.live.services.utc_now_us", lambda: 600)
    with pytest.raises(DomainError) as denied:
        await manager._socket_row(
            Session(),
            "a" * 43,
            "project",
            "monitor",
            LiveControlInput(workspace_id="page", lease_revision=2),
        )
    assert denied.value.code == code
