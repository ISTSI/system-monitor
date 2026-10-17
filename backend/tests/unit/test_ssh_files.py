"""Real loopback AsyncSSH/SFTP proves bounded planning and immutable retrieval."""

import asyncio
import hashlib
import io
import os
import stat
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field, replace

import asyncssh
import pytest

from inspector.errors import DomainError
from inspector.ssh_files import RemoteFile, open_files
from inspector.ssh_transport import Endpoint


@dataclass
class State:
    connections: set = field(default_factory=set)
    passwords: list = field(default_factory=list)
    commands: list = field(default_factory=list)
    opens: list = field(default_factory=list)
    writes: list = field(default_factory=list)
    reads: list = field(default_factory=list)
    directories: list = field(default_factory=list)
    allowed_forward: tuple[str, int] | None = None
    read_hook: Callable | None = None
    open_hook: Callable | None = None
    denied: set[bytes] = field(default_factory=set)
    named_replacements: dict = field(default_factory=dict)
    reported_symlinks: set[bytes] = field(default_factory=set)
    closed: asyncio.Event = field(default_factory=asyncio.Event)


class Server(asyncssh.SSHServer):
    def __init__(self, state):
        self.state = state

    def connection_made(self, connection):
        self.connection = connection
        self.state.connections.add(connection)
        self.state.closed.clear()

    def connection_lost(self, exc):
        self.state.connections.discard(self.connection)
        if not self.state.connections:
            self.state.closed.set()

    def begin_auth(self, username):
        return True

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        self.state.passwords.append((username, password))
        return username == "fixture-reader" and password == "fixture-password"

    def connection_requested(self, host, port, orig_host, orig_port):
        return (host, port) == self.state.allowed_forward


class ReadOnlySFTP(asyncssh.SFTPServer):
    def __init__(self, channel, root, state):
        super().__init__(channel, chroot=str(root))
        self.state = state

    def lstat(self, path):
        if path in self.state.denied:
            raise asyncssh.SFTPPermissionDenied("private diagnostic must not escape")
        if path in self.state.named_replacements:
            return self.state.named_replacements[path].stat()
        if path in self.state.reported_symlinks:
            return asyncssh.SFTPAttrs(
                type=asyncssh.FILEXFER_TYPE_SYMLINK,
                permissions=stat.S_IFLNK | 0o777,
                size=1,
            )
        return super().lstat(path)

    def open(self, path, pflags, attrs):
        self.state.opens.append((path, pflags))
        if pflags != asyncssh.FXF_READ:
            self.state.writes.append((path, pflags))
            raise asyncssh.SFTPPermissionDenied("write flags forbidden")
        if path in self.state.denied:
            raise asyncssh.SFTPPermissionDenied("private diagnostic must not escape")
        if self.state.open_hook:
            self.state.open_hook()
        return super().open(path, pflags, attrs)

    async def read(self, file_obj, offset, size):
        self.state.reads.append((offset, size))
        if self.state.read_hook:
            await self.state.read_hook(file_obj, offset, size)
        return super().read(file_obj, offset, size)

    async def scandir(self, path):
        self.state.directories.append(path)
        async for entry in super().scandir(path):
            yield entry

    def setstat(self, path, attrs):
        self.state.writes.append("setstat")
        raise asyncssh.SFTPPermissionDenied("writes forbidden")

    def remove(self, path):
        self.state.writes.append("remove")
        raise asyncssh.SFTPPermissionDenied("writes forbidden")

    def rename(self, oldpath, newpath):
        self.state.writes.append("rename")
        raise asyncssh.SFTPPermissionDenied("writes forbidden")

    def mkdir(self, path, attrs):
        self.state.writes.append("mkdir")
        raise asyncssh.SFTPPermissionDenied("writes forbidden")


@asynccontextmanager
async def endpoint(root, *, allowed_forward=None):
    state = State(allowed_forward=allowed_forward)
    key = asyncssh.generate_private_key("ssh-ed25519")

    async def reject_exec(process):
        state.commands.append(process.command)
        process.exit(126)

    listener = await asyncssh.listen(
        "127.0.0.1",
        0,
        server_factory=lambda: Server(state),
        server_host_keys=[key],
        process_factory=reject_exec,
        sftp_factory=lambda channel: ReadOnlySFTP(channel, root, state),
        config=[],
    )
    target = Endpoint(
        "127.0.0.1",
        listener.get_port(),
        "fixture-reader",
        "fixture-password",
        key.export_public_key().decode().strip(),
    )
    try:
        yield target, state
    finally:
        listener.close()
        await listener.wait_closed()
        connections = tuple(state.connections)
        for connection in connections:
            connection.abort()
        await asyncio.gather(*(connection.wait_closed() for connection in connections))


