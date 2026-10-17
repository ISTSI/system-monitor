"""Connected preparation only: resolve official Linux image digests without a daemon."""

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {"mariadb": "mariadb:11.8.9", "python": "python:3.13.16-slim"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        required=True,
        help="Explicitly contact Docker Hub; never used at runtime.",
    )
    parser.parse_args()
    docker_config = ROOT / ".cache" / "docker-public-registry"
    docker_config.mkdir(parents=True, exist_ok=True)
    evidence = []
    images = {}
    for name, tag in IMAGES.items():
        result = subprocess.run(
            ["docker", "--config", str(docker_config), "manifest", "inspect", "--verbose", tag],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode:
            raise SystemExit(
                f"Cannot resolve official {name} image (exit {result.returncode}); existing lock preserved."
            )
        manifests = json.loads(result.stdout)
        selected = [
            entry
            for entry in manifests
            if entry["Descriptor"].get("platform", {}) == {"architecture": "amd64", "os": "linux"}
        ]
        if len(selected) != 1:
            raise SystemExit(
                f"Expected one linux/amd64 manifest for {name}; existing lock preserved."
            )
        reference = selected[0]["Ref"]
        images[name] = {
            "tag": tag,
            "reference": reference,
            "platform": "linux/amd64",
            "registry_resolved": True,
            "container_tested": False,
        }
        evidence.append(
            {
                "tag": tag,
                "selected_reference": reference,
                "descriptors": [entry["Descriptor"] for entry in manifests],
            }
        )
        print(f"Resolved {tag} for linux/amd64.")
    output = ROOT / "deploy/local-mariadb/images.lock.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "images": images,
                "scope": "Registry metadata only; no image pull or container test implied.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    verification = ROOT / "verification/mariadb-setup"
    verification.mkdir(parents=True, exist_ok=True)
    (verification / "registry-manifests.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
