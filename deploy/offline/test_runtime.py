"""Behavioural security tests for delivered recovery tools; no external services."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fileops
import manage


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        for namespace in ("state", "cache"):
            (self.data / namespace).mkdir(parents=True)
        (self.data / "cache/project-a").mkdir()
        (self.data / "cache/project-a/source.raw").write_bytes(b"A\x00\nretained log\n")
        (self.data / "state/settings").write_bytes(b"private state")
        (self.data / "state/ssh-vault.key").write_bytes(bytes(range(32)))
        self.backup = self.root / "backup"
        self.backup.mkdir()
        records = fileops.snapshot(self.data, self.backup)
        for name, content in (
            ("database.sql", b"synthetic dump"),
            ("database-metadata.txt", b"schema\nprojects\t2\n"),
            ("policy.json", b"{}"),
        ):
            (self.backup / name).write_bytes(content)
            records.append(
                dict(path=name, bytes=len(content), sha256=fileops.digest(self.backup / name))
            )
        self.metadata = dict(
            format="system-inspector-backup-1", vault_key_included=False, files=records
        )
        self.save_manifest()

    def tearDown(self):
        self.temporary.cleanup()

    def save_manifest(self):
        (self.backup / "backup.json").write_text(json.dumps(self.metadata), encoding="utf-8")

    def test_complete_backup_keeps_scoped_raw_bytes_and_excludes_external_key(self):
        # A key outside state/cache is never part of a data snapshot.
        (self.root / "inspector_vault_key").write_text("separate recovery secret")
        manifest = fileops.verify(self.backup)
        names = {record["path"] for record in manifest["files"]}
        self.assertIn("files/cache/project-a/source.raw", names)
        self.assertNotIn("files/state/ssh-vault.key", names)
        self.assertFalse(any("vault_key" in name for name in names))
        self.assertEqual(
            (self.backup / "files/cache/project-a/source.raw").read_bytes(),
            b"A\x00\nretained log\n",
        )

    def test_manifest_cannot_reintroduce_vault_key(self):
        key = self.backup / "files/state/ssh-vault.key"
        key.write_bytes(bytes(range(32)))
        self.metadata["files"].append(
            dict(path="files/state/ssh-vault.key", bytes=32, sha256=fileops.digest(key))
        )
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "Vault key"):
            fileops.verify(self.backup)

    def test_modified_member_fails_before_restore(self):
        (self.backup / "files/cache/project-a/source.raw").write_bytes(b"malicious alteration")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            fileops.verify(self.backup)

    def test_traversal_and_windows_path_members_rejected(self):
        for value in (
            "../outside",
            "/etc/shadow",
            "files/state/../../outside",
            "files\\state\\x",
            "files/state/C:secret",
            "files//state/x",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Unsafe"):
                fileops.relative(value)

    def test_duplicate_and_unlisted_files_rejected(self):
        self.metadata["files"].append(dict(self.metadata["files"][0]))
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "duplicated"):
            fileops.verify(self.backup)
        self.metadata["files"].pop()
        self.save_manifest()
        (self.backup / "unlisted-secret").write_text("untrusted")
        with self.assertRaisesRegex(ValueError, "Unlisted"):
            fileops.verify(self.backup)

    @unittest.skipUnless(os.name == "posix", "Linux filesystem semantics")
    def test_symlink_and_hardlink_members_rejected(self):
        outside = self.root / "outside"
        outside.write_bytes(b"protected")
        path = self.backup / "files/state/settings"
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "regular"):
            fileops.verify(self.backup)
        path.unlink()
        os.link(outside, path)
        with self.assertRaisesRegex(ValueError, "regular"):
            fileops.verify(self.backup)

    @unittest.skipUnless(os.name == "posix" and os.getuid() == 0, "Linux recovery identity")
    def test_restore_preserves_raw_bytes_and_ownership_and_refuses_overwrite(self):
        restored = self.root / "restored"
        for namespace in ("state", "cache"):
            (restored / namespace).mkdir(parents=True)
        fileops.restore(self.backup, restored)
        path = restored / "cache/project-a/source.raw"
        self.assertEqual(path.read_bytes(), b"A\x00\nretained log\n")
        self.assertEqual(path.stat().st_uid, 10001)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, "empty"):
            fileops.restore(self.backup, restored)

    def test_actual_byte_budget_is_enforced_during_copy(self):
        target = self.root / "limited"
        with self.assertRaisesRegex(ValueError, "byte limit"):
            fileops.copy_file(self.data / "state/settings", target, 3)

    @unittest.skipUnless(os.name == "posix" and os.getuid() == 0, "Linux managed recovery identity")
    def test_native_init_key_is_replaced_by_explicit_restore_and_extra_data_is_refused(self):
        # Use real file recovery and native directory permissions. Database I/O
        # is a separate integration gate; this regression isolates the manager's
        # documented init -> restore boundary before any DB contact.
        runtime = manage.Runtime.__new__(manage.Runtime)
        runtime.root = self.root / "fresh-runtime"
        runtime.stack = "inspector-0123456789"
        runtime.settings = {"external": False}
        runtime.images = {"app": {"image_id": "synthetic-unit-fixture"}}
        runtime.config = {}
        for name in ("secrets", "data/state", "data/cache"):
            (runtime.root / name).mkdir(parents=True, mode=0o700)
        initial_key = bytes(reversed(range(32)))
        (runtime.root / "secrets/inspector_vault_key").write_bytes(initial_key)
        (runtime.root / "data/state/ssh-vault.key").write_bytes(initial_key)
        (runtime.root / "application.yaml").write_text("{}", encoding="utf-8")
        policy = {name: {} for name in ("limits", "retention", "auth", "bootstrap_settings")}
        (self.backup / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
        self.metadata["images"] = runtime.images
        for row in self.metadata["files"]:
            if row["path"] == "policy.json":
                row.update(
                    bytes=(self.backup / "policy.json").stat().st_size,
                    sha256=fileops.digest(self.backup / "policy.json"),
                )
        self.save_manifest()
        key = self.root / "separate-raw-key"
        key.write_bytes(bytes(range(32)))
        database_actions = []
        runtime.preflight = lambda: None
        runtime.exists = lambda *_: False
        runtime.database = lambda: database_actions.append("database")

        def file_operation(action, backup=None, *, key=None):
            if action == "restore":
                fileops.restore(backup, runtime.root / "data")
            elif action == "bind-key":
                fileops.bind_key(runtime.root / "data", key)
            else:
                self.fail("Unexpected recovery file operation")

        def database(action, **kwargs):
            database_actions.append(action)
            if action == "inspect":
                return (self.backup / "database-metadata.txt").read_text(encoding="utf-8")
            if action == "restore":
                self.assertEqual(kwargs["stdin"].read(), b"synthetic dump")

        runtime.file_operation = file_operation
        runtime.db = database
        extra = runtime.root / "data/cache/retained-unexpected-data"
        extra.write_bytes(b"must survive rejection")
        with self.assertRaisesRegex(ValueError, "empty"):
            runtime.restore(self.backup, key)
        self.assertEqual((runtime.root / "data/state/ssh-vault.key").read_bytes(), initial_key)
        self.assertEqual(database_actions, [])
        extra.unlink()
        runtime.restore(self.backup, key)
        self.assertEqual((runtime.root / "data/state/ssh-vault.key").read_bytes(), bytes(range(32)))
        self.assertEqual(
            (runtime.root / "data/cache/project-a/source.raw").read_bytes(),
            b"A\x00\nretained log\n",
        )
        self.assertEqual(database_actions, ["database", "restore", "inspect", "revoke"])

    @unittest.skipUnless(
        os.name == "posix" and os.getuid() == 0 and importlib.util.find_spec("inspector"),
        "Linux backend runner with a service UID",
    )
    def test_actual_backend_vault_accepts_rebound_raw_key_and_rejects_wrong_modes(self):
        self.root.chmod(0o755)
        self.data.chmod(0o755)
        recovery = self.root / "separate-vault-key"
        recovery.write_bytes(bytes(range(32)))
        fileops.bind_key(self.data, recovery)
        fileops.own(self.data)
        key = self.data / "state/ssh-vault.key"

        def as_service():
            os.setgroups([])
            os.setgid(10001)
            os.setuid(10001)

        program = """
