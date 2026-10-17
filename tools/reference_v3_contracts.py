"""Pure v3 scope/budget/reconciliation oracles, NOT production authorization.

Callers supply synthetic authoritative context. These checks do not authenticate,
query MariaDB, secure an HTTP route or open SSH/browser connections.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import re
from typing import Any

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def scoped_key(project_id: str, *parts: str) -> str:
    """Generated namespace key avoids separator/path collisions; not an access token."""
    if not parts or any(not isinstance(x, str) or not ID.fullmatch(x) for x in (project_id, *parts)):
        raise ValueError("Invalid scoped identifier")
    raw = json.dumps([project_id, *parts], ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def event_identity(event: dict[str, Any]) -> tuple[str, str]:
    return (event["project_id"], event["event_id"])


def project_events(events: list[dict[str, Any]], project_id: str, contains: str = "") -> list[dict[str, Any]]:
    """Context must already be authorized; this oracle is deliberately not a route."""
    return [deepcopy(e) for e in events if e["project_id"] == project_id and contains in e["raw_line"]]


def require_private_scope(resource: dict[str, Any], *, project_id: str, actor_id: str,
                          workspace_id: str | None = None) -> None:
    if resource.get("project_id") != project_id or resource.get("owner_user_id") != actor_id:
        raise ValueError("NOT_FOUND")
    if workspace_id is not None and resource.get("workspace_id") != workspace_id:
        raise ValueError("WORKSPACE_IN_USE")


def validate_frame(frame: dict[str, Any], *, project_id: str, workspace_id: str,
                   session_id: str, filter_version: int) -> None:
    if frame.get("protocol_version") != 2:
        raise ValueError("UNSUPPORTED_PROTOCOL")
    for field, expected in (("project_id", project_id), ("workspace_id", workspace_id),
                            ("session_id", session_id), ("filter_version", filter_version)):
        if frame.get(field) != expected:
            raise ValueError("FRAME_SCOPE_MISMATCH")
    for event in frame.get("payload", {}).get("items", []):
        if event.get("project_id") != project_id:
            raise ValueError("EVENT_SCOPE_MISMATCH")


def validate_preview(binding: dict[str, Any], *, project_id: str, actor_id: str,
                     auth_version: int, source_id: str, revision: int,
                     content_sha256: str, mapping_sha256: str, now_utc: str) -> None:
    require_private_scope(binding, project_id=project_id, actor_id=actor_id)
    if binding["expires_at"] <= now_utc:
        raise ValueError("PREVIEW_EXPIRED")
    for key, expected in (("auth_version", auth_version), ("inventory_source_id", source_id),
                          ("expected_revision", revision), ("content_sha256", content_sha256),
                          ("mapping_sha256", mapping_sha256)):
        if binding[key] != expected:
            raise ValueError("PREVIEW_CONFLICT")


def check_limits(config: dict[str, Any]) -> None:
    limits = config["limits"]
    pairs = [("max_live_processes_per_workspace", "max_live_processes_per_user"),
             ("max_live_processes_per_workspace", "max_live_processes_per_project"),
             ("max_live_processes_per_project", "max_live_processes_global"),
             ("max_live_processes_per_user", "max_live_processes_global"),
             ("max_workspaces_per_user", "max_workspaces_global"),
             ("max_collection_jobs_per_project", "max_collection_jobs_global")]
    defaults = {"max_live_processes_per_workspace": 5, "max_live_processes_per_project": 10,
                "max_workspaces_per_user": 8, "max_workspaces_global": 64,
                "max_collection_jobs_per_project": 2}
    # Optional v3 defaults fit explicit lower legacy ceilings rather than rejecting
    # an otherwise valid old deployment or silently raising its configured limits.
    defaults["max_live_processes_per_project"] = min(10, limits["max_live_processes_global"])
    defaults["max_live_processes_per_workspace"] = min(5, limits["max_live_processes_per_user"],
        limits.get("max_live_processes_per_project", defaults["max_live_processes_per_project"]))
    defaults["max_collection_jobs_per_project"] = min(2, limits["max_collection_jobs_global"])
    defaults["max_workspaces_per_user"] = min(8, limits.get("max_workspaces_global", 64))
    effective = defaults | limits
    for lower, upper in pairs:
        if any(type(effective[k]) is not int or effective[k] < 1 for k in (lower, upper)):
            raise ValueError("Invalid limit type")
        if effective[lower] > effective[upper]:
            raise ValueError("Invalid limit ordering")


def can_reserve(existing: list[dict[str, Any]], request: dict[str, Any], limits: dict[str, int]) -> bool:
    """Pure fixture calculation; real application needs atomic reservations."""
    if type(request.get("process_count")) is not int or request["process_count"] < 1:
        return False
    checks = [(None, "max_live_processes_global"), ("owner_user_id", "max_live_processes_per_user"),
              ("project_id", "max_live_processes_per_project"), ("workspace_id", "max_live_processes_per_workspace")]
    for field, cap in checks:
        used = sum(row["process_count"] for row in existing
                   if field is None or row[field] == request[field])
        if used + request["process_count"] > limits[cap]:
            return False
    return True


def detach_workspace(sessions: list[dict[str, Any]], workspace_id: str, actor_id: str) -> list[dict[str, Any]]:
    result = deepcopy(sessions)
    for session in result:
        if session["workspace_id"] == workspace_id and session["owner_user_id"] == actor_id:
            session["state"] = "detached"
    return result


def reconcile_preview(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], *,
                      project_id: str, source_id: str) -> dict[str, list[dict[str, Any]]]:
    """Host-address diff only: no writes/deletes, no topology importer implementation."""
    keys = [(r["project_id"], r["inventory_source_id"], r["inventory_hostname"]) for r in existing]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate existing import mapping")
    aliases = [row["inventory_hostname"] for row in incoming]
    if len(aliases) != len(set(aliases)):
        raise ValueError("Duplicate incoming alias")
    lookup = {k: row for k, row in zip(keys, existing, strict=True)}
    result: dict[str, list[dict[str, Any]]] = {k: [] for k in ("added", "unchanged", "changed", "absent_preserved")}
    for row in incoming:
        previous = lookup.get((project_id, source_id, row["inventory_hostname"]))
        if previous is None:
            result["added"].append(deepcopy(row))
        elif previous["host"] == row["host"]:
            result["unchanged"].append(deepcopy(previous))
        else:
            result["changed"].append({"existing_id": previous["server_id"], "old_host": previous["host"],
                                      "new_host": row["host"], "preserved_documentation": previous.get("description", ""),
                                      "preserved_layout": deepcopy(previous.get("layout", {}))})
    for row in existing:
        if row["project_id"] == project_id and row["inventory_source_id"] == source_id and row["inventory_hostname"] not in aliases:
            result["absent_preserved"].append(deepcopy(row))
    return result
