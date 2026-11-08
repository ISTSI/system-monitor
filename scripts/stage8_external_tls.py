"""Qualify the real asyncmy/MariaDB external-TLS path on an isolated local network.

Only fresh named containers and an internal Docker network are created. No ports,
existing volumes, production endpoints, pulls, package installers or retained
application containers are used. Private fixture files remain under .secrets;
the public receipt records only assertions, image identities and runtime facts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import ssl
import subprocess
import time
import traceback
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import local_mariadb as local
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
DATABASE = "inspector_test_s8tls"
HOSTNAME = "database.stage8.test"
EXPIRED_HOSTNAME = "expired.stage8.test"
WRONG_HOSTNAME = "wrong.stage8.test"


def certificates(directory: Path) -> None:
    """Generate a private test CA and valid/expired server certificates."""
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Stage 08 synthetic CA")])
    authority = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    for label, hostname, expired in (
        ("valid", HOSTNAME, False),
        ("expired", EXPIRED_HOSTNAME, True),
    ):
        server_dir = directory / label
        local.private_directory(server_dir)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        leaf = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
            .issuer_name(authority.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=2))
            .not_valid_after(now - timedelta(days=1) if expired else now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(True, False, True, False, False, False, False, False, False),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                critical=False,
            )
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        for path, content in (
            (server_dir / "server.pem", leaf.public_bytes(serialization.Encoding.PEM)),
            (server_dir / "ca.pem", authority.public_bytes(serialization.Encoding.PEM)),
            (
                server_dir / "server.key",
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                ),
            ),
        ):
            local.write_private(path, content.decode("ascii"), mounted_secret=True)
    client_dir = directory / "client"
    local.private_directory(client_dir)
    local.write_private(
        client_dir / "ca.pem",
        authority.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        mounted_secret=True,
    )
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(other_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(other_key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(other_key.public_key()),
            critical=False,
        )
        .sign(other_key, hashes.SHA256())
    )
    local.write_private(
        client_dir / "wrong-ca.pem",
        other.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        mounted_secret=True,
    )


def fixture_configuration(directory: Path) -> None:
    certificates(directory)
    app_password = "  #; quote'\\Zażółć-𝔘-" + secrets.token_hex(16) + "  "
    migration_password = "  #; migration'\\gęślą-𝔘-" + secrets.token_hex(16) + "  "
    scope = local.grant_schema_pattern(DATABASE)
    quoted_app = app_password.replace("'", "''")
    quoted_migration = migration_password.replace("'", "''")
    sql = (
        "SET sql_mode='NO_BACKSLASH_ESCAPES';\n"
        f"CREATE USER 'inspector_tls_app'@'%' IDENTIFIED BY '{quoted_app}' REQUIRE SSL;\n"
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{scope}`.* TO 'inspector_tls_app'@'%';\n"
        f"CREATE USER 'inspector_tls_migrator'@'%' IDENTIFIED BY '{quoted_migration}' REQUIRE SSL;\n"
        f"GRANT ALL PRIVILEGES ON `{scope}`.* TO 'inspector_tls_migrator'@'%';\n"
    )
    for label in ("valid", "expired"):
        server = directory / label
        local.write_private(
            server / "root_password", secrets.token_hex(32) + "\n", mounted_secret=True
        )
        local.write_private(server / "bootstrap.sql", sql, mounted_secret=True)
        local.write_private(
            server / "server.cnf",
            "[mariadb]\nssl_ca=/run/qualification/ca.pem\n"
            "ssl_cert=/run/qualification/server.pem\nssl_key=/run/qualification/server.key\n"
            "require_secure_transport=ON\nskip-name-resolve\n",
            mounted_secret=True,
        )
    client = directory / "client"
    local.write_private(client / "app_password", app_password + "\n", mounted_secret=True)
    local.write_private(
        client / "migration_password", migration_password + "\n", mounted_secret=True
    )
    document = yaml.safe_load((ROOT / "examples/deployment-policy.example.yaml").read_text("utf-8"))
    document["deployment"].update(
        public_origin="https://qualification.stage8.test",
        state_dir="/tmp/qualification-state",
        cache_dir="/tmp/qualification-cache",
    )
    document["database"].update(
        topology="external",
        host=HOSTNAME,
        name=DATABASE,
        username="inspector_tls_app",
        password_file="/qualification/app_password",
        tls={"mode": "verify_identity", "ca_file": "/qualification/ca.pem"},
    )
    local.write_private(client / "application.yaml", yaml.safe_dump(document), mounted_secret=True)


def server_arguments(
    name: str, network: str, directory: Path, image: str, *, expired: bool
) -> list[str]:
    argv = [
        "docker",
        "run",
        "--detach",
        "--pull=never",
        "--name",
        name,
        "--network",
        network,
        "--network-alias",
        EXPIRED_HOSTNAME if expired else HOSTNAME,
        "--label",
        "system-inspector.qualification=stage8-tls",
        "--cap-drop=ALL",
        "--cap-add=CHOWN",
        "--cap-add=SETUID",
        "--cap-add=SETGID",
        "--cap-add=DAC_OVERRIDE",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=256",
        "--memory=768m",
        "--tmpfs=/var/lib/mysql:rw,size=536870912",
        "--tmpfs=/run/mysqld:rw",
        "--mount",
        f"type=bind,src={directory.as_posix()},dst=/run/qualification,readonly",
        "--mount",
        f"type=bind,src={(directory / 'server.cnf').as_posix()},dst=/etc/mysql/conf.d/qualification.cnf,readonly",
        "--mount",
        f"type=bind,src={(directory / 'bootstrap.sql').as_posix()},dst=/docker-entrypoint-initdb.d/20-runtime.sql,readonly",
        "--env=MARIADB_ROOT_PASSWORD_FILE=/run/qualification/root_password",
        f"--env=MARIADB_DATABASE={DATABASE}",
        "--env=MARIADB_ROOT_HOST=localhost",
        "--health-cmd=healthcheck.sh --connect --innodb_initialized",
        "--health-interval=2s",
        "--health-timeout=3s",
        "--health-retries=45",
    ]
    if not expired:
        argv.extend(["--network-alias", WRONG_HOSTNAME])
    return [*argv, image]


def exception_chain(error: BaseException) -> list[BaseException]:
    result = []
    seen = set()
    while error is not None and id(error) not in seen:
        result.append(error)
        seen.add(id(error))
        error = error.__cause__ or error.__context__
    return result


async def worker() -> dict[str, object]:
    """Use production config, driver, migrations, authorization and HTTP routes."""
    import httpx
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from inspector import auth
    from inspector.app import create_app
    from inspector.cli import migrate
    from inspector.config import parse_config
    from inspector.database import check_runtime_grants, create_engine

    config_path = Path("/qualification/application.yaml")
    config = parse_config(await asyncio.to_thread(config_path.read_bytes), environment={})
    await migrate(config_path, "inspector_tls_migrator", Path("/qualification/migration_password"))
    engine = create_engine(config.database)
    administrator_password = secrets.token_urlsafe(24)
    try:
        async with engine.connect() as connection:
            await check_runtime_grants(connection)
            version = str(await connection.scalar(text("SELECT VERSION()")))
            cipher = (
                await connection.execute(text("SHOW SESSION STATUS LIKE 'Ssl_cipher'"))
            ).one()[1]
            assert "mariadb" in version.lower() and cipher
        async with async_sessionmaker(engine).begin() as session:
            await auth.bootstrap_admin(
                session, "tls-admin", "TLS qualification", administrator_password
            )
    finally:
        await engine.dispose()
    app = create_app(config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=config.public_origin,
            headers={"Origin": config.public_origin},
        ) as client:
            assert (await client.get("/api/v1/health/ready")).status_code == 200
            assert (await client.get("/api/v1/projects")).status_code == 401
            csrf = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
            login = await client.post(
                "/api/v1/auth/login",
                json={"username": "tls-admin", "password": administrator_password},
                headers={"x-csrf-token": csrf},
            )
            assert login.status_code == 200
            client.headers["x-csrf-token"] = login.json()["csrf_token"]
            assert (
                await client.post("/api/v1/projects", json={"name": "Synthetic TLS system"})
            ).status_code == 201
            assert len((await client.get("/api/v1/projects")).json()["items"]) == 1
            preferences = await client.patch(
                "/api/v1/me/preferences", json={"expected_revision": 1, "theme_mode": "light"}
            )
            assert preferences.status_code == 200 and preferences.json()["theme_mode"] == "light"
    cases = []
    for label, database in (
        (
            "wrong_ca",
            replace(
                config.database,
                tls={"mode": "verify_identity", "ca_file": "/qualification/wrong-ca.pem"},
            ),
        ),
        ("wrong_hostname", replace(config.database, host=WRONG_HOSTNAME)),
        ("expired", replace(config.database, host=EXPIRED_HOSTNAME)),
        (
            "plaintext_forbidden",
            replace(config.database, tls={"mode": "disabled", "ca_file": None}),
        ),
    ):
        engine = create_engine(database, dedicated=True)
        try:
            async with engine.connect():
                raise AssertionError(f"{label} unexpectedly authenticated")
        except AssertionError:
            raise
        except Exception as error:
            chain = exception_chain(error)
            if label != "plaintext_forbidden":
                assert any(isinstance(item, ssl.SSLCertVerificationError) for item in chain), [
                    type(item).__name__ for item in chain
                ]
            cases.append(
                {
                    "case": label,
                    "rejected": True,
                    "exception_types": [type(item).__name__ for item in chain],
                }
            )
        finally:
            await engine.dispose()
    return {
        "mariadb_version": version,
        "tls_cipher": cipher,
        "configured_external_hostname": config.database.host,
        "real_driver_and_schema_migration": True,
        "dml_only_runtime_grants": True,
        "real_application_ready": True,
        "unauthenticated_inventory_rejected": True,
        "authenticated_project_and_preference_persistence": True,
        "failure_cases": cases,
    }


def qualify() -> int:
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".cache/docker"))
    local.require_local_docker()
    identity = "s8tls-" + secrets.token_hex(5)
    private = ROOT / ".secrets/stage8-tls" / identity
    local.private_directory(private)
    fixture_configuration(private)
    lock = json.loads((ROOT / "deploy/local-mariadb/images.lock.json").read_text("utf-8"))
    image = lock["images"]["mariadb"]["reference"]
    runner = "system-inspector-runner:stage7"
    images = {
        name: local.run(
            ["docker", "image", "inspect", ref, "--format", "{{.Id}}"],
            label="Inspect cached TLS qualification image",
        ).strip()
        for name, ref in (("mariadb", image), ("runner", runner))
    }
    receipt: dict[str, object] = {
        "id": identity,
        "images": images,
        "no_published_ports": True,
        "network_internal": True,
        "no_pulls": True,
        "existing_installations_modified": False,
        "runtime": json.loads(
            local.run(
                ["docker", "version", "--format", "{{json .Server}}"], label="Inspect local runtime"
            )
        ),
    }
    containers = []
    network_created = False
    started = time.monotonic()
    phase = "create_isolated_network"
    try:
        local.run(
            [
                "docker",
                "network",
                "create",
                "--internal",
                "--label",
                "system-inspector.qualification=stage8-tls",
                identity,
            ],
            label="Create isolated TLS test network",
        )
        network_created = True
        for label in ("valid", "expired"):
            phase = "start_" + label + "_endpoint"
            name = identity + "-" + label
            local.run(
                server_arguments(
                    name, identity, private / label, image, expired=label == "expired"
                ),
                label="Start isolated TLS MariaDB fixture",
            )
            containers.append(name)
        phase = "wait_for_database_readiness"
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            states = [
                json.loads(
                    local.run(
                        ["docker", "inspect", name, "--format", "{{json .State}}"],
                        label="Check isolated TLS database readiness",
                    )
                )
                for name in containers
            ]
            if any(not row["Running"] for row in states):
                raise local.SetupError("Isolated TLS database stopped before readiness.")
            if all(row.get("Health", {}).get("Status") == "healthy" for row in states):
                break
            time.sleep(1)
        else:
            raise local.SetupError("Isolated TLS database readiness timed out.")
        phase = "run_production_client_tls_gate"
        argv = [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--network",
            identity,
            "--user=10001:10001",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--pids-limit=128",
            "--memory=768m",
            "--tmpfs=/tmp:mode=1777",
            "--workdir=/workspace/backend",
            "--env=PYTHONPATH=/workspace/backend/src",
            "--env=PYTHONDONTWRITEBYTECODE=1",
            "--mount",
            f"type=bind,src={(ROOT / 'backend').as_posix()},dst=/workspace/backend,readonly",
            "--mount",
            f"type=bind,src={(ROOT / 'scripts').as_posix()},dst=/workspace/scripts,readonly",
            "--mount",
            f"type=bind,src={(private / 'client').as_posix()},dst=/qualification,readonly",
            "--entrypoint=python",
            runner,
            "/workspace/scripts/stage8_external_tls.py",
            "--worker",
        ]
        completed = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=180, check=False)
        local.write_private(
            private / "client-output.log",
            (completed.stdout + completed.stderr).decode("utf-8", errors="replace"),
        )
        if completed.returncode:
            raise local.SetupError(
                "External TLS client failed; private fixture diagnostic retained."
            )
        raw = completed.stdout.decode("utf-8")
        receipt["assertions"] = json.loads(raw.split("STAGE8_TLS_RESULT=", 1)[1])
        phase = "shipped_external_backup_client_complex_password"
        metadata = local.run(
            [
                "docker",
                "run",
                "--rm",
                "--pull=never",
                "--network",
                identity,
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--pids-limit=64",
                "--memory=256m",
                "--tmpfs=/tmp:mode=1777",
                "--mount",
                f"type=bind,src={(ROOT / 'deploy/offline/db-client.sh').as_posix()},dst=/qualification/db-client.sh,readonly",
                "--mount",
                f"type=bind,src={(private / 'client/migration_password').as_posix()},dst=/run/secrets/inspector_db_migration_password,readonly",
                "--mount",
                f"type=bind,src={(private / 'client/ca.pem').as_posix()},dst=/run/tls/database-ca.crt,readonly",
                "--env=SI_DB_HOST=" + HOSTNAME,
                "--env=SI_DB_PORT=3306",
                "--env=SI_DB_NAME=" + DATABASE,
                "--env=SI_DB_USER=inspector_tls_migrator",
                "--env=SI_DB_TLS=verify_identity",
                "--entrypoint=sh",
                image,
                "/qualification/db-client.sh",
                "inspect",
            ],
            label="Shipped verified-TLS backup client authentication",
            timeout=30,
        )
        assert metadata.splitlines()[0] == "0016_optional_connection"
        assert "projects\t1" in metadata and "users\t1" in metadata
        receipt["assertions"]["utf8_whitespace_and_options_metacharacter_passwords"] = True
        receipt["assertions"]["shipped_external_database_backup_client_verified_tls"] = True
        receipt["passed"] = True
    except Exception as error:
        receipt.update(passed=False, failed_phase=phase, error_type=type(error).__name__)
    finally:
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
        for name in reversed(containers):
            local.run(
                ["docker", "rm", "--force", name], label="Remove own disposable TLS container"
            )
        if network_created:
            local.run(
                ["docker", "network", "rm", identity], label="Remove own disposable TLS network"
            )
    target = ROOT / "verification/stage-8/external-tls"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{identity}.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": receipt["passed"],
                "receipt": (target / f"{identity}.json").relative_to(ROOT).as_posix(),
            }
        )
    )
    return int(not receipt["passed"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            print("STAGE8_TLS_RESULT=" + json.dumps(asyncio.run(worker())))
            return 0
        except Exception as error:
            print(
                json.dumps(
                    {
                        "passed": False,
                        "error_type": type(error).__name__,
                        "chain": [
                            {
                                "type": type(item).__name__,
                                "errno": item.args[0]
                                if item.args and isinstance(item.args[0], int)
                                else None,
                                "verify_code": getattr(item, "verify_code", None),
                            }
                            for item in exception_chain(error)
                        ],
                        "frames": [
                            {
                                "file": Path(frame.filename).name,
                                "line": frame.lineno,
                                "function": frame.name,
                            }
                            for frame in traceback.extract_tb(error.__traceback__)
                        ],
                    }
                )
            )
            return 1
    return qualify()


if __name__ == "__main__":
    raise SystemExit(main())
