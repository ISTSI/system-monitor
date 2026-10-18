"""Read-only TLS/image/container checks for retained local installations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import urllib.request
from datetime import UTC, datetime

import local_mariadb as local


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--baseline", action="store_true")
    modes.add_argument("--installed-stage6", action="store_true")
    args = parser.parse_args()
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(local.ROOT / ".cache/docker"))
    local.require_local_docker()
    output = local.ROOT / "verification/stage-6"
    output.mkdir(parents=True, exist_ok=True)
    baseline_path = output / "retained-baseline.json"
    if args.baseline and baseline_path.exists():
        raise local.SetupError(
            "The retained-installation baseline already exists; it was preserved."
        )
    prior = local.ROOT / "verification/stage-5"
    prepared = json.loads((prior / "deployment-prepared.json").read_text("utf-8"))
    prior_images = json.loads(
        (local.ROOT / "verification/stage-1/docker/20-offline-images.json").read_text("utf-8")
    )
    stage6_build = json.loads((output / "runner-build.json").read_text("utf-8"))
    original = local.run(
        ["docker", "image", "inspect", "system-inspector-runner:local", "--format", "{{.Id}}"],
        label="Inspect preserved original runner tag",
    ).strip()
    assert original == stage6_build["original_runner_id"]
    expected_stage5 = json.loads((prior / "deployment-installation.json").read_text("utf-8"))[
        "image"
    ]
    installed = json.loads((prior / "deployment-installation.json").read_text("utf-8"))
    audited = json.loads((prior / "deployment-audit.json").read_text("utf-8"))["runtime"]
    if args.installed_stage6:
        prepared = json.loads((output / "deployment-prepared.json").read_text("utf-8"))
        installed = json.loads((output / "deployment-installation.json").read_text("utf-8"))
        audited = json.loads((output / "deployment-audit-post.json").read_text("utf-8"))["runtime"]
        expected_stage5 = stage6_build["stage6_runner_id"]
    checks = []
    for port, stage, container, expected in [
        (
            8444,
            "stage2-browser",
            "system-inspector-local-runtime-1",
            prior_images["saved_and_loaded_image_ids"]["system-inspector-runner:local"],
        ),
        (8445, "stage3-browser", "system-inspector-local-runtime-stage3-1", expected_stage5),
    ]:
        certificate = local.ROOT / ".secrets" / stage / "localhost-cert.pem"
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(
                context=ssl.create_default_context(cafile=str(certificate))
            ),
        )
        with opener.open(f"https://localhost:{port}/api/v1/health/ready", timeout=10) as response:
            assert response.status == 200
        with opener.open(f"https://localhost:{port}/", timeout=10) as response:
            index_hash = hashlib.sha256(response.read()).hexdigest()
        if port == 8445:
            assert index_hash == installed["package"]["frontend_assets"]["index.html"]
        elif args.installed_stage6:
            assert index_hash == prepared["other_app_index_sha256"]
        template = '{"container_id":"{{.Id}}","image_id":"{{.Image}}","started_at":"{{.State.StartedAt}}","restart_count":{{.RestartCount}},"state":"{{.State.Status}}"}'
        identity = json.loads(
            local.run(
                ["docker", "inspect", container, "--format", template],
                label="Inspect retained application container metadata",
            )
        )
        assert identity["image_id"] == expected and identity["state"] == "running"
        if port == 8444:
            assert identity["container_id"] == prepared["other_app_container_id"]
            assert identity["started_at"] == prepared["other_app_started_at"]
        else:
            assert identity["container_id"] == audited["container_id"]
            assert identity["started_at"] == audited["started_at"]
        checks.append(
            {
                "origin": f"https://localhost:{port}",
                "readiness": 200,
                "tls_certificate_and_hostname_verified": True,
                "index_sha256": index_hash,
                "container": container,
                **identity,
            }
        )
    fixtures = {
        name: local.run(
            [
                "docker",
                "inspect",
                "system-inspector-local-" + name + "-1",
                "--format",
                "{{.State.Status}}",
            ],
            label="Inspect isolated synthetic fixture state",
        ).strip()
        for name in ("stage5-browser", "stage5-sftp", "stage6-browser", "stage6-sftp")
    }
    assert fixtures["stage5-browser"] == fixtures["stage5-sftp"] == "exited"
    if not args.baseline and not args.installed_stage6:
        baseline = json.loads(baseline_path.read_text("utf-8"))
        assert checks == baseline["checks"]
        assert fixtures["stage6-browser"] == fixtures["stage6-sftp"] == "exited"
    if args.installed_stage6:
        assert set(fixtures.values()) == {"exited"}
    result = {
        "measured_at": datetime.now(UTC).isoformat(),
        "read_only": True,
        "authenticated_or_state_changing_requests": 0,
        "original_runner_tag_preserved": True,
        "checks": checks,
        "synthetic_fixture_states": fixtures,
        "container_image_starttime_and_restart_count_preserved": not args.baseline
        and not args.installed_stage6,
        "installed_stage6": args.installed_stage6,
        "untouched_8444_preserved_since_deployment_preparation": args.installed_stage6,
        "authorized_8445_stage6_artifact_verified": args.installed_stage6,
        "prior_stage5_evidence_modified": False,
    }
    destination = (
        baseline_path
        if args.baseline
        else output / "deployment-preservation.json"
        if args.installed_stage6
        else output / "retained-installations.json"
    )
    if args.installed_stage6 and destination.exists():
        raise local.SetupError("Existing deployment preservation evidence was retained.")
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        "Retained 8444/8445 TLS readiness, assets, images and container metadata verified without mutations."
    )


if __name__ == "__main__":
    main()
