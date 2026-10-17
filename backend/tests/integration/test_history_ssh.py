"""Actual MariaDB HTTP collections through isolated direct/single-jump AsyncSSH.

Every endpoint is created on an ephemeral loopback port and exposes only copied
synthetic logs. No production target, existing account password or shell is used.
Capture IDs are intentionally new; equality uses source position and raw bytes.
"""

import asyncio
import copy
import hashlib
import json
import shutil
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path

import asyncssh
import pytest
from sqlalchemy import select
from test_history import CASES, EVENTS, FROM, TO, finished
from test_ssh_access import enable_vault

from inspector.persistence.models import HistorySource
from inspector.ssh_transport import Endpoint

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]
ROOT = Path(__file__).resolve().parents[3]


@dataclass
class EndpointState:
    connections: set = field(default_factory=set)
    opens: list = field(default_factory=list)
    reads: list = field(default_factory=list)
    commands: list = field(default_factory=list)
    mutations: list = field(default_factory=list)
    forwards: list = field(default_factory=list)
    forward_target: tuple[str, int] | None = None
    read_hook: Callable | None = None


class SyntheticSSH(asyncssh.SSHServer):
    def __init__(self, state):
        self.state = state

    def connection_made(self, connection):
        self.connection = connection
        self.state.connections.add(connection)

    def connection_lost(self, exc):
        self.state.connections.discard(self.connection)

    def begin_auth(self, username):
        return True

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return username == "fixture-history-reader" and password == "synthetic-history-password"

    def connection_requested(self, host, port, orig_host, orig_port):
        self.state.forwards.append((host, port))
        return (host, port) == self.state.forward_target


class SyntheticReadOnlySFTP(asyncssh.SFTPServer):
    def __init__(self, channel, root, state):
        super().__init__(channel, chroot=str(root))
        self.state = state

    def open(self, path, pflags, attrs):
        self.state.opens.append((path, pflags))
        if pflags != asyncssh.FXF_READ:
            self._deny("open-write")
        return super().open(path, pflags, attrs)

    async def read(self, file_obj, offset, size):
        self.state.reads.append((offset, size))
        if self.state.read_hook:
            await self.state.read_hook(file_obj, offset, size)
        return super().read(file_obj, offset, size)

    def _deny(self, *args, **kwargs):
        self.state.mutations.append("mutation")
        raise asyncssh.SFTPPermissionDenied("The synthetic fixture is read-only.")

    open56 = _deny
    write = _deny
    setstat = _deny
    fsetstat = _deny
    lsetstat = _deny
    remove = _deny
    mkdir = _deny
    rmdir = _deny
    rename = _deny
    posix_rename = _deny
    symlink = _deny
    link = _deny
    lock = _deny
    unlock = _deny


@asynccontextmanager
async def endpoint(root, *, forward_target=None, sftp=True):
    state = EndpointState(forward_target=forward_target)
    key = asyncssh.generate_private_key("ssh-ed25519")

    async def reject_exec(process):
        state.commands.append(process.command)
        process.exit(126)

    server = await asyncssh.listen(
        "127.0.0.1",
        0,
        server_factory=lambda: SyntheticSSH(state),
        server_host_keys=[key],
        process_factory=reject_exec,
        sftp_factory=(lambda channel: SyntheticReadOnlySFTP(channel, root, state))
        if sftp
        else None,
        allow_scp=False,
        config=[],
    )
    connection = Endpoint(
        "127.0.0.1",
        server.get_port(),
        "fixture-history-reader",
        "synthetic-history-password",
        key.export_public_key().decode().strip(),
    )
    try:
        yield connection, state
    finally:
        server.close()
        await server.wait_closed()
        connections = tuple(state.connections)
        for active in connections:
            active.abort()
        await asyncio.gather(*(active.wait_closed() for active in connections))


def enable_remote(foundation, tmp_path, **limits):
    access = enable_vault(foundation, tmp_path)
    config = replace(
        access.config,
        ssh_allow_loopback=True,
        local_history_demo=False,
        cache_dir=str(tmp_path / "remote-cache"),
        history_limits={**access.config.history_limits, **limits},
    )
    access.config = config
    foundation.app.state.config = config
    foundation.app.state.history.config = config
    foundation.app.state.history.remote.config = config


