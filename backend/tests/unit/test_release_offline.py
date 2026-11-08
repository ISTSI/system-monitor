"""Release integrity failures must stop a transfer before any container starts."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("release_offline", SCRIPTS / "release_offline.py")
assert spec and spec.loader
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def fixture_release(directory: Path) -> None:
    (directory / "images").mkdir()
    images = []
    files = {}
    for role in ("app", "proxy", "mariadb"):
        name = f"images/{role}.tar"
        (directory / name).write_bytes(role.encode())
        files[name] = release.digest(directory / name)
        images.append(
            {"role": role, "archive": name, "sha256": files[name], "image_id": "sha256:" + "a" * 64}
        )
    release.write_json(
        directory / "manifest.json", {"schema_version": 1, "images": images, "files": files}
    )
    sums = {**files, "manifest.json": release.digest(directory / "manifest.json")}
    (directory / "SHA256SUMS").write_text(
        "".join(f"{value}  {name}\n" for name, value in sums.items()), encoding="utf-8"
    )


def test_transfer_checks_every_archive_and_rejects_tampering(tmp_path: Path) -> None:
    fixture_release(tmp_path)
    release.verify(tmp_path)
    (tmp_path / "images/app.tar").write_bytes(b"substituted")
    with pytest.raises(release.ReleaseError, match="checksum mismatch"):
        release.verify(tmp_path)


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/absolute",
        "images/../outside",
        "images\\outside",
        "./images/app.tar",
        "images//app.tar",
    ],
)
def test_transfer_manifest_cannot_escape_release(tmp_path: Path, name: str) -> None:
    with pytest.raises(release.ReleaseError, match="Unsafe"):
        release.safe_path(tmp_path, name)


def test_transfer_requires_all_three_images_and_rejects_unrecorded_files(tmp_path: Path) -> None:
    fixture_release(tmp_path)
    (tmp_path / "unexpected-secret").write_bytes(b"synthetic")
    with pytest.raises(release.ReleaseError, match="unrecorded"):
        release.verify(tmp_path)
    (tmp_path / "unexpected-secret").unlink()
    manifest = json.loads((tmp_path / "manifest.json").read_text("utf-8"))
    manifest["images"].pop()
    release.write_json(tmp_path / "manifest.json", manifest)
    with pytest.raises(release.ReleaseError, match="three"):
        release.verify(tmp_path)
