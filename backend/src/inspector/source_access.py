"""Configured-source confirmation policy and fresh authorization around read-only SFTP.

Importing configuration never creates a local approval. Network work starts
only after its transaction closes and is cancelled if current access cannot be
verified. Login sessions authorize users; no mutable active system is inferred.
"""

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Annotated, Any, TypeVar
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from inspector import foundation, services, ssh_files, ssh_transport
from inspector.domain import Principal
from inspector.errors import DomainError
from inspector.persistence.models import (
    ApplicationSetting,
    Audit,
    AuthSession,
    Project,
    ProjectCredentialBinding,
    SecurityState,
    SourceAccessApproval,
    SSHCredential,
    SSHHostTrust,
    TopologyState,
    User,
)
from inspector.security import authorize, token_hash
from inspector.ssh_access import NetworkSnapshot, SSHAccess, route_digest

T = TypeVar("T")
_LOGGER = logging.getLogger(__name__)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceTestInput(StrictInput):
    expected_config_revision: int = Field(ge=1)


class SourceRevisionInput(SourceTestInput):
    expected_approval_revision: int = Field(ge=0)


class SourceApprovalInput(SourceRevisionInput):
    verified: bool
    expires_seconds: int = Field(default=86_400, ge=60, le=2_592_000)


class SourceApprovalStatus(StrictInput):
    approved: bool
    revision: int
    expires_us: str | None


class SourceAccessResponse(StrictInput):
    project_id: str
    connection_id: str
    config_revision: int
    manual_confirmation_required: bool
    approval: SourceApprovalStatus
    roots: list[str]
    process_ids: list[str]


class SourcePathResult(StrictInput):
    process_id: str
    accessible: bool
    candidate_count: int
    estimated_bytes: int
    warning: str | None


class SourcePathTestResponse(StrictInput):
    project_id: str
    connection_id: str
    config_revision: int
    processes: list[SourcePathResult]


def roots_digest(roots: tuple[str, ...]) -> str:
    return hashlib.sha256(
        json.dumps(sorted(set(roots)), separators=(",", ":")).encode()
    ).hexdigest()


def configured_roots(route: list[dict[str, Any]]) -> tuple[str, ...]:
    roots = tuple(route[0].get("allowed_log_roots", []))
    if not roots or any(
        not isinstance(root, str)
        or not root.startswith("/")
        or root.startswith("//")
        or ".." in PurePosixPath(root).parts
        or "\\" in root
        or any(ord(char) < 32 or ord(char) == 127 for char in root)
        for root in roots
    ):
        raise DomainError("SOURCE_NOT_APPROVED", "Configure valid log roots before approval.", 409)
    return roots


def approval_matches(
    row: SourceAccessApproval | None,
    revision: int,
    network: NetworkSnapshot,
    roots: tuple[str, ...],
    now: int,
) -> bool:
    return bool(
        row
        and row.approved
        and row.expires_us > now
        and row.config_revision == revision
        and row.route_digest == network.route_digest
        and row.roots_digest == roots_digest(roots)
        and row.network_signature == network.signature
    )


@dataclass(frozen=True)
class SourceSnapshot:
    project_id: str
    connection_id: str
    owner_user_id: str
    config_revision: int
    approval_revision: int
    roots: tuple[str, ...]
    signature: str
    auth_session_hash: str | None = field(repr=False)
    network: NetworkSnapshot = field(repr=False)

    @property
    def target(self) -> ssh_transport.Endpoint:
        return self.network.target

    @property
    def jump(self) -> ssh_transport.Endpoint | None:
        return self.network.jump

    @property
    def route_digest(self) -> str:
        return self.network.route_digest