def source(**changes):
    return {
        "active_path": "/logs/app.log",
        "rotated_patterns": [],
        "archives": [],
        "allow_symlink": False,
        **changes,
    }


@pytest.fixture
def logs(tmp_path):
    directory = tmp_path / "logs"
    directory.mkdir()
    (directory / "app.log").write_bytes(b"2026-10-16T12:00:00Z active\n")
    return directory


async def closed(*states):
    async with asyncio.timeout(2):
        await asyncio.gather(*(state.closed.wait() for state in states if state.connections))


async def test_jump_plans_active_rotated_archives_and_copies_using_one_read_only_route(
    tmp_path, logs
):
    (logs / "app.log.1").write_bytes(b"rotated\n")
    (logs / "app-2026.zip").write_bytes(b"archive bytes are validated by archive reader")
    (logs / "app-2026.tar.gz").write_bytes(b"archive bytes are validated by archive reader")
    definition = source(
        rotated_patterns=["/logs/app.log.*"],
        archives=[
            {"path_pattern": "/logs/app-*.zip", "member_patterns": ["app.log", "old/*.log"]},
            {"path_pattern": "/logs/app-*.tar.gz", "member_patterns": ["app.log"]},
        ],
    )
    async with endpoint(tmp_path) as (target, target_state):
        async with endpoint(tmp_path, allowed_forward=(target.host, target.port)) as (
            jump,
            jump_state,
        ):
            async with open_files(target, jump, allow_loopback=True) as remote:
                candidates = await remote.plan(definition, ["/logs"])
                assert [item.kind for item in candidates] == ["tar.gz", "zip", "plain", "plain"]
                assert candidates[1].member_patterns == ("app.log", "old/*.log")
                for candidate in candidates:
                    restored = RemoteFile(**asdict(candidate))
                    destination = io.BytesIO()
                    result = await remote.copy(restored, destination, max_bytes=1000)
                    expected = (tmp_path / candidate.path.lstrip("/")).read_bytes()
                    assert destination.getvalue() == expected
                    assert result.bytes == len(expected)
                    assert result.checksum == hashlib.sha256(expected).hexdigest()
                    assert result.fingerprint == candidate.fingerprint
                    assert not result.snapshot_changed
            assert len(target_state.passwords) == len(jump_state.passwords) == 1
            assert target_state.commands == jump_state.commands == []
            assert target_state.writes == jump_state.writes == []
            assert all(flags == asyncssh.FXF_READ for _, flags in target_state.opens)
            assert jump_state.opens == []
            await closed(target_state, jump_state)


async def test_same_snapshot_fingerprint_stable_across_connections(tmp_path, logs):
    async with endpoint(tmp_path) as (target, state):
        snapshots = []
        for _ in range(2):
            async with open_files(target, allow_loopback=True) as remote:
                candidate = (await remote.plan(source(), ["/logs"]))[0]
                snapshots.append(candidate)
                await remote.check(candidate)
        assert snapshots[0] == snapshots[1]
        assert len(state.passwords) == 2
        await closed(state)


async def test_generic_archive_pattern_resolves_each_supported_file_type(tmp_path, logs):
    (logs / "archives").mkdir()
    (logs / "archives/log.zip").write_bytes(b"ZIP archive")
    (logs / "archives/log.tgz").write_bytes(b"TAR.GZ archive")
    async with endpoint(tmp_path) as (target, _):
        async with open_files(target, allow_loopback=True) as remote:
            candidates = await remote.plan(
                source(
                    archives=[{"path_pattern": "/logs/archives/*", "member_patterns": ["*.log"]}]
                ),
                ["/logs"],
            )
            assert {item.kind for item in candidates} == {"plain", "zip", "tar.gz"}


async def test_directory_glob_only_traverses_matching_directories(tmp_path, logs):
    (logs / "old").mkdir()
    (logs / "old/app.log").write_bytes(b"configured archived plain history")
    async with endpoint(tmp_path) as (target, _):
        async with open_files(target, allow_loopback=True) as remote:
            candidates = await remote.plan(source(rotated_patterns=["/logs/*/app.log"]), ["/logs"])
            assert [item.path for item in candidates] == ["/logs/app.log", "/logs/old/app.log"]


