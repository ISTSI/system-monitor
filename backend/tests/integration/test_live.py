"""Live HTTP/WebSocket contracts with real MariaDB and isolated read-only SFTP.

The in-process WebSocket client uses the actual ASGI protocol and same cookie
as HTTP. It changes no production host and cannot bypass socket authentication.
Synthetic writes are direct local test-file writes, never an SSH command.
"""

import asyncio
import copy
import json
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import asyncssh
import pytest
from conftest import Account, Foundation
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from test_history_ssh import configure, copy_logs, enable_remote, endpoint

from inspector import auth, services
from inspector.app import create_app
from inspector.domain import Principal
from inspector.errors import DomainError
from inspector.persistence.models import User
from inspector.security import token_hash

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]
PROCESSES = ["p-ingest-a", "p-parser-a", "p-router-a", "p-delivery-a", "p-audit-a"]
EMPTY_FILTER = {"include": [], "exclude": [], "include_mode": "any", "case_sensitive": True}
EXAMPLE = Path(__file__).resolve().parents[3] / "examples/project.example.json"


def predicate(*include, exclude=(), case_sensitive=True):
    return {
        "include": list(include),
        "exclude": list(exclude),
        "include_mode": "all",
        "case_sensitive": case_sensitive,
    }


async def workspace(client, project):
    response = await client.post(f"/api/v1/projects/{project}/workspaces", json={})
    assert response.status_code == 201, response.text
    return response.json()["workspace_id"]


def base(project):
    return f"/api/v1/projects/{project}/live-sessions"


async def create_payload(client, project, work, processes=None, **overrides):
    configuration = await client.get(f"/api/v1/projects/{project}/topology")
    assert configuration.status_code == 200, configuration.text
    aliases = {
        "global_filter": "filter",
        "requested_rows": "seed_rows",
        "layout": "mode",
        "recording": "record",
    }
    return {
        "project_id": project,
        "project_revision": configuration.json()["revision"],
        "workspace_id": work,
        "process_ids": processes or PROCESSES[:1],
        "filter": EMPTY_FILTER,
        "per_process_filters": {},
        "seed_rows": 30,
        "seed_rows_by_process": {},
        "mode": "merged",
        "record": False,
        **{aliases.get(key, key): value for key, value in overrides.items()},
    }


async def start(client, project, work, processes=None, **overrides):
    payload = await create_payload(client, project, work, processes, **overrides)
    response = await client.post(base(project), json=payload)
    assert response.status_code in (201, 202), response.text
    return response.json()


async def status(client, project, identity):
    response = await client.get(f"{base(project)}/{identity}")
    assert response.status_code == 200, response.text
    return response.json()


async def until(client, project, identity, condition, deadline_seconds=6):
    async with asyncio.timeout(deadline_seconds):
        while True:
            current = await status(client, project, identity)
            if condition(current):
                return current
            await asyncio.sleep(0.04)


def rows(session):
    return session["snapshot"]["events"]


def append(path, data):
    with path.open("ab") as stream:
        stream.write(data)


def active_files(root):
    document = json.loads(EXAMPLE.read_text("utf-8"))
    return {
        process["id"]: root / process["log_source"]["active_path"].lstrip("/")
        for process in document["processes"]
    }


def live_config(foundation, tmp_path, **limits):
    enable_remote(foundation, tmp_path, **limits)
    # Stage 04's helper predates the live manager; keep its configured local
    # target/vault boundary consistent across both acquisition services.
    foundation.app.state.live.config = foundation.app.state.config


@asynccontextmanager
async def synthetic(foundation, tmp_path, *, both=False, **limits):
    live_config(foundation, tmp_path, **limits)
    root = copy_logs(tmp_path)
    async with asyncio.timeout(45):
        async with endpoint(root) as (target, captured):
            async with foundation.client(foundation.database.administrator) as admin:
                await configure(admin, foundation.project_a, target)
                if both:
                    await configure(admin, foundation.project_b, target)
            try:
                yield active_files(root), captured
            finally:
                # Close collectors before their synthetic server. Otherwise a
                # still-polling client can race endpoint teardown/reconnect.
                await asyncio.wait_for(foundation.app.state.live.close(), 4)


class Socket:
    """Minimal queued ASGI WebSocket transport; application frames remain real."""

    def __init__(self, app, client, project, session, origin=None, host=None, outgoing_limit=0):
        self.app, self.client, self.project, self.session = app, client, project, session
        self.incoming, self.outgoing = asyncio.Queue(), asyncio.Queue(maxsize=outgoing_limit)
        self.blocked = asyncio.Event()
        self.waiting_for_receive = asyncio.Event()
        self.origin = origin or str(client.base_url).rstrip("/")
        self.host = host.encode() if host is not None else client.base_url.netloc
        self.task = None

    async def __aenter__(self):
        cookie = "; ".join(f"{name}={value}" for name, value in self.client.cookies.items())
        path = f"{base(self.project)}/{self.session['session_id']}/stream"
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "scheme": "wss",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "server": ("localhost", 443),
            "client": ("127.0.0.1", 54545),
            "subprotocols": [],
            "headers": [
                (b"origin", self.origin.encode()),
                (b"cookie", cookie.encode()),
                (b"host", self.host),
            ],
            "state": {},
            "extensions": {"websocket.http.response": {}},
        }
        self.task = asyncio.create_task(self.app(scope, self.receive_incoming, self.send))
        await self.incoming.put({"type": "websocket.connect"})
        self.handshake = await self.receive_raw()
        return self

    async def send(self, message):
        if self.outgoing.full():
            self.blocked.set()
        await self.outgoing.put(message)

    async def receive_incoming(self):
        self.waiting_for_receive.set()
        try:
            return await self.incoming.get()
        finally:
            self.waiting_for_receive.clear()

    async def __aexit__(self, *args):
        await self.incoming.put({"type": "websocket.disconnect", "code": 1000})
        try:
            await asyncio.wait_for(self.task, 4)
        except TimeoutError:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    async def receive_raw(self, deadline_seconds=4):
        return await asyncio.wait_for(self.outgoing.get(), deadline_seconds)

    async def hello(self, **overrides):
        frame = {
            "protocol_version": 2,
            "type": "hello",
            "project_id": self.project,
            "workspace_id": self.session["workspace_id"],
            "session_id": self.session["session_id"],
            "filter_version": self.session["filter_version"],
            "payload": {
                "csrf_token": self.client.headers["x-csrf-token"],
                "lease_revision": self.session["lease_revision"],
                "last_seq": 0,
            },
            **overrides,
        }
        await self.incoming.put({"type": "websocket.receive", "text": json.dumps(frame)})

    async def frame(self, kind=None, deadline_seconds=4):
        async with asyncio.timeout(deadline_seconds):
            while True:
                message = await self.receive_raw(deadline_seconds)
                assert message["type"] == "websocket.send", message
                frame = json.loads(message.get("text") or message["bytes"])
                assert frame["protocol_version"] == 2
                assert frame["project_id"] == self.project
                assert frame["workspace_id"] == self.session["workspace_id"]
                assert frame["session_id"] == self.session["session_id"]
                assert isinstance(frame["seq"], int) and frame["sent_at"].endswith("Z")
                for event in frame["payload"].get("events", frame["payload"].get("items", [])):
                    assert event["project_id"] == self.project
                if kind is None or frame["type"] == kind:
                    return frame


