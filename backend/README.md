# System Inspector backend

FastAPI/Python 3.13 serves the bundled React application and uses MariaDB only.
Implemented: local Administrator/Inspector accounts, protected first-account CLI,
account lifecycle and forced password changes, opaque sessions/CSRF, persistent
appearance and application defaults, named systems, safe synthetic documentation,
revisioned metadata/archive/restore and private per-page workspaces. Stage 02 adds
scoped topology entities and constraints, shared documentation, flows, named
views, revisioned editing/undo/redo, scoped search and safe YAML/JSON import
preview/commit/export. Stage 03 adds local historical collection, bounded archive
parsing, exact microsecond event indexing in MariaDB, literal filtering, source
context and owner/project-bound snapshot pagination. Stage 04 adds encrypted
passwords, independent host-key and target/root approval, configured path checks,
and bounded direct/single-jump SSH/SFTP historical collection. Live following,
saved analysis tools and Ansible inventory reconciliation remain later work.

To configure a server as an Administrator, add a subsystem, then choose **Add
server**. Its **SSH connection** section shows the selected profile's host and
port. Choose **Create a new SSH profile** to enter an IP address or hostname,
SSH port (default 22), username, unresolved credential reference and proposed
log roots directly in the server form. Saving creates the server and profile in
one revision; cancelling saves neither. Existing profiles are reusable. Select a
server and use **Edit SSH connection**, or use **Connections**, to edit a profile;
changes affect every server using that profile.

When moving logs to another directory, keep the existing proposed log roots and
add the new directory on a separate line first. Save the profile, update each
affected process's active log path, rotated patterns and archive paths, then
remove any obsolete root. The connection editor lists the dependent paths across
all servers using the profile and marks paths outside the proposed roots.
For example, synthetic sources under `/var/log/demo` still need that root while
adding `/tmp/log`. Changing roots never moves files or grants source approval.

Select the server and choose **Password & connection test** (also available in
**Connections**). The credential reference is a safe label, not a password.
**Save SSH password** creates or replaces the password for that reference in this
system. Passwords are stored only as authenticated AES-GCM ciphertext in MariaDB
`ssh_credentials`; `project_credential_bindings` explicitly maps a system's
reference to its vault record. They are not returned by GET, exported in project
configuration, written to browser storage, or shown again after saving.

Next choose **Inspect host key**, compare its fingerprint against an independent
trusted source, check the verification statement, then **Approve host key**.
**Test connection** checks password authentication and the SFTP handshake without
opening a shell or writing files. Use the separate configured-source check below
to test log paths.
For one jump host, first configure its own password and approve its independent
key. Unknown or changed keys fail closed. The application server must resolve
and reach the target/jump; laptop-only VPN access is insufficient.

The deployment's `deployment.vault_key_file` supplies a protected file containing
exactly 32 raw random bytes, owned by the Linux service user with mode 0600 or
0400. The key stays outside MariaDB and exports. Back it up separately: changing
or losing it makes existing credentials undecryptable. Automated key rotation is
not implemented in this slice. Missing/invalid keys leave ordinary topology and
local history usable but disable SSH password storage/testing/collection.

Administrators control manual source confirmation through **Settings →
Additional security measures**. It starts checked to preserve the existing
policy. When checked, review **Approve target and log roots**, confirm
authorization for the displayed system, target and roots, then approve. Approval
expires after 24 hours by default; the API allows an explicit 60-second to
30-day duration. Configuration, password, trust or route changes require
reapproval. Imports and host-key approvals never create source approval.

When unchecked and saved, paths and parsers apply automatically without a
separate source-confirmation checkbox. Credentials and explicit target/jump
host-key verification are still required. **Test configured log paths** checks
only that connection's configured sources, active/rotated/archive readability
and root confinement. Inspectors cannot change the setting, manage approvals or
submit path tests. Reenabling the setting requires a valid current approval.
The change adds migration `0008_security_setting`; existing running apps need
that migration and the rebuilt application before the setting appears.

