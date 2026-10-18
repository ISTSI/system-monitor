"""Run Linux unit/package checks in a non-root, offline, read-only local runner."""

import argparse
import json
import os
import re
import subprocess
import tarfile
import time
from pathlib import Path

import local_mariadb as local


def source_archive() -> Path:
    """Own source files only, with repository (non-executable) POSIX file modes."""
    archive = local.ROOT / ".cache/stage7-linux-source.tar"
    archive.parent.mkdir(parents=True, exist_ok=True)
    ignored = {
        ".venv",
        "__pycache__",
        "node_modules",
        "dist",
        "web",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
    manifest = json.loads((local.ROOT / "PACKAGE_MANIFEST.json").read_text("utf-8"))
    files = {local.ROOT / entry["path"] for entry in manifest["files"]}
    for name in (
        "backend",
        "contracts",
        "examples",
        "fixtures",
        "scripts",
        "tools",
        "tests",
        "docs",
        "prompts",
        "progress",
        "assets",
        "frontend",
        "third_party",
    ):
        for directory, children, names in os.walk(local.ROOT / name):
            children[:] = [child for child in children if child not in ignored]
            files.update(
                Path(directory) / filename
                for filename in names
                if not filename.endswith((".pyc", ".pyo"))
            )
    files.add(local.ROOT / "deploy/local-mariadb/compose.yaml")
    files.update(
        local.ROOT / name
        for name in subprocess.check_output(
            ["git", "ls-files", "deploy"], cwd=local.ROOT, text=True
        ).splitlines()
        if not name.endswith(".local")
    )
    for path in local.ROOT.iterdir():
        if path.is_file() and (
            path.suffix in {".md", ".json"} or path.name in {"Makefile", ".gitignore"}
        ):
            files.add(path)
    # Include real local Markdown targets (including sanitized verification receipts).
    # Package validation also verifies those links in its temporary source copy.
    for source in list(files):
        if source.suffix != ".md":
            continue
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", source.read_text("utf-8")):
            if link.startswith(("http:", "https:", "mailto:", "#")):
                continue
            target = (source.parent / link.split("#", 1)[0]).resolve()
            if not target.is_relative_to(local.ROOT.resolve()) or any(
                part in {".secrets", ".state", ".cache"}
                for part in target.relative_to(local.ROOT.resolve()).parts
            ):
                raise local.SetupError("Unsafe linked test source; nothing staged.")
            if target.is_dir():
                candidate = next(
                    (
                        item
                        for item in sorted(target.rglob("*.json"))
                        if item.is_file() and not item.is_symlink()
                    ),
                    None,
                )
                if candidate is not None:
                    files.add(candidate)
            elif target.is_file():
                files.add(target)
    with tarfile.open(archive, "w") as bundle:
        for path in sorted(files):
            relative = path.resolve().relative_to(local.ROOT.resolve())
            if (
                path.is_symlink()
                or any(
                    part.startswith(".secrets") or part in {"secrets", ".state", ".git"}
                    for part in relative.parts
                )
                or path.name.endswith(".local.yaml")
            ):
                raise local.SetupError("Unsafe test source path; no container started.")
            info = bundle.gettarinfo(str(path), arcname=relative.as_posix())
            info.mode = 0o644
            with path.open("rb") as stream:
                bundle.addfile(info, stream)
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-only", action="store_true")
    args = parser.parse_args()
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(local.ROOT / ".cache/docker"))
    local.require_local_docker()
    archive = source_archive()
    argv = [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--pull=never",
        "--network=none",
        "--user=10001:10001",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=128",
        "--memory=1g",
        "--tmpfs=/tmp:mode=1777",
        "--workdir=/tmp",
        "--env=PYTHONPATH=/tmp/stage7-source/backend/src",
        "--env=PYTHONDONTWRITEBYTECODE=1",
        "--entrypoint=python",
    ]
    # Stream our own generated source archive. No host filesystem/secret/daemon mounts.
    argv.extend(
        [
            "system-inspector-runner:stage7",
            "-c",
            (
                "import os,pathlib,subprocess,sys,tarfile\n"
                "base=pathlib.Path('/tmp/stage7-source');base.mkdir()\n"
                "with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:\n"
                " for member in archive:\n"
                "  target=(base/member.name).resolve()\n"
                "  if not member.isfile() or not target.is_relative_to(base): raise ValueError('Invalid test source')\n"
                "  target.parent.mkdir(parents=True,exist_ok=True)\n"
                "  with archive.extractfile(member) as source: target.write_bytes(source.read())\n"
                "  target.chmod(0o644)\n"
                "os.chdir(base)\n"
                + (
                    "a=0\n"
                    if args.package_only
                    else "a=subprocess.call([sys.executable,'-m','pytest','backend/tests/unit','-q','-p','no:cacheprovider'])\n"
                )
                + "b=subprocess.call([sys.executable,'-m','unittest','discover','-s','tests/package','-q'])\n"
                "sys.exit(bool(a or b))\n"
            ),
        ]
    )
    started = time.monotonic()
    with archive.open("rb") as stream:
        result = subprocess.run(
            argv, stdin=stream, cwd=local.ROOT, capture_output=True, timeout=300, check=False
        )
    output = local.ROOT / "verification/stage-7"
    output.mkdir(parents=True, exist_ok=True)
    name = "linux-package-only" if args.package_only else "linux-unit-package"
    (output / f"{name}.log").write_bytes(result.stdout + result.stderr)
    (output / f"{name}-command.json").write_text(
        json.dumps(
            dict(
                argv=argv,
                exit_code=result.returncode,
                elapsed_seconds=round(time.monotonic() - started, 3),
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Linux unit/package checks: exit {result.returncode}; see retained verification log.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
