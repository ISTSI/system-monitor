"""Add isolated SSH fixtures/vault mounting to the existing Stage 03 local app.

Preparation preserves its existing schema, accounts, topology, HTTPS endpoint
and secrets. It never seeds or resets application data, runs migrations, pulls
images, contacts user targets, or touches the Stage 02/VM environments.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import stat
import sys
from copy import deepcopy
from pathlib import Path

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from local_mariadb import (
    DEPLOY,
    ROOT,
    SetupError,
    compose,
    private_directory,
    write_private,
)

STATE = ROOT / ".state/stage4-ssh"
PRIVATE = ROOT / ".secrets/stage4-ssh"
STAGE3_SETUP = ROOT / ".state/stage3-browser/setup.json"
VAULT_RUNTIME = "/var/lib/system-inspector/ssh-vault.key"


def load_existing() -> tuple[dict, Path, dict, Path, dict]:
    setup = json.loads(STAGE3_SETUP.read_text("utf-8"))
    database = setup.get("database", "")
    if not re.fullmatch(r"inspector_test_s3_web_[a-f0-9]{10}", database):
        raise SetupError("Refusing to change anything outside the existing Stage 03 test schema.")
    override = Path(setup["override"]).resolve()
    if override != (DEPLOY / "stage3-browser.compose.local.yaml").resolve():
        raise SetupError("Unexpected Stage 03 override; existing configuration preserved.")
    application = DEPLOY / f"{database}.local.yaml"
    document = yaml.safe_load(application.read_text("utf-8"))
    if (
        document["database"]["name"] != database
        or document["database"]["host"] != "mariadb"
        or document["deployment"]["public_origin"] != "https://localhost:8445"
    ):
        raise SetupError("Unexpected Stage 03 application identity; nothing changed.")
    services = yaml.safe_load(override.read_text("utf-8"))
    return setup, override, services, application, document


def write_raw_once(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    if os.name != "nt":
        os.fchmod(descriptor, 0o444)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)


def ensure_regular(path: Path) -> None:
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise SetupError("A local SSH fixture secret is not a regular file.")


def prepare() -> None:
    setup, override, services, application, document = load_existing()
    private_directory(PRIVATE, windows_owner=os.environ.get("SI_WINDOWS_SECRET_OWNER"))
    STATE.mkdir(parents=True, exist_ok=True)
    vault = PRIVATE / "vault-master.key"
    if not vault.exists():
        write_raw_once(vault, secrets.token_bytes(32))
    ensure_regular(vault)
    if len(vault.read_bytes()) != 32:
        raise SetupError("Existing vault master key must contain exactly 32 raw bytes.")
    metadata = {"synthetic": True, "username": "synthetic-log-reader", "endpoints": {}}
    for role in ("target", "jump"):
        key_file = PRIVATE / f"{role}-host-key.pem"
        if not key_file.exists():
            key = ed25519.Ed25519PrivateKey.generate()
            write_private(
                key_file,
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.OpenSSH,
                    serialization.NoEncryption(),
                ).decode("ascii"),
                mounted_secret=True,
            )
        ensure_regular(key_file)
        key = serialization.load_ssh_private_key(key_file.read_bytes(), password=None)
        public_key = (
            key.public_key()
            .public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
            .decode("ascii")
        )
        fingerprint = "SHA256:" + base64.b64encode(
            hashlib.sha256(base64.b64decode(public_key.split()[1])).digest()
        ).decode("ascii").rstrip("=")
        password_file = PRIVATE / f"{role}-password"
        if not password_file.exists():
            write_private(password_file, secrets.token_urlsafe(32) + "\n", mounted_secret=True)
        ensure_regular(password_file)
        metadata["endpoints"][role] = {
            "host": "ssh-" + role,
            "port": 8022,
            "fingerprint": fingerprint,
            "public_key": public_key,
        }
    runtime = services["services"]["runtime-stage3"]
    wrapped = ["python", "/workspace/scripts/stage4_local.py", "serve", "--"]
    if runtime["command"][: len(wrapped)] != wrapped:
        runtime["command"] = wrapped + runtime["command"]
    service_secrets = runtime.setdefault("secrets", [])
    if "ssh_vault_master" not in service_secrets:
        service_secrets.append("ssh_vault_master")
    services.setdefault("secrets", {})["ssh_vault_master"] = {"file": vault.as_posix()}
    # The source master key stays a read-only mount. The app's own startup
    # wrapper copies it into its ephemeral tmpfs with Linux owner-only mode.
    document["deployment"]["vault_key_file"] = VAULT_RUNTIME
    for role in ("target", "jump"):
        fixture = {
            "platform": "linux/amd64",
            "profiles": ["tooling"],
            "image": "${INSPECTOR_RUNNER_IMAGE:-system-inspector-runner:local}",
            "pull_policy": "never",
            "user": "${INSPECTOR_RUNNER_USER:-10001:10001}",
            "working_dir": "/workspace/backend",
            "entrypoint": [],
            "command": [
                "python",
                "/workspace/scripts/stage4_ssh_fixture.py",
                role,
                "--key-file",
                f"/run/secrets/ssh_{role}_host_key",
                "--password-file",
                f"/run/secrets/ssh_{role}_password",
            ],
            "environment": {"PYTHONDONTWRITEBYTECODE": "1"},
            "volumes": [f"{(ROOT / 'scripts').as_posix()}:/workspace/scripts:ro"],
            "secrets": [f"ssh_{role}_host_key", f"ssh_{role}_password"],
            "networks": ["database"],
            "read_only": True,
            "tmpfs": ["/tmp:mode=1777"],
            "security_opt": ["no-new-privileges:true"],
            "cap_drop": ["ALL"],
            "pids_limit": 64,
            "mem_limit": "128m",
        }
        if role == "target":
            fixture["volumes"].append(
                f"{(ROOT / 'fixtures/logs').as_posix()}:/fixture-root/var/log/inspector-demo:ro"
            )
        services["services"]["ssh-" + role] = fixture
        services["secrets"][f"ssh_{role}_host_key"] = {
            "file": (PRIVATE / f"{role}-host-key.pem").as_posix()
        }
        services["secrets"][f"ssh_{role}_password"] = {
            "file": (PRIVATE / f"{role}-password").as_posix()
        }
    application.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    override.write_text(yaml.safe_dump(services, sort_keys=False), encoding="utf-8")
    (STATE / "public-fixture.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    (STATE / "setup.json").write_text(
        json.dumps(
            {**deepcopy(setup), "fixture_metadata": str(STATE / "public-fixture.json")}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    print("Prepared SSH fixtures and protected vault mount for the existing Stage 03 app.")
    print(
        "Existing accounts, schema, topology and HTTPS endpoint are preserved; no services started."
    )
    print("Public fixture fingerprints: .state/stage4-ssh/public-fixture.json")


def serve(arguments: list[str]) -> None:
    """Container-only wrapper: protect the copied key, then exec original ASGI argv."""
    if arguments and arguments[0] == "--":
        arguments = arguments[1:]
    if not arguments:
        raise SetupError("The original server command is required.")
    configured = yaml.safe_load(Path(os.environ["INSPECTOR_CONFIG_FILE"]).read_text("utf-8"))
    if configured["deployment"]["vault_key_file"] != VAULT_RUNTIME:
        raise SetupError("The local vault destination is unexpected.")
    source = Path("/run/secrets/ssh_vault_master")
    ensure_regular(source)
    key = source.read_bytes()
    if len(key) != 32:
        raise SetupError("The mounted local vault master key has an invalid length.")
    destination = Path(VAULT_RUNTIME)
    if destination.exists() or destination.is_symlink():
        ensure_regular(destination)
        metadata = destination.stat()
        if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
            raise SetupError("An existing local vault copy is not private to the app.")
        if destination.read_bytes() != key:
            raise SetupError("An existing local vault copy differs; refusing implicit rotation.")
    else:
        descriptor = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(key)
    os.execvp(arguments[0], arguments)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "up", "fixtures-up", "stop", "serve"])
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.command == "serve":
            serve(args.arguments)
            return
        if os.environ.get("DOCKER_HOST") is None and os.name == "nt":
            os.environ["DOCKER_HOST"] = "npipe:////./pipe/dockerDesktopLinuxEngine"
            os.environ["DOCKER_CONFIG"] = str(ROOT / ".cache/docker")
        if args.command == "prepare":
            prepare()
            return
        _, override, _, _, _ = load_existing()
        if not (STATE / "setup.json").is_file():
            raise SetupError("Run stage4_local.py prepare first.")
        if args.command in ("up", "fixtures-up"):
            targets = ["ssh-target", "ssh-jump"]
            if args.command == "up":
                targets.append("runtime-stage3")
            print(compose("up", "--detach", "--no-deps", *targets, override=override), end="")
        else:
            print(
                compose("stop", "runtime-stage3", "ssh-target", "ssh-jump", override=override),
                end="",
            )
    except (SetupError, OSError, ValueError, KeyError):
        error = sys.exception()
        message = (
            str(error)
            if isinstance(error, SetupError)
            else "Local SSH setup failed; no secrets were printed."
        )
        parser.exit(1, message + "\n")


if __name__ == "__main__":
    main()