def copy_logs(tmp_path):
    root = tmp_path / "synthetic-target"
    shutil.copytree(ROOT / "fixtures/logs", root / "var/log/inspector-demo")
    return root


async def configure(
    admin, project, target, jump=None, *, approve_sources=True, source_overrides=None
):
    document = json.loads((ROOT / "examples/project.example.json").read_text("utf-8"))
    document["project"].update(id=project, revision=1)
    for server in document["servers"]:
        server["connection_id"] = "c-ingest"
    if source_overrides:
        for process in document["processes"]:
            process["log_source"].update(source_overrides)
    document["connections"] = [
        {
            "id": "c-ingest",
            "name": "Isolated synthetic target",
            "host": target.host,
            "port": target.port,
            "username": target.username,
            "credential_ref": "synthetic-target",
            "jump_connection_id": "c-jump" if jump else None,
            "allowed_log_roots": ["/var/log/inspector-demo"],
        }
    ]
    if jump:
        document["connections"].append(
            {
                "id": "c-jump",
                "name": "Isolated synthetic jump",
                "host": jump.host,
                "port": jump.port,
                "username": jump.username,
                "credential_ref": "synthetic-jump",
                "jump_connection_id": None,
                "allowed_log_roots": [],
            }
        )
    response = await admin.put(
        f"/api/v1/projects/{project}/topology", json={"expected_revision": 1, "config": document}
    )
    assert response.status_code == 200, response.text
    # Verify each observed key against the independently generated endpoint key.
    # Jump trust must be ready before inspecting the target through that route.
    for identity, entry in ([("c-jump", jump)] if jump else []) + [("c-ingest", target)]:
        base = f"/api/v1/projects/{project}/connections/{identity}"
        password = await admin.put(
            base + "/password",
            json={
                "expected_config_revision": 2,
                "expected_credential_revision": 0,
                "password": entry.password,
            },
        )
        assert password.status_code == 200, password.text
        inspection = await admin.post(
            base + "/host-key/inspect", json={"expected_config_revision": 2}
        )
        assert inspection.status_code == 200, inspection.text
        independent = asyncssh.import_public_key(entry.host_key).get_fingerprint()
        assert inspection.json()["fingerprint"] == independent
        approved = await admin.post(
            base + "/host-key/approve",
            json={
                "expected_config_revision": 2,
                "expected_trust_revision": 0,
                "inspection_token": inspection.json()["inspection_token"],
                "verified": True,
            },
        )
        assert approved.status_code == 200, approved.text
    source_base = f"/api/v1/projects/{project}/connections/c-ingest/source-access"
    status = await admin.get(source_base)
    assert status.status_code == 200 and not status.json()["approval"]["approved"]
    if approve_sources:
        approved = await admin.post(
            source_base + "/approve",
            json={"expected_config_revision": 2, "expected_approval_revision": 0, "verified": True},
        )
        assert approved.status_code == 200 and approved.json()["approval"]["approved"]


async def scope(client, project, processes=None):
    workspace = await client.post(f"/api/v1/projects/{project}/workspaces", json={})
    assert workspace.status_code == 201, workspace.text
    return {
        "workspace_id": workspace.json()["workspace_id"],
        "process_ids": processes or CASES[0]["request"]["process_ids"],
        "from": FROM,
        "to": TO,
        "transport": "ssh",
    }


async def start(client, project, payload):
    response = await client.post(f"/api/v1/projects/{project}/collections", json=payload)
    assert response.status_code == 202, response.text
    return response.json()


def position(event):
    source = event["source"]
    return (
        event["process_id"],
        source["remote_path"],
        source["archive_member"],
        source["member_ordinal"],
        source["byte_start"],
        source["byte_end"],
    )


def normalized(event):
    result = copy.deepcopy(event)
    for key in ("project_id", "event_id", "received_at"):
        result.pop(key)
    result["source"].pop("source_revision_id")
    return result


