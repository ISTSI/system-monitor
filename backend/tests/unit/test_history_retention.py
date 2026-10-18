"""Deletion is limited to a generated flat namespace and can restore staged files."""

import os
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from inspector.errors import DomainError
from inspector.history_retention import checked_stat, read_download_chunk, stage_cache

ROOT = Path(__file__).resolve().parents[3]


def capture(root):
    directory = root / "historical" / "synthetic-project-hash" / "synthetic-job"
    directory.mkdir(parents=True)
    (directory / "synthetic-source").write_bytes(b"original synthetic log\n")
    (directory / "synthetic-source.part").write_bytes(b"partial synthetic log\n")
    return directory


def test_staging_restore_and_removal_preserve_sibling_capture(tmp_path):
    root = tmp_path / "cache"
    directory = capture(root)
    other = directory.with_name("another-job")
    other.mkdir()
    (other / "source").write_bytes(b"retained")
    staged = stage_cache(directory, root)
    assert staged is not None and not directory.exists() and staged.detached.is_dir()
    staged.restore()
    assert (directory / "synthetic-source").read_bytes() == b"original synthetic log\n"
    staged = stage_cache(directory, root)
    staged.remove()
    assert not directory.exists() and not staged.detached.exists()
    assert (other / "source").read_bytes() == b"retained"


def test_empty_missing_and_foreign_directories(tmp_path):
    root = tmp_path / "cache"
    assert stage_cache(root / "missing-job", root) is None
    directory = root / "empty-job"
    directory.mkdir(parents=True)
    staged = stage_cache(directory, root)
    assert staged is not None
    staged.remove()
    for path in (tmp_path, root, root / ".." / "outside"):
        with pytest.raises(DomainError, match="unsafe"):
            stage_cache(path, root)


def test_subdirectories_and_entry_overflow_fail_without_renaming(tmp_path):
    root = tmp_path / "cache"
    directory = capture(root)
    with pytest.raises(DomainError, match="unsafe"):
        stage_cache(directory, root, maximum_entries=1)
    nested = directory / "unexpected-directory"
    nested.mkdir()
    with pytest.raises(DomainError, match="unsafe"):
        stage_cache(directory, root)
    assert directory.exists() and len(list(directory.iterdir())) == 3


def test_reparse_entry_is_rejected_without_following_it(tmp_path, monkeypatch):
    path = tmp_path / "synthetic-junction"
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda _: SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400),
    )
    with pytest.raises(DomainError, match="unsafe"):
        checked_stat(path)


@pytest.mark.skipif(
    os.name == "nt", reason="Creating symlinks requires Windows developer privileges."
)
def test_symlinked_cache_ancestor_and_member_never_touch_external_data(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "source").write_bytes(b"preserved external bytes")
    root = tmp_path / "cache"
    directory = capture(root)
    (directory / "external-source").symlink_to(outside / "source")
    with pytest.raises(DomainError, match="unsafe"):
        stage_cache(directory, root)
    (directory / "external-source").unlink()
    namespace = directory.parent
    linked = root / "linked"
    linked.symlink_to(namespace, target_is_directory=True)
    with pytest.raises(DomainError, match="unsafe"):
        stage_cache(linked / directory.name, root)
    assert (outside / "source").read_bytes() == b"preserved external bytes"
    assert directory.exists()


def test_chunk_read_closes_file_and_keeps_exact_offset(tmp_path):
    root = tmp_path / "cache"
    directory = capture(root)
    source = directory / "synthetic-source"
    source.write_bytes(b"x" * 65_536 + b"tail")
    assert read_download_chunk(source, root, 0) == b"x" * 65_536
    assert read_download_chunk(source, root, 65_536) == b"tail"
    staged = stage_cache(directory, root)
    staged.remove()


async def test_delete_restores_staged_bytes_when_rollback_reports_failure(tmp_path, monkeypatch):
    from inspector import history
    from inspector.config import parse_config
    from inspector.domain import Principal

    config = parse_config((ROOT / "examples/deployment-policy.example.yaml").read_bytes(), {})
    manager = history.HistoryManager(replace(config, cache_dir=str(tmp_path / "cache")), None, None)
    actor = Principal("synthetic-owner", "inspector", 1)
    directory = manager.cache_path("synthetic-project", "synthetic-job", "unused").parent
    directory.mkdir(parents=True)
    (directory / "source").write_bytes(b"preserved through rollback failure")
    monkeypatch.setattr(
        history,
        "checked_job",
        AsyncMock(return_value=SimpleNamespace(owner_user_id=actor.user_id, status="completed")),
    )
    rolled_back = AsyncMock()

    async def rollback_then_fail():
        await rolled_back()
        raise OSError("Synthetic connection cleanup failure after rollback.")

    session = SimpleNamespace(
        get=AsyncMock(return_value=None),
        scalar=AsyncMock(side_effect=[0, 1]),
        execute=AsyncMock(
            side_effect=DomainError("SYNTHETIC_DELETE_FAILURE", "Synthetic failure.", 409)
        ),
        rollback=rollback_then_fail,
    )
    try:
        with pytest.raises(OSError, match="after rollback"):
            await manager._delete_capture(session, actor, "synthetic-project", "synthetic-job")
        rolled_back.assert_awaited_once()
        assert (directory / "source").read_bytes() == b"preserved through rollback failure"
        assert not list(directory.parent.glob("deleted-*"))
        assert not manager.resource_locks
    finally:
        await manager.close()
