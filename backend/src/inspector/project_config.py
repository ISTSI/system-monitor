"""Bounded project interchange and semantic validation, without network or approvals.

The authoritative interchange schemas are bundled with the wheel. Credential IDs and
allowed roots are proposals only; this module never creates local credential bindings,
target approvals, or SSH trust. Runtime configuration always comes from MariaDB.
"""

import codecs
import copy
import json
import math
import re
import unicodedata
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import unquote

import yaml
from jsonschema import Draft202012Validator

from inspector.domain import ID_PATTERN
from inspector.errors import DomainError

MAX_CONFIG_BYTES = 10 * 1024 * 1024
MAX_DEPTH = 32
MAX_TREE_NODES = 200_000
MAX_ENTITIES = 5_000
MAX_GEOMETRY = 10_000_000
MAX_PROJECT_DESCRIPTION = 10_000
COLLECTIONS = ("subsystems", "connections", "servers", "processes", "parsers", "flows", "views")
_CONTRACTS = Path(__file__).parent / "contracts"
_VALIDATORS = {
    version: Draft202012Validator(json.loads((_CONTRACTS / filename).read_text(encoding="utf-8")))
    for version, filename in (("2.0", "project.schema.json"), ("1.0", "project-v1.schema.json"))
}
_PATH_FIELDS = re.compile(r"[\x00-\x1f\x7f-\x9f$`~{}\\;|&<>]")
_GLOB = re.compile(r"[*?\[\]]")
_HTML = re.compile(r"<!--|<\s*/?\s*[A-Za-z][A-Za-z0-9-]*(?:\s[^>]*|\s*/?)>", re.DOTALL)
_IMAGE = re.compile(r"!\s*\[|<\s*(?:img|iframe|object|embed)\b", re.IGNORECASE)
_DANGEROUS_LINK = re.compile(r"(?:javascript|vbscript|data|file)\s*:", re.IGNORECASE)
_FORMAT_DIRECTIVES = set("YmdHMSfz%")
_SUPPORTED_ENCODINGS = {"utf-8", "utf-8-sig", "ascii", "iso8859-1", "cp1250", "cp1252"}


def _fail(path: str, message: str) -> NoReturn:
    raise DomainError("INVALID_PROJECT", f"{path}: {message}", 422)


def _safe_path(parts: Any) -> str:
    """Only schema field names and integer indices belong in diagnostics."""
    result = "configuration"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        elif isinstance(part, str) and re.fullmatch(r"[a-z_]{1,64}", part):
            result += "." + part
        else:
            result += ".field"
    return result


class _ProjectLoader(yaml.SafeLoader):
    pass


def _yaml_mapping(loader: _ProjectLoader, node: yaml.MappingNode) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            _fail(
                f"configuration line {key_node.start_mark.line + 1}",
                "duplicate or non-string mapping key.",
            )
        result[key] = loader.construct_object(value_node)
    return result


_ProjectLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _yaml_mapping)


