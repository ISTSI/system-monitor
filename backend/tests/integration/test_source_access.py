"""Explicit local source approvals and cancellation against actual MariaDB."""

import asyncio
import copy
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from test_ssh_access import (
    OBSERVED,
    approve,
    base,
    enable_vault,
    inspect,
    isolated_admin,
    save,
    seed,
)

from inspector import services, ssh_files, ssh_transport
from inspector.errors import DomainError
from inspector.persistence.models import (
    AuthSession,
    Project,
    ProjectCredentialBinding,
    SourceAccessApproval,
    SSHCredential,
    SSHHostTrust,
    TopologyState,
)
from inspector.security import token_hash

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


def source_base(project):
    return base(project) + "/source-access"


def approval_body(**changes):
    return {
        "expected_config_revision": 2,
        "expected_approval_revision": 0,
        "verified": True,
        **changes,
    }


async def configured(foundation, tmp_path, monkeypatch, client):
    enable_vault(foundation, tmp_path)

    async def observed(*args, **kwargs):
        return OBSERVED

    monkeypatch.setattr(ssh_transport, "inspect_key", observed)
    config = await seed(client, foundation.project_a)
    assert (await save(client, foundation.project_a)).status_code == 200
    observed_key = await inspect(client, foundation.project_a)
    assert observed_key.status_code == 200, observed_key.text
    assert (
        await approve(client, foundation.project_a, observed_key.json()["inspection_token"])
    ).status_code == 200
    return config


async def test_import_and_host_key_approval_never_implicitly_approve_log_roots(
    foundation, tmp_path, monkeypatch
):
    manager = foundation.app.state.source_access
    async with foundation.client(foundation.database.administrator) as admin:
        await configured(foundation, tmp_path, monkeypatch, admin)
        status = await admin.get(source_base(foundation.project_a))
        assert status.status_code == 200, status.text
        assert status.json()["approval"] == {"approved": False, "revision": 0, "expires_us": None}
        assert status.json()["roots"] == ["/var/log/inspector-demo"]
        assert status.json()["process_ids"] == ["p-ingest-a"]
        invalid = await admin.post(
            source_base(foundation.project_a) + "/approve", json=approval_body(verified=False)
        )
        assert invalid.status_code == 422
        async with foundation.client(foundation.alice) as inspector:
            login = token_hash(inspector.cookies.get("__Host-si-session"))
            with pytest.raises(DomainError) as denied:
                await manager.prepare(
                    foundation.alice.principal, foundation.project_a, "c-ingest", 2, login
                )
            assert denied.value.code == "SOURCE_NOT_APPROVED"
            approved = await admin.post(
                source_base(foundation.project_a) + "/approve", json=approval_body()
            )
            assert approved.status_code == 200, approved.text
            assert approved.json()["approval"]["approved"]
            snapshot = await manager.prepare(
                foundation.alice.principal, foundation.project_a, "c-ingest", 2, login
            )
            assert snapshot.project_id == foundation.project_a
            assert snapshot.owner_user_id == foundation.alice.principal.user_id
            assert snapshot.roots == ("/var/log/inspector-demo",)
        exported = await admin.get(
            f"/api/v1/projects/{foundation.project_a}/config/export?format=json"
        )
        assert exported.status_code == 200
        assert (
            "network_signature" not in exported.text and "approved_by_user_id" not in exported.text
        )
        replay = await admin.post(
            source_base(foundation.project_a) + "/approve", json=approval_body()
        )
        assert replay.status_code == 409


