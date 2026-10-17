"""Owner-scoped deletion uses real MariaDB FKs and removes retained local bytes."""

import asyncio
import threading
from pathlib import Path

import pytest
from sqlalchemy import func, select
from test_history import CASES, FROM, TO, enable_demo, finished, seed, start

from inspector import history, history_retention
from inspector.errors import DomainError
from inspector.history_cache import HistoricalReadCache
from inspector.persistence.models import (
    Audit,
    HistoryCursor,
    HistoryDownload,
    HistoryEvent,
    HistoryJob,
    HistorySource,
)

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


def base(project_id, investigation_id):
    return f"/api/v1/projects/{project_id}/investigations/{investigation_id}"


async def retained_counts(foundation, project_id, job_id):
    result = {}
    async with foundation.database.sessions() as session:
        for model in (HistoryDownload, HistoryCursor, HistoryEvent, HistorySource):
            result[model.__name__] = await session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.project_id == project_id, model.job_id == job_id)
            )
        result["HistoryJob"] = await session.scalar(
            select(func.count())
            .select_from(HistoryJob)
            .where(HistoryJob.project_id == project_id, HistoryJob.id == job_id)
        )
    return result


async def test_delete_owned_capture_revokes_all_access_and_preserves_other_resources(
    foundation, tmp_path, monkeypatch
):
    enable_demo(foundation, tmp_path)
    cache = HistoricalReadCache(1_048_576)
    monkeypatch.setattr(history, "READ_CACHE", cache)
    manager = foundation.app.state.history
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
        await seed(admin, foundation.project_b)
        admin_capture, _, _ = await start(admin, foundation.project_a)
        await finished(admin, foundation.project_a, admin_capture["job_id"])
        async with foundation.client(foundation.alice) as alice:
            capture, _, _ = await start(alice, foundation.project_a)
            job = await finished(alice, foundation.project_a, capture["job_id"])
            other, _, _ = await start(alice, foundation.project_b)
            await finished(alice, foundation.project_b, other["job_id"])
            endpoint = base(foundation.project_a, capture["job_id"])
            payload = {**CASES[0]["request"], "limit": 1}
            first = await alice.post(endpoint + "/query", json=payload)
            assert first.status_code == 200 and first.json()["next_cursor"]
            event_id = first.json()["items"][0]["event_id"]
            assert cache.entries
            other_endpoint = base(foundation.project_b, other["job_id"])
            assert (await alice.post(other_endpoint + "/query", json=payload)).status_code == 200
            source_id = job["coverage"][0]["source_revision_id"]
            grant = await alice.post(endpoint + f"/sources/{source_id}/download", json={})
            assert grant.status_code == 200
            url = grant.json()["url"]
            assert (await alice.get(url)).content
            assert (await admin.delete(endpoint)).status_code == 404
            assert (
                await alice.delete(base(foundation.project_b, capture["job_id"]))
            ).status_code == 404
            assert (await alice.delete(endpoint, headers={"x-csrf-token": ""})).status_code == 403
            async with foundation.client(foundation.bob) as bob:
                bob_capture, _, _ = await start(bob, foundation.project_a)
                await finished(bob, foundation.project_a, bob_capture["job_id"])
                assert (await bob.delete(endpoint)).status_code == 404
            async with foundation.client() as anonymous:
                assert (await anonymous.delete(endpoint)).status_code == 401
            directory = manager.cache_path(foundation.project_a, capture["job_id"], "unused").parent
            assert directory.is_dir() and list(directory.iterdir())
            before = await retained_counts(foundation, foundation.project_a, capture["job_id"])
            assert all(before.values()), before
            response = await alice.delete(endpoint)
            assert response.status_code == 200, response.text
            assert response.json() == {
                "project_id": foundation.project_a,
                "investigation_id": capture["job_id"],
                "cache_cleanup_pending": False,
            }
            assert not directory.exists()
            assert not list(directory.parent.glob("deleted-*"))
            assert not any(
                key[0] == foundation.project_a and key[2] == capture["job_id"]
                for key in cache.entries
            )
            assert any(
                key[0] == foundation.project_b and key[2] == other["job_id"]
                for key in cache.entries
            )
            assert cache.used_bytes == sum(entry.bytes for entry in cache.entries.values())
            assert not any(
                (
                    await retained_counts(foundation, foundation.project_a, capture["job_id"])
                ).values()
            )
            for stale in (
                await alice.get(endpoint),
                await alice.get(
                    f"/api/v1/projects/{foundation.project_a}/jobs/{capture['job_id']}"
                ),
                await alice.post(
                    endpoint + "/query", json={**payload, "cursor": first.json()["next_cursor"]}
                ),
                await alice.post(
                    endpoint + f"/events/{event_id}/context", json={"from": FROM, "to": TO}
                ),
                await alice.post(endpoint + f"/sources/{source_id}/download", json={}),
                await alice.get(url),
                await alice.delete(endpoint),
            ):
                assert stale.status_code == 404, stale.text
            own_list = await alice.get(f"/api/v1/projects/{foundation.project_a}/investigations")
            assert own_list.status_code == 200 and own_list.json()["items"] == []
            for project, kept in (
                (foundation.project_b, other),
                (foundation.project_a, bob_capture),
                (foundation.project_a, admin_capture),
            ):
                counts = await retained_counts(foundation, project, kept["job_id"])
                assert (
                    counts["HistoryJob"] == 1
                    and counts["HistoryEvent"] > 0
                    and counts["HistorySource"] > 0
                )
                assert manager.cache_path(project, kept["job_id"], "unused").parent.is_dir()
            assert (await alice.post(other_endpoint + "/query", json=payload)).json()["items"]
        # Administrator can delete their own capture, but never another owner's.
        assert (
            await admin.delete(base(foundation.project_a, admin_capture["job_id"]))
        ).status_code == 200
    async with foundation.database.sessions() as session:
        audits = (
            await session.scalars(
                select(Audit).where(
                    Audit.action == "investigation.delete",
                    Audit.project_id == foundation.project_a,
                    Audit.target_id == capture["job_id"],
                )
            )
        ).all()
        assert len(audits) == 1 and audits[0].actor_user_id == foundation.alice.principal.user_id


