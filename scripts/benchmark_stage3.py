"""Run the guarded local Stage 03 benchmark and retain sanitized UTF-8 evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import yaml
from local_mariadb import DEPLOY, ENV_FILE, ROOT, require_local_docker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-job")
    parser.add_argument("--profile-compare-job")
    parser.add_argument("--ingestion-profile", action="store_true")
    args = parser.parse_args()
    if os.name == "nt" and "DOCKER_HOST" not in os.environ:
        os.environ["DOCKER_HOST"] = "npipe:////./pipe/dockerDesktopLinuxEngine"
        os.environ["DOCKER_CONFIG"] = str(ROOT / ".cache/docker")
    require_local_docker()
    setup = json.loads((ROOT / ".state/stage3-browser/setup.json").read_text("utf-8"))
    override = Path(setup["override"])
    document = yaml.safe_load(override.read_text("utf-8"))
    secrets = []
    accounts = json.loads((ROOT / ".secrets/stage3-browser/accounts.json").read_text("utf-8"))
    secrets.extend(account["password"] for account in accounts.values())
    for item in document.get("secrets", {}).values():
        path = Path(item.get("file", ""))
        if path.is_file() and path.name not in {"accounts.json", "localhost-cert.pem"}:
            value = path.read_text("utf-8").rstrip("\r\n")
            if value:
                secrets.append(value)

    def sanitized(text: str) -> str:
        for value in secrets:
            text = text.replace(value, "[REDACTED]")
        return text

    argv = [
        "docker",
        "compose",
        "--project-name",
        "system-inspector-local",
        "--project-directory",
        str(DEPLOY),
        "--env-file",
        str(ENV_FILE),
        "-f",
        str(DEPLOY / "compose.yaml"),
        "-f",
        str(override),
        "run",
        "--rm",
        "--no-deps",
        "--name",
        "inspector-stage3-benchmark-" + uuid4().hex[:12],
        "runtime-stage3",
        "python",
        "/workspace/scripts/benchmark_history.py",
    ]
    if args.profile_job is not None:
        argv.extend(["--profile-job", args.profile_job])
    if args.profile_compare_job is not None:
        argv.extend(["--profile-compare-job", args.profile_compare_job])
    if args.ingestion_profile:
        argv.append("--ingestion-profile")
    label = (
        "profile"
        if args.profile_job is not None
        else "ingestion-profile"
        if args.ingestion_profile
        else "benchmark"
    )
    output = ROOT / "verification/stage-3"
    output.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=600, check=False)
        stdout = sanitized(result.stdout.decode("utf-8", errors="replace"))
        stderr = sanitized(result.stderr.decode("utf-8", errors="replace"))
        code = result.returncode
    except subprocess.TimeoutExpired as error:
        stdout = sanitized((error.stdout or b"").decode("utf-8", errors="replace"))
        stderr = sanitized((error.stderr or b"").decode("utf-8", errors="replace"))
        code = 124
        # A killed Compose client can leave its attached container alive. Stop only
        # this invocation's generated local runner so it cannot retain the supervisor.
        try:
            subprocess.run(
                ["docker", "stop", "--time", "2", argv[argv.index("--name") + 1]],
                cwd=ROOT,
                capture_output=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            stderr += "\nGenerated benchmark runner cleanup could not be confirmed.\n"
    (output / f"{label}-stdout.log").write_text(stdout, encoding="utf-8")
    (output / f"{label}-stderr.log").write_text(stderr, encoding="utf-8")
    (output / f"{label}-command.json").write_text(
        json.dumps({"argv": argv, "cwd": str(ROOT), "exit_code": code}, indent=2) + "\n",
        encoding="utf-8",
    )
    if code == 0:
        record = json.loads(stdout)
        (output / f"mariadb-{label}.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(record, indent=2))
    else:
        print(json.dumps({"exit_code": code, "diagnostics": str(output / f"{label}-stderr.log")}))
    return code


if __name__ == "__main__":
    sys.exit(main())
