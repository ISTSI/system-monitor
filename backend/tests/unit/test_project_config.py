import copy
import json
from pathlib import Path

import pytest
import yaml

from inspector import project_config
from inspector.errors import DomainError
from inspector.project_config import empty_project, parse_config, validate_project

ROOT = Path(__file__).resolve().parents[3]


def sample():
    return json.loads((ROOT / "examples/project.example.json").read_text(encoding="utf-8"))


def reject(config, field):
    before = copy.deepcopy(config)
    with pytest.raises(DomainError) as error:
        validate_project(config)
    assert error.value.code == "INVALID_PROJECT"
    assert error.value.status == 422
    assert field in error.value.message
    assert config == before


@pytest.mark.parametrize("format", ["json", "yaml", "yml"])
def test_roundtrip_preserves_full_demo_ids_layout_and_sources(format):
    original = sample()
    content = json.dumps(original) if format == "json" else yaml.safe_dump(original)
    parsed, warnings = parse_config(content, format)
    assert parsed == original
    assert len(warnings) == 2
    assert "unresolved" in warnings[0]
    assert "approval" in warnings[1]
    assert not any("enabled" in connection for connection in parsed["connections"])


@pytest.mark.parametrize("system", ["alpha", "beta"])
def test_independent_system_examples_allow_repeated_local_ids_and_names(system):
    config = json.loads(
        (ROOT / f"examples/systems/{system}.project.json").read_text(encoding="utf-8")
    )
    validate_project(config)


@pytest.mark.parametrize(
    "path,format",
    [
        ("examples/project.example.json", "json"),
        ("examples/project.example.yaml", "yaml"),
        ("examples/systems/alpha.project.json", "json"),
        ("examples/systems/alpha.project.yaml", "yaml"),
        ("examples/systems/beta.project.json", "json"),
        ("examples/systems/beta.project.yaml", "yaml"),
        ("examples/legacy/project-v1.example.json", "json"),
    ],
)
def test_supplied_current_and_legacy_example_files_parse(path, format):
    parsed, _warnings = parse_config((ROOT / path).read_text(encoding="utf-8"), format)
    assert parsed["schema_version"] == "2.0"


def test_supplied_legacy_json_also_converts_through_yaml_upload():
    legacy = json.loads(
        (ROOT / "examples/legacy/project-v1.example.json").read_text(encoding="utf-8")
    )
    converted, warnings = parse_config(yaml.safe_dump(legacy), "yaml")
    assert converted["schema_version"] == "2.0"
    assert "Converted schema 1.0" in warnings[0]


def test_empty_project_is_valid_and_returns_fresh_mutable_collections():
    first = empty_project("system-a", "Alpha", "Documentation", 2)
    second = empty_project("system-b", "Beta", "", 1)
    first["subsystems"].append({"id": "s", "name": "A", "description": "", "tags": []})
    assert second["subsystems"] == []
    assert first["project"]["revision"] == 2
    assert parse_config(json.dumps(second), "json") == (second, [])


@pytest.mark.parametrize("format", ["json", "yaml"])
def test_unconnected_servers_and_their_documented_processes_roundtrip(format):
    original = sample()
    for server in original["servers"]:
        server["connection_id"] = None
    original["connections"] = []
    content = json.dumps(original) if format == "json" else yaml.safe_dump(original)
    parsed, warnings = parse_config(content, format)
    assert parsed == original
    assert warnings == []


def test_assigning_connection_checks_previously_unconnected_process_roots():
    config = sample()
    config["servers"][0]["connection_id"] = None
    source = next(
        p["log_source"] for p in config["processes"] if p["server_id"] == config["servers"][0]["id"]
    )
    source["active_path"] = "/documented-only/app.log"
    validate_project(config)
    config["servers"][0]["connection_id"] = sample()["servers"][0]["connection_id"]
    reject(config, "active_path")


@pytest.mark.parametrize("field,value", [("active_path", "/logs/../etc"), ("active_path", "$(id)")])
def test_unconnected_process_paths_still_require_safe_static_linux_paths(field, value):
    config = sample()
    for server in config["servers"]:
        server["connection_id"] = None
    config["processes"][0]["log_source"][field] = value
    reject(config, field)


def test_project_description_bound_fits_runtime_mariadb_text_columns():
    config = sample()
    config["project"]["description"] = "🙂" * project_config.MAX_PROJECT_DESCRIPTION
    validate_project(config)
    config["project"]["description"] += "🙂"
    reject(config, "project.description")


