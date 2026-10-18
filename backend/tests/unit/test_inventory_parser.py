"""Security and behavioural coverage for the runtime static inventory parser."""

import copy
import json
import stat
import struct
import warnings
import zipfile
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest

from inspector import inventory_parser
from inspector.inventory_parser import (
    DEFAULT_LIMITS,
    InventoryParseError,
    inspect_upload,
    parse_inventory,
)

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples/ansible"
SECRET = "never-return-this-sensitive-value"


def zipped(files):
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files:
            archive.writestr(name, raw)
    return stream.getvalue()


def parse_yaml(text, **kwargs):
    return parse_inventory("inventory.yaml", text.encode(), "yaml", **kwargs)


def parse_json(document, **kwargs):
    return parse_inventory(
        "inventory.json", json.dumps(document).encode(), "canonical_json", **kwargs
    )


def host(result, alias="node"):
    return next(item for item in result["hosts"] if item["alias"] == alias)


def rejected(code, callable):
    with pytest.raises(InventoryParseError) as error:
        callable()
    assert error.value.code == code
    assert SECRET not in str(error.value)
    assert SECRET not in repr(error.value)
    assert error.value.status == 422


@pytest.mark.parametrize(
    "filename",
    ["hosts", "inventory.hosts.ini", "inventory.static.yaml", "inventory.canonical.json"],
)
def test_supplied_formats_map_literal_aliases_and_never_invent_processes(filename):
    result = parse_inventory(filename, (EXAMPLES / filename).read_bytes())
    assert [
        (item["alias"], item["address"], item["port"], item["user"]) for item in result["hosts"]
    ] == [
        ("demo-core-01", "192.0.2.21", 22, "logreader"),
        ("demo-delivery-01", "192.0.2.22", 22, "logreader"),
        ("demo-ingest-01", "192.0.2.20", 22, "logreader"),
    ]
    assert result["process_count"] == (5 if filename.endswith(("yaml", "json")) else 0)
    assert not result["conflicts"]
    assert result["provenance"]["source_files"] == [filename]
    assert "COMPANIONS_NOT_SUPPLIED" in {item["code"] for item in result["warnings"]}
    if not result["process_count"]:
        assert "NO_PROCESS_DEFINITIONS" in {item["code"] for item in result["warnings"]}


def test_canonical_and_yaml_extensions_have_identical_process_records():
    results = [
        parse_inventory(filename, (EXAMPLES / filename).read_bytes())
        for filename in ("inventory.canonical.json", "inventory.static.yaml")
    ]
    assert [item["processes"] for item in results[0]["hosts"]] == [
        item["processes"] for item in results[1]["hosts"]
    ]


def test_uploaded_companion_bundle_matches_canonical_and_manifest_is_sanitized():
    files = [
        (str(path.relative_to(EXAMPLES / "bundle")).replace("\\", "/"), path.read_bytes())
        for path in sorted((EXAMPLES / "bundle").rglob("*"))
        if path.is_file()
    ]
    raw = zipped(files)
    manifest = inspect_upload("bundle.zip", raw)
    assert manifest["source_candidates"] == ["hosts.ini"]
    assert manifest["file_count"] == 8
    assert manifest["expanded_bytes"] == sum(len(data) for _, data in files)
    assert len(manifest["content_sha256"]) == len(manifest["manifest_sha256"]) == 64
    assert all(
        set(item) == {"path", "size", "role", "format", "sha256"} for item in manifest["files"]
    )
    result = parse_inventory("bundle.zip", raw, "static_zip", ["hosts.ini"])
    reference = parse_inventory(
        "inventory.canonical.json", (EXAMPLES / "inventory.canonical.json").read_bytes()
    )
    assert [(h["address"], h["port"], h["user"], h["processes"]) for h in result["hosts"]] == [
        (h["address"], h["port"], h["user"], h["processes"]) for h in reference["hosts"]
    ]
    assert result["provenance"]["companion_files"] == [
        name for name, _ in files if name != "hosts.ini"
    ]
    assert not result["provenance"]["ignored_files"]


