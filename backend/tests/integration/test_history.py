"""Production local engine/index/API against an explicitly disposable MariaDB."""

import asyncio
import copy
import hashlib
import json
import threading
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from inspector import history
from inspector.database import create_engine
from inspector.history import NONTERMINAL, HistoryJob, HistorySource, persist_event_batch
from inspector.log_engine import LiteralFilter
from inspector.persistence.models import Audit, HistoryDownload, HistoryEvent, Workspace

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]
ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads((ROOT / "fixtures/expected/query-cases.json").read_text(encoding="utf-8"))
EVENTS = json.loads((ROOT / "fixtures/expected/events.json").read_text(encoding="utf-8"))
FROM = "2026-10-13T00:00:00.000000Z"
TO = "2026-10-17T00:00:00.000000Z"


async def seed(client, project_id):
    config = json.loads((ROOT / "examples/project.example.json").read_text(encoding="utf-8"))
    config["project"].update(id=project_id, revision=1)
    response = await client.put(
        f"/api/v1/projects/{project_id}/topology", json={"expected_revision": 1, "config": config}
    )
    assert response.status_code == 200, response.text


def enable_demo(foundation, tmp_path):
    config = replace(foundation.config, local_history_demo=True, cache_dir=str(tmp_path / "cache"))
    foundation.app.state.config = config
    foundation.app.state.history.config = config


async def start(client, project_id, processes=None):
    base = f"/api/v1/projects/{project_id}"
    workspace = await client.post(base + "/workspaces", json={})
    assert workspace.status_code == 201, workspace.text
    payload = {
        "workspace_id": workspace.json()["workspace_id"],
        "process_ids": processes or CASES[0]["request"]["process_ids"],
        "from": FROM,
        "to": TO,
    }
    plan = await client.post(base + "/collections/plan", json=payload)
    assert plan.status_code == 200, plan.text
    response = await client.post(base + "/collections", json=payload)
    assert response.status_code == 202, response.text
    return response.json(), plan.json(), payload


async def finished(client, project_id, job_id):
    for _ in range(300):
        response = await client.get(f"/api/v1/projects/{project_id}/jobs/{job_id}")
        assert response.status_code == 200, response.text
        if response.json()["status"] not in NONTERMINAL:
            return response.json()
        await asyncio.sleep(0.02)
    pytest.fail("Bounded synthetic collection did not terminate.")


async def test_all_golden_queries_full_event_provenance_and_diagnostic_lane(foundation, tmp_path):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    async with foundation.client(foundation.alice) as client:
        created, plan, _payload = await start(client, foundation.project_a)
        assert plan["demo_mode"] and plan["source_count"] == 21
        job = await finished(client, foundation.project_a, created["job_id"])
        assert job["status"] == "completed", job
        assert job["event_count"] == 38 and job["parse_issue_count"] == 1
        assert job["coverage_status"] == "complete_for_scanned_candidates"
        assert all(s["status"] == "completed" and s["checksum"] for s in job["coverage"])
        base = (
            f"/api/v1/projects/{foundation.project_a}/investigations/{created['investigation_id']}"
        )
        for case in CASES:
            response = await client.post(base + "/query", json=case["request"])
            assert response.status_code == 200, (case["id"], response.text)
            assert [e["event_id"] for e in response.json()["items"]] == case[
                "expected_event_ids"
            ], case["id"]
        payload = {
            **CASES[0]["request"],
            "from": FROM,
            "to": TO,
            "filter": {"include": [], "include_mode": "any", "exclude": [], "case_sensitive": True},
        }
        valid = (await client.post(base + "/query", json=payload)).json()
        diagnostic = (
            await client.post(base + "/query", json={**payload, "lane": "diagnostic"})
        ).json()
        assert len(valid["items"]) == 37 and len(diagnostic["items"]) == 1
        assert diagnostic["items"][0]["timestamp_us"] is None
        expected = {e["event_id"]: e for e in EVENTS}
        for event in [*valid["items"], *diagnostic["items"]]:
            oracle = copy.deepcopy(expected[event["event_id"]])
            oracle["project_id"] = foundation.project_a
            oracle["received_at"] = event["received_at"]
            assert event == oracle


