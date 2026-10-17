"""Record the actual frontend quality/build commands without network access."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "verification/stage-1/frontend"


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    records = []
    for name in ("lint", "typecheck", "api:check", "build"):
        command = [sys.executable, str(ROOT / "scripts/frontend.py"), name]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        log = name.replace(":", "-") + ".log"
        (OUTPUT / log).write_text(result.stdout + result.stderr, encoding="utf-8")
        records.append(
            {"command": command, "cwd": str(ROOT), "exit_code": result.returncode, "log": log}
        )
        print(f"{name}: {'PASS' if result.returncode == 0 else 'FAIL'}")
    (OUTPUT / "commands.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return int(any(record["exit_code"] != 0 for record in records))


if __name__ == "__main__":
    sys.exit(main())
