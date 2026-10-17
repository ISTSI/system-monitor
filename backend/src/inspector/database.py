"""MariaDB-only connections and dedicated process/migration locks."""

import asyncio
import hashlib
import re
import sys
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from inspector.config import DatabaseConfig, read_secret

SCHEMA_REVISION = "0002_foundation_preferences"


def validate_runtime_grants(grants: list[str], database: str) -> None:
    """Accept only exact-schema DML; never include authentication text in errors."""
    required = {"SELECT", "INSERT", "UPDATE", "DELETE"}
    granted: set[str] = set()
    exact_scope = "`" + database.replace("_", r"\_") + "`.*"
    for grant in grants:
        match = re.match(r"^GRANT (.+?) ON (.+?) TO ", grant)
        if match is None or " WITH GRANT OPTION" in grant:
            raise RuntimeError(
                "Runtime database account must have exact-schema DML-only privileges."
            )
        permissions = {item.strip() for item in match[1].split(",")}
        if permissions == {"USAGE"} and match[2] == "*.*":
            continue
        if match[2] != exact_scope or not permissions or not permissions <= required:
            raise RuntimeError(
                "Runtime database account must have exact-schema DML-only privileges."
            )
        granted.update(permissions)
    if granted != required:
        raise RuntimeError("Runtime database account must have exact-schema DML-only privileges.")


async def check_runtime_grants(connection: AsyncConnection) -> None:
    rows = (await connection.execute(text("SHOW GRANTS FOR CURRENT_USER"))).scalars().all()
    validate_runtime_grants([str(row) for row in rows], str(connection.engine.url.database))


def create_engine(config: DatabaseConfig, *, dedicated: bool = False) -> AsyncEngine:
    secret = read_secret(config.password_file)
    url = URL.create(
        "mysql+asyncmy",
        username=config.username,
        password=secret,
        host=config.host,
        port=config.port,
        database=config.name,
        query={"charset": "utf8mb4"},
    )
    options: dict[str, Any] = {
        "connect_args": {
            "connect_timeout": config.connect_timeout_seconds,
            "read_timeout": config.connect_timeout_seconds,
            "password": secret.encode("utf-8"),
            "ssl": config.ssl_context(),
        },
        "hide_parameters": True,
        "echo": False,
        "isolation_level": "READ COMMITTED",
    }
    if dedicated:
        options["poolclass"] = NullPool
    else:
        options.update(
            pool_size=config.pool["size"],
            max_overflow=config.pool["max_overflow"],
            pool_timeout=config.pool["timeout_seconds"],
            pool_recycle=config.pool["recycle_seconds"],
            pool_pre_ping=True,
        )
    return create_async_engine(url, **options)


async def check_schema(connection: AsyncConnection) -> None:
    version = str(await connection.scalar(text("SELECT VERSION()")))
    if "mariadb" not in version.lower():
        raise RuntimeError("A supported MariaDB server is required.")
    revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
    if revision != SCHEMA_REVISION:
        raise RuntimeError("Schema mismatch; run the explicit migration job before serving.")


def _lock_name(connection: AsyncConnection, kind: str) -> str:
    # MariaDB named locks are server-wide; namespace by the configured database.
    database = str(connection.engine.url.database)
    return "inspector:" + hashlib.sha256(database.encode()).hexdigest()[:32] + ":" + kind


async def _acquire(connection: AsyncConnection, name: str) -> None:
    if await connection.scalar(text("SELECT GET_LOCK(:name, 0)"), {"name": name}) != 1:
        raise RuntimeError("Another migration or serving process holds the database lock.")
    await connection.commit()


async def _release(connection: AsyncConnection, name: str) -> None:
    if connection.in_transaction():
        await connection.rollback()
    await connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})
    await connection.commit()


@asynccontextmanager
async def migration_guard(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as connection:
        migration_name = _lock_name(connection, "migration")
        await _acquire(connection, migration_name)
        try:
            owner = await connection.scalar(
                text("SELECT IS_USED_LOCK(:name)"), {"name": _lock_name(connection, "supervisor")}
            )
            await connection.commit()
            if owner is not None:
                raise RuntimeError("Stop the serving supervisor before running migrations.")
            yield connection
        finally:
            await _release(connection, migration_name)


class Supervisor:
    def __init__(self, connection: AsyncConnection) -> None:
        self.connection = connection
        self.connection_id: int | None = None
        self.failed = False
        self._probe_lock = asyncio.Lock()

    async def healthy(self) -> bool:
        async with self._probe_lock:
            return await self._healthy_locked()

    async def _healthy_locked(self) -> bool:
        if self.failed:
            return False
        try:
            owner = await self.connection.scalar(
                text("SELECT IS_USED_LOCK(:name)"),
                {"name": _lock_name(self.connection, "supervisor")},
            )
            await self.connection.commit()
            if owner != self.connection_id:
                self.failed = True
        except Exception:
            # Never silently reacquire a lost lock; a controlled restart is required.
            self.failed = True
        return not self.failed


@asynccontextmanager
async def supervisor_guard(engine: AsyncEngine) -> AsyncIterator[Supervisor]:
    async with engine.connect() as connection:
        migration_name = _lock_name(connection, "migration")
        supervisor_name = _lock_name(connection, "supervisor")
        await _acquire(connection, migration_name)
        try:
            await _acquire(connection, supervisor_name)
        finally:
            await _release(connection, migration_name)
        try:
            await check_schema(connection)
            await check_runtime_grants(connection)
            instance = Supervisor(connection)
            instance.connection_id = await connection.scalar(text("SELECT CONNECTION_ID()"))
            await connection.commit()
            yield instance
        finally:
            await _release(connection, supervisor_name)


@contextmanager
def local_state_lock(state_dir: str) -> Iterator[None]:
    path = Path(state_dir)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (path / "supervisor.lock").open("a+b") as stream:
        if not stream.seek(0, 2):
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
