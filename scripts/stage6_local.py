"""Isolated Stage 06 HTTPS/MariaDB/read-only-SFTP browser fixture on port 8448.

Existing 8444/8445 installations and all their secrets, schemas and caches are
preserved. Images must already exist locally. Generated fixture writes occur
only inside the new synthetic SFTP container, never through application SSH.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import secrets
import ssl
import urllib.request
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from http.cookiejar import CookieJar
from pathlib import Path

import local_mariadb as local
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.x509.oid import NameOID

ROOT = local.ROOT
STATE = ROOT / ".state/stage6-browser"
PRIVATE = ROOT / ".secrets/stage6-browser"
SETUP = STATE / "setup.json"
ORIGIN = "https://localhost:8448"
SERVICE = "stage6-browser"
SSH_SERVICE = "stage6-sftp"
RUNNER = "system-inspector-runner:stage6"
PROJECTS = ("stage6-fixture-a", "stage6-fixture-b")


def prepare() -> None:
    if SETUP.exists():
        checked_setup()
        print("Existing Stage 06 fixture preserved; no schema or secret changed.")
        return
    local.require_local_docker()
    local.private_directory(PRIVATE, windows_owner=os.environ.get("SI_WINDOWS_SECRET_OWNER"))
    STATE.mkdir(parents=True, exist_ok=True)
    suffix = "s6_web_" + secrets.token_hex(5)
    local.new_test(suffix, execute=False)
    database = "inspector_test_" + suffix
    integration = yaml.safe_load(
        (local.DEPLOY / f"{database}.compose.local.yaml").read_text("utf-8")
    )
    document = yaml.safe_load((local.DEPLOY / f"{database}.local.yaml").read_text("utf-8"))
    document["deployment"].update(
        public_origin=ORIGIN,
        state_dir="/var/lib/system-inspector",
        vault_key_file="/var/lib/system-inspector/ssh-vault.key",
    )
    application = STATE / "application.yaml"
    local.write_private(application, yaml.safe_dump(document, sort_keys=False))
    accounts = {
        role: {"username": "stage6-" + role, "password": secrets.token_urlsafe(32)}
        for role in ("administrator", "inspector")
    }
    local.write_private(PRIVATE / "accounts.json", json.dumps(accounts), mounted_secret=True)
    local.write_private(PRIVATE / "ssh-password", secrets.token_urlsafe(32), mounted_secret=True)
    # Raw vault bytes use an owner-only file, preserving stage4's wrapper format.
    descriptor = os.open(PRIVATE / "vault.key", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(secrets.token_bytes(32))
    ssh_key = ed25519.Ed25519PrivateKey.generate()
    local.write_private(
        PRIVATE / "ssh-key.pem",
        ssh_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption(),
        ).decode(),
        mounted_secret=True,
    )
    public_key = (
        ssh_key.public_key()
        .public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
        .decode()
    )
    fingerprint = "SHA256:" + base64.b64encode(
        hashlib.sha256(base64.b64decode(public_key.split()[1])).digest()
    ).decode().rstrip("=")
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic Stage 06 localhost")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=7))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    local.write_private(
        PRIVATE / "tls-key.pem",
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        mounted_secret=True,
    )
    local.write_private(
        PRIVATE / "tls-cert.pem",
        certificate.public_bytes(serialization.Encoding.PEM).decode(),
        mounted_secret=True,
    )
    base = yaml.safe_load((local.DEPLOY / "compose.yaml").read_text("utf-8"))
    runtime = deepcopy(base["services"]["runtime"])
    runtime.update(
        image=RUNNER,
        networks=["database", "stage6-browser-network"],
        ports=["127.0.0.1:8448:8443"],
        command=[
            "python",
            "/workspace/scripts/stage4_local.py",
            "serve",
            "--",
            "python",
            "-m",
            "uvicorn",
            "inspector.app:create_app",
            "--factory",
            "--host",
            "0.0.0.0",
            "--port",
            "8443",
            "--workers",
            "1",
            "--no-access-log",
            "--no-proxy-headers",
            "--ssl-keyfile",
            "/run/secrets/stage6_tls_key",
            "--ssl-certfile",
            "/run/secrets/stage6_tls_cert",
            "--ws",
            "websockets",
            "--ws-max-size",
            "16384",
            "--ws-max-queue",
            "16",
        ],
        volumes=[
            f"{(ROOT / 'backend').as_posix()}:/workspace/backend:ro",
            f"{application.as_posix()}:/etc/system-inspector/application.yaml:ro",
            f"{(ROOT / 'scripts').as_posix()}:/workspace/scripts:ro",
            f"{(ROOT / 'examples').as_posix()}:/workspace/examples:ro",
        ],
        secrets=[
            "test_db_password",
            "browser_accounts",
            "stage6_tls_key",
            "stage6_tls_cert",
            "ssh_vault_master",
        ],
    )
    sftp = deepcopy(base["services"]["runtime"])
    sftp.update(
        image=RUNNER,
        networks=["database"],
        environment={"PYTHONDONTWRITEBYTECODE": "1"},
        command=[
            "python",
            "/workspace/scripts/stage6_sftp_fixture.py",
            "serve",
            "--key-file",
            "/run/secrets/stage6_ssh_key",
            "--password-file",
            "/run/secrets/stage6_ssh_password",
        ],
        volumes=[
            f"{(ROOT / 'scripts').as_posix()}:/workspace/scripts:ro",
            f"{(ROOT / 'fixtures').as_posix()}:/workspace/fixtures:ro",
        ],
        secrets=["stage6_ssh_key", "stage6_ssh_password"],
    )
    sftp.pop("depends_on", None)
    overlay = {
        "services": {
            "integration": integration["services"]["integration"],
            SERVICE: runtime,
            SSH_SERVICE: sftp,
        },
        "networks": {"stage6-browser-network": {}},
        "secrets": {
            **integration["secrets"],
            **{
                name: {"file": (PRIVATE / filename).as_posix()}
                for name, filename in {
                    "browser_accounts": "accounts.json",
                    "stage6_tls_key": "tls-key.pem",
                    "stage6_tls_cert": "tls-cert.pem",
                    "ssh_vault_master": "vault.key",
                    "stage6_ssh_key": "ssh-key.pem",
                    "stage6_ssh_password": "ssh-password",
                }.items()
            },
        },
    }
    overlay["services"]["integration"]["image"] = RUNNER
    override = local.DEPLOY / "stage6-browser.compose.local.yaml"
    local.write_private(override, yaml.safe_dump(overlay, sort_keys=False))
    (STATE / "public-fixture.json").write_text(
        json.dumps(
            {
                "synthetic": True,
                "host": SSH_SERVICE,
                "port": 8022,
                "username": "synthetic-log-reader",
                "public_key": public_key,
                "fingerprint": fingerprint,
                "projects": PROJECTS,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    SETUP.write_text(
        json.dumps({"database": database, "override": override.as_posix()}, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Prepared fresh isolated Stage 06 schema, HTTPS 8448 and synthetic read-only SFTP.")


def checked_setup() -> Path:
    setup = json.loads(SETUP.read_text("utf-8"))
    import re

    if not re.fullmatch(r"inspector_test_s6_web_[a-f0-9]{10}", setup["database"]):
        raise local.SetupError("Unexpected Stage 06 database identity; nothing changed.")
    override = Path(setup["override"]).resolve()
    if override != (local.DEPLOY / "stage6-browser.compose.local.yaml").resolve():
        raise local.SetupError("Unexpected Stage 06 Compose path; nothing changed.")
    config = yaml.safe_load((STATE / "application.yaml").read_text("utf-8"))
    if (
        config["database"]["name"] != setup["database"]
        or config["database"]["host"] != "mariadb"
        or config["database"]["port"] != 3306
        or config["deployment"]["public_origin"] != ORIGIN
    ):
        raise local.SetupError("Unexpected Stage 06 application scope; nothing changed.")
    services = yaml.safe_load(override.read_text("utf-8"))["services"]
    if set(services) != {"integration", SERVICE, SSH_SERVICE} or services[SERVICE]["ports"] != [
        "127.0.0.1:8448:8443"
    ]:
        raise local.SetupError("Unexpected Stage 06 service boundaries; nothing changed.")
    return override


def new_schema() -> None:
    """Retain a failed synthetic schema and select a new one while the fixture is stopped."""
    override = checked_setup()
    if local.compose("ps", "--quiet", SERVICE, override=override).strip():
        raise local.SetupError(
            "Stop the isolated Stage 06 browser before replacing its test schema."
        )
    previous = json.loads(SETUP.read_text("utf-8"))["database"]
    suffix = "s6_web_" + secrets.token_hex(5)
    local.new_test(suffix, execute=False)
    database = "inspector_test_" + suffix
    generated = yaml.safe_load((local.DEPLOY / f"{database}.compose.local.yaml").read_text("utf-8"))
    application = yaml.safe_load((STATE / "application.yaml").read_text("utf-8"))
    application["database"] = yaml.safe_load(
        (local.DEPLOY / f"{database}.local.yaml").read_text("utf-8")
    )["database"]
    document = yaml.safe_load(override.read_text("utf-8"))
    document["services"]["integration"] = generated["services"]["integration"]
    document["services"]["integration"]["image"] = RUNNER
    document["secrets"].update(generated["secrets"])
    (STATE / "application.yaml").write_text(
        yaml.safe_dump(application, sort_keys=False), encoding="utf-8"
    )
    override.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    history = STATE / "retained-schema-identities.json"
    retained = json.loads(history.read_text("utf-8")) if history.exists() else []
    history.write_text(json.dumps([*retained, previous], indent=2) + "\n", encoding="utf-8")
    SETUP.write_text(
        json.dumps({"database": database, "override": override.as_posix()}, indent=2) + "\n",
        encoding="utf-8",
    )
    checked_setup()
    print(
        "Selected a fresh Stage 06 test schema; previous synthetic schema and fixture identities preserved."
    )


async def seed() -> None:
    """Runs with the isolated schema's runtime DML account, never migration/root."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from inspector import auth, foundation, services
    from inspector.config import load_config
    from inspector.database import create_engine
    from inspector.domain import Principal
    from inspector.persistence.models import Project, User

    config = load_config()
    if not config.database.name.startswith("inspector_test_s6_web_"):
        raise local.SetupError("Refusing Stage 06 seeding outside its isolated schema.")
    accounts = json.loads(
        await asyncio.to_thread(Path("/run/secrets/browser_accounts").read_text, "utf-8")
    )
    engine = create_engine(config.database)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
            admin = await session.scalar(
                select(User).where(User.username_key == accounts["administrator"]["username"])
            )
            if admin is None:
                admin = await auth.bootstrap_admin(
                    session,
                    accounts["administrator"]["username"],
                    "Synthetic Stage 06 Administrator",
                    accounts["administrator"]["password"],
                )
            principal = Principal(admin.id, admin.role, admin.auth_version)
            if not await session.scalar(
                select(User.id).where(User.username_key == accounts["inspector"]["username"])
            ):
                await auth.create_user(
                    session,
                    principal,
                    accounts["inspector"]["username"],
                    "Synthetic Stage 06 Inspector",
                    accounts["inspector"]["password"],
                )
            await foundation.initialize_settings(session, config)
            for project in PROJECTS:
                if await session.get(Project, project) is None:
                    await services.create_project(
                        session,
                        principal,
                        "[Synthetic investigation] " + project[-1].upper(),
                        "Isolated live SFTP fixture only.",
                        project_id=project,
                    )
        print("Seeded only new Stage 06 synthetic accounts and systems; no credentials printed.")
    finally:
        await engine.dispose()


