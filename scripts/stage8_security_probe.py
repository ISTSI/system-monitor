"""Read-only privilege, egress and grant checks of the isolated release fixture."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import local_mariadb as local

ROOT = Path(__file__).resolve().parents[1]


def run(argv: list[str], *, allowed_failure=False, timeout=30):
    result = subprocess.run(
        argv, cwd=ROOT, input=b"", capture_output=True, timeout=timeout, check=False
    )
    if result.returncode and not allowed_failure:
        raise RuntimeError("Read-only qualification command failed; no private output displayed")
    return result


def main() -> int:
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".cache/docker"))
    local.require_local_docker()
    setup = json.loads((ROOT / ".state/stage8-runtime/setup.json").read_text("utf-8"))
    stack = setup["stack"]
    if not stack.startswith("inspector-s8-") or len(stack) != 23:
        raise ValueError("Unexpected fixture stack identity")
    ids = (
        run(
            [
                "docker",
                "ps",
                "--filter",
                "label=com.docker.compose.project=" + stack,
                "--format",
                "{{.ID}}",
            ]
        )
        .stdout.decode()
        .split()
    )
    rows = json.loads(run(["docker", "inspect", *ids]).stdout)
    containers = {row["Config"]["Labels"]["com.docker.compose.service"]: row for row in rows}
    receipt = {"stack": stack, "read_only_checks": True, "services": {}, "network_checks": {}}
    for role in ("app", "proxy"):
        row = containers[role]
        uid = run(["docker", "exec", row["Id"], "id", "-u"]).stdout.decode().strip()
        status = run(["docker", "exec", row["Id"], "cat", "/proc/self/status"]).stdout.decode()
        fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
        assert uid == "10001"
        assert int(fields["CapEff"].strip(), 16) == 0 and int(fields["NoNewPrivs"].strip()) == 1
        assert row["HostConfig"]["ReadonlyRootfs"]
        assert row["HostConfig"]["CapDrop"] == ["ALL"]
        destinations = [mount["Destination"] for mount in row["Mounts"]]
        assert not any(
            "docker.sock" in path
            or "podman.sock" in path
            or "db_root" in path
            or "migration_password" in path
            for path in destinations
        )
        receipt["services"][role] = dict(
            image_id=row["Image"],
            uid=int(uid),
            effective_capabilities=fields["CapEff"].strip(),
            no_new_privileges=True,
            root_filesystem_readonly=True,
            secret_and_socket_boundaries_verified=True,
        )
        networks = {}
        for name in row["NetworkSettings"]["Networks"]:
            network = json.loads(run(["docker", "network", "inspect", name]).stdout)[0]
            networks[name] = dict(internal=network["Internal"], options=network["Options"])
        receipt["network_checks"][role] = networks
    socket_program = (
        "import json,socket,time\n"
        "started=time.monotonic()\n"
        "try:\n"
        " connection=socket.create_connection(('1.1.1.1',443),timeout=1.5)\n"
        " connection.close();result={'tcp_connected':True}\n"
        "except OSError as error: result={'tcp_connected':False,'error_type':type(error).__name__,'errno':error.errno}\n"
        "result['elapsed_seconds']=round(time.monotonic()-started,3)\n"
        "print(json.dumps(result))\n"
    )
    result = json.loads(
        run(
            ["docker", "exec", containers["app"]["Id"], "python", "-c", socket_program], timeout=10
        ).stdout
    )
    assert result["tcp_connected"] is False
    receipt["app_public_tcp_probe"] = result
    # BusyBox zero-I/O mode opens TCP without sending application data.
    started = time.monotonic()
    proxy = run(
        [
            "docker",
            "exec",
            containers["proxy"]["Id"],
            "busybox",
            "nc",
            "-n",
            "-z",
            "-w",
            "2",
            "1.1.1.1",
            "443",
        ],
        allowed_failure=True,
        timeout=10,
    )
    assert proxy.returncode == 1, (
        "Proxy public egress was available or zero-I/O probe was unavailable"
    )
    receipt["proxy_public_tcp_probe"] = dict(
        tcp_connected=False,
        zero_io_probe_exit_code=proxy.returncode,
        elapsed_seconds=round(time.monotonic() - started, 3),
    )
    private = ROOT / ".secrets/stage8-runtime"
    grant_program = (
        "import asyncio,json,pathlib\n"
        "from sqlalchemy import text\n"
        "from inspector.config import parse_config\n"
        "from inspector.database import create_engine\n"
        "async def verify():\n"
        " c=parse_config(pathlib.Path('/etc/system-inspector/application.yaml').read_bytes(),{'SI_MIGRATION_DB_USERNAME':'inspector_migrator','SI_MIGRATION_DB_PASSWORD_FILE':'/run/secrets/inspector_db_migration_password'},migration=True)\n"
        " engine=create_engine(c.database,dedicated=True)\n"
        " try:\n"
        "  async with engine.connect() as connection:\n"
        "   grants=(await connection.execute(text('SHOW GRANTS FOR CURRENT_USER'))).scalars().all()\n"
        "   scopes=[str(grant).split(' TO ',1)[0] for grant in grants]\n"
        "   assert scopes==['GRANT USAGE ON *.*','GRANT ALL PRIVILEGES ON `system\\\\_inspector`.*'],scopes\n"
        "   print(json.dumps({'scopes':scopes,'authentication_metadata_returned':False}))\n"
        " finally: await engine.dispose()\n"
        "asyncio.run(verify())\n"
    )
    argv = [
        "docker",
        "compose",
        "--project-name",
        stack,
        "--project-directory",
        str(private),
        "-f",
        str(private / "compose.yaml"),
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        "migrate",
        "-c",
        grant_program,
    ]
    grants = run(argv).stdout.decode()
    receipt["migrator_grants"] = json.loads(grants)
    receipt["passed"] = True
    target = ROOT / "verification/stage-8/production-image-security.json"
    target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "receipt": target.relative_to(ROOT).as_posix()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
