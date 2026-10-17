"""Local provisioning safety and credential boundaries without contacting Docker."""

import importlib.util
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("local_mariadb", ROOT / "scripts/local_mariadb.py")
assert SPEC is not None and SPEC.loader is not None
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


@pytest.fixture
def prepared_tree(monkeypatch, tmp_path):
    if setup.os.name != "nt":
        monkeypatch.setattr(setup.os, "getuid", lambda: 10001)
        monkeypatch.setattr(setup.os, "getgid", lambda: 10001)
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    private = tmp_path / "private"
    monkeypatch.setattr(setup, "DEPLOY", deploy)
    monkeypatch.setattr(setup, "SECRET_DIR", private)
    monkeypatch.setattr(setup, "ENV_FILE", deploy / ".env.local")
    monkeypatch.setattr(
        setup, "private_directory", lambda path, **kwargs: path.mkdir(exist_ok=True)
    )
    examples = tmp_path / "examples"
    examples.mkdir()
    (examples / "deployment-policy.example.yaml").write_bytes(
        (ROOT / "examples/deployment-policy.example.yaml").read_bytes()
    )
    monkeypatch.setattr(setup, "ROOT", tmp_path)
    return deploy, private


def test_linux_root_cannot_prepare_a_root_runner(prepared_tree, monkeypatch):
    _, private = prepared_tree
    with monkeypatch.context() as context:
        context.setattr(setup.os, "name", "posix")
        context.setattr(setup.os, "getuid", lambda: 0, raising=False)
        with pytest.raises(setup.SetupError, match="UID 0"):
            setup.prepare("mariadb:11.8.9@sha256:" + "a" * 64)
    assert not private.exists()


def test_prepare_creates_separate_secrets_and_never_rotates_existing_setup(prepared_tree, capsys):
    deploy, private = prepared_tree
    setup.prepare("mariadb:11.8.9@sha256:" + "a" * 64)
    names = (
        "inspector_db_root_password",
        "inspector_db_migration_password",
        "inspector_db_password",
    )
    passwords = [(private / name).read_text().strip() for name in names]
    assert len(set(passwords)) == 3
    assert all(re.fullmatch(r"[a-f0-9]{64}", value) for value in passwords)
    captured = capsys.readouterr().out
    assert all(value not in captured for value in passwords)
    document = yaml.safe_load((deploy / "application.local.yaml").read_text())
    assert document["database"]["host"] == "mariadb"
    assert document["database"]["name"] == "system_inspector"
    assert document["database"]["username"] == "inspector_app"
    assert document["database"]["password_file"] == "/run/secrets/inspector_db_password"
    bootstrap = (private / "bootstrap.sql").read_text()
    assert passwords[2] in bootstrap
    assert "REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'inspector_migrator'@'%';" in bootstrap
    assert (
        "GRANT ALL PRIVILEGES ON `system\\_inspector`.* TO 'inspector_migrator'@'%';" in bootstrap
    )
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON `system\\_inspector`.*" in bootstrap
    assert "ON `system_inspector`" not in bootstrap
    with pytest.raises(setup.SetupError, match="already exists"):
        setup.prepare("mariadb:11.8.9@sha256:" + "b" * 64)
    assert passwords == [(private / name).read_text().strip() for name in names]


@pytest.mark.parametrize(
    "image", ["mariadb:11.8", "mariadb:latest", "other:11.8.9@sha256:" + "a" * 64]
)
def test_prepare_rejects_unpinned_or_nonofficial_images_before_writing(prepared_tree, image):
    _, private = prepared_tree
    with pytest.raises(setup.SetupError, match="official"):
        setup.prepare(image)
    assert not private.exists()


def test_subprocess_failure_never_exposes_sql_password_or_server_diagnostics(monkeypatch):
    sentinel = "password-must-never-appear"
    monkeypatch.setattr(
        setup.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, sentinel, sentinel),
    )
    with pytest.raises(setup.SetupError) as error:
        setup.run(["docker", "compose"], label="Provisioning", data=sentinel)
    assert sentinel not in str(error.value)


def test_existing_test_schema_is_refused_before_any_secrets_or_data_change(
    prepared_tree, monkeypatch
):
    _, private = prepared_tree
    calls = []
    monkeypatch.setattr(setup, "root_sql", lambda statement: calls.append(statement) or "1\n")
    with pytest.raises(setup.SetupError, match="already exists"):
        setup.new_test("existing", execute=False)
    assert len(calls) == 1 and calls[0].startswith("SELECT COUNT(*)")
    assert not private.exists()


def test_root_provisioning_keeps_credentials_out_of_process_arguments(monkeypatch):
    calls = []
    monkeypatch.setattr(setup, "require_local_docker", lambda: None)
    monkeypatch.setattr(setup, "run", lambda argv, **kwargs: calls.append((argv, kwargs)) or "")
    setup.root_sql("SELECT 1;\n")
    argv, options = calls[0]
    assert "--password" not in " ".join(argv)
    assert "shell" not in options
    assert options["data"] == "SELECT 1;\n"
    assert "cat /run/secrets/inspector_db_root_password" in argv[-1]
    assert "--defaults-extra-file" in argv[-1]


