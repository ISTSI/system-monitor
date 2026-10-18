"""Verify optional server connections using fresh isolated local MariaDB schemas."""

import argparse
import os
import secrets

import verify_stage3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["integration", "upgrade"])
    args = parser.parse_args()
    os.environ["INSPECTOR_RUNNER_IMAGE"] = "system-inspector-runner:stage7"
    verify_stage3.OUTPUT = verify_stage3.ROOT / "verification/optional-connections"
    verify_stage3.OUTPUT.mkdir(parents=True, exist_ok=True)
    import local_mariadb as local

    original = local.compose

    def scoped(*arguments, **kwargs):
        if args.command == "upgrade":
            arguments = tuple(
                "tests/migrations/verify_optional_connection_upgrade.py"
                if value == "tests/migrations/verify_populated_upgrade.py"
                else value
                for value in arguments
            )
        elif arguments[-1:] == ("integration",):
            arguments = (
                *arguments,
                "python",
                "-m",
                "pytest",
                "tests/integration/test_optional_connection.py",
                "tests/integration/test_topology.py",
                "tests/integration/test_history.py",
                "tests/integration/test_live.py",
                "-v",
                "-rs",
                "-p",
                "no:cacheprovider",
            )
            kwargs["timeout"] = 600
        return original(*arguments, **kwargs)

    local.compose = scoped
    try:
        prefix = "opt_upgrade_" if args.command == "upgrade" else "optional_"
        return verify_stage3.integration(
            prefix + secrets.token_hex(3), upgrade=args.command == "upgrade"
        )
    finally:
        local.compose = original


if __name__ == "__main__":
    raise SystemExit(main())
