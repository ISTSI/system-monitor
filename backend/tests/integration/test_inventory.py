"""Actual MariaDB/static-upload reconciliation, without SSH or retained deployment data."""

import asyncio
import copy
import json
import threading
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from inspector import auth, topology
from inspector.errors import DomainError
from inspector.persistence.inventory_models import (
    InventoryHostMapping,
    InventoryPreview,
    InventoryProcessMapping,
    InventoryUpload,
)
from inspector.persistence.models import (
    EntityIdentity,
    LiveSession,
    Project,
    ProjectRevision,
    Server,
    SourceAccessApproval,
    SSHHostTrust,
    TopologySnapshot,
    TopologyState,
    User,
)

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]
ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "examples" / "ansible"


def mapping(**overrides):
    return (
        dict(
            group_to_subsystem={"ingress": "s-ingress", "core": "s-core", "delivery": "s-delivery"},
            host_to_subsystem={},
            tag_only_groups=[],
            credential_mapping={},
            jump_mapping={},
            parser_mapping={},
            preserve_existing_documentation=True,
            preserve_existing_layout=True,
            delete_missing_hosts=False,
        )
        | overrides
    )


async def seed_parser(client, project_id):
    current = (await client.get(f"/api/v1/projects/{project_id}/config")).json()
    config = current["config"]
    example = json.loads((ROOT / "examples" / "project.example.json").read_text(encoding="utf-8"))
    config["parsers"] = example["parsers"]
    result = await client.put(
        f"/api/v1/projects/{project_id}/topology",
        json={"expected_revision": current["revision"], "config": config},
    )
    assert result.status_code == 200, result.text
    return result.json()["revision"]


