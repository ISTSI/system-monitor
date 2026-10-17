#!/usr/bin/env python3
"""Generate fresh local deployment secrets; never overwrite or print their values.

Only the standard library is used. This script does not contact Docker, databases,
networks or monitored hosts. File permissions assume a Linux deployment host.
"""
from __future__ import annotations
import argparse
import base64
import os
from pathlib import Path
import secrets
import stat
import sys

NAMES = ("inspector_db_root_password", "inspector_db_migration_password", "inspector_db_password", "inspector_vault_key")

def prepare(output: Path) -> list[str]:
    if os.name != "posix":
        raise ValueError("Run on Linux or a POSIX deployment staging host; Windows ACLs need separate provisioning")
    if output.is_symlink():
        raise ValueError("Secret directory must not be a symlink")
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise ValueError("Use a new or empty secret directory; existing secrets are never replaced")
        if stat.S_IMODE(output.stat().st_mode) != 0o700:
            raise ValueError("Existing secret directory must have mode 0700")
    else:
        output.mkdir(mode=0o700, parents=False)
    values = [secrets.token_hex(32) for _ in range(3)]
    values.append(base64.b64encode(secrets.token_bytes(32)).decode("ascii"))
    created = []
    for name, value in zip(NAMES, values, strict=True):
        path = output / name
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(value + "\n")
        # Local Compose secrets are bind-mounted files; uid/mode remapping is
        # not assumed. 0700 parent protects host access; only authorized
        # containers receive a read-only mount of the individual 0444 file.
        path.chmod(0o444)
        created.append(name)
    return created

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("secrets"))
    args = parser.parse_args()
    try:
        names = prepare(args.output_dir)
    except (OSError, ValueError) as exc:
        print(f"Cannot provision secrets: {exc}", file=sys.stderr)
        return 1
    print(f"Created {len(names)} secret files in {args.output_dir}; values are not displayed.")
    print("Keep the directory private (0700); see README.md for mounts, backup and rotation.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