In **Log history**, select processes and UTC bounds, then **Collect sources**.
**Preview collection plan** is optional and opens the plan panel only when
requested. Completed and reopened collections automatically load Timestamped
events. **Log entry** omits the parsed timestamp prefix; **Context** preserves
the full original line. **Delete collection** removes your finished collection,
its events and captured files after confirmation. An active collection must
finish or be cancelled first. Production uses approved SSH/SFTP. The explicitly enabled local
demo additionally offers a labelled synthetic-fixture transport selector; it
does not approve SSH targets. Plans scan configured candidates irrespective of
filename dates. Remote files stream to generated private cache names with
actual-byte, listing, probe, candidate, timeout and cancellation limits. ZIP and
TAR.GZ members use the same bounded Stage 03 reader without extraction.

Jobs retain immutable configuration/source snapshots. Access is checked before
network dispatch and every 250 ms during work, with bounded database checks;
revocation, login/credential/approval expiry and database/supervisor failure stop
collection. One operation reuses a connection for compatible configured sources,
then closes both hops. Separate jobs, owners and systems share no SSH connection
or mutable filter. Changing a historical filter reads retained data without SSH.

Active logs freeze their byte boundary during planning. Appends during planning,
configured-path checks or collection do not interrupt retrieval or increase its
budget; later entries belong to another capture. Probes check the same captured
prefix before and after copying. Observed truncation, replacement, prefix changes
and equal-size metadata changes still fail visibly. Rotated files and archives
remain immutable and reject appends too.
SFTP v3 cannot prove absence of every same-size rewrite or path race;
dedicated account permissions remain essential. Symlinks are rejected. A
successful scan describes its candidates, not continuous or exactly-once history.

The current local development app remains **https://localhost:8445**, using the
existing Stage 03 schema/accounts/configuration upgraded to `0008_security_setting`.
`scripts/stage4_local.py prepare` adds isolated SSH fixtures and a protected master
key under ignored `.secrets/stage4-ssh/`; it never resets existing data. Its
container wrapper copies the mounted key to
`/var/lib/system-inspector/ssh-vault.key` with mode 0600 before starting ASGI.
Prepare, stop the serving app, back up its database/cache, explicitly run
`scripts/stage3_local.py migrate`, then `scripts/stage4_local.py up`. Normal
restarts use `stage4_local.py up`; no package downloads or connections occur at
startup. Fixture host keys/passwords are synthetic and are not application-wide
default credentials. The named non-root Linux account is required by AsyncSSH.

The 17 October collection-viewer update is installed from the isolated artifact
at `.state/stage4-ssh/collection-ui/backend`, mounted into `runtime-stage3` as
`/workspace/backend`. It includes automatic results, direct collection, Log entry
and owned collection deletion, and preserves the active-log append fix. Schema
remains `0008_security_setting`. Keep that directory for restarts; normal
restarts use `scripts/stage4_local.py up`, and future source updates require a
fresh artifact. The previous `.state/stage4-ssh/active-append-fix/backend` and
`.state/stage4-ssh/installed-0008/backend` artifacts remain available for rollback.
The shared repository bundle used by the retained 8444 app is intact. Consistent
pre-install database/cache and previous-backend/deployment backups are protected
under `.secrets/stage4-ssh/pre-collection-ui/`; older append-fix and migration
backups remain in their existing protected directories.

`scripts/verify_stage4.py integration` runs the real MariaDB/SSH gate in a fresh
disposable local schema; `upgrade` checks populated additive migration and
`checks` records unit, contract, lint, type, generated API and build results.
These tests use synthetic targets only and never try configured user hosts.

Historical result pages and context are capped at 8 MiB of raw text. A page can
contain fewer rows than requested; its cursor continues from the last emitted
event. Oversized-line diagnostics remain visible with an explicitly unknown
literal match result. A 64 MiB, five-minute read-through cache includes in-flight
builds and leased immutable rows. Its key includes owner, project, capture,
configuration/snapshot revision, process/time scope and diagnostic lane. Every
query still checks MariaDB authorization/session state; a cache entry grants no
access. Cold or evicted scopes use the bounded MariaDB scan.

