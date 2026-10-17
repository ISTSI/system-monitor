"""Provision the isolated local MariaDB without exposing passwords in argv or output.

Requires the locked backend Python environment (PyYAML). All Docker subprocesses
use argv without a shell. No pull, destructive reset, or existing-secret rotation
is performed. The compose project and persistent volume are local to this repo.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "local-mariadb"
SECRET_DIR = ROOT / ".secrets" / "local-mariadb"
ENV_FILE = DEPLOY / ".env.local"
IMAGE_PATTERN = re.compile(r"(?:docker\.io/library/)?mariadb:11\.8\.[0-9]+@sha256:[a-f0-9]{64}")
SUFFIX_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,19}")


class SetupError(Exception):
    """Safe failure text, with no underlying database output."""


def run(argv: list[str], *, label: str, data: str | None = None, timeout: int = 180) -> str:
    try:
        result = subprocess.run(
            argv,
            input=data,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            cwd=ROOT,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise SetupError(
            f"{label} unavailable or timed out; no credentials were printed."
        ) from None
    if result.returncode:
        raise SetupError(f"{label} failed (exit {result.returncode}); no credentials were printed.")
    return result.stdout


def require_local_docker() -> None:
    """Fail before mutation if the selected daemon could be a remote host."""

    def local(endpoint: str) -> bool:
        if not isinstance(endpoint, str) or any(ord(char) < 32 for char in endpoint):
            return False
        return (
            endpoint.startswith("unix:///") and len(endpoint) > len("unix:///")
        ) or re.fullmatch(r"npipe:/{2,4}\./pipe/[A-Za-z0-9_.-]+", endpoint) is not None

    docker_host = os.environ.get("DOCKER_HOST")
    if docker_host and not local(docker_host):
        raise SetupError("Refusing a remote DOCKER_HOST; only a local Docker daemon is authorized.")
    context = os.environ.get("DOCKER_CONTEXT")
    # A supplied local DOCKER_HOST is the endpoint when no context overrides it.
    if docker_host and not context:
        return
    argv = ["docker", "context", "inspect"]
    if context:
        argv.append(context)
    argv.extend(["--format", "{{json .Endpoints.docker.Host}}"])
    try:
        endpoint = json.loads(run(argv, label="Inspecting the selected local Docker context"))
    except (ValueError, TypeError):
        raise SetupError("Unable to verify that the selected Docker daemon is local.") from None
    if not local(endpoint):
        raise SetupError(
            "Refusing a remote Docker context; only a local Docker daemon is authorized."
        )


def private_directory(path: Path, *, windows_owner: str | None = None) -> None:
    if path.is_symlink():
        raise SetupError("Secret directory must not be a symbolic link.")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "nt":
        raw = run(["whoami", "/user", "/fo", "csv", "/nh"], label="Local account lookup")
        rows = list(csv.reader(io.StringIO(raw)))
        if len(rows) != 1 or len(rows[0]) != 2 or not re.fullmatch(r"S-[0-9-]+", rows[0][1]):
            raise SetupError("Unable to identify the local secret owner.")
        owner_sid = rows[0][1]
        designated_owner = path / ".windows_owner_sid"
        additional_sid = None
        if designated_owner.exists():
            if designated_owner.is_symlink() or not designated_owner.is_file():
                raise SetupError("The designated Windows-owner record is invalid.")
            additional_sid = designated_owner.read_text("ascii").strip()
            if not re.fullmatch(r"S-[0-9-]+", additional_sid):
                raise SetupError("The designated Windows-owner record is invalid.")
        if windows_owner is not None:
            quoted_owner = "'" + windows_owner.replace("'", "''") + "'"
            lookup = (
                "$ErrorActionPreference='Stop';"
                f"$taskOwner=New-Object System.Security.Principal.NTAccount({quoted_owner});"
                "$taskOwner.Translate([System.Security.Principal.SecurityIdentifier]).Value;"
            )
            encoded_lookup = base64.b64encode(lookup.encode("utf-16-le")).decode("ascii")
            translated = run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    encoded_lookup,
                ],
                label="Resolving the designated local Windows owner",
            ).strip()
            if not re.fullmatch(r"S-[0-9-]+", translated):
                raise SetupError("Unable to resolve the designated Windows owner.")
            if additional_sid is not None and additional_sid != translated:
                raise SetupError(
                    "A different Windows owner is already designated; nothing was changed."
                )
            additional_sid = translated
        # Replace the DACL rather than leaving unexpected explicit ACEs behind.
        # The encoded command contains only the path and owner SID, no secrets.
        quoted_path = "'" + str(path).replace("'", "''") + "'"
        account_sids = list(dict.fromkeys([owner_sid, additional_sid, "S-1-5-18", "S-1-5-32-544"]))
        sid_array = ",".join(f"'{sid}'" for sid in account_sids if sid is not None)
        script = (
            "$ErrorActionPreference='Stop';"
            "$taskAcl=New-Object System.Security.AccessControl.DirectorySecurity;"
            "$taskAcl.SetAccessRuleProtection($true,$false);"
            f"foreach($taskSid in @({sid_array})){{"
            "$taskIdentity=New-Object System.Security.Principal.SecurityIdentifier($taskSid);"
            "$taskRule=New-Object System.Security.AccessControl.FileSystemAccessRule("
            "$taskIdentity,'FullControl','ContainerInherit,ObjectInherit','None','Allow');"
            "$taskAcl.AddAccessRule($taskRule);};"
            f"$taskDirectory=New-Object System.IO.DirectoryInfo({quoted_path});"
            "$taskDirectory.SetAccessControl($taskAcl);"
        )
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            label="Restricting local secret-directory ACL",
        )
        if windows_owner is not None and not designated_owner.exists():
            write_private(designated_owner, additional_sid + "\n")
    else:
        if windows_owner is not None:
            raise SetupError("A designated Windows owner is supported only on Windows.")
        path.chmod(0o700)


def write_private(path: Path, content: str, *, mounted_secret: bool = False) -> None:
    """Create once, without following links or replacing existing secret files."""
    try:
        # Compose mounts individual secret files read-only. The 0700 parent (or
        # Windows DACL) protects them on the host; MariaDB's mysql UID and the
        # runner UID must be able to read their deliberately mounted files.
        mode = 0o444 if mounted_secret else 0o600
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        if os.name != "nt":
            # A restrictive caller umask must not make mounted files unreadable
            # by the mysql UID. The containing directory remains private.
            os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    except FileExistsError:
        raise SetupError(
            "A generated file already exists; existing secrets/configuration preserved."
        ) from None


def existing_secret(path: Path) -> str:
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise SetupError("A local secret is not a regular file.")
    value = path.read_text(encoding="ascii").removesuffix("\n")
    if not re.fullmatch(r"[a-f0-9]{64}", value):
        raise SetupError("An existing local secret has an invalid format; nothing was rotated.")
    return value


def deployment_config(database: str, username: str, password_file: str, state: str) -> str:
    document = yaml.safe_load((ROOT / "examples/deployment-policy.example.yaml").read_text("utf-8"))
    document["deployment"].update(
        public_origin="https://localhost:8443",
        state_dir=state,
        cache_dir="/var/cache/system-inspector",
        vault_key_file="/run/secrets/inspector_vault_key",
    )
    document["database"].update(
        topology="managed",
        host="mariadb",
        port=3306,
        name=database,
        username=username,
        password_file=password_file,
        tls={"mode": "disabled", "ca_file": None},
    )
    return yaml.safe_dump(document, sort_keys=False)


def grant_schema_pattern(database: str) -> str:
    """GRANT database names are patterns even inside identifier quotes."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", database):
        raise SetupError("Invalid database name for a scoped grant.")
    return database.replace("_", r"\_")


