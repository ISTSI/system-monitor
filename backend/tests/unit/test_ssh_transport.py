"""Real ephemeral SSH servers prove trust ordering and the SFTP-only surface."""

import asyncio
import socket
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace

import asyncssh
import pytest

from inspector import ssh_transport
from inspector.errors import DomainError
from inspector.ssh_transport import Endpoint, inspect_key
from inspector.ssh_transport import test_connection as check_connection


@dataclass
class ServerState:
    password_attempts: list[tuple[str, str]] = field(default_factory=list)
    authentication_requests: list[str] = field(default_factory=list)
    commands: list[str | None] = field(default_factory=list)
    file_operations: list[str] = field(default_factory=list)
    forwards: list[tuple[str, int]] = field(default_factory=list)
    connections: set[asyncssh.SSHServerConnection] = field(default_factory=set)
    allowed_forward: tuple[str, int] | None = None
    closed: asyncio.Event = field(default_factory=asyncio.Event)


class SyntheticServer(asyncssh.SSHServer):
    def __init__(self, state):
        self.state = state

    def connection_made(self, connection):
        self.connection = connection
        self.state.closed.clear()
        self.state.connections.add(connection)

    def connection_lost(self, exc):
        self.state.connections.discard(self.connection)
        if not self.state.connections:
            self.state.closed.set()

    def begin_auth(self, username):
        self.state.authentication_requests.append(username)
        return True

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        self.state.password_attempts.append((username, password))
        return username == "synthetic-reader" and password == "synthetic-password"

    def connection_requested(self, dest_host, dest_port, orig_host, orig_port):
        self.state.forwards.append((dest_host, dest_port))
        return (dest_host, dest_port) == self.state.allowed_forward


class ReadOnlySyntheticSFTP(asyncssh.SFTPServer):
    def __init__(self, channel, state, root):
        super().__init__(channel, chroot=str(root))
        self.state = state

    def open(self, path, pflags, attrs):
        self.state.file_operations.append("open")
        raise asyncssh.SFTPPermissionDenied("Synthetic server denies all file operations")

    def setstat(self, path, attrs):
        self.state.file_operations.append("setstat")
        raise asyncssh.SFTPPermissionDenied("Synthetic server denies all file operations")

    def mkdir(self, path, attrs):
        self.state.file_operations.append("mkdir")
        raise asyncssh.SFTPPermissionDenied("Synthetic server denies all file operations")

    def remove(self, path):
        self.state.file_operations.append("remove")
        raise asyncssh.SFTPPermissionDenied("Synthetic server denies all file operations")

    def rename(self, oldpath, newpath):
        self.state.file_operations.append("rename")
        raise asyncssh.SFTPPermissionDenied("Synthetic server denies all file operations")


@asynccontextmanager
async def synthetic_server(tmp_path, *, sftp=True, allowed_forward=None, sftp_barrier=None):
    state = ServerState(allowed_forward=allowed_forward)
    key = asyncssh.generate_private_key("ssh-ed25519")

    async def reject_command(process):
        state.commands.append(process.command)
        process.exit(126)

    async def make_sftp(channel):
        if sftp_barrier:
            ready, release = sftp_barrier
            ready.set()
            await release.wait()
        return ReadOnlySyntheticSFTP(channel, state, tmp_path)

    listener = await asyncssh.listen(
        "127.0.0.1",
        0,
        server_factory=lambda: SyntheticServer(state),
        server_host_keys=[key],
        process_factory=reject_command,
        sftp_factory=make_sftp if sftp else None,
        config=[],
        login_timeout=5,
    )
    endpoint = Endpoint(
        host="127.0.0.1",
        port=listener.get_port(),
        username="synthetic-reader",
        password="synthetic-password",
        host_key=key.export_public_key("openssh").decode().strip(),
    )
    try:
        yield endpoint, state, key
    finally:
        if sftp_barrier:
            sftp_barrier[1].set()
        listener.close()
        await listener.wait_closed()
        for connection in tuple(state.connections):
            connection.abort()
        if state.connections:
            await asyncio.gather(*(item.wait_closed() for item in tuple(state.connections)))


async def assert_closed(*states):
    async with asyncio.timeout(2):
        await asyncio.gather(*(state.closed.wait() for state in states if state.connections))


