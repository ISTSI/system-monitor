"""Bounded configured-file planning and read-only SFTP snapshot retrieval.

Authorization belongs to the calling service: an operation must be bound to its
project, owner, configuration revision and current target/root approval. Reuse is
limited to that operation; no route or capture is cached here. SFTP v3 does not
offer a portable atomic open-beneath/inode contract. Component lstat, realpath,
handle stat and bounded content probes detect observed changes, but cannot prove
absence of every concurrent same-size rewrite. Dedicated read-only account
permissions remain a required boundary and captures carry that limitation.
"""

import asyncio
import fnmatch
import hashlib
import json
import posixpath
import stat
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from typing import Any, BinaryIO

import asyncssh

from inspector.errors import DomainError
from inspector.ssh_transport import Endpoint, sftp_session

_BLOCK_BYTES = 65_536
_PROBE_BYTES = 4096
_GLOB_CHARS = "*?["


@dataclass(frozen=True)
class RemoteFile:
    path: str
    kind: str
    estimated_bytes: int
    fingerprint: str
    root: str
    metadata: dict[str, int | str | None]
    member_patterns: tuple[str, ...] = ()
    active: bool = False


@dataclass(frozen=True)
class CaptureResult:
    bytes: int
    checksum: str
    fingerprint: str
    snapshot_changed: bool = False


def _error(code: str, message: str, status: int = 422) -> DomainError:
    return DomainError(code, message, status)


def _path(path: str, *, pattern: bool = False) -> str:
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or len(path) > 4096
        or any(ord(char) < 32 or ord(char) == 127 for char in path)
        or any(char in path for char in "\\$`~{}")
        or any(part in {".", ".."} for part in path.split("/"))
        or (not pattern and any(char in path for char in _GLOB_CHARS))
        or (path != "/" and any(part == "" for part in path[1:].split("/")))
        or len(path.split("/")) > 65
    ):
        raise _error("SOURCE_PATH_INVALID", "The configured log path is unsafe.")
    return path


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _archive_kind(path: str) -> str:
    if path.lower().endswith(".zip"):
        return "zip"
    if path.lower().endswith((".tar.gz", ".tgz")):
        return "tar.gz"
    raise _error("SOURCE_ARCHIVE_UNSUPPORTED", "Configured archives must be ZIP or TAR.GZ files.")


def _metadata(attrs: asyncssh.SFTPAttrs) -> dict[str, int | str | None]:
    if attrs.size is None or attrs.size < 0:
        raise _error("SOURCE_STAT_INVALID", "The log source did not provide a valid byte size.")
    return {
        "size": attrs.size,
        "mtime": attrs.mtime,
        "mtime_ns": attrs.mtime_ns,
        "ctime": attrs.ctime,
        "ctime_ns": attrs.ctime_ns,
        "permissions": attrs.permissions,
        "uid": attrs.uid,
        "gid": attrs.gid,
    }


def _regular(attrs: asyncssh.SFTPAttrs) -> bool:
    return attrs.type == asyncssh.FILEXFER_TYPE_REGULAR and (
        attrs.permissions is None or stat.S_ISREG(attrs.permissions)
    )


def _unchanged_or_appended(
    before: dict[str, int | str | None],
    after: dict[str, int | str | None],
    *,
    active: bool,
) -> bool:
    if before == after:
        return True
    # Appending changes size and modification/change times. Only active logs
    # may grow; ownership/permissions and the probed captured prefix must stay
    # unchanged. Equal-size changes and observed shrinking still fail closed.
    return (
        active
        and isinstance(before["size"], int)
        and isinstance(after["size"], int)
        and after["size"] > before["size"]
        and all(before[key] == after[key] for key in ("permissions", "uid", "gid"))
    )