@pytest.mark.parametrize(
    "path",
    [
        "/logs/../private",
        "/logs/./app.log",
        "/logs//app.log",
        "/logs/$HOME",
        "/logs/`id`",
        "/logs/app\n.log",
        "/logs/*.log",
        "logs/app.log",
    ],
)
async def test_unsafe_active_paths_fail_without_opening_files(tmp_path, logs, path):
    async with endpoint(tmp_path) as (target, state):
        async with open_files(target, allow_loopback=True) as remote:
            with pytest.raises(DomainError) as failure:
                await remote.plan(source(active_path=path), ["/logs"])
            assert failure.value.code == "SOURCE_PATH_INVALID"
        assert state.opens == state.commands == state.writes == []


async def test_outside_root_and_prefix_collision_fail_without_listing(tmp_path, logs):
    async with endpoint(tmp_path) as (target, state):
        async with open_files(target, allow_loopback=True) as remote:
            with pytest.raises(DomainError) as failure:
                await remote.plan(source(active_path="/logs-other/app.log"), ["/logs"])
            assert failure.value.code == "SOURCE_ROOT_DENIED"
            assert state.opens == state.directories == []


async def test_inaccessible_path_error_is_distinct_and_sanitized(tmp_path, logs):
    async with endpoint(tmp_path) as (target, state):
        state.denied.add(b"/logs/app.log")
        async with open_files(target, allow_loopback=True) as remote:
            with pytest.raises(DomainError) as failure:
                await remote.plan(source(), ["/logs"])
            assert failure.value.code == "SOURCE_PERMISSION_DENIED"
            assert "private diagnostic" not in str(failure.value)


async def test_missing_active_file_does_not_omit_available_configured_history(tmp_path, logs):
    (logs / "app.log").unlink()
    (logs / "app.log.1").write_bytes(b"old history")
    async with endpoint(tmp_path) as (target, _):
        async with open_files(target, allow_loopback=True) as remote:
            candidates = await remote.plan(source(rotated_patterns=["/logs/app.log.*"]), ["/logs"])
            assert [item.path for item in candidates] == ["/logs/app.log.1"]
            assert remote.warnings == ["ACTIVE_SOURCE_UNAVAILABLE"]


async def test_no_available_source_fails_clearly(tmp_path, logs):
    (logs / "app.log").unlink()
    async with endpoint(tmp_path) as (target, _):
        async with open_files(target, allow_loopback=True) as remote:
            with pytest.raises(DomainError) as failure:
                await remote.plan(source(), ["/logs"])
            assert failure.value.code == "SOURCE_NOT_FOUND"


@pytest.mark.parametrize(
    "limits,code",
    [
        ({"max_candidates": 1}, "SOURCE_CANDIDATE_LIMIT"),
        ({"max_listing_entries": 1}, "SOURCE_LISTING_LIMIT"),
        ({"max_listing_bytes": 1}, "SOURCE_LISTING_LIMIT"),
        ({"max_estimated_bytes": 1}, "DOWNLOAD_LIMIT"),
        ({"max_probe_bytes": 1}, "SOURCE_PROBE_LIMIT"),
    ],
)
async def test_candidate_listing_and_byte_limits_are_explicit(tmp_path, logs, limits, code):
    (logs / "app.log.1").write_bytes(b"old history")
    async with endpoint(tmp_path) as (target, state):
        async with open_files(target, allow_loopback=True, **limits) as remote:
            with pytest.raises(DomainError) as failure:
                await remote.plan(source(rotated_patterns=["/logs/app.log.*"]), ["/logs"])
            assert failure.value.code == code
        assert state.writes == state.commands == []


async def test_download_budget_rejects_before_any_capture_write(tmp_path, logs):
    async with endpoint(tmp_path) as (target, _):
        async with open_files(target, allow_loopback=True) as remote:
            candidate = (await remote.plan(source(), ["/logs"]))[0]
            destination = io.BytesIO()
            with pytest.raises(DomainError) as failure:
                await remote.copy(candidate, destination, max_bytes=candidate.estimated_bytes - 1)
            assert failure.value.code == "DOWNLOAD_LIMIT"
            assert destination.getvalue() == b""