import sys
from types import SimpleNamespace
from inspector.ssh_access import Vault
vault = Vault(sys.argv[1])
if sys.argv[2] == 'available':
    assert vault.available
    nonce, ciphertext = vault.encrypt('synthetic-credential', 'read-only-test-password')
    assert vault.decrypt(SimpleNamespace(id='synthetic-credential', key_version=1, nonce=nonce, ciphertext=ciphertext)) == 'read-only-test-password'
else:
    assert not vault.available
"""
        subprocess.run(
            [sys.executable, "-B", "-c", program, str(key), "available"],
            check=True,
            preexec_fn=as_service,
        )
        key.chmod(0o644)
        subprocess.run(
            [sys.executable, "-B", "-c", program, str(key), "unavailable"],
            check=True,
            preexec_fn=as_service,
        )
        key.chmod(0o600)
        os.chown(key, 0, 0)
        subprocess.run(
            [sys.executable, "-B", "-c", program, str(key), "unavailable"],
            check=True,
            preexec_fn=as_service,
        )


class RecipeTests(unittest.TestCase):
    def test_password_files_preserve_utf8_reserved_characters_and_single_terminator(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "external-password"
            value = '  Synthetic #;@:/?% "quote" \\ slash żółć  '.encode()
            for suffix in (b"", b"\n", b"\r\n"):
                path.write_bytes(value + suffix)
                self.assertEqual(manage.database_secret(path), value)
            for invalid in (
                b"",
                value + b"\n\n",
                b"embedded\x00nul",
                b"embedded\rcarriage",
                b"bad\xffutf8",
                b"x" * 4097,
            ):
                path.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    manage.database_secret(path)

    @unittest.skipUnless(importlib.util.find_spec("yaml"), "YAML build-time validation dependency")
    def test_every_tmpfs_mount_is_absolute_and_preserves_option_commas(self):
        import yaml

        for name in ("compose.yaml", "compose.external.yaml"):
            document = yaml.safe_load((Path(__file__).parent / name).read_text(encoding="utf-8"))
            for role in ("migrate", "app", "proxy"):
                with self.subTest(name=name, role=role):
                    mounts = document["services"][role]["tmpfs"]
                    self.assertEqual(len(mounts), 1)
                    self.assertTrue(mounts[0].startswith("/tmp:"))
                    self.assertIn(",mode=1777", mounts[0])

    @unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "Linux sourced init helper")
    def test_sourced_provisioning_accepts_official_helpers_empty_argv(self):
        program = """