async def test_approval_is_project_scoped_and_all_setup_actions_reject_inspector(
    foundation, tmp_path, monkeypatch
):
    async with foundation.client(foundation.database.administrator) as admin:
        await configured(foundation, tmp_path, monkeypatch, admin)
        await seed(admin, foundation.project_b)
        approved = await admin.post(
            source_base(foundation.project_a) + "/approve", json=approval_body()
        )
        assert approved.status_code == 200
        other = await admin.get(source_base(foundation.project_b))
        assert other.status_code == 200
        assert other.json()["approval"]["revision"] == 0
        assert not other.json()["approval"]["approved"]
        missing = await admin.get(
            f"/api/v1/projects/{foundation.project_b}/connections/unconfigured/source-access"
        )
        assert missing.status_code == 404
        arbitrary = await admin.post(
            source_base(foundation.project_a) + "/test",
            json={"expected_config_revision": 2, "path": "/etc/passwd"},
        )
        assert arbitrary.status_code == 422
    async with foundation.client(foundation.alice) as inspector:
        assert (await inspector.get(source_base(foundation.project_a))).status_code == 403
        for suffix, payload in [
            ("/approve", approval_body()),
            ("/revoke", {"expected_config_revision": 2, "expected_approval_revision": 1}),
            ("/test", {"expected_config_revision": 2}),
        ]:
            assert (
                await inspector.post(source_base(foundation.project_a) + suffix, json=payload)
            ).status_code == 403


@pytest.mark.parametrize("change", ["config", "password", "trust", "expiry", "credential_expiry"])
async def test_changed_or_expired_context_cannot_dispatch_collection(
    foundation, tmp_path, monkeypatch, change
):
    manager = foundation.app.state.source_access
    async with foundation.client(foundation.database.administrator) as admin:
        document = await configured(foundation, tmp_path, monkeypatch, admin)
        assert (
            await admin.post(source_base(foundation.project_a) + "/approve", json=approval_body())
        ).status_code == 200
        if change == "config":
            document = copy.deepcopy(document)
            document["servers"][0]["description"] = (
                "Changed configuration requires new explicit approval."
            )
            changed = await admin.put(
                f"/api/v1/projects/{foundation.project_a}/topology",
                json={"expected_revision": 2, "config": document},
            )
            assert changed.status_code == 200, changed.text
        elif change == "password":
            assert (
                await save(admin, foundation.project_a, "synthetic-replacement-password", 1)
            ).status_code == 200
        elif change == "trust":
            assert (
                await admin.post(
                    base(foundation.project_a) + "/revoke",
                    json={"expected_config_revision": 2, "expected_trust_revision": 1},
                )
            ).status_code == 200
        elif change == "expiry":
            async with foundation.database.sessions.begin() as session:
                row = await session.get(SourceAccessApproval, (foundation.project_a, "c-ingest"))
                row.expires_us = services.utc_now_us() - 1
        else:
            async with foundation.database.sessions.begin() as session:
                binding = await session.get(
                    ProjectCredentialBinding, (foundation.project_a, "credential-demo-ingest")
                )
                row = await session.get(SSHCredential, binding.credential_id)
                row.expires_us = services.utc_now_us() - 1
        assert not (await admin.get(source_base(foundation.project_a))).json()["approval"][
            "approved"
        ]
    async with foundation.client(foundation.alice) as inspector:
        with pytest.raises(DomainError) as denied:
            await manager.prepare(
                foundation.alice.principal,
                foundation.project_a,
                "c-ingest",
                3 if change == "config" else 2,
                token_hash(inspector.cookies.get("__Host-si-session")),
            )
        assert (
            denied.value.code
            == {
                "config": "SOURCE_NOT_APPROVED",
                "password": "SOURCE_NOT_APPROVED",
                "trust": "HOST_KEY_REQUIRED",
                "expiry": "SOURCE_APPROVAL_EXPIRED",
                "credential_expiry": "SSH_CREDENTIAL_EXPIRED",
            }[change]
        )


