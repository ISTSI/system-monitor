"""Executable oracle/fixture checks, NOT tests of an implemented application."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from reference_contracts import (  # noqa: E402
    event_sort_key, fixture_event_id, is_safe_archive_name, load_json,
    matches_filter, parse_timestamp, query_events, read_fixture_source,
    utc_microseconds, validate_filter, validate_project,
)


def specification(include=None, exclude=None, mode="any", case_sensitive=True):
    return {"include": [] if include is None else include, "exclude": [] if exclude is None else exclude,
            "include_mode": mode, "case_sensitive": case_sensitive}


class FilterContractTests(unittest.TestCase):
    def test_include_any(self):
        self.assertTrue(matches_filter("alpha beta", specification(["missing", "beta"])))

    def test_include_all(self):
        self.assertFalse(matches_filter("alpha beta", specification(["alpha", "missing"], mode="all")))

    def test_exclusion_wins(self):
        self.assertFalse(matches_filter("alpha beta", specification(["alpha"], ["beta"])))

    def test_empty_include_matches(self):
        self.assertTrue(matches_filter("anything", specification([""])))

    def test_empty_exclusion_ignored(self):
        self.assertTrue(matches_filter("anything", specification(exclude=[""])))

    def test_whitespace_is_literal(self):
        self.assertFalse(matches_filter("foo", specification([" foo "])))
        self.assertTrue(matches_filter("x foo y", specification([" foo "])))

    def test_metacharacters_are_literal(self):
        self.assertTrue(matches_filter("a.*b [x] 100% _", specification(["a.*b [x] 100% _"])))
        self.assertFalse(matches_filter("axxxb", specification(["a.*b"])))

    def test_unicode_casefold(self):
        self.assertTrue(matches_filter("Straße", specification(["STRASSE"], case_sensitive=False)))
        self.assertFalse(matches_filter("Straße", specification(["STRASSE"])))

    def test_filter_limit(self):
        with self.assertRaises(ValueError):
            validate_filter(specification(["x"] * 21))
        with self.assertRaises(ValueError):
            validate_filter(specification(["x" * 513]))

    def test_invalid_filter_type(self):
        value = specification(); value["case_sensitive"] = "false"
        with self.assertRaises(ValueError):
            validate_filter(value)


class TimestampContractTests(unittest.TestCase):
    def test_microseconds_are_exact(self):
        self.assertEqual(utc_microseconds("2026-10-16T12:00:00.000001Z") - utc_microseconds("2026-10-16T12:00:00Z"), 1)

    def test_supported_utc_offset(self):
        self.assertEqual(utc_microseconds("2026-10-16T12:00:00Z"), utc_microseconds("2026-10-16T12:00:00+00:00"))

    def test_nonzero_offset_rejected(self):
        with self.assertRaises(ValueError):
            utc_microseconds("2026-10-16T12:00:00+02:00")

    def test_precision_not_silently_truncated(self):
        self.assertEqual(parse_timestamp("2026-10-16T12:00:00.1234567Z INFO message"), (None, None, None))

    def test_fixed_width_utc(self):
        result = parse_timestamp("2026-10-16 12:00:00,123 INFO", kind="fixed_width", width=23, timestamp_format="%Y-%m-%d %H:%M:%S,%f")
        self.assertEqual(result[1], "2026-10-16T12:00:00.123000Z")

    def test_invalid_time_visible_as_null(self):
        self.assertEqual(parse_timestamp("NOT_A_TIMESTAMP INFO text"), (None, None, None))
        self.assertEqual(parse_timestamp("2026-99-99T12:00:00Z INFO text"), (None, None, None))


class FixtureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = load_json("fixtures/expected/events.json")
        cls.labels = load_json("fixtures/expected/labels.json")
        cls.cases = load_json("fixtures/expected/query-cases.json")
        cls.sources = load_json("fixtures/source-manifest.json")["sources"]

    def test_all_golden_queries(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                actual = [e["event_id"] for e in query_events(self.events, case["request"])]
                self.assertEqual(actual, case["expected_event_ids"])

    def test_source_member_checksums(self):
        for source in self.sources:
            with self.subTest(source=source["source_revision_id"]):
                self.assertEqual(hashlib.sha256(read_fixture_source(source)).hexdigest(), source["content_sha256"])

    def test_every_event_matches_source_bytes(self):
        data = {s["source_revision_id"]: read_fixture_source(s) for s in self.sources}
        for event in self.events:
            source = event["source"]
            raw = data[source["source_revision_id"]][source["byte_start"]:source["byte_end"]]
            self.assertEqual(raw.decode("utf-8").removesuffix("\n").removesuffix("\r"), event["raw_line"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source["content_sha256"])
            self.assertEqual(fixture_event_id(event), event["event_id"])

    def test_duplicate_messages_are_distinct_events(self):
        by_id = {e["event_id"]: e for e in self.events}
        first, second = [by_id[self.labels[n]] for n in ("ingest-repeat-1", "ingest-repeat-2")]
        self.assertEqual(first["raw_line"], second["raw_line"])
        self.assertNotEqual(first["event_id"], second["event_id"])
        self.assertNotEqual(first["source"]["byte_start"], second["source"]["byte_start"])

    def test_invalid_timestamp_not_in_time_query(self):
        self.assertEqual(sum(e["timestamp_us"] is None for e in self.events), 1)
        for case in self.cases:
            self.assertNotIn(self.labels["ingest-invalid"], case["expected_event_ids"])

    def test_exact_correlation_differs_from_substring(self):
        case = load_json("fixtures/expected/correlation-exact.json")
        lower, upper = utc_microseconds(case["from"]), utc_microseconds(case["to"])
        actual = sorted([e for e in self.events if e["timestamp_us"] is not None
                         and lower <= e["timestamp_us"] < upper
                         and e["process_id"] in case["process_ids"]
                         and e["metadata"].get(case["field"]) == case["value"]], key=event_sort_key)
        self.assertEqual([e["event_id"] for e in actual], case["expected_event_ids"])
        self.assertNotIn(self.labels["audit-similar-id"], case["expected_event_ids"])

    def test_invalid_interval_rejected(self):
        request = copy.deepcopy(self.cases[0]["request"]); request["to"] = request["from"]
        with self.assertRaises(ValueError):
            query_events(self.events, request)

    def test_all_expected_timestamps_match_parser(self):
        for event in self.events:
            parsed = parse_timestamp(event["raw_line"])
            self.assertEqual(parsed[1], event["timestamp_utc"])
            self.assertEqual(parsed[2], event["timestamp_us"])

    def test_line_endings_and_partial_line_fixtures(self):
        crlf = (ROOT / "fixtures/logs/crlf.log").read_bytes()
        self.assertEqual(crlf.count(b"\r\n"), 2)
        partial = (ROOT / "fixtures/logs/partial-write.log").read_bytes()
        self.assertEqual(partial.count(b"\n"), 1)
        self.assertFalse(partial.endswith(b"\n"))

    def test_small_load_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new"
            completed = subprocess.run([sys.executable, str(ROOT / "tools/generate_load_fixture.py"),
                                        "--output-dir", str(output), "--size-mib", "0.01", "--processes", "2"],
                                       check=True, capture_output=True, text=True, timeout=15)
            self.assertIn("total_bytes", completed.stdout)
            manifest = json.loads((output / "generated-manifest.json").read_text())
            self.assertGreaterEqual(manifest["total_bytes"], int(0.01 * 1024 * 1024))
            self.assertEqual(len(manifest["sources"]), 2)
            repeated = subprocess.run([sys.executable, str(ROOT / "tools/generate_load_fixture.py"),
                                       "--output-dir", str(output), "--size-mib", "0.01"],
                                      capture_output=True, text=True, timeout=15)
            self.assertNotEqual(repeated.returncode, 0)


class ConfigurationAndArchiveContractTests(unittest.TestCase):
    def test_valid_project(self):
        validate_project(load_json("examples/project.example.json"))

    def test_duplicate_id_rejected(self):
        value = load_json("examples/project.example.json")
        value["servers"][1]["id"] = value["servers"][0]["id"]
        with self.assertRaises(ValueError):
            validate_project(value)

    def test_missing_parent_rejected(self):
        value = load_json("examples/project.example.json")
        value["processes"][0]["server_id"] = "missing"
        with self.assertRaises(ValueError):
            validate_project(value)

    def test_jump_cycle_rejected(self):
        value = load_json("examples/project.example.json")
        value["connections"][0]["jump_connection_id"] = "c-core"
        with self.assertRaises(ValueError):
            validate_project(value)

    def test_path_escape_rejected(self):
        value = load_json("examples/project.example.json")
        value["processes"][0]["log_source"]["active_path"] = "/var/log/inspector-demo/../../outside"
        with self.assertRaises(ValueError):
            validate_project(value)

    def test_secret_in_config_rejected(self):
        value = load_json("examples/project.example.json")
        value["connections"][0]["password"] = "SYNTHETIC-NOT-A-REAL-SECRET"
        with self.assertRaises(ValueError):
            validate_project(value)

    def test_archive_paths(self):
        for name in ("../outside", "/absolute", "C:/drive", "logs/../../outside", "..\\outside", "a\x00b"):
            self.assertFalse(is_safe_archive_name(name))
        self.assertTrue(is_safe_archive_name("logs/app.log.2026-10-15"))

    def test_traversal_zip_is_unsafe(self):
        with zipfile.ZipFile(ROOT / "fixtures/rejected/traversal.zip") as archive:
            self.assertFalse(is_safe_archive_name(archive.infolist()[0].filename))

    def test_symlink_tar_is_unsafe(self):
        with tarfile.open(ROOT / "fixtures/rejected/symlink.tar.gz", "r:gz") as archive:
            info = archive.getmembers()[0]
            self.assertTrue(info.issym())
            self.assertFalse(info.isfile())

    def test_corrupt_zip_rejected(self):
        with self.assertRaises(zipfile.BadZipFile):
            with zipfile.ZipFile(ROOT / "fixtures/rejected/corrupt.zip"):
                pass


if __name__ == "__main__":
    unittest.main()