class RemoteFiles:
    def __init__(
        self,
        sftp: asyncssh.SFTPClient,
        *,
        max_candidates: int,
        max_listing_entries: int,
        max_listing_bytes: int,
        max_estimated_bytes: int,
        max_probe_bytes: int,
    ) -> None:
        self.sftp = sftp
        self.max_candidates = max_candidates
        self.max_listing_entries = max_listing_entries
        self.max_listing_bytes = max_listing_bytes
        self.max_estimated_bytes = max_estimated_bytes
        self.max_probe_bytes = max_probe_bytes
        self.warnings: list[str] = []
        self.listing_entries = 0
        self.listing_bytes = 0
        self.probe_bytes = 0
        self.candidate_count = 0
        self.estimated_bytes = 0

    @asynccontextmanager
    async def _errors(self) -> AsyncIterator[None]:
        try:
            yield
        except asyncssh.SFTPPermissionDenied:
            raise _error(
                "SOURCE_PERMISSION_DENIED",
                "The log-read account cannot access a configured source.",
            ) from None
        except (asyncssh.SFTPNoSuchFile, asyncssh.SFTPNoSuchPath):
            raise _error("SOURCE_NOT_FOUND", "A configured log source is unavailable.") from None
        except asyncssh.SFTPError:
            raise _error(
                "SOURCE_READ_FAILED", "The configured log source could not be read."
            ) from None
        except UnicodeError:
            raise _error("SOURCE_PATH_INVALID", "A source path is not valid UTF-8.") from None

    @asynccontextmanager
    async def _open(self, path: str) -> AsyncIterator[asyncssh.SFTPClientFile]:
        # Disable AsyncSSH's parallel-reader task fan-out. One explicit bounded
        # request keeps cancellation local and prevents detached read tasks.
        handle = await self.sftp.open(
            path, asyncssh.FXF_READ, encoding=None, block_size=0, max_requests=1
        )
        cancelled = False
        try:
            yield handle
        except asyncio.CancelledError:
            cancelled = True
            self.sftp.exit()
            raise
        finally:
            if not cancelled:
                try:
                    async with asyncio.timeout(0.5):
                        await handle.close()
                except (TimeoutError, asyncssh.Error, OSError):
                    # A server may serialize CLOSE behind a stalled READ.
                    self.sftp.exit()

    async def _validated(
        self, path: str, root: str, *, directory: bool = False
    ) -> asyncssh.SFTPAttrs:
        _path(path)
        _path(root)
        if not _inside(path, root):
            raise _error(
                "SOURCE_ROOT_DENIED", "The configured log path is outside approved roots.", 409
            )
        current = "/"
        attrs = await self.sftp.lstat(current)
        for part in path[1:].split("/"):
            if not part:
                continue
            current = posixpath.join(current, part)
            attrs = await self.sftp.lstat(current)
            if attrs.type == asyncssh.FILEXFER_TYPE_SYMLINK or (
                attrs.permissions is not None and stat.S_ISLNK(attrs.permissions)
            ):
                raise _error("SOURCE_SYMLINK_DENIED", "Symlink log paths are disabled.", 409)
            if current != path and attrs.type != asyncssh.FILEXFER_TYPE_DIRECTORY:
                raise _error("SOURCE_NOT_REGULAR", "A log path component is not a directory.")
        canonical = await self.sftp.realpath(path)
        if not isinstance(canonical, str) or canonical != path or not _inside(canonical, root):
            raise _error(
                "SOURCE_ROOT_DENIED", "The canonical log path is outside approved roots.", 409
            )
        if directory:
            if attrs.type != asyncssh.FILEXFER_TYPE_DIRECTORY:
                raise _error("SOURCE_NOT_REGULAR", "A configured log directory is unavailable.")
        elif not _regular(attrs):
            raise _error("SOURCE_NOT_REGULAR", "Only regular log files can be collected.")
        return attrs

    async def _probe(self, handle: asyncssh.SFTPClientFile, size: int) -> str:
        digest = hashlib.sha256()
        for offset, length in (
            (0, min(size, _PROBE_BYTES)),
            (
                max(_PROBE_BYTES, size - _PROBE_BYTES),
                min(max(0, size - _PROBE_BYTES), _PROBE_BYTES),
            ),
        ):
            if not length:
                continue
            self.probe_bytes += length
            if self.probe_bytes > self.max_probe_bytes:
                raise _error(
                    "SOURCE_PROBE_LIMIT", "The configured source probe byte limit was reached.", 413
                )
            data = await handle.read(length, offset)
            if not isinstance(data, bytes):
                raise _error("SOURCE_READ_FAILED", "The log source did not return binary data.")
            if len(data) != length:
                raise _error(
                    "SOURCE_CHANGED", "The log source changed while its snapshot was read.", 409
                )
            digest.update(data)
        return digest.hexdigest()

    async def _snapshot(
        self,
        handle: asyncssh.SFTPClientFile,
        path: str,
        root: str,
        *,
        metadata: dict[str, int | str | None],
        active: bool,
        previous: dict[str, int | str | None] | None = None,
    ) -> tuple[dict[str, int | str | None], str]:
        named = _metadata(await self._validated(path, root))
        opened = await handle.stat()
        if (
            not _regular(opened)
            or not _unchanged_or_appended(metadata, named, active=active)
            or (previous is not None and not _unchanged_or_appended(previous, named, active=active))
            or not _unchanged_or_appended(named, _metadata(opened), active=active)
        ):
            raise _error(
                "SOURCE_CHANGED", "The configured log file changed before it could be read.", 409
            )
        # The plan fixes the boundary, including for probes. Reading a growing
        # current EOF here would invalidate the prefix on every ordinary append.
        size = metadata["size"]
        assert isinstance(size, int)
        probe = await self._probe(handle, size)
        after = await handle.stat()
        if not _regular(after) or not _unchanged_or_appended(
            _metadata(opened), _metadata(after), active=active
        ):
            raise _error(
                "SOURCE_CHANGED", "The log source changed while its snapshot was read.", 409
            )
        fingerprint = hashlib.sha256(
            json.dumps(
                {"metadata": metadata, "probe": probe}, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        return _metadata(after), fingerprint

    async def _candidate(
        self, path: str, kind: str, root: str, patterns: tuple[str, ...], *, active: bool
    ) -> RemoteFile:
        attrs = await self._validated(path, root)
        assert attrs.size is not None
        if self.candidate_count >= self.max_candidates:
            raise _error(
                "SOURCE_CANDIDATE_LIMIT", "The configured source count limit was reached.", 413
            )
        if self.estimated_bytes + attrs.size > self.max_estimated_bytes:
            raise _error(
                "DOWNLOAD_LIMIT", "The collection exceeds the configured download budget.", 413
            )
        # Explicit FXF_READ and one outstanding read: never create, append or write.
        metadata = _metadata(attrs)
        async with self._open(path) as handle:
            _, fingerprint = await self._snapshot(
                handle, path, root, metadata=metadata, active=active
            )
        candidate = RemoteFile(
            path, kind, attrs.size, fingerprint, root, metadata, patterns, active
        )
        self.candidate_count += 1
        self.estimated_bytes += attrs.size
        return candidate

    async def _expand(self, pattern: str, root: str) -> list[str]:
        paths = ["/"]
        components = pattern[1:].split("/")
        for index, component in enumerate(components):
            final = index == len(components) - 1
            expanded = []
            for directory in paths:
                if not any(char in component for char in _GLOB_CHARS):
                    expanded.append(posixpath.join(directory, component))
                    continue
                # A fixed prefix may be an ancestor of an approved root, but
                # wildcard listing may only begin inside the approved root.
                if not _inside(directory, root):
                    raise _error(
                        "SOURCE_ROOT_DENIED", "Log patterns must be inside approved roots.", 409
                    )
                await self._validated(directory, root, directory=True)
                async for entry in self.sftp.scandir(directory):
                    self.listing_entries += 1
                    name = entry.filename
                    if not isinstance(name, str):
                        raise _error(
                            "SOURCE_PATH_INVALID", "A source directory returned an invalid name."
                        )
                    self.listing_bytes += len(name.encode("utf-8"))
                    if (
                        self.listing_entries > self.max_listing_entries
                        or self.listing_bytes > self.max_listing_bytes
                    ):
                        raise _error(
                            "SOURCE_LISTING_LIMIT",
                            "The configured directory listing limit was reached.",
                            413,
                        )
                    if name in {".", ".."}:
                        continue
                    if "/" in name or "\\" in name or not name:
                        raise _error(
                            "SOURCE_PATH_INVALID", "A source directory returned an unsafe name."
                        )
                    if fnmatch.fnmatchcase(name, component):
                        path = posixpath.join(directory, name)
                        if not final:
                            attrs = await self.sftp.lstat(path)
                            if attrs.type not in {
                                asyncssh.FILEXFER_TYPE_DIRECTORY,
                                asyncssh.FILEXFER_TYPE_SYMLINK,
                            }:
                                continue
                        await self._validated(path, root, directory=not final)
                        expanded.append(path)
                        if len(expanded) > self.max_candidates:
                            raise _error(
                                "SOURCE_CANDIDATE_LIMIT",
                                "The configured source count limit was reached.",
                                413,
                            )
            paths = sorted(set(expanded))
        return paths

    async def plan(self, log_source: dict[str, Any], roots: list[str]) -> list[RemoteFile]:
        """Enumerate all configured candidates; never infer time from file names."""
        checked_roots = sorted((_path(root) for root in roots), key=len, reverse=True)
        definitions: list[tuple[str, str, tuple[str, ...], bool]] = [
            (_path(log_source["active_path"]), "plain", (), True)
        ]
        definitions.extend(
            (_path(pattern, pattern=True), "plain", (), False)
            for pattern in log_source["rotated_patterns"]
        )
        for archive in log_source["archives"]:
            pattern = _path(archive["path_pattern"], pattern=True)
            definitions.append((pattern, "archive", tuple(archive["member_patterns"]), False))
        candidates: dict[str, RemoteFile] = {}
        async with self._errors():
            for pattern, kind, members, active in definitions:
                fixed_parts = []
                for part in pattern[1:].split("/"):
                    if any(char in part for char in _GLOB_CHARS):
                        break
                    fixed_parts.append(part)
                fixed_prefix = "/" + "/".join(fixed_parts)
                root = next((root for root in checked_roots if _inside(fixed_prefix, root)), None)
                if root is None:
                    raise _error(
                        "SOURCE_ROOT_DENIED",
                        "The configured log path is outside approved roots.",
                        409,
                    )
                try:
                    paths = await self._expand(pattern, root)
                    for path in paths:
                        file_kind = _archive_kind(path) if kind == "archive" else kind
                        if path in candidates:
                            existing = candidates[path]
                            if existing.kind != file_kind:
                                raise _error(
                                    "SOURCE_CONFIG_AMBIGUOUS",
                                    "A source is configured with conflicting file types.",
                                )
                            if members:
                                candidates[path] = replace(
                                    existing,
                                    member_patterns=tuple(
                                        sorted(set(existing.member_patterns) | set(members))
                                    ),
                                )
                            continue
                        candidates[path] = await self._candidate(
                            path, file_kind, root, members, active=active
                        )
                except (asyncssh.SFTPNoSuchFile, asyncssh.SFTPNoSuchPath):
                    if active:
                        self.warnings.append("ACTIVE_SOURCE_UNAVAILABLE")
                    else:
                        # Missing optional rotation directories are visible, not
                        # silently advertised as complete candidate coverage.
                        self.warnings.append("CONFIGURED_HISTORY_UNAVAILABLE")
            if not candidates:
                raise _error("SOURCE_NOT_FOUND", "No configured log candidates are available.")
        return sorted(candidates.values(), key=lambda candidate: candidate.path)

    async def check(self, candidate: RemoteFile) -> None:
        """Revalidate readability and the frozen snapshot using bounded probes."""
        async with self._errors():
            previous = _metadata(await self._validated(candidate.path, candidate.root))
            async with self._open(candidate.path) as handle:
                _, fingerprint = await self._snapshot(
                    handle,
                    candidate.path,
                    candidate.root,
                    metadata=candidate.metadata,
                    active=candidate.active,
                    previous=previous,
                )
                if fingerprint != candidate.fingerprint:
                    raise _error(
                        "SOURCE_CHANGED",
                        "The planned log snapshot has changed; preview again.",
                        409,
                    )

    async def copy(
        self, candidate: RemoteFile, destination: BinaryIO, *, max_bytes: int
    ) -> CaptureResult:
        """Copy at most the planned length; reject changed or truncated captures.

        A caller owns the generated temporary destination and removes it after
        cancellation/failure. No path is accepted from the browser, and partial
        captures must never be indexed as a successful immutable snapshot.
        """
        if candidate.estimated_bytes > max_bytes or max_bytes < 0:
            raise _error(
                "DOWNLOAD_LIMIT", "The collection exceeds the configured download budget.", 413
            )
        async with self._errors():
            previous = _metadata(await self._validated(candidate.path, candidate.root))
            async with self._open(candidate.path) as handle:
                before, fingerprint = await self._snapshot(
                    handle,
                    candidate.path,
                    candidate.root,
                    metadata=candidate.metadata,
                    active=candidate.active,
                    previous=previous,
                )
                if fingerprint != candidate.fingerprint:
                    raise _error(
                        "SOURCE_CHANGED",
                        "The planned log snapshot has changed; preview again.",
                        409,
                    )
                count = 0
                checksum = hashlib.sha256()
                while count < candidate.estimated_bytes:
                    data = await handle.read(
                        min(_BLOCK_BYTES, candidate.estimated_bytes - count, max_bytes - count),
                        count,
                    )
                    if not isinstance(data, bytes):
                        raise _error(
                            "SOURCE_READ_FAILED", "The log source did not return binary data."
                        )
                    if not data:
                        raise _error(
                            "SOURCE_CHANGED", "The log source was truncated during collection.", 409
                        )
                    if (
                        count + len(data) > max_bytes
                        or count + len(data) > candidate.estimated_bytes
                    ):
                        raise _error(
                            "DOWNLOAD_LIMIT", "The actual source byte limit was reached.", 413
                        )
                    try:
                        stored = destination.write(data)
                    except OSError:
                        raise _error(
                            "CACHE_WRITE_FAILED",
                            "The local log cache could not store the capture.",
                            503,
                        ) from None
                    if stored != len(data):
                        raise _error(
                            "CACHE_WRITE_FAILED",
                            "The local log cache could not store the capture.",
                            503,
                        )
                    checksum.update(data)
                    count += len(data)
                    await asyncio.sleep(0)
                _, after_fingerprint = await self._snapshot(
                    handle,
                    candidate.path,
                    candidate.root,
                    metadata=candidate.metadata,
                    active=candidate.active,
                    previous=before,
                )
                if after_fingerprint != fingerprint:
                    raise _error(
                        "SOURCE_CHANGED",
                        "The log source changed during collection; capture is partial.",
                        409,
                    )
                return CaptureResult(count, checksum.hexdigest(), fingerprint)


@asynccontextmanager
async def open_files(
    target: Endpoint,
    jump: Endpoint | None = None,
    *,
    allow_loopback: bool = False,
    timeout_seconds: float = 120.0,
    max_candidates: int = 1000,
    max_listing_entries: int = 10_000,
    max_listing_bytes: int = 4_194_304,
    max_estimated_bytes: int = 536_870_912,
    max_probe_bytes: int = 33_554_432,
) -> AsyncIterator[RemoteFiles]:
    limits = (
        max_candidates,
        max_listing_entries,
        max_listing_bytes,
        max_estimated_bytes,
        max_probe_bytes,
    )
    if any(value < 1 for value in limits):
        raise ValueError("SFTP planning limits must be positive")
    async with sftp_session(
        target, jump, allow_loopback=allow_loopback, timeout_seconds=timeout_seconds
    ) as sftp:
        yield RemoteFiles(
            sftp,
            max_candidates=max_candidates,
            max_listing_entries=max_listing_entries,
            max_listing_bytes=max_listing_bytes,
            max_estimated_bytes=max_estimated_bytes,
            max_probe_bytes=max_probe_bytes,
        )
