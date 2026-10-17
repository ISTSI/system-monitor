"""Record Stage 05 verification against fresh, isolated local MariaDB schemas.

The existing guarded provisioner creates DML-only runtime and separate migration
accounts. No installed app, existing schema, remote target or image is changed.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import time

import verify_stage3


def linux_unit() -> int:
    import local_mariadb as local
    from stage5_local import checked_setup

    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(local.ROOT / ".cache/docker"))
    local.require_local_docker()
    override = checked_setup()
    original = local.run

    def recorded(
        argv: list[str], *, label: str, data: str | None = None, timeout: int = 180
    ) -> str:
        started = time.monotonic()
        result = subprocess.run(
            argv,
            input=data,
            cwd=local.ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        (verify_stage3.OUTPUT / "linux-live-unit.log").write_text(
            result.stdout + result.stderr, encoding="utf-8"
        )
        (verify_stage3.OUTPUT / "linux-live-unit-command.json").write_text(
            json.dumps(
                {
                    "argv": argv,
                    "cwd": str(local.ROOT),
                    "exit_code": result.returncode,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if result.returncode:
            raise local.SetupError("Linux live tests failed; see retained verification output.")
        return result.stdout

    local.run = recorded
    try:
        print(
            local.compose(
                "run",
                "--rm",
                "--no-deps",
                "integration",
                "python",
                "-m",
                "pytest",
                "tests/unit/test_live_engine.py",
                "tests/unit/test_live_sftp.py",
                "tests/unit/test_ws_transport.py",
                "-q",
                "-s",
                "-p",
                "no:cacheprovider",
                override=override,
            ),
            end="",
        )
        return 0
    finally:
        local.run = original


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["checks", "integration", "upgrade", "live", "linux-unit"]
    )
    parser.add_argument("--suffix", help="Fresh disposable schema suffix; never reuse one")
    parser.add_argument("--match", help="Optional pytest -k selection for the live command")
    args = parser.parse_args()
    # Never retag or rebuild the installed services' original runner image.
    os.environ["INSPECTOR_RUNNER_IMAGE"] = "system-inspector-runner:stage5"
    verify_stage3.OUTPUT = verify_stage3.ROOT / "verification/stage-5"
    verify_stage3.OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.command == "checks":
        return verify_stage3.checks()
    if args.command == "linux-unit":
        return linux_unit()
    if args.command != "live":
        suffix = args.suffix or (
            "s2_upgrade_" + secrets.token_hex(4)
            if args.command == "upgrade"
            else "s5_" + secrets.token_hex(5)
        )
        return verify_stage3.integration(suffix, upgrade=args.command == "upgrade")

    # Keep the same empty-schema and local-daemon guards as the complete suite,
    # while selecting only the live contract during focused development.
    import local_mariadb as local

    original = local.compose

    def focused(*arguments: str, **kwargs: object) -> str:
        if arguments[-1:] == ("integration",):
            arguments = (
                *arguments,
                "python",
                "-m",
                "pytest",
                "tests/integration/test_live.py",
                "tests/integration/test_live_filter_fence.py",
                "tests/integration/test_live_terminal_fence.py",
                "-v",
                "-rs",
                "-s",
                "-p",
                "no:cacheprovider",
                *(("-k", args.match) if args.match else ()),
            )
        return original(*arguments, **kwargs)

    local.compose = focused
    try:
        return verify_stage3.integration(args.suffix or "s5_live_" + secrets.token_hex(4))
    finally:
        local.compose = original


if __name__ == "__main__":
    raise SystemExit(main())
