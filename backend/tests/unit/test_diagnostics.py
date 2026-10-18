"""Parser previews must agree with collected event timestamps and fail safely."""

import copy
import json
from pathlib import Path

import pytest

from inspector.diagnostics import preview
from inspector.errors import DomainError

ROOT = Path(__file__).resolve().parents[3]


def document():
    return json.loads((ROOT / "examples/project.example.json").read_text("utf-8"))


def test_preview_uses_exact_utc_and_literal_metadata_preserving_original_text():
    config = document()
    parser = copy.deepcopy(config["parsers"][0])
    parser["timestamp"] = {"kind": "iso8601_prefix", "naive_timezone": "UTC"}
    parser["correlation_markers"] = [
        {"key": "request_id", "prefix": "request_id=", "terminators": " "}
    ]
    sample = "2026-10-16T12:00:00.123456Z INFO request_id=REQ-0042 <script>\ncontinuation\n2026-02-30T12:00:00Z bad"
    before = copy.deepcopy(config)
    rows = preview(config, parser, sample)
    assert rows[0]["timestamp_utc"] == "2026-10-16T12:00:00.123456Z"
    assert rows[0]["timestamp_us"] == "1792152000123456"
    assert rows[0]["metadata"] == {"request_id": "REQ-0042"}
    assert rows[0]["original_line"].endswith("<script>")
    assert rows[1]["timestamp_us"] is None and rows[1]["error"]
    assert rows[2]["timestamp_original"] == "2026-02-30T12:00:00Z"
    assert rows[2]["timestamp_utc"] is None and rows[2]["error"]
    assert config == before


def test_fixed_width_preview_shares_microsecond_contract():
    config = document()
    parser = copy.deepcopy(config["parsers"][0])
    parser["timestamp"] = {
        "kind": "fixed_width",
        "width": 23,
        "format": "%Y-%m-%d %H:%M:%S,%f",
        "naive_timezone": "UTC",
    }
    rows = preview(config, parser, "2026-10-16 12:00:00,123 INFO\ninvalid")
    assert rows[0]["timestamp_utc"] == "2026-10-16T12:00:00.123000Z"
    assert rows[0]["timestamp_us"] == "1792152000123000"
    assert rows[1]["timestamp_us"] is None


def test_preview_uses_collection_physical_lines_and_preserves_unicode_separators():
    config = document()
    parser = copy.deepcopy(config["parsers"][0])
    sample = "2026-10-16T12:00:00Z first\u0085still-first\u2028still-first\vstill-first\rnot-an-end\r\nsecond\nlast\r"
    rows = preview(config, parser, sample)
    assert len(rows) == 3
    assert rows[0]["original_line"] == sample.split("\r\n", 1)[0]
    assert rows[1]["original_line"] == "second"
    assert rows[2]["original_line"] == "last\r"
    assert len(preview(config, parser, "one\n")) == 1
    assert len(preview(config, parser, "\n")) == 1
    assert preview(config, parser, "") == []


def test_preview_rejects_invalid_unicode_with_a_sanitized_diagnostic():
    config = document()
    with pytest.raises(DomainError) as caught:
        preview(config, config["parsers"][0], "sensitive-value\ud800")
    assert caught.value.code == "PARSER_SAMPLE_ENCODING"
    assert "sensitive-value" not in caught.value.message


@pytest.mark.parametrize(
    "sample",
    ["x" * 4097, "\n" * 101, "é" * 32769],
    ids=["line-bytes", "line-count", "total-utf8-bytes"],
)
def test_preview_rejects_actual_line_count_line_bytes_and_total_bytes(sample):
    config = document()
    with pytest.raises(DomainError) as caught:
        preview(config, config["parsers"][0], sample)
    assert caught.value.code == "PARSER_SAMPLE_LIMIT"
    assert sample not in caught.value.message


def test_preview_rejects_executable_or_incomplete_draft_without_echoing_sample():
    config = document()
    parser = copy.deepcopy(config["parsers"][0])
    parser["timestamp"] = {
        "kind": "fixed_width",
        "width": 2,
        "format": "%H",
        "naive_timezone": "UTC",
    }
    with pytest.raises(DomainError) as caught:
        preview(config, parser, "anonymised-sample")
    assert caught.value.code == "INVALID_PROJECT"
    assert "anonymised-sample" not in caught.value.message