async def test_real_sftp_refilter_partial_utf8_duplicate_positions_and_no_reconnect(
    foundation, tmp_path
):
    async with synthetic(foundation, tmp_path) as (paths, captured):
        path = paths[PROCESSES[0]]
        path.write_bytes(b"2026-10-16T12:00:00Z VISIBLE seed\n2026-10-16T12:00:01Z HIDDEN seed\n")
        async with foundation.client(foundation.alice) as client:
            work = await workspace(client, foundation.project_a)
            live = await start(
                client, foundation.project_a, work, global_filter=predicate("VISIBLE")
            )
            identity = live["session_id"]
            seeded = await until(
                client, foundation.project_a, identity, lambda state: len(rows(state)) == 1
            )
            connections = frozenset(captured.connections)
            assert "VISIBLE" in rows(seeded)[0]["raw_line"]
            duplicate = b"2026-10-16T12:00:02Z VISIBLE duplicate\n"
            append(path, duplicate + duplicate)
            result = await until(
                client, foundation.project_a, identity, lambda state: len(rows(state)) == 3
            )
            duplicates = [event for event in rows(result) if "duplicate" in event["raw_line"]]
            assert len(duplicates) == 2 and duplicates[0]["event_id"] != duplicates[1]["event_id"]
            partial_start = path.stat().st_size
            prefix = "2026-10-16T12:00:03Z VISIBLE Straße ".encode()
            append(path, prefix + b"\xe2")
            await asyncio.sleep(1.2)
            assert len(rows(await status(client, foundation.project_a, identity))) == 3
            append(path, b"\x82\xac complete\n")
            completed = await until(
                client,
                foundation.project_a,
                identity,
                lambda state: any("complete" in event["raw_line"] for event in rows(state)),
            )
            event = next(event for event in rows(completed) if "complete" in event["raw_line"])
            assert "Straße €" in event["raw_line"] and "\ufffd" not in event["raw_line"]
            assert event["source"]["byte_start"] == partial_start
            changed = await client.put(
                f"{base(foundation.project_a)}/{identity}/filters",
                json={
                    "workspace_id": work,
                    "lease_revision": live["lease_revision"],
                    "expected_filter_version": live["filter_version"],
                    "global_filter": predicate("HIDDEN"),
                    "per_process_filters": {},
                    "requested_rows": 30,
                    "layout": "merged",
                },
            )
            assert changed.status_code == 200, changed.text
            refiltered = changed.json()
            assert refiltered["filter_version"] == live["filter_version"] + 1
            assert len(rows(refiltered)) == 1 and "HIDDEN" in rows(refiltered)[0]["raw_line"]
            assert frozenset(captured.connections) == connections, "Refilter must reuse SSH."
            assert not captured.commands and not captured.mutations


async def test_two_systems_five_sources_atomic_limit_and_idle_source_latency(foundation, tmp_path):
    async with synthetic(foundation, tmp_path, both=True) as (paths, captured):
        async with foundation.client(foundation.alice) as client:
            wa, wb = (
                await workspace(client, foundation.project_a),
                await workspace(client, foundation.project_b),
            )
            first = await start(client, foundation.project_a, wa, PROCESSES)
            second = await start(client, foundation.project_b, wb, PROCESSES)
            for project, live in ((foundation.project_a, first), (foundation.project_b, second)):
                state = await until(
                    client,
                    project,
                    live["session_id"],
                    lambda item: len(item["snapshot"]["sources"]) == 5 and bool(rows(item)),
                )
                assert all(event["project_id"] == project for event in rows(state))
            rejected = await client.post(
                base(foundation.project_a),
                json=await create_payload(
                    client, foundation.project_a, await workspace(client, foundation.project_a)
                ),
            )
            assert (
                rejected.status_code == 429 and rejected.json()["error"]["code"] == "LIMIT_REACHED"
            )
            delays = []
            for index in range(8):
                token = f"SYNTHETIC-IDLE-LATENCY-{index}"
                started = time.monotonic()
                append(paths[PROCESSES[0]], f"2026-10-16T12:00:10.{index:06d}Z {token}\n".encode())
                await until(
                    client,
                    foundation.project_a,
                    first["session_id"],
                    lambda item, token=token: any(
                        token in event["raw_line"] for event in rows(item)
                    ),
                )
                delays.append(time.monotonic() - started)
            assert sorted(delays)[-1] <= 2, f"Observed p95 line-to-API delay: {max(delays):.3f}s"
            print(f"Five-source idle-peer line-to-API p95 (8 samples): {max(delays):.3f}s")
            for live, project in ((first, foundation.project_a), (second, foundation.project_b)):
                response = await client.post(
                    f"{base(project)}/{live['session_id']}/stop",
                    json={
                        "workspace_id": live["workspace_id"],
                        "lease_revision": live["lease_revision"],
                    },
                )
                assert response.status_code == 200, response.text
            assert not captured.commands and not captured.mutations


async def test_same_owner_workspaces_shared_capture_independent_filters_stop_and_resume(
    foundation, tmp_path
):
    async with synthetic(foundation, tmp_path) as (paths, captured):
        async with foundation.client(foundation.alice) as client:
            wa, wb = (
                await workspace(client, foundation.project_a),
                await workspace(client, foundation.project_a),
            )
            first = await start(client, foundation.project_a, wa)
            await until(
                client, foundation.project_a, first["session_id"], lambda item: bool(rows(item))
            )
            connections = frozenset(captured.connections)
            second = await start(
                client, foundation.project_a, wb, global_filter=predicate("NEVER-MATCH")
            )
            assert rows(second) == [] and frozenset(captured.connections) == connections
            occupied = await client.post(
                f"{base(foundation.project_a)}/{first['session_id']}/attach",
                json={"workspace_id": wb, "expected_lease_revision": first["lease_revision"]},
            )
            assert (
                occupied.status_code == 409
                and occupied.json()["error"]["code"] == "WORKSPACE_IN_USE"
            )
            forged = await client.post(
                f"{base(foundation.project_a)}/{first['session_id']}/stop",
                json={"workspace_id": wb, "lease_revision": first["lease_revision"]},
            )
            assert forged.status_code == 404
            stopped = await client.post(
                f"{base(foundation.project_a)}/{second['session_id']}/stop",
                json={"workspace_id": wb, "lease_revision": second["lease_revision"]},
            )
            assert stopped.status_code == 200
            append(paths[PROCESSES[0]], b"2026-10-16T12:00:12Z SURVIVING-WORKSPACE\n")
            await until(
                client,
                foundation.project_a,
                first["session_id"],
                lambda item: any("SURVIVING-WORKSPACE" in row["raw_line"] for row in rows(item)),
            )
            detached = await client.post(
                f"/api/v1/projects/{foundation.project_a}/workspaces/{wa}/detach", json={}
            )
            assert detached.status_code == 200
            detached_state = await status(client, foundation.project_a, first["session_id"])
            resumed = await client.post(
                f"{base(foundation.project_a)}/{first['session_id']}/attach",
                json={
                    "workspace_id": wb,
                    "expected_lease_revision": detached_state["lease_revision"],
                },
            )
            assert resumed.status_code == 200, resumed.text
            assert resumed.json()["workspace_id"] == wb
            assert resumed.json()["lease_revision"] > first["lease_revision"]
            assert not captured.commands and not captured.mutations


async def test_websocket_scope_csrf_owner_and_silent_auth_revocation(foundation, tmp_path):
    async with synthetic(foundation, tmp_path):
        async with foundation.client(foundation.alice) as client:
            wa = await workspace(client, foundation.project_a)
            live = await start(client, foundation.project_a, wa)
            async with Socket(
                foundation.app, client, foundation.project_a, live, origin="https://hostile.invalid"
            ) as rejected:
                assert rejected.handshake["type"] in (
                    "websocket.close",
                    "websocket.http.response.start",
                )
            async with Socket(foundation.app, client, foundation.project_a, live) as invalid:
                assert invalid.handshake["type"] == "websocket.accept"
                await invalid.hello(project_id=foundation.project_b)
                assert (await invalid.receive_raw())["type"] == "websocket.close"
            async with Socket(
                foundation.app, client, foundation.project_a, live, host="hostile.invalid"
            ) as invalid:
                assert invalid.handshake["type"] in (
                    "websocket.close",
                    "websocket.http.response.start",
                )
            for invalid_fields in (
                {"protocol_version": 1},
                {
                    "payload": {
                        "csrf_token": "synthetic-invalid-proof",
                        "lease_revision": live["lease_revision"],
                    }
                },
            ):
                async with Socket(foundation.app, client, foundation.project_a, live) as invalid:
                    assert invalid.handshake["type"] == "websocket.accept"
                    await invalid.hello(**invalid_fields)
                    assert (await invalid.receive_raw())["type"] == "websocket.close"
            async with Socket(foundation.app, client, foundation.project_a, live) as invalid:
                assert invalid.handshake["type"] == "websocket.accept"
                await invalid.incoming.put(
                    {"type": "websocket.receive", "bytes": b"\x00synthetic-binary"}
                )
                assert (await invalid.receive_raw())["type"] == "websocket.close"
            assert (
                await client.get(f"{base(foundation.project_b)}/{live['session_id']}")
            ).status_code == 404
            async with foundation.client(foundation.bob) as other:
                async with Socket(foundation.app, other, foundation.project_a, live) as denied:
                    if denied.handshake["type"] == "websocket.accept":
                        await denied.hello()
                        assert (await denied.receive_raw())["type"] == "websocket.close"
                    else:
                        assert denied.handshake["type"] in (
                            "websocket.close",
                            "websocket.http.response.start",
                        )
                assert (
                    await other.get(f"{base(foundation.project_a)}/{live['session_id']}")
                ).status_code == 404
            async with foundation.database.sessions() as session:
                from inspector.persistence.models import Audit

                denials = list(
                    await session.scalars(
                        select(Audit).where(
                            Audit.action == "authorization.denied",
                            Audit.target_id == live["session_id"],
                        )
                    )
                )
                assert denials and any(
                    row.actor_user_id == foundation.alice.principal.user_id for row in denials
                )
                assert all(row.outcome == "denied" for row in denials)
            async with Socket(foundation.app, client, foundation.project_a, live) as socket:
                assert socket.handshake["type"] == "websocket.accept"
                await socket.hello()
                frame = await socket.frame()
                assert frame["type"] in {"snapshot", "resync_required", "status", "counters"}
                started = time.monotonic()
                async with foundation.database.sessions.begin() as session:
                    await session.execute(
                        update(User)
                        .where(User.id == foundation.alice.principal.user_id)
                        .values(auth_version=User.auth_version + 1)
                    )
                async with asyncio.timeout(2.5):
                    while True:
                        message = await socket.receive_raw()
                        if message["type"] == "websocket.close":
                            break
                assert time.monotonic() - started <= 2.5
                assert (
                    await client.get(f"{base(foundation.project_a)}/{live['session_id']}")
                ).status_code == 401


