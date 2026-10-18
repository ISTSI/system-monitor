"""Record Stage 07 checks against fresh, explicitly disposable local MariaDB."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys

import verify_stage3


def checks() -> int:
    root = verify_stage3.ROOT
    commands = [
        ("unit", root, ["-m", "pytest", "backend/tests/unit", "-q"]),
        ("package", root, ["-m", "unittest", "discover", "-s", "tests/package", "-q"]),
        ("package-validator", root, ["tools/validate_package.py"]),
        ("schemas", root, ["tools/validate_schemas.py"]),
        ("deployment", root, ["tools/validate_deployment_examples.py"]),
        (
            "ruff",
            root,
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
            root,
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
        ("mypy", root / "backend", ["-m", "mypy", "src"]),
        ("frontend-lint", root, ["scripts/frontend.py", "lint"]),
        ("frontend-types", root, ["scripts/frontend.py", "typecheck"]),
        ("frontend-tests-api", root, ["scripts/frontend.py", "test"]),
        ("artifact", root, ["scripts/verify_stage7_build.py"]),
    ]
    output = verify_stage3.OUTPUT / "checks"
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for name, directory, arguments in commands:
        argv = [sys.executable, *arguments]
        result = subprocess.run(
            argv,
            cwd=directory,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            capture_output=True,
            timeout=300,
            check=False,
        )
        (output / f"{name}.log").write_bytes(result.stdout + result.stderr)
        records.append(dict(name=name, argv=argv, cwd=str(directory), exit_code=result.returncode))
        print(f"{name}: exit {result.returncode}", flush=True)
    (output / "commands.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return int(any(row["exit_code"] for row in records))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["checks", "integration", "upgrade", "inventory"])
    parser.add_argument("--suffix", help="Fresh isolated schema suffix; never reuse one")
    parser.add_argument("--match", help="Optional pytest -k selection for investigation tests")
    args = parser.parse_args()
    os.environ["INSPECTOR_RUNNER_IMAGE"] = "system-inspector-runner:stage7"
    verify_stage3.OUTPUT = verify_stage3.ROOT / "verification/stage-7"
    verify_stage3.OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.command == "checks":
        return checks()

    import local_mariadb as local

    original = local.compose

    def scoped(*arguments: str, **kwargs: object) -> str:
        # The complete regression includes the Stage 05 four-minute MariaDB/SSH
        # suite plus Stage 07 exchange/security/capacity cases.
        if args.command == "integration":
            kwargs["timeout"] = 720
        if (
            args.command == "upgrade"
            and "tests/migrations/verify_populated_upgrade.py" in arguments
        ):
            arguments = tuple(
                "tests/migrations/verify_stage7_upgrade.py"
                if value == "tests/migrations/verify_populated_upgrade.py"
                else value
                for value in arguments
            )
        elif args.command == "inventory" and arguments[-1:] == ("integration",):
            arguments = (
                *arguments,
                "python",
                "-m",
                "pytest",
                "tests/integration/test_inventory.py",
                "tests/integration/test_diagnostics.py",
                "-v",
                "-rs",
                "-s",
                "-p",
                "no:cacheprovider",
                *(("-k", args.match) if args.match else ()),
            )
        return original(*arguments, **kwargs)

    local.compose = scoped
    try:
        prefix = "s7_upgrade_" if args.command == "upgrade" else "s7_"
        return verify_stage3.integration(
            args.suffix or prefix + secrets.token_hex(4), upgrade=args.command == "upgrade"
        )
    finally:
        local.compose = original


if __name__ == "__main__":
    raise SystemExit(main())
