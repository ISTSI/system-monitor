# Incremental v3 implementation plan — 17 October 2026

## Inspected starting point

The supplied tree contained specifications, contracts, fixtures, package helpers and deployment examples only. No `backend`, `frontend`, migrations, lockfiles, runtime database, cache, live deployment state or Git metadata existed. `git status --short` and `git log -5 --oneline` both reported “not a git repository.” There is no v1 prerequisite to apply, no SQLite deployment to migrate, and no existing user data to backfill. All 166 original manifest file hashes/sizes were independently verified before edits. Package helper code is retained as test tooling and is not application authorization or persistence.

Version dimensions remain distinct: package 3.0, project interchange 2.0, deployment 2.0 with optional v3 limits, workspace/catalogue 1.0, future WS protocol 2, and first actual Alembic revision `0001_scoped_foundation`. Existing fixture Project/event IDs, assets, expected results and deployment examples remain unchanged.

## Review slices

1. **Current slice, backend foundation:** explicit immutable ProjectContext; one MariaDB endpoint; secure local accounts and opaque sessions; named Project catalogue and revisioned metadata; server-issued owner/project workspaces; composite workspace-to-project-revision constraint; bounded quotas, supervision and initial migration. Unit/API boundary tests and guarded real-MariaDB tests. Stop for review. Stage 01 remains incomplete until real DB validation and browser foundation exist.
2. **Current continuation, finish Stage 00/01:** use the user-approved temporary MariaDB 12.3.3 VM database `system-monitor` through the existing workstation SSH tunnel while Docker Desktop is unavailable. The schema is migrated and rollback-only database checks pass; obtain a separate DML-only runtime identity before serving, then complete the original disposable-database integration tests when their separate schema/accounts are available. Preserve the prepared Docker setup and its image/offline/volume lifecycle gates for later validation. Then add Node 24 LTS/React/TypeScript/Vite locks and the two-themed browser catalogue/workspace shell with generated clients. Test different-system and duplicated same-system pages in one browser context/account, fresh bootstrap on reload and no collection on GET. Complete account lifecycle/last-Administrator concurrency, preferences, settings and authenticated foundation gates before Stage 02.
3. **Stage 02 topology/config — implemented; review gate:** scoped MariaDB topology entities and composite FK pairs; graph/documentation CRUD, explicit reparenting, directed flows, named geometry, undo/redo, system-local search/reveal and safe Inspector projection. Schema-2.0 YAML/JSON interchange has explicit v1 conversion, target-project remapping, bound previews, optimistic transactions and immutable-ID/name history. Real database and browser evidence and remaining limits are recorded below. No singleton active project and no log collection.
4. **Stages 03/04 historical/SSH:** carry ProjectContext through source planning, exact integer-microsecond indexing, private investigation parents, query/cursor/download grants, raw-cache namespaces and strict host/root/trust/credential-binding contexts. Preserve event IDs; resource identity is `(project_id,event_id)`. SFTP integration uses local synthetic hosts only after local environment authorization. No cross-system raw-byte deduplication or shell commands.
5. **Stage 05 live:** required workspace IDs and controller leases; explicit detached resume and revision conflicts; WS protocol 2 validates project/workspace/session on every frame; page-local filters/replay. Reserve subscription budgets atomically: defaults 5/workspace and 10/project/user/deployment, preserving explicit lower legacy ceilings. Test two × five and rejected-eleventh isolation, slow/background pages and global logout with a local SSH fixture.
6. **Stage 06 investigation:** project/owner-scoped notes, bookmarks, source/event joins, context/correlation, redacted bundles and expiring grants; source IDs unchanged, no existence leaks or broad administrative content access.
7. **Stage 07 inventory/UI:** direct bounded static INI, extensionless hosts and YAML, plus validated relative `group_vars`/`host_vars` ZIP and canonical JSON. Never execute Ansible/plugins/Jinja/ProxyCommand, inspect uploaded `ansible.cfg`, or read referenced host files. Preserve host-only imports and optional explicit processes. Bind upload/source/mapping/preview/commit identity to project, account/auth version, revision, content/manifest hash and expiry; commit transactionally with idempotent reconciliation. Reimport into A and B with colliding aliases, then change A only. Keep missing hosts and unrelated manual data.
8. **Stage 08 release:** scoped multi-system DB/cache backup and checksummed manifests, restored owner mappings and interrupted sessions, offline image save/load/cold start on Ubuntu and Rocky, Podman/systemd, security/advisory/license review and bounded performance. Real-data migration dry-runs need disposable copies plus explicit authorization and matching rollback artifacts. Never infer a default project for ambiguous rows or keep unscoped legacy operations that guess one.

