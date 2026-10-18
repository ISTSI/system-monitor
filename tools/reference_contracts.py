"""Small fixture oracle for this specification package, not production app code.

No networking, remote execution, persistence service or UI is implemented here.
Codex must implement and test the application independently against these results.
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
ISO_TOKEN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$"
)
ISO_PREFIX = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00))(?=$|[ \t])"
)


def load_json(relative_path: str) -> Any:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def utc_microseconds(text: str) -> int:
    """Parse a supported UTC time exactly, with no floating-point rounding."""
    if not isinstance(text, str) or not ISO_TOKEN.fullmatch(text):
        raise ValueError("Expected full UTC timestamp with at most six fractional digits")
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    delta = value - EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def parse_timestamp(
    line: str, *, kind: str = "iso8601_prefix", width: int | None = None,
    timestamp_format: str | None = None,
) -> tuple[str | None, str | None, int | None]:
    """Return original token, canonical UTC and exact microseconds or nulls."""
    try:
        if kind == "iso8601_prefix":
            match = ISO_PREFIX.match(line)
            if match is None:
                return None, None, None
            original = match.group(1)
            value = datetime.fromisoformat(original.replace("Z", "+00:00"))
            micros = utc_microseconds(original)
        elif kind == "fixed_width":
            if width is None or not 1 <= width <= 64 or not timestamp_format:
                raise ValueError("A bounded width and format are required")
            original = line[:width]
            value = datetime.strptime(original, timestamp_format)
            if value.tzinfo is not None and value.utcoffset().total_seconds() != 0:
                return None, None, None
            value = value.replace(tzinfo=timezone.utc)
            delta = value - EPOCH
            micros = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
        else:
            raise ValueError("Unsupported parser strategy")
        return original, value.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), micros
    except (ValueError, OverflowError):
        return None, None, None


def validate_filter(value: dict[str, Any]) -> None:
    expected = {"include", "exclude", "include_mode", "case_sensitive"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("Filter fields do not match the contract")
    if value["include_mode"] not in ("any", "all"):
        raise ValueError("Unknown include mode")
    if not isinstance(value["case_sensitive"], bool):
        raise ValueError("case_sensitive must be a boolean")
    for field in ("include", "exclude"):
        terms = value[field]
        if not isinstance(terms, list) or len(terms) > 20:
            raise ValueError("At most 20 terms are allowed per field")
        if any(not isinstance(term, str) or len(term) > 512 for term in terms):
            raise ValueError("Filter terms must be strings of at most 512 characters")


def matches_filter(raw_line: str, specification: dict[str, Any]) -> bool:
    validate_filter(specification)
    # Ignore only exactly empty terms. Whitespace can be the intended literal.
    include = [term for term in specification["include"] if term != ""]
    exclude = [term for term in specification["exclude"] if term != ""]
    if not specification["case_sensitive"]:
        raw_line = raw_line.casefold()
        include = [term.casefold() for term in include]
        exclude = [term.casefold() for term in exclude]
    if any(term in raw_line for term in exclude):
        return False
    if not include:
        return True
    predicate = all if specification["include_mode"] == "all" else any
    return predicate(term in raw_line for term in include)


def event_sort_key(event: dict[str, Any]) -> tuple[Any, ...]:
    source = event["source"]
    ordinal = source["member_ordinal"]
    return (
        event["timestamp_us"], event["process_id"], source["source_revision_id"],
        -1 if ordinal is None else ordinal, source["byte_start"], event["event_id"],
    )


def query_events(events: Iterable[dict[str, Any]], request: dict[str, Any]) -> list[dict[str, Any]]:
    lower, upper = utc_microseconds(request["from"]), utc_microseconds(request["to"])
    if lower >= upper:
        raise ValueError("from must be strictly before to")
    selected = set(request["process_ids"])
    if not selected:
        raise ValueError("At least one process is required")
    validate_filter(request["filter"])
    per_process = request["per_process_filters"]
    if not set(per_process).issubset(selected):
        raise ValueError("Per-process filter refers to an unselected process")
    for specification in per_process.values():
        validate_filter(specification)
    result = []
    for event in events:
        timestamp = event["timestamp_us"]
        if event["process_id"] not in selected or timestamp is None:
            continue
        if not lower <= timestamp < upper:
            continue
        if not matches_filter(event["raw_line"], request["filter"]):
            continue
        specific = per_process.get(event["process_id"])
        if specific is not None and not matches_filter(event["raw_line"], specific):
            continue
        result.append(event)
    return sorted(result, key=event_sort_key)


def is_safe_archive_name(name: str) -> bool:
    if not name or "\\" in name or any(ord(char) < 32 for char in name):
        return False
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        return False
    return ".." not in PurePosixPath(name).parts


def read_fixture_source(source: dict[str, Any], *, limit: int = 1_048_576) -> bytes:
    """Read a SMALL, approved local fixture member, without archive extraction."""
    candidate = (ROOT / source["fixture_path"]).resolve()
    if not candidate.is_relative_to(ROOT / "fixtures"):
        raise ValueError("Fixture path escapes the fixture directory")
    kind = source["kind"]
    if kind == "plain":
        with candidate.open("rb") as handle:
            data = handle.read(limit + 1)
    elif kind == "zip":
        with zipfile.ZipFile(candidate) as archive:
            info = archive.infolist()[source["member_ordinal"]]
            mode = (info.external_attr >> 16) & 0xFFFF
            if (info.filename != source["archive_member"] or not is_safe_archive_name(info.filename)
                    or info.is_dir() or stat.S_ISLNK(mode)):
                raise ValueError("Unsafe or mismatched ZIP fixture member")
            with archive.open(info) as handle:
                data = handle.read(limit + 1)
    elif kind == "tar.gz":
        with tarfile.open(candidate, "r:gz") as archive:
            info = archive.getmembers()[source["member_ordinal"]]
            if info.name != source["archive_member"] or not is_safe_archive_name(info.name) or not info.isfile():
                raise ValueError("Unsafe or mismatched TAR fixture member")
            handle = archive.extractfile(info)
            if handle is None:
                raise ValueError("Fixture member has no readable data")
            with handle:
                data = handle.read(limit + 1)
    else:
        raise ValueError("Unknown fixture source type")
    if len(data) > limit:
        raise ValueError("Small fixture reader limit exceeded")
    return data


def validate_project(project: dict[str, Any]) -> None:
    """Check selected cross-reference invariants; full structure uses JSON Schema."""
    if project.get("schema_version") != "2.0":
        raise ValueError("Unsupported schema version")
    entities: dict[str, dict[str, dict[str, Any]]] = {}
    global_ids: set[str] = set()
    for kind in ("subsystems", "connections", "servers", "processes", "parsers", "flows", "views"):
        records = project[kind]
        ids = [record["id"] for record in records]
        if len(set(ids)) != len(ids) or any(identifier in global_ids for identifier in ids):
            raise ValueError("Duplicate entity ID")
        global_ids.update(ids)
        if kind in ("subsystems", "servers", "processes"):
            names = [record["name"].casefold() for record in records]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate entity name")
        entities[kind] = {record["id"]: record for record in records}
    for connection in project["connections"]:
        jump = connection["jump_connection_id"]
        if jump is not None:
            if jump == connection["id"] or jump not in entities["connections"]:
                raise ValueError("Invalid jump reference")
            if entities["connections"][jump]["jump_connection_id"] is not None:
                raise ValueError("Only one jump hop is supported")
    for server in project["servers"]:
        if server["subsystem_id"] not in entities["subsystems"] or (server["connection_id"] is not None and server["connection_id"] not in entities["connections"]):
            raise ValueError("Missing server parent or connection")
    for process in project["processes"]:
        if process["server_id"] not in entities["servers"]:
            raise ValueError("Missing process server")
        source = process["log_source"]
        if source["parser_id"] not in entities["parsers"]:
            raise ValueError("Missing parser")
        connection_id = entities["servers"][process["server_id"]]["connection_id"]
        connection = entities["connections"][connection_id] if connection_id is not None else None
        paths = [source["active_path"], *source["rotated_patterns"], *[a["path_pattern"] for a in source["archives"]]]
        for path in paths:
            if (not path.startswith("/") or ".." in PurePosixPath(path).parts
                    or any(ord(char) < 32 for char in path)):
                raise ValueError("Unsafe remote path")
            if connection is not None and not any(path == root or path.startswith(root.rstrip("/") + "/") for root in connection["allowed_log_roots"]):
                raise ValueError("Remote path outside proposed roots")
    for flow in project["flows"]:
        if flow["source_process_id"] not in entities["processes"] or flow["target_process_id"] not in entities["processes"]:
            raise ValueError("Missing flow endpoint")
    model_ids = set(entities["subsystems"]) | set(entities["servers"]) | set(entities["processes"])
    for view in project["views"]:
        node_ids = [node["element_id"] for node in view["nodes"]]
        if len(node_ids) != len(set(node_ids)) or not set(node_ids).issubset(model_ids):
            raise ValueError("Invalid view nodes")
        for node in view["nodes"]:
            element = node["element_id"]
            if element in entities["processes"] and entities["processes"][element]["server_id"] not in node_ids:
                raise ValueError("Process view is missing server ancestor")
            if element in entities["servers"] and entities["servers"][element]["subsystem_id"] not in node_ids:
                raise ValueError("Server view is missing subsystem ancestor")
        if not set(view["flow_ids"]).issubset(entities["flows"]):
            raise ValueError("Unknown view flow")
    def reject_secrets(value: Any) -> None:
        if isinstance(value, dict):
            if set(value) & {"password", "ansible_password", "private_key", "master_key", "ciphertext"}:
                raise ValueError("Secret material is not permitted in project config")
            for child in value.values():
                reject_secrets(child)
        elif isinstance(value, list):
            for child in value:
                reject_secrets(child)
    reject_secrets(project)


def fixture_event_id(event: dict[str, Any]) -> str:
    source = event["source"]
    fields = [event["process_id"], source["source_revision_id"], source["archive_member"] or "",
              str(source["member_ordinal"] if source["member_ordinal"] is not None else -1),
              str(source["byte_start"]), str(source["byte_end"])]
    return "evt-" + hashlib.sha256("\0".join(fields).encode("utf-8")).hexdigest()
