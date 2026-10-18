"""Read-only baseline/comparison of retained TLS applications and local runner tags."""

import argparse
import hashlib
import json
import os
import ssl
import urllib.request

import local_mariadb as local


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    if os.name == "nt":
        os.environ.setdefault("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
        os.environ.setdefault("DOCKER_CONFIG", str(local.ROOT / ".cache/docker"))
    local.require_local_docker()
    output = local.ROOT / "verification/stage-7"
    output.mkdir(parents=True, exist_ok=True)
    baseline = output / "retained-baseline.json"
    if args.baseline and baseline.exists():
        raise local.SetupError("Existing baseline preserved; choose comparison mode.")
    applications = []
    for port, stage, container in (
        (8444, "stage2-browser", "system-inspector-local-runtime-1"),
        (8445, "stage3-browser", "system-inspector-local-runtime-stage3-1"),
    ):
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(
                context=ssl.create_default_context(
                    cafile=str(local.ROOT / ".secrets" / stage / "localhost-cert.pem")
                )
            ),
        )
        with opener.open(f"https://localhost:{port}/api/v1/health/ready", timeout=10) as response:
            assert response.status == 200
        with opener.open(f"https://localhost:{port}/", timeout=10) as response:
            index_sha256 = hashlib.sha256(response.read()).hexdigest()
        identity = local.run(
            [
                "docker",
                "inspect",
                container,
                "--format",
                "{{.Id}} {{.Image}} {{.State.StartedAt}} {{.RestartCount}} {{.State.Status}}",
            ],
            label="Read retained application identity",
        ).strip()
        applications.append(
            dict(port=port, identity=identity, index_sha256=index_sha256, readiness=200)
        )
    runners = {
        tag: local.run(
            ["docker", "image", "inspect", "system-inspector-runner:" + tag, "--format", "{{.Id}}"],
            label="Read retained runner identity",
        ).strip()
        for tag in ("local", "stage6")
    }
    result = dict(applications=applications, runners=runners)
    if not args.baseline:
        assert json.loads(baseline.read_text("utf-8")) == result, "Retained application changed."
    target = baseline if args.baseline else output / "retained-comparison.json"
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        "PASS: retained TLS applications and runner identities "
        + ("recorded." if args.baseline else "preserved.")
    )


if __name__ == "__main__":
    main()
