"""Production engine verification against fixed golden outputs, never oracle functions."""

from __future__ import annotations

import hashlib
import io
import json
import struct
import tarfile
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from inspector.log_engine import (
    CancellationToken,
    CorrelationMarker,
    EngineError,
    EngineLimits,
    LiteralFilter,
    LocalSource,
    ParserConfig,
    ScanProgress,
    event_sort_key,
    iter_source_events,
    parse_timestamp,
    safe_archive_name,
    utc_microseconds,
)

ROOT = Path(__file__).resolve().parents[3]


def read_json(path: str) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def local(path: Path, **options: Any) -> LocalSource:
    return LocalSource("project-a", "process-a", "source-a", path, "/approved/app.log", **options)


@pytest.fixture(scope="module")
def captured() -> list[dict[str, Any]]:
    config = read_json("examples/project.example.json")
    processes = {item["id"]: item for item in config["processes"]}
    servers = {item["id"]: item for item in config["servers"]}
    results = []
    for item in read_json("fixtures/source-manifest.json")["sources"]:
        process = processes[item["process_id"]]
        server = servers[process["server_id"]]
        source = LocalSource(
            project_id="project-demo",
            process_id=item["process_id"],
            source_revision_id=item["source_revision_id"],
            path=ROOT / item["fixture_path"],
            remote_path=item["remote_path"],
            kind=item["kind"],
            archive_member=item["archive_member"],
            member_ordinal=item["member_ordinal"],
            server_id=server["id"],
            process_name=process["name"],
            server_name=server["name"],
            correlation_markers=(CorrelationMarker("request_id", "request_id="),),
        )
        progress = ScanProgress()
        events = list(
            iter_source_events(source, progress=progress, received_at="2026-10-16T12:00:03.000000Z")
        )
        assert progress.source_complete and progress.source_stable
        assert progress.source_sha256 == item["file_sha256"]
        assert progress.downloaded_bytes == source.path.stat().st_size
        assert progress.expanded_bytes == item["uncompressed_bytes"]
        results.extend(events)
    return results


def test_all_golden_events_and_exact_physical_provenance(captured: list[dict[str, Any]]) -> None:
    expected = {event["event_id"]: event for event in read_json("fixtures/expected/events.json")}
    assert len(captured) == len(expected) == 38
    for event in captured:
        assert event == expected[event["event_id"]]


@pytest.mark.parametrize(
    "case", read_json("fixtures/expected/query-cases.json"), ids=lambda case: case["id"]
)
def test_all_golden_queries(captured: list[dict[str, Any]], case: dict[str, Any]) -> None:
    request = case["request"]
    lower, upper = utc_microseconds(request["from"]), utc_microseconds(request["to"])
    global_filter = LiteralFilter(**request["filter"])
    per_process = {
        key: LiteralFilter(**value) for key, value in request["per_process_filters"].items()
    }
    actual = [
        event
        for event in captured
        if event["timestamp_us"] is not None
        and event["process_id"] in request["process_ids"]
        and lower <= event["timestamp_us"] < upper
        and global_filter.matches(event["raw_line"])
        and per_process.get(event["process_id"], LiteralFilter()).matches(event["raw_line"])
    ]
    assert [event["event_id"] for event in sorted(actual, key=event_sort_key)] == case[
        "expected_event_ids"
    ]


@pytest.mark.parametrize(
    "token",
    [
        "2026-99-99T12:00:00Z",
        "2026-10-16T12:00:00.1234567Z",
        "2026-10-16T12:00:60Z",
        "2026-10-16T12:00:00-00:00",
        "2026-10-16T12:00:00+01:00",
        "2026-10-16T12:00:00Zsuffix",
        "2026-10-16 12:00:00",
    ],
)
def test_unsupported_timestamp_is_never_invented(token: str) -> None:
    assert parse_timestamp(token + " INFO").micros is None
    with pytest.raises(ValueError):
        utc_microseconds(token)


