# System Inspector backend

Stage 07 source adds the Administrator **Import Ansible inventory files** wizard,
safe static INI/extensionless-hosts/YAML/canonical-JSON parsing, ZIP companion
variables, project-scoped source identities and revision-bound atomic
reconciliation. It also adds parser-draft diagnostics using the real collection
parser. That Stage 07 artifact expects additive MariaDB revision `0013_inventory`.
Following isolated synthetic verification and separate deployment authorization
on 18 October 2026, the original Stage 07 artifact was installed at
**https://localhost:8445**; the subsequent language deployment below replaces it.
Production release and offline installation remain Stage 08 work.

The subsequent language follow-up is deployed at **https://localhost:8445**,
with **`0014_languages`** and its matching frozen frontend/backend. It adds
English/Polish application default and personal preferences in MariaDB;
existing settings, revisions and themes are
preserved. Optional `bootstrap_settings.default_language: en` (or `pl`)
initializes fresh settings only. Use Settings for the shared default and user
menu → Preferences for personal Language / Application default. Migrate with
serving stopped and separate migration credentials as described below. The
8445 deployment applied the migration with serving stopped after a consistent
SQL/cache backup. Existing settings, accounts and retained data are preserved;
actual installed English/Polish controls and role restrictions pass. Recovery
material remains protected under `.secrets/language-install/pre-0014-languages/`;
see `verification/language-support/deployment-*.json` and `progress/STATUS.md`.

Local synthetic verification: `python scripts/verify_languages.py integration`
and `python scripts/verify_languages.py upgrade` provision fresh disposable
MariaDB schemas. Browser checks use only the isolated Stage 07 fixture on 8449
with fresh built assets; receipts are in `verification/language-support/`.

The subsequent authorized Preferences/Settings UI update on the same local
8445 application uses `.state/preferences-install/frontend` as a read-only
overlay at `/workspace/backend/src/inspector/web`. The original Stage 07 wheel,
backend snapshot, runtime image and `0013_inventory` schema remain unchanged.
Rollback removes only that runtime overlay using the protected previous Compose
file; details and actual verification are recorded in `progress/STATUS.md`.

On the selected system's topology page, choose/create one stable inventory
source, upload the file or ZIP, select source entries in explicit order, parse,
map groups/individual hosts to exactly one subsystem each, then review exact
changes and commit. The system name/ID and expected revision stay visible.
An explicit new subsystem ID creates an initially empty subsystem named with
that ID. Optional process definitions require a same-system parser; host-only
inventories create zero processes. Missing SSH usernames/credentials remain
unresolved proposals. Imported profiles start without new host-key trust or
target/root approval. Credentials and jumps use explicit existing project
references, and import itself opens no SSH connection.

Reimports use source+host alias and optional local process ID, preserving existing
documentation, diagram geometry, flows, unrelated processes and manual tags.
Missing records remain present and are reported as absent. Manual edits to
imported managed fields block commit for review; there is no force-overwrite
option. An unchanged reimport preserves IDs and the topology revision. Correct
unsupported/ambiguous input or resolve supported subsystem mappings before
obtaining a fresh preview. The importer does not run Ansible, scripts, plugins,
Jinja, shell arguments or uploaded configuration files. See the full
[static subset, limits and reconciliation rules](../docs/10_ANSIBLE_IMPORT.md)
and [implemented API](../docs/05_API_AND_WEBSOCKET.md).

Raw uploads use protected, expiring files under
`deployment.state_dir/inventory-staging`, with sanitized metadata/previews and
field baselines in MariaDB. Default hard bounds are 10 MiB upload, 20 MiB expanded,
200 files, two upload slots and ten pending uploads/account; lower configured
`inventory_upload_bytes`, `inventory_expanded_bytes` and `inventory_file_limit`
are enforced. Upload bytes also respect `config_upload_bytes`. Commit or
upload/wizard cancellation removes raw staging. Preview-only cancellation keeps
the upload for remapping; staging expires after 15 minutes and the reaper runs every
30 seconds. Upload/parser workers release database/auth locks and revalidate
login, role, ownership and revision before publishing their result.
Cooperative parser callbacks stop work after HTTP/task cancellation, upload
cancellation or expiry; bounded worker reservations remain held until exit.

