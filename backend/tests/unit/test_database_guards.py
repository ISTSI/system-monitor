import asyncio
import importlib.util
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import OperationalError

from inspector.database import Supervisor, _release, local_state_lock

ROOT = Path(__file__).resolve().parents[3]


async def test_concurrent_supervisor_probes_serialize_and_loss_never_reacquires():
    class ProbeConnection:
        engine = SimpleNamespace(url=SimpleNamespace(database="inspector_test_unit"))
        closed = invalidated = False

        def __init__(self):
            self.busy = False
            self.calls = 0
            self.owner = 73

        async def scalar(self, *_args):
            assert not self.busy, "concurrent driver read"
            self.busy = True
            self.calls += 1
            await asyncio.sleep(0)
            self.busy = False
            return self.owner

        async def commit(self):
            self.busy = False

    connection = ProbeConnection()
    supervisor = Supervisor(connection)
    supervisor.connection_id = 73
    assert await asyncio.gather(*[supervisor.healthy() for _ in range(20)]) == [True] * 20
    connection.owner = 74
    assert not await supervisor.healthy()
    connection.owner = 73
    calls = connection.calls
    assert not await supervisor.healthy()
    assert connection.calls == calls


async def test_cancelled_probe_waiter_does_not_cancel_shared_driver_operation():
    started, release, driver_cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class ProbeConnection:
        engine = SimpleNamespace(url=SimpleNamespace(database="inspector_test_unit"))
        closed = invalidated = False
        calls = commits = 0

        async def scalar(self, statement, *_args):
            self.calls += 1
            if "IS_USED_LOCK" in str(statement):
                started.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    self.invalidated = True
                    driver_cancelled.set()
                    raise
            return 73

        async def commit(self):
            self.commits += 1

    connection = ProbeConnection()
    supervisor = Supervisor(connection)
    supervisor.connection_id = 73
    first = asyncio.create_task(supervisor.healthy())
    await asyncio.wait_for(started.wait(), 1)
    second = asyncio.create_task(supervisor.healthy())
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert await asyncio.wait_for(second, 1)
    assert not driver_cancelled.is_set()
    assert connection.calls == 2 and connection.commits == 1
    assert not supervisor.failed and not connection.invalidated
    await supervisor.drain()
    assert not await supervisor.healthy()  # Closing never starts another query.
    assert connection.calls == 2


async def test_probe_has_its_own_timeout_and_does_not_reconnect_after_failure(monkeypatch):
    from inspector import database

    monkeypatch.setattr(database, "_PROBE_TIMEOUT_SECONDS", 0.03)

    class ProbeConnection:
        engine = SimpleNamespace(url=SimpleNamespace(database="inspector_test_unit"))
        closed = invalidated = False
        calls = 0

        async def scalar(self, *_args):
            self.calls += 1
            try:
                await asyncio.Event().wait()
            finally:
                self.invalidated = True

    connection = ProbeConnection()
    supervisor = Supervisor(connection)
    supervisor.connection_id = 73
    assert not await asyncio.wait_for(supervisor.healthy(), 0.5)
    assert supervisor.failed and connection.invalidated
    assert not await supervisor.healthy()
    assert connection.calls == 1
    await supervisor.drain()
    assert supervisor._probe_task.done()


async def test_shutdown_drains_probe_after_its_request_was_cancelled():
    started, release = asyncio.Event(), asyncio.Event()

    class ProbeConnection:
        engine = SimpleNamespace(url=SimpleNamespace(database="inspector_test_unit"))
        closed = invalidated = False

        async def scalar(self, *_args):
            started.set()
            await release.wait()
            return 73

        async def commit(self):
            pass

    supervisor = Supervisor(ProbeConnection())
    supervisor.connection_id = 73
    caller = asyncio.create_task(supervisor.healthy())
    await asyncio.wait_for(started.wait(), 1)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    closing = asyncio.create_task(supervisor.drain())
    await asyncio.sleep(0)
    assert not closing.done()
    release.set()
    await asyncio.wait_for(closing, 1)
    assert supervisor._probe_task.done() and not supervisor.failed


@pytest.mark.parametrize("invalidated,closed", [(True, False), (False, True)])
async def test_invalidated_or_closed_lock_connection_is_never_queried_or_released(
    invalidated, closed
):
    class Connection:
        async def scalar(self, *_args):
            pytest.fail("Lost dedicated connection was silently reconnected")

    connection = Connection()
    connection.invalidated, connection.closed = invalidated, closed
    supervisor = Supervisor(connection)
    supervisor.connection_id = 73
    assert not await supervisor.healthy()
    await _release(connection, "synthetic-supervisor-lock")


async def test_changed_physical_connection_id_cannot_reuse_original_lock_owner():
    class Connection:
        engine = SimpleNamespace(url=SimpleNamespace(database="inspector_test_unit"))
        closed = invalidated = False
        calls = 0

        async def scalar(self, statement, *_args):
            self.calls += 1
            return 73 if "IS_USED_LOCK" in str(statement) else 74

        async def commit(self):
            pass

    connection = Connection()
    supervisor = Supervisor(connection)
    supervisor.connection_id = 73
    assert not await supervisor.healthy()
    assert supervisor.failed
    assert not await supervisor.healthy() and connection.calls == 2


def test_local_lock_excludes_second_process_handle_and_can_reopen(tmp_path):
    with local_state_lock(str(tmp_path)):
        with pytest.raises(OSError), local_state_lock(str(tmp_path)):
            pass
    with local_state_lock(str(tmp_path)):
        pass


def test_fresh_migration_compiles_mariadb_sql_without_execution():
    path = Path(__file__).resolve().parents[2] / "migrations/versions/0001_scoped_foundation.py"
    spec = importlib.util.spec_from_file_location("initial_revision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="mysql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        module.upgrade()
    sql = output.getvalue()
    assert (
        "FOREIGN KEY(project_id, opened_revision) REFERENCES project_revisions (project_id, revision)"
        in sql
    )
    assert "INSERT INTO security_state" in sql
    assert "DROP TABLE" not in sql
    assert sql.count("CREATE TABLE") == 7


async def test_commit_failure_is_reported_before_success_response():
    import httpx

    from inspector import services
    from inspector.app import authenticated, create_app, transaction
    from inspector.config import parse_config
    from inspector.domain import Principal

    config = parse_config((ROOT / "examples/deployment-policy.example.yaml").read_bytes(), {})
    app = create_app(config)

    class Healthy:
        async def healthy(self):
            return True

    app.state.supervisor = Healthy()

    async def failed_commit():
        yield None
        raise OperationalError("synthetic commit", {}, RuntimeError("synthetic failure"))

    async def actor():
        return Principal("test-owner", "inspector", 1)

    # Only the API response/transaction boundary is under test; no DB is emulated.
    app.dependency_overrides[transaction] = failed_commit
    app.dependency_overrides[authenticated] = actor
    original = services.list_projects

    async def empty_catalogue(*_args, **_kwargs):
        return {"items": []}

    services.list_projects = empty_catalogue
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=config.public_origin
        ) as client:
            response = await client.get("/api/v1/projects")
        assert response.status_code == 503
        assert "synthetic failure" not in response.text
    finally:
        services.list_projects = original
