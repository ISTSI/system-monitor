"""Record executed local checks. Integration skips remain explicit in pytest output."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUTPUT = ROOT / "verification" / "upgrade-slice-1"


def record_changes() -> None:
    baseline = json.loads((ROOT / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
    originals = {entry["path"]: entry for entry in baseline["files"]}
    ignored = {
        ".git",
        ".bootstrap",
        ".toolchains",
        ".cache",
        ".venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
        ".secrets",
    }
    paths = []
    for directory, children, files in os.walk(ROOT):
        children[:] = sorted(
            name for name in children if name not in ignored and not name.endswith(".egg-info")
        )
        paths.extend(
            Path(directory) / name for name in files if not name.endswith((".pyc", ".local.yaml"))
        )
    changed = []
    for path in sorted(paths):
        relative = path.relative_to(ROOT).as_posix()
        if relative == "PACKAGE_MANIFEST.json":
            continue
        original = originals.get(relative)
        if original is None:
            changed.append({"path": relative, "status": "added"})
        elif hashlib.sha256(path.read_bytes()).hexdigest() != original["sha256"]:
            changed.append({"path": relative, "status": "modified"})
    for relative in originals:
        if not (ROOT / relative).exists():
            changed.append({"path": relative, "status": "missing"})
    target = OUTPUT / "file_changes.json"
    if not target.exists():
        changed.append({"path": target.relative_to(ROOT).as_posix(), "status": "added"})
    target.write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    OUTPUT = args.output_dir.resolve()
    if not OUTPUT.is_relative_to(ROOT):
        parser.error("verification output must stay inside the repository")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    commands = [
        ("package-tests", ROOT, ["-m", "unittest", "discover", "-s", "tests/package", "-v"]),
        ("package-consistency", ROOT, ["tools/validate_package.py"]),
        ("schemas", ROOT, ["tools/validate_schemas.py"]),
        ("deployment-static", ROOT, ["tools/validate_deployment_examples.py"]),
        ("backend-unit", BACKEND, ["-m", "pytest", "tests/unit", "-v"]),
        ("backend-integration", BACKEND, ["-m", "pytest", "tests/integration", "-v", "-rs"]),
        (
            "lint",
            ROOT,
            [
                "-m",
                "ruff",
                "check",
                "--config",
                "backend/pyproject.toml",
                "backend/src",
                "backend/tests",
                "backend/migrations",
                "scripts",
            ],
        ),
        (
            "format",
            ROOT,
            [
                "-m",
                "ruff",
                "format",
                "--check",
                "--config",
                "backend/pyproject.toml",
                "backend/src",
                "backend/tests",
                "backend/migrations",
                "scripts",
            ],
        ),
        ("typecheck", BACKEND, ["-m", "mypy", "src"]),
        ("build", BACKEND, ["-m", "hatchling", "build"]),
        ("openapi", ROOT, ["-m", "inspector.cli", "openapi", "--output", "backend/openapi.json"]),
    ]
    if os.environ.get("SI_TEST_APPROVED_SCHEMA") and os.environ.get(
        "INSPECTOR_VM_MIGRATION_CONFIG"
    ):
        commands.append(
            (
                "backend-vm",
                BACKEND,
                ["-m", "pytest", "tests/vm/test_vm_mariadb.py", "-v", "--tb=short", "-rs"],
            )
        )
    if os.environ.get("SI_TEST_APPROVED_SCHEMA") and os.environ.get("INSPECTOR_STAGE1_CONFIG"):
        commands.append(
            ("backend-stage1", BACKEND, ["-m", "pytest", "tests/stage1", "-v", "--tb=short", "-rs"])
        )
    results = []
    for name, cwd, arguments in commands:
        command = [sys.executable, *arguments]
        environment = dict(os.environ)
        if name == "openapi":
            environment["INSPECTOR_CONFIG_FILE"] = str(
                ROOT / "examples/deployment-policy.example.yaml"
            )
        completed = subprocess.run(
            command, cwd=cwd, env=environment, capture_output=True, timeout=120, check=False
        )
        log = OUTPUT / f"{name}.log"
        log.write_bytes(completed.stdout + completed.stderr)
        results.append(
            {
                "name": name,
                "command": command,
                "cwd": str(cwd),
                "exit_code": completed.returncode,
                "log": log.relative_to(ROOT).as_posix(),
            }
        )
        print(f"{name}: exit {completed.returncode}")
    (OUTPUT / "commands.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    record_changes()
    print("Read integration logs: exit 0 with skips does not establish MariaDB acceptance.")
    return int(any(result["exit_code"] != 0 for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