async def test_cursor_scope_owner_job_predicate_snapshot_and_context(foundation, tmp_path):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
        await seed(admin, foundation.project_b)
    async with foundation.client(foundation.alice) as alice:
        a, _, _ = await start(alice, foundation.project_a)
        b, _, _ = await start(alice, foundation.project_b)
        await finished(alice, foundation.project_a, a["job_id"])
        await finished(alice, foundation.project_b, b["job_id"])
        abase = f"/api/v1/projects/{foundation.project_a}/investigations/{a['job_id']}"
        bbase = f"/api/v1/projects/{foundation.project_b}/investigations/{b['job_id']}"
        payload = {**CASES[0]["request"], "limit": 2}
        first = (await alice.post(abase + "/query", json=payload)).json()
        cursor = first["next_cursor"]
        assert cursor
        pages = [*first["items"]]
        while cursor:
            response = await alice.post(abase + "/query", json={**payload, "cursor": cursor})
            assert response.status_code == 200, response.text
            assert response.json()["source_snapshot_revision"] == first["source_snapshot_revision"]
            pages.extend(response.json()["items"])
            cursor = response.json()["next_cursor"]
        assert [e["event_id"] for e in pages] == CASES[0]["expected_event_ids"]
        for url, request in (
            (bbase + "/query", {**payload, "cursor": first["next_cursor"]}),
            (
                abase + "/query",
                {**payload, "cursor": first["next_cursor"], "filter": {"include": ["altered"]}},
            ),
            (
                f"/api/v1/projects/{foundation.project_b}/investigations/{a['job_id']}/query",
                payload,
            ),
        ):
            expected_status = (
                409 if request.get("filter", {}).get("include") == ["altered"] else 404
            )
            assert (await alice.post(url, json=request)).status_code == expected_status
        context = await alice.post(
            abase + f"/events/{pages[0]['event_id']}/context",
            json={
                "before": 2,
                "after": 3,
                "from": payload["from"],
                "to": payload["to"],
                "filter": payload["filter"],
            },
        )
        assert context.status_code == 200, context.text
        assert any(item["is_anchor"] for item in context.json()["items"])
        assert any(
            not item["matches_filter"] or item["outside_time_bounds"]
            for item in context.json()["items"]
        )
        assert (
            await alice.post(
                bbase + f"/events/{pages[0]['event_id']}/context", json={"from": FROM, "to": TO}
            )
        ).status_code == 200  # same local ID, different project capture
        listing = await alice.get(f"/api/v1/projects/{foundation.project_a}/investigations")
        assert [item["job_id"] for item in listing.json()["items"]] == [a["job_id"]]
    async with foundation.client(foundation.bob) as bob:
        for url in (f"/api/v1/projects/{foundation.project_a}/jobs/{a['job_id']}", abase):
            assert (await bob.get(url)).status_code == 404
        assert (await bob.post(abase + "/query", json=payload)).status_code == 404
    async with foundation.client(foundation.database.administrator) as admin:
        assert (
            await admin.get(f"/api/v1/projects/{foundation.project_a}/jobs/{a['job_id']}")
        ).status_code == 404


