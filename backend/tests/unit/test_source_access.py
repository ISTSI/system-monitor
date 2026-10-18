"""Root identity and cancellation without a network or substitute database."""

import asyncio
import warnings
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects.mysql import asyncmy
from sqlalchemy.exc import SAWarning, SQLAlchemyError
from sqlalchemy.sql import FROM_LINTING

from inspector.domain import Principal
from inspector.errors import DomainError
from inspector.persistence.models import (
    ApplicationSetting,
    AuthSession,
    Project,
    ProjectCredentialBinding,
    SecurityState,
    SourceAccessApproval,
    SSHCredential,
    SSHHostTrust,
    TopologyState,
    User,
)
from inspector.source_access import (
    SourceAccess,
    SourceApprovalInput,
    SourceSnapshot,
    SourceTestInput,
    approval_matches,
    configured_roots,
    roots_digest,
)
from inspector.ssh_access import NetworkSnapshot, SSHAccess, route_digest
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


async def test_fresh_batch_matches_individual_direct_and_jump_snapshots_without_repeated_reads(
    monkeypatch,
):
    actor = Principal("owner", "inspector", 1)
    profiles = [
        dict(
            id=identifier,
            host=f"192.0.2.{index + 1}",
            port=22,
            username="logs",
            credential_ref=identifier,
            jump_connection_id="jump" if identifier == "target" else None,
            allowed_log_roots=["/logs"],
        )
        for index, identifier in enumerate(("direct", "target", "jump"))
    ]
    project = Project(id="project-a", revision=2, archived=False)
    topology = TopologyState(project_id=project.id, config={"connections": profiles})
    user = User(
        id=actor.user_id,
        role="inspector",
        auth_version=1,
        enabled=True,
        must_change_password=False,
    )
    login = AuthSession(
        user_id=actor.user_id,
        auth_version=1,
        created_us=100,
        last_seen_us=500,
        expires_us=1000,
    )
    settings_row = ApplicationSetting(id=1, additional_security_measures=False)
    rows: dict[type, dict] = {
        TopologyState: {project.id: topology},
        SourceAccessApproval: {},
        ProjectCredentialBinding: {},
        SSHCredential: {},
        SSHHostTrust: {},
    }
    for profile in profiles:
        identifier = profile["id"]
        route = [profile, profiles[-1]] if identifier == "target" else [profile]
        rows[SSHHostTrust][(project.id, identifier)] = SSHHostTrust(
            project_id=project.id,
            connection_id=identifier,
            revision=1,
            approved=True,
            route_digest=route_digest(route),
            public_key=f"synthetic-{identifier}",
        )
        rows[ProjectCredentialBinding][(project.id, identifier)] = ProjectCredentialBinding(
            project_id=project.id, alias=identifier, credential_id=f"credential-{identifier}"
        )
        rows[SSHCredential][f"credential-{identifier}"] = SSHCredential(
            id=f"credential-{identifier}", revision=1, expires_us=None
        )

    calls = dict(actor=0, settings=0, project=0, get=0, batch=0)

    async def current(*args, **kwargs):
        assert kwargs["lock"] is False
        calls["actor"] += 1
        return actor

    async def settings(*args):
        calls["settings"] += 1
        return SimpleNamespace(additional_security_measures=False)

    async def scoped(*args, **kwargs):
        assert args[1].project_id == project.id and not kwargs["lock"]
        calls["project"] += 1
        return project

    class Session:
        async def get(self, model, key, **kwargs):
            calls["get"] += 1
            return rows[model].get(key)

        async def execute(self, query):
            calls["batch"] += 1
            model = query.column_descriptions[0]["entity"]
            parameters = query.compile().params
            assert project.id in parameters.values()
            with warnings.catch_warnings():
                warnings.simplefilter("error", SAWarning)
                query.compile(dialect=asyncmy.dialect(), linting=FROM_LINTING)
            if model is SecurityState:
                return SimpleNamespace(
                    first=lambda: (
                        SecurityState(id=1),
                        user,
                        login,
                        settings_row,
                        project,
                        topology,
                    )
                )
            if model is SSHHostTrust:
                values = [
                    (trust, rows[SourceAccessApproval].get(key))
                    for key, trust in rows[SSHHostTrust].items()
                ]
            else:
                values = [
                    (binding, rows[SSHCredential].get(binding.credential_id))
                    for binding in rows[ProjectCredentialBinding].values()
                ]
            return SimpleNamespace(all=lambda: values)

    ssh = object.__new__(SSHAccess)
    ssh.sessions = None
    ssh.config = SimpleNamespace(idle_timeout_us=200)
    ssh.vault = SimpleNamespace(decrypt=lambda row: f"synthetic-password-{row.id}")
    ssh._actor = current
    manager = SourceAccess(ssh)
    monkeypatch.setattr("inspector.source_access.foundation.settings_value", settings)
    monkeypatch.setattr("inspector.source_access.services.project_in_context", scoped)
    monkeypatch.setattr("inspector.source_access.services.utc_now_us", lambda: 600)
    session = Session()
    batch = await manager.prepare_many_in_transaction(
        session, actor, project.id, ["direct", "target"], 2, "login-a"
    )
    assert calls == dict(actor=0, settings=0, project=0, get=0, batch=3)
    for identifier in ("direct", "target"):
        individual = await manager._prepare(
            session,
            actor,
            project.id,
            identifier,
            2,
            "login-a",
            require_approval=True,
            action="collection.create",
            lock=False,
        )
        assert batch[identifier] == individual
    assert batch["direct"].jump is None
    assert batch["target"].jump.host == profiles[-1]["host"]
    rows[SSHCredential]["credential-jump"].expires_us = 1
    with pytest.raises(DomainError) as denied:
        await manager.prepare_many_in_transaction(
            session, actor, project.id, ["direct", "target"], 2, "login-a"
        )
    assert denied.value.code == "SSH_CREDENTIAL_EXPIRED"


