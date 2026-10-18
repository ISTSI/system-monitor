"""Historical SSH planning with explicit system, owner and access snapshots.

Only configured process IDs reach this adapter. Connections are reused inside a
single guarded job/plan and closed at its end; nothing is pooled by address.
"""

import asyncio
from collections import Counter
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from inspector.domain import Principal, server_connection_id
from inspector.errors import DomainError


class RemoteHistory:
    def __init__(self, access: Any, config: Any) -> None:
        self.access, self.config = access, config
        self.active: Counter[tuple[str, str]] = Counter()
        self.host_slots = asyncio.BoundedSemaphore(
            min(4, config.history_limits.get("concurrent_hosts", 4))
        )

    def file_limits(self) -> dict[str, int]:
        limits = self.config.history_limits
        return dict(
            max_candidates=limits.get("max_source_files_per_collection", 1000),
            max_listing_entries=limits.get("max_source_listing_entries", 10_000),
            max_listing_bytes=limits.get("max_source_listing_bytes", 4_194_304),
            max_probe_bytes=limits.get("max_source_probe_bytes", 33_554_432),
            max_estimated_bytes=limits.get("max_download_bytes_per_collection", 536_870_912),
        )

    async def plan(
        self,
        actor: Principal,
        project_id: str,
        revision: int,
        document: dict,
        selection: list[str],
        session_hash: str | None,
    ) -> list[dict]:
        from inspector.ssh_files import open_files

        key = (project_id, actor.user_id)
        if (
            sum(self.active.values())
            >= min(4, self.config.history_limits.get("max_collection_jobs_global", 4))
            or sum(n for (_, owner), n in self.active.items() if owner == actor.user_id)
            >= min(2, self.config.history_limits.get("max_collection_jobs_per_user", 2))
            or sum(n for (project, _), n in self.active.items() if project == project_id)
            >= min(2, self.config.history_limits.get("max_collection_jobs_per_project", 2))
        ):
            raise DomainError("LIMIT_REACHED", "Historical source planning is busy.", 429)
        processes = {p["id"]: p for p in document["processes"]}
        servers = {s["id"]: s for s in document["servers"]}
        if not set(selection) <= processes.keys():
            raise DomainError("NOT_FOUND", "Resource not found.", 404)
        grouped: dict[str, list[dict]] = {}
        for process_id in selection:
            process = processes[process_id]
            connection_id = server_connection_id(servers[process["server_id"]])
            grouped.setdefault(connection_id, []).append(process)
        self.active[key] += 1
        try:
            candidates: list[dict] = []
            remaining = self.config.history_limits.get(
                "max_download_bytes_per_collection", 536_870_912
            )
            for connection_id, group in grouped.items():
                route_limits = self.file_limits()
                route_limits["max_candidates"] -= len(candidates)
                route_limits["max_estimated_bytes"] = max(1, remaining)
                if route_limits["max_candidates"] < 1:
                    raise DomainError("CANDIDATE_LIMIT", "Too many historical candidates.", 413)
                snapshot = await self.access.prepare(
                    actor, project_id, connection_id, revision, session_hash
                )

                async def operation(
                    snapshot: Any = snapshot,
                    group: list[dict] = group,
                    connection_id: str = connection_id,
                    route_limits: dict[str, int] = route_limits,
                ) -> list[dict]:
                    result: list[dict] = []
                    async with (
                        self.host_slots,
                        open_files(
                            snapshot.target,
                            snapshot.jump,
                            allow_loopback=self.config.ssh_allow_loopback,
                            timeout_seconds=self.config.history_limits.get(
                                "archive_task_timeout_seconds", 120
                            ),
                            **route_limits,
                        ) as remote,
                    ):
                        for process in group:
                            warning_start = len(remote.warnings)
                            files = await remote.plan(process["log_source"], list(snapshot.roots))
                            warnings = list(remote.warnings[warning_start:])
                            for entry in files:
                                # This ID identifies this immutable capture, independently of
                                # names, filters or any unproven remote generation/inode.
                                source_id = str(uuid4())
                                result.append(
                                    dict(
                                        transport="ssh",
                                        source_revision_id=source_id,
                                        process_id=process["id"],
                                        connection_id=connection_id,
                                        config_revision=revision,
                                        access_signature=snapshot.signature,
                                        remote_file=asdict(entry),
                                        remote_path=entry.path,
                                        kind=entry.kind,
                                        estimated_bytes=entry.estimated_bytes,
                                        archive_member=None,
                                        member_ordinal=None,
                                        member_patterns=list(entry.member_patterns),
                                        warnings=warnings,
                                    )
                                )
                    return result

                found = await self.access.watched(
                    actor, project_id, connection_id, revision, session_hash, snapshot, operation
                )
                remaining -= sum(item["estimated_bytes"] for item in found)
                if remaining < 0:
                    raise DomainError(
                        "DOWNLOAD_LIMIT", "The collection exceeds the download budget.", 413
                    )
                candidates.extend(found)
                if len(candidates) > self.config.history_limits.get(
                    "max_source_files_per_collection", 1000
                ):
                    raise DomainError("CANDIDATE_LIMIT", "Too many historical candidates.", 413)
            if set(selection) != {item["process_id"] for item in candidates}:
                raise DomainError("SOURCE_MISSING", "No readable configured source was found.", 422)
            return candidates
        finally:
            self.active[key] -= 1
            if not self.active[key]:
                del self.active[key]