async def test_inspection_collects_fingerprint_without_any_target_authentication(tmp_path):
    async with synthetic_server(tmp_path) as (target, state, key):
        proposal = await inspect_key(replace(target, host_key=None), allow_loopback=True)
        assert proposal == {
            "public_key": target.host_key,
            "algorithm": "ssh-ed25519",
            "fingerprint": key.get_fingerprint("sha256"),
        }
        assert state.authentication_requests == []
        assert state.password_attempts == []
        assert state.commands == []
        assert state.file_operations == []
        await assert_closed(state)


async def test_direct_password_authentication_only_negotiates_sftp_and_closes(tmp_path):
    async with synthetic_server(tmp_path) as (target, state, _):
        assert await check_connection(target, allow_loopback=True) == {"ssh": True, "sftp": True}
        assert state.password_attempts == [(target.username, target.password)]
        assert state.commands == []
        assert state.file_operations == []
        assert state.forwards == []
        await assert_closed(state)


@pytest.mark.parametrize("changed", [False, True])
async def test_unapproved_and_changed_keys_fail_before_authentication(tmp_path, changed):
    async with synthetic_server(tmp_path) as (target, state, _):
        wrong_key = asyncssh.generate_private_key("ssh-ed25519").export_public_key().decode()
        target = replace(target, host_key=wrong_key if changed else None)
        with pytest.raises(DomainError) as failure:
            await check_connection(target, allow_loopback=True)
        assert failure.value.code == ("HOST_KEY_CHANGED" if changed else "HOST_KEY_REQUIRED")
        assert state.authentication_requests == []
        assert state.password_attempts == []
        await assert_closed(state)


async def test_wrong_password_is_sanitized_and_connection_closes(tmp_path):
    async with synthetic_server(tmp_path) as (target, state, _):
        with pytest.raises(DomainError) as failure:
            await check_connection(replace(target, password="rejected-secret"), allow_loopback=True)
        assert failure.value.code == "SSH_AUTH_FAILED"
        assert "rejected-secret" not in str(failure.value)
        assert target.host not in str(failure.value)
        await assert_closed(state)


async def test_real_jump_authenticates_both_pinned_hops_without_exec_or_files(tmp_path):
    async with synthetic_server(tmp_path) as (target, target_state, _):
        async with synthetic_server(tmp_path, allowed_forward=(target.host, target.port)) as (
            jump,
            jump_state,
            _,
        ):
            assert await check_connection(target, jump, allow_loopback=True) == {
                "ssh": True,
                "sftp": True,
            }
            assert target_state.password_attempts == [(target.username, target.password)]
            assert jump_state.password_attempts == [(jump.username, jump.password)]
            assert jump_state.forwards == [(target.host, target.port)]
            assert target_state.commands == jump_state.commands == []
            assert target_state.file_operations == jump_state.file_operations == []
            await assert_closed(target_state, jump_state)


async def test_inspection_through_jump_sends_credentials_only_to_pinned_jump(tmp_path):
    async with synthetic_server(tmp_path) as (target, target_state, _):
        async with synthetic_server(tmp_path, allowed_forward=(target.host, target.port)) as (
            jump,
            jump_state,
            _,
        ):
            proposal = await inspect_key(replace(target, host_key=None), jump, allow_loopback=True)
            assert proposal["public_key"] == target.host_key
            assert target_state.authentication_requests == []
            assert target_state.password_attempts == []
            assert jump_state.password_attempts == [(jump.username, jump.password)]
            await assert_closed(target_state, jump_state)


@pytest.mark.parametrize("changed", [False, True])
async def test_unapproved_or_changed_jump_blocks_both_passwords(tmp_path, changed):
    async with synthetic_server(tmp_path) as (target, target_state, _):
        async with synthetic_server(tmp_path, allowed_forward=(target.host, target.port)) as (
            jump,
            jump_state,
            _,
        ):
            wrong_key = asyncssh.generate_private_key("ssh-ed25519").export_public_key().decode()
            with pytest.raises(DomainError) as failure:
                await check_connection(
                    target,
                    replace(jump, host_key=wrong_key if changed else None),
                    allow_loopback=True,
                )
            assert failure.value.code == ("HOST_KEY_CHANGED" if changed else "HOST_KEY_REQUIRED")
            assert target_state.password_attempts == jump_state.password_attempts == []
            assert target_state.authentication_requests == jump_state.authentication_requests == []
            await assert_closed(target_state, jump_state)


