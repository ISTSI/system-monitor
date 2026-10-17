"""Explicit connected preparation: stage pinned images and build the Linux DB-test runner."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from local_mariadb import SetupError, require_local_docker

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connected",
        required=True,
        action="store_true",
        help="Explicitly authorize image pulls and dependency downloads during build.",
    )
    parser.parse_args()
    if os.environ.get("BUILDX_BUILDER") or os.environ.get("BUILDKIT_HOST"):
        parser.exit(1, "Use the local Docker builder without builder endpoint overrides.\n")
    try:
        require_local_docker()
    except SetupError as error:
        parser.exit(1, str(error) + "\n")
    lock = json.loads((ROOT / "deploy/local-mariadb/images.lock.json").read_text(encoding="utf-8"))
    references = {}
    for name in ("mariadb", "python"):
        reference = lock["images"][name]["reference"]
        if not re.fullmatch(
            r"docker\.io/library/" + name + r":[A-Za-z0-9_.-]+@sha256:[a-f0-9]{64}", reference
        ):
            parser.exit(1, "Invalid official pinned image reference; no image was pulled.\n")
        references[name] = reference
    # Check the daemon before starting any download. Never change Docker context.
    result = subprocess.run(
        ["docker", "info", "--format", "{{.OSType}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode or result.stdout.strip() != "linux":
        parser.exit(1, "A running local Linux Docker engine is required; no images were pulled.\n")
    for name, reference in references.items():
        subprocess.run(
            ["docker", "pull", "--platform", "linux/amd64", reference], cwd=ROOT, check=True
        )
        print(f"Staged pinned {name} image.")
    subprocess.run(
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "--build-arg",
            "PYTHON_IMAGE=" + references["python"],
            "--file",
            "deploy/local-mariadb/runner.Dockerfile",
            "--tag",
            "system-inspector-runner:local",
            ".",
        ],
        cwd=ROOT,
        check=True,
    )
    print("Built local non-root Linux runner; runtime Compose never pulls images.")


if __name__ == "__main__":
    main()
