"""Bounded deployment-file reader. No project or browser can switch databases."""

import json
import ntpath
import os
import ssl
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator


class ConfigurationError(ValueError):
    pass


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader: UniqueLoader, node: yaml.MappingNode) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ConfigurationError("Configuration contains duplicate or invalid keys.")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def read_secret(path: str) -> str:
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError
        value = raw.decode("utf-8")
        if value.endswith("\r\n"):
            value = value[:-2]
        elif value.endswith("\n"):
            value = value[:-1]
        if not value or any(char in value for char in "\r\n\x00"):
            raise ValueError
        return value
    except (OSError, UnicodeError, ValueError):
        raise ConfigurationError("database.password_file: unreadable or invalid secret.") from None


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    name: str
    username: str
    password_file: str = field(repr=False)
    topology: str
    connect_timeout_seconds: int
    startup_timeout_seconds: int
    pool: dict[str, Any]
    tls: dict[str, Any]

    def ssl_context(self) -> ssl.SSLContext | None:
        if self.tls["mode"] == "disabled":
            return None
        try:
            return ssl.create_default_context(cafile=self.tls["ca_file"])
        except (OSError, ssl.SSLError):
            raise ConfigurationError("database.tls.ca_file: cannot load trusted CA.") from None


@dataclass(frozen=True)
class Config:
    database: DatabaseConfig
    public_origin: str
    state_dir: str
    idle_timeout_us: int
    absolute_timeout_us: int
    max_workspaces_per_user: int
    max_workspaces_global: int
    default_theme_mode: str = "dark"
    config_upload_bytes: int = 10_485_760
    cache_dir: str = "/var/cache/system-inspector"
    history_limits: dict[str, int] = field(default_factory=dict)
    local_history_demo: bool = False


