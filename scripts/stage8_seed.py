"""Seed and inspect only explicitly disposable Stage 08 release installations.

Invoked inside the release app image, with scripts/examples mounted read-only.
Credentials come from /run/secrets/browser_accounts and are never returned.
Collection, inventory import and trust approval remain explicit real API actions.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import traceback
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from inspector import auth, foundation, services, topology
from inspector.config import load_config
from inspector.database import check_runtime_grants, check_schema, create_engine
from inspector.domain import Principal
from inspector.persistence.models import Project, SSHCredential, User
from inspector.ssh_access import Vault

PROJECTS = ("stage8-fixture-a", "stage8-fixture-b")
ROOT = Path(__file__).resolve().parents[1]
STABLE_TABLES = (
    "users",
    "user_preferences",
    "application_settings",
    "projects",
    "project_revisions",
    "topology_states",
    "topology_snapshots",
    "entity_identities",
    "topology_entity_names",
    "subsystems",
    "connection_profiles",
    "parser_profiles",
    "servers",
    "processes",
    "flows",
    "shared_views",
    "view_nodes",
    "view_flows",
    "history_sources",
    "history_events",
    "saved_investigations",
    "investigation_bookmarks",
    "offline_investigations",
    "offline_analysis",
    "inventory_sources",
    "inventory_host_mappings",
    "inventory_process_mappings",
    "ssh_credentials",
    "project_credential_bindings",
    "ssh_host_trust",
    "source_access_approvals",
)


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str
    ).encode("ascii")


def cache_manifest(directory: str) -> list[dict]:
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Qualification cache must be a real directory")
    result = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Qualification cache cannot contain symlinks")
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
            result.append(
                dict(
                    path=path.relative_to(root).as_posix(),
                    bytes=path.stat().st_size,
                    sha256=digest.hexdigest(),
                )
            )
    return result


async def seed(sessions, config) -> dict:
    accounts = json.loads(
        await asyncio.to_thread(Path("/run/secrets/browser_accounts").read_text, "utf-8")
    )
    document = json.loads(
        await asyncio.to_thread((ROOT / "examples/project.example.json").read_text, "utf-8")
    )
    async with sessions.begin() as session:
        if await session.scalar(select(User.id).limit(1)) or await session.scalar(
            select(Project.id).limit(1)
        ):
            raise ValueError(
                "Seed requires an empty disposable installation; existing data is preserved"
            )
        admin = await auth.bootstrap_admin(
            session,
            accounts["administrator"]["username"],
            "Synthetic Stage 08 Administrator",
            accounts["administrator"]["password"],
        )
        actor = Principal(admin.id, admin.role, admin.auth_version)
        inspector = await auth.create_user(
            session,
            actor,
            accounts["inspector"]["username"],
            "Synthetic Stage 08 Inspector",
            accounts["inspector"]["password"],
        )
        await foundation.initialize_settings(session, config)
        for account, theme in ((admin, "dark"), (inspector, "light")):
            await foundation.update_preferences(
                session,
                Principal(account.id, account.role, account.auth_version),
                foundation.PreferenceInput(expected_revision=1, theme_mode=theme, language="en"),
            )
        for identifier in PROJECTS:
            project = await services.create_project(
                session,
                actor,
                "[Synthetic investigation] " + identifier[-1].upper(),
                "Disposable offline release qualification",
                project_id=identifier,
            )
            config_document = json.loads(json.dumps(document))
            config_document["project"].update(id=identifier, name=project.name, revision=1)
            config_document["connections"] = [
                {
                    "id": "c-live",
                    "name": "Synthetic Stage 08 SFTP",
                    "host": "stage8-sftp",
                    "port": 8022,
                    "username": "synthetic-log-reader",
                    "credential_ref": "synthetic-stage8",
                    "jump_connection_id": None,
                    "allowed_log_roots": ["/var/log/inspector-demo"],
                }
            ]
            for server in config_document["servers"]:
                server["connection_id"] = "c-live"
            current_actor, project, state = await topology.context(
                session, actor, identifier, "topology.write", writable=True
            )
            await topology.save(
                session,
                current_actor,
                project,
                state,
                config_document,
                confirmed_deletions=False,
                reparent=False,
            )
    return dict(
        seeded=True,
        projects=list(PROJECTS),
        account_roles=["administrator", "inspector"],
        personal_themes=["dark", "light"],
        automatic_target_connections=0,
    )


async def snapshot(sessions, config, *, require_data: bool) -> dict:
    result = {"projects": list(PROJECTS), "tables": {}, "project_counts": {}}
    async with sessions() as session:
        names = set(
            (
                await session.scalars(
                    text(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE()"
                    )
                )
            ).all()
        )
        for name in STABLE_TABLES:
            if name not in names:
                continue
            rows = [
                dict(row)
                for row in (await session.execute(text(f"SELECT * FROM `{name}`"))).mappings()
            ]
            encoded = sorted(canonical(row).decode("ascii") for row in rows)
            result["tables"][name] = dict(
                count=len(rows), sha256=hashlib.sha256(canonical(encoded)).hexdigest()
            )
        assert result["tables"]["projects"]["count"] == 2
        assert result["tables"]["users"]["count"] == 2
        roles = sorted(
            (await session.execute(text("SELECT role FROM users WHERE enabled=1"))).scalars()
        )
        assert roles == ["administrator", "inspector"]
        themes = sorted(
            (await session.execute(text("SELECT theme_mode FROM user_preferences"))).scalars()
        )
        assert themes == ["dark", "light"]
        for project in PROJECTS:
            counts = {}
            for name in (
                "history_events",
                "saved_investigations",
                "inventory_sources",
                "inventory_host_mappings",
            ):
                if name in names:
                    counts[name] = await session.scalar(
                        text(f"SELECT COUNT(*) FROM `{name}` WHERE project_id=:project"),
                        {"project": project},
                    )
            if require_data:
                assert all(
                    counts.get(name, 0) > 0
                    for name in (
                        "history_events",
                        "saved_investigations",
                        "inventory_sources",
                        "inventory_host_mappings",
                    )
                ), f"System {project} lacks required real captured/imported/saved data"
            result["project_counts"][project] = counts
        sources = (
            (
                await session.execute(
                    text(
                        "SELECT project_id,job_id,cache_name,checksum,downloaded_bytes FROM history_sources WHERE checksum IS NOT NULL"
                    )
                )
            )
            .mappings()
            .all()
        )
        credentials = (await session.scalars(select(SSHCredential))).all()
        if require_data:
            assert credentials, "Real SFTP collection must have protected bound credentials"
        vault = Vault(config.vault_key_file)
        for credential in credentials:
            assert vault.decrypt(credential), "Protected credential recovery failed"
    files = await asyncio.to_thread(cache_manifest, config.cache_dir)
    if require_data:
        assert all(
            any(source["project_id"] == project for source in sources) for project in PROJECTS
        ), "Both systems require retained raw sources with checksums"
        assert files, "Real captured data requires nonempty retained cache"
    indexed = {item["path"]: item for item in files}
    for source in sources:
        key = "/".join(
            (
                "historical",
                hashlib.sha256(source["project_id"].encode()).hexdigest(),
                source["job_id"],
                source["cache_name"],
            )
        )
        assert indexed[key]["sha256"] == source["checksum"]
        assert indexed[key]["bytes"] == source["downloaded_bytes"]
    result["cache"] = dict(
        count=len(files),
        bytes=sum(item["bytes"] for item in files),
        sha256=hashlib.sha256(canonical(files)).hexdigest(),
    )
    result["source_checksums_verified"] = len(sources)
    result["decrypted_credentials_verified"] = len(credentials)
    return result


async def run(args) -> dict:
    if os.environ.get("SI_STAGE8_DISPOSABLE") != "1":
        raise ValueError("SI_STAGE8_DISPOSABLE=1 opt-in is required; no database was contacted")
    config = load_config()
    engine = create_engine(config.database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.connect() as connection:
            await check_schema(connection)
            await check_runtime_grants(connection)
        if args.command == "seed":
            return await seed(sessions, config)
        actual = await snapshot(sessions, config, require_data=args.require_data)
        if args.command == "verify-restored":
            if not args.expected:
                raise ValueError("verify-restored requires --expected snapshot JSON")
            expected = json.loads(await asyncio.to_thread(args.expected.read_text, "utf-8"))
            assert actual == expected, (
                "Restored roles/preferences/configuration/mappings/investigations/cache differ"
            )
            async with sessions() as session:
                assert await session.scalar(text("SELECT COUNT(*) FROM auth_sessions")) == 0, (
                    "Restored authentication must be revoked before login"
                )
                assert (
                    await session.scalar(
                        text("SELECT COUNT(*) FROM workspaces WHERE state='active'")
                    )
                    == 0
                )
                assert (
                    await session.scalar(
                        text(
                            "SELECT COUNT(*) FROM live_sessions WHERE status NOT IN ('stopped','failed','interrupted')"
                        )
                    )
                    == 0
                )
                assert (
                    await session.scalar(
                        text(
                            "SELECT COUNT(*) FROM history_jobs WHERE status NOT IN ('completed','partial','cancelled','failed','interrupted')"
                        )
                    )
                    == 0
                )
            return dict(
                restored=True,
                stable_snapshot_identical=True,
                roles_preferences_and_owned_data_preserved=True,
                all_system_cache_checksums_verified=actual["source_checksums_verified"],
                recovered_vault_credentials_verified=actual["decrypted_credentials_verified"],
                authentication_sessions=0,
                active_workspaces=0,
                active_live_sessions=0,
                active_collection_jobs=0,
            )
        return actual
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["seed", "snapshot", "verify-restored"])
    parser.add_argument("--expected", type=Path)
    parser.add_argument(
        "--require-data",
        action="store_true",
        help="Require real imported mappings, captured events and saved investigations in both systems",
    )
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(run(args)), sort_keys=True))
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "passed": False,
                    "error_type": type(error).__name__,
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


if __name__ == "__main__":
    raise SystemExit(main())
