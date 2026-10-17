"""Shared, transport-independent physical-event and literal-query semantics."""

from __future__ import annotations

import hashlib
import math
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)")
_PREFIX = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00))(?=$|[ \t])"
)
_MAX_SAFE_INTEGER = 9_007_199_254_740_991


class EngineError(ValueError):
    """Safe diagnostic code; never include untrusted log text in error messages."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _micros(value: datetime) -> int:
    delta = value - _EPOCH
    result = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    if not -_MAX_SAFE_INTEGER <= result <= _MAX_SAFE_INTEGER:
        raise ValueError("Timestamp is outside the supported exact range.")
    return result


def utc_microseconds(text: str) -> int:
    if not isinstance(text, str) or _ISO.fullmatch(text) is None:
        raise ValueError("Expected a full UTC timestamp with at most six fractional digits.")
    return _micros(datetime.fromisoformat(text.replace("Z", "+00:00")))


def canonical_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ParserConfig:
    kind: str = "iso8601_prefix"
    width: int | None = None
    format: str | None = None
    naive_timezone: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"iso8601_prefix", "fixed_width"}:
            raise ValueError("Unsupported parser strategy.")
        if self.naive_timezone not in {None, "UTC"}:
            raise ValueError("Only UTC is supported.")
        if self.kind == "fixed_width" and (
            self.width is None
            or not 1 <= self.width <= 64
            or not self.format
            or len(self.format) > 128
        ):
            raise ValueError("Fixed-width parsing requires bounded width and format.")


@dataclass(frozen=True)
class ParsedTimestamp:
    original: str | None
    utc: str | None
    micros: int | None


@dataclass(frozen=True)
class CorrelationMarker:
    key: str
    prefix: str
    terminators: str = " \t"

    def __post_init__(self) -> None:
        if (
            not 1 <= len(self.key) <= 64
            or not 1 <= len(self.prefix) <= 128
            or len(self.terminators) > 32
        ):
            raise ValueError("Correlation markers must be bounded literals.")


def extract_metadata(text: str, markers: tuple[CorrelationMarker, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for marker in markers:
        start = text.find(marker.prefix)
        if start < 0:
            continue
        start += len(marker.prefix)
        end = start
        while end < len(text) and text[end] not in marker.terminators and end - start <= 512:
            end += 1
        if start < end and end - start <= 512:
            result[marker.key] = text[start:end]
    return result


def parse_timestamp(line: str, parser: ParserConfig | None = None) -> ParsedTimestamp:
    config = parser or ParserConfig()
    original: str | None = None
    try:
        if config.kind == "iso8601_prefix":
            match = _PREFIX.match(line)
            if match is None:
                # Preserve a bounded timestamp-like token without inventing a parsed time.
                token = re.split(r"[ \t]", line[:64], maxsplit=1)[0]
                original = token if re.match(r"^\d{4}-", token) else None
                return ParsedTimestamp(original, None, None)
            original = match.group(1)
            value = datetime.fromisoformat(original.replace("Z", "+00:00"))
        else:
            assert config.width is not None and config.format is not None
            original = line[: config.width]
            if (
                len(original) != config.width
                or "-00:00" in original
                or ("%z" in config.format and "-0000" in original)
            ):
                return ParsedTimestamp(original, None, None)
            value = datetime.strptime(original, config.format)
            if value.tzinfo is None:
                if config.naive_timezone != "UTC":
                    return ParsedTimestamp(original, None, None)
                value = value.replace(tzinfo=UTC)
            if value.utcoffset() != UTC.utcoffset(value):
                return ParsedTimestamp(original, None, None)
        return ParsedTimestamp(original, canonical_utc(value), _micros(value))
    except (ValueError, OverflowError):
        return ParsedTimestamp(original, None, None)


@dataclass(frozen=True)
class LiteralFilter:
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    include_mode: str = "any"
    case_sensitive: bool = True
    _include: tuple[str, ...] = field(init=False, repr=False)
    _exclude: tuple[str, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.include_mode not in {"any", "all"} or type(self.case_sensitive) is not bool:
            raise ValueError("Invalid literal filter options.")
        for terms in (self.include, self.exclude):
            if (
                not isinstance(terms, (tuple, list))
                or len(terms) > 20
                or any(not isinstance(term, str) or len(term) > 512 for term in terms)
            ):
                raise ValueError("At most 20 strings of 512 characters are permitted per field.")
        transform = (lambda text: text) if self.case_sensitive else str.casefold
        object.__setattr__(
            self, "_include", tuple(transform(term) for term in self.include if term != "")
        )
        object.__setattr__(
            self, "_exclude", tuple(transform(term) for term in self.exclude if term != "")
        )

    def matches(self, raw_line: str) -> bool:
        text = raw_line if self.case_sensitive else raw_line.casefold()
        if any(term in text for term in self._exclude):
            return False
        if not self._include:
            return True
        check = all if self.include_mode == "all" else any
        return check(term in text for term in self._include)


def event_id(
    process_id: str,
    source_revision_id: str,
    archive_member: str | None,
    member_ordinal: int | None,
    byte_start: int,
    byte_end: int,
) -> str:
    fields = (
        process_id,
        source_revision_id,
        archive_member or "",
        str(member_ordinal if member_ordinal is not None else -1),
        str(byte_start),
        str(byte_end),
    )
    if any("\0" in part for part in fields):
        raise ValueError("Invalid identity component.")
    return "evt-" + hashlib.sha256("\0".join(fields).encode("utf-8")).hexdigest()


def event_sort_key(event: dict[str, Any]) -> tuple[Any, ...]:
    source = event["source"]
    ordinal = source["member_ordinal"]
    return (
        event["timestamp_us"],
        event["process_id"],
        source["source_revision_id"],
        -1 if ordinal is None else ordinal,
        source["byte_start"],
        event["event_id"],
    )


@dataclass(frozen=True)
class LocalSource:
    project_id: str
    process_id: str
    source_revision_id: str
    path: Path
    remote_path: str
    kind: str = "plain"
    archive_member: str | None = None
    member_ordinal: int | None = None
    server_id: str = ""
    process_name: str = ""
    server_name: str = ""
    parser: ParserConfig = field(default_factory=ParserConfig)
    encoding: str = "utf-8"
    member_globs: tuple[str, ...] = ("*",)
    correlation_markers: tuple[CorrelationMarker, ...] = ()

    def __post_init__(self) -> None:
        if not self.project_id or not self.process_id or not self.source_revision_id:
            raise ValueError("Explicit project, process and source identities are required.")
        if self.kind not in {"plain", "zip", "tar.gz"}:
            raise ValueError("Unsupported source type.")
        if not 1 <= len(self.member_globs) <= 20 or any(
            len(item) > 4096 for item in self.member_globs
        ):
            raise ValueError("Invalid archive member selectors.")
        if len(self.correlation_markers) > 20:
            raise ValueError("Too many correlation markers.")


@dataclass(frozen=True)
class EngineLimits:
    max_download_bytes: int = 512 * 1024 * 1024
    max_expanded_bytes: int = 1024 * 1024 * 1024
    max_member_bytes: int = 128 * 1024 * 1024
    max_members: int = 10_000
    max_compression_ratio: int = 500
    max_line_bytes: int = 256 * 1024
    max_events: int = 2_000_000
    wall_seconds: float = 120

    def __post_init__(self) -> None:
        if (
            any(
                type(value) is not int or value <= 0
                for key, value in vars(self).items()
                if key != "wall_seconds"
            )
            or isinstance(self.wall_seconds, bool)
            or not isinstance(self.wall_seconds, (int, float))
            or not math.isfinite(self.wall_seconds)
            or self.wall_seconds <= 0
        ):
            raise ValueError("All engine limits must be positive.")


@dataclass
class ScanProgress:
    downloaded_bytes: int = 0
    expanded_bytes: int = 0
    events: int = 0
    diagnostic_events: int = 0
    members: int = 0
    source_sha256: str | None = None
    source_stable: bool = True
    source_complete: bool = False


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def check(self) -> None:
        if self._cancelled.is_set():
            raise EngineError("CANCELLED")
