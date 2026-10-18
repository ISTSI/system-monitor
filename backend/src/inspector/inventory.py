"""Bounded static uploads and revision-bound, atomic inventory reconciliation.

Raw content is restricted, expiring local staging. MariaDB retains only sanitized
normalization and field baselines. Import never contacts or approves a target.
"""

import asyncio
import copy
import hashlib
import json
import os
import posixpath
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import unquote
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import APIRouter, Depends, Request
from jsonschema import Draft202012Validator
from pydantic import Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from inspector import inventory_parser, project_config, services, topology
from inspector.config import Config
from inspector.domain import ID_PATTERN, Principal
from inspector.errors import DomainError
from inspector.persistence.inventory_models import (
    InventoryHostMapping,
    InventoryPreview,
    InventoryProcessMapping,
    InventorySource,
    InventoryUpload,
)
from inspector.persistence.models import ProjectCredentialBinding
from inspector.security import authorize

LEASE_US = 900_000_000
MAX_PENDING = 10
_LOG_VALIDATOR = Draft202012Validator(
    json.loads(
        (Path(__file__).parent / "contracts" / "project.schema.json").read_text(encoding="utf-8")
    )["properties"]["processes"]["items"]["properties"]["log_source"]
)


class SourceInput(topology.StrictInput):
    name: str = Field(min_length=1, max_length=256, pattern=r"\S")


class ParseInput(topology.RevisionInput):
    inventory_source_id: str = Field(pattern=ID_PATTERN)
    upload_id: str = Field(pattern=ID_PATTERN)
    format: Literal["ini", "yaml", "canonical_json", "static_zip"]
    source_files: list[str] = Field(min_length=1, max_length=200)


class MappingInput(topology.StrictInput):
    group_to_subsystem: dict[str, str] = Field(max_length=1000)
    host_to_subsystem: dict[str, str] = Field(max_length=1000)
    tag_only_groups: list[str] = Field(max_length=200)
    credential_mapping: dict[str, str] = Field(max_length=1000)
    jump_mapping: dict[str, str | None] = Field(max_length=1000)
    parser_mapping: dict[str, str] = Field(max_length=1000)
    preserve_existing_documentation: Literal[True]
    preserve_existing_layout: Literal[True]
    delete_missing_hosts: Literal[False]


class PreviewInput(ParseInput):
    project_id: str = Field(pattern=ID_PATTERN)
    mapping: MappingInput


class CommitInput(topology.RevisionInput):
    preview_id: str = Field(pattern=ID_PATTERN)


class EmptyInput(topology.StrictInput):
    pass


class SourceResponse(topology.StrictInput):
    project_id: str
    id: str
    name: str
    created_us: str


class SourcesResponse(topology.StrictInput):
    project_id: str
    items: list[SourceResponse]


class UploadResponse(topology.StrictInput):
    project_id: str
    inventory_source_id: str
    upload_id: str
    expected_revision: int
    expires_us: str
    filename: str
    format: str | None
    files: list[dict[str, Any]]
    file_count: int
    expanded_bytes: int
    source_candidates: list[str]
    ignored_files: list[str]
    warnings: list[dict[str, Any]]
    content_sha256: str
    manifest_sha256: str


class ParseResponse(topology.StrictInput):
    project_id: str
    inventory_source_id: str
    upload_id: str
    expected_revision: int
    hosts: list[dict[str, Any]]
    groups: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    provenance: dict[str, Any]
    manifest: dict[str, Any]
    process_count: int
    omitted_variables: list[dict[str, Any]]


class PreviewResponse(topology.StrictInput):
    project_id: str
    inventory_source_id: str
    preview_id: str
    expected_revision: int
    expires_us: str
    can_commit: bool
    records: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    process_count: int


class CancelResponse(topology.StrictInput):
    cancelled: bool


def digest(value: Any) -> str:
    return hashlib.sha256(topology.canonical_bytes(value)).hexdigest()


def source_response(row: InventorySource) -> dict:
    return dict(project_id=row.project_id, id=row.id, name=row.name, created_us=str(row.created_us))


def inventory_limits(config: Config) -> inventory_parser.InventoryLimits:
    """Apply every configured lower ceiling without raising parser hard bounds."""
    defaults = inventory_parser.DEFAULT_LIMITS
    return inventory_parser.InventoryLimits(
        upload_bytes=min(
            config.inventory_upload_bytes, config.config_upload_bytes, defaults.upload_bytes
        ),
        expanded_bytes=min(config.inventory_expanded_bytes, defaults.expanded_bytes),
        files=min(config.inventory_file_limit, defaults.files),
        hosts=min(project_config.MAX_ENTITIES, defaults.hosts),
        groups=min(project_config.MAX_ENTITIES, defaults.groups),
        processes=min(project_config.MAX_ENTITIES, defaults.processes),
    )