docker_process_sql() {
  if [ "$1" = '--unused-option' ]; then shift; fi
  cat
}
source "$1"
"""
        environment = dict(
            os.environ,
            MARIADB_DATABASE="system_inspector",
            MARIADB_USER="inspector_migrator",
            INSPECTOR_DB_APP_USER="inspector_app",
        )
        # A private generated-format test secret is mounted at the fixed path
        # only in the real MariaDB lifecycle. For this helper boundary, replace
        # cat so the empty-argv official function is exercised without that mount.
        program = (
            "cat() { if [ \"${1:-}\" = /run/secrets/inspector_db_password ]; then printf '%064d' 0; else command cat; fi; }\n"
            + program
        )
        result = subprocess.run(
            ["bash", "-c", program, "test", str(Path(__file__).parent / "20-runtime-user.sh")],
            env=environment,
            capture_output=True,
            check=True,
        )
        self.assertIn(b"GRANT SELECT, INSERT, UPDATE, DELETE", result.stdout)
        self.assertIn(b"`system\\_inspector`.*", result.stdout)
        self.assertNotIn(b"GRANT ALL", result.stdout)

    @unittest.skipUnless(
        os.name == "posix" and shutil.which("openssl"), "Linux certificate provisioning"
    )
    def test_initialization_binds_certificate_and_generates_raw_private_key(self):
        from argparse import Namespace

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            certificate, key = root / "server.crt", root / "server.key"
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "ec",
                    "-pkeyopt",
                    "ec_paramgen_curve:P-256",
                    "-nodes",
                    "-days",
                    "2",
                    "-subj",
                    "/CN=localhost",
                    "-addext",
                    "subjectAltName=DNS:localhost",
                    "-keyout",
                    str(key),
                    "-out",
                    str(certificate),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            args = Namespace(
                runtime=root / "runtime",
                origin="https://localhost:8443",
                bind_address="127.0.0.1",
                certificate=certificate,
                private_key=key,
                external_db=None,
                engine="docker",
            )
            manage.initialize(args)
            raw = (args.runtime / "secrets/inspector_vault_key").read_bytes()
            self.assertEqual(len(raw), 32)
            state_key = args.runtime / "data/state/ssh-vault.key"
            self.assertEqual(state_key.read_bytes(), raw)
            self.assertEqual(state_key.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "new or empty"):
                manage.initialize(args)


if __name__ == "__main__":
    unittest.main()
