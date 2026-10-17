"""An in-flight SSH setup check stops promptly when its authority changes.

MariaDB owns authentication, credentials, trust and configuration in these tests.
The intentionally blocked transport isolates cancellation from remote timing;
real network trust ordering is covered by test_ssh_transport.py.
"""

import asyncio
import time

import pytest
from sqlalchemy.exc import SQLAlchemyError
from test_ssh_access import (
    OBSERVED,
    approve,
    base,
    enable_vault,
    inspect,
    isolated_admin,
    save,
    seed,
)

from inspector import ssh_transport

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]


@pytest.mark.parametrize(
    "change", ["password", "trust", "logout", "config", "database_error", "database_timeout"]
)
async def test_blocked_ssh_check_is_cancelled_within_two_seconds_of_invalidation(
    foundation, tmp_path, monkeypatch, change
):
    manager = enable_vault(foundation, tmp_path)
    started, stopped, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def observed(*args, **kwargs):
        return OBSERVED

    async def blocked_connection(*args, **kwargs):
        started.set()
        try:
            await release.wait()
            return {"ssh": True, "sftp": True}
        finally:
            stopped.set()

    monkeypatch.setattr(ssh_transport, "inspect_key", observed)
    monkeypatch.setattr(ssh_transport, "test_connection", blocked_connection)
    account = (
        await isolated_admin(foundation)
        if change == "logout"
        else foundation.database.administrator
    )
    async with foundation.client(account) as client:
        config = await seed(client, foundation.project_a)
        saved = await save(client, foundation.project_a)
        assert saved.status_code == 200, saved.text
        inspected = await inspect(client, foundation.project_a)
        assert inspected.status_code == 200, inspected.text
        approved = await approve(client, foundation.project_a, inspected.json()["inspection_token"])
        assert approved.status_code == 200, approved.text
        request = asyncio.create_task(
            client.post(base(foundation.project_a) + "/test", json={"expected_config_revision": 2})
        )
        try:
            await asyncio.wait_for(started.wait(), timeout=3)
            expected_status = 409
            if change == "password":
                changed = await save(client, foundation.project_a, "synthetic-replacement", 1)
            elif change == "trust":
                changed = await client.post(
                    base(foundation.project_a) + "/revoke",
                    json={"expected_config_revision": 2, "expected_trust_revision": 1},
                )
            elif change == "logout":
                changed = await client.post("/api/v1/auth/logout", json={})
                expected_status = 401
            elif change == "config":
                config["connections"][0]["name"] = "Synthetic changed configuration"
                changed = await client.put(
                    f"/api/v1/projects/{foundation.project_a}/topology",
                    json={"expected_revision": 2, "config": config},
                )
            else:
                # Fail only the guard's fresh DB authorization boundary. Other
                # fixtures and application readiness retain their real MariaDB.
                async def unavailable_database(*args, **kwargs):
                    if change == "database_timeout":
                        await asyncio.Event().wait()
                    raise SQLAlchemyError("synthetic unavailable database detail")

                monkeypatch.setattr(manager, "_actor", unavailable_database)
                changed = None
                expected_status = 503
            if changed is not None:
                assert changed.status_code == 200, changed.text
            invalidated_at = time.monotonic()
            await asyncio.wait_for(stopped.wait(), timeout=2)
            response = await asyncio.wait_for(request, timeout=0.5)
            assert time.monotonic() - invalidated_at < 2
            assert not release.is_set(), "The transport completed without cancellation"
            assert response.status_code == expected_status, response.text
            assert "synthetic unavailable database detail" not in response.text
            assert manager._network_active == 0
        finally:
            release.set()
            if not request.done():
                request.cancel()
            await asyncio.gather(request, return_exceptions=True)
