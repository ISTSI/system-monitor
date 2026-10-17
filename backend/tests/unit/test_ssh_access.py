"""Vault confidentiality, authenticated binding and bounded setup-check admission."""

import copy
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from inspector.config import parse_config
from inspector.domain import Principal
from inspector.errors import DomainError
from inspector.persistence.models import SSHCredential
from inspector.ssh_access import PasswordInput, SSHAccess, Vault, route_digest

ROOT = Path(__file__).resolve().parents[3]


def vault_file(tmp_path, raw=None):
    path = tmp_path / "ssh-vault.key"
    path.write_bytes(os.urandom(32) if raw is None else raw)
    path.chmod(0o600)
    return path


def test_password_authenticated_encryption_binds_id_and_key_version(tmp_path):
    vault = Vault(str(vault_file(tmp_path)))
    secret = "synthetic-$ecret-password"
    first = vault.encrypt("credential-a", secret)
    second = vault.encrypt("credential-a", secret)
    assert first != second
    assert len(first[0]) == 12 and len(first[1]) == len(secret.encode()) + 16
    assert all(secret.encode() not in part for part in first)
    row = SSHCredential(
        id="credential-a", revision=1, key_version=1, nonce=first[0], ciphertext=first[1]
    )
    assert vault.decrypt(row) == secret
    row.id = "credential-b"
    with pytest.raises(DomainError, match="cannot be decrypted"):
        vault.decrypt(row)
    row.id, row.key_version = "credential-a", 2
    with pytest.raises(DomainError, match="cannot be decrypted"):
        vault.decrypt(row)


@pytest.mark.parametrize("raw", [b"", b"a" * 31, b"a" * 33, b"a" * 2048])
def test_missing_or_invalid_master_key_keeps_vault_disabled(tmp_path, raw):
    vault = Vault(str(vault_file(tmp_path, raw)))
    assert not vault.available
    with pytest.raises(DomainError) as denied:
        vault.encrypt("id", "synthetic-secret")
    assert denied.value.code == "SSH_VAULT_UNAVAILABLE"
    assert "synthetic-secret" not in str(denied.value)


def test_directory_and_absent_key_do_not_enable_vault(tmp_path):
    assert not Vault("").available
    assert not Vault(str(tmp_path / "absent")).available
    assert not Vault(str(tmp_path)).available


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission contract applies to Linux server")
def test_group_readable_key_and_symlink_are_rejected(tmp_path):
    path = vault_file(tmp_path)
    path.chmod(0o640)
    assert not Vault(str(path)).available
    path.chmod(0o600)
    link = tmp_path / "link.key"
    link.symlink_to(path)
    assert not Vault(str(link)).available


@pytest.mark.parametrize("secret", ["", "x" * 1025, "\x00", "\ud800", "ą" * 513])
def test_password_boundaries_never_repeat_secret(tmp_path, secret):
    vault = Vault(str(vault_file(tmp_path)))
    with pytest.raises(DomainError) as denied:
        vault.encrypt("id", secret)
    assert denied.value.code == "INVALID_SSH_PASSWORD"
    assert str(denied.value) == "Use a nonempty password of at most 1024 UTF-8 bytes."


def test_write_only_input_repr_hides_password():
    payload = PasswordInput(
        expected_config_revision=1, expected_credential_revision=0, password="synthetic-secret"
    )
    assert "synthetic-secret" not in repr(payload)
    with pytest.raises(ValidationError):
        PasswordInput(expected_config_revision=1, expected_credential_revision=0, password="")


def test_route_identity_tracks_endpoint_route_alias_but_ignores_layout_names():
    route = [
        dict(
            id="target",
            name="Friendly name",
            host="192.0.2.20",
            port=22,
            username="logs",
            credential_ref="unresolved-a",
            jump_connection_id="jump",
        ),
        dict(
            id="jump",
            host="192.0.2.10",
            port=22,
            username="jump-logs",
            credential_ref="unresolved-b",
            jump_connection_id=None,
        ),
    ]
    expected = route_digest(route)
    renamed = copy.deepcopy(route)
    renamed[0]["name"] = "New friendly name"
    assert route_digest(renamed) == expected
    for index, key, value in [
        (0, "host", "192.0.2.21"),
        (0, "port", 2222),
        (0, "credential_ref", "other"),
        (1, "host", "192.0.2.11"),
        (1, "username", "other"),
    ]:
        changed = copy.deepcopy(route)
        changed[index][key] = value
        assert route_digest(changed) != expected


def test_network_admission_has_no_unbounded_pending_queue():
    config = parse_config((ROOT / "examples/deployment-policy.example.yaml").read_bytes(), {})
    access = SSHAccess(config, None)
    actor = Principal("synthetic-admin", "administrator", 1)
    for _ in range(4):
        access._reserve(actor)
    with pytest.raises(DomainError) as denied:
        access._reserve(actor)
    assert denied.value.status == 429
    access._network_active = 0
    for _ in range(6):
        access._reserve(actor)
        access._network_active = 0
    with pytest.raises(DomainError) as denied:
        access._reserve(actor)
    assert denied.value.code == "LIMIT_REACHED"
