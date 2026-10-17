"""Exercise the configured external-client TLS context against local certificates."""

import asyncio
import ssl
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from inspector.config import parse_config

ROOT = Path(__file__).resolve().parents[3]


def certificate_pair(tmp_path, *, expired=False):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "db.example.test")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now - timedelta(days=1) if expired else now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("db.example.test")]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    certificate = tmp_path / "server.pem"
    keyfile = tmp_path / "server.key"
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return certificate, keyfile


@pytest.mark.parametrize("fault", [None, "wrong_ca", "wrong_hostname", "expired"])
async def test_external_tls_fails_closed_without_plaintext_retry(tmp_path, fault):
    cert, key = certificate_pair(tmp_path, expired=fault == "expired")
    trusted = cert
    if fault == "wrong_ca":
        other = tmp_path / "other"
        other.mkdir()
        trusted, _ = certificate_pair(other)
    db = parse_config((ROOT / "examples/deployment-policy.example.yaml").read_bytes(), {}).database
    configured = replace(
        db, topology="external", tls={"mode": "verify_identity", "ca_file": str(trusted)}
    )
    client_context = configured.ssl_context()
    assert client_context.verify_mode == ssl.CERT_REQUIRED and client_context.check_hostname
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert, key)

    async def connected(reader, writer):
        writer.write(b"verified")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(connected, "127.0.0.1", 0, ssl=server_context)
    async with server:
        port = server.sockets[0].getsockname()[1]
        hostname = "wrong.example.test" if fault == "wrong_hostname" else "db.example.test"
        if fault:
            with pytest.raises(ssl.SSLCertVerificationError):
                await asyncio.open_connection(
                    "127.0.0.1", port, ssl=client_context, server_hostname=hostname
                )
        else:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", port, ssl=client_context, server_hostname=hostname
            )
            assert await reader.read() == b"verified"
            writer.close()
            await writer.wait_closed()
