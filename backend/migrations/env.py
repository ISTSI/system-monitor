"""Explicit async MariaDB migrations, separate from the serving application."""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from inspector.config import load_config
from inspector.database import create_engine, migration_guard
from inspector.persistence import (
    bundle_models,  # noqa: F401
    investigation_models,  # noqa: F401
)
from inspector.persistence.models import Base


def configure_and_run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    deployment = load_config(migration=True)
    engine = create_engine(deployment.database, dedicated=True)
    try:
        async with migration_guard(engine) as connection:
            await connection.run_sync(configure_and_run)
            await connection.commit()
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError(
        "Offline migration execution is disabled; an explicitly configured disposable "
        "or operator-approved MariaDB endpoint and migration lock are required."
    )
elif context.config.attributes.get("connection") is not None:
    # Explicit migration tools can share a validated connection and its held
    # migration lock. The serving application never invokes this entry point.
    configure_and_run(context.config.attributes["connection"])
else:
    asyncio.run(run_online())
