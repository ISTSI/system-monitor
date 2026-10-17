"""Bounded, one-shot SSH identity inspection and read-only SFTP handshakes.

The access service supplies project-scoped approved keys and decrypted passwords.
This module never loads client configuration, local keys, an agent or known-host
files. Inspection rejects the offered key before target authentication; approval
is always a separate operation in the access service.
"""

import asyncio
import ipaddress
import socket
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field

import asyncssh

from inspector.errors import DomainError

_TIMEOUT_SECONDS = 20.0
_CLOSE_TIMEOUT_SECONDS = 2.0
_SLOTS = asyncio.BoundedSemaphore(4)


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int
    username: str
    password: str = field(default="", repr=False)
    host_key: str | None = None


class _InspectClient(asyncssh.SSHClient):
    """Record an untrusted proposal while refusing to establish trust."""

    def __init__(self) -> None:
        self.offered_key: asyncssh.SSHKey | None = None

    def validate_host_public_key(
        self, host: str, addr: str, port: int, key: asyncssh.SSHKey
    ) -> bool:
        self.offered_key = key
        return False


def _validate(endpoint: Endpoint) -> None:
    if (
        not endpoint.host
        or len(endpoint.host) > 253
        or any(char.isspace() or ord(char) < 32 for char in endpoint.host)
        or any(char in endpoint.host for char in "/\\%[]@")
        or not 1 <= endpoint.port <= 65535
        or len(endpoint.username) > 256
        or any(ord(char) < 32 or ord(char) == 127 for char in endpoint.username)
    ):
        raise DomainError("SSH_ROUTE_INVALID", "The configured SSH endpoint is invalid.", 422)


def _permitted_address(address: str, allow_loopback: bool) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_loopback:
        return allow_loopback
    return not (
        ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
        or str(ip) == "100.100.100.200"  # Alibaba's metadata endpoint.
    )


async def _resolve(endpoint: Endpoint, allow_loopback: bool) -> str:
    _validate(endpoint)
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            endpoint.host, endpoint.port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
    except (OSError, UnicodeError):
        raise DomainError(
            "SSH_RESOLUTION_FAILED", "The SSH hostname could not be resolved.", 422
        ) from None
    candidates = sorted({str(item[4][0]) for item in addresses})
    if not candidates:
        raise DomainError("SSH_RESOLUTION_FAILED", "The SSH hostname could not be resolved.", 422)
    # Reject a mixed DNS answer too. Connect only to the checked literal address,
    # so AsyncSSH/the jump cannot perform a second, different DNS resolution.
    if any(not _permitted_address(address, allow_loopback) for address in candidates):
        raise DomainError(
            "SSH_ADDRESS_DENIED",
            "The SSH destination is blocked by deployment network policy.",
            422,
        )
    return candidates[0]


def _approved_key(endpoint: Endpoint) -> asyncssh.SSHKey:
    if not endpoint.host_key:
        raise DomainError(
            "HOST_KEY_REQUIRED", "Inspect and approve the SSH host key before authentication.", 409
        )
    try:
        return asyncssh.import_public_key(endpoint.host_key)
    except (asyncssh.KeyImportError, ValueError):
        raise DomainError(
            "HOST_KEY_REQUIRED",
            "The SSH host key approval is invalid; inspect and approve it again.",
            409,
        ) from None


async def _close(connection: asyncssh.SSHClientConnection) -> None:
    connection.close()
    try:
        async with asyncio.timeout(_CLOSE_TIMEOUT_SECONDS):
            await connection.wait_closed()
    except (TimeoutError, asyncssh.Error, OSError):
        connection.abort()


async def _authenticate(
    endpoint: Endpoint,
    address: str,
    approved_key: asyncssh.SSHKey,
    jump: asyncssh.SSHClientConnection | None,
) -> asyncssh.SSHClientConnection:
    return await asyncssh.connect(
        address,
        endpoint.port,
        username=endpoint.username,
        password=endpoint.password,
        host_key_alias=endpoint.host,
        known_hosts=([approved_key], [], []),
        tunnel=jump or (),
        config=[],
        client_keys=[],
        agent_path=None,
        agent_forwarding=False,
        public_key_auth=False,
        host_based_auth=False,
        kbdint_auth=False,
        password_auth=True,
        preferred_auth=["password"],
        gss_auth=False,
        gss_kex=False,
        x509_trusted_certs=[],
        connect_timeout=_TIMEOUT_SECONDS,
        login_timeout=_TIMEOUT_SECONDS,
    )


