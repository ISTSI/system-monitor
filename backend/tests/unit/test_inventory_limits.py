"""Configured inventory ceilings reach actual upload inspection and parsing."""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

from inspector.config import ConfigurationError, parse_config
from inspector.inventory import inventory_limits
from inspector.inventory_parser import InventoryParseError, inspect_upload, parse_inventory

ROOT = Path(__file__).resolve().parents[3]


def config(**limits):
    document = yaml.safe_load((ROOT / "examples/deployment-policy.example.yaml").read_bytes())
    for name in ("inventory_upload_bytes", "inventory_expanded_bytes", "inventory_file_limit"):
        document["limits"].pop(name, None)
    document["limits"].update(limits)
    return parse_config(yaml.safe_dump(document).encode(), {})


def bundle():
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("hosts", "[one]\nnode ansible_host=192.0.2.20\n")
        archive.writestr("group_vars/one.yaml", "ansible_user: logreader\n")
    return output.getvalue()


def test_inventory_defaults_apply_to_legacy_deployment_files():
    actual = config()
    assert (
        actual.inventory_upload_bytes,
        actual.inventory_expanded_bytes,
        actual.inventory_file_limit,
    ) == (10_485_760, 20_971_520, 200)
    effective = inventory_limits(actual)
    assert (
        effective.upload_bytes == 10_485_760
        and effective.expanded_bytes == 20_971_520
        and effective.files == 200
    )
    assert effective.hosts == effective.groups == effective.processes == 5000


@pytest.mark.parametrize(
    "field,value",
    [("inventory_upload_bytes", 8), ("inventory_expanded_bytes", 9), ("inventory_file_limit", 1)],
)
def test_explicit_lower_limits_are_preserved(field, value):
    actual = config(**{field: value})
    assert getattr(actual, field) == value
    effective = inventory_limits(actual)
    assert (
        getattr(
            effective,
            {
                "inventory_upload_bytes": "upload_bytes",
                "inventory_expanded_bytes": "expanded_bytes",
                "inventory_file_limit": "files",
            }[field],
        )
        == value
    )


@pytest.mark.parametrize(
    "field", ["inventory_upload_bytes", "inventory_expanded_bytes", "inventory_file_limit"]
)
@pytest.mark.parametrize("value", [0, -1, True, "100", 1.5, None])
def test_inventory_limits_reject_invalid_deployment_values(field, value):
    with pytest.raises(ConfigurationError):
        config(**{field: value})


def test_config_upload_ceiling_and_parser_hard_bounds_remain_effective():
    actual = config(
        config_upload_bytes=4,
        inventory_upload_bytes=100_000_000,
        inventory_expanded_bytes=100_000_000,
        inventory_file_limit=1000,
    )
    effective = inventory_limits(actual)
    assert effective.upload_bytes == 4
    assert effective.expanded_bytes == 20_971_520
    assert effective.files == 200


@pytest.mark.parametrize(
    "settings,filename,data,code",
    [
        ({"inventory_upload_bytes": 8}, "hosts", b"[one]\nnode\n", "UPLOAD_LIMIT"),
        ({"inventory_expanded_bytes": 8}, "bundle.zip", None, "EXPANDED_LIMIT"),
        ({"inventory_file_limit": 1}, "bundle.zip", None, "FILE_LIMIT"),
    ],
)
def test_actual_inspection_and_parse_apply_configured_limits(settings, filename, data, code):
    raw = bundle() if data is None else data
    effective = inventory_limits(config(**settings))
    for operation in (
        lambda: inspect_upload(filename, raw, limits=effective),
        lambda: parse_inventory(filename, raw, source_files=["hosts"], limits=effective),
    ):
        with pytest.raises(InventoryParseError) as error:
            operation()
        assert error.value.code == code


def test_process_count_respects_total_project_entity_ceiling(monkeypatch):
    from inspector import project_config

    monkeypatch.setattr(project_config, "MAX_ENTITIES", 1)
    assert inventory_limits(config()).processes == 1
