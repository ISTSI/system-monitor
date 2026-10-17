"""Bounded read-only capacity diagnostics for only the isolated Stage 05 schema.

Never records SQL text from PROCESSLIST, account names, filters or log contents.
Docker statistics and database state polls run independently so short indexing
windows are observed without delaying the browser's producers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
from datetime import UTC, datetime

import local_mariadb as local
from stage5_local import SETUP, checked_setup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--seconds", type=int, default=45, choices=range(1, 61))
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", args.label):
        raise local.SetupError("Invalid synthetic diagnostics label.")
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(local.ROOT / ".cache/docker"))
    local.require_local_docker()
    checked_setup()
    database = json.loads(SETUP.read_text("utf-8"))["database"]
    if not re.fullmatch(r"inspector_test_s5_web_[a-f0-9]{10}", database):
        raise local.SetupError("Unexpected diagnostic database boundary.")
    statement = (
        f"SELECT 'job',project_id,id,status,event_count,downloaded_bytes,expanded_bytes "
        f"FROM `{database}`.history_jobs WHERE status IN ('queued','planning','collecting','indexing') "
        "AND project_id IN ('stage5-fixture-a','stage5-fixture-b') ORDER BY project_id;\n"
        f"SELECT 'live',project_id,COUNT(*) FROM `{database}`.live_subscriptions "
        "WHERE project_id IN ('stage5-fixture-a','stage5-fixture-b') GROUP BY project_id;\n"
        "SELECT 'threads_running',VARIABLE_VALUE FROM information_schema.GLOBAL_STATUS "
        "WHERE VARIABLE_NAME='THREADS_RUNNING';\n"
        "SELECT 'process',COMMAND,TIME,STATE FROM information_schema.PROCESSLIST "
        f"WHERE DB='{database}' ORDER BY COMMAND,TIME;\n"
    )
    containers = ["system-inspector-local-stage5-browser-1", "system-inspector-local-mariadb-1"]
    limits = local.run(
        [
            "docker",
            "inspect",
            *containers,
            "--format",
            "{{.Name}} memory={{.HostConfig.Memory}} nano_cpus={{.HostConfig.NanoCpus}} cpu_quota={{.HostConfig.CpuQuota}} cpu_period={{.HostConfig.CpuPeriod}} cpuset={{.HostConfig.CpusetCpus}}",
        ],
        label="Read isolated fixture CPU and memory ceilings",
    )
    samples: list[dict] = []
    statistics: list[dict] = []
    errors: list[str] = []
    stop = threading.Event()

    def sql_samples() -> None:
        while not stop.is_set():
            started = time.monotonic()
            try:
                rows = [line.split("\t") for line in local.root_sql(statement).splitlines()]
                samples.append(
                    {
                        "measured_at": datetime.now(UTC).isoformat(),
                        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                        "rows": rows,
                    }
                )
            except (local.SetupError, OSError):
                errors.append("sql_state_probe_failed")
                break
            stop.wait(0.1)

    def docker_statistics() -> None:
        while not stop.is_set():
            try:
                started = datetime.now(UTC).isoformat()
                measured = local.run(
                    ["docker", "stats", "--no-stream", "--format", "{{json .}}", *containers],
                    label="Read isolated capacity CPU and RSS",
                    timeout=10,
                )
                statistics.append(
                    {
                        "started_at": started,
                        "measured_at": datetime.now(UTC).isoformat(),
                        "containers": [json.loads(line) for line in measured.splitlines()],
                    }
                )
            except (local.SetupError, OSError, ValueError):
                errors.append("docker_statistics_probe_failed")
                break

    workers = [threading.Thread(target=sql_samples), threading.Thread(target=docker_statistics)]
    for worker in workers:
        worker.start()
    try:
        stop.wait(args.seconds)
    finally:
        stop.set()
        for worker in workers:
            worker.join(timeout=12)
    evidence = local.ROOT / "verification/stage-5" / f"capacity-diagnostic-{args.label}.json"
    evidence.write_text(
        json.dumps(
            {
                "read_only": True,
                "duration_seconds": args.seconds,
                "sql_fields": "job project/id/state/counts; live project/count; global Threads_running; PROCESSLIST command/time/state only",
                "container_limits": limits.splitlines(),
                "sql_samples": samples,
                "docker_statistics": statistics,
                "errors": errors,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Recorded {len(samples)} safe database-state samples and {len(statistics)} Docker measurements."
    )


if __name__ == "__main__":
    main()