class InventoryStaging:
    def __init__(self, state_dir: str, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.directory = Path(state_dir) / "inventory-staging"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            self.directory.chmod(0o700)
        self.sessions = sessions
        self.slots = asyncio.Semaphore(2)
        self.operations: dict[tuple[str, str], set[threading.Event]] = {}
        self.task: asyncio.Task | None = None

    def path(self, identifier: str) -> Path:
        # Filenames are generated server UUIDs, never archive/user names.
        if re.fullmatch(r"[a-f0-9-]{36}", identifier) is None:
            raise DomainError("NOT_FOUND", "Resource not found.", 404)
        return self.directory / identifier

    def cancel(self, project_id: str, identifier: str) -> None:
        for signal in self.operations.get((project_id, identifier), set()):
            signal.set()

    async def remove(self, identifier: str, *, project_id: str | None = None) -> None:
        if project_id is not None:
            self.cancel(project_id, identifier)
        await topology.cpu_work(lambda: self.path(identifier).unlink(missing_ok=True))

    async def purge(self, *, restart: bool = False) -> None:
        async with self.sessions.begin() as session:
            now = services.utc_now_us()
            expired = list(
                (
                    await session.scalars(
                        select(InventoryUpload).where(InventoryUpload.expires_us <= now)
                    )
                ).all()
            )
            await session.execute(
                delete(InventoryPreview).where(InventoryPreview.expires_us <= now)
            )
            for upload in expired:
                await session.execute(
                    delete(InventoryPreview).where(
                        InventoryPreview.project_id == upload.project_id,
                        InventoryPreview.upload_id == upload.id,
                    )
                )
                await self.remove(upload.id, project_id=upload.project_id)
                await session.delete(upload)
            if restart:
                valid = set((await session.scalars(select(InventoryUpload.id))).all())

                # Remove incomplete uploads left by cancellation or an interrupted transaction.
                def remove_orphans() -> None:
                    for item in self.directory.iterdir():
                        if item.is_file() and item.name not in valid:
                            item.unlink()

                await topology.cpu_work(remove_orphans)

    async def start(self) -> None:
        await self.purge(restart=True)
        self.task = asyncio.create_task(self._reap())

    async def _reap(self) -> None:
        while True:
            await asyncio.sleep(30)
            try:
                await self.purge()
            except Exception:
                # Never log uploaded content, parser exceptions or database parameters.
                continue

    async def close(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


async def source_in_context(
    session: AsyncSession, project_id: str, identifier: str
) -> InventorySource:
    source = await session.get(InventorySource, (project_id, identifier))
    if source is None:
        raise DomainError("NOT_FOUND", "Resource not found.", 404)
    return source


async def upload_in_context(
    session: AsyncSession, actor: Principal, project_id: str, identifier: str
) -> InventoryUpload:
    upload = await session.scalar(
        select(InventoryUpload)
        .where(
            InventoryUpload.project_id == project_id,
            InventoryUpload.id == identifier,
            InventoryUpload.owner_user_id == actor.user_id,
        )
        .with_for_update()
    )
    if upload is None:
        raise DomainError("NOT_FOUND", "Resource not found.", 404)
    if upload.expires_us <= services.utc_now_us():
        raise DomainError("PREVIEW_EXPIRED", "Inventory upload expired; upload again.", 410)
    if upload.auth_version != actor.auth_version:
        raise DomainError("REVISION_CONFLICT", "Authorization changed; upload again.", 409)
    return upload


async def parse_upload(request: Request, upload: InventoryUpload, payload: ParseInput) -> dict:
    if upload.source_id != payload.inventory_source_id:
        raise DomainError("NOT_FOUND", "Resource not found.", 404)
    if upload.expected_revision != payload.expected_revision:
        raise DomainError("REVISION_CONFLICT", "Upload revision changed; upload again.", 409)
    staging: InventoryStaging = request.app.state.inventory

    def parse(cancelled: Callable[[], bool]) -> dict:
        try:
            data = staging.path(upload.id).read_bytes()
        except FileNotFoundError:
            raise DomainError(
                "PREVIEW_EXPIRED", "Inventory staging is unavailable; upload again.", 410
            ) from None
        if hashlib.sha256(data).hexdigest() != upload.digest:
            raise DomainError("REVISION_CONFLICT", "Inventory content changed; upload again.", 409)
        try:
            return inventory_parser.parse_inventory(
                upload.filename,
                data,
                format=payload.format,
                source_files=payload.source_files,
                limits=inventory_limits(request.app.state.config),
                cancelled=cancelled,
            )
        except inventory_parser.InventoryParseError as error:
            raise DomainError(error.code, error.message, 422) from None

    return await inventory_work(request, upload.project_id, upload.id, parse)


async def inventory_work[Result](
    request: Request,
    project_id: str,
    upload_id: str,
    operation: Callable[[Callable[[], bool]], Result],
) -> Result:
    """Cooperate with cancellation while retaining the shared worker reservation."""
    staging: InventoryStaging = request.app.state.inventory
    key = (project_id, upload_id)
    signal = threading.Event()
    staging.operations.setdefault(key, set()).add(signal)

    async def disconnected() -> None:
        while not signal.is_set():
            if await request.is_disconnected():
                signal.set()
                return
            await asyncio.sleep(0.05)

    watcher = asyncio.create_task(disconnected())
    worker = asyncio.create_task(topology.cpu_work(lambda: operation(signal.is_set)))
    was_cancelled = False
    try:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                was_cancelled = True
                signal.set()
            except Exception:
                if not was_cancelled:
                    raise
        if was_cancelled:
            if not worker.cancelled():
                worker.exception()
            raise asyncio.CancelledError
        return worker.result()
    finally:
        signal.set()
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        pending = staging.operations.get(key)
        if pending is not None:
            pending.discard(signal)
            if not pending:
                staging.operations.pop(key, None)


def identity(source_id: str, alias: str, kind: str, local_id: str = "") -> str:
    return str(
        uuid5(NAMESPACE_URL, json.dumps([source_id, alias, kind, local_id], separators=(",", ":")))
    )


def proposal_roots(paths: list[str]) -> list[str]:
    """Confined literal parent proposals, including wildcard directory patterns."""
    candidates = set()
    for path in paths:
        first_pattern = min(
            (path.index(char) for char in ("*", "?", "[") if char in path), default=len(path)
        )
        candidates.add(posixpath.dirname(path[:first_pattern]) or "/")
    roots: list[str] = []
    for root in sorted(candidates, key=lambda candidate: (len(candidate), candidate)):
        if not any(
            root == ancestor or root.startswith(ancestor.rstrip("/") + "/") for ancestor in roots
        ):
            roots.append(root)
    return sorted(roots)


def managed(item: dict, fields: tuple[str, ...]) -> dict:
    return {field: copy.deepcopy(item[field]) for field in fields}


SERVER_FIELDS = ("name", "subsystem_id", "connection_id")
CONNECTION_FIELDS = (
    "host",
    "port",
    "username",
    "credential_ref",
    "jump_connection_id",
    "allowed_log_roots",
)
PROCESS_FIELDS = ("name", "server_id", "pcs_resource_name", "log_source")


def validate_extensions(parsed: dict) -> None:
    for host in parsed["hosts"]:
        for index, process in enumerate(host["processes"]):
            error = next(_LOG_VALIDATOR.iter_errors(process.get("log_source")), None)
            if error is not None:
                path = f"inspector_processes[{index}].log_source"
                for part in error.path:
                    if isinstance(part, int):
                        path += f"[{part}]"
                    elif isinstance(part, str) and re.fullmatch(r"[a-z_]{1,64}", part):
                        path += "." + part
                if error.validator == "required" and isinstance(error.instance, dict):
                    missing = next(
                        (key for key in error.validator_value if key not in error.instance), None
                    )
                    if isinstance(missing, str) and re.fullmatch(r"[a-z_]{1,64}", missing):
                        path += "." + missing
                provenance = host.get("effective_provenance", {}).get("inspector_processes")
                if not isinstance(provenance, dict):
                    records = host.get("provenance", {}).get("inspector_processes", [])
                    provenance = records[-1] if records else {}
                source = provenance.get("source")
                location = (
                    source
                    if isinstance(source, str)
                    and len(source) <= 512
                    and not any(ord(char) < 32 or ord(char) == 127 for char in source)
                    else "inventory"
                )
                if type(provenance.get("line")) is int and provenance["line"] > 0:
                    location += f":{provenance['line']}"
                raise DomainError(
                    "INVALID_LOG_SOURCE",
                    f"{location}: {path}: invalid log-source definition.",
                    422,
                )


def reconcile(
    config: dict,
    parsed: dict,
    source_id: str,
    mapping: dict,
    host_rows: list[InventoryHostMapping],
    process_rows: list[InventoryProcessMapping],
    credential_aliases: set[str],
) -> dict:
    """Pure merge: missing/manual/geometry/documentation/flow records survive."""
    value = copy.deepcopy(config)
    validate_extensions(parsed)
    by_id = {
        collection: {item["id"]: item for item in value[collection]}
        for collection in topology.COLLECTIONS
    }
    hosts = {row.alias: row for row in host_rows}
    processes = {(row.alias, row.local_id): row for row in process_rows}
    records: list[dict] = []
    conflicts = []
    parsed_by_alias = {host["alias"]: host for host in parsed["hosts"]}
    for conflict in parsed["conflicts"]:
        alias = conflict.get("alias")
        explicitly_resolved = conflict.get("key") == "inspector_subsystem" and (
            alias in mapping["host_to_subsystem"]
            or len(
                {
                    mapping["group_to_subsystem"][group]
                    for group in parsed_by_alias.get(alias, {}).get("groups", [])
                    if group in mapping["group_to_subsystem"]
                }
            )
            == 1
        )
        if not explicitly_resolved:
            conflicts.append(copy.deepcopy(conflict))
    host_baselines, process_baselines = [], []
    aliases = {host["alias"] for host in parsed["hosts"]}
    group_names = {group["name"] for group in parsed["groups"]}
    for key in (
        "group_to_subsystem",
        "host_to_subsystem",
        "credential_mapping",
        "jump_mapping",
        "parser_mapping",
    ):
        for name, target in mapping[key].items():
            if re.fullmatch(ID_PATTERN, name) is None or (
                target is not None and re.fullmatch(ID_PATTERN, target) is None
            ):
                raise DomainError(
                    "INVALID_MAPPING",
                    "Mapping identifiers must use the supported identifier syntax.",
                    422,
                )
    if (
        set(mapping["host_to_subsystem"]) - aliases
        or set(mapping["group_to_subsystem"]) - group_names
        or set(mapping["tag_only_groups"]) - group_names
    ):
        raise DomainError(
            "INVALID_MAPPING",
            "Mapping references a host/group outside this uploaded inventory.",
            422,
        )
    if set(mapping["credential_mapping"]) - aliases or set(mapping["jump_mapping"]) - aliases:
        raise DomainError(
            "INVALID_MAPPING", "Connection mapping references an unknown inventory host.", 422
        )
    if set(mapping["credential_mapping"].values()) - credential_aliases:
        raise DomainError(
            "INVALID_MAPPING", "Credentials must be explicitly bound to the selected system.", 422
        )
    for jump in mapping["jump_mapping"].values():
        if jump is not None and (
            jump not in by_id["connections"]
            or by_id["connections"][jump]["jump_connection_id"] is not None
        ):
            raise DomainError(
                "INVALID_MAPPING",
                "Jump profiles must exist in this system and have no jump of their own.",
                422,
            )
    for parser_id in mapping["parser_mapping"].values():
        if parser_id not in by_id["parsers"]:
            raise DomainError(
                "INVALID_MAPPING", "Parser mapping must resolve inside this system.", 422
            )

    def add_record(
        kind: str,
        alias: str,
        target_id: str,
        before: dict | None,
        after: dict,
        baseline: dict | None,
        local_id: str | None = None,
    ) -> dict:
        changed = [
            dict(field=field, before=(before or {}).get(field), after=after[field])
            for field in after
            if before is None or before.get(field) != after[field]
        ]
        manual = [
            field
            for field, previous in (baseline or {}).items()
            if before is None or before.get(field) != previous
        ]
        status = (
            "conflicting"
            if manual
            else "added"
            if before is None
            else "changed"
            if changed
            else "unchanged"
        )
        record = dict(kind=kind, alias=alias, target_id=target_id, status=status, changes=changed)
        if local_id is not None:
            record["local_id"] = local_id
        if manual:
            record["message"] = (
                "Previously imported fields were edited manually; preserve or resolve them before importing."
            )
            record["manual_fields"] = manual
            conflicts.append(
                dict(code="MANUAL_EDIT", alias=alias, target_id=target_id, fields=manual)
            )
        records.append(record)
        return record

    for host in parsed["hosts"]:
        alias = host["alias"]
        prior = hosts.get(alias)
        server_id = prior.server_id if prior else identity(source_id, alias, "server")
        connection_id = prior.connection_id if prior else identity(source_id, alias, "connection")
        existing_server, existing_connection = (
            by_id["servers"].get(server_id),
            by_id["connections"].get(connection_id),
        )
        if prior is None and (existing_server is not None or existing_connection is not None):
            records.append(
                dict(
                    kind="host",
                    alias=alias,
                    target_id=server_id,
                    status="conflicting",
                    changes=[],
                    message="Proposed identity already belongs to an entity without this source mapping.",
                )
            )
            conflicts.append(dict(code="IDENTITY_COLLISION", alias=alias, target_id=server_id))
            continue
        selected = (
            {mapping["host_to_subsystem"][alias]}
            if alias in mapping["host_to_subsystem"]
            else {
                mapping["group_to_subsystem"][group]
                for group in host["groups"]
                if group in mapping["group_to_subsystem"]
            }
        )
        if not selected and host.get("vars", {}).get("inspector_subsystem"):
            selected = {host["vars"]["inspector_subsystem"]}
        if len(selected) != 1:
            records.append(
                dict(
                    kind="host",
                    alias=alias,
                    target_id=server_id,
                    status="conflicting" if selected else "unassigned",
                    changes=[],
                    message="Each host requires exactly one selected subsystem.",
                )
            )
            conflicts.append(
                dict(code="SUBSYSTEM_CONFLICT" if selected else "SUBSYSTEM_UNASSIGNED", alias=alias)
            )
            continue
        subsystem_id = next(iter(selected))
        if not isinstance(subsystem_id, str) or re.fullmatch(ID_PATTERN, subsystem_id) is None:
            raise DomainError(
                "INVALID_MAPPING", "Subsystem IDs must use the supported identifier syntax.", 422
            )
        if subsystem_id not in by_id["subsystems"]:
            subsystem = dict(id=subsystem_id, name=subsystem_id, description="", tags=[])
            value["subsystems"].append(subsystem)
            by_id["subsystems"][subsystem_id] = subsystem
        imported_tags = sorted(set(host["groups"]) & set(mapping["tag_only_groups"]))
        old_tags = prior.baseline.get("tags", []) if prior else []
        tags = sorted(
            (set(existing_server["tags"]) - set(old_tags) if existing_server else set())
            | set(imported_tags)
        )
        server = (
            copy.deepcopy(existing_server)
            if existing_server
            else dict(id=server_id, description="")
        ) | dict(name=alias, subsystem_id=subsystem_id, connection_id=connection_id, tags=tags)
        paths = [
            process["log_source"]["active_path"]
            for process in host["processes"]
            if isinstance(process.get("log_source"), dict)
            and isinstance(process["log_source"].get("active_path"), str)
        ]
        for process in host["processes"]:
            source = process.get("log_source", {})
            paths.extend(source.get("rotated_patterns", []))
            paths.extend(item["path_pattern"] for item in source.get("archives", []))
        roots = proposal_roots(paths)
        if any(root == "/" for root in roots):
            conflicts.append(
                dict(
                    code="ROOT_MAPPING_REQUIRED",
                    alias=alias,
                    message="Top-level logs require an explicit confined path definition outside inventory import.",
                )
            )
        connection = dict(
            id=connection_id,
            name=(existing_connection["name"] if existing_connection else alias),
            host=host["address"],
            port=host["port"],
            username=host.get("user") or "unresolved-log-reader",
            credential_ref=mapping["credential_mapping"].get(
                alias,
                (
                    existing_connection["credential_ref"]
                    if existing_connection
                    else "unresolved-" + connection_id
                ),
            ),
            jump_connection_id=mapping["jump_mapping"].get(
                alias, existing_connection["jump_connection_id"] if existing_connection else None
            ),
            allowed_log_roots=sorted(
                set(roots)
                | set(existing_connection["allowed_log_roots"] if existing_connection else [])
            ),
        )
        before = (
            dict(
                server=managed(existing_server, SERVER_FIELDS),
                connection=managed(existing_connection, CONNECTION_FIELDS),
            )
            if existing_server and existing_connection
            else None
        )
        after = dict(
            server=managed(server, SERVER_FIELDS), connection=managed(connection, CONNECTION_FIELDS)
        )
        baseline = {key: prior.baseline[key] for key in ("server", "connection")} if prior else None
        record = add_record("host", alias, server_id, before, after, baseline)
        record["provenance"] = host.get("provenance", {})
        if existing_server is None or existing_server["tags"] != tags:
            record["changes"].append(
                dict(
                    field="tags",
                    before=existing_server["tags"] if existing_server else None,
                    after=tags,
                )
            )
            if record["status"] == "unchanged":
                record["status"] = "changed"
        if record["status"] != "conflicting":
            for collection, merged_item in (("servers", server), ("connections", connection)):
                if merged_item["id"] in by_id[collection]:
                    by_id[collection][merged_item["id"]].update(merged_item)
                else:
                    value[collection].append(merged_item)
                    by_id[collection][merged_item["id"]] = merged_item
        host_baselines.append(
            dict(
                alias=alias,
                server_id=server_id,
                connection_id=connection_id,
                baseline=after | {"tags": imported_tags},
            )
        )
        seen_local: set[str] = set()
        for process in host["processes"]:
            local_id = process["id"]
            if local_id in seen_local or re.fullmatch(ID_PATTERN, local_id) is None:
                raise DomainError(
                    "INVALID_MAPPING",
                    "Process extension IDs must be valid and unique per host.",
                    422,
                )
            seen_local.add(local_id)
            prior_process = processes.get((alias, local_id))
            process_id = (
                prior_process.process_id
                if prior_process
                else identity(source_id, alias, "process", local_id)
            )
            existing = by_id["processes"].get(process_id)
            if prior_process is None and existing is not None:
                records.append(
                    dict(
                        kind="process",
                        alias=alias,
                        local_id=local_id,
                        target_id=process_id,
                        status="conflicting",
                        changes=[],
                        message="Proposed identity already belongs to a process without this source mapping.",
                    )
                )
                conflicts.append(
                    dict(
                        code="IDENTITY_COLLISION",
                        alias=alias,
                        local_id=local_id,
                        target_id=process_id,
                    )
                )
                continue
            item: dict[str, Any] = (
                copy.deepcopy(existing)
                if existing
                else dict(id=process_id, description="", tags=[])
            )
            item.update(
                name=process["name"],
                server_id=server_id,
                pcs_resource_name=process.get("pcs_resource_name"),
                log_source=copy.deepcopy(process["log_source"]),
            )
            original_parser = item["log_source"]["parser_id"]
            item["log_source"]["parser_id"] = mapping["parser_mapping"].get(
                original_parser, original_parser
            )
            if item["log_source"]["parser_id"] not in by_id["parsers"]:
                records.append(
                    dict(
                        kind="process",
                        alias=alias,
                        local_id=local_id,
                        target_id=process_id,
                        status="unassigned",
                        changes=[],
                        message="Map the log parser to a parser in this system.",
                    )
                )
                conflicts.append(
                    dict(
                        code="PARSER_UNASSIGNED",
                        alias=alias,
                        local_id=local_id,
                        parser_id=original_parser,
                    )
                )
                continue
            after_process = managed(item, PROCESS_FIELDS)
            process_record = add_record(
                "process",
                alias,
                process_id,
                managed(existing, PROCESS_FIELDS) if existing else None,
                after_process,
                prior_process.baseline if prior_process else None,
                local_id,
            )
            if process_record["status"] != "conflicting":
                if existing:
                    existing.update(item)
                else:
                    value["processes"].append(item)
                    by_id["processes"][process_id] = item
            process_baselines.append(
                dict(alias=alias, local_id=local_id, process_id=process_id, baseline=after_process)
            )
        for (old_alias, local_id), row in processes.items():
            if old_alias == alias and local_id not in seen_local:
                records.append(
                    dict(
                        kind="process",
                        alias=alias,
                        local_id=local_id,
                        target_id=row.process_id,
                        status="absent",
                        changes=[],
                        message="Absent from upload; retained unchanged.",
                    )
                )
    for alias, host_row in hosts.items():
        if alias not in aliases:
            records.append(
                dict(
                    kind="host",
                    alias=alias,
                    target_id=host_row.server_id,
                    status="absent",
                    changes=[],
                    message="Absent from upload; retained unchanged.",
                )
            )
            for (old_alias, local_id), process_row in processes.items():
                if old_alias == alias:
                    records.append(
                        dict(
                            kind="process",
                            alias=alias,
                            local_id=local_id,
                            target_id=process_row.process_id,
                            status="absent",
                            changes=[],
                            message="Host absent from upload; process retained unchanged.",
                        )
                    )
    if not conflicts:
        try:
            project_config.validate_project(value)
        except DomainError as error:
            conflicts.append(dict(code=error.code, message=error.message))
    return dict(
        config=value,
        host_baselines=host_baselines,
        process_baselines=process_baselines,
        records=records,
        conflicts=conflicts,
        can_commit=not conflicts,
        process_count=parsed["process_count"],
        warnings=parsed["warnings"]
        + [
            dict(
                code="UNRESOLVED_USERNAME",
                alias=host["alias"],
                message="No ansible_user was supplied; the disabled proposal uses an unresolved account placeholder. Configure a dedicated log-read account before access testing.",
            )
            for host in parsed["hosts"]
            if not host.get("user")
        ]
        + [
            dict(
                code="NO_APPROVAL",
                message="Imported targets, roots and credentials require separate project binding and approval; SSH host keys remain untrusted. Import makes no network connection.",
            )
        ],
    )


def build_inventory_router(transaction: Any, authenticated: Any, protected_write: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}/inventory")
    Session = Annotated[AsyncSession, Depends(transaction, scope="function")]
    Actor = Annotated[Principal, Depends(authenticated)]
    Writer = Annotated[Principal, Depends(protected_write)]

    @router.get(
        "/sources",
        response_model=SourcesResponse,
        openapi_extra={"x-permission": "inventory.source.manage"},
    )
    async def list_sources(project_id: str, actor: Actor, session: Session) -> dict:
        await topology.context(session, actor, project_id, "inventory.source.manage")
        rows = (
            await session.scalars(
                select(InventorySource)
                .where(InventorySource.project_id == project_id)
                .order_by(InventorySource.created_us)
            )
        ).all()
        return dict(project_id=project_id, items=[source_response(row) for row in rows])

    @router.post(
        "/sources",
        response_model=SourceResponse,
        openapi_extra={"x-permission": "inventory.source.manage"},
    )
    async def create_source(
        project_id: str, payload: SourceInput, actor: Writer, session: Session
    ) -> dict:
        actor, project, _state = await topology.context(
            session, actor, project_id, "inventory.source.manage", writable=True
        )
        name = payload.name.strip()
        if any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise DomainError(
                "INVALID_MAPPING", "Source name contains unsupported control characters.", 422
            )
        name_key = hashlib.sha256(name.casefold().encode()).hexdigest()
        if await session.scalar(
            select(InventorySource.id).where(
                InventorySource.project_id == project_id, InventorySource.name_key == name_key
            )
        ):
            raise DomainError(
                "NAME_CONFLICT",
                "A source with this name already exists in the selected system.",
                409,
            )
        count = await session.scalar(
            select(func.count())
            .select_from(InventorySource)
            .where(InventorySource.project_id == project_id)
        )
        if (count or 0) >= 100:
            raise DomainError("LIMIT_REACHED", "System inventory source limit reached.", 429)
        row = InventorySource(
            project_id=project_id,
            id=str(uuid4()),
            name=name,
            name_key=name_key,
            created_us=services.utc_now_us(),
        )
        session.add(row)
        services.audit(
            session, actor, "inventory.source.create", project.id, row.id, services.utc_now_us()
        )
        await session.flush()
        return source_response(row)

    @router.post(
        "/uploads",
        response_model=UploadResponse,
        openapi_extra={"x-permission": "inventory.upload"},
    )
    async def upload(
        project_id: str,
        request: Request,
        actor: Writer,
        session: Session,
        inventory_source_id: str,
        expected_revision: int,
    ) -> dict:
        actor, project, _state = await topology.context(
            session, actor, project_id, "inventory.upload", writable=True
        )
        topology.check_revision(project, expected_revision)
        await source_in_context(session, project_id, inventory_source_id)
        filename = unquote(request.headers.get("x-inventory-filename", ""))
        if (
            not filename
            or len(filename) > 256
            or any(ord(char) < 32 or ord(char) == 127 for char in filename)
            or "/" in filename
            or "\\" in filename
        ):
            raise DomainError(
                "INVALID_INVENTORY",
                "Supply a single inventory filename without directory components.",
                422,
            )
        count = await session.scalar(
            select(func.count())
            .select_from(InventoryUpload)
            .where(
                InventoryUpload.owner_user_id == actor.user_id,
                InventoryUpload.expires_us > services.utc_now_us(),
            )
        )
        if (count or 0) >= MAX_PENDING:
            raise DomainError(
                "LIMIT_REACHED",
                "Too many pending uploads; cancel an upload or wait for expiry.",
                429,
            )
        staging: InventoryStaging = request.app.state.inventory
        if staging.slots.locked():
            raise DomainError(
                "LIMIT_REACHED", "Inventory upload workers are busy; retry later.", 429
            )
        await staging.slots.acquire()
        identifier = str(uuid4())
        path = staging.path(identifier)
        try:
            # Login and topology locks must not span client streaming or parsing.
            await session.commit()
            fd = await topology.cpu_work(
                lambda: os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            )
            try:
                size = 0
                async with asyncio.timeout(30):
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > inventory_limits(request.app.state.config).upload_bytes:
                            raise DomainError(
                                "PAYLOAD_TOO_LARGE", "Inventory exceeds the upload byte limit.", 413
                            )

                        def write_chunk(data: bytes = chunk) -> None:
                            view = memoryview(data)
                            while view:
                                view = view[os.write(fd, view) :]

                        await topology.cpu_work(write_chunk)
            finally:
                os.close(fd)

            def inspect(cancelled: Callable[[], bool]) -> dict:
                try:
                    return inventory_parser.inspect_upload(
                        filename,
                        path.read_bytes(),
                        limits=inventory_limits(request.app.state.config),
                        cancelled=cancelled,
                    )
                except inventory_parser.InventoryParseError as error:
                    raise DomainError(error.code, error.message, 422) from None

            summary = await inventory_work(request, project_id, identifier, inspect)
            session.expire_all()
            actor = await authenticated(request, session)
            actor, project, _state = await topology.context(
                session, actor, project_id, "inventory.upload", writable=True
            )
            topology.check_revision(project, expected_revision)
            await source_in_context(session, project_id, inventory_source_id)
            count = await session.scalar(
                select(func.count())
                .select_from(InventoryUpload)
                .where(
                    InventoryUpload.owner_user_id == actor.user_id,
                    InventoryUpload.expires_us > services.utc_now_us(),
                )
            )
            if (count or 0) >= MAX_PENDING:
                raise DomainError(
                    "LIMIT_REACHED",
                    "Too many pending uploads; cancel an upload or wait for expiry.",
                    429,
                )
            row = InventoryUpload(
                project_id=project_id,
                id=identifier,
                source_id=inventory_source_id,
                owner_user_id=actor.user_id,
                auth_version=actor.auth_version,
                expected_revision=project.revision,
                filename=filename,
                digest=summary["content_sha256"],
                manifest_digest=summary["manifest_sha256"],
                summary=summary,
                expires_us=services.utc_now_us() + LEASE_US,
            )
            session.add(row)
            await session.flush()
            return dict(
                project_id=project_id,
                inventory_source_id=inventory_source_id,
                upload_id=identifier,
                expected_revision=project.revision,
                expires_us=str(row.expires_us),
                **summary,
            )
        except TimeoutError:
            await staging.remove(identifier, project_id=project_id)
            raise DomainError(
                "IMPORT_TIMEOUT", "Inventory upload exceeded the time limit.", 408
            ) from None
        except BaseException:
            await staging.remove(identifier, project_id=project_id)
            raise
        finally:
            staging.slots.release()

    @router.post(
        "/parse", response_model=ParseResponse, openapi_extra={"x-permission": "inventory.import"}
    )
    async def parse(
        project_id: str, payload: ParseInput, actor: Writer, session: Session, request: Request
    ) -> dict:
        actor, project, _state = await topology.context(
            session, actor, project_id, "inventory.import", writable=True
        )
        topology.check_revision(project, payload.expected_revision)
        upload = await upload_in_context(session, actor, project_id, payload.upload_id)
        await session.commit()
        parsed = await parse_upload(request, upload, payload)
        await topology.cpu_work(lambda: validate_extensions(parsed))
        session.expire_all()
        actor = await authenticated(request, session)
        actor, project, _state = await topology.context(
            session, actor, project_id, "inventory.import", writable=True
        )
        topology.check_revision(project, payload.expected_revision)
        upload = await upload_in_context(session, actor, project_id, payload.upload_id)
        return dict(
            project_id=project_id,
            inventory_source_id=upload.source_id,
            upload_id=upload.id,
            expected_revision=project.revision,
            **parsed,
        )

    @router.post(
        "/preview",
        response_model=PreviewResponse,
        openapi_extra={"x-permission": "inventory.import"},
    )
    async def preview(
        project_id: str, payload: PreviewInput, actor: Writer, session: Session, request: Request
    ) -> dict:
        actor, project, state = await topology.context(
            session, actor, project_id, "inventory.import", writable=True
        )
        if project_id != payload.project_id:
            raise DomainError("PROJECT_MISMATCH", "Route and mapping system must agree.", 422)
        topology.check_revision(project, payload.expected_revision)
        upload = await upload_in_context(session, actor, project_id, payload.upload_id)
        await session.commit()
        parsed = await parse_upload(request, upload, payload)
        session.expire_all()
        actor = await authenticated(request, session)
        actor, project, state = await topology.context(
            session, actor, project_id, "inventory.import", writable=True
        )
        topology.check_revision(project, payload.expected_revision)
        upload = await upload_in_context(session, actor, project_id, payload.upload_id)
        host_rows = list(
            (
                await session.scalars(
                    select(InventoryHostMapping).where(
                        InventoryHostMapping.project_id == project_id,
                        InventoryHostMapping.source_id == upload.source_id,
                    )
                )
            ).all()
        )
        process_rows = list(
            (
                await session.scalars(
                    select(InventoryProcessMapping).where(
                        InventoryProcessMapping.project_id == project_id,
                        InventoryProcessMapping.source_id == upload.source_id,
                    )
                )
            ).all()
        )
        credentials = set(
            (
                await session.scalars(
                    select(ProjectCredentialBinding.alias).where(
                        ProjectCredentialBinding.project_id == project_id
                    )
                )
            ).all()
        )
        mapping = payload.mapping.model_dump()
        config_snapshot = copy.deepcopy(state.config)
        await session.commit()
        document = await topology.cpu_work(
            lambda: reconcile(
                config_snapshot,
                parsed,
                upload.source_id,
                mapping,
                host_rows,
                process_rows,
                credentials,
            )
        )
        document["mapping"] = mapping
        document["source_files"] = payload.source_files
        document["format"] = payload.format

        def check_size() -> None:
            if (
                len(topology.canonical_bytes(document["config"]))
                > request.app.state.config.config_upload_bytes
                or len(topology.canonical_bytes(document)) > 20 * 1024 * 1024
            ):
                raise DomainError(
                    "PAYLOAD_TOO_LARGE", "Normalized inventory exceeds the preview byte limit.", 413
                )

        await topology.cpu_work(check_size)
        session.expire_all()
        actor = await authenticated(request, session)
        actor, project, state = await topology.context(
            session, actor, project_id, "inventory.import", writable=True
        )
        topology.check_revision(project, payload.expected_revision)
        upload = await upload_in_context(session, actor, project_id, payload.upload_id)
        await session.execute(
            delete(InventoryPreview).where(
                InventoryPreview.project_id == project_id, InventoryPreview.upload_id == upload.id
            )
        )
        pending = InventoryPreview(
            project_id=project_id,
            id=str(uuid4()),
            source_id=upload.source_id,
            upload_id=upload.id,
            owner_user_id=actor.user_id,
            auth_version=actor.auth_version,
            expected_revision=project.revision,
            content_digest=upload.digest,
            manifest_digest=upload.manifest_digest,
            mapping_digest=digest(mapping),
            digest=digest(document),
            document=document,
            expires_us=upload.expires_us,
        )
        session.add(pending)
        await session.flush()
        return dict(
            project_id=project_id,
            inventory_source_id=upload.source_id,
            preview_id=pending.id,
            expected_revision=project.revision,
            expires_us=str(pending.expires_us),
            **{
                key: document[key]
                for key in ("can_commit", "records", "warnings", "conflicts", "process_count")
            },
        )

    @router.post(
        "/commit",
        response_model=topology.TopologyResponse,
        openapi_extra={"x-permission": "inventory.import"},
    )
    async def commit(
        project_id: str, payload: CommitInput, actor: Writer, session: Session, request: Request
    ) -> dict:
        actor = await services.current_actor(session, actor)
        authorize(actor, "inventory.import")
        pending = await session.scalar(
            select(InventoryPreview)
            .where(
                InventoryPreview.project_id == project_id,
                InventoryPreview.id == payload.preview_id,
                InventoryPreview.owner_user_id == actor.user_id,
            )
            .with_for_update()
        )
        if pending is None:
            raise DomainError("NOT_FOUND", "Resource not found.", 404)
        actor, project, state = await topology.context(
            session, actor, project_id, "inventory.import", writable=True
        )
        if pending.expires_us <= services.utc_now_us():
            raise DomainError("PREVIEW_EXPIRED", "Inventory preview expired; upload again.", 410)
        topology.check_revision(project, payload.expected_revision)
        upload = await upload_in_context(session, actor, project_id, pending.upload_id)
        document = pending.document
        if (
            pending.auth_version != actor.auth_version
            or pending.expected_revision != project.revision
            or pending.expected_revision != upload.expected_revision
            or pending.content_digest != upload.digest
            or pending.manifest_digest != upload.manifest_digest
            or pending.mapping_digest != digest(document["mapping"])
            or pending.digest != digest(document)
        ):
            raise DomainError(
                "REVISION_CONFLICT", "Stored inventory binding changed; preview again.", 409
            )
        if not document["can_commit"]:
            raise DomainError(
                "IMPORT_CONFLICT",
                "Resolve every conflicting or unassigned record before commit.",
                409,
            )
        # Revalidate digest from the restricted stage; clients send no replacement data.
        try:
            actual_digest = await topology.cpu_work(
                lambda: hashlib.sha256(
                    request.app.state.inventory.path(upload.id).read_bytes()
                ).hexdigest()
            )
        except FileNotFoundError:
            raise DomainError(
                "PREVIEW_EXPIRED", "Inventory staging is unavailable; upload again.", 410
            ) from None
        if actual_digest != pending.content_digest:
            raise DomainError("REVISION_CONFLICT", "Inventory content changed; upload again.", 409)
        if topology.canonical_bytes(document["config"]) == topology.canonical_bytes(state.config):
            result = topology.response(project, state, actor)
        else:
            result = await topology.save(
                session,
                actor,
                project,
                state,
                document["config"],
                confirmed_deletions=False,
                reparent=True,
                already_validated=True,
            )
        for item in document["host_baselines"]:
            row = await session.get(
                InventoryHostMapping, (project_id, pending.source_id, item["alias"])
            )
            if row is None:
                session.add(
                    InventoryHostMapping(project_id=project_id, source_id=pending.source_id, **item)
                )
            else:
                row.baseline = item["baseline"]
        await session.flush()
        for item in document["process_baselines"]:
            process_row = await session.get(
                InventoryProcessMapping,
                (project_id, pending.source_id, item["alias"], item["local_id"]),
            )
            if process_row is None:
                session.add(
                    InventoryProcessMapping(
                        project_id=project_id, source_id=pending.source_id, **item
                    )
                )
            else:
                process_row.baseline = item["baseline"]
        services.audit(
            session, actor, "inventory.commit", project_id, pending.source_id, services.utc_now_us()
        )
        await session.execute(
            delete(InventoryPreview).where(
                InventoryPreview.project_id == project_id, InventoryPreview.upload_id == upload.id
            )
        )
        await session.delete(upload)
        await session.flush()
        await request.app.state.inventory.remove(upload.id, project_id=project_id)
        return result

    @router.post(
        "/uploads/{upload_id}/cancel",
        response_model=CancelResponse,
        openapi_extra={"x-permission": "inventory.upload.cancel"},
    )
    async def cancel_upload(
        project_id: str,
        upload_id: str,
        payload: EmptyInput,
        actor: Writer,
        session: Session,
        request: Request,
    ) -> dict:
        actor, _project, _state = await topology.context(
            session, actor, project_id, "inventory.import"
        )
        row = await session.scalar(
            select(InventoryUpload)
            .where(
                InventoryUpload.project_id == project_id,
                InventoryUpload.id == upload_id,
                InventoryUpload.owner_user_id == actor.user_id,
            )
            .with_for_update()
        )
        if row is None:
            raise DomainError("NOT_FOUND", "Resource not found.", 404)
        authorize(actor, "inventory.upload.cancel", owner_user_id=row.owner_user_id)
        await session.execute(
            delete(InventoryPreview).where(
                InventoryPreview.project_id == project_id, InventoryPreview.upload_id == row.id
            )
        )
        await session.delete(row)
        await request.app.state.inventory.remove(row.id, project_id=project_id)
        return dict(cancelled=True)

    @router.post(
        "/previews/{preview_id}/cancel",
        response_model=CancelResponse,
        openapi_extra={"x-permission": "inventory.upload.cancel"},
    )
    async def cancel_preview(
        project_id: str,
        preview_id: str,
        payload: EmptyInput,
        actor: Writer,
        session: Session,
        request: Request,
    ) -> dict:
        actor, _project, _state = await topology.context(
            session, actor, project_id, "inventory.import"
        )
        row = await session.scalar(
            select(InventoryPreview)
            .where(
                InventoryPreview.project_id == project_id,
                InventoryPreview.id == preview_id,
                InventoryPreview.owner_user_id == actor.user_id,
            )
            .with_for_update()
        )
        if row is None:
            raise DomainError("NOT_FOUND", "Resource not found.", 404)
        authorize(actor, "inventory.upload.cancel", owner_user_id=row.owner_user_id)
        await session.delete(row)
        return dict(cancelled=True)

    return router