async def test_active_collection_cannot_be_deleted(foundation, tmp_path, monkeypatch):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)

    async def leave_queued(*_):
        pass

    monkeypatch.setattr(foundation.app.state.history, "launch", leave_queued)
    async with foundation.client(foundation.alice) as alice:
        capture, _, _ = await start(alice, foundation.project_a)
        endpoint = base(foundation.project_a, capture["job_id"])
        for status in history.NONTERMINAL:
            async with foundation.database.sessions.begin() as session:
                job = await session.get(HistoryJob, (foundation.project_a, capture["job_id"]))
                job.status = status
            response = await alice.delete(endpoint)
            assert (
                response.status_code == 409
                and response.json()["error"]["code"] == "COLLECTION_ACTIVE"
            )
            current = await retained_counts(foundation, foundation.project_a, capture["job_id"])
            assert current["HistoryJob"] == 1 and current["HistorySource"] > 0
        # Every terminal status permits deletion, including empty interrupted captures.
        for index, status in enumerate(history.TERMINAL):
            async with foundation.database.sessions.begin() as session:
                job = await session.get(HistoryJob, (foundation.project_a, capture["job_id"]))
                job.status = status
            response = await alice.delete(endpoint)
            assert response.status_code == 200, (status, response.text)
            if index != len(history.TERMINAL) - 1:
                capture, _, _ = await start(alice, foundation.project_a)
                endpoint = base(foundation.project_a, capture["job_id"])


async def test_failed_delete_rolls_back_database_and_restores_staged_bytes(
    foundation, tmp_path, monkeypatch
):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    async with foundation.client(foundation.alice) as alice:
        capture, _, _ = await start(alice, foundation.project_a)
        await finished(alice, foundation.project_a, capture["job_id"])
        endpoint = base(foundation.project_a, capture["job_id"])
        directory = foundation.app.state.history.cache_path(
            foundation.project_a, capture["job_id"], "unused"
        ).parent
        original = {path.name: path.read_bytes() for path in directory.iterdir()}
        before = await retained_counts(foundation, foundation.project_a, capture["job_id"])
        audit = history.services.audit

        def fail_delete_audit(session, actor, action, project, target, now):
            if action == "investigation.delete":
                raise DomainError("SYNTHETIC_DELETE_FAILURE", "Synthetic rollback test.", 409)
            return audit(session, actor, action, project, target, now)

        monkeypatch.setattr(history.services, "audit", fail_delete_audit)
        response = await alice.delete(endpoint)
        assert (
            response.status_code == 409
            and response.json()["error"]["code"] == "SYNTHETIC_DELETE_FAILURE"
        )
        assert before == await retained_counts(foundation, foundation.project_a, capture["job_id"])
        assert original == {path.name: path.read_bytes() for path in directory.iterdir()}
        assert not list(directory.parent.glob("deleted-*"))
        assert (await alice.post(endpoint + "/query", json=CASES[0]["request"])).json()["items"]


async def test_deletion_waits_for_query_and_removes_its_cursor(foundation, tmp_path, monkeypatch):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    async with foundation.client(foundation.alice) as alice:
        capture, _, _ = await start(alice, foundation.project_a)
        await finished(alice, foundation.project_a, capture["job_id"])
        endpoint = base(foundation.project_a, capture["job_id"])
        entered, release = asyncio.Event(), asyncio.Event()
        original = history.historical_query

        async def held_query(*args, **kwargs):
            entered.set()
            await release.wait()
            return await original(*args, **kwargs)

        monkeypatch.setattr(history, "historical_query", held_query)
        query = asyncio.create_task(
            alice.post(endpoint + "/query", json={**CASES[0]["request"], "limit": 1})
        )
        await asyncio.wait_for(entered.wait(), 5)
        deletion = asyncio.create_task(alice.delete(endpoint))
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(deletion), 0.05)
        finally:
            release.set()
        page, response = await asyncio.wait_for(asyncio.gather(query, deletion), 10)
        assert page.status_code == 200 and page.json()["next_cursor"]
        assert response.status_code == 200, response.text
        assert not any(
            (await retained_counts(foundation, foundation.project_a, capture["job_id"])).values()
        )
        assert foundation.app.state.history.resource_locks == {}