async def test_both_roles_private_content_and_administrator_stop_exception(foundation, tmp_path):
    async with synthetic(foundation, tmp_path):
        async with (
            foundation.client(foundation.alice) as inspector,
            foundation.client(foundation.database.administrator) as admin,
        ):
            owned = await start(
                inspector, foundation.project_a, await workspace(inspector, foundation.project_a)
            )
            admin_owned = await start(
                admin, foundation.project_a, await workspace(admin, foundation.project_a)
            )
            identity = owned["session_id"]
            assert (await admin.get(f"{base(foundation.project_a)}/{identity}")).status_code == 404
            denied = await admin.put(
                f"{base(foundation.project_a)}/{identity}/filters",
                json={
                    "workspace_id": owned["workspace_id"],
                    "lease_revision": owned["lease_revision"],
                    "expected_filter_version": 1,
                    "global_filter": predicate("read-denied"),
                    "per_process_filters": {},
                    "requested_rows": 30,
                    "layout": "merged",
                },
            )
            assert denied.status_code == 404
            assert (
                await inspector.get(f"{base(foundation.project_a)}/{admin_owned['session_id']}")
            ).status_code == 404
            stopped = await admin.post(
                f"{base(foundation.project_a)}/{identity}/stop",
                json={
                    "workspace_id": owned["workspace_id"],
                    "lease_revision": owned["lease_revision"],
                },
            )
            assert stopped.status_code == 200, stopped.text
            assert stopped.json().get("snapshot") is None, (
                "Administrative stop must not grant content."
            )
            async with foundation.database.sessions() as session:
                from inspector.persistence.models import Audit

                audits = list(
                    await session.scalars(select(Audit).where(Audit.target_id == identity))
                )
                assert audits, "Cross-owner stop must be audited."


async def test_live_scoped_database_foreign_keys(foundation, tmp_path):
    from inspector.persistence.models import LiveSession, LiveSubscription

    async with synthetic(foundation, tmp_path, both=True):
        async with foundation.client(foundation.alice) as client:
            live = await start(
                client, foundation.project_a, await workspace(client, foundation.project_a)
            )
            async with foundation.database.sessions() as session:
                stored = await session.get(LiveSession, (foundation.project_a, live["session_id"]))
                assert (
                    stored is not None
                    and stored.owner_user_id == foundation.alice.principal.user_id
                )
            async with foundation.database.sessions.begin() as session:
                with pytest.raises(IntegrityError):
                    async with session.begin_nested():
                        session.add(
                            LiveSubscription(
                                project_id=foundation.project_b,
                                session_id=live["session_id"],
                                owner_user_id=foundation.alice.principal.user_id,
                                process_id=PROCESSES[0],
                            )
                        )
                        await session.flush()


async def test_live_recording_preserves_unfiltered_event_ids_for_offline_query(
    foundation, tmp_path
):
    async with synthetic(foundation, tmp_path) as (paths, _captured):
        paths[PROCESSES[0]].write_bytes(
            b"2026-10-16T12:00:00Z VISIBLE\n2026-10-16T12:00:01Z HIDDEN\n"
        )
        async with foundation.client(foundation.alice) as client:
            work = await workspace(client, foundation.project_a)
            live = await start(
                client,
                foundation.project_a,
                work,
                global_filter=predicate("VISIBLE"),
                recording=True,
            )
            assert live["recording"] and live["investigation_id"]
            control = {"workspace_id": work, "lease_revision": live["lease_revision"]}
            stopped = await client.post(
                f"{base(foundation.project_a)}/{live['session_id']}/stop", json=control
            )
            assert stopped.status_code == 200, stopped.text
            query = await client.post(
                f"/api/v1/projects/{foundation.project_a}/investigations/{live['investigation_id']}/query",
                json={
                    "process_ids": PROCESSES[:1],
                    "from": "2026-10-16T12:00:00.000000Z",
                    "to": "2026-10-16T12:00:02.000000Z",
                    "filter": EMPTY_FILTER,
                    "per_process_filters": {},
                    "limit": 100,
                },
            )
            assert query.status_code == 200, query.text
            captured = query.json()["items"]
            assert len(captured) == 2 and any("HIDDEN" in event["raw_line"] for event in captured)
            assert {event["event_id"] for event in rows(live)} <= {
                event["event_id"] for event in captured
            }
            async with foundation.client(foundation.bob) as other:
                denied = await other.post(
                    f"/api/v1/projects/{foundation.project_a}/investigations/{live['investigation_id']}/query",
                    json={
                        "process_ids": PROCESSES[:1],
                        "from": "2026-10-16T12:00:00.000000Z",
                        "to": "2026-10-16T12:00:02.000000Z",
                    },
                )
                assert denied.status_code == 404
            deletion = await client.delete(
                f"/api/v1/projects/{foundation.project_a}/investigations/{live['investigation_id']}"
            )
            assert deletion.status_code == 200, deletion.text
            retained_monitor = await status(client, foundation.project_a, live["session_id"])
            assert retained_monitor["investigation_id"] is None
            assert retained_monitor["recording"] is False


async def test_cancelling_recording_job_stops_live_capture_without_losing_partial_data(
    foundation, tmp_path
):
    async with synthetic(foundation, tmp_path) as (paths, _captured):
        async with foundation.client(foundation.alice) as client:
            live = await start(
                client,
                foundation.project_a,
                await workspace(client, foundation.project_a),
                recording=True,
            )
            investigation = live["investigation_id"]
            cancelled = await client.post(
                f"/api/v1/projects/{foundation.project_a}/jobs/{investigation}/cancel", json={}
            )
            assert cancelled.status_code == 200, cancelled.text
            append(paths[PROCESSES[0]], b"2026-10-16T12:00:25Z AFTER-CANCEL\n")
            await until(
                client,
                foundation.project_a,
                live["session_id"],
                lambda item: item["status"] in {"stopped", "interrupted", "failed"},
            )
            job = await client.get(f"/api/v1/projects/{foundation.project_a}/jobs/{investigation}")
            assert job.status_code == 200
            assert job.json()["status"] == "cancelled"
            assert job.json()["event_count"] > 0


