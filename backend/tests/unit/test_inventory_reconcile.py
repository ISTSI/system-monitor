"""Pure import reconciliation edges; database authorization uses MariaDB tests."""

import copy
import json
from pathlib import Path

import pytest

from inspector.errors import DomainError
from inspector.inventory import identity, reconcile
from inspector.inventory_parser import parse_inventory
from inspector.persistence.inventory_models import InventoryHostMapping, InventoryProcessMapping
from inspector.project_config import empty_project

ROOT = Path(__file__).resolve().parents[3]
SOURCE = "inventory-source"


def mapping(**changes):
    return (
        dict(
            group_to_subsystem={"application": "subsystem-app"},
            host_to_subsystem={},
            tag_only_groups=[],
            credential_mapping={},
            jump_mapping={},
            parser_mapping={},
            preserve_existing_documentation=True,
            preserve_existing_layout=True,
            delete_missing_hosts=False,
        )
        | changes
    )


def config():
    value = empty_project("system-a", "System A", "", 1)
    sample = json.loads((ROOT / "examples/project.example.json").read_text(encoding="utf-8"))
    value["parsers"] = sample["parsers"]
    return value


def parsed(*, processes=False, address="192.0.2.10", subsystem=None):
    variables = {"ansible_host": address, "ansible_user": "reader"}
    if subsystem is not None:
        variables["inspector_subsystem"] = subsystem
    if processes:
        sample = json.loads((ROOT / "examples/project.example.json").read_text(encoding="utf-8"))
        source = copy.deepcopy(sample["processes"][0]["log_source"])
        variables["inspector_processes"] = [
            {"id": "app-local", "name": "Application", "log_source": source}
        ]
    return parse_inventory(
        "inventory.yaml",
        json.dumps({"application": {"hosts": {"node": variables}}}).encode(),
        "yaml",
    )


def merge(value, normalized, selected=None, hosts=(), processes=(), credentials=()):
    return reconcile(
        value,
        normalized,
        SOURCE,
        selected or mapping(),
        list(hosts),
        list(processes),
        set(credentials),
    )


def rows(document):
    hosts = [
        InventoryHostMapping(project_id="system-a", source_id=SOURCE, **item)
        for item in document["host_baselines"]
    ]
    processes = [
        InventoryProcessMapping(project_id="system-a", source_id=SOURCE, **item)
        for item in document["process_baselines"]
    ]
    return hosts, processes


def test_tag_only_change_is_visible_in_exact_preview_and_preserves_manual_tags():
    normalized = parsed()
    first = merge(config(), normalized)
    assert first["can_commit"]
    hosts, processes = rows(first)
    current = copy.deepcopy(first["config"])
    current["servers"][0]["tags"] = ["manual-tag"]
    second = merge(current, normalized, mapping(tag_only_groups=["application"]), hosts, processes)
    assert second["can_commit"]
    record = next(item for item in second["records"] if item["kind"] == "host")
    assert record["status"] == "changed"
    assert any(
        change["before"] == ["manual-tag"] and change["after"] == ["application", "manual-tag"]
        for change in record["changes"]
    )
    assert second["config"]["servers"][0]["tags"] == ["application", "manual-tag"]


def test_removing_previously_imported_tag_is_visible_and_keeps_unrelated_tag():
    normalized = parsed()
    first = merge(config(), normalized, mapping(tag_only_groups=["application"]))
    hosts, processes = rows(first)
    first["config"]["servers"][0]["tags"].append("manual-tag")
    second = merge(first["config"], normalized, mapping(), hosts, processes)
    assert second["can_commit"]
    record = next(item for item in second["records"] if item["kind"] == "host")
    assert record["status"] == "changed"
    assert second["config"]["servers"][0]["tags"] == ["manual-tag"]
    assert any(
        "application" in str(change["before"]) and change["after"] == ["manual-tag"]
        for change in record["changes"]
    )


@pytest.mark.parametrize("kind", ["server", "connection"])
def test_unmapped_predictable_identity_collision_never_adopts_manual_entity(kind):
    normalized = parsed()
    first = merge(config(), normalized)
    original = copy.deepcopy(first["config"])
    target = original["servers" if kind == "server" else "connections"][0]
    target["name"] = "Manually owned entity"
    # No provenance mappings exist: knowing a deterministic identifier is not import ownership.
    second = merge(original, normalized)
    assert not second["can_commit"]
    assert any(item["code"] == "IDENTITY_COLLISION" for item in second["conflicts"])
    assert second["config"] == original


def test_unmapped_process_identity_collision_preserves_manual_process():
    normalized = parsed(processes=True)
    first = merge(config(), normalized)
    assert first["can_commit"]
    hosts, _processes = rows(first)
    current = copy.deepcopy(first["config"])
    current["processes"][0]["name"] = "Manually owned process"
    second = merge(current, normalized, hosts=hosts)
    assert not second["can_commit"]
    assert any(item["code"] == "IDENTITY_COLLISION" for item in second["conflicts"])
    assert second["config"]["processes"] == current["processes"]


