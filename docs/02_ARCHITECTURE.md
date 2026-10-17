# 02 — Architecture and technology decisions

## Selected stack

| Layer | Choice | Responsibility |
|---|---|---|
| Client | React + TypeScript + Vite | Browser application, typed API client, accessible controls and local assets |
| Diagram | React Flow (`@xyflow/react`, MIT core) | Nested custom subsystem/server/process nodes, connections, selection and viewport [S02] |
| Log presentation | TanStack Virtual | Render visible rows, with stable keys and bounded client caches [S03] |
| API/services | Python 3.13 + FastAPI/Pydantic + Uvicorn | HTTP API, WebSockets, validation, supervision and business logic [S04, S05] |
| Remote I/O | AsyncSSH | SSH password authentication, strict trust, SFTP and jump tunnels [S06] |
| Persistence | MariaDB + SQLAlchemy asyncio/asyncmy + Alembic | Canonical model, accounts/roles/preferences, jobs, investigations, event index and migrations [S18, S19] |
| Archive handling | Python `zipfile`, `tarfile`, `gzip` | Stream approved regular members with hard resource limits [S07, S08] |
| Security libraries | `cryptography`, `argon2-cffi` | Authenticated encryption of secrets and operator password hashing; do not invent cryptography |
| Tests | pytest, Vitest/Testing Library, Playwright | Unit/contracts, API, transport and browser acceptance |
| Production delivery | OCI app image; HTTPS reverse proxy | Identical application artifact on Ubuntu/Rocky; no runtime package install |

Select current compatible supported package releases during Stage 00, record them and commit actual lockfiles. Use the latest security-patched Python 3.13 maintenance release available at build time and Node.js 24 LTS for frontend builds; Node is not a production backend dependency. Do not treat any example base tag as an immutable release reference. Maintain an SBOM, notices and image checksums. Research references are in SOURCES.md, not a substitute for compatibility testing.

## Why this replaces Electron

The browser renders the interface while the Linux server owns connections and cached logs. There is no need for a desktop wrapper or privileged browser-to-OS bridge. Python's asynchronous I/O and archive libraries provide a direct backend implementation path at this modest scale. Keeping two languages is a deliberate trade-off: TypeScript for the graphical UI, Python for log and SSH services. MariaDB is an explicit user requirement, provided as a managed container or configured existing endpoint. No distributed job broker is required.

MariaDB is a separate database service. The browser never connects to it. Use InnoDB, foreign keys, utf8mb4, exact integer timestamp indexes, short transactions and a bounded asynchronous pool. Local raw-cache files remain on the application server. See docs/14_MARIADB.md for types, privileges, leases and configuration. Do not use SQLite as a runtime or database-integration-test substitute.

Substring searching is **not** implemented as token-based full-text search. At 10–20 MB per investigation, narrow by process and timestamp indexes, then scan candidate raw text with the exact literal predicate. MariaDB FULLTEXT is not a substitute for the literal predicate. Any optional prefilter must be a proven superset, followed by exact application-level matching; preserve punctuation, substrings and Unicode casefolding. A SQL LIKE query without escaping is not an acceptable substitute.

## Data path

Browser → same-origin HTTPS proxy → FastAPI routes/services → AsyncSSH direct or jump connection → SFTP on target hosts.

Downloaded byte ranges/archive objects → managed cache → bounded parser/archive workers → MariaDB event/provenance index → historical queries or bounded live subscriptions → WebSocket → virtualised viewer.

The browser receives only selected pages and current live batches. It does not download entire raw archives to perform filtering, hold credentials in local storage, connect to SSH, or fetch arbitrary URLs.

## Backend service boundaries

`AuthorizationService` enforces roles and ownership before every service operation; `AccountService` owns user lifecycle, session revocation and personal preferences; `SettingsService` owns revisioned Administrator-managed application settings. `ProjectService` owns validated model transactions, revisions and view layouts. `ImportService` produces a non-executing preview before commit. `CredentialVault` returns a password only to the connection layer. `SSHConnectionManager` owns direct/jump pools, host trust, leases and reconnect policy. `SourcePlanner` enumerates allowed configured files. `CollectionSupervisor` runs cancellable persistent jobs. `ArchiveReader` and `TimestampParser` produce indexed events with provenance. `LiveSupervisor` polls sources, owns raw buffers/cursors and publishes subscription changes. `QueryService` implements exactly one shared filter predicate. `InvestigationService` handles workspaces, traces, notes and context. `BundleService` exports/imports validated non-executable data packages.

Separate transport adapters from parsing and query functions so fixtures can exercise all semantic cases without a network. A file-backed fake SFTP adapter is acceptable in tests; do not use it to claim production SSH support.

## Concurrency and lifecycle

Use **one ASGI worker**, one process-local SSH pool and one supervisor. FastAPI notes that process-local WebSocket state is not shared across workers [S04]. Scale through bounded async tasks, not extra Uvicorn workers. Acquire a database-scoped supervisor advisory lock on a dedicated connection as well as a local state-directory lock; accidental second instances against the same database fail clearly. Loss of that connection stops protected collection/streaming until a safe supervisor restart; never reconnect it silently as if the lock survived [S25].

