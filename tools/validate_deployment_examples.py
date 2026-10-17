#!/usr/bin/env python3
"""Static deployment-template checks, not docker compose config or container tests.

Requires PyYAML. Optional --compose-schema validates a locally supplied official
Compose JSON Schema; this script never downloads it or executes a container.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(relative: str):
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def validate_templates() -> tuple[dict, dict, dict, int]:
    base = load("examples/deployment/compose.mariadb.yaml")
    overlay = load("examples/deployment/compose.application.example.yaml")
    config = load("examples/deployment-policy.example.yaml")
    # Only merges these template maps; deliberately not a general Compose merger.
    merged = deepcopy(base)
    for section, values in overlay.items():
        if section not in {"services", "volumes", "networks"}:
            raise ValueError(f"Unsupported template section: {section}")
        if set(values) & set(merged.get(section, {})):
            raise ValueError("Unexpected shared keys; use the real Compose merge rules")
        merged.setdefault(section, {}).update(values)
    checks = 0
    def check(ok: bool, message: str):
        nonlocal checks
        checks += 1
        if not ok:
            raise ValueError(message)
    services = merged["services"]
    check(set(services) == {"mariadb", "app", "migrate", "proxy"}, "Service set differs")
    db, app, migration, proxy = (services[n] for n in ("mariadb", "app", "migrate", "proxy"))
    check(not db.get("ports"), "MariaDB must not publish a host port")
    check(merged["networks"]["database"]["internal"] is True, "Database network not isolated")
    check(db["networks"] == ["database"], "Database has an unexpected egress network")
    check("database" not in proxy["networks"], "Proxy should not reach the database network")
    check("service" in app["networks"], "App needs approved LAN/VPN egress")
    check(db["healthcheck"]["test"] == ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"], "Missing DB readiness check")
    check(app["depends_on"]["mariadb"]["condition"] == "service_healthy", "App must await DB health")
    check(app["depends_on"]["migrate"]["condition"] == "service_completed_successfully", "App must await migrations")
    check(migration["depends_on"]["mariadb"]["condition"] == "service_healthy", "Migration must await DB health")
    check(set(app["secrets"]) == {"inspector_db_password", "inspector_vault_key"}, "Serving app has incorrect secrets")
    check(set(migration["secrets"]) == {"inspector_db_migration_password"}, "Migration has unexpected secrets")
    check(set(db["secrets"]) == {"inspector_db_root_password", "inspector_db_migration_password", "inspector_db_password"}, "DB init secret set differs")
    check(db["environment"]["MARIADB_DATABASE"] == config["database"]["name"], "Schema name mismatch")
    check(db["environment"]["INSPECTOR_DB_APP_USER"] == config["database"]["username"], "Runtime username mismatch")
    check(db["environment"]["MARIADB_USER"] != config["database"]["username"], "Runtime/migration accounts must differ")
    check(db["environment"]["MARIADB_ROOT_HOST"] == "localhost", "Root must stay local")
    check(config["database"]["host"] == "mariadb", "Managed config must use the DB service name")
    check(config["database"]["password_file"] == "/run/secrets/inspector_db_password", "Runtime password path mismatch")
    check("mariadb-data:/var/lib/mysql" in db["volumes"], "No persistent MariaDB volume")
    hook = ROOT / "examples/deployment/mariadb/initdb/20-runtime-user.sh"
    check(hook.is_file() and not hook.stat().st_mode & 0o111, "Init helper must exist and be non-executable for sourcing")
    check("MARIADB_PASSWORD_FILE" in db["environment"] and "MARIADB_PASSWORD" not in db["environment"], "No plaintext migration password")
    for name, service in services.items():
        check(service.get("pull_policy") == "never", f"{name} may pull an image at runtime")
        check(not service.get("privileged", False), f"{name} cannot be privileged")
        check(not any("docker.sock" in str(v) for v in service.get("volumes", [])), "Docker socket mount is forbidden")
        check(all(s in merged["secrets"] for s in service.get("secrets", [])), "Undeclared secret")
        check(all(n in merged["networks"] for n in service["networks"]), "Undeclared network")
    check(app["read_only"] and migration["read_only"], "App/migrator filesystem must be read-only")
    check(app["cap_drop"] == ["ALL"] and migration["cap_drop"] == ["ALL"], "App/migrator need no capabilities")
    return base, overlay, merged, checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-schema", type=Path)
    args = parser.parse_args()
    base, overlay, merged, checks = validate_templates()
    schema_hash = None
    if args.compose_schema:
        import jsonschema
        raw = args.compose_schema.read_bytes()
        schema = json.loads(raw)
        cls = jsonschema.validators.validator_for(schema)
        cls.check_schema(schema)
        validator = cls(schema)
        for document in (base, overlay, merged):
            validator.validate(document)
        schema_hash = hashlib.sha256(raw).hexdigest()
    print(json.dumps({"result": "PASS", "static_checks": checks,
                      "compose_documents": 2, "locally_merged_documents": 1,
                      "official_compose_schema_sha256": schema_hash,
                      "scope": "template structure/policy only; no Compose CLI, image, database or application executed"}, indent=2))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