def test_integer_timestamps_fixed_width_and_negative_epoch() -> None:
    assert utc_microseconds("1969-12-31T23:59:59.999999Z") == -1
    assert utc_microseconds("2026-10-16T12:00:00.000001+00:00") == 1_792_152_000_000_001
    parser = ParserConfig("fixed_width", 23, "%Y-%m-%d %H:%M:%S,%f", "UTC")
    parsed = parse_timestamp("2026-10-16 12:00:00,123 INFO", parser)
    assert parsed.utc == "2026-10-16T12:00:00.123000Z"
    assert (
        parse_timestamp("2026-10-16 12:00:00,123 INFO", replace(parser, naive_timezone=None)).micros
        is None
    )
    assert (
        parse_timestamp(
            "2026-10-16 12:00:00,123 INFO", ParserConfig("fixed_width", 23, "%Y-%m-%d %H:%M:%S,%f")
        ).micros
        is None
    )
    assert (
        parse_timestamp(
            "2026-10-16 12:00:00,123+0100",
            ParserConfig("fixed_width", 28, "%Y-%m-%d %H:%M:%S,%f%z"),
        ).micros
        is None
    )


def test_literal_unicode_and_validation() -> None:
    assert LiteralFilter(include=("STRASSE",), case_sensitive=False).matches("Straße")
    assert LiteralFilter(include=("a.*[x]%_\\|$()",)).matches(" a.*[x]%_\\|$() ")
    assert LiteralFilter(include=("  ",)).matches("x  y")
    assert not LiteralFilter(include=("  ",)).matches("x y")
    assert LiteralFilter(include=("",), exclude=("",)).matches("anything")
    assert not LiteralFilter(include=("a",), exclude=("a",)).matches("a")
    for options in (
        {"include": ["x"] * 21},
        {"exclude": ["x" * 513]},
        {"include_mode": "regex"},
        {"case_sensitive": 1},
        {"include": "abc"},
    ):
        with pytest.raises(ValueError):
            LiteralFilter(**options)


def test_crlf_final_line_offsets_decode_and_repeated_text(tmp_path: Path) -> None:
    path = tmp_path / "capture.log"
    line = b"2026-10-16T12:00:00Z identical\r\n"
    data = line * 2 + b"invalid \xff\n" + b"2026-10-16T12:00:01Z final"
    path.write_bytes(data)
    events = list(iter_source_events(local(path)))
    assert len(events) == 4
    assert events[0]["raw_line"] == events[1]["raw_line"]
    assert events[0]["event_id"] != events[1]["event_id"]
    assert events[0]["source"]["byte_end"] == len(line)
    assert events[1]["source"]["byte_start"] == len(line)
    assert events[0]["source"]["content_sha256"] == hashlib.sha256(line).hexdigest()
    assert events[2]["parse_status"] == "decode_error" and events[2]["timestamp_us"] is None
    assert events[3]["parse_status"] == "incomplete_final_line"
    assert events[3]["source"]["byte_end"] == len(data)
    assert (
        list(iter_source_events(replace(local(path), project_id="project-b")))[0]["event_id"]
        == events[0]["event_id"]
    )


@pytest.mark.parametrize(
    "name", ["../escape", "a/../escape", "/absolute", "C:/escape", "a\\escape", "a\0b"]
)
def test_unsafe_archive_paths(name: str) -> None:
    assert not safe_archive_name(name)


@pytest.mark.parametrize(
    "fixture,kind,code",
    [
        ("traversal.zip", "zip", "UNSAFE_ARCHIVE_PATH"),
        ("symlink.tar.gz", "tar.gz", "UNSAFE_ARCHIVE_MEMBER_TYPE"),
        ("corrupt.zip", "zip", "CORRUPT_ARCHIVE"),
    ],
)
def test_supplied_rejection_fixtures(fixture: str, kind: str, code: str) -> None:
    with pytest.raises(EngineError, match=code):
        list(iter_source_events(local(ROOT / "fixtures/rejected" / fixture, kind=kind)))


def make_zip(
    path: Path, entries: list[tuple[str, bytes]], compression: int = zipfile.ZIP_STORED
) -> None:
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, data in entries:
            archive.writestr(name, data)


def test_archive_metadata_is_validated_before_first_event(tmp_path: Path) -> None:
    path = tmp_path / "source.zip"
    make_zip(path, [("okay.log", b"valid\n"), ("../bad.log", b"bad\n")])
    with pytest.raises(EngineError, match="UNSAFE_ARCHIVE_PATH"):
        next(iter_source_events(local(path, kind="zip")))
    with pytest.warns(UserWarning, match="Duplicate name"):
        make_zip(path, [("same.log", b"one\n"), ("same.log", b"two\n")])
    with pytest.raises(EngineError, match="DUPLICATE_ARCHIVE_MEMBER"):
        list(iter_source_events(local(path, kind="zip")))
    make_zip(path, [("nested.zip", b"harmless marker")])
    with pytest.raises(EngineError, match="NESTED_ARCHIVE_UNSUPPORTED"):
        list(iter_source_events(local(path, kind="zip")))


