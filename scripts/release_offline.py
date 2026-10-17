"""Fail explicitly until Stage 08 offline release evidence exists."""

import sys

if __name__ == "__main__":
    print(
        "Offline release is not available: Stage 08 image, Linux lifecycle, backup/restore and security gates remain open.",
        file=sys.stderr,
    )
    raise SystemExit(1)
