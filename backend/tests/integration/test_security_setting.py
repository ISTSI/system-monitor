"""Administrator confirmation policy against MariaDB and synthetic read-only SSH."""

import asyncio
import copy
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import pytest_asyncio
from test_history import finished
from test_history_ssh import configure, copy_logs, enable_remote, endpoint, scope, start
from test_source_access import approval_body, configured, source_base

from inspector import services, ssh_files
from inspector.errors import DomainError
from inspector.foundation import initialize_settings
from inspector.persistence.models import (
    ApplicationSetting,
    ProjectCredentialBinding,
    SourceAccessApproval,
    SSHCredential,
    SSHHostTrust,
)
from inspector.security import token_hash

pytestmark = [pytest.mark.mariadb, pytest.mark.asyncio(loop_scope="session")]
SETTINGS = "/api/v1/admin/settings"


def settings_body(value, **changes):
    return {
        "expected_revision": value["revision"],
        "branding": value["branding"],
        "default_theme_mode": value["default_theme_mode"],
        **changes,
    }


async def set_policy(admin, required):
    current = await admin.get(SETTINGS)
    assert current.status_code == 200, current.text
    response = await admin.patch(
        SETTINGS, json=settings_body(current.json(), additional_security_measures=required)
    )
    assert response.status_code == 200, response.text
    assert response.json()["additional_security_measures"] is required
    return response.json()


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def restore_confirmation_policy(foundation):
    """The deployment setting is shared by every integration test's application."""
    async with foundation.client(foundation.database.administrator) as admin:
        current = await admin.get(SETTINGS)
        assert current.status_code == 200, current.text
        original = current.json()["additional_security_measures"]
        if not original:
            await set_policy(admin, True)
        try:
            yield
        finally:
            current = await admin.get(SETTINGS)
            assert current.status_code == 200, current.text
            if current.json()["additional_security_measures"] is not original:
                await set_policy(admin, original)


async def no_source_approval(foundation):
    async with foundation.database.sessions() as session:
        assert await session.get(SourceAccessApproval, (foundation.project_a, "c-ingest")) is None


async def test_confirmation_setting_is_persisted_revisioned_admin_only_and_csrf_protected(
    foundation,
):
    async with foundation.client(foundation.database.administrator) as admin:
        initial = (await admin.get(SETTINGS)).json()
        assert initial["additional_security_measures"] is True
        payload = settings_body(initial, additional_security_measures=False)
        csrf = admin.headers.pop("x-csrf-token")
        try:
            rejected = await admin.patch(SETTINGS, json=payload)
            assert rejected.status_code == 403
            assert rejected.json()["error"]["code"] == "CSRF_FAILED"
        finally:
            admin.headers["x-csrf-token"] = csrf
        assert (await admin.get(SETTINGS)).json() == initial
        changed = await admin.patch(SETTINGS, json=payload)
        assert changed.status_code == 200, changed.text
        current = changed.json()
        assert current["revision"] == initial["revision"] + 1
        assert current["additional_security_measures"] is False
        stale = await admin.patch(SETTINGS, json=payload)
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "REVISION_CONFLICT"
        # Older appearance clients may omit the newly introduced security field.
        appearance = await admin.patch(SETTINGS, json=settings_body(current))
        assert appearance.status_code == 200, appearance.text
        assert appearance.json()["additional_security_measures"] is False
        async with foundation.database.sessions.begin() as session:
            persisted = await session.get(ApplicationSetting, 1)
            assert persisted.additional_security_measures is False
            # Startup initialization must not overwrite an Administrator's choice.
            initialized = await initialize_settings(session, foundation.config)
            assert initialized.additional_security_measures is False
        async with foundation.client(foundation.database.administrator) as other_window:
            assert (await other_window.get(SETTINGS)).json() == appearance.json()
        async with foundation.client(foundation.alice) as inspector:
            assert (await inspector.get(SETTINGS)).status_code == 403
            denied = await inspector.patch(
                SETTINGS,
                json=settings_body(appearance.json(), additional_security_measures=True),
            )
            assert denied.status_code == 403
        assert (await admin.get(SETTINGS)).json() == appearance.json()


async def test_confirmation_setting_rejects_non_boolean_values_without_mutation(foundation):
    async with foundation.client(foundation.database.administrator) as admin:
        initial = (await admin.get(SETTINGS)).json()
        for invalid in (None, 0, 1, "false", "true", [], {}):
            rejected = await admin.patch(
                SETTINGS,
                json=settings_body(initial, additional_security_measures=invalid),
            )
            assert rejected.status_code == 422, (invalid, rejected.text)
            assert rejected.json()["error"]["code"] == "INVALID_REQUEST"
            assert (await admin.get(SETTINGS)).json() == initial


