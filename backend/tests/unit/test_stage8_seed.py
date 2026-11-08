"""Release qualification refuses unapproved DB use and detects cache corruption."""

import argparse
import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("stage8_seed", ROOT / "scripts/stage8_seed.py")
assert SPEC is not None and SPEC.loader is not None
qualification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualification)


async def test_no_database_or_configuration_access_without_disposable_opt_in(monkeypatch):
    monkeypatch.delenv("SI_STAGE8_DISPOSABLE", raising=False)

    def unavailable():
        pytest.fail("Configuration must not be loaded without explicit disposable opt-in")

    monkeypatch.setattr(qualification, "load_config", unavailable)
    with pytest.raises(ValueError, match="opt-in is required"):
        await qualification.run(argparse.Namespace(command="seed"))


def test_cache_manifest_covers_actual_bytes_and_detects_changed_content(tmp_path):
    nested = tmp_path / "historical" / "opaque-project-key"
    nested.mkdir(parents=True)
    source = nested / "opaque-source-key"
    source.write_bytes(b"synthetic source\n" * 100_000)
    before = qualification.cache_manifest(str(tmp_path))
    assert before == [
        {
            "path": "historical/opaque-project-key/opaque-source-key",
            "bytes": source.stat().st_size,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    ]
    source.write_bytes(b"corrupted source\n")
    assert qualification.cache_manifest(str(tmp_path)) != before


def test_cache_manifest_refuses_linked_directories_and_files(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    (target / "source").write_bytes(b"synthetic")
    link = tmp_path / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("This host does not grant test symlink creation")
    with pytest.raises(ValueError, match="real directory"):
        qualification.cache_manifest(str(link))
    with pytest.raises(ValueError, match="symlinks"):
        qualification.cache_manifest(str(tmp_path))
