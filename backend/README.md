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
context and owner/project-bound snapshot pagination. SSH, saved analysis tools
and Ansible inventory reconciliation belong to later stages.

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