async def test_changed_snapshot_between_preview_and_download_is_rejected(tmp_path, logs):
    async with endpoint(tmp_path) as (target, _):
        async with open_files(target, allow_loopback=True) as remote:
            candidate = (await remote.plan(source(), ["/logs"]))[0]
            original = (logs / "app.log").stat()
            (logs / "app.log").write_bytes(b"X" * candidate.estimated_bytes)
            os.utime(logs / "app.log", ns=(original.st_atime_ns, original.st_mtime_ns))
            destination = io.BytesIO()
            with pytest.raises(DomainError) as failure:
                await remote.copy(candidate, destination, max_bytes=1000)
            assert failure.value.code == "SOURCE_CHANGED"
            assert destination.getvalue() == b""


@pytest.mark.parametrize("stage", ["open", "planning", "between", "check", "copy"])
@pytest.mark.parametrize("size", [37, 20_000, 200_000])
async def test_active_appends_preserve_planned_prefix_and_budget(tmp_path, logs, stage, size):
    path = logs / "app.log"
    original = b"A" * size  # Also retain an unterminated physical line exactly.
    path.write_bytes(original)
    appended = 0

    def append():
        nonlocal appended
        with path.open("ab") as stream:
            stream.write(b"\nnew log entry\n")
        appended += 1

    async def append_on_read(file_obj, offset, length):
        append()

    async with endpoint(tmp_path) as (target, state):
        async with open_files(target, allow_loopback=True, max_estimated_bytes=size) as remote:
            if stage == "open":
                state.open_hook = append
            elif stage == "planning":
                state.read_hook = append_on_read
            candidate = (await remote.plan(source(), ["/logs"]))[0]
            state.open_hook = state.read_hook = None
            assert candidate.estimated_bytes == candidate.metadata["size"] == size
            assert remote.estimated_bytes == size
        # Reopen the route as collection does after planning. Serialized plan
        # metadata must retain its boundary even when the remote EOF has grown.
        candidate = RemoteFile(**asdict(candidate))
        async with open_files(target, allow_loopback=True) as remote:
            if stage == "between":
                append()
            elif stage == "check":
                state.read_hook = append_on_read
            await remote.check(candidate)
            state.read_hook = append_on_read if stage == "copy" else None
            destination = io.BytesIO()
            result = await remote.copy(candidate, destination, max_bytes=size)
            assert appended > 0
            assert destination.getvalue() == original
            assert result.bytes == size
            assert result.checksum == hashlib.sha256(original).hexdigest()
            assert result.fingerprint == candidate.fingerprint
            assert not result.snapshot_changed
            assert path.stat().st_size > size
            assert state.commands == state.writes == []
            assert all(flags == asyncssh.FXF_READ for _, flags in state.opens)


async def test_empty_active_snapshot_excludes_later_entries(tmp_path, logs):
    path = logs / "app.log"
    path.write_bytes(b"")
    async with endpoint(tmp_path) as (target, _):
        async with open_files(target, allow_loopback=True) as remote:
            candidate = (await remote.plan(source(), ["/logs"]))[0]
            path.write_bytes(b"first entry\n")
            await remote.check(candidate)
            destination = io.BytesIO()
            result = await remote.copy(candidate, destination, max_bytes=0)
            assert destination.getvalue() == b""
            assert result.bytes == 0 and result.checksum == hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize("offset", [0, 199_999])
@pytest.mark.parametrize("stage", ["before", "during"])
async def test_growth_does_not_hide_changed_captured_prefix(tmp_path, logs, offset, stage):
    path = logs / "app.log"
    path.write_bytes(b"A" * 200_000)
    async with endpoint(tmp_path) as (target, state):
        async with open_files(target, allow_loopback=True) as remote:
            candidate = (await remote.plan(source(), ["/logs"]))[0]

            def mutate():
                with path.open("ab") as stream:
                    stream.write(b"appended\n")
                with path.open("r+b") as stream:
                    stream.seek(offset)
                    stream.write(b"B")

            async def mutate_on_read(file_obj, offset, size):
                if size > 4096:
                    state.read_hook = None
                    mutate()

            if stage == "before":
                mutate()
            else:
                state.read_hook = mutate_on_read
            with pytest.raises(DomainError) as failure:
                await remote.copy(candidate, io.BytesIO(), max_bytes=200_000)
            assert failure.value.code == "SOURCE_CHANGED"


