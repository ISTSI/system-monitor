"""Read-only TLS readiness/image checks for the retained local test installations."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import urllib.request

import local_mariadb as local


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-stage5", action="store_true")
    args = parser.parse_args()
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(local.ROOT / ".cache/docker"))
    local.require_local_docker()
    evidence = local.ROOT / "verification/stage-5"
    original = json.loads((evidence / "runner-build.json").read_text("utf-8"))["original_runner_id"]
    current = local.run(
        ["docker", "image", "inspect", "system-inspector-runner:local", "--format", "{{.Id}}"],
        label="Inspect retained runner image",
    ).strip()
    assert current == original
    stage1 = json.loads(
        (local.ROOT / "verification/stage-1/docker/20-offline-images.json").read_text("utf-8")
    )
    stage2_runner = stage1["saved_and_loaded_image_ids"]["system-inspector-runner:local"]
    stage5_runner = "sha256:668bfc011a595c63ea4f88c29eea56c326828662dbba1cd20a18a4eacdfcd8a8"
    prepared = (
        json.loads((evidence / "deployment-prepared.json").read_text("utf-8"))
        if args.installed_stage5
        else None
    )
    checks = []
    for port, stage, container, expected in (
        (8444, "stage2-browser", "system-inspector-local-runtime-1", stage2_runner),
        (
            8445,
            "stage3-browser",
            "system-inspector-local-runtime-stage3-1",
            stage5_runner if args.installed_stage5 else original,
        ),
    ):
        certificate = local.ROOT / ".secrets" / stage / "localhost-cert.pem"
        context = ssl.create_default_context(cafile=str(certificate))
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context)
        )
        with opener.open(f"https://localhost:{port}/api/v1/health/ready", timeout=10) as response:
            assert response.status == 200
        image = local.run(
            ["docker", "inspect", container, "--format", "{{.Image}}"],
            label="Inspect retained application image",
        ).strip()
        assert image == expected
        if port == 8444 and prepared is not None:
            identity = local.run(
                ["docker", "inspect", container, "--format", "{{.Id}} {{.State.StartedAt}}"],
                label="Verify retained 8444 container was not restarted or replaced",
            ).split()
            assert identity == [
                prepared["other_app_container_id"],
                prepared["other_app_started_at"],
            ]
        checks.append(
            {
                "origin": f"https://localhost:{port}",
                "readiness": 200,
                "tls_certificate_and_hostname_verified": True,
                "container": container,
                "image_id": image,
                "expected_image_verified": image == expected,
                **(
                    {"authorized_stage5_image_verified": True}
                    if port == 8445 and args.installed_stage5
                    else {"original_image_preserved": True}
                ),
            }
        )
    fixture_states = {
        name: local.run(
            ["docker", "inspect", name, "--format", "{{.State.Status}}"],
            label="Read completed synthetic fixture state",
        ).strip()
        for name in (
            "system-inspector-local-stage5-browser-1",
            "system-inspector-local-stage5-sftp-1",
        )
    }
    if args.installed_stage5:
        assert set(fixture_states.values()) == {"exited"}
    filename = (
        "deployment-preservation.json" if args.installed_stage5 else "retained-installations.json"
    )
    (evidence / filename).write_text(
        json.dumps(
            {
                "read_only": True,
                "installed_stage5": args.installed_stage5,
                "original_runner_tag_preserved": current == original,
                "checks": checks,
                "authenticated_or_state_changing_requests": 0,
                "completed_stage5_fixture_state": fixture_states,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "Installed Stage5 on 8445 and preserved 8444/runner/stopped fixtures verified."
        if args.installed_stage5
        else "Retained 8444/8445 readiness, TLS hostname/certificate and original images verified."
    )


if __name__ == "__main__":
    main()
