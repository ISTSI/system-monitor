"""Bounded, non-executing static inventory upload parsing.

Only uploaded bytes are inspected. This module never reads an inventory path,
loads an Ansible plugin, renders a template, extracts an archive, or opens SSH.
Returned dictionaries contain relevant, recursively sanitized values only.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shlex
import stat
import time
import unicodedata
import zipfile
import zlib
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, NoReturn

import yaml

from inspector.errors import DomainError


@dataclass(frozen=True)
class InventoryLimits:
    upload_bytes: int = 10 * 1024 * 1024
    expanded_bytes: int = 20 * 1024 * 1024
    files: int = 200
    path_depth: int = 8
    tree_depth: int = 32
    tree_nodes: int = 100_000
    line_bytes: int = 65_536
    field_bytes: int = 65_536
    hosts: int = 5_000
    groups: int = 5_000
    processes: int = 10_000
    seconds: float = 10.0


DEFAULT_LIMITS = InventoryLimits()
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_SENSITIVE = re.compile(
    r"password|passwd|(?:^|_)pass(?:$|_)|private.?key|secret|token|credential|vault", re.I
)
_UNSAFE = {
    "ansible_ssh_common_args",
    "ansible_ssh_extra_args",
    "ansible_ssh_args",
    "ansible_scp_extra_args",
    "ansible_sftp_extra_args",
    "ansible_ssh_executable",
    "ansible_shell_executable",
    "ansible_shell_type",
    "ansible_ssh_private_key_file",
    "proxycommand",
    "proxyjump",
}
_RELEVANT = {
    "ansible_host",
    "ansible_port",
    "ansible_user",
    "ansible_connection",
    "ansible_become",
    "inspector_subsystem",
    "inspector_processes",
}
_SUFFIX_FORMAT = {".ini": "ini", ".yaml": "yaml", ".yml": "yaml", ".json": "canonical_json"}
_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".gz", ".bz2", ".xz", ".7z")
_IGNORED_PARTS = {".git", "roles", "playbooks", "plugins", "inventory_plugins", "vars_plugins"}
_IGNORED_NAMES = {"ansible.cfg", "readme", "readme.md", "readme.txt", "license", "license.txt"}


class InventoryParseError(DomainError):
    """A stable diagnostic without uploaded values or underlying exceptions."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        source: str | None = None,
        field: str | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        self.description = message
        self.source, self.field, self.line, self.column = source, field, line, column
        location = []
        if source is not None:
            location.append(f"File {source}")
        if field is not None:
            location.append(f"field {field}")
        if line is not None:
            location.append(f"line {line}")
        if column is not None:
            location.append(f"column {column}")
        super().__init__(code, "; ".join(location) + ": " + message if location else message, 422)

    def located(
        self,
        *,
        source: str | None = None,
        field: str | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> InventoryParseError:
        return InventoryParseError(
            self.code,
            self.description,
            source=self.source if self.source is not None else source,
            field=self.field if self.field is not None else field,
            line=self.line if self.line is not None else line,
            column=self.column if self.column is not None else column,
        )


def _fail(
    code: str,
    message: str,
    *,
    source: str | None = None,
    field: str | None = None,
    line: int | None = None,
    column: int | None = None,
) -> NoReturn:
    raise InventoryParseError(code, message, source=source, field=field, line=line, column=column)


@contextmanager
def _location(
    source: str | None = None,
    field: str | None = None,
    line: int | None = None,
    column: int | None = None,
) -> Iterator[None]:
    """Attach only validated member names and structural coordinates, never values."""
    try:
        yield
    except InventoryParseError as error:
        raise error.located(source=source, field=field, line=line, column=column) from None


@dataclass
class _Budget:
    limits: InventoryLimits
    cancelled: Callable[[], bool] | None = None
    deadline: float = field(init=False)
    nodes: int = 0

    def __post_init__(self) -> None:
        self.deadline = time.monotonic() + self.limits.seconds

    def check(self) -> None:
        if self.cancelled is not None and self.cancelled():
            _fail("IMPORT_CANCELLED", "Inventory parsing was cancelled.")
        if time.monotonic() > self.deadline:
            _fail("IMPORT_TIMEOUT", "Inventory parsing exceeded its time limit.")

    def node(self) -> None:
        self.nodes += 1
        if self.nodes > self.limits.tree_nodes:
            _fail("PARSE_LIMIT", "Inventory parse-node limit exceeded.")
        if self.nodes % 128 == 0:
            self.check()


def _warning(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def _text(raw: bytes, budget: _Budget) -> str:
    budget.check()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        _fail("INVALID_ENCODING", "Inventory files must contain UTF-8 text.")
    if "\x00" in text:
        _fail("INVALID_TEXT", "Inventory text contains a forbidden control character.")
    if "$ANSIBLE_VAULT" in text or re.search(r"(?:^|\s)!vault(?:\s|$)", text):
        _fail(
            "VAULT_UNSUPPORTED",
            "Vault input is unsupported; upload resolved, secret-free static data or canonical JSON.",
        )
    for line_number, line in enumerate(text.splitlines(), 1):
        budget.check()
        if len(line.encode("utf-8")) > budget.limits.line_bytes:
            _fail("LINE_LIMIT", "Inventory line length exceeds its limit.", line=line_number)
    return text


class _Loader(yaml.SafeLoader):
    pass


def _mapping(loader: _Loader, node: yaml.MappingNode) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            _fail(
                "DUPLICATE_KEY",
                "Duplicate or non-string inventory mapping key.",
                line=key_node.start_mark.line + 1,
                column=key_node.start_mark.column + 1,
            )
        result[key] = loader.construct_object(value_node)
    return result


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _json_mapping(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_KEY", "Duplicate inventory JSON mapping key.")
        result[key] = value
    return result


def _constant(_value: str) -> NoReturn:
    _fail("UNSUPPORTED_SCALAR", "Inventory numbers must be finite.")


def _check_tree(value: Any, budget: _Budget) -> None:
    stack = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        budget.node()
        if depth > budget.limits.tree_depth:
            _fail("PARSE_LIMIT", "Inventory nesting limit exceeded.")
        if isinstance(current, dict):
            for key, child in current.items():
                if not isinstance(key, str):
                    _fail("UNSUPPORTED_SCALAR", "Inventory mapping keys must be strings.")
                stack.extend(((key, depth + 1), (child, depth + 1)))
        elif isinstance(current, list):
            stack.extend((child, depth + 1) for child in current)
        elif isinstance(current, str):
            try:
                size = len(current.encode("utf-8"))
            except UnicodeError:
                _fail("INVALID_TEXT", "Inventory contains invalid Unicode.")
            if size > budget.limits.field_bytes:
                _fail("FIELD_LIMIT", "Inventory field length exceeds its limit.")
        elif type(current) is float:
            if not math.isfinite(current):
                _fail("UNSUPPORTED_SCALAR", "Inventory numbers must be finite.")
        elif current is not None and type(current) not in (bool, int):
            _fail(
                "UNSUPPORTED_SCALAR",
                "Inventory requires literal JSON-compatible values; resolve complex values externally.",
            )
    budget.check()


def _data(raw: bytes, format: str, budget: _Budget) -> Any:
    text = _text(raw, budget)
    try:
        if format == "canonical_json":
            depth = 0
            quoted = escaped = False
            for index, char in enumerate(text):
                if index % 4096 == 0:
                    budget.check()
                if quoted:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        quoted = False
                elif char == '"':
                    quoted = True
                elif char in "[{":
                    depth += 1
                    if depth > budget.limits.tree_depth:
                        _fail("PARSE_LIMIT", "Inventory nesting limit exceeded.")
                elif char in "]}":
                    depth -= 1
            result = json.loads(text, object_pairs_hook=_json_mapping, parse_constant=_constant)
        else:
            depth = 0
            events = 0
            for event in yaml.parse(text, Loader=_Loader):
                events += 1
                if events > budget.limits.tree_nodes * 3:
                    _fail("PARSE_LIMIT", "Inventory parse-node limit exceeded.")
                if events % 128 == 0:
                    budget.check()
                if isinstance(event, yaml.events.AliasEvent) or getattr(event, "anchor", None):
                    _fail(
                        "YAML_CONSTRUCT_UNSUPPORTED",
                        "YAML anchors and aliases are unsupported; supply literal values.",
                        line=event.start_mark.line + 1,
                        column=event.start_mark.column + 1,
                    )
                if getattr(event, "tag", None):
                    _fail(
                        "YAML_CONSTRUCT_UNSUPPORTED",
                        "Explicit YAML tags are unsupported; supply literal values.",
                        line=event.start_mark.line + 1,
                        column=event.start_mark.column + 1,
                    )
                if isinstance(
                    event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)
                ):
                    depth += 1
                    if depth > budget.limits.tree_depth:
                        _fail("PARSE_LIMIT", "Inventory nesting limit exceeded.")
                elif isinstance(event, (yaml.events.MappingEndEvent, yaml.events.SequenceEndEvent)):
                    depth -= 1
            result = yaml.load(text, Loader=_Loader)
    except InventoryParseError:
        raise
    except (yaml.YAMLError, json.JSONDecodeError) as error:
        mark = getattr(error, "problem_mark", None)
        _fail(
            "INVALID_INVENTORY_DATA",
            "Invalid inventory syntax; parser diagnostics never include source values.",
            line=error.lineno
            if isinstance(error, json.JSONDecodeError)
            else mark.line + 1
            if mark
            else None,
            column=error.colno
            if isinstance(error, json.JSONDecodeError)
            else mark.column + 1
            if mark
            else None,
        )
    except (UnicodeError, ValueError, RecursionError):
        _fail(
            "INVALID_INVENTORY_DATA",
            "Invalid inventory syntax; parser diagnostics never include source values.",
        )
    _check_tree(result, budget)
    return result


def _member_path(raw_name: str, budget: _Budget, *, directory: bool = False) -> str:
    name = raw_name[:-1] if directory and raw_name.endswith("/") else raw_name
    parts = name.split("/")
    if (
        not name
        or len(name) > 512
        or len(parts) > budget.limits.path_depth
        or "\\" in name
        or ":" in name
        or any(part in ("", ".", "..") for part in parts)
        or any(unicodedata.category(char) in {"Cc", "Cs"} for char in name)
        or PurePosixPath(name).is_absolute()
    ):
        _fail("UNSAFE_MEMBER", "Inventory bundle contains an unsafe member path.")
    return name


def _archive_signature(data: bytes) -> bool:
    return (
        data.startswith(
            (
                b"PK\x03\x04",
                b"PK\x05\x06",
                b"\x1f\x8b",
                b"BZh",
                b"\xfd7zXZ\x00",
                b"7z\xbc\xaf\x27\x1c",
            )
        )
        or data[257:262] == b"ustar"
    )


def _zip_files(data: bytes, budget: _Budget) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    # Bound central-directory allocation before ZipFile constructs ZipInfo objects.
    tail = data[-65_557:]
    end = tail.rfind(b"PK\x05\x06")
    if end >= 0 and len(tail) >= end + 22:
        entry_count = int.from_bytes(tail[end + 10 : end + 12], "little")
        if entry_count > budget.limits.files:
            _fail("FILE_LIMIT", "Inventory bundle file-count limit exceeded.")
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > budget.limits.files:
                _fail("FILE_LIMIT", "Inventory bundle file-count limit exceeded.")
            names: dict[str, bool] = {}
            validated: list[tuple[zipfile.ZipInfo, str]] = []
            for info in infos:
                budget.check()
                name = _member_path(info.orig_filename, budget, directory=info.is_dir())
                normalized = unicodedata.normalize("NFC", name).casefold()
                if normalized in names:
                    _fail(
                        "DUPLICATE_MEMBER",
                        "Inventory bundle contains duplicate or normalization-colliding paths.",
                    )
                names[normalized] = info.is_dir()
                mode = stat.S_IFMT(info.external_attr >> 16)
                if (
                    mode not in (0, stat.S_IFREG, stat.S_IFDIR)
                    or (mode == stat.S_IFDIR and not info.is_dir())
                    or (mode == stat.S_IFREG and info.is_dir())
                ):
                    _fail(
                        "NON_REGULAR_MEMBER",
                        "Inventory bundle links and special files are forbidden.",
                    )
                # Unix link metadata may be present even with misleading regular-file mode.
                offset = 0
                while offset + 4 <= len(info.extra):
                    header = int.from_bytes(info.extra[offset : offset + 2], "little")
                    length = int.from_bytes(info.extra[offset + 2 : offset + 4], "little")
                    if header == 0x756E or (header == 0x000D and length > 12):
                        _fail("NON_REGULAR_MEMBER", "Inventory bundle link metadata is forbidden.")
                    offset += 4 + length
                if offset != len(info.extra):
                    _fail("INVALID_ARCHIVE", "Inventory bundle contains invalid member metadata.")
                if info.flag_bits & 0x41:
                    _fail("ENCRYPTED_ARCHIVE", "Encrypted inventory bundles are unsupported.")
                if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    _fail(
                        "UNSUPPORTED_COMPRESSION",
                        "Inventory ZIP supports stored or deflated members only.",
                    )
                if not info.is_dir():
                    if name.casefold().endswith(_ARCHIVE_SUFFIXES):
                        _fail(
                            "NESTED_ARCHIVE", "Nested archives in inventory bundles are forbidden."
                        )
                    validated.append((info, name))
            for normalized in names:
                parts = normalized.split("/")
                if any(names.get("/".join(parts[:end])) is False for end in range(1, len(parts))):
                    _fail(
                        "DUPLICATE_MEMBER",
                        "Inventory bundle contains colliding file and directory paths.",
                    )
            total = 0
            for info, name in validated:
                chunks: list[bytes] = []
                with archive.open(info) as stream:
                    while True:
                        budget.check()
                        chunk = stream.read(min(65_536, budget.limits.expanded_bytes - total + 1))
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > budget.limits.expanded_bytes:
                            _fail("EXPANDED_LIMIT", "Inventory expanded-byte limit exceeded.")
                        chunks.append(chunk)
                raw = b"".join(chunks)
                if _archive_signature(raw):
                    _fail(
                        "NESTED_ARCHIVE",
                        "Nested archive content in inventory bundles is forbidden.",
                    )
                files[name] = raw
    except InventoryParseError:
        raise
    except (
        zipfile.BadZipFile,
        RuntimeError,
        ValueError,
        NotImplementedError,
        OSError,
        EOFError,
        zlib.error,
        UnicodeError,
    ):
        _fail("INVALID_ARCHIVE", "Invalid inventory ZIP bundle.")
    return files


def _file_format(path: str, data: bytes) -> str | None:
    item = PurePosixPath(path)
    if (
        any(part.casefold() in _IGNORED_PARTS for part in item.parts)
        or item.name.casefold() in _IGNORED_NAMES
    ):
        return None
    if item.suffix.lower() in _SUFFIX_FORMAT:
        return _SUFFIX_FORMAT[item.suffix.lower()]
    if item.suffix:
        return None
    stripped = data.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped.startswith(b"#!"):
        return None
    if stripped.startswith(b"{"):
        return "canonical_json"
    # Extensionless inventories can be YAML; an INI group section starts with '['.
    meaningful = b"\n".join(
        line for line in stripped.splitlines() if not line.lstrip().startswith((b"#", b";"))
    )
    if meaningful.lstrip().startswith((b"---", b"all:")) or re.match(
        rb"[A-Za-z0-9_.:-]+:\s*(?:\r?\n|\{)", meaningful
    ):
        return "yaml"
    return "ini"


def _role(path: str, data: bytes) -> tuple[str, str | None]:
    parts = PurePosixPath(path).parts
    if "group_vars" in parts or "host_vars" in parts:
        suffix = PurePosixPath(path).suffix.lower()
        return (
            ("companion", "canonical_json" if suffix == ".json" else "yaml")
            if suffix in ("", ".yml", ".yaml", ".json")
            else ("ignored", None)
        )
    format = _file_format(path, data)
    return ("source", format) if format is not None else ("ignored", None)


def _upload(filename: str, data: bytes, budget: _Budget) -> tuple[dict[str, bytes], dict[str, Any]]:
    budget.check()
    if len(data) > budget.limits.upload_bytes:
        _fail("UPLOAD_LIMIT", "Inventory upload exceeds its configured byte limit.")
    if not data:
        _fail("EMPTY_INVENTORY", "Inventory upload is empty.")
    _member_path(filename, budget)
    is_zip = (
        data.startswith((b"PK\x03\x04", b"PK\x05\x06"))
        or PurePosixPath(filename).suffix.lower() == ".zip"
    )
    files = _zip_files(data, budget) if is_zip else {filename: data}
    if not is_zip:
        if len(data) > budget.limits.expanded_bytes:
            _fail("EXPANDED_LIMIT", "Inventory expanded-byte limit exceeded.")
        with _location(filename, "inventory"):
            _text(data, budget)
        if _role(filename, data)[0] != "source":
            _fail(
                "SOURCE_UNSUPPORTED",
                "Upload a supported static INI, YAML or canonical JSON source; executable and other file types are unsupported.",
            )
    rows: list[dict[str, Any]] = []
    for path, raw in files.items():
        role, format = _role(path, raw)
        rows.append(
            {
                "path": path,
                "size": len(raw),
                "role": role,
                "format": format,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    rows.sort(key=lambda item: item["path"])
    digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    candidates = [row["path"] for row in rows if row["role"] == "source"]
    warnings = (
        []
        if is_zip
        else [
            _warning(
                "COMPANIONS_NOT_SUPPLIED",
                "No companion files were uploaded; server-side group_vars and host_vars are never read.",
            )
        ]
    )
    manifest = {
        "filename": filename,
        "format": "static_zip" if is_zip else _file_format(filename, data),
        "files": rows,
        "file_count": len(rows),
        "expanded_bytes": sum(row["size"] for row in rows),
        "source_candidates": candidates,
        "ignored_files": [row["path"] for row in rows if row["role"] == "ignored"],
        "warnings": warnings,
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "manifest_sha256": digest,
    }
    return files, manifest


def inspect_upload(
    filename: str,
    data: bytes,
    *,
    limits: InventoryLimits = DEFAULT_LIMITS,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Validate uploaded bytes and return filenames/counts, never file contents."""
    _, manifest = _upload(filename, data, _Budget(limits, cancelled))
    return manifest


def _name(value: Any, kind: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value) or "[" in value or "]" in value:
        _fail(
            "INVALID_" + kind.upper(),
            "Inventory names must be literal stable aliases; host ranges are unsupported.",
        )
    return value


def _scrub(value: Any, omitted: Counter[str]) -> Any:
    if isinstance(value, dict):
        clean = {}
        for key, child in value.items():
            if _SENSITIVE.search(key) or key.casefold() in _UNSAFE:
                omitted[key] += 1
            else:
                clean[key] = _scrub(child, omitted)
        return clean
    if isinstance(value, list):
        return [_scrub(child, omitted) for child in value]
    return value


def _template(value: Any) -> bool:
    if isinstance(value, str):
        return any(token in value for token in ("{{", "{%", "{#")) or bool(
            re.search(r"\b(?:lookup|query)\s*\(", value)
        )
    if isinstance(value, dict):
        return any(_template(child) for child in value.values())
    return isinstance(value, list) and any(_template(child) for child in value)


@dataclass
class _Entity:
    members: set[str] = field(default_factory=set)
    children: set[str] = field(default_factory=set)
    values: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    sources: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _Inventory:
    budget: _Budget
    groups: dict[str, _Entity] = field(
        default_factory=lambda: {"all": _Entity(), "ungrouped": _Entity()}
    )
    hosts: dict[str, _Entity] = field(default_factory=dict)
    omitted: Counter[str] = field(default_factory=Counter)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    companion_order: list[str] = field(default_factory=list)

    def group(self, name: Any) -> _Entity:
        name = _name(name, "group")
        if name not in self.groups:
            if len(self.groups) >= self.budget.limits.groups:
                _fail("GROUP_LIMIT", "Inventory group-count limit exceeded.")
            self.groups[name] = _Entity()
        return self.groups[name]

    def variables(
        self,
        entity: _Entity,
        values: Any,
        source: str,
        *,
        group: str | None = None,
        alias: str | None = None,
        companion: bool = False,
        line: int | None = None,
    ) -> None:
        if values is None:
            values = {}
        if not isinstance(values, dict):
            _fail(
                "INVALID_VARIABLES",
                "Inventory variables must be a literal mapping.",
                source=source,
                field="vars",
                line=line,
            )
        if "ansible_group_priority" in values:
            _fail(
                "GROUP_PRIORITY_UNSUPPORTED",
                "Explicit Ansible group priority is unsupported; resolve precedence externally and upload canonical JSON.",
                source=source,
                field="ansible_group_priority",
                line=line,
            )
        clean = _scrub(values, self.omitted)
        origin: dict[str, Any] = {
            "source": source,
            "group": group,
            "alias": alias,
            "companion": companion,
        }
        if line is not None:
            origin["line"] = line
        if origin not in entity.sources:
            entity.sources.append(origin)
        for key, value in clean.items():
            self.budget.node()
            if key not in _RELEVANT:
                self.omitted[key] += 1
                continue
            if _template(value):
                _fail(
                    "TEMPLATE_UNSUPPORTED",
                    "A required connection/process value contains unresolved templating; upload literal values or resolved canonical JSON.",
                    source=source,
                    field=key,
                    line=line,
                )
            record = {"value": value, **origin}
            history = entity.history.setdefault(key, [])
            if record not in history:
                history.append(record)
            if companion:
                # Explicit lexicographic companion ordering is the documented overlay.
                entity.values[key] = [record]
            else:
                records = entity.values.setdefault(key, [])
                if record not in records:
                    records.append(record)

    def host(
        self, alias: Any, values: Any, parent: str, source: str, line: int | None = None
    ) -> None:
        with _location(source, "hosts", line):
            alias = _name(alias, "host")
        if alias not in self.hosts:
            if len(self.hosts) >= self.budget.limits.hosts:
                _fail("HOST_LIMIT", "Inventory host-count limit exceeded.")
            self.hosts[alias] = _Entity()
        self.group(parent).members.add(alias)
        self.variables(self.hosts[alias], values, source, alias=alias, line=line)

    def yaml(self, document: Any, source: str) -> None:
        if not isinstance(document, dict) or "plugin" in document:
            _fail(
                "DYNAMIC_OR_INVALID_INVENTORY",
                "Static group inventory required; uploaded plugin configurations are never executed.",
            )

        def visit(name: str, value: Any) -> None:
            self.budget.check()
            group = self.group(name)
            if value is None:
                value = {}
            if not isinstance(value, dict) or set(value) - {"hosts", "children", "vars"}:
                _fail(
                    "YAML_GROUP_UNSUPPORTED",
                    "Static YAML groups support only hosts, children and literal vars; resolve other semantics externally.",
                )
            self.variables(group, value.get("vars"), source, group=name)
            hosts = value.get("hosts") or {}
            children = value.get("children") or {}
            if not isinstance(hosts, dict) or not isinstance(children, dict):
                _fail("INVALID_YAML_GROUP", "YAML hosts and children must be mappings.")
            for alias, variables in hosts.items():
                self.host(alias, variables, name, source)
            for child, child_value in children.items():
                self.group(child)
                group.children.add(child)
                visit(child, child_value)

        for name, value in document.items():
            visit(name, value)

    def canonical(self, document: Any, source: str) -> None:
        if not isinstance(document, dict) or "plugin" in document:
            _fail(
                "INVALID_CANONICAL_INVENTORY",
                "Canonical JSON must contain groups and optional _meta.hostvars.",
            )
        meta = document.get("_meta", {})
        if (
            not isinstance(meta, dict)
            or set(meta) - {"hostvars"}
            or not isinstance(meta.get("hostvars", {}), dict)
        ):
            _fail(
                "INVALID_CANONICAL_META", "Canonical JSON _meta.hostvars must be a literal mapping."
            )
        for alias, variables in meta.get("hostvars", {}).items():
            self.host(alias, variables, "all", source)
        for name, value in document.items():
            if name == "_meta":
                continue
            group = self.group(name)
            if not isinstance(value, dict) or set(value) - {"hosts", "children", "vars"}:
                _fail(
                    "INVALID_CANONICAL_GROUP",
                    "Canonical groups support hosts, children and vars only.",
                )
            self.variables(group, value.get("vars"), source, group=name)
            hosts = value.get("hosts", [])
            children = value.get("children", [])
            if not isinstance(hosts, list) or not isinstance(children, list):
                _fail(
                    "INVALID_CANONICAL_GROUP",
                    "Canonical group hosts and children must be literal lists.",
                )
            for alias in hosts:
                self.host(alias, {}, name, source)
            for child in children:
                self.group(child)
                group.children.add(child)

    def ini(self, raw: bytes, source: str) -> None:
        text = _text(raw, self.budget)
        current, mode = "ungrouped", "hosts"
        for line_no, line in enumerate(text.splitlines(), 1):
            self.budget.node()
            self.budget.check()
            with _location(source, "inventory", line_no):
                stripped = line.strip()
                if not stripped or stripped.startswith(("#", ";")):
                    continue
                if stripped.startswith("#!"):
                    _fail(
                        "DYNAMIC_INVENTORY_UNSUPPORTED",
                        "Executable inventories are unsupported; upload static inventory or canonical JSON.",
                    )
                if stripped.startswith("["):
                    match = re.fullmatch(r"\[([^\[\]]+)\]\s*(?:[#;].*)?", stripped)
                    if match is None:
                        _fail(
                            "INVALID_INI_SECTION",
                            "Invalid static INI group section; ranges are unsupported.",
                        )
                    current, separator, suffix = match[1].partition(":")
                    mode = suffix if separator else "hosts"
                    if mode not in {"hosts", "children", "vars"}:
                        _fail(
                            "INI_SECTION_UNSUPPORTED",
                            "Static INI supports group, group:children and group:vars sections.",
                        )
                    self.group(current)
                    self.variables(self.group(current), {}, source, group=current, line=line_no)
                    continue
                try:
                    lexer = shlex.shlex(stripped, posix=True)
                    lexer.whitespace_split = True
                    lexer.commenters = "#;"
                    tokens = list(lexer)
                except ValueError:
                    _fail("INVALID_INI_QUOTING", "Invalid quoting in static INI inventory.")
                if not tokens:
                    continue
                if mode == "children":
                    if len(tokens) != 1:
                        _fail(
                            "INVALID_CHILD_GROUP",
                            "INI child-group declarations contain one literal group name.",
                        )
                    self.group(tokens[0])
                    self.group(current).children.add(tokens[0])
                    continue
                if mode == "vars":
                    # Unlike host lines, :vars permits an unquoted scalar containing spaces.
                    key, separator, value = stripped.partition("=")
                    if not separator or not _KEY.fullmatch(key.strip()):
                        _fail(
                            "INVALID_INI_VARIABLE",
                            "INI group vars require one literal key=value per line.",
                        )
                    try:
                        value_lexer = shlex.shlex(value, posix=True)
                        value_lexer.whitespace_split = True
                        value_lexer.commenters = "#;"
                        parsed = list(value_lexer)
                    except ValueError:
                        _fail("INVALID_INI_QUOTING", "Invalid quoting in static INI inventory.")
                    if any("=" in token for token in parsed) and not value.lstrip().startswith(
                        ("'", '"')
                    ):
                        _fail(
                            "INI_VARS_SUBSET_LIMIT",
                            "INI group vars contain one scalar value; use YAML for structured values.",
                        )
                    self._ini_vars(
                        self.group(current),
                        {key.strip(): " ".join(parsed)},
                        source,
                        group=current,
                        line=line_no,
                    )
                    continue
                alias, *rest = tokens
                values: dict[str, Any] = {}
                for token in rest:
                    key, separator, value = token.partition("=")
                    if not separator or not _KEY.fullmatch(key) or key in values:
                        _fail(
                            "INVALID_INI_VARIABLE",
                            "INI host vars require distinct literal key=value tokens.",
                        )
                    values[key] = value
                if ":" in alias:
                    if alias.count(":") != 1:
                        _fail(
                            "AMBIGUOUS_HOST_PORT",
                            "Use a literal IPv6 ansible_host and separate ansible_port.",
                        )
                    alias, port = alias.rsplit(":", 1)
                    if "ansible_port" in values and str(values["ansible_port"]) != port:
                        _fail(
                            "CONFLICTING_HOST_PORT", "Host port suffix conflicts with ansible_port."
                        )
                    values["ansible_port"] = port
                self.host(alias, {}, current, source, line_no)
                self._ini_vars(self.hosts[alias], values, source, alias=alias, line=line_no)

    def _ini_vars(
        self, entity: _Entity, values: dict[str, Any], source: str, **origin: Any
    ) -> None:
        for key, value in values.items():
            if key == "inspector_processes" or (
                key in _RELEVANT
                and isinstance(value, str)
                and value.lstrip().startswith(("[", "{", "("))
            ):
                _fail(
                    "INI_COMPLEX_VALUE_UNSUPPORTED",
                    "Structured process/connection values require YAML, companion host_vars or canonical JSON; INI values are never evaluated.",
                    source=source,
                    field=key,
                    line=origin.get("line"),
                )
        self.variables(entity, values, source, **origin)

    def companions(self, files: dict[str, bytes], source_files: list[str]) -> list[str]:
        used: list[str] = []
        roots = list(dict.fromkeys(str(PurePosixPath(path).parent) for path in source_files))
        for root in roots:
            prefix = "" if root == "." else root + "/"
            for path, raw in sorted(files.items()):
                self.budget.check()
                if not path.startswith(prefix):
                    continue
                parts = PurePosixPath(path[len(prefix) :]).parts
                if len(parts) < 2 or parts[0] not in {"host_vars", "group_vars"}:
                    continue
                if PurePosixPath(path).suffix.lower() not in {"", ".yaml", ".yml", ".json"}:
                    continue
                name = parts[1] if len(parts) > 2 else PurePosixPath(parts[1]).stem
                target = self.hosts.get(name) if parts[0] == "host_vars" else self.groups.get(name)
                if target is None:
                    continue
                with _location(path, "vars"):
                    value = _data(
                        raw, "canonical_json" if path.endswith(".json") else "yaml", self.budget
                    )
                    self.variables(
                        target,
                        value,
                        path,
                        alias=name if parts[0] == "host_vars" else None,
                        group=name if parts[0] == "group_vars" else None,
                        companion=True,
                    )
                used.append(path)
        self.companion_order = used
        return used

    def normalize(self) -> dict[str, Any]:
        # Every root group is implicitly below all. Detect explicit cycles first.
        parents: dict[str, set[str]] = {name: set() for name in self.groups}
        for name, group in self.groups.items():
            for child in group.children:
                self.budget.node()
                if child == "all":
                    _fail(
                        "GROUP_CYCLE", "The implicit all root cannot be a child of another group."
                    )
                parents[child].add(name)
        ancestry: dict[str, set[str]] = {}
        active: set[str] = set()

        def ancestors(name: str) -> set[str]:
            self.budget.check()
            if name in active:
                _fail("GROUP_CYCLE", "Inventory groups contain a cycle; only a DAG is supported.")
            if name in ancestry:
                return ancestry[name]
            active.add(name)
            result: set[str] = set()
            for parent in parents[name]:
                self.budget.node()
                result.add(parent)
                for ancestor in ancestors(parent):
                    self.budget.node()
                    result.add(ancestor)
            active.remove(name)
            if name != "all":
                result.add("all")
            ancestry[name] = result
            return result

        try:
            for name in self.groups:
                ancestors(name)
        except RecursionError:
            _fail("GROUP_DEPTH_LIMIT", "Inventory group depth exceeds its supported limit.")
        hosts = []
        conflicts = []
        total_processes = 0
        for alias, entity in sorted(self.hosts.items()):
            self.budget.check()
            memberships: set[str] = set()
            for name, group in self.groups.items():
                self.budget.node()
                if alias in group.members:
                    memberships.add(name)
            memberships.update(*(ancestry[name] for name in tuple(memberships)))
            memberships.add("all")
            if not (memberships - {"all", "ungrouped"}):
                memberships.add("ungrouped")
            else:
                memberships.discard("ungrouped")
            effective: dict[str, Any] = {}
            effective_provenance: dict[str, dict[str, Any]] = {}
            provenance: dict[str, list[dict[str, Any]]] = {}
            for key in sorted(_RELEVANT):
                candidates = [
                    record
                    for group in sorted(memberships)
                    for record in self.groups[group].values.get(key, [])
                ]
                host_values = entity.values.get(key, [])
                all_records = candidates + host_values
                if not all_records:
                    continue
                if host_values:
                    winners = host_values
                else:
                    winners = [
                        record
                        for record in candidates
                        if not any(
                            record["group"] in ancestry[other["group"]]
                            for other in candidates
                            if other["group"] != record["group"]
                        )
                    ]
                history = [
                    record
                    for group in sorted(memberships)
                    for record in self.groups[group].history.get(key, [])
                ] + entity.history.get(key, [])
                provenance[key] = [
                    {k: v for k, v in record.items() if k != "value"} for record in history
                ]
                distinct: list[dict[str, Any]] = []
                for record in winners:
                    if not any(record["value"] == item["value"] for item in distinct):
                        distinct.append(record)
                if len(distinct) > 1:
                    conflicts.append(
                        {
                            "alias": alias,
                            "key": key,
                            "values": distinct,
                            "code": "STATIC_VARIABLE_CONFLICT",
                        }
                    )
                # A conflict is always explicit and blocks commit; this value is only a proposal.
                effective[key] = winners[0]["value"]
                effective_provenance[key] = {
                    name: value for name, value in winners[0].items() if name != "value"
                }
            address = effective.get("ansible_host", alias)
            user = effective.get("ansible_user")
            for key, value in (
                ("ansible_host", address),
                ("ansible_user", user),
                ("inspector_subsystem", effective.get("inspector_subsystem")),
            ):
                if value is not None and (
                    not isinstance(value, str)
                    or not value.strip()
                    or any(unicodedata.category(char) == "Cc" for char in value)
                ):
                    _fail(
                        "INVALID_CONNECTION_VALUE",
                        "Connection and subsystem values must be nonblank literal strings without control characters.",
                        source=effective_provenance.get(key, {}).get("source"),
                        field=key,
                        line=effective_provenance.get(key, {}).get("line"),
                    )
            port = effective.get("ansible_port", 22)
            if isinstance(port, str) and re.fullmatch(r"[0-9]{1,5}", port):
                port = int(port)
            if type(port) is not int or not 1 <= port <= 65535:
                _fail(
                    "INVALID_PORT",
                    "ansible_port must be an integer between 1 and 65535.",
                    source=effective_provenance.get("ansible_port", {}).get("source"),
                    field="ansible_port",
                    line=effective_provenance.get("ansible_port", {}).get("line"),
                )
            connection = effective.get("ansible_connection", "ssh")
            if not isinstance(connection, str) or connection not in {"ssh", "smart", "paramiko"}:
                _fail(
                    "CONNECTION_UNSUPPORTED",
                    "Only literal SSH inventory connections can be mapped; non-SSH activation is unsupported.",
                    source=effective_provenance.get("ansible_connection", {}).get("source"),
                    field="ansible_connection",
                    line=effective_provenance.get("ansible_connection", {}).get("line"),
                )
            processes = effective.get("inspector_processes", [])
            process_origin = effective_provenance.get("inspector_processes", {})
            if not isinstance(processes, list) or any(
                not isinstance(process, dict) for process in processes
            ):
                _fail(
                    "INVALID_PROCESSES",
                    "inspector_processes must be a literal list of process records.",
                    source=process_origin.get("source"),
                    field="inspector_processes",
                    line=process_origin.get("line"),
                )
            process_ids: set[str] = set()
            process_names: set[str] = set()
            for process_index, process in enumerate(processes):
                prefix = f"inspector_processes[{process_index}]"
                with _location(
                    process_origin.get("source"), prefix + ".id", process_origin.get("line")
                ):
                    process_id = _name(process.get("id"), "process")
                name = process.get("name")
                if (
                    not isinstance(name, str)
                    or not name.strip()
                    or process_id in process_ids
                    or name.casefold() in process_names
                    or not isinstance(process.get("log_source"), dict)
                ):
                    _fail(
                        "INVALID_PROCESSES",
                        "Each process needs a distinct stable id/name and a structured log_source.",
                        source=process_origin.get("source"),
                        field=prefix
                        + (
                            ".id"
                            if process_id in process_ids
                            else ".name"
                            if not isinstance(name, str)
                            or not name.strip()
                            or name.casefold() in process_names
                            else ".log_source"
                        ),
                        line=process_origin.get("line"),
                    )
                if set(process) - {"id", "name", "pcs_resource_name", "log_source"}:
                    _fail(
                        "INVALID_PROCESSES",
                        "Process extension contains unsupported fields.",
                        source=process_origin.get("source"),
                        field=prefix,
                        line=process_origin.get("line"),
                    )
                process_ids.add(process_id)
                process_names.add(name.casefold())
            total_processes += len(processes)
            if total_processes > self.budget.limits.processes:
                _fail("PROCESS_LIMIT", "Inventory process-count limit exceeded.")
            host_warnings = []
            become = effective.get("ansible_become", False)
            if become not in (False, None, "false", "False", "no", "0", 0):
                host_warnings.append(
                    _warning(
                        "BECOME_IGNORED",
                        "Privilege escalation is never imported; configure a dedicated non-sudo log-read account.",
                    )
                )
            hosts.append(
                {
                    "alias": alias,
                    "inventory_hostname": alias,
                    "address": address,
                    "port": port,
                    "user": user,
                    "groups": sorted(memberships),
                    "vars": effective,
                    "processes": processes,
                    "provenance": provenance,
                    "effective_provenance": effective_provenance,
                    "declarations": entity.sources,
                    "warnings": host_warnings,
                }
            )
        if total_processes == 0:
            self.warnings.append(
                _warning(
                    "NO_PROCESS_DEFINITIONS",
                    "Zero process definitions found; add processes after importing hosts.",
                )
            )
        if self.omitted:
            self.warnings.append(
                _warning(
                    "VARIABLES_OMITTED",
                    "Sensitive, unsafe SSH and unrecognized variable values were omitted; only names and counts are retained.",
                    count=sum(self.omitted.values()),
                )
            )
        return {
            "hosts": hosts,
            "groups": [
                {
                    "name": name,
                    "hosts": sorted(group.members),
                    "children": sorted(group.children),
                    "vars": {key: records[0]["value"] for key, records in group.values.items()},
                    "provenance": group.sources,
                }
                for name, group in sorted(self.groups.items())
            ],
            "warnings": self.warnings,
            "conflicts": conflicts,
            "process_count": total_processes,
            "omitted_variables": [
                {"name": name, "count": count} for name, count in sorted(self.omitted.items())
            ],
        }


def parse_inventory(
    filename: str,
    data: bytes,
    format: str = "auto",
    source_files: list[str] | None = None,
    *,
    limits: InventoryLimits = DEFAULT_LIMITS,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Parse selected uploaded sources in order; return a sanitized proposal.

    Variable conflicts are returned for explicit operator resolution. Unsupported
    executable/ambiguous semantics fail with a stable, source-value-free error.
    The service must validate process log sources against its project schema.
    """
    budget = _Budget(limits, cancelled)
    files, manifest = _upload(filename, data, budget)
    is_zip = manifest["format"] == "static_zip"
    if format not in {"auto", "ini", "yaml", "canonical_json", "static_zip"}:
        _fail("FORMAT_UNSUPPORTED", "Choose static INI, YAML, canonical JSON or a ZIP bundle.")
    if format == "static_zip" and not is_zip:
        _fail("FORMAT_MISMATCH", "Selected ZIP format does not match the uploaded content.")
    if source_files is None:
        if is_zip:
            _fail(
                "SOURCE_SELECTION_REQUIRED",
                "Select static inventory sources from the ZIP in the required order.",
            )
        source_files = [filename]
    if (
        not source_files
        or len(source_files) > limits.files
        or len(set(source_files)) != len(source_files)
    ):
        _fail(
            "INVALID_SOURCE_SELECTION",
            "Select one or more unique uploaded inventory sources in explicit order.",
        )
    inventory = _Inventory(budget)
    formats: list[dict[str, str]] = []
    for path in source_files:
        _member_path(path, budget)
        with _location(path, "inventory"):
            if path not in files:
                _fail("SOURCE_NOT_FOUND", "A selected inventory source is absent from this upload.")
            raw = files[path]
            role, detected = _role(path, raw)
            if role != "source" or detected is None:
                _fail(
                    "SOURCE_UNSUPPORTED",
                    "Selected source is not a supported static inventory file; executable/plugin/other files are never executed.",
                )
            if raw.lstrip().startswith(b"#!"):
                _fail(
                    "DYNAMIC_INVENTORY_UNSUPPORTED",
                    "Executable inventories are unsupported; upload static inventory or canonical JSON.",
                )
            selected_format = detected if format in {"auto", "static_zip"} else format
            formats.append({"source": path, "format": selected_format})
            if selected_format == "ini":
                inventory.ini(raw, path)
            elif selected_format == "yaml":
                inventory.yaml(_data(raw, selected_format, budget), path)
            else:
                inventory.canonical(_data(raw, selected_format, budget), path)
    companions = inventory.companions(files, source_files) if is_zip else []
    used = set(source_files) | set(companions)
    ignored = sorted(set(files) - used)
    inventory.warnings.extend(manifest["warnings"])
    if ignored:
        inventory.warnings.append(
            _warning(
                "FILES_IGNORED",
                "Unselected and unsupported files were ignored without execution.",
                files=ignored,
                count=len(ignored),
            )
        )
    result = inventory.normalize()
    result["manifest"] = manifest
    result["provenance"] = {
        "source_files": source_files,
        "sources": formats,
        "companion_files": companions,
        "ignored_files": ignored,
    }
    budget.check()
    return result