def bootstrap_sql(runtime_password: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{64}", runtime_password):
        raise SetupError("Invalid bootstrap password format.")
    pattern = grant_schema_pattern("system_inspector")
    # Defensively give the new migrator a known exact scope without changing
    # its authentication. This runs only during an empty-volume initialization.
    return (
        "REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'inspector_migrator'@'%';\n"
        f"GRANT ALL PRIVILEGES ON `{pattern}`.* TO 'inspector_migrator'@'%';\n"
        f"CREATE USER 'inspector_app'@'%' IDENTIFIED BY '{runtime_password}';\n"
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{pattern}`.* TO 'inspector_app'@'%';\n"
    )


def compose(*arguments: str, override: Path | None = None, timeout: int = 180) -> str:
    if not ENV_FILE.is_file():
        raise SetupError("Run prepare with a pinned image first.")
    require_local_docker()
    argv = [
        "docker",
        "compose",
        "--project-name",
        "system-inspector-local",
        "--project-directory",
        str(DEPLOY),
        "--env-file",
        str(ENV_FILE),
        "-f",
        str(DEPLOY / "compose.yaml"),
    ]
    if override:
        argv.extend(["-f", str(override)])
    argv.extend(arguments)
    return run(argv, label="Local MariaDB Compose operation", timeout=timeout)


def root_sql(statement: str) -> str:
    # The password is read inside the container. Only the options-file path is
    # passed to mariadb; SQL is supplied through stdin and never logged here.
    require_local_docker()
    script = """set -eu
umask 077
options=$(mktemp)
trap 'rm -f "$options"' EXIT
root_password=$(cat /run/secrets/inspector_db_root_password)
[[ "$root_password" =~ ^[a-f0-9]{64}$ ]] || exit 1
printf '[client]\\nuser=root\\npassword=%s\\n' "$root_password" > "$options"
unset root_password
mariadb --defaults-extra-file="$options" --protocol=socket --batch --skip-column-names
"""
    # compose uses run() for safe captured diagnostics; this form needs stdin.
    argv = [
        "docker",
        "compose",
        "--project-name",
        "system-inspector-local",
        "--project-directory",
        str(DEPLOY),
        "--env-file",
        str(ENV_FILE),
        "-f",
        str(DEPLOY / "compose.yaml"),
        "exec",
        "-T",
        "--user",
        "root",
        "mariadb",
        "bash",
        "-c",
        script,
    ]
    return run(argv, label="Local MariaDB provisioning", data=statement)


def prepare(image: str | None, *, windows_owner: str | None = None) -> None:
    if os.name != "nt" and os.getuid() == 0:
        raise SetupError(
            "Run local preparation as an unprivileged Linux account; runners must not use UID 0."
        )
    if image is None:
        try:
            lock = json.loads((DEPLOY / "images.lock.json").read_text("utf-8"))
            image = lock["images"]["mariadb"]["reference"]
        except (OSError, ValueError, KeyError, TypeError):
            raise SetupError(
                "A valid local images.lock.json or explicit --image is required."
            ) from None
    if not IMAGE_PATTERN.fullmatch(image):
        raise SetupError("Image must be an official mariadb:11.8.PATCH@sha256:DIGEST reference.")
    private_directory(SECRET_DIR, windows_owner=windows_owner)
    if ENV_FILE.exists() or (DEPLOY / "application.local.yaml").exists():
        raise SetupError(
            "Local setup already exists; retained secrets/configuration were not changed."
        )
    passwords = {}
    for name in (
        "inspector_db_root_password",
        "inspector_db_migration_password",
        "inspector_db_password",
    ):
        path = SECRET_DIR / name
        if path.exists():
            passwords[name] = existing_secret(path)
        else:
            passwords[name] = secrets.token_hex(32)
            write_private(path, passwords[name] + "\n", mounted_secret=True)
    bootstrap = SECRET_DIR / "bootstrap.sql"
    if not bootstrap.exists():
        write_private(
            bootstrap,
            bootstrap_sql(passwords["inspector_db_password"]),
            mounted_secret=True,
        )
    write_private(
        DEPLOY / "application.local.yaml",
        deployment_config(
            "system_inspector",
            "inspector_app",
            "/run/secrets/inspector_db_password",
            "/var/lib/system-inspector",
        ),
    )
    runner_user = "10001:10001" if os.name == "nt" else f"{os.getuid()}:{os.getgid()}"
    write_private(
        ENV_FILE,
        f"MARIADB_IMAGE={image}\n"
        "INSPECTOR_RUNNER_IMAGE=system-inspector-runner:local\n"
        f"INSPECTOR_RUNNER_USER={runner_user}\n"
        f"INSPECTOR_SECRETS_DIR={SECRET_DIR.as_posix()}\n",
    )
    print(
        "Prepared private local secrets and Linux application configuration; no database contacted."
    )


def new_test(suffix: str | None, *, execute: bool) -> None:
    suffix = suffix or "run_" + secrets.token_hex(6)
    if not SUFFIX_PATTERN.fullmatch(suffix):
        raise SetupError(
            "Test suffix must be 1-20 lowercase letters, digits or underscores, starting with a letter."
        )
    database = "inspector_test_" + suffix
    # Independent users grant access to this test schema only.
    identity = secrets.token_hex(6)
    username, migration_user = "it_app_" + identity, "it_migrat_" + identity
    if (
        root_sql(
            f"SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='{database}';\n"
        ).strip()
        != "0"
    ):
        raise SetupError(
            "Test schema already exists; existing data preserved. Choose a new suffix."
        )
    private_directory(SECRET_DIR)
    runtime_path = SECRET_DIR / f"{database}_app_password"
    migration_path = SECRET_DIR / f"{database}_migration_password"
    runtime_password, migration_password = secrets.token_hex(32), secrets.token_hex(32)
    write_private(runtime_path, runtime_password + "\n", mounted_secret=True)
    write_private(migration_path, migration_password + "\n", mounted_secret=True)
    config_path = DEPLOY / f"{database}.local.yaml"
    override_path = DEPLOY / f"{database}.compose.local.yaml"
    write_private(
        config_path,
        deployment_config(
            database, username, "/run/secrets/test_db_password", "/tmp/inspector-state"
        ),
    )
    override = {
        "services": {
            "integration": {
                "environment": {
                    "SI_TEST_DISPOSABLE_MARIADB": "1",
                    "INSPECTOR_TEST_CONFIG": "/etc/system-inspector/integration.yaml",
                    "SI_MIGRATION_DB_USERNAME": migration_user,
                    "SI_MIGRATION_DB_PASSWORD_FILE": "/run/secrets/test_db_migration_password",
                },
                "volumes": [f"{config_path.as_posix()}:/etc/system-inspector/integration.yaml:ro"],
                "secrets": ["test_db_password", "test_db_migration_password"],
            }
        },
        "secrets": {
            "test_db_password": {"file": runtime_path.as_posix()},
            "test_db_migration_password": {"file": migration_path.as_posix()},
        },
    }
    write_private(override_path, yaml.safe_dump(override, sort_keys=False))
    grant_pattern = grant_schema_pattern(database)
    root_sql(
        f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;\n"
        f"CREATE USER '{username}'@'%' IDENTIFIED BY '{runtime_password}';\n"
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{grant_pattern}`.* TO '{username}'@'%';\n"
        f"CREATE USER '{migration_user}'@'%' IDENTIFIED BY '{migration_password}';\n"
        f"GRANT ALL PRIVILEGES ON `{grant_pattern}`.* TO '{migration_user}'@'%';\n"
    )
    print(f"Prepared fresh isolated schema: {database}")
    print(f"Integration override: {override_path.relative_to(ROOT).as_posix()}")
    if execute:
        output = compose("run", "--rm", "--no-deps", "integration", override=override_path)
        print(output, end="")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparer = commands.add_parser(
        "prepare", help="Generate private secrets/config; no Docker required"
    )
    preparer.add_argument(
        "--image", help="Defaults to the resolved images.lock.json MariaDB reference"
    )
    preparer.add_argument(
        "--windows-owner", help="Also allow this Windows account to read local secrets"
    )
    securer = commands.add_parser(
        "secure-secrets", help="Set local secret ACLs without changing credentials"
    )
    securer.add_argument("--windows-owner", required=True)
    commands.add_parser("up", help="Start the prepared local DB image and wait healthy")
    commands.add_parser("status", help="Print safe container status")
    commands.add_parser("stop", help="Stop the DB; always retain the volume")
    commands.add_parser("migrate", help="Explicitly migrate only the project development schema")
    tester = commands.add_parser(
        "new-test", help="Create a fresh empty isolated integration schema"
    )
    tester.add_argument("--suffix")
    tester.add_argument(
        "--run", action="store_true", help="Run integration tests in the Linux runner"
    )
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.image, windows_owner=args.windows_owner)
        elif args.command == "secure-secrets":
            if not SECRET_DIR.is_dir():
                raise SetupError("Prepare the local secret directory first.")
            private_directory(SECRET_DIR, windows_owner=args.windows_owner)
            print("Local secret ACLs updated; no credentials or database data were changed.")
        elif args.command == "up":
            compose("up", "--detach", "--wait", "--wait-timeout", "180", "mariadb", timeout=210)
            print("Local MariaDB is healthy; the persistent volume is retained.")
        elif args.command == "status":
            output = compose("ps", "--format", "json", "mariadb")
            for line in output.splitlines():
                row = json.loads(line)
                print(json.dumps({key: row.get(key) for key in ("Name", "State", "Health")}))
        elif args.command == "stop":
            compose("stop", "mariadb")
            print("Local MariaDB stopped; the persistent volume and all schemas were retained.")
        elif args.command == "migrate":
            compose("run", "--rm", "--no-deps", "migrate")
            print("Project development schema explicitly migrated.")
        elif args.command == "new-test":
            new_test(args.suffix, execute=args.run)
    except (SetupError, OSError, ValueError):
        error = sys.exception()
        message = (
            str(error)
            if isinstance(error, SetupError)
            else "Local setup failed; existing data was preserved."
        )
        parser.exit(1, message + "\n")


if __name__ == "__main__":
    main()
