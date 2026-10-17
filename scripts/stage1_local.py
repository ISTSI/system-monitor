"""Explicit Stage 01 development setup for the approved existing VM tunnel.

Never starts SSH/VPN, changes database accounts, or replaces existing user data.
The fixture command is synthetic test setup, not the production bootstrap CLI.
"""

import argparse
import asyncio
import ipaddress
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import yaml
from alembic import command
from alembic.config import Config as AlembicConfig
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from local_mariadb import SetupError, private_directory, write_private
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from inspector import auth, foundation, services
from inspector.config import parse_config
from inspector.database import (
    SCHEMA_REVISION,
    check_runtime_grants,
    check_schema,
    create_engine,
    migration_guard,
)
from inspector.domain import Principal
from inspector.persistence.models import AuthSession, User
from inspector.security import token_hash

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy/vm-mariadb"
PRIVATE = ROOT / ".secrets/vm-mariadb"
APPLICATION = DEPLOY / "application.local.yaml"
ACCOUNTS = PRIVATE / "stage1-browser-accounts.json"
EVIDENCE = ROOT / "verification/stage-1"


def config_for(path: Path, *, migration: bool = False):
    config = parse_config(path.read_bytes(), environment={}, migration=migration)
    db = config.database
    if (db.host, db.port, db.name, db.topology) != (
        "127.0.0.1",
        13306,
        "system-monitor",
        "ssh_tunnel",
    ):
        raise SetupError("Refusing a configuration outside the approved Stage 01 VM scope.")
    return config


def prepare() -> None:
    private_directory(PRIVATE)
    document = yaml.safe_load((DEPLOY / "migration.local.yaml").read_text(encoding="utf-8"))
    document["database"].update(
        username="system-monitor-app", password_file=(PRIVATE / "runtime_password").as_posix()
    )
    document["deployment"]["public_origin"] = "https://localhost:8443"
    raw = yaml.safe_dump(document, sort_keys=False)
    parse_config(raw.encode(), environment={})
    if APPLICATION.exists() and APPLICATION.read_text(encoding="utf-8") != raw:
        raise SetupError("Existing runtime configuration differs; preserved without rewriting.")
    if not APPLICATION.exists():
        write_private(APPLICATION, raw)
    certificate = PRIVATE / "localhost-cert.pem"
    keyfile = PRIVATE / "localhost-key.pem"
    if certificate.exists() != keyfile.exists():
        raise SetupError("Partial local TLS setup exists; preserved for review.")
    if not certificate.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "System Inspector local development")]
        )
        now = datetime.now(UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
                ),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        write_private(
            keyfile,
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode(),
        )
        write_private(certificate, cert.public_bytes(serialization.Encoding.PEM).decode())
    print("Prepared ignored runtime configuration and development-only localhost TLS files.")


