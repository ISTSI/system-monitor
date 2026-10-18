"""The bundled browser data must exactly match Python's backend casefold."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_generated_browser_casefold_matches_locked_python_for_every_unicode_scalar():
    specification = importlib.util.spec_from_file_location(
        "generate_casefold", ROOT / "scripts/generate_casefold.py"
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    assert (ROOT / "frontend/src/unicodeCasefold.ts").read_text("utf-8") == module.generated()
