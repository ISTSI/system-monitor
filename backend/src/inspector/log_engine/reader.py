"""Bounded local capture parsing. No archive member is ever extracted to disk."""

from __future__ import annotations

import codecs
import fnmatch
import gzip
import hashlib
import io
import os
import re
import stat
import struct
import tarfile
import time
import zipfile
import zlib
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import IO, Any

from .core import (
    CancellationToken,
    EngineError,
    EngineLimits,
    LocalSource,
    ScanProgress,
    canonical_utc,
    event_id,
    extract_metadata,
    parse_timestamp,
)

_CHUNK = 64 * 1024
_NESTED = (".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar")
_ZIP_METADATA_LIMIT = 16 * 1024 * 1024


class _PinnedRaw(io.RawIOBase):
    """A seekable view ending at the source size observed before collection."""

    def __init__(self, handle: IO[bytes], boundary: int) -> None:
        self.handle = handle
        self.boundary = boundary

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.handle.tell()

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        position = offset
        if whence == io.SEEK_CUR:
            position += self.tell()
        elif whence == io.SEEK_END:
            position += self.boundary
        elif whence != io.SEEK_SET:
            raise ValueError("Invalid seek origin.")
        if position < 0:
            raise ValueError("Invalid negative seek position.")
        return self.handle.seek(position)

    def readinto(self, buffer: Any) -> int:
        maximum = max(0, min(len(buffer), self.boundary - self.tell()))
        data = self.handle.read(maximum)
        buffer[: len(data)] = data
        return len(data)


class _Budget:
    def __init__(
        self, limits: EngineLimits, cancellation: CancellationToken, progress: ScanProgress
    ) -> None:
        self.limits = limits
        self.cancellation = cancellation
        self.progress = progress
        self.deadline = time.monotonic() + limits.wall_seconds

    def check(self) -> None:
        self.cancellation.check()
        if time.monotonic() > self.deadline:
            raise EngineError("DEADLINE_EXCEEDED")

    def expanded(self, size: int) -> None:
        self.check()
        self.progress.expanded_bytes += size
        if self.progress.expanded_bytes > self.limits.max_expanded_bytes:
            raise EngineError("EXPANDED_BYTES_LIMIT")


def safe_archive_name(name: str) -> bool:
    return (
        bool(name)
        and len(name) <= 4096
        and not (
            name.startswith("/")
            or "\\" in name
            or re.match(r"^[a-zA-Z]:", name)
            or any(ord(char) < 32 or ord(char) == 127 for char in name)
            or ".." in PurePosixPath(name).parts
        )
    )


def _validate_member(
    name: str, size: int, is_directory: bool, seen: set[str], budget: _Budget
) -> None:
    budget.check()
    if not safe_archive_name(name):
        raise EngineError("UNSAFE_ARCHIVE_PATH")
    canonical = str(PurePosixPath(name))
    if canonical in seen:
        raise EngineError("DUPLICATE_ARCHIVE_MEMBER")
    seen.add(canonical)
    if len(seen) > budget.limits.max_members:
        raise EngineError("MEMBER_COUNT_LIMIT")
    if size < 0 or size > budget.limits.max_member_bytes:
        raise EngineError("MEMBER_BYTES_LIMIT")
    if not is_directory and name.casefold().endswith(_NESTED):
        raise EngineError("NESTED_ARCHIVE_UNSUPPORTED")


def _selected(source: LocalSource, name: str, ordinal: int) -> bool:
    if source.archive_member is not None and name != source.archive_member:
        return False
    if source.member_ordinal is not None and ordinal != source.member_ordinal:
        return False
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in source.member_globs)


