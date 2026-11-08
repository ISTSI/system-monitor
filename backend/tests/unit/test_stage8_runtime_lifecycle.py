"""Retiring synthetic release stacks releases routes without deleting data."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def fixture_runtime(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "stage8_runtime_lifecycle", ROOT / "scripts/stage8_runtime.py"
    )
    assert spec is not None and spec.loader is not None
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    state = tmp_path / "state"
    private = tmp_path / "private"
    state.mkdir()
    private.mkdir()
    monkeypatch.setattr(runtime, "STATE", state)
    monkeypatch.setattr(runtime, "PRIVATE", private)
    stack = "inspector-s8-0123456789"
    saved = {
        "stack": stack,
        "images": {"app": "synthetic-fixture-image"},
        "release": "retained-release",
    }
    (state / "setup.json").write_text(json.dumps(saved), encoding="utf-8")
    document = {
        "name": stack,
        "services": {"mariadb": {"volumes": ["mariadb-data:/var/lib/mysql"]}},
        "volumes": {"mariadb-data": {}, "app-state": {}, "log-cache": {}},
    }
    (private / "compose.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
    (private / "backup-source-setup.json").write_text(json.dumps(saved), encoding="utf-8")
    (private / "recovery").mkdir()
    for name in ("vault.key", "recovery/database.sql", "retained-receipt.json"):
        (private / name).write_bytes(b"retained synthetic data")
    return runtime, saved


def test_terminal_stop_removes_only_own_routes_without_data_or_image_flags(
    fixture_runtime, monkeypatch
):
    runtime, saved = fixture_runtime
    original_files = {
        path.relative_to(runtime.PRIVATE): path.read_bytes()
        for path in runtime.PRIVATE.rglob("*")
        if path.is_file()
    }
    commands = []
    monkeypatch.setattr(runtime, "run", lambda argv, **kwargs: commands.append(argv) or b"")
    monkeypatch.setattr(runtime.local, "require_local_docker", lambda: None)
    monkeypatch.setattr(sys, "argv", ["stage8_runtime.py", "stop"])

    assert runtime.main() == 0

    assert commands == [
        [
            "docker",
            "compose",
            "--project-name",
            saved["stack"],
            "--project-directory",
            str(runtime.PRIVATE),
            "-f",
            str(runtime.PRIVATE / "compose.yaml"),
            "down",
            "--timeout",
            "60",
        ]
    ]
    # No --volumes/-v, --rmi, --remove-orphans, prune, production stack or
    # deployment entrypoint is permitted by this entire command assertion.
    assert {
        path.relative_to(runtime.PRIVATE): path.read_bytes()
        for path in runtime.PRIVATE.rglob("*")
        if path.is_file()
    } == original_files
    assert runtime.setup() == saved


def test_fresh_attempt_releases_old_project_before_selecting_new_identity(
    fixture_runtime, monkeypatch
):
    runtime, saved = fixture_runtime
    seen = []

    def command(argv, **kwargs):
        seen.append((argv, runtime.setup()["stack"]))
        return b""

    monkeypatch.setattr(runtime, "run", command)
    monkeypatch.setattr(runtime.secrets, "token_hex", lambda size: "abcdef0123")
    runtime.fresh_attempt()

    assert len(seen) == 1
    assert seen[0][1] == saved["stack"]
    assert seen[0][0][-3:] == ["down", "--timeout", "60"]
    assert seen[0][0][seen[0][0].index("--project-name") + 1] == saved["stack"]
    assert runtime.setup()["stack"] == "inspector-s8-abcdef0123"
    assert json.loads((runtime.STATE / (saved["stack"] + ".json")).read_text()) == saved
    assert (runtime.PRIVATE / "recovery/database.sql").read_bytes() == b"retained synthetic data"


def test_failed_release_does_not_abandon_original_fixture_identity(fixture_runtime, monkeypatch):
    runtime, saved = fixture_runtime

    def rejected(argv, **kwargs):
        raise RuntimeError("Synthetic teardown failure")

    monkeypatch.setattr(runtime, "run", rejected)
    with pytest.raises(RuntimeError, match="teardown failure"):
        runtime.fresh_attempt()

    assert runtime.setup() == saved
    assert not (runtime.STATE / (saved["stack"] + ".json")).exists()


def test_restore_releases_source_routes_before_creating_restored_copy(fixture_runtime, monkeypatch):
    runtime, saved = fixture_runtime
    seen = []

    class PreparedCopyBoundary(Exception):
        pass

    def command(argv, **kwargs):
        seen.append((argv, runtime.setup()["stack"]))
        if argv[:2] == ["docker", "run"]:
            raise PreparedCopyBoundary
        return b""

    monkeypatch.setattr(runtime, "run", command)
    monkeypatch.setattr(runtime.secrets, "token_hex", lambda size: "abcdef0123")
    with pytest.raises(PreparedCopyBoundary):
        runtime.restore_runtime()

    assert seen[0][1] == saved["stack"]
    assert seen[0][0][-3:] == ["down", "--timeout", "60"]
    assert seen[1][1] == "inspector-s8-abcdef0123"
    assert json.loads((runtime.PRIVATE / "backup-source-setup.json").read_text()) == saved
    assert (runtime.PRIVATE / "recovery/database.sql").read_bytes() == b"retained synthetic data"


@pytest.mark.parametrize("stack", ["system-inspector-local", "inspector-s8-short"])
def test_retirement_rejects_non_fixture_stack_before_any_docker_operation(
    fixture_runtime, monkeypatch, stack
):
    runtime, saved = fixture_runtime
    (runtime.STATE / "setup.json").write_text(json.dumps({**saved, "stack": stack}))
    monkeypatch.setattr(
        runtime, "run", lambda *args, **kwargs: pytest.fail("Unexpected Docker operation")
    )
    with pytest.raises(ValueError, match="fixture stack identity"):
        runtime.stop_fixture()
