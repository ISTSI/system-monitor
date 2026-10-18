"""Write-only password vault and explicit, project-scoped SSH setup checks.

Only explicit inspection/test POSTs perform network work. Their transactions are
closed before connecting, and all authentication/configuration/access versions
are checked again before accepting results. This module never collects logs.
"""

import asyncio
import hashlib
import json
import os
import stat
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from inspector import auth, services, ssh_transport
from inspector.config import Config
from inspector.domain import Principal, ProjectContext
from inspector.errors import DomainError
from inspector.persistence.models import (
    Audit,
    AuthSession,
    Project,
    ProjectCredentialBinding,
    SSHCredential,
    SSHHostTrust,
    SSHKeyInspection,
    TopologyState,
)
from inspector.security import authorize, issue_token, token_hash


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RevisionInput(StrictInput):
    expected_config_revision: int = Field(ge=1)


class PasswordInput(RevisionInput):
    expected_credential_revision: int = Field(ge=0)
    password: SecretStr = Field(min_length=1, max_length=1024, repr=False)


class TrustInput(RevisionInput):
    expected_trust_revision: int = Field(ge=0)


class ApproveInput(TrustInput):
    inspection_token: SecretStr = Field(min_length=43, max_length=43, repr=False)
    verified: bool


class CredentialStatus(StrictInput):
    configured: bool
    revision: int


class TrustStatus(StrictInput):
    approved: bool
    revision: int
    fingerprint: str | None
    algorithm: str | None


class AccessResponse(StrictInput):
    project_id: str
    connection_id: str
    config_revision: int
    credential: CredentialStatus
    host_key: TrustStatus
    jump_connection_id: str | None
    vault_available: bool


class InspectResponse(StrictInput):
    inspection_token: str
    fingerprint: str
    algorithm: str
    expires_us: str


class TestResponse(StrictInput):
    ssh: bool
    sftp: bool
    config_revision: int


class Vault:
    """The raw 256-bit master key lives outside MariaDB and every API response."""

    def __init__(self, key_file: str) -> None:
        self._key: bytes | None = None
        if not key_file:
            return
        try:
            path = Path(key_file)
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or path.is_symlink():
                return
            if os.name == "posix" and (
                info.st_uid != getattr(os, "geteuid", lambda: -1)()
                or stat.S_IMODE(info.st_mode) & 0o077
            ):
                return
            with path.open("rb") as stream:
                raw = stream.read(33)
            if len(raw) == 32:
                self._key = raw
        except OSError:
            pass

    @property
    def available(self) -> bool:
        return self._key is not None

    def _cipher(self) -> AESGCM:
        if self._key is None:
            raise DomainError(
                "SSH_VAULT_UNAVAILABLE", "The server SSH vault key is unavailable.", 503
            )
        return AESGCM(self._key)

    @staticmethod
    def _aad(credential_id: str, key_version: int) -> bytes:
        return json.dumps([credential_id, key_version], separators=(",", ":")).encode("ascii")

    def encrypt(
        self, credential_id: str, password: str, key_version: int = 1
    ) -> tuple[bytes, bytes]:
        try:
            raw = password.encode("utf-8")
        except UnicodeError:
            raw = b""
        if not 1 <= len(raw) <= 1024 or b"\x00" in raw:
            raise DomainError(
                "INVALID_SSH_PASSWORD", "Use a nonempty password of at most 1024 UTF-8 bytes.", 422
            )
        nonce = os.urandom(12)
        ciphertext = self._cipher().encrypt(nonce, raw, self._aad(credential_id, key_version))
        return nonce, ciphertext

    def decrypt(self, row: SSHCredential) -> str:
        try:
            return (
                self._cipher()
                .decrypt(
                    row.nonce,
                    row.ciphertext,
                    self._aad(row.id, row.key_version),
                )
                .decode("utf-8")
            )
        except (ValueError, InvalidTag, UnicodeError):
            raise DomainError(
                "SSH_VAULT_UNAVAILABLE", "The saved SSH credential cannot be decrypted.", 503
            ) from None


def route_digest(route: list[dict[str, Any]]) -> str:
    """Names/layout are irrelevant; identity, endpoint, alias and routing are not."""
    fields = ("id", "host", "port", "username", "credential_ref", "jump_connection_id")
    normalized = [{key: hop.get(key) for key in fields} for hop in route]
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class NetworkSnapshot:
    target: ssh_transport.Endpoint = field(repr=False)
    jump: ssh_transport.Endpoint | None = field(repr=False)
    signature: str
    route_digest: str