def _physical_lines(
    handle: IO[bytes], budget: _Budget, *, member: bool
) -> Iterator[tuple[int, int, bytes, str, bool, bool]]:
    """Yield offsets, bounded text bytes, full physical-byte hash and status flags."""
    offset = 0
    member_start = budget.progress.expanded_bytes
    while True:
        budget.check()
        part = handle.readline(budget.limits.max_line_bytes + 1)
        if not part:
            return
        start = offset
        digest = hashlib.sha256()
        length = 0
        preview = bytearray()
        terminated = False
        while part:
            budget.expanded(len(part))
            if (
                member
                and budget.progress.expanded_bytes - member_start > budget.limits.max_member_bytes
            ):
                raise EngineError("MEMBER_BYTES_LIMIT")
            length += len(part)
            offset += len(part)
            digest.update(part)
            if len(preview) < budget.limits.max_line_bytes:
                preview.extend(part[: budget.limits.max_line_bytes - len(preview)])
            terminated = part.endswith(b"\n")
            if terminated:
                break
            budget.check()
            part = handle.readline(min(_CHUNK, budget.limits.max_line_bytes + 1))
        oversized = length > budget.limits.max_line_bytes
        content = bytes(preview)
        if not oversized and terminated:
            content = content[:-1]
            if content.endswith(b"\r"):
                content = content[:-1]
        yield start, offset, content, digest.hexdigest(), oversized, terminated
        if not terminated:
            return


def _events(
    handle: IO[bytes],
    source: LocalSource,
    member: str | None,
    ordinal: int | None,
    budget: _Budget,
    received_at: str,
) -> Iterator[dict[str, Any]]:
    member_start = budget.progress.expanded_bytes
    for number, (start, end, data, checksum, oversized, terminated) in enumerate(
        _physical_lines(handle, budget, member=member is not None), 1
    ):
        if (
            member is not None
            and budget.progress.expanded_bytes - member_start > budget.limits.max_member_bytes
        ):
            raise EngineError("MEMBER_BYTES_LIMIT")
        try:
            text = data.decode(source.encoding, errors="strict")
            decode_error = False
        except UnicodeDecodeError:
            text = data.decode(source.encoding, errors="replace")
            decode_error = True
        parsed = parse_timestamp(text, source.parser)
        metadata = {} if oversized else extract_metadata(text, source.correlation_markers)
        parse_status = "ok"
        if oversized:
            parse_status = "oversized_line"
            metadata["preview_truncated"] = "true"
        elif decode_error:
            parse_status = "decode_error"
        elif parsed.micros is None:
            parse_status = "invalid_timestamp"
        elif not terminated:
            parse_status = "incomplete_final_line"
        # A partial preview cannot establish either a positive or negative full-line predicate.
        timestamp_us = None if oversized or decode_error else parsed.micros
        budget.progress.events += 1
        if budget.progress.events > budget.limits.max_events:
            raise EngineError("EVENT_COUNT_LIMIT")
        if parse_status != "ok":
            budget.progress.diagnostic_events += 1
        yield {
            "schema_version": "1.0",
            "event_id": event_id(
                source.process_id, source.source_revision_id, member, ordinal, start, end
            ),
            "project_id": source.project_id,
            "process_id": source.process_id,
            "server_id": source.server_id,
            "process_name_snapshot": source.process_name or source.process_id,
            "server_name_snapshot": source.server_name or source.server_id,
            "raw_line": text,
            "timestamp_original": parsed.original,
            "timestamp_utc": parsed.utc if timestamp_us is not None else None,
            "timestamp_us": timestamp_us,
            "received_at": received_at,
            "parse_status": parse_status,
            "metadata": metadata,
            "source": {
                "source_revision_id": source.source_revision_id,
                "remote_path": source.remote_path,
                "archive_member": member,
                "member_ordinal": ordinal,
                "byte_start": start,
                "byte_end": end,
                "line_number": number,
                "content_sha256": checksum,
            },
        }