async def test_download_forgery_and_composite_foreign_keys(foundation, tmp_path):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
        await seed(admin, foundation.project_b)
    async with foundation.client(foundation.alice) as alice:
        a, _, _ = await start(alice, foundation.project_a, ["p-ingest-a"])
        await finished(alice, foundation.project_a, a["job_id"])
        base = f"/api/v1/projects/{foundation.project_a}/investigations/{a['job_id']}"
        grant = await alice.post(base + "/sources/src-ingest-plain-00/download", json={})
        assert grant.status_code == 200, grant.text
        downloaded = await alice.get(grant.json()["url"])
        assert downloaded.status_code == 200
        assert downloaded.content == (ROOT / "fixtures/logs/ingest/app.log").read_bytes()
        forged = grant.json()["url"].replace(foundation.project_a, foundation.project_b)
        assert (await alice.get(forged)).status_code == 404
    async with foundation.client(foundation.bob) as bob:
        assert (await bob.get(grant.json()["url"])).status_code == 404
    async with foundation.database.sessions() as session:
        source = await session.get(
            HistorySource, (foundation.project_a, a["job_id"], "src-ingest-plain-00")
        )
        event = await session.scalar(
            select(HistoryEvent).where(
                HistoryEvent.project_id == foundation.project_a, HistoryEvent.job_id == a["job_id"]
            )
        )
        cursor_job = await session.get(HistoryJob, (foundation.project_a, a["job_id"]))
        event_id = event.event_id
        workspace_id = cursor_job.workspace_id
        statements = [
            update(HistorySource)
            .where(
                HistorySource.project_id == foundation.project_a,
                HistorySource.job_id == a["job_id"],
                HistorySource.id == source.id,
            )
            .values(project_id=foundation.project_b),
            update(HistorySource)
            .where(
                HistorySource.project_id == foundation.project_a,
                HistorySource.job_id == a["job_id"],
                HistorySource.id == source.id,
            )
            .values(process_id="h-ingest-a"),
            update(HistoryEvent)
            .where(
                HistoryEvent.project_id == foundation.project_a,
                HistoryEvent.job_id == a["job_id"],
                HistoryEvent.event_id == event_id,
            )
            .values(process_id="p-parser-a"),
            update(HistoryJob)
            .where(HistoryJob.project_id == foundation.project_a, HistoryJob.id == a["job_id"])
            .values(owner_user_id=foundation.bob.principal.user_id),
            update(HistoryDownload).values(project_id=foundation.project_b),
        ]
    for statement in statements:
        async with foundation.database.sessions() as session:
            with pytest.raises(IntegrityError):
                await session.execute(statement)
                await session.commit()
            await session.rollback()
    async with foundation.database.sessions() as session:
        assert (
            await session.get(Workspace, (foundation.project_a, workspace_id))
        ).owner_user_id == foundation.alice.principal.user_id


async def test_snapshot_pagination_large_unicode_exact_bigint_and_nullable_source_order(
    foundation, tmp_path
):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    async with foundation.client(foundation.alice) as alice:
        created, _, _ = await start(alice, foundation.project_a, ["p-ingest-a"])
        await finished(alice, foundation.project_a, created["job_id"])
        base = f"/api/v1/projects/{foundation.project_a}/investigations/{created['job_id']}"
        request = {
            **CASES[0]["request"],
            "process_ids": ["p-ingest-a"],
            "filter": {"include": [], "exclude": [], "include_mode": "any", "case_sensitive": True},
            "from": FROM,
            "to": TO,
            "limit": 2,
        }
        first = (await alice.post(base + "/query", json=request)).json()
        assert first["next_cursor"]
        large_text = "2026-10-16T12:00:00.123457Z " + "😀" * 43_000 + " Straße %_ a.*b [x]"
        assert len(large_text.encode("utf-8")) > 170_000
        event = copy.deepcopy(first["items"][0])
        event.update(
            event_id="evt-large-unicode",
            raw_line=large_text,
            timestamp_us=1792152000123457,
            timestamp_utc="2026-10-16T12:00:00.123457Z",
        )
        event["source"].update(
            source_revision_id="src-ingest-plain-00",
            archive_member=None,
            member_ordinal=None,
            byte_start=1_000_000,
            byte_end=1_000_000 + len(large_text.encode("utf-8")),
            content_sha256="1" * 64,
        )
        async with foundation.database.sessions.begin() as session:
            job = await session.get(
                HistoryJob, (foundation.project_a, created["job_id"]), with_for_update=True
            )
            source = await session.get(
                HistorySource,
                (foundation.project_a, created["job_id"], "src-ingest-plain-00"),
                with_for_update=True,
            )
            await persist_event_batch(session, job, source, [event])
        all_items = [*first["items"]]
        cursor = first["next_cursor"]
        while cursor:
            response = await alice.post(base + "/query", json={**request, "cursor": cursor})
            assert response.status_code == 200, response.text
            assert response.json()["source_snapshot_revision"] == first["source_snapshot_revision"]
            assert response.json()["partial"]
            assert response.json()["matched_count"] == first["matched_count"]
            all_items.extend(response.json()["items"])
            cursor = response.json()["next_cursor"]
        assert len(all_items) == first["matched_count"]
        assert "evt-large-unicode" not in {e["event_id"] for e in all_items}
        literal = {
            **request,
            "limit": 200,
            "filter": {
                "include": ["STRASSE", "%_", "a.*b", "[x]"],
                "exclude": [],
                "include_mode": "all",
                "case_sensitive": False,
            },
        }
        result = await alice.post(base + "/query", json=literal)
        assert result.status_code == 200, result.text
        assert [e["event_id"] for e in result.json()["items"]] == ["evt-large-unicode"]
        assert result.json()["items"][0]["raw_line"] == large_text
        assert result.json()["items"][0]["timestamp_us"] == 1792152000123457
        # The complete allowed term count/length reaches service validation instead of HTTP16KiB.
        max_terms = {
            **request,
            "filter": {
                "include": ["😀" * 512] * 20,
                "exclude": ["😀" * 512] * 20,
                "include_mode": "all",
                "case_sensitive": False,
            },
        }
        assert (await alice.post(base + "/query", json=max_terms)).status_code == 200
        too_many = {**max_terms, "filter": {**max_terms["filter"], "include": ["term"] * 21}}
        assert (await alice.post(base + "/query", json=too_many)).status_code == 422
        async with foundation.database.sessions() as session:
            persisted = await session.get(
                HistoryEvent, (foundation.project_a, created["job_id"], "evt-large-unicode")
            )
            assert persisted.member_order == -1 and persisted.timestamp_us == 1792152000123457


