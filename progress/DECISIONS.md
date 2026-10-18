# Implementation decision log — version 3

Use this file for actual implementation decisions. Preserve an existing repository's decision history when applying the upgrade; do not silently change confirmed requirements.

Fixed decisions: Linux web UI; Python/FastAPI/AsyncSSH; React/TypeScript; MariaDB only via SQLAlchemy/asyncmy/Alembic; read-only agentless SFTP; one jump hop; dedicated non-sudo target credentials; literal filters; UTC [from,to); offline runtime; Administrator/Inspector with backend authorization; Cool Slate light and Graphite Dusk dark themes.

Package defaults: configurable System Inspector branding, English UI, dark shared default and personal default/light/dark/system preferences, owned investigations for both roles, no automatic process-health checks, one ASGI worker and MariaDB supervisor lock, direct local-cache storage, application-encrypted SSH secrets. Managed official MariaDB image is provisioned alongside app/proxy; existing verified-TLS database endpoint is also supported. Account limits and personal-analysis exceptions are design defaults, not new independently supplied infrastructure facts.

Record date, alternatives, chosen resolution, affected contracts/tests and user approval when needed. Resolve and record compatible package/image versions in the authorized connected build environment; never invent digests.


Version 3 fixed requirements: multiple named systems per deployment; same-account independent parallel browser windows; direct Ansible INI/YAML/extensionless inventory reading and supported companion-file bundles. Package defaults: System uses existing Project/project_id, application-global roles (no per-system ACLs), URL-local selection, fresh server-issued workspaces with explicit detached-session resume, project-scoped identities/approvals/resources, no cross-project raw-byte deduplication, 5 live subscriptions/workspace and 10/project/user/deployment. These defaults and scope design must be preserved or explicitly reviewed against a demonstrated blocker.

## 17 October 2026 — first review slice

- Inspection found no application/data/Git metadata. Build fresh v3 foundations; no conditional v1 migration or arbitrary default-system mapping applies. Preserve all delivered fixtures/assets/contracts. Backend slice only, then review; Stage 00/01 incomplete runtime/browser gates remain visible.
- Project is the sole System entity. The initial schema contains global accounts/sessions/audit plus Projects, metadata revisions and server-owned workspaces. Composite `(project_id,opened_revision)` foreign key preserves page snapshots. No competing System table or mutable auth/current-project exists. Topology/source/event scope will be added together with their callers in later staged slices.
- Runtime credentials load from validated deployment password files; explicit migration identity overrides are read only by the migration CLI. DML serving identity has no migration execution. External DB TLS verifies CA and hostname. No SQLite substitute, production connection or container startup occurs.
- Initial security transactions serialize on one seeded row with security → account → project → workspace lock order and READ COMMITTED isolation. This avoids stale quota counts and lock inversions. Argon2 runs in two bounded off-loop workers; probes on the dedicated supervisor connection serialize. Lost supervisor ownership stays failed until restart; initial startup/read operations have explicit bounds. Future SSH/stream/file work must run outside these transactions.
- API commits before sending success, uses declared contract action identifiers, safe response schemas and separate denial-audit transactions after rollback. Exact Host/write Origin, pre-session login CSRF, opaque hashed sessions, authenticated CSRF and Secure/HttpOnly/Strict cookies are required. Logout revokes the whole account intentionally. Workspace GET polling renews page expiry without renewing login idle; deliberate writes and explicit session access can renew idle, subject to absolute expiry.
- Workspace lifetime is initially 300 seconds; active polling renews it, detach does not grant adoption, and expiry releases only that workspace's reservation. No live control/resume behavior is claimed until its lease slice. Demo CLI seeds clearly labelled catalogue entries only and refuses any existing demo IDs.
- Keep source package checks cross-platform without changing expected outcomes: UTF-8 decoding, prune generated dependency trees, and inspect raw ZIP member names before normalization. Package helpers remain test oracles and are never imported into application services.
- Backend dependencies/toolchain are actual resolutions recorded in TOOLCHAIN.md and uv.lock; source wheel build passed locally. Frontend toolchain, Linux/MariaDB/image digests, full runtime license/advisory audit and offline lifecycle remain blocked/pending, with no fabricated versions or verification.

## 17 October 2026 — local MariaDB setup follow-up