def parse_config(
    raw: bytes, environment: dict[str, str] | None = None, *, migration: bool = False
) -> Config:
    if len(raw) > 131072:
        raise ConfigurationError("Configuration exceeds 128 KiB.")
    try:
        depth = 0
        for token in yaml.scan(raw):
            if isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)):
                raise ConfigurationError("Configuration YAML aliases are unsupported.")
            if isinstance(
                token,
                (
                    yaml.tokens.BlockMappingStartToken,
                    yaml.tokens.BlockSequenceStartToken,
                    yaml.tokens.FlowMappingStartToken,
                    yaml.tokens.FlowSequenceStartToken,
                ),
            ):
                depth += 1
                if depth > 20:
                    raise ConfigurationError("Configuration nesting exceeds limit.")
            elif isinstance(
                token,
                (
                    yaml.tokens.BlockEndToken,
                    yaml.tokens.FlowMappingEndToken,
                    yaml.tokens.FlowSequenceEndToken,
                ),
            ):
                depth -= 1
        data = yaml.load(raw, Loader=UniqueLoader)
    except (yaml.YAMLError, UnicodeError):
        raise ConfigurationError("Invalid deployment YAML.") from None
    if not isinstance(data, dict):
        raise ConfigurationError("Expected deployment configuration object.")
    schema_path = Path(__file__).parent / "contracts" / "deployment.schema.json"
    validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))
    env = environment if environment is not None else dict(os.environ)
    if env.get("SI_LOCAL_HISTORY_DEMO", "0") not in {"0", "1"}:
        raise ConfigurationError("SI_LOCAL_HISTORY_DEMO: expected 0 or 1.")
    overrides = {
        "SI_DB_HOST": "host",
        "SI_DB_PORT": "port",
        "SI_DB_NAME": "name",
        "SI_DB_USERNAME": "username",
        "SI_DB_PASSWORD_FILE": "password_file",
    }
    if migration:
        overrides.update(
            {
                "SI_MIGRATION_DB_USERNAME": "username",
                "SI_MIGRATION_DB_PASSWORD_FILE": "password_file",
            }
        )
    if not isinstance(data.get("database"), dict):
        raise ConfigurationError("database: required configuration object.")
    for name, key in overrides.items():
        if name in env:
            if not env[name]:
                raise ConfigurationError(f"{name}: empty override.")
            try:
                data["database"][key] = int(env[name]) if key == "port" else env[name]
            except ValueError:
                raise ConfigurationError(f"{name}: invalid port.") from None
    errors = sorted(validator.iter_errors(data), key=lambda error: str(error.path))
    if errors:
        path = ".".join(str(part) for part in errors[0].absolute_path)
        raise ConfigurationError(f"{path or 'configuration'}: invalid or unknown field.")
    db = data["database"]
    for value in (db["host"], db["name"], db["username"], data["deployment"]["public_origin"]):
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ConfigurationError("Configuration endpoint contains control characters.")
    for path in (
        db["password_file"],
        db["tls"]["ca_file"],
        data["deployment"]["state_dir"],
        data["deployment"]["cache_dir"],
        data["deployment"]["vault_key_file"],
    ):
        if path:
            native_path = PureWindowsPath(path) if len(path) > 1 and path[1] == ":" else None
            if (
                "\\" in path
                or path.startswith("//")
                or ".." in PurePosixPath(path).parts
                or (
                    native_path is not None
                    and (not native_path.is_absolute() or ntpath.isreserved(path))
                )
                or any(ord(char) < 32 or ord(char) == 127 for char in path)
            ):
                raise ConfigurationError("Configuration contains an unsafe mounted path.")
    if db["topology"] == "external" and db["tls"]["mode"] != "verify_identity":
        raise ConfigurationError("database.tls: external connections require verify_identity.")
    if db["topology"] == "ssh_tunnel" and (
        db["host"] not in {"127.0.0.1", "::1"} or db["tls"]["mode"] != "disabled"
    ):
        raise ConfigurationError(
            "database: SSH tunnel tooling requires a literal loopback endpoint."
        )
    if db["tls"]["mode"] == "verify_identity" and not db["tls"]["ca_file"]:
        raise ConfigurationError("database.tls.ca_file: required for verify_identity.")
    if db["username"] in {"root", "mysql", "mariadb"} or (
        not migration and "migrat" in db["username"]
    ):
        raise ConfigurationError("database.username: privileged credentials are not permitted.")
    limits = data["limits"]
    for per_user, global_name in (
        ("max_live_processes_per_user", "max_live_processes_global"),
        ("max_collection_jobs_per_user", "max_collection_jobs_global"),
    ):
        if limits[per_user] > limits[global_name]:
            raise ConfigurationError(f"limits.{per_user}: exceeds deployment ceiling.")
    return Config(
        database=DatabaseConfig(**{key: db[key] for key in DatabaseConfig.__dataclass_fields__}),
        public_origin=data["deployment"]["public_origin"],
        state_dir=data["deployment"]["state_dir"],
        idle_timeout_us=data["auth"]["idle_timeout_minutes"] * 60_000_000,
        absolute_timeout_us=data["auth"]["absolute_timeout_hours"] * 3_600_000_000,
        max_workspaces_per_user=min(
            limits.get("max_workspaces_per_user", 8), limits.get("max_workspaces_global", 64)
        ),
        max_workspaces_global=limits.get("max_workspaces_global", 64),
        default_theme_mode=data["bootstrap_settings"]["default_theme_mode"],
        config_upload_bytes=limits["config_upload_bytes"],
        cache_dir=data["deployment"]["cache_dir"],
        history_limits={key: value for key, value in limits.items() if isinstance(value, int)},
        local_history_demo=env.get("SI_LOCAL_HISTORY_DEMO", "0") == "1",
    )


def load_config(*, migration: bool = False) -> Config:
    path = os.environ.get("INSPECTOR_CONFIG_FILE", "/etc/system-inspector/application.yaml")
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(131073)
    except OSError:
        raise ConfigurationError("Cannot read deployment configuration file.") from None
    return parse_config(raw, migration=migration)