async def test_equal_size_metadata_change_outside_probes_is_rejected(tmp_path, logs):
    path = logs / "app.log"
    path.write_bytes(b"A" * 20_000)
    async with endpoint(tmp_path) as (target, _):
        async with open_files(target, allow_loopback=True) as remote:
            candidate = (await remote.plan(source(), ["/logs"]))[0]
            original = path.stat()
            with path.open("r+b") as stream:
                stream.seek(10_000)
                stream.write(b"B")
            os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns + 2_000_000_000))
            with pytest.raises(DomainError) as failure:
                await remote.check(candidate)
            assert failure.value.code == "SOURCE_CHANGED"


async def test_named_replacement_cannot_shrink_after_observed_growth(tmp_path, logs):
    path = logs / "app.log"
    path.write_bytes(b"A" * 200_000)
    async with endpoint(tmp_path) as (target, state):
        async with open_files(target, allow_loopback=True) as remote:
            candidate = (await remote.plan(source(), ["/logs"]))[0]
            with path.open("ab") as stream:
                stream.write(b"A" * 100_000)

            async def replace_after_growth(file_obj, offset, size):
                if size > 4096:
                    state.read_hook = None
                    replacement = logs / "replacement"
                    replacement.write_bytes(b"A" * 250_000)
                    if os.name == "nt":
                        state.named_replacements[b"/logs/app.log"] = replacement
                    else:
                        replacement.replace(path)

            state.read_hook = replace_after_growth
            with pytest.raises(DomainError) as failure:
                await remote.copy(candidate, io.BytesIO(), max_bytes=200_000)
            assert failure.value.code == "SOURCE_CHANGED"


@pytest.mark.parametrize("kind", ["plain", "zip", "tar.gz"])
@pytest.mark.parametrize("stage", ["planning", "between", "copy"])
async def test_appends_to_immutable_history_remain_rejected(tmp_path, logs, kind, stage):
    path = logs / {"plain": "old.log", "zip": "old.zip", "tar.gz": "old.tar.gz"}[kind]
    path.write_bytes(b"A" * 20_000)
    definition = source(
        rotated_patterns=["/logs/old.log"] if kind == "plain" else [],
        archives=[]
        if kind == "plain"
        else [{"path_pattern": "/logs/" + path.name, "member_patterns": ["*.log"]}],
    )
    async with endpoint(tmp_path) as (target, state):
        async with open_files(target, allow_loopback=True) as remote:

            async def append(file_obj, offset, size):
                if b"old." in os.fsencode(file_obj.name):
                    state.read_hook = None
                    with path.open("ab") as stream:
                        stream.write(b"changed")

            if stage == "planning":
                state.read_hook = append
                with pytest.raises(DomainError) as failure:
                    await remote.plan(definition, ["/logs"])
            else:
                candidate = next(
                    entry
                    for entry in await remote.plan(definition, ["/logs"])
                    if entry.kind == kind and not entry.active
                )
                if stage == "between":
                    with path.open("ab") as stream:
                        stream.write(b"changed")
                    with pytest.raises(DomainError) as failure:
                        await remote.check(candidate)
                else:
                    state.read_hook = append
                    with pytest.raises(DomainError) as failure:
                        await remote.copy(candidate, io.BytesIO(), max_bytes=30_000)
            assert failure.value.code == "SOURCE_CHANGED"


@pytest.mark.parametrize("change", ["truncate", "replace"])
async def test_changed_active_file_during_download_is_reported(tmp_path, logs, change):
    (logs / "app.log").write_bytes(b"A" * 200_000)
    async with endpoint(tmp_path) as (target, state):
        async with open_files(target, allow_loopback=True) as remote:
            candidate = (await remote.plan(source(), ["/logs"]))[0]

            async def mutate(file_obj, offset, size):
                if size > 4096:
                    state.read_hook = None
                    if change == "truncate":
                        with (logs / "app.log").open("r+b") as stream:
                            stream.truncate(100)
                    else:
                        replacement = logs / "replacement"
                        replacement.write_bytes(b"B" * 200_001)
                        if os.name == "nt":
                            # Windows denies replacing an open Python file.
                            # Expose the new named file's actual stat through
                            # SFTP while the read handle remains on the old file,
                            # matching POSIX rename semantics on the Linux target.
                            state.named_replacements[b"/logs/app.log"] = replacement
                        else:
                            replacement.replace(logs / "app.log")

            state.read_hook = mutate
            with pytest.raises(DomainError) as failure:
                await remote.copy(candidate, io.BytesIO(), max_bytes=300_000)
            assert failure.value.code == "SOURCE_CHANGED"