@asynccontextmanager
async def _route(
    target: Endpoint, jump: Endpoint | None, allow_loopback: bool, *, authenticate_target: bool
) -> AsyncIterator[tuple[str, asyncssh.SSHClientConnection | None, asyncssh.SSHKey | None]]:
    """Validate the entire route before sending a password on either hop."""
    target_key = _approved_key(target) if authenticate_target else None
    jump_key = _approved_key(jump) if jump else None
    async with AsyncExitStack() as stack:
        address = await _resolve(target, allow_loopback)
        jump_connection = None
        if jump:
            jump_address = await _resolve(jump, allow_loopback)
            if (address, target.port) == (jump_address, jump.port):
                raise DomainError(
                    "SSH_ROUTE_INVALID", "The SSH target and jump endpoint must be distinct.", 422
                )
            assert jump_key is not None
            jump_connection = await _authenticate(jump, jump_address, jump_key, None)
            stack.push_async_callback(_close, jump_connection)
        yield address, jump_connection, target_key


@asynccontextmanager
async def _bounded_operation() -> AsyncIterator[None]:
    try:
        async with asyncio.timeout(_TIMEOUT_SECONDS), _SLOTS:
            yield
    except DomainError:
        raise
    except TimeoutError:
        raise DomainError("SSH_TIMEOUT", "The SSH connection test timed out.", 504) from None
    except asyncssh.HostKeyNotVerifiable:
        raise DomainError(
            "HOST_KEY_CHANGED",
            "The SSH host key does not match its approval. Verify it independently.",
            409,
        ) from None
    except asyncssh.PermissionDenied:
        raise DomainError("SSH_AUTH_FAILED", "SSH password authentication failed.", 422) from None
    except asyncssh.ChannelOpenError:
        raise DomainError(
            "SSH_FORWARDING_DENIED",
            "The jump host could not forward to the configured SSH target.",
            422,
        ) from None
    except (asyncssh.Error, OSError):
        raise DomainError(
            "SSH_CONNECT_FAILED", "The SSH endpoint could not be reached or negotiated.", 422
        ) from None


async def inspect_key(
    target: Endpoint, jump: Endpoint | None = None, *, allow_loopback: bool = False
) -> dict[str, str]:
    """Return an untrusted key proposal without authenticating to the target.

    A configured jump must already have a pinned approved key and credentials.
    No host-key validation is bypassed: the target key callback always rejects.
    """
    async with _bounded_operation():
        async with _route(target, jump, allow_loopback, authenticate_target=False) as route:
            address, jump_connection, _ = route
            observer = _InspectClient()
            try:
                # Empty known-hosts plus a rejecting callback ends the handshake
                # at key verification, before any target authentication request.
                connection = await asyncssh.connect(
                    address,
                    target.port,
                    username="",
                    password=None,
                    host_key_alias=target.host,
                    known_hosts=([], [], []),
                    client_factory=lambda: observer,
                    server_host_key_algs="default",
                    tunnel=jump_connection or (),
                    config=[],
                    client_keys=[],
                    agent_path=None,
                    agent_forwarding=False,
                    public_key_auth=False,
                    host_based_auth=False,
                    kbdint_auth=False,
                    password_auth=False,
                    gss_auth=False,
                    gss_kex=False,
                    x509_trusted_certs=[],
                    connect_timeout=_TIMEOUT_SECONDS,
                    login_timeout=_TIMEOUT_SECONDS,
                )
            except asyncssh.HostKeyNotVerifiable:
                if observer.offered_key is None:
                    raise
                key = observer.offered_key
                return {
                    "public_key": key.export_public_key("openssh").decode("ascii").strip(),
                    "algorithm": key.get_algorithm(),
                    "fingerprint": key.get_fingerprint("sha256"),
                }
            else:
                # Defensive: inspection must never yield an accepted connection.
                await _close(connection)
                raise DomainError(
                    "SSH_CONNECT_FAILED",
                    "The SSH server did not provide an inspectable host key.",
                    422,
                )


async def test_connection(
    target: Endpoint, jump: Endpoint | None = None, *, allow_loopback: bool = False
) -> dict[str, bool]:
    """Authenticate only pinned keys, negotiate SFTP, and close both hops."""
    async with _bounded_operation():
        async with _route(target, jump, allow_loopback, authenticate_target=True) as route:
            address, jump_connection, target_key = route
            assert target_key is not None
            connection = await _authenticate(target, address, target_key, jump_connection)
            try:
                try:
                    async with connection.start_sftp_client():
                        return {"ssh": True, "sftp": True}
                except (asyncssh.SFTPError, asyncssh.ChannelOpenError):
                    raise DomainError(
                        "SSH_SFTP_FAILED",
                        "SSH authenticated, but the SFTP subsystem is unavailable.",
                        422,
                    ) from None
            finally:
                await _close(connection)