@pytest.mark.parametrize(
    "change",
    [
        "revoke",
        "expiry",
        "credential_expiry",
        "password",
        "config",
        "logout",
        "database",
        "supervisor",
    ],
)
async def test_inflight_inspector_read_stops_after_fresh_authority_loss(
    foundation, tmp_path, monkeypatch, change
):
    manager = foundation.app.state.source_access
    started, stopped = asyncio.Event(), asyncio.Event()
    account = (
        await isolated_admin(foundation)
        if change == "logout"
        else foundation.database.administrator
    )
    async with foundation.client(account) as admin:
        document = await configured(foundation, tmp_path, monkeypatch, admin)
        assert (
            await admin.post(source_base(foundation.project_a) + "/approve", json=approval_body())
        ).status_code == 200
        async with foundation.client(foundation.alice) as inspector:
            # Normal collection is permitted for Inspector, not just setup Administrator.
            login = token_hash(inspector.cookies.get("__Host-si-session"))
            snapshot = await manager.prepare(
                foundation.alice.principal, foundation.project_a, "c-ingest", 2, login
            )

            async def blocked():
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()

            task = asyncio.create_task(
                manager.watched(
                    foundation.alice.principal,
                    foundation.project_a,
                    "c-ingest",
                    2,
                    login,
                    snapshot,
                    blocked,
                )
            )
            await asyncio.wait_for(started.wait(), 3)
            if change == "revoke":
                revoked = await asyncio.wait_for(
                    admin.post(
                        source_base(foundation.project_a) + "/revoke",
                        json={"expected_config_revision": 2, "expected_approval_revision": 1},
                    ),
                    2,
                )
                assert revoked.status_code == 200, revoked.text
            elif change == "expiry":
                async with foundation.database.sessions.begin() as session:
                    row = await session.get(
                        SourceAccessApproval, (foundation.project_a, "c-ingest")
                    )
                    row.expires_us = services.utc_now_us() - 1
            elif change == "credential_expiry":
                async with foundation.database.sessions.begin() as session:
                    binding = await session.get(
                        ProjectCredentialBinding, (foundation.project_a, "credential-demo-ingest")
                    )
                    row = await session.get(SSHCredential, binding.credential_id)
                    row.expires_us = services.utc_now_us() - 1
            elif change == "password":
                assert (
                    await save(admin, foundation.project_a, "synthetic-replacement", 1)
                ).status_code == 200
            elif change == "config":
                document["servers"][0]["description"] = "Configuration changed during remote read."
                changed = await admin.put(
                    f"/api/v1/projects/{foundation.project_a}/topology",
                    json={"expected_revision": 2, "config": document},
                )
                assert changed.status_code == 200, changed.text
            elif change == "logout":
                assert (await inspector.post("/api/v1/auth/logout", json={})).status_code == 200
            elif change == "database":

                async def unavailable(*args, **kwargs):
                    raise SQLAlchemyError()

                monkeypatch.setattr(manager, "prepare", unavailable)
            else:

                async def unavailable():
                    return False

                monkeypatch.setattr(manager.ssh.supervisor, "healthy", unavailable)
            try:
                with pytest.raises(DomainError) as denied:
                    await asyncio.wait_for(task, 2)
                assert stopped.is_set()
                assert (
                    denied.value.code
                    == {
                        "revoke": "SOURCE_NOT_APPROVED",
                        "expiry": "SOURCE_APPROVAL_EXPIRED",
                        "credential_expiry": "SSH_CREDENTIAL_EXPIRED",
                        "password": "SOURCE_NOT_APPROVED",
                        "config": "REVISION_CONFLICT",
                        "logout": "AUTH_REQUIRED",
                        "database": "DATABASE_UNAVAILABLE",
                        "supervisor": "DATABASE_UNAVAILABLE",
                    }[change]
                )
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)


async def test_path_check_uses_only_approved_configured_process_sources(
    foundation, tmp_path, monkeypatch
):
    requests = []

    class Remote:
        warnings = []

        async def plan(self, source, roots):
            requests.append((source, roots))
            return [SimpleNamespace(estimated_bytes=50)]

        async def check(self, candidate):
            assert candidate.estimated_bytes == 50

    @asynccontextmanager
    async def open_files(target, jump, **kwargs):
        assert target.host == "192.0.2.20" and jump is None
        yield Remote()

    monkeypatch.setattr(ssh_files, "open_files", open_files)
    async with foundation.client(foundation.database.administrator) as admin:
        document = await configured(foundation, tmp_path, monkeypatch, admin)
        assert (
            await admin.post(source_base(foundation.project_a) + "/approve", json=approval_body())
        ).status_code == 200
        response = await admin.post(
            source_base(foundation.project_a) + "/test", json={"expected_config_revision": 2}
        )
        assert response.status_code == 200, response.text
        assert response.json()["processes"] == [
            {
                "process_id": "p-ingest-a",
                "accessible": True,
                "candidate_count": 1,
                "estimated_bytes": 50,
                "warning": None,
            }
        ]
        assert requests == [(document["processes"][0]["log_source"], ["/var/log/inspector-demo"])]