def test_ini_lexical_quotes_comments_children_and_unambiguous_host_port():
    raw = b"""# comment\nnode:2222 ansible_host=192.0.2.1 ansible_user="read only"\n[region:children]\napplication # membership\n[application]\nnode\n[all:vars]\nansible_connection=ssh\n"""
    result = parse_inventory("hosts", raw)
    item = host(result)
    assert item["address"] == "192.0.2.1"
    assert item["user"] == "read only"
    assert item["port"] == 2222
    assert item["groups"] == ["all", "application", "region"]
    assert item["provenance"]["ansible_port"][0]["line"] == 2
    assert len(result["hosts"]) == 1


def test_ini_group_vars_accept_quoted_scalars_and_semicolon_comments():
    result = parse_inventory(
        "hosts",
        b"""node\n[all:vars]\nansible_user="read=only" ; comment\nansible_port=2222 ; comment\n""",
    )
    assert host(result)["user"] == "read=only"
    assert host(result)["port"] == 2222


def test_group_declarations_have_provenance_even_without_variables():
    result = parse_yaml("application:\n  hosts: {node: null}\n")
    group = next(item for item in result["groups"] if item["name"] == "application")
    assert group["provenance"] == [
        {"source": "inventory.yaml", "group": "application", "alias": None, "companion": False}
    ]
    assert host(result)["declarations"][0]["source"] == "inventory.yaml"


def test_implicit_all_parent_then_ancestor_child_and_host_precedence():
    result = parse_yaml(
        """all:\n  vars:\n    ansible_user: all-reader\n    ansible_port: 22\nregion:\n  vars:\n    ansible_user: region-reader\n    ansible_port: 2222\n  children:\n    app:\n      vars:\n        ansible_user: app-reader\n      hosts:\n        node:\n          ansible_user: host-reader\n"""
    )
    item = host(result)
    assert item["user"] == "host-reader"
    assert item["port"] == 2222
    assert item["groups"] == ["all", "app", "region"]
    assert [r["group"] for r in item["provenance"]["ansible_user"]] == [
        "all",
        "app",
        "region",
        None,
    ]
    assert not result["conflicts"]


def test_dag_shared_descendant_and_identical_repeated_declarations_merge():
    result = parse_yaml(
        """east:\n  vars: {ansible_user: reader}\n  children:\n    shared:\n      hosts: {node: {ansible_host: 192.0.2.1}}\nwest:\n  vars: {ansible_user: reader}\n  children:\n    shared:\n      hosts: {node: {ansible_host: 192.0.2.1}}\n"""
    )
    assert len(result["hosts"]) == 1
    assert host(result)["groups"] == ["all", "east", "shared", "west"]
    assert host(result)["user"] == "reader"
    assert not result["conflicts"]


def test_sibling_value_conflicts_are_visible_with_provenance_and_no_alphabetic_precedence():
    result = parse_yaml(
        """east:\n  hosts: {node: null}\n  vars: {ansible_user: east-reader}\nwest:\n  hosts: {node: null}\n  vars: {ansible_user: west-reader}\n"""
    )
    assert len(result["conflicts"]) == 1
    conflict = result["conflicts"][0]
    assert (conflict["alias"], conflict["key"]) == ("node", "ansible_user")
    assert {(v["group"], v["value"], v["source"]) for v in conflict["values"]} == {
        ("east", "east-reader", "inventory.yaml"),
        ("west", "west-reader", "inventory.yaml"),
    }


def test_host_override_resolves_sibling_values_without_losing_provenance():
    result = parse_json(
        {
            "_meta": {"hostvars": {"node": {"ansible_user": "resolved"}}},
            "one": {"hosts": ["node"], "vars": {"ansible_user": "a"}},
            "two": {"hosts": ["node"], "vars": {"ansible_user": "b"}},
        }
    )
    assert host(result)["user"] == "resolved"
    assert len(host(result)["provenance"]["ansible_user"]) == 3
    assert not result["conflicts"]