def _zip_preflight(handle: IO[bytes], budget: _Budget) -> None:
    """Bound the central-directory allocation performed by ZipFile's constructor.

    EOCD counts are untrusted: also walk fixed-size central headers without allocating
    filename/extra/comment payloads, before allowing ZipFile to build its member list.
    """
    budget.check()
    handle.seek(0, io.SEEK_END)
    length = handle.tell()
    tail_size = min(length, 65_535 + 22)
    handle.seek(length - tail_size)
    tail = handle.read(tail_size)
    position = tail.rfind(b"PK\x05\x06")
    if position < 0 or len(tail) - position < 22:
        raise EngineError("CORRUPT_ARCHIVE")
    disk, directory_disk, disk_count, total_count, metadata_bytes, directory_offset, comment = (
        struct.unpack_from("<HHHHIIH", tail, position + 4)
    )
    if len(tail) - position != 22 + comment:
        raise EngineError("CORRUPT_ARCHIVE")
    if 65_535 in (disk_count, total_count) or 4_294_967_295 in (metadata_bytes, directory_offset):
        raise EngineError("ZIP64_UNSUPPORTED")
    if disk != 0 or directory_disk != 0 or disk_count != total_count:
        raise EngineError("MULTIVOLUME_ARCHIVE_UNSUPPORTED")
    if total_count > budget.limits.max_members:
        raise EngineError("MEMBER_COUNT_LIMIT")
    if metadata_bytes > _ZIP_METADATA_LIMIT:
        raise EngineError("ARCHIVE_METADATA_LIMIT")
    end = length - tail_size + position
    beginning = end - metadata_bytes
    if beginning < 0 or directory_offset > beginning:
        raise EngineError("CORRUPT_ARCHIVE")
    handle.seek(beginning)
    actual_count = 0
    while handle.tell() < end:
        budget.check()
        header = handle.read(46)
        if len(header) != 46 or header[:4] != b"PK\x01\x02":
            raise EngineError("CORRUPT_ARCHIVE")
        name_size, extra_size, comment_size = struct.unpack_from("<HHH", header, 28)
        actual_count += 1
        if actual_count > budget.limits.max_members:
            raise EngineError("MEMBER_COUNT_LIMIT")
        following = handle.tell() + name_size + extra_size + comment_size
        if following > end:
            raise EngineError("CORRUPT_ARCHIVE")
        handle.seek(following)
    if actual_count != total_count or handle.tell() != end:
        raise EngineError("CORRUPT_ARCHIVE")
    handle.seek(0)


def _zip(
    handle: IO[bytes], source: LocalSource, budget: _Budget, received_at: str
) -> Iterator[dict[str, Any]]:
    _zip_preflight(handle, budget)
    with zipfile.ZipFile(handle) as archive:
        members = archive.infolist()
        if len(members) > budget.limits.max_members:
            raise EngineError("MEMBER_COUNT_LIMIT")
        seen: set[str] = set()
        total_declared = 0
        for info in members:
            if info.orig_filename != info.filename:
                raise EngineError("UNSAFE_ARCHIVE_PATH")
            mode = (info.external_attr >> 16) & 0xFFFF
            is_directory = info.is_dir() or stat.S_ISDIR(mode)
            _validate_member(info.filename, info.file_size, is_directory, seen, budget)
            if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise EngineError("UNSAFE_ARCHIVE_MEMBER_TYPE")
            if info.flag_bits & 1:
                raise EngineError("ENCRYPTED_ARCHIVE_UNSUPPORTED")
            if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise EngineError("COMPRESSION_UNSUPPORTED")
            if info.file_size > max(1, info.compress_size) * budget.limits.max_compression_ratio:
                raise EngineError("COMPRESSION_RATIO_LIMIT")
            total_declared += info.file_size
            if total_declared > budget.limits.max_expanded_bytes:
                raise EngineError("EXPANDED_BYTES_LIMIT")
        budget.progress.members = len(members)
        selected = False
        for ordinal, info in enumerate(members):
            if info.is_dir() or stat.S_ISDIR((info.external_attr >> 16) & 0xFFFF):
                continue
            if _selected(source, info.filename, ordinal):
                selected = True
                with archive.open(info) as content:
                    before = budget.progress.expanded_bytes
                    yield from _events(content, source, info.filename, ordinal, budget, received_at)
                    actual = budget.progress.expanded_bytes - before
                    if actual > max(1, info.compress_size) * budget.limits.max_compression_ratio:
                        raise EngineError("COMPRESSION_RATIO_LIMIT")
            else:
                # Validate checksums and actual expansion of ignored members as well.
                with archive.open(info) as content:
                    actual = 0
                    while chunk := content.read(_CHUNK):
                        budget.expanded(len(chunk))
                        actual += len(chunk)
                        if actual > budget.limits.max_member_bytes:
                            raise EngineError("MEMBER_BYTES_LIMIT")
                        if (
                            actual
                            > max(1, info.compress_size) * budget.limits.max_compression_ratio
                        ):
                            raise EngineError("COMPRESSION_RATIO_LIMIT")
        if not selected and (
            source.archive_member is not None or source.member_ordinal is not None
        ):
            raise EngineError("ARCHIVE_MEMBER_UNAVAILABLE")