async def source(client, project_id, name="Primary static inventory"):
    response = await client.post(
        f"/api/v1/projects/{project_id}/inventory/sources", json={"name": name}
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def upload(
    client, project_id, source_id, revision, filename="inventory.hosts.ini", data=None
):
    if data is None:
        data = (FIXTURES / filename).read_bytes()
    response = await client.post(
        f"/api/v1/projects/{project_id}/inventory/uploads",
        params={"inventory_source_id": source_id, "expected_revision": revision},
        content=data,
        headers={
            "content-type": "application/octet-stream",
            "x-inventory-filename": quote(filename),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def parse_payload(staged, format, source_files=None):
    return dict(
        inventory_source_id=staged["inventory_source_id"],
        upload_id=staged["upload_id"],
        expected_revision=staged["expected_revision"],
        format=format,
        source_files=source_files or staged["source_candidates"],
    )


async def preview(client, project_id, staged, format, selected_mapping=None, source_files=None):
    response = await client.post(
        f"/api/v1/projects/{project_id}/inventory/preview",
        json=dict(
            project_id=project_id,
            **parse_payload(staged, format, source_files),
            mapping=selected_mapping or mapping(),
        ),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def commit(client, project_id, pending):
    response = await client.post(
        f"/api/v1/projects/{project_id}/inventory/commit",
        json={
            "preview_id": pending["preview_id"],
            "expected_revision": pending["expected_revision"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    "filename,format,process_count",
    [
        ("inventory.hosts.ini", "ini", 0),
        ("inventory.static.yaml", "yaml", 5),
        ("inventory.canonical.json", "canonical_json", 5),
        ("inventory-with-vars.zip", "static_zip", 5),
    ],
)
async def test_uploaded_formats_atomic_commit_stable_reimport_and_no_approval(
    foundation, filename, format, process_count
):
    admin = foundation.database.administrator
    project_id = foundation.project_a
    async with foundation.client(admin) as client:
        revision = await seed_parser(client, project_id)
        source_id = await source(client, project_id)
        staged = await upload(client, project_id, source_id, revision, filename)
        selected = ["hosts.ini"] if format == "static_zip" else None
        parsed = await client.post(
            f"/api/v1/projects/{project_id}/inventory/parse",
            json=parse_payload(staged, format, selected),
        )
        assert parsed.status_code == 200, parsed.text
        assert len(parsed.json()["hosts"]) == 3
        assert parsed.json()["process_count"] == process_count
        assert (foundation.app.state.inventory.path(staged["upload_id"])).is_file()
        pending = await preview(client, project_id, staged, format, source_files=selected)
        assert pending["can_commit"], pending
        current = await commit(client, project_id, pending)
        assert current["revision"] == revision + 1
        assert len(current["config"]["servers"]) == 3
        assert len(current["config"]["processes"]) == process_count
        assert not foundation.app.state.inventory.path(staged["upload_id"]).exists()
        # Filename is not identity; an explicitly selected same source is.
        renamed = "renamed.zip" if format == "static_zip" else "hosts"
        staged = await upload(
            client,
            project_id,
            source_id,
            current["revision"],
            renamed,
            (FIXTURES / filename).read_bytes(),
        )
        pending = await preview(client, project_id, staged, format, source_files=selected)
        assert pending["can_commit"], pending
        assert {record["status"] for record in pending["records"]} == {"unchanged"}
        repeated = await commit(client, project_id, pending)
        assert repeated == current
    async with foundation.database.sessions() as session:
        assert not (
            await session.scalars(
                select(InventoryUpload).where(InventoryUpload.project_id == project_id)
            )
        ).all()
        assert not (
            await session.scalars(
                select(InventoryPreview).where(InventoryPreview.project_id == project_id)
            )
        ).all()
        assert not (
            await session.scalars(select(SSHHostTrust).where(SSHHostTrust.project_id == project_id))
        ).all()
        assert not (
            await session.scalars(
                select(SourceAccessApproval).where(SourceAccessApproval.project_id == project_id)
            )
        ).all()


async def test_project_source_identity_membership_and_host_only_import(foundation):
    async with foundation.client(foundation.database.administrator) as client:
        targets = []
        for project_id in (foundation.project_a, foundation.project_b):
            source_id = await source(client, project_id, "hosts")
            staged = await upload(
                client,
                project_id,
                source_id,
                1,
                "hosts",
                b"[one]\nshared ansible_host=192.0.2.20 ansible_user=logreader\n[two]\nshared\n",
            )
            blocked = await preview(
                client,
                project_id,
                staged,
                "ini",
                mapping(group_to_subsystem={"one": "s-one", "two": "s-two"}, tag_only_groups=[]),
            )
            assert not blocked["can_commit"]
            denied = await client.post(
                f"/api/v1/projects/{project_id}/inventory/commit",
                json={"preview_id": blocked["preview_id"], "expected_revision": 1},
            )
            assert denied.status_code == 409
            assert (await client.get(f"/api/v1/projects/{project_id}/config")).json()[
                "revision"
            ] == 1
            resolved = await preview(
                client,
                project_id,
                staged,
                "ini",
                mapping(
                    group_to_subsystem={"one": "s-one", "two": "s-two"},
                    host_to_subsystem={"shared": "s-one"},
                    tag_only_groups=["two"],
                ),
            )
            current = await commit(client, project_id, resolved)
            assert current["config"]["processes"] == []
            assert current["config"]["servers"][0]["tags"] == ["two"]
            targets.append(current["config"]["servers"][0]["id"])
        assert targets[0] != targets[1]
        # A second same-named file belongs to a distinct source and must not match by IP/alias.
        separate = await source(client, foundation.project_a, "Independent source")
        staged = await upload(
            client,
            foundation.project_a,
            separate,
            2,
            "hosts",
            b"[one]\nshared ansible_host=192.0.2.20\n",
        )
        separate_preview = await preview(
            client,
            foundation.project_a,
            staged,
            "ini",
            mapping(group_to_subsystem={"one": "s-one"}, tag_only_groups=[]),
        )
        assert separate_preview["records"][0]["target_id"] != targets[0]
        assert not separate_preview["can_commit"]  # project name uniqueness, no silent merge
    async with foundation.database.sessions.begin() as session:
        session.add(
            InventoryHostMapping(
                project_id=foundation.project_b,
                source_id=separate,
                alias="foreign",
                server_id=targets[0],
                connection_id=targets[0],
                baseline={},
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


async def test_address_update_preserves_manual_documentation_layout_flows_and_unrelated_processes(
    foundation,
):
    project_id = foundation.project_a
    original = json.loads((FIXTURES / "inventory.canonical.json").read_text(encoding="utf-8"))
    async with foundation.client(foundation.database.administrator) as client:
        revision = await seed_parser(client, project_id)
        source_id = await source(client, project_id)
        staged = await upload(
            client, project_id, source_id, revision, "inventory.json", json.dumps(original).encode()
        )
        current = await commit(
            client, project_id, await preview(client, project_id, staged, "canonical_json")
        )
        value = current["config"]
        host = value["servers"][0]
        host["description"] = "Keep **manual** documentation."
        value["processes"][0]["description"] = "Manual process documentation"
        manual = copy.deepcopy(value["processes"][0])
        manual.update(id="manual-process", name="Separate manually configured process")
        value["processes"].append(manual)
        value["flows"] = [
            dict(
                id="manual-flow",
                name="Documented only",
                source_process_id=value["processes"][0]["id"],
                target_process_id="manual-process",
                protocol="TCP",
                description="Manual flow",
            )
        ]
        value["views"] = [
            dict(
                id="manual-view",
                name="Manual layout",
                nodes=[
                    dict(
                        element_id=host["subsystem_id"],
                        x=0,
                        y=0,
                        width=600,
                        height=500,
                        collapsed=False,
                    ),
                    dict(element_id=host["id"], x=133, y=77, width=410, height=300, collapsed=True),
                    dict(
                        element_id=value["processes"][0]["id"],
                        x=15,
                        y=70,
                        width=300,
                        height=60,
                        collapsed=False,
                    ),
                    dict(
                        element_id="manual-process",
                        x=15,
                        y=140,
                        width=300,
                        height=60,
                        collapsed=False,
                    ),
                ],
                flow_ids=["manual-flow"],
            )
        ]
        edited = await client.put(
            f"/api/v1/projects/{project_id}/topology",
            json={"expected_revision": current["revision"], "config": value},
        )
        assert edited.status_code == 200, edited.text
        current = edited.json()
        changed = copy.deepcopy(original)
        changed["_meta"]["hostvars"][host["name"]]["ansible_host"] = "192.0.2.99"
        staged = await upload(
            client,
            project_id,
            source_id,
            current["revision"],
            "changed.json",
            json.dumps(changed).encode(),
        )
        pending = await preview(client, project_id, staged, "canonical_json")
        assert pending["can_commit"], pending
        updated = await commit(client, project_id, pending)
        assert updated["config"]["servers"] == current["config"]["servers"]
        assert updated["config"]["processes"] == current["config"]["processes"]
        assert updated["config"]["views"] == current["config"]["views"]
        assert updated["config"]["flows"] == current["config"]["flows"]
        connection_id = host["connection_id"]
        assert (
            next(c for c in updated["config"]["connections"] if c["id"] == connection_id)["host"]
            == "192.0.2.99"
        )
        # Missing hosts/processes are retained. Remove one extension, then a whole host.
        absent_alias = next(
            alias for alias in changed["_meta"]["hostvars"] if alias != host["name"]
        )
        del changed["_meta"]["hostvars"][absent_alias]
        for group in changed.values():
            if isinstance(group, dict) and isinstance(group.get("hosts"), list):
                group["hosts"] = [alias for alias in group["hosts"] if alias != absent_alias]
        changed["_meta"]["hostvars"][host["name"]]["inspector_processes"] = []
        staged = await upload(
            client,
            project_id,
            source_id,
            updated["revision"],
            "absent.json",
            json.dumps(changed).encode(),
        )
        pending = await preview(client, project_id, staged, "canonical_json")
        assert any(record["status"] == "absent" for record in pending["records"])
        absent = await commit(client, project_id, pending)
        assert absent["config"]["servers"] == updated["config"]["servers"]
        assert absent["config"]["processes"] == updated["config"]["processes"]
        # A manual address change blocks reimport and leaves all model rows unchanged.
        value = copy.deepcopy(absent["config"])
        value["connections"][0]["host"] = "192.0.2.88"
        edited = await client.put(
            f"/api/v1/projects/{project_id}/topology",
            json={"expected_revision": absent["revision"], "config": value},
        )
        assert edited.status_code == 200
        staged = await upload(
            client,
            project_id,
            source_id,
            edited.json()["revision"],
            "manual.json",
            json.dumps(changed).encode(),
        )
        pending = await preview(client, project_id, staged, "canonical_json")
        assert not pending["can_commit"]
        assert any(conflict["code"] == "MANUAL_EDIT" for conflict in pending["conflicts"])
        response = await client.post(
            f"/api/v1/projects/{project_id}/inventory/commit",
            json={
                "preview_id": pending["preview_id"],
                "expected_revision": pending["expected_revision"],
            },
        )
        assert response.status_code == 409
        assert (await client.get(f"/api/v1/projects/{project_id}/config")).json() == edited.json()


async def test_secret_omission_scope_owner_stale_and_tampered_bindings(foundation):
    project_id = foundation.project_a
    secret = "SyntheticDoNotPersistThisSecret"
    async with foundation.client(foundation.database.administrator) as client:
        source_id = await source(client, project_id)
        staged = await upload(
            client,
            project_id,
            source_id,
            1,
            "hosts",
            f"[one]\nshared ansible_host=192.0.2.20 ansible_password={secret}\n".encode(),
        )
        pending = await preview(
            client,
            project_id,
            staged,
            "ini",
            mapping(group_to_subsystem={"one": "s-one"}, tag_only_groups=[]),
        )
        assert secret not in json.dumps(pending)
        async with foundation.database.sessions() as session:
            upload_row = await session.get(InventoryUpload, (project_id, staged["upload_id"]))
            preview_row = await session.get(InventoryPreview, (project_id, pending["preview_id"]))
            assert secret not in json.dumps(upload_row.summary)
            assert secret not in json.dumps(preview_row.document)
        foreign = await client.post(
            f"/api/v1/projects/{foundation.project_b}/inventory/commit",
            json={"preview_id": pending["preview_id"], "expected_revision": 1},
        )
        assert foreign.status_code == 404
        # Another Administrator has no private staging bypass.
        username, password = f"inventory-admin-{uuid4()}", "Synthetic administrator password 12345"
        async with foundation.database.sessions.begin() as session:
            await auth.create_user(
                session,
                foundation.database.administrator.principal,
                username,
                "Other administrator",
                password,
                role="administrator",
            )
        async with foundation.client() as other:
            csrf = (await other.get("/api/v1/auth/csrf")).json()["csrf_token"]
            login = await other.post(
                "/api/v1/auth/login",
                json={"username": username, "password": password},
                headers={"x-csrf-token": csrf},
            )
            other.headers["x-csrf-token"] = login.json()["csrf_token"]
            denied = await other.post(
                f"/api/v1/projects/{project_id}/inventory/commit",
                json={"preview_id": pending["preview_id"], "expected_revision": 1},
            )
            assert denied.status_code == 404
        async with foundation.database.sessions.begin() as session:
            await session.execute(
                update(InventoryPreview)
                .where(
                    InventoryPreview.project_id == project_id,
                    InventoryPreview.id == pending["preview_id"],
                )
                .values(mapping_digest="0" * 64)
            )
        tampered = await client.post(
            f"/api/v1/projects/{project_id}/inventory/commit",
            json={"preview_id": pending["preview_id"], "expected_revision": 1},
        )
        assert tampered.status_code == 409
        pending = await preview(
            client,
            project_id,
            staged,
            "ini",
            mapping(group_to_subsystem={"one": "s-one"}, tag_only_groups=[]),
        )
        changed = await client.patch(
            f"/api/v1/projects/{project_id}/metadata",
            json={"expected_revision": 1, "name": "Revision changed", "description": ""},
        )
        assert changed.status_code == 200
        stale = await client.post(
            f"/api/v1/projects/{project_id}/inventory/commit",
            json={"preview_id": pending["preview_id"], "expected_revision": 2},
        )
        assert stale.status_code == 409
    async with foundation.database.sessions() as session:
        assert (await session.get(Project, project_id)).revision == 2
        assert (await session.get(TopologyState, project_id)).config["servers"] == []


async def test_inspector_denials_csrf_cancel_expiry_and_malicious_upload_cleanup(foundation):
    project_id = foundation.project_a
    endpoint = f"/api/v1/projects/{project_id}/inventory"
    async with foundation.client(foundation.database.administrator) as admin:
        source_id = await source(admin, project_id)
        staged = await upload(admin, project_id, source_id, 1)
        pending = await preview(admin, project_id, staged, "ini")
        async with foundation.client(foundation.alice) as inspector:
            assert (await inspector.get(endpoint + "/sources")).status_code == 403
            attempts = [
                ("/sources", {"name": "forged"}),
                ("/parse", parse_payload(staged, "ini")),
                (
                    "/preview",
                    dict(project_id=project_id, **parse_payload(staged, "ini"), mapping=mapping()),
                ),
                ("/commit", {"preview_id": pending["preview_id"], "expected_revision": 1}),
                (f"/uploads/{staged['upload_id']}/cancel", {}),
                (f"/previews/{pending['preview_id']}/cancel", {}),
            ]
            for suffix, body in attempts:
                response = await inspector.post(endpoint + suffix, json=body)
                assert response.status_code == 403, (suffix, response.text)
            denied_upload = await inspector.post(
                endpoint + "/uploads",
                params={"inventory_source_id": source_id, "expected_revision": 1},
                content=b"[one]\nhost",
                headers={"x-inventory-filename": "hosts"},
            )
            assert denied_upload.status_code == 403
        missing_csrf = await admin.post(
            endpoint + "/sources", json={"name": "forged"}, headers={"x-csrf-token": ""}
        )
        assert missing_csrf.status_code == 403
        cancelled = await admin.post(
            endpoint + f"/previews/{pending['preview_id']}/cancel", json={}
        )
        assert cancelled.status_code == 200
        assert foundation.app.state.inventory.path(staged["upload_id"]).exists()
        consumed = await admin.post(
            endpoint + "/commit", json={"preview_id": pending["preview_id"], "expected_revision": 1}
        )
        assert consumed.status_code == 404
        remapped = await preview(
            admin,
            project_id,
            staged,
            "ini",
            mapping(
                group_to_subsystem={
                    "ingress": "s-ingress",
                    "core": "s-core-remapped",
                    "delivery": "s-delivery",
                }
            ),
        )
        assert remapped["can_commit"]
        core = next(record for record in remapped["records"] if record["alias"] == "demo-core-01")
        assert (
            next(change for change in core["changes"] if change["field"] == "server")["after"][
                "subsystem_id"
            ]
            == "s-core-remapped"
        )
        cancelled_upload = await admin.post(
            endpoint + f"/uploads/{staged['upload_id']}/cancel", json={}
        )
        assert cancelled_upload.status_code == 200
        assert not foundation.app.state.inventory.path(staged["upload_id"]).exists()
        assert (
            await admin.post(
                endpoint + "/commit",
                json={"preview_id": remapped["preview_id"], "expected_revision": 1},
            )
        ).status_code == 404
        staged = await upload(admin, project_id, source_id, 1)
        async with foundation.database.sessions.begin() as session:
            await session.execute(
                update(InventoryUpload)
                .where(
                    InventoryUpload.project_id == project_id,
                    InventoryUpload.id == staged["upload_id"],
                )
                .values(expires_us=1)
            )
        expired = await admin.post(endpoint + "/parse", json=parse_payload(staged, "ini"))
        assert expired.status_code == 410
        await foundation.app.state.inventory.purge()
        assert not foundation.app.state.inventory.path(staged["upload_id"]).exists()
        before = set(foundation.app.state.inventory.directory.iterdir())
        bad = await admin.post(
            endpoint + "/uploads",
            params={"inventory_source_id": source_id, "expected_revision": 1},
            content=b"#!/bin/sh\necho do-not-execute",
            headers={"x-inventory-filename": "hosts"},
        )
        # Upload inspection may classify; parse is the static semantics gate.
        if bad.status_code == 200:
            response = await admin.post(
                endpoint + "/parse", json=parse_payload(bad.json(), "ini", ["hosts"])
            )
            assert response.status_code == 422
            assert "do-not-execute" not in response.text
            await admin.post(endpoint + f"/uploads/{bad.json()['upload_id']}/cancel", json={})
        else:
            assert bad.status_code == 422
        assert set(foundation.app.state.inventory.directory.iterdir()) == before


async def test_preview_upload_foreign_keys_bind_project_source_and_owner(foundation):
    admin = foundation.database.administrator
    async with foundation.client(admin) as client:
        source_a = await source(client, foundation.project_a, "A")
        source_other = await source(client, foundation.project_a, "Other")
        source_b = await source(client, foundation.project_b, "B")
        staged = await upload(client, foundation.project_a, source_a, 1)
    baseline = dict(
        project_id=foundation.project_a,
        id=str(uuid4()),
        source_id=source_a,
        upload_id=staged["upload_id"],
        owner_user_id=admin.principal.user_id,
        auth_version=admin.principal.auth_version,
        expected_revision=1,
        content_digest="0" * 64,
        manifest_digest="0" * 64,
        mapping_digest="0" * 64,
        digest="0" * 64,
        document={},
        expires_us=staged["expires_us"],
    )
    for invalid in (
        dict(project_id=foundation.project_b, source_id=source_b),
        dict(source_id=source_other),
        dict(owner_user_id=foundation.alice.principal.user_id),
        dict(upload_id=str(uuid4())),
    ):
        async with foundation.database.sessions() as session:
            session.add(InventoryPreview(**(baseline | invalid)))
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()


async def test_upload_releases_authorization_locks_and_rechecks_revocation_before_staging(
    foundation,
):
    admin = foundation.database.administrator
    username, password = f"upload-admin-{uuid4()}", "Synthetic upload administrator password 12345"
    async with foundation.database.sessions.begin() as session:
        user = await auth.create_user(
            session,
            admin.principal,
            username,
            "Upload administrator",
            password,
            role="administrator",
        )
        user_id = user.id
    async with foundation.client(admin) as administrator:
        source_id = await source(administrator, foundation.project_a)
    async with foundation.client() as client:
        csrf = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
            headers={"x-csrf-token": csrf},
        )
        assert login.status_code == 200
        client.headers["x-csrf-token"] = login.json()["csrf_token"]
        streaming, finish = asyncio.Event(), asyncio.Event()

        async def chunks():
            yield b"[one]\n"
            streaming.set()
            await finish.wait()
            yield b"host ansible_host=192.0.2.20\n"

        upload_task = asyncio.create_task(
            client.post(
                f"/api/v1/projects/{foundation.project_a}/inventory/uploads",
                params={"inventory_source_id": source_id, "expected_revision": 1},
                content=chunks(),
                headers={"x-inventory-filename": "hosts"},
            )
        )
        try:
            await asyncio.wait_for(streaming.wait(), timeout=5)
            # This must complete while the client still controls its streaming body.
            async with asyncio.timeout(2):
                async with foundation.database.sessions.begin() as session:
                    await session.execute(
                        update(User)
                        .where(User.id == user_id)
                        .values(auth_version=User.auth_version + 1)
                    )
            finish.set()
            rejected = await upload_task
            assert rejected.status_code == 401
        finally:
            finish.set()
            if not upload_task.done():
                upload_task.cancel()
                await asyncio.gather(upload_task, return_exceptions=True)
    async with foundation.database.sessions() as session:
        assert not (
            await session.scalars(
                select(InventoryUpload).where(InventoryUpload.owner_user_id == user_id)
            )
        ).all()
    assert list(foundation.app.state.inventory.directory.iterdir()) == []


@pytest.mark.parametrize(
    "settings,status,code",
    [
        ({"inventory_upload_bytes": 8}, 413, "PAYLOAD_TOO_LARGE"),
        ({"inventory_expanded_bytes": 8}, 422, "EXPANDED_LIMIT"),
        ({"inventory_file_limit": 1}, 422, "FILE_LIMIT"),
    ],
)
async def test_configured_inventory_ceiling_rejects_actual_upload_without_staging(
    foundation, settings, status, code
):
    async with foundation.client(foundation.database.administrator) as client:
        source_id = await source(client, foundation.project_a)
        original = foundation.app.state.config
        foundation.app.state.config = replace(original, **settings)
        try:
            result = await client.post(
                f"/api/v1/projects/{foundation.project_a}/inventory/uploads",
                params={"inventory_source_id": source_id, "expected_revision": 1},
                content=(FIXTURES / "inventory-with-vars.zip").read_bytes(),
                headers={"x-inventory-filename": "bundle.zip"},
            )
            assert result.status_code == status, result.text
            assert result.json()["error"]["code"] == code
        finally:
            foundation.app.state.config = original
    assert list(foundation.app.state.inventory.directory.iterdir()) == []
    async with foundation.database.sessions() as session:
        assert not (
            await session.scalars(
                select(InventoryUpload).where(InventoryUpload.project_id == foundation.project_a)
            )
        ).all()


async def test_mid_transaction_failure_rolls_back_topology_mappings_revision_and_allows_retry(
    foundation, monkeypatch
):
    project_id = foundation.project_a
    observed = {}
    original_flush = AsyncSession.flush

    async def fail_after_mapping_flush(session, objects=None):
        importing = any(
            isinstance(row, InventoryHostMapping) and row.project_id == project_id
            for row in session.new
        )
        await original_flush(session, objects)
        if importing:
            # Prove real SQL mutations exist in the uncommitted transaction.
            observed["hosts"] = await session.scalar(
                select(func.count())
                .select_from(InventoryHostMapping)
                .where(InventoryHostMapping.project_id == project_id)
            )
            observed["servers"] = await session.scalar(
                select(func.count()).select_from(Server).where(Server.project_id == project_id)
            )
            observed["revision"] = await session.scalar(
                select(Project.revision).where(Project.id == project_id)
            )
            raise DomainError(
                "SYNTHETIC_IMPORT_INTERRUPTED", "Synthetic inventory transaction interrupted.", 503
            )

    async with foundation.client(foundation.database.administrator) as client:
        before = (await client.get(f"/api/v1/projects/{project_id}/config")).json()
        source_id = await source(client, project_id)
        staged = await upload(client, project_id, source_id, before["revision"])
        pending = await preview(client, project_id, staged, "ini")
        assert pending["can_commit"]
        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "flush", fail_after_mapping_flush)
            interrupted = await client.post(
                f"/api/v1/projects/{project_id}/inventory/commit",
                json={
                    "preview_id": pending["preview_id"],
                    "expected_revision": pending["expected_revision"],
                },
            )
        assert interrupted.status_code == 503
        assert interrupted.json()["error"]["code"] == "SYNTHETIC_IMPORT_INTERRUPTED"
        assert observed == {"hosts": 3, "servers": 3, "revision": before["revision"] + 1}
        assert (await client.get(f"/api/v1/projects/{project_id}/config")).json() == before
        async with foundation.database.sessions() as session:
            state = await session.get(TopologyState, project_id)
            assert (
                state.config == before["config"]
                and state.undo_stack == []
                and state.redo_stack == []
            )
            assert (await session.get(Project, project_id)).revision == before["revision"]
            assert list(
                (
                    await session.scalars(
                        select(ProjectRevision.revision).where(
                            ProjectRevision.project_id == project_id
                        )
                    )
                ).all()
            ) == [before["revision"]]
            assert list(
                (
                    await session.scalars(
                        select(TopologySnapshot.revision).where(
                            TopologySnapshot.project_id == project_id
                        )
                    )
                ).all()
            ) == [before["revision"]]
            for model in (
                InventoryHostMapping,
                InventoryProcessMapping,
                EntityIdentity,
                *[entry[1] for entry in topology.COLLECTIONS.values()],
            ):
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(model)
                        .where(model.project_id == project_id)
                    )
                    == 0
                )
            assert await session.get(InventoryUpload, (project_id, staged["upload_id"])) is not None
            assert (
                await session.get(InventoryPreview, (project_id, pending["preview_id"])) is not None
            )
        assert foundation.app.state.inventory.path(staged["upload_id"]).is_file()
        retried = await commit(client, project_id, pending)
        assert retried["revision"] == before["revision"] + 1
        assert len(retried["config"]["servers"]) == 3
        assert not foundation.app.state.inventory.path(staged["upload_id"]).exists()
        async with foundation.database.sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(InventoryHostMapping)
                    .where(InventoryHostMapping.project_id == project_id)
                )
                == 3
            )
            assert await session.get(InventoryUpload, (project_id, staged["upload_id"])) is None
            assert await session.get(InventoryPreview, (project_id, pending["preview_id"])) is None


@pytest.mark.parametrize("cancellation", ["upload-cancel", "expiry-reaper"])
async def test_active_inventory_parser_cooperatively_stops_when_upload_is_cancelled_or_expired(
    foundation, monkeypatch, cancellation
):
    from inspector import inventory_parser

    project_id = foundation.project_a
    started = threading.Event()
    original = inventory_parser.parse_inventory

    def waiting_parser(*args, **kwargs):
        cancelled = kwargs.get("cancelled")
        assert callable(cancelled), "Production parser must receive a cancellation callback."
        started.set()
        deadline = time.monotonic() + 4
        while not cancelled():
            if time.monotonic() > deadline:
                raise AssertionError("Upload cancellation did not reach its parser.")
            time.sleep(0.005)
        return original(*args, **kwargs)

    async with foundation.client(foundation.database.administrator) as client:
        source_id = await source(client, project_id)
        staged = await upload(client, project_id, source_id, 1)
        monkeypatch.setattr(inventory_parser, "parse_inventory", waiting_parser)
        parsing = asyncio.create_task(
            client.post(
                f"/api/v1/projects/{project_id}/inventory/parse", json=parse_payload(staged, "ini")
            )
        )
        try:
            assert await asyncio.to_thread(started.wait, 2)
            async with asyncio.timeout(2):
                if cancellation == "upload-cancel":
                    cancelled = await client.post(
                        f"/api/v1/projects/{project_id}/inventory/uploads/{staged['upload_id']}/cancel",
                        json={},
                    )
                    assert cancelled.status_code == 200, cancelled.text
                else:
                    async with foundation.database.sessions.begin() as session:
                        await session.execute(
                            update(InventoryUpload)
                            .where(
                                InventoryUpload.project_id == project_id,
                                InventoryUpload.id == staged["upload_id"],
                            )
                            .values(expires_us=1)
                        )
                    await foundation.app.state.inventory.purge()
                response = await parsing
            assert response.status_code == 422, response.text
            assert response.json()["error"]["code"] == "IMPORT_CANCELLED"
        finally:
            foundation.app.state.inventory.cancel(project_id, staged["upload_id"])
            if not parsing.done():
                parsing.cancel()
                await asyncio.gather(parsing, return_exceptions=True)
    assert foundation.app.state.inventory.operations == {}
    assert not foundation.app.state.inventory.path(staged["upload_id"]).exists()
    async with foundation.database.sessions() as session:
        assert await session.get(InventoryUpload, (project_id, staged["upload_id"])) is None
        assert (await session.get(Project, project_id)).revision == 1


async def test_missing_inventory_parser_can_be_mapped_only_to_existing_same_system_parser(
    foundation,
):
    project_id = foundation.project_a
    payload = json.loads((FIXTURES / "inventory.canonical.json").read_text("utf-8"))
    for host in payload["_meta"]["hostvars"].values():
        for process in host["inspector_processes"]:
            process["log_source"]["parser_id"] = "external-parser"
    async with foundation.client(foundation.database.administrator) as client:
        revision = await seed_parser(client, project_id)
        foreign = (await client.get(f"/api/v1/projects/{foundation.project_b}/config")).json()[
            "config"
        ]
        sample = json.loads((ROOT / "examples/project.example.json").read_text("utf-8"))["parsers"][
            0
        ]
        foreign["parsers"] = [sample | {"id": "foreign-only-parser"}]
        assert (
            await client.put(
                f"/api/v1/projects/{foundation.project_b}/topology",
                json={"expected_revision": 1, "config": foreign},
            )
        ).status_code == 200
        source_id = await source(client, project_id)
        staged = await upload(
            client, project_id, source_id, revision, "inventory.json", json.dumps(payload).encode()
        )
        unresolved = await preview(client, project_id, staged, "canonical_json")
        assert not unresolved["can_commit"]
        assert sum(record["status"] == "unassigned" for record in unresolved["records"]) == 5
        denied = await client.post(
            f"/api/v1/projects/{project_id}/inventory/preview",
            json=dict(
                project_id=project_id,
                **parse_payload(staged, "canonical_json"),
                mapping=mapping(parser_mapping={"external-parser": "foreign-only-parser"}),
            ),
        )
        assert denied.status_code == 422 and denied.json()["error"]["code"] == "INVALID_MAPPING"
        pending = await preview(
            client,
            project_id,
            staged,
            "canonical_json",
            mapping(parser_mapping={"external-parser": "parser-iso-utc"}),
        )
        assert pending["can_commit"]
        current = await commit(client, project_id, pending)
        assert len(current["config"]["processes"]) == 5
        assert {
            process["log_source"]["parser_id"] for process in current["config"]["processes"]
        } == {"parser-iso-utc"}


async def test_changed_inventory_process_path_never_retargets_existing_live_source_snapshot(
    foundation, tmp_path
):
    import asyncssh
    from test_history_ssh import copy_logs, endpoint
    from test_live import live_config, start, until, workspace

    live_config(foundation, tmp_path)
    root = copy_logs(tmp_path)
    project_id = foundation.project_a
    extension = copy.deepcopy(
        json.loads((FIXTURES / "inventory.canonical.json").read_text("utf-8"))["_meta"]["hostvars"][
            "demo-ingest-01"
        ]["inspector_processes"][0]
    )
    old_path = extension["log_source"]["active_path"]
    new_path = "/var/log/inspector-demo/ingest/next.log"
    (root / new_path.lstrip("/")).write_text(
        "2026-10-16T12:00:01Z SHOULD_NOT_RETARGET\n", encoding="utf-8"
    )
    async with endpoint(root) as (target, captured):
        async with foundation.client(foundation.database.administrator) as client:
            revision = await seed_parser(client, project_id)
            payload = {
                "_meta": {
                    "hostvars": {
                        "imported-node": {
                            "ansible_host": target.host,
                            "ansible_port": target.port,
                            "ansible_user": target.username,
                            "inspector_subsystem": "s-imported",
                            "inspector_processes": [extension],
                        }
                    }
                },
                "all": {"hosts": ["imported-node"]},
            }
            source_id = await source(client, project_id)
            selected_mapping = mapping(group_to_subsystem={}, tag_only_groups=[])
            staged = await upload(
                client,
                project_id,
                source_id,
                revision,
                "inventory.json",
                json.dumps(payload).encode(),
            )
            current = await commit(
                client,
                project_id,
                await preview(client, project_id, staged, "canonical_json", selected_mapping),
            )
            process_id = current["config"]["processes"][0]["id"]
            connection_id = current["config"]["servers"][0]["connection_id"]
            connection = f"/api/v1/projects/{project_id}/connections/{connection_id}"
            assert (
                await client.put(
                    connection + "/password",
                    json={
                        "expected_config_revision": current["revision"],
                        "expected_credential_revision": 0,
                        "password": target.password,
                    },
                )
            ).status_code == 200
            inspection = await client.post(
                connection + "/host-key/inspect",
                json={"expected_config_revision": current["revision"]},
            )
            assert inspection.status_code == 200, inspection.text
            assert (
                inspection.json()["fingerprint"]
                == asyncssh.import_public_key(target.host_key).get_fingerprint()
            )
            assert (
                await client.post(
                    connection + "/host-key/approve",
                    json={
                        "expected_config_revision": current["revision"],
                        "expected_trust_revision": 0,
                        "inspection_token": inspection.json()["inspection_token"],
                        "verified": True,
                    },
                )
            ).status_code == 200
            assert (
                await client.post(
                    connection + "/source-access/approve",
                    json={
                        "expected_config_revision": current["revision"],
                        "expected_approval_revision": 0,
                        "verified": True,
                    },
                )
            ).status_code == 200
            try:
                work = await workspace(client, project_id)
                running = await start(client, project_id, work, [process_id])
                identity = running["session_id"]
                await until(
                    client,
                    project_id,
                    identity,
                    lambda state: (
                        state["status"] == "following" and bool(state["snapshot"]["events"])
                    ),
                )
                async with foundation.database.sessions() as session:
                    before = await session.get(LiveSession, (project_id, identity))
                    original_snapshot = copy.deepcopy(before.config_snapshot)
                    original_revision = before.config_revision
                payload["_meta"]["hostvars"]["imported-node"]["inspector_processes"][0][
                    "log_source"
                ]["active_path"] = new_path
                staged = await upload(
                    client,
                    project_id,
                    source_id,
                    current["revision"],
                    "inventory.json",
                    json.dumps(payload).encode(),
                )
                pending = await preview(
                    client, project_id, staged, "canonical_json", selected_mapping
                )
                assert pending["can_commit"], pending
                assert (
                    next(record for record in pending["records"] if record["kind"] == "process")[
                        "status"
                    ]
                    == "changed"
                )
                updated = await commit(client, project_id, pending)
                assert updated["config"]["processes"][0]["id"] == process_id
                assert updated["config"]["processes"][0]["log_source"]["active_path"] == new_path
                async with foundation.database.sessions() as session:
                    existing = await session.get(LiveSession, (project_id, identity))
                    assert existing.config_snapshot == original_snapshot
                    assert existing.config_revision == original_revision
                    assert (
                        existing.config_snapshot["processes"][0]["log_source"]["active_path"]
                        == old_path
                    )
                with (root / old_path.lstrip("/")).open("ab") as old_file:
                    old_file.write(b"2026-10-16T12:00:02Z OLD_SNAPSHOT_AFTER_IMPORT\n")
                retained = await until(
                    client,
                    project_id,
                    identity,
                    lambda state: (
                        state["status"] == "interrupted"
                        or any(
                            "OLD_SNAPSHOT_AFTER_IMPORT" in event["raw_line"]
                            for event in state["snapshot"]["events"]
                        )
                    ),
                )
                if retained["status"] == "interrupted":
                    assert retained["error_code"] == "REVISION_CONFLICT"
                else:
                    observed = next(
                        event
                        for event in retained["snapshot"]["events"]
                        if "OLD_SNAPSHOT_AFTER_IMPORT" in event["raw_line"]
                    )
                    assert observed["source"]["remote_path"] == old_path
                assert not any(
                    "SHOULD_NOT_RETARGET" in event["raw_line"]
                    for event in retained["snapshot"]["events"]
                )
                assert not any(path.decode() == new_path for path, _flags in captured.opens)
                async with foundation.database.sessions() as session:
                    retained_row = await session.get(LiveSession, (project_id, identity))
                    assert retained_row.config_snapshot == original_snapshot
                    assert retained_row.config_revision == original_revision
                assert captured.commands == captured.mutations == []
            finally:
                await foundation.app.state.live.close()
