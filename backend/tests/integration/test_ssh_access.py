"""Actual MariaDB vault/trust services; transport is isolated in its local SSH suite."""

import asyncio
import copy
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from inspector import auth, ssh_transport
from inspector.domain import Principal
from inspector.persistence.models import (
    Audit,
    ProjectCredentialBinding,
    SSHCredential,
    SSHHostTrust,
)
from inspector.security import issue_token
from inspector.ssh_access import Vault

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]
ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "synthetic-test-password-$-never-a-shell"
OBSERVED = {
    "public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEVhZgysyntheticfixture",
    "algorithm": "ssh-ed25519",
    "fingerprint": "SHA256:synthetic-inspection-fixture",
}


def enable_vault(foundation, tmp_path):
    key = tmp_path / "ssh-vault.key"
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    manager = foundation.app.state.ssh_access
    manager.config = replace(foundation.config, vault_key_file=str(key))
    manager.vault = Vault(str(key))
    return manager


async def isolated_admin(foundation):
    """Logout intentionally revokes every login; never revoke the shared bootstrap."""
    username, password = "ssh-admin-" + issue_token(), issue_token()
    async with foundation.database.sessions.begin() as session:
        user = await auth.create_user(
            session,
            foundation.database.administrator.principal,
            username,
            "Synthetic SSH lifecycle Administrator",
            password,
            role="administrator",
        )
        return replace(
            foundation.database.administrator,
            username=username,
            password=password,
            principal=Principal(user.id, user.role, user.auth_version),
        )


async def seed(client, project_id):
    config = json.loads((ROOT / "examples/project.example.json").read_text(encoding="utf-8"))
    config["project"].update(id=project_id, revision=1)
    response = await client.put(
        f"/api/v1/projects/{project_id}/topology", json={"expected_revision": 1, "config": config}
    )
    assert response.status_code == 200, response.text
    return response.json()["config"]


def base(project):
    return f"/api/v1/projects/{project}/connections/c-ingest"


async def save(client, project, password=PASSWORD, credential_revision=0, config_revision=2):
    return await client.put(
        base(project) + "/password",
        json={
            "expected_config_revision": config_revision,
            "expected_credential_revision": credential_revision,
            "password": password,
        },
    )


async def inspect(client, project, config_revision=2):
    return await client.post(
        base(project) + "/host-key/inspect", json={"expected_config_revision": config_revision}
    )


async def approve(client, project, token, trust_revision=0, config_revision=2, verified=True):
    return await client.post(
        base(project) + "/host-key/approve",
        json={
            "expected_config_revision": config_revision,
            "expected_trust_revision": trust_revision,
            "inspection_token": token,
            "verified": verified,
        },
    )


