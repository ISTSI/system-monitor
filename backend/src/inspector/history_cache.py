"""Bounded, immutable read-through accelerators; never authentication authority.

Rows come only from the MariaDB snapshot query. Mutable capture state and filter
results are never cached. The caller supplies the complete authorized scope key.
The accounting includes builds and leased entries, plus container/string/int
objects created for each compact row. Only capture-local process/source strings
are pooled; arbitrary log text is never interned globally.
"""

import sys
import time
from collections import OrderedDict
from collections.abc import Hashable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

DEFAULT_CACHE_BYTES = 64 * 1024 * 1024


def scope_size(value: Any, seen: set[int] | None = None) -> int:
    """Exact unique-object accounting for the small immutable scope key."""
    seen = seen if seen is not None else set()
    if id(value) in seen:
        return 0
    seen.add(id(value))
    return sys.getsizeof(value) + (
        sum(scope_size(v, seen) for v in value) if isinstance(value, tuple) else 0
    )


@dataclass
class CacheEntry:
    key: Hashable
    rows: tuple[tuple, ...]
    bytes: int
    expires: float
    leases: int = 0


class HistoricalReadCache:
    def __init__(self, max_bytes: int = DEFAULT_CACHE_BYTES, ttl_seconds: float = 300) -> None:
        if max_bytes < 1 or ttl_seconds <= 0:
            raise ValueError("Positive cache bounds are required.")
        self.max_bytes = max_bytes
        self.ttl_seconds = ttl_seconds
        self.used_bytes = 0
        self.entries: OrderedDict[Hashable, CacheEntry] = OrderedDict()

    def _remove(self, entry: CacheEntry) -> None:
        self.entries.pop(entry.key, None)
        self.used_bytes -= entry.bytes

    def reserve(self, amount: int) -> bool:
        now = time.monotonic()
        for entry in list(self.entries.values()):
            if not entry.leases and (
                entry.expires <= now or self.used_bytes + amount > self.max_bytes
            ):
                self._remove(entry)
        if self.used_bytes + amount > self.max_bytes:
            return False
        self.used_bytes += amount
        return True

    @contextmanager
    def lease(self, key: Hashable) -> Iterator[CacheEntry | None]:
        entry = self.entries.get(key)
        if entry is not None and entry.expires <= time.monotonic():
            if not entry.leases:
                self._remove(entry)
            entry = None
        if entry is not None:
            entry.leases += 1
            self.entries.move_to_end(key)
        try:
            yield entry
        finally:
            if entry is not None:
                entry.leases -= 1

    def builder(self, key: Hashable) -> "CacheBuilder":
        return CacheBuilder(self, key)


class CacheBuilder:
    def __init__(self, cache: HistoricalReadCache, key: Hashable) -> None:
        self.cache, self.key = cache, key
        self.rows: list[tuple] = []
        self.pool: dict[str, str] = {}
        self.bytes = (
            scope_size(key)
            + sys.getsizeof(self.rows)
            + sys.getsizeof(self.pool)
            + sys.getsizeof(self)
            + 1024
        )
        self.active = cache.reserve(self.bytes)
        if not self.active:
            self.bytes = 0

    def add(self, row: tuple) -> None:
        if not self.active:
            return
        old_pool_size = sys.getsizeof(self.pool)
        pooled_cost = 0
        pooled = []
        for value in row[1:3]:
            if value not in self.pool:
                self.pool[value] = value
                pooled_cost += sys.getsizeof(value)
            pooled.append(self.pool[value])
        compact: tuple[Any, ...] = (
            row[0],
            pooled[0],
            pooled[1],
            row[3],
            row[4],
            row[5],
            row[6],
            row[7],
            row[8],
        )
        # Text, IDs and large numeric values are independently allocated by the
        # driver per row. Small integer/bool singleton storage is process-owned.
        cost = (
            sys.getsizeof(compact)
            + sys.getsizeof(compact[5])
            + sys.getsizeof(compact[6])
            + pooled_cost
            + sys.getsizeof(self.pool)
            - old_pool_size
        )
        cost += sum(
            sys.getsizeof(compact[index])
            for index in (0, 3, 4, 8)
            if not -5 <= compact[index] <= 256
        )
        old_list_size = sys.getsizeof(self.rows)
        self.rows.append(compact)
        cost += sys.getsizeof(self.rows) - old_list_size
        if not self.cache.reserve(cost):
            self.abort()
            return
        self.bytes += cost

    def publish(self) -> None:
        if not self.active:
            return
        # Reserve the immutable container while the builder still owns its list.
        extra = sys.getsizeof(tuple()) + len(self.rows) * 8
        if not self.cache.reserve(extra):
            self.abort()
            return
        self.bytes += extra
        rows = tuple(self.rows)
        released = sys.getsizeof(self.rows) + sys.getsizeof(self.pool)
        self.rows.clear()
        self.pool.clear()
        self.bytes -= released
        self.cache.used_bytes -= released
        previous = self.cache.entries.get(self.key)
        if previous is not None:
            if previous.leases:
                self.cache.used_bytes -= self.bytes
                self.active = False
                return
            self.cache._remove(previous)
        self.cache.entries[self.key] = CacheEntry(
            self.key, rows, self.bytes, time.monotonic() + self.cache.ttl_seconds
        )
        self.active = False

    def abort(self) -> None:
        if self.active:
            self.cache.used_bytes -= self.bytes
            self.bytes = 0
            self.rows.clear()
            self.pool.clear()
            self.active = False


READ_CACHE = HistoricalReadCache()
