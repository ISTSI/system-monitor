"""Owned saved analysis, exact traces and retained source-local bookmarks."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import Field, model_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from inspector import services
from inspector.domain import ID_PATTERN, Principal
from inspector.errors import DomainError
from inspector.history import (
    TERMINAL,
    HistoricalContextInput,
    HistoricalContextResponse,
    HistoricalFilter,
    HistoricalQueryInput,
    HistoricalQueryResponse,
    StrictInput,
    canonical_time,
    checked_job,
    format_time,
    historical_context,
    historical_query,
    job_response,
    not_found,
)
from inspector.history_cache import READ_CACHE
from inspector.persistence.investigation_models import InvestigationBookmark, SavedInvestigation
from inspector.persistence.models import (
    HistoryCursor,
    HistoryDownload,
    HistoryEvent,
    HistoryJob,
    HistorySource,
)


class RevisionInput(StrictInput):
    expected_revision: int = Field(ge=0)


class PinGroup(StrictInput):
    id: str = Field(pattern=ID_PATTERN)
    description: str = Field(max_length=10000)
    bookmark_ids: list[Annotated[str, Field(pattern=ID_PATTERN)]] = Field(
        min_length=1, max_length=100
    )
    created_us: int = Field(ge=0, le=9_007_199_254_740_991)

    @model_validator(mode="after")
    def unique_bookmarks(self) -> "PinGroup":
        if len(set(self.bookmark_ids)) != len(self.bookmark_ids):
            raise ValueError("A pin group must reference each bookmark once.")
        return self


class PinEventInput(HistoricalContextInput):
    event_id: str = Field(pattern=ID_PATTERN)
    before: Literal[0] = 0
    after: Literal[0] = 0


class PinCreate(RevisionInput):
    description: str = Field(default="", max_length=10000)
    events: list[PinEventInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_events(self) -> "PinCreate":
        if len({event.event_id for event in self.events}) != len(self.events):
            raise ValueError("Select each event once per pin group.")
        return self


class PinUpdate(RevisionInput):
    description: str = Field(max_length=10000)
    events: list[PinEventInput] | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_events(self) -> "PinUpdate":
        if "events" in self.model_fields_set and self.events is None:
            raise ValueError("Omit events to keep the existing pin selection.")
        if self.events is not None and len({event.event_id for event in self.events}) != len(
            self.events
        ):
            raise ValueError("Select each event once per pin group.")
        return self


@asynccontextmanager
async def pin_deadline() -> AsyncIterator[None]:
    try:
        async with asyncio.timeout(30):
            yield
    except TimeoutError:
        raise DomainError(
            "PIN_TIMEOUT", "Pinning selected events exceeded its time budget.", 408
        ) from None


def pin_groups(state: dict) -> list[dict]:
    """Typed server-owned extension of the existing personal analysis JSON."""
    groups = [PinGroup.model_validate(group).model_dump() for group in state.get("pin_groups", [])]
    identities = [group["id"] for group in groups]
    bookmarks = [bookmark for group in groups for bookmark in group["bookmark_ids"]]
    if (
        len(groups) > 1000
        or len(set(identities)) != len(identities)
        or len(set(bookmarks)) != len(bookmarks)
    ):
        raise ValueError("Invalid pin group identities or membership.")
    return groups


def with_pin_groups(state: dict, groups: list[dict]) -> dict:
    candidate = {**state, "pin_groups": groups}
    return {**state, "pin_groups": pin_groups(candidate)}


def pruned_pin_groups(state: dict, bookmark_ids: set[str]) -> list[dict]:
    return [
        {**group, "bookmark_ids": retained}
        for group in pin_groups(state)
        if (retained := [key for key in group["bookmark_ids"] if key in bookmark_ids])
    ]


class SavedWorkspaceInput(RevisionInput):
    title: str = Field(min_length=1, max_length=200)
    process_ids: list[Annotated[str, Field(pattern=ID_PATTERN)]] = Field(
        min_length=1, max_length=200
    )
    from_: str = Field(alias="from")
    to: str
    filter: HistoricalFilter = Field(default_factory=HistoricalFilter)
    per_process_filters: dict[str, HistoricalFilter] = Field(default_factory=dict, max_length=200)
    layout: Literal["merged", "split"] = "merged"
    notes: str = Field(default="", max_length=10000)
    pinned: bool = False

    @model_validator(mode="after")
    def valid_scope(self) -> "SavedWorkspaceInput":
        if canonical_time(self.from_) >= canonical_time(self.to):
            raise ValueError("The exclusive end must follow the start.")
        if len(set(self.process_ids)) != len(self.process_ids) or not set(
            self.per_process_filters
        ) <= set(self.process_ids):
            raise ValueError("Invalid process/filter selection.")
        return self


class SavedWorkspaceResponse(StrictInput):
    project_id: str
    investigation_id: str
    revision: int
    saved: bool
    title: str
    process_ids: list[str]
    from_: str = Field(alias="from")
    to: str
    filter: HistoricalFilter
    per_process_filters: dict[str, HistoricalFilter]
    layout: Literal["merged", "split"]
    notes: str
    pinned: bool
    collection_references: list[str]
    availability: Literal["retained", "partial", "unavailable"]
    source_snapshot_revision: int
    pin_groups: list[PinGroup] = Field(default_factory=list, max_length=1000)


class BookmarkCreate(HistoricalContextInput):
    expected_revision: int = Field(ge=0)
    event_id: str = Field(pattern=ID_PATTERN)
    annotation: str = Field(default="", max_length=10000)
    pin_context: bool = True


class BookmarkUpdate(RevisionInput):
    annotation: str = Field(max_length=10000)
    pin_context: bool


class BookmarkItem(StrictInput):
    bookmark_id: str
    event_id: str
    annotation: str
    pin_context: bool
    context: HistoricalContextResponse | None
    process_name_snapshot: str
    server_name_snapshot: str
    created_us: int
    availability: Literal["retained", "unavailable"]


class BookmarkResponse(StrictInput):
    project_id: str
    investigation_id: str
    revision: int
    items: list[BookmarkItem]
    pin_groups: list[PinGroup] = Field(default_factory=list, max_length=1000)


class CorrelationInput(HistoricalQueryInput):
    correlation: None = None
    mode: Literal["exact", "literal"] = "exact"
    field: str = Field(default="request_id", min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=512)


class TraceDelta(StrictInput):
    event_id: str
    delta_us: int | None
    source_time_inversion: bool


class CorrelationResponse(HistoricalQueryResponse):
    deltas: list[TraceDelta]
    warning: str


class ExpireResponse(StrictInput):
    project_id: str
    investigation_id: str
    revision: int
    availability: Literal["unavailable"]
    cache_cleanup_pending: bool


class SourceDetails(StrictInput):
    project_id: str
    investigation_id: str
    source_revision_id: str
    process_id: str
    remote_path: str
    kind: str
    status: str
    error_code: str | None
    checksum: str | None
    downloaded_bytes: int
    expanded_bytes: int
    retained_event_count: int
    parse_issue_count: int
    observed_from: str | None
    observed_to: str | None
    captured_ranges: list[dict[str, int]]
    raw_bytes_available: bool
    limitations: list[str]


def default_state(job: HistoryJob) -> dict:
    return dict(
        title="Untitled investigation",
        process_ids=job.process_ids,
        **{"from": format_time(job.from_us)},
        to=format_time(job.to_us),
        filter=HistoricalFilter().model_dump(),
        per_process_filters={},
        layout="merged",
        notes="",
    )


async def saved_row(session: AsyncSession, job: HistoryJob) -> SavedInvestigation | None:
    return await session.get(SavedInvestigation, (job.project_id, job.id), populate_existing=True)


async def revise(session: AsyncSession, job: HistoryJob, expected: int) -> SavedInvestigation:
    # All personal mutations lock the same scoped parent before checking this revision.
    saved = await saved_row(session, job)
    if expected != (saved.revision if saved else 0):
        raise DomainError(
            "REVISION_CONFLICT", "Saved analysis changed; reload it before saving.", 409
        )
    if saved is None:
        saved = SavedInvestigation(
            project_id=job.project_id,
            job_id=job.id,
            owner_user_id=job.owner_user_id,
            revision=1,
            state=default_state(job),
            pinned=False,
            expired=False,
            updated_us=services.utc_now_us(),
        )
        session.add(saved)
    else:
        saved.revision += 1
        saved.updated_us = services.utc_now_us()
    await session.flush()
    return saved


async def workspace_response(session: AsyncSession, job: HistoryJob) -> dict:
    saved = await saved_row(session, job)
    response = await job_response(session, job)
    unavailable = bool(saved and saved.expired) or response["coverage_status"] == "unavailable"
    return dict(
        project_id=job.project_id,
        investigation_id=job.id,
        revision=saved.revision if saved else 0,
        saved=saved is not None,
        **(saved.state if saved else default_state(job)),
        pinned=saved.pinned if saved else False,
        collection_references=[job.id],
        availability="unavailable"
        if unavailable
        else "retained"
        if job.status == "completed"
        else "partial",
        source_snapshot_revision=job.snapshot_revision,
    )


async def bookmark_response(session: AsyncSession, job: HistoryJob) -> dict:
    saved = await saved_row(session, job)
    rows = (
        await session.scalars(
            select(InvestigationBookmark)
            .where(
                InvestigationBookmark.project_id == job.project_id,
                InvestigationBookmark.job_id == job.id,
            )
            .order_by(InvestigationBookmark.created_us, InvestigationBookmark.id)
            .limit(1000)
        )
    ).all()
    return dict(
        project_id=job.project_id,
        investigation_id=job.id,
        revision=saved.revision if saved else 0,
        pin_groups=pin_groups(saved.state) if saved else [],
        items=[
            dict(
                bookmark_id=row.id,
                event_id=row.event_id,
                annotation=row.annotation,
                pin_context=row.pin_context,
                context=row.context or None,
                process_name_snapshot=row.process_name_snapshot,
                server_name_snapshot=row.server_name_snapshot,
                created_us=row.created_us,
                availability="retained" if row.context else "unavailable",
            )
            for row in rows
        ],
    )


def build_investigation_router(
    transaction: Any, authenticated: Any, protected_write: Any
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/investigations/{job_id}", tags=["investigation tools"]
    )
    Actor = Annotated[Principal, Depends(authenticated)]
    Writer = Annotated[Principal, Depends(protected_write)]
    Session = Annotated[AsyncSession, Depends(transaction, scope="function")]

    @router.get(
        "/workspace",
        response_model=SavedWorkspaceResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def workspace(project_id: str, job_id: str, actor: Actor, session: Session) -> dict:
        return await workspace_response(
            session, await checked_job(session, actor, project_id, job_id)
        )

    @router.patch(
        "/workspace",
        response_model=SavedWorkspaceResponse,
        openapi_extra={"x-permission": "investigation.write"},
    )
    async def save_workspace(
        project_id: str, job_id: str, payload: SavedWorkspaceInput, actor: Writer, session: Session
    ) -> dict:
        job = await checked_job(
            session, actor, project_id, job_id, lock=True, action="investigation.write"
        )
        if not set(payload.process_ids) <= set(job.process_ids):
            raise not_found()
        saved = await revise(session, job, payload.expected_revision)
        if saved.expired and payload.pinned:
            raise DomainError("SOURCE_EXPIRED", "Unavailable source data cannot be pinned.", 410)
        saved.state = with_pin_groups(
            payload.model_dump(by_alias=True, exclude={"expected_revision", "pinned"}),
            pin_groups(saved.state),
        )
        saved.pinned = payload.pinned
        await session.flush()
        return await workspace_response(session, job)

    @router.get(
        "/bookmarks",
        response_model=BookmarkResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def bookmarks(project_id: str, job_id: str, actor: Actor, session: Session) -> dict:
        return await bookmark_response(
            session, await checked_job(session, actor, project_id, job_id)
        )

    @router.post(
        "/pins",
        response_model=BookmarkResponse,
        status_code=201,
        openapi_extra={"x-permission": "bookmark.write"},
    )
    async def create_pin(
        project_id: str,
        job_id: str,
        payload: PinCreate,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        await session.commit()
        async with pin_deadline(), request.app.state.history.use_capture(project_id, job_id):
            await authenticated(request, session)
            job = await checked_job(
                session, actor, project_id, job_id, lock=True, action="investigation.write"
            )
            saved = await revise(session, job, payload.expected_revision)
            count, retained_bytes = (
                await session.execute(
                    select(
                        func.count(),
                        func.coalesce(
                            func.sum(func.octet_length(InvestigationBookmark.context)), 0
                        ),
                    ).where(
                        InvestigationBookmark.project_id == project_id,
                        InvestigationBookmark.job_id == job_id,
                    )
                )
            ).one()
            if count + len(payload.events) > 1000:
                raise DomainError(
                    "LIMIT_REACHED", "This investigation has reached its bookmark limit.", 429
                )
            created = services.utc_now_us()
            groups = pin_groups(saved.state)
            group: dict = dict(
                id=str(uuid4()),
                description=payload.description,
                bookmark_ids=[],
                created_us=created,
            )
            byte_count = retained_bytes + len(
                json.dumps(
                    [*groups, {**group, "bookmark_ids": ["0" * 36] * len(payload.events)}],
                    ensure_ascii=True,
                ).encode()
            )
            rows = []
            for event in payload.events:
                context_input = HistoricalContextInput.model_validate(
                    event.model_dump(by_alias=True, exclude={"event_id"})
                )
                context = await historical_context(
                    session, actor, project_id, job_id, event.event_id, context_input
                )
                byte_count += len(json.dumps(context, ensure_ascii=True).encode())
                if byte_count > 33_554_432:
                    raise DomainError(
                        "LIMIT_REACHED",
                        "Pinned context exceeds the 32 MiB investigation budget.",
                        413,
                    )
                anchor = next(item["event"] for item in context["items"] if item["is_anchor"])
                bookmark_id = str(uuid4())
                group["bookmark_ids"].append(bookmark_id)
                rows.append(
                    InvestigationBookmark(
                        project_id=project_id,
                        job_id=job_id,
                        id=bookmark_id,
                        owner_user_id=actor.user_id,
                        event_id=event.event_id,
                        reference_event_id=event.event_id,
                        annotation="",
                        pin_context=True,
                        context=context,
                        process_name_snapshot=anchor["process_name_snapshot"],
                        server_name_snapshot=anchor["server_name_snapshot"],
                        created_us=created,
                    )
                )
                await asyncio.sleep(0)
            await authenticated(request, session)
            saved.state = with_pin_groups(saved.state, [*groups, group])
            session.add_all(rows)
            await session.flush()
            return await bookmark_response(session, job)

    @router.patch(
        "/pins/{pin_id}",
        response_model=BookmarkResponse,
        openapi_extra={"x-permission": "bookmark.write"},
    )
    async def edit_pin(
        project_id: str,
        job_id: str,
        pin_id: str,
        payload: PinUpdate,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        await session.commit()
        async with pin_deadline(), request.app.state.history.use_capture(project_id, job_id):
            await authenticated(request, session)
            job = await checked_job(
                session, actor, project_id, job_id, lock=True, action="investigation.write"
            )
            saved = await saved_row(session, job)
            groups = pin_groups(saved.state) if saved else []
            original = next((group for group in groups if group["id"] == pin_id), None)
            if original is None:
                raise not_found()
            saved = await revise(session, job, payload.expected_revision)
            replacement = {**original, "description": payload.description}
            conditions = [
                InvestigationBookmark.project_id == project_id,
                InvestigationBookmark.job_id == job_id,
            ]
            if payload.events is not None:
                conditions.append(InvestigationBookmark.id.not_in(original["bookmark_ids"]))
                replacement["bookmark_ids"] = [str(uuid4()) for _ in payload.events]
            groups = [replacement if group["id"] == pin_id else group for group in groups]
            count, retained_bytes = (
                await session.execute(
                    select(
                        func.count(),
                        func.coalesce(
                            func.sum(func.octet_length(InvestigationBookmark.context)), 0
                        ),
                    ).where(*conditions)
                )
            ).one()
            if payload.events is not None and count + len(payload.events) > 1000:
                raise DomainError(
                    "LIMIT_REACHED", "This investigation has reached its bookmark limit.", 429
                )
            byte_count = retained_bytes + len(json.dumps(groups, ensure_ascii=True).encode())
            rows = []
            created = services.utc_now_us()
            for event, bookmark_id in zip(
                payload.events or [],
                replacement["bookmark_ids"] if payload.events is not None else [],
                strict=True,
            ):
                context_input = HistoricalContextInput.model_validate(
                    event.model_dump(by_alias=True, exclude={"event_id"})
                )
                context = await historical_context(
                    session, actor, project_id, job_id, event.event_id, context_input
                )
                byte_count += len(json.dumps(context, ensure_ascii=True).encode())
                if byte_count > 33_554_432:
                    raise DomainError(
                        "LIMIT_REACHED",
                        "Pinned context exceeds the 32 MiB investigation budget.",
                        413,
                    )
                anchor = next(item["event"] for item in context["items"] if item["is_anchor"])
                rows.append(
                    InvestigationBookmark(
                        project_id=project_id,
                        job_id=job_id,
                        id=bookmark_id,
                        owner_user_id=actor.user_id,
                        event_id=event.event_id,
                        reference_event_id=event.event_id,
                        annotation="",
                        pin_context=True,
                        context=context,
                        process_name_snapshot=anchor["process_name_snapshot"],
                        server_name_snapshot=anchor["server_name_snapshot"],
                        created_us=created,
                    )
                )
                await asyncio.sleep(0)
            if byte_count > 33_554_432:
                raise DomainError(
                    "LIMIT_REACHED", "Pinned context exceeds the 32 MiB investigation budget.", 413
                )
            await authenticated(request, session)
            if payload.events is not None:
                await session.execute(
                    delete(InvestigationBookmark).where(
                        InvestigationBookmark.project_id == project_id,
                        InvestigationBookmark.job_id == job_id,
                        InvestigationBookmark.id.in_(original["bookmark_ids"]),
                    )
                )
                session.add_all(rows)
            saved.state = with_pin_groups(saved.state, groups)
            await session.flush()
            return await bookmark_response(session, job)

    @router.post(
        "/pins/{pin_id}/delete",
        response_model=BookmarkResponse,
        openapi_extra={"x-permission": "bookmark.write"},
    )
    async def delete_pin(
        project_id: str,
        job_id: str,
        pin_id: str,
        payload: RevisionInput,
        actor: Writer,
        session: Session,
    ) -> dict:
        job = await checked_job(
            session, actor, project_id, job_id, lock=True, action="investigation.write"
        )
        saved = await saved_row(session, job)
        groups = pin_groups(saved.state) if saved else []
        group = next((item for item in groups if item["id"] == pin_id), None)
        if group is None:
            raise not_found()
        saved = await revise(session, job, payload.expected_revision)
        await session.execute(
            delete(InvestigationBookmark).where(
                InvestigationBookmark.project_id == project_id,
                InvestigationBookmark.job_id == job_id,
                InvestigationBookmark.id.in_(group["bookmark_ids"]),
            )
        )
        saved.state = with_pin_groups(
            saved.state, [item for item in groups if item["id"] != pin_id]
        )
        await session.flush()
        return await bookmark_response(session, job)

    @router.post(
        "/bookmarks",
        response_model=BookmarkResponse,
        status_code=201,
        openapi_extra={"x-permission": "bookmark.write"},
    )
    async def create_bookmark(
        project_id: str,
        job_id: str,
        payload: BookmarkCreate,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        await session.commit()
        async with request.app.state.history.use_capture(project_id, job_id):
            await authenticated(request, session)
            job = await checked_job(
                session, actor, project_id, job_id, lock=True, action="investigation.write"
            )
            count = await session.scalar(
                select(func.count())
                .select_from(InvestigationBookmark)
                .where(
                    InvestigationBookmark.project_id == project_id,
                    InvestigationBookmark.job_id == job_id,
                )
            )
            if (count or 0) >= 1000:
                raise DomainError(
                    "LIMIT_REACHED", "This investigation has reached its bookmark limit.", 429
                )
            context_input = HistoricalContextInput.model_validate(
                payload.model_dump(
                    by_alias=True,
                    exclude={"expected_revision", "event_id", "annotation", "pin_context"},
                )
            )
            context = await historical_context(
                session, actor, project_id, job_id, payload.event_id, context_input
            )
            retained_bytes = await session.scalar(
                select(func.sum(func.octet_length(InvestigationBookmark.context))).where(
                    InvestigationBookmark.project_id == project_id,
                    InvestigationBookmark.job_id == job_id,
                )
            )
            saved = await saved_row(session, job)
            group_bytes = len(
                json.dumps(pin_groups(saved.state) if saved else [], ensure_ascii=True).encode()
            )
            if (
                payload.pin_context
                and (retained_bytes or 0)
                + group_bytes
                + len(json.dumps(context, ensure_ascii=True).encode())
                > 33_554_432
            ):
                raise DomainError(
                    "LIMIT_REACHED", "Pinned context exceeds the 32 MiB investigation budget.", 413
                )
            await revise(session, job, payload.expected_revision)
            anchor = next(item["event"] for item in context["items"] if item["is_anchor"])
            session.add(
                InvestigationBookmark(
                    project_id=project_id,
                    job_id=job_id,
                    id=str(uuid4()),
                    owner_user_id=actor.user_id,
                    event_id=payload.event_id,
                    reference_event_id=payload.event_id,
                    annotation=payload.annotation,
                    pin_context=payload.pin_context,
                    context=context if payload.pin_context else {},
                    process_name_snapshot=anchor["process_name_snapshot"],
                    server_name_snapshot=anchor["server_name_snapshot"],
                    created_us=services.utc_now_us(),
                )
            )
            await session.flush()
            return await bookmark_response(session, job)

    @router.patch(
        "/bookmarks/{bookmark_id}",
        response_model=BookmarkResponse,
        openapi_extra={"x-permission": "bookmark.write"},
    )
    async def edit_bookmark(
        project_id: str,
        job_id: str,
        bookmark_id: str,
        payload: BookmarkUpdate,
        actor: Writer,
        session: Session,
    ) -> dict:
        job = await checked_job(
            session, actor, project_id, job_id, lock=True, action="investigation.write"
        )
        row = await session.get(InvestigationBookmark, (project_id, job_id, bookmark_id))
        if row is None:
            raise not_found()
        if payload.pin_context and not row.context:
            raise DomainError(
                "CONTEXT_UNAVAILABLE", "Expand and bookmark the context again to pin it.", 409
            )
        await revise(session, job, payload.expected_revision)
        row.annotation, row.pin_context = payload.annotation, payload.pin_context
        if not row.pin_context:
            row.context = {}
        await session.flush()
        return await bookmark_response(session, job)

    @router.post(
        "/bookmarks/{bookmark_id}/delete",
        response_model=BookmarkResponse,
        openapi_extra={"x-permission": "bookmark.write"},
    )
    async def remove_bookmark(
        project_id: str,
        job_id: str,
        bookmark_id: str,
        payload: RevisionInput,
        actor: Writer,
        session: Session,
    ) -> dict:
        job = await checked_job(
            session, actor, project_id, job_id, lock=True, action="investigation.write"
        )
        row = await session.get(InvestigationBookmark, (project_id, job_id, bookmark_id))
        if row is None:
            raise not_found()
        saved = await revise(session, job, payload.expected_revision)
        await session.delete(row)
        groups = [
            {**group, "bookmark_ids": [key for key in group["bookmark_ids"] if key != bookmark_id]}
            for group in pin_groups(saved.state)
        ]
        saved.state = with_pin_groups(
            saved.state, [group for group in groups if group["bookmark_ids"]]
        )
        await session.flush()
        return await bookmark_response(session, job)

    @router.post(
        "/correlation",
        response_model=CorrelationResponse,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def correlation(
        project_id: str,
        job_id: str,
        payload: CorrelationInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        from inspector.app import SESSION_COOKIE
        from inspector.security import token_hash

        query_input = HistoricalQueryInput.model_validate(
            {
                **payload.model_dump(by_alias=True, exclude={"mode", "field", "value"}),
                "correlation": {
                    "mode": payload.mode,
                    "field": payload.field,
                    "value": payload.value,
                },
            }
        )
        await session.commit()
        async with request.app.state.history.use_capture(project_id, job_id):
            result = await historical_query(
                session,
                actor,
                project_id,
                job_id,
                query_input,
                supervisor=request.app.state.supervisor,
                login_hash=token_hash(request.cookies.get(SESSION_COOKIE, "")),
                idle_timeout_us=request.app.state.config.idle_timeout_us,
            )
            # A predecessor in physical source order with a later timestamp is an observed inversion.
            await session.commit()
            predecessor_row = aliased(HistoryEvent)
            predecessor_query = (
                select(predecessor_row.timestamp_us)
                .where(
                    predecessor_row.project_id == HistoryEvent.project_id,
                    predecessor_row.job_id == HistoryEvent.job_id,
                    predecessor_row.source_revision_id == HistoryEvent.source_revision_id,
                    predecessor_row.member_order == HistoryEvent.member_order,
                    predecessor_row.byte_start < HistoryEvent.byte_start,
                    predecessor_row.timestamp_us.is_not(None),
                )
                .order_by(predecessor_row.byte_start.desc())
                .limit(1)
                .correlate(HistoryEvent)
                .scalar_subquery()
            )
            predecessors: dict[str, int | None] = (
                {
                    row[0]: row[1]
                    for row in (
                        await session.execute(
                            select(HistoryEvent.event_id, predecessor_query).where(
                                HistoryEvent.project_id == project_id,
                                HistoryEvent.job_id == job_id,
                                HistoryEvent.event_id.in_(
                                    [event["event_id"] for event in result["items"]]
                                ),
                            )
                        )
                    ).all()
                }
                if result["items"]
                else {}
            )
            deltas = []
            previous = None
            for event in result["items"]:
                predecessor = predecessors.get(event["event_id"])
                stamp = event["timestamp_us"]
                deltas.append(
                    dict(
                        event_id=event["event_id"],
                        delta_us=stamp - previous
                        if stamp is not None and previous is not None
                        else None,
                        source_time_inversion=stamp is not None
                        and predecessor is not None
                        and stamp < predecessor,
                    )
                )
                previous = stamp
            await session.commit()
            await checked_job(session, await authenticated(request, session), project_id, job_id)
            return dict(
                **result,
                deltas=deltas,
                warning="Observed event-time deltas within this page are not network latency or proof of causality. Clock skew and source-order inversions may occur.",
            )

    @router.post(
        "/expire",
        response_model=ExpireResponse,
        openapi_extra={"x-permission": "investigation.write"},
    )
    async def expire(
        project_id: str,
        job_id: str,
        payload: RevisionInput,
        request: Request,
        actor: Writer,
        session: Session,
    ) -> dict:
        from inspector.history_retention import stage_cache

        async def perform() -> dict:
            async with request.app.state.history.use_capture(project_id, job_id):
                await authenticated(request, session)
                job = await checked_job(
                    session, actor, project_id, job_id, lock=True, action="investigation.write"
                )
                if job.status not in TERMINAL:
                    raise DomainError(
                        "COLLECTION_ACTIVE", "Stop collection before expiring its cache.", 409
                    )
                existing = await saved_row(session, job)
                if existing and existing.pinned:
                    raise DomainError(
                        "INVESTIGATION_PINNED",
                        "Unpin this investigation before expiring its source cache.",
                        409,
                    )
                saved = await revise(session, job, payload.expected_revision)
                path = request.app.state.history.cache_path(project_id, job_id, "unused").parent
                source_count = await session.scalar(
                    select(func.count())
                    .select_from(HistorySource)
                    .where(HistorySource.project_id == project_id, HistorySource.job_id == job_id)
                )
                staged = await asyncio.to_thread(
                    stage_cache,
                    path,
                    Path(request.app.state.config.cache_dir),
                    max(1, (source_count or 0) * 2),
                )
                try:
                    await session.execute(
                        update(InvestigationBookmark)
                        .where(
                            InvestigationBookmark.project_id == project_id,
                            InvestigationBookmark.job_id == job_id,
                        )
                        .values(reference_event_id=None)
                    )
                    for model in (HistoryCursor, HistoryDownload, HistoryEvent):
                        await session.execute(
                            delete(model).where(
                                model.project_id == project_id, model.job_id == job_id
                            )
                        )
                    await session.execute(
                        update(HistorySource)
                        .where(
                            HistorySource.project_id == project_id, HistorySource.job_id == job_id
                        )
                        .values(status="unavailable", error_code="SOURCE_EXPIRED")
                    )
                    saved.expired = True
                    job.snapshot_revision += 1
                    services.audit(
                        session,
                        actor,
                        "investigation.expire",
                        project_id,
                        job_id,
                        services.utc_now_us(),
                    )
                    await session.commit()
                except BaseException:
                    try:
                        await session.rollback()
                    finally:
                        if staged is not None:
                            await asyncio.to_thread(staged.restore)
                    raise
                READ_CACHE.invalidate(project_id, job_id)
                pending = False
                if staged:
                    try:
                        await asyncio.to_thread(staged.remove)
                    except (OSError, DomainError):
                        pending = True
                return dict(
                    project_id=project_id,
                    investigation_id=job_id,
                    revision=saved.revision,
                    availability="unavailable",
                    cache_cleanup_pending=pending,
                )

        await session.commit()
        task = asyncio.create_task(perform())
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
            task.result()
            raise

    @router.get(
        "/sources/{source_id}/provenance",
        response_model=SourceDetails,
        openapi_extra={"x-permission": "investigation.read"},
    )
    async def provenance(
        project_id: str,
        job_id: str,
        source_id: str,
        request: Request,
        actor: Actor,
        session: Session,
    ) -> dict:
        await checked_job(session, actor, project_id, job_id)
        source = await session.get(HistorySource, (project_id, job_id, source_id))
        if source is None:
            raise not_found()
        stats = (
            await session.execute(
                select(
                    func.count(),
                    func.count(HistoryEvent.timestamp_us),
                    func.min(HistoryEvent.timestamp_us),
                    func.max(HistoryEvent.timestamp_us),
                ).where(
                    HistoryEvent.project_id == project_id,
                    HistoryEvent.job_id == job_id,
                    HistoryEvent.source_revision_id == source_id,
                )
            )
        ).one()
        path = request.app.state.history.cache_path(project_id, job_id, source.cache_name)
        import stat

        from inspector.history_retention import checked_directory, checked_stat

        def available() -> bool:
            try:
                return checked_directory(
                    path.parent, Path(request.app.state.config.cache_dir)
                ) and stat.S_ISREG(checked_stat(path).st_mode)
            except (OSError, DomainError):
                return False

        await session.commit()
        raw_available = await asyncio.to_thread(available)
        await authenticated(request, session)
        await checked_job(session, actor, project_id, job_id)
        ranges = source.manifest.get("captured_ranges", [])
        if not ranges and source.status == "completed" and raw_available:
            ranges = [
                dict(
                    byte_start=0,
                    byte_end=source.downloaded_bytes,
                    cache_start=0,
                    cache_end=source.downloaded_bytes,
                )
            ]
        return dict(
            project_id=project_id,
            investigation_id=job_id,
            source_revision_id=source.id,
            process_id=source.process_id,
            remote_path=source.remote_path,
            kind=source.kind,
            status=source.status,
            error_code=source.error_code,
            checksum=source.checksum,
            downloaded_bytes=source.downloaded_bytes,
            expanded_bytes=source.expanded_bytes,
            retained_event_count=stats[0],
            parse_issue_count=stats[0] - stats[1],
            observed_from=format_time(stats[2]) if stats[2] is not None else None,
            observed_to=format_time(stats[3]) if stats[3] is not None else None,
            captured_ranges=ranges,
            raw_bytes_available=raw_available,
            limitations=[
                "Observed timestamp extrema do not prove continuous time coverage.",
                "Only configured candidates and proven captured byte ranges are represented.",
                *(
                    [
                        "Live recording retains partial ranges; hidden rotations or rewrites may be missed."
                    ]
                    if source.manifest.get("transport") == "live"
                    else []
                ),
                *(
                    ["Original source bytes have expired; retained index/context is separate."]
                    if not raw_available
                    else []
                ),
            ],
        )

    return router
