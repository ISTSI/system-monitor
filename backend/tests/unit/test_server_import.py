"""Single-server exports use the existing bounded import and reconciliation contracts."""

import copy
import json
import zipfile
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from inspector.inventory import reconcile
from inspector.inventory_parser import (
    DEFAULT_LIMITS,
    InventoryParseError,
    inspect_upload,
    parse_inventory,
)
from inspector.persistence.inventory_models import InventoryHostMapping, InventoryProcessMapping
from inspector.project_config import empty_project

ROOT = Path(__file__).resolve().parents[3]
SECRET = "never-display-this-uploaded-value"


def document():
    project = json.loads((ROOT / "examples/project.example.json").read_text(encoding="utf-8"))
    return {
        "format": "system-inspector-server",
        "schema_version": "1.0",
        "server": {
            "id": "stable-host-01",
            "name": "Application host",
            "address": "192.0.2.20",
            "user": "logreader",
            "subsystem_id": "s-core",
        },
        "services": [
            {
                "id": "application.service",
                "name": "Application service",
                "log_source": copy.deepcopy(project["processes"][0]["log_source"]),
            }
        ],
    }


def parse(value=None, format="auto", filename="server.json", **kwargs):
    return parse_inventory(filename, json.dumps(value or document()).encode(), format, **kwargs)


def rejected(code, value, **kwargs):
    with pytest.raises(InventoryParseError) as error:
        parse(value, **kwargs)
    assert error.value.code == code
    assert SECRET not in str(error.value)
    assert SECRET not in repr(error.value)
    return error.value


def selected_mapping():
    return dict(
        group_to_subsystem={},
        host_to_subsystem={},
        tag_only_groups=[],
        credential_mapping={},
        jump_mapping={},
        parser_mapping={},
        preserve_existing_documentation=True,
        preserve_existing_layout=True,
        delete_missing_hosts=False,
    )


def config():
    value = empty_project("system-a", "System A", "", 1)
    value["parsers"] = json.loads(
        (ROOT / "examples/project.example.json").read_text(encoding="utf-8")
    )["parsers"]
    return value


def merge(value, normalized, hosts=(), processes=()):
    return reconcile(
        value, normalized, "stable-source", selected_mapping(), list(hosts), list(processes), set()
    )


def mappings(*documents):
    hosts, processes = {}, {}
    for value in documents:
        hosts.update(
            {
                item["alias"]: InventoryHostMapping(
                    project_id="system-a", source_id="stable-source", **item
                )
                for item in value["host_baselines"]
            }
        )
        processes.update(
            {
                (item["alias"], item["local_id"]): InventoryProcessMapping(
                    project_id="system-a", source_id="stable-source", **item
                )
                for item in value["process_baselines"]
            }
        )
    return list(hosts.values()), list(processes.values())


def test_schema_example_packaged_copy_and_log_source_contract_are_identical():
    schema_bytes = (ROOT / "contracts/server-import.schema.json").read_bytes()
    assert (
        schema_bytes
        == (ROOT / "backend/src/inspector/contracts/server-import.schema.json").read_bytes()
    )
    schema = json.loads(schema_bytes)
    Draft202012Validator.check_schema(schema)
    project = json.loads((ROOT / "contracts/project.schema.json").read_text(encoding="utf-8"))
    assert (
        schema["$defs"]["logSource"]
        == project["properties"]["processes"]["items"]["properties"]["log_source"]
    )
    example = json.loads(
        (ROOT / "examples/server-import/server.example.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(example)
    result = parse(example)
    assert result["process_count"] == len(example["services"])
    assert result["hosts"][0]["name"] == example["server"]["name"]


@pytest.mark.parametrize("format", ["auto", "server_json"])
@pytest.mark.parametrize("filename", ["server.json", "server"])
def test_detects_single_host_and_preserves_service_instance_ids_and_sources(format, filename):
    value = document()
    raw = json.dumps(value).encode()
    manifest = inspect_upload(filename, raw)
    assert manifest["format"] == "server_json"
    assert manifest["files"][0]["format"] == "server_json"
    assert value["server"]["address"] not in json.dumps(manifest)
    result = parse(value, format, filename)
    assert not result["conflicts"]
    assert result["process_count"] == 1
    host = result["hosts"][0]
    assert (host["alias"], host["name"], host["address"], host["port"], host["user"]) == (
        "stable-host-01",
        "Application host",
        "192.0.2.20",
        22,
        "logreader",
    )
    assert host["processes"] == value["services"]
    assert host["vars"]["inspector_subsystem"] == "s-core"
    assert result["provenance"]["sources"] == [{"source": filename, "format": "server_json"}]


def test_optional_name_account_subsystem_and_empty_services_are_supported():
    value = document()
    value["server"] = {"id": "stable-host-01", "address": "2001:db8::20"}
    value["services"] = []
    result = parse(value)
    host = result["hosts"][0]
    assert host["name"] == host["alias"] == "stable-host-01"
    assert host["user"] is None
    assert host["processes"] == []
    assert result["process_count"] == 0
    assert "NO_PROCESS_DEFINITIONS" in {warning["code"] for warning in result["warnings"]}


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("server",),
        ("services", 0),
        ("services", 0, "log_source"),
        ("services", 0, "log_source", "archives", 0),
    ],
)
def test_unknown_fields_at_every_level_are_rejected_without_echoing_keys_or_values(path):
    value = document()
    target = value
    for component in path:
        target = target[component]
    target[SECRET] = SECRET
    rejected("INVALID_SERVER_IMPORT", value)


