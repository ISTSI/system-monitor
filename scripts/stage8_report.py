"""Combine executed Stage 08 receipts, retaining explicit open release gates."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "verification/stage-8"


def read(name: str) -> dict:
    return json.loads((DIRECTORY / name).read_text("utf-8"))


def main() -> None:
    original = DIRECTORY / "qualification-agent.json"
    if not original.exists():
        original.write_bytes((DIRECTORY / "qualification.json").read_bytes())
    report = json.loads(original.read_text("utf-8"))
    report["scope"] = (
        "Combined actually executed Stage 08 checks; native and strict clean-host gates remain open."
    )
    report["overall_release_gate"] = "incomplete"
    report["root_checks"] = []
    for name, expected, skipped in (
        ("help-browser-source.json", 4, 0),
        ("browser-source.json", 5, 0),
        ("browser-restored.json", 2, 3),
        ("browser-cold.json", 2, 3),
    ):
        stats = read(name)["stats"]
        if (
            stats["expected"] != expected
            or stats["skipped"] != skipped
            or stats["unexpected"]
            or stats["flaky"]
        ):
            raise ValueError("Browser receipt does not establish its stated outcome")
        report["root_checks"].append(
            {
                "name": name,
                "status": "passed",
                "passed": expected,
                "deliberately_skipped": skipped,
                "evidence": "verification/stage-8/" + name,
            }
        )
    recovery = read("runtime/recovery.json")
    cold = read("runtime/cold-start.json")
    assert recovery["restored_assertions"]["restored"]
    assert recovery["restored_assertions"]["authentication_sessions"] == 0
    assert recovery["restored_assertions"]["recovered_vault_credentials_verified"] == 2
    assert cold["all_three_archives_loaded"] and not cold["clean_image_store_tested"]
    report["root_checks"].extend(
        [
            {
                "name": "Windows backend unit suite",
                "command": "backend/.venv/Scripts/python.exe -m pytest backend/tests/unit -q",
                "passed": 858,
                "skipped": 5,
                "exit_code": 0,
            },
            {
                "name": "Frontend unit/API types",
                "command": "backend/.venv/Scripts/python.exe scripts/frontend.py test",
                "passed": 20,
                "exit_code": 0,
            },
            {
                "name": "Existing live component browser suite",
                "command": "backend/.venv/Scripts/python.exe scripts/frontend.py e2e --config e2e/live_notices.playwright.config.ts",
                "passed": 8,
                "exit_code": 0,
                "scope": "Intercepted HTTP/WebSockets, source components",
            },
            {
                "name": "Ruff/backend format",
                "commands": [
                    "backend/.venv/Scripts/python.exe -m ruff check --config backend/pyproject.toml backend/src backend/tests backend/migrations scripts",
                    "backend/.venv/Scripts/python.exe -m ruff format --check --config backend/pyproject.toml backend/src backend/tests backend/migrations scripts",
                ],
                "exit_code": 0,
            },
            {
                "name": "Ruff/runtime Python 3.9",
                "commands": [
                    "backend/.venv/Scripts/python.exe -m ruff check --config backend/pyproject.toml --target-version py39 deploy/offline",
                    "backend/.venv/Scripts/python.exe -m ruff format --check --config backend/pyproject.toml --target-version py39 deploy/offline",
                ],
                "exit_code": 0,
            },
            {
                "name": "mypy",
                "command": ".venv/Scripts/python.exe -m mypy src (cwd backend)",
                "modules": 37,
                "exit_code": 0,
            },
            {
                "name": "Frontend lint and TypeScript",
                "commands": [
                    "backend/.venv/Scripts/python.exe scripts/frontend.py lint",
                    "backend/.venv/Scripts/python.exe scripts/frontend.py typecheck",
                ],
                "exit_code": 0,
            },
            {
                "name": "Package, schemas, deployment examples",
                "command": "python -m unittest discover -s tests/package -q; python tools/validate_package.py; python tools/validate_schemas.py; python tools/validate_deployment_examples.py",
                "package_tests": 129,
                "exit_code": 0,
                "scope": "Specification consistency; runtime evidence is separate",
            },
            {
                "name": "Final-image all-system recovery",
                "commands": [
                    "python scripts/stage8_runtime.py recover",
                    "python scripts/stage8_runtime.py resume-restore",
                ],
                "first_attempt": "Backup passed; revoke failed on nonexistent error_code column. Corrected shipped SQL; resumed only the unexposed restored copy. Windows helper write/line-ending retries preserved.",
                "final_exit_code": 0,
                "assertions": recovery["restored_assertions"],
                "evidence": "verification/stage-8/runtime/recovery.json",
            },
            {
                "name": "Archive reload and container cold restart",
                "command": "python scripts/stage8_runtime.py cold-restart",
                "exit_code": 0,
                "assertions": cold,
                "evidence": "verification/stage-8/runtime/cold-start.json",
            },
            {
                "name": "Fixture cleanup",
                "command": "python scripts/stage8_runtime.py stop",
                "exit_code": 0,
                "scope": "Only current disposable restored stack; volumes/backups retained",
            },
        ]
    )
    report["review_findings"] = [
        dict(
            item,
            disposition="Corrected and covered by the final operator tests/recovery or documented runtime-template upgrade procedure",
        )
        if item["priority"] != "cleared"
        else item
        for item in report["review_findings"]
    ]
    report["outside_this_report"] = [
        "Native Ubuntu/Rocky/rootless SELinux runtime execution",
        "Strict zero-local-image disposable-host transfer with host/client Internet blocked",
        "Full previous-release artifact/DB/cache upgrade and rollback on target hosts",
        "All historical stage-specific Playwright suites rerun against final images",
        "Fresh sustained paced ten-source latency/RSS measurements at the 16 GB baseline",
        "CVE scan and complete corresponding-source/source-offer distribution review",
    ]
    report["notices_scope"] = (
        "Preserves actual bundled license/copyright texts from all three images plus Python/npm notices. No complete OSS source bundle or invented source offer is claimed."
    )
    (DIRECTORY / "qualification.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("Combined actual Stage 08 receipts; release qualification remains incomplete.")


if __name__ == "__main__":
    main()
