"""MariaDB-only connections and dedicated process/migration locks."""

import asyncio
import hashlib
import logging
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

SCHEMA_REVISION = "0014_languages"
_PROBE_TIMEOUT_SECONDS = 1.0
_DRAIN_TIMEOUT_SECONDS = 1.25
_LOGGER = logging.getLogger(__name__)


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
    # A named lock belongs to its original physical connection. Executing after
    # invalidation can reconnect and must never be mistaken for lock ownership.
    if connection.closed or connection.invalidated:
        return
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
        self._closing = False
        self._probe_task: asyncio.Task[bool] | None = None
        self.last_failure_phase: str | None = None
        self.last_failure_code: str | None = None
        self._probe_phase = "idle"

    async def healthy(self) -> bool:
        if self.failed or self._closing:
            return False
        if self.connection.closed or self.connection.invalidated:
            self.failed = True
            return False
        if self._probe_task is None or self._probe_task.done():
            # One independently bounded operation owns the dedicated connection.
            # A caller may time out or cancel without interrupting driver I/O and
            # poisoning the supervisor used by every other request/job.
            self._probe_task = asyncio.create_task(self._probe())
        return await asyncio.shield(self._probe_task)

    async def _probe(self) -> bool:
        began = asyncio.get_running_loop().time()
        try:
            async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
                return await self._healthy_locked()
        except (Exception, asyncio.CancelledError) as error:
            self.failed = True
            self.last_failure_phase = self._probe_phase
            self.last_failure_code = type(error).__name__
            if not self._closing:
                _LOGGER.warning(
                    "Persistence supervisor probe failed closed: phase=%s error=%s elapsed_seconds=%.3f",
                    self._probe_phase,
                    type(error).__name__,
                    asyncio.get_running_loop().time() - began,
                )
            return False

    async def _healthy_locked(self) -> bool:
        if self.failed:
            return False
        try:
            self._probe_phase = "lock_owner"
            owner = await self.connection.scalar(
                text("SELECT IS_USED_LOCK(:name)"),
                {"name": _lock_name(self.connection, "supervisor")},
            )
            self._probe_phase = "connection_identity"
            connection_id = await self.connection.scalar(text("SELECT CONNECTION_ID()"))
            self._probe_phase = "commit"
            await self.connection.commit()
            if owner != self.connection_id or connection_id != self.connection_id:
                self.failed = True
                self.last_failure_phase = "ownership"
                self.last_failure_code = "LOCK_OWNERSHIP_LOST"
        except Exception as error:
            # Never silently reacquire a lost lock; a controlled restart is required.
            self.failed = True
            self.last_failure_phase = self._probe_phase
            self.last_failure_code = type(error).__name__
            _LOGGER.warning(
                "Persistence supervisor query failed closed: phase=%s error=%s",
                self._probe_phase,
                type(error).__name__,
            )
        return not self.failed

    async def drain(self) -> None:
        """Stop new probes and finish the shared driver operation before close."""
        self._closing = True
        task = self._probe_task
        if task is None:
            return
        done, _ = await asyncio.wait((task,), timeout=_DRAIN_TIMEOUT_SECONDS)
        if task not in done:
            self.failed = True
            task.cancel()
            done, _ = await asyncio.wait((task,), timeout=0.25)
            if task not in done:
                # A driver which ignores cancellation cannot authorize further
                # work. Invalidation closes this connection without reacquiring.
                try:
                    async with asyncio.timeout(0.25):
                        await self.connection.invalidate()
                except Exception:
                    pass
        if task.done() and not task.cancelled():
            task.exception()  # Retrieve defensive unexpected task failures.


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
        instance: Supervisor | None = None
        try:
            await check_schema(connection)
            await check_runtime_grants(connection)
            instance = Supervisor(connection)
            instance.connection_id = await connection.scalar(text("SELECT CONNECTION_ID()"))
            await connection.commit()
            yield instance
        finally:
            if instance is not None:
                await instance.drain()
            if instance is None or not instance.failed:
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