def _json_mapping(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("configuration", "duplicate JSON mapping key.")
        result[key] = value
    return result


def _nonfinite_json(_value: str) -> NoReturn:
    _fail("configuration", "non-finite numbers are unsupported.")


def _preflight_json(content: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for char in content:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                _fail("configuration", "nesting exceeds limit.")
        elif char in "]}":
            depth -= 1


def _preflight_yaml(content: str) -> None:
    depth = 0
    count = 0
    for event in yaml.parse(content, Loader=_ProjectLoader):
        count += 1
        if count > MAX_TREE_NODES * 2:
            _fail("configuration", "item count exceeds limit.")
        if isinstance(event, yaml.events.AliasEvent) or getattr(event, "anchor", None):
            _fail("configuration", "YAML anchors and aliases are unsupported.")
        if isinstance(event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)):
            depth += 1
            if depth > MAX_DEPTH:
                _fail("configuration", "nesting exceeds limit.")
        elif isinstance(event, (yaml.events.MappingEndEvent, yaml.events.SequenceEndEvent)):
            depth -= 1


def _check_tree(config: Any) -> None:
    stack: list[tuple[Any, int, tuple[Any, ...]]] = [(config, 0, ())]
    count = 0
    seen: set[int] = set()
    byte_count = 0
    while stack:
        value, depth, path = stack.pop()
        count += 1
        if count > MAX_TREE_NODES:
            _fail("configuration", "item count exceeds limit.")
        if depth > MAX_DEPTH:
            _fail("configuration", "nesting exceeds limit.")
        if isinstance(value, (dict, list)):
            if id(value) in seen:
                _fail(_safe_path(path), "shared or recursive structures are unsupported.")
            seen.add(id(value))
            if isinstance(value, dict):
                for key, item in value.items():
                    if not isinstance(key, str):
                        _fail(_safe_path(path), "mapping keys must be strings.")
                    try:
                        byte_count += len(key.encode("utf-8"))
                    except UnicodeError:
                        _fail(_safe_path(path), "invalid Unicode mapping key.")
                    stack.append((item, depth + 1, (*path, key)))
            else:
                stack.extend((item, depth + 1, (*path, index)) for index, item in enumerate(value))
        elif isinstance(value, str):
            try:
                byte_count += len(value.encode("utf-8"))
            except UnicodeError:
                _fail(_safe_path(path), "invalid Unicode text.")
        elif isinstance(value, float):
            if not math.isfinite(value):
                _fail(_safe_path(path), "finite number required.")
        elif value is not None and not isinstance(value, (bool, int)):
            _fail(_safe_path(path), "JSON-compatible scalar required.")
        if byte_count > MAX_CONFIG_BYTES:
            _fail("configuration", "content exceeds 10 MiB limit.")


def _schema(config: dict[str, Any], version: str) -> None:
    error = next(_VALIDATORS[version].iter_errors(config), None)
    if error is not None:
        _fail(_safe_path(error.absolute_path), "invalid, missing, or unknown field.")


def _serialized_size(config: dict[str, Any]) -> None:
    try:
        content = json.dumps(config, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(content.encode("utf-8")) > MAX_CONFIG_BYTES:
            _fail("configuration", "serialized content exceeds 10 MiB limit.")
    except (ValueError, UnicodeError, TypeError):
        _fail("configuration", "invalid JSON-compatible content.")


def parse_config(content: str, format: str) -> tuple[dict[str, Any], list[str]]:
    """Parse and validate a bounded upload, visibly converting legacy v1 input."""
    try:
        if len(content.encode("utf-8")) > MAX_CONFIG_BYTES:
            _fail("configuration", "upload exceeds 10 MiB limit.")
        if format.lower() == "json":
            _preflight_json(content)
            config = json.loads(
                content, object_pairs_hook=_json_mapping, parse_constant=_nonfinite_json
            )
        elif format.lower() in {"yaml", "yml"}:
            _preflight_yaml(content)
            config = yaml.load(content, Loader=_ProjectLoader)
        else:
            _fail("configuration", "choose JSON or YAML format.")
    except json.JSONDecodeError as error:
        _fail(f"configuration line {error.lineno} column {error.colno}", "invalid JSON.")
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = f" line {mark.line + 1} column {mark.column + 1}" if mark else ""
        _fail(f"configuration{location}", "invalid or unsupported YAML.")
    except (UnicodeError, RecursionError, ValueError):
        _fail("configuration", "invalid or excessively nested text.")
    if not isinstance(config, dict):
        _fail("configuration", "project object required.")
    _check_tree(config)
    warnings: list[str] = []
    if config.get("schema_version") == "1.0":
        _schema(config, "1.0")
        config = copy.deepcopy(config)
        config["schema_version"] = "2.0"
        config["settings"]["ui"].pop("theme", None)
        warnings.append(
            "Converted schema 1.0 to 2.0; removed legacy theme. Account and global appearance remain unchanged."
        )
    validate_project(config)
    if config["connections"]:
        warnings.append(
            "Credential references remain unresolved. Import does not create credential bindings, enable targets, or trust SSH host keys."
        )
        if any(connection["allowed_log_roots"] for connection in config["connections"]):
            warnings.append(
                "Allowed log roots are proposals requiring separate local Administrator approval."
            )
    return config, warnings


def _plain_name(value: str, path: str) -> None:
    if not value.strip() or any(unicodedata.category(char) == "Cc" for char in value):
        _fail(path, "nonblank name without control characters required.")


def _markdown(value: str, path: str) -> None:
    # Documentation is rendered again with a no-HTML/no-assets renderer in the UI.
    # Refusing assets at import gives a useful field error before anything is saved.
    decoded = unquote(unescape(value))
    normalized = "".join(char for char in decoded if ord(char) >= 32 and ord(char) != 127)
    if _HTML.search(value) or _IMAGE.search(value) or _DANGEROUS_LINK.search(normalized):
        _fail(path, "raw HTML, image assets, and unsafe URL schemes are unsupported in Markdown.")


def _linux_path(value: str, path: str, *, pattern: bool = False, member: bool = False) -> None:
    parts = value.split("/")
    if (
        not value
        or _PATH_FIELDS.search(value)
        or any(part in {".", ".."} for part in parts)
        or (not member and (not value.startswith("/") or value.startswith("//") or value == "/"))
        or (member and (value.startswith("/") or re.match(r"^[A-Za-z]:", value)))
        or (not pattern and _GLOB.search(value))
    ):
        _fail(
            path,
            "safe relative archive member required."
            if member
            else "safe absolute Linux path required.",
        )
    if pattern:
        # Ordinary filename and member globs are data; shell expansion is never used.
        if value.count("[") != value.count("]"):
            _fail(path, "unbalanced glob character class.")


def _within_roots(value: str, roots: list[str], path: str) -> None:
    if not any(value.startswith(root.rstrip("/") + "/") for root in roots):
        _fail(path, "path must be below a proposed connection log root.")


def _timestamp(timestamp: dict[str, Any], path: str) -> None:
    if timestamp["kind"] != "fixed_width":
        return
    value = timestamp["format"]
    directives: set[str] = set()
    index = 0
    while index < len(value):
        if value[index] == "%":
            index += 1
            if index == len(value) or value[index] not in _FORMAT_DIRECTIVES:
                _fail(path + ".format", "unsupported timestamp directive.")
            directives.add(value[index])
        index += 1
    if not set("YmdHMS") <= directives:
        _fail(path + ".format", "full year, month, day, hour, minute, and second required.")
    # Verify the format is accepted by the same standard-library parser used by
    # the later log engine. Fractional seconds may contain one to six digits.
    try:
        probe = datetime(2026, 10, 17, 12, 34, 56, 123456, tzinfo=UTC).strftime(value)
        datetime.strptime(probe, value)
    except (ValueError, OverflowError, re.error):
        _fail(path + ".format", "unsupported timestamp format.")
    minimum_width = len(probe) - (5 if "f" in directives else 0)
    if not minimum_width <= timestamp["width"] <= len(probe):
        _fail(path + ".width", "width is incompatible with timestamp format.")


def validate_project(config: dict[str, Any]) -> None:
    """Validate one project only; callers enforce route identity and revisions."""
    _check_tree(config)
    _serialized_size(config)
    _schema(config, "2.0")
    if re.fullmatch(ID_PATTERN, config["project"]["id"]) is None:
        _fail("project.id", "invalid identifier.")
    _plain_name(config["project"]["name"], "project.name")
    if len(config["project"]["description"]) > MAX_PROJECT_DESCRIPTION:
        _fail("project.description", "description exceeds 10000 character limit.")
    _markdown(config["project"]["description"], "project.description")
    _plain_name(config["settings"]["ui"]["product_name"], "settings.ui.product_name")
    records: dict[str, dict[str, Any]] = {}
    all_ids: set[str] = set()
    count = sum(len(config[kind]) for kind in COLLECTIONS)
    if count > MAX_ENTITIES:
        _fail("configuration", "entity count exceeds limit.")
    for kind in COLLECTIONS:
        ids: dict[str, Any] = {}
        names: set[str] = set()
        for index, record in enumerate(config[kind]):
            path = f"{kind}[{index}]"
            if re.fullmatch(ID_PATTERN, record["id"]) is None:
                _fail(path + ".id", "invalid identifier.")
            if record["id"] in all_ids:
                _fail(path + ".id", "duplicate ID in this system.")
            all_ids.add(record["id"])
            ids[record["id"]] = record
            _plain_name(record["name"], path + ".name")
            folded = record["name"].casefold()
            if folded in names:
                _fail(path + ".name", "duplicate name in this system and entity kind.")
            names.add(folded)
            if "description" in record:
                _markdown(record["description"], path + ".description")
        records[kind] = ids
    elements: dict[str, Any] = {}
    for kind in ("subsystems", "servers", "processes"):
        for index, record in enumerate(config[kind]):
            if record["id"] in elements:
                _fail(
                    f"{kind}[{index}].id", "diagram element IDs must be unique across entity kinds."
                )
            elements[record["id"]] = record

    def reference(kind: str, identifier: str, path: str) -> dict[str, Any]:
        if identifier not in records[kind]:
            _fail(path, "reference does not exist in this system.")
        return records[kind][identifier]  # type: ignore[no-any-return]

    for index, connection in enumerate(config["connections"]):
        path = f"connections[{index}]"
        for field in ("host", "username"):
            _plain_name(connection[field], path + "." + field)
        if re.fullmatch(ID_PATTERN, connection["credential_ref"]) is None:
            _fail(path + ".credential_ref", "invalid credential reference.")
        if any(char.isspace() for char in connection["host"]) or any(
            char in connection["host"] for char in "/\\$`{};|&<>"
        ):
            _fail(path + ".host", "literal hostname or address required.")
        jump_id = connection["jump_connection_id"]
        if jump_id is not None:
            jump = reference("connections", jump_id, path + ".jump_connection_id")
            if jump_id == connection["id"] or jump["jump_connection_id"] is not None:
                _fail(
                    path + ".jump_connection_id",
                    "connection cycles and more than one jump hop are unsupported.",
                )
        for root_index, root in enumerate(connection["allowed_log_roots"]):
            _linux_path(root, path + f".allowed_log_roots[{root_index}]")
    for index, server in enumerate(config["servers"]):
        reference("subsystems", server["subsystem_id"], f"servers[{index}].subsystem_id")
        reference("connections", server["connection_id"], f"servers[{index}].connection_id")
    for index, parser in enumerate(config["parsers"]):
        _timestamp(parser["timestamp"], f"parsers[{index}].timestamp")
    for index, process in enumerate(config["processes"]):
        path = f"processes[{index}]"
        server = reference("servers", process["server_id"], path + ".server_id")
        source = process["log_source"]
        source_path = path + ".log_source"
        reference("parsers", source["parser_id"], source_path + ".parser_id")
        try:
            encoding = codecs.lookup(source["encoding"]).name
        except LookupError:
            _fail(source_path + ".encoding", "unsupported text encoding.")
        if encoding not in _SUPPORTED_ENCODINGS:
            _fail(source_path + ".encoding", "unsupported text encoding.")
        roots = records["connections"][server["connection_id"]]["allowed_log_roots"]
        _linux_path(source["active_path"], source_path + ".active_path")
        _within_roots(source["active_path"], roots, source_path + ".active_path")
        for pattern_index, pattern in enumerate(source["rotated_patterns"]):
            field = source_path + f".rotated_patterns[{pattern_index}]"
            _linux_path(pattern, field, pattern=True)
            _within_roots(pattern, roots, field)
        for archive_index, archive in enumerate(source["archives"]):
            field = source_path + f".archives[{archive_index}]"
            _linux_path(archive["path_pattern"], field + ".path_pattern", pattern=True)
            _within_roots(archive["path_pattern"], roots, field + ".path_pattern")
            for member_index, pattern in enumerate(archive["member_patterns"]):
                _linux_path(
                    pattern, field + f".member_patterns[{member_index}]", pattern=True, member=True
                )
    for index, flow in enumerate(config["flows"]):
        for field in ("source_process_id", "target_process_id"):
            reference("processes", flow[field], f"flows[{index}].{field}")
    for index, view in enumerate(config["views"]):
        path = f"views[{index}]"
        visible: set[str] = set()
        for node_index, node in enumerate(view["nodes"]):
            field = path + f".nodes[{node_index}]"
            identifier = node["element_id"]
            for coordinate in ("x", "y", "width", "height"):
                if abs(node[coordinate]) > MAX_GEOMETRY:
                    _fail(field + "." + coordinate, "coordinate exceeds supported canvas bounds.")
            if identifier not in elements:
                _fail(field + ".element_id", "diagram element does not exist in this system.")
            if identifier in visible:
                _fail(field + ".element_id", "duplicate view node.")
            visible.add(identifier)
        for node_index, node in enumerate(view["nodes"]):
            record = elements[node["element_id"]]
            parent = record.get("server_id", record.get("subsystem_id"))
            if parent is not None and parent not in visible:
                _fail(
                    path + f".nodes[{node_index}].element_id",
                    "every ancestor must be present in this view.",
                )
        flow_ids: set[str] = set()
        for flow_index, identifier in enumerate(view["flow_ids"]):
            field = path + f".flow_ids[{flow_index}]"
            flow = reference("flows", identifier, field)
            if identifier in flow_ids:
                _fail(field, "duplicate view flow.")
            flow_ids.add(identifier)
            if flow["source_process_id"] not in visible or flow["target_process_id"] not in visible:
                _fail(field, "both flow endpoints must be present in this view.")


def empty_project(project_id: str, name: str, description: str, revision: int) -> dict[str, Any]:
    config: dict[str, Any] = {
        "schema_version": "2.0",
        "project": {
            "id": project_id,
            "name": name,
            "description": description,
            "revision": revision,
            "display_timezone": "UTC",
        },
        **{kind: [] for kind in COLLECTIONS},
        "settings": {
            "ui": {"product_name": "System Inspector", "locale": "en"},
            "live": {"poll_interval_ms": 750, "reorder_buffer_ms": 500, "record_by_default": False},
        },
    }
    validate_project(config)
    return config
