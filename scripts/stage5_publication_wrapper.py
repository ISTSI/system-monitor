"""Temporary Stage 05 publication/guard timing only; no SQL or input logging."""

import functools
import logging
import re
import runpy
import sys
import time
from datetime import UTC, datetime

from inspector.config import load_config
from inspector.live import LiveManager
from inspector.live_engine import LiveEngine

_LOGGER = logging.getLogger("stage5.publication")
_EXPIRES = time.monotonic() + 90
_REMAINING = 300


def emit(message, *values):
    global _REMAINING
    if _REMAINING > 0 and time.monotonic() < _EXPIRES:
        _REMAINING -= 1
        _LOGGER.warning("Stage5 publication diagnostic " + message, *values)


def system(project):
    return {"stage5-fixture-a": "A", "stage5-fixture-b": "B"}.get(project, "other")


def main():
    config = load_config()
    if (
        config.public_origin != "https://localhost:8447"
        or config.database.host != "mariadb"
        or config.database.port != 3306
        or not re.fullmatch(r"inspector_test_s5_web_[a-f0-9]{10}", config.database.name)
    ):
        raise SystemExit("Publication diagnostics require the isolated Stage 05 scope.")
    original_frame, original_guard = LiveEngine._frame, LiveManager._fresh_guard

    def frame(engine, session, kind, payload):
        result = original_frame(engine, session, kind, payload)
        if kind == "events":
            received = [event["metadata"].get("received_at", "") for event in payload["events"]]
            received = [value for value in received if re.fullmatch(r"[0-9:T.\-]+Z", value)]
            emit(
                "publication system=%s seq=%d published_at=%s received_min=%s received_max=%s",
                system(session.sources[0].source.project_id),
                session.seq,
                datetime.now(UTC).isoformat(),
                min(received, default="none"),
                max(received, default="none"),
            )
        return result

    @functools.wraps(original_guard)
    async def guard(manager, actor, project, *args):
        began = time.monotonic()
        error = "none"
        try:
            return await original_guard(manager, actor, project, *args)
        except BaseException as failure:
            error = type(failure).__name__
            raise
        finally:
            emit(
                "guard system=%s elapsed_ms=%.3f error=%s",
                system(project),
                (time.monotonic() - began) * 1000,
                error,
            )

    LiveEngine._frame, LiveManager._fresh_guard = frame, guard
    sys.argv = ["uvicorn", *sys.argv[1:]]
    runpy.run_module("uvicorn", run_name="__main__")


if __name__ == "__main__":
    main()