The parser editor's **Test parser sample** accepts up to 64 KiB UTF-8, 100
physical lines and 4 KiB/line. It returns original/UTC timestamps, exact
microseconds, metadata and timestamp errors without saving the draft/sample.
Failed timestamps retain a diagnostic explanation. Configured remote path tests
remain in the separate Administrator connection/source-access panel and require
the existing project credential, host-key and approval policy.

Stage 07 verification helpers use fresh disposable schemas or a separately
prepared synthetic HTTPS/SFTP fixture on port 8449, preserving existing schemas
and installations. With the pinned runner image already prepared:

```sh
python scripts/verify_stage7.py inventory
python scripts/verify_stage7.py integration
python scripts/verify_stage7.py upgrade
python scripts/verify_stage7.py checks
```

The isolated browser fixture uses `scripts/stage7_local.py` commands `prepare`,
`migrate`, `fixture`, `up` and `configure`; `stop` retains that synthetic data.
Its generated account file stays protected under `.secrets/stage7-browser/`.
Migration tools require a stopped fixture and distinct migration credentials.
The populated-upgrade check compares Stage 06 data before/after `0013_inventory`;
actual commands/results and remaining stage-gate limitations are recorded in
[STATUS.md](../progress/STATUS.md) and `verification/stage-7/`.

Stage 06 source adds owned saved workspaces, exact parsed-field and literal
correlation traces, annotations/bookmarks, source-local context pins, provenance,
explicit cache expiry, and previewed sanitized ZIP bundles. Both roles have the
same personal tools. Its additive schema `0012_offline_analysis` was installed
on the retained local 8445 application after separate Stage 06 deployment
authorization, before the subsequent Stage 07 upgrade to `0013_inventory`.
Do not run an older serving artifact against the current schema. Stage 06 implementation
verification used an isolated synthetic HTTPS/SFTP fixture on port 8448.

Saved analysis has one optimistic revision across workspace and bookmark edits.
Pinning the investigation protects its captured source cache. Pinning a bookmark
retains an independent event-text/provenance context snapshot (32 MiB total per
investigation); it does not preserve the entire original source file. Explicit
expiry removes unpinned source bytes/index rows while keeping analysis and pinned
context. Responses distinguish unavailable data from zero matching events.

Bundle import streams a bounded ZIP to a temporary spool, validates the two
regular members and checksums before staging, and commits separate private
offline data after preview. It creates no active topology, source associations,
credentials, trust or connection attempts. Foreign IDs remain origin provenance.
Exports contain a typed topology projection and retained event data, and apply
literal redaction to every string. Review the full preview: the redactor cannot
identify unspecified sensitive values. Original cache files remain unchanged.

Stage 07 is installed at **https://localhost:8445**, using migration `0013_inventory`
and the tested Python environment (including BSD-licensed `websockets` 16.1.1).
The isolated installed artifact is `.state/stage7-install/backend`; the Compose
override pins the tested runtime image. Existing data, configuration, cache and
vault were backed up and verified unchanged. The isolated Stage 05/06/07 test fixtures
on 8447/8448/8449 are stopped; their commands are for synthetic verification only.

Both roles can select configured processes and choose **Monitor selected** or
open **Live monitor** in the logs workspace. Starting is explicit. Each page
owns its session, filter version and revisioned workspace control lease. The
stream authenticates cookies, exact Origin and a CSRF-bearing protocol 2 hello;
no tokens or terms go in its URL. Every protected dispatch and a silent-socket
watchdog check current authentication and ownership. Database/supervisor loss
stops collection; database recovery never automatically restarts it.

SFTP polls every 750 ms and buffers new arrivals for at most 500 ms. Host
connections and raw source capture can be shared within the complete matching
project/owner/configuration/access context. Filters remain private to each
monitor. Seed requests use measured rows (1–500); scans and raw retention obey
deployment ceilings. Changing or clearing literal filters refilters retained
unfiltered bytes without reconnecting. Unknown timestamps have a diagnostic
lane. Source status explains scanned boundaries, exhaustion, errors, observed
rotation/truncation, disconnects and retention eviction. SFTP observations cannot
prove lossless continuity through every rewrite or rotation.

**Pause display** continues receipt; **Resume display** shows the retained
position. **Stop this monitor** releases only its subscriptions. A page/socket
disconnect retains a bounded reconnect lease (at most 300 seconds, or a smaller
configured limit). A new page lists detached owned sessions and requires
**Resume in this window**; it cannot take an occupied lease. Theme preferences
are shared account state and leave streams running. Logout revokes every page
using that login.