def test_zip_links_encryption_and_unsupported_compression(tmp_path: Path) -> None:
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w") as archive:
        link = zipfile.ZipInfo("link.log")
        link.external_attr = 0o120777 << 16
        archive.writestr(link, b"marker")
    with pytest.raises(EngineError, match="UNSAFE_ARCHIVE_MEMBER_TYPE"):
        list(iter_source_events(local(path, kind="zip")))
    make_zip(path, [("source.log", b"data\n")], zipfile.ZIP_BZIP2)
    with pytest.raises(EngineError, match="COMPRESSION_UNSUPPORTED"):
        list(iter_source_events(local(path, kind="zip")))
    make_zip(path, [("source.log", b"data\n")])
    data = bytearray(path.read_bytes())
    struct.pack_into("<H", data, data.index(b"PK\x01\x02") + 8, 1)
    path.write_bytes(data)
    with pytest.raises(EngineError, match="ENCRYPTED_ARCHIVE_UNSUPPORTED"):
        list(iter_source_events(local(path, kind="zip")))


def test_limits_actual_physical_bytes_and_oversized_preview(tmp_path: Path) -> None:
    path = tmp_path / "source.log"
    raw = b"2026-10-16T12:00:00Z " + b"x" * 1024 + b"\nnext\n"
    path.write_bytes(raw)
    state = ScanProgress()
    events = list(iter_source_events(local(path), EngineLimits(max_line_bytes=50), progress=state))
    assert events[0]["parse_status"] == "oversized_line" and events[0]["timestamp_us"] is None
    assert events[0]["metadata"]["preview_truncated"] == "true"
    assert len(events[0]["raw_line"].encode()) == 50
    assert events[1]["source"]["byte_start"] == len(raw) - len(b"next\n")
    assert state.expanded_bytes == len(raw)
    for limits, code in [
        (EngineLimits(max_download_bytes=10), "DOWNLOAD_BYTES_LIMIT"),
        (EngineLimits(max_expanded_bytes=100), "EXPANDED_BYTES_LIMIT"),
        (EngineLimits(max_events=1), "EVENT_COUNT_LIMIT"),
    ]:
        with pytest.raises(EngineError, match=code):
            list(iter_source_events(local(path), limits))
    archive = tmp_path / "source.zip"
    make_zip(archive, [("one.log", b"a" * 100_000)], zipfile.ZIP_DEFLATED)
    for limits, code in [
        (EngineLimits(max_compression_ratio=2), "COMPRESSION_RATIO_LIMIT"),
        (EngineLimits(max_member_bytes=10), "MEMBER_BYTES_LIMIT"),
    ]:
        with pytest.raises(EngineError, match=code):
            list(iter_source_events(local(archive, kind="zip"), limits))
    make_zip(archive, [("one.log", b"a"), ("two.log", b"b")])
    with pytest.raises(EngineError, match="MEMBER_COUNT_LIMIT"):
        list(iter_source_events(local(archive, kind="zip"), EngineLimits(max_members=1)))


def test_tar_member_selection_and_safe_type_validation(tmp_path: Path) -> None:
    path = tmp_path / "source.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name in ("one.log", "ignored.txt"):
            info = tarfile.TarInfo(name)
            info.size = 5
            archive.addfile(info, io.BytesIO(b"data\n"))
    state = ScanProgress()
    events = list(
        iter_source_events(local(path, kind="tar.gz", member_globs=("*.log",)), progress=state)
    )
    assert len(events) == 1 and state.members == 2 and state.expanded_bytes == 10
    with tarfile.open(path, "w:gz") as archive:
        okay = tarfile.TarInfo("okay.log")
        okay.size = 5
        archive.addfile(okay, io.BytesIO(b"data\n"))
        link = tarfile.TarInfo("bad.log")
        link.type = tarfile.LNKTYPE
        link.linkname = "okay.log"
        archive.addfile(link)
    with pytest.raises(EngineError, match="UNSAFE_ARCHIVE_MEMBER_TYPE"):
        next(iter_source_events(local(path, kind="tar.gz")))