async def test_approval_disabled_paths_validation_and_cancellation(
    foundation, tmp_path, monkeypatch
):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    # Keep queue reservation pending to exercise true queued cancellation, not a decorated button.
    manager = foundation.app.state.history
    await manager.slots.acquire()
    await manager.slots.acquire()
    try:
        async with foundation.client(foundation.alice) as alice:
            created, _, payload = await start(alice, foundation.project_a)
            endpoint = f"/api/v1/projects/{foundation.project_a}"
            assert (
                await alice.post(endpoint + "/collections", json={**payload, "path": "C:/private"})
            ).status_code == 422
            assert (
                await alice.post(
                    endpoint + "/collections",
                    json={**payload, "owner_user_id": foundation.bob.principal.user_id},
                )
            ).status_code == 422
            denied = await alice.post(
                endpoint + "/collections/plan", json={**payload, "workspace_id": "forged"}
            )
            assert denied.status_code == 404
            cancel = await alice.post(endpoint + f"/jobs/{created['job_id']}/cancel", json={})
            assert cancel.status_code == 200 and cancel.json()["status"] == "cancel_requested"
    finally:
        manager.slots.release()
        manager.slots.release()
    async with foundation.client(foundation.alice) as alice:
        cancelled = await finished(alice, foundation.project_a, created["job_id"])
        assert cancelled["status"] == "cancelled" and cancelled["event_count"] == 0
        disabled = replace(foundation.app.state.config, local_history_demo=False)
        foundation.app.state.config = disabled
        response = await alice.post(
            f"/api/v1/projects/{foundation.project_a}/collections/plan", json=payload
        )
        assert (
            response.status_code == 409
            and response.json()["error"]["code"] == "LOCAL_TRANSPORT_DISABLED"
        )