async def test_recording_save_during_blocked_shared_peer_commits_before_publication(
    foundation, tmp_path, monkeypatch
):
    from inspector.persistence.models import HistoryEvent, HistorySource

    async with synthetic(foundation, tmp_path) as (paths, _captured):
        path = paths[PROCESSES[0]]
        path.write_bytes(b"2026-10-16T12:00:00Z SEED\n")
        async with foundation.client(foundation.alice) as client:
            first = await start(
                client,
                foundation.project_a,
                await workspace(client, foundation.project_a),
                recording=True,
            )
            second = await start(
                client, foundation.project_a, await workspace(client, foundation.project_a)
            )
            engine = foundation.app.state.live.engine
            first_state = engine.sessions[first["session_id"]]
            second_state = engine.sessions[second["session_id"]]
            assert first_state.sources[0] is second_state.sources[0]
            assert first_state.recording_enabled and not second_state.recording_enabled
            blocked, release, committed, published = (asyncio.Event() for _ in range(4))
            token = "SAVE-WHILE-SHARED-PEER-BLOCKED Straße"
            original_bytes = f"2026-10-16T12:00:01Z {token}\r\n".encode()
            inflight, published_events = [], []
            first_callback, second_callback = first_state.on_events, second_state.on_events
            original_frame = engine._frame
            investigation = None

            async def blocking_recorder(identifier, events):
                matching = [event for event in events if token in event["raw_line"]]
                if matching:
                    inflight.extend(matching)
                    blocked.set()
                    await release.wait()
                await first_callback(identifier, events)

            async def committed_recorder(identifier, events):
                await second_callback(identifier, events)
                for event in events:
                    if token in event["raw_line"]:
                        # A separate real transaction must see the durable row
                        # before the engine may publish this source position.
                        async with foundation.database.sessions() as session:
                            row = await session.get(
                                HistoryEvent,
                                (foundation.project_a, investigation, event["event_id"]),
                            )
                            assert row is not None and row.raw_line == event["raw_line"]
                        committed.set()

            def checked_frame(state, kind, payload):
                matches = [
                    event for event in payload.get("events", []) if token in event["raw_line"]
                ]
                if state is second_state and kind == "events" and matches:
                    assert committed.is_set(), "Published before the activated recorder committed."
                    published_events.extend(matches)
                    published.set()
                return original_frame(state, kind, payload)

            first_state.on_events = blocking_recorder
            second_state.on_events = committed_recorder
            monkeypatch.setattr(engine, "_frame", checked_frame)
            try:
                append(path, original_bytes)
                await asyncio.wait_for(blocked.wait(), 3)
                assert not any(
                    token in event["raw_line"]
                    for event in engine.retained_events(second_state.session_id)
                )
                saved = await client.post(
                    f"{base(foundation.project_a)}/{second_state.session_id}/save",
                    json={
                        "workspace_id": second["workspace_id"],
                        "lease_revision": second["lease_revision"],
                    },
                )
                assert saved.status_code == 200, saved.text
                investigation = saved.json()["investigation_id"]
                assert second_state.recording_enabled
                async with foundation.database.sessions() as session:
                    assert (
                        await session.get(
                            HistoryEvent,
                            (foundation.project_a, investigation, inflight[0]["event_id"]),
                        )
                        is None
                    )
                release.set()
                await asyncio.wait_for(published.wait(), 4)
                assert committed.is_set()
                assert published_events[0]["event_id"] == inflight[0]["event_id"]
                stopped = await client.post(
                    f"{base(foundation.project_a)}/{second_state.session_id}/stop",
                    json={
                        "workspace_id": second["workspace_id"],
                        "lease_revision": second["lease_revision"],
                    },
                )
                assert stopped.status_code == 200, stopped.text
                query_base = (
                    f"/api/v1/projects/{foundation.project_a}/investigations/{investigation}"
                )
                query = await client.post(
                    query_base + "/query",
                    json={
                        "process_ids": PROCESSES[:1],
                        "from": "2026-10-16T12:00:00.000000Z",
                        "to": "2026-10-16T12:00:02.000000Z",
                        "filter": EMPTY_FILTER,
                        "per_process_filters": {},
                        "limit": 100,
                    },
                )
                assert query.status_code == 200, query.text
                recorded = next(
                    event for event in query.json()["items"] if token in event["raw_line"]
                )
                assert recorded["event_id"] == inflight[0]["event_id"]
                assert recorded["raw_line"] == original_bytes.decode().rstrip("\r\n")
                grant = await client.post(
                    query_base + f"/sources/{recorded['source']['source_revision_id']}/download",
                    json={},
                )
                assert (
                    grant.status_code == 409
                    and grant.json()["error"]["code"] == "SOURCE_INCOMPLETE"
                )
                async with foundation.database.sessions() as session:
                    source = await session.get(
                        HistorySource,
                        (
                            foundation.project_a,
                            investigation,
                            recorded["source"]["source_revision_id"],
                        ),
                    )
                    ranges = source.manifest["captured_ranges"]
                    cache = foundation.app.state.history.cache_path(
                        foundation.project_a, investigation, source.cache_name
                    )
                    captured_range = next(
                        item
                        for item in ranges
                        if item["byte_start"] <= recorded["source"]["byte_start"]
                        and item["byte_end"] >= recorded["source"]["byte_end"]
                    )
                cached = await asyncio.to_thread(cache.read_bytes)
                offset = (
                    captured_range["cache_start"]
                    + recorded["source"]["byte_start"]
                    - captured_range["byte_start"]
                )
                assert cached[offset : offset + len(original_bytes)] == original_bytes
            finally:
                release.set()


@pytest.mark.parametrize("outcome", ["cancelled_request", "failed_backfill"])
async def test_recording_save_settles_committed_activation_without_affecting_other_owner(
    foundation, tmp_path, monkeypatch, outcome
):
    from inspector.persistence.models import HistoryJob, LiveSession

    async with synthetic(foundation, tmp_path) as (paths, _captured):
        paths[PROCESSES[0]].write_bytes(b"2026-10-16T12:00:00Z SAVE-SETTLEMENT-SEED\n")
        async with (
            foundation.client(foundation.alice) as alice,
            foundation.client(foundation.bob) as bob,
        ):
            live = await start(
                alice, foundation.project_a, await workspace(alice, foundation.project_a)
            )
            other = await start(
                bob, foundation.project_a, await workspace(bob, foundation.project_a)
            )
            manager = foundation.app.state.live
            original = manager._record_events
            entered, release = asyncio.Event(), asyncio.Event()
            first_call = True

            async def delayed_backfill(identifier, events):
                nonlocal first_call
                if identifier == live["session_id"] and first_call:
                    first_call = False
                    entered.set()
                    await release.wait()
                    if outcome == "failed_backfill":
                        raise DomainError("CACHE_CHANGED", "Synthetic backfill failure.", 409)
                await original(identifier, events)

            monkeypatch.setattr(manager, "_record_events", delayed_backfill)
            saving = asyncio.create_task(
                alice.post(
                    f"{base(foundation.project_a)}/{live['session_id']}/save",
                    json={
                        "workspace_id": live["workspace_id"],
                        "lease_revision": live["lease_revision"],
                    },
                )
            )
            try:
                await asyncio.wait_for(entered.wait(), 3)
                async with foundation.database.sessions() as session:
                    committed_row = await session.get(
                        LiveSession, (foundation.project_a, live["session_id"])
                    )
                    investigation = committed_row.investigation_id
                    assert committed_row.recording and investigation
                    assert manager.engine.sessions[live["session_id"]].recording_enabled
                    job = await session.get(HistoryJob, (foundation.project_a, investigation))
                    assert job.status == "collecting" and job.event_count == 0
                if outcome == "cancelled_request":
                    saving.cancel()
                    await asyncio.sleep(0.05)
                release.set()
                result = (
                    await asyncio.wait_for(asyncio.gather(saving, return_exceptions=True), 4)
                )[0]
                if outcome == "cancelled_request":
                    assert isinstance(result, asyncio.CancelledError)
                    settled = await status(alice, foundation.project_a, live["session_id"])
                    assert settled["status"] == "following" and settled["recording"]
                    assert manager.engine.sessions[live["session_id"]].recording_enabled
                else:
                    assert (
                        result.status_code == 409
                        and result.json()["error"]["code"] == "CACHE_CHANGED"
                    )
                    settled = await until(
                        alice,
                        foundation.project_a,
                        live["session_id"],
                        lambda item: item["status"] == "failed",
                    )
                    assert settled["error_code"] == "CACHE_CHANGED"
                async with foundation.database.sessions() as session:
                    job = await session.get(HistoryJob, (foundation.project_a, investigation))
                    if outcome == "cancelled_request":
                        assert job.status == "collecting" and job.event_count == 1
                    else:
                        assert job.status == "partial" and "CACHE_CHANGED" in job.errors
                assert (await status(bob, foundation.project_a, other["session_id"]))[
                    "status"
                ] == "following"
                append(paths[PROCESSES[0]], b"2026-10-16T12:00:01Z OTHER-OWNER-SURVIVES-SAVE\n")
                await until(
                    bob,
                    foundation.project_a,
                    other["session_id"],
                    lambda item: any(
                        "OTHER-OWNER-SURVIVES-SAVE" in event["raw_line"] for event in rows(item)
                    ),
                )
            finally:
                release.set()
                if not saving.done():
                    saving.cancel()
                    await asyncio.gather(saving, return_exceptions=True)