def test_zip_sources_are_read_in_explicit_order_and_same_level_changes_conflict():
    raw = zipped([("b.ini", "node ansible_user=b\n"), ("a.ini", "node ansible_user=a\n")])
    result = parse_inventory("upload.zip", raw, "static_zip", ["b.ini", "a.ini"])
    assert result["provenance"]["source_files"] == ["b.ini", "a.ini"]
    assert host(result)["provenance"]["ansible_user"] == [
        {"source": "b.ini", "group": None, "alias": "node", "companion": False, "line": 1},
        {"source": "a.ini", "group": None, "alias": "node", "companion": False, "line": 1},
    ]
    assert [v["value"] for v in result["conflicts"][0]["values"]] == ["b", "a"]


def test_companion_root_is_upload_relative_and_directories_are_ordered_unit_overlays():
    raw = zipped(
        [
            ("production/hosts", "[app]\nnode\n"),
            ("production/group_vars/all.yaml", "ansible_user: base\n"),
            (
                "production/host_vars/node/20-last.json",
                '{"ansible_user":"last","inspector_processes":[]}',
            ),
            (
                "production/host_vars/node/10-first",
                "ansible_user: first\ninspector_processes: []\n",
            ),
            ("other/host_vars/node.yaml", "ansible_user: outside\n"),
            ("host_vars/node.yaml", "ansible_user: outside-root\n"),
            ("production/ansible.cfg", SECRET),
        ]
    )
    result = parse_inventory("bundle.zip", raw, "static_zip", ["production/hosts"])
    assert host(result)["user"] == "last"
    assert result["provenance"]["companion_files"] == [
        "production/group_vars/all.yaml",
        "production/host_vars/node/10-first",
        "production/host_vars/node/20-last.json",
    ]
    assert result["provenance"]["ignored_files"] == [
        "host_vars/node.yaml",
        "other/host_vars/node.yaml",
        "production/ansible.cfg",
    ]
    assert SECRET not in json.dumps(result)


def test_companion_process_lists_replace_as_units_and_preserve_all_field_provenance():
    raw = zipped(
        [
            (
                "hosts.yaml",
                "all: {hosts: {node: {ansible_user: inline, inspector_processes: [{id: p1, name: one, log_source: {}}]}}}",
            ),
            (
                "host_vars/node/10-first.yaml",
                "ansible_user: first\ninspector_processes: [{id: p2, name: two, log_source: {}}]",
            ),
            ("host_vars/node/20-last.yaml", "ansible_user: last\ninspector_processes: []"),
        ]
    )
    result = parse_inventory("bundle.zip", raw, "static_zip", ["hosts.yaml"])
    assert host(result)["processes"] == []
    assert [item["source"] for item in host(result)["provenance"]["ansible_user"]] == [
        "hosts.yaml",
        "host_vars/node/10-first.yaml",
        "host_vars/node/20-last.yaml",
    ]
    assert not result["conflicts"]


def test_recursive_sensitive_fields_shell_arguments_and_unknown_values_are_omitted_everywhere():
    process = {
        "id": "p1",
        "name": "reader",
        "log_source": {
            "active_path": "/var/log/a",
            "password": SECRET,
            "archives": [
                {"path_pattern": "/var/log/*.zip", "member_patterns": ["a"], "token": SECRET}
            ],
        },
        "private_key": SECRET,
    }
    variables = {
        "ansible_password": SECRET,
        "ansible_ssh_pass": SECRET,
        "ansible_become_password": SECRET,
        "ansible_ssh_private_key_file": SECRET,
        "ansible_ssh_common_args": SECRET,
        "ProxyCommand": SECRET,
        "unknown": {"secret": SECRET, "value": SECRET},
        "inspector_processes": [process],
    }
    result = parse_json({"_meta": {"hostvars": {"node": variables}}})
    assert SECRET not in json.dumps(result)
    assert host(result)["processes"] == [
        {
            "id": "p1",
            "name": "reader",
            "log_source": {
                "active_path": "/var/log/a",
                "archives": [{"path_pattern": "/var/log/*.zip", "member_patterns": ["a"]}],
            },
        }
    ]
    assert {item["name"] for item in result["omitted_variables"]} >= {
        "ansible_password",
        "ansible_ssh_common_args",
        "ProxyCommand",
        "private_key",
        "token",
        "unknown",
    }