async def test_passwords_are_encrypted_scoped_write_only_and_replacement_is_versioned(
    foundation, tmp_path
):
    manager = enable_vault(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as client:
        await seed(client, foundation.project_a)
        await seed(client, foundation.project_b)
        before = await client.get(base(foundation.project_a) + "/access")
        assert before.json()["credential"] == {"configured": False, "revision": 0}
        saved = await save(client, foundation.project_a)
        assert saved.status_code == 200, saved.text
        assert saved.json()["credential"] == {"configured": True, "revision": 1}
        assert PASSWORD not in saved.text
        other = await client.get(base(foundation.project_b) + "/access")
        assert other.json()["credential"] == {"configured": False, "revision": 0}
        assert (await save(client, foundation.project_a)).status_code == 409
        updated = await save(client, foundation.project_a, "synthetic-replacement", 1)
        assert updated.status_code == 200
        assert updated.json()["credential"]["revision"] == 2
        exported = await client.get(
            f"/api/v1/projects/{foundation.project_a}/config/export?format=json"
        )
        assert exported.status_code == 200, exported.text
        assert PASSWORD not in exported.text and "synthetic-replacement" not in exported.text
    async with foundation.database.sessions() as session:
        binding = await session.get(
            ProjectCredentialBinding, (foundation.project_a, "credential-demo-ingest")
        )
        credential = await session.get(SSHCredential, binding.credential_id)
        assert b"synthetic-replacement" not in credential.ciphertext
        assert manager.vault.decrypt(credential) == "synthetic-replacement"
        audits = (
            await session.scalars(select(Audit).where(Audit.project_id == foundation.project_a))
        ).all()
        assert all(PASSWORD not in repr(vars(row)) for row in audits)


async def test_inspect_approve_test_revoke_requires_explicit_same_system_verified_key(
    foundation, tmp_path, monkeypatch
):
    enable_vault(foundation, tmp_path)
    calls = []

    async def observed(target, jump=None, **options):
        calls.append("inspect")
        assert target.password == ""  # Inspection never authenticates to target.
        return OBSERVED

    async def connected(target, jump=None, **options):
        calls.append("test")
        assert target.password == PASSWORD
        assert target.host_key == OBSERVED["public_key"]
        return {"ssh": True, "sftp": True}

    monkeypatch.setattr(ssh_transport, "inspect_key", observed)
    monkeypatch.setattr(ssh_transport, "test_connection", connected)
    async with foundation.client(foundation.database.administrator) as client:
        await seed(client, foundation.project_a)
        await seed(client, foundation.project_b)
        assert (await save(client, foundation.project_a)).status_code == 200
        assert (
            await client.post(
                base(foundation.project_a) + "/test", json={"expected_config_revision": 2}
            )
        ).status_code == 409
        inspected = await inspect(client, foundation.project_a)
        assert inspected.status_code == 200, inspected.text
        token = inspected.json()["inspection_token"]
        assert (
            await approve(client, foundation.project_a, token, verified=False)
        ).status_code == 422
        assert (await approve(client, foundation.project_b, token)).status_code == 404
        approved = await approve(client, foundation.project_a, token)
        assert approved.status_code == 200, approved.text
        assert approved.json()["host_key"]["approved"]
        assert (
            await approve(client, foundation.project_a, token, trust_revision=1)
        ).status_code == 404
        tested = await client.post(
            base(foundation.project_a) + "/test", json={"expected_config_revision": 2}
        )
        assert tested.status_code == 200, tested.text
        assert tested.json() == {"ssh": True, "sftp": True, "config_revision": 2}
        revoked = await client.post(
            base(foundation.project_a) + "/revoke",
            json={"expected_config_revision": 2, "expected_trust_revision": 1},
        )
        assert revoked.status_code == 200
        assert revoked.json()["host_key"] == {
            "approved": False,
            "revision": 2,
            "fingerprint": None,
            "algorithm": None,
        }
        assert (
            await client.post(
                base(foundation.project_a) + "/test", json={"expected_config_revision": 2}
            )
        ).status_code == 409
    assert calls == ["inspect", "test"]


async def test_profile_edit_invalidates_trust_without_breaking_normalized_topology(
    foundation, tmp_path, monkeypatch
):
    enable_vault(foundation, tmp_path)

    async def observed(*args, **kwargs):
        return OBSERVED

    monkeypatch.setattr(ssh_transport, "inspect_key", observed)
    async with foundation.client(foundation.database.administrator) as client:
        config = await seed(client, foundation.project_a)
        inspected = await inspect(client, foundation.project_a)
        assert (
            await approve(client, foundation.project_a, inspected.json()["inspection_token"])
        ).status_code == 200
        config = copy.deepcopy(config)
        next(item for item in config["connections"] if item["id"] == "c-ingest")["host"] = (
            "192.0.2.254"
        )
        edited = await client.put(
            f"/api/v1/projects/{foundation.project_a}/topology",
            json={"expected_revision": 2, "config": config},
        )
        assert edited.status_code == 200, edited.text
        status = await client.get(base(foundation.project_a) + "/access")
        assert status.json()["config_revision"] == 3
        assert not status.json()["host_key"]["approved"]
        assert status.json()["host_key"]["fingerprint"] is None
        assert (await inspect(client, foundation.project_a)).status_code == 409


async def test_inspector_cannot_use_setup_endpoints_or_read_access_metadata(
    foundation, tmp_path, monkeypatch
):
    enable_vault(foundation, tmp_path)

    async def forbidden_network(*args, **kwargs):
        pytest.fail("Inspector caused a network setup operation")

    monkeypatch.setattr(ssh_transport, "inspect_key", forbidden_network)
    monkeypatch.setattr(ssh_transport, "test_connection", forbidden_network)
    async with foundation.client(foundation.database.administrator) as client:
        await seed(client, foundation.project_a)
    async with foundation.client(foundation.alice) as client:
        assert (await client.get(base(foundation.project_a) + "/access")).status_code == 403
        assert (await save(client, foundation.project_a)).status_code == 403
        for suffix, body in [
            ("/test", {"expected_config_revision": 2}),
            ("/host-key/inspect", {"expected_config_revision": 2}),
            ("/revoke", {"expected_config_revision": 2, "expected_trust_revision": 0}),
        ]:
            assert (
                await client.post(base(foundation.project_a) + suffix, json=body)
            ).status_code == 403


async def test_password_change_during_network_has_no_database_lock_and_rejects_stale_result(
    foundation, tmp_path, monkeypatch
):
    enable_vault(foundation, tmp_path)
    started, release = asyncio.Event(), asyncio.Event()

    async def observed(*args, **kwargs):
        started.set()
        await release.wait()
        return OBSERVED

    monkeypatch.setattr(ssh_transport, "inspect_key", observed)
    async with foundation.client(foundation.database.administrator) as client:
        await seed(client, foundation.project_a)
        assert (await save(client, foundation.project_a)).status_code == 200
        request = asyncio.create_task(inspect(client, foundation.project_a))
        try:
            await asyncio.wait_for(started.wait(), 3)
            # Finishing this while the network is held proves it holds no security/project lock.
            changed = await asyncio.wait_for(
                save(client, foundation.project_a, "synthetic-rotated", 1), 3
            )
            assert changed.status_code == 200, changed.text
        finally:
            release.set()
        result = await request
        assert result.status_code == 409


async def test_logout_during_network_invalidates_result(foundation, tmp_path, monkeypatch):
    enable_vault(foundation, tmp_path)
    started, release = asyncio.Event(), asyncio.Event()

    async def observed(*args, **kwargs):
        started.set()
        await release.wait()
        return OBSERVED

    monkeypatch.setattr(ssh_transport, "inspect_key", observed)
    account = await isolated_admin(foundation)
    async with foundation.client(account) as client:
        await seed(client, foundation.project_a)
        request = asyncio.create_task(inspect(client, foundation.project_a))
        try:
            await asyncio.wait_for(started.wait(), 3)
            assert (
                await asyncio.wait_for(client.post("/api/v1/auth/logout", json={}), 3)
            ).status_code == 200
        finally:
            release.set()
        assert (await request).status_code == 401


async def test_revoke_before_first_approval_cancels_pending_key_inspection(
    foundation, tmp_path, monkeypatch
):
    manager = enable_vault(foundation, tmp_path)
    started, stopped, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def observed(*args, **kwargs):
        started.set()
        try:
            await release.wait()
            return OBSERVED
        finally:
            stopped.set()

    monkeypatch.setattr(ssh_transport, "inspect_key", observed)
    async with foundation.client(foundation.database.administrator) as client:
        await seed(client, foundation.project_a)
        request = asyncio.create_task(inspect(client, foundation.project_a))
        try:
            await asyncio.wait_for(started.wait(), 3)
            revoked = await client.post(
                base(foundation.project_a) + "/revoke",
                json={"expected_config_revision": 2, "expected_trust_revision": 0},
            )
            assert revoked.status_code == 200, revoked.text
            assert revoked.json()["host_key"] == {
                "approved": False,
                "revision": 1,
                "fingerprint": None,
                "algorithm": None,
            }
            await asyncio.wait_for(stopped.wait(), 2)
            assert (await asyncio.wait_for(request, 1)).status_code == 409
            assert not release.is_set()
            assert manager._network_active == 0
        finally:
            release.set()
            if not request.done():
                request.cancel()
            await asyncio.gather(request, return_exceptions=True)


async def test_mariadb_rejects_host_trust_for_wrong_scoped_entity_type(foundation):
    async with foundation.client(foundation.database.administrator) as client:
        await seed(client, foundation.project_a)
    async with foundation.database.sessions() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                session.add(
                    SSHHostTrust(
                        project_id=foundation.project_a,
                        connection_id="p-ingest-a",
                        revision=1,
                        approved=True,
                        route_digest="0" * 64,
                        public_key=OBSERVED["public_key"],
                        algorithm=OBSERVED["algorithm"],
                        fingerprint=OBSERVED["fingerprint"],
                    )
                )
                await session.flush()
