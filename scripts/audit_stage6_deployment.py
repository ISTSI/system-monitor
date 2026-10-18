"""Independent read-only audit of the authorized local 8445 Stage 06 upgrade."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import ssl
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import local_mariadb as local
import websockets
from websockets.exceptions import InvalidStatus

ROOT = local.ROOT
OUTPUT = ROOT / "verification/stage-6"
TARGET = "system-inspector-local-runtime-stage3-1"
OTHER = "system-inspector-local-runtime-1"
EXPECTED_SCHEMA = "inspector_test_s3_web_317d3a3c4a"
EXPECTED_SECRETS = sorted(
    "/run/secrets/" + name
    for name in (
        "browser_accounts",
        "browser_cert",
        "browser_key",
        "ssh_vault_master",
        "test_db_password",
    )
)

RUNTIME_READ = r"""
import asyncio, json, os, stat
from pathlib import Path
import inspector
from sqlalchemy import text
from inspector.config import load_config
from inspector.database import create_engine, check_runtime_grants
async def run():
    config = load_config()
    assert config.database.name == "inspector_test_s3_web_317d3a3c4a"
    assert config.database.username.startswith("it_app_")
    assert config.database.password_file == "/run/secrets/test_db_password"
    assert os.geteuid() == 10001 and os.getegid() == 10001
    key = Path(config.vault_key_file)
    metadata = key.stat()
    assert not key.is_symlink() and stat.S_ISREG(metadata.st_mode)
    assert metadata.st_uid == 10001 and stat.S_IMODE(metadata.st_mode) in (0o400, 0o600)
    assert metadata.st_size == 32
    capabilities = {line.split(":")[0]: line.split()[1] for line in Path("/proc/1/status").read_text().splitlines() if line.startswith(("CapEff:", "CapBnd:"))}
    assert capabilities == {"CapEff": "0000000000000000", "CapBnd": "0000000000000000"}
    engine = create_engine(config.database)
    try:
        async with engine.connect() as connection:
            await check_runtime_grants(connection)
            grantee = await connection.scalar(text("SELECT CONCAT(QUOTE(SUBSTRING_INDEX(CURRENT_USER(),'@',1)),'@',QUOTE(SUBSTRING_INDEX(CURRENT_USER(),'@',-1)))"))
            privileges = list((await connection.scalars(text("SELECT PRIVILEGE_TYPE FROM information_schema.schema_privileges WHERE GRANTEE=:grantee ORDER BY PRIVILEGE_TYPE"), {"grantee":grantee})).all())
            global_privileges = list((await connection.scalars(text("SELECT PRIVILEGE_TYPE FROM information_schema.user_privileges WHERE GRANTEE=:grantee ORDER BY PRIVILEGE_TYPE"), {"grantee":grantee})).all())
            assert privileges == ["DELETE", "INSERT", "SELECT", "UPDATE"]
            assert global_privileges == ["USAGE"]
            values = {}
            statements = {
                "history_jobs": "SELECT COUNT(*) FROM history_jobs",
                "active_history_jobs": "SELECT COUNT(*) FROM history_jobs WHERE status IN ('queued','planning','collecting','indexing','cancel_requested')",
                "live_sessions": "SELECT COUNT(*) FROM live_sessions",
                "active_live_sessions": "SELECT COUNT(*) FROM live_sessions WHERE status NOT IN ('stopped','failed','interrupted')",
                "live_subscriptions": "SELECT COUNT(*) FROM live_subscriptions",
                "target_action_audits": "SELECT COUNT(*) FROM audit_events WHERE action LIKE 'ssh.%' OR action IN ('collection.create','live.create')"
            }
            for key, statement in statements.items():
                values[key] = await connection.scalar(text(statement))
            print(json.dumps({"schema":config.database.name,"revision":await connection.scalar(text("SELECT version_num FROM alembic_version")),"runtime_schema_privileges":privileges,"runtime_global_privileges":global_privileges,"uid":os.geteuid(),"gid":os.getegid(),"effective_and_bounding_capabilities_zero":True,"vault_key_owner_mode_size_valid":True,"module_file":inspector.__file__,**values}))
    finally:
        await engine.dispose()