async def test_lost_real_database_supervisor_stops_socket_and_never_restarts_ssh(
    foundation, tmp_path
):
    from inspector.database import _lock_name

    async with synthetic(foundation, tmp_path) as (_paths, captured):
        async with foundation.client(foundation.alice) as client:
            live = await start(
                client, foundation.project_a, await workspace(client, foundation.project_a)
            )
            async with Socket(foundation.app, client, foundation.project_a, live) as socket:
                assert socket.handshake["type"] == "websocket.accept"
                await socket.hello()
                await socket.frame()
                supervisor = foundation.app.state.supervisor
                name = _lock_name(supervisor.connection, "supervisor")
                assert (
                    await supervisor.connection.scalar(
                        text("SELECT RELEASE_LOCK(:name)"), {"name": name}
                    )
                    == 1
                )
                await supervisor.connection.commit()
                started = time.monotonic()
                async with asyncio.timeout(2):
                    while (await socket.receive_raw())["type"] != "websocket.close":
                        pass
                assert time.monotonic() - started < 2
                assert supervisor.failed
                opens = len(captured.opens)
                await asyncio.sleep(1)
                assert len(captured.opens) == opens
                assert not await supervisor.healthy()
                assert (await client.get("/api/v1/health/ready")).status_code == 503


async def test_detached_lease_expiry_releases_only_its_subscription(foundation, tmp_path):
    from inspector.persistence.models import LiveSession, LiveSubscription

    async with synthetic(foundation, tmp_path):
        async with foundation.client(foundation.alice) as client:
            first = await start(
                client, foundation.project_a, await workspace(client, foundation.project_a)
            )
            second = await start(
                client, foundation.project_a, await workspace(client, foundation.project_a)
            )
            async with foundation.database.sessions.begin() as session:
                await session.execute(
                    update(LiveSession)
                    .where(
                        LiveSession.project_id == foundation.project_a,
                        LiveSession.id == first["session_id"],
                    )
                    .values(detached_until_us=services.utc_now_us() - 1)
                )
            expired = await until(
                client,
                foundation.project_a,
                first["session_id"],
                lambda item: item["status"] == "stopped",
            )
            assert expired["error_code"] == "LEASE_EXPIRED"
            assert (await status(client, foundation.project_a, second["session_id"]))[
                "status"
            ] == "following"
            async with foundation.database.sessions() as session:
                subscriptions = list(
                    await session.scalars(
                        select(LiveSubscription.session_id).where(
                            LiveSubscription.project_id == foundation.project_a,
                            LiveSubscription.owner_user_id == foundation.alice.principal.user_id,
                        )
                    )
                )
                assert subscriptions == [second["session_id"]]


async def test_real_backend_restart_marks_live_interrupted_without_remote_reconnection(
    database, tmp_path
):
    from inspector.persistence.models import LiveSession, LiveSubscription

    async with database.sessions.begin() as session:
        identity = str(uuid4())
        password = "synthetic-restart-" + identity
        user = await auth.create_user(
            session,
            database.administrator.principal,
            "restart-" + identity,
            "Synthetic restart owner",
            password,
        )
        account = Account(
            "restart-" + identity, password, Principal(user.id, user.role, user.auth_version)
        )
        projects = [
            await services.create_project(
                session, database.administrator.principal, "Synthetic restart " + label, ""
            )
            for label in ("A", "B")
        ]
    config = replace(database.config, state_dir=str(tmp_path / "restart-state"))
    app = create_app(config)
    fixture = Foundation(database, config, app, account, account, projects[0].id, projects[1].id)
    root = copy_logs(tmp_path)
    async with endpoint(root) as (target, captured):
        async with app.router.lifespan_context(app):
            live_config(fixture, tmp_path)
            async with fixture.client(database.administrator) as admin:
                await configure(admin, fixture.project_a, target)
            async with fixture.client(account) as client:
                live = await start(
                    client, fixture.project_a, await workspace(client, fixture.project_a)
                )
                assert rows(live)
            restart_config = app.state.config
        assert not captured.connections
        opens = len(captured.opens)
        restarted = create_app(restart_config)
        fixture.app = restarted
        async with restarted.router.lifespan_context(restarted):
            async with fixture.client(account) as client:
                retained = await status(client, fixture.project_a, live["session_id"])
                assert (
                    retained["status"] == "interrupted"
                    and retained["error_code"] == "BACKEND_RESTART"
                )
                await workspace(client, fixture.project_a)
            await asyncio.sleep(0.8)
            assert len(captured.opens) == opens and not captured.connections
            assert not restarted.state.live.engine.sessions
            async with database.sessions() as session:
                row = await session.get(LiveSession, (fixture.project_a, live["session_id"]))
                assert row.status == "interrupted"
                assert not list(
                    await session.scalars(
                        select(LiveSubscription).where(
                            LiveSubscription.project_id == fixture.project_a
                        )
                    )
                )


async def test_attach_rejects_destination_workspace_capacity_without_moving_lease(
    foundation, tmp_path
):
    async with synthetic(foundation, tmp_path):
        async with foundation.client(foundation.alice) as client:
            old = await workspace(client, foundation.project_a)
            destination = await workspace(client, foundation.project_a)
            live = await start(client, foundation.project_a, old)
            occupied = await start(client, foundation.project_a, destination, PROCESSES)
            response = await client.post(
                f"/api/v1/projects/{foundation.project_a}/workspaces/{old}/detach", json={}
            )
            assert response.status_code == 200
            rejected = await client.post(
                f"{base(foundation.project_a)}/{live['session_id']}/attach",
                json={
                    "workspace_id": destination,
                    "expected_lease_revision": live["lease_revision"],
                },
            )
            assert (
                rejected.status_code == 429 and rejected.json()["error"]["code"] == "LIMIT_REACHED"
            )
            original = await status(client, foundation.project_a, live["session_id"])
            assert (
                original["workspace_id"] == old
                and original["lease_revision"] == live["lease_revision"]
            )
            assert (await status(client, foundation.project_a, occupied["session_id"]))[
                "status"
            ] == "following"


async def test_administrative_stop_racing_attach_leaves_no_subscription(foundation, tmp_path):
    from inspector.persistence.models import LiveSubscription

    async with synthetic(foundation, tmp_path):
        async with (
            foundation.client(foundation.alice) as owner,
            foundation.client(foundation.database.administrator) as admin,
        ):
            old, new = (
                await workspace(owner, foundation.project_a),
                await workspace(owner, foundation.project_a),
            )
            live = await start(owner, foundation.project_a, old)
            assert (
                await owner.post(
                    f"/api/v1/projects/{foundation.project_a}/workspaces/{old}/detach", json={}
                )
            ).status_code == 200
            attached, stopped = await asyncio.gather(
                owner.post(
                    f"{base(foundation.project_a)}/{live['session_id']}/attach",
                    json={"workspace_id": new, "expected_lease_revision": live["lease_revision"]},
                ),
                admin.post(
                    f"{base(foundation.project_a)}/{live['session_id']}/stop",
                    json={"workspace_id": old, "lease_revision": live["lease_revision"]},
                ),
            )
            assert stopped.status_code == 200 and "snapshot" not in stopped.json()
            assert attached.status_code in (200, 409)
            assert (await status(owner, foundation.project_a, live["session_id"]))[
                "status"
            ] == "stopped"
            async with foundation.database.sessions() as session:
                assert not list(
                    await session.scalars(
                        select(LiveSubscription).where(
                            LiveSubscription.project_id == foundation.project_a,
                            LiveSubscription.session_id == live["session_id"],
                        )
                    )
                )


async def test_canonical_create_contract_rejects_wrong_project_stale_revision_and_legacy_fields(
    foundation, tmp_path
):
    async with synthetic(foundation, tmp_path):
        async with foundation.client(foundation.alice) as client:
            work = await workspace(client, foundation.project_a)
            payload = await create_payload(client, foundation.project_a, work)
            for invalid, code in (
                ({"project_id": foundation.project_b}, 422),
                ({"project_revision": payload["project_revision"] - 1}, 409),
                ({"global_filter": EMPTY_FILTER}, 422),
            ):
                response = await client.post(
                    base(foundation.project_a), json={**payload, **invalid}
                )
                assert response.status_code == code, response.text


