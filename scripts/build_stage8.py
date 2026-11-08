"""Build an isolated Stage 08 wheel and freeze its source/asset correspondence."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import build_stage7
import verify_stage7_build

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".state/stage8-build"


def main() -> int:
    verify_stage7_build.BUILD_RELATIVE = Path(".state/stage8-build")
    build_stage7.OUTPUT = OUTPUT
    inputs = verify_stage7_build.source_hashes(ROOT)
    frontend = OUTPUT / "frontend"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/frontend.py"),
            "build",
            "--outDir",
            str(frontend),
            "--emptyOutDir",
        ],
        cwd=ROOT,
        check=True,
    )
    backend = OUTPUT / "backend"
    backend.mkdir(parents=True, exist_ok=True)
    for name in ("src", "migrations"):
        build_stage7.clear_generated(backend / name)
        shutil.copytree(
            ROOT / "backend" / name,
            backend / name,
            ignore=shutil.ignore_patterns("__pycache__", "web"),
        )
    for name in ("pyproject.toml", "uv.lock", "alembic.ini", "README.md"):
        shutil.copyfile(ROOT / "backend" / name, backend / name)
    web = backend / "src/inspector/web"
    shutil.copytree(frontend, web)
    assets = {
        p.relative_to(frontend).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in frontend.rglob("*")
        if p.is_file()
    }
    (web / "BUILD_ASSETS.json").write_text(json.dumps(assets, indent=2) + "\n", encoding="utf-8")
    build_stage7.clear_generated(backend / "dist")
    subprocess.run([sys.executable, "-m", "hatchling", "build"], cwd=backend, check=True)
    verify_stage7_build.record_inputs(ROOT, inputs)
    report = verify_stage7_build.verify_build(ROOT)
    evidence = ROOT / "verification/stage-8"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "build.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "Stage 08 isolated wheel and local assets verified."
        if report["verified"]
        else "Build verification failed."
    )
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
