"""Flat, generated capture directories; never recursively follow cache entries."""

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from inspector.errors import DomainError


def unsafe_cache() -> DomainError:
    return DomainError("UNSAFE_CACHE_PATH", "The retained cache path is unsafe to delete.", 409)


def checked_stat(path: Path) -> os.stat_result:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or (
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        raise unsafe_cache()
    return metadata


def checked_directory(path: Path, cache_root: Path) -> bool:
    """Validate lexical containment and every existing ancestor without resolving links."""
    root, directory = cache_root.absolute(), path.absolute()
    if (
        ".." in directory.parts
        or ".." in root.parts
        or not directory.is_relative_to(root)
        or directory == root
    ):
        raise unsafe_cache()
    for ancestor in reversed((directory, *directory.parents)):
        try:
            metadata = checked_stat(ancestor)
        except FileNotFoundError:
            return False
        if not stat.S_ISDIR(metadata.st_mode):
            raise unsafe_cache()
    return True


def checked_files(directory: Path, maximum_entries: int) -> list[Path]:
    result: list[Path] = []
    with os.scandir(directory) as entries:
        for entry in entries:
            if len(result) >= maximum_entries:
                raise unsafe_cache()
            path = Path(entry.path)
            if not stat.S_ISREG(checked_stat(path).st_mode):
                raise unsafe_cache()
            result.append(path)
    return result


@dataclass(frozen=True)
class StagedCache:
    original: Path
    detached: Path
    root: Path
    maximum_entries: int

    def restore(self) -> None:
        if not checked_directory(self.detached, self.root) or self.original.exists():
            raise unsafe_cache()
        self.detached.rename(self.original)

    def remove(self) -> None:
        if not checked_directory(self.detached, self.root):
            return
        for path in checked_files(self.detached, self.maximum_entries):
            # Recheck immediately before unlink; do not traverse directories.
            if not stat.S_ISREG(checked_stat(path).st_mode):
                raise unsafe_cache()
            path.unlink()
        self.detached.rmdir()


def stage_cache(
    directory: Path, cache_root: Path, maximum_entries: int = 2000
) -> StagedCache | None:
    if not checked_directory(directory, cache_root):
        return None
    checked_files(directory, maximum_entries)
    detached = directory.with_name("deleted-" + str(uuid4()))
    directory.rename(detached)
    return StagedCache(directory, detached, cache_root, maximum_entries)


def read_download_chunk(path: Path, cache_root: Path, offset: int) -> bytes:
    if not checked_directory(path.parent, cache_root) or not stat.S_ISREG(
        checked_stat(path).st_mode
    ):
        raise unsafe_cache()
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    )
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise unsafe_cache()
        stream.seek(offset)
        return stream.read(65_536)