@pytest.mark.parametrize("via_jump", [False, True], ids=["direct", "single-jump"])
async def test_real_ssh_history_matches_every_golden_query_and_source_position(
    foundation, tmp_path, via_jump
):
    enable_remote(foundation, tmp_path)
    root = copy_logs(tmp_path)
    async with endpoint(root) as (target, target_state):
        async with endpoint(root, forward_target=(target.host, target.port), sftp=False) as (
            jump,
            jump_state,
        ):
            async with foundation.client(foundation.database.administrator) as admin:
                await configure(admin, foundation.project_a, target, jump if via_jump else None)
                await configure(
                    admin,
                    foundation.project_b,
                    target,
                    jump if via_jump else None,
                    approve_sources=False,
                )
            async with foundation.client(foundation.alice) as inspector:
                base = f"/api/v1/projects/{foundation.project_a}"
                payload = await scope(inspector, foundation.project_a)
                other_payload = await scope(inspector, foundation.project_b)
                blocked = await inspector.post(
                    f"/api/v1/projects/{foundation.project_b}/collections/plan", json=other_payload
                )
                assert blocked.status_code == 409, blocked.text
                assert blocked.json()["error"]["code"] == "SOURCE_NOT_APPROVED"
                planned = await inspector.post(base + "/collections/plan", json=payload)
                assert planned.status_code == 200, planned.text
                plan = planned.json()
                assert not plan["demo_mode"] and plan["source_count"] == 21
                assert {source["kind"] for source in plan["sources"]} == {"plain", "zip", "tar.gz"}
                assert plan["estimated_bytes"] == sum(
                    (root / source["remote_path"].lstrip("/")).stat().st_size
                    for source in plan["sources"]
                )
                created = await start(inspector, foundation.project_a, payload)
                job = await finished(inspector, foundation.project_a, created["job_id"])
                assert job["status"] == "completed", job
                assert not job["demo_mode"]
                assert job["event_count"] == 38 and job["parse_issue_count"] == 1
                assert job["coverage_status"] == "complete_for_scanned_candidates"
                assert all(
                    source["status"] == "completed" and source["checksum"]
                    for source in job["coverage"]
                )
                assert job["downloaded_bytes"] == plan["estimated_bytes"]
                investigation = base + f"/investigations/{created['investigation_id']}"
                expected_events = {event["event_id"]: event for event in EVENTS}
                for case in CASES:
                    response = await inspector.post(investigation + "/query", json=case["request"])
                    assert response.status_code == 200, (case["id"], response.text)
                    result = response.json()
                    expected = [
                        expected_events[identity] for identity in case["expected_event_ids"]
                    ]
                    assert result["matched_count"] == len(expected), case["id"]
                    assert [position(event) for event in result["items"]] == [
                        position(event) for event in expected
                    ], case["id"]
                    assert [normalized(event) for event in result["items"]] == [
                        normalized(event) for event in expected
                    ], case["id"]
                query = {**CASES[0]["request"], "limit": 2}

                async def pages():
                    result, cursor, identities = [], None, []
                    while True:
                        response = await inspector.post(
                            investigation + "/query", json={**query, "cursor": cursor}
                        )
                        assert response.status_code == 200, response.text
                        page = response.json()
                        result.extend(page["items"])
                        identities.extend(event["event_id"] for event in page["items"])
                        cursor = page["next_cursor"]
                        if not cursor:
                            return result, identities

                first, first_ids = await pages()
                repeated, repeated_ids = await pages()
                assert first == repeated and first_ids == repeated_ids
                assert len(set(first_ids)) == len(CASES[0]["expected_event_ids"])
                assert [position(event) for event in first] == [
                    position(expected_events[identity])
                    for identity in CASES[0]["expected_event_ids"]
                ]
                all_query = {
                    **query,
                    "from": FROM,
                    "to": TO,
                    "filter": {"include": [], "exclude": [], "case_sensitive": True},
                    "limit": 200,
                }
                diagnostic = await inspector.post(
                    investigation + "/query", json={**all_query, "lane": "diagnostic"}
                )
                assert diagnostic.status_code == 200, diagnostic.text
                unknown = diagnostic.json()["items"]
                assert len(unknown) == 1 and unknown[0]["timestamp_us"] is None
                assert unknown[0]["timestamp_utc"] is None
                oracle = next(event for event in EVENTS if event["timestamp_us"] is None)
                assert normalized(unknown[0]) == normalized(oracle)
                second_scope = await scope(inspector, foundation.project_a)
                second = await start(inspector, foundation.project_a, second_scope)
                assert second_scope["workspace_id"] != payload["workspace_id"]
                assert second["investigation_id"] != created["investigation_id"]
                assert (await finished(inspector, foundation.project_a, second["job_id"]))[
                    "status"
                ] == "completed"
                other_query = await inspector.post(
                    base + f"/investigations/{second['investigation_id']}/query",
                    json={**query, "filter": {"include": ["no-synthetic-match"]}},
                )
                assert other_query.status_code == 200 and other_query.json()["matched_count"] == 0
                assert (await pages())[1] == first_ids
            assert target_state.opens and target_state.reads
            assert all(flags == asyncssh.FXF_READ for _, flags in target_state.opens)
            assert not target_state.commands and not target_state.mutations
            assert not jump_state.commands and not jump_state.mutations
            assert bool(jump_state.forwards) == via_jump