async def test_cancelling_read_closes_target_jump_and_file_handle(tmp_path, logs):
    (logs / "app.log").write_bytes(b"A" * 200_000)
    ready, release = asyncio.Event(), asyncio.Event()
    async with endpoint(tmp_path) as (target, target_state):
        async with endpoint(tmp_path, allowed_forward=(target.host, target.port)) as (
            jump,
            jump_state,
        ):

            async def blocked_read(file_obj, offset, size):
                if size > 4096:
                    ready.set()
                    await release.wait()

            async def run():
                async with open_files(target, jump, allow_loopback=True) as remote:
                    candidate = (await remote.plan(source(), ["/logs"]))[0]
                    target_state.read_hook = blocked_read
                    await remote.copy(candidate, io.BytesIO(), max_bytes=300_000)

            task = asyncio.create_task(run())
            await asyncio.wait_for(ready.wait(), timeout=3)
            cancelled_at = time.monotonic()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            release.set()
            await closed(target_state, jump_state)
            assert time.monotonic() - cancelled_at < 2
            assert target_state.writes == jump_state.writes == []
            assert target_state.commands == jump_state.commands == []


async def test_operation_deadline_bounds_stalled_reads_and_closes_route(tmp_path, logs):
    ready, release = asyncio.Event(), asyncio.Event()
    async with endpoint(tmp_path) as (target, state):

        async def blocked_read(file_obj, offset, size):
            ready.set()
            await release.wait()

        state.read_hook = blocked_read
        with pytest.raises(DomainError) as failure:
            async with open_files(target, allow_loopback=True, timeout_seconds=0.2) as remote:
                await remote.plan(source(), ["/logs"])
        assert failure.value.code == "SSH_TIMEOUT"
        assert ready.is_set()
        release.set()
        await closed(state)


async def test_directory_is_not_a_regular_log(tmp_path, logs):
    async with endpoint(tmp_path) as (target, _):
        async with open_files(target, allow_loopback=True) as remote:
            with pytest.raises(DomainError) as failure:
                await remote.plan(source(active_path="/logs"), ["/logs"])
            assert failure.value.code == "SOURCE_NOT_REGULAR"


async def test_symlink_and_symlink_directory_are_denied(tmp_path, logs):
    try:
        (logs / "linked.log").symlink_to(logs / "app.log")
        (tmp_path / "linked-directory").symlink_to(logs, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"OS does not permit creating synthetic symlinks: {error}")
    async with endpoint(tmp_path) as (target, _):
        for path, root in [
            ("/logs/linked.log", "/logs"),
            ("/linked-directory/app.log", "/linked-directory"),
        ]:
            async with open_files(target, allow_loopback=True) as remote:
                with pytest.raises(DomainError) as failure:
                    await remote.plan(source(active_path=path), [root])
                assert failure.value.code == "SOURCE_SYMLINK_DENIED"


@pytest.mark.parametrize("link", [b"/logs", b"/logs/app.log"])
async def test_sftp_reported_symlinks_are_denied_without_open(tmp_path, logs, link):
    async with endpoint(tmp_path) as (target, state):
        state.reported_symlinks.add(link)
        async with open_files(target, allow_loopback=True) as remote:
            with pytest.raises(DomainError) as failure:
                await remote.plan(source(), ["/logs"])
            assert failure.value.code == "SOURCE_SYMLINK_DENIED"
            assert state.opens == []


async def test_unknown_key_and_expired_password_cannot_begin_file_planning(tmp_path, logs):
    async with endpoint(tmp_path) as (target, state):
        for changed, code in [
            (replace(target, host_key=None), "HOST_KEY_REQUIRED"),
            (replace(target, password="expired"), "SSH_AUTH_FAILED"),
        ]:
            with pytest.raises(DomainError) as failure:
                async with open_files(changed, allow_loopback=True):
                    pytest.fail("Invalid access must not yield an SFTP client")
            assert failure.value.code == code
        assert state.opens == state.directories == state.commands == []
