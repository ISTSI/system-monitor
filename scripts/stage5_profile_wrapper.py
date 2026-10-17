"""Temporary bounded diagnostics for only the generated Stage 05 backend.

Outputs static method names, durations, query aggregates, sequence numbers and
server timestamps. SQL text, parameters, cookies, filters and log data are never
recorded. The normal fixture command must be restored after diagnostic use.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import logging
import re
import runpy
import sys
import time
from datetime import UTC, datetime

from sqlalchemy import event
from sqlalchemy.engine import Engine

from inspector import auth
from inspector.config import load_config
from inspector.live import LiveManager
from inspector.live_engine import LiveEngine
from inspector.source_access import SourceAccess
from inspector.ssh_access import SSHAccess

_LOGGER = logging.getLogger("stage5.profile")
_SCOPES: contextvars.ContextVar[tuple[dict, ...]] = contextvars.ContextVar("s5_profile", default=())
_EXPIRES = time.monotonic() + 90
_REMAINING = 2500


def emit(message: str, *values: object) -> None:
    global _REMAINING
    if _REMAINING > 0 and time.monotonic() <= _EXPIRES:
        _REMAINING -= 1
        _LOGGER.warning("Stage5 diagnostic " + message, *values)


def measured(owner: object, name: str) -> None:
    original = getattr(owner, name)
    label = f"{getattr(owner, '__name__', 'auth')}.{name}"

    @functools.wraps(original)
    async def wrapped(*args: object, **kwargs: object) -> object:
        began = time.monotonic()
        scope = {"queries": []}
        token = _SCOPES.set((*_SCOPES.get(), scope))
        error = "none"
        try:
            return await original(*args, **kwargs)
        except BaseException as failure:
            error = type(failure).__name__
            raise
        finally:
            elapsed = (time.monotonic() - began) * 1000
            queries = scope["queries"]
            emit(
                "method=%s elapsed_ms=%.3f sql_count=%d sql_sum_ms=%.3f sql_max_ms=%.3f error=%s",
                label,
                elapsed,
                len(queries),
                sum(queries),
                max(queries, default=0),
                error,
            )
            _SCOPES.reset(token)

    setattr(owner, name, wrapped)


def before_query(_connection, _cursor, _statement, _parameters, context, _executemany):
    context._stage5_profile_began = time.monotonic()


def after_query(_connection, _cursor, _statement, _parameters, context, _executemany):
    elapsed = (time.monotonic() - context._stage5_profile_began) * 1000
    for scope in _SCOPES.get():
        scope["queries"].append(elapsed)


async def loop_lag() -> None:
    while time.monotonic() < _EXPIRES:
        samples = []
        for _ in range(25):
            expected = time.monotonic() + 0.02
            await asyncio.sleep(0.02)
            samples.append(max(0, (time.monotonic() - expected) * 1000))
        emit(
            "loop_samples=%d loop_mean_lag_ms=%.3f loop_max_lag_ms=%.3f",
            len(samples),
            sum(samples) / len(samples),
            max(samples),
        )


def main() -> None:
    config = load_config()
    if config.public_origin != "https://localhost:8447" or not re.fullmatch(
        r"inspector_test_s5_web_[a-f0-9]{10}", config.database.name
    ):
        raise SystemExit("Diagnostics require the isolated Stage 05 scope.")
    for owner, names in (
        (LiveManager, ("_fresh_guard", "_socket_row")),
        (SourceAccess, ("prepare_many_in_transaction",)),
        (SSHAccess, ("_actor",)),
        (auth, ("authenticate",)),
        (LiveEngine, ("_record_shared", "_poll")),
    ):
        for name in names:
            measured(owner, name)
    event.listen(Engine, "before_cursor_execute", before_query)
    event.listen(Engine, "after_cursor_execute", after_query)
    original_frame, original_init = LiveEngine._frame, LiveManager.__init__

    def frame(engine, session, kind, payload):
        result = original_frame(engine, session, kind, payload)
        if kind == "events":
            project = session.sources[0].source.project_id
            label = {"stage5-fixture-a": "A", "stage5-fixture-b": "B"}.get(project, "other")
            emit(
                "publication system=%s seq=%d published_at=%s",
                label,
                session.seq,
                datetime.now(UTC).isoformat(),
            )
        return result

    def initialize(manager, *args, **kwargs):
        original_init(manager, *args, **kwargs)
        manager._stage5_diagnostic_lag = asyncio.create_task(loop_lag())

    LiveEngine._frame = frame
    LiveManager.__init__ = initialize
    sys.argv = ["uvicorn", *sys.argv[1:]]
    runpy.run_module("uvicorn", run_name="__main__")


if __name__ == "__main__":
    main()