asyncio.run(run())
"""


def inspect(name: str) -> dict:
    return json.loads(
        local.run(["docker", "inspect", name], label="Read local deployment metadata")
    )[0]


def get(port: int, path: str) -> bytes:
    stage = "stage2-browser" if port == 8444 else "stage3-browser"
    certificate = ROOT / ".secrets" / stage / "localhost-cert.pem"
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(certificate))),
    )
    with opener.open(f"https://localhost:{port}" + path, timeout=10) as response:
        assert response.status == 200
        return response.read()


async def unauthenticated_websocket() -> dict:
    context = ssl.create_default_context(
        cafile=str(ROOT / ".secrets/stage3-browser/localhost-cert.pem")
    )
    try:
        async with websockets.connect(
            "wss://localhost:8445/api/v1/projects/deployment-audit/live-sessions/not-a-session/stream",
            origin="https://localhost:8445",
            ssl=context,
            open_timeout=5,
            proxy=None,
        ):
            raise AssertionError("An unauthenticated WebSocket was accepted.")
    except InvalidStatus as error:
        assert error.response.status_code == 403
        return {
            "authentication": "none",
            "exact_origin": True,
            "tls_certificate_and_hostname_verified": True,
            "http_upgrade_status": 403,
            "accepted": False,
        }


def runtime_metadata(current: dict) -> dict:
    assert current["State"]["Running"] and current["Config"]["User"] == "10001:10001"
    host = current["HostConfig"]
    assert host["ReadonlyRootfs"] and host["CapDrop"] == ["ALL"] and not host.get("CapAdd")
    assert "no-new-privileges:true" in host["SecurityOpt"]
    assert not host["Privileged"] and host["PidsLimit"] == 128 and host["Memory"] == 536870912
    assert host["PortBindings"] == {"8443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8445"}]}
    command = current["Config"]["Cmd"]
    for flag, value in [
        ("--workers", "1"),
        ("--ws", "websockets"),
        ("--ws-max-size", "16384"),
        ("--ws-max-queue", "16"),
    ]:
        assert command.count(flag) == 1 and command[command.index(flag) + 1] == value
    mounts = {mount["Destination"]: mount for mount in current["Mounts"]}
    secret_mounts = sorted(name for name in mounts if name.startswith("/run/secrets/"))
    assert secret_mounts == EXPECTED_SECRETS
    assert all(not mounts[name]["RW"] for name in secret_mounts)
    assert not mounts["/workspace/backend"]["RW"]
    assert not any("docker.sock" in name or "containerd.sock" in name for name in mounts)
    assert not any(
        "SI_MIGRATION_" in value or value.startswith(("DB_PASSWORD=", "SI_DB_PASSWORD="))
        for value in current["Config"]["Env"]
    )
    return {
        "container_id": current["Id"],
        "started_at": current["State"]["StartedAt"],
        "image": current["Image"],
        "user": "10001:10001",
        "single_asgi_worker": True,
        "read_only_root": True,
        "drop_all_capabilities": True,
        "no_new_privileges": True,
        "pids_limit": host["PidsLimit"],
        "memory_limit_bytes": host["Memory"],
        "published_port": "127.0.0.1:8445",
        "secret_mount_destinations": secret_mounts,
        "migration_or_root_secrets_mounted": False,
        "runtime_raw_password_or_migration_environment": False,
        "docker_socket_mounted": False,
        "backend_snapshot_mount_readonly": True,
        "backend_snapshot": mounts["/workspace/backend"]["Source"],
    }


def verify_installed_wheel(snapshot: str) -> dict:
    expected = json.loads((OUTPUT / "final-artifact-correspondence.json").read_text("utf-8"))
    folder = Path(snapshot).resolve()
    assert folder == (ROOT / ".state/stage6-install/backend").resolve()
    wheel = folder / "dist/system_inspector-0.1.0-py3-none-any.whl"
    checksum = hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert checksum == expected["wheel_sha256"]
    count = 0
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith("inspector/") and not name.endswith("/"):
                assert archive.read(name) == (folder / "src" / name).read_bytes()
                count += 1
    for name, checksum in expected["runtime_sources"].items():
        assert hashlib.sha256((folder / "src" / name).read_bytes()).hexdigest() == checksum
    return {
        "wheel_sha256": expected["wheel_sha256"],
        "packaged_files_verified": count,
        "runtime_module_files_verified": len(expected["runtime_sources"]),
        "assets": expected["assets"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["pre", "post", "post-browser"])
    args = parser.parse_args()
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".cache/docker"))
    local.require_local_docker()
    destination = OUTPUT / f"deployment-audit-{args.phase}.json"
    if destination.exists():
        raise local.SetupError(
            "Existing deployment audit evidence was preserved; no overwrite attempted."
        )
    prior = json.loads((OUTPUT / "retained-installations.json").read_text("utf-8"))
    baseline_other = next(
        item for item in prior["checks"] if item["origin"] == "https://localhost:8444"
    )
    current, other = inspect(TARGET), inspect(OTHER)
    runtime = runtime_metadata(current)
    assert other["Id"] == baseline_other["container_id"] and other["State"]["Running"]
    assert other["State"]["StartedAt"] == baseline_other["started_at"]
    assert (
        other["Image"] == baseline_other["image_id"]
        and other["RestartCount"] == baseline_other["restart_count"]
    )
    get(8444, "/api/v1/health/ready")
    other_index_hash = hashlib.sha256(get(8444, "/")).hexdigest()
    prepared = json.loads((OUTPUT / "deployment-prepared.json").read_text("utf-8"))
    assert other_index_hash == prepared["other_app_index_sha256"]
    historical_other_asset_drift = other_index_hash != baseline_other["index_sha256"]
    get(8445, "/api/v1/health/ready")
    index_hash = hashlib.sha256(get(8445, "/")).hexdigest()
    before = json.loads(
        local.run(
            ["docker", "exec", TARGET, "python", "-c", RUNTIME_READ],
            label="Read serving application DML grants and safe operational counts",
            timeout=30,
        )
    )
    assert before["module_file"] == "/workspace/backend/src/inspector/__init__.py"
    websocket = asyncio.run(unauthenticated_websocket())
    after = json.loads(
        local.run(
            ["docker", "exec", TARGET, "python", "-c", RUNTIME_READ],
            label="Confirm unauthenticated audit started no targets",
            timeout=30,
        )
    )
    assert after == before
    assert (
        before["active_history_jobs"]
        == before["active_live_sessions"]
        == before["live_subscriptions"]
        == 0
    )
    original = local.run(
        ["docker", "image", "inspect", "system-inspector-runner:local", "--format", "{{.Id}}"],
        label="Verify preserved original runner tag",
    ).strip()
    assert (
        original
        == json.loads((OUTPUT / "runner-build.json").read_text("utf-8"))["original_runner_id"]
    )
    fixtures = {
        name: inspect("system-inspector-local-" + name + "-1")["State"]["Status"]
        for name in ("stage5-browser", "stage5-sftp", "stage6-browser", "stage6-sftp")
    }
    assert set(fixtures.values()) == {"exited"}
    package = None
    if args.phase == "pre":
        stage5 = json.loads(
            (ROOT / "verification/stage-5/deployment-installation.json").read_text("utf-8")
        )
        assert runtime["image"] == stage5["image"] and before["revision"] == "0009_live"
        assert index_hash == stage5["package"]["frontend_assets"]["index.html"]
    else:
        old = json.loads((OUTPUT / "deployment-audit-pre.json").read_text("utf-8"))
        assert other_index_hash == old["other_8444"]["index_sha256"]
        if args.phase == "post-browser":
            post = json.loads((OUTPUT / "deployment-audit-post.json").read_text("utf-8"))
            for name in ("container_id", "started_at", "image", "backend_snapshot"):
                assert runtime[name] == post["runtime"][name]
        assert before["revision"] == "0012_offline_analysis"
        expected_image = json.loads((OUTPUT / "runner-build.json").read_text("utf-8"))[
            "stage6_runner_id"
        ]
        assert runtime["image"] == expected_image
        package = verify_installed_wheel(runtime["backend_snapshot"])
        assert index_hash == package["assets"]["index.html"]
        for name in ("history_jobs", "live_sessions", "target_action_audits"):
            assert before[name] == old["database"][name]
    result = {
        "measured_at": datetime.now(UTC).isoformat(),
        "phase": args.phase,
        "read_only": True,
        "target": "https://localhost:8445",
        "tls_readiness": 200,
        "tls_certificate_and_hostname_verified": True,
        "runtime": runtime,
        "database": before,
        "serving_index_sha256": index_hash,
        "package": package,
        "unauthenticated_websocket": websocket,
        "unauthenticated_audit_started_targets": False,
        "other_8444": {
            "container_id_unchanged": True,
            "image_unchanged": True,
            "started_at_unchanged": True,
            "restart_count_unchanged": True,
            "index_sha256": other_index_hash,
            "assets_unchanged_since_deployment_preparation": True,
            "asset_drift_since_earlier_coding_baseline": historical_other_asset_drift,
            "earlier_coding_baseline_index_sha256": baseline_other["index_sha256"],
            "tls_readiness": 200,
        },
        "original_runner_tag_preserved": True,
        "completed_synthetic_fixtures": fixtures,
        "authenticated_requests": 0,
        "state_changing_requests": 0,
        "passed": True,
    }
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"PASS: independent {args.phase}-deployment audit, TLS and unauthenticated WebSocket boundaries verified."
    )


if __name__ == "__main__":
    main()