- The user authorized setting up the actual project container/database. Provision it in `deploy/local-mariadb/`, distinct from production examples and other applications. One `system_inspector` schema contains all Projects; separate `inspector_test_<suffix>` schemas are test isolation, not a database per System.
- Use a private internal network and no published DB port. Run Python operations in a non-root Linux runner to preserve POSIX config paths from Windows. Mount each operation's own secret files and explicit source subtrees only. Retain the named volume and generated secrets; no reset/delete helper.
- Registry-resolved MariaDB 11.8.9/Python 3.13.16-slim Linux amd64 digests and hash-verified uv bootstrap are recorded. Connected image preparation is explicit; runtime pull policy is never. Registry resolution does not establish image, database or Linux compatibility tests.
- Bootstrap uses protected SQL rather than a sourced script so Windows executable bind-mount modes cannot change behavior. Escape underscore grant patterns, explicitly retain exact schema privileges, and avoid MySQL-only MariaDB configuration syntax. Root is local provisioning only; serving has runtime DML credentials only.
- Local setup supports private Windows ACLs for the tool identity and explicitly designated real Docker owner. Normal workspace commands run under the tool sandbox account; reviewed host commands run under the signed-in account. No passwords are printed, stored in argv or copied into versioned configuration.
- Docker Desktop is blocked by its `docker-users` membership check and a missing Linux engine pipe; the user is enabling it. Complete setup files/static/unit checks now; actual creation/migration and the 13 database tests remain pending until the engine becomes reachable. This is a host prerequisite, not an automatic approval-review rejection.

## 17 October 2026 — user-authorized temporary VM database

- Docker group membership was added, but Desktop sign-in remains unavailable. The user supplied an existing empty MariaDB 12.3.3 schema through an already-running pinned-host-key VPN/SSH tunnel. Use that explicit endpoint; preserve the VPN/tunnel and do not require Docker for current database work. No new SSH command was necessary.
- Retain hyphenated `system-monitor` schema/account names and the database's default collation. SQLAlchemy URL construction and bound metadata scope avoid manual DSNs; explicit SQL identifiers remain quoted. Application tables/identity columns retain binary collations, verified on the actual server.
- Add an explicit loopback-only `ssh_tunnel` development topology and safe Windows host-tooling paths to deployment schema 2.0. This narrowly implements the latest instruction; direct external database TLS rules remain strict. Do not claim end-to-end MariaDB TLS or change Linux production requirements.
- The supplied schema-wide account is migration-only and cannot delegate/create the needed runtime user. Enforce runtime privileges from actual grants before serving starts, instead of relying on a username convention. Prepare separate private runtime credentials/DBA SQL; never serve with the provided DDL account.
- Migrate only after checking selected schema, server product and empty-table state under the migration lock. Preserve injected-connection lock ownership and commit the migration version explicitly. Refuse partial/incompatible schema states rather than resetting them. Subsequent initialization is idempotent.
- Four real VM tests exercise scoped services/constraints and safe migration-account refusal. All synthetic rows roll back and committed counts are verified afterward. Do not weaken or relabel the original disposable-schema/DML-account integration suite; full API/browser/offline gates remain open.


## 17 October 2026 — remaining Stage 01 authorized and implemented

- The user confirmed DBA execution. Actual grants verify the VM runtime identity
  has only exact-schema DML. Serving uses the runtime password file, never the
  supplied schema-wide migration identity. Explicit migration 0002 compared all
  original rows and retained a private pre-migration snapshot.
- Persist account appearance and application branding/default theme in MariaDB
  with independent optimistic revisions. Initialize deployment defaults only when
  the singleton is absent. Preferences cannot assign roles/ownership/settings.
  Account changes serialize the last-Administrator guard and revoke sessions and
  owned workspaces. Authentication polling never extends the idle timeout.
- Keep synthetic demo documentation in an explicit project-owned DB snapshot with
  no connection profiles/approvals. Render it as read-only text/components and
  label it; production topology editing/schema remains Stage 02. Test-local IDs
  intentionally collide between the two demo projects.
- Each document owns its fresh server workspace and URL selection. Browser state
  stays in component memory; BroadcastChannel carries account authentication and
  appearance notifications only. Reload/duplicate/BFCache restore never adopts a
  workspace. Theme changes preserve page state and unsaved forms.
- Fence asynchronous account/session/preference completions by authentication
  generation. An old response cannot restore logged-out state or clear a newer
  login's CSRF state. Generic 401 responses do not delete cookies that might have
  been replaced by another request; a stale cookie can obtain pre-login CSRF.
- The real signed-in account can access Docker's Linux engine even though the
  sandbox tool account cannot. Use explicit local npipe plus workspace CLI config
  for reviewed Docker commands, with no login, daemon reconfiguration, VPN change
  or tunnel restart. Preserve the existing managed DB volume/secrets and use a new
  disposable integration schema. Original empty-schema/test guards stay intact.
- Build all browser assets locally into the wheel and non-root app image. Per-
  Dockerfile context allowlists exclude local secrets/toolchains. Runtime receives
  only runtime credentials and makes no dependency/update/telemetry calls. Full
  Stage 08 offline release assembly remains separate from Stage 01 lifecycle tests.

## Stage 05 implementation decisions — 17 October 2026

- Persist live ownership, configuration snapshots, quotas and revisioned control
  leases in MariaDB; raw source buffers/replay remain ephemeral. Restart records
  interruption and releases reservations without reopening SSH. The same
  singleton security lock serializes starts and transfers against all quotas.
