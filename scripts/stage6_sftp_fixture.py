"""Serve only copied synthetic golden logs through the read-only SFTP fixture."""

from __future__ import annotations

import argparse
import asyncio
import shutil
from pathlib import Path

from stage4_ssh_fixture import serve

ROOT = Path("/tmp/stage6-fixture")
FIXTURES = Path("/workspace/fixtures/logs")


def prepare() -> None:
    if ROOT.exists():
        raise ValueError("The synthetic fixture root already exists.")
    destination = ROOT / "var/log/inspector-demo"
    destination.mkdir(parents=True)
    for name in ("ingest", "parser", "router", "delivery", "audit"):
        source = FIXTURES / name
        target = destination / name
        target.mkdir()
        for path in source.iterdir():
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_048_576:
                raise ValueError("Unexpected synthetic fixture file boundary.")
            shutil.copyfile(path, target / path.name)


async def run(args: argparse.Namespace) -> None:
    await asyncio.to_thread(prepare)
    args.role = "target"
    args.root = ROOT
    await serve(args)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["serve"])
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--username", default="synthetic-log-reader")
    parser.add_argument("--port", type=int, default=8022)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