async def test_archive_rejection_records_actual_bytes_partial_coverage_and_no_extraction(
    foundation, tmp_path, monkeypatch
):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    candidates = history.local_manifest(foundation.app.state.config)
    unsafe = next(
        copy.deepcopy(item)
        for item in candidates
        if item["kind"] == "zip" and item["process_id"] == "p-ingest-a"
    )
    source = ROOT / "fixtures/rejected/traversal.zip"
    unsafe.update(
        local_path=str(source),
        file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        estimated_bytes=source.stat().st_size,
    )
    monkeypatch.setattr(history, "local_manifest", lambda config: [unsafe])
    async with foundation.client(foundation.alice) as alice:
        created, _, _ = await start(alice, foundation.project_a, ["p-ingest-a"])
        result = await finished(alice, foundation.project_a, created["job_id"])
        assert result["status"] == "partial", result
        assert result["event_count"] == 0 and result["downloaded_bytes"] == source.stat().st_size
        assert result["coverage"][0]["status"] == "failed"
        assert "UNSAFE_ARCHIVE_PATH" in result["errors"]
        assert not list((tmp_path / "cache").rglob("*.part"))
        assert not list((tmp_path / "cache").rglob("marker.txt"))
        download = await alice.post(
            f"/api/v1/projects/{foundation.project_a}/investigations/{created['job_id']}/sources/{unsafe['source_revision_id']}/download",
            json={},
        )
        assert download.status_code == 409


async def test_large_query_releases_auth_locks_and_logout_interrupts_dispatch(
    foundation, tmp_path, monkeypatch
):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    async with foundation.client(foundation.alice) as alice:
        created, _, _ = await start(alice, foundation.project_a)
        await finished(alice, foundation.project_a, created["job_id"])
        original = LiteralFilter.matches

        def slow_matches(self, raw_line):
            time.sleep(0.025)
            return original(self, raw_line)

        monkeypatch.setattr(LiteralFilter, "matches", slow_matches)
        request = {
            **CASES[0]["request"],
            "from": FROM,
            "to": TO,
            "filter": {"include": ["never-match-this-synthetic-value"]},
        }
        running = asyncio.create_task(
            alice.post(
                f"/api/v1/projects/{foundation.project_a}/investigations/{created['job_id']}/query",
                json=request,
            )
        )
        await asyncio.sleep(0.04)
        began = time.perf_counter()
        logout = await alice.post("/api/v1/auth/logout", json={})
        assert logout.status_code == 200, logout.text
        assert time.perf_counter() - began < 2.0
        interrupted = await running
        assert interrupted.status_code == 401, interrupted.text


async def test_active_cancellation_preserves_actual_bytes_before_first_batch(
    foundation, tmp_path, monkeypatch
):
    from inspector import log_engine

    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    began = threading.Event()
    original = log_engine.iter_source_events

    def slow_source(*args, **kwargs):
        began.set()
        time.sleep(0.5)
        yield from original(*args, **kwargs)

    monkeypatch.setattr(log_engine, "iter_source_events", slow_source)
    async with foundation.client(foundation.alice) as alice:
        created, _, _ = await start(alice, foundation.project_a, ["p-ingest-a"])
        for _ in range(100):
            if began.is_set():
                break
            await asyncio.sleep(0.01)
        assert began.is_set()
        started = time.perf_counter()
        response = await alice.post(
            f"/api/v1/projects/{foundation.project_a}/jobs/{created['job_id']}/cancel", json={}
        )
        assert response.status_code == 200, response.text
        stopped = await finished(alice, foundation.project_a, created["job_id"])
        assert time.perf_counter() - started < 2.0
        assert stopped["status"] == "cancelled" and stopped["event_count"] == 0
        assert stopped["downloaded_bytes"] > 0
        assert sum(s["bytes"] for s in stopped["coverage"]) == stopped["downloaded_bytes"]
        assert not list((tmp_path / "cache").rglob("*.part"))