async def migrate() -> None:
    config = config_for(DEPLOY / "migration.local.yaml", migration=True)
    engine = create_engine(config.database, dedicated=True)
    original = (
        "users",
        "security_state",
        "auth_sessions",
        "projects",
        "project_revisions",
        "workspaces",
        "audit_events",
    )
    try:
        async with migration_guard(engine) as connection:
            version = str(await connection.scalar(text("SELECT VERSION()")))
            if "mariadb" not in version.lower():
                raise SetupError("Approved database must be MariaDB.")
            current = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            if current == SCHEMA_REVISION:
                print("Stage 01 schema is already current; no migration executed.")
                return
            if current != "0001_scoped_foundation":
                raise SetupError("Unexpected starting revision; no migration executed.")
            before = {
                table: [
                    dict(row)
                    for row in (
                        await connection.execute(text(f"SELECT * FROM `{table}` ORDER BY 1"))
                    ).mappings()
                ]
                for table in original
            }
            backup = PRIVATE / "stage1-pre-migration.json"
            if backup.exists():
                raise SetupError(
                    "A previous Stage 01 migration backup exists; preserved for review."
                )
            write_private(
                backup, json.dumps({"revision": current, "tables": before}, indent=2) + "\n"
            )
            await connection.commit()

            def upgrade(sync_connection):
                alembic = AlembicConfig(str(ROOT / "backend/alembic.ini"))
                alembic.attributes["connection"] = sync_connection
                command.upgrade(alembic, "head")

            await connection.run_sync(upgrade)
            await connection.commit()
            await check_schema(connection)
            after = {
                table: [
                    dict(row)
                    for row in (
                        await connection.execute(text(f"SELECT * FROM `{table}` ORDER BY 1"))
                    ).mappings()
                ]
                for table in original
            }
            for row in after["users"]:
                row.pop("must_change_password")
            if before != after:
                raise SetupError("Original data comparison failed; protected backup retained.")
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            (EVIDENCE / "migration.json").write_text(
                json.dumps(
                    {
                        "from_revision": current,
                        "to_revision": SCHEMA_REVISION,
                        "original_tables_compared": len(original),
                        "original_rows_preserved": True,
                        "existing_user_passwords_changed": False,
                        "tunnel_changed": False,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print("Stage 01 migration applied; original rows preserved and compared.")
    finally:
        await engine.dispose()


async def fixture() -> None:
    config = config_for(APPLICATION)
    engine = create_engine(config.database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.connect() as connection:
            await check_schema(connection)
            await check_runtime_grants(connection)
        if not ACCOUNTS.exists():
            suffix = uuid4().hex[:8]
            document = {
                role: {"username": f"stage1-{role}-{suffix}", "password": secrets.token_urlsafe(32)}
                for role in ("administrator", "inspector")
            }
            document["projects"] = [
                {"project_id": "demo-foundation-a", "name": "[Synthetic demo] Payments"},
                {"project_id": "demo-foundation-b", "name": "[Synthetic demo] Orders"},
            ]
            write_private(ACCOUNTS, json.dumps(document, indent=2) + "\n")
        credentials = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
        async with sessions.begin() as session:
            existing = await session.scalar(
                select(User).where(User.username_key == credentials["administrator"]["username"])
            )
            if existing is None:
                # Guarded test fixture only; real installations use interactive inspector.cli.
                if await session.scalar(select(User.id).limit(1)) is not None:
                    raise SetupError(
                        "Synthetic first-admin setup refuses an installation with existing accounts."
                    )
                existing = await auth.bootstrap_admin(
                    session,
                    credentials["administrator"]["username"],
                    "Synthetic Stage 01 Administrator",
                    credentials["administrator"]["password"],
                )
            principal = Principal(existing.id, existing.role, existing.auth_version)
            inspector = await session.scalar(
                select(User).where(User.username_key == credentials["inspector"]["username"])
            )
            if inspector is None:
                await auth.create_user(
                    session,
                    principal,
                    credentials["inspector"]["username"],
                    "Synthetic Stage 01 Inspector",
                    credentials["inspector"]["password"],
                )
            await foundation.initialize_settings(session, config)
            await foundation.seed_demo(session, principal)
        print(
            "Synthetic demo accounts/documentation ready; credentials remain in the protected ignored fixture file."
        )
    finally:
        await engine.dispose()


def integration_request() -> None:
    """Prepare DBA-only creation of an independent disposable schema, never execute it."""
    config_for(APPLICATION)
    target = PRIVATE / "stage1-integration-provision.sql"
    if target.exists():
        raise SetupError("The integration DBA request already exists; credentials preserved.")
    suffix = uuid4().hex[:8]
    database = f"inspector_test_s1_{suffix}"
    runtime_user, migration_user = f"s1_app_{suffix}", f"s1_migrator_{suffix}"
    runtime_password, migration_password = secrets.token_hex(32), secrets.token_hex(32)
    runtime_file, migration_file = (
        PRIVATE / "integration_runtime_password",
        PRIVATE / "integration_migration_password",
    )
    if runtime_file.exists() or migration_file.exists():
        raise SetupError("Partial integration secret setup exists; preserved for review.")
    write_private(runtime_file, runtime_password)
    write_private(migration_file, migration_password)
    scope = database.replace("_", r"\_")
    sql = f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;\nCREATE USER '{runtime_user}'@'%' IDENTIFIED BY '{runtime_password}';\nCREATE USER '{migration_user}'@'%' IDENTIFIED BY '{migration_password}';\nGRANT SELECT, INSERT, UPDATE, DELETE ON `{scope}`.* TO '{runtime_user}'@'%';\nGRANT ALL PRIVILEGES ON `{scope}`.* TO '{migration_user}'@'%';\n"
    write_private(target, sql)
    document = yaml.safe_load(APPLICATION.read_text(encoding="utf-8"))
    document["database"].update(
        name=database, username=runtime_user, password_file=runtime_file.as_posix()
    )
    document["deployment"]["state_dir"] = (ROOT / ".state/stage1-integration").as_posix()
    raw = yaml.safe_dump(document, sort_keys=False)
    parse_config(raw.encode(), environment={})
    integration_config = DEPLOY / "integration.local.yaml"
    if integration_config.exists():
        raise SetupError("Integration configuration already exists; preserved for review.")
    write_private(integration_config, raw)
    write_private(
        DEPLOY / "integration.env.local",
        f"SI_TEST_DISPOSABLE_MARIADB=1\nINSPECTOR_TEST_CONFIG={integration_config.as_posix()}\nSI_MIGRATION_DB_USERNAME={migration_user}\nSI_MIGRATION_DB_PASSWORD_FILE={migration_file.as_posix()}\n",
    )
    print(
        "Prepared ignored stage1-integration-provision.sql for the DBA; no database/accounts were created."
    )


async def browser_pool() -> None:
    """Fresh synthetic accounts for a browser rerun without raising workspace ceilings."""
    target = PRIVATE / "stage1-browser-recheck-accounts.json"
    if target.exists():
        print("Browser recheck fixture already exists; credentials preserved.")
        return
    config = config_for(APPLICATION)
    original = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    suffix = uuid4().hex[:8]
    document = {
        role: {"username": f"stage1-browser-{role}-{suffix}", "password": secrets.token_urlsafe(32)}
        for role in ("administrator", "inspector")
    }
    document["projects"] = original["projects"]
    engine = create_engine(config.database)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
            credentials = await auth.login(
                session,
                original["administrator"]["username"],
                original["administrator"]["password"],
                services.utc_now_us(),
                config.idle_timeout_us,
                config.absolute_timeout_us,
            )
            for role in ("administrator", "inspector"):
                await auth.create_user(
                    session,
                    credentials.principal,
                    document[role]["username"],
                    f"Synthetic Browser {role.title()}",
                    document[role]["password"],
                    role=role,
                )
            await session.execute(
                delete(AuthSession).where(AuthSession.token_hash == token_hash(credentials.token))
            )
            write_private(target, json.dumps(document, indent=2) + "\n")
        print("Fresh protected browser recheck fixture created; workspace ceilings unchanged.")
    finally:
        await engine.dispose()


def serve() -> None:
    import uvicorn

    config_for(APPLICATION)
    os.environ["INSPECTOR_CONFIG_FILE"] = str(APPLICATION)
    uvicorn.run(
        "inspector.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8443,
        workers=1,
        proxy_headers=False,
        access_log=False,
        ssl_keyfile=str(PRIVATE / "localhost-key.pem"),
        ssl_certfile=str(PRIVATE / "localhost-cert.pem"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["prepare", "migrate", "fixture", "serve", "integration-request", "browser-pool"],
    )
    parser.add_argument("--approved-schema", required=True, choices=["system-monitor"])
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare()
        elif args.command == "integration-request":
            integration_request()
        elif args.command == "serve":
            serve()
        elif args.command == "browser-pool":
            asyncio.run(browser_pool())
        else:
            asyncio.run(migrate() if args.command == "migrate" else fixture())
    except Exception as error:
        # Never emit SQL/driver values, URLs, passwords or account fixture payloads.
        if isinstance(error, SetupError):
            parser.exit(1, str(error) + "\n")
        parser.exit(
            1,
            f"Stage 01 operation unavailable ({type(error).__name__}); private data was not printed.\n",
        )


if __name__ == "__main__":
    main()