def test_legacy_conversion_only_changes_interchange_version_and_legacy_theme():
    legacy = sample()
    legacy["schema_version"] = "1.0"
    legacy["settings"]["ui"]["theme"] = "navy_cyan_gold"
    converted, warnings = parse_config(yaml.safe_dump(legacy), "yaml")
    assert converted == sample()
    assert "Converted schema 1.0" in warnings[0]
    assert "Account and global appearance remain unchanged" in warnings[0]
    assert legacy["schema_version"] == "1.0"
    assert "theme" in legacy["settings"]["ui"]


@pytest.mark.parametrize(
    "content,format",
    [
        ('{"schema_version":"2.0","schema_version":"1.0"}', "json"),
        ("schema_version: '2.0'\nschema_version: '1.0'", "yaml"),
        ("x: &anchor [1]\ny: *anchor", "yaml"),
        ("x: &anchor [1]", "yaml"),
        ("x: !!python/object/apply:os.system ['unsafe']", "yaml"),
        ("x: !!binary aGVsbG8=", "yaml"),
        ("x: 2026-10-17", "yaml"),
        ("x: .inf", "yaml"),
        ("x: .nan", "yaml"),
        ('{"x": NaN}', "json"),
        ('{"x": 1e9999}', "json"),
        ("{broken sensitive-payload", "json"),
        ("x: [broken sensitive-payload", "yaml"),
        ("[1, 2]", "json"),
        ("42", "yaml"),
        ('{"x": 1}', "toml"),
    ],
)
def test_unsafe_invalid_non_json_values_and_duplicates_fail_without_echo(content, format):
    with pytest.raises(DomainError) as error:
        parse_config(content, format)
    assert error.value.status == 422
    assert "sensitive-payload" not in error.value.message
    assert "os.system" not in error.value.message


@pytest.mark.parametrize("format", ["json", "yaml"])
def test_depth_limit_precedes_recursive_construction(format):
    text = "[" * (project_config.MAX_DEPTH + 1) + "0" + "]" * (project_config.MAX_DEPTH + 1)
    with pytest.raises(DomainError, match="nesting exceeds limit"):
        parse_config(text, format)


def test_size_limit_is_actual_utf8_bytes_and_item_limits_are_enforced(monkeypatch):
    monkeypatch.setattr(project_config, "MAX_CONFIG_BYTES", 100)
    with pytest.raises(DomainError, match="upload exceeds"):
        parse_config("é" * 51, "yaml")
    monkeypatch.setattr(project_config, "MAX_CONFIG_BYTES", 10 * 1024 * 1024)
    monkeypatch.setattr(project_config, "MAX_TREE_NODES", 10)
    with pytest.raises(DomainError, match="item count exceeds"):
        parse_config(json.dumps(sample()), "json")
    monkeypatch.setattr(project_config, "MAX_TREE_NODES", 200_000)
    monkeypatch.setattr(project_config, "MAX_ENTITIES", 1)
    with pytest.raises(DomainError, match="entity count exceeds"):
        validate_project(sample())


def test_direct_validation_counts_serialized_escape_bytes(monkeypatch):
    config = empty_project("system-a", "A", "\n" * 1000, 1)
    monkeypatch.setattr(project_config, "MAX_CONFIG_BYTES", 2000)
    with pytest.raises(DomainError, match="serialized content exceeds"):
        validate_project(config)


@pytest.mark.parametrize("field", ["password", "ciphertext", "trusted_host_keys", "enabled"])
def test_connection_import_refuses_secrets_trust_and_activation_without_echo(field):
    config = sample()
    config["connections"][0][field] = "sensitive-payload"
    with pytest.raises(DomainError) as error:
        parse_config(json.dumps(config), "json")
    assert "sensitive-payload" not in error.value.message
    assert "connections[0]" in error.value.message


@pytest.mark.parametrize("field", ["database", "users", "roles", "bootstrap_settings"])
def test_deployment_or_account_fields_are_forbidden_even_in_legacy_input(field):
    config = sample()
    config["schema_version"] = "1.0"
    config["settings"]["ui"]["theme"] = "navy_cyan_gold"
    config[field] = {"password": "sensitive-payload"}
    with pytest.raises(DomainError) as error:
        parse_config(json.dumps(config), "json")
    assert "sensitive-payload" not in error.value.message


