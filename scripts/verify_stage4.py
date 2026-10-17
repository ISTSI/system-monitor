"""Record Stage 04 checks with isolated local SSH/SFTP and MariaDB fixtures.

Database checks reuse the guarded disposable-schema runner. Linux unit tests
reuse the existing local image and guarded fixture configuration without starting
the serving application, pulling images or mutating a database schema.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import time
from pathlib import Path

import verify_stage3


def _secret_values(services: dict) -> set[str]:
    """Keep mounted runtime secrets in memory solely for output redaction."""
    from local_mariadb import ROOT, SetupError

    values: set[str] = set()

    def collect(document: object) -> None:
        if isinstance(document, dict):
            for name, value in document.items():
                if (
                    name
                    in {
                        "password",
                        "password_hash",
                        "csrf_token",
                        "token",
                        "private_key",
                    }
                    and isinstance(value, str)
                    and value
                ):
                    values.add(value)
                collect(value)
        elif isinstance(document, list):
            for value in document:
                collect(value)

    private_root = (ROOT / ".secrets").resolve()
    for mounted in services["services"]["runtime-stage3"].get("secrets", []):
        name = mounted if isinstance(mounted, str) else mounted["source"]
        source = services["secrets"][name]
        original_path = Path(source["file"])
        path = original_path.resolve()
        if (
            not path.is_relative_to(private_root)
            or original_path.is_symlink()
            or not path.is_file()
        ):
            raise SetupError("A mounted local runtime secret has an unexpected file boundary.")
        payload = path.read_bytes()
        if not payload:
            continue
        values.add(payload.hex())
        values.add(base64.b64encode(payload).decode("ascii"))
        try:
            decoded = payload.decode("utf-8").rstrip("\r\n")
        except UnicodeError:
            continue
        if decoded:
            values.add(decoded)
        if path.suffix == ".json":
            collect(json.loads(decoded))
    return values


def linux_unit() -> int:
    import local_mariadb as local
    from stage4_local import load_existing

    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(local.ROOT / ".cache/docker"))
    local.require_local_docker()
    _, override, services, _, _ = load_existing()
    runtime = services["services"]["runtime-stage3"]
    if runtime.get("pull_policy") != "never" or runtime.get("entrypoint") != []:
        raise local.SetupError("The local unit runner must disable image pulls and its entrypoint.")
    redactions = _secret_values(services)

    def sanitized(value: str) -> str:
        for secret in sorted(redactions, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        return value

    original = local.run

    def recorded(
        argv: list[str], *, label: str, data: str | None = None, timeout: int = 180
    ) -> str:
        if argv[:2] != ["docker", "compose"]:
            return original(argv, label=label, data=data, timeout=timeout)
        started = time.monotonic()
        try:
            result = subprocess.run(
                argv,
                cwd=local.ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as error:
            stdout = (error.stdout or b"").decode("utf-8", errors="replace")
            stderr = (error.stderr or b"").decode("utf-8", errors="replace")
            code = 124
        output = sanitized(stdout + stderr)
        (verify_stage3.OUTPUT / "linux-unit.log").write_text(output, encoding="utf-8")
        (verify_stage3.OUTPUT / "linux-unit-command.json").write_text(
            json.dumps(
                {
                    "argv": argv,
                    "cwd": str(local.ROOT),
                    "container_cwd": "/workspace/backend",
                    "exit_code": code,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if code:
            raise local.SetupError("Linux unit tests failed; see sanitized linux-unit.log.")
        return sanitized(stdout)

    local.run = recorded
    try:
        output = local.compose(
            "run",
            "--rm",
            "--no-deps",
            "--volume",
            f"{(local.ROOT / 'contracts').as_posix()}:/workspace/contracts:ro",
            "--volume",
            f"{(local.DEPLOY / 'compose.yaml').as_posix()}:/workspace/deploy/local-mariadb/compose.yaml:ro",
            "runtime-stage3",
            "python",
            "-m",
            "pytest",
            "tests/unit",
            "-q",
            "-p",
            "no:cacheprovider",
            override=override,
            timeout=300,
        )
        print(output, end="")
        return 0
    finally:
        local.run = original


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["checks", "integration", "upgrade", "linux-unit"])
    parser.add_argument("--suffix")
    args = parser.parse_args()
    verify_stage3.OUTPUT = verify_stage3.ROOT / "verification/stage-4"
    verify_stage3.OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.command in {"integration", "upgrade"}:
        return verify_stage3.integration(args.suffix, upgrade=args.command == "upgrade")
    if args.command == "linux-unit":
        from local_mariadb import SetupError

        try:
            return linux_unit()
        except SetupError as error:
            parser.exit(1, str(error) + "\n")
        except (OSError, ValueError, KeyError):
            parser.exit(1, "Local Linux unit verification failed; no secrets were printed.\n")
    return verify_stage3.checks()


if __name__ == "__main__":
    raise SystemExit(main())