def test_remote_docker_host_is_rejected_before_any_docker_operation(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://production.example:2376")
    calls = []
    monkeypatch.setattr(setup, "run", lambda *args, **kwargs: calls.append(args) or "")
    with pytest.raises(setup.SetupError, match="remote DOCKER_HOST"):
        setup.require_local_docker()
    assert calls == []


def test_remote_selected_context_is_rejected_before_compose_mutation(prepared_tree, monkeypatch):
    deploy, _ = prepared_tree
    (deploy / ".env.local").write_text("MARIADB_IMAGE=unused\n")
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setenv("DOCKER_CONTEXT", "remote")
    calls = []
    monkeypatch.setattr(
        setup, "run", lambda argv, **kwargs: calls.append(argv) or '"ssh://production.example"'
    )
    with pytest.raises(setup.SetupError, match="remote Docker context"):
        setup.compose("up", "--detach", "mariadb")
    assert len(calls) == 1
    assert calls[0][:4] == ["docker", "context", "inspect", "remote"]


@pytest.mark.parametrize(
    "endpoint", ["unix:///var/run/docker.sock", "npipe:////./pipe/docker_engine"]
)
def test_local_selected_context_is_accepted(monkeypatch, endpoint):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setattr(setup, "run", lambda *args, **kwargs: setup.json.dumps(endpoint))
    setup.require_local_docker()


def test_new_test_grants_only_its_unique_schema_and_keeps_passwords_private(
    prepared_tree, monkeypatch, capsys
):
    deploy, private = prepared_tree
    calls = []
    monkeypatch.setattr(setup, "root_sql", lambda statement: calls.append(statement) or "0\n")
    setup.new_test("foundation", execute=False)
    assert len(calls) == 2
    provision = calls[1]
    assert "CREATE DATABASE `inspector_test_foundation`" in provision
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON `inspector\\_test\\_foundation`.*" in provision
    assert "GRANT ALL PRIVILEGES ON `inspector\\_test\\_foundation`.*" in provision
    assert "ON `inspector_test_foundation`" not in provision
    assert "ON *.*" not in provision
    output = capsys.readouterr().out
    for path in private.iterdir():
        assert path.read_text().strip() not in output
    override = yaml.safe_load((deploy / "inspector_test_foundation.compose.local.yaml").read_text())
    integration = override["services"]["integration"]
    assert integration["environment"]["SI_TEST_DISPOSABLE_MARIADB"] == "1"
    assert integration["secrets"] == ["test_db_password", "test_db_migration_password"]
    assert "root" not in str(override)


def test_grant_schema_patterns_escape_every_underscore_and_reject_other_pattern_syntax():
    assert setup.grant_schema_pattern("inspector_test_one") == r"inspector\_test\_one"
    for invalid in ("other%", "name`", r"has\slash", "schema.*"):
        with pytest.raises(setup.SetupError, match="Invalid database name"):
            setup.grant_schema_pattern(invalid)


def test_compose_keeps_database_private_and_runtime_credentials_separate():
    compose = yaml.safe_load((ROOT / "deploy/local-mariadb/compose.yaml").read_text())
    services = compose["services"]
    assert "ports" not in services["mariadb"]
    assert compose["networks"]["database"]["internal"] is True
    assert services["runtime"]["secrets"] == ["inspector_db_password"]
    assert services["migrate"]["secrets"] == ["inspector_db_migration_password"]
    for service in services.values():
        assert service["pull_policy"] == "never"
    # A whole-repository mount would give the app access to provisioning secrets.
    assert all(
        ".secrets" not in mount and mount != "../..:/workspace:ro"
        for mount in services["runtime"]["volumes"]
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL generation only")
def test_designated_windows_owner_is_exact_and_survives_later_provisioning(monkeypatch, tmp_path):
    commands = []

    def invoke(argv, **kwargs):
        commands.append(argv)
        if argv[0] == "whoami":
            return '"machine\\sandbox","S-1-5-21-111-1001"\n'
        if kwargs["label"] == "Resolving the designated local Windows owner":
            return "S-1-5-21-222-1001\n"
        return ""

    monkeypatch.setattr(setup, "run", invoke)
    setup.private_directory(tmp_path, windows_owner="DOMAIN\\human")
    assert (tmp_path / ".windows_owner_sid").read_text().strip() == "S-1-5-21-222-1001"
    commands.clear()
    setup.private_directory(tmp_path)
    assert len(commands) == 2  # Current owner lookup and DACL application, no identity switch.
    script = setup.base64.b64decode(commands[-1][-1]).decode("utf-16-le")
    assert "S-1-5-21-111-1001" in script
    assert "S-1-5-21-222-1001" in script
    assert "S-1-5-18" in script
    assert "S-1-5-32-544" in script
    assert "Everyone" not in script
