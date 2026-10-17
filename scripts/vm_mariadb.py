"""Explicit development migration via a user-managed loopback SSH tunnel.

This tool never starts/stops SSH or VPN, creates another database, or serves the
application using the migration account. Passwords are file-only and never argv.
"""

import argparse
import asyncio
import json
import re
import secrets
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from local_mariadb import SetupError, private_directory, write_private
from sqlalchemy import text

from inspector.config import parse_config
from inspector.database import SCHEMA_REVISION, check_schema, create_engine, migration_guard

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy/vm-mariadb"
SECRET_DIR = ROOT / ".secrets/vm-mariadb"
CONFIG = DEPLOY / "migration.local.yaml"


def save_once(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise SetupError(
                "Local VM configuration already differs; existing files were preserved."
            )
    else:
        write_private(path, content)


def prepare(args: argparse.Namespace) -> None:
    import yaml

    private_directory(SECRET_DIR)
    DEPLOY.mkdir(parents=True, exist_ok=True)
    password = Path(args.password_file).resolve()
    if not password.is_relative_to(SECRET_DIR) or not password.is_file():
        raise SetupError("Use the existing password file inside the private VM secret directory.")
    document = yaml.safe_load(
        (ROOT / "examples/deployment-policy.example.yaml").read_text(encoding="utf-8")
    )
    document["deployment"].update(
        public_origin="https://localhost:8443",
        state_dir=(ROOT / ".state/vm-mariadb").as_posix(),
        cache_dir=(ROOT / ".cache/vm-mariadb").as_posix(),
        vault_key_file=(SECRET_DIR / "vault_key").as_posix(),
    )
    document["database"].update(
        topology="ssh_tunnel",
        host=args.host,
        port=args.port,
        name=args.database,
        username=args.username,
        password_file=password.as_posix(),
        tls={"mode": "disabled", "ca_file": None},
    )
    raw = yaml.safe_dump(document, sort_keys=False)
    parse_config(raw.encode(), {}, migration=True)
    save_once(CONFIG, raw)
    save_once(
        DEPLOY / ".env.local",
        f"DB_HOST={args.host}\nDB_PORT={args.port}\nDB_DATABASE={args.database}\nDB_USERNAME={args.username}\nDB_PASSWORD_FILE={password.as_posix()}\nINSPECTOR_VM_MIGRATION_CONFIG={CONFIG.as_posix()}\n",
    )
    print("Prepared ignored VM migration configuration using the existing tunnel and secret file.")


async def initialize(args: argparse.Namespace) -> None:
    config = parse_config(CONFIG.read_bytes(), {}, migration=True)
    if config.database.topology != "ssh_tunnel" or config.database.name != args.expected_database:
        raise SetupError(
            "VM scope must match the explicitly expected database and SSH-tunnel transport."
        )
    engine = create_engine(config.database, dedicated=True)
    report = {
        "database": config.database.name,
        "remote_schema_created": False,
        "tunnel_changed": False,
    }
    try:
        async with migration_guard(engine) as connection:
            version = str(await connection.scalar(text("SELECT VERSION()")))
            if "mariadb" not in version.lower():
                raise SetupError("The approved endpoint must be MariaDB; no migration executed.")
            report["server_version"] = version
            current = await connection.scalar(text("SELECT DATABASE()"))
            if current != args.expected_database:
                raise SetupError(
                    "Connection selected an unexpected database; no migration executed."
                )
            count = await connection.scalar(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=:schema"),
                {"schema": config.database.name},
            )
            if count:
                await check_schema(connection)
                report["result"] = "already_initialized"
            else:
                await connection.commit()

                def upgrade(sync_connection):
                    alembic = AlembicConfig(str(ROOT / "backend/alembic.ini"))
                    alembic.attributes["connection"] = sync_connection
                    command.upgrade(alembic, "head")

                await connection.run_sync(upgrade)
                await connection.commit()
                await check_schema(connection)
                report["result"] = "initialized_from_empty_schema"
            report["schema_revision"] = SCHEMA_REVISION
            report["table_count"] = await connection.scalar(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=:schema"),
                {"schema": config.database.name},
            )
            await connection.commit()
    finally:
        await engine.dispose()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


def runtime_request(args: argparse.Namespace) -> None:
    config = parse_config(CONFIG.read_bytes(), {}, migration=True)
    if (
        args.username in {"root", "mysql", "mariadb"}
        or "migrat" in args.username
        or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", args.username)
        or args.username == config.database.username
    ):
        raise SetupError("Choose a distinct bounded runtime account name.")
    private_directory(SECRET_DIR)
    password_path = SECRET_DIR / "runtime_password"
    if password_path.exists():
        raise SetupError(
            "A runtime provisioning request already exists; no credential was rotated."
        )
    password = secrets.token_hex(32)
    write_private(password_path, password)
    scope = config.database.name.replace("_", r"\_")
    sql = f"CREATE USER '{args.username}'@'%' IDENTIFIED BY '{password}';\nGRANT SELECT, INSERT, UPDATE, DELETE ON `{scope}`.* TO '{args.username}'@'%';\n"
    write_private(SECRET_DIR / "provision_runtime.sql", sql)
    print(
        "Prepared an ignored DBA provisioning SQL file and separate runtime password; no SQL was executed."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparer = commands.add_parser("prepare")
    preparer.add_argument("--host", required=True)
    preparer.add_argument("--port", required=True, type=int)
    preparer.add_argument("--database", required=True)
    preparer.add_argument("--username", required=True)
    preparer.add_argument("--password-file", required=True)
    initializer = commands.add_parser("initialize")
    initializer.add_argument("--expected-database", required=True)
    initializer.add_argument(
        "--output", type=Path, default=ROOT / "verification/vm-mariadb/migration.json"
    )
    requester = commands.add_parser("runtime-request")
    requester.add_argument("--username", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args)
        elif args.command == "initialize":
            asyncio.run(initialize(args))
        else:
            runtime_request(args)
    except SetupError as error:
        parser.exit(1, str(error) + "\n")
    except Exception as error:
        number = error.args[0] if error.args and isinstance(error.args[0], int) else "unavailable"
        parser.exit(
            1,
            f"VM operation failed safely ({type(error).__name__}, code {number}); credentials were not printed.\n",
        )


if __name__ == "__main__":
    main()
