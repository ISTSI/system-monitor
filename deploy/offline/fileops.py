#!/usr/bin/env python3
"""Private bounded backup file copying; no archive extraction or remote access."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath

MAX_BYTES = 64 * 1024**3
MAX_FILES = 200_000


def relative(value: str) -> Path:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or ":" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("Unsafe backup member path")
    return Path(*path.parts)


def regular(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Backup permits regular, singly linked files only")


def digest(path: Path) -> str:
    regular(path)
    result = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            count += len(chunk)
            if count > MAX_BYTES:
                raise ValueError("File exceeds backup byte limit")
            result.update(chunk)
    return result.hexdigest()


def copy_file(source: Path, destination: Path, budget: int) -> int:
    regular(source)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    written = 0
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with source.open("rb") as reader, os.fdopen(descriptor, "wb") as writer:
        while chunk := reader.read(1024 * 1024):
            written += len(chunk)
            if written > budget:
                raise ValueError("Backup byte limit exceeded")
            writer.write(chunk)
    return written


def snapshot(data: Path, target: Path) -> list[dict]:
    records = []
    total = 0
    for namespace in ("state", "cache"):
        root = data / namespace
        if root.is_symlink() or not root.is_dir():
            raise ValueError("Unsafe application data directory")
        for directory, directories, files in os.walk(root, followlinks=False):
            for name in sorted(directories):
                if (Path(directory) / name).is_symlink():
                    raise ValueError("Symlink in application state")
            for name in sorted(files):
                source = Path(directory) / name
                if namespace == "state" and source == root / "ssh-vault.key":
                    # The raw master key is separate recovery material.
                    continue
                member = "files/" + namespace + "/" + source.relative_to(root).as_posix()
                destination = target / relative(member)
                size = copy_file(source, destination, MAX_BYTES - total)
                total += size
                records.append(dict(path=member, bytes=size, sha256=digest(destination)))
                if len(records) > MAX_FILES:
                    raise ValueError("Backup file count exceeded")
    return records


def verify(backup: Path) -> dict:
    if backup.is_symlink() or not backup.is_dir():
        raise ValueError("Backup must be a real directory")
    regular(backup / "backup.json")
    if (backup / "backup.json").stat().st_size > 32 * 1024**2:
        raise ValueError("Backup manifest exceeds limit")
    metadata = json.loads((backup / "backup.json").read_text(encoding="utf-8"))
    if metadata.get("format") != "system-inspector-backup-1":
        raise ValueError("Unsupported backup manifest")
    entries = metadata.get("files")
    if not isinstance(entries, list) or len(entries) > MAX_FILES + 3:
        raise ValueError("Backup file count exceeded")
    expected = {"backup.json"}
    total = 0
    for record in entries:
        member = record["path"]
        relative(member)
        if member == "files/state/ssh-vault.key":
            raise ValueError("Vault key must not be included in a data backup")
        if member in expected or not (
            member in {"database.sql", "database-metadata.txt", "policy.json"}
            or member.startswith("files/state/")
            or member.startswith("files/cache/")
        ):
            raise ValueError("Unexpected or duplicated backup member")
        expected.add(member)
        path = backup / relative(member)
        for parent in path.parents:
            if parent == backup:
                break
            if parent.is_symlink():
                raise ValueError("Symlink in backup path")
        regular(path)
        size = path.stat().st_size
        total += size
        if total > MAX_BYTES or size != record["bytes"] or digest(path) != record["sha256"]:
            raise ValueError("Backup size or checksum mismatch")
    if not {"database.sql", "database-metadata.txt", "policy.json"} <= expected:
        raise ValueError("Backup is incomplete")
    for directory, directories, files in os.walk(backup, followlinks=False):
        if any((Path(directory) / name).is_symlink() for name in directories):
            raise ValueError("Symlink in backup")
        for name in files:
            if (Path(directory) / name).relative_to(backup).as_posix() not in expected:
                raise ValueError("Unlisted file in backup")
    return metadata


def restore(backup: Path, data: Path) -> None:
    metadata = verify(backup)
    for namespace in ("state", "cache"):
        root = data / namespace
        if root.is_symlink() or not root.is_dir() or any(root.iterdir()):
            raise ValueError("Restore requires empty state and cache directories")
    total = 0
    for record in metadata["files"]:
        if record["path"].startswith("files/"):
            source = backup / relative(record["path"])
            destination = data / relative(record["path"][len("files/") :])
            total += copy_file(source, destination, MAX_BYTES - total)
    own(data)


def own(data: Path) -> None:
    for namespace in ("state", "cache"):
        root = data / namespace
        if root.is_symlink():
            raise ValueError("Data directory must not be a symlink")
        for directory, directories, files in os.walk(root, followlinks=False):
            if any((Path(directory) / name).is_symlink() for name in directories + files):
                raise ValueError("Data contains a symlink")
            os.chown(directory, 10001, 10001)
            os.chmod(directory, 0o700)
            for name in files:
                path = Path(directory) / name
                regular(path)
                os.chown(path, 10001, 10001)
                os.chmod(path, 0o600)


def bind_key(data: Path, key: Path) -> None:
    regular(key)
    raw = key.read_bytes()
    if len(raw) != 32:
        raise ValueError("Vault recovery key must contain exactly 32 raw bytes")
    destination = data / "state/ssh-vault.key"
    if destination.exists() or destination.is_symlink():
        regular(destination)
        destination.unlink()
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
    os.chown(destination, 10001, 10001)
    os.chmod(destination, 0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["snapshot", "restore", "own", "bind-key"])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--key", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "snapshot":
        records = snapshot(args.data, args.backup)
        print(json.dumps(records))
    elif args.action == "restore":
        restore(args.backup, args.data)
    elif args.action == "bind-key":
        bind_key(args.data, args.key)
    else:
        own(args.data)


if __name__ == "__main__":
    main()
