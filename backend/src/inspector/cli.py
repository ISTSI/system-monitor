"""Protected server-side provisioning. Passwords are prompted, never argv values."""

import argparse
import asyncio
import json
from getpass import getpass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_sessionmaker

from inspector import auth, foundation, services
from inspector.app import create_app
from inspector.config import ConfigurationError, load_config, parse_config
from inspector.database import check_schema, create_engine, migration_guard
from inspector.errors import DomainError


async def provision(command: str) -> None:
    config = load_config()
    engine = create_engine(config.database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.connect() as connection:
            await check_schema(connection)
        if command == "bootstrap-admin":
            username = await asyncio.to_thread(input, "Administrator username: ")
            display_name = await asyncio.to_thread(input, "Display name: ")
            password = await asyncio.to_thread(getpass, "New password: ")
            if password != await asyncio.to_thread(getpass, "Repeat password: "):
                raise DomainError("INVALID_PASSWORD", "Passwords do not match.", 422)
            async with sessions.begin() as session:
                await auth.bootstrap_admin(session, username, display_name, password)
            print("Administrator created.")
            return
        username = await asyncio.to_thread(input, "Administrator username: ")
        password = await asyncio.to_thread(getpass, "Administrator password: ")
        if command == "create-inspector":
            new_username = await asyncio.to_thread(input, "Inspector username: ")
            display_name = await asyncio.to_thread(input, "Display name: ")
            new_password = await asyncio.to_thread(getpass, "Initial password: ")
            if new_password != await asyncio.to_thread(getpass, "Repeat password: "):
                raise DomainError("INVALID_PASSWORD", "Passwords do not match.", 422)
        async with sessions.begin() as session:
            credentials = await auth.login(
                session,
                username,
                password,
                services.utc_now_us(),
                config.idle_timeout_us,
                config.absolute_timeout_us,
            )
            if command == "seed-demo":
                await foundation.seed_demo(session, credentials.principal)
                print(
                    "Two labelled synthetic documentation systems are available; no collection configured."
                )
            elif command == "create-inspector":
                await auth.create_user(
                    session, credentials.principal, new_username, display_name, new_password
                )
                print("Inspector created.")
            # Do not retain the CLI's temporary login session.
            from sqlalchemy import delete

            from inspector.persistence.models import AuthSession
            from inspector.security import token_hash

            await session.execute(
                delete(AuthSession).where(AuthSession.token_hash == token_hash(credentials.token))
            )
    finally:
        await engine.dispose()


def migration_ini() -> Path:
    bundled = Path(__file__).parent / "alembic.ini"
    return bundled if bundled.is_file() else Path(__file__).resolve().parents[2] / "alembic.ini"


async def migrate(config_path: Path, username: str, password_file: Path) -> None:
    """Explicit operator job only; serving never calls this function."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    config = parse_config(
        await asyncio.to_thread(config_path.read_bytes),
        {
            "SI_MIGRATION_DB_USERNAME": username,
            "SI_MIGRATION_DB_PASSWORD_FILE": password_file.as_posix(),
        },
        migration=True,
    )
    engine = create_engine(config.database, dedicated=True)
    ini = await asyncio.to_thread(migration_ini)
    try:
        async with migration_guard(engine) as connection:
            from sqlalchemy import text

            version = str(await connection.scalar(text("SELECT VERSION()")))
            if "mariadb" not in version.lower():
                raise ConfigurationError("Explicit migration requires MariaDB.")
            await connection.commit()

            def upgrade(sync_connection: Connection) -> None:
                alembic = AlembicConfig(str(ini))
                alembic.attributes["connection"] = sync_connection
                command.upgrade(alembic, "head")

            await connection.run_sync(upgrade)
            await connection.commit()
        print("Explicit schema migration completed.")
    finally:
        await engine.dispose()


def healthcheck() -> None:
    config = load_config()
    request = Request(
        "http://127.0.0.1:8000/api/v1/health/ready",
        headers={"Host": urlsplit(config.public_origin).netloc},
    )
    with urlopen(request, timeout=5) as response:
        if response.status != 200 or json.load(response).get("status") != "ready":
            raise ConfigurationError("Readiness check failed.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "bootstrap-admin",
            "create-inspector",
            "seed-demo",
            "openapi",
            "db",
            "healthcheck",
        ],
    )
    parser.add_argument("action", nargs="?")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--username")
    parser.add_argument("--password-file", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "db":
            if (
                args.action != "upgrade"
                or not args.config
                or not args.username
                or not args.password_file
            ):
                parser.error("db upgrade requires --config, --username and --password-file")
            asyncio.run(migrate(args.config, args.username, args.password_file))
        elif args.command == "healthcheck":
            healthcheck()
        elif args.command == "openapi":
            if args.output is None:
                parser.error("openapi requires --output")
            schema = create_app().openapi()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        else:
            asyncio.run(provision(args.command))
    except (ConfigurationError, DomainError) as error:
        parser.exit(1, f"{error}\n")
    except Exception:
        parser.exit(
            1,
            "Provisioning unavailable; check configured database/schema and protected server diagnostics.\n",
        )


if __name__ == "__main__":
    main()
