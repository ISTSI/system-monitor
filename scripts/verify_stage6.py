"""Record Stage 06 checks against fresh, explicitly disposable local MariaDB."""

from __future__ import annotations

import argparse
import os
import secrets

import verify_stage3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["checks", "integration", "upgrade", "investigations", "core"]
    )
    parser.add_argument("--suffix", help="Fresh isolated schema suffix; never reuse one")
    parser.add_argument("--match", help="Optional pytest -k selection for investigation tests")
    args = parser.parse_args()
    os.environ["INSPECTOR_RUNNER_IMAGE"] = "system-inspector-runner:stage6"
    verify_stage3.OUTPUT = verify_stage3.ROOT / "verification/stage-6"
    verify_stage3.OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.command == "checks":
        return verify_stage3.checks()

    import local_mariadb as local

    original = local.compose

    def scoped(*arguments: str, **kwargs: object) -> str:
        # The complete regression includes the Stage 05 four-minute MariaDB/SSH
        # suite plus Stage 06 exchange/security/capacity cases.
        if args.command == "integration":
            kwargs["timeout"] = 720
        if (
            args.command == "upgrade"
            and "tests/migrations/verify_populated_upgrade.py" in arguments
        ):
            arguments = tuple(
                "tests/migrations/verify_stage6_upgrade.py"
                if value == "tests/migrations/verify_populated_upgrade.py"
                else value
                for value in arguments
            )
        elif args.command in {"investigations", "core"} and arguments[-1:] == ("integration",):
            arguments = (
                *arguments,
                "python",
                "-m",
                "pytest",
                "tests/integration/test_investigations.py",
                *(
                    (
                        "tests/integration/test_investigation_bundles.py",
                        "tests/integration/test_investigation_capacity.py",
                    )
                    if args.command == "investigations"
                    else ()
                ),
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
        prefix = "s6_upgrade_" if args.command == "upgrade" else "s6_"
        return verify_stage3.integration(
            args.suffix or prefix + secrets.token_hex(4), upgrade=args.command == "upgrade"
        )
    finally:
        local.compose = original


if __name__ == "__main__":
    raise SystemExit(main())