class SourceAccess:
    def __init__(self, ssh_access: SSHAccess) -> None:
        self.ssh = ssh_access
        self.sessions = ssh_access.sessions

    async def _prepare(
        self,
        session: AsyncSession,
        actor: Principal,
        project_id: str,
        connection_id: str,
        revision: int,
        session_hash: str | None,
        *,
        require_approval: bool,
        action: str,
        lock: bool = True,
    ) -> SourceSnapshot:
        actor = await self.ssh._actor(session, actor, action, session_hash, lock=lock)
        if not require_approval and action != "source_access.manage":
            raise DomainError("FORBIDDEN", "Source approval cannot be bypassed.", 403)
        manual_confirmation = (
            await foundation.settings_value(session)
        ).additional_security_measures
        _, route = await self.ssh._profile(
            session, actor, project_id, connection_id, revision, lock=lock
        )
        roots = configured_roots(route)
        network = await self.ssh._snapshot(
            session, actor, project_id, connection_id, revision, inspect=False, lock=lock
        )
        approval = await session.get(
            SourceAccessApproval, (project_id, connection_id), populate_existing=True
        )
        return self._source_snapshot(
            actor,
            project_id,
            connection_id,
            revision,
            session_hash,
            roots,
            network,
            approval,
            manual_confirmation=manual_confirmation,
            require_approval=require_approval,
        )

    @staticmethod
    def _source_snapshot(
        actor: Principal,
        project_id: str,
        connection_id: str,
        revision: int,
        session_hash: str | None,
        roots: tuple[str, ...],
        network: NetworkSnapshot,
        approval: SourceAccessApproval | None,
        *,
        manual_confirmation: bool,
        require_approval: bool,
    ) -> SourceSnapshot:
        if (
            require_approval
            and manual_confirmation
            and not approval_matches(approval, revision, network, roots, services.utc_now_us())
        ):
            if approval and approval.approved and approval.expires_us <= services.utc_now_us():
                raise DomainError(
                    "SOURCE_APPROVAL_EXPIRED",
                    "The target/root approval expired; ask an Administrator.",
                    410,
                )
            raise DomainError(
                "SOURCE_NOT_APPROVED",
                "An Administrator must approve this system's current target and log roots.",
                409,
            )
        approval_revision = approval.revision if approval else 0
        signature = hashlib.sha256(
            json.dumps(
                [
                    project_id,
                    connection_id,
                    revision,
                    actor.user_id,
                    actor.auth_version,
                    session_hash,
                    roots_digest(roots),
                    network.signature,
                    manual_confirmation,
                    approval_revision if manual_confirmation else None,
                    approval.expires_us if manual_confirmation and approval else None,
                    approval.approved if manual_confirmation and approval else False,
                ],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return SourceSnapshot(
            project_id=project_id,
            connection_id=connection_id,
            owner_user_id=actor.user_id,
            config_revision=revision,
            approval_revision=approval_revision,
            roots=roots,
            signature=signature,
            auth_session_hash=session_hash,
            network=network,
        )

    async def prepare_many_in_transaction(
        self,
        session: AsyncSession,
        actor: Principal,
        project_id: str,
        connection_ids: list[str],
        revision: int,
        session_hash: str | None,
    ) -> dict[str, SourceSnapshot]:
        """Fresh read-only live validation with bounded, project-scoped batch reads.

        This never grants a write reservation. Control mutations continue using
        prepare_in_transaction and its security/project locks. No loaded rows or
        completed authorization survive this caller-owned transaction.
        """
        if not 1 <= len(connection_ids) <= 200 or len(set(connection_ids)) != len(connection_ids):
            raise DomainError("INVALID_REQUEST", "Select 1 to 200 distinct connections.", 422)
        context = (
            await session.execute(
                select(SecurityState, User, AuthSession, ApplicationSetting, Project, TopologyState)
                .select_from(SecurityState)
                .outerjoin(User, User.id == actor.user_id)
                .outerjoin(
                    AuthSession,
                    AuthSession.token_hash
                    == case((SecurityState.id == 1, session_hash), else_=None),
                )
                .outerjoin(ApplicationSetting, ApplicationSetting.id == SecurityState.id)
                .outerjoin(
                    Project, Project.id == case((SecurityState.id == 1, project_id), else_=None)
                )
                .outerjoin(TopologyState, TopologyState.project_id == Project.id)
                .where(SecurityState.id == 1)
                .execution_options(populate_existing=True)
            )
        ).first()
        if context is None:
            raise DomainError("NOT_READY", "Security state is unavailable.", 503)
        _, user, login, settings, project, state = context
        # Keep the ordinary actor -> permission -> login -> settings -> project
        # validation order. Locked control paths reuse these same pure checks.
        actor = services._validated_actor(user, actor)
        authorize(actor, "collection.create")
        actor = self.ssh._validated_login(actor, login)
        if settings is None:
            raise DomainError("NOT_READY", "Application settings are unavailable.", 503)
        manual_confirmation = settings.additional_security_measures
        if project is None:
            raise DomainError("NOT_FOUND", "Resource not found.", 404)
        routes = {
            identifier: self.ssh._route(project, state, identifier, revision)
            for identifier in connection_ids
        }
        profiles = {profile["id"]: profile for route in routes.values() for profile in route}
        trust_rows = (
            await session.execute(
                select(SSHHostTrust, SourceAccessApproval)
                .outerjoin(
                    SourceAccessApproval,
                    and_(
                        SourceAccessApproval.project_id == SSHHostTrust.project_id,
                        SourceAccessApproval.connection_id == SSHHostTrust.connection_id,
                    ),
                )
                .where(
                    SSHHostTrust.project_id == project_id,
                    SSHHostTrust.connection_id.in_(profiles),
                )
                .execution_options(populate_existing=True)
            )
        ).all()
        trusts = {trust.connection_id: trust for trust, _ in trust_rows}
        approvals = {
            trust.connection_id: approval for trust, approval in trust_rows if approval is not None
        }
        credential_rows = (
            await session.execute(
                select(ProjectCredentialBinding, SSHCredential)
                .outerjoin(
                    SSHCredential, SSHCredential.id == ProjectCredentialBinding.credential_id
                )
                .where(
                    ProjectCredentialBinding.project_id == project_id,
                    ProjectCredentialBinding.alias.in_(
                        {profile["credential_ref"] for profile in profiles.values()}
                    ),
                )
                .execution_options(populate_existing=True)
            )
        ).all()
        credentials = {binding.alias: credential for binding, credential in credential_rows}
        profile_credentials = {
            identifier: credentials.get(profile["credential_ref"])
            for identifier, profile in profiles.items()
        }
        return {
            identifier: self._source_snapshot(
                actor,
                project_id,
                identifier,
                revision,
                session_hash,
                configured_roots(route),
                self.ssh._network(route, trusts, profile_credentials, inspect=False),
                approvals.get(identifier),
                manual_confirmation=manual_confirmation,
                require_approval=True,
            )
            for identifier, route in routes.items()
        }

    async def prepare_many(
        self,
        actor: Principal,
        project_id: str,
        connection_ids: list[str],
        revision: int,
        session_hash: str | None,
    ) -> dict[str, SourceSnapshot]:
        async with self.sessions.begin() as session:
            return await self.prepare_many_in_transaction(
                session, actor, project_id, connection_ids, revision, session_hash
            )

    async def prepare(
        self,
        actor: Principal,
        project_id: str,
        connection_id: str,
        revision: int,
        session_hash: str | None,
        *,
        require_approval: bool = True,
        action: str = "collection.create",
        lock: bool = True,
    ) -> SourceSnapshot:
        async with self.sessions.begin() as session:
            return await self._prepare(
                session,
                actor,
                project_id,
                connection_id,
                revision,
                session_hash,
                require_approval=require_approval,
                action=action,
                lock=lock,
            )

    async def prepare_in_transaction(
        self,
        session: AsyncSession,
        actor: Principal,
        project_id: str,
        connection_id: str,
        revision: int,
        session_hash: str | None,
    ) -> SourceSnapshot:
        """Revalidate before job reservation; the caller owns this short transaction.

        No network work may run until it commits. The security/project locks
        serialize this check with credential, approval and configuration writes.
        """
        # Refresh only this scope without discarding the caller's pending state.
        # Lock security before project, matching the ordinary mutation order.
        await self.ssh._actor(session, actor, "collection.create", session_hash)
        await session.get(Project, project_id, populate_existing=True, with_for_update=True)
        await session.get(TopologyState, project_id, populate_existing=True, with_for_update=True)
        return await self._prepare(
            session,
            actor,
            project_id,
            connection_id,
            revision,
            session_hash,
            require_approval=True,
            action="collection.create",
        )

    async def _healthy(self) -> None:
        began = asyncio.get_running_loop().time()
        error_code = "unhealthy_probe"
        try:
            async with asyncio.timeout(1):
                healthy = self.ssh.supervisor is not None and await self.ssh.supervisor.healthy()
        except (TimeoutError, SQLAlchemyError) as error:
            healthy = False
            error_code = type(error).__name__
        if not healthy:
            _LOGGER.warning(
                "Source persistence check failed closed: error=%s elapsed_seconds=%.3f supervisor_failed=%s supervisor_phase=%s supervisor_error=%s",
                error_code,
                asyncio.get_running_loop().time() - began,
                getattr(self.ssh.supervisor, "failed", None),
                getattr(self.ssh.supervisor, "last_failure_phase", None),
                getattr(self.ssh.supervisor, "last_failure_code", None),
            )
            raise DomainError(
                "DATABASE_UNAVAILABLE",
                "Remote access stopped because persistence is unavailable.",
                503,
            )

    async def watched(
        self,
        actor: Principal,
        project_id: str,
        connection_id: str,
        revision: int,
        session_hash: str | None,
        before: SourceSnapshot,
        operation: Callable[[], Awaitable[T]],
        *,
        require_approval: bool = True,
        action: str = "collection.create",
    ) -> T:
        """Run no network until revalidated; cancel promptly on any access loss."""
        if (
            before.project_id != project_id
            or before.connection_id != connection_id
            or before.owner_user_id != actor.user_id
            or before.config_revision != revision
            or before.auth_session_hash != session_hash
        ):
            raise DomainError("NOT_FOUND", "Resource not found.", 404)

        async def revalidate() -> None:
            try:
                async with asyncio.timeout(1):
                    await self._healthy()
                    current = await self.prepare(
                        actor,
                        project_id,
                        connection_id,
                        revision,
                        session_hash,
                        require_approval=require_approval,
                        action=action,
                    )
                    if current.signature != before.signature:
                        raise DomainError(
                            "REVISION_CONFLICT", "Source access changed; repeat the request.", 409
                        )
            except (SQLAlchemyError, TimeoutError):
                raise DomainError(
                    "DATABASE_UNAVAILABLE",
                    "Remote access stopped because persistence could not be verified.",
                    503,
                ) from None

        async def watch() -> None:
            while True:
                await asyncio.sleep(0.25)
                await revalidate()

        async def perform_operation() -> T:
            return await operation()

        await revalidate()
        network = asyncio.create_task(perform_operation())
        guard = asyncio.create_task(watch())
        try:
            done, _ = await asyncio.wait((network, guard), return_when=asyncio.FIRST_COMPLETED)
            if guard in done:
                await guard
            result = await network
            await revalidate()
            return result
        finally:
            for task in (network, guard):
                if not task.done():
                    task.cancel()
            await asyncio.gather(network, guard, return_exceptions=True)

    @staticmethod
    async def _processes(session: AsyncSession, project_id: str, connection_id: str) -> list[dict]:
        state = await session.get(TopologyState, project_id)
        document = state.config if state else {}
        server_ids = {
            item["id"]
            for item in document.get("servers", [])
            if item["connection_id"] == connection_id
        }
        return [item for item in document.get("processes", []) if item["server_id"] in server_ids]

    async def _status(
        self, session: AsyncSession, actor: Principal, project_id: str, connection_id: str
    ) -> dict[str, Any]:
        project, route = await self.ssh._profile(session, actor, project_id, connection_id)
        row = await session.get(SourceAccessApproval, (project_id, connection_id))
        roots = tuple(route[0].get("allowed_log_roots", []))
        manual_confirmation = (
            await foundation.settings_value(session)
        ).additional_security_measures
        valid = False
        if not project.archived:
            try:
                roots = configured_roots(route)
                network = await self.ssh._snapshot(
                    session, actor, project_id, connection_id, project.revision, inspect=False
                )
                valid = not manual_confirmation or approval_matches(
                    row, project.revision, network, roots, services.utc_now_us()
                )
            except DomainError:
                # Missing credentials or key approval is ordinary setup status.
                valid = False
        return dict(
            project_id=project_id,
            connection_id=connection_id,
            config_revision=project.revision,
            manual_confirmation_required=manual_confirmation,
            approval=dict(
                approved=valid,
                revision=row.revision if row else 0,
                expires_us=(
                    str(row.expires_us) if manual_confirmation and row and row.approved else None
                ),
            ),
            roots=list(roots),
            process_ids=[
                item["id"] for item in await self._processes(session, project_id, connection_id)
            ],
        )

    async def access(
        self, actor: Principal, project_id: str, connection_id: str, session_hash: str | None
    ) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            actor = await self.ssh._actor(session, actor, "source_access.manage", session_hash)
            return await self._status(session, actor, project_id, connection_id)

    async def approve(
        self,
        actor: Principal,
        project_id: str,
        connection_id: str,
        payload: SourceApprovalInput,
        session_hash: str | None,
    ) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            actor = await self.ssh._actor(session, actor, "source_access.manage", session_hash)
            if not payload.verified:
                raise DomainError(
                    "APPROVAL_REQUIRED",
                    "Confirm independent authorization of the target and log roots.",
                    422,
                )
            before = await self._prepare(
                session,
                actor,
                project_id,
                connection_id,
                payload.expected_config_revision,
                session_hash,
                require_approval=False,
                action="source_access.manage",
            )
            row = await session.get(SourceAccessApproval, (project_id, connection_id))
            if payload.expected_approval_revision != (row.revision if row else 0):
                raise DomainError("REVISION_CONFLICT", "Source approval changed; reload it.", 409)
            now = services.utc_now_us()
            if row is None:
                row = SourceAccessApproval(
                    project_id=project_id, connection_id=connection_id, revision=1
                )
                session.add(row)
            else:
                row.revision += 1
            row.approved = True
            row.config_revision = before.config_revision
            row.route_digest = before.route_digest
            row.roots_digest = roots_digest(before.roots)
            row.network_signature = before.network.signature
            row.approved_by_user_id = actor.user_id
            row.approved_us, row.expires_us = now, now + payload.expires_seconds * 1_000_000
            services.audit(session, actor, "source_access.manage", project_id, connection_id, now)
            await session.flush()
            return await self._status(session, actor, project_id, connection_id)

    async def revoke(
        self,
        actor: Principal,
        project_id: str,
        connection_id: str,
        payload: SourceRevisionInput,
        session_hash: str | None,
    ) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            actor = await self.ssh._actor(session, actor, "source_access.manage", session_hash)
            _, route = await self.ssh._profile(
                session, actor, project_id, connection_id, payload.expected_config_revision
            )
            row = await session.get(SourceAccessApproval, (project_id, connection_id))
            if payload.expected_approval_revision != (row.revision if row else 0):
                raise DomainError("REVISION_CONFLICT", "Source approval changed; reload it.", 409)
            now = services.utc_now_us()
            if row is None:
                row = SourceAccessApproval(
                    project_id=project_id,
                    connection_id=connection_id,
                    revision=1,
                    config_revision=payload.expected_config_revision,
                    route_digest=route_digest(route),
                    roots_digest=roots_digest(tuple(route[0].get("allowed_log_roots", []))),
                    network_signature="0" * 64,
                    approved_by_user_id=actor.user_id,
                    approved_us=now,
                    expires_us=now + 1,
                )
                session.add(row)
            else:
                row.revision += 1
            row.approved = False
            services.audit(session, actor, "source_access.manage", project_id, connection_id, now)
            await session.flush()
            return await self._status(session, actor, project_id, connection_id)

    async def test(
        self,
        actor: Principal,
        project_id: str,
        connection_id: str,
        payload: SourceTestInput,
        session_hash: str | None,
    ) -> dict[str, Any]:
        before = await self.prepare(
            actor,
            project_id,
            connection_id,
            payload.expected_config_revision,
            session_hash,
            action="source.test",
        )
        async with self.sessions.begin() as session:
            processes = await self._processes(session, project_id, connection_id)
        self.ssh._reserve(actor)

        async def perform() -> list[dict[str, Any]]:
            results = []
            async with ssh_files.open_files(
                before.target,
                before.jump,
                allow_loopback=self.ssh.config.ssh_allow_loopback,
                timeout_seconds=30,
                max_candidates=self.ssh.config.history_limits.get(
                    "max_source_files_per_collection", 1000
                ),
                max_listing_entries=self.ssh.config.history_limits.get(
                    "max_source_listing_entries", 10_000
                ),
                max_listing_bytes=self.ssh.config.history_limits.get(
                    "max_source_listing_bytes", 4_194_304
                ),
                max_probe_bytes=self.ssh.config.history_limits.get(
                    "max_source_probe_bytes", 33_554_432
                ),
                max_estimated_bytes=self.ssh.config.history_limits.get(
                    "max_download_bytes_per_collection", 536_870_912
                ),
            ) as remote:
                for process in processes:
                    warning_start = len(remote.warnings)
                    try:
                        candidates = await remote.plan(process["log_source"], list(before.roots))
                        for candidate in candidates:
                            await remote.check(candidate)
                        results.append(
                            dict(
                                process_id=process["id"],
                                accessible=bool(candidates),
                                candidate_count=len(candidates),
                                estimated_bytes=sum(item.estimated_bytes for item in candidates),
                                warning="; ".join(remote.warnings[warning_start:]) or None,
                            )
                        )
                    except DomainError as error:
                        results.append(
                            dict(
                                process_id=process["id"],
                                accessible=False,
                                candidate_count=0,
                                estimated_bytes=0,
                                warning=str(error),
                            )
                        )
            return results

        try:
            await self._audit_test(actor, project_id, connection_id, "started")
            async with asyncio.timeout(35):
                results = await self.watched(
                    actor,
                    project_id,
                    connection_id,
                    payload.expected_config_revision,
                    session_hash,
                    before,
                    perform,
                    action="source.test",
                )
            await self._audit_test(
                actor,
                project_id,
                connection_id,
                "success" if all(item["accessible"] for item in results) else "failed",
            )
        except TimeoutError:
            await self._audit_test_failure(actor, project_id, connection_id)
            raise DomainError("SSH_TIMEOUT", "Configured source checks timed out.", 504) from None
        except DomainError:
            await self._audit_test_failure(actor, project_id, connection_id)
            raise
        finally:
            self.ssh._network_active -= 1
        return dict(
            project_id=project_id,
            connection_id=connection_id,
            config_revision=payload.expected_config_revision,
            processes=results,
        )

    async def _audit_test(
        self, actor: Principal, project_id: str, connection_id: str, outcome: str
    ) -> None:
        async with asyncio.timeout(1):
            async with self.sessions.begin() as session:
                session.add(
                    Audit(
                        id=str(uuid4()),
                        actor_user_id=actor.user_id,
                        actor_role=actor.role,
                        action="source.test",
                        project_id=project_id,
                        target_id=connection_id,
                        created_us=services.utc_now_us(),
                        outcome=outcome,
                    )
                )

    async def _audit_test_failure(
        self, actor: Principal, project_id: str, connection_id: str
    ) -> None:
        try:
            await self._audit_test(actor, project_id, connection_id, "failed")
        except (SQLAlchemyError, TimeoutError):
            # An unavailable DB must not mask the original fail-closed result.
            pass


def build_source_access_router(
    transaction: Callable, authenticated: Callable, protected_write: Callable
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/connections/{connection_id}/source-access"
    )
    Session = Annotated[AsyncSession, Depends(transaction, scope="function")]
    Actor = Annotated[Principal, Depends(authenticated)]
    Writer = Annotated[Principal, Depends(protected_write)]

    def manager(request: Request) -> SourceAccess:
        return request.app.state.source_access

    def login_hash(request: Request) -> str | None:
        return token_hash(request.cookies.get("__Host-si-session", ""))

    @router.get(
        "",
        response_model=SourceAccessResponse,
        openapi_extra={"x-permission": "source_access.manage"},
    )
    async def access(
        project_id: str, connection_id: str, request: Request, actor: Actor, session: Session
    ) -> dict:
        await session.commit()
        return await manager(request).access(actor, project_id, connection_id, login_hash(request))

    @router.post(
        "/approve",
        response_model=SourceAccessResponse,
        openapi_extra={"x-permission": "source_access.manage"},
    )
    async def approve(
        project_id: str,
        connection_id: str,
        payload: SourceApprovalInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        await session.commit()
        return await manager(request).approve(
            actor, project_id, connection_id, payload, login_hash(request)
        )

    @router.post(
        "/revoke",
        response_model=SourceAccessResponse,
        openapi_extra={"x-permission": "source_access.manage"},
    )
    async def revoke(
        project_id: str,
        connection_id: str,
        payload: SourceRevisionInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        await session.commit()
        return await manager(request).revoke(
            actor, project_id, connection_id, payload, login_hash(request)
        )

    @router.post(
        "/test",
        response_model=SourcePathTestResponse,
        openapi_extra={"x-permission": "source.test"},
    )
    async def test(
        project_id: str,
        connection_id: str,
        payload: SourceTestInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        await session.commit()
        return await manager(request).test(
            actor, project_id, connection_id, payload, login_hash(request)
        )

    return router
