"""Stage 01 persisted-demo backfill on a real, explicitly disposable MariaDB.

This exercises startup data reconciliation after the schema migration. It does
not downgrade a populated schema or claim to test an Alembic 0002-only database.
"""

import copy
import hashlib
import json
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from inspector import services
from inspector.domain import ProjectContext
from inspector.persistence.models import (
    ConnectionProfile,
    DemoSnapshot,
    EntityIdentity,
    Flow,
    ParserProfile,
    Process,
    Project,
    ProjectRevision,
    Server,
    SharedView,
    Subsystem,
    TopologySnapshot,
    TopologyState,
    User,
    ViewFlow,
    ViewNode,
)
from inspector.topology import initialize_legacy_documents

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


async def _account_digest(session):
    # A failed assertion may show these digests, never password verifiers.
    users = (await session.scalars(select(User).order_by(User.id))).all()
    payload = [
        {
            key: getattr(user, key)
            for key in (
                "id",
                "username_key",
                "display_name",
                "password_hash",
                "role",
                "enabled",
                "auth_version",
                "must_change_password",
            )
        }
        for user in users
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


async def _project_counts(session, project_id):
    return {
        model.__tablename__: await session.scalar(
            select(func.count()).select_from(model).where(model.project_id == project_id)
        )
        for model in (
            EntityIdentity,
            Subsystem,
            ConnectionProfile,
            Server,
            ParserProfile,
            Process,
            Flow,
            SharedView,
            ViewNode,
            ViewFlow,
            TopologySnapshot,
        )
    }


async def test_startup_backfills_verified_legacy_demo_without_resetting_scope_or_accounts(
    foundation,
):
    sessions = foundation.database.sessions
    actor = foundation.database.administrator.principal
    payload = {
        "subsystems": [
            {
                "id": "legacy-subsystem",
                "name": "Legacy intake",
                "description": "Preserved subsystem documentation.",
                "servers": [
                    {
                        "id": "legacy-server",
                        "name": "legacy-host-01",
                        "description": "Preserved server documentation.",
                        "processes": [
                            {
                                "id": f"legacy-process-{index}",
                                "name": f"Legacy instance {index}",
                                "description": f"## Instance {index}\nPreserved process documentation.",
                                "log_path": f"/var/log/demo/instance-{index}.log",
                            }
                            for index in (1, 2)
                        ],
                    }
                ],
            }
        ]
    }
    project_ids = []
    expected_metadata = {}
    async with sessions.begin() as session:
        accounts_before = await _account_digest(session)
        sentinel = await session.get(TopologyState, foundation.project_b)
        sentinel_config = copy.deepcopy(sentinel.config)
        for label in ("A", "B"):
            # Restrict all deletions below to this test's newly created empty
            # derived topology rows; retain every Project/ProjectRevision/user.
            project = await services.create_project(
                session,
                actor,
                f"Legacy demo {label}",
                f"Initial synthetic {label}",
                project_id=f"legacy-upgrade-{uuid4()}",
            )
            project = await services.rename_project(
                session,
                actor,
                project.id,
                f"Renamed legacy demo {label}",
                f"Preserved project documentation {label}.",
                expected_revision=1,
            )
            project_ids.append(project.id)
            expected_metadata[project.id] = (project.name, project.description, project.revision)
            state = await session.get(TopologyState, project.id)
            assert state.config["subsystems"] == [] and state.config["processes"] == []
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(EntityIdentity)
                    .where(EntityIdentity.project_id == project.id)
                )
                == 0
            )
            await session.execute(
                delete(TopologySnapshot).where(TopologySnapshot.project_id == project.id)
            )
            await session.execute(
                delete(TopologyState).where(TopologyState.project_id == project.id)
            )
            session.add(DemoSnapshot(project_id=project.id, payload=copy.deepcopy(payload)))

    async with sessions.begin() as session:
        await initialize_legacy_documents(session)

    async with sessions() as session:
        assert await _account_digest(session) == accounts_before
        sentinel = await session.get(TopologyState, foundation.project_b)
        assert sentinel.config == sentinel_config
        first_counts = {}
        for project_id in project_ids:
            project = await services.project_in_context(
                session, ProjectContext(project_id, actor.user_id)
            )
            name, description, revision = expected_metadata[project_id]
            assert (project.name, project.description, project.revision) == (
                name,
                description,
                revision,
            )
            assert revision == 2
            state = await session.get(TopologyState, project_id)
            assert state.config["project"] == {
                "id": project_id,
                "name": name,
                "description": description,
                "revision": revision,
                "display_timezone": "UTC",
            }
            assert state.undo_stack == [] and state.redo_stack == []
            assert (
                state.config["subsystems"][0]["description"]
                == payload["subsystems"][0]["description"]
            )
            assert (
                state.config["servers"][0]["description"]
                == payload["subsystems"][0]["servers"][0]["description"]
            )
            for index in (1, 2):
                process = await session.get(Process, (project_id, f"legacy-process-{index}"))
                assert process.server_id == "legacy-server"
                assert (
                    process.payload["description"]
                    == payload["subsystems"][0]["servers"][0]["processes"][index - 1]["description"]
                )
                assert (
                    process.payload["log_source"]["active_path"]
                    == f"/var/log/demo/instance-{index}.log"
                )
                assert process.parser_id == "parser-demo"
            server = await session.get(Server, (project_id, "legacy-server"))
            assert server.subsystem_id == "legacy-subsystem"
            assert server.connection_id == "connection-legacy-server"
            connection = await session.get(ConnectionProfile, (project_id, server.connection_id))
            assert connection.payload["credential_ref"] == "unresolved-legacy-server"
            assert connection.payload["allowed_log_roots"] == ["/var/log/demo"]
            assert set(connection.payload) == {
                "id",
                "name",
                "host",
                "port",
                "username",
                "credential_ref",
                "jump_connection_id",
                "allowed_log_roots",
            }
            assert connection.jump_connection_id is None
            flow = await session.get(Flow, (project_id, "flow-demo-0"))
            assert (flow.source_process_id, flow.target_process_id) == (
                "legacy-process-1",
                "legacy-process-2",
            )
            nodes = (
                await session.scalars(select(ViewNode).where(ViewNode.project_id == project_id))
            ).all()
            assert {node.element_id for node in nodes} == {
                "legacy-subsystem",
                "legacy-server",
                "legacy-process-1",
                "legacy-process-2",
            }
            assert all(node.view_id == "view-overview" for node in nodes)
            retained_demo = await session.get(DemoSnapshot, project_id)
            assert retained_demo.payload == payload
            snapshots = (
                await session.scalars(
                    select(TopologySnapshot).where(TopologySnapshot.project_id == project_id)
                )
            ).all()
            assert len(snapshots) == 1 and snapshots[0].revision == revision
            assert snapshots[0].config == state.config
            revisions = (
                await session.scalars(
                    select(ProjectRevision)
                    .where(ProjectRevision.project_id == project_id)
                    .order_by(ProjectRevision.revision)
                )
            ).all()
            assert [row.revision for row in revisions] == [1, 2]
            assert revisions[0].description.startswith("Initial synthetic")
            assert revisions[1].description == description
            first_counts[project_id] = await _project_counts(session, project_id)
            assert first_counts[project_id] == {
                "entity_identities": 8,
                "subsystems": 1,
                "connection_profiles": 1,
                "servers": 1,
                "parser_profiles": 1,
                "processes": 2,
                "flows": 1,
                "shared_views": 1,
                "view_nodes": 4,
                "view_flows": 1,
                "topology_snapshots": 1,
            }
            assert await session.get(Project, project_id) is not None

    # Startup reconciliation is idempotent and never advances semantic revisions.
    async with sessions.begin() as session:
        await initialize_legacy_documents(session)
    async with sessions() as session:
        assert await _account_digest(session) == accounts_before
        for project_id in project_ids:
            assert await _project_counts(session, project_id) == first_counts[project_id]
            project = await session.get(Project, project_id)
            assert project.revision == expected_metadata[project_id][2]
