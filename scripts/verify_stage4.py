"""Record SSH setup checks against fresh disposable local MariaDB schemas.

This reuses the guarded Stage 03 runner and does not establish the full Stage 04
historical collection gate. No production endpoint is accepted.
"""

from __future__ import annotations

import argparse

import verify_stage3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["checks", "integration", "upgrade"])
    parser.add_argument("--suffix")
    args = parser.parse_args()
    verify_stage3.OUTPUT = verify_stage3.ROOT / "verification/stage-4"
    verify_stage3.OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.command in {"integration", "upgrade"}:
        return verify_stage3.integration(args.suffix, upgrade=args.command == "upgrade")
    return verify_stage3.checks()


if __name__ == "__main__":
    raise SystemExit(main())
