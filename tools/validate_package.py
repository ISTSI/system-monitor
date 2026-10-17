#!/usr/bin/env python3
"""Validate package integrity and semantic fixtures; no third-party dependencies."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from reference_contracts import ROOT, load_json, query_events, read_fixture_source, validate_project, fixture_event_id


GENERATED_DIRECTORIES = frozenset({
    ".git", ".bootstrap", ".toolchains", ".cache", ".venv", "node_modules",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", "build", "dist",
    ".secrets", "secrets", ".state", "state", "cache",
})


def source_files(root: Path, suffix: str) -> list[Path]:
    """Inspect source files without descending into generated/vendor trees."""
    def fail_on_walk_error(error: OSError) -> None:
        raise error

    result = []
    for directory, children, files in os.walk(root, onerror=fail_on_walk_error):
        children[:] = sorted(name for name in children if name.casefold() not in GENERATED_DIRECTORIES)
        result.extend(Path(directory) / name for name in files if Path(name).suffix.casefold() == suffix)
    return sorted(result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-handoff", action="store_true", help="Verify original delivered-file hashes; omit after editing the repository")
    args = parser.parse_args()
    required = ["README.md", "AGENTS.md", "CODEX_START_PROMPT.md", "assets/style-reference.png",
                "docs/01_PRODUCT_REQUIREMENTS.md", "docs/04_LOG_ENGINE.md", "docs/09_ACCEPTANCE_TESTS.md",
                "docs/12_TRACEABILITY.md", "fixtures/expected/query-cases.json", "CODEX_UPGRADE_PROMPT.md",
                "docs/13_ROLES_AND_AUTHORIZATION.md", "docs/14_MARIADB.md", "docs/15_UPGRADING_FROM_V1.md",
                "assets/themes/light-cool-slate.png", "assets/themes/dark-graphite-dusk.png",
                "assets/themes/tokens.json", "assets/themes/tokens.css", "contracts/deployment.schema.json",
                "examples/deployment/compose.mariadb.yaml", "examples/deployment/compose.application.example.yaml",
                "examples/deployment/prepare_secrets.py", "tests/package/test_v2_contracts.py", "tests/package/test_v3_contracts.py",
                "docs/16_MULTI_SYSTEM_WORKSPACES.md", "docs/17_UPGRADING_TO_V3.md",
                "contracts/scope-policy.json", "contracts/live-frame.schema.json",
                "examples/ansible/inventory-with-vars.zip", "examples/systems/alpha.project.json",
                "examples/systems/beta.project.json"]
    for relative in required:
        if not (ROOT / relative).is_file():
            raise ValueError(f"Missing required file: {relative}")
    json_files = source_files(ROOT, ".json")
    for path in json_files:
        json.loads(path.read_text(encoding="utf-8"))
    validate_project(load_json("examples/project.example.json"))
    events = load_json("fixtures/expected/events.json")
    manifest = load_json("fixtures/source-manifest.json")
    data_by_source = {}
    for source in manifest["sources"]:
        raw = read_fixture_source(source)
        if hashlib.sha256(raw).hexdigest() != source["content_sha256"]:
            raise ValueError("Source content checksum mismatch")
        file_hash = hashlib.sha256((ROOT / source["fixture_path"]).read_bytes()).hexdigest()
        if file_hash != source["file_sha256"] or len(raw) != source["uncompressed_bytes"]:
            raise ValueError("Source file checksum/length mismatch")
        data_by_source[source["source_revision_id"]] = raw
    if len({event["event_id"] for event in events}) != len(events):
        raise ValueError("Duplicate expected event IDs")
    for event in events:
        source = event["source"]
        raw = data_by_source[source["source_revision_id"]][source["byte_start"]:source["byte_end"]]
        if hashlib.sha256(raw).hexdigest() != source["content_sha256"]:
            raise ValueError("Event source-byte checksum mismatch")
        if raw.decode("utf-8").removesuffix("\n").removesuffix("\r") != event["raw_line"]:
            raise ValueError("Event raw line differs from source bytes")
        if fixture_event_id(event) != event["event_id"]:
            raise ValueError("Unexpected event identity")
    cases = load_json("fixtures/expected/query-cases.json")
    labels = load_json("fixtures/expected/labels.json")
    for case in cases:
        ids = [event["event_id"] for event in query_events(events, case["request"])]
        if ids != case["expected_event_ids"]:
            raise ValueError(f"Golden query failed: {case['id']}")
        if [labels[name] for name in case["expected_labels"]] != ids:
            raise ValueError("Readable labels differ from golden IDs")
    index = load_json("contracts/acceptance-index.json")
    covered = {rid for item in index for rid in item["requirements"]}
    required_ids = set(re.findall(r"^\| (R\d{2}) \|", (ROOT / "docs/01_PRODUCT_REQUIREMENTS.md").read_text(encoding="utf-8"), re.M))
    if covered != required_ids or required_ids != {f"R{i:02d}" for i in range(1, 57)}:
        raise ValueError("Requirement traceability is incomplete")
    target_ids = [item["id"] for item in index]
    if target_ids != [f"AT{i:02d}" for i in range(1, 121)]:
        raise ValueError("Acceptance index is incomplete or unordered")
    acceptance_text = (ROOT / "docs/09_ACCEPTANCE_TESTS.md").read_text(encoding="utf-8")
    blocks = re.findall(r"^## (AT\d+) — (.+)\n\*\*Requirements:\*\* ([R0-9,]+)\.", acceptance_text, re.M)
    if [{"id": aid, "title": title, "requirements": reqs.split(",")} for aid, title, reqs in blocks] != index:
        raise ValueError("Acceptance document and index differ")
    staged_targets = set()
    for prompt in (ROOT / "prompts").glob("*.md"):
        match = re.search(r"Acceptance targets: ([AT0-9, ]+)\.", prompt.read_text(encoding="utf-8"))
        if not match:
            raise ValueError(f"Missing stage target list in {prompt.name}")
        staged_targets.update(re.findall(r"AT\d+", match[1]))
    if staged_targets != set(target_ids):
        raise ValueError("Stage target coverage is incomplete")
    for asset in load_json("assets/themes/reference-manifest.json")["references"]:
        raw = (ROOT / asset["package_path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != asset["sha256"] or len(raw) != asset["bytes"]:
            raise ValueError("Supplied theme reference changed")
    for path in source_files(ROOT, ".md"):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            if target.startswith(("http:", "https:", "mailto:", "#")):
                continue
            local = target.split("#", 1)[0]
            if local and not (path.parent / local).exists():
                raise ValueError(f"Broken local Markdown link in {path.relative_to(ROOT)}: {target}")
    package_manifest = ROOT / "PACKAGE_MANIFEST.json"
    hashes_checked = 0
    if args.verify_handoff:
        if not package_manifest.exists():
            raise ValueError("Missing handoff checksum manifest")
        for item in json.loads(package_manifest.read_text(encoding="utf-8"))["files"]:
            file = ROOT / item["path"]
            if (not file.is_file() or file.stat().st_size != item["bytes"]
                    or hashlib.sha256(file.read_bytes()).hexdigest() != item["sha256"]):
                raise ValueError(f"Package checksum/size mismatch: {item['path']}")
            hashes_checked += 1
    print(json.dumps({"result": "PASS", "json_files": len(json_files), "fixture_sources": len(data_by_source),
                      "expected_events": len(events), "golden_query_cases": len(cases),
                      "requirements_mapped": len(covered), "application_acceptance_targets": len(index),
                      "package_file_hashes_verified": hashes_checked,
                      "scope": "specification package only; no application/runtime tests"}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
