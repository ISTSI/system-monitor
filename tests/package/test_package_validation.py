"""Package validation must decode UTF-8 independently of the host locale."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import validate_package  # noqa: E402
import reference_contracts  # noqa: E402


class PackageValidationTests(unittest.TestCase):
    def validate_with_windows_locale(self, *, tamper_acceptance: bool = False) -> dict:
        read_text = Path.read_text

        def windows_read_text(path, encoding=None, errors=None):
            text = read_text(path, encoding=encoding or "cp1250", errors=errors)
            if tamper_acceptance and path == ROOT / "docs/09_ACCEPTANCE_TESTS.md":
                text = text.replace("AT01 \u2014 Package and contract baseline", "AT01 \u2014 Altered acceptance", 1)
            return text

        output = StringIO()
        with patch.object(Path, "read_text", windows_read_text), patch.object(sys, "argv", ["validate_package.py"]):
            with redirect_stdout(output):
                self.assertEqual(validate_package.main(), 0)
        return json.loads(output.getvalue())

    def test_utf8_package_validates_with_cp1250_default(self):
        result = self.validate_with_windows_locale()
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["requirements_mapped"], 56)
        self.assertEqual(result["application_acceptance_targets"], 120)

    def test_acceptance_mismatch_still_rejected_with_cp1250_default(self):
        with self.assertRaisesRegex(ValueError, "Acceptance document and index differ"):
            self.validate_with_windows_locale(tamper_acceptance=True)


class GeneratedDirectoryValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()
        manifest = json.loads((ROOT / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
        sources = {ROOT / entry["path"] for entry in manifest["files"]}
        # Current documentation can link to files added after the handoff.
        # Recreate those source files without copying installed dependencies.
        for suffix in (".json", ".md", ".py", ".ts", ".tsx", ".mjs", ".yaml", ".yml", ".log"):
            sources.update(validate_package.source_files(ROOT, suffix))
        for source in sorted(sources):
            destination = self.root / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

    def validate(self):
        with patch.object(validate_package, "ROOT", self.root), patch.object(reference_contracts, "ROOT", self.root):
            with patch.object(sys, "argv", ["validate_package.py"]), redirect_stdout(StringIO()):
                return validate_package.main()

    def test_generated_trees_with_invalid_json_and_links_are_pruned(self):
        for name in validate_package.GENERATED_DIRECTORIES:
            generated = self.root / "backend" / name / "nested"
            generated.mkdir(parents=True)
            (generated / "invalid.json").write_text("invalid JSON", encoding="utf-8")
            (generated / "README.md").write_text("[missing](missing.md)", encoding="utf-8")
        self.assertEqual(self.validate(), 0)

    def test_invalid_source_json_still_rejected(self):
        source = self.root / "backend" / "src"
        source.mkdir(parents=True, exist_ok=True)
        (source / "invalid.json").write_text("invalid JSON", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            self.validate()

    def validate_schemas(self):
        import importlib.util
        if not all(importlib.util.find_spec(name) for name in ("jsonschema", "yaml")):
            self.skipTest("Schema checks require jsonschema and PyYAML")
        import validate_schemas
        with patch.object(validate_schemas, "ROOT", self.root), redirect_stdout(StringIO()):
            return validate_schemas.main()

    def test_schema_scan_prunes_invalid_vendor_yaml(self):
        for name in validate_package.GENERATED_DIRECTORIES:
            generated = self.root / name
            generated.mkdir(parents=True, exist_ok=True)
            (generated / "invalid.yaml").write_text("test: '", encoding="utf-8")
        self.assertEqual(self.validate_schemas(), 0)

    def test_schema_scan_still_rejects_invalid_source_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("Schema checks require PyYAML")
        (self.root / "invalid.yaml").write_text("test: '", encoding="utf-8")
        with self.assertRaises(yaml.YAMLError):
            self.validate_schemas()

    def test_broken_source_markdown_link_still_rejected(self):
        source = self.root / "backend" / "src"
        source.mkdir(parents=True, exist_ok=True)
        (source / "README.md").write_text("[missing](missing.md)", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Broken local Markdown link"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
