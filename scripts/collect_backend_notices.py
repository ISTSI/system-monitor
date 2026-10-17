"""Collect installed wheel license notices; run with the locked backend interpreter."""

import json
from importlib.metadata import distributions
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
destination = ROOT / "third_party" / "backend"
destination.mkdir(parents=True, exist_ok=True)
inventory = []
for distribution in sorted(distributions(), key=lambda item: item.metadata["Name"].lower()):
    name = distribution.metadata["Name"]
    if name == "system-inspector":
        continue
    notices = []
    for file in distribution.files or []:
        if any(
            part.lower() in {"licenses", "license", "copying"} for part in file.parts
        ) or file.name.lower().startswith(("license", "notice", "copying")):
            source = Path(distribution.locate_file(file))
            if source.is_file():
                relative = Path(name.lower().replace("_", "-")) / Path(*file.parts)
                if ".." in relative.parts:
                    raise ValueError("Unexpected notice path in distribution")
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                notices.append(relative.as_posix())
    inventory.append(
        {
            "name": name,
            "version": distribution.version,
            "license_expression": distribution.metadata.get("License-Expression")
            or distribution.metadata.get("License"),
            "license_classifiers": [
                value
                for value in distribution.metadata.get_all("Classifier", [])
                if value.startswith("License ::")
            ],
            "notices": notices,
        }
    )
(destination / "inventory.json").write_text(
    json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
)
print(f"Collected installed notices for {len(inventory)} backend/build/test dependencies.")