Results and release gates are in [STATUS.md](../progress/STATUS.md). Setup:
[temporary VM](../deploy/vm-mariadb/README.md),
[local Docker](../deploy/local-mariadb/README.md),
[web toolchain](../frontend/README.md), [app image](../deploy/app/README.md).

Use Python 3.13.16 and the real `uv.lock`. From the repository root:

```sh
uv sync --project backend --locked
uv run --project backend --locked python scripts/frontend.py install --connected
uv run --project backend --locked python scripts/build_stage1.py
uv run --project backend --locked pytest backend/tests/unit -q
uv run --project backend --locked ruff check --config backend/pyproject.toml backend/src backend/tests backend/migrations scripts
cd backend
uv run --locked mypy src
```

Node/npm are build tools only. The build includes byte-checked local frontend
assets, the deployment schema and explicit Alembic migrations in the wheel.
No configuration or secret file is bundled. Root Make targets expose
`dev`, `test`, `lint`, `typecheck`, `build`, `integration` and `e2e`; the current
`dev` target uses the approved VM configuration. `integration` provisions a new
local disposable Docker schema and runs the actual Linux suite; it never accepts
skips as database evidence. `release-offline` deliberately
fails until Stage 08 release gates are met. GNU Make is absent on this Windows
host; verification runs the underlying commands directly.

Set `INSPECTOR_CONFIG_FILE` to protected deployment schema-2.0 YAML. Required
host/port/name/user/password-file/TLS/pool settings are validated before startup.
Ordinary external database connections verify CA and hostname TLS. The explicit
loopback SSH tunnel is a development exception; another machine/container must
not reuse the workstation's localhost. Serving checks actual exact-schema DML
grants and rejects migration credentials.

Migrate with serving stopped and migration credentials mounted only into this job:

```sh
python -m inspector.cli db upgrade --config /etc/system-inspector/application.yaml --username inspector_migrator --password-file /run/secrets/inspector_db_migration_password
```

The protected operator CLI prompts for passwords without echo or argv values:

```sh
python -m inspector.cli bootstrap-admin
python -m inspector.cli create-inspector
python -m inspector.cli seed-demo
```

Bootstrap refuses an existing enabled Administrator. The other commands require
Administrator credentials. Demo seeding creates two labelled synthetic systems
with real editable topology and unresolved connection/root proposals. It does
not approve targets, bind credentials, trust host keys or start collection.
The separate VM browser fixture is explicit test
setup with random credentials in ignored protected files; no universal seed
password or public setup API exists.

Production starts with `python -m inspector`: one worker on port 8000 behind
the configured same-origin HTTPS proxy. `python -m inspector.cli healthcheck`
checks local readiness using the configured Host. Cookies are always Secure,
HttpOnly and SameSite Strict. Host and write Origin must match exactly. Login
uses pre-session CSRF; protected writes use authenticated CSRF. All security
mutations increment the account version, revoke its sessions and expire its page
workspaces. Deletion is unavailable; the last enabled Administrator is retained.

Stage 03 local browser verification uses a separate Docker test schema and
`runtime-stage3` service at `https://localhost:8445`. Run its setup with existing
pinned local images (no pulls):

```sh
python scripts/stage3_local.py prepare
python scripts/stage3_local.py migrate
python scripts/stage3_local.py fixture
python scripts/build_stage1.py
python scripts/stage3_local.py up
```

The fixture creates `[Synthetic demo] Historical A/B` with the golden configured
processes. Open **Log history**, select processes and enter UTC bounds, for
example `[2026-10-16T12:00:00.000000Z, 2026-10-16T12:00:02.000000Z)`, preview
the collection plan, then collect and apply the filter. Inspector and
Administrator both own their captures. Retained collections reopen through their
system-scoped URLs; sources/context/downloads remain ownership checked.

Local collection requires explicit deployment environment `SI_LOCAL_HISTORY_DEMO=1`.
It maps only the supplied fixed fixture manifest through configured process/path
selectors. The default is disabled. No browser-supplied host, path, parser or
credential can replace approved configuration. This is a labelled local adapter,
not SSH transport. ZIP64/multivolume archives and nested archives are explicitly
unsupported. Archives are streamed; members are never extracted.