Use asynchronous SFTP reads. Run blocking archive/decode/index batches outside the event loop in a bounded executor; cancellation must be checked between chunks. Two concurrent archive jobs and four concurrent host collectors are initial limits. A thread is not a hard sandbox; use a killable subprocess for a task that cannot honour the configured time/memory limits. All persistence writes flow through short transactions or a bounded write queue; do not share ORM sessions across tasks.

Long-running live tasks belong to an application lifespan supervisor, not request-scoped `BackgroundTasks`. Startup marks interrupted nonterminal jobs appropriately; it does not silently restart remote collection. Shutdown cancels tasks, closes transports, checkpoints cursors and flushes committed data within a deadline [S05].

A source collector can serve several panes/tabs of the same authenticated user. Do not share live-session objects or filter/subscription state between different users. Reuse it only when project, source configuration revision, target, credential version and permission context match. Reference-count subscriptions. Close unused transports after a short idle timeout. A credential/trust change invalidates affected pooled connections. Never pool only by hostname.

## Persistence and retention

Use MariaDB for topology, configuration revisions, users/roles/preferences, jobs, investigations, annotations, auth sessions, audit records and source manifests. Event rows may share it initially with suitable indexes; document any later split. Raw bytes live in generated cache paths, never user-controlled path concatenations. Retention removes an indexed source transactionally and marks dependent unpinned investigations as unavailable. Pinned sources count against the same disk budget; stop new collection with a clear message if the budget cannot be honoured.

Live data is retained unfiltered in bounded transient storage. Explicit recording persists its events and sources into an investigation. Bookmarks/notes created from a transient view must prompt to pin/save the event and context before the session can expire. Filters never change the underlying captured source data.

## Suggested repository layout after implementation

```
backend/
  pyproject.toml
  uv.lock
  src/inspector/
    api/            # auth, projects, jobs, query, live, bundles
    domain/         # typed entities, validation and filter semantics
    services/       # application use cases and supervisors
    transports/     # AsyncSSH/SFTP only; test adapter interface
    logengine/      # discovery, archives, timestamps, cursor tracking
    persistence/    # models, repositories, migrations
    security/       # vault, sessions, host trust, input policy
    app.py
  tests/
frontend/
  package.json
  package-lock.json
  src/
    api/            # generated types + authenticated client
    features/       # topology, inspector, investigations, live, settings
    components/     # virtualised viewer, forms, panels
    theme/
  tests/
deploy/             # OCI build, reverse proxy, Compose, Podman/systemd
scripts/            # dev/test/build/offline release and recovery tools
docs/, contracts/, fixtures/, assets/, progress/
```

This layout is a target, not an assertion that those files already exist. Root `AGENTS.md` remains short enough to guide work; detailed contracts stay in the appropriate documents.

## Design decisions that must not be reversed accidentally

Web, not desktop. SFTP reads and local processing, not interpolated `grep` shell commands. MariaDB canonical state, not competing live YAML and DB copies. Validated deployment DB endpoints, not a hard-coded service location. Model entities independent of view layout. No credentials in project files. Literal filters, bounded retention and visible coverage. No false exactly-once promise. No Internet services required at runtime. MariaDB and the reverse proxy are bundled local/LAN deployment services.

## Version 2 configuration boundaries

Deployment YAML is read before connecting to MariaDB and provides its host, port, database name, user, password-file/TLS settings and operational ceilings. Admin-editable application settings live in MariaDB with revisions and audit entries; bootstrap defaults are applied only on first initialization. Personal appearance/layout preferences are separate user-owned records. Project interchange cannot change deployment endpoints, accounts, roles, vault/trust or global appearance. See documents 03, 13 and 14.

One backend is retained despite multiple accounts; resource limits apply globally as well as per user. Use bounded per-user job queues and an Administrator-visible aggregate usage panel so several Inspectors cannot multiply the original workload without limits. Session validation must fail closed during a DB outage.


## Version 3 deployment and workspace boundaries

Multiple System configurations reuse the existing Project entity. There is still one backend supervisor and MariaDB database; two browser windows are independent clients, not competing serving processes. `ProjectService` now supplies the catalogue/lifecycle; `WorkspaceService` owns server-assigned per-page contexts and live control leases. Follow document 16 in every service and repository.

Pass immutable, authorized project context explicitly through collection/planning/query/cache/SSH/import operations. A live collector may share immutable raw capture for the same project/owner/source/trust revision, but each workspace owns separate live sessions, filters, counters, replay and UI state. Reserve per-workspace/project/user/global budgets atomically. Never key pools, React query caches or MariaDB lookups by hostname/process ID alone. Source/cache/event identity includes project even when local IDs repeat.

The URL selects the project for each page. No auth-session/global active-project singleton, shared current-system cookie or localStorage-driven router is allowed. One page's navigation/filter/stop cannot broadcast a state replacement to another. Auth revocation and account-wide theme preferences remain intentionally shared. Current single-worker/lock rules apply to the backend deployment only. The historical `concurrent_hosts` limit must not cap persistent live-source connections at four; test the required two × five baseline.