async def test_automatic_policy_allows_configured_paths_and_parser_edits_without_approval_rows(
    foundation, tmp_path, monkeypatch
):
    requests = []

    class Remote:
        warnings = []

        async def plan(self, source, roots):
            requests.append((copy.deepcopy(source), roots))
            return [SimpleNamespace(estimated_bytes=50)]

        async def check(self, candidate):
            assert candidate.estimated_bytes == 50

    @asynccontextmanager
    async def open_files(target, jump, **kwargs):
        assert target.host == "192.0.2.20" and jump is None
        yield Remote()

    monkeypatch.setattr(ssh_files, "open_files", open_files)
    manager = foundation.app.state.source_access
    async with foundation.client(foundation.database.administrator) as admin:
        document = await configured(foundation, tmp_path, monkeypatch, admin)
        await set_policy(admin, False)
        status = await admin.get(source_base(foundation.project_a))
        assert status.status_code == 200, status.text
        assert status.json()["manual_confirmation_required"] is False
        assert status.json()["approval"] == {
            "approved": True,
            "revision": 0,
            "expires_us": None,
        }
        for revision, change in [(2, "path"), (3, "parser"), (4, "roots")]:
            if change == "path":
                document["processes"][0]["log_source"]["active_path"] = (
                    "/var/log/inspector-demo/ingest/reconfigured.log"
                )
            elif change == "parser":
                document["processes"][0]["log_source"]["parser_id"] = "parser-fixed-utc"
            else:
                connection = next(
                    item for item in document["connections"] if item["id"] == "c-ingest"
                )
                connection["allowed_log_roots"].append("/var/log/new-logs")
                document["processes"][0]["log_source"]["active_path"] = (
                    "/var/log/new-logs/reconfigured.log"
                )
            edited = await admin.put(
                f"/api/v1/projects/{foundation.project_a}/topology",
                json={"expected_revision": revision, "config": document},
            )
            assert edited.status_code == 200, edited.text
            document = edited.json()["config"]
            tested = await admin.post(
                source_base(foundation.project_a) + "/test",
                json={"expected_config_revision": revision + 1},
            )
            assert tested.status_code == 200, tested.text
            assert tested.json()["processes"][0]["accessible"] is True
            async with foundation.client(foundation.alice) as inspector:
                snapshot = await manager.prepare(
                    foundation.alice.principal,
                    foundation.project_a,
                    "c-ingest",
                    revision + 1,
                    token_hash(inspector.cookies.get("__Host-si-session")),
                )
                assert snapshot.config_revision == revision + 1
                for suffix, body in [
                    ("/approve", approval_body(expected_config_revision=revision + 1)),
                    ("/test", {"expected_config_revision": revision + 1}),
                ]:
                    assert (
                        await inspector.post(source_base(foundation.project_a) + suffix, json=body)
                    ).status_code == 403
            await no_source_approval(foundation)
        assert len(requests) == 3
        assert requests[-1][0]["active_path"].endswith("/reconfigured.log")
        assert requests[-1][0]["parser_id"] == "parser-fixed-utc"
        assert requests[-1][1] == ["/var/log/inspector-demo", "/var/log/new-logs"]
        invalid = copy.deepcopy(document)
        invalid["processes"][0]["log_source"]["active_path"] = "/etc/passwd"
        rejected = await admin.put(
            f"/api/v1/projects/{foundation.project_a}/topology",
            json={"expected_revision": 5, "config": invalid},
        )
        assert rejected.status_code == 422
        assert (await admin.get(source_base(foundation.project_a))).json()["config_revision"] == 5
        arbitrary = await admin.post(
            source_base(foundation.project_a) + "/test",
            json={"expected_config_revision": 5, "path": "/etc/passwd"},
        )
        assert arbitrary.status_code == 422
        assert len(requests) == 3


@pytest.mark.parametrize("missing", ["host_key", "password", "expired_password"])
async def test_automatic_policy_preserves_host_key_and_credential_checks(
    foundation, tmp_path, monkeypatch, missing
):
    async with foundation.client(foundation.database.administrator) as admin:
        await configured(foundation, tmp_path, monkeypatch, admin)
        await set_policy(admin, False)
        async with foundation.database.sessions.begin() as session:
            if missing == "host_key":
                trust = await session.get(SSHHostTrust, (foundation.project_a, "c-ingest"))
                trust.approved = False
            else:
                binding = await session.get(
                    ProjectCredentialBinding, (foundation.project_a, "credential-demo-ingest")
                )
                if missing == "password":
                    await session.delete(binding)
                else:
                    credential = await session.get(SSHCredential, binding.credential_id)
                    credential.expires_us = services.utc_now_us() - 1
        status = await admin.get(source_base(foundation.project_a))
        assert status.status_code == 200, status.text
        assert status.json()["manual_confirmation_required"] is False
        assert status.json()["approval"]["approved"] is False
        async with foundation.client(foundation.alice) as inspector:
            with pytest.raises(DomainError) as denied:
                await foundation.app.state.source_access.prepare(
                    foundation.alice.principal,
                    foundation.project_a,
                    "c-ingest",
                    2,
                    token_hash(inspector.cookies.get("__Host-si-session")),
                )
            assert (
                denied.value.code
                == {
                    "host_key": "HOST_KEY_REQUIRED",
                    "password": "SSH_PASSWORD_REQUIRED",
                    "expired_password": "SSH_CREDENTIAL_EXPIRED",
                }[missing]
            )
        await no_source_approval(foundation)


