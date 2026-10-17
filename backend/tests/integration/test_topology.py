"""Actual MariaDB topology transactions; no SQLite or remote hosts."""

import asyncio
import copy
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from inspector import auth, topology
from inspector.persistence.models import (
    ConfigPreview,
    EntityIdentity,
    EntityNameSnapshot,
    Flow,
    Process,
    Server,
    TopologySnapshot,
    TopologyState,
    ViewFlow,
    ViewNode,
)

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]
ROOT = Path(__file__).resolve().parents[3]


def config_for(project_id, revision=1):
    value = json.loads((ROOT / "examples/project.example.json").read_text(encoding="utf-8"))
    value["project"].update(id=project_id, name="Synthetic topology", revision=revision)
    return value


async def seed(client, project_id):
    value = config_for(project_id)
    result = await client.put(
        f"/api/v1/projects/{project_id}/topology", json={"expected_revision": 1, "config": value}
    )
    assert result.status_code == 200, result.text
    return result.json()


async def test_topology_crud_revisions_names_layout_and_search_are_scoped(foundation):
    admin = foundation.database.administrator
    async with foundation.client(admin) as client:
        current = await seed(client, foundation.project_a)
        await seed(client, foundation.project_b)
        edited = copy.deepcopy(current["config"])
        edited["processes"][0]["name"] = "Straße renamed process"
        edited["processes"][0]["description"] = "Shared **safe Markdown** documentation."
        edited["views"][0]["nodes"][0]["collapsed"] = True
        edited["views"][0]["nodes"][0]["x"] = 88
        result = await client.put(
            f"/api/v1/projects/{foundation.project_a}/topology",
            json={"expected_revision": 2, "config": edited},
        )
        assert result.status_code == 200, result.text
        assert result.json()["revision"] == 3
        assert result.json()["config"]["flows"] == current["config"]["flows"]
        assert result.json()["config"]["views"][0]["nodes"][0]["x"] == 88
        stale = await client.put(
            f"/api/v1/projects/{foundation.project_a}/topology",
            json={"expected_revision": 2, "config": edited},
        )
        assert stale.status_code == 409
        found = await client.post(
            f"/api/v1/projects/{foundation.project_a}/search", json={"q": "STRASSE"}
        )
        assert found.status_code == 200
        assert found.json()["results"] == [
            {
                "kind": "process",
                "id": "p-ingest-a",
                "name": "Straße renamed process",
                "view_id": "v-overview",
            }
        ]
        other = await client.post(
            f"/api/v1/projects/{foundation.project_b}/search", json={"q": "STRASSE"}
        )
        assert other.json()["results"] == []
        assert (await client.get(f"/api/v1/projects/{foundation.project_b}/topology")).json()[
            "revision"
        ] == 2
    async with foundation.database.sessions() as session:
        original = await session.get(TopologySnapshot, (foundation.project_a, 2))
        assert original.config["processes"][0]["name"] == "ingest-instance-a"
        history = (
            await session.scalars(
                select(EntityNameSnapshot)
                .where(
                    EntityNameSnapshot.project_id == foundation.project_a,
                    EntityNameSnapshot.id == "p-ingest-a",
                )
                .order_by(EntityNameSnapshot.revision)
            )
        ).all()
        assert [item.name for item in history] == ["ingest-instance-a", "Straße renamed process"]


