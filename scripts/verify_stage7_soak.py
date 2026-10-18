"""Measure an existing generated Stage 07 fixture, without new identities.

The browser test temporarily expands existing system A and restores its exact
configuration. This controller appends only its five existing generated app.log
files and restores their original bytes. It never uses application SSH writes,
creates accounts/projects/secrets, or changes trust, credentials or log roots.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import stat
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://localhost:8449"
FIXTURE = Path("/tmp/stage6-fixture/var/log/inspector-demo")


def run_id(value: str) -> str:
    if re.fullmatch(r"[a-f0-9]{12}", value) is None:
        raise ValueError("A generated 12-digit synthetic run identity is required.")
    return value


def source_files() -> list[Path]:
    root = FIXTURE.resolve(strict=True)
    if FIXTURE.is_symlink() or str(root) != str(FIXTURE):
        raise ValueError("The existing generated fixture boundary changed.")
    files = [
        FIXTURE / name / "app.log" for name in ("ingest", "parser", "router", "delivery", "audit")
    ]
    for path in files:
        if (
            path.parent.is_symlink()
            or path.is_symlink()
            or not path.resolve(strict=True).is_relative_to(root)
            or not stat.S_ISREG(path.stat().st_mode)
            or path.stat().st_size > 1048576
        ):
            raise ValueError("An existing bounded regular fixture log is unavailable.")
    return files


def record(identifier: str, source: int, sequence: int) -> bytes:
    timestamp = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    return f"{timestamp} SOAK run={identifier} source={source} seq={sequence} {'EVEN' if sequence % 2 == 0 else 'ODD'}\n".encode()


def validate_fixture() -> dict:
    return {
        "synthetic": True,
        "files": [
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in source_files()
        ],
    }


def produce_fixture(identifier: str, seconds: int) -> dict:
    if not 1800 <= seconds <= 2400:
        raise ValueError("The synthetic producer requires a bounded 30-40 minute run.")
    files = source_files()
    originals = [path.read_bytes() for path in files]
    before = validate_fixture()
    stopped = False

    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGUSR1, stop)
    signal.signal(signal.SIGTERM, stop)
    start = time.monotonic()
    first = last = None
    count = 0
    try:
        while time.monotonic() - start < seconds and not stopped:
            source = count % 5
            payload = record(identifier, source, count)
            with files[source].open("ab") as stream:
                stream.write(payload)
            stamp = payload.decode().split(" ", 1)[0]
            first = first or stamp
            last = stamp
            count += 1
            time.sleep(max(0, start + count - time.monotonic()))
    finally:
        for path, original in zip(files, originals, strict=True):
            if path.is_symlink() or not path.is_file():
                raise ValueError("The original fixture path changed; restore refused.")
            path.write_bytes(original)
    after = validate_fixture()
    if before != after:
        raise ValueError("Exact fixture log restoration failed.")
    return {
        "synthetic": True,
        "run_id": identifier,
        "actual_records": count,
        "first_timestamp_utc": first,
        "last_timestamp_utc": last,
        "elapsed_seconds": time.monotonic() - start,
        "configured_total_records_per_second": 1,
        "sources": 5,
        "stopped_explicitly": stopped,
        "original_files": before,
        "exact_original_bytes_restored": before == after,
    }


def stop_fixture(identifier: str) -> dict:
    stopped = []
    expected = [
        b"python",
        b"/workspace/scripts/verify_stage7_soak.py",
        b"produce-fixture",
        b"--run-id",
        identifier.encode(),
        b"--seconds",
        b"1860",
    ]
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            if (path / "cmdline").read_bytes().rstrip(b"\0").split(b"\0") == expected:
                os.kill(int(path.name), signal.SIGUSR1)
                stopped.append(int(path.name))
        except (OSError, ValueError):
            continue
    return {"run_id": identifier, "stopped_owned_local_fixture_writers": stopped}


def process_state() -> dict:
    """Read the actual ASGI process, without exposing argv or environment."""
    processes = []
    ticks = os.sysconf("SC_CLK_TCK")
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            command = (path / "cmdline").read_bytes()
            if (
                b"uvicorn" not in command
                or b"inspector.app:create_app" not in command
                or b"verify_stage7_soak.py" in command
            ):
                continue
            fields = dict(
                line.split(":", 1)
                for line in (path / "status").read_text().splitlines()
                if ":" in line
            )
            values = (path / "stat").read_text().split(")", 1)[1].split()
            fds = list((path / "fd").iterdir())
            processes.append(
                {
                    "pid": int(path.name),
                    "rss_bytes": int(fields["VmRSS"].split()[0]) * 1024,
                    "cpu_seconds": (int(values[11]) + int(values[12])) / ticks,
                    "threads": int(fields["Threads"]),
                    "os_task_count": len(list((path / "task").iterdir())),
                    "file_descriptor_count": len(fds),
                    "socket_file_descriptors": sum(
                        os.readlink(fd).startswith("socket:") for fd in fds
                    ),
                }
            )
        except (OSError, ValueError, KeyError):
            continue
    if not processes:
        raise ValueError("No live fixture ASGI process was found.")
    return {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "processes": processes,
        "rss_bytes": sum(item["rss_bytes"] for item in processes),
        "scope": "Actual Linux ASGI process RSS/CPU, OS tasks/threads and open sockets; asyncio task objects are not exposed.",
    }


def local_environment() -> None:
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".cache/docker"))


def setup_local():
    import local_mariadb as local
    import stage7_local

    local_environment()
    local.require_local_docker()
    return local, stage7_local, stage7_local.checked_setup()


def resources(identifier: str) -> dict:
    local, _stage, override = setup_local()
    app = local.compose("ps", "--quiet", "stage7-browser", override=override).strip()
    database = local.compose("ps", "--quiet", "mariadb", override=override).strip()
    if not re.fullmatch(r"[a-f0-9]{64}", app) or not re.fullmatch(r"[a-f0-9]{64}", database):
        raise ValueError("Expected live local fixture containers.")
    state = json.loads(
        local.compose(
            "exec",
            "-T",
            "stage7-browser",
            "python",
            "/workspace/scripts/verify_stage7_soak.py",
            "process-state",
            override=override,
            timeout=20,
        )
    )
    statistics = [
        json.loads(line)
        for line in local.run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}", app, database],
            label="Read local soak resource counters",
            timeout=20,
        ).splitlines()
    ]
    by_container = {item["Container"]: item for item in statistics}
    if set(by_container) != {app, database}:
        raise ValueError("Actual Docker resource identities did not match the fixture containers.")
    statistics = [by_container[app], by_container[database]]
    limits = [
        json.loads(line)
        for line in local.run(
            [
                "docker",
                "inspect",
                app,
                database,
                "--format",
                '{"memory_bytes":{{.HostConfig.Memory}},"nanocpus":{{.HostConfig.NanoCpus}},"pids_limit":{{json .HostConfig.PidsLimit}}}',
            ],
            label="Read fixture resource ceilings",
            timeout=20,
        ).splitlines()
    ]
    docker_memory = int(
        local.run(
            ["docker", "info", "--format", "{{.MemTotal}}"],
            label="Read local Docker Linux memory budget",
            timeout=20,
        ).strip()
    )
    host_memory = None
    if os.name == "nt":
        host_memory = int(
            local.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
                ],
                label="Read client host physical memory",
                timeout=20,
            ).strip()
        )
    return {
        "run_id": run_id(identifier),
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "app_process": state,
        "containers": {"app": statistics[0], "mariadb_shared_fixture": statistics[1]},
        "container_limits": {"app": limits[0], "mariadb": limits[1]},
        "docker_linux_memory_bytes": docker_memory,
        "windows_host_memory_bytes": host_memory,
        "proxy": {
            "present": False,
            "rss_bytes": 0,
            "cpu_seconds": 0,
            "reason": "This isolated fixture uses direct ASGI TLS; proxy and Ubuntu/Rocky release qualification remain Stage 08.",
        },
    }


def controller(command: str, identifier: str, seconds: int) -> dict:
    local, _stage, override = setup_local()
    action = {
        "produce": "produce-fixture",
        "stop": "stop-fixture",
        "validate": "validate-fixture",
    }[command]
    argv = [
        "exec",
        "-T",
        "stage7-sftp",
        "python",
        "/workspace/scripts/verify_stage7_soak.py",
        action,
        "--run-id",
        run_id(identifier),
    ]
    if command == "produce":
        argv += ["--seconds", str(seconds)]
    return json.loads(
        local.compose(
            *argv,
            override=override,
            timeout=seconds + 60 if command == "produce" else 20,
        )
    )


def analyze(identifier: str) -> dict:
    """Evaluate actual completed observations; never manufacture measurements."""
    identifier = run_id(identifier)
    path = ROOT / "verification/stage-7" / f"soak-{identifier}.json"
    report = json.loads(path.read_text("utf-8"))
    restoration = json.loads(
        (ROOT / ".state/stage7-soak" / f"{identifier}-restored.json").read_text("utf-8")
    )
    original_config = json.loads(
        (ROOT / ".state/stage7-soak" / f"{identifier}-original.json").read_text("utf-8")
    )
    observations = report["observations"]
    if (
        not report["complete"]
        or report["actual_elapsed_seconds"] < 1800
        or report["configured_processes"] != 60
        or report["monitored_processes"] != 5
        or len(observations) < 3
        or report["errors"]
        or report["external_requests"]
        or not report["producer"]["exact_original_bytes_restored"]
        or report["producer"]["actual_records"] < 1800
        or not restoration["restored"]
        or not restoration["content_equal_except_revision"]
    ):
        raise ValueError("The actual thirty-minute/restoration acceptance evidence is incomplete.")

    def browser_rows(observation):
        value = observation["browser_process_memory"]
        return value if isinstance(value, list) else [value]

    def metric(observation, name):
        return next(
            item["value"] for item in observation["page_performance"] if item["name"] == name
        )

    start, end = observations[0], observations[-1]
    middle = (start["elapsed_seconds"] + end["elapsed_seconds"]) / 2
    midpoint = min(observations, key=lambda item: abs(item["elapsed_seconds"] - middle))
    for item in observations:
        containers = item["app_and_database"]["containers"]
        if (
            containers["app"]["Name"] != "system-inspector-local-stage7-browser-1"
            or containers["mariadb_shared_fixture"]["Name"] != "system-inspector-local-mariadb-1"
        ):
            raise ValueError("Actual app and database resource labels do not match.")
    app = [item["app_and_database"]["app_process"] for item in observations]
    browser_rss = [sum(row["WorkingSet64"] for row in browser_rows(item)) for item in observations]
    database = [
        item["app_and_database"]["containers"]["mariadb_shared_fixture"] for item in observations
    ]
    database_cpu = [float(item["CPUPerc"].removesuffix("%")) for item in database]

    def memory_bytes(value):
        match = re.fullmatch(r"([0-9.]+)(B|kB|KB|KiB|MB|MiB|GB|GiB)", value.split(" / ", 1)[0])
        if not match:
            raise ValueError("Unsupported actual Docker memory counter.")
        units = {
            "B": 1,
            "kB": 1000,
            "KB": 1000,
            "KiB": 1024,
            "MB": 1000000,
            "MiB": 1048576,
            "GB": 1000000000,
            "GiB": 1073741824,
        }
        return int(float(match[1]) * units[match[2]])

    database_rss = [memory_bytes(item["MemUsage"]) for item in database]
    app_peak = max(item["rss_bytes"] for item in app)
    if app_peak >= 1073741824:
        raise ValueError("Actual backend RSS exceeded the AT61 one-GiB target.")
    if any(
        item["live"]["status"] != "following"
        or item["live"]["process_count"] != 5
        or item["open_websocket_count"] != 1
        or item["websocket_connections_created"] != 1
        or any(
            source["state"] != "following"
            or source["error"]
            or source["reconnects"]
            or source["gaps"]
            for source in item["live"]["sources"]
        )
        for item in observations
    ):
        raise ValueError("The five-source capture/socket continuity assertion failed.")
    tasks = [sum(process["os_task_count"] for process in item["processes"]) for item in app]
    sockets = [
        sum(process["socket_file_descriptors"] for process in item["processes"]) for item in app
    ]
    fds = [sum(process["file_descriptor_count"] for process in item["processes"]) for item in app]
    # Compare the second half after seeding/graph/filter warmup. The finite
    # baseline establishes a bounded observed trend, not a universal leak proof.
    warm_app = app[len(app) // 2 :]
    if (
        app[-1]["rss_bytes"] > warm_app[0]["rss_bytes"] + 32 * 1048576
        or max(tasks) > min(tasks) + 4
        or max(sockets) > min(sockets) + 4
        or max(fds) > min(fds) + 8
        or browser_rss[-1] > browser_rss[len(browser_rss) // 2] + 128 * 1048576
        or metric(end, "JSHeapUsedSize") > metric(midpoint, "JSHeapUsedSize") + 64 * 1048576
        or metric(end, "Nodes") > metric(midpoint, "Nodes") + 2000
    ):
        raise ValueError(
            "Observed warmed application memory/task/socket growth exceeded the bounded baseline."
        )
    elapsed = end["elapsed_seconds"] - start["elapsed_seconds"]

    def app_cpu(item):
        return sum(
            process["cpu_seconds"]
            for process in item["app_and_database"]["app_process"]["processes"]
        )

    def browser_cpu(item):
        return sum(row["CPU"] for row in browser_rows(item))

    def snapshot(item):
        return {
            "elapsed_seconds": item["elapsed_seconds"],
            "app_rss_bytes": item["app_and_database"]["app_process"]["rss_bytes"],
            "app_cpu_seconds": app_cpu(item),
            "mariadb": item["app_and_database"]["containers"]["mariadb_shared_fixture"],
            "browser_working_set_bytes": sum(row["WorkingSet64"] for row in browser_rows(item)),
            "browser_cpu_seconds": browser_cpu(item),
            "page_js_heap_bytes": metric(item, "JSHeapUsedSize"),
            "received": item["live"]["counters"]["received"],
        }

    limits = end["app_and_database"]["container_limits"]
    server_caps = limits["app"]["memory_bytes"] + limits["mariadb"]["memory_bytes"]
    if not 0 < server_caps < 16 * 1073741824:
        raise ValueError(
            "The configured fixture ceilings provide no measured 16-GiB design headroom."
        )
    result = {
        "passed": True,
        "run_id": identifier,
        "started_at_utc": report["started_at_utc"],
        "finished_at_utc": report["finished_at_utc"],
        "actual_elapsed_seconds": report["actual_elapsed_seconds"],
        "sample_count": len(observations),
        "model": {
            "configured_processes": 60,
            "existing_servers": len(original_config["servers"]),
            "monitored_processes": 5,
            "scope": "Denser existing three-server synthetic model; no 10-20-host or native OS release qualification is claimed.",
        },
        "start": snapshot(start),
        "midpoint": snapshot(midpoint),
        "end": snapshot(end),
        "peak_app_rss_bytes": app_peak,
        "peak_browser_working_set_bytes": max(browser_rss),
        "mariadb_container_memory_bytes_range": [min(database_rss), max(database_rss)],
        "mariadb_sampled_cpu_percent_range": [min(database_cpu), max(database_cpu)],
        "mariadb_sampled_cpu_percent_mean": sum(database_cpu) / len(database_cpu),
        "app_average_one_core_cpu_percent": (app_cpu(end) - app_cpu(start)) / elapsed * 100,
        "browser_average_one_core_cpu_percent": (browser_cpu(end) - browser_cpu(start))
        / elapsed
        * 100,
        "app_os_task_count_range": [min(tasks), max(tasks)],
        "app_socket_fd_range": [min(sockets), max(sockets)],
        "app_fd_range": [min(fds), max(fds)],
        "live_websocket_count": 1,
        "live_reconnects": 0,
        "container_limits": limits,
        "server_container_memory_caps_bytes": server_caps,
        "headroom_below_16_gib_server_design_budget_bytes": 16 * 1073741824 - server_caps,
        "docker_linux_memory_bytes": end["app_and_database"]["docker_linux_memory_bytes"],
        "headroom_below_actual_docker_linux_memory_bytes": end["app_and_database"][
            "docker_linux_memory_bytes"
        ]
        - server_caps,
        "windows_client_host_memory_bytes": end["app_and_database"]["windows_host_memory_bytes"],
        "proxy": end["app_and_database"]["proxy"],
        "exact_original_log_bytes_restored": True,
        "topology_restoration": restoration,
        "limits": "Actual local Docker Linux/Windows Chromium baseline. MariaDB is a shared test container. Proxy is absent. Asyncio task objects are not exposed; OS tasks/threads, source states, descriptors and sockets are measured. Finite thirty-minute bounded trends do not qualify Ubuntu/Rocky offline production release.",
    }
    (path.parent / f"soak-{identifier}-summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "validate",
            "analyze",
            "resources",
            "produce",
            "stop",
            "validate-fixture",
            "produce-fixture",
            "stop-fixture",
            "process-state",
        ],
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument("--seconds", type=int, default=1860)
    args = parser.parse_args()
    if args.command == "process-state":
        result = process_state()
    elif args.command == "validate-fixture":
        result = validate_fixture()
    elif args.command == "produce-fixture":
        result = produce_fixture(run_id(args.run_id), args.seconds)
    elif args.command == "stop-fixture":
        result = stop_fixture(run_id(args.run_id))
    elif args.command == "resources":
        result = resources(run_id(args.run_id))
    elif args.command == "analyze":
        result = analyze(run_id(args.run_id))
    else:
        result = controller(args.command, run_id(args.run_id), args.seconds)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