Set `INSPECTOR_E2E_URL=https://localhost:8445`, `INSPECTOR_E2E_REPORT_STAGE=stage-3`
and `INSPECTOR_E2E_ACCOUNTS` to the absolute protected
`.secrets/stage3-browser/accounts.json` path. `fixture` expires only these
synthetic accounts' old workspaces. The cache survives the Stage 03 container
restart; `stop` retains all test data. Migrations require the test server stopped.

`python scripts/verify_stage3.py integration` creates a new disposable MariaDB
schema and records actual Linux test output. `python scripts/verify_stage3.py checks`
records unit/package/lint/type/API/build results. For the generated 20 MiB
production collector/index/query benchmark, stop this test server and run
`python scripts/stage3_local.py benchmark`, then `up` again. Benchmark input
generation and network transfer are excluded from the recorded ingestion timing.
`python scripts/verify_stage3.py upgrade` verifies a populated foundation upgrade
to the current schema in a newly guarded disposable database. Existing schemas
are refused. `python scripts/benchmark_stage3.py` records the benchmark with
sanitized UTF-8 diagnostics and exact commands; the test server must be stopped.

Stage 02 browser verification remains at `https://localhost:8444`. The retained Stage 01 VM-backed
app on port 8443 is stopped at the user's request; its database, tunnel and data
are preserved. Stage 02 does not migrate or replace that database.
With the pinned local database and runner already prepared:

```sh
python scripts/stage2_local.py prepare
python scripts/stage2_local.py migrate
python scripts/stage2_local.py fixture
python scripts/build_stage1.py
python scripts/stage2_local.py up
```

`fixture` expires only this isolated schema's synthetic browser-account workspaces
before a rerun. Test account values stay in `.secrets/stage2-browser/accounts.json`.
Set `INSPECTOR_E2E_URL`, `INSPECTOR_E2E_ACCOUNTS` and
`INSPECTOR_E2E_REPORT_STAGE=stage-2` for the browser suite. `stop` retains data.
Migrations run with the test server stopped and separate migration credentials.
Project configuration import accepts version 2 YAML/JSON and previewed version 1
conversion; Ansible inventory files and reconciliation arrive in Stage 07.

Each document creates a fresh workspace using POST under its URL's project.
There is no mutable current-project session, browser storage or shared filter.
GET never creates a workspace or starts collection. Read polling renews only the
300-second page lease; protected writes renew login idle, bounded by absolute
expiry. Authentication polling does not renew idle. Reload/duplication gets a
new workspace; detachment cannot adopt a controller. Startup detaches old pages.
Later live-control leases are outside this stage.

Transactions follow security/account/project/workspace lock order and READ
COMMITTED isolation. Quotas reserve atomically. Supervisor ownership is exclusive
to a server process, not a browser page, and fails closed after connection/lock
loss. Password hashing uses two bounded off-loop workers. Audit records only
classification/IDs/time/outcome, including preferences and denied actions.

The original integration suite requires a new empty `inspector_test_` schema,
separate DML/migration identities and explicit opt-in. It refuses occupied schemas
and retains synthetic history. The approved VM API suite uses its own guarded
fixture and preserves unrelated data; fixture systems are archived after tests.
The initial rollback-only VM smoke checks require no application data and are
historical first-migration evidence, not rerunnable against the seeded database.
See status for exact commands and Linux container results.

OpenAPI and frontend types are generated from actual route models:

```sh
python -m inspector.cli openapi --output backend/openapi.json
python scripts/frontend.py api:generate
python scripts/frontend.py api:check
```

Every protected route declares a known permission; tests check mutation CSRF
dependencies. Original dependency notices are preserved in the
[backend inventory](../third_party/backend/inventory.json) and
[frontend inventory](../third_party/frontend/README.md). Full release advisory,
Ubuntu/Rocky and offline installation gates remain separate from Stage 01.