class _ExpandedTar(io.RawIOBase):
    """Count actual gzip output, including skipped TAR payloads and padding."""

    def __init__(self, stream: gzip.GzipFile, budget: _Budget, compressed_size: int) -> None:
        self.stream = stream
        self.budget = budget
        self.compressed_size = compressed_size
        self.actual = 0

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        self.budget.check()
        data = self.stream.read(_CHUNK if size < 0 else min(size, _CHUNK))
        self.actual += len(data)
        # TAR headers count toward expansion safety, but progress records member bytes separately.
        if self.actual > self.budget.limits.max_expanded_bytes:
            raise EngineError("EXPANDED_BYTES_LIMIT")
        if self.actual > max(1, self.compressed_size) * self.budget.limits.max_compression_ratio:
            raise EngineError("COMPRESSION_RATIO_LIMIT")
        return data


def _bounded_tarinfo(budget: _Budget) -> type[tarfile.TarInfo]:
    """Guard TAR extension payloads before tarfile reads them into memory."""
    metadata_bytes = 0
    metadata_count = 0

    class BoundedTarInfo(tarfile.TarInfo):
        def _proc_member(self, archive: tarfile.TarFile) -> tarfile.TarInfo:
            nonlocal metadata_bytes, metadata_count
            budget.check()
            if self.type == tarfile.GNUTYPE_SPARSE:
                raise EngineError("UNSAFE_ARCHIVE_MEMBER_TYPE")
            if self.type in {
                tarfile.GNUTYPE_LONGNAME,
                tarfile.GNUTYPE_LONGLINK,
                tarfile.XHDTYPE,
                tarfile.XGLTYPE,
                tarfile.SOLARIS_XHDTYPE,
            }:
                metadata_count += 1
                metadata_bytes += self.size
                if (
                    self.size < 0
                    or metadata_bytes > min(_CHUNK, budget.limits.max_member_bytes)
                    or metadata_count > min(20, budget.limits.max_members)
                ):
                    raise EngineError("ARCHIVE_METADATA_LIMIT")
            # typeshed omits this standard-library extension hook; guarding it prevents
            # tarfile's PAX/GNU implementation from allocating unbounded header payloads.
            return super()._proc_member(archive)  # type: ignore[misc]

    return BoundedTarInfo


