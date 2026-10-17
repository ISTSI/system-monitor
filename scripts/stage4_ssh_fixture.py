"""Synthetic password-only SSH endpoints for local connection verification.

The target exposes only its mounted synthetic log tree through read-only SFTP.
The jump endpoint permits forwarding only to ssh-target:8022. Neither endpoint
accepts a shell, exec, remote forwarding, an agent, or filesystem mutations.
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import os
import signal
import socket
from pathlib import Path

import asyncssh


class FixtureServer(asyncssh.SSHServer):
    def __init__(
        self,
        username: str,
        password: str,
        *,
        jump: bool,
        forwarding_hosts: frozenset[str] = frozenset({"ssh-target"}),
    ) -> None:
        self.username = username
        self.password = password
        self.jump = jump
        self.forwarding_hosts = forwarding_hosts

    def begin_auth(self, username: str) -> bool:
        return True

    def password_auth_supported(self) -> bool:
        return True

    def validate_password(self, username: str, password: str) -> bool:
        return hmac.compare_digest(username.encode("utf-8"), self.username.encode("utf-8")) and (
            hmac.compare_digest(password.encode("utf-8"), self.password.encode("utf-8"))
        )

    def connection_requested(
        self, dest_host: str, dest_port: int, orig_host: str, orig_port: int
    ) -> bool:
        return self.jump and dest_host in self.forwarding_hosts and dest_port == 8022


class ReadOnlyFixtureSFTP(asyncssh.SFTPServer):
    """Deny every mutating operation, including the v5/v6 open variant."""

    def open(self, path: bytes, pflags: int, attrs: asyncssh.SFTPAttrs) -> object:
        if pflags != asyncssh.FXF_READ:
            raise asyncssh.SFTPPermissionDenied("Synthetic log fixture is read-only.")
        return super().open(path, pflags, attrs)

    def _deny(self, *args: object, **kwargs: object) -> None:
        raise asyncssh.SFTPPermissionDenied("Synthetic log fixture is read-only.")

    open56 = _deny
    write = _deny
    setstat = _deny
    fsetstat = _deny
    lsetstat = _deny
    remove = _deny
    mkdir = _deny
    rmdir = _deny
    rename = _deny
    posix_rename = _deny
    symlink = _deny
    link = _deny
    lock = _deny
    unlock = _deny


async def serve(args: argparse.Namespace) -> None:
    password = args.password_file.read_text("ascii").strip()
    if not password or len(password) > 1024:
        raise ValueError("Invalid fixture password file.")
    if args.role == "target":
        logs = args.root / "var/log/inspector-demo"
        if not logs.is_dir() or any(path.is_symlink() for path in logs.rglob("*")):
            raise ValueError("Synthetic fixture tree must exist and contain no symlinks.")

        def sftp_factory(channel):
            return ReadOnlyFixtureSFTP(channel, chroot=os.fsencode(args.root))
    else:
        sftp_factory = None
    forwarding_hosts = {"ssh-target"}
    if args.role == "jump":
        # The application pins a DNS-validated literal IP before forwarding.
        # Resolve only this fixed synthetic name, never a client-supplied host.
        async with asyncio.timeout(10):
            addresses = await asyncio.get_running_loop().getaddrinfo(
                "ssh-target", 8022, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
            )
        forwarding_hosts.update(str(item[4][0]) for item in addresses)
    server = await asyncssh.listen(
        "0.0.0.0",
        args.port,
        server_factory=lambda: FixtureServer(
            args.username,
            password,
            jump=args.role == "jump",
            forwarding_hosts=frozenset(forwarding_hosts),
        ),
        server_host_keys=[str(args.key_file)],
        sftp_factory=sftp_factory,
        sftp_version=3,
        allow_scp=False,
        login_timeout=15,
        rekey_seconds=3600,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, stop.set)
        except NotImplementedError:
            pass
    print(f"Synthetic read-only SSH {args.role} ready on port {args.port}.", flush=True)
    try:
        await stop.wait()
    finally:
        server.close()
        await server.wait_closed()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["target", "jump"])
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--username", default="synthetic-log-reader")
    parser.add_argument("--port", type=int, default=8022)
    parser.add_argument("--root", type=Path, default=Path("/fixture-root"))
    args = parser.parse_args()
    asyncio.run(serve(args))


if __name__ == "__main__":
    main()