async def test_cancelled_request_finishes_staged_deletion(foundation, tmp_path, monkeypatch):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    async with foundation.client(foundation.alice) as alice:
        capture, _, _ = await start(alice, foundation.project_a)
        await finished(alice, foundation.project_a, capture["job_id"])
        endpoint = base(foundation.project_a, capture["job_id"])
        entered, release = threading.Event(), threading.Event()
        original = history_retention.stage_cache

        def held_stage(*args):
            entered.set()
            assert release.wait(5)
            return original(*args)

        monkeypatch.setattr(history_retention, "stage_cache", held_stage)
        deletion = asyncio.create_task(alice.delete(endpoint))
        assert await asyncio.to_thread(entered.wait, 5)
        deletion.cancel()
        await asyncio.sleep(0)
        deletion.cancel()
        await asyncio.sleep(0)
        assert not deletion.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(deletion, 10)
        assert not any(
            (await retained_counts(foundation, foundation.project_a, capture["job_id"])).values()
        )
        directory = foundation.app.state.history.cache_path(
            foundation.project_a, capture["job_id"], "unused"
        ).parent
        assert not directory.exists() and not list(directory.parent.glob("deleted-*"))


async def test_deletion_stops_download_between_closed_bounded_reads(
    foundation, tmp_path, monkeypatch
):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    async with foundation.client(foundation.alice) as alice:
        capture, _, _ = await start(alice, foundation.project_a)
        job = await finished(alice, foundation.project_a, capture["job_id"])
        endpoint = base(foundation.project_a, capture["job_id"])
        source_id = job["coverage"][0]["source_revision_id"]
        grant = await alice.post(endpoint + f"/sources/{source_id}/download", json={})
        assert grant.status_code == 200
        manager = foundation.app.state.history
        async with foundation.database.sessions() as session:
            source = await session.get(
                HistorySource, (foundation.project_a, capture["job_id"], source_id)
            )
            path = manager.cache_path(foundation.project_a, capture["job_id"], source.cache_name)
        # The synthetic local byte source is deliberately larger than two chunks.
        path.write_bytes(b"synthetic-byte-" * 20_000)
        entered, release = threading.Event(), threading.Event()
        original = history_retention.read_download_chunk

        def held_read(*args):
            if args[2] == 0:
                entered.set()
                assert release.wait(5)
            return original(*args)

        monkeypatch.setattr(history_retention, "read_download_chunk", held_read)
        download = asyncio.create_task(alice.get(grant.json()["url"]))
        assert await asyncio.to_thread(entered.wait, 5)
        deletion = asyncio.create_task(alice.delete(endpoint))
        try:
            for _ in range(200):
                guarded = manager.resource_locks.get((foundation.project_a, capture["job_id"]))
                if guarded is not None and guarded[1] == 2:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Deletion did not wait for the bounded source read.")
        finally:
            release.set()
        response, removed = await asyncio.wait_for(asyncio.gather(download, deletion), 10)
        assert response.status_code == 200 and len(response.content) == 65_536
        assert removed.status_code == 200 and not removed.json()["cache_cleanup_pending"]
        assert not path.exists() and manager.resource_locks == {}
        assert (await alice.get(grant.json()["url"])).status_code == 404


async def test_cleanup_failure_reports_committed_deletion_and_pending_private_bytes(
    foundation, tmp_path, monkeypatch
):
    enable_demo(foundation, tmp_path)
    async with foundation.client(foundation.database.administrator) as admin:
        await seed(admin, foundation.project_a)
    async with foundation.client(foundation.alice) as alice:
        capture, _, _ = await start(alice, foundation.project_a)
        await finished(alice, foundation.project_a, capture["job_id"])
        endpoint = base(foundation.project_a, capture["job_id"])
        manager = foundation.app.state.history
        directory = manager.cache_path(foundation.project_a, capture["job_id"], "unused").parent

        def denied_cleanup(_staged):
            raise PermissionError("Synthetic cleanup denial.")

        with monkeypatch.context() as patch:
            patch.setattr(history_retention.StagedCache, "remove", denied_cleanup)
            response = await alice.delete(endpoint)
        assert response.status_code == 200 and response.json()["cache_cleanup_pending"]
        assert not any(
            (await retained_counts(foundation, foundation.project_a, capture["job_id"])).values()
        )
        assert not directory.exists()
        detached = list(directory.parent.glob("deleted-*"))
        assert len(detached) == 1
        assert (await alice.get(endpoint)).status_code == 404
        listed = await alice.get(f"/api/v1/projects/{foundation.project_a}/investigations")
        assert listed.status_code == 200 and listed.json()["items"] == []
        # The test releases only its own generated private cache namespace.
        history_retention.StagedCache(
            directory, detached[0], Path(manager.config.cache_dir), 100
        ).remove()
