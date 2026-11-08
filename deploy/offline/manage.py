#!/usr/bin/env python3
"""Offline Linux operator tools. No registry pulls, shell commands or target SSH."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fileops import digest, regular, relative
from fileops import verify as verify_backup

HERE = Path(__file__).resolve().parent
IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")
IMAGE_ID = re.compile(r"sha256:[a-f0-9]{64}\Z")
TEMPLATE_FILES = (
    "compose.yaml",
    "compose.external.yaml",
    "20-runtime-user.sh",
    "mariadb.cnf",
    "db-client.sh",
    "fileops.py",
    "manage.py",
    "application.template.json",
)


def private_write(path: Path, value: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(value)
    path.chmod(mode)


def json_write(path: Path, value: object, mode: int = 0o600) -> None:
    private_write(path, (json.dumps(value, indent=2) + "\n").encode(), mode)


def database_secret(path: Path) -> bytes:
    regular(path)
    with path.open("rb") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError("Database password file exceeds its byte limit")
    if raw.endswith(b"\r\n"):
        raw = raw[:-2]
    elif raw.endswith(b"\n"):
        raw = raw[:-1]
    try:
        value = raw.decode("utf-8")
    except UnicodeError:
        raise ValueError("Database password file must contain a UTF-8 value") from None
    if not value or any(char in value for char in "\r\n\x00"):
        raise ValueError("Database password file must contain one nonempty value")
    return raw


def execute(
    command: list[str],
    *,
    capture: bool = False,
    stdin=None,
    stdout=None,
    sensitive: bool = False,
    timeout: int = 900,
    environment: dict[str, str] | None = None,
) -> str:
    result = subprocess.run(
        command,
        check=False,
        stdin=stdin,
        stdout=subprocess.PIPE if capture else stdout,
        stderr=subprocess.PIPE if sensitive else None,
        timeout=timeout,
        env=environment,
    )
    if result.returncode:
        raise ValueError("Container/operator command failed; inspect protected server diagnostics")
    return result.stdout.decode("utf-8") if capture else ""


def release_images(release: Path) -> dict[str, dict]:
    regular(release / "manifest.json")
    if (release / "manifest.json").stat().st_size > 4 * 1024**2:
        raise ValueError("Release manifest exceeds limit")
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    images = {}
    for item in manifest["images"]:
        role = item["role"]
        if role not in {"app", "proxy", "mariadb"} or role in images:
            raise ValueError("Missing or duplicate release image role")
        if not IMAGE_ID.fullmatch(item["image_id"]):
            raise ValueError("Release image has no exact content ID")
        reference = item["reference"]
        if not isinstance(reference, str) or not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9_./:@-]{0,300}", reference
        ):
            raise ValueError("Invalid local image reference")
        member = relative(item["archive"])
        if member.parts[0] != "images" or len(member.parts) != 2:
            raise ValueError("Invalid image archive location")
        archive = release / member
        if archive.parent.is_symlink() or digest(archive) != item["sha256"]:
            raise ValueError("Release image checksum mismatch")
        images[role] = item
    if set(images) != {"app", "proxy", "mariadb"}:
        raise ValueError("Release must include all three image archives")
    return images


def loaded_images(engine: str, images: dict[str, dict]) -> None:
    for image in images.values():
        actual = execute(
            [engine, "image", "inspect", "--format", "{{.Id}}", image["reference"]], capture=True
        )
        if actual.strip() != image["image_id"]:
            raise ValueError("Loaded image identity differs from the release manifest")


def check_certificate(certificate: Path, key: Path, hostname: str) -> None:
    regular(certificate)
    regular(key)
    # The operator verifies its CA separately; these checks bind hostname and key.
    execute(
        ["openssl", "x509", "-in", str(certificate), "-noout", "-checkend", "86400"], sensitive=True
    )
    check = "-checkip" if _is_ip(hostname) else "-checkhost"
    execute(["openssl", "x509", "-in", str(certificate), "-noout", check, hostname], sensitive=True)
    public_certificate = execute(
        ["openssl", "x509", "-in", str(certificate), "-pubkey", "-noout"],
        capture=True,
        sensitive=True,
    )
    public_key = execute(
        ["openssl", "pkey", "-in", str(key), "-pubout"], capture=True, sensitive=True
    )
    if public_certificate != public_key:
        raise ValueError("Certificate and private key do not match")


def _is_ip(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def initialize(args) -> None:
    runtime = args.runtime
    origin = urlsplit(args.origin)
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.path
        or origin.query
        or origin.fragment
        or not re.fullmatch(r"[A-Za-z0-9.:-]+", origin.netloc)
    ):
        raise ValueError("Origin must be an explicit HTTPS origin with a valid hostname")
    port = origin.port or 443
    if not 1024 <= port <= 65535:
        raise ValueError("Use an unprivileged HTTPS port, 1024 through 65535")
    ipaddress.ip_address(args.bind_address)
    check_certificate(args.certificate, args.private_key, origin.hostname)
    if runtime.is_symlink() or (runtime.exists() and any(runtime.iterdir())):
        raise ValueError("Initialization requires a new or empty private runtime directory")
    runtime.mkdir(mode=0o700, parents=False, exist_ok=True)
    runtime.chmod(0o700)
    for name in ("secrets", "tls", "data", "data/state", "data/cache"):
        (runtime / name).mkdir(mode=0o700)
    for name in TEMPLATE_FILES:
        regular(HERE / name)
        private_write(runtime / name, (HERE / name).read_bytes(), 0o444)
    config = json.loads((HERE / "application.template.json").read_text(encoding="utf-8"))
    config["deployment"]["public_origin"] = args.origin
    external = None
    if args.external_db:
        external = json.loads(args.external_db.read_text(encoding="utf-8"))
        required = {
            "host",
            "port",
            "name",
            "username",
            "migration_username",
            "ca_file",
            "password_file",
            "migration_password_file",
        }
        if set(external) != required or not all(
            IDENTIFIER.fullmatch(external[key])
            for key in ("name", "username", "migration_username")
        ):
            raise ValueError("External database configuration fields/accounts are invalid")
        if (
            external["username"] in {"root", "mysql", "mariadb"}
            or "migrat" in external["username"]
            or external["username"] == external["migration_username"]
        ):
            raise ValueError(
                "External database requires separate scoped runtime/migration accounts"
            )
        if (
            not isinstance(external["port"], int)
            or not 1 <= external["port"] <= 65535
            or not re.fullmatch(r"[A-Za-z0-9_.:-]+", external["host"])
        ):
            raise ValueError("Invalid external endpoint")
        for field, destination in (
            ("password_file", "inspector_db_password"),
            ("migration_password_file", "inspector_db_migration_password"),
        ):
            source = Path(external[field])
            secret = database_secret(source)
            private_write(runtime / "secrets" / destination, secret + b"\n", 0o444)
        ca = Path(external["ca_file"])
        regular(ca)
        private_write(runtime / "tls/database-ca.crt", ca.read_bytes(), 0o444)
        config["database"].update(
            {key: external[key] for key in ("host", "port", "name", "username")}
        )
        config["database"].update(
            topology="external",
            tls={"mode": "verify_identity", "ca_file": "/run/tls/database-ca.crt"},
        )
    else:
        for name in (
            "inspector_db_password",
            "inspector_db_migration_password",
            "inspector_db_root_password",
        ):
            private_write(
                runtime / "secrets" / name, (secrets.token_hex(32) + "\n").encode(), 0o444
            )
    vault_key = secrets.token_bytes(32)
    private_write(runtime / "secrets/inspector_vault_key", vault_key)
    private_write(runtime / "data/state/ssh-vault.key", vault_key)
    config["deployment"]["vault_key_file"] = "/var/lib/system-inspector/ssh-vault.key"
    private_write(runtime / "tls/server.crt", args.certificate.read_bytes(), 0o444)
    private_write(runtime / "tls/server.key", args.private_key.read_bytes(), 0o444)
    json_write(runtime / "application.yaml", config, 0o444)
    settings = dict(
        stack="inspector-" + secrets.token_hex(5),
        engine=args.engine,
        bind_address=args.bind_address,
        port=port,
        external=bool(external),
        migration_user=external["migration_username"] if external else "inspector_migrator",
    )
    json_write(runtime / "settings.json", settings)
    print("Private runtime initialized. Load images, then start and bootstrap-admin.")


class Runtime:
    def __init__(self, args):
        self.root = args.runtime
        self.release = args.release
        if self.root.is_symlink() or stat.S_IMODE(self.root.stat().st_mode) != 0o700:
            raise ValueError("Runtime directory must be private (0700), without symlinks")
        self.settings = json.loads((self.root / "settings.json").read_text(encoding="utf-8"))
        self.engine = args.engine
        if self.settings["engine"] != self.engine:
            raise ValueError("Use the engine chosen when initializing this runtime")
        self.stack = self.settings["stack"]
        if not re.fullmatch(r"inspector-[a-f0-9]{10}", self.stack):
            raise ValueError("Invalid private stack identity")
        self.config = json.loads((self.root / "application.yaml").read_text(encoding="utf-8"))
        self.images = release_images(args.release)

    def preflight(self):
        loaded_images(self.engine, self.images)
        for name in ("secrets", "tls", "data"):
            path = self.root / name
            if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o700:
                raise ValueError("Runtime private directories must retain mode 0700")
        env = {
            "INSPECTOR_STACK": self.stack,
            "INSPECTOR_IMAGE": self.images["app"]["image_id"],
            "PROXY_IMAGE": self.images["proxy"]["image_id"],
            "MARIADB_IMAGE": self.images["mariadb"]["image_id"],
            "INSPECTOR_BIND_ADDRESS": self.settings["bind_address"],
            "INSPECTOR_HTTPS_PORT": str(self.settings["port"]),
            "INSPECTOR_MIGRATION_USER": self.settings["migration_user"],
        }
        destination = self.root / "images.env"
        if destination.exists():
            regular(destination)
            destination.unlink()
        private_write(
            destination, "".join(f"{key}={value}\n" for key, value in env.items()).encode()
        )

    def compose(self, *arguments, **kwargs):
        file = "compose.external.yaml" if self.settings["external"] else "compose.yaml"
        # Inherited shell variables override --env-file in Compose. Remove the
        # complete recipe namespace so a stale operator shell cannot retarget
        # this private stack or substitute an unverified image.
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("INSPECTOR_", "MARIADB_IMAGE", "PROXY_IMAGE", "COMPOSE_"))
        }
        return execute(
            [
                "docker",
                "compose",
                "--project-name",
                self.stack,
                "--project-directory",
                str(self.root),
                "--env-file",
                str(self.root / "images.env"),
                "-f",
                str(self.root / file),
                *arguments,
            ],
            environment=environment,
            **kwargs,
        )

    def file_operation(
        self, action: str, backup: Path | None = None, capture=False, key: Path | None = None
    ):
        command = [
            "python3",
            str(self.root / "fileops.py"),
            action,
            "--data",
            str(self.root / "data"),
        ]
        if backup is not None:
            command.extend(["--backup", str(backup)])
        if key is not None:
            command.extend(["--key", str(key)])
        if self.engine == "podman":
            command = ["podman", "unshare", *command]
        return execute(command, capture=capture)

    def name(self, role: str) -> str:
        return self.stack + "-" + role

    def exists(self, kind: str, name: str) -> bool:
        result = subprocess.run(
            [self.engine, kind, "inspect", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0

    def stop(self, all_services: bool = False):
        roles = ["proxy", "app"] + (
            ["mariadb"] if all_services and not self.settings["external"] else []
        )
        if self.engine == "docker":
            self.compose("stop", "--timeout", "60", *roles)
            for role in roles:
                ids = self.compose("ps", "-q", "--all", role, capture=True).split()
                for container in ids:
                    if (
                        execute(
                            ["docker", "inspect", "--format", "{{.State.Running}}", container],
                            capture=True,
                        ).strip()
                        != "false"
                    ):
                        raise ValueError("Cannot quiesce the serving application")
        else:
            for role in roles:
                if self.exists("container", self.name(role)):
                    execute(["podman", "stop", "--time", "60", self.name(role)])
        print("Collection, edits and retention stopped; no SSH is restarted automatically.")

    def wait_health(self, name: str):
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            status = execute(
                [self.engine, "inspect", "--format", "{{.State.Health.Status}}", name], capture=True
            ).strip()
            if status == "healthy":
                return
            if status == "unhealthy":
                break
            time.sleep(2)
        raise ValueError("Container did not become healthy; serving remains unavailable")

    def podman_networks(self):
        for role in ("database", "service"):
            name = self.name(role)
            if not self.exists("network", name):
                execute(
                    [
                        "podman",
                        "network",
                        "create",
                        *(["--internal"] if role == "database" else []),
                        name,
                    ]
                )

    def mount(self, source: str, target: str, private=True) -> list[str]:
        return ["--volume", f"{self.root / source}:{target}:ro,{('Z' if private else 'z')}"]

    def podman_app(self, migration=False):
        role = "migrate" if migration else "app"
        name = self.name(role)
        if self.exists("container", name):
            execute(["podman", "rm", "--force", name])
        command = [
            "podman",
            "run",
            "--pull=never",
            "--name",
            name,
            "--user",
            "10001:10001",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit",
            "128" if migration else "256",
            "--memory",
            "1g" if migration else "4g",
            "--tmpfs",
            "/tmp:rw,size=256m,mode=1777",
            "--network",
            self.name("service"),
            *self.mount("application.yaml", "/etc/system-inspector/application.yaml", False),
        ]
        if not self.settings["external"]:
            command += ["--network", self.name("database")]
        else:
            command += self.mount("tls/database-ca.crt", "/run/tls/database-ca.crt", False)
        if migration:
            command += self.mount(
                "secrets/inspector_db_migration_password",
                "/run/secrets/inspector_db_migration_password",
                False,
            )
        else:
            command += [
                "--detach",
                "--network-alias",
                "app",
                "--env",
                "INSPECTOR_CONFIG_FILE=/etc/system-inspector/application.yaml",
                "--health-cmd",
                "python -m inspector.cli healthcheck",
                "--health-interval",
                "5s",
                "--health-retries",
                "24",
                "--health-timeout",
                "8s",
                "--health-start-period",
                "15s",
                "--volume",
                f"{self.root / 'data/state'}:/var/lib/system-inspector:Z",
                "--volume",
                f"{self.root / 'data/cache'}:/var/cache/system-inspector:Z",
            ]
            for secret in ("inspector_db_password",):
                command += self.mount("secrets/" + secret, "/run/secrets/" + secret, False)
        command += [self.images["app"]["image_id"]]
        if migration:
            command += [
                "python",
                "-m",
                "inspector.cli",
                "db",
                "upgrade",
                "--config",
                "/etc/system-inspector/application.yaml",
                "--username",
                self.settings["migration_user"],
                "--password-file",
                "/run/secrets/inspector_db_migration_password",
            ]
        execute(command)

    def database(self):
        if self.settings["external"]:
            return
        if self.engine == "docker":
            self.compose("up", "--detach", "--wait", "--wait-timeout", "180", "mariadb")
            return
        self.podman_networks()
        name = self.name("mariadb")
        if self.exists("container", name):
            execute(["podman", "start", name])
        else:
            command = [
                "podman",
                "run",
                "--detach",
                "--pull=never",
                "--name",
                name,
                "--network",
                self.name("database"),
                "--network-alias",
                "mariadb",
                "--security-opt=no-new-privileges",
                "--memory",
                "1g",
                "--pids-limit",
                "256",
                "--volume",
                self.stack + "_database:/var/lib/mysql:Z",
                "--health-cmd",
                "healthcheck.sh --connect --innodb_initialized",
                "--health-interval",
                "5s",
                "--health-timeout",
                "5s",
                "--health-retries",
                "24",
                "--health-start-period",
                "30s",
            ]
            for key, value in {
                "MARIADB_DATABASE": "system_inspector",
                "MARIADB_USER": "inspector_migrator",
                "MARIADB_PASSWORD_FILE": "/run/secrets/inspector_db_migration_password",
                "MARIADB_ROOT_PASSWORD_FILE": "/run/secrets/inspector_db_root_password",
                "MARIADB_ROOT_HOST": "localhost",
                "INSPECTOR_DB_APP_USER": "inspector_app",
                "TZ": "UTC",
            }.items():
                command += ["--env", f"{key}={value}"]
            for secret in (
                "inspector_db_root_password",
                "inspector_db_migration_password",
                "inspector_db_password",
            ):
                command += self.mount("secrets/" + secret, "/run/secrets/" + secret, False)
            for source, target in (
                ("mariadb.cnf", "/etc/mysql/conf.d/inspector.cnf"),
                ("20-runtime-user.sh", "/docker-entrypoint-initdb.d/20-runtime-user.sh"),
                ("db-client.sh", "/opt/inspector/db-client.sh"),
            ):
                command += self.mount(source, target, False)
            execute([*command, self.images["mariadb"]["image_id"]])
        self.wait_health(name)

    def start(self):
        self.preflight()
        self.stop()
        self.file_operation("own")
        if self.engine == "docker":
            self.compose("config", "--quiet")
            self.database()
            # Recreate every time; an old completed migration is never evidence
            # that the current release has migrated the configured database.
            self.compose("up", "--detach", "--force-recreate", "--no-deps", "migrate")
            migration_id = self.compose("ps", "--all", "--quiet", "migrate", capture=True).strip()
            if (
                not migration_id
                or execute(["docker", "wait", migration_id], capture=True).strip() != "0"
            ):
                raise ValueError("Explicit migration failed; serving remains stopped")
            self.compose("up", "--detach", "--wait", "--wait-timeout", "180", "app", "proxy")
        else:
            self.podman_networks()
            self.database()
            self.podman_app(migration=True)
            self.podman_app()
            self.wait_health(self.name("app"))
            name = self.name("proxy")
            if self.exists("container", name):
                execute(["podman", "rm", "--force", name])
            execute(
                [
                    "podman",
                    "run",
                    "--detach",
                    "--pull=never",
                    "--name",
                    name,
                    "--user",
                    "10001:10001",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--pids-limit",
                    "64",
                    "--memory",
                    "128m",
                    "--tmpfs",
                    "/tmp:rw,size=64m,mode=1777",
                    "--network",
                    self.name("service"),
                    "--publish",
                    f"{self.settings['bind_address']}:{self.settings['port']}:8443",
                    *self.mount("tls/server.crt", "/run/tls/server.crt", False),
                    *self.mount("tls/server.key", "/run/tls/server.key", False),
                    self.images["proxy"]["image_id"],
                ]
            )
        print("Application ready. First installation requires interactive bootstrap-admin.")

    def bootstrap(self):
        self.preflight()
        if self.engine == "docker":
            self.compose("exec", "app", "python", "-m", "inspector.cli", "bootstrap-admin")
        else:
            execute(
                [
                    "podman",
                    "exec",
                    "--interactive",
                    "--tty",
                    self.name("app"),
                    "python",
                    "-m",
                    "inspector.cli",
                    "bootstrap-admin",
                ]
            )

    def db(self, action: str, stdin=None, stdout=None, capture=False):
        if not self.settings["external"]:
            if self.engine == "docker":
                return self.compose(
                    "exec",
                    "-T",
                    "mariadb",
                    "sh",
                    "/opt/inspector/db-client.sh",
                    action,
                    stdin=stdin,
                    stdout=stdout,
                    capture=capture,
                    sensitive=True,
                )
            return execute(
                [
                    "podman",
                    "exec",
                    "--interactive",
                    self.name("mariadb"),
                    "sh",
                    "/opt/inspector/db-client.sh",
                    action,
                ],
                stdin=stdin,
                stdout=stdout,
                capture=capture,
                sensitive=True,
            )
        database = self.config["database"]
        command = [
            self.engine,
            "run",
            "--rm",
            "--pull=never",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--tmpfs",
            "/tmp:rw,size=64m,mode=1777",
            "--interactive",
            "--env",
            "SI_DB_HOST=" + database["host"],
            "--env",
            "SI_DB_PORT=" + str(database["port"]),
            "--env",
            "SI_DB_NAME=" + database["name"],
            "--env",
            "SI_DB_USER=" + self.settings["migration_user"],
            "--env",
            "SI_DB_TLS=verify_identity",
        ]
        for source, target in (
            ("db-client.sh", "/opt/inspector/db-client.sh"),
            (
                "secrets/inspector_db_migration_password",
                "/run/secrets/inspector_db_migration_password",
            ),
            ("tls/database-ca.crt", "/run/tls/database-ca.crt"),
        ):
            command += [
                "--volume",
                f"{self.root / source}:{target}:ro" + (",z" if self.engine == "podman" else ""),
            ]
        command += [
            self.images["mariadb"]["image_id"],
            "sh",
            "/opt/inspector/db-client.sh",
            action,
        ]
        return execute(command, stdin=stdin, stdout=stdout, capture=capture, sensitive=True)

    def backup(self, target: Path):
        self.preflight()
        if target.exists() or target.is_relative_to(self.root):
            raise ValueError("Backup destination must be new and outside the runtime")
        target.mkdir(mode=0o700, parents=False)
        self.stop()
        try:
            with (target / "database.sql").open("xb") as stream:
                self.db("dump", stdout=stream)
            private_write(
                target / "database-metadata.txt", self.db("inspect", capture=True).encode()
            )
            json_write(target / "policy.json", self.config)
            records = json.loads(self.file_operation("snapshot", target, capture=True))
            for name in ("database.sql", "database-metadata.txt", "policy.json"):
                path = target / name
                records.append(dict(path=name, bytes=path.stat().st_size, sha256=digest(path)))
            json_write(
                target / "backup.json",
                dict(
                    format="system-inspector-backup-1",
                    created_utc=datetime.now(timezone.utc).isoformat(),
                    images=self.images,
                    vault_key_included=False,
                    files=records,
                ),
            )
            verify_backup(target)
        except BaseException:
            print(
                "Backup incomplete; application remains stopped. Keep the original data.",
                file=sys.stderr,
            )
            raise
        print(
            "Coordinated backup verified. Keep a separate protected copy of the vault key. Application remains stopped."
        )

    def restore(self, source: Path, vault_key: Path):
        self.preflight()
        metadata = verify_backup(source)
        # Restore is deliberately a fresh managed-volume operation. External DB
        # recovery remains an explicit DBA operation, documented in the guide.
        if self.settings["external"]:
            raise ValueError(
                "External database restore requires the documented DBA-controlled fresh-schema procedure"
            )
        if self.exists("volume", self.stack + "_database"):
            raise ValueError(
                "Restore requires a fresh runtime whose database volume does not exist"
            )
        initial_key = self.root / "data/state/ssh-vault.key"
        protected_key = self.root / "secrets/inspector_vault_key"
        for name in ("state", "cache"):
            directory = self.root / "data" / name
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("Restore requires real private state and cache directories")
            entries = list(directory.iterdir())
            if entries and not (name == "state" and entries == [initial_key]):
                raise ValueError("Restore requires empty state and cache directories")
        regular(protected_key)
        if initial_key.exists() or initial_key.is_symlink():
            regular(initial_key)
            if (
                len(initial_key.read_bytes()) != 32
                or initial_key.read_bytes() != protected_key.read_bytes()
            ):
                raise ValueError(
                    "Fresh runtime vault key differs from its protected initialization copy"
                )
        regular(vault_key)
        raw_key = vault_key.read_bytes()
        if len(raw_key) != 32:
            raise ValueError("Invalid separate vault recovery key")
        # Matching image sets are required for rollback; newer releases migrate
        # only after this restore completes and its baseline has been verified.
        if any(
            metadata["images"][role]["image_id"] != self.images[role]["image_id"]
            for role in self.images
        ):
            raise ValueError(
                "Restore with the backup's matching release before an explicit upgrade"
            )
        policy = json.loads((source / "policy.json").read_text(encoding="utf-8"))
        if not isinstance(policy, dict) or any(
            not isinstance(policy.get(category), dict)
            for category in ("limits", "retention", "auth", "bootstrap_settings")
        ):
            raise ValueError("Backup recovery policy is incomplete")
        # A fresh init creates only this bootstrap key. Replace it only after
        # every backup/image/key/policy check, without relaxing fileops.restore.
        if initial_key.exists():
            initial_key.unlink()
        self.file_operation("restore", source)
        key_path = self.root / "secrets/inspector_vault_key"
        regular(key_path)
        key_path.unlink()
        private_write(key_path, raw_key)
        self.file_operation("bind-key", key=key_path)
        # Preserve custom ceilings/auth/retention while retaining the fresh endpoint/origin.
        for category in ("limits", "retention", "auth", "bootstrap_settings"):
            self.config[category] = policy[category]
        (self.root / "application.yaml").unlink()
        json_write(self.root / "application.yaml", self.config, 0o444)
        self.database()
        with (source / "database.sql").open("rb") as stream:
            self.db("restore", stdin=stream)
        if self.db("inspect", capture=True) != (source / "database-metadata.txt").read_text(
            encoding="utf-8"
        ):
            raise ValueError("Restored schema/table counts differ; do not expose the runtime")
        self.db("revoke")
        print(
            "Database/cache restored and verified; sessions revoked. Application remains stopped. Run start, then validate both roles and saved investigations."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=HERE.parent)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--engine", choices=["docker", "podman"], default="docker")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--origin", required=True)
    init.add_argument("--bind-address", default="127.0.0.1")
    init.add_argument("--certificate", type=Path, required=True)
    init.add_argument("--private-key", type=Path, required=True)
    init.add_argument("--external-db", type=Path)
    for name in ("verify", "load", "start", "stop", "bootstrap-admin"):
        commands.add_parser(name)
    backup = commands.add_parser("backup")
    backup.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--vault-key", type=Path, required=True)
    args = parser.parse_args()
    args.release = args.release.absolute()
    args.runtime = args.runtime.absolute()
    os.umask(0o077)
    try:
        if args.command == "verify":
            release_images(args.release)
            print(
                "All three release archive hashes verified. Verify the trusted checksum source separately."
            )
        elif os.name != "posix":
            raise ValueError("Run lifecycle commands on the Linux deployment host")
        elif args.engine == "docker" and os.geteuid() != 0:
            raise ValueError(
                "Native Docker lifecycle requires the approved root operator shell for private data ownership; use sudo or rootless Podman"
            )
        elif args.command == "init":
            initialize(args)
        elif args.command == "load":
            images = release_images(args.release)
            for image in images.values():
                execute(
                    [
                        args.engine,
                        "image",
                        "load",
                        "--input",
                        str(args.release / relative(image["archive"])),
                    ]
                )
            loaded_images(args.engine, images)
            print("All three exact image identities loaded locally.")
        else:
            runtime = Runtime(args)
            if args.command == "start":
                runtime.start()
            elif args.command == "stop":
                runtime.preflight()
                runtime.stop(all_services=True)
            elif args.command == "bootstrap-admin":
                runtime.bootstrap()
            elif args.command == "backup":
                runtime.backup(args.output.absolute())
            elif args.command == "restore":
                runtime.restore(args.backup.absolute(), args.vault_key.absolute())
    except ValueError as error:
        # ValueErrors above contain fixed descriptions, never data or credentials.
        print(f"Operation failed: {error}.", file=sys.stderr)
        return 1
    except (OSError, KeyError, TypeError, subprocess.SubprocessError):
        print(
            "Operation failed. Verify protected configuration, checksums, permissions and container diagnostics; no secrets were displayed.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
