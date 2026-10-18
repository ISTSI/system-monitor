"""Bounded, non-persisting Administrator parser tests using the collection engine."""

import copy
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from inspector import project_config, topology
from inspector.domain import ID_PATTERN, Principal
from inspector.errors import DomainError
from inspector.log_engine.core import (
    CorrelationMarker,
    ParserConfig,
    extract_metadata,
    parse_timestamp,
)


class ParserTestInput(topology.StrictInput):
    project_id: str = Field(pattern=ID_PATTERN)
    expected_revision: int = Field(ge=1, le=2_147_483_646)
    parser: dict[str, Any]
    sample: str = Field(max_length=65_536)


class ParserTestLine(topology.StrictInput):
    line_number: int
    original_line: str
    timestamp_original: str | None
    timestamp_utc: str | None
    timestamp_us: str | None
    metadata: dict[str, str]
    error: str | None


class ParserTestResponse(topology.StrictInput):
    project_id: str
    revision: int
    parser_id: str
    lines: list[ParserTestLine]
    valid_count: int
    error_count: int


def preview(document: dict, parser: dict, sample: str) -> list[dict]:
    """Never write the sample, invoke a regex from it, or invent a failed time."""
    try:
        sample_bytes = sample.encode("utf-8")
    except UnicodeError:
        raise DomainError(
            "PARSER_SAMPLE_ENCODING", "The sample must contain valid UTF-8 text.", 422
        ) from None
    if len(sample_bytes) > 65_536:
        raise DomainError("PARSER_SAMPLE_LIMIT", "Use a sample of at most 64 KiB.", 422)
    # Match the collector's physical LF framing. Unicode separators and bare CR
    # are log text, and a final newline does not create an extra empty event.
    parts = sample.split("\n")
    lines = [line.removesuffix("\r") for line in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    if len(lines) > 100 or any(len(line.encode("utf-8")) > 4096 for line in lines):
        raise DomainError(
            "PARSER_SAMPLE_LIMIT", "Use at most 100 physical lines, each at most 4 KiB.", 422
        )
    proposed = copy.deepcopy(document)
    proposed["parsers"] = [p for p in proposed["parsers"] if p["id"] != parser.get("id")]
    proposed["parsers"].append(parser)
    project_config.validate_project(proposed)
    config = ParserConfig(**parser["timestamp"])
    markers = tuple(CorrelationMarker(**marker) for marker in parser.get("correlation_markers", []))
    result = []
    for number, line in enumerate(lines, 1):
        parsed = parse_timestamp(line, config)
        result.append(
            dict(
                line_number=number,
                original_line=line,
                timestamp_original=parsed.original,
                timestamp_utc=parsed.utc,
                timestamp_us=str(parsed.micros) if parsed.micros is not None else None,
                metadata=extract_metadata(line, markers),
                error=None
                if parsed.micros is not None
                else "No valid UTC event timestamp; diagnostic lane.",
            )
        )
    return result


def build_diagnostics_router(
    transaction: Any, authenticated: Any, protected_write: Any
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}")
    Session = Annotated[AsyncSession, Depends(transaction, scope="function")]
    Writer = Annotated[Principal, Depends(protected_write)]

    @router.post(
        "/parsers/test",
        response_model=ParserTestResponse,
        openapi_extra={"x-permission": "parser.test"},
    )
    async def test_parser(
        project_id: str, payload: ParserTestInput, actor: Writer, session: Session, request: Request
    ) -> dict:
        actor, project, state = await topology.context(session, actor, project_id, "parser.test")
        if payload.project_id != project_id:
            raise DomainError("PROJECT_MISMATCH", "Request system must match the route.", 422)
        topology.check_revision(project, payload.expected_revision)
        document = copy.deepcopy(state.config)
        await session.commit()
        lines = await topology.cpu_work(lambda: preview(document, payload.parser, payload.sample))
        # Work can finish after an account/revision change; check before disclosing its result.
        session.expire_all()
        actor = await authenticated(request, session)
        _, project, _ = await topology.context(session, actor, project_id, "parser.test")
        topology.check_revision(project, payload.expected_revision)
        valid = sum(item["error"] is None for item in lines)
        return dict(
            project_id=project.id,
            revision=project.revision,
            parser_id=payload.parser["id"],
            lines=lines,
            valid_count=valid,
            error_count=len(lines) - valid,
        )

    return router
