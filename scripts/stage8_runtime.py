"""Isolated Docker Desktop release qualification; never a native OS claim.

Only the generated inspector-s8-* projects are addressed. The shipped Compose
recipe is adapted to named state/cache volumes because Windows bind mounts do
not implement Linux ownership. Both application networks are internal; only
the synthetic HTTPS proxy is bound to loopback. No retained installation changes.
Terminal stop and abandoned attempts release their fixture containers/networks;
named data volumes, images and private recovery files remain retained.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import ssl
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from http.cookiejar import CookieJar
from pathlib import Path

import local_mariadb as local
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.x509.oid import NameOID

ROOT = local.ROOT
STATE = ROOT / ".state/stage8-runtime"
PRIVATE = ROOT / ".secrets/stage8-runtime"
EVIDENCE = ROOT / "verification/stage-8/runtime"
ORIGIN = "https://localhost:8460"
PROJECTS = ["stage8-fixture-a", "stage8-fixture-b"]


def run(
    argv: list[str], *, data: bytes | None = None, output: Path | None = None, timeout: int = 300
) -> bytes:
    result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        # Logs may contain fixture data; keep them private, never print payloads.
        (PRIVATE / "last-command-error.txt").write_bytes(result.stdout + result.stderr)
        raise RuntimeError(
            "Isolated runtime command failed; inspect protected last-command-error.txt."
        )
    if output:
        output.write_bytes(result.stdout)
    return result.stdout


def setup() -> dict:
    data = json.loads((STATE / "setup.json").read_text("utf-8"))
    if not data["stack"].startswith("inspector-s8-") or len(data["stack"]) != 23:
        raise ValueError("Unexpected fixture stack identity")
    return data


def compose(
    *args: str, data: bytes | None = None, output: Path | None = None, timeout: int = 300
) -> bytes:
    saved = setup()
    return run(
        [
            "docker",
            "compose",
            "--project-name",
            saved["stack"],
            "--project-directory",
            str(PRIVATE),
            "-f",
            str(PRIVATE / "compose.yaml"),
            *args,
        ],
        data=data,
        output=output,
        timeout=timeout,
    )


def stop_fixture() -> None:
    """Release this synthetic project's routes while retaining all volume data.

    Merely stopping containers leaves their bridge routes installed. Accumulated
    attempts can exhaust Docker's address pool and capture a real LAN/VPN subnet.
    Compose down is scoped by setup() to this generated project; deliberately do
    not add volume/image/orphan removal. Retained volumes can be cold-restarted.
    """
    compose("down", "--timeout", "60")


def certs() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Stage 08 synthetic localhost")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=7))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    local.write_private(
        PRIVATE / "tls/server.crt",
        cert.public_bytes(serialization.Encoding.PEM).decode(),
        mounted_secret=True,
    )
    local.write_private(
        PRIVATE / "tls/server.key",
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        mounted_secret=True,
    )


def prepare(release: Path) -> None:
    if (STATE / "setup.json").exists():
        raise ValueError("Existing isolated runtime preserved; use start or verification commands")
    local.private_directory(PRIVATE)
    for name in ("secrets", "tls"):
        local.private_directory(PRIVATE / name)
    STATE.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((release / "manifest.json").read_text("utf-8"))
    images = {row["role"]: row["image_id"] for row in manifest["images"]}
    for name in (
        "inspector_db_password",
        "inspector_db_migration_password",
        "inspector_db_root_password",
    ):
        local.write_private(PRIVATE / "secrets" / name, secrets.token_hex(32), mounted_secret=True)
    local.write_private(
        PRIVATE / "secrets/inspector_vault_key", "unused-host-reference", mounted_secret=True
    )
    (PRIVATE / "vault.key").write_bytes(secrets.token_bytes(32))
    accounts = {
        role: dict(username="stage8-" + role, password=secrets.token_urlsafe(32))
        for role in ("administrator", "inspector")
    }
    local.write_private(PRIVATE / "accounts.json", json.dumps(accounts), mounted_secret=True)
    certs()
    key = ed25519.Ed25519PrivateKey.generate()
    local.write_private(
        PRIVATE / "ssh-key.pem",
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption(),
        ).decode(),
        mounted_secret=True,
    )
    local.write_private(PRIVATE / "ssh-password", secrets.token_urlsafe(32), mounted_secret=True)
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
        .decode()
    )
    fingerprint = "SHA256:" + base64.b64encode(
        hashlib.sha256(base64.b64decode(public.split()[1])).digest()
    ).decode().rstrip("=")
    config = json.loads((ROOT / "deploy/offline/application.template.json").read_text("utf-8"))
    config["deployment"].update(
        public_origin=ORIGIN, vault_key_file="/var/lib/system-inspector/ssh-vault.key"
    )
    local.write_private(PRIVATE / "application.yaml", json.dumps(config), mounted_secret=True)
    stack = "inspector-s8-" + secrets.token_hex(5)
    document = yaml.safe_load((ROOT / "deploy/offline/compose.yaml").read_text("utf-8"))
    document["name"] = stack
    for role, service in document["services"].items():
        service["image"] = images["app" if role == "migrate" else role]
        service.pop("restart", None)
        if role == "app":
            service["volumes"] = [
                value.replace("./data/state:", "app-state:").replace("./data/cache:", "log-cache:")
                for value in service["volumes"]
            ]
        if role == "mariadb":
            service["volumes"] = [
                value
                for value in service["volumes"]
                if not value.startswith("./20-runtime-user.sh:")
            ]
            service["volumes"].append("init-config:/docker-entrypoint-initdb.d:ro")
        if role == "proxy":
            service["ports"] = ["127.0.0.1:8460:8443"]
            service["networks"] = ["service", "browser-edge"]
    document["volumes"].update({"app-state": {}, "log-cache": {}, "init-config": {}})
    document["networks"]["service"]["internal"] = True
    # Docker Desktop suppresses port publication for internal-only networks.
    # Only the proxy receives this ingress bridge, with outbound NAT disabled.
    document["networks"]["browser-edge"] = {
        "driver": "bridge",
        "driver_opts": {"com.docker.network.bridge.enable_ip_masquerade": "false"},
    }
    for name in ("20-runtime-user.sh", "mariadb.cnf", "db-client.sh"):
        local.write_private(
            PRIVATE / name, (ROOT / "deploy/offline" / name).read_text("utf-8"), mounted_secret=True
        )
    document["services"]["stage8-sftp"] = {
        "image": "system-inspector-runner:stage7",
        "pull_policy": "never",
        "user": "10001:10001",
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "pids_limit": 128,
        "mem_limit": "1g",
        "tmpfs": ["/tmp:mode=1777"],
        "networks": ["database"],
        "environment": {"PYTHONDONTWRITEBYTECODE": "1"},
        "command": [
            "python",
            "/workspace/scripts/stage6_sftp_fixture.py",
            "serve",
            "--key-file",
            "/run/secrets/fixture_ssh_key",
            "--password-file",
            "/run/secrets/fixture_ssh_password",
        ],
        "volumes": [
            str(ROOT / "scripts") + ":/workspace/scripts:ro",
            str(ROOT / "fixtures") + ":/workspace/fixtures:ro",
        ],
        "secrets": ["fixture_ssh_key", "fixture_ssh_password"],
    }
    document["secrets"].update(
        {
            "fixture_ssh_key": {"file": "./ssh-key.pem"},
            "fixture_ssh_password": {"file": "./ssh-password"},
            "browser_accounts": {"file": "./accounts.json"},
        }
    )
    local.write_private(PRIVATE / "compose.yaml", yaml.safe_dump(document, sort_keys=False))
    saved = dict(
        stack=stack, release=str(release.resolve()), images=images, fingerprint=fingerprint
    )
    (STATE / "setup.json").write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
    (STATE / "fixture.json").write_text(
        json.dumps(
            dict(
                synthetic=True,
                origin=ORIGIN,
                accounts_file=str(PRIVATE / "accounts.json"),
                project_ids=PROJECTS,
                **{"from": "2026-10-16T12:00:00Z", "to": "2026-10-16T12:00:02Z"},
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    compose("config", "--quiet")
    print("Prepared isolated release-image fixture; all service networks are internal.")


def helper(
    script: str,
    *,
    data: bytes | None = None,
    user: str = "0:0",
    volumes: list[str] | None = None,
) -> bytes:
    saved = setup()
    return run(
        [
            "docker",
            "run",
            "--rm",
            "--interactive",
            "--pull=never",
            "--network=none",
            "--user=" + user,
            "--read-only",
            "--cap-drop=ALL",
            *(
                ["--cap-add=CHOWN", "--cap-add=FOWNER", "--cap-add=DAC_OVERRIDE"]
                if user == "0:0"
                else []
            ),
            "--security-opt=no-new-privileges:true",
            "--volume",
            saved["stack"] + "_app-state:/data/state",
            "--volume",
            saved["stack"] + "_log-cache:/data/cache",
            *[argument for volume in (volumes or []) for argument in ("--volume", volume)],
            "--entrypoint=python",
            saved["images"]["app"],
            "-c",
            script,
        ],
        data=data,
    )


def start() -> None:
    saved = setup()
    # Windows bind mounts appear executable. The MariaDB entrypoint must SOURCE
    # this fixed provisioning helper, so copy it with real Linux 0444 mode.
    run(
        [
            "docker",
            "run",
            "--rm",
            "--interactive",
            "--pull=never",
            "--network=none",
            "--user=0:0",
            "--read-only",
            "--cap-drop=ALL",
            "--volume",
            saved["stack"] + "_init-config:/init",
            "--entrypoint=python",
            saved["images"]["app"],
            "-c",
            "import pathlib,sys;p=pathlib.Path('/init/20-runtime-user.sh');p.chmod(0o600) if p.exists() else None;p.write_bytes(sys.stdin.buffer.read());p.chmod(0o444)",
        ],
        data=(ROOT / "deploy/offline/20-runtime-user.sh").read_bytes(),
    )
    compose("up", "--detach", "--pull", "never", "--wait", "mariadb")
    compose("run", "--rm", "--no-deps", "migrate", timeout=300)
    # Linux ownership is verified on actual volumes, never emulated by Windows chmod.
    helper(
        "import os;[(os.chown('/data/'+n,10001,10001),os.chmod('/data/'+n,0o700)) for n in ('state','cache')]"
    )
    helper(
        "import os,pathlib,sys;p=pathlib.Path('/data/state/ssh-vault.key');data=sys.stdin.buffer.read();assert len(data)==32;fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.write(fd,data);os.close(fd)",
        data=(PRIVATE / "vault.key").read_bytes(),
        user="10001:10001",
    )
    compose(
        "run",
        "--rm",
        "--no-deps",
        "--env",
        "SI_STAGE8_DISPOSABLE=1",
        "--volume",
        str(ROOT / "scripts") + ":/workspace/scripts:ro",
        "--volume",
        str(ROOT / "examples") + ":/workspace/examples:ro",
        "--volume",
        str(PRIVATE / "accounts.json") + ":/run/secrets/browser_accounts:ro",
        "app",
        "python",
        "/workspace/scripts/stage8_seed.py",
        "seed",
    )
    compose("up", "--detach", "--no-deps", "stage8-sftp", "app")
    wait_ready()
    compose("up", "--detach", "--no-deps", "proxy")
    time.sleep(2)
    print("Release application, proxy and managed MariaDB ready on loopback 8460.")


def fresh_attempt() -> None:
    saved = setup()
    stop_fixture()
    history = STATE / (saved["stack"] + ".json")
    history.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
    saved["stack"] = "inspector-s8-" + secrets.token_hex(5)
    (STATE / "setup.json").write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
    document = yaml.safe_load((PRIVATE / "compose.yaml").read_text("utf-8"))
    service = document["services"]["mariadb"]
    service["volumes"] = [
        value
        for value in service["volumes"]
        if not value.startswith("./20-runtime-user.sh:") and not value.startswith("init-config:")
    ]
    service["volumes"].append("init-config:/docker-entrypoint-initdb.d:ro")
    document["volumes"]["init-config"] = {}
    (PRIVATE / "compose.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    print("Failed synthetic volume retained; selected a new isolated attempt.")


def wait_ready() -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        container = compose("ps", "--quiet", "app").decode().strip()
        if container:
            value = (
                run(["docker", "inspect", "--format", "{{.State.Health.Status}}", container])
                .decode()
                .strip()
            )
            if value == "healthy":
                return
            if value == "unhealthy":
                break
        time.sleep(2)
    raise RuntimeError("Release application readiness did not pass")


def configure() -> None:
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(
            context=ssl.create_default_context(cafile=str(PRIVATE / "tls/server.crt"))
        ),
        urllib.request.HTTPCookieProcessor(CookieJar()),
    )
    csrf = ""

    def request(path: str, data: dict | None = None, method: str | None = None) -> dict:
        headers = {"Origin": ORIGIN, "Content-Type": "application/json", "X-CSRF-Token": csrf}
        with opener.open(
            urllib.request.Request(
                ORIGIN + "/api/v1" + path,
                data=None if data is None else json.dumps(data).encode(),
                headers=headers,
                method=method,
            ),
            timeout=30,
        ) as response:
            return json.loads(response.read())

    csrf = request("/auth/csrf")["csrf_token"]
    csrf = request(
        "/auth/login", json.loads((PRIVATE / "accounts.json").read_text("utf-8"))["administrator"]
    )["csrf_token"]
    for project in PROJECTS:
        current = request(f"/projects/{project}/topology")
        revision = current["revision"]
        base = f"/projects/{project}/connections/c-live"
        request(
            base + "/password",
            {
                "expected_config_revision": revision,
                "expected_credential_revision": 0,
                "password": (PRIVATE / "ssh-password").read_text("ascii").strip(),
            },
            "PUT",
        )
        inspection = request(base + "/host-key/inspect", {"expected_config_revision": revision})
        if inspection["fingerprint"] != setup()["fingerprint"]:
            raise ValueError("Synthetic host fingerprint differs")
        request(
            base + "/host-key/approve",
            {
                "expected_config_revision": revision,
                "expected_trust_revision": 0,
                "inspection_token": inspection["inspection_token"],
                "verified": True,
            },
        )
        request(
            base + "/source-access/approve",
            {
                "expected_config_revision": revision,
                "expected_approval_revision": 0,
                "verified": True,
            },
        )
    request("/auth/logout", {})
    print("Only the generated local SFTP target was approved in both systems.")


def inspect_data(command: str, *, expected: Path | None = None) -> dict:
    """Execute real DB/cache assertions in the built release, without serving."""
    arguments = [
        "run",
        "--rm",
        "--no-deps",
        "--env",
        "SI_STAGE8_DISPOSABLE=1",
        "--volume",
        str(ROOT / "scripts") + ":/workspace/scripts:ro",
    ]
    if expected is not None:
        arguments += ["--volume", str(expected) + ":/run/recovery/expected.json:ro"]
    arguments += ["app", "python", "/workspace/scripts/stage8_seed.py", command, "--require-data"]
    if expected is not None:
        arguments += ["--expected", "/run/recovery/expected.json"]
    return json.loads(compose(*arguments, timeout=300))


def backup_runtime() -> None:
    """Quiesce the isolated source stack and use the shipped recovery algorithms."""
    recovery = PRIVATE / "recovery"
    if recovery.exists():
        raise ValueError("Existing verified recovery preserved; no overwrite permitted")
    local.private_directory(recovery)
    expected = inspect_data("snapshot")
    local.write_private(recovery / "expected.json", json.dumps(expected, indent=2) + "\n")
    compose("stop", "--timeout", "60", "proxy", "app", "stage8-sftp")
    for role in ("proxy", "app", "stage8-sftp"):
        container = compose("ps", "--all", "--quiet", role).decode().strip()
        if container:
            assert (
                run(["docker", "inspect", "--format", "{{.State.Running}}", container]).strip()
                == b"false"
            )
    # The SQL client uses its migration password only through a temporary
    # protected defaults file. Dump + source files share a quiescent point.
    compose(
        "exec",
        "-T",
        "mariadb",
        "sh",
        "/opt/inspector/db-client.sh",
        "dump",
        output=recovery / "database.sql",
    )
    compose(
        "exec",
        "-T",
        "mariadb",
        "sh",
        "/opt/inspector/db-client.sh",
        "inspect",
        output=recovery / "database-metadata.txt",
    )
    local.write_private(recovery / "policy.json", (PRIVATE / "application.yaml").read_text("utf-8"))
    records = json.loads(
        helper(
            "import json,sys;from pathlib import Path;sys.path.insert(0,'/ops');import fileops;print(json.dumps(fileops.snapshot(Path('/data'),Path('/recovery'))))",
            volumes=[str(ROOT / "deploy/offline") + ":/ops:ro", str(recovery) + ":/recovery"],
        )
    )
    assert not any(row["path"] == "files/state/ssh-vault.key" for row in records)
    for name in ("database.sql", "database-metadata.txt", "policy.json"):
        content = (recovery / name).read_bytes()
        records.append(
            dict(path=name, bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
        )
    images = {
        row["role"]: row
        for row in json.loads((Path(setup()["release"]) / "manifest.json").read_text("utf-8"))[
            "images"
        ]
    }
    manifest = dict(
        format="system-inspector-backup-1",
        images=images,
        vault_key_included=False,
        created_utc=datetime.now(UTC).isoformat(),
        files=records,
    )
    local.write_private(recovery / "backup.json", json.dumps(manifest, indent=2) + "\n")
    # Expected assertions are kept outside the strict data backup manifest.
    local.write_private(
        PRIVATE / "expected-recovery.json", (recovery / "expected.json").read_text("utf-8")
    )
    (recovery / "expected.json").unlink()
    helper(
        "import sys;from pathlib import Path;sys.path.insert(0,'/ops');import fileops;fileops.verify(Path('/recovery'));print('verified')",
        volumes=[str(ROOT / "deploy/offline") + ":/ops:ro", str(recovery) + ":/recovery:ro"],
    )
    local.write_private(PRIVATE / "backup-source-setup.json", json.dumps(setup(), indent=2) + "\n")
    print(
        "All-system SQL/cache backup verified; source app, proxy and synthetic SFTP remain stopped."
    )


def restore_runtime() -> None:
    """Restore to fresh named volumes and revoke logins before exposing a copy."""
    recovery = PRIVATE / "recovery"
    original = json.loads((PRIVATE / "backup-source-setup.json").read_text("utf-8"))
    current = setup()
    if current["stack"] != original["stack"]:
        raise ValueError("Fresh restore already attempted; preserved target must be reviewed")
    stop_fixture()
    saved = dict(original, stack="inspector-s8-" + secrets.token_hex(5))
    (STATE / "setup.json").write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
    # Copy the non-executable sourced helper into a real Linux filesystem.
    run(
        [
            "docker",
            "run",
            "--rm",
            "--interactive",
            "--pull=never",
            "--network=none",
            "--user=0:0",
            "--read-only",
            "--cap-drop=ALL",
            "--volume",
            saved["stack"] + "_init-config:/init",
            "--entrypoint=python",
            saved["images"]["app"],
            "-c",
            "import pathlib,sys;p=pathlib.Path('/init/20-runtime-user.sh');p.write_bytes(sys.stdin.buffer.read());p.chmod(0o444)",
        ],
        data=(ROOT / "deploy/offline/20-runtime-user.sh").read_bytes(),
    )
    helper(
        "import sys;from pathlib import Path;sys.path.insert(0,'/ops');import fileops;fileops.restore(Path('/recovery'),Path('/data'));fileops.bind_key(Path('/data'),Path('/run/recovery/vault.key'))",
        volumes=[
            str(ROOT / "deploy/offline") + ":/ops:ro",
            str(recovery) + ":/recovery:ro",
            str(PRIVATE / "vault.key") + ":/run/recovery/vault.key:ro",
        ],
    )
    compose("up", "--detach", "--pull", "never", "--wait", "mariadb")
    compose(
        "exec",
        "-T",
        "mariadb",
        "sh",
        "/opt/inspector/db-client.sh",
        "restore",
        data=(recovery / "database.sql").read_bytes(),
    )
    restored_metadata = compose(
        "exec", "-T", "mariadb", "sh", "/opt/inspector/db-client.sh", "inspect"
    )
    assert restored_metadata == (recovery / "database-metadata.txt").read_bytes()
    finish_restore()


def finish_restore() -> None:
    """Resume only revocation/verification of an already populated test copy."""
    original = json.loads((PRIVATE / "backup-source-setup.json").read_text("utf-8"))
    saved = setup()
    if saved["stack"] == original["stack"] or compose("ps", "--quiet", "app").strip():
        raise ValueError("Recovery verification requires the stopped isolated restored copy")
    (PRIVATE / "db-client.sh").chmod(0o600)
    (PRIVATE / "db-client.sh").write_text(
        (ROOT / "deploy/offline/db-client.sh").read_text("utf-8"), encoding="utf-8", newline="\n"
    )
    (PRIVATE / "db-client.sh").chmod(0o444)
    compose("exec", "-T", "mariadb", "sh", "/opt/inspector/db-client.sh", "revoke")
    assertions = inspect_data("verify-restored", expected=PRIVATE / "expected-recovery.json")
    compose("up", "--detach", "--no-deps", "app")
    wait_ready()
    compose("up", "--detach", "--no-deps", "proxy")
    assert not compose("ps", "--quiet", "stage8-sftp").strip()
    fixture = json.loads((STATE / "fixture.json").read_text("utf-8"))
    fixture["phase"] = "restored"
    (STATE / "fixture.json").write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    receipt = dict(
        platform="Docker Desktop Linux containers on Windows; not a native Ubuntu/Rocky claim",
        coordinated_quiescent_backup=True,
        all_system_cache_members_verified=True,
        vault_key_excluded_from_backup=True,
        separate_raw_vault_key_rebound=True,
        database_accounts_reprovisioned_in_fresh_volume=True,
        source_stack=original["stack"],
        restored_stack=saved["stack"],
        images=saved["images"],
        no_target_container_running=True,
        restored_assertions=assertions,
        completed_utc=datetime.now(UTC).isoformat(),
    )
    (EVIDENCE / "recovery.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        "Fresh-volume recovery verified under both-system DB/cache assertions. Source SFTP remains stopped; browser fixture phase restored."
    )


def cold_restart() -> None:
    """Cold-load all three archives and restart retained volumes without targets."""
    saved = setup()
    # The restored browser gate legitimately changes preference revisions;
    # preserve the state at this restart's own maintenance boundary.
    expected = inspect_data("snapshot")
    compose("stop", "--timeout", "60")
    compose("rm", "--force")
    release = Path(saved["release"])
    manifest = json.loads((release / "manifest.json").read_text("utf-8"))
    for image in manifest["images"]:
        archive = release / image["archive"]
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == image["sha256"]
        run(["docker", "image", "load", "--input", str(archive)], timeout=300)
        assert (
            run(["docker", "image", "inspect", "--format", "{{.Id}}", image["reference"]])
            .decode()
            .strip()
            == image["image_id"]
        )
    compose("up", "--detach", "--pull", "never", "--wait", "mariadb")
    compose("run", "--rm", "--no-deps", "migrate")
    compose("up", "--detach", "--no-deps", "app")
    wait_ready()
    compose("up", "--detach", "--no-deps", "proxy")
    assert not compose("ps", "--quiet", "stage8-sftp").strip()
    assert inspect_data("snapshot") == expected
    (EVIDENCE / "cold-start.json").write_text(
        json.dumps(
            dict(
                all_three_archives_loaded=True,
                container_cold_start=True,
                clean_image_store_tested=False,
                exact_image_ids_verified=True,
                retained_database_and_cache_verified=True,
                app_and_database_networks_internal=True,
                proxy_ingress_bridge_masquerading=False,
                runtime_pulls_disabled=True,
                no_automatic_sftp_container=True,
                platform="Docker Desktop Linux containers on Windows; not a native Ubuntu/Rocky claim",
                completed_utc=datetime.now(UTC).isoformat(),
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (PRIVATE / "db-client.sh").chmod(0o444)
    print(
        "Three-image cold load and retained-volume offline restart verified; target SFTP remains stopped."
    )


def verify_release_archives(release: Path) -> None:
    """Load final export bytes and bind them to the previously exercised image IDs."""
    from release_offline import verify

    verify(release)
    manifest = json.loads((release / "manifest.json").read_text("utf-8"))
    tested = setup()["images"]
    records = []
    for row in manifest["images"]:
        if row["image_id"] != tested[row["role"]]:
            raise ValueError("Final archive image differs from the tested runtime")
        run(["docker", "image", "load", "--input", str(release / row["archive"])])
        loaded = (
            run(["docker", "image", "inspect", "--format", "{{.Id}}", row["reference"]])
            .decode()
            .strip()
        )
        assert loaded == row["image_id"]
        records.append(dict(role=row["role"], archive_sha256=row["sha256"], image_id=loaded))
    (EVIDENCE / "final-archive-load.json").write_text(
        json.dumps(
            dict(
                release=str(release),
                final_export_bytes_loaded=True,
                tested_image_ids_preserved=True,
                image_store_was_not_empty=True,
                images=records,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "Final three exports load to the exact tested image IDs; tar metadata need not be identical between exports."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "prepare",
            "start",
            "configure",
            "stop",
            "fresh-attempt",
            "backup",
            "restore",
            "recover",
            "resume-restore",
            "cold-restart",
            "verify-release-archives",
        ],
    )
    parser.add_argument(
        "--release", type=Path, default=ROOT / "dist/system-inspector-0.1.0-offline-rc2"
    )
    args = parser.parse_args()
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".cache/docker"))
    local.require_local_docker()
    try:
        if args.command == "prepare":
            prepare(args.release)
        elif args.command == "start":
            start()
        elif args.command == "configure":
            configure()
        elif args.command == "fresh-attempt":
            fresh_attempt()
        elif args.command == "backup":
            backup_runtime()
        elif args.command == "restore":
            restore_runtime()
        elif args.command == "recover":
            backup_runtime()
            restore_runtime()
        elif args.command == "resume-restore":
            finish_restore()
        elif args.command == "cold-restart":
            cold_restart()
        elif args.command == "verify-release-archives":
            verify_release_archives(args.release)
        else:
            stop_fixture()
            print(
                "Fixture containers and networks removed; named volumes and recovery files retained."
            )
        return 0
    except Exception as error:
        print(
            f"Stage 08 isolated fixture failed ({type(error).__name__}); protected data retained for diagnosis.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