class SSHAccess:
    def __init__(
        self, config: Config, sessions: async_sessionmaker[AsyncSession], supervisor: Any = None
    ) -> None:
        self.config = config
        self.sessions = sessions
        self.supervisor = supervisor
        self.vault = Vault(config.vault_key_file)
        self._network_active = 0
        self._attempts: deque[tuple[float, str]] = deque()

    async def _actor(
        self,
        session: AsyncSession,
        actor: Principal,
        action: str,
        session_hash: str | None,
        *,
        lock: bool = True,
    ) -> Principal:
        actor = await services.current_actor(session, actor, lock=lock)
        authorize(actor, action)
        # Recheck the actual login too: logout deletes it without changing auth_version.
        login = (
            await session.get(AuthSession, session_hash, populate_existing=True)
            if session_hash
            else None
        )
        return self._validated_login(actor, login)

    def _validated_login(self, actor: Principal, login: AuthSession | None) -> Principal:
        """Recheck a fresh login row without changing actor/login error order."""
        now = services.utc_now_us()
        if (
            login is None
            or login.user_id != actor.user_id
            or login.auth_version != actor.auth_version
            or auth.session_expired(login, now, self.config.idle_timeout_us)
        ):
            raise DomainError("AUTH_REQUIRED", "Authentication is required.", 401)
        return actor

    async def _profile(
        self,
        session: AsyncSession,
        actor: Principal,
        project_id: str,
        connection_id: str,
        expected_revision: int | None = None,
        *,
        lock: bool = True,
    ) -> tuple[Project, list[dict[str, Any]]]:
        project = await services.project_in_context(
            session, ProjectContext(project_id, actor.user_id), lock=lock
        )
        state = await session.get(TopologyState, project_id, populate_existing=not lock)
        return project, self._route(project, state, connection_id, expected_revision)

    @staticmethod
    def _route(
        project: Project,
        state: TopologyState | None,
        connection_id: str,
        expected_revision: int | None = None,
    ) -> list[dict[str, Any]]:
        """Apply the same route checks to one fresh topology snapshot."""
        profiles = {item["id"]: item for item in state.config["connections"]} if state else {}
        target = profiles.get(connection_id)
        if target is None:
            raise DomainError("NOT_FOUND", "Resource not found.", 404)
        if expected_revision is not None:
            if project.archived:
                raise DomainError("PROJECT_ARCHIVED", "Archived system is read-only.", 409)
            if project.revision != expected_revision:
                raise DomainError(
                    "REVISION_CONFLICT", "System has changed; reload before continuing.", 409
                )
        route = [target]
        if target.get("jump_connection_id"):
            jump = profiles.get(target["jump_connection_id"])
            if jump is None or jump.get("jump_connection_id") or jump["id"] == target["id"]:
                raise DomainError(
                    "SSH_ROUTE_INVALID",
                    "Only a direct connection or one jump host is supported.",
                    422,
                )
            route.append(jump)
        return route

    async def _credential(
        self, session: AsyncSession, project_id: str, profile: dict[str, Any]
    ) -> SSHCredential | None:
        binding = await session.get(
            ProjectCredentialBinding,
            (project_id, profile["credential_ref"]),
            populate_existing=True,
        )
        return (
            await session.get(SSHCredential, binding.credential_id, populate_existing=True)
            if binding
            else None
        )

    async def _status(
        self,
        session: AsyncSession,
        project_id: str,
        connection_id: str,
        project: Project,
        route: list[dict[str, Any]],
    ) -> dict[str, Any]:
        credential = await self._credential(session, project_id, route[0])
        trust = await session.get(SSHHostTrust, (project_id, connection_id))
        valid = bool(trust and trust.approved and trust.route_digest == route_digest(route))
        return dict(
            project_id=project_id,
            connection_id=connection_id,
            config_revision=project.revision,
            credential=dict(
                configured=credential is not None, revision=credential.revision if credential else 0
            ),
            host_key=dict(
                approved=valid,
                revision=trust.revision if trust else 0,
                fingerprint=trust.fingerprint if valid and trust else None,
                algorithm=trust.algorithm if valid and trust else None,
            ),
            jump_connection_id=route[0].get("jump_connection_id"),
            vault_available=self.vault.available,
        )

    async def access(
        self, actor: Principal, project_id: str, connection_id: str, session_hash: str | None
    ) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            actor = await self._actor(session, actor, "credential.manage", session_hash)
            project, route = await self._profile(session, actor, project_id, connection_id)
            return await self._status(session, project_id, connection_id, project, route)

    async def save_password(
        self,
        actor: Principal,
        project_id: str,
        connection_id: str,
        payload: PasswordInput,
        session_hash: str | None,
    ) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            actor = await self._actor(session, actor, "credential.manage", session_hash)
            project, route = await self._profile(
                session, actor, project_id, connection_id, payload.expected_config_revision
            )
            row = await self._credential(session, project_id, route[0])
            if payload.expected_credential_revision != (row.revision if row else 0):
                raise DomainError(
                    "REVISION_CONFLICT", "SSH password has changed; reload before saving.", 409
                )
            if row is None:
                row = SSHCredential(id=str(uuid4()), revision=1, key_version=1)
                row.nonce, row.ciphertext = self.vault.encrypt(
                    row.id, payload.password.get_secret_value()
                )
                session.add(row)
                await session.flush()
                # Imported aliases never look up another project's global vault row.
                session.add(
                    ProjectCredentialBinding(
                        project_id=project_id,
                        alias=route[0]["credential_ref"],
                        credential_id=row.id,
                    )
                )
            else:
                row.nonce, row.ciphertext = self.vault.encrypt(
                    row.id, payload.password.get_secret_value(), row.key_version
                )
                row.revision += 1
            # Explicit replacement renews an expired password record.
            row.expires_us = None
            services.audit(
                session,
                actor,
                "credential.manage",
                project_id,
                connection_id,
                services.utc_now_us(),
            )
            await session.flush()
            return await self._status(session, project_id, connection_id, project, route)

    async def _snapshot(
        self,
        session: AsyncSession,
        actor: Principal,
        project_id: str,
        connection_id: str,
        revision: int,
        *,
        inspect: bool,
        lock: bool = True,
    ) -> NetworkSnapshot:
        _, route = await self._profile(
            session, actor, project_id, connection_id, revision, lock=lock
        )
        trusts = {}
        credentials = {}
        for profile in route:
            trusts[profile["id"]] = await session.get(
                SSHHostTrust, (project_id, profile["id"]), populate_existing=True
            )
            credentials[profile["id"]] = await self._credential(session, project_id, profile)
        return self._network(route, trusts, credentials, inspect=inspect)

    def _network(
        self,
        route: list[dict[str, Any]],
        trusts: Mapping[str, SSHHostTrust | None],
        credentials: Mapping[str, SSHCredential | None],
        *,
        inspect: bool,
    ) -> NetworkSnapshot:
        """Build a network snapshot from rows read in the caller's transaction."""
        endpoints: list[ssh_transport.Endpoint] = []
        versions: list[dict[str, Any]] = []
        for index, profile in enumerate(route):
            hop_route = route if index == 0 else [profile]
            trust = trusts.get(profile["id"])
            valid = bool(trust and trust.approved and trust.route_digest == route_digest(hop_route))
            credential = credentials.get(profile["id"])
            needs_auth = not inspect or index > 0
            if needs_auth and not valid:
                raise DomainError(
                    "HOST_KEY_REQUIRED",
                    "Inspect and independently verify this connection's host key before testing.",
                    409,
                )
            if needs_auth and credential is None:
                raise DomainError(
                    "SSH_PASSWORD_REQUIRED",
                    "Save an SSH password for this connection before testing.",
                    409,
                )
            if (
                needs_auth
                and credential
                and credential.expires_us is not None
                and credential.expires_us <= services.utc_now_us()
            ):
                raise DomainError(
                    "SSH_CREDENTIAL_EXPIRED",
                    "The SSH credential expired; ask an Administrator to replace it.",
                    410,
                )
            endpoints.append(
                ssh_transport.Endpoint(
                    host=profile["host"],
                    port=profile["port"],
                    username=profile["username"],
                    password=self.vault.decrypt(credential) if needs_auth and credential else "",
                    host_key=trust.public_key if valid and trust else None,
                )
            )
            versions.append(
                dict(
                    credential_id=credential.id if credential else None,
                    credential_revision=credential.revision if credential else 0,
                    credential_expires_us=credential.expires_us if credential else None,
                    trust_revision=trust.revision if trust else 0,
                )
            )
        digest = route_digest(route)
        signature = hashlib.sha256(
            json.dumps([digest, versions], sort_keys=True).encode()
        ).hexdigest()
        return NetworkSnapshot(
            endpoints[0], endpoints[1] if len(endpoints) == 2 else None, signature, digest
        )

    def _reserve(self, actor: Principal) -> None:
        now = time.monotonic()
        while self._attempts and now - self._attempts[0][0] >= 60:
            self._attempts.popleft()
        if (
            self._network_active >= 4
            or len(self._attempts) >= 30
            or sum(user == actor.user_id for _, user in self._attempts) >= 10
        ):
            raise DomainError(
                "LIMIT_REACHED", "SSH checks are busy or rate limited; try again shortly.", 429
            )
        self._attempts.append((now, actor.user_id))
        self._network_active += 1

    async def _watched_network(
        self,
        actor: Principal,
        project_id: str,
        connection_id: str,
        revision: int,
        session_hash: str | None,
        before: NetworkSnapshot,
        *,
        inspect: bool,
    ) -> dict[str, Any]:
        """Cancel a pending handshake promptly after access or database revocation."""
        action = "host_trust.manage" if inspect else "connection.test"

        async def supervisor_ready() -> None:
            try:
                async with asyncio.timeout(1):
                    healthy = self.supervisor is not None and await self.supervisor.healthy()
            except TimeoutError:
                healthy = False
            if not healthy:
                raise DomainError(
                    "DATABASE_UNAVAILABLE",
                    "The SSH check was cancelled because persistence is unavailable.",
                    503,
                )

        await supervisor_ready()

        async def watch_access() -> None:
            while True:
                await asyncio.sleep(0.25)
                try:
                    async with asyncio.timeout(1):
                        await supervisor_ready()
                        async with self.sessions.begin() as session:
                            current = await self._actor(session, actor, action, session_hash)
                            snapshot = await self._snapshot(
                                session,
                                current,
                                project_id,
                                connection_id,
                                revision,
                                inspect=inspect,
                            )
                            if snapshot.signature != before.signature:
                                raise DomainError(
                                    "REVISION_CONFLICT",
                                    "SSH access changed during the check; repeat it.",
                                    409,
                                )
                except (SQLAlchemyError, TimeoutError):
                    raise DomainError(
                        "NOT_READY",
                        "Database access is unavailable; the SSH check was cancelled.",
                        503,
                    ) from None

        async def perform() -> dict[str, Any]:
            if inspect:
                return await ssh_transport.inspect_key(
                    before.target, before.jump, allow_loopback=self.config.ssh_allow_loopback
                )
            return await ssh_transport.test_connection(
                before.target, before.jump, allow_loopback=self.config.ssh_allow_loopback
            )

        network = asyncio.create_task(perform())
        watch = asyncio.create_task(watch_access())
        try:
            done, _ = await asyncio.wait((network, watch), return_when=asyncio.FIRST_COMPLETED)
            if watch in done:
                await watch
            return await network
        finally:
            # Await cancellation so no transport survives an expired request/approval.
            for task in (network, watch):
                if not task.done():
                    task.cancel()
            await asyncio.gather(network, watch, return_exceptions=True)

    async def check(
        self,
        actor: Principal,
        project_id: str,
        connection_id: str,
        revision: int,
        session_hash: str | None,
        *,
        inspect: bool,
    ) -> dict[str, Any]:
        action = "host_trust.manage" if inspect else "connection.test"
        async with self.sessions.begin() as session:
            actor = await self._actor(session, actor, action, session_hash)
            before = await self._snapshot(
                session, actor, project_id, connection_id, revision, inspect=inspect
            )
        self._reserve(actor)
        result: dict[str, Any] | None = None
        failure: DomainError | None = None
        try:
            try:
                async with asyncio.timeout(30):
                    result = await self._watched_network(
                        actor,
                        project_id,
                        connection_id,
                        revision,
                        session_hash,
                        before,
                        inspect=inspect,
                    )
            except TimeoutError:
                failure = DomainError("SSH_TIMEOUT", "The SSH check timed out.", 504)
            except DomainError as error:
                failure = error
            if failure is not None and failure.status == 503:
                # A failed persistence guard never produces an accepted result.
                # Do not start another potentially blocked DB probe after cancellation.
                raise failure
            async with self.sessions.begin() as session:
                actor = await self._actor(session, actor, action, session_hash)
                after = await self._snapshot(
                    session, actor, project_id, connection_id, revision, inspect=inspect
                )
                if before.signature != after.signature:
                    raise DomainError(
                        "REVISION_CONFLICT", "SSH access changed during the check; repeat it.", 409
                    )
                if failure:
                    # Classification only; remote exception text never enters the audit.
                    session.add(
                        Audit(
                            id=str(uuid4()),
                            actor_user_id=actor.user_id,
                            actor_role=actor.role,
                            action=action,
                            project_id=project_id,
                            target_id=connection_id,
                            created_us=services.utc_now_us(),
                            outcome="failed",
                        )
                    )
                elif result is not None and inspect:
                    token = issue_token()
                    expires = services.utc_now_us() + 300_000_000
                    await session.execute(
                        delete(SSHKeyInspection).where(
                            SSHKeyInspection.expires_us <= services.utc_now_us()
                        )
                    )
                    current_trust = await session.get(SSHHostTrust, (project_id, connection_id))
                    session.add(
                        SSHKeyInspection(
                            token_hash=token_hash(token),
                            project_id=project_id,
                            connection_id=connection_id,
                            owner_user_id=actor.user_id,
                            auth_version=actor.auth_version,
                            auth_session_hash=session_hash,
                            config_revision=revision,
                            route_digest=before.route_digest,
                            network_signature=before.signature,
                            trust_revision=current_trust.revision if current_trust else 0,
                            public_key=result["public_key"],
                            algorithm=result["algorithm"],
                            fingerprint=result["fingerprint"],
                            expires_us=expires,
                        )
                    )
                    services.audit(
                        session, actor, action, project_id, connection_id, services.utc_now_us()
                    )
                    return dict(
                        inspection_token=token,
                        fingerprint=result["fingerprint"],
                        algorithm=result["algorithm"],
                        expires_us=str(expires),
                    )
                else:
                    services.audit(
                        session, actor, action, project_id, connection_id, services.utc_now_us()
                    )
            if failure:
                raise failure
            return dict(ssh=True, sftp=True, config_revision=revision)
        finally:
            self._network_active -= 1

    async def approve(
        self,
        actor: Principal,
        project_id: str,
        connection_id: str,
        payload: ApproveInput,
        session_hash: str | None,
    ) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            actor = await self._actor(session, actor, "host_trust.manage", session_hash)
            if not payload.verified:
                raise DomainError(
                    "HOST_KEY_VERIFICATION_REQUIRED",
                    "Verify the fingerprint through an independent trusted source before approval.",
                    422,
                )
            project, route = await self._profile(
                session, actor, project_id, connection_id, payload.expected_config_revision
            )
            key = token_hash(payload.inspection_token.get_secret_value())
            observed = await session.get(SSHKeyInspection, key) if key else None
            if (
                observed is None
                or observed.project_id != project_id
                or observed.connection_id != connection_id
                or observed.owner_user_id != actor.user_id
            ):
                raise DomainError("NOT_FOUND", "Host-key inspection not found.", 404)
            if observed.expires_us <= services.utc_now_us():
                raise DomainError(
                    "INSPECTION_EXPIRED", "Host-key inspection expired; inspect again.", 410
                )
            if (
                observed.auth_version != actor.auth_version
                or observed.auth_session_hash != session_hash
                or observed.config_revision != project.revision
                or observed.route_digest != route_digest(route)
            ):
                raise DomainError(
                    "REVISION_CONFLICT", "Connection changed; inspect the host key again.", 409
                )
            current_snapshot = await self._snapshot(
                session,
                actor,
                project_id,
                connection_id,
                payload.expected_config_revision,
                inspect=True,
            )
            if observed.network_signature != current_snapshot.signature:
                raise DomainError(
                    "REVISION_CONFLICT", "SSH access changed; inspect the host key again.", 409
                )
            trust = await session.get(SSHHostTrust, (project_id, connection_id))
            if (
                payload.expected_trust_revision != (trust.revision if trust else 0)
                or observed.trust_revision != payload.expected_trust_revision
            ):
                raise DomainError(
                    "REVISION_CONFLICT", "Host-key trust changed; inspect again.", 409
                )
            if trust is None:
                trust = SSHHostTrust(project_id=project_id, connection_id=connection_id, revision=1)
                session.add(trust)
            else:
                trust.revision += 1
            trust.approved = True
            trust.route_digest = observed.route_digest
            trust.public_key, trust.algorithm, trust.fingerprint = (
                observed.public_key,
                observed.algorithm,
                observed.fingerprint,
            )
            await session.delete(observed)
            services.audit(
                session,
                actor,
                "host_trust.manage",
                project_id,
                connection_id,
                services.utc_now_us(),
            )
            await session.flush()
            return await self._status(session, project_id, connection_id, project, route)

    async def revoke(
        self,
        actor: Principal,
        project_id: str,
        connection_id: str,
        payload: TrustInput,
        session_hash: str | None,
    ) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            actor = await self._actor(session, actor, "host_trust.manage", session_hash)
            project, route = await self._profile(
                session, actor, project_id, connection_id, payload.expected_config_revision
            )
            trust = await session.get(SSHHostTrust, (project_id, connection_id))
            if payload.expected_trust_revision != (trust.revision if trust else 0):
                raise DomainError(
                    "REVISION_CONFLICT", "Host-key trust changed; reload before revoking.", 409
                )
            if trust:
                trust.approved = False
                trust.revision += 1
            else:
                # Retain a version even before first approval, so revocation
                # also invalidates inspections currently waiting on a network.
                trust = SSHHostTrust(
                    project_id=project_id,
                    connection_id=connection_id,
                    revision=1,
                    approved=False,
                    route_digest=route_digest(route),
                    public_key="",
                    algorithm="",
                    fingerprint="",
                )
                session.add(trust)
            await session.execute(
                delete(SSHKeyInspection).where(
                    SSHKeyInspection.project_id == project_id,
                    SSHKeyInspection.connection_id == connection_id,
                )
            )
            services.audit(
                session,
                actor,
                "host_trust.manage",
                project_id,
                connection_id,
                services.utc_now_us(),
            )
            await session.flush()
            return await self._status(session, project_id, connection_id, project, route)