def test_become_is_diagnostic_only_and_non_ssh_connection_is_rejected():
    result = parse_yaml("all:\n  hosts:\n    node:\n      ansible_become: true\n")
    assert host(result)["warnings"][0]["code"] == "BECOME_IGNORED"
    assert "sudo" in host(result)["warnings"][0]["message"]
    rejected(
        "CONNECTION_UNSUPPORTED",
        lambda: parse_yaml("all: {hosts: {node: {ansible_connection: local}}}"),
    )
    rejected(
        "CONNECTION_UNSUPPORTED",
        lambda: parse_yaml("all: {hosts: {node: {ansible_connection: []}}}"),
    )


@pytest.mark.parametrize(
    "text,code",
    [
        ("all: {hosts: {node: {ansible_host: '{{ lookup(SECRET) }}'}}}", "TEMPLATE_UNSUPPORTED"),
        ("plugin: amazon.aws.aws_ec2\n", "DYNAMIC_OR_INVALID_INVENTORY"),
        ("all: {vars: {ansible_group_priority: 10}}", "GROUP_PRIORITY_UNSUPPORTED"),
        ("all: {hosts: {'node[1:3]': null}}", "INVALID_HOST"),
        ("all: {children: {child: {children: {all: null}}}}", "GROUP_CYCLE"),
        ("one: {children: {two: null}}\ntwo: {children: {one: null}}", "GROUP_CYCLE"),
        ("all: {hosts: {node: {ansible_port: true}}}", "INVALID_PORT"),
        ("all: {hosts: {node: {ansible_port: 0}}}", "INVALID_PORT"),
        ("all: {hosts: {node: {ansible_port: 65536}}}", "INVALID_PORT"),
        ("all: {hosts: {node: {ansible_port: 22.5}}}", "INVALID_PORT"),
        ("all: {hosts: {node: {ansible_host: []}}}", "INVALID_CONNECTION_VALUE"),
        ("all: {hosts: {node: {inspector_processes: '[]'}}}", "INVALID_PROCESSES"),
        ("all: {hosts: {node: {inspector_processes: [{id: p, name: a}]}}}", "INVALID_PROCESSES"),
        ("all: {hosts: {node: null}, unexpected: value}", "YAML_GROUP_UNSUPPORTED"),
        ("all: {hosts: [node]}", "INVALID_YAML_GROUP"),
    ],
)
def test_specific_unsupported_or_malformed_static_values(text, code):
    rejected(code, lambda: parse_yaml(text))


@pytest.mark.parametrize(
    "text,code",
    [
        ("all:\n  hosts: {}\n  hosts: {}\n", "DUPLICATE_KEY"),
        ("all: &alias {hosts: {node: null}}\nother: *alias\n", "YAML_CONSTRUCT_UNSUPPORTED"),
        (
            "all: {hosts: {node: {ansible_host: !!python/object:os.system ignored}}}",
            "YAML_CONSTRUCT_UNSUPPORTED",
        ),
        ("all: {hosts: {node: {ansible_host: !custom ignored}}}", "YAML_CONSTRUCT_UNSUPPORTED"),
        ("all: {hosts: {node: {password: !vault ignored}}}", "VAULT_UNSUPPORTED"),
        ("$ANSIBLE_VAULT;1.1;AES256\nsecret", "VAULT_UNSUPPORTED"),
        ("all: {hosts: {node: {value: 2026-10-18}}}", "UNSUPPORTED_SCALAR"),
        ("all: {hosts: {node: {value: .nan}}}", "UNSUPPORTED_SCALAR"),
        ("all: {hosts: {node: {1: value}}}", "DUPLICATE_KEY"),
    ],
)
def test_yaml_rejects_unsafe_constructs_without_values(text, code):
    rejected(code, lambda: parse_yaml(text.replace("ignored", SECRET)))


