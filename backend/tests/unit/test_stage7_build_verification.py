"""A successful artifact check must reject stale sources and altered packages."""

import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import build_stage7  # noqa: E402
from verify_stage7_build import (  # noqa: E402
    BUILD_RELATIVE,
    BuildVerificationError,
    file_hash,
    record_inputs,
    source_hashes,
    verify_build,
)


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def built(tmp_path):
    for name, content in {
        "backend/src/inspector/__init__.py": '"""Synthetic package."""\n',
        "backend/src/inspector/module.py": "def value(): return 42\n",
        "backend/migrations/env.py": '"""Synthetic migration."""\n',
        "backend/pyproject.toml": "# synthetic build input\n",
        "backend/uv.lock": "# synthetic lock input\n",
        "backend/alembic.ini": "[alembic]\n",
        "frontend/src/main.ts": "document.body.textContent = 'synthetic';\n",
        "frontend/package.json": '{"name":"synthetic"}',
        "frontend/package-lock.json": '{"name":"synthetic"}',
        "frontend/index.html": "<html>synthetic source</html>",
        "scripts/frontend.py": "# synthetic build wrapper\n",
        "scripts/build_stage7.py": "# synthetic isolated builder\n",
        "scripts/verify_stage7_build.py": "# synthetic verifier input\n",
        "scripts/generate_casefold.py": "# synthetic casefold generator input\n",
    }.items():
        write(tmp_path, name, content)
    stage = tmp_path / BUILD_RELATIVE
    shutil.copytree(tmp_path / "backend", stage / "backend")
    index = write(stage, "frontend/index.html", "<html>synthetic build</html>")
    script = write(stage, "frontend/assets/app.js", "document.body.textContent = 'synthetic';\n")
    assets = {"index.html": file_hash(index), "assets/app.js": file_hash(script)}
    shutil.copytree(stage / "frontend", stage / "backend/src/inspector/web")
    write(stage, "backend/src/inspector/web/BUILD_ASSETS.json", json.dumps(assets))
    wheel = stage / "backend/dist/synthetic-py3-none-any.whl"
    wheel.parent.mkdir()
    with zipfile.ZipFile(wheel, "w") as archive:
        for path in (stage / "backend/src").rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(stage / "backend/src").as_posix())
        archive.write(stage / "backend/migrations/env.py", "inspector/migrations/env.py")
        archive.write(stage / "backend/alembic.ini", "inspector/alembic.ini")
        archive.writestr("synthetic.dist-info/METADATA", "Synthetic fixture metadata")
    record_inputs(tmp_path, source_hashes(tmp_path))
    return tmp_path


def test_matches_current_runtime_staged_backend_wheel_and_assets(built):
    result = verify_build(built)
    assert result["verified"]
    assert all(not paths for check in result["checks"].values() for paths in check.values())
    assert len(result["wheel_sha256"]) == 64


def test_frontend_source_change_invalidates_existing_bundle(built):
    write(built, "frontend/src/main.ts", "document.body.textContent = 'changed';")
    result = verify_build(built)
    assert not result["verified"]
    assert result["checks"]["current_sources"]["changed"] == ["frontend/src/main.ts"]


def test_stale_extra_staged_backend_module_is_detected(built):
    write(built / BUILD_RELATIVE, "backend/src/inspector/removed_module.py", "stale = True")
    result = verify_build(built)
    assert not result["verified"]
    assert result["checks"]["staged_backend_sources"]["extra"] == ["inspector/removed_module.py"]


def test_changed_web_asset_is_detected_in_manifest_and_wheel(built):
    write(built / BUILD_RELATIVE, "backend/src/inspector/web/assets/app.js", "changed bundled code")
    result = verify_build(built)
    assert not result["verified"]
    assert result["checks"]["backend_web_assets"]["changed"] == ["assets/app.js"]
    assert "inspector/web/assets/app.js" in result["checks"]["wheel_runtime_files"]["changed"]


def test_changed_wheel_module_is_detected_without_extraction(built):
    wheel = next((built / BUILD_RELATIVE / "backend/dist").glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    contents["inspector/module.py"] = b"tampered = True"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    result = verify_build(built)
    assert not result["verified"]
    assert result["checks"]["wheel_runtime_files"]["changed"] == ["inspector/module.py"]


def test_docs_tests_and_progress_do_not_invalidate_runtime_artifacts(built):
    for path in (
        "docs/new.md",
        "progress/STATUS.md",
        "backend/tests/unit/new_test.py",
        "frontend/e2e/new.spec.ts",
    ):
        write(built, path, "Synthetic review evidence added after source freeze")
    assert verify_build(built)["verified"]


def test_source_change_during_build_cannot_be_recorded_as_success(built):
    before = source_hashes(built)
    write(built, "backend/src/inspector/module.py", "changed = True")
    with pytest.raises(BuildVerificationError, match="changed during the build"):
        record_inputs(built, before)
    assert not verify_build(built)["verified"]


def test_unrecorded_build_is_rejected(built):
    (built / BUILD_RELATIVE / "BUILD_INPUTS.json").unlink()
    with pytest.raises(BuildVerificationError, match="manifest is absent"):
        verify_build(built)


def test_build_cleanup_refuses_outside_targets_before_deleting(tmp_path, monkeypatch):
    monkeypatch.setattr(build_stage7, "ROOT", tmp_path)
    monkeypatch.setattr(build_stage7, "OUTPUT", tmp_path / BUILD_RELATIVE)
    preserved = write(tmp_path, "retained/source.py", "preserve = True")
    with pytest.raises(RuntimeError, match="outside the isolated"):
        build_stage7.clear_generated(preserved.parent)
    assert preserved.read_text() == "preserve = True"


def test_build_cleanup_removes_only_checked_generated_subdirectory(tmp_path, monkeypatch):
    monkeypatch.setattr(build_stage7, "ROOT", tmp_path)
    monkeypatch.setattr(build_stage7, "OUTPUT", tmp_path / BUILD_RELATIVE)
    generated = write(tmp_path / BUILD_RELATIVE, "backend/src/old.py", "stale = True")
    build_stage7.clear_generated(generated.parent)
    assert not generated.parent.exists()
