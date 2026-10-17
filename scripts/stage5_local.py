"""Isolated Stage 05 HTTPS/MariaDB/read-only-SFTP browser fixture on port 8447.

Existing 8444/8445 installations and all their secrets, schemas and caches are
preserved. Images must already exist locally. Generated fixture writes occur
only inside the new synthetic SFTP container, never through application SSH.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import secrets
import ssl
import urllib.request
from copy import deepcopy
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
STATE = ROOT / ".state/stage5-browser"
PRIVATE = ROOT / ".secrets/stage5-browser"
SETUP = STATE / "setup.json"
ORIGIN = "https://localhost:8447"
SERVICE = "stage5-browser"
SSH_SERVICE = "stage5-sftp"
RUNNER = "system-inspector-runner:stage5"
PROJECTS = ("stage5-fixture-a", "stage5-fixture-b")


def prepare() -> None:
    if SETUP.exists():
        checked_setup()
        print("Existing Stage 05 fixture preserved; no schema or secret changed.")
        return
    local.require_local_docker()
    local.private_directory(PRIVATE, windows_owner=os.environ.get("SI_WINDOWS_SECRET_OWNER"))
    STATE.mkdir(parents=True, exist_ok=True)
    suffix = "s5_web_" + secrets.token_hex(5)
    local.new_test(suffix, execute=False)
    database = "inspector_test_" + suffix
    integration = yaml.safe_load(
        (local.DEPLOY / f"{database}.compose.local.yaml").read_text("utf-8")
    )
    document = yaml.safe_load((local.DEPLOY / f"{database}.local.yaml").read_text("utf-8"))
    document["deployment"].update(
        public_origin=ORIGIN,
        state_dir="/var/lib/system-inspector",
        vault_key_file="/var/lib/system-inspector/ssh-vault.key",
    )
    application = STATE / "application.yaml"
    local.write_private(application, yaml.safe_dump(document, sort_keys=False))
    accounts = {
        role: {"username": "stage5-" + role, "password": secrets.token_urlsafe(32)}
        for role in ("administrator", "inspector")
    }
    local.write_private(PRIVATE / "accounts.json", json.dumps(accounts), mounted_secret=True)
    local.write_private(PRIVATE / "ssh-password", secrets.token_urlsafe(32), mounted_secret=True)
    # Raw vault bytes use an owner-only file, preserving stage4's wrapper format.
    descriptor = os.open(PRIVATE / "vault.key", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(secrets.token_bytes(32))
    ssh_key = ed25519.Ed25519PrivateKey.generate()
    local.write_private(
        PRIVATE / "ssh-key.pem",
        ssh_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption(),
        ).decode(),
        mounted_secret=True,
    )
    public_key = (
        ssh_key.public_key()
        .public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
        .decode()
    )
    fingerprint = "SHA256:" + base64.b64encode(
        hashlib.sha256(base64.b64decode(public_key.split()[1])).digest()
    ).decode().rstrip("=")
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic Stage 05 localhost")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=7))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    local.write_private(
        PRIVATE / "tls-key.pem",
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        mounted_secret=True,
    )
    local.write_private(
        PRIVATE / "tls-cert.pem",
        certificate.public_bytes(serialization.Encoding.PEM).decode(),
        mounted_secret=True,
    )
    base = yaml.safe_load((local.DEPLOY / "compose.yaml").read_text("utf-8"))
    runtime = deepcopy(base["services"]["runtime"])
    runtime.update(
        image=RUNNER,
        networks=["database", "stage5-browser-network"],
        ports=["127.0.0.1:8447:8443"],
        command=[
            "python",
            "/workspace/scripts/stage4_local.py",
            "serve",
            "--",
            "python",
            "-m",
            "uvicorn",
            "inspector.app:create_app",
            "--factory",
            "--host",
            "0.0.0.0",
            "--port",
            "8443",
            "--workers",
            "1",
            "--no-access-log",
            "--no-proxy-headers",
            "--ssl-keyfile",
            "/run/secrets/stage5_tls_key",
            "--ssl-certfile",
            "/run/secrets/stage5_tls_cert",
            "--ws",
            "websockets",
            "--ws-max-size",
            "16384",
            "--ws-max-queue",
            "16",
        ],
        volumes=[
            f"{(ROOT / 'backend').as_posix()}:/workspace/backend:ro",
            f"{application.as_posix()}:/etc/system-inspector/application.yaml:ro",
            f"{(ROOT / 'scripts').as_posix()}:/workspace/scripts:ro",
            f"{(ROOT / 'examples').as_posix()}:/workspace/examples:ro",
        ],
        secrets=[
            "test_db_password",
            "browser_accounts",
            "stage5_tls_key",
            "stage5_tls_cert",
            "ssh_vault_master",
        ],
    )
    sftp = deepcopy(base["services"]["runtime"])
    sftp.update(
        image=RUNNER,
        networks=["database"],
        environment={"PYTHONDONTWRITEBYTECODE": "1"},
        command=[
            "python",
            "/workspace/scripts/stage5_sftp_fixture.py",
            "serve",
            "--key-file",
            "/run/secrets/stage5_ssh_key",
            "--password-file",
            "/run/secrets/stage5_ssh_password",
        ],
        volumes=[f"{(ROOT / 'scripts').as_posix()}:/workspace/scripts:ro"],
        secrets=["stage5_ssh_key", "stage5_ssh_password"],
    )
    sftp.pop("depends_on", None)
    overlay = {
        "services": {
            "integration": integration["services"]["integration"],
            SERVICE: runtime,
            SSH_SERVICE: sftp,
        },
        "networks": {"stage5-browser-network": {}},
        "secrets": {
            **integration["secrets"],
            **{
                name: {"file": (PRIVATE / filename).as_posix()}
                for name, filename in {
                    "browser_accounts": "accounts.json",
                    "stage5_tls_key": "tls-key.pem",
                    "stage5_tls_cert": "tls-cert.pem",
                    "ssh_vault_master": "vault.key",
                    "stage5_ssh_key": "ssh-key.pem",
                    "stage5_ssh_password": "ssh-password",
                }.items()
            },
        },
    }
    overlay["services"]["integration"]["image"] = RUNNER
    override = local.DEPLOY / "stage5-browser.compose.local.yaml"
    local.write_private(override, yaml.safe_dump(overlay, sort_keys=False))
    (STATE / "public-fixture.json").write_text(
        json.dumps(
            {
                "synthetic": True,
                "host": SSH_SERVICE,
                "port": 8022,
                "username": "synthetic-log-reader",
                "public_key": public_key,
                "fingerprint": fingerprint,
                "projects": PROJECTS,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    SETUP.write_text(
        json.dumps({"database": database, "override": override.as_posix()}, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Prepared fresh isolated Stage 05 schema, HTTPS 8447 and synthetic read-only SFTP.")


def checked_setup() -> Path:
    setup = json.loads(SETUP.read_text("utf-8"))
    import re

    if not re.fullmatch(r"inspector_test_s5_web_[a-f0-9]{10}", setup["database"]):
        raise local.SetupError("Unexpected Stage 05 database identity; nothing changed.")
    override = Path(setup["override"]).resolve()
    if override != (local.DEPLOY / "stage5-browser.compose.local.yaml").resolve():
        raise local.SetupError("Unexpected Stage 05 Compose path; nothing changed.")
    config = yaml.safe_load((STATE / "application.yaml").read_text("utf-8"))
    if (
        config["database"]["name"] != setup["database"]
        or config["database"]["host"] != "mariadb"
        or config["database"]["port"] != 3306
        or config["deployment"]["public_origin"] != ORIGIN
    ):
        raise local.SetupError("Unexpected Stage 05 application scope; nothing changed.")
    services = yaml.safe_load(override.read_text("utf-8"))["services"]
    if set(services) != {"integration", SERVICE, SSH_SERVICE} or services[SERVICE]["ports"] != [
        "127.0.0.1:8447:8443"
    ]:
        raise local.SetupError("Unexpected Stage 05 service boundaries; nothing changed.")
    return override


def runner() -> None:
    """Refresh only the generated Stage 05 overlay to its isolated runner tag."""
    override = checked_setup()
    if override.is_symlink() or not override.is_file():
        raise local.SetupError("Unexpected Stage 05 overlay file boundary.")
    document = yaml.safe_load(override.read_text("utf-8"))
    for name in (SERVICE, SSH_SERVICE, "integration"):
        document["services"][name]["image"] = RUNNER
    command = document["services"][SERVICE]["command"]
    if "--ws" not in command:
        command.extend(["--ws", "websockets", "--ws-max-size", "16384", "--ws-max-queue", "16"])
    else:
        command[command.index("--ws") + 1] = "websockets"
    override.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    print("Updated only the generated Stage 05 runner overlay and bounded WebSocket settings.")


def resources(label: str) -> None:
    """Read-only instantaneous measurements, with an explicit fixture label."""
    import re

    local.require_local_docker()
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", label):
        raise local.SetupError("Invalid synthetic measurement label.")
    containers = ["system-inspector-local-stage5-browser-1", "system-inspector-local-mariadb-1"]

    def workload() -> dict:
        return json.loads(
            local.compose(
                "exec",
                "-T",
                SERVICE,
                "python",
                "/workspace/scripts/stage5_local.py",
                "capacity-state",
                override=checked_setup(),
                timeout=20,
            )
        )

    before = workload() if label.startswith("capacity") else None
    measured = local.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", *containers],
        label="Read synthetic application and local MariaDB resource usage",
    )
    linux_memory = local.run(
        ["docker", "info", "--format", "{{.MemTotal}}"],
        label="Read local Docker Linux memory allocation",
    )
    limits = local.run(
        ["docker", "inspect", *containers, "--format", "{{json .HostConfig.Memory}}"],
        label="Read test container memory ceilings",
    )
    after = workload() if before is not None else None
    windows_memory = None
    if os.name == "nt":
        windows_memory = int(
            local.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
                ],
                label="Read local physical memory total",
            ).strip()
        )
    evidence = ROOT / "verification/stage-5" / f"resources-{label}.json"
    existing = json.loads(evidence.read_text("utf-8")) if evidence.exists() else []
    existing.append(
        {
            "measured_at": datetime.now(UTC).isoformat(),
            "label": label,
            "windows_physical_memory_bytes": windows_memory,
            "docker_linux_memory_bytes": int(linux_memory.strip()),
            "container_memory_ceilings_bytes": dict(
                zip(containers, map(int, limits.splitlines()), strict=True)
            ),
            "containers": [json.loads(value) for value in measured.splitlines()],
            "workload_before": before,
            "workload_after": after,
            "proxy": "Direct local Uvicorn TLS; release proxy verification belongs to Stage 08.",
        }
    )
    evidence.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    print("Recorded read-only synthetic application/database resource usage.")


async def capacity_state() -> dict[str, object]:
    """Container-only DML-identity read; output contains synthetic IDs/counts only."""
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from inspector.config import load_config
    from inspector.database import create_engine
    from inspector.history import NONTERMINAL
    from inspector.persistence.models import HistoryJob, LiveSession, LiveSubscription

    config = load_config()
    if (
        not config.database.name.startswith("inspector_test_s5_web_")
        or config.database.host != "mariadb"
    ):
        raise local.SetupError(
            "Refusing workload measurement outside the isolated Stage 05 schema."
        )
    engine = create_engine(config.database)
    try:
        async with async_sessionmaker(engine)() as session:
            jobs = (
                (
                    await session.execute(
                        select(
                            HistoryJob.project_id,
                            HistoryJob.id,
                            HistoryJob.status,
                            HistoryJob.downloaded_bytes,
                            HistoryJob.expanded_bytes,
                            HistoryJob.event_count,
                        )
                        .where(
                            HistoryJob.project_id.in_(PROJECTS), HistoryJob.status.in_(NONTERMINAL)
                        )
                        .order_by(HistoryJob.project_id, HistoryJob.created_us.desc())
                    )
                )
                .mappings()
                .all()
            )
            counts = (
                await session.execute(
                    select(LiveSubscription.project_id, func.count())
                    .where(LiveSubscription.project_id.in_(PROJECTS))
                    .group_by(LiveSubscription.project_id)
                )
            ).all()
            recent_live = (
                (
                    await session.execute(
                        select(
                            LiveSession.project_id,
                            LiveSession.id,
                            LiveSession.status,
                            LiveSession.error_code,
                            LiveSession.created_us,
                        )
                        .where(LiveSession.project_id.in_(PROJECTS))
                        .order_by(LiveSession.created_us.desc())
                        .limit(4)
                    )
                )
                .mappings()
                .all()
            )
            recent_jobs = (
                (
                    await session.execute(
                        select(
                            HistoryJob.project_id,
                            HistoryJob.id,
                            HistoryJob.status,
                            HistoryJob.event_count,
                            HistoryJob.downloaded_bytes,
                            HistoryJob.expanded_bytes,
                            HistoryJob.errors,
                            HistoryJob.created_us,
                        )
                        .where(HistoryJob.project_id.in_(PROJECTS))
                        .order_by(HistoryJob.created_us.desc())
                        .limit(4)
                    )
                )
                .mappings()
                .all()
            )
            return {
                "measured_at": datetime.now(UTC).isoformat(),
                "active_jobs": [dict(job) for job in jobs],
                "live_subscriptions": {project: count for project, count in counts},
                "recent_live_sessions": [dict(row) for row in recent_live],
                "recent_jobs": [dict(row) for row in recent_jobs],
            }
    finally:
        await engine.dispose()


async def seed() -> None:
    """Runs with the isolated schema's runtime DML account, never migration/root."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from inspector import auth, foundation, services
    from inspector.config import load_config
    from inspector.database import create_engine
    from inspector.domain import Principal
    from inspector.persistence.models import Project, User

    config = load_config()
    if not config.database.name.startswith("inspector_test_s5_web_"):
        raise local.SetupError("Refusing Stage 05 seeding outside its isolated schema.")
    accounts = json.loads(
        await asyncio.to_thread(Path("/run/secrets/browser_accounts").read_text, "utf-8")
    )
    engine = create_engine(config.database)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
            admin = await session.scalar(
                select(User).where(User.username_key == accounts["administrator"]["username"])
            )
            if admin is None:
                admin = await auth.bootstrap_admin(
                    session,
                    accounts["administrator"]["username"],
                    "Synthetic Stage 05 Administrator",
                    accounts["administrator"]["password"],
                )
            principal = Principal(admin.id, admin.role, admin.auth_version)
            if not await session.scalar(
                select(User.id).where(User.username_key == accounts["inspector"]["username"])
            ):
                await auth.create_user(
                    session,
                    principal,
                    accounts["inspector"]["username"],
                    "Synthetic Stage 05 Inspector",
                    accounts["inspector"]["password"],
                )
            await foundation.initialize_settings(session, config)
            for project in PROJECTS:
                if await session.get(Project, project) is None:
                    await services.create_project(
                        session,
                        principal,
                        "[Synthetic live] " + project[-1].upper(),
                        "Isolated live SFTP fixture only.",
                        project_id=project,
                    )
        print("Seeded only new Stage 05 synthetic accounts and systems; no credentials printed.")
    finally:
        await engine.dispose()