@pytest.mark.parametrize(
    "process,field,code",
    [
        ({"name": "worker", "log_source": {}}, "inspector_processes[0].id", "INVALID_PROCESS"),
        ({"id": "worker", "log_source": {}}, "inspector_processes[0].name", "INVALID_PROCESSES"),
        (
            {"id": "worker", "name": "worker"},
            "inspector_processes[0].log_source",
            "INVALID_PROCESSES",
        ),
    ],
)
def test_required_process_fields_identify_uploaded_filename_and_safe_field(process, field, code):
    document = {
        "all": {"hosts": {"node": {"ansible_password": SECRET, "inspector_processes": [process]}}}
    }
    with pytest.raises(InventoryParseError) as caught:
        parse_inventory("selected-inventory.yaml", json.dumps(document).encode(), "yaml")
    error = caught.value
    assert error.code == code
    assert error.source == "selected-inventory.yaml"
    assert error.field == field
    assert "selected-inventory.yaml" in error.message and field in error.message
    assert SECRET not in str(error) and SECRET not in repr(error)


def test_invalid_inherited_value_identifies_effective_companion_file_and_field():
    raw = zipped(
        [
            ("production/hosts.ini", "node ansible_port=22\n"),
            (
                "production/host_vars/node.yaml",
                "ansible_password: " + SECRET + "\nansible_port: 0\n",
            ),
        ]
    )
    with pytest.raises(InventoryParseError) as caught:
        parse_inventory("bundle.zip", raw, "static_zip", ["production/hosts.ini"])
    error = caught.value
    assert (error.code, error.source, error.field) == (
        "INVALID_PORT",
        "production/host_vars/node.yaml",
        "ansible_port",
    )
    assert SECRET not in error.message


@pytest.mark.parametrize(
    "filename,raw,format,code,line",
    [
        ("selected.yaml", b"all:\n  hosts: [invalid\n", "yaml", "INVALID_INVENTORY_DATA", 3),
        (
            "selected.json",
            ('{\n"password":"' + SECRET + '",\n"all": {').encode(),
            "canonical_json",
            "INVALID_INVENTORY_DATA",
            3,
        ),
        ("selected.yaml", b"all:\n  hosts: {}\n  hosts: {}\n", "yaml", "DUPLICATE_KEY", 3),
        (
            "hosts",
            (
                "# comment\nnode ansible_password=" + SECRET + "\nnode ansible_user='unterminated"
            ).encode(),
            "ini",
            "INVALID_INI_QUOTING",
            3,
        ),
    ],
)
def test_syntax_errors_identify_source_and_existing_line_coordinates_without_source_values(
    filename, raw, format, code, line
):
    with pytest.raises(InventoryParseError) as caught:
        parse_inventory(filename, raw, format)
    error = caught.value
    assert error.code == code
    assert error.source == filename and error.line == line
    assert f"line {line}" in error.message
    if format != "ini":
        assert isinstance(error.column, int) and error.column >= 1
    assert SECRET not in str(error) and SECRET not in repr(error)


def test_selected_zip_source_syntax_location_names_member_rather_than_outer_bundle():
    raw = zipped(
        [("production/hosts.yaml", "all:\n  hosts: [invalid\n"), ("unused.ini", "other\n")]
    )
    with pytest.raises(InventoryParseError) as caught:
        parse_inventory("outer.zip", raw, "static_zip", ["production/hosts.yaml"])
    assert caught.value.source == "production/hosts.yaml"
    assert caught.value.line == 3


