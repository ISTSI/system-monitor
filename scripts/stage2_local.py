"""Isolated local Docker/MariaDB browser verification for Stage 02.

Uses a new synthetic schema and file-only random accounts. Never contacts the
approved VM, changes existing accounts, pulls images or removes retained data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from local_mariadb import (
    DEPLOY,
    ROOT,
    SetupError,
    compose,
    new_test,
    private_directory,
    write_private,
)

STATE = ROOT / ".state/stage2-browser"
PRIVATE = ROOT / ".secrets/stage2-browser"
SETUP = STATE / "setup.json"


def prepare() -> None:
    if SETUP.exists():
        print("Stage 02 browser setup exists; existing schema and credentials preserved.")
        return
    private_directory(PRIVATE)
    STATE.mkdir(parents=True, exist_ok=True)
    suffix = "s2_web_" + secrets.token_hex(5)
    new_test(suffix, execute=False)
    database = "inspector_test_" + suffix
    application = DEPLOY / f"{database}.local.yaml"
    integration = yaml.safe_load((DEPLOY / f"{database}.compose.local.yaml").read_text("utf-8"))
    document = yaml.safe_load(application.read_text("utf-8"))
    document["deployment"]["public_origin"] = "https://localhost:8444"
    application.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    accounts = {
        role: {"username": "stage2-" + role, "password": secrets.token_urlsafe(32)}
        for role in ("administrator", "inspector")
    }
    write_private(
        PRIVATE / "accounts.json", json.dumps(accounts, indent=2) + "\n", mounted_secret=True
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Stage 02 localhost test")])
    now = datetime.now(UTC)
    cert = (
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
    write_private(
        PRIVATE / "localhost-key.pem",
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        mounted_secret=True,
    )
    write_private(
        PRIVATE / "localhost-cert.pem",
        cert.public_bytes(serialization.Encoding.PEM).decode(),
        mounted_secret=True,
    )
    migration_env = integration["services"]["integration"]["environment"]
    override = {
        "services": {
            "migrate": {
                "environment": {
                    "SI_MIGRATION_DB_USERNAME": migration_env["SI_MIGRATION_DB_USERNAME"],
                    "SI_MIGRATION_DB_PASSWORD_FILE": "/run/secrets/test_db_migration_password",
                },
                "volumes": [f"{application.as_posix()}:/etc/system-inspector/application.yaml:ro"],
                "secrets": ["test_db_migration_password"],
            },
            "runtime": {
                "networks": ["database", "browser"],
                "command": [
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
                    "/run/secrets/browser_key",
                    "--ssl-certfile",
                    "/run/secrets/browser_cert",
                ],
                "ports": ["127.0.0.1:8444:8443"],
                "volumes": [
                    f"{application.as_posix()}:/etc/system-inspector/application.yaml:ro",
                    f"{(ROOT / 'scripts').as_posix()}:/workspace/scripts:ro",
                ],
                "secrets": ["test_db_password", "browser_accounts", "browser_key", "browser_cert"],
            },
        },
        "networks": {"browser": {}},
        "secrets": {
            **integration["secrets"],
            "browser_accounts": {"file": (PRIVATE / "accounts.json").as_posix()},
            "browser_key": {"file": (PRIVATE / "localhost-key.pem").as_posix()},
            "browser_cert": {"file": (PRIVATE / "localhost-cert.pem").as_posix()},
        },
    }
    override_file = DEPLOY / "stage2-browser.compose.local.yaml"
    write_private(override_file, yaml.safe_dump(override, sort_keys=False))
    SETUP.write_text(
        json.dumps({"database": database, "override": override_file.as_posix()}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "Prepared new isolated Stage 02 browser schema, accounts and localhost TLS; no VM changes."
    )


async def seed() -> None:
    """Runs inside the DML-only container with explicitly mounted test accounts."""
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from inspector import auth, foundation
    from inspector.config import load_config
    from inspector.database import create_engine
    from inspector.domain import Principal
    from inspector.persistence.models import User, Workspace

    config = load_config()
    if not config.database.name.startswith("inspector_test_s2_web_"):
        raise SetupError("Refusing fixture outside the new Stage 02 browser schema.")
    credentials = json.loads(
        await asyncio.to_thread(Path("/run/secrets/browser_accounts").read_text, "utf-8")
    )
    engine = create_engine(config.database)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
            account = await session.scalar(
                select(User).where(User.username_key == credentials["administrator"]["username"])
            )
            if account is None:
                account = await auth.bootstrap_admin(
                    session,
                    credentials["administrator"]["username"],
                    "Synthetic Stage 02 Administrator",
                    credentials["administrator"]["password"],
                )
            actor = Principal(account.id, account.role, account.auth_version)
            inspector = await session.scalar(
                select(User).where(User.username_key == credentials["inspector"]["username"])
            )
            if inspector is None:
                await auth.create_user(
                    session,
                    actor,
                    credentials["inspector"]["username"],
                    "Synthetic Stage 02 Inspector",
                    credentials["inspector"]["password"],
                )
            # Explicit fixture reset affects only these two synthetic accounts
            # in the guarded fresh test schema; never ordinary application users.
            test_users = select(User.id).where(
                User.username_key.in_([entry["username"] for entry in credentials.values()])
            )
            await session.execute(
                update(Workspace)
                .where(Workspace.owner_user_id.in_(test_users))
                .values(state="expired", revision=Workspace.revision + 1)
            )
            await foundation.initialize_settings(session, config)
            await foundation.seed_demo(session, actor)
        print("Seeded synthetic accounts and demos; all secrets remain file-only.")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "migrate", "fixture", "up", "stop", "seed"])
    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(seed())
        return
    if os.environ.get("DOCKER_HOST") is None and os.name == "nt":
        os.environ["DOCKER_HOST"] = "npipe:////./pipe/dockerDesktopLinuxEngine"
        os.environ["DOCKER_CONFIG"] = str(ROOT / ".cache/docker")
    if args.command == "prepare":
        prepare()
        return
    setup = json.loads(SETUP.read_text("utf-8"))
    override = Path(setup["override"])
    if args.command == "migrate":
        output = compose("run", "--rm", "--no-deps", "migrate", override=override)
    elif args.command == "fixture":
        output = compose(
            "run",
            "--rm",
            "--no-deps",
            "runtime",
            "python",
            "/workspace/scripts/stage2_local.py",
            "seed",
            override=override,
        )
    elif args.command == "up":
        # The database bridge is internal; a separate app bridge carries only
        # the explicitly loopback-published browser port on Docker Desktop.
        document = yaml.safe_load(override.read_text("utf-8"))
        document["services"]["runtime"]["networks"] = ["database", "browser"]
        document.setdefault("networks", {})["browser"] = {}
        override.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        output = compose("up", "--detach", "--no-deps", "runtime", override=override)
    else:
        output = compose("stop", "runtime", override=override)
    print(output, end="")


if __name__ == "__main__":
    main()
