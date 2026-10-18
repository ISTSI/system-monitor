"""A measured 12 MiB synthetic offline exchange through the real MariaDB/API path."""

import asyncio
import copy
import hashlib
import json
import resource
import time
from collections import Counter
from pathlib import Path

import pytest
from test_investigation_bundles import download_export, import_preview, preview_export
from test_investigations import QUERY, capture

from inspector.history import canonical_time, format_time
from inspector.investigation_bundles import encoded, pack_bundle

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


def resident_bytes():
    status = Path("/proc/self/status").read_text("utf-8")
    return (
        int(next(line.split()[1] for line in status.splitlines() if line.startswith("VmRSS:")))
        * 1024
    )


async def test_twelve_mib_offline_bundle_exchange_preserves_events_and_reports_memory(
    foundation, tmp_path, monkeypatch
):
    import asyncssh

    async with foundation.client(foundation.alice) as client:
        _base, created = await capture(foundation, tmp_path, client)
        template = (await preview_export(client, foundation.project_a, created["job_id"]))[
            "document"
        ]
        document = copy.deepcopy(template)
        document["bookmarks"] = []
        document["events"] = []
        private = "CAPACITY-PRIVATE"
        line_bytes = 131_072
        start = canonical_time(QUERY["from"])
        for index in range(96):
            event = copy.deepcopy(template["events"][index % len(template["events"])])
            event["event_id"] = f"capacity-event-{index:04d}"
            prefix = f"2026-10-16T12:00:00.000000Z request_id=CAPACITY-PRIVATE record={index:04d} "
            event["raw_line"] = (
                prefix
                + (private * ((line_bytes - len(prefix) + len(private) - 1) // len(private)))[
                    : line_bytes - len(prefix)
                ]
            )
            event["timestamp_us"] = start + index * 1000
            event["timestamp_utc"] = event["timestamp_original"] = format_time(
                event["timestamp_us"]
            )
            event["metadata"] = {"request_id": private}
            event["source"].update(
                byte_start=index * (line_bytes + 1),
                byte_end=(index + 1) * (line_bytes + 1),
                line_number=index + 1,
                content_sha256=hashlib.sha256((event["raw_line"] + "\n").encode()).hexdigest(),
            )
            document["events"].append(event)
        counts = Counter(event["source"]["source_revision_id"] for event in document["events"])
        for source in document["sources"]:
            source["events"] = counts[source["source_revision_id"]]
        raw_bytes = sum(len(event["raw_line"].encode()) for event in document["events"])
        assert raw_bytes == 12 * 1024 * 1024
        document_bytes = len(encoded(document))
        assert 10 * 1024 * 1024 <= document_bytes <= 20 * 1024 * 1024
        blob = pack_bundle(document, 32 * 1024 * 1024)
        calls = []

        async def forbidden(*args, **kwargs):
            calls.append(True)
            raise AssertionError("Offline capacity exchange attempted SSH.")

        monkeypatch.setattr(asyncssh, "connect", forbidden)
        rss_before = await asyncio.to_thread(resident_bytes)
        started = time.monotonic()
        preview = await import_preview(client, foundation.project_b, blob)
        assert preview.status_code == 200, preview.text[:500]
        committed = await client.post(
            f"/api/v1/projects/{foundation.project_b}/bundles/import",
            json={"preview_id": preview.json()["preview_id"]},
        )
        assert committed.status_code == 201, committed.text[:500]
        identity = committed.json()["investigation_id"]
        imported_seconds = time.monotonic() - started
        replay = await client.post(
            f"/api/v1/projects/{foundation.project_b}/bundle-investigations/{identity}/query",
            json={**QUERY, "limit": 3},
        )
        assert replay.status_code == 200, replay.text[:500]
        assert replay.json()["matched_count"] == 96 and len(replay.json()["items"]) == 3
        exported = await preview_export(
            client,
            foundation.project_b,
            identity,
            redact_terms=[private],
            replacement="[REDACTED]".ljust(len(private), "X"),
        )
        assert len(exported["document"]["events"]) == 96
        assert private.encode() not in encoded(exported["document"])
        exported_blob, _url = await download_export(client, foundation.project_b, exported)
        assert 12 * 1024 * 1024 < len(exported_blob) < 20 * 1024 * 1024
        rss_after = await asyncio.to_thread(resident_bytes)
        print(
            json.dumps(
                {
                    "capacity_exchange": {
                        "synthetic": True,
                        "raw_text_bytes": raw_bytes,
                        "document_bytes": document_bytes,
                        "upload_bytes": len(blob),
                        "redacted_download_bytes": len(exported_blob),
                        "events": 96,
                        "line_bytes": line_bytes,
                        "import_seconds": round(imported_seconds, 3),
                        "total_seconds": round(time.monotonic() - started, 3),
                        "process_rss_before_bytes": rss_before,
                        "process_rss_after_bytes": rss_after,
                        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                        * 1024,
                        "ssh_attempts": len(calls),
                        "scope": "Offline investigation bundle exchange; no live capacity or target collection claim.",
                    }
                }
            ),
            flush=True,
        )
        assert calls == []
