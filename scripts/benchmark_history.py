"""20 MiB production collector/index/query benchmark in a guarded synthetic schema.

Run inside the Stage 03 local runner after stage3_local.py fixture, with its
server stopped. No arbitrary filesystem input or remote endpoint is accepted.
Generated input uses the original tools/generate_load_fixture.py. Only the
server-side synthetic source manifest differs from the small golden fixture.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4


def phase(name: str, **values: object) -> None:
    """Safe timings only: never emit account records, query text or configuration."""
    print(json.dumps({"phase": name, **values}), file=sys.stderr, flush=True)


def container_limits() -> dict:
    """Read fixed Linux cgroup metadata only; absence is recorded explicitly."""
    result = {}
    for label, filename in {
        "memory_max": "/sys/fs/cgroup/memory.max",
        "memory_high": "/sys/fs/cgroup/memory.high",
        "cpu_max": "/sys/fs/cgroup/cpu.max",
        "cpuset_effective": "/sys/fs/cgroup/cpuset.cpus.effective",
        "v1_memory_limit_bytes": "/sys/fs/cgroup/memory/memory.limit_in_bytes",
        "v1_memory_peak_bytes": "/sys/fs/cgroup/memory/memory.max_usage_in_bytes",
        "v1_cpu_quota_us": "/sys/fs/cgroup/cpu/cpu.cfs_quota_us",
        "v1_cpu_period_us": "/sys/fs/cgroup/cpu/cpu.cfs_period_us",
        "v1_cpuset_cpus": "/sys/fs/cgroup/cpuset/cpuset.cpus",
    }.items():
        try:
            with Path(filename).open("r", encoding="ascii") as stream:
                result[label] = stream.read(4096).strip()
        except OSError:
            result[label] = None
    return result


async def profile_query(job_id: str, compare_job_id: str | None = None) -> dict:
    """Read-only SQL/driver/matcher diagnostics; never open the serving supervisor."""
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from inspector.config import load_config
    from inspector.database import create_engine
    from inspector.history import order_columns
    from inspector.log_engine import LiteralFilter
    from inspector.persistence.models import HistoryEvent, HistoryJob

    config = load_config()
    if not config.local_history_demo or not config.database.name.startswith(
        "inspector_test_s3_web_"
    ):
        raise RuntimeError("Read-only profiling requires the isolated Stage 03 synthetic schema.")
    engine = create_engine(config.database)
    timings = {}
    storage = {}
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            job = await session.get(HistoryJob, ("stage3-fixture-a", job_id))
            if job is None or job.status != "completed" or job.event_count != 102575:
                raise RuntimeError("Expected the completed synthetic 20 MiB benchmark capture.")
            conditions = (
                HistoryEvent.project_id == job.project_id,
                HistoryEvent.job_id == job.id,
                HistoryEvent.capture_seq <= job.event_count,
                HistoryEvent.timestamp_us >= job.from_us,
                HistoryEvent.timestamp_us < job.to_us,
                HistoryEvent.process_id.in_(job.process_ids),
            )
            columns = (
                HistoryEvent.event_id,
                HistoryEvent.timestamp_us,
                HistoryEvent.process_id,
                HistoryEvent.source_revision_id,
                HistoryEvent.member_order,
                HistoryEvent.byte_start,
            )

            async def measured(label: str, query: object) -> list:
                samples = []
                rows = []
                for _ in range(3):
                    before = time.perf_counter()
                    rows = (await session.execute(query)).all()
                    samples.append((time.perf_counter() - before) * 1000)
                timings[label] = {"rows": len(rows), "samples_ms": samples, "min_ms": min(samples)}
                return rows

            keys = await measured(
                "keys_plus_octet_length_4096",
                select(*columns, func.octet_length(HistoryEvent.raw_line).label("raw_bytes"))
                .where(*conditions)
                .order_by(*order_columns())
                .limit(4096),
            )
            await measured(
                "keys_without_octet_length_4096",
                select(*columns).where(*conditions).order_by(*order_columns()).limit(4096),
            )
            ids = [row.event_id for row in keys]
            raw_conditions = (
                HistoryEvent.project_id == job.project_id,
                HistoryEvent.job_id == job.id,
                HistoryEvent.event_id.in_(ids),
            )
            json_status = func.json_unquote(
                func.json_extract(HistoryEvent.payload, "$.parse_status")
            )
            await measured(
                "raw_plus_json_status_by_ids_4096",
                select(
                    HistoryEvent.event_id, HistoryEvent.raw_line, json_status.label("parse_status")
                ).where(*raw_conditions),
            )
            raw = await measured(
                "raw_without_json_by_ids_4096",
                select(HistoryEvent.event_id, HistoryEvent.raw_line).where(*raw_conditions),
            )
            await measured(
                "keys_raw_json_one_select_4096",
                select(*columns, HistoryEvent.raw_line, json_status.label("parse_status"))
                .where(*conditions)
                .order_by(*order_columns())
                .limit(4096),
            )
            matcher = LiteralFilter(include=("request_id=REQ-0042 ",))
            before = time.perf_counter()
            matches = sum(matcher.matches(row.raw_line) for row in raw)
            timings["python_literal_4096"] = {
                "matches": matches,
                "milliseconds": (time.perf_counter() - before) * 1000,
                "raw_bytes": sum(len(row.raw_line.encode("utf-8")) for row in raw),
            }
            for selected_job in dict.fromkeys([job_id, compare_job_id]):
                if selected_job is None:
                    continue
                parent = await session.get(HistoryJob, ("stage3-fixture-a", selected_job))
                if parent is None or parent.status != "completed" or parent.event_count != 102575:
                    raise RuntimeError("Storage comparison requires a complete synthetic capture.")
                before = time.perf_counter()
                totals = (
                    await session.execute(
                        select(
                            func.count().label("events"),
                            func.sum(func.octet_length(HistoryEvent.raw_line)).label("raw_bytes"),
                            func.sum(func.octet_length(HistoryEvent.payload)).label(
                                "payload_bytes"
                            ),
                            func.max(func.octet_length(HistoryEvent.payload)).label(
                                "max_payload_bytes"
                            ),
                        ).where(
                            HistoryEvent.project_id == "stage3-fixture-a",
                            HistoryEvent.job_id == selected_job,
                        )
                    )
                ).one()
                storage[selected_job] = {
                    "events": int(totals.events),
                    "raw_bytes": int(totals.raw_bytes),
                    "payload_bytes": int(totals.payload_bytes),
                    "max_payload_bytes": int(totals.max_payload_bytes),
                    "payload_bytes_per_event": int(totals.payload_bytes) / int(totals.events),
                    "aggregate_query_ms": (time.perf_counter() - before) * 1000,
                }
    finally:
        await engine.dispose()
    return {
        "synthetic": True,
        "read_only": True,
        "job_id": job_id,
        "purpose": "Concurrent-browser diagnostic sample; not acceptance performance evidence.",
        "measurements": timings,
        "storage_totals": storage,
    }


async def benchmark(generated: Path, *, profile_ingestion: bool = False) -> dict:
    import resource

    from sqlalchemy import text

    from inspector import auth, services
    from inspector.app import create_app
    from inspector.config import load_config
    from inspector.domain import ProjectContext
    from inspector.history import HistoricalQueryInput, canonical_time, historical_query
    from inspector.history_cache import READ_CACHE
    from inspector.persistence.models import HistoryJob, HistorySource, Project, TopologyState
    from inspector.security import token_hash

    config = load_config()
    if not config.local_history_demo or not config.database.name.startswith(
        "inspector_test_s3_web_"
    ):
        raise RuntimeError("Benchmark requires the isolated Stage 03 synthetic schema.")
    accounts = json.loads(
        await asyncio.to_thread(Path("/run/secrets/browser_accounts").read_text, "utf-8")
    )
    manifest = json.loads(
        await asyncio.to_thread((generated / "generated-manifest.json").read_text, "utf-8")
    )
    application = create_app(config)
    ingestion_profile: dict = {}
    job_id = str(uuid4())
    project_id = "stage3-fixture-a"
    phase("application_start")
    async with application.router.lifespan_context(application):
        phase("application_ready")
        sessions = application.state.sessions
        async with sessions.begin() as session:
            credentials = await auth.login(
                session,
                accounts["inspector"]["username"],
                accounts["inspector"]["password"],
                services.utc_now_us(),
                config.idle_timeout_us,
                config.absolute_timeout_us,
            )
            actor = credentials.principal
            workspace = await services.create_workspace(
                session,
                actor,
                ProjectContext(project_id, actor.user_id),
                max_per_user=config.max_workspaces_per_user,
                max_global=config.max_workspaces_global,
                now_us=services.utc_now_us(),
            )
            project = await session.get(Project, project_id)
            state = await session.get(TopologyState, project_id)
            assert project is not None and state is not None
            document = copy.deepcopy(state.config)
            selected = [process["id"] for process in document["processes"]]
            job = HistoryJob(
                project_id=project_id,
                id=job_id,
                workspace_id=workspace["workspace_id"],
                owner_user_id=actor.user_id,
                auth_version=actor.auth_version,
                auth_session_hash=token_hash(credentials.token),
                config_revision=project.revision,
                config_snapshot=document,
                process_ids=selected,
                from_us=canonical_time("2026-10-16T12:00:00.000000Z"),
                to_us=canonical_time("2026-10-16T12:02:00.000000Z"),
                status="queued",
                snapshot_revision=0,
                event_count=0,
                parse_issue_count=0,
                downloaded_bytes=0,
                expanded_bytes=0,
                created_us=services.utc_now_us(),
                errors=[],
            )
            session.add(job)
            await session.flush()
            for process, generated_source in zip(
                document["processes"], manifest["sources"], strict=True
            ):
                source_id = "benchmark-" + process["id"]
                session.add(
                    HistorySource(
                        project_id=project_id,
                        job_id=job_id,
                        id=source_id,
                        process_id=process["id"],
                        process_kind="process",
                        remote_path=process["log_source"]["active_path"],
                        kind="plain",
                        cache_name=str(uuid4()),
                        checksum=None,
                        status="queued",
                        error_code=None,
                        event_count=0,
                        downloaded_bytes=0,
                        expanded_bytes=0,
                        manifest={
                            "process_id": process["id"],
                            "source_revision_id": source_id,
                            "local_path": str(generated / generated_source["file"]),
                            "remote_path": process["log_source"]["active_path"],
                            "kind": "plain",
                            "archive_member": None,
                            "member_ordinal": None,
                            "file_sha256": generated_source["sha256"],
                        },
                    )
                )
        phase("collection_start", input_bytes=manifest["total_bytes"])
        start = time.perf_counter()
        if profile_ingestion:
            from sqlalchemy import event

            from inspector import history, log_engine

            original_persist = history.persist_event_batch
            original_parser = log_engine.iter_source_events
            original_dispatch = application.state.history._dispatch
            original_source = application.state.history._source
            source_start = 0.0
            statements: dict[str, dict] = {}
            ingestion_profile = {
                "purpose": "Diagnostic wrapper timings; phases can overlap across parser/consumer.",
                "persist_calls": 0,
                "persist_seconds": 0.0,
                "dispatch_calls": 0,
                "dispatch_seconds": 0.0,
                "parser_next_calls": 0,
                "parser_next_seconds": 0.0,
                "capture_setup_seconds": 0.0,
                "sources": [],
            }

            async def measured_persist(*args, **kwargs):
                began = time.perf_counter()
                try:
                    return await original_persist(*args, **kwargs)
                finally:
                    ingestion_profile["persist_calls"] += 1
                    ingestion_profile["persist_seconds"] += time.perf_counter() - began

            async def measured_dispatch(*args, **kwargs):
                began = time.perf_counter()
                try:
                    return await original_dispatch(*args, **kwargs)
                finally:
                    ingestion_profile["dispatch_calls"] += 1
                    ingestion_profile["dispatch_seconds"] += time.perf_counter() - began

            async def measured_source(*args, **kwargs):
                nonlocal source_start
                source_start = time.perf_counter()
                try:
                    return await original_source(*args, **kwargs)
                finally:
                    elapsed = time.perf_counter() - source_start
                    ingestion_profile["sources"].append({"source_id": args[2], "seconds": elapsed})

            def measured_parser(*args, **kwargs):
                ingestion_profile["capture_setup_seconds"] += time.perf_counter() - source_start
                iterator = iter(original_parser(*args, **kwargs))
                while True:
                    began = time.perf_counter()
                    try:
                        value = next(iterator)
                    except StopIteration:
                        ingestion_profile["parser_next_seconds"] += time.perf_counter() - began
                        return
                    ingestion_profile["parser_next_seconds"] += time.perf_counter() - began
                    ingestion_profile["parser_next_calls"] += 1
                    yield value

            def statement_before(connection, cursor, statement, parameters, context, many):
                context._stage3_begin = time.perf_counter()

            def statement_after(connection, cursor, statement, parameters, context, many):
                kind = statement.lstrip().partition(" ")[0].upper()
                entry = statements.setdefault(kind, {"calls": 0, "seconds": 0.0})
                entry["calls"] += 1
                entry["seconds"] += time.perf_counter() - context._stage3_begin

            history.persist_event_batch = measured_persist
            log_engine.iter_source_events = measured_parser
            application.state.history._dispatch = measured_dispatch
            application.state.history._source = measured_source
            sql_engine = sessions.kw["bind"].sync_engine
            event.listen(sql_engine, "before_cursor_execute", statement_before)
            event.listen(sql_engine, "after_cursor_execute", statement_after)
            try:
                await application.state.history._collect(project_id, job_id)
            finally:
                history.persist_event_batch = original_persist
                log_engine.iter_source_events = original_parser
                application.state.history._dispatch = original_dispatch
                application.state.history._source = original_source
                event.remove(sql_engine, "before_cursor_execute", statement_before)
                event.remove(sql_engine, "after_cursor_execute", statement_after)
                ingestion_profile["sql_statements"] = statements
        else:
            await application.state.history._collect(project_id, job_id)
        ingestion_seconds = time.perf_counter() - start
        phase("collection_finished", seconds=ingestion_seconds)
        async with sessions.begin() as session:
            indexed = await session.get(HistoryJob, (project_id, job_id))
            assert indexed is not None and indexed.status == "completed", (
                "Capture did not complete."
            )
            expected_count = sum(source["lines"] for source in manifest["sources"])
            assert indexed.event_count == expected_count
            assert indexed.downloaded_bytes == manifest["total_bytes"]
        timings = {}
        expected_matches = {
            "full_interval_unfiltered": expected_count,
            "full_interval_literal": sum(
                (source["lines"] + 957) // 1000 for source in manifest["sources"]
            ),
            "narrow_interval_literal": len(manifest["sources"]),
        }
        for label, literal, end in (
            ("full_interval_unfiltered", "", "2026-10-16T12:02:00.000000Z"),
            ("full_interval_literal", "request_id=REQ-0042 ", "2026-10-16T12:02:00.000000Z"),
            ("narrow_interval_literal", "request_id=REQ-0042 ", "2026-10-16T12:00:01.000000Z"),
        ):
            samples = []
            request = HistoricalQueryInput.model_validate(
                {
                    "process_ids": selected,
                    "from": "2026-10-16T12:00:00.000000Z",
                    "to": end,
                    "filter": {"include": [literal] if literal else []},
                    "limit": 200,
                }
            )
            for iteration in range(11):
                phase("query_start", query=label, iteration=iteration)
                begin = time.perf_counter()
                async with sessions() as session:
                    result = await historical_query(
                        session,
                        actor,
                        project_id,
                        job_id,
                        request,
                        supervisor=application.state.supervisor,
                        login_hash=token_hash(credentials.token),
                        idle_timeout_us=config.idle_timeout_us,
                    )
                    await session.commit()
                elapsed_ms = (time.perf_counter() - begin) * 1000
                phase("query_finished", query=label, iteration=iteration, milliseconds=elapsed_ms)
                assert result["matched_count"] == expected_matches[label]
                if iteration:
                    samples.append(elapsed_ms)
                else:
                    cold_ms = elapsed_ms
            timings[label] = {
                "runs": len(samples),
                "warmup_runs": 1,
                "cold_ms": cold_ms,
                "matched_count": result["matched_count"],
                "page_items": len(result["items"]),
                "p95_ms": sorted(samples)[math.ceil(len(samples) * 0.95) - 1],
                "min_ms": min(samples),
                "max_ms": max(samples),
            }
        async with sessions.begin() as session:
            version = await session.scalar(text("SELECT VERSION()"))
            await auth.logout(session, actor, services.utc_now_us())
        cache = {
            "used_bytes": READ_CACHE.used_bytes,
            "max_bytes": READ_CACHE.max_bytes,
            "entries": len(READ_CACHE.entries),
            "ttl_seconds": READ_CACHE.ttl_seconds,
        }
        phase("benchmark_finished")
    return {
        "synthetic": True,
        "transport": "local cached files; network download excluded",
        "implementation": "HistoryManager._collect, production bounded parser/bulk index and historical_query",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "logical_cpus": os.cpu_count(),
        "container_limits": container_limits(),
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "read_cache": cache,
        "mariadb": version,
        "job_id": job_id,
        "input_bytes": manifest["total_bytes"],
        "processes": len(manifest["sources"]),
        "input_manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest(),
        "indexed_events": expected_count,
        "ingestion_seconds": ingestion_seconds,
        "ingestion_profile": ingestion_profile,
        "queries": timings,
        "target_ingestion_seconds": 10,
        "target_query_p95_ms": 500,
        "target_ingestion_met": ingestion_seconds <= 10,
        "target_all_query_p95_met": all(row["p95_ms"] <= 500 for row in timings.values()),
    }


def main() -> None:
    if os.name != "posix":
        raise SystemExit("Run this benchmark inside the isolated Stage 03 Linux runner.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-job")
    parser.add_argument("--profile-compare-job")
    parser.add_argument("--ingestion-profile", action="store_true")
    args = parser.parse_args()
    if args.profile_job is not None:
        print(
            json.dumps(
                asyncio.run(profile_query(args.profile_job, args.profile_compare_job)), indent=2
            )
        )
        return
    with tempfile.TemporaryDirectory(prefix="inspector-benchmark-") as directory:
        generated = Path(directory) / "input"
        subprocess.run(
            [
                sys.executable,
                "/workspace/tools/generate_load_fixture.py",
                "--output-dir",
                str(generated),
                "--size-mib",
                "20",
                "--processes",
                "5",
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        print(
            json.dumps(
                asyncio.run(benchmark(generated, profile_ingestion=args.ingestion_profile)),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
