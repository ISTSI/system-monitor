"""Run the pinned web toolchain without a machine-wide Node installation."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
NODE_VERSION = "24.22.0"
NPM_VERSION = "11.19.1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "dev",
            "build",
            "lint",
            "typecheck",
            "test",
            "e2e",
            "api:generate",
            "api:check",
            "notices",
            "install",
        ],
    )
    parser.add_argument("--connected", action="store_true")
    args, extra = parser.parse_known_args()
    local = ROOT / ".toolchains" / f"node-v{NODE_VERSION}-win-x64"
    node = local / "node.exe"
    if node.is_file():
        npm = local / "node_modules" / "npm" / "bin" / "npm-cli.js"
    else:
        located = shutil.which("node")
        if located is None:
            parser.error("Node 24.22.0 is required; see frontend/README.md for connected setup.")
        node = Path(located)
        npm_command = shutil.which("npm")
        if npm_command is None:
            parser.error("npm is unavailable.")
        npm = Path(npm_command).resolve()
        if npm.suffix != ".js":
            npm = node.parent.parent / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js"
        if not npm.is_file():
            npm = node.parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    version = subprocess.check_output([str(node), "--version"], text=True).strip()
    if version != f"v{NODE_VERSION}" or not npm.is_file():
        parser.error("The recorded Node 24.22.0/npm toolchain is required.")
    npm_version = subprocess.check_output([str(node), str(npm), "--version"], text=True).strip()
    if npm_version != NPM_VERSION:
        parser.error("The recorded npm 11.19.1 toolchain is required.")
    env = os.environ.copy()
    env["PATH"] = str(node.parent) + os.pathsep + env.get("PATH", "")
    env["npm_config_cache"] = str(ROOT / ".cache" / "npm")
    env["npm_config_update_notifier"] = "false"
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(ROOT / ".cache" / "playwright")
    if args.command == "install":
        if not args.connected:
            parser.error("Dependency download requires explicit --connected.")
        command = [str(node), str(npm), "ci", "--ignore-scripts", "--no-audit", "--no-fund"]
    else:
        command = [str(node), str(npm), "run", args.command]
        if extra:
            command.extend(["--", *extra])
    return subprocess.call(command, cwd=FRONTEND, env=env)


if __name__ == "__main__":
    sys.exit(main())