async def test_reenabling_policy_requires_verified_unexpired_manual_approval(
    foundation, tmp_path, monkeypatch
):
    async with foundation.client(foundation.database.administrator) as admin:
        await configured(foundation, tmp_path, monkeypatch, admin)
        await set_policy(admin, False)
        await no_source_approval(foundation)
        await set_policy(admin, True)
        status = await admin.get(source_base(foundation.project_a))
        assert status.json()["manual_confirmation_required"] is True
        assert not status.json()["approval"]["approved"]
        blocked = await admin.post(
            source_base(foundation.project_a) + "/test", json={"expected_config_revision": 2}
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "SOURCE_NOT_APPROVED"
        rejected = await admin.post(
            source_base(foundation.project_a) + "/approve", json=approval_body(verified=False)
        )
        assert rejected.status_code == 422
        await no_source_approval(foundation)
        approved = await admin.post(
            source_base(foundation.project_a) + "/approve", json=approval_body()
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["manual_confirmation_required"] is True
        assert approved.json()["approval"]["approved"]
        assert int(approved.json()["approval"]["expires_us"]) > services.utc_now_us()
        async with foundation.database.sessions.begin() as session:
            row = await session.get(SourceAccessApproval, (foundation.project_a, "c-ingest"))
            row.expires_us = services.utc_now_us() - 1
        async with foundation.client(foundation.alice) as inspector:
            login = token_hash(inspector.cookies.get("__Host-si-session"))
            with pytest.raises(DomainError) as denied:
                await foundation.app.state.source_access.prepare(
                    foundation.alice.principal, foundation.project_a, "c-ingest", 2, login
                )
            assert denied.value.code == "SOURCE_APPROVAL_EXPIRED"
            await set_policy(admin, False)
            snapshot = await foundation.app.state.source_access.prepare(
                foundation.alice.principal, foundation.project_a, "c-ingest", 2, login
            )
            assert snapshot.config_revision == 2
            automatic = await admin.get(source_base(foundation.project_a))
            assert automatic.json()["approval"] == {
                "approved": True,
                "revision": 1,
                "expires_us": None,
            }


async def test_automatic_policy_revalidates_during_a_watched_read(
    foundation, tmp_path, monkeypatch
):
    manager = foundation.app.state.source_access
    started, stopped = asyncio.Event(), asyncio.Event()
    async with foundation.client(foundation.database.administrator) as admin:
        await configured(foundation, tmp_path, monkeypatch, admin)
        await set_policy(admin, False)
        async with foundation.client(foundation.alice) as inspector:
            login = token_hash(inspector.cookies.get("__Host-si-session"))
            before = await manager.prepare(
                foundation.alice.principal, foundation.project_a, "c-ingest", 2, login
            )

            async def blocked():
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()

            task = asyncio.create_task(
                manager.watched(
                    foundation.alice.principal,
                    foundation.project_a,
                    "c-ingest",
                    2,
                    login,
                    before,
                    blocked,
                )
            )
            try:
                await asyncio.wait_for(started.wait(), 3)
                await set_policy(admin, True)
                with pytest.raises(DomainError) as denied:
                    await asyncio.wait_for(task, 2)
                assert denied.value.code == "SOURCE_NOT_APPROVED"
                assert stopped.is_set()
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)


async def test_automatic_policy_collects_real_read_only_ssh_history_without_manual_approval(
    foundation, tmp_path
):
    enable_remote(foundation, tmp_path)
    root = copy_logs(tmp_path)
    async with endpoint(root) as (target, state):
        async with foundation.client(foundation.database.administrator) as admin:
            await configure(admin, foundation.project_a, target, approve_sources=False)
            await set_policy(admin, False)
            async with foundation.client(foundation.alice) as inspector:
                payload = await scope(inspector, foundation.project_a)
                prefix = f"/api/v1/projects/{foundation.project_a}"
                planned = await inspector.post(prefix + "/collections/plan", json=payload)
                assert planned.status_code == 200, planned.text
                assert planned.json()["source_count"] == 21
                created = await start(inspector, foundation.project_a, payload)
                job = await finished(inspector, foundation.project_a, created["job_id"])
                assert job["status"] == "completed", job
                assert job["event_count"] == 38
                assert job["parse_issue_count"] == 1
                assert job["coverage_status"] == "complete_for_scanned_candidates"
                assert not job["demo_mode"]
                await no_source_approval(foundation)
                await set_policy(admin, True)
                blocked = await inspector.post(prefix + "/collections/plan", json=payload)
                assert blocked.status_code == 409
                assert blocked.json()["error"]["code"] == "SOURCE_NOT_APPROVED"
        assert state.reads and state.opens
        assert not state.commands and not state.mutations
