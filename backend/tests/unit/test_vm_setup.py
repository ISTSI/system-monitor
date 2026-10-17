import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_refuses_remote_host_before_reading_secret(monkeypatch, tmp_path):
    module = load("probe_mariadb")

    def no_secret(_path):
        pytest.fail("Secret must not be read for a remote endpoint")

    monkeypatch.setattr(module, "read_secret", no_secret)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "probe",
            "--host",
            "192.0.2.1",
            "--port",
            "3306",
            "--database",
            "synthetic",
            "--username",
            "synthetic",
            "--password-file",
            str(tmp_path / "secret"),
            "--output",
            str(tmp_path / "out.json"),
        ],
    )
    with pytest.raises(SystemExit) as refused:
        module.main()
    assert refused.value.code == 2
    assert not (tmp_path / "out.json").exists()


@pytest.mark.parametrize(
    "username", ["root", "mysql", "mariadb", "inspector_migrator", "system-monitor", "bad'account"]
)
def test_bad_runtime_request_never_creates_credentials(monkeypatch, tmp_path, username):
    module = load("vm_mariadb")
    config = tmp_path / "migration.local.yaml"
    config.write_bytes(b"synthetic config")
    secret_dir = tmp_path / "private"
    monkeypatch.setattr(module, "CONFIG", config)
    monkeypatch.setattr(module, "SECRET_DIR", secret_dir)
    monkeypatch.setattr(
        module,
        "parse_config",
        lambda *_args, **_kwargs: SimpleNamespace(
            database=SimpleNamespace(username="system-monitor", name="system-monitor")
        ),
    )
    with pytest.raises(module.SetupError):
        module.runtime_request(SimpleNamespace(username=username))
    assert not secret_dir.exists()


async def test_non_mariadb_server_is_rejected_before_any_ddl(monkeypatch, tmp_path):
    from contextlib import asynccontextmanager

    module = load("vm_mariadb")
    config = tmp_path / "migration.local.yaml"
    config.write_bytes(b"synthetic config")
    monkeypatch.setattr(module, "CONFIG", config)
    monkeypatch.setattr(
        module,
        "parse_config",
        lambda *_args, **_kwargs: SimpleNamespace(
            database=SimpleNamespace(topology="ssh_tunnel", name="system-monitor")
        ),
    )
    calls = []

    class Engine:
        async def dispose(self):
            calls.append("disposed")

    class Connection:
        async def scalar(self, statement):
            calls.append(str(statement))
            return "8.4-synthetic-non-Maria-server"

        async def run_sync(self, _operation):
            pytest.fail("DDL must not be attempted against the wrong database product")

    @asynccontextmanager
    async def guard(_engine):
        yield Connection()

    monkeypatch.setattr(module, "create_engine", lambda *_args, **_kwargs: Engine())
    monkeypatch.setattr(module, "migration_guard", guard)
    with pytest.raises(module.SetupError, match="must be MariaDB"):
        await module.initialize(
            SimpleNamespace(expected_database="system-monitor", output=tmp_path / "out.json")
        )
    assert calls == ["SELECT VERSION()", "disposed"]
    assert not (tmp_path / "out.json").exists()
