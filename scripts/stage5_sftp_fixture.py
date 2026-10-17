"""Local synthetic live log writer with a read-only SFTP interface.

Only the Docker-side test writer changes these generated files. SFTP clients
cannot write, execute commands, forward ports or access another filesystem.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from stage4_ssh_fixture import serve

ROOT = Path("/tmp/stage5-fixture")
LOGS = ROOT / "var/log/inspector-demo"


def line(source: int, text: str) -> bytes:
    return f"{datetime.now(UTC).isoformat(timespec='microseconds').replace('+00:00', 'Z')} source={source} {text}\n".encode()


def seed_content(source: int) -> bytes:
    return b"".join(
        line(
            source,
            f"seed={index} {'VISIBLE' if index % 3 == 0 else 'HIDDEN'} literal=.*[x] Straße",
        )
        for index in range(360)
    )


def reset_active() -> dict[str, object]:
    """Reset only the five generated logs; preserve the archive and SSH identity."""
    if not LOGS.is_dir() or LOGS.is_symlink():
        raise ValueError("The synthetic fixture root is unavailable.")
    paths = [LOGS / f"live-{source}.log" for source in range(5)]
    archive_path = LOGS / "source0.zip"
    for path in [*paths, archive_path]:
        if (
            path.is_symlink()
            or not path.is_file()
            or not stat.S_ISREG(path.stat().st_mode)
            or path.stat().st_size > 32 * 1024 * 1024
        ):
            raise ValueError("Unexpected synthetic file boundary.")
    archive_digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    files = []
    for source, path in enumerate(paths):
        before = path.stat().st_size
        content = seed_content(source)
        temporary = LOGS / f"reset-live-{source}-{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        files.append(
            {
                "source": source,
                "path": f"/var/log/inspector-demo/live-{source}.log",
                "before_bytes": before,
                "after_bytes": path.stat().st_size,
                "records": content.count(b"\n"),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != archive_digest:
        raise ValueError("The preserved synthetic archive changed.")
    return {
        "synthetic": True,
        "reset_at": datetime.now(UTC).isoformat(),
        "files": files,
        "archive_preserved_sha256": archive_digest,
        "archive_bytes": archive_path.stat().st_size,
    }


def append(source: int, text: str) -> None:
    if source not in range(5) or len(text) > 4096 or any(char in text for char in "\r\n\x00"):
        raise ValueError("Invalid synthetic append.")
    with (LOGS / f"live-{source}.log").open("ab") as stream:
        stream.write(line(source, text))


def append_batch(items_json: str, interval_ms: int) -> None:
    if len(items_json.encode("utf-8")) > 16_384 or not 100 <= interval_ms <= 1000:
        raise ValueError("Invalid synthetic append batch bounds.")
    items = json.loads(items_json)
    if not isinstance(items, list) or not 1 <= len(items) <= 16:
        raise ValueError("Synthetic append batch must contain 1–16 records.")
    for item in items:
        if not isinstance(item, dict) or set(item) != {"source", "text"}:
            raise ValueError("Invalid synthetic append batch record.")
        if (
            type(item["source"]) is not int
            or item["source"] not in range(4)
            or not isinstance(item["text"], str)
        ):
            raise ValueError("The fifth synthetic source must remain idle.")
        if len(item["text"]) > 512 or any(char in item["text"] for char in "\r\n\x00"):
            raise ValueError("Invalid synthetic append literal.")
    for index, item in enumerate(items):
        if index:
            time.sleep(interval_ms / 1000)
        append(item["source"], item["text"])


def burst(source: int, text: str, count: int) -> None:
    if (
        source not in range(5)
        or not 1 <= count <= 25_000
        or len(text) > 256
        or any(char in text for char in "\r\n\x00")
    ):
        raise ValueError("Invalid synthetic burst.")
    if count * len(line(source, text + f" burst_seq={count}")) > 8 * 1024 * 1024:
        raise ValueError("Synthetic burst byte limit exceeded.")
    with (LOGS / f"live-{source}.log").open("ab") as stream:
        for index in range(count):
            stream.write(line(source, text + f" burst_seq={index}"))


def archive() -> None:
    path = LOGS / "source0.zip"
    if not path.exists():
        with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(
                "logs/synthetic.log",
                b"".join(line(0, f"SYNTHETIC-ARCHIVE seq={index}") for index in range(20)),
            )


def capacity_archive() -> dict[str, object]:
    """Replace only the generated source0 ZIP with a bounded 16 MiB fixture."""
    if not LOGS.is_dir() or LOGS.is_symlink():
        raise ValueError("The synthetic fixture root is unavailable.")
    destination = LOGS / "source0.zip"
    if destination.exists() and (
        destination.is_symlink() or not stat.S_ISREG(destination.stat().st_mode)
    ):
        raise ValueError("The synthetic archive is not a regular file.")
    temporary = LOGS / f"capacity-{uuid4().hex}.zip.tmp"
    expected_bytes = 65_536 * 256
    digest = hashlib.sha256()
    try:
        with zipfile.ZipFile(
            temporary, "x", compression=zipfile.ZIP_STORED, allowZip64=False
        ) as bundle:
            member_info = zipfile.ZipInfo("logs/synthetic.log")
            member_info.create_system = 3
            member_info.external_attr = (stat.S_IFREG | 0o600) << 16
            member_info.compress_type = zipfile.ZIP_STORED
            with bundle.open(member_info, "w") as member:
                for index in range(65_536):
                    prefix = f"2026-10-16T12:00:00.{index:06d}Z source=0 SYNTHETIC-CAPACITY seq={index:05d} ".encode(
                        "ascii"
                    )
                    record = prefix + b"x" * (255 - len(prefix)) + b"\n"
                    assert len(record) == 256
                    digest.update(record)
                    member.write(record)
        with zipfile.ZipFile(temporary) as checked:
            members = checked.infolist()
            assert len(members) == 1
            assert members[0].filename == "logs/synthetic.log"
            assert members[0].file_size == expected_bytes
            assert members[0].compress_type == zipfile.ZIP_STORED
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "synthetic": True,
        "remote_path": "/var/log/inspector-demo/source0.zip",
        "member": "logs/synthetic.log",
        "records": 65_536,
        "line_bytes": 256,
        "expanded_bytes": expected_bytes,
        "archive_bytes": destination.stat().st_size,
        "compression": "ZIP_STORED",
        "uncompressed_sha256": digest.hexdigest(),
    }


async def run(args: argparse.Namespace) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    for source in range(5):
        path = LOGS / f"live-{source}.log"
        if not path.exists():
            path.write_bytes(seed_content(source))
    archive()
    args.role = "target"
    args.root = ROOT
    await serve(args)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    server = actions.add_parser("serve")
    server.add_argument("--key-file", type=Path, required=True)
    server.add_argument("--password-file", type=Path, required=True)
    server.add_argument("--username", default="synthetic-log-reader")
    server.add_argument("--port", type=int, default=8022)
    writer = actions.add_parser("append")
    writer.add_argument("--source", type=int, required=True, choices=range(5))
    writer.add_argument("--text", required=True)
    flood = actions.add_parser("burst")
    flood.add_argument("--source", type=int, required=True, choices=range(5))
    flood.add_argument("--text", required=True)
    flood.add_argument("--count", type=int, required=True)
    actions.add_parser("archive")
    actions.add_parser("capacity-archive")
    actions.add_parser("reset-active")
    paced = actions.add_parser("append-batch")
    paced.add_argument("--items-json", required=True)
    paced.add_argument("--interval-ms", type=int, default=250)
    args = parser.parse_args()
    if args.action == "append":
        append(args.source, args.text)
    elif args.action == "burst":
        burst(args.source, args.text, args.count)
    elif args.action == "archive":
        archive()
    elif args.action == "capacity-archive":
        print(json.dumps(capacity_archive()))
    elif args.action == "reset-active":
        print(json.dumps(reset_active()))
    elif args.action == "append-batch":
        append_batch(args.items_json, args.interval_ms)
    else:
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