@pytest.mark.parametrize("identifiers", [[], ["same", "same"], [str(i) for i in range(201)]])
async def test_fresh_source_batch_rejects_invalid_count_before_database_work(identifiers):
    manager = SourceAccess(SimpleNamespace(sessions=None))
    with pytest.raises(DomainError) as denied:
        await manager.prepare_many_in_transaction(
            None, Principal("owner", "inspector", 1), "project-a", identifiers, 2, "login-a"
        )
    assert denied.value.code == "INVALID_REQUEST"


@pytest.mark.parametrize(
    "change,code",
    [
        ("security", "NOT_READY"),
        ("user", "AUTH_REQUIRED"),
        ("disabled", "AUTH_REQUIRED"),
        ("role", "AUTH_REQUIRED"),
        ("version", "AUTH_REQUIRED"),
        ("password", "PASSWORD_CHANGE_REQUIRED"),
        ("login", "AUTH_REQUIRED"),
        ("login_owner", "AUTH_REQUIRED"),
        ("login_version", "AUTH_REQUIRED"),
        ("expiry", "AUTH_REQUIRED"),
        ("idle", "AUTH_REQUIRED"),
        ("settings", "NOT_READY"),
        ("project", "NOT_FOUND"),
        ("state", "NOT_FOUND"),
        ("revision", "REVISION_CONFLICT"),
    ],
)
async def test_common_source_snapshot_keeps_actor_login_policy_and_scope_error_order(
    monkeypatch, change, code
):
    actor = Principal("owner", "inspector", 1)
    ssh = object.__new__(SSHAccess)
    ssh.sessions = None
    ssh.config = SimpleNamespace(idle_timeout_us=200)
    manager = SourceAccess(ssh)
    user = User(
        id=actor.user_id,
        auth_version=1,
        role="inspector",
        enabled=True,
        must_change_password=False,
    )
    login = AuthSession(
        user_id="owner", auth_version=1, created_us=100, last_seen_us=500, expires_us=1000
    )
    settings = ApplicationSetting(id=1, additional_security_measures=False)
    project = Project(id="project-a", revision=2, archived=False)
    state = TopologyState(project_id=project.id, config={"connections": [{"id": "target"}]})
    if change == "user":
        user = None
    elif change == "disabled":
        user.enabled = False
    elif change == "role":
        user.role = "unknown"
    elif change == "version":
        user.auth_version += 1
    elif change == "password":
        user.must_change_password = True
        login = settings = project = None  # User policy still fails first.
    elif change == "login":
        login = None
    elif change == "login_owner":
        login.user_id = "another-owner"
    elif change == "login_version":
        login.auth_version += 1
    elif change == "expiry":
        login.expires_us = 600
    elif change == "idle":
        login.last_seen_us = 400
    elif change == "settings":
        settings = project = None  # Missing settings precedes missing project.
    elif change == "project":
        project = None
    elif change == "state":
        state = None
    elif change == "revision":
        project.revision += 1
    statements = []

    class Session:
        async def execute(self, query):
            assert not statements  # Validation fails after exactly one common read.
            with warnings.catch_warnings():
                warnings.simplefilter("error", SAWarning)
                query.compile(dialect=asyncmy.dialect(), linting=FROM_LINTING)
            assert all(
                value in query.compile().params.values()
                for value in ("project-a", "owner", "login-a")
            )
            statements.append(query)
            record = (
                None
                if change == "security"
                else (SecurityState(id=1), user, login, settings, project, state)
            )
            return SimpleNamespace(first=lambda: record)

    monkeypatch.setattr("inspector.source_access.services.utc_now_us", lambda: 600)
    with pytest.raises(DomainError) as denied:
        await manager.prepare_many_in_transaction(
            Session(), actor, "project-a", ["target"], 2, "login-a"
        )
    assert denied.value.code == code and len(statements) == 1


def test_ssh_login_guard_respects_remembered_inactivity_and_absolute_expiry(monkeypatch):
    actor = Principal("owner", "inspector", 1)
    ssh = object.__new__(SSHAccess)
    ssh.config = SimpleNamespace(idle_timeout_us=200)
    login = AuthSession(
        user_id="owner",
        auth_version=1,
        created_us=100,
        last_seen_us=100,
        expires_us=1000,
        remember_me=True,
    )
    monkeypatch.setattr("inspector.ssh_access.services.utc_now_us", lambda: 999)
    assert ssh._validated_login(actor, login) == actor
    login.remember_me = False
    with pytest.raises(DomainError) as idle:
        ssh._validated_login(actor, login)
    assert idle.value.code == "AUTH_REQUIRED"
    login.remember_me = True
    monkeypatch.setattr("inspector.ssh_access.services.utc_now_us", lambda: 1000)
    with pytest.raises(DomainError) as absolute:
        ssh._validated_login(actor, login)
    assert absolute.value.code == "AUTH_REQUIRED"
