"""Root identity and cancellation without a network or substitute database."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from inspector.domain import Principal
from inspector.errors import DomainError
from inspector.persistence.models import SourceAccessApproval
from inspector.source_access import (
    SourceAccess,
    SourceApprovalInput,
    SourceSnapshot,
    SourceTestInput,
    approval_matches,
    configured_roots,
    roots_digest,
)
from inspector.ssh_access import NetworkSnapshot
from inspector.ssh_transport import Endpoint


def snapshot():
    return SourceSnapshot(
        project_id="project-a",
        connection_id="target",
        owner_user_id="owner",
        config_revision=2,
        approval_revision=1,
        roots=("/logs",),
        signature="context-a",
        auth_session_hash="login-a",
        network=NetworkSnapshot(Endpoint("192.0.2.20", 22, "logs"), None, "network-a", "route-a"),
    )


def test_roots_are_order_independent_but_do_not_inherit_other_paths():
    assert roots_digest(("/logs/a", "/logs/b")) == roots_digest(("/logs/b", "/logs/a"))
    assert roots_digest(("/logs/a",)) != roots_digest(("/logs",))


@pytest.mark.parametrize(
    "roots", [[], ["logs"], ["//logs"], ["/logs/../etc"], ["/logs\\etc"], ["/logs\x00"]]
)
def test_invalid_roots_cannot_be_approved(roots):
    with pytest.raises(DomainError) as denied:
        configured_roots([{"allowed_log_roots": roots}])
    assert denied.value.code == "SOURCE_NOT_APPROVED"


@pytest.mark.parametrize("change", ["expiry", "revision", "roots", "route", "network", "revoked"])
def test_approval_requires_every_current_context_component(change):
    before = snapshot()
    row = SourceAccessApproval(
        approved=True,
        revision=1,
        config_revision=2,
        route_digest="route-a",
        roots_digest=roots_digest(("/logs",)),
        network_signature="network-a",
        expires_us=200,
    )
    assert approval_matches(row, 2, before.network, before.roots, 100)
    if change == "expiry":
        row.expires_us = 100
    elif change == "revision":
        row.config_revision = 3
    elif change == "roots":
        row.roots_digest = roots_digest(("/other",))
    elif change == "route":
        row.route_digest = "route-b"
    elif change == "network":
        row.network_signature = "network-b"
    else:
        row.approved = False
    assert not approval_matches(row, 2, before.network, before.roots, 100)


def test_only_configured_path_selectors_are_accepted_from_browser():
    with pytest.raises(ValidationError):
        SourceTestInput(expected_config_revision=2, host="192.0.2.20", path="/etc/passwd")
    with pytest.raises(ValidationError):
        SourceApprovalInput(
            expected_config_revision=2,
            expected_approval_revision=0,
            verified=True,
            expires_seconds=0,
        )


@pytest.mark.parametrize(
    "failure", ["revoked", "expired", "database", "database_timeout", "supervisor", "changed"]
)
async def test_guard_cancels_blocked_transport_after_fresh_access_failure(monkeypatch, failure):
    before = snapshot()
    actor = Principal("owner", "inspector", 1)
    invalidated, started, stopped = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def healthy():
        return not (invalidated.is_set() and failure == "supervisor")

    manager = SourceAccess(
        SimpleNamespace(sessions=None, supervisor=SimpleNamespace(healthy=healthy))
    )

    async def prepare(*args, **kwargs):
        if invalidated.is_set():
            if failure == "revoked":
                raise DomainError("SOURCE_NOT_APPROVED", "Revoked.", 409)
            if failure == "expired":
                raise DomainError("SOURCE_APPROVAL_EXPIRED", "Expired.", 410)
            if failure == "database":
                raise SQLAlchemyError()
            if failure == "database_timeout":
                await asyncio.Event().wait()
            if failure == "changed":
                return replace(before, signature="context-b")
        return before

    async def blocked():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(manager, "prepare", prepare)
    task = asyncio.create_task(
        manager.watched(actor, "project-a", "target", 2, "login-a", before, blocked)
    )
    await asyncio.wait_for(started.wait(), 1)
    invalidated.set()
    with pytest.raises(DomainError) as denied:
        await asyncio.wait_for(task, 2)
    assert stopped.is_set()
    assert (
        denied.value.code
        == {
            "revoked": "SOURCE_NOT_APPROVED",
            "expired": "SOURCE_APPROVAL_EXPIRED",
            "database": "DATABASE_UNAVAILABLE",
            "database_timeout": "DATABASE_UNAVAILABLE",
            "supervisor": "DATABASE_UNAVAILABLE",
            "changed": "REVISION_CONFLICT",
        }[failure]
    )


@pytest.mark.parametrize(
    "project,owner,login",
    [
        ("project-b", "owner", "login-a"),
        ("project-a", "other", "login-a"),
        ("project-a", "owner", "login-b"),
    ],
)
async def test_snapshot_cannot_be_reused_in_another_project_owner_or_login(project, owner, login):
    manager = SourceAccess(SimpleNamespace(sessions=None))

    async def forbidden():
        pytest.fail("A mismatched snapshot started network work")

    with pytest.raises(DomainError) as denied:
        await manager.watched(
            Principal(owner, "inspector", 1), project, "target", 2, login, snapshot(), forbidden
        )
    assert denied.value.status == 404


async def test_completed_network_result_is_rejected_when_final_access_check_changes(monkeypatch):
    before = snapshot()
    changed = False

    async def healthy():
        return True

    manager = SourceAccess(
        SimpleNamespace(sessions=None, supervisor=SimpleNamespace(healthy=healthy))
    )

    async def prepare(*args, **kwargs):
        return replace(before, signature="changed") if changed else before

    async def operation():
        nonlocal changed
        changed = True
        return "must not be accepted"

    monkeypatch.setattr(manager, "prepare", prepare)
    with pytest.raises(DomainError) as denied:
        await manager.watched(
            Principal("owner", "inspector", 1),
            "project-a",
            "target",
            2,
            "login-a",
            before,
            operation,
        )
    assert denied.value.code == "REVISION_CONFLICT"


async def test_collection_action_cannot_bypass_explicit_approval():
    actor = Principal("owner", "inspector", 1)

    async def current(*args, **kwargs):
        return actor

    manager = SourceAccess(SimpleNamespace(sessions=None, _actor=current))
    with pytest.raises(DomainError) as denied:
        await manager._prepare(
            None,
            actor,
            "project-a",
            "target",
            2,
            "login-a",
            require_approval=False,
            action="collection.create",
        )
    assert denied.value.status == 403
