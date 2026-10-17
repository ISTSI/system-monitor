import json
from pathlib import Path

import httpx
import pytest

from inspector.app import create_app, transaction
from inspector.config import parse_config

ROOT = Path(__file__).resolve().parents[3]
ORIGIN = "https://inspector.internal.example:8443"


class TestSupervisor:
    __test__ = False

    async def healthy(self):
        return True


@pytest.fixture
async def client():
    config = parse_config((ROOT / "examples/deployment-policy.example.yaml").read_bytes(), {})
    app = create_app(config)
    app.state.supervisor = TestSupervisor()  # Only boundary tests; no persistence is simulated.

    async def no_database():
        yield None

    app.dependency_overrides[transaction] = no_database
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        yield client


async def test_anonymous_catalogue_is_denied_before_database(client):
    response = await client.get("/api/v1/projects")
    assert response.status_code == 401
    assert "items" not in response.json()


async def test_login_csrf_origin_and_actual_body_size(client):
    assert (await client.post("/api/v1/auth/login", json={})).status_code == 403
    csrf = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
    assert len(csrf) == 43
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "someone", "password": "private-password"},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 403
    response = await client.post(
        "/api/v1/auth/login", content=b"x" * 16385, headers={"Origin": ORIGIN}
    )
    assert response.status_code == 413


async def test_cookie_flags_safe_validation_no_password_reflection(client):
    response = await client.get("/api/v1/auth/csrf")
    cookie = response.headers["set-cookie"].lower()
    assert all(value in cookie for value in ("secure", "httponly", "samesite=strict", "path=/"))
    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": ORIGIN},
        json={"username": "x", "password": "secret-value", "owner_user_id": "fake"},
    )
    assert response.status_code == 422
    assert "secret-value" not in response.text


async def test_wrong_host_and_unsafe_legacy_operations(client):
    assert (
        await client.get("/api/v1/projects", headers={"Host": "other.example"})
    ).status_code == 400
    for route in (
        "/api/v1/live-sessions",
        "/api/v1/jobs/x",
        "/api/v1/downloads/x",
        "/api/v1/set-current-project",
    ):
        assert (await client.get(route)).status_code == 404


async def test_health_fails_closed_without_supervisor():
    config = parse_config((ROOT / "examples/deployment-policy.example.yaml").read_bytes(), {})
    app = create_app(config)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        assert (await client.get("/api/v1/health/live")).status_code == 200
        assert (await client.get("/api/v1/health/ready")).status_code == 503
        assert (await client.get("/api/v1/projects")).status_code == 503


def test_every_project_route_declares_a_contract_permission():
    config = parse_config((ROOT / "examples/deployment-policy.example.yaml").read_bytes(), {})
    schema = create_app(config).openapi()
    actions = json.loads((ROOT / "contracts/rbac-policy.json").read_text())["actions"]
    for path, methods in schema["paths"].items():
        if path.startswith("/api/v1/projects"):
            for operation in methods.values():
                assert operation["x-permission"] in actions