def test_schema_unknown_future_version_and_fields_do_not_echo_values():
    config = sample()
    config["schema_version"] = "3.0"
    reject(config, "schema_version")
    config = sample()
    config["project"]["sensitive-payload"] = "sensitive-value"
    with pytest.raises(DomainError) as error:
        validate_project(config)
    assert "sensitive" not in error.value.message


@pytest.mark.parametrize(
    "kind", ["subsystems", "servers", "processes", "connections", "parsers", "flows", "views"]
)
def test_duplicate_ids_and_unicode_casefold_names_rejected_per_kind(kind):
    config = sample()
    duplicate = copy.deepcopy(config[kind][0])
    config[kind].append(duplicate)
    reject(config, ".id")
    config[kind][0]["name"] = "Straße"
    config[kind][-1]["name"] = "STRASSE"
    config[kind][-1]["id"] = "unique-new-id"
    reject(config, ".name")


def test_diagram_identity_is_unambiguous_across_node_kinds():
    config = sample()
    config["servers"][0]["id"] = config["subsystems"][0]["id"]
    reject(config, "servers[0].id")


def test_immutable_identity_is_unique_across_other_entity_kinds():
    config = sample()
    config["parsers"][0]["id"] = config["connections"][0]["id"]
    reject(config, "parsers[0].id")


@pytest.mark.parametrize("field", ["project", "process", "credential"])
def test_id_patterns_reject_final_newline_even_when_schema_regex_accepts_it(field):
    config = sample()
    if field == "project":
        config["project"]["id"] += "\n"
        expected = "project.id"
    elif field == "process":
        config["processes"][0]["id"] += "\n"
        expected = "processes[0].id"
    else:
        config["connections"][0]["credential_ref"] += "\n"
        expected = "credential_ref"
    reject(config, expected)


@pytest.mark.parametrize(
    "kind,field",
    [
        ("servers", "subsystem_id"),
        ("servers", "connection_id"),
        ("processes", "server_id"),
        ("flows", "source_process_id"),
        ("flows", "target_process_id"),
    ],
)
def test_reference_must_exist_inside_this_project(kind, field):
    config = sample()
    config[kind][0][field] = "foreign-system-only-id"
    reject(config, f"{kind}[0].{field}")


def test_parser_reference_must_exist_inside_project():
    config = sample()
    config["processes"][0]["log_source"]["parser_id"] = "foreign-parser"
    reject(config, "processes[0].log_source.parser_id")


@pytest.mark.parametrize("jump", ["missing", "c-jump", "c-core"])
def test_connection_missing_jump_self_cycle_and_two_hops_rejected(jump):
    config = sample()
    config["connections"][0]["jump_connection_id"] = jump
    reject(config, "jump_connection_id")


@pytest.mark.parametrize(
    "path",
    [
        "relative.log",
        "/",
        "/var/log/../secret",
        "/var/log/./app",
        "/var/log/$HOME",
        "/var/log/${name}",
        "/var/log/`whoami`",
        "/var/log/~/app",
        "/var/log/a\x00",
        "/var/log/a\n",
        "/var/log/a\x7f",
        "/var/log/a\\b",
        "//var/log/app",
        "/var/log/a*",
        "/var/log/a?",
        "/var/log/a[0]",
    ],
)
def test_active_paths_reject_traversal_controls_expansion_and_globs(path):
    config = sample()
    config["processes"][0]["log_source"]["active_path"] = path
    reject(config, "active_path")


def test_root_proposals_bound_all_paths_with_component_boundaries():
    config = sample()
    config["processes"][0]["log_source"]["active_path"] = "/var/log/inspector-demo-other/app.log"
    reject(config, "active_path")
    config = sample()
    config["connections"][1]["allowed_log_roots"] = []
    reject(config, "active_path")
    config = sample()
    config["connections"][1]["allowed_log_roots"] = ["/var/log/*"]
    reject(config, "allowed_log_roots")
    config = sample()
    config["processes"][0]["log_source"]["archives"][0]["path_pattern"] = "/elsewhere/*.zip"
    reject(config, "path_pattern")


@pytest.mark.parametrize(
    "member",
    [
        "../outside",
        "logs/../../outside",
        "/absolute",
        "C:/absolute",
        "logs/./file",
        "logs/${env}",
        "logs/file\n",
        "logs\\file",
        "logs/[invalid",
    ],
)
def test_archive_member_patterns_reject_unsafe_paths(member):
    config = sample()
    config["processes"][0]["log_source"]["archives"][0]["member_patterns"] = [member]
    reject(config, "member_patterns")


