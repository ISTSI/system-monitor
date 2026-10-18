"""Map-only servers must fail before a collection can reach remote access."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from inspector.config import parse_config
from inspector.domain import Principal
from inspector.errors import DomainError
from inspector.history import approved_candidates
from inspector.history_remote import RemoteHistory

ROOT = Path(__file__).resolve().parents[3]


def document():
    value = json.loads((ROOT / "examples/project.example.json").read_text(encoding="utf-8"))
    process = value["processes"][0]
    next(s for s in value["servers"] if s["id"] == process["server_id"])["connection_id"] = None
    return value, process["id"]


def test_synthetic_collection_rejects_map_only_server_before_fixture_read(monkeypatch):
    value, process_id = document()

    def unexpected_manifest(*_args):
        pytest.fail("An unconnected server must be rejected before fixture access.")

    monkeypatch.setattr("inspector.history.local_manifest", unexpected_manifest)
    with pytest.raises(DomainError) as denied:
        approved_candidates(SimpleNamespace(), value, [process_id])
    assert denied.value.code == "SERVER_NOT_CONNECTED" and denied.value.status == 409


async def test_remote_plan_rejects_entire_selection_before_access_or_reservation():
    value, process_id = document()
    config = parse_config((ROOT / "examples/deployment-policy.example.yaml").read_bytes(), {})
    access = SimpleNamespace(prepare=AsyncMock(), watched=AsyncMock())
    remote = RemoteHistory(access, replace(config, ssh_allow_loopback=True))
    connected = next(
        p["id"]
        for p in value["processes"]
        if next(s for s in value["servers"] if s["id"] == p["server_id"])["connection_id"]
        is not None
    )
    with pytest.raises(DomainError) as denied:
        await remote.plan(
            Principal("owner", "inspector", 1),
            value["project"]["id"],
            value["project"]["revision"],
            value,
            [connected, process_id],
            "login",
        )
    assert denied.value.code == "SERVER_NOT_CONNECTED" and denied.value.status == 409
    access.prepare.assert_not_awaited()
    access.watched.assert_not_awaited()
    assert not remote.active