def test_effective_provenance_tracks_replacing_companion_without_retaining_values():
    raw = zipped(
        [
            ("hosts", "node ansible_user=inline\n"),
            ("host_vars/node.yaml", "ansible_user: companion\n"),
        ]
    )
    result = parse_inventory("upload.zip", raw, "static_zip", ["hosts"])
    origin = host(result)["effective_provenance"]["ansible_user"]
    assert origin == {
        "source": "host_vars/node.yaml",
        "group": None,
        "alias": "node",
        "companion": True,
    }
    assert "value" not in origin


@pytest.mark.parametrize(
    "raw",
    [
        b'{"all":{},"all":{}}',
        b'{"_meta":{"hostvars":{"node":{"password":"' + SECRET.encode() + b'","value":NaN}}}}',
        b'{"all":{"vars":{"bad":"' + SECRET.encode() + b'"}',
        b"[" + b"[" * 40 + b"0" + b"]" * 41,
    ],
)
def test_json_rejects_duplicate_nonfinite_malformed_and_excessive_nesting_without_echo(raw):
    with pytest.raises(InventoryParseError) as error:
        parse_inventory("data.json", raw, "canonical_json")
    assert SECRET not in str(error.value)


@pytest.mark.parametrize(
    "raw,code",
    [
        (b"node[1:10] ansible_user=reader", "INVALID_HOST"),
        (b"node inspector_processes=[]", "INI_COMPLEX_VALUE_UNSUPPORTED"),
        (b"node ansible_port=invalid", "INVALID_PORT"),
        (b"node ansible_user='unterminated", "INVALID_INI_QUOTING"),
        (b"node ansible_user=one ansible_user=two", "INVALID_INI_VARIABLE"),
        (b"[group:unknown]\nnode", "INI_SECTION_UNSUPPORTED"),
        (b"[group:children]\none two", "INVALID_CHILD_GROUP"),
        (b"2001:db8::1", "AMBIGUOUS_HOST_PORT"),
        (b"node:22 ansible_port=2222", "CONFLICTING_HOST_PORT"),
    ],
)
def test_ini_rejects_ranges_complex_literals_bad_ports_and_quoting(raw, code):
    rejected(code, lambda: parse_inventory("hosts", raw))


def test_ipv6_is_literal_ansible_host_with_separate_port():
    result = parse_inventory("hosts", b"node ansible_host=2001:db8::1 ansible_port=2222")
    assert (host(result)["address"], host(result)["port"]) == ("2001:db8::1", 2222)


def test_content_is_checked_and_explicit_format_can_resolve_extensionless_ambiguity():
    result = parse_inventory("hosts", b"application:\n  hosts: {node: null}\n", "yaml")
    assert host(result)["groups"] == ["all", "application"]
    rejected(
        "INVALID_INVENTORY_DATA", lambda: parse_inventory("hosts.yaml", b"not: [valid", "yaml")
    )
    rejected(
        "SOURCE_UNSUPPORTED", lambda: parse_inventory("inventory.py", b"print('never run')", "ini")
    )
    rejected(
        "SOURCE_UNSUPPORTED",
        lambda: parse_inventory("hosts", b"#!/usr/bin/python\nprint('never run')"),
    )
    rejected("SOURCE_UNSUPPORTED", lambda: inspect_upload("hosts", b"#!/bin/sh\necho never-run"))
    rejected("SOURCE_UNSUPPORTED", lambda: inspect_upload("inventory.py", b"print('never-run')"))


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "a/../../escape",
        "/absolute",
        "C:/absolute",
        "a\\b",
        "a//b",
        "a/./b",
        "a\x00b",
        "a\nb",
        "a/" * 9 + "b",
    ],
)
def test_zip_rejects_unsafe_paths_before_selection(name):
    info = zipfile.ZipInfo(name)
    if "\x00" in name:
        # ZipInfo truncates NUL on construction; construct an archive with a genuine NUL name.
        raw = zipped([("a0b", b"node")]).replace(b"a0b", b"a\x00b")
    elif "\\" in name:
        # Windows ZipInfo normalizes separators while writing, before the parser sees them.
        raw = zipped([("a0b", b"node")]).replace(b"a0b", b"a\\b")
    else:
        raw = zipped([(info, b"node")])
    rejected("UNSAFE_MEMBER", lambda: inspect_upload("bundle.zip", raw))


