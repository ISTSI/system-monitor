"""Independent v2 contract oracles, NOT application auth, UI or database code.

No sockets, databases or remote hosts are opened. Production implementations must
be tested separately; these functions only clarify expected policy semantics.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any
import re

from reference_contracts import load_json, validate_project


def resolve_theme(preference: str, shared_default: str, system_dark: bool) -> str:
    if shared_default not in {"light", "dark"}:
        raise ValueError("Shared default must be light or dark")
    if type(system_dark) is not bool:
        raise ValueError("System appearance must be a boolean")
    if preference == "default":
        return shared_default
    if preference == "system":
        return "dark" if system_dark else "light"
    if preference in {"light", "dark"}:
        return preference
    raise ValueError("Unknown appearance preference")


def contrast_ratio(first: str, second: str) -> float:
    """WCAG relative luminance ratio for opaque six-digit sRGB colours only."""
    def luminance(value: str) -> float:
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("Expected opaque six-digit sRGB colour")
        rgb = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
        return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))
    a, b = sorted((luminance(first), luminance(second)))
    return (b + 0.05) / (a + 0.05)


def policy_allows(role: str, action: str, actor_id: str | None,
                  owner_id: str | None = None, *, enabled: bool = True,
                  supplied_owner: bool = False) -> bool:
    """Fixture policy decision only: does not authenticate or fetch resource owners.

The caller of a real application must read authoritative ownership and account
state; passing a user-controlled owner into this oracle is NOT an authorization
implementation. supplied_owner identifies any owner field in a create payload.
"""
    policy = load_json("contracts/rbac-policy.json")
    if enabled is not True or not actor_id or role not in policy["roles"]:
        return False
    rule = policy["actions"].get(action)
    if rule is None or role not in rule["roles"]:
        return False
    scope = rule["ownership"]
    if scope == "none":
        return True
    if scope == "create_self":
        return not supplied_owner
    if not owner_id:
        return False
    if scope == "self":
        return actor_id == owner_id
    if scope == "self_or_administrator":
        return actor_id == owner_id or role == "administrator"
    return False


def convert_v1_project(project: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Pure preview conversion of the documented legacy format; never writes data.

A production importer must first validate the complete v1 JSON Schema, then apply
this transformation, validate v2 semantics and require an Administrator commit.
"""
    if not isinstance(project, dict) or project.get("schema_version") != "1.0":
        raise ValueError("Expected version 1.0 project; unsupported versions are rejected")
    converted = deepcopy(project)
    converted["schema_version"] = "2.0"
    removed = converted.get("settings", {}).get("ui", {}).pop("theme", None)
    warnings = []
    if removed is not None:
        warnings.append("Legacy project theme removed; account appearance and shared default now control presentation.")
    validate_project(converted)
    return converted, warnings


def check_database_semantics(config: dict[str, Any]) -> None:
    """Selected cross-field checks; JSON Schema is separately required."""
    db = config["database"]
    if db.get("engine") != "mariadb" or db.get("driver") != "asyncmy":
        raise ValueError("MariaDB/asyncmy is required; no SQLite fallback")
    if not isinstance(db.get("host"), str) or not db["host"] or any(ch.isspace() for ch in db["host"]):
        raise ValueError("A database host without whitespace is required")
    if type(db.get("port")) is not int or not 1 <= db["port"] <= 65535:
        raise ValueError("Port must be an integer from 1 to 65535")
    if "password" in db or "url" in db or "dsn" in db:
        raise ValueError("Use a password file, not plaintext or a DSN")
    password_file = db.get("password_file")
    if not isinstance(password_file, str) or not password_file.startswith("/") or ".." in password_file.split("/"):
        raise ValueError("Password file must be an absolute, non-traversing path")
    if db.get("username") in {"root", "inspector_migrator"}:
        raise ValueError("Serving app must use a separate runtime account")
    if db.get("topology") not in {"managed", "external"}:
        raise ValueError("Unknown database topology")
    tls = db["tls"]
    if db["topology"] == "external" and tls.get("mode") != "verify_identity":
        raise ValueError("External database requires verified TLS")
    if tls.get("mode") == "verify_identity":
        if not isinstance(tls.get("ca_file"), str) or not tls["ca_file"].startswith("/"):
            raise ValueError("Verified TLS requires an absolute CA-file path")
    elif tls.get("mode") != "disabled" or tls.get("ca_file") is not None:
        raise ValueError("Invalid TLS policy")
    for prefix in ("live_processes", "collection_jobs"):
        if config["limits"][f"max_{prefix}_per_user"] > config["limits"][f"max_{prefix}_global"]:
            raise ValueError("Per-user cap cannot exceed the global cap")