async def test_page_and_context_text_byte_budgets_and_oversized_diagnostics(foundation, tmp_path):
    from inspector.log_engine import LocalSource, iter_source_events

    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    async with foundation.client(foundation.alice) as alice:
        created, _, _ = await start(alice, foundation.project_a, ["p-ingest-a"])
        await finished(alice, foundation.project_a, created["job_id"])
        path = tmp_path / "bounded-large-lines.log"
        prefix = "2026-10-16T12:00:00.050000Z byte-budget "
        with path.open("wb") as stream:
            for index in range(60):
                stream.write((prefix + str(index) + "x" * 199_900 + "\n").encode())
            stream.write(
                ("2026-10-16T12:00:00.050000Z " + "x" * 300_000 + " beyond-preview\n").encode()
            )
        source_id = "src-bounded-large-lines"
        source = LocalSource(
            project_id=foundation.project_a,
            process_id="p-ingest-a",
            source_revision_id=source_id,
            path=path,
            remote_path="/var/log/inspector-demo/ingest/bounded.log",
            server_id="h-ingest-a",
            process_name="Synthetic process",
            server_name="Synthetic server",
        )
        events = list(iter_source_events(source))
        assert len(events) == 61
        async with foundation.database.sessions.begin() as session:
            job = await session.get(
                HistoryJob, (foundation.project_a, created["job_id"]), with_for_update=True
            )
            retained = HistorySource(
                project_id=foundation.project_a,
                job_id=created["job_id"],
                id=source_id,
                process_id="p-ingest-a",
                remote_path=source.remote_path,
                kind="plain",
                cache_name=str(uuid4()),
                checksum=None,
                status="completed",
                error_code=None,
                event_count=0,
                downloaded_bytes=path.stat().st_size,
                expanded_bytes=path.stat().st_size,
                manifest={},
            )
            session.add(retained)
            await session.flush()
            await persist_event_batch(session, job, retained, events)
        base = f"/api/v1/projects/{foundation.project_a}/investigations/{created['job_id']}"
        request = {
            **CASES[0]["request"],
            "process_ids": ["p-ingest-a"],
            "from": "2026-10-16T12:00:00.050000Z",
            "to": "2026-10-16T12:00:00.050001Z",
            "filter": {"include": [], "exclude": [], "include_mode": "any", "case_sensitive": True},
            "limit": 1000,
        }
        for predicate in ({"include": []}, {"include": ["byte-budget"]}):
            first = await alice.post(base + "/query", json={**request, "filter": predicate})
            assert first.status_code == 200, first.text
            first = first.json()
            assert first["matched_count"] == 60 and 1 < len(first["items"]) < 60
            assert sum(len(e["raw_line"].encode()) for e in first["items"]) <= 8_388_608
            assert first["next_cursor"]
            second = (
                await alice.post(
                    base + "/query",
                    json={**request, "filter": predicate, "cursor": first["next_cursor"]},
                )
            ).json()
            assert len(first["items"]) + len(second["items"]) == 60
            assert not {e["event_id"] for e in first["items"]} & {
                e["event_id"] for e in second["items"]
            }
        anchor = events[30]
        context = await alice.post(
            base + f"/events/{anchor['event_id']}/context",
            json={"before": 50, "after": 50, "from": FROM, "to": TO},
        )
        assert (
            context.status_code == 413 and context.json()["error"]["code"] == "CONTEXT_BYTE_LIMIT"
        )
        diagnostic = await alice.post(
            base + "/query",
            json={**request, "lane": "diagnostic", "filter": {"include": ["beyond-preview"]}},
        )
        assert diagnostic.status_code == 200, diagnostic.text
        assert diagnostic.json()["matched_count"] is None
        assert len(diagnostic.json()["items"]) == 1
        oversized = diagnostic.json()["items"][0]
        assert (
            oversized["parse_status"] == "oversized_line"
            and "beyond-preview" not in oversized["raw_line"]
        )
        context = await alice.post(
            base + f"/events/{oversized['event_id']}/context",
            json={
                "before": 0,
                "after": 0,
                "from": FROM,
                "to": TO,
                "filter": {"include": ["beyond-preview"]},
            },
        )
        assert context.status_code == 200, context.text
        assert context.json()["items"][0]["matches_filter"] is None


