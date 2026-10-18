"""Production parser cancellation signals retain bounded workers until exit."""

import asyncio
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from inspector import inventory_parser
from inspector.inventory import InventoryStaging, inventory_work, validate_extensions


@pytest.mark.parametrize(
    "cause", ["request-task", "http-disconnect", "scoped-upload", "raw-removal"]
)
async def test_inventory_worker_cancels_actual_parser_and_drains_before_releasing_slot(
    tmp_path, cause
):
    staging = InventoryStaging(str(tmp_path), None)
    identifier = str(uuid4())
    started, finished, disconnected = threading.Event(), threading.Event(), threading.Event()

    async def is_disconnected():
        return disconnected.is_set()

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(inventory=staging)),
        is_disconnected=is_disconnected,
    )

    def operation(cancelled):
        try:
            started.set()
            deadline = time.monotonic() + 3
            while not cancelled():
                if time.monotonic() > deadline:
                    raise AssertionError("Production cancellation callback was not set.")
                time.sleep(0.005)
            return inventory_parser.parse_inventory("hosts", b"[one]\nnode\n", cancelled=cancelled)
        finally:
            finished.set()

    task = asyncio.create_task(inventory_work(request, "project-a", identifier, operation))
    assert await asyncio.to_thread(started.wait, 2)
    if cause == "request-task":
        task.cancel()
    elif cause == "http-disconnect":
        disconnected.set()
    elif cause == "scoped-upload":
        staging.cancel("project-b", identifier)
        await asyncio.sleep(0.05)
        assert not task.done()
        staging.cancel("project-a", identifier)
    else:
        staging.path(identifier).write_bytes(b"synthetic staging")
        await staging.remove(identifier, project_id="project-a")
        assert not staging.path(identifier).exists()
    if cause == "request-task":
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
    else:
        with pytest.raises(inventory_parser.InventoryParseError) as error:
            await asyncio.wait_for(task, 1)
        assert error.value.code == "IMPORT_CANCELLED"
    assert finished.is_set()
    assert staging.operations == {}


def test_log_source_schema_diagnostic_identifies_effective_file_and_safe_field_only():
    parsed = {
        "hosts": [
            {
                "processes": [
                    {
                        "log_source": {
                            "active_path": "DO_NOT_ECHO_VALUE",
                            "rotated_patterns": [],
                            "archives": [],
                            "parser_id": "parser",
                            "encoding": "utf-8",
                        }
                    }
                ],
                "effective_provenance": {
                    "inspector_processes": {"source": "host_vars/node.yaml", "line": 7}
                },
            }
        ]
    }
    with pytest.raises(inventory_parser.DomainError) as caught:
        validate_extensions(parsed)
    assert caught.value.code == "INVALID_LOG_SOURCE"
    assert "host_vars/node.yaml:7" in caught.value.message
    assert "inspector_processes[0].log_source" in caught.value.message
    assert "DO_NOT_ECHO_VALUE" not in caught.value.message
