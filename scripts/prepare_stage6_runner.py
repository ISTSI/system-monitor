"""Build a separate Stage 06 Linux test image; preserve the installed runner tag."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time

import local_mariadb as local


def main() -> None:
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(local.ROOT / ".cache/docker"))
    if os.environ.get("BUILDX_BUILDER") or os.environ.get("BUILDKIT_HOST"):
        raise local.SetupError("Only the local Docker builder is authorized.")
    local.require_local_docker()
    source = local.ROOT / "deploy/local-mariadb/images.lock.json"
    reference = json.loads(source.read_text("utf-8"))["images"]["python"]["reference"]
    if not re.fullmatch(
        r"docker\.io/library/python:[A-Za-z0-9_.-]+@sha256:[a-f0-9]{64}", reference
    ):
        raise local.SetupError("The pinned official Python base is invalid.")
    # Inspect fails if absent. Do not issue docker pull or replace the original tag.
    local.run(
        ["docker", "image", "inspect", reference, "--format", "{{.Id}}"],
        label="Verify the existing local pinned Python image",
    )
    original = local.run(
        ["docker", "image", "inspect", "system-inspector-runner:local", "--format", "{{.Id}}"],
        label="Inspect the installed runner",
    ).strip()
    argv = [
        "docker",
        "build",
        "--pull=false",
        "--platform",
        "linux/amd64",
        "--build-arg",
        "PYTHON_IMAGE=" + reference,
        "--file",
        "deploy/local-mariadb/runner.Dockerfile",
        "--tag",
        "system-inspector-runner:stage6",
        ".",
    ]
    started = time.monotonic()
    result = subprocess.run(argv, cwd=local.ROOT, capture_output=True, timeout=300, check=False)
    output = local.ROOT / "verification/stage-6"
    output.mkdir(parents=True, exist_ok=True)
    (output / "runner-build.log").write_bytes(result.stdout + result.stderr)
    after = local.run(
        ["docker", "image", "inspect", "system-inspector-runner:local", "--format", "{{.Id}}"],
        label="Verify installed runner preservation",
    ).strip()
    details = {
        "argv": argv,
        "exit_code": result.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "original_runner_id": original,
        "original_runner_preserved": original == after,
        "uv_lock_sha256": hashlib.sha256((local.ROOT / "backend/uv.lock").read_bytes()).hexdigest(),
    }
    if result.returncode == 0:
        details["stage6_runner_id"] = local.run(
            ["docker", "image", "inspect", "system-inspector-runner:stage6", "--format", "{{.Id}}"],
            label="Inspect the separate Stage 06 runner",
        ).strip()
    (output / "runner-build.json").write_text(
        json.dumps(details, indent=2) + "\n", encoding="utf-8"
    )
    if result.returncode or original != after:
        raise local.SetupError("Stage 06 runner build failed; see retained verification evidence.")
    print("Built separate system-inspector-runner:stage6; original installed image preserved.")


if __name__ == "__main__":
    try:
        main()
    except local.SetupError as error:
        raise SystemExit(str(error)) from None
