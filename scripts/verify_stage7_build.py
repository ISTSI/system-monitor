"""Verify frozen runtime sources, the isolated Stage 07 wheel and bundled assets.

No build, installation, network access or retained deployment mutation is done.
The build command records its inputs; verification refuses an unrecorded or
changed source tree, stale copied modules, or inconsistent frontend/wheel files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BUILD_RELATIVE = Path(".state/stage7-build")
_FRONTEND_FILES = (
    "index.html",
    "package.json",
    "package-lock.json",
    "vite.config.ts",
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.node.json",
)
_BACKEND_FILES = ("pyproject.toml", "uv.lock", "alembic.ini")


class BuildVerificationError(ValueError):
    pass


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(directory: Path, *, exclude_web: bool = False) -> dict[str, str]:
    if directory.is_symlink() or not directory.is_dir():
        raise BuildVerificationError("Required build/source directory is absent.")
    result = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if exclude_web and relative.parts[:2] == ("inspector", "web"):
            continue
        if path.is_symlink():
            raise BuildVerificationError("Build/source links are unsupported.")
        if path.is_file():
            result[relative.as_posix()] = file_hash(path)
    return result


def source_hashes(root: Path = ROOT) -> dict[str, str]:
    """Include runtime/build inputs; exclude tests, docs, secrets and progress."""
    result = {}
    for relative, exclude_web in (
        ("backend/src", True),
        ("backend/migrations", False),
        ("frontend/src", False),
    ):
        result.update(
            {
                f"{relative}/{name}": digest
                for name, digest in tree_hashes(root / relative, exclude_web=exclude_web).items()
            }
        )
    if (root / "frontend/public").is_dir():
        result.update(
            {
                f"frontend/public/{name}": digest
                for name, digest in tree_hashes(root / "frontend/public").items()
            }
        )
    for name in _BACKEND_FILES:
        result["backend/" + name] = file_hash(root / "backend" / name)
    for name in _FRONTEND_FILES:
        path = root / "frontend" / name
        if path.is_file():
            result["frontend/" + name] = file_hash(path)
    for name in (
        "scripts/frontend.py",
        "scripts/build_stage7.py",
        "scripts/verify_stage7_build.py",
        "scripts/generate_casefold.py",
    ):
        result[name] = file_hash(root / name)
    return dict(sorted(result.items()))


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def record_inputs(root: Path, hashes: dict[str, str]) -> None:
    if source_hashes(root) != hashes:
        raise BuildVerificationError(
            "Runtime/build inputs changed during the build; freeze sources and build again."
        )
    destination = root / BUILD_RELATIVE / "BUILD_INPUTS.json"
    destination.write_text(
        json.dumps(
            {"schema_version": 1, "sources": hashes, "sources_sha256": _digest(hashes)},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _compare(expected: dict[str, str], actual: dict[str, str]) -> dict[str, list[str]]:
    return {
        "missing": sorted(expected.keys() - actual.keys()),
        "extra": sorted(actual.keys() - expected.keys()),
        "changed": sorted(
            name for name in expected.keys() & actual.keys() if expected[name] != actual[name]
        ),
    }


def verify_build(root: Path = ROOT) -> dict[str, Any]:
    directory = root / BUILD_RELATIVE
    manifest_path = directory / "BUILD_INPUTS.json"
    if not manifest_path.is_file():
        raise BuildVerificationError(
            "Build-input manifest is absent; run the isolated Stage 07 build after the source freeze."
        )
    manifest = json.loads(manifest_path.read_text("utf-8"))
    recorded = manifest.get("sources")
    if (
        manifest.get("schema_version") != 1
        or not isinstance(recorded, dict)
        or manifest.get("sources_sha256") != _digest(recorded)
    ):
        raise BuildVerificationError("Invalid build-input manifest.")
    checks = {"current_sources": _compare(recorded, source_hashes(root))}
    current_backend = tree_hashes(root / "backend/src", exclude_web=True)
    staged_backend = tree_hashes(directory / "backend/src", exclude_web=True)
    checks["staged_backend_sources"] = _compare(current_backend, staged_backend)
    current_migrations = tree_hashes(root / "backend/migrations")
    checks["staged_migrations"] = _compare(
        current_migrations, tree_hashes(directory / "backend/migrations")
    )
    checks["staged_backend_build_inputs"] = _compare(
        {name: file_hash(root / "backend" / name) for name in _BACKEND_FILES},
        {name: file_hash(directory / "backend" / name) for name in _BACKEND_FILES},
    )
    frontend = tree_hashes(directory / "frontend")
    web = tree_hashes(directory / "backend/src/inspector/web")
    asset_manifest_path = directory / "backend/src/inspector/web/BUILD_ASSETS.json"
    asset_manifest = json.loads(asset_manifest_path.read_text("utf-8"))
    if not isinstance(asset_manifest, dict):
        raise BuildVerificationError("Invalid frontend asset manifest.")
    checks["frontend_manifest"] = _compare(asset_manifest, frontend)
    checks["backend_web_assets"] = _compare(
        frontend,
        {name: digest for name, digest in web.items() if name != "BUILD_ASSETS.json"},
    )
    wheels = sorted((directory / "backend/dist").glob("*.whl"))
    if len(wheels) != 1:
        raise BuildVerificationError("Expected exactly one isolated Stage 07 wheel.")
    wheel = wheels[0]
    expected_wheel = {
        **{f"{name}": digest for name, digest in current_backend.items()},
        **{f"inspector/migrations/{name}": digest for name, digest in current_migrations.items()},
        **{f"inspector/web/{name}": digest for name, digest in web.items()},
        "inspector/alembic.ini": file_hash(root / "backend/alembic.ini"),
    }
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise BuildVerificationError("Wheel contains duplicate members.")
        actual_wheel = {
            name: hashlib.sha256(archive.read(name)).hexdigest()
            for name in names
            if name.startswith("inspector/") and not name.endswith("/")
        }
    checks["wheel_runtime_files"] = _compare(expected_wheel, actual_wheel)
    success = not any(paths for check in checks.values() for paths in check.values())
    return {
        "verified": success,
        "runtime_source_count": len(recorded),
        "sources_sha256": manifest["sources_sha256"],
        "build_inputs_sha256": file_hash(manifest_path),
        "frontend_assets": frontend,
        "wheel": wheel.name,
        "wheel_sha256": file_hash(wheel),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "verification/stage-7/build-verification.json",
    )
    args = parser.parse_args()
    try:
        report = verify_build()
    except (BuildVerificationError, OSError, ValueError, zipfile.BadZipFile) as error:
        report = {"verified": False, "error": str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "Stage 07 build verification passed."
        if report["verified"]
        else "Stage 07 build verification failed; inspect the verification report."
    )
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