def configure() -> None:
    """Approve only our generated SFTP endpoint through the real secured API."""
    checked_setup()
    jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(
            context=ssl.create_default_context(cafile=str(PRIVATE / "tls-cert.pem"))
        ),
        urllib.request.HTTPCookieProcessor(jar),
    )
    csrf = ""

    def request(path: str, data: dict | None = None, method: str | None = None) -> dict:
        payload = None if data is None else json.dumps(data).encode()
        headers = {"Origin": ORIGIN, "Content-Type": "application/json", "x-csrf-token": csrf}
        with opener.open(
            urllib.request.Request(
                ORIGIN + "/api/v1" + path, data=payload, headers=headers, method=method
            ),
            timeout=30,
        ) as result:
            return json.loads(result.read())

    csrf = request("/auth/csrf")["csrf_token"]
    account = json.loads((PRIVATE / "accounts.json").read_text("utf-8"))["administrator"]
    csrf = request("/auth/login", account)["csrf_token"]
    metadata = json.loads((STATE / "public-fixture.json").read_text("utf-8"))
    for project in PROJECTS:
        topology = request(f"/projects/{project}/topology")
        if topology["revision"] != 1:
            print(f"Existing configured synthetic system {project} preserved.")
            continue
        document = json.loads((ROOT / "examples/project.example.json").read_text("utf-8"))
        document["project"].update(
            id=project, name="[Synthetic investigation] " + project[-1].upper(), revision=1
        )
        document["connections"] = [
            {
                "id": "c-live",
                "name": "Synthetic Stage 06 SFTP",
                "host": SSH_SERVICE,
                "port": 8022,
                "username": metadata["username"],
                "credential_ref": "synthetic-stage6",
                "jump_connection_id": None,
                "allowed_log_roots": ["/var/log/inspector-demo"],
            }
        ]
        for server in document["servers"]:
            server["connection_id"] = "c-live"
        request(
            f"/projects/{project}/topology", {"expected_revision": 1, "config": document}, "PUT"
        )
        base = f"/projects/{project}/connections/c-live"
        request(
            base + "/password",
            {
                "expected_config_revision": 2,
                "expected_credential_revision": 0,
                "password": (PRIVATE / "ssh-password").read_text("ascii").strip(),
            },
            "PUT",
        )
        inspection = request(base + "/host-key/inspect", {"expected_config_revision": 2})
        if inspection["fingerprint"] != metadata["fingerprint"]:
            raise local.SetupError(
                "Generated Stage 06 host fingerprint did not match; approval refused."
            )
        request(
            base + "/host-key/approve",
            {
                "expected_config_revision": 2,
                "expected_trust_revision": 0,
                "inspection_token": inspection["inspection_token"],
                "verified": True,
            },
        )
        request(
            base + "/source-access/approve",
            {"expected_config_revision": 2, "expected_approval_revision": 0, "verified": True},
        )
    print("Configured only generated Stage 06 target keys, passwords and log-root approvals.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "prepare",
            "migrate",
            "fixture",
            "seed",
            "up",
            "stop",
            "stop-sftp",
            "configure",
            "restart",
            "new-schema",
        ],
    )
    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(seed())
        return
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".cache/docker"))
    if args.command == "prepare":
        prepare()
        return
    override = checked_setup()
    if args.command == "new-schema":
        new_schema()
        return
    if args.command == "configure":
        configure()
        return
    if args.command == "migrate":
        output = local.compose(
            "run",
            "--rm",
            "--no-deps",
            "-e",
            "INSPECTOR_CONFIG_FILE=/etc/system-inspector/integration.yaml",
            "integration",
            "python",
            "-m",
            "alembic",
            "upgrade",
            "head",
            override=override,
        )
    elif args.command == "fixture":
        output = local.compose(
            "run",
            "--rm",
            "--no-deps",
            SERVICE,
            "python",
            "/workspace/scripts/stage6_local.py",
            "seed",
            override=override,
        )
    elif args.command == "up":
        output = local.compose(
            "up", "--detach", "--no-deps", SSH_SERVICE, SERVICE, override=override
        )
    elif args.command == "restart":
        output = local.compose("restart", SERVICE, override=override)
    elif args.command == "stop-sftp":
        output = local.compose("stop", SSH_SERVICE, override=override)
    else:
        output = local.compose("stop", SERVICE, SSH_SERVICE, override=override)
    print(output, end="")


if __name__ == "__main__":
    try:
        main()
    except local.SetupError as error:
        raise SystemExit(str(error)) from None
    except (OSError, ValueError, KeyError):
        raise SystemExit("Stage 06 fixture failed safely; no secret values were printed.") from None