@pytest.mark.parametrize(
    "names",
    [["hosts", "hosts"], ["Hosts", "hosts"], ["h\u00f6sts", "ho\u0308sts"], ["a", "a/hosts"]],
)
def test_zip_rejects_duplicate_normalized_or_file_directory_colliding_names(names):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        raw = zipped([(name, b"node") for name in names])
    rejected("DUPLICATE_MEMBER", lambda: inspect_upload("bundle.zip", raw))


@pytest.mark.parametrize(
    "kind", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFDIR]
)
def test_zip_rejects_links_and_special_files_even_when_ignored(kind):
    info = zipfile.ZipInfo("ignored.py")
    info.create_system = 3
    info.external_attr = (kind | 0o600) << 16
    rejected("NON_REGULAR_MEMBER", lambda: inspect_upload("bundle.zip", zipped([(info, SECRET)])))


def test_zip_rejects_unix_hardlink_metadata():
    info = zipfile.ZipInfo("hosts")
    info.extra = struct.pack("<HH", 0x000D, 13) + b"\x00" * 13
    rejected("NON_REGULAR_MEMBER", lambda: inspect_upload("bundle.zip", zipped([(info, "node")])))


@pytest.mark.parametrize(
    "name,data",
    [
        ("nested.zip", b"not even an archive"),
        ("nested.tgz", b"not even an archive"),
        ("renamed", b"PK\x03\x04anything"),
        ("renamed", b"\x1f\x8banything"),
    ],
)
def test_zip_rejects_nested_archives_by_name_or_actual_signature(name, data):
    rejected("NESTED_ARCHIVE", lambda: inspect_upload("bundle.zip", zipped([(name, data)])))


def test_zip_rejects_encrypted_unsupported_compression_and_corruption():
    raw = bytearray(zipped([("hosts", "node")]))
    # Encryption flags in both local and central headers, without requiring any crypto library.
    raw[6:8] = (1).to_bytes(2, "little")
    central = raw.index(b"PK\x01\x02")
    raw[central + 8 : central + 10] = (1).to_bytes(2, "little")
    rejected("ENCRYPTED_ARCHIVE", lambda: inspect_upload("bundle.zip", bytes(raw)))
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_BZIP2) as archive:
        archive.writestr("hosts", "node")
    rejected("UNSUPPORTED_COMPRESSION", lambda: inspect_upload("bundle.zip", buffer.getvalue()))
    rejected("INVALID_ARCHIVE", lambda: inspect_upload("bundle.zip", b"invalid"))


def test_bundle_requires_explicit_selection_and_cannot_select_ignored_or_missing_sources():
    raw = zipped(
        [
            ("hosts", "node"),
            ("script.py", "raise RuntimeError('never executed')"),
            ("group_vars/all.yaml", "ansible_user: reader"),
        ]
    )
    rejected("SOURCE_SELECTION_REQUIRED", lambda: parse_inventory("bundle.zip", raw))
    rejected(
        "SOURCE_UNSUPPORTED",
        lambda: parse_inventory("bundle.zip", raw, "static_zip", ["script.py"]),
    )
    rejected(
        "SOURCE_UNSUPPORTED",
        lambda: parse_inventory("bundle.zip", raw, "static_zip", ["group_vars/all.yaml"]),
    )
    rejected(
        "SOURCE_NOT_FOUND", lambda: parse_inventory("bundle.zip", raw, "static_zip", ["missing"])
    )
    rejected(
        "INVALID_SOURCE_SELECTION",
        lambda: parse_inventory("bundle.zip", raw, "static_zip", ["hosts", "hosts"]),
    )