async def test_query_dispatch_supports_single_connection_pool(foundation, tmp_path):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    async with foundation.client(foundation.alice) as alice:
        created, _, _ = await start(alice, foundation.project_a)
        await finished(alice, foundation.project_a, created["job_id"])
    database = replace(
        foundation.config.database,
        pool={
            **foundation.config.database.pool,
            "size": 1,
            "max_overflow": 0,
            "timeout_seconds": 1,
        },
    )
    engine = create_engine(database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for literal in (["request_id=REQ-0042"], []):
            async with sessions() as session:
                async with asyncio.timeout(5):
                    result = await history.historical_query(
                        session,
                        foundation.alice.principal,
                        foundation.project_a,
                        created["job_id"],
                        history.HistoricalQueryInput.model_validate(
                            {**CASES[0]["request"], "filter": {"include": literal}}
                        ),
                    )
                    await session.commit()
                assert result["items"] and result["matched_count"]
    finally:
        await engine.dispose()


async def test_collision_fixture_ids_and_distinct_text_are_project_paired(foundation, tmp_path):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
        await seed(admin, foundation.project_b)
    collisions = json.loads(
        (ROOT / "fixtures/multi-system/events.json").read_text(encoding="utf-8")
    )
    ids_by_project = {}
    async with foundation.client(foundation.alice) as alice:
        for project_id, fixture_project, marker in (
            (foundation.project_a, "system-alpha", "ALPHA"),
            (foundation.project_b, "system-beta", "BETA"),
        ):
            original, _, _ = await start(alice, project_id, ["p-ingest-a"])
            await finished(alice, project_id, original["job_id"])
            collision_job_id = str(uuid4())
            selected = [
                {**event, "project_id": project_id}
                for event in collisions
                if event["project_id"] == fixture_project
            ]
            async with foundation.database.sessions.begin() as session:
                old = await session.get(HistoryJob, (project_id, original["job_id"]))
                job = HistoryJob(
                    **{
                        column.name: getattr(old, column.name)
                        for column in HistoryJob.__table__.columns
                    }
                )
                job.id = collision_job_id
                job.event_count = job.parse_issue_count = job.snapshot_revision = 0
                source = HistorySource(
                    project_id=project_id,
                    job_id=collision_job_id,
                    id="src-ingest-plain-00",
                    process_id="p-ingest-a",
                    remote_path="/var/log/inspector-demo/ingest/app.log",
                    kind="plain",
                    cache_name=str(uuid4()),
                    checksum=None,
                    status="completed",
                    error_code=None,
                    event_count=0,
                    downloaded_bytes=0,
                    expanded_bytes=0,
                    manifest={},
                )
                session.add(job)
                await session.flush()
                session.add(source)
                await session.flush()
                await persist_event_batch(session, job, source, selected)
            request = {
                **CASES[0]["request"],
                "process_ids": ["p-ingest-a"],
                "from": FROM,
                "to": TO,
                "filter": {"include": ["system_marker=" + marker]},
            }
            endpoint = f"/api/v1/projects/{project_id}/investigations/{collision_job_id}/query"
            own = await alice.post(endpoint, json=request)
            assert own.status_code == 200, own.text
            assert len(own.json()["items"]) == 2
            assert all(
                event["project_id"] == project_id and "system_marker=" + marker in event["raw_line"]
                for event in own.json()["items"]
            )
            ids_by_project[project_id] = [event["event_id"] for event in own.json()["items"]]
            other_marker = "BETA" if marker == "ALPHA" else "ALPHA"
            foreign = await alice.post(
                endpoint, json={**request, "filter": {"include": ["system_marker=" + other_marker]}}
            )
            assert foreign.status_code == 200 and foreign.json()["items"] == []
        assert ids_by_project[foundation.project_a] == ids_by_project[foundation.project_b]


async def test_administrative_cancel_is_audited_without_private_read_access(foundation, tmp_path):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    manager = foundation.app.state.history
    await manager.slots.acquire()
    await manager.slots.acquire()
    try:
        async with foundation.client(foundation.alice) as alice:
            created, _, _ = await start(alice, foundation.project_a)
        base = f"/api/v1/projects/{foundation.project_a}"
        async with foundation.client(foundation.bob) as bob:
            assert (
                await bob.post(base + f"/jobs/{created['job_id']}/cancel", json={})
            ).status_code == 404
        async with foundation.client(foundation.database.administrator) as admin:
            assert (await admin.get(base + f"/jobs/{created['job_id']}")).status_code == 404
            assert (
                await admin.post(
                    base + f"/investigations/{created['job_id']}/query", json=CASES[0]["request"]
                )
            ).status_code == 404
            assert (
                await admin.post(
                    f"/api/v1/projects/{foundation.project_b}/jobs/{created['job_id']}/cancel",
                    json={},
                )
            ).status_code == 404
            response = await admin.post(base + f"/jobs/{created['job_id']}/cancel", json={})
            assert response.status_code == 200, response.text
            assert response.json() == {
                "project_id": foundation.project_a,
                "job_id": created["job_id"],
                "status": "cancel_requested",
            }
    finally:
        manager.slots.release()
        manager.slots.release()
    async with foundation.client(foundation.alice) as alice:
        assert (await finished(alice, foundation.project_a, created["job_id"]))[
            "status"
        ] == "cancelled"
    async with foundation.database.sessions() as session:
        records = (
            await session.scalars(
                select(Audit).where(
                    Audit.action == "collection.cancel",
                    Audit.target_id == created["job_id"],
                    Audit.actor_user_id == foundation.database.administrator.principal.user_id,
                )
            )
        ).all()
        assert len(records) == 1 and records[0].project_id == foundation.project_a


async def test_read_cache_scope_refilter_auth_and_snapshot_append(
    foundation, tmp_path, monkeypatch
):
    from inspector.history_cache import HistoricalReadCache

    cache = HistoricalReadCache(1_048_576)
    monkeypatch.setattr(history, "READ_CACHE", cache)
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    async with foundation.client(foundation.alice) as alice:
        created, _, _ = await start(alice, foundation.project_a)
        await finished(alice, foundation.project_a, created["job_id"])
        base = f"/api/v1/projects/{foundation.project_a}/investigations/{created['job_id']}"
        first = await alice.post(base + "/query", json=CASES[0]["request"])
        assert first.status_code == 200, first.text
        assert len(cache.entries) == 1
        initial_key = next(iter(cache.entries))
        again = await alice.post(base + "/query", json=CASES[0]["request"])
        assert again.json() == first.json() and len(cache.entries) == 1
        refilter = await alice.post(base + "/query", json=CASES[1]["request"])
        assert [event["event_id"] for event in refilter.json()["items"]] == CASES[1][
            "expected_event_ids"
        ]
        assert len(cache.entries) == 1  # filter terms never identify a raw snapshot cache
        for changed in (
            {"from": "2026-10-16T12:00:00.100000Z"},
            {"process_ids": ["p-ingest-a"]},
            {"lane": "diagnostic"},
        ):
            response = await alice.post(base + "/query", json={**CASES[0]["request"], **changed})
            assert response.status_code == 200, response.text
        assert len(cache.entries) == 4
        event = copy.deepcopy(first.json()["items"][0])
        event.update(
            event_id="evt-after-cache-snapshot",
            raw_line=event["raw_line"] + " retained-after-cache",
        )
        event["source"]["byte_start"] = 2_000_000
        async with foundation.database.sessions.begin() as session:
            job = await session.get(
                HistoryJob, (foundation.project_a, created["job_id"]), with_for_update=True
            )
            source = await session.get(
                HistorySource,
                (foundation.project_a, created["job_id"], event["source"]["source_revision_id"]),
                with_for_update=True,
            )
            await persist_event_batch(session, job, source, [event])
        appended = await alice.post(base + "/query", json=CASES[0]["request"])
        assert appended.status_code == 200, appended.text
        assert "evt-after-cache-snapshot" in {row["event_id"] for row in appended.json()["items"]}
        assert len(cache.entries) == 5 and initial_key in cache.entries
        assert (
            await alice.post(
                base.replace(foundation.project_a, foundation.project_b) + "/query",
                json=CASES[0]["request"],
            )
        ).status_code == 404
    async with foundation.client(foundation.bob) as bob:
        assert (await bob.post(base + "/query", json=CASES[0]["request"])).status_code == 404
    assert len(cache.entries) == 5 and cache.used_bytes <= cache.max_bytes
