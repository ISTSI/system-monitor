#!/usr/bin/env python3
"""Create synthetic local ingestion benchmarks, never live/production log data."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path, help="New or empty output directory")
    parser.add_argument("--size-mib", type=float, default=20.0, help="Approximate total log bytes in MiB")
    parser.add_argument("--processes", type=int, default=5)
    args = parser.parse_args()
    if not math.isfinite(args.size_mib) or not 0 < args.size_mib <= 1024:
        parser.error("--size-mib must be greater than 0 and no more than 1024")
    if not 1 <= args.processes <= 60:
        parser.error("--processes must be between 1 and 60")
    output = args.output_dir.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("Refusing to overwrite a nonempty directory or existing file")
    output.mkdir(parents=True, exist_ok=True)
    per_file = math.ceil(args.size_mib * 1024 * 1024 / args.processes)
    start = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    sources = []
    for number in range(args.processes):
        target = output / f"process-{number + 1:02d}.log"
        count = size = 0
        checksum = hashlib.sha256()
        with target.open("xb") as handle:
            while size < per_file:
                timestamp = (start + timedelta(microseconds=count * 1000)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                message = (f"{timestamp} INFO request_id=REQ-{count % 1000:04d} "
                           f"process=load-{number + 1:02d} sequence={count} phase=synthetic "
                           "payload=" + "x" * 96 + "\n").encode("utf-8")
                handle.write(message); checksum.update(message)
                count += 1; size += len(message)
        sources.append({"process_id": f"load-{number + 1:02d}", "file": target.name,
                        "bytes": size, "lines": count, "sha256": checksum.hexdigest()})
    result = {"synthetic": True, "purpose": "local historical ingestion benchmark; not a live-rate model",
              "total_bytes": sum(s["bytes"] for s in sources), "sources": sources}
    (output / "generated-manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output), "total_bytes": result["total_bytes"],
                      "processes": len(sources)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