async def test_unapproved_target_blocks_even_approved_jump_authentication(tmp_path):
    async with synthetic_server(tmp_path) as (target, target_state, _):
        async with synthetic_server(tmp_path, allowed_forward=(target.host, target.port)) as (
            jump,
            jump_state,
            _,
        ):
            with pytest.raises(DomainError) as failure:
                await check_connection(replace(target, host_key=None), jump, allow_loopback=True)
            assert failure.value.code == "HOST_KEY_REQUIRED"
            assert target_state.authentication_requests == jump_state.authentication_requests == []
            assert target_state.password_attempts == jump_state.password_attempts == []
            assert target_state.connections == jump_state.connections == set()


async def test_changed_target_behind_jump_is_rejected_before_target_auth(tmp_path):
    async with synthetic_server(tmp_path) as (target, target_state, _):
        async with synthetic_server(tmp_path, allowed_forward=(target.host, target.port)) as (
            jump,
            jump_state,
            _,
        ):
            wrong_key = asyncssh.generate_private_key("ssh-ed25519").export_public_key().decode()
            with pytest.raises(DomainError) as failure:
                await check_connection(
                    replace(target, host_key=wrong_key), jump, allow_loopback=True
                )
            assert failure.value.code == "HOST_KEY_CHANGED"
            assert target_state.authentication_requests == []
            assert target_state.password_attempts == []
            assert len(jump_state.password_attempts) == 1
            await assert_closed(target_state, jump_state)


async def test_jump_forwarding_denial_is_distinct_and_closes_jump(tmp_path):
    async with synthetic_server(tmp_path) as (target, target_state, _):
        async with synthetic_server(tmp_path) as (jump, jump_state, _):
            with pytest.raises(DomainError) as failure:
                await check_connection(target, jump, allow_loopback=True)
            assert failure.value.code == "SSH_FORWARDING_DENIED"
            assert target_state.password_attempts == []
            assert len(jump_state.password_attempts) == 1
            await assert_closed(target_state, jump_state)


async def test_missing_sftp_subsystem_is_reported_and_does_not_execute_command(tmp_path):
    async with synthetic_server(tmp_path, sftp=False) as (target, state, _):
        with pytest.raises(DomainError) as failure:
            await check_connection(target, allow_loopback=True)
        assert failure.value.code == "SSH_SFTP_FAILED"
        assert state.commands == []
        await assert_closed(state)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "::1",
        "::ffff:127.0.0.1",
        "169.254.169.254",
        "fe80::1",
        "224.0.0.1",
        "0.0.0.0",
        "::",
        "100.100.100.200",
    ],
)
async def test_special_destinations_are_denied_before_network_connections(host):
    with pytest.raises(DomainError) as failure:
        await inspect_key(Endpoint(host, 22, "synthetic-reader"))
    assert failure.value.code == "SSH_ADDRESS_DENIED"


async def test_mixed_dns_answers_are_rejected_and_no_second_resolution_occurs(monkeypatch):
    loop = asyncio.get_running_loop()
    resolutions = []

    async def resolve(host, port, **kwargs):
        resolutions.append((host, port))
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.30.40", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port)),
        ]

    monkeypatch.setattr(loop, "getaddrinfo", resolve)
    with pytest.raises(DomainError) as failure:
        await inspect_key(Endpoint("synthetic.example", 22, "synthetic-reader"))
    assert failure.value.code == "SSH_ADDRESS_DENIED"
    assert resolutions == [("synthetic.example", 22)]


async def test_dns_failure_is_sanitized(monkeypatch):
    async def resolve(*args, **kwargs):
        raise socket.gaierror("sensitive internal DNS details")

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    with pytest.raises(DomainError) as failure:
        await inspect_key(Endpoint("synthetic.example", 22, "synthetic-reader"))
    assert failure.value.code == "SSH_RESOLUTION_FAILED"
    assert "sensitive" not in str(failure.value)


