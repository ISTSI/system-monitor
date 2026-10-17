import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from inspector.config import ConfigurationError, parse_config, read_secret
from inspector.domain import ProjectContext
from inspector.errors import DomainError

ROOT = Path(__file__).resolve().parents[3]


def sample():
    return yaml.safe_load(
        (ROOT / "examples/deployment-policy.example.yaml").read_text(encoding="utf-8")
    )


def parse(data, env=None, **kwargs):
    return parse_config(yaml.safe_dump(data).encode(), env or {}, **kwargs)


def test_valid_schema2_config_and_lower_custom_workspace_ceiling():
    config = parse(sample())
    assert config.database.host == "mariadb"
    assert config.max_workspaces_per_user == 8
    data = sample()
    data["limits"].pop("max_workspaces_per_user")
    data["limits"]["max_workspaces_global"] = 3
    assert parse(data).max_workspaces_per_user == 3
    assert data["limits"]["max_live_processes_global"] == 10


def test_local_history_demo_requires_explicit_server_opt_in_and_preserves_caps():
    config = parse(sample())
    assert config.local_history_demo is False
    assert config.cache_dir == sample()["deployment"]["cache_dir"]
    assert config.history_limits["max_line_bytes"] == 262144
    assert parse(sample(), {"SI_LOCAL_HISTORY_DEMO": "1"}).local_history_demo is True
    for value in ("", "true", "yes", "2"):
        with pytest.raises(ConfigurationError, match="SI_LOCAL_HISTORY_DEMO"):
            parse(sample(), {"SI_LOCAL_HISTORY_DEMO": value})


def test_duplicate_unknown_alias_and_oversize_rejected():
    for raw in (
        b"database: 1\ndatabase: 2",
        b"x: &x [*x]",
        b"x: " + b"a" * 131072,
        b"!!python/object:os.system {}",
    ):
        with pytest.raises(ConfigurationError):
            parse_config(raw, {})
    data = sample()
    data["database"]["password"] = "sensitive-value"
    with pytest.raises(ConfigurationError) as error:
        parse(data)
    assert "sensitive-value" not in str(error.value)


@pytest.mark.parametrize(
    "env",
    [
        {"SI_DB_PORT": ""},
        {"SI_DB_PORT": "0"},
        {"SI_DB_PORT": "wat"},
        {"SI_DB_USERNAME": "root"},
        {"SI_DB_USERNAME": "inspector_migrator"},
        {"SI_DB_HOST": ""},
    ],
)
def test_invalid_overrides_fail_safely(env):
    with pytest.raises(ConfigurationError):
        parse(sample(), env)


def test_migration_secret_is_separate_and_runtime_ignores_it():
    env = {
        "SI_MIGRATION_DB_USERNAME": "inspector_migrator",
        "SI_MIGRATION_DB_PASSWORD_FILE": "/run/secrets/migrator",
    }
    assert parse(sample(), env).database.username == "inspector_app"
    config = parse(sample(), env, migration=True)
    assert config.database.username == "inspector_migrator"
    assert config.database.password_file == "/run/secrets/migrator"
    assert "/run/secrets/migrator" not in repr(config)


def test_external_db_requires_verified_tls_and_safe_paths():
    data = sample()
    data["database"]["topology"] = "external"
    with pytest.raises(ConfigurationError):
        parse(data)
    data["database"]["tls"] = {"mode": "verify_identity", "ca_file": "/run/ca.pem"}
    assert parse(data).database.ssl_context  # Does not connect/load until engine creation.
    data["database"]["password_file"] = "/run/../secrets/pass"
    with pytest.raises(ConfigurationError):
        parse(data)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_explicit_ssh_tunnel_accepts_only_literal_loopback_and_disabled_database_tls(host):
    data = sample()
    data["database"].update(topology="ssh_tunnel", host=host, port=13306)
    config = parse(data)
    assert config.database.host == host
    assert config.database.topology == "ssh_tunnel"
    assert config.database.ssl_context() is None


@pytest.mark.parametrize(
    "host", ["localhost", "127.0.0.2", "127.1", "::ffff:127.0.0.1", "db.internal", "172.19.0.2"]
)
def test_tunnel_cannot_redirect_to_remote_or_inferred_loopback_hosts(host):
    data = sample()
    data["database"].update(topology="ssh_tunnel", host=host)
    with pytest.raises(ConfigurationError):
        parse(data)


def test_tunnel_overrides_and_external_loopback_cannot_bypass_transport_policy():
    data = sample()
    data["database"].update(topology="ssh_tunnel", host="127.0.0.1")
    with pytest.raises(ConfigurationError):
        parse(data, {"SI_DB_HOST": "172.19.0.2"})
    data["database"]["tls"] = {"mode": "verify_identity", "ca_file": "/run/ca.pem"}
    with pytest.raises(ConfigurationError):
        parse(data)
    data["database"].update(topology="external", tls={"mode": "disabled", "ca_file": None})
    with pytest.raises(ConfigurationError):
        parse(data)
    data["database"]["topology"] = "automatic_tunnel"
    with pytest.raises(ConfigurationError):
        parse(data)


