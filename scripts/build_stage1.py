"""Build local browser assets and a backend wheel containing those exact assets."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/frontend.py"), "build"], cwd=ROOT, check=True
    )
    source = ROOT / "frontend/dist"
    destination = ROOT / "backend/src/inspector/web"
    manifest = destination / "BUILD_ASSETS.json"
    if destination.exists() and not manifest.is_file() and any(destination.iterdir()):
        raise RuntimeError("Refusing to replace an unrecognized web asset directory.")
    destination.mkdir(parents=True, exist_ok=True)
    previous = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    current = {
        path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source.rglob("*")
        if path.is_file()
    }
    for relative in previous.keys() - current.keys():
        obsolete = (destination / relative).resolve()
        if not obsolete.is_relative_to(destination.resolve()) or obsolete.is_symlink():
            raise RuntimeError("Unsafe previous build manifest; no stale file deleted.")
        obsolete.unlink(missing_ok=True)
    for relative in current:
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes((source / relative).read_bytes())
    manifest.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, "-m", "hatchling", "build"], cwd=ROOT / "backend", check=True)
    print(
        "Built browser assets and Python distributions; this does not establish an OCI/Linux release."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