def test_actual_upload_expansion_file_line_field_tree_host_group_and_process_limits():
    rejected(
        "UPLOAD_LIMIT",
        lambda: inspect_upload(
            "hosts", b"node\n" * 100, limits=replace(DEFAULT_LIMITS, upload_bytes=20)
        ),
    )
    rejected(
        "EXPANDED_LIMIT",
        lambda: inspect_upload(
            "bundle.zip",
            zipped([("hosts", b"node\n" * 1000)]),
            limits=replace(DEFAULT_LIMITS, expanded_bytes=100),
        ),
    )
    rejected(
        "FILE_LIMIT",
        lambda: inspect_upload(
            "bundle.zip",
            zipped([("a", "node"), ("b", "other")]),
            limits=replace(DEFAULT_LIMITS, files=1),
        ),
    )
    rejected(
        "LINE_LIMIT",
        lambda: parse_inventory(
            "hosts", ("\u00e9" * 20).encode(), limits=replace(DEFAULT_LIMITS, line_bytes=30)
        ),
    )
    rejected(
        "FIELD_LIMIT",
        lambda: parse_yaml(
            "all: {vars: {unused: long-value}}", limits=replace(DEFAULT_LIMITS, field_bytes=4)
        ),
    )
    rejected(
        "PARSE_LIMIT",
        lambda: parse_yaml(
            "all: {hosts: {one: null, two: null}}", limits=replace(DEFAULT_LIMITS, tree_nodes=5)
        ),
    )
    rejected(
        "PARSE_LIMIT",
        lambda: parse_yaml(
            "all: {hosts: {one: null}}", limits=replace(DEFAULT_LIMITS, tree_depth=1)
        ),
    )
    rejected(
        "HOST_LIMIT",
        lambda: parse_yaml(
            "all: {hosts: {one: null, two: null}}", limits=replace(DEFAULT_LIMITS, hosts=1)
        ),
    )
    rejected(
        "GROUP_LIMIT",
        lambda: parse_yaml("one: {}\ntwo: {}", limits=replace(DEFAULT_LIMITS, groups=3)),
    )
    rejected(
        "PROCESS_LIMIT",
        lambda: parse_yaml(
            "all: {hosts: {node: {inspector_processes: [{id: p1, name: p1, log_source: {}}]}}}",
            limits=replace(DEFAULT_LIMITS, processes=0),
        ),
    )


def test_cancellation_and_deadline_are_checked_with_sanitized_errors():
    rejected("IMPORT_CANCELLED", lambda: parse_inventory("hosts", b"node", cancelled=lambda: True))
    rejected(
        "IMPORT_TIMEOUT",
        lambda: inspect_upload("hosts", b"node", limits=replace(DEFAULT_LIMITS, seconds=-1)),
    )
    calls = 0

    def cancel_during_parse():
        nonlocal calls
        calls += 1
        return calls > 20

    rejected(
        "IMPORT_CANCELLED",
        lambda: parse_yaml(
            "all:\n  hosts:\n" + "".join(f"    host{i}: null\n" for i in range(100)),
            cancelled=cancel_during_parse,
        ),
    )


def test_parsing_never_uses_server_files_or_executes_uploaded_code(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Parser attempted forbidden host filesystem access")

    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    result = parse_inventory(
        "hosts", b"node ansible_password=hidden ansible_ssh_common_args='$(touch /tmp/sentinel)'\n"
    )
    assert host(result)["address"] == "node"
    assert "hidden" not in json.dumps(result)
    assert "sentinel" not in json.dumps(result)


def test_mutating_result_does_not_mutate_subsequent_parse_or_default_limits():
    document = {"_meta": {"hostvars": {"node": {"ansible_user": "reader"}}}}
    before = copy.deepcopy(document)
    first = parse_json(document)
    host(first)["vars"]["ansible_user"] = "changed"
    assert host(parse_json(document))["user"] == "reader"
    assert document == before
    assert inventory_parser.DEFAULT_LIMITS is DEFAULT_LIMITS
