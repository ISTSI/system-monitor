"""Record Stage 03 checks using installed tools and isolated local MariaDB only."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "verification/stage-3"


def integration(suffix: str | None, *, upgrade: bool = False) -> int:
    import local_mariadb as local

    suffix = suffix or (
        ("s2_upgrade_" + secrets.token_hex(4)) if upgrade else "s3_" + secrets.token_hex(5)
    )
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".cache/docker"))
    # new_test verifies a local daemon and an absent schema before provisioning.
    # Root/migration secrets stay in the existing protected file-only mechanism.
    local.new_test(suffix, execute=False)
    original = local.run

    def recorded(
        argv: list[str], *, label: str, data: str | None = None, timeout: int = 180
    ) -> str:
        result = subprocess.run(
            argv,
            input=data,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        (OUTPUT / f"{suffix}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        (OUTPUT / f"{suffix}-command.json").write_text(
            json.dumps({"argv": argv, "cwd": str(ROOT), "exit_code": result.returncode}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        if result.returncode:
            raise local.SetupError("Integration failed; see retained sanitized test output.")
        return result.stdout

    local.run = recorded
    try:
        arguments = ["run", "--rm", "--no-deps"]
        if upgrade:
            arguments.extend(["-e", "INSPECTOR_CONFIG_FILE=/etc/system-inspector/integration.yaml"])
        arguments.append("integration")
        if upgrade:
            arguments.extend(["python", "tests/migrations/verify_populated_upgrade.py"])
        result = local.compose(
            *arguments,
            override=local.DEPLOY / f"inspector_test_{suffix}.compose.local.yaml",
            timeout=300,
        )
        print(result, end="")
        return 0
    finally:
        local.run = original


def checks() -> int:
    commands = [
        ("unit", ROOT, ["-m", "pytest", "backend/tests/unit", "-q"]),
        ("package", ROOT, ["-m", "unittest", "discover", "-s", "tests/package", "-q"]),
        ("package-validator", ROOT, ["tools/validate_package.py"]),
        ("schemas", ROOT, ["tools/validate_schemas.py"]),
        ("deployment", ROOT, ["tools/validate_deployment_examples.py"]),
        (
            "ruff",
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
        ("mypy", ROOT / "backend", ["-m", "mypy", "src"]),
        ("frontend-lint", ROOT, ["scripts/frontend.py", "lint"]),
        ("frontend-types", ROOT, ["scripts/frontend.py", "typecheck"]),
        ("generated-api", ROOT, ["scripts/frontend.py", "api:check"]),
        ("build", ROOT, ["scripts/build_stage1.py"]),
    ]
    results = []
    target = OUTPUT / "checks"
    target.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, PYTHONIOENCODING="utf-8")
    for name, directory, arguments in commands:
        argv = [sys.executable, *arguments]
        completed = subprocess.run(
            argv,
            cwd=directory,
            env=environment,
            capture_output=True,
            timeout=300,
            check=False,
        )
        (target / f"{name}.log").write_bytes(completed.stdout + completed.stderr)
        results.append(
            {"name": name, "argv": argv, "cwd": str(directory), "exit_code": completed.returncode}
        )
        print(f"{name}: exit {completed.returncode}", flush=True)
    (target / "commands.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return int(any(row["exit_code"] for row in results))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["checks", "integration", "upgrade"])
    parser.add_argument("--suffix", help="New disposable schema suffix; never reuse existing data")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    return (
        integration(args.suffix, upgrade=args.command == "upgrade")
        if args.command != "checks"
        else checks()
    )


if __name__ == "__main__":
    raise SystemExit(main())