@pytest.mark.parametrize("change", ["cancel", "revoke"])
async def test_remote_collection_stops_during_actual_sftp_read(foundation, tmp_path, change):
    enable_remote(foundation, tmp_path)
    root = copy_logs(tmp_path)
    blocked, release = asyncio.Event(), asyncio.Event()
    async with endpoint(root) as (target, state):
        async with foundation.client(foundation.database.administrator) as admin:
            await configure(admin, foundation.project_a, target)
            async with foundation.client(foundation.alice) as inspector:
                payload = await scope(inspector, foundation.project_a, ["p-ingest-a"])
                created = await start(inspector, foundation.project_a, payload)

                async def slow_read(*args):
                    blocked.set()
                    await release.wait()

                state.read_hook = slow_read
                try:
                    await asyncio.wait_for(blocked.wait(), timeout=5)
                    if change == "cancel":
                        changed = await inspector.post(
                            f"/api/v1/projects/{foundation.project_a}/jobs/{created['job_id']}/cancel",
                            json={},
                        )
                    else:
                        changed = await admin.post(
                            f"/api/v1/projects/{foundation.project_a}/connections/c-ingest/source-access/revoke",
                            json={"expected_config_revision": 2, "expected_approval_revision": 1},
                        )
                    assert changed.status_code == 200, changed.text
                    started = time.monotonic()
                    job = await asyncio.wait_for(
                        finished(inspector, foundation.project_a, created["job_id"]), timeout=2
                    )
                    assert time.monotonic() - started < 2
                    assert job["status"] in {"cancelled", "failed", "partial"}, job
                    assert not release.is_set()
                    assert (
                        "CANCELLED" in job["errors"]
                        if change == "cancel"
                        else "SOURCE_NOT_APPROVED" in job["errors"]
                    )
                    assert not state.commands and not state.mutations
                finally:
                    release.set()
                    state.read_hook = None


async def test_missing_active_source_warning_survives_collection_and_reopen(foundation, tmp_path):
    enable_remote(foundation, tmp_path)
    root = copy_logs(tmp_path)
    active_path = "/var/log/inspector-demo/ingest/app.log"
    (root / active_path.lstrip("/")).unlink()
    async with endpoint(root) as (target, state):
        async with foundation.client(foundation.database.administrator) as admin:
            await configure(admin, foundation.project_a, target)
        base = f"/api/v1/projects/{foundation.project_a}"
        async with foundation.client(foundation.alice) as inspector:
            payload = await scope(inspector, foundation.project_a, ["p-ingest-a"])
            response = await inspector.post(base + "/collections/plan", json=payload)
            assert response.status_code == 200, response.text
            plan = response.json()
            assert "ACTIVE_SOURCE_UNAVAILABLE" in plan["warnings"]
            assert all(source["remote_path"] != active_path for source in plan["sources"])
            assert {source["kind"] for source in plan["sources"]} == {"plain", "zip", "tar.gz"}
            created = await start(inspector, foundation.project_a, payload)
            job = await finished(inspector, foundation.project_a, created["job_id"])
            assert job["status"] == "partial", job
            assert "ACTIVE_SOURCE_UNAVAILABLE" in job["errors"]
            assert job["coverage_status"] == "partial"
            assert job["scanned_sources"] == job["source_count"] == plan["source_count"]
            assert all(source["status"] == "completed" for source in job["coverage"])
            investigation = base + f"/investigations/{created['investigation_id']}"
        # A fresh account login reopens only retained MariaDB/cache state. The
        # missing active file cannot disappear from the persisted coverage notice.
        async with foundation.client(foundation.alice) as reopened:
            retained = await reopened.get(investigation)
            assert retained.status_code == 200, retained.text
            assert retained.json()["status"] == "partial"
            assert "ACTIVE_SOURCE_UNAVAILABLE" in retained.json()["errors"]
            query = await reopened.post(
                investigation + "/query",
                json={
                    "process_ids": ["p-ingest-a"],
                    "from": FROM,
                    "to": TO,
                    "filter": {"include": [], "exclude": [], "case_sensitive": True},
                    "limit": 200,
                },
            )
            assert query.status_code == 200, query.text
            result = query.json()
            assert result["partial"] is True
            expected = [
                event
                for event in EVENTS
                if event["process_id"] == "p-ingest-a"
                and event["source"]["remote_path"] != active_path
                and event["timestamp_utc"] is not None
                and FROM <= event["timestamp_utc"] < TO
            ]
            expected.sort(key=lambda event: (event["timestamp_us"], position(event)))
            assert result["matched_count"] == len(expected) > 0
            assert [normalized(event) for event in result["items"]] == [
                normalized(event) for event in expected
            ]
        assert state.reads and not state.commands and not state.mutations