def test_explicit_host_mapping_resolves_subsystem_variable_conflict_only():
    normalized = parse_inventory(
        "hosts.yaml",
        b"east: {hosts: {node: null}, vars: {inspector_subsystem: s-east}}\nwest: {hosts: {node: null}, vars: {inspector_subsystem: s-west}}",
        "yaml",
    )
    assert normalized["conflicts"][0]["key"] == "inspector_subsystem"
    result = merge(
        config(), normalized, mapping(group_to_subsystem={}, host_to_subsystem={"node": "chosen"})
    )
    assert result["can_commit"]
    assert result["config"]["servers"][0]["subsystem_id"] == "chosen"
    normalized["conflicts"].append(
        {"code": "STATIC_VARIABLE_CONFLICT", "alias": "node", "key": "ansible_user", "values": []}
    )
    blocked = merge(
        config(), normalized, mapping(group_to_subsystem={}, host_to_subsystem={"node": "chosen"})
    )
    assert not blocked["can_commit"]
    assert any(item["key"] == "ansible_user" for item in blocked["conflicts"])


def test_explicit_unique_group_mapping_resolves_subsystem_proposal_conflict():
    normalized = parse_inventory(
        "hosts.yaml",
        b"east: {hosts: {node: null}, vars: {inspector_subsystem: s-east}}\nwest: {hosts: {node: null}, vars: {inspector_subsystem: s-west}}",
        "yaml",
    )
    result = merge(config(), normalized, mapping(group_to_subsystem={"east": "chosen"}))
    assert result["can_commit"]
    assert result["config"]["servers"][0]["subsystem_id"] == "chosen"


def test_reimport_does_not_mutate_inputs_or_documentation_processes_and_layout():
    normalized = parsed(processes=True)
    first = merge(config(), normalized)
    hosts, processes = rows(first)
    current = copy.deepcopy(first["config"])
    current["servers"][0]["description"] = "Keep manual documentation"
    current["processes"][0]["description"] = "Keep process notes"
    current["processes"][0]["tags"] = ["manual-process-tag"]
    manual = copy.deepcopy(current["processes"][0])
    manual.update(id="separate-manual-process", name="Separate process")
    current["processes"].append(manual)
    before = copy.deepcopy(current)
    normalized_before = copy.deepcopy(normalized)
    second = merge(current, normalized, hosts=hosts, processes=processes)
    assert second["can_commit"]
    assert second["config"] == current == before
    assert normalized == normalized_before
    assert all(item["status"] == "unchanged" for item in second["records"])


def test_absent_host_and_processes_are_retained_without_manufactured_deletion():
    first = merge(config(), parsed(processes=True))
    hosts, processes = rows(first)
    normalized = parsed()
    second = merge(first["config"], normalized, hosts=hosts, processes=processes)
    assert second["can_commit"]
    assert second["config"]["processes"] == first["config"]["processes"]
    assert any(
        item["kind"] == "process" and item["status"] == "absent" for item in second["records"]
    )
    normalized["hosts"] = []
    third = merge(second["config"], normalized, hosts=hosts, processes=processes)
    assert third["can_commit"]
    assert third["config"] == second["config"]
    assert any(
        item["kind"] == "host"
        and item["target_id"] == identity(SOURCE, "node", "server")
        and item["status"] == "absent"
        and not item["changes"]
        for item in third["records"]
    )
    assert all(item["status"] == "absent" and not item["changes"] for item in third["records"])


@pytest.mark.parametrize(
    "changes",
    [
        {"credential_mapping": {"node": "foreign-credential"}},
        {"jump_mapping": {"node": "foreign-jump"}},
        {"parser_mapping": {"old-parser": "foreign-parser"}},
        {"host_to_subsystem": {"foreign-host": "s-one"}},
        {"group_to_subsystem": {"foreign-group": "s-one"}},
        {"credential_mapping": {"foreign-host": "credential"}},
    ],
)
def test_mapping_references_must_resolve_in_inventory_and_selected_project(changes):
    with pytest.raises(DomainError) as error:
        merge(config(), parsed(), mapping(**changes))
    assert error.value.code == "INVALID_MAPPING"
    assert "foreign" not in error.value.message


def test_process_log_source_schema_error_has_no_uploaded_value():
    normalized = parsed(processes=True)
    normalized["hosts"][0]["processes"][0]["log_source"]["malicious"] = "never echo this"
    with pytest.raises(DomainError) as error:
        merge(config(), normalized)
    assert error.value.code == "INVALID_LOG_SOURCE"
    assert "never echo this" not in error.value.message


def test_wildcard_directory_patterns_propose_only_the_confined_literal_root():
    normalized = parsed(processes=True)
    source = normalized["hosts"][0]["processes"][0]["log_source"]
    source["active_path"] = "/var/log/apps/instance-a/app.log"
    source["rotated_patterns"] = ["/var/log/apps/*/app.log.[0-9]"]
    source["archives"] = [
        {"path_pattern": "/var/log/apps/*/archive/*.zip", "member_patterns": ["logs/*.log"]}
    ]
    result = merge(config(), normalized)
    assert result["can_commit"], result["conflicts"]
    assert result["config"]["connections"][0]["allowed_log_roots"] == ["/var/log/apps"]
    assert result["config"]["processes"][0]["log_source"] == source
    assert "NO_APPROVAL" in {item["code"] for item in result["warnings"]}
