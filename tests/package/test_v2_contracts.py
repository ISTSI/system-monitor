"""Tests of supplied v2 specification assets/oracles/templates, not the future app."""
from __future__ import annotations

from copy import deepcopy
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from reference_contracts import load_json
from reference_v2_contracts import (check_database_semantics, contrast_ratio,
                                    convert_v1_project, policy_allows, resolve_theme)


class ThemeContractTests(unittest.TestCase):
    def test_exactly_two_distinct_modes(self):
        themes = load_json("assets/themes/tokens.json")["themes"]
        self.assertEqual({t["mode"] for t in themes}, {"light", "dark"})
        self.assertEqual(len(themes), 2)
        self.assertNotEqual(themes[0]["tokens"], themes[1]["tokens"])

    def test_same_semantic_token_keys(self):
        themes = load_json("assets/themes/tokens.json")["themes"]
        self.assertEqual(set(themes[0]["tokens"]), set(themes[1]["tokens"]))
        self.assertEqual(len(themes[0]["tokens"]), 21)

    def test_css_matches_json_palette(self):
        css = (ROOT / "assets/themes/tokens.css").read_text()
        for theme in load_json("assets/themes/tokens.json")["themes"]:
            block = re.search(r'html\[data-theme="' + theme["mode"] + r'"\]\s*\{([^}]+)\}', css)
            self.assertIsNotNone(block)
            actual = dict(re.findall(r'--si-([a-z-]+):\s*(#[A-Fa-f0-9]{6});', block.group(1)))
            expected = {k.replace("_", "-"): v for k, v in theme["tokens"].items()}
            self.assertEqual(actual, expected)

    def test_token_text_contrast(self):
        for theme in load_json("assets/themes/tokens.json")["themes"]:
            c = theme["tokens"]
            for fg in ("text", "text_muted", "accent", "success", "warning", "danger", "unknown"):
                for bg in ("canvas", "surface", "raised", "header", "log_background", "input_background", "selection_background"):
                    with self.subTest(theme=theme["mode"], fg=fg, bg=bg):
                        self.assertGreaterEqual(contrast_ratio(c[fg], c[bg]), 4.5)

    def test_token_focus_control_and_flow_contrast(self):
        for theme in load_json("assets/themes/tokens.json")["themes"]:
            c = theme["tokens"]
            for fg in ("focus", "control_border", "flow"):
                for bg in ("canvas", "surface", "raised", "header", "log_background", "input_background", "selection_background"):
                    self.assertGreaterEqual(contrast_ratio(c[fg], c[bg]), 3)

    def test_match_highlight_contrast(self):
        for theme in load_json("assets/themes/tokens.json")["themes"]:
            self.assertGreaterEqual(contrast_ratio(theme["tokens"]["match_text"], theme["tokens"]["match_background"]), 4.5)

    def test_reference_assets_match_recorded_upload_hashes(self):
        for asset in load_json("assets/themes/reference-manifest.json")["references"]:
            raw = (ROOT / asset["package_path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), asset["sha256"])
            self.assertEqual(len(raw), asset["bytes"])
            self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", raw[16:24]), (asset["width"], asset["height"]))

    def test_default_and_explicit_appearance(self):
        self.assertEqual(resolve_theme("default", "light", True), "light")
        self.assertEqual(resolve_theme("default", "dark", False), "dark")
        self.assertEqual(resolve_theme("light", "dark", True), "light")
        self.assertEqual(resolve_theme("dark", "light", False), "dark")

    def test_system_preference(self):
        self.assertEqual(resolve_theme("system", "light", True), "dark")
        self.assertEqual(resolve_theme("system", "dark", False), "light")

    def test_unknown_appearance_rejected(self):
        for args in (("legacy", "dark", True), ("dark", "default", False), ("system", "light", 1)):
            with self.assertRaises(ValueError):
                resolve_theme(*args)

    def test_contrast_oracle_known_values_and_invalid_input(self):
        self.assertAlmostEqual(contrast_ratio("#000000", "#FFFFFF"), 21.0)
        self.assertAlmostEqual(contrast_ratio("#888888", "#888888"), 1.0)
        for c in ("#fff", "transparent", "#GG0000", "#00000080"):
            with self.assertRaises(ValueError):
                contrast_ratio(c, "#FFFFFF")


class AuthorizationContractTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_json("contracts/rbac-policy.json")

    def test_roles_and_default_deny(self):
        self.assertEqual(set(self.policy["roles"]), {"administrator", "inspector"})
        self.assertIs(self.policy["default_deny"], True)

    def test_admin_only_action_set(self):
        expected = {"topology.write", "documentation.write", "shared_view.write", "project_config.read",
                    "project_config.import", "project_config.export", "inventory.import", "connection.manage",
                    "connection.test", "credential.manage", "host_trust.manage", "parser.manage", "parser.test",
                    "settings.read", "settings.write", "appearance.default.write", "users.manage", "audit.read",
                    "operations.metadata.read", "system.create", "system.metadata.write", "system.archive",
                    "system.restore", "inventory.upload", "inventory.source.manage", "inventory.upload.cancel",
                    "credential_binding.manage"}
        actual = {k for k, rule in self.policy["actions"].items() if rule["roles"] == ["administrator"]}
        self.assertEqual(actual, expected)
        for action in expected:
            self.assertFalse(policy_allows("inspector", action, "u1"))
            self.assertTrue(policy_allows("administrator", action, "u1", "u1"))

    def test_safe_topology_reads_both_roles(self):
        for role in self.policy["roles"]:
            for action in ("topology.read", "topology.search", "logs.source_status.read"):
                self.assertTrue(policy_allows(role, action, "u1"))

    def test_each_personal_action_requires_owner_even_for_admin(self):
        for action, rule in self.policy["actions"].items():
            if rule["ownership"] != "self":
                continue
            for role in self.policy["roles"]:
                with self.subTest(action=action, role=role):
                    self.assertEqual(policy_allows(role, action, "u1", "u1"), role in rule["roles"])
                    self.assertFalse(policy_allows(role, action, "u1", "u2"))
                    self.assertFalse(policy_allows(role, action, "u1", None))

    def test_creation_is_server_owned(self):
        for action in ("collection.create", "live.create", "investigation.create", "bundle.import"):
            for role in self.policy["roles"]:
                self.assertTrue(policy_allows(role, action, "u1"))
                self.assertFalse(policy_allows(role, action, "u1", supplied_owner=True))

    def test_admin_stop_exception_does_not_allow_content(self):
        for action in ("collection.cancel", "live.stop"):
            self.assertTrue(policy_allows("administrator", action, "u1", "u2"))
            self.assertFalse(policy_allows("inspector", action, "u1", "u2"))
            self.assertTrue(policy_allows("inspector", action, "u1", "u1"))
            self.assertFalse(policy_allows("administrator", action, "u1", None))
        for action in ("live.read", "collection.read", "download.read", "investigation.read"):
            self.assertFalse(policy_allows("administrator", action, "u1", "u2"))

    def test_disabled_accounts_denied_every_action(self):
        for role in self.policy["roles"]:
            for action in self.policy["actions"]:
                self.assertFalse(policy_allows(role, action, "u1", "u1", enabled=False))

    def test_unauthenticated_unknown_role_and_action_deny(self):
        self.assertFalse(policy_allows("administrator", "topology.read", None))
        self.assertFalse(policy_allows("root", "topology.write", "u1"))
        self.assertFalse(policy_allows("administrator", "terminal.open", "u1"))
        self.assertFalse(policy_allows("administrator", "database.shell", "u1"))


class DatabaseAndCompatibilityContractTests(unittest.TestCase):
    def setUp(self):
        self.config = load_json("examples/deployment-policy.example.json")

    def test_managed_database_semantics(self):
        check_database_semantics(self.config)

    def test_external_database_requires_verified_ca(self):
        self.config["database"]["topology"] = "external"
        with self.assertRaises(ValueError):
            check_database_semantics(self.config)
        self.config["database"]["tls"] = {"mode": "verify_identity", "ca_file": "/etc/inspector/ca.pem"}
        check_database_semantics(self.config)
        self.config["database"]["tls"]["ca_file"] = None
        with self.assertRaises(ValueError):
            check_database_semantics(self.config)

    def test_invalid_ports_rejected(self):
        for value in (True, False, "3306", 0, 65536, 3306.0):
            self.config["database"]["port"] = value
            with self.assertRaises(ValueError):
                check_database_semantics(self.config)

    def test_plain_secret_and_privileged_runtime_rejected(self):
        for key in ("password", "url", "dsn"):
            config = deepcopy(self.config)
            config["database"][key] = "synthetic-secret"
            with self.assertRaises(ValueError):
                check_database_semantics(config)
        for user in ("root", "inspector_migrator"):
            config = deepcopy(self.config)
            config["database"]["username"] = user
            with self.assertRaises(ValueError):
                check_database_semantics(config)

    def test_fallback_and_unsafe_host_path_rejected(self):
        for key, value in (("engine", "sqlite"), ("host", "bad host"), ("password_file", "relative"),
                           ("password_file", "/run/secrets/../escape")):
            config = deepcopy(self.config)
            config["database"][key] = value
            with self.assertRaises(ValueError):
                check_database_semantics(config)

    def test_per_user_budget_cannot_exceed_global(self):
        for name in ("live_processes", "collection_jobs"):
            config = deepcopy(self.config)
            config["limits"][f"max_{name}_per_user"] = config["limits"][f"max_{name}_global"] + 1
            with self.assertRaises(ValueError):
                check_database_semantics(config)

    def test_v1_conversion_matches_v2_example(self):
        legacy = load_json("examples/legacy/project-v1.example.json")
        original = deepcopy(legacy)
        converted, warnings = convert_v1_project(legacy)
        self.assertEqual(converted, load_json("examples/project.example.json"))
        self.assertEqual(legacy, original)
        self.assertEqual(len(warnings), 1)
        self.assertNotIn("theme", converted["settings"]["ui"])

    def test_conversion_rejects_unsupported_version(self):
        for version in ("2.0", "9.0", None):
            legacy = load_json("examples/legacy/project-v1.example.json")
            legacy["schema_version"] = version
            with self.assertRaises(ValueError):
                convert_v1_project(legacy)


@unittest.skipUnless(os.name == "posix", "POSIX secret-file permissions and shell tests")
class DeploymentHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        path = ROOT / "examples/deployment/prepare_secrets.py"
        spec = importlib.util.spec_from_file_location("package_secret_helper", path)
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)
        self.hook = ROOT / "examples/deployment/mariadb/initdb/20-runtime-user.sh"

    def tearDown(self):
        self.temp.cleanup()

    def test_secret_shapes_and_permissions(self):
        output = self.directory / "secrets"
        names = self.helper.prepare(output)
        self.assertEqual(len(names), 4)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
        passwords = []
        for name in names:
            path = output / name
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            value = path.read_text().strip()
            if name.endswith("vault_key"):
                self.assertEqual(len(base64.b64decode(value, validate=True)), 32)
            else:
                self.assertRegex(value, r"^[0-9a-f]{64}$")
                passwords.append(value)
        self.assertEqual(len(set(passwords)), 3)

    def test_secret_generation_never_overwrites(self):
        output = self.directory / "secrets"
        self.helper.prepare(output)
        before = {p.name: p.read_bytes() for p in output.iterdir()}
        with self.assertRaises(ValueError):
            self.helper.prepare(output)
        self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()}, before)

    def test_insecure_directory_rejected(self):
        output = self.directory / "insecure"
        output.mkdir(mode=0o755)
        with self.assertRaises(ValueError):
            self.helper.prepare(output)
        self.assertEqual(list(output.iterdir()), [])

    def test_symlink_directory_rejected(self):
        output = self.directory / "link"
        output.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.helper.prepare(output)

    def test_generator_cli_does_not_print_secrets(self):
        output = self.directory / "secrets"
        result = subprocess.run([sys.executable, str(ROOT / "examples/deployment/prepare_secrets.py"),
                                 "--output-dir", str(output)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in output.iterdir():
            self.assertNotIn(path.read_text().strip(), result.stdout + result.stderr)

    def test_init_hook_bash_syntax_and_nonexecutable_mode(self):
        result = subprocess.run(["bash", "-n", str(self.hook)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.hook.stat().st_mode & 0o111, 0)

    def run_fake_init(self, username="inspector_app", password="a" * 64):
        """Replace the official image SQL helper with a local capture function."""
        secret = self.directory / "password"
        secret.write_text(password + "\n")
        capture = self.directory / "captured.sql"
        env = dict(os.environ, MARIADB_DATABASE="system_inspector", MARIADB_USER="inspector_migrator",
                   INSPECTOR_DB_APP_USER=username, INSPECTOR_DB_APP_PASSWORD_FILE=str(secret),
                   TEST_SQL_CAPTURE=str(capture))
        result = subprocess.run(["bash", "-c", 'docker_process_sql() { cat > "$TEST_SQL_CAPTURE"; }; source "$1"',
                                 "test-only", str(self.hook)], env=env, capture_output=True, text=True, timeout=5)
        return result, capture

    def test_init_hook_emits_limited_grant_to_mock_only(self):
        result, capture = self.run_fake_init()
        self.assertEqual(result.returncode, 0, result.stderr)
        sql = capture.read_text()
        self.assertIn("CREATE USER 'inspector_app'@'%'", sql)
        self.assertIn("GRANT SELECT, INSERT, UPDATE, DELETE ON `system_inspector`.*", sql)
        self.assertNotIn("GRANT ALL", sql)
        self.assertNotIn("a" * 64, result.stdout + result.stderr)

    def test_init_hook_rejects_privileged_or_injected_username(self):
        for username in ("root", "inspector_migrator", "bad';GRANT ALL"):
            result, capture = self.run_fake_init(username=username)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(capture.exists())

    def test_init_hook_rejects_unsafe_bootstrap_password(self):
        result, capture = self.run_fake_init(password="quote'bad")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(capture.exists())
        self.assertNotIn("quote'bad", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