async def test_active_appends_during_preview_planning_and_copy_preserve_frozen_captures(
    foundation, tmp_path
):
    enable_remote(foundation, tmp_path)
    root = copy_logs(tmp_path)
    active_path = root / "var/log/inspector-demo/ingest/app.log"
    # More than one SFTP body block makes this exercise growth while copying,
    # independently of the small bounded probes used to plan/recheck a source.
    lines = [
        f"2026-10-16T12:00:00.{index:06d}Z initial-{index:03d} {'x' * 800}\n".encode()
        for index in range(96)
    ]
    initial = b"".join(lines)
    active_path.write_bytes(initial)
    appended = {
        phase: f"2026-10-16T12:00:00.{96 + index:06d}Z append-{phase}\n".encode()
        for index, phase in enumerate(("preview", "between", "planning", "copy"))
    }
    phase = "preview"
    observed = []

    def append(label):
        with active_path.open("ab") as stream:
            assert stream.write(appended[label]) == len(appended[label])
        observed.append(label)

    async def append_during_read(file_obj, offset, size):
        nonlocal phase
        if phase in {"preview", "planning"} and size <= 4096:
            append(phase)
            phase = "idle" if phase == "preview" else "copy"
        elif phase == "copy" and size > 4096:
            append("copy")
            phase = "idle"

    async with endpoint(root) as (target, state):
        async with foundation.client(foundation.database.administrator) as admin:
            await configure(
                admin,
                foundation.project_a,
                target,
                source_overrides={"rotated_patterns": [], "archives": []},
            )
        async with foundation.client(foundation.alice) as inspector:
            base = f"/api/v1/projects/{foundation.project_a}"
            payload = await scope(inspector, foundation.project_a, ["p-ingest-a"])
            state.read_hook = append_during_read
            preview = await inspector.post(base + "/collections/plan", json=payload)
            assert preview.status_code == 200, preview.text
            assert preview.json()["source_count"] == 1
            assert preview.json()["estimated_bytes"] == len(initial)
            assert observed == ["preview"]
            # Creation makes its own bounded plan. It must accept a larger
            # active file than the earlier preview without treating it as stale.
            append("between")
            frozen = initial + appended["preview"] + appended["between"]
            phase = "planning"
            created = await start(inspector, foundation.project_a, payload)
            job = await finished(inspector, foundation.project_a, created["job_id"])
            state.read_hook = None
            assert observed == ["preview", "between", "planning", "copy"]
            assert active_path.read_bytes() == frozen + appended["planning"] + appended["copy"]

            async def assert_capture(created, job, expected):
                assert job["status"] == "completed", job
                assert job["coverage_status"] == "complete_for_scanned_candidates"
                assert job["source_count"] == job["scanned_sources"] == 1
                assert job["downloaded_bytes"] == len(expected)
                assert job["event_count"] == len(expected.splitlines())
                assert job["parse_issue_count"] == 0
                assert "SOURCE_CHANGED" not in job["errors"]
                async with foundation.database.sessions() as session:
                    source = (
                        await session.scalars(
                            select(HistorySource).where(
                                HistorySource.project_id == foundation.project_a,
                                HistorySource.job_id == created["job_id"],
                            )
                        )
                    ).one()
                cached = foundation.app.state.history.cache_path(
                    foundation.project_a, created["job_id"], source.cache_name
                )
                assert cached.read_bytes() == expected
                assert source.downloaded_bytes == len(expected)
                assert source.checksum == hashlib.sha256(expected).hexdigest()
                assert job["coverage"][0]["bytes"] == len(expected)
                assert job["coverage"][0]["checksum"] == source.checksum
                query = await inspector.post(
                    base + f"/investigations/{created['investigation_id']}/query",
                    json={
                        "process_ids": ["p-ingest-a"],
                        "from": FROM,
                        "to": TO,
                        "filter": {"include": [], "exclude": [], "case_sensitive": True},
                        "limit": 200,
                    },
                )
                assert query.status_code == 200, query.text
                result = query.json()
                assert result["matched_count"] == job["event_count"]
                expected_lines = expected.splitlines(keepends=True)
                assert [event["raw_line"] for event in result["items"]] == [
                    line.decode().removesuffix("\n") for line in expected_lines
                ]
                offset = 0
                for event, line in zip(result["items"], expected_lines, strict=True):
                    assert event["source"]["byte_start"] == offset
                    offset += len(line)
                    assert event["source"]["byte_end"] == offset
                assert result["next_cursor"] is None

            await assert_capture(created, job, frozen)
            # New entries belong to the next collection. They must not be lost
            # or injected into the already immutable investigation above.
            later_bytes = active_path.read_bytes()
            later = await start(inspector, foundation.project_a, payload)
            later_job = await finished(inspector, foundation.project_a, later["job_id"])
            await assert_capture(later, later_job, later_bytes)
            await assert_capture(created, job, frozen)
        assert all(flags == asyncssh.FXF_READ for _, flags in state.opens)
        assert not state.commands and not state.mutations


