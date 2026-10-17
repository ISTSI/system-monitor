# Temporary MariaDB VM through the existing tunnel

Use the user-authorized workstation listener `127.0.0.1:13306`, database
`system-monitor`, MariaDB 12.3.3. Keep the company VPN and existing pinned-host-key
SSH tunnel running. The application/tools do not start, stop or repair either.
Production remains Linux-hosted; a container has a different localhost.

The database already existed empty. The first migration created seven application
tables plus Alembic versioning; Stage 01 added preferences, application settings,
synthetic documentation snapshots and the forced-password-change flag. The
existing default utf8mb4_unicode_ci collation is preserved; application tables
and identity columns use binary collations. Explicit schema identifiers are
backtick-quoted; metadata scope is bound and URLs use SQLAlchemy URL.create.

The supplied schema-wide account is migration-only. Its password remains in
ignored protected `.secrets/vm-mariadb/migration_password`. The DBA applied
`provision_runtime.sql`; the separate `system-monitor-app` account is verified to
have exactly SELECT, INSERT, UPDATE and DELETE on the approved schema. Its
password is in `.secrets/vm-mariadb/runtime_password`. Serving verifies actual
grants and rejects migration/global/other-schema privileges.

Ignored `migration.local.yaml` and `application.local.yaml` hold coordinates and
password-file references only. Explicit `ssh_tunnel` topology permits literal
loopback with disabled database TLS. This is the user's development exception,
not a claim of end-to-end MariaDB TLS. Ordinary external deployments require
verified database TLS. Never expose or rewrite the tunnel binding implicitly.

From the repository root, the already-prepared Stage 01 application runs with:

```powershell
backend/.venv/Scripts/python.exe scripts/stage1_local.py serve --approved-schema system-monitor
```

Open `https://localhost:8443`. The protected local development certificate is
self-signed and valid for 30 days; it is not installed into workstation trust.
Production uses a provisioned HTTPS certificate/proxy. No public registration or
shipped default login exists. Synthetic browser credentials are in ignored
`.secrets/vm-mariadb/stage1-browser-accounts.json`; the isolated browser rerun pool
is in `stage1-browser-recheck-accounts.json`. Read those files locally rather than
printing their passwords into terminals/logs. Actual installations bootstrap the
first Administrator interactively using the CLI in [backend setup](../../backend/README.md).

The guarded test fixture creates explicitly synthetic accounts and two read-only
documentation systems through real backend services. It is separate from normal
production bootstrap. It does not create SSH profiles, approve targets or start
collection. Generated API-test systems are archived after checks; history remains.
The initial migration's four rollback-only smoke tests are retained as historical
evidence; their empty-application-data guard deliberately refuses this seeded DB.

Run the broader runtime-identity API suite only with its explicit scope/fixture:

```powershell
$env:SI_TEST_APPROVED_SCHEMA = 'system-monitor'
$env:INSPECTOR_STAGE1_CONFIG = (Resolve-Path deploy/vm-mariadb/application.local.yaml).Path
$env:INSPECTOR_E2E_ACCOUNTS = (Resolve-Path .secrets/vm-mariadb/stage1-browser-accounts.json).Path
backend/.venv/Scripts/python.exe -m pytest backend/tests/stage1 -v --tb=short -rs
```

Stop this app process before that suite: it starts an exclusive serving supervisor
for its tests. The sole-Administrator test requires only its fixture Administrator
to be enabled; use the disposable Docker suite for independent repeatable account
invariant checks once additional Administrators exist. Never disable ordinary
accounts to fit a test. Browser tests require the HTTPS app already running; set
INSPECTOR_E2E_ACCOUNTS to the chosen protected fixture and use `scripts/frontend.py e2e`.
Detached page leases count until expiry; use fresh synthetic accounts for rapid
reruns instead of raising deployment limits.

The separate ignored `stage1-integration-provision.sql` was prepared for a DBA to
create independent disposable VM test resources. It was not executed by Codex and
is optional now that the local Docker integration environment is available. It
never changes `system-monitor`. Do not infer DBA execution from an intent to run it.

No VM restart, tunnel interruption, unrelated schema deletion or production
deployment was performed. Docker lifecycle evidence is independent of this VM.
See [status and exact verification](../../progress/STATUS.md).