async def test_live_real_single_jump_sftp_preserves_host_trust_and_readonly_route(
    foundation, tmp_path
):
    live_config(foundation, tmp_path)
    root = copy_logs(tmp_path)
    paths = active_files(root)
    async with asyncio.timeout(30):
        async with endpoint(root) as (target, target_state):
            async with endpoint(root, forward_target=(target.host, target.port), sftp=False) as (
                jump,
                jump_state,
            ):
                try:
                    async with foundation.client(foundation.database.administrator) as admin:
                        await configure(admin, foundation.project_a, target, jump)
                    async with foundation.client(foundation.alice) as client:
                        live = await start(
                            client,
                            foundation.project_a,
                            await workspace(client, foundation.project_a),
                        )
                        assert rows(live)
                        append(paths[PROCESSES[0]], b"2026-10-16T12:00:40Z SYNTHETIC-JUMP-LIVE\n")
                        await until(
                            client,
                            foundation.project_a,
                            live["session_id"],
                            lambda item: any(
                                "SYNTHETIC-JUMP-LIVE" in event["raw_line"] for event in rows(item)
                            ),
                        )
                        assert jump_state.forwards and all(
                            route == (target.host, target.port) for route in jump_state.forwards
                        )
                        assert not jump_state.opens and target_state.reads
                        assert not target_state.commands and not jump_state.commands
                        assert not target_state.mutations and not jump_state.mutations
                finally:
                    await asyncio.wait_for(foundation.app.state.live.close(), 4)


async def test_personal_live_budget_rejects_one_owner_without_evicting_others(foundation, tmp_path):
    async with synthetic(
        foundation, tmp_path, max_live_processes_per_user=2, max_live_processes_global=10
    ) as (_paths, captured):
        async with (
            foundation.client(foundation.alice) as alice,
            foundation.client(foundation.bob) as bob,
        ):
            owned = await start(
                alice,
                foundation.project_a,
                await workspace(alice, foundation.project_a),
                PROCESSES[:2],
            )
            rejected = await alice.post(
                base(foundation.project_a),
                json=await create_payload(
                    alice, foundation.project_a, await workspace(alice, foundation.project_a)
                ),
            )
            assert (
                rejected.status_code == 429 and rejected.json()["error"]["code"] == "LIMIT_REACHED"
            )
            assert "user" in rejected.json()["error"]["message"]
            other = await start(
                bob, foundation.project_a, await workspace(bob, foundation.project_a)
            )
            assert other["status"] == "following"
            assert (await status(alice, foundation.project_a, owned["session_id"]))[
                "status"
            ] == "following"
            connections = frozenset(captured.connections)
            full = {
                "include": ["x" * 512] * 20,
                "exclude": ["y" * 512] * 20,
                "include_mode": "all",
                "case_sensitive": True,
            }
            control = {
                "workspace_id": owned["workspace_id"],
                "lease_revision": owned["lease_revision"],
                "expected_filter_version": owned["filter_version"],
                "global_filter": full,
                "per_process_filters": {},
                "requested_rows": 30,
                "layout": "merged",
            }
            assert len(json.dumps(control)) > 16_384
            changed = await alice.put(
                f"{base(foundation.project_a)}/{owned['session_id']}/filters", json=control
            )
            assert changed.status_code == 200, changed.text
            assert frozenset(captured.connections) == connections
            rejected_filter = await alice.put(
                f"{base(foundation.project_a)}/{owned['session_id']}/filters",
                json={
                    **control,
                    "expected_filter_version": changed.json()["filter_version"],
                    "global_filter": {**full, "include": ["x"] * 21},
                },
            )
            assert rejected_filter.status_code == 422


async def test_recording_load_older_commits_original_ranges_before_snapshot_without_deadlock(
    foundation, tmp_path
):
    async with synthetic(foundation, tmp_path) as (paths, _captured):
        path = paths[PROCESSES[0]]
        path.write_bytes(
            b"".join(
                f"2026-10-16T12:00:00.{index:06d}Z seq={index} {'x' * 1000}\n".encode()
                for index in range(200)
            )
        )
        async with foundation.client(foundation.alice) as client:
            work = await workspace(client, foundation.project_a)
            live = await start(client, foundation.project_a, work, requested_rows=1)
            assert 0 < len(rows(live)) < 200
            assert min(event["source"]["byte_start"] for event in rows(live)) > 0
            control = {"workspace_id": work, "lease_revision": live["lease_revision"]}
            saved = await client.post(
                f"{base(foundation.project_a)}/{live['session_id']}/save", json=control
            )
            assert saved.status_code == 200, saved.text
            async with asyncio.timeout(8):
                older = await client.post(
                    f"{base(foundation.project_a)}/{live['session_id']}/history",
                    json={**control, "requested_rows": 500},
                )
            assert older.status_code == 200, older.text
            assert older.json()["snapshot"]["counters"]["retained"] == 200
            assert len(rows(older.json())) > len(rows(live))
            if len(rows(older.json())) < 200:
                assert older.json()["snapshot"]["coverage"]["view_limit_reached"]
            investigation = saved.json()["investigation_id"]
            query_base = f"/api/v1/projects/{foundation.project_a}/investigations/{investigation}"
            interval = {"from": "2026-10-16T12:00:00.000000Z", "to": "2026-10-16T12:00:01.000000Z"}
            query = await client.post(
                query_base + "/query",
                json={
                    **interval,
                    "process_ids": PROCESSES[:1],
                    "filter": EMPTY_FILTER,
                    "per_process_filters": {},
                    "limit": 500,
                },
            )
            assert query.status_code == 200, query.text
            captured = query.json()["items"]
            assert len(captured) == 200
            assert {event["event_id"] for event in captured} >= {
                event["event_id"] for event in rows(older.json())
            }
            oldest = captured[0]
            assert oldest["source"]["byte_start"] == 0
            context = await client.post(
                query_base + f"/events/{oldest['event_id']}/context",
                json={**interval, "before": 0, "after": 0},
            )
            assert context.status_code == 200, context.text
            assert context.json()["items"][0]["event"]["raw_line"] == oldest["raw_line"]


async def test_websocket_queued_old_filter_ack_does_not_close_new_version_stream(
    foundation, tmp_path
):
    async with synthetic(foundation, tmp_path) as (paths, _captured):
        async with foundation.client(foundation.alice) as client:
            work = await workspace(client, foundation.project_a)
            live = await start(client, foundation.project_a, work)
            async with Socket(foundation.app, client, foundation.project_a, live) as socket:
                assert socket.handshake["type"] == "websocket.accept"
                await socket.hello()
                first = await socket.frame("snapshot")
                changed = await client.put(
                    f"{base(foundation.project_a)}/{live['session_id']}/filters",
                    json={
                        "workspace_id": work,
                        "lease_revision": live["lease_revision"],
                        "expected_filter_version": live["filter_version"],
                        "global_filter": EMPTY_FILTER,
                        "per_process_filters": {},
                        "requested_rows": 30,
                        "layout": "merged",
                    },
                )
                assert changed.status_code == 200 and changed.json()["filter_version"] == 2
                await socket.incoming.put(
                    {
                        "type": "websocket.receive",
                        "text": json.dumps(
                            {
                                "protocol_version": 2,
                                "type": "ack",
                                "project_id": foundation.project_a,
                                "workspace_id": work,
                                "session_id": live["session_id"],
                                "filter_version": 1,
                                "payload": {"last_seq": first["seq"]},
                            }
                        ),
                    }
                )
                replacement = await socket.frame("snapshot")
                assert replacement["filter_version"] == 2
                append(paths[PROCESSES[0]], b"2026-10-16T12:00:50Z AFTER-REFILTER-ACK\n")
                received = await socket.frame("events")
                assert received["filter_version"] == 2
                assert any(
                    "AFTER-REFILTER-ACK" in item["raw_line"]
                    for item in received["payload"]["items"]
                )


