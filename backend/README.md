# Stage 01 foundation

FastAPI/Python 3.13 serves the bundled React application and uses MariaDB only.
Implemented: local Administrator/Inspector accounts, protected first-account CLI,
account lifecycle and forced password changes, opaque sessions/CSRF, persistent
appearance and application defaults, named systems, safe synthetic documentation,
revisioned metadata/archive/restore and private per-page workspaces. Collection,
SSH, editable topology, imports and investigations belong to later stages.

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
with read-only documentation snapshots. It does not approve targets, create SSH
profiles or start collection. The separate VM browser fixture is explicit test
setup with random credentials in ignored protected files; no universal seed
password or public setup API exists.

Production starts with `python -m inspector`: one worker on port 8000 behind
the configured same-origin HTTPS proxy. `python -m inspector.cli healthcheck`
checks local readiness using the configured Host. Cookies are always Secure,
HttpOnly and SameSite Strict. Host and write Origin must match exactly. Login
uses pre-session CSRF; protected writes use authenticated CSRF. All security
mutations increment the account version, revoke its sessions and expire its page
workspaces. Deletion is unavailable; the last enabled Administrator is retained.

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