async def test_remote_captured_bytes_and_checksums_survive_immediate_parser_budget_failure(
    foundation, tmp_path
):
    enable_remote(foundation, tmp_path, max_expanded_bytes_per_collection=1)
    root = copy_logs(tmp_path)
    async with endpoint(root) as (target, state):
        async with foundation.client(foundation.database.administrator) as admin:
            # Two configured plain files guarantee the first parser consumes
            # real bytes before exhausting expansion; later files must not copy.
            await configure(admin, foundation.project_a, target, source_overrides={"archives": []})
        async with foundation.client(foundation.alice) as inspector:
            payload = await scope(inspector, foundation.project_a, ["p-ingest-a"])
            created = await start(inspector, foundation.project_a, payload)
            job = await finished(inspector, foundation.project_a, created["job_id"])
            assert job["status"] == "partial", job
            assert job["source_count"] == job["scanned_sources"] == 2
            assert "EXPANDED_BYTES_LIMIT" in job["errors"]
            assert "COLLECTION_BUDGET" in job["errors"]
            assert job["event_count"] == 0
            async with foundation.database.sessions() as session:
                sources = (
                    await session.scalars(
                        select(HistorySource).where(
                            HistorySource.project_id == foundation.project_a,
                            HistorySource.job_id == created["job_id"],
                        )
                    )
                ).all()
            manager = foundation.app.state.history
            paths = {
                source.id: manager.cache_path(
                    foundation.project_a, created["job_id"], source.cache_name
                )
                for source in sources
            }
            captures = [source for source in sources if paths[source.id].is_file()]
            assert len(captures) == 1
            captured = captures[0]
            content = paths[captured.id].read_bytes()
            assert captured.downloaded_bytes == len(content) > 1
            assert captured.checksum == hashlib.sha256(content).hexdigest()
            assert captured.error_code == "EXPANDED_BYTES_LIMIT"
            assert job["downloaded_bytes"] == sum(source.downloaded_bytes for source in sources)
            assert job["downloaded_bytes"] == sum(
                path.stat().st_size
                for path in paths[captured.id].parent.rglob("*")
                if path.is_file()
            )
            for source in sources:
                if source.id != captured.id:
                    assert source.downloaded_bytes == 0
                    assert source.checksum is None
                    assert source.error_code == "COLLECTION_BUDGET"
                    assert not paths[source.id].exists()
            reported = {source["source_revision_id"]: source for source in job["coverage"]}
            assert reported[captured.id]["bytes"] == len(content)
            assert reported[captured.id]["checksum"] == hashlib.sha256(content).hexdigest()
            assert not list(paths[captured.id].parent.glob("*.part"))
        assert all(flags == asyncssh.FXF_READ for _, flags in state.opens)
        assert not state.commands and not state.mutations