async def test_route_pins_resolved_ip_and_preserves_configured_host_identity(tmp_path, monkeypatch):
    async with synthetic_server(tmp_path) as (target, state, _):
        loop = asyncio.get_running_loop()
        original_resolve = loop.getaddrinfo
        original_connect = asyncssh.connect
        checked_calls = []

        async def resolve(host, port, **kwargs):
            if host == "synthetic.example":
                return await original_resolve("127.0.0.1", port, **kwargs)
            return await original_resolve(host, port, **kwargs)

        def connect(host, port, **kwargs):
            checked_calls.append((host, port, kwargs["host_key_alias"]))
            return original_connect(host, port, **kwargs)

        monkeypatch.setattr(loop, "getaddrinfo", resolve)
        monkeypatch.setattr(asyncssh, "connect", connect)
        await check_connection(replace(target, host="synthetic.example"), allow_loopback=True)
        assert checked_calls == [("127.0.0.1", target.port, "synthetic.example")]
        await assert_closed(state)


async def test_target_and_jump_cannot_resolve_to_same_endpoint(tmp_path):
    async with synthetic_server(tmp_path) as (target, state, _):
        with pytest.raises(DomainError) as failure:
            await check_connection(target, target, allow_loopback=True)
        assert failure.value.code == "SSH_ROUTE_INVALID"
        assert state.password_attempts == []
        assert state.connections == set()


async def test_timeout_is_bounded_and_cancellation_releases_operation_slot(monkeypatch):
    blocked = asyncio.Event()

    async def resolve(*args, **kwargs):
        blocked.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    monkeypatch.setattr(ssh_transport, "_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(DomainError) as failure:
        await inspect_key(Endpoint("synthetic.example", 22, "synthetic-reader"))
    assert failure.value.code == "SSH_TIMEOUT"
    assert blocked.is_set()
    monkeypatch.setattr(ssh_transport, "_TIMEOUT_SECONDS", 5)
    task = asyncio.create_task(inspect_key(Endpoint("synthetic.example", 22, "synthetic-reader")))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ssh_transport._SLOTS._value == 4


async def test_cancelling_sftp_handshake_closes_target_and_jump(tmp_path):
    ready, release = asyncio.Event(), asyncio.Event()
    async with synthetic_server(tmp_path, sftp_barrier=(ready, release)) as (
        target,
        target_state,
        _,
    ):
        async with synthetic_server(tmp_path, allowed_forward=(target.host, target.port)) as (
            jump,
            jump_state,
            _,
        ):
            task = asyncio.create_task(check_connection(target, jump, allow_loopback=True))
            await asyncio.wait_for(ready.wait(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await assert_closed(target_state, jump_state)


async def test_operation_deadline_closes_authenticated_connection(tmp_path, monkeypatch):
    ready, release = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(ssh_transport, "_TIMEOUT_SECONDS", 0.2)
    async with synthetic_server(tmp_path, sftp_barrier=(ready, release)) as (target, state, _):
        with pytest.raises(DomainError) as failure:
            await check_connection(target, allow_loopback=True)
        assert ready.is_set()
        assert failure.value.code == "SSH_TIMEOUT"
        await assert_closed(state)


async def test_admission_bounds_actual_ssh_connections(tmp_path, monkeypatch):
    monkeypatch.setattr(ssh_transport, "_SLOTS", asyncio.BoundedSemaphore(1))
    ready, release = asyncio.Event(), asyncio.Event()
    async with synthetic_server(tmp_path, sftp_barrier=(ready, release)) as (target, state, _):
        first = asyncio.create_task(check_connection(target, allow_loopback=True))
        await asyncio.wait_for(ready.wait(), timeout=2)
        second = asyncio.create_task(check_connection(target, allow_loopback=True))
        await asyncio.sleep(0.05)
        assert len(state.connections) == 1
        assert len(state.password_attempts) == 1
        release.set()
        assert await asyncio.gather(first, second) == [
            {"ssh": True, "sftp": True},
            {"ssh": True, "sftp": True},
        ]
        assert len(state.password_attempts) == 2
        await assert_closed(state)


def test_endpoint_representation_never_includes_password():
    assert "synthetic-password" not in repr(
        Endpoint("10.1.2.3", 22, "reader", "synthetic-password")
    )
