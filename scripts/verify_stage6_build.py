"""Compare the final Stage 06 wheel, runtime sources and browser-tested assets."""

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    wheel = ROOT / "backend/dist/system_inspector-0.1.0-py3-none-any.whl"
    package = ROOT / "backend/src/inspector"
    expected = {
        "inspector/" + path.relative_to(package).as_posix(): path
        for path in package.rglob("*")
        if path.is_file() and path.suffix in {".py", ".json", ".html", ".js", ".css"}
    }
    expected.update(
        {
            "inspector/migrations/" + path.relative_to(ROOT / "backend/migrations").as_posix(): path
            for path in (ROOT / "backend/migrations").rglob("*.py")
        }
    )
    expected["inspector/alembic.ini"] = ROOT / "backend/alembic.ini"
    with zipfile.ZipFile(wheel) as archive:
        for member, source in expected.items():
            assert archive.read(member) == source.read_bytes(), member
    review = json.loads((ROOT / "verification/stage-6/frontend-ui-review.json").read_text("utf-8"))
    for relative, checksum in review["source_sha256"].items():
        assert sha((ROOT / relative).read_bytes()) == checksum, relative
    assets = json.loads((package / "web/BUILD_ASSETS.json").read_text("utf-8"))
    for relative, checksum in assets.items():
        assert sha((package / "web" / relative).read_bytes()) == checksum, relative
        assert sha((ROOT / "frontend/dist" / relative).read_bytes()) == checksum, relative
    report = {
        "passed": True,
        "wheel_sha256": sha(wheel.read_bytes()),
        "matched_packaged_files": len(expected),
        "browser_tested_source_files": len(review["source_sha256"]),
        "browser_report": review["browser_report"],
        "assets": assets,
        "runtime_sources": {
            member: sha(source.read_bytes())
            for member, source in expected.items()
            if member.endswith(".py") and not member.startswith("inspector/migrations/")
        },
        "scope": "Source/wheel/browser artifact correspondence; no installation or release qualification.",
    }
    (ROOT / "verification/stage-6/final-artifact-correspondence.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(f"PASS: {len(expected)} packaged files match; browser-tested sources and assets match.")


if __name__ == "__main__":
    main()