@pytest.mark.parametrize(
    "path,invalid",
    [
        (("format",), "future-server-format"),
        (("schema_version",), "9.0"),
        (("server", "id"), "unstable@host"),
        (("server", "address"), ""),
        (("server", "port"), True),
        (("server", "port"), 65536),
        (("server", "name"), "   "),
        (("services",), {}),
        (("services", 0, "log_source", "active_path"), "relative.log"),
        (("services", 0, "log_source", "allow_symlink"), "false"),
    ],
)
def test_invalid_versions_and_fields_have_sanitized_diagnostics(path, invalid):
    value = document()
    target = value
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = invalid
    rejected("INVALID_SERVER_IMPORT", value, format="server_json")


@pytest.mark.parametrize("field", ["format", "schema_version", "server", "services"])
def test_required_top_level_fields_are_not_invented(field):
    value = document()
    del value[field]
    rejected("INVALID_SERVER_IMPORT", value, format="server_json")


def test_duplicate_service_ids_and_casefold_duplicate_names_are_rejected():
    value = document()
    value["services"].append(copy.deepcopy(value["services"][0]))
    rejected("INVALID_PROCESSES", value)
    value["services"][1]["id"] = "another-instance"
    value["services"][1]["name"] = value["services"][0]["name"].upper()
    rejected("INVALID_PROCESSES", value)


def test_duplicate_json_keys_are_rejected_before_schema_validation():
    raw = json.dumps(document()).replace(
        '"schema_version": "1.0"', '"schema_version": "1.0", "schema_version": "1.0"'
    )
    with pytest.raises(InventoryParseError, match="Duplicate inventory JSON") as error:
        parse_inventory("server.json", raw.encode(), "server_json")
    assert error.value.code == "DUPLICATE_KEY"


@pytest.mark.parametrize("format", ["auto", "static_zip", "server_json"])
def test_zip_cannot_smuggle_one_or_multiple_server_documents_into_import(format):
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("server.json", json.dumps(document()))
        archive.writestr("other.json", json.dumps(document()))
    with pytest.raises(InventoryParseError) as error:
        parse_inventory("servers.zip", output.getvalue(), format, ["server.json", "other.json"])
    assert error.value.code == "SERVER_IMPORT_SINGLE_FILE"


def test_multiple_source_selection_and_wrong_explicit_format_fail_closed():
    rejected(
        "SERVER_IMPORT_SINGLE_FILE",
        document(),
        format="server_json",
        source_files=["server.json", "other.json"],
    )
    rejected("FORMAT_MISMATCH", document(), format="canonical_json")


@pytest.mark.parametrize(
    "limit,expected",
    [
        ({"upload_bytes": 10}, "UPLOAD_LIMIT"),
        ({"expanded_bytes": 10}, "EXPANDED_LIMIT"),
        ({"tree_depth": 2}, "PARSE_LIMIT"),
        ({"tree_nodes": 5}, "PARSE_LIMIT"),
        ({"field_bytes": 4}, "FIELD_LIMIT"),
        ({"processes": 0}, "PROCESS_LIMIT"),
        ({"hosts": 0}, "HOST_LIMIT"),
        ({"seconds": 0}, "IMPORT_TIMEOUT"),
    ],
)
def test_existing_actual_byte_tree_count_and_time_limits_apply(limit, expected):
    rejected(expected, document(), format="server_json", limits=replace(DEFAULT_LIMITS, **limit))


def test_cancellation_applies_before_format_detection_or_schema_validation():
    rejected("IMPORT_CANCELLED", document(), cancelled=lambda: True)


def test_same_source_incremental_hosts_reimport_names_and_missing_services_preserve_identity():
    first_document = document()
    first = merge(config(), parse(first_document))
    assert first["can_commit"]
    first_server = copy.deepcopy(first["config"]["servers"][0])
    first_process = copy.deepcopy(first["config"]["processes"][0])
    first["config"]["servers"][0]["description"] = "Manually documented"
    second_document = document()
    second_document["server"].update(id="stable-host-02", name="Other host", address="192.0.2.21")
    second_document["services"][0]["name"] = "Other service"
    second = merge(first["config"], parse(second_document), *mappings(first))
    assert second["can_commit"]
    assert len(second["config"]["servers"]) == len(second["config"]["processes"]) == 2
    assert any(
        record["status"] == "absent" and record["alias"] == "stable-host-01"
        for record in second["records"]
    )
    first_document["server"].update(name="Renamed host", address="192.0.2.22")
    first_document["services"][0]["name"] = "Renamed service"
    third = merge(
        second["config"], parse(first_document, filename="renamed.json"), *mappings(first, second)
    )
    assert third["can_commit"]
    server = next(item for item in third["config"]["servers"] if item["id"] == first_server["id"])
    process = next(
        item for item in third["config"]["processes"] if item["id"] == first_process["id"]
    )
    assert server["name"] == "Renamed host"
    assert server["description"] == "Manually documented"
    assert process["name"] == "Renamed service"
    repeated = merge(third["config"], parse(first_document), *mappings(first, second, third))
    assert repeated["can_commit"]
    assert repeated["config"] == third["config"]
    assert {record["status"] for record in repeated["records"]} == {"unchanged", "absent"}
    first_document["services"] = []
    empty = merge(third["config"], parse(first_document), *mappings(first, second, third))
    assert empty["can_commit"]
    assert empty["config"]["processes"] == third["config"]["processes"]
    assert any(
        record["kind"] == "process" and record["status"] == "absent" for record in empty["records"]
    )