async def test_websocket_outbound_change_wakes_pending_receive_without_losing_ack(
    foundation, tmp_path
):
    async with synthetic(foundation, tmp_path) as (paths, _captured):
        async with foundation.client(foundation.alice) as client:
            work = await workspace(client, foundation.project_a)
            live = await start(client, foundation.project_a, work)
            async with Socket(foundation.app, client, foundation.project_a, live) as socket:
                assert socket.handshake["type"] == "websocket.accept"
                await socket.hello()
                await socket.frame("snapshot")
                # This observes the real ASGI receive callback. No inbound
                # message will wake it until after the HTTP reset is delivered.
                await asyncio.wait_for(socket.waiting_for_receive.wait(), 2)
                changed = await client.put(
                    f"{base(foundation.project_a)}/{live['session_id']}/filters",
                    json={
                        "workspace_id": work,
                        "lease_revision": live["lease_revision"],
                        "expected_filter_version": live["filter_version"],
                        "global_filter": EMPTY_FILTER,
                        "per_process_filters": {},
                        "requested_rows": 30,
                        "layout": "merged",
                    },
                )
                assert changed.status_code == 200 and changed.json()["filter_version"] == 2
                committed = time.monotonic()
                snapshot = await socket.frame("snapshot", deadline_seconds=0.2)
                assert snapshot["filter_version"] == 2
                assert time.monotonic() - committed < 0.2
                await socket.incoming.put(
                    {
                        "type": "websocket.receive",
                        "text": json.dumps(
                            {
                                "protocol_version": 2,
                                "type": "ack",
                                "project_id": foundation.project_a,
                                "workspace_id": work,
                                "session_id": live["session_id"],
                                "filter_version": 2,
                                "payload": {"last_seq": snapshot["seq"]},
                            }
                        ),
                    }
                )
                append(paths[PROCESSES[0]], b"2026-10-16T12:00:51Z AFTER-OUTBOUND-WAKE-ACK\n")
                async with asyncio.timeout(3):
                    while True:
                        received = await socket.frame("events")
                        if any(
                            "AFTER-OUTBOUND-WAKE-ACK" in item["raw_line"]
                            for item in received["payload"]["items"]
                        ):
                            break
                assert received["filter_version"] == 2


async def test_stalled_websocket_transport_closes_boundedly_without_stalling_other_monitor(
    foundation, tmp_path
):
    async with synthetic(foundation, tmp_path) as (paths, _captured):
        async with foundation.client(foundation.alice) as client:
            first = await start(
                client, foundation.project_a, await workspace(client, foundation.project_a)
            )
            second = await start(
                client, foundation.project_a, await workspace(client, foundation.project_a)
            )
            async with Socket(
                foundation.app, client, foundation.project_a, first, outgoing_limit=1
            ) as slow:
                assert slow.handshake["type"] == "websocket.accept"
                await slow.hello()
                await slow.frame("snapshot")
                async with Socket(foundation.app, client, foundation.project_a, second) as fast:
                    assert fast.handshake["type"] == "websocket.accept"
                    await fast.hello()
                    await fast.frame("snapshot")
                    append(paths[PROCESSES[0]], b"2026-10-16T12:01:00Z SLOW-TRANSPORT-SEED\n")
                    await asyncio.wait_for(slow.blocked.wait(), 4)
                    started = time.monotonic()
                    await asyncio.wait_for(asyncio.shield(slow.task), 1.6)
                    assert time.monotonic() - started < 1.6
                    assert slow.outgoing.qsize() == 1
                    append(paths[PROCESSES[0]], b"2026-10-16T12:01:01Z FAST-WORKSPACE-SURVIVES\n")
                    async with asyncio.timeout(4):
                        while True:
                            received = await fast.frame("events")
                            if any(
                                "FAST-WORKSPACE-SURVIVES" in item["raw_line"]
                                for item in received["payload"]["items"]
                            ):
                                break


async def test_fresh_live_guards_survive_control_plane_locks_then_revoke_on_commit(
    foundation, tmp_path
):
    from sqlalchemy import event

    from inspector.live import LiveControlInput
    from inspector.persistence.models import Project, SecurityState

    async with synthetic(foundation, tmp_path) as (paths, _captured):
        async with foundation.client(foundation.alice) as client:
            live = await start(
                client, foundation.project_a, await workspace(client, foundation.project_a)
            )
            manager = foundation.app.state.live
            current_task = asyncio.current_task()
            query_count = 0

            def count_current_query(*_args):
                nonlocal query_count
                if asyncio.current_task() is current_task:
                    query_count += 1

            database_engine = manager.sessions.kw["bind"].sync_engine
            event.listen(database_engine, "before_cursor_execute", count_current_query)
            try:
                async with manager.sessions.begin() as session:
                    actor, row = await manager._socket_row(
                        session,
                        client.cookies.get("__Host-si-session"),
                        foundation.project_a,
                        live["session_id"],
                        LiveControlInput(
                            workspace_id=live["workspace_id"], lease_revision=live["lease_revision"]
                        ),
                    )
                    assert actor.user_id == foundation.alice.principal.user_id
                    assert (row.project_id, row.id) == (foundation.project_a, live["session_id"])
                assert query_count == 1, (
                    "Each fresh protected socket read requires one joined query."
                )
            finally:
                event.remove(database_engine, "before_cursor_execute", count_current_query)
            async with Socket(foundation.app, client, foundation.project_a, live) as socket:
                assert socket.handshake["type"] == "websocket.accept"
                await socket.hello()
                await socket.frame("snapshot")
                async with foundation.database.sessions() as blocker:
                    await blocker.begin()
                    await blocker.get(SecurityState, 1, with_for_update=True)
                    user = await blocker.get(
                        User, foundation.alice.principal.user_id, with_for_update=True
                    )
                    await blocker.get(Project, foundation.project_a, with_for_update=True)
                    # Real historical/control transactions retain these same
                    # rows. Fresh read authorization must not request writer
                    # locks or mistake their contention for a database outage.
                    await asyncio.sleep(1.2)
                    assert not foundation.app.state.live.engine.sessions[live["session_id"]].stopped
                    started = time.monotonic()
                    append(paths[PROCESSES[0]], b"2026-10-16T12:02:00Z LIVE-UNDER-CONTROL-LOCKS\n")
                    async with asyncio.timeout(2):
                        while True:
                            received = await socket.frame("events")
                            if any(
                                "LIVE-UNDER-CONTROL-LOCKS" in item["raw_line"]
                                for item in received["payload"]["items"]
                            ):
                                break
                    assert time.monotonic() - started < 2
                    assert not foundation.app.state.live.failed_closed
                    user.auth_version += 1
                    state = foundation.app.state.live.engine.sessions[live["session_id"]]
                    state.changed.clear()
                    await blocker.commit()
                revoked = time.monotonic()
                async with asyncio.timeout(2):
                    while (await socket.receive_raw())["type"] != "websocket.close":
                        pass
                    while not state.stopped:
                        await state.changed.wait()
                        state.changed.clear()
                assert time.monotonic() - revoked < 2


async def configure_guard_routes(admin, project, target, jump):
    """Retain the example's direct and two single-jump source profiles."""
    document = json.loads(await asyncio.to_thread(EXAMPLE.read_text, "utf-8"))
    document["project"].update(id=project, revision=1)
    for connection in document["connections"]:
        entry = jump if connection["id"] == "c-jump" else target
        connection.update(host=entry.host, port=entry.port, username=entry.username)
    changed = await admin.put(
        f"/api/v1/projects/{project}/topology", json={"expected_revision": 1, "config": document}
    )
    assert changed.status_code == 200, changed.text
    for identity in ("c-jump", "c-ingest", "c-core", "c-delivery"):
        entry = jump if identity == "c-jump" else target
        connection = f"/api/v1/projects/{project}/connections/{identity}"
        saved = await admin.put(
            connection + "/password",
            json={
                "expected_config_revision": 2,
                "expected_credential_revision": 0,
                "password": entry.password,
            },
        )
        assert saved.status_code == 200, saved.text
        inspected = await admin.post(
            connection + "/host-key/inspect", json={"expected_config_revision": 2}
        )
        assert inspected.status_code == 200, inspected.text
        assert (
            inspected.json()["fingerprint"]
            == asyncssh.import_public_key(entry.host_key).get_fingerprint()
        )
        trusted = await admin.post(
            connection + "/host-key/approve",
            json={
                "expected_config_revision": 2,
                "expected_trust_revision": 0,
                "inspection_token": inspected.json()["inspection_token"],
                "verified": True,
            },
        )
        assert trusted.status_code == 200, trusted.text
        if identity != "c-jump":
            approved = await admin.post(
                connection + "/source-access/approve",
                json={
                    "expected_config_revision": 2,
                    "expected_approval_revision": 0,
                    "verified": True,
                },
            )
            assert approved.status_code == 200, approved.text


