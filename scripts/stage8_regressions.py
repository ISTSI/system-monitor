"""Rerun real MariaDB regressions in a fresh schema, preserving earlier evidence."""

from __future__ import annotations

import argparse
import os
import secrets

import local_mariadb as local
import verify_stage3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["integration", "foundation-upgrade", "upgrade", "optional-upgrade"]
    )
    parser.add_argument(
        "--suffix", help="Fresh disposable schema suffix; an existing schema is refused"
    )
    args = parser.parse_args()
    os.environ["INSPECTOR_RUNNER_IMAGE"] = "system-inspector-runner:stage7"
    verify_stage3.OUTPUT = local.ROOT / "verification/stage-8/regressions"
    verify_stage3.OUTPUT.mkdir(parents=True, exist_ok=True)
    original = local.compose

    def scoped(*arguments: str, **kwargs: object) -> str:
        kwargs["timeout"] = 900
        if args.command not in {"integration", "foundation-upgrade"}:
            target = (
                "tests/migrations/verify_optional_connection_upgrade.py"
                if args.command == "optional-upgrade"
                else "tests/migrations/verify_stage7_upgrade.py"
            )
            arguments = tuple(
                target if value == "tests/migrations/verify_populated_upgrade.py" else value
                for value in arguments
            )
        return original(*arguments, **kwargs)

    local.compose = scoped
    try:
        prefix = {
            "integration": "s8_",
            "foundation-upgrade": "s2_upgrade_",
            "upgrade": "s7_upgrade_",
            "optional-upgrade": "opt_upgrade_",
        }[args.command]
        return verify_stage3.integration(
            args.suffix or prefix + secrets.token_hex(4), upgrade=args.command != "integration"
        )
    finally:
        local.compose = original


if __name__ == "__main__":
    raise SystemExit(main())