def build_ssh_access_router(
    transaction: Callable, authenticated: Callable, protected_write: Callable
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}/connections/{connection_id}")
    Session = Annotated[AsyncSession, Depends(transaction, scope="function")]
    Actor = Annotated[Principal, Depends(authenticated)]
    Writer = Annotated[Principal, Depends(protected_write)]

    def manager(request: Request) -> SSHAccess:
        return request.app.state.ssh_access

    def login_hash(request: Request) -> str | None:
        return token_hash(request.cookies.get("__Host-si-session", ""))

    @router.get(
        "/access",
        response_model=AccessResponse,
        openapi_extra={"x-permission": "credential.manage"},
    )
    async def access(
        project_id: str, connection_id: str, request: Request, actor: Actor, session: Session
    ) -> dict:
        await session.commit()
        return await manager(request).access(actor, project_id, connection_id, login_hash(request))

    @router.put(
        "/password",
        response_model=AccessResponse,
        openapi_extra={"x-permission": "credential.manage"},
    )
    async def password(
        project_id: str,
        connection_id: str,
        payload: PasswordInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        await session.commit()
        return await manager(request).save_password(
            actor, project_id, connection_id, payload, login_hash(request)
        )

    @router.post(
        "/host-key/inspect",
        response_model=InspectResponse,
        openapi_extra={"x-permission": "host_trust.manage"},
    )
    async def inspect(
        project_id: str,
        connection_id: str,
        payload: RevisionInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        await session.commit()
        return await manager(request).check(
            actor,
            project_id,
            connection_id,
            payload.expected_config_revision,
            login_hash(request),
            inspect=True,
        )

    @router.post(
        "/host-key/approve",
        response_model=AccessResponse,
        openapi_extra={"x-permission": "host_trust.manage"},
    )
    async def approve(
        project_id: str,
        connection_id: str,
        payload: ApproveInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        await session.commit()
        return await manager(request).approve(
            actor, project_id, connection_id, payload, login_hash(request)
        )

    @router.post(
        "/test", response_model=TestResponse, openapi_extra={"x-permission": "connection.test"}
    )
    async def test(
        project_id: str,
        connection_id: str,
        payload: RevisionInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        await session.commit()
        return await manager(request).check(
            actor,
            project_id,
            connection_id,
            payload.expected_config_revision,
            login_hash(request),
            inspect=False,
        )

    @router.post(
        "/revoke",
        response_model=AccessResponse,
        openapi_extra={"x-permission": "host_trust.manage"},
    )
    async def revoke(
        project_id: str,
        connection_id: str,
        payload: TrustInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        await session.commit()
        return await manager(request).revoke(
            actor, project_id, connection_id, payload, login_hash(request)
        )

    return router
