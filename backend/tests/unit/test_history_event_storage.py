"""Golden provenance survives normalized and retained legacy event payloads."""

import json
from pathlib import Path

from inspector.history import compact_event_payload, event_payload
from inspector.persistence.models import HistoryEvent

ROOT = Path(__file__).resolve().parents[3]


def test_all_golden_events_roundtrip_normalized_and_legacy_payloads():
    expected = json.loads((ROOT / "fixtures/expected/events.json").read_text(encoding="utf-8"))
    full_bytes = compact_bytes = 0
    for event in expected:
        compact = compact_event_payload(event)
        legacy = {key: value for key, value in event.items() if key != "raw_line"}
        full_bytes += len(json.dumps(legacy).encode())
        compact_bytes += len(json.dumps(compact).encode())
        for payload in (compact, legacy):
            row = HistoryEvent(
                project_id=event["project_id"],
                job_id="synthetic-capture",
                event_id=event["event_id"],
                process_id=event["process_id"],
                source_revision_id=event["source"]["source_revision_id"],
                capture_seq=1,
                timestamp_us=event["timestamp_us"],
                member_order=-1
                if event["source"]["member_ordinal"] is None
                else event["source"]["member_ordinal"],
                byte_start=event["source"]["byte_start"],
                raw_line=event["raw_line"],
                payload=payload,
            )
            assert event_payload(row) == event
    assert compact_bytes < full_bytes * 0.8


def test_legacy_identity_fields_never_override_authoritative_index_columns():
    event = json.loads((ROOT / "fixtures/expected/events.json").read_text(encoding="utf-8"))[0]
    row = HistoryEvent(
        project_id="actual-project",
        job_id="actual-capture",
        event_id="actual-event",
        process_id="actual-process",
        source_revision_id="actual-source",
        capture_seq=1,
        timestamp_us=1_792_152_000_123_457,
        member_order=-1,
        byte_start=9876,
        raw_line=event["raw_line"],
        payload=event,
    )
    restored = event_payload(row)
    assert (restored["project_id"], restored["event_id"], restored["process_id"]) == (
        "actual-project",
        "actual-event",
        "actual-process",
    )
    assert restored["timestamp_us"] == 1_792_152_000_123_457
    assert restored["timestamp_utc"] == "2026-10-16T12:00:00.123457Z"
    assert restored["source"]["source_revision_id"] == "actual-source"
    assert restored["source"]["member_ordinal"] is None and restored["source"]["byte_start"] == 9876
