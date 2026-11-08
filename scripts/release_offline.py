"""Build and verify three-image offline artifacts without deploying them.

Use --connected only on a preparation host to download locked build packages.
Producing archives never certifies untested operating systems or acceptance gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import local_mariadb as local
import verify_stage7_build

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist/system-inspector-0.1.0-offline-rc3"
NGINX = "docker.io/library/nginx:1.30.6-alpine@sha256:959ae6b898852db82e5b29b929388e59914f42be0a8f4d44c89a4c1f53b49208"
EVIDENCE = ROOT / "verification/stage-8"


class ReleaseError(ValueError):
    """Public error text contains no secret values."""


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def safe_path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or relative.is_absolute()
        or any(p in {"", ".", ".."} for p in name.split("/"))
    ):
        raise ReleaseError("Unsafe release member path.")
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()) or any(
        p.is_symlink() for p in (path, *path.parents) if p != root.parent
    ):
        raise ReleaseError("Release paths must remain inside their directory without links.")
    return path


def run(argv: list[str], *, timeout: int = 600, name: str | None = None) -> str:
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout, check=False)
    if name:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / (name + ".log")).write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise ReleaseError(
            f"Release command failed (exit {result.returncode}); see {name or 'local command'} evidence."
        )
    return result.stdout.decode("utf-8", errors="replace")


def docker_setup() -> None:
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".cache/docker"))
    if os.environ.get("BUILDX_BUILDER") or os.environ.get("BUILDKIT_HOST"):
        raise ReleaseError("Use the local Docker builder without endpoint overrides.")
    local.require_local_docker()


def inspect(reference: str) -> dict[str, Any]:
    info = json.loads(run(["docker", "image", "inspect", reference]))[0]
    if info["Os"] != "linux" or info["Architecture"] != "amd64":
        raise ReleaseError("Only the tested Linux amd64 release architecture is supported.")
    return info


def build_images(*, connected: bool) -> dict[str, str]:
    run([sys.executable, "scripts/build_stage8.py"], name="wheel-build")
    run([sys.executable, "scripts/collect_backend_notices.py"], name="backend-notices")
    run([sys.executable, "scripts/frontend.py", "notices"], name="frontend-notices")
    verify_stage7_build.BUILD_RELATIVE = Path(".state/stage8-build")
    build = verify_stage7_build.verify_build(ROOT)
    if not build["verified"]:
        raise ReleaseError("Current sources do not match the isolated wheel.")
    identity = build["sources_sha256"][:12]
    context = ROOT / f".state/stage8-build/contexts/{time.time_ns()}"
    (context / "backend/dist").mkdir(parents=True)
    for name in ("uv.lock", "pyproject.toml"):
        shutil.copyfile(ROOT / "backend" / name, context / "backend" / name)
    shutil.copyfile(
        ROOT / ".state/stage8-build/backend/dist" / build["wheel"],
        context / "backend/dist" / build["wheel"],
    )
    shutil.copyfile(
        ROOT / "deploy/local-mariadb/runner-bootstrap.requirements.txt",
        context / "bootstrap.requirements.txt",
    )
    shutil.copytree(ROOT / "third_party", context / "notices")
    shutil.copyfile(ROOT / "deploy/app/release.Dockerfile", context / "Dockerfile")
    proxy_context = context / "proxy"
    (proxy_context / "deploy/offline/proxy").mkdir(parents=True)
    shutil.copyfile(
        ROOT / "deploy/offline/proxy/nginx.conf", proxy_context / "deploy/offline/proxy/nginx.conf"
    )
    shutil.copyfile(ROOT / "deploy/offline/proxy/Dockerfile", proxy_context / "Dockerfile")
    refs = {
        "app": f"system-inspector-app:0.1.0-stage8-{identity}",
        "proxy": f"system-inspector-proxy:0.1.0-stage8-{digest(ROOT / 'deploy/offline/proxy/nginx.conf')[:12]}",
        "mariadb": json.loads((ROOT / "deploy/local-mariadb/images.lock.json").read_text("utf-8"))[
            "images"
        ]["mariadb"]["reference"],
    }
    inspect(refs["mariadb"])
    inspect(NGINX)
    network = "default" if connected else "none"
    for role, directory, dockerfile in (
        ("app", context, context / "Dockerfile"),
        ("proxy", proxy_context, proxy_context / "Dockerfile"),
    ):
        run(
            [
                "docker",
                "build",
                "--pull=false",
                "--network=" + network,
                "--platform=linux/amd64",
                "--file",
                str(dockerfile),
                "--tag",
                refs[role],
                str(directory),
            ],
            name=role + "-image-build",
        )
    write_json(EVIDENCE / "images.json", refs)
    return refs


def image_inventory(role: str, reference: str) -> dict[str, Any]:
    command = [
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=64",
        "--memory=256m",
    ]
    if role == "app":
        script = (
            "import importlib.metadata as m,json,subprocess,pathlib,hashlib,inspector;"
            "root=pathlib.Path(inspector.__file__).parent;"
            "print(json.dumps({'python':[{'name':d.metadata['Name'],'version':d.version,'license':d.metadata.get('License-Expression') or d.metadata.get('License')} for d in m.distributions()],"
            "'runtime_files':{'inspector/'+p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts},"
            "'os':subprocess.check_output(['dpkg-query','-W','-f=${Package}\\t${Version}\\n'],text=True)}))"
        )
        return json.loads(run([*command, "--entrypoint=python", reference, "-c", script]))
    if role == "mariadb":
        packages = run(
            [*command, "--entrypoint=dpkg-query", reference, "-W", "-f=${Package}\t${Version}\n"]
        )
    else:
        packages = run([*command, "--entrypoint=/sbin/apk", reference, "info", "-v"])
    return {"os": packages}


def assemble(output: Path, refs: dict[str, str]) -> dict[str, Any]:
    verify_stage7_build.BUILD_RELATIVE = Path(".state/stage8-build")
    build = verify_stage7_build.verify_build(ROOT)
    if not build["verified"]:
        raise ReleaseError("Sources changed after the image build; rebuild the candidate.")
    if output.is_symlink() or output.exists():
        raise ReleaseError(
            "Release destination already exists; verification never overwrites a release."
        )
    output.mkdir(parents=True)
    (output / "images").mkdir()
    images = []
    inventories = {}
    for role in ("app", "proxy", "mariadb"):
        reference = refs[role]
        details = inspect(reference)
        archive = output / "images" / (role + "-0.1.0-linux-amd64.tar")
        run(
            ["docker", "image", "save", "--output", str(archive), reference],
            name=role + "-image-save",
        )
        images.append(
            dict(
                role=role,
                reference=reference,
                image_id=details["Id"],
                archive=archive.relative_to(output).as_posix(),
                sha256=digest(archive),
                size_bytes=archive.stat().st_size,
                platform="linux/amd64",
            )
        )
        inventories[role] = image_inventory(role, reference)
        if role == "app":
            with zipfile.ZipFile(
                ROOT / ".state/stage8-build/backend/dist" / build["wheel"]
            ) as wheel:
                expected = {
                    name: hashlib.sha256(wheel.read(name)).hexdigest()
                    for name in wheel.namelist()
                    if name.startswith("inspector/") and not name.endswith("/")
                }
            if inventories[role]["runtime_files"] != expected:
                raise ReleaseError(
                    "Application image runtime files differ from the verified wheel."
                )
    shutil.copytree(
        ROOT / "deploy/offline",
        output / "runtime",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    runtime_readme = output / "runtime/README.md"
    runtime_readme.write_text(
        runtime_readme.read_text("utf-8").replace(
            "../../docs/OFFLINE_OPERATIONS.md", "../docs/OFFLINE_OPERATIONS.md"
        ),
        encoding="utf-8",
    )
    shutil.copytree(ROOT / "third_party", output / "notices")
    (output / "notices/images").mkdir()
    license_paths = {
        "app": [
            "usr/share/doc",
            "usr/share/common-licenses",
            "usr/local/lib/python3.13/LICENSE.txt",
        ],
        "proxy": ["usr/share/doc", "usr/share/licenses"],
        "mariadb": ["usr/share/doc", "usr/share/common-licenses"],
    }
    for row in images:
        target = output / "notices/images" / (row["role"] + "-base-notices.tar")
        with target.open("xb") as stream:
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--pull=never",
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges:true",
                    "--entrypoint=tar",
                    row["image_id"],
                    "-C",
                    "/",
                    "-cf",
                    "-",
                    *license_paths[row["role"]],
                ],
                stdout=stream,
                stderr=subprocess.PIPE,
                timeout=120,
                check=False,
            )
        if result.returncode:
            raise ReleaseError("Failed to preserve the image's original license notices.")
    (output / "notices/README.txt").write_text(
        "Original installed Python/npm notices are in backend/ and frontend/. images/ preserves original OS, CPython, nginx/module and MariaDB copyright/license documents from the exact shipped images. Image archive links are preserved without dereferencing. SBOM package versions come from installed images and the npm lock. No fonts from the build host are distributed. No new paid component is required. This inventory is not a vulnerability scan or a substitute for the recipient's distribution/license review.\n",
        encoding="utf-8",
    )
    for name in (
        "OFFLINE_OPERATIONS.md",
        "18_RELEASE_QUALIFICATION.md",
        "01_PRODUCT_REQUIREMENTS.md",
        "12_TRACEABILITY.md",
    ):
        source = ROOT / "docs" / name
        if source.is_file():
            (output / "docs").mkdir(exist_ok=True)
            shutil.copyfile(source, output / "docs" / name)
    write_json(output / "inventory.json", inventories)
    frontend = json.loads((ROOT / "third_party/frontend/inventory.json").read_text("utf-8"))[
        "packages"
    ]
    components = []
    for package in inventories["app"]["python"]:
        components.append(
            dict(
                type="library",
                name=package["name"],
                version=package["version"],
                purl=f"pkg:pypi/{package['name'].lower().replace('_', '-')}@{package['version']}",
            )
        )
    for package in frontend:
        components.append(
            dict(
                type="library",
                name=package["name"],
                version=package["version"],
                scope="excluded" if package["development"] else "required",
                purl=f"pkg:npm/{package['name'].replace('@', '%40')}@{package['version']}",
            )
        )
    for image in images:
        components.append(
            dict(
                type="container",
                name="system-inspector-" + image["role"],
                version=image["image_id"],
                hashes=[{"alg": "SHA-256", "content": image["sha256"]}],
            )
        )
        for line in inventories[image["role"]]["os"].splitlines():
            if "\t" in line:
                name, version = line.split("\t", 1)
            else:
                match = re.fullmatch(r"(.+)-([0-9][^-]*-r[0-9]+)", line)
                if match is None:
                    raise ReleaseError("Cannot parse an installed OS package for the SBOM.")
                name, version = match.groups()
            components.append(
                {
                    "type": "library",
                    "name": name,
                    "version": version,
                    "properties": [
                        {"name": "system-inspector:image-role", "value": image["role"]},
                        {
                            "name": "system-inspector:package-manager",
                            "value": "apk" if image["role"] == "proxy" else "dpkg",
                        },
                    ],
                }
            )
    write_json(
        output / "sbom.cdx.json",
        {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": datetime.now(UTC).isoformat(),
                "component": {
                    "type": "application",
                    "name": "System Inspector",
                    "version": "0.1.0",
                },
            },
            "components": components,
            "properties": [
                {"name": "system-inspector:os-package-inventory", "value": "inventory.json"}
            ],
        },
    )
    report = {
        "qualification": "incomplete",
        "reason": "See verification/stage-8 and operator guide. Native Ubuntu/Rocky, clean-daemon transfer and blocked-Internet browser/SSH/restore acceptance require actual execution.",
        "runtime_downloads": False,
        "vulnerability_scan": "Not performed; dependency inventory is not a CVE scan.",
        "license_distribution_review": "Actual bundled notices preserved; complete corresponding-source/source-offer coverage is not established.",
        "native_platforms": {
            "Ubuntu 24.04 LTS": "untested",
            "Rocky Linux 9 rootless SELinux": "untested",
        },
    }
    qualification = EVIDENCE / "qualification.json"
    if qualification.is_file():
        report["executed_checks"] = json.loads(qualification.read_text("utf-8"))
    for name in (
        "build.json",
        "qualification.json",
        "runtime/recovery.json",
        "runtime/cold-start.json",
    ):
        source = EVIDENCE / name
        if source.is_file():
            destination = output / "verification" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    write_json(output / "TEST_REPORT.json", report)
    files = {
        p.relative_to(output).as_posix(): digest(p)
        for p in sorted(output.rglob("*"))
        if p.is_file()
    }
    manifest = {
        "schema_version": 1,
        "application": "System Inspector",
        "version": "0.1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "expected_schema": "0016_optional_connection",
        "images": images,
        "files": files,
        "qualification": report["qualification"],
        "source_build": json.loads((EVIDENCE / "build.json").read_text("utf-8")),
    }
    write_json(output / "manifest.json", manifest)
    checksums = dict(files, **{"manifest.json": digest(output / "manifest.json")})
    (output / "SHA256SUMS").write_text(
        "".join(f"{value}  {name}\n" for name, value in sorted(checksums.items())), encoding="utf-8"
    )
    verify(output)
    write_json(
        EVIDENCE / "release.json",
        {
            "directory": str(output),
            "manifest_sha256": digest(output / "manifest.json"),
            "images": images,
            "qualification": "incomplete",
        },
    )
    return manifest


def verify(output: Path) -> None:
    if output.is_symlink() or not output.is_dir():
        raise ReleaseError("Release directory is missing or linked.")
    manifest = json.loads((output / "manifest.json").read_text("utf-8"))
    files = manifest.get("files")
    if manifest.get("schema_version") != 1 or not isinstance(files, dict) or not files:
        raise ReleaseError("Unsupported release manifest.")
    roles = {row["role"] for row in manifest.get("images", [])}
    if roles != {"app", "proxy", "mariadb"} or len(manifest["images"]) != 3:
        raise ReleaseError("Exactly three release images are required.")
    for name, expected in files.items():
        path = safe_path(output, name)
        if (
            not re.fullmatch(r"[a-f0-9]{64}", expected)
            or not path.is_file()
            or digest(path) != expected
        ):
            raise ReleaseError("Release file checksum mismatch: " + name)
    for row in manifest["images"]:
        if files.get(row["archive"]) != row["sha256"] or not re.fullmatch(
            r"sha256:[a-f0-9]{64}", row["image_id"]
        ):
            raise ReleaseError("Image identity/checksum differs from file inventory.")
    sums = (output / "SHA256SUMS").read_text("utf-8").splitlines()
    expected_sums = {**files, "manifest.json": digest(output / "manifest.json")}
    if len(sums) != len(expected_sums) or set(sums) != {
        f"{value}  {name}" for name, value in expected_sums.items()
    }:
        raise ReleaseError("Release SHA256SUMS is inconsistent.")
    actual = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    if actual != set(files) | {"manifest.json", "SHA256SUMS"}:
        raise ReleaseError("Release contains unrecorded files.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", nargs="?", default="build", choices=("build", "assemble", "verify")
    )
    parser.add_argument(
        "--connected",
        action="store_true",
        help="Allow locked package downloads during image BUILD only; never pull base images.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    started = time.monotonic()
    try:
        if args.command == "verify":
            verify(args.output)
        else:
            docker_setup()
            refs = (
                build_images(connected=args.connected)
                if args.command == "build"
                else json.loads((EVIDENCE / "images.json").read_text("utf-8"))
            )
            assemble(args.output, refs)
    except (
        ReleaseError,
        local.SetupError,
        OSError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        print(f"Offline release failed: {error}", file=sys.stderr)
        return 1
    print(
        f"Offline release {args.command} passed in {time.monotonic() - started:.1f}s. Qualification status is recorded in TEST_REPORT.json."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
