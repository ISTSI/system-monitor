"""Immutable read-cache scope, real object accounting, leases, bounds and TTL."""

import sys

from inspector.history_cache import HistoricalReadCache, scope_size


def key(project="a", owner="alice", sequence=2, revision=1, start=1, end=10, lane="events"):
    return (project, owner, "job", sequence, revision, 2, 1, ("process",), start, end, lane)


def row(number=0, text="synthetic line"):
    return (
        1_792_152_000_000_000 + number,
        "process",
        "source",
        -1,
        number * 1000,
        "evt-" + str(number),
        text,
        False,
        len(text.encode()),
    )


def populate(cache, scope, records):
    builder = cache.builder(scope)
    for record in records:
        builder.add(record)
    builder.publish()


def test_complete_immutable_cache_is_scope_specific_and_accounted():
    cache = HistoricalReadCache(100_000)
    original = row()
    populate(cache, key(), [original, row(1, "another synthetic line")])
    with cache.lease(key()) as entry:
        assert entry is not None and entry.rows == (original, row(1, "another synthetic line"))
        assert isinstance(entry.rows, tuple)
        assert entry.rows[0][1] is entry.rows[1][1]
        assert entry.rows[0][2] is entry.rows[1][2]
        actual = (
            scope_size((entry.key, entry.rows))
            + sys.getsizeof(entry)
            + sys.getsizeof(entry.__dict__)
            + sys.getsizeof(cache.entries)
        )
        assert actual <= cache.used_bytes <= cache.max_bytes
    for different in (
        key(project="b"),
        key(owner="bob"),
        key(sequence=3),
        key(revision=2),
        key(start=0),
        key(end=11),
        key(lane="diagnostic"),
    ):
        with cache.lease(different) as entry:
            assert entry is None


def test_builds_are_bounded_and_never_publish_partial_entries():
    cache = HistoricalReadCache(5000)
    builder = cache.builder(key())
    for number in range(100):
        builder.add(row(number, "x" * 1000))
        assert 0 <= cache.used_bytes <= cache.max_bytes
    builder.publish()
    assert not cache.entries and cache.used_bytes == 0
    aborted = cache.builder(key())
    aborted.add(row())
    aborted.abort()
    assert not cache.entries and cache.used_bytes == 0


def test_lru_eviction_expiry_and_leases_share_one_global_budget(monkeypatch):
    cache = HistoricalReadCache(6000, ttl_seconds=5)
    populate(cache, key(), [row(text="x" * 1500)])
    assert cache.entries
    with cache.lease(key()) as leased:
        assert leased is not None
        populate(cache, key(project="b"), [row(text="x" * 4000)])
        assert key() in cache.entries
        assert key(project="b") not in cache.entries
        assert cache.used_bytes <= cache.max_bytes
    populate(cache, key(project="b"), [row(text="x" * 1500)])
    assert key(project="b") in cache.entries
    entry = cache.entries[key(project="b")]
    monkeypatch.setattr("inspector.history_cache.time.monotonic", lambda: entry.expires + 1)
    with cache.lease(key(project="b")) as expired:
        assert expired is None
    assert cache.used_bytes == sum(e.bytes for e in cache.entries.values())


def test_capture_invalidation_preserves_other_scopes_and_retires_leased_accounting():
    cache = HistoricalReadCache(100_000)
    populate(cache, key(), [row()])
    populate(cache, key(revision=2), [row(1)])
    populate(cache, key(project="b"), [row()])
    populate(cache, key(owner="bob"), [row()])
    other_bytes = cache.entries[key(project="b")].bytes
    with cache.lease(key()) as leased:
        assert leased is not None
        cache.invalidate("a", "job")
        assert list(cache.entries) == [key(project="b")]
        assert cache.used_bytes == other_bytes + leased.bytes
        with cache.lease(key()) as deleted:
            assert deleted is None
    assert cache.used_bytes == other_bytes


def test_invalidated_pending_build_cannot_republish_deleted_rows():
    cache = HistoricalReadCache(100_000)
    builder = cache.builder(key())
    builder.add(row())
    cache.invalidate("a", "job")
    builder.publish()
    assert not cache.entries and cache.used_bytes == 0
