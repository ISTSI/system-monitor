"""Actual authenticated MariaDB parser diagnostics; samples create no config writes."""

import asyncio
import json
import threading
from pathlib import Path

import pytest

from inspector import diagnostics

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]
ROOT = Path(__file__).resolve().parents[3]


async def test_parser_diagnostics_role_csrf_scope_revision_and_no_persistence(foundation):
    route = f"/api/v1/projects/{foundation.project_a}"
    document = json.loads((ROOT / "examples/project.example.json").read_text("utf-8"))
    document["project"].update(
        id=foundation.project_a, name="Synthetic parser diagnostics", revision=1
    )
    parser = document["parsers"][0]
    parser["timestamp"] = {"kind": "iso8601_prefix", "naive_timezone": "UTC"}
    payload = dict(
        project_id=foundation.project_a,
        expected_revision=2,
        parser=parser,
        sample="2026-10-16T12:00:00.123456Z request_id=REQ-0042\nunknown",
    )
    async with foundation.client(foundation.database.administrator) as client:
        saved = await client.put(
            route + "/topology", json=dict(expected_revision=1, config=document)
        )
        assert saved.status_code == 200
        before = (await client.get(route + "/topology")).json()
        result = await client.post(route + "/parsers/test", json=payload)
        assert result.status_code == 200, result.text
        assert result.json()["valid_count"] == 1
        assert result.json()["error_count"] == 1
        assert result.json()["lines"][0]["timestamp_us"] == "1792152000123456"
        assert result.json()["lines"][1]["timestamp_utc"] is None
        assert (await client.get(route + "/topology")).json() == before
        wrong = {**payload, "project_id": foundation.project_b}
        assert (await client.post(route + "/parsers/test", json=wrong)).status_code == 422
        assert (
            await client.post(route + "/parsers/test", json={**payload, "expected_revision": 1})
        ).status_code == 409
        assert (
            await client.post(route + "/parsers/test", json=payload, headers={"x-csrf-token": ""})
        ).status_code == 403
    async with foundation.client(foundation.alice) as client:
        denied = await client.post(route + "/parsers/test", json=payload)
        assert denied.status_code == 403
        assert "original_line" not in denied.text
        assert "REQ-0042" not in denied.text


async def test_parser_worker_releases_security_lock_and_rechecks_logged_out_cookie(
    foundation, monkeypatch
):
    started = threading.Event()
    release = threading.Event()
    real_preview = diagnostics.preview

    def delayed_preview(document, parser, sample):
        started.set()
        if not release.wait(timeout=10):
            raise AssertionError("Parser diagnostic test worker did not resume")
        return real_preview(document, parser, sample)

    monkeypatch.setattr(diagnostics, "preview", delayed_preview)
    document = json.loads((ROOT / "examples/project.example.json").read_text("utf-8"))
    payload = dict(
        project_id=foundation.project_a,
        expected_revision=1,
        parser=document["parsers"][0],
        sample="2026-10-16T12:00:00Z sensitive-diagnostic-sample",
    )
    async with foundation.client(foundation.database.administrator) as client:
        pending = asyncio.create_task(
            client.post(f"/api/v1/projects/{foundation.project_a}/parsers/test", json=payload)
        )
        try:
            assert await asyncio.to_thread(started.wait, 5), "Parser worker never started"
            # Logout needs the global security lock too. It must complete while
            # the bounded parser worker is still waiting, rather than behind it.
            logged_out = await asyncio.wait_for(
                client.post("/api/v1/auth/logout", json={}), timeout=3
            )
            assert logged_out.status_code == 200, logged_out.text
        finally:
            release.set()
        response = await asyncio.wait_for(pending, timeout=5)
        assert response.status_code == 401, response.text
        assert "sensitive-diagnostic-sample" not in response.text