def test_hyphenated_database_and_account_names_are_preserved():
    config = parse(sample(), {"SI_DB_NAME": "system-monitor", "SI_DB_USERNAME": "system-monitor"})
    assert config.database.name == config.database.username == "system-monitor"


@pytest.mark.parametrize("value", ["name`", "name.*", "name/child", "name;select", "-name", "Name"])
def test_database_and_account_identifier_limits_remain_bounded(value):
    for field in ("name", "username"):
        data = sample()
        data["database"][field] = value
        with pytest.raises(ConfigurationError):
            parse(data)
    for field, limit in (("name", 48), ("username", 32)):
        data = sample()
        data["database"][field] = "a" * (limit + 1)
        with pytest.raises(ConfigurationError):
            parse(data)


def test_absolute_windows_forward_slash_paths_are_preserved_for_host_tooling():
    data = sample()
    data["database"].update(
        topology="external",
        password_file="C:/_Projects/system-monitor/.secrets/database-password",
        tls={"mode": "verify_identity", "ca_file": "D:/Local certificates/mariadb-ca.pem"},
    )
    for field in ("state_dir", "cache_dir", "vault_key_file"):
        data["deployment"][field] = "C:/_Projects/system-monitor/.state/" + field
    config = parse(data)
    assert config.state_dir == data["deployment"]["state_dir"]
    assert config.database.password_file == data["database"]["password_file"]
    assert config.database.tls["ca_file"] == data["database"]["tls"]["ca_file"]


@pytest.mark.parametrize(
    "path",
    [
        "relative/secrets",
        "C:relative/secrets",
        "//server/share/secrets",
        "//?/C:/secrets",
        r"\\server\share\secrets",
        r"\\?\C:\secrets",
        r"C:\secrets\password",
        "C:/NUL",
        "C:/CON/password",
        "C:/folder/COM1.txt",
        "C:/password:secret",
        r"/run/..\secrets/password",
        "C:/../secrets/password",
        "C:/state/../secrets/password",
        "/run/../secrets/password",
        "/run/password\x00",
        "C:/secrets/password\x7f",
    ],
)
def test_all_server_paths_reject_relative_unc_device_traversal_and_controls(path):
    for section, field in (
        ("database", "password_file"),
        ("tls", "ca_file"),
        ("deployment", "state_dir"),
        ("deployment", "cache_dir"),
        ("deployment", "vault_key_file"),
    ):
        data = sample()
        if section == "tls":
            data["database"].update(topology="external")
            data["database"]["tls"] = {"mode": "verify_identity", "ca_file": path}
        else:
            data[section][field] = path
        with pytest.raises(ConfigurationError):
            parse(data)


@pytest.mark.parametrize(
    "raw,expected", [(b"ab:@?# ", "ab:@?# "), (b"pass\r\n", "pass"), (b"pass\n", "pass")]
)
def test_password_file_preserves_value(tmp_path, raw, expected):
    path = tmp_path / "password"
    path.write_bytes(raw)
    assert read_secret(str(path)) == expected


@pytest.mark.parametrize(
    "raw", [b"", b"\n", b"pass\n\n", b"pass\x00", b"pass\r", b"a" * 4097, b"\xff"]
)
def test_bad_secret_never_echoes_payload(tmp_path, raw):
    path = tmp_path / "password"
    path.write_bytes(raw)
    with pytest.raises(ConfigurationError) as error:
        read_secret(str(path))
    assert str(error.value) == "database.password_file: unreadable or invalid secret."


def test_bundled_schema_matches_authoritative_contract():
    bundled = ROOT / "backend/src/inspector/contracts/deployment.schema.json"
    assert json.loads(bundled.read_text()) == json.loads(
        (ROOT / "contracts/deployment.schema.json").read_text()
    )


def test_ssh_vault_and_local_network_exception_are_deployment_owned():
    raw = yaml.safe_dump(sample()).encode()
    config = parse_config(raw, {})
    assert config.vault_key_file == sample()["deployment"]["vault_key_file"]
    assert config.ssh_allow_loopback is False
    assert parse_config(raw, {"SI_SSH_ALLOW_LOOPBACK": "1"}).ssh_allow_loopback is True
    with pytest.raises(ConfigurationError, match="SI_SSH_ALLOW_LOOPBACK"):
        parse_config(raw, {"SI_SSH_ALLOW_LOOPBACK": "yes"})


def test_scope_is_explicit_immutable_and_not_a_display_path():
    context = ProjectContext("system-alpha", "owner")
    with pytest.raises(FrozenInstanceError):
        context.project_id = "system-beta"
    with pytest.raises(DomainError):
        ProjectContext("../../beta", "owner")


@pytest.mark.parametrize(
    "field,value", [("host", "db\x00host"), ("name", "inspector\n"), ("username", "root\n")]
)
def test_endpoint_controls_cannot_bypass_schema_patterns(field, value):
    data = sample()
    data["database"][field] = value
    with pytest.raises(ConfigurationError):
        parse(data)
