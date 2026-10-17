"""Every implemented protected route declares a known action and enforces CSRF on writes."""

import json
from pathlib import Path

from fastapi.routing import APIRoute

from inspector.app import create_app, protected_write
from inspector.config import parse_config

ROOT = Path(__file__).resolve().parents[3]


def calls(dependency):
    return {dependency.call} | {call for child in dependency.dependencies for call in calls(child)}


def routes_in(router):
    for route in router.routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):
            yield from routes_in(route.original_router)


def test_all_protected_routes_bind_declared_actions_and_mutation_csrf():
    config = parse_config((ROOT / "examples/deployment-policy.example.yaml").read_bytes(), {})
    app = create_app(config)
    actions = json.loads((ROOT / "contracts/rbac-policy.json").read_text(encoding="utf-8"))[
        "actions"
    ]
    checked = set()
    for route in routes_in(app):
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/v1/"):
            continue
        if (
            route.path.startswith(("/api/v1/health/", "/api/v1/auth/"))
            or route.path == "/api/v1/ui/bootstrap"
        ):
            continue
        action = (route.openapi_extra or {}).get("x-permission")
        assert action in actions, f"Undeclared action on {route.path}"
        if route.methods - {"GET", "HEAD", "OPTIONS"}:
            assert protected_write in calls(route.dependant), (
                f"CSRF boundary missing on {route.path}"
            )
        checked.add(route.path)
    assert {
        "/api/v1/admin/users",
        "/api/v1/me/password",
        "/api/v1/me/preferences",
        "/api/v1/admin/settings",
        "/api/v1/projects/{project_id}/archive",
    } <= checked