def configure(*, archive_only: bool = False) -> None:
    """Approve only our generated SFTP endpoint through the real secured API."""
    checked_setup()
    jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(
            context=ssl.create_default_context(cafile=str(PRIVATE / "tls-cert.pem"))
        ),
        urllib.request.HTTPCookieProcessor(jar),
    )
    csrf = ""

    def request(path: str, data: dict | None = None, method: str | None = None) -> dict:
        payload = None if data is None else json.dumps(data).encode()
        headers = {"Origin": ORIGIN, "Content-Type": "application/json", "x-csrf-token": csrf}
        with opener.open(
            urllib.request.Request(
                ORIGIN + "/api/v1" + path, data=payload, headers=headers, method=method
            ),
            timeout=30,
        ) as result:
            return json.loads(result.read())

    csrf = request("/auth/csrf")["csrf_token"]
    account = json.loads((PRIVATE / "accounts.json").read_text("utf-8"))["administrator"]
    csrf = request("/auth/login", account)["csrf_token"]
    metadata = json.loads((STATE / "public-fixture.json").read_text("utf-8"))
    for project in PROJECTS:
        topology = request(f"/projects/{project}/topology")
        if topology["revision"] != 1:
            if archive_only:
                document = topology["config"]
                if (
                    len(document["connections"]) != 1
                    or document["connections"][0]["host"] != SSH_SERVICE
                ):
                    raise local.SetupError(
                        "Archive fixture configuration is not the generated endpoint."
                    )
                archive_spec = [
                    {
                        "path_pattern": "/var/log/inspector-demo/source0.zip",
                        "member_patterns": ["logs/*.log"],
                    }
                ]
                if document["processes"][0]["log_source"]["archives"] != archive_spec:
                    document["processes"][0]["log_source"]["archives"] = archive_spec
                    changed = request(
                        f"/projects/{project}/topology",
                        {"expected_revision": topology["revision"], "config": document},
                        "PUT",
                    )
                    revision = changed["revision"]
                else:
                    revision = topology["revision"]
                base = f"/projects/{project}/connections/c-live/source-access"
                approval = request(base)
                if not approval["approval"]["approved"]:
                    request(
                        base + "/approve",
                        {
                            "expected_config_revision": revision,
                            "expected_approval_revision": approval["approval"]["revision"],
                            "verified": True,
                        },
                    )
                print(f"Configured generated synthetic archive for {project}.")
                continue
            print(f"Existing configured synthetic system {project} preserved.")
            continue
        document = json.loads((ROOT / "examples/project.example.json").read_text("utf-8"))
        document["project"].update(
            id=project, name="[Synthetic live] " + project[-1].upper(), revision=1
        )
        document["connections"] = [
            {
                "id": "c-live",
                "name": "Synthetic Stage 05 SFTP",
                "host": SSH_SERVICE,
                "port": 8022,
                "username": metadata["username"],
                "credential_ref": "synthetic-stage5",
                "jump_connection_id": None,
                "allowed_log_roots": ["/var/log/inspector-demo"],
            }
        ]
        for server in document["servers"]:
            server["connection_id"] = "c-live"
        for index, process in enumerate(document["processes"]):
            process["log_source"].update(
                active_path=f"/var/log/inspector-demo/live-{index}.log",
                rotated_patterns=[],
                archives=[],
                parser_id="parser-iso-utc",
            )
            if index == 0:
                process["log_source"]["archives"] = [
                    {
                        "path_pattern": "/var/log/inspector-demo/source0.zip",
                        "member_patterns": ["logs/*.log"],
                    }
                ]
        request(
            f"/projects/{project}/topology", {"expected_revision": 1, "config": document}, "PUT"
        )
        base = f"/projects/{project}/connections/c-live"
        request(
            base + "/password",
            {
                "expected_config_revision": 2,
                "expected_credential_revision": 0,
                "password": (PRIVATE / "ssh-password").read_text("ascii").strip(),
            },
            "PUT",
        )
        inspection = request(base + "/host-key/inspect", {"expected_config_revision": 2})
        if inspection["fingerprint"] != metadata["fingerprint"]:
            raise local.SetupError(
                "Generated Stage 05 host fingerprint did not match; approval refused."
            )
        request(
            base + "/host-key/approve",
            {
                "expected_config_revision": 2,
                "expected_trust_revision": 0,
                "inspection_token": inspection["inspection_token"],
                "verified": True,
            },
        )
        request(
            base + "/source-access/approve",
            {"expected_config_revision": 2, "expected_approval_revision": 0, "verified": True},
        )
    print("Configured only generated Stage 05 target keys, passwords and log-root approvals.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "prepare",
            "migrate",
            "seed",
            "fixture",
            "up",
            "stop",
            "configure",
            "append",
            "restart",
            "runner",
            "burst",
            "resources",
            "archives",
            "capacity-archive",
            "capacity-state",
            "append-batch",
            "reset-active",
        ],
    )
    parser.add_argument("--source", type=int, choices=range(5), default=0)
    parser.add_argument("--text", default="SYNTHETIC-BROWSER-APPEND")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--label", default="two-systems-five")
    parser.add_argument("--items-json", default="[]")
    parser.add_argument("--interval-ms", type=int, default=250)
    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(seed())
        return
    if args.command == "capacity-state":
        print(json.dumps(asyncio.run(capacity_state())))
        return
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".cache/docker"))
    if args.command == "prepare":
        prepare()
        return
    override = checked_setup()
    if args.command == "runner":
        runner()
        return
    if args.command == "resources":
        resources(args.label)
        return
    if args.command == "configure":
        configure()
        return
    if args.command == "archives":
        local.compose(
            "exec",
            "-T",
            SSH_SERVICE,
            "python",
            "/workspace/scripts/stage5_sftp_fixture.py",
            "archive",
            override=override,
        )
        configure(archive_only=True)
        return
    if args.command == "capacity-archive":
        metadata = json.loads(
            local.compose(
                "exec",
                "-T",
                SSH_SERVICE,
                "python",
                "/workspace/scripts/stage5_sftp_fixture.py",
                "capacity-archive",
                override=override,
            )
        )
        if metadata.get("expanded_bytes") != 16_777_216 or metadata.get("records") != 65_536:
            raise local.SetupError("Unexpected capacity fixture size.")
        evidence = ROOT / "verification/stage-5/capacity-fixture.json"
        evidence.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        print(
            "Prepared generated 16 MiB regular ZIP member with 65,536 exact 256-byte UTC records."
        )
        return
    if args.command == "reset-active":
        workload = json.loads(
            local.compose(
                "exec",
                "-T",
                SERVICE,
                "python",
                "/workspace/scripts/stage5_local.py",
                "capacity-state",
                override=override,
                timeout=20,
            )
        )
        if workload["active_jobs"] or any(workload["live_subscriptions"].values()):
            raise local.SetupError(
                "Stop all Stage 05 fixture investigations before resetting logs."
            )
        metadata = json.loads(
            local.compose(
                "exec",
                "-T",
                SSH_SERVICE,
                "python",
                "/workspace/scripts/stage5_sftp_fixture.py",
                "reset-active",
                override=override,
            )
        )
        if len(metadata["files"]) != 5 or any(item["records"] != 360 for item in metadata["files"]):
            raise local.SetupError("Unexpected synthetic active-log reset result.")
        evidence = ROOT / "verification/stage-5/active-log-resets.json"
        entries = json.loads(evidence.read_text("utf-8")) if evidence.exists() else []
        entries.append({"command": "stage5_local.py reset-active", **metadata})
        evidence.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
        print(
            "Reset only five generated active logs to 360 records each; ZIP and SSH identity preserved."
        )
        return
    if args.command == "migrate":
        output = local.compose(
            "run",
            "--rm",
            "--no-deps",
            "-e",
            "INSPECTOR_CONFIG_FILE=/etc/system-inspector/integration.yaml",
            "integration",
            "python",
            "-m",
            "alembic",
            "upgrade",
            "head",
            override=override,
        )
    elif args.command == "fixture":
        output = local.compose(
            "run",
            "--rm",
            "--no-deps",
            SERVICE,
            "python",
            "/workspace/scripts/stage5_local.py",
            "seed",
            override=override,
        )
    elif args.command in {"append", "burst"}:
        output = local.compose(
            "exec",
            "-T",
            SSH_SERVICE,
            "python",
            "/workspace/scripts/stage5_sftp_fixture.py",
            args.command,
            "--source",
            str(args.source),
            "--text",
            args.text,
            *(("--count", str(args.count)) if args.command == "burst" else ()),
            override=override,
        )
    elif args.command == "append-batch":
        output = local.compose(
            "exec",
            "-T",
            SSH_SERVICE,
            "python",
            "/workspace/scripts/stage5_sftp_fixture.py",
            "append-batch",
            "--items-json",
            args.items_json,
            "--interval-ms",
            str(args.interval_ms),
            override=override,
            timeout=30,
        )
    elif args.command == "up":
        output = local.compose(
            "up", "--detach", "--no-deps", SSH_SERVICE, SERVICE, override=override
        )
    elif args.command == "restart":
        output = local.compose("restart", SERVICE, override=override)
    else:
        output = local.compose("stop", SERVICE, SSH_SERVICE, override=override)
    print(output, end="")


if __name__ == "__main__":
    try:
        main()
    except local.SetupError as error:
        raise SystemExit(str(error)) from None
    except (OSError, ValueError, KeyError):
        raise SystemExit("Stage 05 fixture failed safely; no secret values were printed.") from None