async def test_mariadb_rejects_approval_for_cross_project_or_wrong_entity_kind(
    foundation, tmp_path, monkeypatch
):
    async with foundation.client(foundation.database.administrator) as admin:
        await configured(foundation, tmp_path, monkeypatch, admin)
    for project_id, connection_id in [
        (foundation.project_b, "c-ingest"),
        (foundation.project_a, "p-ingest-a"),
    ]:
        async with foundation.database.sessions() as session:
            with pytest.raises(IntegrityError):
                async with session.begin():
                    session.add(
                        SourceAccessApproval(
                            project_id=project_id,
                            connection_id=connection_id,
                            revision=1,
                            approved=True,
                            config_revision=2,
                            route_digest="0" * 64,
                            roots_digest="0" * 64,
                            network_signature="0" * 64,
                            approved_by_user_id=foundation.database.administrator.principal.user_id,
                            approved_us=1,
                            expires_us=2,
                        )
                    )
                    await session.flush()


@pytest.mark.parametrize("change", ["config", "revoke", "credential_expiry"])
async def test_reservation_rechecks_retained_orm_objects_after_network_transaction_gap(
    foundation, tmp_path, monkeypatch, change
):
    manager = foundation.app.state.source_access
    async with foundation.client(foundation.database.administrator) as admin:
        document = await configured(foundation, tmp_path, monkeypatch, admin)
        assert (
            await admin.post(source_base(foundation.project_a) + "/approve", json=approval_body())
        ).status_code == 200
        async with foundation.client(foundation.alice) as inspector:
            login = token_hash(inspector.cookies.get("__Host-si-session"))
            async with foundation.database.sessions() as session:
                binding = await session.get(
                    ProjectCredentialBinding, (foundation.project_a, "credential-demo-ingest")
                )
                # Strong references deliberately preserve identity-map rows across
                # the transaction gap while another request changes authority.
                retained = [
                    await session.get(Project, foundation.project_a),
                    await session.get(TopologyState, foundation.project_a),
                    await session.get(SourceAccessApproval, (foundation.project_a, "c-ingest")),
                    await session.get(SSHCredential, binding.credential_id),
                    await session.get(SSHHostTrust, (foundation.project_a, "c-ingest")),
                    await session.get(AuthSession, login),
                ]
                assert all(retained)
                await session.commit()
                if change == "config":
                    document["servers"][0]["description"] = "Changed between plan and reservation."
                    response = await admin.put(
                        f"/api/v1/projects/{foundation.project_a}/topology",
                        json={"expected_revision": 2, "config": document},
                    )
                    assert response.status_code == 200, response.text
                elif change == "revoke":
                    response = await admin.post(
                        source_base(foundation.project_a) + "/revoke",
                        json={"expected_config_revision": 2, "expected_approval_revision": 1},
                    )
                    assert response.status_code == 200, response.text
                else:
                    async with foundation.database.sessions.begin() as update:
                        credential = await update.get(SSHCredential, binding.credential_id)
                        credential.expires_us = services.utc_now_us() - 1
                async with session.begin():
                    with pytest.raises(DomainError) as denied:
                        await manager.prepare_in_transaction(
                            session,
                            foundation.alice.principal,
                            foundation.project_a,
                            "c-ingest",
                            2,
                            login,
                        )
                assert (
                    denied.value.code
                    == {
                        "config": "REVISION_CONFLICT",
                        "revoke": "SOURCE_NOT_APPROVED",
                        "credential_expiry": "SSH_CREDENTIAL_EXPIRED",
                    }[change]
                )
