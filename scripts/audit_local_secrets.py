"""Read-only password leak scan of project sources/logs and built application wheels.

Run as a local identity allowed to read the ignored .secrets directory. No secret
value, verifier or value hash is emitted. This is development verification only.
"""

import json
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    ".git",
    ".secrets",
    "secrets",
    ".bootstrap",
    ".toolchains",
    ".cache",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "test-results",
    "playwright-report",
}


def main() -> int:
    values: set[bytes] = set()
    private_files = 0

    def collect(document: object) -> None:
        if isinstance(document, dict):
            for name, value in document.items():
                if (
                    name in {"password", "password_hash", "csrf_token", "token", "private_key"}
                    and isinstance(value, str)
                    and len(value) >= 12
                ):
                    values.add(value.encode("utf-8"))
                collect(value)
        elif isinstance(document, list):
            for value in document:
                collect(value)

    for private in (ROOT / ".secrets").rglob("*"):
        if not private.is_file():
            continue
        if private.suffix == ".json":
            collect(json.loads(private.read_text(encoding="utf-8")))
            private_files += 1
        elif (
            "password" in private.name
            or private.name.endswith((".key", "-key.pem"))
            or private.name == "vault_key"
        ):
            payload = private.read_bytes().rstrip(b"\r\n")
            if len(payload) >= 12:
                values.add(payload)
                private_files += 1
    if not values:
        raise RuntimeError("No private values were available for the audit.")
    matches: set[str] = set()
    files = 0

    def check(name: str, payload: bytes) -> None:
        nonlocal files
        files += 1
        if any(value in payload for value in values):
            for value in values:
                name = name.replace(value.decode("utf-8", errors="replace"), "[redacted]")
            matches.add(name)

    for directory, children, names in os.walk(ROOT):
        children[:] = [
            name
            for name in children
            if name.casefold() not in EXCLUDED and not name.endswith(".egg-info")
        ]
        for name in names:
            path = Path(directory) / name
            if path.suffix != ".pyc" and not path.is_symlink():
                check(path.relative_to(ROOT).as_posix(), path.read_bytes())
    members = 0
    for wheel in (ROOT / "backend/dist").glob("*.whl"):
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                check(wheel.name + ":" + name, archive.read(name))
                members += 1
    report = {
        "private_files_read": private_files,
        "distinct_private_values_checked": len(values),
        "source_log_and_wheel_entries_scanned": files,
        "wheel_members_scanned": members,
        "matching_files": sorted(matches),
        "scope": "Private/toolchain/cache/build directories excluded; wheel contents scanned explicitly. Values and value hashes never emitted.",
    }
    output = ROOT / "verification/stage-1/secret-audit.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(bool(matches))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError):
        print(
            "Secret audit could not complete; use an authorized local identity and review private files without printing their contents.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