def test_tar_extension_metadata_is_bounded_before_internal_allocation(tmp_path: Path) -> None:
    path = tmp_path / "source.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        header = tarfile.TarInfo("pax-header")
        header.type = tarfile.XHDTYPE
        header.size = 100_000
        archive.addfile(header, io.BytesIO(b"x" * header.size))
    with pytest.raises(EngineError, match="ARCHIVE_METADATA_LIMIT"):
        list(iter_source_events(local(path, kind="tar.gz")))


def test_zip_embedded_nul_is_not_silently_stripped(tmp_path: Path) -> None:
    path = tmp_path / "source.zip"
    make_zip(path, [("aXb.log", b"data\n")])
    path.write_bytes(path.read_bytes().replace(b"aXb.log", b"a\0b.log"))
    with pytest.raises(EngineError, match="UNSAFE_ARCHIVE_PATH"):
        list(iter_source_events(local(path, kind="zip")))


def test_cancellation_and_deadline_report_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "capture.log"
    path.write_bytes(b"one\ntwo\nthree\n")
    token = CancellationToken()
    state = ScanProgress()
    iterator = iter_source_events(local(path), cancellation=token, progress=state)
    assert next(iterator)["raw_line"] == "one"
    token.cancel()
    with pytest.raises(EngineError, match="CANCELLED"):
        next(iterator)
    assert state.events == 1 and not state.source_complete
    moments = iter([0, 121])
    monkeypatch.setattr("inspector.log_engine.reader.time.monotonic", lambda: next(moments))
    with pytest.raises(EngineError, match="DEADLINE_EXCEEDED"):
        list(iter_source_events(local(path)))


def test_snapshot_boundary_excludes_appends_and_reports_unstable_source(tmp_path: Path) -> None:
    path = tmp_path / "capture.log"
    path.write_bytes(b"one\ntwo\n")
    state = ScanProgress()
    iterator = iter_source_events(local(path), progress=state)
    assert next(iterator)["raw_line"] == "one"
    with path.open("ab") as handle:
        handle.write(b"appended\n")
    assert next(iterator)["raw_line"] == "two"
    with pytest.raises(EngineError, match="SOURCE_UNSTABLE"):
        next(iterator)
    assert state.source_stable is False and state.source_complete is False


def test_actual_gzip_output_limit_includes_tar_padding(tmp_path: Path) -> None:
    path = tmp_path / "padded.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("tiny.log")
        member.size = 2
        archive.addfile(member, io.BytesIO(b"x\n"))
    with pytest.raises(EngineError, match="EXPANDED_BYTES_LIMIT"):
        list(iter_source_events(local(path, kind="tar.gz"), EngineLimits(max_expanded_bytes=5120)))
    with pytest.raises(EngineError, match="COMPRESSION_RATIO_LIMIT"):
        list(iter_source_events(local(path, kind="tar.gz"), EngineLimits(max_compression_ratio=1)))


