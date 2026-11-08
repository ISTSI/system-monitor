"""Run current Linux unit/package gates without Internet or retained-state mounts."""

from __future__ import annotations

import json
import os
import subprocess
import tarfile
import time
from pathlib import Path

import local_mariadb as local
import verify_stage7_linux


def source_archive() -> Path:
    archive = verify_stage7_linux.source_archive()
    with tarfile.open(archive, "r") as bundle:
        existing = set(bundle.getnames())
    with tarfile.open(archive, "a") as bundle:
        for directory in (local.ROOT / "deploy/offline", local.ROOT / "deploy/app"):
            for path in sorted(directory.rglob("*")):
                if path.is_symlink():
                    raise local.SetupError("Linked deployment source cannot enter qualification")
                relative = path.relative_to(local.ROOT)
                if any(
                    part in {"__pycache__", ".secrets", ".state", ".cache"}
                    for part in relative.parts
                ):
                    continue
                if (
                    not path.is_file()
                    or path.suffix in {".pyc", ".pyo"}
                    or relative.as_posix() in existing
                ):
                    continue
                if ".local" in path.name:
                    raise local.SetupError(
                        "Local deployment configuration cannot enter qualification"
                    )
                info = bundle.gettarinfo(str(path), arcname=relative.as_posix())
                info.mode = 0o644
                with path.open("rb") as stream:
                    bundle.addfile(info, stream)
    return archive


def main() -> int:
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(local.ROOT / ".cache/docker"))
    local.require_local_docker()
    archive = source_archive()
    program = (
        "import os,pathlib,subprocess,sys,tarfile\n"
        "base=pathlib.Path('/tmp/stage8-source');base.mkdir()\n"
        "with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:\n"
        " for member in archive:\n"
        "  target=(base/member.name).resolve()\n"
        "  if not member.isfile() or not target.is_relative_to(base): raise ValueError('Unsafe source')\n"
        "  target.parent.mkdir(parents=True,exist_ok=True)\n"
        "  with archive.extractfile(member) as source: target.write_bytes(source.read())\n"
        "  target.chmod(0o644)\n"
        "os.chdir(base)\n"
        "a=subprocess.call([sys.executable,'-m','pytest','backend/tests/unit','-q','-p','no:cacheprovider'])\n"
        "b=subprocess.call([sys.executable,'-m','unittest','discover','-s','tests/package','-q'])\n"
        "sys.exit(bool(a or b))\n"
    )
    argv = [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--pull=never",
        "--network=none",
        "--user=10001:10001",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=128",
        "--memory=1g",
        "--tmpfs=/tmp:mode=1777",
        "--workdir=/tmp",
        "--env=PYTHONPATH=/tmp/stage8-source/backend/src",
        "--env=PYTHONDONTWRITEBYTECODE=1",
        "--entrypoint=python",
        "system-inspector-runner:stage7",
        "-c",
        program,
    ]
    started = time.monotonic()
    with archive.open("rb") as stream:
        result = subprocess.run(
            argv, stdin=stream, cwd=local.ROOT, capture_output=True, timeout=600, check=False
        )
    output = local.ROOT / "verification/stage-8"
    output.mkdir(parents=True, exist_ok=True)
    (output / "linux-unit-package.log").write_bytes(result.stdout + result.stderr)
    (output / "linux-unit-package-command.json").write_text(
        json.dumps(
            dict(
                argv=argv,
                exit_code=result.returncode,
                elapsed_seconds=round(time.monotonic() - started, 3),
                runtime="Docker Desktop Linux runner; native Ubuntu/Rocky remain untested",
                source_deployment_files_included=True,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Linux unit/package qualification exit {result.returncode}; retained Stage 08 receipt and log"
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