@pytest.mark.parametrize(
    "encoding", ["nonexistent", "unicode_escape", "base64_codec", "utf-16", "rot_13"]
)
def test_unsupported_or_non_text_encodings_rejected(encoding):
    config = sample()
    config["processes"][0]["log_source"]["encoding"] = encoding
    reject(config, "encoding")


@pytest.mark.parametrize(
    "format", ["%H:%M:%S", "%Y-%m-%d %H:%M:%S %Q", "%Y-%m-%d %H:%M:%S%", "%Y%Y-%m-%d %H:%M:%S"]
)
def test_invalid_incomplete_or_unsupported_timestamp_formats_rejected(format):
    config = sample()
    config["parsers"][1]["timestamp"]["format"] = format
    reject(config, "timestamp.format")


def test_timestamp_width_and_offsets_are_validated():
    config = sample()
    config["parsers"][1]["timestamp"]["width"] = 5
    reject(config, "timestamp.width")
    config["parsers"][1]["timestamp"].update(format="%Y-%m-%dT%H:%M:%S%z", width=24)
    validate_project(config)


@pytest.mark.parametrize(
    "field,value", [("x", float("nan")), ("y", float("inf")), ("width", 0), ("height", -1)]
)
def test_view_coordinates_are_finite_and_dimensions_positive(field, value):
    config = sample()
    config["views"][0]["nodes"][0][field] = value
    with pytest.raises(DomainError) as error:
        validate_project(config)
    assert field in error.value.message


@pytest.mark.parametrize("field", ["x", "y", "width", "height"])
def test_view_geometry_has_supported_canvas_bounds(field):
    config = sample()
    config["views"][0]["nodes"][0][field] = project_config.MAX_GEOMETRY + 1
    reject(config, field)


def test_each_view_requires_ancestors_and_flow_endpoints():
    config = sample()
    config["views"][0]["nodes"] = [
        node for node in config["views"][0]["nodes"] if node["element_id"] != "s-core"
    ]
    reject(config, "every ancestor")
    config = sample()
    config["views"][0]["nodes"] = [
        node for node in config["views"][0]["nodes"] if node["element_id"] != "p-parser-a"
    ]
    reject(config, "both flow endpoints")


def test_view_references_and_duplicates_are_rejected():
    config = sample()
    config["views"][0]["nodes"].append(copy.deepcopy(config["views"][0]["nodes"][0]))
    reject(config, "duplicate view node")
    config = sample()
    config["views"][0]["flow_ids"].append(config["views"][0]["flow_ids"][0])
    reject(config, "duplicate view flow")
    config = sample()
    config["views"][0]["nodes"][0]["element_id"] = "foreign-element"
    reject(config, "diagram element")
    config = sample()
    config["views"][0]["flow_ids"][0] = "foreign-flow"
    reject(config, "reference does not exist")


@pytest.mark.parametrize(
    "description",
    [
        "![external](https://example.com/image.png)",
        "![reference][asset]\n[asset]: //example.com/asset",
        "<script>alert(1)</script>",
        "<img src='https://example.com/pixel'>",
        "[run](javascript:alert(1))",
        "[file](file:///etc/passwd)",
        "[run](java&#x73;cript:alert(1))",
        "[run](java\tscript:alert(1))",
        "[run](javascript%3aalert(1))",
    ],
)
def test_unsafe_markdown_refused_with_field_error(description):
    config = sample()
    config["processes"][0]["description"] = description
    reject(config, "processes[0].description")


def test_safe_documentation_links_and_markdown_are_retained():
    config = sample()
    config["processes"][0]["description"] = (
        "# Summary\n\n**Bold** and [local](#summary), [manual](https://example.com/manual), <https://example.com/manual>."
    )
    validate_project(config)


def test_direct_validation_refuses_cycles_and_invalid_unicode():
    config = sample()
    config["extra"] = config
    with pytest.raises(DomainError, match="recursive"):
        validate_project(config)
    config = sample()
    config["project"]["description"] = "\ud800"
    with pytest.raises(DomainError, match="invalid Unicode"):
        validate_project(config)


def test_bundled_schemas_match_authoritative_contracts():
    for name in ("project.schema.json", "project-v1.schema.json"):
        assert json.loads(
            (ROOT / "backend/src/inspector/contracts" / name).read_text(encoding="utf-8")
        ) == json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
