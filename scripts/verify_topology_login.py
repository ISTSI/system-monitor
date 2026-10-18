"""Verify the topology/login follow-up against fresh local MariaDB schemas."""

import argparse
import os
import secrets

import verify_stage3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["integration", "upgrade"])
    args = parser.parse_args()
    os.environ["INSPECTOR_RUNNER_IMAGE"] = "system-inspector-runner:stage7"
    verify_stage3.OUTPUT = verify_stage3.ROOT / "verification/topology-login"
    verify_stage3.OUTPUT.mkdir(parents=True, exist_ok=True)
    import local_mariadb as local

    original = local.compose

    def scoped(*arguments, **kwargs):
        if args.command == "upgrade":
            arguments = tuple(
                "tests/migrations/verify_remember_login_upgrade.py"
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
                "tests/integration/test_remember_login.py",
                "tests/integration/test_foundation.py",
                "tests/integration/test_accounts.py",
                "tests/integration/test_topology.py",
                "tests/integration/test_ssh_revocation.py",
                "tests/integration/test_investigation_bundles.py",
                "-v",
                "-rs",
                "-p",
                "no:cacheprovider",
            )
            kwargs["timeout"] = 600
        return original(*arguments, **kwargs)

    local.compose = scoped
    try:
        prefix = "rem_upgrade_" if args.command == "upgrade" else "login_"
        return verify_stage3.integration(
            prefix + secrets.token_hex(3), upgrade=args.command == "upgrade"
        )
    finally:
        local.compose = original


if __name__ == "__main__":
    raise SystemExit(main())
