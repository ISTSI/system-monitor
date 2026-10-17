"""Strict browser controls and original-byte recording lifecycle boundaries."""

import asyncio
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from inspector.errors import DomainError
from inspector.live import (
    HelloInput,
    LiveCreateInput,
    LiveFilterInput,
    _append_recording,
    _file_work,
    _restore_recording,
)


def test_live_selection_filter_controls_reject_mass_assignment_and_unknown_processes():
    payload = {
        "project_id": "project",
        "project_revision": 1,
        "workspace_id": "w",
        "process_ids": ["p"],
        "mode": "merged",
        "seed_rows": 12,
        "seed_rows_by_process": {},
        "filter": {"include": [], "exclude": [], "include_mode": "any", "case_sensitive": True},
        "per_process_filters": {},
        "record": False,
    }
    schema = json.loads(
        (Path(__file__).resolve().parents[3] / "contracts/live-request.schema.json").read_text(
            "utf-8"
        )
    )
    Draft202012Validator(schema).validate(payload)
    accepted = LiveCreateInput.model_validate(payload)
    assert accepted.project_id == "project" and accepted.requested_rows == 12
    assert accepted.model_dump(by_alias=True) == payload
    with pytest.raises(ValidationError, match="Select each process once"):
        LiveCreateInput.model_validate({**payload, "process_ids": ["p", "p"]})
    with pytest.raises(ValidationError):
        LiveCreateInput.model_validate({**payload, "owner_user_id": "forged"})
    with pytest.raises(ValidationError):
        LiveCreateInput.model_validate({**payload, "per_process_filters": {"other": {}}})
    with pytest.raises(ValidationError):
        LiveFilterInput(workspace_id="w", lease_revision=0, expected_filter_version=1)
    with pytest.raises(ValidationError):
        LiveCreateInput.model_validate({**payload, "seed_rows": 501})
    with pytest.raises(ValidationError):
        HelloInput(csrf_token="x", lease_revision=1, command="ignored")


def test_recording_preserves_exact_bytes_and_restores_uncommitted_append(tmp_path):
    path = tmp_path / "historical" / "namespace" / "job" / "capture"
    original = [b"2026-10-17T11:00:00Z STRASSE\r\n", "2026-10-17T11:00:01Z Straße\n".encode()]
    _append_recording(path, original, 0)
    previous = path.read_bytes()
    assert previous == b"".join(original)
    _append_recording(path, [b"not committed\n"], len(previous))
    _restore_recording(path, len(previous))
    assert path.read_bytes() == previous
    with pytest.raises(DomainError, match="size changed"):
        _append_recording(path, [b"must not write\n"], 0)
    assert path.read_bytes() == previous


@pytest.mark.asyncio
async def test_cancelled_file_operation_finishes_before_rollback(tmp_path):
    import threading

    entered = threading.Event()
    release = threading.Event()
    path = tmp_path / "capture"

    def writer():
        entered.set()
        assert release.wait(3)
        path.write_bytes(b"finished")

    task = asyncio.create_task(_file_work(writer))
    await asyncio.to_thread(entered.wait, 3)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert path.read_bytes() == b"finished"