async def test_inspector_safe_projection_and_direct_forbidden_mutations(foundation):
    async with foundation.client(foundation.database.administrator) as admin:
        current = await seed(admin, foundation.project_a)
    path = f"/api/v1/projects/{foundation.project_a}"
    async with foundation.client(foundation.alice) as inspector:
        result = await inspector.get(path + "/topology")
        assert result.status_code == 200
        value = result.json()
        assert not value["editable"] and not value["can_undo"]
        assert {"connections", "parsers", "settings"}.isdisjoint(value["config"])
        assert "connection_id" not in value["config"]["servers"][0]
        assert "log_source" not in value["config"]["processes"][0]
        for secret in ("logreader", "credential-demo-jump", "192.0.2.10"):
            assert secret not in result.text
        assert (await inspector.post(path + "/search", json={"q": "ingest"})).status_code == 200
        for response in (
            await inspector.put(
                path + "/topology", json={"expected_revision": 2, "config": current["config"]}
            ),
            await inspector.post(path + "/topology/undo", json={"expected_revision": 2}),
            await inspector.post(path + "/topology/redo", json={"expected_revision": 2}),
            await inspector.post(
                path + "/topology/delete-preview", json={"kind": "process", "id": "p-ingest-a"}
            ),
            await inspector.post(
                path + "/config/preview",
                json={
                    "expected_revision": 2,
                    "format": "json",
                    "content": json.dumps(current["config"]),
                },
            ),
            await inspector.post(
                path + "/config/commit", json={"expected_revision": 2, "preview_id": "guessed"}
            ),
            await inspector.get(path + "/config/export"),
            await inspector.get(path + "/config"),
        ):
            assert response.status_code == 403, response.text
    async with foundation.database.sessions() as session:
        assert (await session.get(TopologyState, foundation.project_a)).config == current["config"]