## Authorized MariaDB provisioning follow-up — 17 October 2026

Before continuing the browser foundation, set up the project's own MariaDB container and database. This is explicit implementation work authorized by the user's follow-up, not an assumption that an external test environment must already exist.

1. Create `deploy/local-mariadb/` with a pinned official MariaDB 11.8 maintenance image, private Docker network, persistent named volume, health check and no published database port. Record real registry digests; stage images on the connected preparation host.
2. Generate protected local password files and initialize database `system_inspector`, runtime identity `inspector_app` with SELECT/INSERT/UPDATE/DELETE only, and separate schema-scoped DDL identity `inspector_migrator`. Root is provisioning-only. Retain volumes, secrets and existing data across reruns.
3. Build a non-root Linux Python 3.13 runner from the real backend lockfile. Mount source/configuration read-only and only each operation's required secret files; the serving runtime receives neither root nor migration secrets. This preserves POSIX deployment paths when developing from Windows.
4. Start MariaDB, await health, verify separate grants, and apply the existing Alembic revision to the project database explicitly. Never execute migrations during serving.
5. Provision a fresh `inspector_test_<suffix>` database with independent runtime/migration identities per integration run. Run the 13 actual-MariaDB tests, including repeated local IDs and invalid composite FK INSERT/UPDATE. Refuse occupied schemas and never delete a database to make a test pass.
6. Verify retained-volume restart and cold startup from preloaded images with runtime network access unavailable. Record commands/results, failed checks and remaining Stage 01 gaps. Continue the browser foundation only at its reviewed scope.

If Docker access requires a Windows administrator, prepare and statically validate all files first and report the exact host change required. Do not claim the database exists until Docker initialization and migration actually succeed.

## Risks and assumptions

- The user added Docker group membership but Docker Desktop remains unavailable due to sign-in/account issues. It no longer blocks direct database development: the authorized VM replacement is initialized and real migration/FK/service checks pass. The VPN and existing pinned-host-key tunnel must stay running; do not stop/reconfigure them or use another host's localhost. No production deployment or unrelated infrastructure access is authorized.
- The current MariaDB schema stores the complete scoped topology/configuration, normalized relationships, views, import previews, bounded undo history and retained identity/name snapshots. Actual topology collisions and composite-FK rejection are tested; source/event identities and operational log resources remain Stage 03–06 work.
- Fresh-schema revision is not an upgrade utility. Existing populated installations require an inventory of actual parent relationships and an approved backup/restore dry-run before additional migration code is accepted.
- Runtime dependency locks are real registry resolutions, but Linux wheel compatibility and a security advisory audit remain open. No exact container digest or frontend dependency lock has been invented.
- Authentication and current service operations use short serialized transactions. Do not extend their lifetime across streaming/network/file operations in subsequent slices.

## Authorized temporary VM alternative — 17 October 2026

Use [the VM setup](../deploy/vm-mariadb/README.md) for the currently approved endpoint `127.0.0.1:13306`, database `system-monitor`, MariaDB 12.3.3. Save credentials only in ignored protected files; retain the user's tunnel and VPN. `ssh_tunnel` is an explicit loopback-only development transport, with no claim of end-to-end database TLS; ordinary external connections retain verified TLS. Allow the supplied hyphenated identifiers and safe Windows host-tooling paths while keeping Linux production.

The initial migration completed in the previously empty database. Preserve its default collation; application tables and identities explicitly use binary collations. Real tests use a single rollback-only transaction and verify unchanged committed rows. Do not create unrelated schemas/users, change server defaults, or relax existing integration guards. The provided full-schema account is migration-only. A separate DML-only runtime account needs DBA provisioning from the prepared ignored SQL file; serving rejects the migration account based on actual grants. Container, backup/restore, Linux runtime and browser gates remain open.


## Stage 01 completion follow-up — 17 October 2026

The user confirmed runtime DBA provisioning and explicitly authorized the rest of
Stage 01. The DML-only account is verified and the approved VM hosts the running
HTTPS browser foundation. Migration 0002 retained original rows and added account
restriction/preferences/settings and explicit read-only synthetic documentation.
React/TypeScript/Vite locks, generated API types, both themes, account management,
revisioned preferences/defaults, system catalogue/archive/restore and independent
page workspaces are implemented. The final browser suite and zoom equivalent
check pass; test data remains labelled and no target connections are started.

Docker's Linux engine is now reachable under the signed-in account using the
explicit local pipe and repository-local CLI config. This supersedes the earlier
Docker blockers without changing the VM tunnel/VPN. The pinned MariaDB 11.8.9
service, separate runtime/migration identities and original 19-test integration
suite now run locally. The optional VM test-database DBA script is no longer a
prerequisite. Final image/lifecycle results and exact commands are in STATUS.md.