def test_corrupt_ignored_zip_and_gzip_trailer_still_fail(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.zip"
    make_zip(path, [("ignored.txt", b"original-marker\n")])
    path.write_bytes(path.read_bytes().replace(b"original-marker", b"modified-marker"))
    with pytest.raises(EngineError, match="CORRUPT_ARCHIVE"):
        list(iter_source_events(local(path, kind="zip", member_globs=("*.log",))))
    path = tmp_path / "corrupt.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("tiny.log")
        member.size = 2
        archive.addfile(member, io.BytesIO(b"x\n"))
    data = bytearray(path.read_bytes())
    data[-8] ^= 1
    path.write_bytes(data)
    with pytest.raises(EngineError, match="CORRUPT_ARCHIVE"):
        list(iter_source_events(local(path, kind="tar.gz")))


def test_large_unicode_and_configured_single_byte_encoding(tmp_path: Path) -> None:
    path = tmp_path / "unicode.log"
    text = "2026-10-16T12:00:00Z " + "ąß界😀" * 15_000
    raw = (text + "\n").encode("utf-8")
    assert 65_536 < len(raw) < 262_144
    path.write_bytes(raw)
    event = next(iter_source_events(local(path)))
    assert event["raw_line"] == text and event["parse_status"] == "ok"
    assert event["source"]["byte_end"] == len(raw)
    path.write_bytes("2026-10-16T12:00:00Z café\n".encode("latin-1"))
    event = next(iter_source_events(local(path, encoding="latin-1")))
    assert event["raw_line"].endswith("café") and event["parse_status"] == "ok"
    with pytest.raises(EngineError, match="ENCODING_UNSUPPORTED"):
        list(iter_source_events(local(path, encoding="utf-16")))
    with pytest.raises(EngineError, match="ENCODING_UNSUPPORTED"):
        list(iter_source_events(local(path, encoding="nonexistent-encoding")))


@pytest.mark.parametrize(
    "options",
    [
        {"max_members": 0},
        {"max_line_bytes": 1.5},
        {"max_member_bytes": True},
        {"wall_seconds": float("nan")},
        {"wall_seconds": float("inf")},
        {"wall_seconds": 0},
    ],
)
def test_invalid_engine_limits_fail_closed(options: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        EngineLimits(**options)


def test_missing_member_and_empty_source_have_explicit_outcomes(tmp_path: Path) -> None:
    path = tmp_path / "empty.log"
    path.write_bytes(b"")
    progress = ScanProgress()
    assert list(iter_source_events(local(path), progress=progress)) == []
    assert progress.source_complete and progress.expanded_bytes == progress.events == 0
    path = tmp_path / "missing.zip"
    make_zip(path, [("present.log", b"data\n")])
    with pytest.raises(EngineError, match="ARCHIVE_MEMBER_UNAVAILABLE"):
        list(iter_source_events(local(path, kind="zip", archive_member="absent.log")))


def test_sparse_tar_header_is_rejected_before_sparse_metadata(tmp_path: Path) -> None:
    path = tmp_path / "sparse.tar.gz"
    with tarfile.open(path, "w:gz", format=tarfile.GNU_FORMAT) as archive:
        member = tarfile.TarInfo("sparse.log")
        member.type = tarfile.GNUTYPE_SPARSE
        archive.addfile(member)
    with pytest.raises(EngineError, match="UNSAFE_ARCHIVE_MEMBER_TYPE"):
        list(iter_source_events(local(path, kind="tar.gz")))


def test_zip_unix_directory_metadata_never_becomes_log_content(tmp_path: Path) -> None:
    path = tmp_path / "directory.zip"
    with zipfile.ZipFile(path, "w") as archive:
        directory = zipfile.ZipInfo("directory-without-slash")
        directory.external_attr = 0o040755 << 16
        archive.writestr(directory, b"directory marker, not a regular log\n")
    assert list(iter_source_events(local(path, kind="zip"))) == []


@pytest.mark.parametrize(
    "field,value,code",
    [
        (10, 10_001, "MEMBER_COUNT_LIMIT"),
        (12, 16 * 1024 * 1024 + 1, "ARCHIVE_METADATA_LIMIT"),
        (10, 65_535, "ZIP64_UNSUPPORTED"),
    ],
)
def test_zip_eocd_preflight_bounds_constructor_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: int, value: int, code: str
) -> None:
    path = tmp_path / "forged.zip"
    make_zip(path, [("source.log", b"data\n")])
    data = bytearray(path.read_bytes())
    position = data.rindex(b"PK\x05\x06")
    if field == 10:
        struct.pack_into("<H", data, position + 8, value)
    struct.pack_into("<H" if field == 10 else "<I", data, position + field, value)
    path.write_bytes(data)

    def forbidden_constructor(*args: Any, **kwargs: Any) -> None:
        pytest.fail("ZipFile must not allocate a member list before bounded preflight succeeds.")

    monkeypatch.setattr("inspector.log_engine.reader.zipfile.ZipFile", forbidden_constructor)
    with pytest.raises(EngineError, match=code):
        list(iter_source_events(local(path, kind="zip")))


def test_zip_eocd_forged_low_count_cannot_bypass_actual_member_limit(tmp_path: Path) -> None:
    path = tmp_path / "forged.zip"
    make_zip(path, [("one.log", b"one\n"), ("two.log", b"two\n")])
    data = bytearray(path.read_bytes())
    position = data.rindex(b"PK\x05\x06")
    struct.pack_into("<HH", data, position + 8, 1, 1)
    path.write_bytes(data)
    with pytest.raises(EngineError, match="MEMBER_COUNT_LIMIT"):
        list(iter_source_events(local(path, kind="zip"), EngineLimits(max_members=1)))