async def test_explicit_reparent_invalid_parents_and_cross_project_scope(foundation):
    path = f"/api/v1/projects/{foundation.project_a}"
    async with foundation.client(foundation.database.administrator) as client:
        current = await seed(client, foundation.project_a)
        edited = copy.deepcopy(current["config"])
        edited["servers"][0]["subsystem_id"] = "missing-parent"
        invalid = await client.put(
            path + "/topology", json={"expected_revision": 2, "config": edited, "reparent": True}
        )
        assert invalid.status_code == 422
        edited["servers"][0]["subsystem_id"] = "s-core"
        refused = await client.put(
            path + "/topology", json={"expected_revision": 2, "config": edited}
        )
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "REPARENT_CONFIRMATION_REQUIRED"
        moved = await client.put(
            path + "/topology", json={"expected_revision": 2, "config": edited, "reparent": True}
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["config"]["servers"][0]["id"] == current["config"]["servers"][0]["id"]
        foreign = copy.deepcopy(moved.json()["config"])
        foreign["project"]["id"] = foundation.project_b
        rejected = await client.put(
            path + "/topology", json={"expected_revision": 3, "config": foreign}
        )
        assert rejected.status_code == 422


def remove_impact(config, impact):
    value = copy.deepcopy(config)
    removed = {item["id"] for item in impact["entities"]}
    for collection in topology.COLLECTIONS:
        value[collection] = [item for item in value[collection] if item["id"] not in removed]
    for view in value["views"]:
        view["nodes"] = [node for node in view["nodes"] if node["element_id"] not in removed]
        view["flow_ids"] = [
            identifier for identifier in view["flow_ids"] if identifier not in removed
        ]
    return value


async def test_delete_impact_confirmation_tombstones_and_transactional_undo_redo(foundation):
    path = f"/api/v1/projects/{foundation.project_a}"
    async with foundation.client(foundation.database.administrator) as client:
        current = await seed(client, foundation.project_a)
        preview = await client.post(
            path + "/topology/delete-preview", json={"kind": "subsystem", "id": "s-core"}
        )
        assert preview.status_code == 200
        impact = preview.json()
        assert {item["id"] for item in impact["entities"]} >= {
            "s-core",
            "h-core-a",
            "p-parser-a",
            "p-router-a",
            "f-ingest-parser",
        }
        assert impact["views"] == ["v-overview"] and impact["active_sessions"] == []
        edited = remove_impact(current["config"], impact)
        refused = await client.put(
            path + "/topology", json={"expected_revision": 2, "config": edited}
        )
        assert refused.status_code == 409
        deleted = await client.put(
            path + "/topology",
            json={"expected_revision": 2, "config": edited, "confirmed_deletions": True},
        )
        assert deleted.status_code == 200, deleted.text
        restore = copy.deepcopy(current["config"])
        restore["project"]["revision"] = 3
        reused = await client.put(
            path + "/topology", json={"expected_revision": 3, "config": restore}
        )
        assert reused.status_code == 422 and reused.json()["error"]["code"] == "IMMUTABLE_ID"
        undone = await client.post(path + "/topology/undo", json={"expected_revision": 3})
        assert undone.status_code == 200 and undone.json()["revision"] == 4
        assert undone.json()["config"]["flows"] == current["config"]["flows"]
        redone = await client.post(path + "/topology/redo", json={"expected_revision": 4})
        assert redone.status_code == 200 and redone.json()["revision"] == 5
        assert redone.json()["config"]["processes"] == edited["processes"]
    async with foundation.database.sessions() as session:
        identity = await session.get(EntityIdentity, (foundation.project_a, "p-parser-a"))
        assert identity.deleted and identity.name == "parser-instance-a"


async def test_yaml_export_roundtrip_preview_scope_expiry_revision_and_no_secret_import(foundation):
    path = f"/api/v1/projects/{foundation.project_a}"
    async with foundation.client(foundation.database.administrator) as client:
        current = await seed(client, foundation.project_a)
        exported = await client.get(path + "/config/export?format=yaml")
        assert exported.status_code == 200
        preview = await client.post(
            path + "/config/preview",
            json={"expected_revision": 2, "format": "yaml", "content": exported.json()["content"]},
        )
        assert preview.status_code == 200, preview.text
        preview_id = preview.json()["preview_id"]
        wrong_project = await client.post(
            f"/api/v1/projects/{foundation.project_b}/config/commit",
            json={"preview_id": preview_id, "expected_revision": 1},
        )
        assert wrong_project.status_code == 404
        commit = await client.post(
            path + "/config/commit", json={"preview_id": preview_id, "expected_revision": 2}
        )
        assert commit.status_code == 200
        restored = commit.json()["config"]
        restored["project"]["revision"] = 2
        assert restored == current["config"]
        consumed = await client.post(
            path + "/config/commit", json={"preview_id": preview_id, "expected_revision": 3}
        )
        assert consumed.status_code == 404
        stale_export = await client.post(
            path + "/config/preview",
            json={"expected_revision": 3, "format": "yaml", "content": exported.json()["content"]},
        )
        assert stale_export.status_code == 409
        foreign = config_for("foreign-source-project", 77)
        remap = await client.post(
            path + "/config/preview",
            json={"expected_revision": 3, "format": "json", "content": json.dumps(foreign)},
        )
        assert remap.status_code == 200
        remap_id = remap.json()["preview_id"]
        unconfirmed = await client.post(
            path + "/config/commit", json={"preview_id": remap_id, "expected_revision": 3}
        )
        assert unconfirmed.status_code == 409
        confirmed = await client.post(
            path + "/config/commit",
            json={"preview_id": remap_id, "expected_revision": 3, "confirm_project_remap": True},
        )
        assert (
            confirmed.status_code == 200 and confirmed.json()["project_id"] == foundation.project_a
        )
        foreign["connections"][0]["password"] = "must-never-be-reflected"
        secret = await client.post(
            path + "/config/preview",
            json={"expected_revision": 4, "format": "json", "content": json.dumps(foreign)},
        )
        assert secret.status_code == 422 and "must-never-be-reflected" not in secret.text
        foreign["connections"][0].pop("password")
        foreign["connections"][0]["enabled"] = True
        approval = await client.post(
            path + "/config/preview",
            json={"expected_revision": 4, "format": "json", "content": json.dumps(foreign)},
        )
        assert approval.status_code == 422
        foreign["connections"][0].pop("enabled")
        pending = await client.post(
            path + "/config/preview",
            json={"expected_revision": 4, "format": "json", "content": json.dumps(foreign)},
        )
        async with foundation.database.sessions.begin() as session:
            await session.execute(
                update(ConfigPreview)
                .where(
                    ConfigPreview.project_id == foundation.project_a,
                    ConfigPreview.id == pending.json()["preview_id"],
                )
                .values(expires_us=1)
            )
        expired = await client.post(
            path + "/config/commit",
            json={
                "preview_id": pending.json()["preview_id"],
                "expected_revision": 4,
                "confirm_project_remap": True,
            },
        )
        assert expired.status_code == 410


async def test_preview_owner_digest_and_independent_project_revisions(foundation):
    from uuid import uuid4

    async with foundation.database.sessions.begin() as session:
        username = f"admin-{uuid4()}"
        password = "Synthetic admin password 12345"
        user = await auth.create_user(
            session,
            foundation.database.administrator.principal,
            username,
            "Other administrator",
            password,
            role="administrator",
        )
        user_id = user.id
    async with foundation.client(foundation.database.administrator) as client:
        value = config_for(foundation.project_a)
        endpoint = f"/api/v1/projects/{foundation.project_a}/config"
        pending = await client.post(
            endpoint + "/preview",
            json={"expected_revision": 1, "format": "json", "content": json.dumps(value)},
        )
        assert pending.status_code == 200
        async with foundation.client() as other:
            token = (await other.get("/api/v1/auth/csrf")).json()["csrf_token"]
            login = await other.post(
                "/api/v1/auth/login",
                json={"username": username, "password": password},
                headers={"x-csrf-token": token},
            )
            other.headers["x-csrf-token"] = login.json()["csrf_token"]
            denied = await other.post(
                endpoint + "/commit",
                json={"expected_revision": 1, "preview_id": pending.json()["preview_id"]},
            )
            assert denied.status_code == 404
        changed_other = await client.patch(
            f"/api/v1/projects/{foundation.project_b}/metadata",
            json={"expected_revision": 1, "name": "Only B changed", "description": ""},
        )
        assert changed_other.status_code == 200
        accepted = await client.post(
            endpoint + "/commit",
            json={"expected_revision": 1, "preview_id": pending.json()["preview_id"]},
        )
        assert accepted.status_code == 200
        value["project"]["revision"] = 2
        tampered = await client.post(
            endpoint + "/preview",
            json={"expected_revision": 2, "format": "json", "content": json.dumps(value)},
        )
        async with foundation.database.sessions.begin() as session:
            await session.execute(
                update(ConfigPreview)
                .where(
                    ConfigPreview.project_id == foundation.project_a,
                    ConfigPreview.id == tampered.json()["preview_id"],
                )
                .values(digest="0" * 64)
            )
        refused = await client.post(
            endpoint + "/commit",
            json={"expected_revision": 2, "preview_id": tampered.json()["preview_id"]},
        )
        assert refused.status_code == 409
    assert user_id


async def test_mariadb_rejects_cross_project_topology_foreign_keys_directly(foundation):
    async with foundation.client(foundation.database.administrator) as client:
        await seed(client, foundation.project_a)
        current = await seed(client, foundation.project_b)
        config = current["config"]
        config["subsystems"].append(
            dict(id="only-b-subsystem", name="Only B subsystem", description="", tags=[])
        )
        config["servers"].append(
            dict(
                id="only-b-server",
                name="Only B server",
                description="",
                tags=[],
                subsystem_id="only-b-subsystem",
                connection_id="c-ingest",
            )
        )
        process = copy.deepcopy(config["processes"][0])
        process.update(id="only-b-process", name="Only B process", server_id="only-b-server")
        config["processes"].append(process)
        config["flows"].append(
            dict(
                id="only-b-flow",
                name="Only B flow",
                source_process_id="only-b-process",
                target_process_id="p-ingest-a",
                protocol="",
                description="",
            )
        )
        saved = await client.put(
            f"/api/v1/projects/{foundation.project_b}/topology",
            json={"expected_revision": 2, "config": config},
        )
        assert saved.status_code == 200, saved.text
    statements = (
        update(Server)
        .where(Server.project_id == foundation.project_a, Server.id == "h-ingest-a")
        .values(subsystem_id="only-b-subsystem"),
        update(Process)
        .where(Process.project_id == foundation.project_a, Process.id == "p-ingest-a")
        .values(server_id="only-b-server"),
        update(Flow)
        .where(Flow.project_id == foundation.project_a, Flow.id == "f-ingest-parser")
        .values(target_process_id="only-b-process"),
        update(ViewNode)
        .where(ViewNode.project_id == foundation.project_a, ViewNode.element_id == "p-ingest-a")
        .values(element_id="only-b-process"),
        update(ViewFlow)
        .where(ViewFlow.project_id == foundation.project_a, ViewFlow.flow_id == "f-ingest-parser")
        .values(flow_id="only-b-flow"),
    )
    for statement in statements:
        async with foundation.database.sessions() as session:
            with pytest.raises(IntegrityError):
                await session.execute(statement)
                await session.commit()
            await session.rollback()
    async with foundation.database.sessions() as session:
        rows = (
            await session.scalars(
                select(Process).where(
                    Process.id == "p-ingest-a",
                    Process.project_id.in_([foundation.project_a, foundation.project_b]),
                )
            )
        ).all()
        assert {row.project_id for row in rows} == {foundation.project_a, foundation.project_b}
        assert all(
            row.name_key == hashlib.sha256(row.name.casefold().encode()).hexdigest() for row in rows
        )


async def test_archive_blocks_mutations_and_metadata_is_in_full_config(foundation):
    path = f"/api/v1/projects/{foundation.project_a}"
    async with foundation.client(foundation.database.administrator) as client:
        current = await seed(client, foundation.project_a)
        metadata = await client.patch(
            path + "/metadata",
            json={
                "expected_revision": 2,
                "name": "New catalogue name",
                "description": "Safe **description**",
            },
        )
        assert metadata.status_code == 200
        value = (await client.get(path + "/topology")).json()
        assert value["config"]["project"]["name"] == "New catalogue name"
        assert value["config"]["project"]["revision"] == 3
        unsafe = await client.patch(
            path + "/metadata",
            json={"expected_revision": 3, "name": "Unsafe", "description": "<script>bad</script>"},
        )
        assert unsafe.status_code == 422
        archived = await client.post(path + "/archive", json={"expected_revision": 3})
        assert archived.status_code == 200
        assert not (await client.get(path + "/topology")).json()["editable"]
        denied = await client.put(
            path + "/topology", json={"expected_revision": 4, "config": current["config"]}
        )
        assert denied.status_code == 409 and denied.json()["error"]["code"] == "PROJECT_ARCHIVED"
        restored = await client.post(path + "/restore", json={"expected_revision": 4})
        assert restored.status_code == 200
        assert (await client.get(path + "/topology")).json()["editable"]


async def test_full_history_is_bounded_but_names_and_tombstones_survive(foundation, monkeypatch):
    monkeypatch.setattr(topology, "HISTORY_LIMIT", 2)
    path = f"/api/v1/projects/{foundation.project_a}"
    async with foundation.client(foundation.database.administrator) as client:
        current = await seed(client, foundation.project_a)
        for index in range(5):
            config = current["config"]
            config["processes"][0]["name"] = f"Historical process name {index}"
            saved = await client.put(
                path + "/topology",
                json={"expected_revision": current["revision"], "config": config},
            )
            assert saved.status_code == 200, saved.text
            current = saved.json()
    async with foundation.database.sessions() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(TopologySnapshot)
            .where(TopologySnapshot.project_id == foundation.project_a)
        )
        assert count == 3
        history = (
            await session.scalars(
                select(EntityNameSnapshot)
                .where(
                    EntityNameSnapshot.project_id == foundation.project_a,
                    EntityNameSnapshot.id == "p-ingest-a",
                )
                .order_by(EntityNameSnapshot.revision)
            )
        ).all()
        assert len(history) == 6 and history[0].name == "ingest-instance-a"
        assert history[-1].name == "Historical process name 4"


async def test_concurrent_revision_checked_writes_have_one_winner_and_reject_integer_overflow(
    foundation,
):
    path = f"/api/v1/projects/{foundation.project_a}/topology"
    async with foundation.client(foundation.database.administrator) as client:
        current = await seed(client, foundation.project_a)
        configs = [copy.deepcopy(current["config"]) for _ in range(2)]
        for index, config in enumerate(configs):
            config["processes"][0]["name"] = f"Concurrent winner candidate {index}"
        responses = await asyncio.gather(
            *[
                client.put(path, json={"expected_revision": 2, "config": config})
                for config in configs
            ]
        )
        assert sorted(response.status_code for response in responses) == [200, 409]
        winner = next(response.json() for response in responses if response.status_code == 200)
        authoritative = (await client.get(path)).json()
        assert authoritative["revision"] == 3
        assert authoritative["config"] == winner["config"]
        overflow = await client.put(
            path, json={"expected_revision": 10**40, "config": winner["config"]}
        )
        assert overflow.status_code == 422
        assert (await client.get(path)).json()["revision"] == 3
