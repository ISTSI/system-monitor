"""Isolated local Docker/MariaDB browser verification for Stage 03.

Uses a new synthetic schema and file-only random accounts. Never contacts the
approved VM, changes existing accounts, pulls images or removes retained data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
from copy import deepcopy
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

STATE = ROOT / ".state/stage3-browser"
PRIVATE = ROOT / ".secrets/stage3-browser"
SETUP = STATE / "setup.json"


def prepare() -> None:
    if SETUP.exists():
        print("Stage 03 browser setup exists; existing schema and credentials preserved.")
        return
    private_directory(PRIVATE, windows_owner=os.environ.get("SI_WINDOWS_SECRET_OWNER"))
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "cache").mkdir(mode=0o700, exist_ok=True)
    suffix = "s3_web_" + secrets.token_hex(5)
    new_test(suffix, execute=False)
    database = "inspector_test_" + suffix
    application = DEPLOY / f"{database}.local.yaml"
    integration = yaml.safe_load((DEPLOY / f"{database}.compose.local.yaml").read_text("utf-8"))
    document = yaml.safe_load(application.read_text("utf-8"))
    document["deployment"]["public_origin"] = "https://localhost:8445"
    application.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    accounts = {
        role: {"username": "stage3-" + role, "password": secrets.token_urlsafe(32)}
        for role in ("administrator", "inspector")
    }
    write_private(
        PRIVATE / "accounts.json", json.dumps(accounts, indent=2) + "\n", mounted_secret=True
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Stage 03 localhost test")])
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
    runtime_base = yaml.safe_load((DEPLOY / "compose.yaml").read_text("utf-8"))["services"][
        "runtime"
    ]
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
            "runtime-stage3": {
                **deepcopy(runtime_base),
                "networks": ["database", "browser"],
                "environment": {"SI_LOCAL_HISTORY_DEMO": "1"},
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
                "ports": ["127.0.0.1:8445:8443"],
                "tmpfs": ["/tmp:mode=1777", "/var/lib/system-inspector:mode=1777"],
                "volumes": [
                    "../../backend:/workspace/backend:ro",
                    f"{application.as_posix()}:/etc/system-inspector/application.yaml:ro",
                    f"{(ROOT / 'scripts').as_posix()}:/workspace/scripts:ro",
                    f"{(ROOT / 'fixtures').as_posix()}:/workspace/fixtures:ro",
                    f"{(ROOT / 'examples').as_posix()}:/workspace/examples:ro",
                    f"{(ROOT / 'tools').as_posix()}:/workspace/tools:ro",
                    f"{(ROOT / 'frontend/dist').as_posix()}:/workspace/frontend/dist:ro",
                    f"{(STATE / 'cache').as_posix()}:/var/cache/system-inspector",
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
    override["services"]["runtime-stage3"]["environment"].update(runtime_base["environment"])
    override_file = DEPLOY / "stage3-browser.compose.local.yaml"
    write_private(override_file, yaml.safe_dump(override, sort_keys=False))
    SETUP.write_text(
        json.dumps({"database": database, "override": override_file.as_posix()}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "Prepared new isolated Stage 03 browser schema, accounts and localhost TLS; no VM changes."
    )


async def seed() -> None:
    """Runs inside the DML-only container with explicitly mounted test accounts."""
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from inspector import auth, foundation, services, topology
    from inspector.config import load_config
    from inspector.database import create_engine
    from inspector.domain import Principal
    from inspector.persistence.models import Project, TopologyState, User, Workspace

    config = load_config()
    if not config.database.name.startswith("inspector_test_s3_web_"):
        raise SetupError("Refusing fixture outside the new Stage 03 browser schema.")
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
                    "Synthetic Stage 03 Administrator",
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
                    "Synthetic Stage 03 Inspector",
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
            for suffix in ("a", "b"):
                project_id = "stage3-fixture-" + suffix
                if await session.get(Project, project_id) is not None:
                    continue
                project = await services.create_project(
                    session,
                    actor,
                    "[Synthetic demo] Historical " + suffix.upper(),
                    "Local golden fixture logs only. No SSH targets are approved.",
                    project_id=project_id,
                )
                state = await session.get(TopologyState, project_id)
                assert state is not None
                value = json.loads(
                    await asyncio.to_thread(
                        Path("/workspace/examples/project.example.json").read_text, "utf-8"
                    )
                )
                value["project"].update(
                    id=project_id,
                    name=project.name,
                    description=project.description,
                    revision=project.revision,
                )
                await topology.save(
                    session,
                    actor,
                    project,
                    state,
                    value,
                    confirmed_deletions=False,
                    reparent=False,
                )
        print("Seeded synthetic accounts and demos; all secrets remain file-only.")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["prepare", "migrate", "fixture", "up", "stop", "seed", "benchmark"]
    )
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
            "runtime-stage3",
            "python",
            "/workspace/scripts/stage3_local.py",
            "seed",
            override=override,
        )
    elif args.command == "benchmark":
        output = compose(
            "run",
            "--rm",
            "--no-deps",
            "runtime-stage3",
            "python",
            "/workspace/scripts/benchmark_history.py",
            override=override,
            timeout=300,
        )
    elif args.command == "up":
        # The database bridge is internal; a separate app bridge carries only
        # the explicitly loopback-published browser port on Docker Desktop.
        document = yaml.safe_load(override.read_text("utf-8"))
        document["services"]["runtime-stage3"]["networks"] = ["database", "browser"]
        document.setdefault("networks", {})["browser"] = {}
        override.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        output = compose("up", "--detach", "--no-deps", "runtime-stage3", override=override)
    else:
        output = compose("stop", "runtime-stage3", override=override)
    print(output, end="")


if __name__ == "__main__":
    main()
