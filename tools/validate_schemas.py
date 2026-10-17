#!/usr/bin/env python3
"""Full local schema/YAML validation. Requires jsonschema and PyYAML; no network."""
from __future__ import annotations
from copy import deepcopy
import json
import sys
from pathlib import Path
try:
    import jsonschema
    import yaml
except ImportError as exc:
    print(f"Supply jsonschema and PyYAML in the approved build environment: {exc}", file=sys.stderr)
    raise SystemExit(2)

from reference_v2_contracts import check_database_semantics, convert_v1_project
from reference_v3_contracts import check_limits
from validate_package import source_files

ROOT = Path(__file__).resolve().parents[1]

def read(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

def main() -> int:
    schemas = {}
    for path in sorted((ROOT / "contracts").glob("*.schema.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(data)
        schemas[path.name] = jsonschema.Draft202012Validator(data)
    validations = 0
    for schema, example in [
        ("project.schema.json", "examples/project.example.json"),
        ("project-v1.schema.json", "examples/legacy/project-v1.example.json"),
        ("query.schema.json", "contracts/query.example.json"),
        ("event.schema.json", "contracts/event.example.json"),
        ("live-request.schema.json", "contracts/live-request.example.json"),
        ("deployment.schema.json", "examples/deployment-policy.example.json"),
        ("theme-catalog.schema.json", "assets/themes/tokens.json"),
        ("rbac-policy.schema.json", "contracts/rbac-policy.json"),
        ("user-preference.schema.json", "contracts/user-preference.example.json"),
        ("user-preference-update.schema.json", "contracts/user-preference-update.example.json"),
        ("system-catalog.schema.json", "contracts/system-catalog.example.json"),
        ("workspace.schema.json", "examples/systems/alpha.workspace.json"),
        ("workspace.schema.json", "examples/systems/beta.workspace.json"),
        ("inventory-import.schema.json", "contracts/inventory-import.example.json"),
        ("inventory-preview-binding.schema.json", "contracts/inventory-preview-binding.example.json"),
        ("inventory-commit.schema.json", "contracts/inventory-commit.example.json"),
        ("live-frame.schema.json", "contracts/live-frame.example.json"),
        ("scope-policy.schema.json", "contracts/scope-policy.json"),
        ("project.schema.json", "examples/systems/alpha.project.json"),
        ("project.schema.json", "examples/systems/beta.project.json"),
    ]:
        schemas[schema].validate(read(example)); validations += 1
    for stem, schema in (("project", "project.schema.json"), ("deployment-policy", "deployment.schema.json")):
        data = yaml.safe_load((ROOT / f"examples/{stem}.example.yaml").read_text(encoding="utf-8"))
        if data != read(f"examples/{stem}.example.json"):
            raise ValueError(f"{stem} YAML/JSON examples differ")
        schemas[schema].validate(data); validations += 1
    external = yaml.safe_load((ROOT / "examples/application.external-db.example.yaml").read_text(encoding="utf-8"))
    schemas["deployment.schema.json"].validate(external); validations += 1
    check_database_semantics(external)
    check_limits(external)
    check_database_semantics(read("examples/deployment-policy.example.json"))
    check_limits(read("examples/deployment-policy.example.json"))
    for slug in ("alpha", "beta"):
        system_yaml = yaml.safe_load((ROOT / f"examples/systems/{slug}.project.yaml").read_text())
        if system_yaml != read(f"examples/systems/{slug}.project.json"):
            raise ValueError("Two-system YAML/JSON mismatch")
        schemas["project.schema.json"].validate(system_yaml); validations += 1
    for event in read("fixtures/multi-system/events.json"):
        schemas["event.schema.json"].validate(event); validations += 1
    converted, _ = convert_v1_project(read("examples/legacy/project-v1.example.json"))
    schemas["project.schema.json"].validate(converted); validations += 1
    if converted != read("examples/project.example.json"):
        raise ValueError("Converted legacy project differs from current example")
    for event in read("fixtures/expected/events.json"):
        schemas["event.schema.json"].validate(event); validations += 1
    for case in read("fixtures/expected/query-cases.json"):
        schemas["query.schema.json"].validate(case["request"]); validations += 1
        schemas["filter.schema.json"].validate(case["request"]["filter"]); validations += 1
    yaml_files = [path for path in source_files(ROOT, ".yaml") if not path.name.endswith(".local.yaml")]
    for path in yaml_files:
        yaml.safe_load(path.read_text(encoding="utf-8"))
    negative_cases = []
    for extra in ("role", "owner_id", "default_theme_mode", "username", "database"):
        obj = read("contracts/user-preference-update.example.json")
        obj[extra] = "administrator"
        negative_cases.append(("user-preference-update.schema.json", obj))
    for bad in ("navy_cyan_gold", "automatic", "", None):
        obj = read("contracts/user-preference-update.example.json")
        obj["theme_mode"] = bad
        negative_cases.append(("user-preference-update.schema.json", obj))
    for bad in (True, "3306", 0, 65536):
        obj = read("examples/deployment-policy.example.json")
        obj["database"]["port"] = bad
        negative_cases.append(("deployment.schema.json", obj))
    for extra in ("password", "url", "dsn"):
        obj = read("examples/deployment-policy.example.json")
        obj["database"][extra] = "synthetic-secret"
        negative_cases.append(("deployment.schema.json", obj))
    obj = read("examples/deployment-policy.example.json")
    obj["database"]["topology"] = "external"
    negative_cases.append(("deployment.schema.json", obj))
    obj = read("examples/deployment-policy.example.json")
    obj["database"]["engine"] = "sqlite"
    negative_cases.append(("deployment.schema.json", obj))
    obj = read("examples/project.example.json")
    obj["settings"]["ui"]["theme"] = "light"
    negative_cases.append(("project.schema.json", obj))
    obj = read("examples/project.example.json")
    obj["database"] = {"host": "must-not-import.example"}
    negative_cases.append(("project.schema.json", obj))
    obj = read("contracts/rbac-policy.json")
    obj["roles"].append("superuser")
    negative_cases.append(("rbac-policy.schema.json", obj))
    # New request schemas reject owner/role injection and unsupported/scope-less payloads.
    for schema, path, changes in [
        ("live-request.schema.json", "contracts/live-request.example.json", {"workspace_id": None}),
        ("live-request.schema.json", "contracts/live-request.example.json", {"owner_user_id": "forged"}),
        ("live-request.schema.json", "contracts/live-request.example.json", {"process_ids": ["p", "p"]}),
        ("live-frame.schema.json", "contracts/live-frame.example.json", {"protocol_version": 1}),
        ("live-frame.schema.json", "contracts/live-frame.example.json", {"project_id": None}),
        ("live-frame.schema.json", "contracts/live-frame.example.json", {"workspace_id": "../escape"}),
        ("inventory-import.schema.json", "contracts/inventory-import.example.json", {"owner_user_id": "forged"}),
        ("inventory-import.schema.json", "contracts/inventory-import.example.json", {"format": "dynamic_plugin"}),
        ("inventory-import.schema.json", "contracts/inventory-import.example.json", {"source_files": ["../outside"]}),
        ("inventory-import.schema.json", "contracts/inventory-import.example.json", {"source_files": ["/etc/hosts"]}),
        ("inventory-import.schema.json", "contracts/inventory-import.example.json", {"expected_revision": 0}),
        ("inventory-commit.schema.json", "contracts/inventory-commit.example.json", {"mapping": {}}),
        ("inventory-commit.schema.json", "contracts/inventory-commit.example.json", {"project_id": "other"}),
        ("scope-policy.schema.json", "contracts/scope-policy.json", {"database_per_system": True}),
        ("scope-policy.schema.json", "contracts/scope-policy.json", {"automatic_collection_on_page_open": True}),
    ]:
        instance = read(path); instance.update(changes); negative_cases.append((schema, instance))
    for schema, instance in negative_cases:
        if schemas[schema].is_valid(instance):
            raise ValueError(f"Invalid payload unexpectedly accepted by {schema}")
    print(json.dumps({"result": "PASS", "schemas": len(schemas), "successful_instance_validations": validations,
                      "negative_instances_rejected": len(negative_cases), "yaml_files_parsed": len(yaml_files),
                      "project_and_deployment_yaml_equal_json": True,
                      "scope": "package contracts only; no production API/database validation"}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
