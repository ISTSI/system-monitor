"""Preserve the existing local app while adding bounded synthetic SSH fixtures."""

import importlib.util
import json
import sys
from pathlib import Path

import asyncssh
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import stage4_local as setup  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "stage4_ssh_fixture", ROOT / "scripts/stage4_ssh_fixture.py"
)
assert SPEC is not None and SPEC.loader is not None
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


@pytest.fixture
def prepared_tree(monkeypatch, tmp_path):
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    state = tmp_path / "state"
    stage3_setup = tmp_path / "stage3-setup.json"
    database = "inspector_test_s3_web_0123456789"
    override = deploy / "stage3-browser.compose.local.yaml"
    application = deploy / f"{database}.local.yaml"
    original_command = ["python", "-m", "uvicorn", "inspector.app:create_app", "--factory"]
    override.write_text(
        yaml.safe_dump(
            {
                "services": {
                    "runtime-stage3": {
                        "command": original_command,
                        "environment": {"SI_LOCAL_HISTORY_DEMO": "1"},
                        "secrets": ["original-secret"],
                    }
                },
                "secrets": {"original-secret": {"file": "/kept/original"}},
            }
        )
    )
    application.write_text(
        yaml.safe_dump(
            {
                "database": {"name": database, "host": "mariadb", "username": "keep-app-account"},
                "deployment": {
                    "public_origin": "https://localhost:8445",
                    "vault_key_file": "/old/unused",
                },
            }
        )
    )
    stage3_setup.write_text(json.dumps({"database": database, "override": str(override)}))
    monkeypatch.setattr(setup, "ROOT", tmp_path)
    monkeypatch.setattr(setup, "DEPLOY", deploy)
    monkeypatch.setattr(setup, "STATE", state)
    monkeypatch.setattr(setup, "PRIVATE", tmp_path / "private")
    monkeypatch.setattr(setup, "STAGE3_SETUP", stage3_setup)
    monkeypatch.setattr(
        setup, "private_directory", lambda path, **kwargs: path.mkdir(exist_ok=True)
    )
    return application, override, original_command


def test_prepare_preserves_schema_accounts_command_and_secret_identity(prepared_tree, capsys):
    application, override, command = prepared_tree
    setup.prepare()
    original = {path.name: path.read_bytes() for path in setup.PRIVATE.iterdir()}
    setup.prepare()
    assert original == {path.name: path.read_bytes() for path in setup.PRIVATE.iterdir()}
    output = capsys.readouterr().out
    assert all(
        value.decode("ascii", errors="ignore").strip() not in output for value in original.values()
    )
    application_value = yaml.safe_load(application.read_text())
    assert application_value["database"] == {
        "name": "inspector_test_s3_web_0123456789",
        "host": "mariadb",
        "username": "keep-app-account",
    }
    assert application_value["deployment"]["public_origin"] == "https://localhost:8445"
    services = yaml.safe_load(override.read_text())
    assert services["secrets"]["original-secret"] == {"file": "/kept/original"}
    runtime = services["services"]["runtime-stage3"]
    assert (
        runtime["command"]
        == ["python", "/workspace/scripts/stage4_local.py", "serve", "--"] + command
    )
    assert runtime["secrets"] == ["original-secret", "ssh_vault_master"]
    assert len(original["vault-master.key"]) == 32
    public = json.loads((setup.STATE / "public-fixture.json").read_text())
    for role in ("target", "jump"):
        endpoint = services["services"]["ssh-" + role]
        assert endpoint["networks"] == ["database"]
        assert "ports" not in endpoint
        assert endpoint["pull_policy"] == "never"
        assert public["endpoints"][role]["fingerprint"].startswith("SHA256:")
        assert "password" not in public["endpoints"][role]


def test_prepare_rejects_unexpected_schema_before_secret_creation(prepared_tree):
    setup.STAGE3_SETUP.write_text(json.dumps({"database": "production", "override": "ignored"}))
    with pytest.raises(setup.SetupError, match="existing Stage 03 test schema"):
        setup.prepare()
    assert not setup.PRIVATE.exists()


@pytest.mark.asyncio
async def test_fixture_auth_readonly_sftp_and_no_exec(tmp_path):
    root = tmp_path / "fixture"
    root.mkdir()
    (root / "synthetic.log").write_text("2026-10-17T12:00:00.000000Z fixture only\n")
    host_key = asyncssh.generate_private_key("ssh-ed25519")
    server = await asyncssh.listen(
        "127.0.0.1",
        0,
        server_factory=lambda: fixture.FixtureServer("reader", "synthetic-password", jump=False),
        server_host_keys=[host_key],
        sftp_factory=lambda channel: fixture.ReadOnlyFixtureSFTP(channel, chroot=str(root)),
        sftp_version=3,
        allow_scp=False,
    )
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_bytes(
        f"[127.0.0.1]:{server.get_port()} ".encode() + host_key.export_public_key()
    )
    connect = {
        "host": "127.0.0.1",
        "port": server.get_port(),
        "username": "reader",
        "known_hosts": str(known_hosts),
        "client_keys": [],
        "agent_path": None,
    }
    try:
        with pytest.raises(asyncssh.PermissionDenied):
            await asyncssh.connect(**connect, password="wrong-password")
        async with asyncssh.connect(**connect, password="synthetic-password") as connection:
            with pytest.raises(asyncssh.ChannelOpenError):
                await connection.run("id")
            with pytest.raises(asyncssh.ChannelOpenError):
                await connection.open_connection("127.0.0.1", 80)
            async with connection.start_sftp_client() as sftp:
                assert await sftp.realpath("/synthetic.log") == "/synthetic.log"
                async with sftp.open("/synthetic.log", "rb") as stream:
                    assert await stream.read() == (root / "synthetic.log").read_bytes()
                with pytest.raises(asyncssh.SFTPPermissionDenied):
                    await sftp.open("/synthetic.log", "wb")
                with pytest.raises(asyncssh.SFTPPermissionDenied):
                    await sftp.rename("/synthetic.log", "/renamed.log")
                with pytest.raises(asyncssh.SFTPPermissionDenied):
                    await sftp.mkdir("/new-directory")
                with pytest.raises(asyncssh.SFTPPermissionDenied):
                    await sftp.remove("/synthetic.log")
                with pytest.raises(asyncssh.SFTPNoSuchFile):
                    await sftp.stat("/../outside")
        assert (root / "synthetic.log").read_text().endswith("fixture only\n")
    finally:
        server.close()
        await server.wait_closed()


def test_jump_forwarding_exact_allowlist():
    jump = fixture.FixtureServer(
        "reader",
        "secret",
        jump=True,
        forwarding_hosts=frozenset({"ssh-target", "172.30.0.42"}),
    )
    assert jump.connection_requested("ssh-target", 8022, "", 0)
    assert jump.connection_requested("172.30.0.42", 8022, "", 0)
    assert not jump.connection_requested("172.30.0.43", 8022, "", 0)
    assert not jump.connection_requested("ssh-target", 22, "", 0)
    assert not jump.connection_requested("mariadb", 3306, "", 0)
    assert not jump.connection_requested("127.0.0.1", 8022, "", 0)
    assert not jump.connection_requested("ssh-target.evil", 8022, "", 0)