def _tar_pass(
    handle: IO[bytes],
    source: LocalSource,
    budget: _Budget,
    received_at: str,
    compressed_size: int,
    *,
    validate: bool,
) -> Iterator[dict[str, Any]]:
    handle.seek(0)
    with gzip.GzipFile(fileobj=handle, mode="rb") as decompressed:
        guarded = _ExpandedTar(decompressed, budget, compressed_size)
        with tarfile.open(fileobj=guarded, mode="r|", tarinfo=_bounded_tarinfo(budget)) as archive:
            seen: set[str] = set()
            selected = False
            total_declared = 0
            for ordinal, info in enumerate(archive):
                _validate_member(info.name, info.size, info.isdir(), seen, budget)
                if (
                    not info.isfile()
                    and not info.isdir()
                    or info.issparse()
                    or any(key.startswith("GNU.sparse") for key in info.pax_headers)
                ):
                    raise EngineError("UNSAFE_ARCHIVE_MEMBER_TYPE")
                total_declared += info.size
                if total_declared > budget.limits.max_expanded_bytes:
                    raise EngineError("EXPANDED_BYTES_LIMIT")
                if validate or not info.isfile():
                    continue
                content = archive.extractfile(info)
                if content is None:
                    raise EngineError("ARCHIVE_MEMBER_UNAVAILABLE")
                with content:
                    if _selected(source, info.name, ordinal):
                        selected = True
                        yield from _events(content, source, info.name, ordinal, budget, received_at)
                    else:
                        actual = 0
                        while chunk := content.read(_CHUNK):
                            budget.expanded(len(chunk))
                            actual += len(chunk)
                            if actual > budget.limits.max_member_bytes:
                                raise EngineError("MEMBER_BYTES_LIMIT")
            if validate:
                budget.progress.members = len(seen)
            elif not selected and (
                source.archive_member is not None or source.member_ordinal is not None
            ):
                raise EngineError("ARCHIVE_MEMBER_UNAVAILABLE")
        # Force checksum/truncation verification, including bytes following the TAR end marker.
        while guarded.read(_CHUNK):
            pass


def iter_source_events(
    source: LocalSource,
    limits: EngineLimits | None = None,
    cancellation: CancellationToken | None = None,
    progress: ScanProgress | None = None,
    received_at: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Parse a pre-authorized local capture, retaining physical identity and explicit errors.

    The caller authorizes project/owner and generates cache paths. This function never resolves
    browser paths, acquires SSH, edits sources, or imports fixture-oracle business logic.
    """
    state = progress if progress is not None else ScanProgress()
    budget = _Budget(limits or EngineLimits(), cancellation or CancellationToken(), state)
    received = received_at or canonical_utc(datetime.now(UTC))
    try:
        encoding = codecs.lookup(source.encoding)
        # Byte-oriented log records require an ASCII-compatible newline representation.
        if "\n".encode(encoding.name) != b"\n" or "\r".encode(encoding.name) != b"\r":
            raise EngineError("ENCODING_UNSUPPORTED")
        if source.path.is_symlink():
            raise EngineError("UNSAFE_LOCAL_SOURCE")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(source.path, flags), "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise EngineError("UNSAFE_LOCAL_SOURCE")
            if before.st_size > budget.limits.max_download_bytes:
                raise EngineError("DOWNLOAD_BYTES_LIMIT")
            digest = hashlib.sha256()
            while chunk := handle.read(min(_CHUNK, before.st_size - state.downloaded_bytes + 1)):
                budget.check()
                state.downloaded_bytes += len(chunk)
                if state.downloaded_bytes > before.st_size:
                    state.source_stable = False
                    raise EngineError("SOURCE_UNSTABLE")
                digest.update(chunk)
            state.source_sha256 = digest.hexdigest()
            handle.seek(0)
            with io.BufferedReader(_PinnedRaw(handle, before.st_size), _CHUNK) as snapshot:
                if source.kind == "plain":
                    yield from _events(snapshot, source, None, None, budget, received)
                elif source.kind == "zip":
                    yield from _zip(snapshot, source, budget, received)
                else:
                    # Validate all metadata before exposing a first event from the archive.
                    yield from _tar_pass(
                        snapshot, source, budget, received, before.st_size, validate=True
                    )
                    yield from _tar_pass(
                        snapshot, source, budget, received, before.st_size, validate=False
                    )
            after = os.fstat(handle.fileno())
            current = source.path.stat(follow_symlinks=False)
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ino,
            ) or current.st_ino != before.st_ino:
                state.source_stable = False
                raise EngineError("SOURCE_UNSTABLE")
            state.source_complete = True
    except EngineError:
        raise
    except LookupError:
        raise EngineError("ENCODING_UNSUPPORTED") from None
    except (
        zipfile.BadZipFile,
        tarfile.TarError,
        gzip.BadGzipFile,
        zlib.error,
        EOFError,
        RuntimeError,
    ):
        raise EngineError("CORRUPT_ARCHIVE") from None
    except OSError:
        raise EngineError("SOURCE_UNAVAILABLE") from None