**Record into investigation** saves the retained raw lines, including current
nonmatches, and persists new original-byte ranges before their publication.
Recording is bounded by the collection byte ceiling and 200,000 events; reaching
a limit stops the affected recording visibly. Oversized preview lines cannot be
misrepresented as original recorded bytes. The partial capture remains queryable
offline through the historical viewer, with original source labels/provenance.
Captured ranges may start after byte zero or have gaps; their cache contains
only recorded ranges. These sources remain explicitly partial and cannot use
the complete-source raw download action. Stopping/cancelling, restart and
recording failures retain committed partial results. The installed investigation tools
add personal analysis, correlation, bookmarks and bundle exchange to these captures.

For a synthetic browser test installation, use the existing local MariaDB
service and `python scripts/prepare_stage5_runner.py`, followed by
`python scripts/stage5_local.py prepare`, `migrate`, `fixture`, `up`, and
`configure`. This fixture uses generated accounts and a read-only SFTP service,
never a real target. `restart` and `stop` affect only that fixture. The
`capacity-archive` action prepares a generated 16 MiB regular ZIP member for
the concurrent-investigation browser check; it writes only the fixture's data.
The runner build needs connected dependency preparation; fixture operation has no Internet
dependency. Use `scripts/verify_stage5.py` for fresh disposable integration and
upgrade checks. Actual commands/results and test limitations are recorded in
[STATUS.md](../progress/STATUS.md).

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
and bounded direct/single-jump SSH/SFTP historical collection. Stage 05 adds
supervised live SFTP capture, independent monitor leases, protocol 2 WebSockets,
retained literal refiltering and explicit recording. Stage 06 adds the personal
analysis/bundle tools described above; Stage 07 source adds inventory
reconciliation and parser diagnostics.

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

The retained local app at **https://localhost:8445** now uses the existing
Stage 03 accounts/configuration and database upgraded from `0012_offline_analysis`
to `0013_inventory` on 18 October 2026. Its tested artifact at
`.state/stage7-install/backend` is mounted
read-only into `runtime-stage3`; the image is pinned to
`sha256:668bfc011a595c63ea4f88c29eea56c326828662dbba1cd20a18a4eacdfcd8a8`.
It runs one worker with explicit `websockets`, a 16 KiB message limit and a
16-message receive queue. The isolated wrapper copies the unchanged vault key
to `/var/lib/system-inspector/ssh-vault.key` as UID 10001 with mode 0600.
No package downloads or target connections occur at startup. Fixture host
keys/passwords are synthetic; the named non-root Linux account is required by
AsyncSSH.

For a normal restart, use the existing local MariaDB base Compose file plus
`deploy/local-mariadb/stage3-browser.compose.local.yaml` and target only
`up --detach --no-deps runtime-stage3`. The earlier `stage4_local.py up/stop`
commands also operate SSH fixtures. Preserve the installed snapshot and its
image; future source updates require a fresh tested artifact.

The matching pre-upgrade schema `0012_offline_analysis` SQL dump (194,617,923
bytes), raw-cache archive with byte/permission manifests, prior backend, exact
deployment files and protected vault copy are retained under
`.secrets/stage7-install/pre-0013-inventory/`. All previous Stage 04/05/06 artifacts
and backups remain available. Rollback after migration must restore a matching
database/cache/application state; no rollback drill was performed for this
upgrade. The Stage 07 migration preserved all 44 old table counts and all 43
non-Alembic checksums and added five initially empty inventory tables. After
startup, all 34 stable table checksums, 897 cache files (230,864,349 bytes), 957
ownership/mode entries, configuration and vault matched the backup baseline.
TLS/hostname verification and readiness pass. Port 8444's container, image,
start/restart state and served assets remain unchanged. See
`verification/stage-7/deployment-*.json` and
[STATUS.md](../progress/STATUS.md) for exact commands and installed checks.
The installed wheel SHA-256 is
`908c3befbd0053da388c8d14916e7e40ff12efb99b2ff8d43fe1296cdb63c729`.
The earlier `verify_stage6_preservation.py --installed-stage6` command checks
historical Stage 06 expectations and is not a current Stage 07 installation
check. This local deployment performs no production rollout or Stage 08 release.

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
conversion. The separate Stage 07 inventory workflow is described above; these
historical Stage 02 fixture commands do not install that later implementation.

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
