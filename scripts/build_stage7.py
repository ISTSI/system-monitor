"""Build Stage 07 in an isolated directory without replacing installed web assets."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from verify_stage7_build import record_inputs, source_hashes

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".state/stage7-build"


def clear_generated(directory: Path) -> None:
    """Only replace checked generated directories inside this isolated build."""
    absolute = directory.resolve()
    build_root = OUTPUT.resolve()
    if (
        OUTPUT.is_symlink()
        or not build_root.is_relative_to(ROOT.resolve())
        or directory.is_symlink()
        or not absolute.is_relative_to(build_root)
        or absolute == build_root
    ):
        raise RuntimeError("Refusing to replace a directory outside the isolated Stage 07 build.")
    if directory.exists():
        shutil.rmtree(directory)


def main() -> int:
    inputs = source_hashes(ROOT)
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
    for directory in ("src", "migrations"):
        clear_generated(backend / directory)
        shutil.copytree(
            ROOT / "backend" / directory,
            backend / directory,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "web"),
        )
    for name in ("pyproject.toml", "uv.lock", "alembic.ini", "README.md"):
        shutil.copyfile(ROOT / "backend" / name, backend / name)
    web = backend / "src/inspector/web"
    shutil.copytree(frontend, web, dirs_exist_ok=True)
    assets = {
        p.relative_to(frontend).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in frontend.rglob("*")
        if p.is_file()
    }
    (web / "BUILD_ASSETS.json").write_text(json.dumps(assets, indent=2) + "\n", encoding="utf-8")
    clear_generated(backend / "dist")
    subprocess.run([sys.executable, "-m", "hatchling", "build"], cwd=backend, check=True)
    record_inputs(ROOT, inputs)
    output = ROOT / "verification/stage-7"
    output.mkdir(parents=True, exist_ok=True)
    (output / "build-assets.json").write_text(json.dumps(assets, indent=2) + "\n", encoding="utf-8")
    print("Built isolated Stage 07 assets and distributions; retained installations preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
