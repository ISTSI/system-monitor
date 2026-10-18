"""Real bundle parsing/redaction and offline-query semantics without a database."""

import copy
import hashlib
import io
import json
import stat
import struct
import time
import zipfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from inspector.errors import DomainError
from inspector.history import HistoricalQueryInput
from inspector.investigation_bundles import (
    WARNING,
    BundleDocument,
    encoded,
    load_json,
    matching_events,
    pack_bundle,
    redact,
    safe_topology,
    unpack_bundle,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def document():
    config = json.loads((ROOT / "examples/project.example.json").read_text(encoding="utf-8"))
    events = json.loads((ROOT / "fixtures/expected/events.json").read_text(encoding="utf-8"))
    project_id = events[0]["project_id"]
    config["project"]["id"] = project_id
    source_by_id = {}
    for event in events:
        source_id = event["source"]["source_revision_id"]
        source_by_id.setdefault(
            source_id,
            dict(
                source_revision_id=source_id,
                process_id=event["process_id"],
                remote_path=event["source"]["remote_path"],
                status="completed",
                events=0,
                bytes=100,
                expanded_bytes=100,
                error_code=None,
                checksum=event["source"]["content_sha256"],
                byte_start=0,
                byte_end=100,
            ),
        )
        source_by_id[source_id]["events"] += 1
    process_ids = sorted({event["process_id"] for event in events})
    output = dict(
        schema_version="1.0",
        origin=dict(
            project_id=project_id,
            investigation_id="capture-a",
            config_revision=1,
            snapshot_revision=1,
        ),
        selection=dict(
            title="Synthetic capture",
            process_ids=process_ids,
            **{"from": "2026-10-13T00:00:00.000000Z"},
            to="2026-10-17T00:00:00.000000Z",
            filter={},
            per_process_filters={},
            layout="merged",
            notes="private note",
        ),
        topology=safe_topology(config, process_ids),
        sources=list(source_by_id.values()),
        events=events,
        bookmarks=[],
        coverage_status="complete_for_scanned_candidates",
        errors=[],
        redaction=dict(applied=False, term_count=0, replacement="[REDACTED]", warning=WARNING),
    )
    return BundleDocument.model_validate(output).model_dump(mode="json", by_alias=True)


def unpack(data, **changes):
    limits = dict(maximum=10_000_000, member_maximum=10_000_000, ratio=500, timeout=5)
    return unpack_bundle(data, **{**limits, **changes})


def custom_bundle(document, *, manifest=None, extra=None, compression=zipfile.ZIP_STORED):
    content = document if isinstance(document, bytes) else encoded(document)
    manifest = manifest or {
        "schema_version": "1.0",
        "files": [
            {
                "path": "investigation.json",
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as archive:
        archive.writestr("manifest.json", encoded(manifest))
        archive.writestr("investigation.json", content)
        if extra is not None:
            archive.writestr(extra, "must never extract")
    return stream.getvalue()


def test_roundtrip_schema_and_unchanged_original(document):
    original = copy.deepcopy(document)
    blob = pack_bundle(document, 10_000_000)
    assert unpack(blob) == original == document
    # Seekable rolled-over upload is accepted without materialising a ZIP copy.
    assert unpack(io.BytesIO(blob)) == document
    schema = json.loads(
        (ROOT / "contracts/investigation-bundle.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(document)


def test_explicit_topology_projection_never_contains_active_configuration():
    config = json.loads((ROOT / "examples/project.example.json").read_text(encoding="utf-8"))
    for collection in ("project", "servers", "processes", "subsystems", "flows"):
        values = [config[collection]] if collection == "project" else config[collection]
        for value in values:
            value.update(
                password="do-not-export",
                credential_ref="do-not-export",
                connection_id="do-not-export",
                host_key="do-not-export",
                nested={"password": "do-not-export"},
            )
    snapshot = safe_topology(config, [process["id"] for process in config["processes"]])
    serialized = encoded(snapshot)
    assert b"do-not-export" not in serialized
    assert b"connections" not in serialized
    assert b"log_source" not in serialized
    assert b"username" not in serialized
    assert len(snapshot["processes"]) == len(config["processes"])


def test_redaction_reaches_metadata_keys_labels_filenames_notes_context_and_topology(document):
    event = document["events"][0]
    event["raw_line"] += " secret-A"
    event["metadata"]["secret-A-key"] = "secret-A value"
    event["source"]["remote_path"] = "/logs/secret-A.log"
    event["process_name_snapshot"] = "secret-A process"
    event["server_name_snapshot"] = "secret-A host"
    document["selection"]["notes"] = "secret-A note"
    document["topology"]["project"]["description"] = "secret-A documentation"
    document["bookmarks"] = [
        dict(
            id="bookmark",
            event_id=event["event_id"],
            annotation="secret-A annotation",
            pin_context=True,
            context=dict(
                project_id=document["origin"]["project_id"],
                event_id=event["event_id"],
                items=[
                    dict(
                        event=copy.deepcopy(event),
                        outside_time_bounds=False,
                        matches_filter=True,
                        is_anchor=True,
                    )
                ],
            ),
            process_name_snapshot="secret-A snapshot",
            server_name_snapshot="secret-A snapshot",
            created_at="2026-10-18T00:00:00.000000Z",
        )
    ]
    original = copy.deepcopy(document)
    result = redact(document, ["secret-A"], "[REDACTED]")
    assert b"secret-A" not in encoded(result)
    assert result["events"][0]["metadata"]["[REDACTED]-key"] == "[REDACTED] value"
    assert result["events"][0]["source"]["remote_path"] == "/logs/[REDACTED].log"
    assert result["bookmarks"][0]["context"]["items"][0]["event"]["raw_line"].endswith("[REDACTED]")
    assert unpack(pack_bundle(result, 10_000_000)) == result
    assert document == original


def test_literal_redaction_is_one_pass_and_reports_collisions():
    assert redact("a.*[a] a.*", ["a.*", "a"], "a") == "a[a] a"
    with pytest.raises(DomainError, match="collapses"):
        redact({"secret-1": "value", "secret-2": "value"}, ["secret-1", "secret-2"], "same")


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "connection",
        "duplicate-event",
        "foreign-origin",
        "bad-source",
        "bad-time",
        "invented-time",
        "negative-offset",
        "bad-context",
    ],
)
def test_semantically_invalid_content_is_rejected_before_commit(document, mutation):
    if mutation == "version":
        document["schema_version"] = "999"
    elif mutation == "connection":
        document["topology"]["servers"][0]["connection_id"] = "active-route"
    elif mutation == "duplicate-event":
        document["events"].append(copy.deepcopy(document["events"][0]))
    elif mutation == "foreign-origin":
        document["events"][0]["project_id"] = "other-project"
    elif mutation == "bad-source":
        document["events"][0]["source"]["source_revision_id"] = "missing"
    elif mutation == "bad-time":
        document["events"][0]["timestamp_us"] += 1
    elif mutation == "invented-time":
        document["events"][0]["timestamp_us"] = None
    elif mutation == "negative-offset":
        document["events"][0]["source"]["byte_start"] = -1
    elif mutation == "bad-context":
        document["bookmarks"] = [
            dict(
                id="bookmark",
                event_id="event",
                annotation="note",
                pin_context=True,
                context={"credentials": "no"},
                process_name_snapshot="process",
                server_name_snapshot="server",
                created_at="2026-10-18T00:00:00.000000Z",
            )
        ]
    with pytest.raises(DomainError) as error:
        unpack(custom_bundle(document))
    assert error.value.code == "INVALID_BUNDLE"


@pytest.mark.parametrize(
    "extra",
    [
        "../outside",
        "/absolute",
        "a\\..\\outside",
        "nested.zip",
        "manifest.json",
        "investigation.json",
        "directory/",
    ],
)
def test_unsafe_extra_or_duplicate_members_rejected(document, extra):
    with (
        pytest.warns(UserWarning)
        if extra in {"manifest.json", "investigation.json"}
        else __import__("contextlib").nullcontext()
    ):
        blob = custom_bundle(document, extra=extra)
    with pytest.raises(DomainError) as error:
        unpack(blob)
    assert error.value.code == "INVALID_BUNDLE"


def test_corrupt_crc_checksum_member_type_and_actual_budget(document):
    valid = pack_bundle(document, 10_000_000)
    with pytest.raises(DomainError):
        unpack(valid, maximum=len(valid) - 1)
    with pytest.raises(DomainError):
        unpack(valid, member_maximum=10)
    with pytest.raises(DomainError):
        unpack(valid, line_maximum=1)
    with pytest.raises(DomainError):
        unpack(valid[:-12])
    manifest = {
        "schema_version": "1.0",
        "files": [{"path": "investigation.json", "bytes": 1, "sha256": "0" * 64}],
    }
    with pytest.raises(DomainError):
        unpack(custom_bundle(document, manifest=manifest))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        link = zipfile.ZipInfo("manifest.json")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "outside")
        archive.writestr("investigation.json", encoded(document))
    with pytest.raises(DomainError):
        unpack(stream.getvalue())
    compressed = custom_bundle(document, compression=zipfile.ZIP_DEFLATED)
    with pytest.raises(DomainError):
        unpack(compressed, ratio=1)


def test_duplicate_keys_nonfinite_and_nested_json_fail():
    for value in (b'{"name":1,"name":2}', b'{"value":NaN}', b"[" * 33 + b"]" * 33):
        with pytest.raises(ValueError):
            load_json(value)


def test_bundle_rejects_identity_redaction_that_cannot_be_reopened(document):
    invalid = copy.deepcopy(document)
    invalid["events"][0]["event_id"] = "[REDACTED]"
    with pytest.raises(DomainError) as rejected:
        unpack(custom_bundle(invalid))
    assert rejected.value.status == 422
    # A replacement which changes immutable process references into display text
    # must fail at preview validation, before an unusable offline copy is saved.
    redacted = redact(document, [document["selection"]["process_ids"][0]], "[REDACTED]")
    with pytest.raises(ValidationError):
        BundleDocument.model_validate(redacted)


def test_shared_unicode_literal_query_time_bounds_diagnostic_and_order(document):
    cases = json.loads((ROOT / "fixtures/expected/query-cases.json").read_text(encoding="utf-8"))
    for case in cases:
        request = HistoricalQueryInput.model_validate(case["request"])
        assert [event["event_id"] for event in matching_events(document, request)] == case[
            "expected_event_ids"
        ], case["id"]
    request = HistoricalQueryInput.model_validate(
        {
            "process_ids": document["selection"]["process_ids"],
            "from": "2026-10-13T00:00:00.000000Z",
            "to": "2026-10-17T00:00:00.000000Z",
            "lane": "diagnostic",
        }
    )
    assert len(matching_events(document, request)) == 1
    assert matching_events(document, request)[0]["timestamp_us"] is None


def test_schema_future_fields_fail_without_evaluating_data(document):
    document["selection"]["owner_user_id"] = "attacker"
    with pytest.raises(ValidationError):
        BundleDocument.model_validate(document)


@pytest.mark.parametrize(
    "unsafe", ["nul-name", "forged-count", "declared-count", "metadata-budget"]
)
def test_zip_preflight_rejects_before_constructor_allocation(document, monkeypatch, unsafe):
    valid = bytearray(pack_bundle(document, 10_000_000))
    end = valid.rfind(b"PK\x05\x06")
    if unsafe == "nul-name":
        central = valid.find(b"PK\x01\x02")
        valid[central + 46] = 0
    elif unsafe == "forged-count":
        struct.pack_into("<HH", valid, end + 8, 1, 1)
    elif unsafe == "declared-count":
        struct.pack_into("<HH", valid, end + 8, 60000, 60000)
    else:
        struct.pack_into("<I", valid, end + 12, 65537)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Unsafe central metadata must be rejected before ZipFile allocates members.")

    monkeypatch.setattr("inspector.investigation_bundles.zipfile.ZipFile", forbidden)
    with pytest.raises(DomainError) as error:
        unpack(bytes(valid))
    assert error.value.code == "INVALID_BUNDLE"


def test_redaction_cached_absent_terms_never_rescan_frequent_match_suffixes():
    calls = {}

    class CountedText(str):
        def find(self, term, start=0, end=None):
            calls[term] = calls.get(term, 0) + 1
            return super().find(term, start) if end is None else super().find(term, start, end)

    absent = [f"missing-{index}" for index in range(19)]
    source = CountedText("a" * 100_000)
    began = time.monotonic()
    assert redact(source, ["a", *absent], "x") == "x" * 100_000
    assert all(calls[term] == 1 for term in absent)
    assert calls["a"] == len(source) + 1
    assert time.monotonic() - began < 5


def test_redaction_output_expansion_fails_before_unbounded_writes(monkeypatch):
    import inspector.investigation_bundles as bundles

    original = bundles.io.StringIO
    written = 0

    class GuardedOutput(original):
        def write(self, text):
            nonlocal written
            written += len(text.encode("utf-8"))
            assert written <= 64, "Budget must be checked before writing expansion."
            return super().write(text)

    monkeypatch.setattr(bundles.io, "StringIO", GuardedOutput)
    with pytest.raises(DomainError) as error:
        redact("a" * 1_000_000, ["a"], "x" * 128, max_bytes=64)
    assert error.value.code == "BUNDLE_BYTE_LIMIT"
    assert written == 0


def test_redaction_counts_exact_utf8_json_escapes_and_cumulative_nodes():
    source = {"a-key": ["a\x00é", "a", True, None, 123], "other": []}
    expected = {"é\\\n-key": ["é\\\n\x00é", "é\\\n", True, None, 123], "other": []}
    size = len(encoded(expected))
    assert redact(source, ["a"], "é\\\n", max_bytes=size) == expected
    with pytest.raises(DomainError) as error:
        redact(source, ["a"], "é\\\n", max_bytes=size - 1)
    assert error.value.code == "BUNDLE_BYTE_LIMIT"
    with pytest.raises(DomainError) as error:
        redact([1, 2, 3], [], "x", max_nodes=3)
    assert error.value.code == "BUNDLE_NODE_LIMIT"
    with pytest.raises(DomainError) as error:
        redact("a", ["a"], "x", deadline=time.monotonic() - 1)
    assert error.value.code == "BUNDLE_TIMEOUT"


def test_json_node_preflight_rejects_before_decoder_allocation(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Structural overflow must be rejected before json.loads allocates objects.")

    monkeypatch.setattr("inspector.investigation_bundles.json.loads", forbidden)
    with pytest.raises(ValueError, match="structural"):
        load_json(b'{"key":[1,true,null,"value"]}', max_nodes=6)


def test_unpaired_surrogate_json_is_rejected_with_sanitized_validation_error():
    value = load_json(b'{"notes":"\\ud800"}')
    with pytest.raises(DomainError) as error:
        encoded(value)
    assert error.value.code == "INVALID_BUNDLE"
    assert error.value.status == 422
    assert "\\ud800" not in str(error.value)