async def test_fresh_batch_guards_preserve_direct_jump_authorization_and_scope(
    foundation, tmp_path
):
    from sqlalchemy import event

    from inspector.persistence.models import (
        ApplicationSetting,
        Project,
        ProjectCredentialBinding,
        SourceAccessApproval,
        SSHCredential,
        SSHHostTrust,
        TopologyState,
    )

    live_config(foundation, tmp_path)
    root = copy_logs(tmp_path)
    manager = foundation.app.state.source_access
    identifiers = ["c-ingest", "c-core", "c-delivery"]
    async with asyncio.timeout(100):
        async with endpoint(root) as (target, target_state):
            async with endpoint(root, forward_target=(target.host, target.port), sftp=False) as (
                jump,
                jump_state,
            ):
                try:
                    async with foundation.client(foundation.database.administrator) as admin:
                        await configure_guard_routes(admin, foundation.project_a, target, jump)
                        await configure(admin, foundation.project_b, target)
                    async with (
                        foundation.client(foundation.alice) as alice,
                        foundation.client(foundation.bob) as bob,
                    ):
                        principal = foundation.alice.principal
                        login = token_hash(alice.cookies.get("__Host-si-session"))
                        current_task = asyncio.current_task()
                        query_count = 0

                        def count_current_query(*_args):
                            nonlocal query_count
                            if asyncio.current_task() is current_task:
                                query_count += 1

                        database_engine = manager.sessions.kw["bind"].sync_engine
                        event.listen(database_engine, "before_cursor_execute", count_current_query)
                        try:
                            batch = await manager.prepare_many(
                                principal, foundation.project_a, identifiers, 2, login
                            )
                            assert query_count == 3, (
                                "Fresh direct and jump authorization uses three bounded queries."
                            )
                        finally:
                            event.remove(
                                database_engine, "before_cursor_execute", count_current_query
                            )
                        for identifier in identifiers:
                            assert batch[identifier] == await manager.prepare(
                                principal, foundation.project_a, identifier, 2, login, lock=False
                            )
                        assert batch["c-ingest"].jump is None
                        assert batch["c-core"].jump.port == jump.port
                        assert batch["c-delivery"].jump.port == jump.port
                        with pytest.raises(DomainError):
                            await manager.prepare_many(
                                principal,
                                foundation.project_a,
                                identifiers,
                                2,
                                token_hash(bob.cookies.get("__Host-si-session")),
                            )
                        with pytest.raises(DomainError) as foreign_profile:
                            await manager.prepare_many(
                                principal, foundation.project_b, ["c-core"], 2, login
                            )
                        assert foreign_profile.value.code == "NOT_FOUND"
                        other = await start(
                            bob, foundation.project_b, await workspace(bob, foundation.project_b)
                        )
                        work = await workspace(alice, foundation.project_a)
                        async with foundation.database.sessions() as session:
                            target_binding = await session.get(
                                ProjectCredentialBinding,
                                (foundation.project_a, "credential-demo-ingest"),
                            )
                            jump_binding = await session.get(
                                ProjectCredentialBinding,
                                (foundation.project_a, "credential-demo-jump"),
                            )
                            credential_ids = (
                                target_binding.credential_id,
                                jump_binding.credential_id,
                            )
                        changes = [
                            (
                                "target trust",
                                SSHHostTrust,
                                (foundation.project_a, "c-ingest"),
                                "approved",
                                False,
                            ),
                            (
                                "jump trust",
                                SSHHostTrust,
                                (foundation.project_a, "c-jump"),
                                "approved",
                                False,
                            ),
                            (
                                "target credential",
                                SSHCredential,
                                credential_ids[0],
                                "expires_us",
                                services.utc_now_us() - 1,
                            ),
                            (
                                "jump credential",
                                SSHCredential,
                                credential_ids[1],
                                "expires_us",
                                services.utc_now_us() - 1,
                            ),
                            (
                                "target trust revision",
                                SSHHostTrust,
                                (foundation.project_a, "c-ingest"),
                                "revision",
                                2,
                            ),
                            (
                                "jump trust revision",
                                SSHHostTrust,
                                (foundation.project_a, "c-jump"),
                                "revision",
                                2,
                            ),
                            (
                                "target credential revision",
                                SSHCredential,
                                credential_ids[0],
                                "revision",
                                2,
                            ),
                            (
                                "jump credential revision",
                                SSHCredential,
                                credential_ids[1],
                                "revision",
                                2,
                            ),
                            (
                                "source approval",
                                SourceAccessApproval,
                                (foundation.project_a, "c-ingest"),
                                "approved",
                                False,
                            ),
                            (
                                "source approval revision",
                                SourceAccessApproval,
                                (foundation.project_a, "c-ingest"),
                                "revision",
                                2,
                            ),
                            (
                                "configured roots",
                                TopologyState,
                                foundation.project_a,
                                "config",
                                None,
                            ),
                            (
                                "configuration revision",
                                Project,
                                foundation.project_a,
                                "revision",
                                3,
                            ),
                            (
                                "security policy",
                                ApplicationSetting,
                                1,
                                "additional_security_measures",
                                False,
                            ),
                        ]
                        for label, model, key, field, replacement in changes:
                            live = await start(alice, foundation.project_a, work, PROCESSES)
                            async with foundation.database.sessions.begin() as session:
                                row = await session.get(model, key, with_for_update=True)
                                previous = copy.deepcopy(getattr(row, field))
                                if label == "configured roots":
                                    replacement = copy.deepcopy(previous)
                                    replacement["connections"][1]["allowed_log_roots"] = [
                                        "/var/log/different-synthetic-root"
                                    ]
                                setattr(row, field, replacement)
                            try:
                                if label in {"security policy", "source approval revision"}:
                                    fresh = await manager.prepare_many(
                                        principal, foundation.project_a, identifiers, 2, login
                                    )
                                    assert (
                                        fresh["c-ingest"].signature != batch["c-ingest"].signature
                                    )
                                    for identifier in identifiers:
                                        assert fresh[identifier] == await manager.prepare(
                                            principal,
                                            foundation.project_a,
                                            identifier,
                                            2,
                                            login,
                                            lock=False,
                                        )
                                else:
                                    affected = "c-core" if label.startswith("jump") else "c-ingest"
                                    with pytest.raises(DomainError) as single:
                                        await manager.prepare(
                                            principal,
                                            foundation.project_a,
                                            affected,
                                            2,
                                            login,
                                            lock=False,
                                        )
                                    with pytest.raises(DomainError) as multiple:
                                        await manager.prepare_many(
                                            principal, foundation.project_a, identifiers, 2, login
                                        )
                                    assert multiple.value.code == single.value.code, label
                                stopped = await until(
                                    alice,
                                    foundation.project_a,
                                    live["session_id"],
                                    lambda item: item["status"] == "interrupted",
                                    deadline_seconds=3,
                                )
                                assert stopped["error_code"] in {
                                    "HOST_KEY_REQUIRED",
                                    "SSH_CREDENTIAL_EXPIRED",
                                    "SOURCE_NOT_APPROVED",
                                    "REVISION_CONFLICT",
                                }, label
                                assert foundation.app.state.live.engine.sessions[
                                    live["session_id"]
                                ].stopped, label
                                if label != "security policy":
                                    assert (
                                        await status(bob, foundation.project_b, other["session_id"])
                                    )["status"] == "following", label
                                else:
                                    await until(
                                        bob,
                                        foundation.project_b,
                                        other["session_id"],
                                        lambda item: item["status"] == "interrupted",
                                        deadline_seconds=3,
                                    )
                            finally:
                                async with foundation.database.sessions.begin() as session:
                                    row = await session.get(model, key, with_for_update=True)
                                    setattr(row, field, previous)
                            print("Fresh batch authorization revoked:", label)
                        assert jump_state.forwards and target_state.reads
                        assert not target_state.commands and not jump_state.commands
                        assert not target_state.mutations and not jump_state.mutations
                finally:
                    await asyncio.wait_for(foundation.app.state.live.close(), 4)