- Reuse raw collectors and host connections only within complete matching
  project/owner/configuration/route/credential/trust/approval contexts. Every
  subscription owns its filters. Acquire live connection establishment slots
  separately from historical lifetime slots, so four historical host slots do
  not cap the required ten live subscriptions.
- Match the existing canonical live-create schema rather than inventing another
  interchange shape. Generated API responses/control models expose explicit
  typed snapshots and lease/filter revisions. WebSocket event batches preserve
  the canonical `payload.items` contract; late flags fit its string metadata.
- Install a locked WebSocket implementation because minimal Uvicorn has none.
  The initial wsproto adapter enforces message bytes but Uvicorn 0.54 ignores
  `ws_max_queue` for that adapter and its SansIO adapter. Use Uvicorn's explicit
  `websockets` adapter, which forwards both message-byte and message-count limits
  to the library. Its legacy API is deprecated upstream; cap the compatible
  major range and require actual TCP fragmentation/backpressure regressions on
  upgrades. Keep wsproto as a development dependency for raw-wire tests. Preserve
  actual resolver locks and original notices. Build a separate Stage 05 test
  image; preserve retained images/services and do not install into them.
- Record exact captured byte ranges with original offsets, not reconstructed
  text. These recordings are explicitly partial historical investigations;
  refuse complete-source downloads and retain committed data after stop, cancel
  or interruption. The operational byte ceiling and 200,000-event cap prevent
  indefinitely growing individual recordings.
- Treat display pause as presentation state. Deadline-based merge wakeups avoid
  an extra polling tick, while idle sources never hold a timestamp watermark.
  Client frames and HTTP completions are fenced by scope, lease, filter version,
  sequence and terminal state. Retention resnapshots cannot roll the view back.
- Use fresh nonlocking reads for live background and established-socket
  authorization. Read the selected routes' project-scoped approvals, trust and
  credential bindings in bounded batches with the same validation/signature
  builders as individual checks. Share only validation still in flight for the
  same project/session; never cache a completed grant. Every protected socket
  dispatch still revalidates current login, owner and lease. State-changing
  controls and quota reservations retain their existing transaction locks.
- Use one fresh joined account/login/monitor/workspace read for each established
  socket check. Reuse pure validation rules with ordinary locked controls;
  reduce round trips without retaining a completed authorization result. Wait
  for database and engine filter versions to agree before constructing frames.
- Skip durable-recorder work for unsaved monitors. Save activation and retained
  backfill settle as one cancellation-shielded operation; shared collection
  checks new recorder consumers again after every awaited callback. Recording
  failure retains a partial investigation and stops only its affected monitor.
- Preserve the specified 750 ms polling and 500 ms merge deadlines. Keep path
  validation serial, but overlap the bounded pinned/named fingerprint reads and
  drain every peer on error/cancellation. Keep proved anchors on an unchanged
  cursor; after append, reuse only the full prefix proved in that poll and read
  the new tail. Read related source configuration/approval/credential rows in
  three scoped joins, preserving the existing validation and signature rules.
- Maintenance actions must take the monitor's control lock and recheck current
  state before applying an earlier scan's intent. An explicit Stop or workspace
  transfer must not be overwritten by a stale maintenance result.


## 18 October 2026 - Stage 06 investigation storage and exchange

- Retain historical job/investigation and source/event identities. Saved analysis
  uses a separate owner/project-scoped row with one optimistic revision shared
  by workspace/bookmark edits; no display name or graph position becomes a key.
- Whole-investigation pins preserve source cache. Bookmark pins preserve bounded
  independent text/provenance context snapshots. Explicit unpinned expiry keeps
  notes and pinned context, nulls live anchor FKs before removing index rows, and
  reports unavailable data independently of empty matches.
- Exchange exactly two versioned ZIP members: a manifest and typed investigation
  document. Stream validated regular members without extraction, validate actual
  lengths/SHA-256/version/identities, and require an owner/project/login-bound
  preview before import or download. All-string literal redaction includes keys,
  labels, filenames, notes, context and topology. Active connection/trust/secret
  fields are excluded through typed projections regardless of redaction rules.
- Imported documents are independent private offline data. Foreign IDs are origin
  provenance, never destination active-entity FKs. A separately revisioned
  OfflineAnalysis row allows notes/bookmarks/filter/layout edits and re-export
  while the original imported event document remains unchanged.
- Keep archive CPU/file work in the existing bounded executor, bound upload
  admission separately, and release DB/authentication locks before receiving a
  file or waiting on a worker. Reauthenticate the actual login before protected
  commit/dispatch; current User state alone cannot detect logout during a wait.
- Keep exact correlation equality in the scoped MariaDB query and quote metadata
  keys with the same ASCII escaping as SQLAlchemy's persisted JSON. Real MariaDB
  tests verify punctuation/quotes/Unicode and distinguish literal escape text.
  Literal matching retains the shared Unicode-casefold engine contract.
