"""Real pinned loopback SFTP exercises the production live adapter and timings."""

import asyncio
import math
import os
import time
from dataclasses import replace

import asyncssh
import pytest
from test_live_engine import line, until
from test_ssh_files import endpoint

from inspector import ssh_transport
from inspector.live_engine import LiveEngine, LiveLimits, LiveSource
from inspector.log_engine import LiteralFilter


def live_source(target, **changes):
    return replace(
        LiveSource(
            "project-a",
            "owner",
            "process-0",
            1,
            "trust-credential-approval-v1",
            "/logs/app.log",
            "/logs",
            target,
            allow_loopback=True,
        ),
        **changes,
    )


async def test_real_sftp_seed_append_race_split_utf8_and_literal_refilter(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    path = logs / "app.log"
    initial = line("seed Straße") + b"2026-10-17T12:00:01Z caf\xc3"
    path.write_bytes(initial)
    async with endpoint(tmp_path) as (target, state):
        raced = False

        async def race(file_obj, offset, size):
            nonlocal raced
            if not raced and size == len(initial) and offset == 0:
                raced = True
                with path.open("ab") as stream:
                    stream.write(b"\xa9\r\n" + line("new unmatched", 2))

        state.read_hook = race
        engine = LiveEngine(LiveLimits(poll_seconds=0.02, merge_seconds=0.02))
        try:
            await engine.start(
                "one",
                [live_source(target)],
                10,
                LiteralFilter(include=("STRASSE",), case_sensitive=False),
            )
            await until(lambda: engine.snapshot("one")["counters"]["received"] == 3)
            assert raced
            assert len(state.passwords) == 1
            first_ids = {event["event_id"] for event in engine.snapshot("one")["events"]}
            result = await engine.refilter("one", LiteralFilter())
            assert len(result["events"]) == 3
            assert first_ids <= {event["event_id"] for event in result["events"]}
            assert result["events"][1]["raw_line"].endswith("café")
            ranges = sorted(
                (event["source"]["byte_start"], event["source"]["byte_end"])
                for event in result["events"]
            )
            assert ranges[0][0] == 0
            assert all(
                first[1] == second[0] for first, second in zip(ranges, ranges[1:], strict=False)
            )
            assert ranges[-1][1] == path.stat().st_size
            assert len(state.passwords) == 1
            assert not state.commands and not state.writes
            assert all(flags == asyncssh.FXF_READ for _, flags in state.opens)
        finally:
            await engine.close()


async def test_real_sftp_ten_sources_two_projects_five_each_no_lifetime_slot_deadlock(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    for index in range(10):
        (logs / f"{index}.log").write_bytes(line(f"seed {index}"))
    async with endpoint(tmp_path) as (target, state):
        engine = LiveEngine(LiveLimits(poll_seconds=0.05, merge_seconds=0.02))
        try:
            async with asyncio.timeout(10):
                await asyncio.gather(
                    *(
                        engine.start(
                            f"page-{project}",
                            [
                                live_source(
                                    target,
                                    project_id=f"project-{project}",
                                    process_id=f"process-{index}",
                                    remote_path=f"/logs/{project * 5 + index}.log",
                                )
                                for index in range(5)
                            ],
                            20,
                        )
                        for project in range(2)
                    )
                )
            assert len(engine.collectors) == 10
            assert len(state.passwords) == 2
            with (logs / "0.log").open("ab") as stream:
                stream.write(line("project-a", 1))
            await until(lambda: engine.snapshot("page-0")["counters"]["received"] == 6)
            assert engine.snapshot("page-1")["counters"]["received"] == 5
            await engine.stop("page-0")
            assert len(engine.collectors) == 5
            with (logs / "5.log").open("ab") as stream:
                stream.write(line("project-b", 2))
            await until(lambda: engine.snapshot("page-1")["counters"]["received"] == 6)
            assert not state.commands and not state.writes
        finally:
            await engine.close()


async def test_real_sftp_five_low_rate_sources_p95_and_idle_does_not_block(
    tmp_path, record_property
):
    logs = tmp_path / "logs"
    logs.mkdir()
    for index in range(5):
        (logs / f"{index}.log").write_bytes(b"")
    async with endpoint(tmp_path) as (target, state):
        engine = LiveEngine()  # Production 750ms polling + 500ms merge wait.
        latencies = []
        try:
            await engine.start(
                "one",
                [
                    live_source(target, process_id=str(index), remote_path=f"/logs/{index}.log")
                    for index in range(5)
                ],
                20,
            )
            # Source four stays idle throughout; it cannot hold a watermark.
            for round_number in range(3):
                began = time.monotonic()
                pending = set()
                for index in range(4):
                    message = f"sample-{round_number}-{index}"
                    pending.add(message)
                    with (logs / f"{index}.log").open("ab") as stream:
                        stream.write(line(message, round_number))
                async with asyncio.timeout(3):
                    while pending:
                        frames = engine.sessions["one"].replay
                        visible = {
                            event["raw_line"].split(" ", 1)[1]
                            for frame in frames
                            if frame["type"] == "events"
                            for event in frame["payload"]["events"]
                        }
                        found = pending & visible
                        latencies.extend([time.monotonic() - began] * len(found))
                        pending -= found
                        if pending:
                            await asyncio.sleep(0.01)
            p95 = sorted(latencies)[math.ceil(len(latencies) * 0.95) - 1]
            record_property("healthy_line_to_engine_publish_p95_seconds", round(p95, 4))
            assert p95 <= 2.0, f"Measured real SFTP p95 {p95:.4f}s exceeds 2 seconds"
            assert engine.snapshot("one")["sources"][4]["received"] == 0
            assert not state.commands and not state.writes
        finally:
            await engine.close()


async def test_real_sftp_disconnect_proven_cursor_recovery(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    path = logs / "app.log"
    path.write_bytes(line("before"))
    async with endpoint(tmp_path) as (target, state):
        engine = LiveEngine(
            LiveLimits(poll_seconds=0.02, merge_seconds=0.02, reconnect_max_seconds=0.02)
        )
        try:
            await engine.start("one", [live_source(target)], 20)
            generation = engine.snapshot("one")["sources"][0]["source_revision_id"]
            for connection in tuple(state.connections):
                connection.abort()
            with path.open("ab") as stream:
                stream.write(line("during interruption", 1))
            await until(lambda: engine.snapshot("one")["counters"]["received"] == 2, 5)
            result = engine.snapshot("one")
            assert result["sources"][0]["source_revision_id"] == generation
            assert result["sources"][0]["gaps"] >= 1
            assert result["sources"][0]["reconnects"] >= 1
            assert len(state.passwords) >= 2
        finally:
            await engine.close()


async def test_real_sftp_observed_copytruncate_has_new_generation_and_gap(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    path = logs / "app.log"
    path.write_bytes(line("initial generation with a longer physical record"))
    async with endpoint(tmp_path) as (target, state):
        engine = LiveEngine(LiveLimits(poll_seconds=0.02, merge_seconds=0.02))
        try:
            await engine.start("one", [live_source(target)], 20)
            generation = engine.snapshot("one")["sources"][0]["source_revision_id"]
            path.write_bytes(line("new", 1))
            await until(lambda: engine.snapshot("one")["counters"]["received"] == 2)
            result = engine.snapshot("one")
            assert result["sources"][0]["source_revision_id"] != generation
            assert "COPYTRUNCATE_OR_REWRITE" in result["sources"][0]["warnings"]
            assert result["sources"][0]["gaps"] == 1
            assert len(state.passwords) == 1
            assert not state.commands and not state.writes
        finally:
            await engine.close()


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows prohibits renaming the synthetic server's ordinary pinned file handle; verified on the Linux runner.",
)
async def test_real_sftp_rename_drains_pinned_old_object_then_new_generation(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    path = logs / "app.log"
    path.write_bytes(line("initial"))
    async with endpoint(tmp_path) as (target, state):
        engine = LiveEngine(LiveLimits(poll_seconds=0.05, merge_seconds=0.02))
        try:
            await engine.start("one", [live_source(target)], 20)
            generation = engine.snapshot("one")["sources"][0]["source_revision_id"]
            rotation = logs / "app.log.1"
            path.rename(rotation)
            with rotation.open("ab") as stream:
                stream.write(line("drained old handle", 1))
            path.write_bytes(line("new active", 2))
            await until(lambda: engine.snapshot("one")["counters"]["received"] == 3)
            result = engine.snapshot("one")
            assert [event["raw_line"].split(" ", 1)[1] for event in result["events"]] == [
                "initial",
                "drained old handle",
                "new active",
            ]
            assert result["events"][1]["source"]["source_revision_id"] == generation
            assert result["events"][2]["source"]["source_revision_id"] != generation
            assert "RENAME_ROTATION_OBSERVED" in result["sources"][0]["warnings"]
            assert len(state.passwords) == 1
            assert not state.commands and not state.writes
        finally:
            await engine.close()


async def test_real_sftp_reconnect_changed_host_key_blocks_before_new_password(
    tmp_path, monkeypatch
):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "app.log").write_bytes(line("initial"))
    async with endpoint(tmp_path) as (target, state):
        engine = LiveEngine(
            LiveLimits(poll_seconds=0.02, merge_seconds=0.02, reconnect_max_seconds=0.02)
        )
        try:
            await engine.start("one", [live_source(target)], 20)
            original = ssh_transport._authenticate
            other_key = asyncssh.generate_private_key("ssh-ed25519")

            async def changed(endpoint_, address, approved_key, jump):
                # Reconnect still reaches the same synthetic server, now using
                # an incompatible pinned approval; key verification must reject
                # before a new password-authentication exchange.
                return await original(endpoint_, address, other_key, jump)

            monkeypatch.setattr(ssh_transport, "_authenticate", changed)
            for connection in tuple(state.connections):
                connection.abort()
            await until(lambda: engine.snapshot("one")["sources"][0]["state"] == "blocked", 5)
            result = engine.snapshot("one")
            assert result["sources"][0]["error"] == "HOST_KEY_CHANGED"
            assert len(state.passwords) == 1
            assert result["sources"][0]["reconnects"] == 1
        finally:
            await engine.close()


@pytest.mark.parametrize("failure", ["unknown", "changed", "password"])
async def test_real_sftp_nonretryable_trust_and_credential_failures(tmp_path, failure):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "app.log").write_bytes(line("private"))
    async with endpoint(tmp_path) as (target, state):
        if failure == "unknown":
            target = replace(target, host_key=None)
        elif failure == "changed":
            target = replace(
                target,
                host_key=asyncssh.generate_private_key("ssh-ed25519")
                .export_public_key()
                .decode()
                .strip(),
            )
        else:
            target = replace(target, password="invalid")
        engine = LiveEngine(LiveLimits(poll_seconds=0.02, merge_seconds=0.02))
        try:
            result = await engine.start("one", [live_source(target)], 20)
            assert result["sources"][0]["state"] == "blocked"
            assert not result["events"]
            assert not state.opens
            assert len(state.passwords) == (1 if failure == "password" else 0)
            await asyncio.sleep(0.06)
            assert len(state.passwords) == (1 if failure == "password" else 0)
        finally:
            await engine.close()
