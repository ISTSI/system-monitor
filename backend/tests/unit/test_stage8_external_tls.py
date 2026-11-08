"""Safety boundaries for the privileged, disposable real-MariaDB TLS qualifier."""

import importlib.util
import ssl
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from cryptography import x509

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "stage8_external_tls", ROOT / "scripts/stage8_external_tls.py"
)
assert SPEC is not None and SPEC.loader is not None
qualification = importlib.util.module_from_spec(SPEC)
# The standalone runner's sibling import uses this repository's existing helper.
LOCAL_SPEC = importlib.util.spec_from_file_location(
    "local_mariadb", ROOT / "scripts/local_mariadb.py"
)
assert LOCAL_SPEC is not None and LOCAL_SPEC.loader is not None
local = importlib.util.module_from_spec(LOCAL_SPEC)
LOCAL_SPEC.loader.exec_module(local)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "local_mariadb", local)
    SPEC.loader.exec_module(qualification)
    monkeypatch.setattr(
        local, "private_directory", lambda path: path.mkdir(parents=True, exist_ok=True)
    )
    qualification.fixture_configuration(tmp_path)
    return tmp_path


def test_fixture_ca_identity_and_expiry_exercise_strict_tls_validation(prepared):
    valid = x509.load_pem_x509_certificate((prepared / "valid/server.pem").read_bytes())
    expired = x509.load_pem_x509_certificate((prepared / "expired/server.pem").read_bytes())
    authority = x509.load_pem_x509_certificate((prepared / "client/ca.pem").read_bytes())
    wrong = x509.load_pem_x509_certificate((prepared / "client/wrong-ca.pem").read_bytes())
    now = datetime.now(UTC)
    assert valid.not_valid_before_utc < now < valid.not_valid_after_utc
    assert expired.not_valid_after_utc < now < authority.not_valid_after_utc
    assert authority.public_key() != wrong.public_key()
    for cert in (valid, expired):
        assert cert.issuer == authority.subject
        assert cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)
    assert valid.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value.get_values_for_type(x509.DNSName) == [qualification.HOSTNAME]
    assert authority.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign


def test_external_config_and_mounts_keep_root_secret_out_of_client(prepared):
    document = yaml.safe_load((prepared / "client/application.yaml").read_text("utf-8"))
    assert document["database"]["topology"] == "external"
    assert document["database"]["host"] == qualification.HOSTNAME
    assert document["database"]["tls"] == {
        "mode": "verify_identity",
        "ca_file": "/qualification/ca.pem",
    }
    assert not list((prepared / "client").glob("*root*"))
    assert not list((prepared / "client").glob("*.key"))
    argv = qualification.server_arguments(
        "own-fixture",
        "own-network",
        prepared / "valid",
        "mariadb:11.8.9@sha256:" + "a" * 64,
        expired=False,
    )
    assert "--pull=never" in argv and "--security-opt=no-new-privileges:true" in argv
    assert not any(
        argument in {"--publish", "-p", "--privileged", "--net=host", "--network=host"}
        for argument in argv
    )
    assert not any("docker.sock" in argument or "docker_engine" in argument for argument in argv)
    root_password = (prepared / "valid/root_password").read_text().strip()
    assert root_password not in " ".join(argv)
    assert "--env=MARIADB_ROOT_PASSWORD_FILE=/run/qualification/root_password" in argv


def test_nested_driver_errors_retain_certificate_failure_evidence(prepared):
    certificate = ssl.SSLCertVerificationError(1, "synthetic validation failure")
    driver = RuntimeError("synthetic driver wrapper")
    driver.__cause__ = certificate
    outer = RuntimeError("synthetic SQLAlchemy wrapper")
    outer.__context__ = driver
    assert qualification.exception_chain(outer) == [outer, driver, certificate]
    certificate.__context__ = outer
    assert qualification.exception_chain(outer) == [outer, driver, certificate]