The Stage 01 review gate passed; the user's subsequent instruction authorized
Stage 02. The retained labelled Stage 01 demo is reconciled into the canonical
topology at startup when its derived topology state is absent. Full SSH/logs,
inventory import, Ubuntu/Rocky deployment and Stage 08 release gates remain
future work.

## Stage 02 review gate — 17 October 2026

The implemented vertical slice uses actual React Flow components and MariaDB
transactions for subsystem/server/process CRUD, directed labelled flows, shared
documentation, independent named views and validated reparenting. Model IDs are
separate from geometry. Administrator mutations, safe Inspector navigation,
project-local search/reveal, delete-impact confirmation, undo/redo, catalogue
archive/restore and YAML/JSON preview/commit/export are connected to the real API.
Imported roots and credentials remain unresolved proposals; no SSH trust,
credential binding, target enablement or collection is created.

Verification evidence:

- **253 backend unit tests passed**, including bounded parsing, semantic
  validation, v1 conversion, unsafe configuration and safe error responses:
  [configuration tests](../backend/tests/unit/test_project_config.py) and
  [recorded unit output](../verification/stage-2/checks/unit.log).
- **30 real Linux MariaDB 11.8.9 integration tests passed in 23.56 seconds**.
  [Ten topology tests](../backend/tests/integration/test_topology.py) cover scoped
  CRUD/revisions/search, forged Inspector writes, explicit parents, deletion and
  history, imports, composite FK rejection, archive/restore and concurrent edits.
  [Startup-backfill coverage](../backend/tests/integration/test_topology_upgrade.py)
  preserves Stage 01 project IDs/revisions/docs/accounts and repeated entity IDs
  across two systems. See [integration output](../verification/stage-2/s2_final_1017.log).
- **Four topology browser tests passed in 10.7 seconds**, covering graph forms,
  stable-ID rename/flows, reparenting, views, collapsed-process search, JSON
  roundtrip, deletion/undo, duplicate-ID refusal, same-context stale drafts and
  Inspector navigation in both themes/sizes and persisted drag/resize. **Ten foundation browser tests
  passed**, including independent same-context pages, keyboard,
  200% layout equivalent and delayed-authentication regressions. See
  [topology tests/report](../frontend/e2e/topology.spec.ts) /
  [result](../verification/stage-2/browser-final.json) and
  [foundation tests](../frontend/e2e/foundation.spec.ts) /
  [result](../verification/stage-2/browser-foundation.json).
- The geometry browser test confirms drag and resize save through real API
  transactions, survive reload and preserve server/process ownership.

Bounds are explicit: 10 MiB UTF-8/serialized project configuration, nesting 32,
200,000 tree nodes, 5,000 configured entities, project description 10,000
characters and finite canvas geometry of magnitude at most 10,000,000. Full
snapshots retain current/undo/redo states; compact historical names and identity
tombstones survive pruning.

AT12 remains partial until real bookmarks, notes, log associations and sessions
exist. AT101's active-job drain/start races and cached investigations also remain
later-stage work. Fresh schema installation through Alembic 0003/0004,
idempotent demo startup backfill and a guarded populated 0002-to-0004 upgrade
passed. The latter preserves two synthetic systems, accounts/password verification,
preferences, metadata, revisions and documentation. No VM or production database
was upgraded, and no existing database was downgraded to manufacture evidence.
Ansible file/bundle import remains Stage 07, distinct from implemented project
configuration import. Stop at the Stage 02 review gate; Stage 03 requires its
separate prompt before historical/log-engine implementation.

## Stage 04 review gate - 17 October 2026

Stage 03 historical parsing/index/query and Stage 04 approved SSH collection are
implemented. Direct and single-jump SFTP download the complete golden fixtures
into the same bounded engine. Local source/root approval remains separate from
configuration import and host-key trust; every remote job binds its owner,
project, login, configuration and current access versions. Same-account browser
pages keep separate workspaces, captures and filters. The final Stage 04 Linux
MariaDB run passes 89 cases, with 23 distinct passing browser scenarios across
the SSH and regression suites. Actual commands, unit counts, failures corrected,
platform limits and the local additive migration/backup are in STATUS.md.

Stop at this review gate. The next authorized stage must be
`prompts/05_LIVE_MONITORING.md`; no live following, reconnect loop, live socket,
live buffer or viewport seed implementation was added in Stage 04. Full saved
analysis, Ansible import and offline release remain their separate stages.
