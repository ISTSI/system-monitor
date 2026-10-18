# Implementation status — version 3

**Current: Stage 07 plus the language follow-up is installed locally at https://localhost:8445 (`0014_languages`).** The separately authorized upgrade used the exact tested artifact, a consistent protected recovery backup and separate migration credentials. Existing accounts, settings, topology, investigations and cache bytes were preserved; the 8444 installation is unchanged. Installed browser checks and independent preservation/security audits pass. Stage 01 on 8443 remains stopped. The isolated 8449 review fixture now runs the current topology/login and Filters/pins frontend/backend at `0015_remember_login`, following the explicit preview-update authorization. Stage 08 has not started. Exact results and limitations are recorded below; earlier blockers remain as dated history.

**Latest source follow-up (18 October 2026):** Live monitor uses `server: process`
labels and clearer gap/error/previous-monitor notices. Three isolated component
browser cases and 20 frontend unit tests pass, as do lint, typecheck and build.
Both themes were visually inspected. This source follow-up is not deployed;
installed environments and the separate Stage 08 gate remain unchanged.

**Earlier requested source follow-up (18 October 2026):** pins have compact
description/View rows, process-grouped previews, editable descriptions,
selection modification and explicit update-or-create choice. Collection UTC
bounds and pending processes are independent of retained display filters and
captured process lists. All six browser cases and 39 MariaDB/Linux integration
cases pass; see the final dated entries below. Following explicit deployment
authorization, this follow-up is now installed on 8449 with matching backend
and frontend, unchanged schema0015 and preserved data. Actual served-browser
and preservation checks pass. 8445 is unchanged; Stage 08 remains separate.

**Earlier topology/login follow-up (18 October 2026):** subsystem/server frame **+** buttons
open Add server/Add process with their parent preselected. New process paths use
the first connection log root. Login offers opt-in fixed 30-day **Remember me**.
The source requires `0015_remember_login` and passes 833 backend unit cases,
50 MariaDB/API cases, a populated migration/rollback check, 17 frontend unit
cases and three browser cases. It is now deployed on the retained 8449 preview,
with actual-served browser and data preservation checks passing; 8445 is
unchanged. The earlier separate 8450 browser fixture remains stopped.

**Results-controls source follow-up (18 October 2026):** results row-count changes now apply
immediately, separate process panes are clearly labelled, and Columns dismisses
on outside click/focus leaving/Escape. Five isolated browser cases, 17 frontend
unit cases, lint and build/typecheck pass. This correction is available for
review at https://localhost:8449; 8445 still serves the previously installed
events-table frontend. Use the Inspector entry in the protected
`.secrets/stage7-browser/accounts.json` for the temporary review setup.

The UTC controls and **Additional security measures** follow-ups are now
installed on 8445, now at schema `0014_languages`. The checkbox defaults to
checked; installation preserved the existing data and security policy. See the
dated installation entry below.

The separately authorized **English/Polish language follow-up is installed and
verified on 8445**, including shared default and personal selection, at
`0014_languages`. Its source verification and subsequent backed-up deployment
are recorded in the dated entries at the end of this document.

**Starting point: specification package only.** The dated entries preserve the inspection and implementation history.

| Stage | State | Evidence |
|---|---|---|
| 00 — Verify and plan | Complete for the foundation scope | Real toolchain/locks/notices; Linux package checks; plan and traceability |
| 01 — Foundation | Complete | 127 units, 23 VM API tests, 19 Linux DB tests, 10 browser cases, container lifecycle |
| 02 — Topology/config | Complete; review gate | 253 units, 30 Linux DB tests, populated upgrade, topology/foundation browser tests; evidence below |
| 03 — Historical log engine | Complete; review gate | 321 units, 47 Linux DB tests, 17 browser cases, populated upgrade; 20 MiB ingest 9.72 s and warmed query p95 at most 240.307 ms on the recorded development machine |
| 04 — SSH and collection | Complete; review gate | 463 Linux units (one platform skip), 89 real Linux DB/SSH tests, 23 distinct browser cases, populated upgrade and inspected UI; final evidence below |
| 05 — Live monitoring | Complete; installed locally on 8445 | 595 unit passes plus 4 platform skips, 136 real MariaDB cases, 44 Linux engine/SFTP/TCP cases, 8 browser cases, populated upgrade; paced concurrent-archive p95 1,592 ms at 3.995 appends/s; backed-up migration and installed browser/data checks passed |
| 06 — Investigation tools | Complete; installed locally on 8445 | 155 real MariaDB cases, personal/offline browser workflows, populated upgrade, backed-up local installation and preservation audit; dated evidence below |
| 07 — Import and UI completion | Complete; installed locally on 8445 | 800 Windows / 803 Linux unit passes; 168 MariaDB regression and 20 focused cases; 17 final browser cases plus visible-text/reference checks; 30-minute resource measurement; backed-up migration, installed browser and independent preservation/security audits |
| 08 — Release and hardening | Not started | — |

For each stage record changed files, requirement IDs, exact commands run, actual results, unexecuted checks and reasons, unresolved blockers and the next stage. Keep a distinction between a unit-tested adapter, an SSH integration tested in a local fixture environment, and a deployment verified on a real target OS.


Package handoff baseline: version 3 supplied scope/import contracts and synthetic helpers. Implementation evidence is in the dated entries below. Live capture is now covered by Stage 05; Ansible import remains Stage 07.

## 17 October 2026 — upgrade inspection and first backend review slice

Starting point verified: specifications only, no application, migrations, lockfiles, runtime data or Git repository. All 166 delivered hashes/sizes matched before edits. No default-system backfill or SQLite migration was applicable. Read CODEX_UPGRADE_PROMPT.md, AGENTS/README, CHANGELOG, requirements, foundation prompts and documents 02/03/05/07/10/13/14/16/17. Preserve the original stage table above as the delivered baseline; this entry records actual work.

Implemented a narrow backend slice: Python 3.13/FastAPI, real uv lock, required deployment-file/secret/TLS configuration, MariaDB-only async SQLAlchemy/asyncmy engine, explicit Alembic initial revision, global local accounts/opaque sessions/CSRF and safe audit, immutable ProjectContext, named catalogue/create/revisioned metadata, fresh server-owned project workspaces/read/detach/expiry, private ownership and atomic workspace caps. Composite workspace-to-project-revision identity permits repeated local IDs without a default system. Dedicated process/migration locks serialize correctly and fail closed. The current schema has seven tables; no topology/source/event schema or legacy-data migration is claimed.

Changed/added source groups:

- `backend/pyproject.toml`, `uv.lock`, `.python-version`, `README.md`, `openapi.json`, `alembic.ini`, `migrations/` and `src/inspector/` (config, database, domain/errors, auth/security, scoped services, API/CLI, persistence models, unchanged bundled deployment schema).
- `backend/tests/unit/` and `backend/tests/integration/`: real Argon2, boundary/error/secret/lock tests and 13 guarded actual-MariaDB cases. Integration checks include colliding names/IDs, direct FK INSERT/UPDATE, independent workspace controls, revocation/expiry, atomic quota/revisions and application restart; they are authored, not executed against a DB here.
- `.gitignore`, `Makefile`, `scripts/collect_backend_notices.py`, `scripts/verify_backend_slice.py`, original installed notices plus `third_party/backend/inventory.json`.
- `tools/validate_package.py`, `tools/inventory_fixture_reader.py`, `tests/package/test_package_validation.py`, `tests/package/test_v3_contracts.py`: explicit UTF-8 and pruned generated trees; preserve raw ZIP names on Windows and reject them before normalization. No expected result or rejection requirement was relaxed.
- `README.md`, `docs/12_TRACEABILITY.md`, this status, `progress/DECISIONS.md`, `V3_SLICE_PLAN.md`, `TOOLCHAIN.md`, and `verification/upgrade-slice-1/`. The generated change inventory lists each added/modified source/artifact file relative to the handoff; generated toolchains/cache/venvs/build archives are excluded.

Requirement evidence: parts of R04/R35/R37/R39/R40/R41/R42/R44/R46/R48/R49/R55/R56. Scope and ownership are implemented for the tables/routes present. Partial targets AT02/AT04/AT71/AT80/AT81/AT91/AT94/AT98/AT115 are mapped; none of these complete application targets is marked passed. AT01 package checks are reported separately from runtime tests.

Commands and actual results (repository root unless noted):

| Command | Result |
|---|---|
| `python tools/validate_package.py --verify-handoff` (before edits) | Failed before hash phase: default Windows cp1250 misread UTF-8 acceptance headings. Independent manifest byte/hash audit: 166/166 matched. Validator fixed with locale regression. |
| `python -m unittest discover -s tests/package -v` (initial Python 3.14, no dependencies) | 120 run, 95 passed, 25 skips (9 POSIX + 16 absent PyYAML); not complete verification. |
| `python tools/validate_schemas.py`; `python tools/validate_deployment_examples.py` (initial) | Blocked: missing jsonschema/PyYAML. Rerun successfully using locked backend environment. |
| `python -m venv .bootstrap`; `.bootstrap/Scripts/python.exe -m pip install --disable-pip-version-check uv` | Local environment created; initial network install failed WinError 10013. Reviewed escalation with `--retries 1` installed uv 0.13.1. |
| `.bootstrap/Scripts/uv.exe --cache-dir .cache/uv python install 3.13 --install-dir .toolchains/python` | Reviewed download installed repository-local Python 3.13.16. Unmanaged user-bin launcher not replaced. |
| `.bootstrap/Scripts/uv.exe --cache-dir .cache/uv lock --project backend --python .toolchains/python/cpython-3.13.16-windows-x86_64-none/python.exe`; corresponding `sync` | Real lock resolved/installed; final offline lock resolution succeeded. No global dependency install. |
| `backend/.venv/Scripts/python.exe scripts/collect_backend_notices.py` | Preserved original notices/metadata for 50 installed dependencies. |
| `backend/.venv/Scripts/python.exe scripts/verify_backend_slice.py` | Runs the exact commands below and writes individual logs plus command/cwd/exit records. Initial final-pass attempt exposed fixture-copy and Ruff-config inconsistencies; both corrected before final rerun. |
| `backend/.venv/Scripts/python.exe -m unittest discover -s tests/package -v` | 126 run: 117 passed, 9 Windows/POSIX skips. Full PyYAML checks now run; Windows raw ZIP-name defect fixed. |
| `backend/.venv/Scripts/python.exe tools/validate_package.py` | PASS: fixtures/expected results, all 56 requirements/120 target mappings and source links. Hash flag deliberately omitted after source edits. |
| `backend/.venv/Scripts/python.exe tools/validate_schemas.py` | PASS: 18 schemas, 102 valid instances, 36 rejected negative instances, 15 YAML files. |
| `backend/.venv/Scripts/python.exe tools/validate_deployment_examples.py` | PASS: 44 static checks; no Docker/schema runtime inferred. |
| `backend/.venv/Scripts/python.exe -m pytest tests/unit -v` (`backend/`) | 46 passed. Includes offline compilation of seven-table MariaDB migration SQL; this is not a database migration run. |
| `backend/.venv/Scripts/python.exe -m pytest tests/integration -v -rs` (`backend/`) | 13 skipped: `SI_TEST_DISPOSABLE_MARIADB=1` absent; no disposable database configuration or reachable Docker daemon. No DB contacted. |
| `backend/.venv/Scripts/python.exe -m ruff check --config backend/pyproject.toml backend/src backend/tests backend/migrations scripts`; corresponding `ruff format --check` | PASS. |
| `backend/.venv/Scripts/python.exe -m mypy src` (`backend/`) | PASS: 11 source files. |
| `backend/.venv/Scripts/python.exe -m hatchling build` (`backend/`) | PASS: source archive and Python wheel. No network/build isolation required; schema included. This is not an OCI/offline release. Earlier uv build attempts failed interpreter/build-environment selection; explicit backend interpreter build succeeded. |
| `INSPECTOR_CONFIG_FILE=<absolute examples/deployment-policy.example.yaml> backend/.venv/Scripts/python.exe -m inspector.cli openapi --output backend/openapi.json` | PASS; generated from actual Pydantic API, no DB connection. |

The machine-specific absolute argv/cwd and exit codes are in `verification/upgrade-slice-1/commands.json`; complete output is in its adjacent logs. Shell syntax above is abbreviated for readability; the log runner uses explicit interpreter argv without a shell. Root Make targets were created but `make` itself could not run because GNU Make is absent.

Unexecuted checks and exact blockers: Docker CLI 27.1.1 cannot open `//./pipe/docker_engine` (file missing); WSL enumeration is denied (`E_ACCESSDENIED`); Podman/MariaDB/MySQL clients are absent. No approved disposable DB configuration was supplied, so MariaDB FK/grant/migration/interruption/Unicode-password/outage/restart/backup/rollback/offline-image lifecycle checks did not run. Nine package tests need POSIX permissions/bash. Node/npm and browser toolchain/UI are absent: no frontend build, browser screenshots or same-browser-context two-page tests ran. No SSH code exists, so SSH/live/two × five tests are pending. Linux compatibility, complete account lifecycle/preferences/themes, generated frontend clients, frontend locks, image digests, license/advisory release audit and full offline release remain open. No production host/data, infrastructure, deployment, remote push or real-data upgrade was touched.

Compatibility gaps: no existing application was available to preserve/test operational compatibility; schema-2.0 interchange contracts and original IDs/assets remain unchanged. This is a fresh-schema foundation, not an upgrade tool. Catalogue metadata is not a topology importer. Workspaces have no live controller/attach implementation. Unimplemented legacy operational routes return no operational data and never guess a project. Live protocol 2, scoped sources/cache/downloads and direct inventory wizard are subsequent slices. Supplied custom deployment limits are read without rewriting; this slice enforces workspace limits only and does not claim live-capacity enforcement.

**Review gate: stop here.** Next reviewed slice: validate this backend against approved disposable Linux MariaDB, finish Stage 00 toolchain/image evidence, then complete Stage 01 themed browser/account foundation and same-context window tests. Follow `V3_SLICE_PLAN.md`; do not advance into topology/live/import release gates from unit-test success.

## 17 October 2026 — authorized local MariaDB provisioning

The user explicitly requested adding container/database provisioning to the plan and proceeding. Updated `V3_SLICE_PLAN.md`: provision the project's own MariaDB container and persistent `system_inspector` database before further browser work. This authorization covers local setup and independent disposable integration schemas, not production data or infrastructure.

Added `deploy/local-mariadb/compose.yaml`, `conf.d/inspector.cnf`, `images.lock.json`, Linux `runner.Dockerfile` and its build-context allowlist/bootstrap hash file, and a setup README. Added `scripts/local_mariadb.py`, `prepare_local_images.py`, `resolve_local_images.py`, helper safety tests and root `make db-*` targets. Updated backend setup documentation and the verification runner's output-directory option to retain the previous slice's logs. Package source scanning now also excludes private secret directories. Each added/modified file is inventoried in `verification/mariadb-setup/file_changes.json`.

Concrete setup: one private internal Docker network, retained named volume, official health check, resource bounds, no published DB port, localhost-only root, exact-schema runtime DML and separate migration accounts. Generated three independent passwords and first-boot SQL in ignored `.secrets/local-mariadb/`, plus ignored `.env.local` and `application.local.yaml`. Windows DACLs permit only the tool account, the designated signed-in Docker owner, SYSTEM and Administrators; real-owner readability was verified without printing values. Secret files are individually readable by their authorized container mounts, with the parent protected. Generated credentials were retained across ACL/bootstrap fixes and never rotated. First-boot SQL escapes database underscores in grants and sets deterministic exact schema privileges; MariaDB's unsupported MySQL `secure-file-priv=NULL` option is not used. The optional test provisioner creates new `inspector_test_<suffix>` schemas/accounts and refuses occupied names, with no drop/reset operation. Commands reject remote Docker endpoints and remote builder overrides.

Real registry evidence was resolved with daemon-free `docker manifest inspect --verbose`: MariaDB **11.8.9** and Python **3.13.16-slim**, Linux amd64 manifest digests in `images.lock.json` and `verification/mariadb-setup/registry-manifests.json`. The uv 0.13.1 Linux bootstrap wheel SHA256 was taken from actual PyPI metadata. These are registry-resolved references, not pulled/tested container claims. The Linux runner uses hash-verified bootstrap, locked dependencies, a non-root identity, read-only source/config and only operation-specific secrets. Runtime/migration/testing use the private database network with `pull_policy: never`.

Commands actually run:

| Command | Result |
|---|---|
| `Start-Process ...Docker Desktop.exe -WindowStyle Hidden`; `Start-Service com.docker.service` | Desktop handoff starts but engine fails its compatibility check; service cannot be opened by this non-administrator process. No runtime/OS installation attempted. |
| Read Docker `backend.error.json`; `docker --context desktop-linux info --format '{{.ServerVersion}} {{.OSType}}'` | Concrete error: signed-in execution account must join `docker-users`. Engine named pipe `dockerDesktopLinuxEngine` remains missing. `docker-engine.log` records the final check. |
| `backend/.venv/Scripts/python.exe scripts/resolve_local_images.py --refresh` | PASS: actual official registry platform digests recorded. No daemon, image pull or container needed. |
| `backend/.venv/Scripts/python.exe scripts/local_mariadb.py prepare` | PASS: local secrets and explicit Linux deployment config created without contacting a database. Windows ACL provider initially failed its privilege check before secret writing; DACL-only implementation then succeeded. |
| `... local_mariadb.py secure-secrets --windows-owner <signed-in-account>` | PASS: tool and real Docker account retain access, no secret payload/database data changed. Real-account read check passed with no values displayed. |
| Refresh generated bootstrap from the retained runtime secret using `bootstrap_sql()` | PASS: corrected exact grant patterns, all existing passwords preserved, no DB contacted. |
| `docker --config .cache/docker compose --env-file deploy/local-mariadb/.env.local -f deploy/local-mariadb/compose.yaml config --quiet` | PASS: actual Compose v2 validates all prepared service/config/secret definitions without a daemon. |
| Parse generated `application.local.yaml` with application `parse_config` | PASS: runtime host `mariadb`, port 3306, database `system_inspector`, user/password-file/TLS/pool fields match the container setup. |
| `backend/.venv/Scripts/python.exe scripts/prepare_local_images.py --connected` | Blocked before any image pull: no running local Linux Docker engine. |
| `backend/.venv/Scripts/python.exe scripts/local_mariadb.py up` | Blocked by the same missing Docker engine. No container/database/volume was created. |
| `backend/.venv/Scripts/python.exe scripts/verify_backend_slice.py --output-dir verification/mariadb-setup` | All executable checks pass; current output includes unit/package/lint/type/build/schema logs. MariaDB integration remains explicitly skipped, not accepted. |

Verification: **62 backend unit/boundary/setup tests passed**, including 16 new provisioning tests; **117 package tests passed**, with nine POSIX-specific skips. Schema/deployment checks, lint/format, mypy and Python wheel/source build pass. **13 actual-MariaDB tests remain skipped** because no running container/test DB exists. No database creation, migration, grants, retained-volume restart, database outage or offline-image lifecycle test is claimed completed.

The user has said they will enable Docker Desktop. While that host change is pending, the setup and protected local credentials are ready. Once the local Linux engine is reachable, continue the already-authorized sequence: `prepare_local_images.py --connected` → `local_mariadb.py up` → `local_mariadb.py migrate` → `local_mariadb.py new-test --run` → grant/restart/offline checks. Do not rerun `prepare` over the retained setup. Leave later browser/topology stages at their gates.

## 17 October 2026 — approved VM MariaDB replacement, migration and real checks

The user supplied a temporary MariaDB VM because Docker Desktop sign-in is unavailable. Authorized endpoint: the existing Windows-workstation SSH forward at `127.0.0.1:13306`, existing empty database/account `system-monitor`, MariaDB 12.3.3. The company VPN and existing pinned-host-key tunnel were reused without stopping, restarting or reconfiguring either. No Docker, VM/container restart, unrelated schema or production deployment was attempted.

Stored the supplied password using non-echoing input in ignored `.secrets/vm-mariadb/migration_password`, protected by the existing Windows private-directory DACL strategy for tool and real owner. No plaintext password appears in argv, committed source, normal output or verification logs. Ignored `deploy/vm-mariadb/migration.local.yaml` and `.env.local` contain only endpoint/account names and password-file references; no password values or credential DSNs. Prepared a separate random runtime password and DBA-ready SQL in ignored `.secrets/vm-mariadb/runtime_password` and `provision_runtime.sql`; that SQL has not been executed by Codex.

Read-only probing confirmed `12.3.3-MariaDB-ubu2404`, selected database `system-monitor`, utf8mb4/default `utf8mb4_unicode_ci`, and zero tables. Sanitized grants show USAGE plus schema-wide ALL with no GRANT OPTION or global CREATE USER. The supplied identity is therefore migration-only. New serving-startup validation checks actual grants and rejects ALL, other/global schema rights, roles, GRANT OPTION and incomplete privileges; only exact-schema SELECT/INSERT/UPDATE/DELETE plus global USAGE are accepted. No serving application was started with the supplied identity.

Explicitly applied `0001_scoped_foundation` to the verified empty database. Result: seven application tables plus `alembic_version`; security_state contains its single bootstrap guard, all application/user/project/session/audit/workspace rows remain empty. The database's existing default collation was preserved. Real metadata confirms InnoDB and binary application-table/identity collations. The existing schema and account identifiers were retained; SQL identifiers are quoted where used, metadata scope is bound, and connection URLs use URL.create. Rechecking initialization reports `already_initialized` without resetting data.

Contract refinements required by the latest user instruction: schema-2.0 database/account names now accept bounded ASCII hyphens; host tooling accepts validated drive-qualified Windows forward-slash paths; new explicit `ssh_tunnel` topology permits only literal loopback and disabled database TLS/null CA. Ordinary external verified-TLS rules remain unchanged. This temporary operator-managed SSH path does not claim end-to-end MariaDB TLS. Linux production and Docker image/lifecycle gates remain in scope. These decisions are documented in docs/14 and the plan rather than pretending this is the managed-container TLS exception.

Changed files: canonical/bundled deployment schemas, `backend/src/inspector/config.py`, `database.py`, `backend/migrations/env.py`, unit config/runtime-grant/helper tests, `backend/tests/vm/test_vm_mariadb.py`, `scripts/probe_mariadb.py`, `vm_mariadb.py`, optional VM verification in `verify_backend_slice.py`, `deploy/vm-mariadb/README.md`, contract/backend documentation, plan/decisions/toolchain/traceability and this status. Full inventory and exact argv/cwd/exit records are under `verification/vm-mariadb/`; private credential directories/local YAML are excluded from that source inventory.

Commands actually run and outcomes:

| Command | Result |
|---|---|
| `probe_mariadb.py --host 127.0.0.1 --port 13306 --database system-monitor --username system-monitor --password-file .secrets/vm-mariadb/migration_password --output verification/vm-mariadb/probe.json` | PASS: connected through existing tunnel, schema empty, version/charset/collation and sanitized privileges recorded; no writes. |
| `vm_mariadb.py prepare --host 127.0.0.1 --port 13306 --database system-monitor --username system-monitor --password-file .secrets/vm-mariadb/migration_password` | PASS: ignored validated migration config/environment references prepared. |
| `vm_mariadb.py initialize --expected-database system-monitor` | PASS: first real migration, eight total tables. MariaDB warns that PRIMARY key names are ignored; constraints remain enforced, as verified below. |
| Same initialize command with `--output verification/vm-mariadb/migration-recheck.json` | PASS: idempotent already-initialized check; no data reset. |
| `vm_mariadb.py runtime-request --username system-monitor-app` | PASS: prepared private DBA request only; supplied account cannot create/delegate the required runtime identity. |
| With `SI_TEST_APPROVED_SCHEMA=system-monitor` and `INSPECTOR_VM_MIGRATION_CONFIG=<absolute ignored migration YAML>`, `python -m pytest backend/tests/vm/test_vm_mariadb.py -v --tb=short -rs` | **4 passed against actual MariaDB**. Metadata, colliding IDs/ownership/role checks, exact BIGINT values, invalid composite FK INSERT/UPDATE, named migration exclusion/release and refusal of migration credentials for serving. Synthetic rows always rolled back; fresh-connection counts unchanged. |
| Post-migration probe to `verification/vm-mariadb/post-migration-probe.json` | PASS: eight tables; default collation and existing grants unchanged; tunnel remains usable. |
| `python -m pytest backend/tests/unit -q` | **112 passed**: parsing, security, API boundaries, runtime-grant checks and provisioning safeguards. |
| `python -m unittest discover -s tests/package -v` | **117 passed**, nine POSIX-only skips; package expectations remain intact. |
| `python scripts/verify_backend_slice.py --output-dir verification/vm-mariadb` with the VM opt-in/config | Package/schema/deployment-static, lint, mypy, build/OpenAPI and real VM checks pass; original integration suite remains explicitly skipped. The first format check found one unformatted addition in the verification runner; Ruff corrected it and the full format recheck passed. Original failure and recheck are retained in adjacent logs/command records. |

All Python commands used `backend/.venv/Scripts/python.exe`. A source/log scan compares the private supplied/runtime password values without printing them and records only absence/count results. Runtime SQL and secret payloads remain private/ignored. No real-data backup/rollback claim is made: the authorized schema was empty before first initialization; only synthetic transactional test rows were rolled back afterward.

Remaining gates: a DBA must provision the distinct runtime account before app startup; the user has said they will have the DBA run the private SQL. The original 13-test suite still needs its separately approved empty disposable schema and distinct runtime/migration accounts; its guards and denied-grant assertions were not relaxed. No complete runtime/API/browser, Linux-host runtime, Docker restart/offline lifecycle, backup/restore or full Stage 01 completion is claimed. MariaDB 12.3.3 is verified for this limited development slice, not substituted for the pinned managed-image release baseline. Next: verify the new runtime account once confirmed, then resume the reviewed foundation scope.


## 17 October 2026 - Stage 01 completion implementation and verification

The user confirmed that the DBA executed the runtime-account script and explicitly
authorized the rest of Stage 01. Verified the supplied runtime identity's actual
exact-schema SELECT/INSERT/UPDATE/DELETE grants. The approved VM and existing
workstation VPN/SSH tunnel remain in use without restart/reconfiguration. No
production data, target host, remote push or deployment was contacted/performed.

Implemented the remaining foundation: account enable/disable/roles/password reset,
session revoke, forced password change, concurrent last-Administrator protection,
auth-version/session/workspace revocation and safe audit; persisted personal
appearance and revisioned application branding/defaults; safe public bootstrap and
Administrator diagnostics; metadata/archive/restore; labelled read-only synthetic
documentation in two systems. Migration 0002 adds the required columns/tables and
compares all seven original tables to a protected pre-migration snapshot. Original
rows and database default collation are preserved; binary app/identity collations
remain explicit. New schema revision is `0002_foundation_preferences`.

Added the React/TypeScript/Vite browser workspace with actual dependency locks,
generated API types, responsive Cool Slate/Graphite Dusk components, real login,
role-specific management/settings, persisted appearance and catalogue/UI mutations.
Each URL-selected page creates a fresh server workspace; page search/selection/
panels stay in component memory. Shared BroadcastChannel messages concern account
login/logout/appearance only. Theme changes preserve unsaved forms/page state.
Authentication polling does not extend idle expiry. Authentication generation
fences prevent delayed successful or failed responses from restoring logged-out
state or clearing a newer session/CSRF value. Stale cookies can obtain login CSRF;
generic 401s never delete a cookie that a concurrent login might have replaced.

Docker became accessible through the signed-in account on the explicit local
Linux-engine pipe, despite the sandbox account's denied pipe access. This
supersedes earlier daemon blockers. Used repository-local Docker CLI config, no
Docker login and no VPN/WSL/daemon changes. Pulled the pinned official MariaDB
11.8.9/Python 3.13.16 images, built the Linux runner, initialized the retained
project DB and migrated a new disposable integration schema with distinct users.
The extra VM DBA test-schema request remains optional/unconfirmed; Docker provides
that isolation now. No existing password, schema or volume was reset.

Changed files/groups (full inventory in verification/stage-1/file_changes.json):

- Backend auth/domain/security, new account router and foundation services/models,
  deployment default-theme reader, API/static serving, explicit CLI/entry point,
  migration 0002, packaged migrations/assets and actual uv lock/crypto dependency.
- New frontend src/components/API/theme/style files, actual npm lock/configs,
  generated OpenAPI types, local Node/bootstrap/build/verification/browser tools,
  Playwright tests and original dependency notices/inventories.
- Guarded VM Stage 01 fixtures/API tests, original integration account-lifecycle
  tests, permission/TLS/unit checks; original disposable/empty-schema guards remain.
- Local VM preparation/synthetic fixture/protected certificates, app Dockerfile and
  context allowlists, root Make targets, schema scanner vendor-tree pruning with
  regression tests, README/setup/plan/toolchain/decisions/traceability/status.

Actual verification (all Python commands use backend/.venv/Scripts/python.exe
unless the command runs in the recorded Linux container):

| Command/check | Result and evidence |
|---|---|
| `scripts/probe_mariadb.py --host 127.0.0.1 --port 13306 --database system-monitor --username system-monitor-app --password-file .secrets/vm-mariadb/runtime_password --output verification/stage-1/runtime-probe.json` | PASS: runtime identity has exact-schema DML only. |
| `scripts/stage1_local.py prepare`, `migrate`, `fixture`, `serve`, each with `--approved-schema system-monitor` | PASS: ignored config/certificates, explicit migration with original-row comparison, protected synthetic test credentials and real HTTPS serving. |
| `scripts/verify_backend_slice.py --output-dir verification/stage-1/backend` with explicit VM config/account opt-ins | 23 actual VM API tests pass. First schema/mypy checks exposed vendor YAML scanning and a missing CLI annotation; fixed, with failures and successful rechecks preserved. |
| `python -m pytest backend/tests/unit -q` | 127 passed, including actual local TLS certificate/CA/hostname/expiry checks and full implemented-route permission/CSRF declarations. |
| `python -m unittest discover -s tests/package -v` on Windows | 128 run: 119 passed, nine POSIX skips. |
| Same package tests offline in Linux runner, source materialized with POSIX modes | 128 passed, zero skips. Initial Windows bind-mount 0777 permission mismatch is retained separately; no assertion relaxed. |
| `tools/validate_package.py`; `tools/validate_schemas.py`; `tools/validate_deployment_examples.py` | PASS: package/traceability/fixtures, 18 schemas, 102 valid/36 negative instances and 44 static deployment checks. |
| Ruff check/format; mypy src | PASS after recorded fixes; 14 backend source files typechecked. Final format recheck passes; initial formatting failures retained. |
| `scripts/frontend.py` lint/typecheck/api:check/build; `scripts/verify_frontend.py` | PASS on final sources. Actual generated-client drift was caught, types regenerated and check passed. |
| `scripts/build_stage1.py` | PASS: bundled local frontend plus wheel/sdist. Zip inspection confirms migrations, CLI/entry point, schema and byte-identical frontend assets; no private paths. |
| Real Playwright full browser suite | 8 passed; both roles/themes/sizes, same-context different/same-system pages, reload fresh workspace, ownership/forgery, global logout/theme and two delayed-auth-response regressions. Initial locator error and successful retry retained. |
| Targeted 200% layout equivalent and real UI system-mutation tests | 1 + 1 passed. CSS 640x360/DPR2 equivalent documented accurately; keyboard/scroll controls reachable. UI-created same-name systems retained independent IDs/descriptions/revisions after refresh; only those synthetic systems archived afterward. |
| Guarded pinned MariaDB Docker integration suite | 19 passed in Linux, zero skips, including concurrent bootstrap/last-Administrator and actual constraints/roles/revocations. Source guards unchanged. |
| Container grant, HTTP, outage, retained-volume and offline image checks | Exact commands/results under verification/stage-1/docker; final completion details below. |

Browser evidence includes 18 screenshots at exact 1280x720/1920x1080 viewports plus
the separately identified zoom equivalent; image dimensions/SHA256s are recorded.
Representative light/dark/role/dialog/zoom views were visually inspected. These
are actual components and text, not screenshot backgrounds; original reference
assets are unchanged. All external browser requests were blocked and none were
attempted. No remote fonts, telemetry or runtime dependency download is added.

Synthetic API accounts/history are retained; only test-owned systems are archived
and their workspaces expired. One newly created, unused browser-test Administrator
was paused/re-enabled around the VM sole-Administrator invariant check; ordinary
accounts were not disabled. Normal production bootstrap remains the protected
interactive CLI, not the guarded synthetic fixture command. Browser passwords
remain in ignored protected JSON, never source/logs/screenshots. Final secret
scan covers project password files, synthetic account JSON values and the wheel.

Full targets that span later stages remain partial: no production topology edit,
log event ingestion/filtering, SSH, live controller/streams, inventory import,
investigation/bundle/download or two-times-five live performance is claimed.
Actual external deployment PKI, Ubuntu/Rocky host installation, production backup/
restore and release advisory/offline installation gates remain later-stage work.
GNU Make is absent; its underlying commands were run. `make release-offline`
exposes an explicit non-success guard until Stage 08, not a claimed release.

**Stop before Stage 02.** Next reviewed scope: scoped production topology models,
repositories/composite constraints and versioned import/export, following the plan.


### Final Stage 01 container and artifact results

- Full 19-test integration suite passed on MariaDB 11.8.9/Python 3.13.16 in Linux.
  All 128 package checks also passed in Linux with zero skips. Windows source
  bind-mount mode emulation was corrected by materializing an ordinary POSIX-mode
  test tree; test assertions were retained. One probe-only attribute typo and an
  incorrect acceptance healthcheck command were corrected and recorded alongside
  successful reruns. The documented installed CLI healthcheck passed.
- Built non-root application image ID
  `sha256:327fdc96ee1dcecd8683e80a1ee41bd3670f006e0336b3ae81958a90988b072f`.
  Wheel SHA256 is
  `637300258684835097325d728c6252709fbc89d99913152923c559c818d5630f`.
  Its local assets/migrations/entry point were inspected; original theme PNGs are
  byte-identical to the handoff. Serving has only runtime DB secret/config mounts,
  UID/GID 10001, read-only root, dropped capabilities and no published port.
- Actual HTTP logins/viewers/catalogue/preferences work for both roles in that
  image; forged Inspector writes fail. Runtime grants and real DDL/out-of-schema
  access denials were tested. A separate new account authenticated using an actual
  UTF-8 password containing URL-reserved characters via the production engine;
  no existing password was rotated.
- Stopping the local DB yields liveness 200 and readiness/protected/CSRF 503.
  Restarting its retained volume with pull-policy never leaves the old app fenced
  until controlled restart. After restart, both systems/accounts/preferences/demo
  snapshots match their prior fingerprint. The VM and its tunnel/VPN were untouched.
- Saved/loaded the verified local image IDs and restarted from local aliases without
  registry pulls or deleting images/volumes. The ignored archive is 747341824 bytes,
  SHA256 `463a223dcc48b48d1f9a6596086bc9847fb1e89bf3c859b1e172de3e5a88e301`.
  This is local lifecycle acceptance; it does not claim a fresh-host release test.
- Acceptance app container is stopped; Docker MariaDB is running healthy with the
  same named volume. The primary approved-VM development app remains running at
  `https://localhost:8443`. Synthetic logins are available only in the ignored
  protected browser-fixture JSON files; no password is repeated in this log.
- Every Docker CLI argv/cwd/exit result and correction is recorded in
  `verification/stage-1/docker/commands.json` and its README/adjacent artifacts.
  Browser reports are `browser-final.json` (8), `browser-zoom.json` (1), and
  `browser-mutations.json` (1). The secret audit checks all private password/account
  values against sources/logs/wheel members without printing values or hashes.

**Stage 01 completion gate passed. Stop for review before Stage 02.** No remaining
Stage 01 environment blocker is inferred from the historical Docker/DBA entries.
The optional VM test-schema DBA script remains unconfirmed and unnecessary for
this completed acceptance run. Later full-product targets remain partial exactly
as stated in traceability; no SSH/live/import or production release is claimed.

Final close-out: readiness is 200 through explicitly trusted local TLS, bundled HTML is served, and no system certificate store was modified. The final authorized-owner secret audit checked 17 distinct private values against 704 source/log/wheel entries (27 wheel members): zero matches. See `final-readiness.json` and `secret-audit.json`.

## Stage 02 — complete, 17 October 2026

The user authorized Stage 02. Implemented Administrator subsystem/server/process,
connection/parser, flow and named-view editing; nested React Flow with pan/zoom,
multi-selection, resize, collapse, dependency selection and fit controls; safe
Markdown; system-scoped search/reveal; explicit moves and delete-impact previews;
transactional undo/redo; and versioned YAML/JSON export/preview/commit. Inspector
navigation uses a safe projection and cannot persist shared changes. Stable IDs,
name history and scoped relationships survive rename, delete/undo and reimport.

MariaDB migrations `0003_topology` and `0004_topology_name_history` add normalized
composite-scoped entities, constraints, retained identities/names, bounded full
undo snapshots and owner/auth-version/revision/digest/expiry-bound import previews.
Imports cannot create credentials, approvals, bindings or SSH trust. New targets
remain unresolved proposals. Safe parsing/validation runs in two bounded workers,
including cancellation. Project revisions and catalogue/archive state stay scoped.

Changed files/groups (inventory: `verification/stage-2/checks/changed-files.txt`):

- Backend topology/config modules, packaged v1/v2 schemas, models/migrations,
  permission declarations, scoped services, safe viewer/demo upgrade, upload caps,
  generated OpenAPI; topology/worker/validation/startup-backfill tests.
- Frontend workspace, graph/editor/config-transfer/Markdown components, domain
  types, generated API types, shared styles and browser tests/report paths.
- Local test setup helper, read-only integration example mount, secret-audit
  output option, README/API/traceability/plan and this status. No dependencies,
  lockfiles, original themes, golden fixtures or source event IDs were changed.

Verification uses fresh disposable schemas in the existing local pinned MariaDB
11.8.9 container, with Python 3.13.16 and the locked toolchain. The separate test
app runs at **https://localhost:8444**, with localhost TLS and protected random
synthetic accounts in `.secrets/stage2-browser/accounts.json`. The VM database,
tunnel and port-8443 application were not migrated or replaced.

Actual commands/results (Python is `backend/.venv/Scripts/python.exe` unless
recorded inside the Linux runner; GNU Make remains unavailable on this host):

| Command/check | Result |
|---|---|
| `scripts/stage2_local.py prepare`, `migrate`, `fixture`, `up` | PASS: new isolated schema, separate DML/migration identities, migrations 0003/0004, synthetic accounts/demo and HTTPS app. Explicit `stop`/`up` later loaded final backend while retaining all test data. |
| `python -m pytest backend/tests/unit -q` | **253 passed**; validation, limits, secret-safe errors, permission/CSRF declarations and cancellation retaining worker permits. Final output `checks/unit.log`. |
| `scripts/local_mariadb.py new-test --suffix s2_final_1017 --run` (same helper invoked by the recorded local evidence wrapper) | **30 passed, zero skips**, on real Linux MariaDB 11.8.9/Python 3.13.16. Includes direct composite-FK rejection, concurrent revisions, preview ownership/scope/expiry/tampering, tombstones/name history, snapshot bounds, archive and idempotent legacy-demo startup. Exact Docker argv/result: `s2_final_1017-command.json`; output: `s2_final_1017.log`. |
| `python tests/migrations/verify_populated_upgrade.py` in a separately provisioned empty `inspector_test_s2_upgrade_1017` schema | PASS: explicitly installs 0002, seeds Stage 01-only synthetic data, upgrades to 0004 and starts the real app with DML credentials. Preserves two accounts/password verification/preferences, two projects/metadata/revisions/docs, derives 16 scoped identities/name records and four processes, and intentionally detaches two old workspaces. No drop/downgrade. `populated-upgrade-command.json` and `populated-upgrade.log`. |
| `scripts/frontend.py e2e topology.spec.ts` with URL/account/report-stage variables | **4 passed in 10.7 s** on the final restarted backend: complete UI graph, duplicate-ID refusal, rename/flow preservation, explicit reparent, named views, collapsed search, JSON download/edit/preview/commit, delete-impact/cancel/confirm/undo, same-context independent pages/stale drafts, Inspector projection, and real drag/resize persistence through reload. `browser-final.json`. |
| `scripts/frontend.py e2e foundation.spec.ts` | **10 passed in 73.4 s**; roles/themes/sizes, same-context same/different-system isolation, global logout/appearance, keyboard, 200% layout equivalent, delayed authentication races and catalogue mutations. One real login-rate-limit response used the suite's bounded 60-second retry. `browser-foundation.json`. |
| Same foundation command with `-g 'uses both themes'` | **2 passed in 4.0 s**; final screenshots captured separately under Stage 02 for both roles/themes at 1280x720 and 1920x1080. `browser-visual.json`. |
| `python -m unittest discover -s tests/package -q` | 128 run: 119 passed, nine POSIX-only permission cases skipped on Windows. Their assertions were retained; Linux integration above has no skips. |
| `tools/validate_package.py`, `tools/validate_schemas.py`, `tools/validate_deployment_examples.py` | PASS; 18 schemas, 102 valid/36 rejected contract instances and 44 static deployment checks. These remain package checks, not runtime proof. |
| Ruff check and format-check over backend/src/tests/migrations/scripts; `cd backend; .venv/Scripts/python.exe -m mypy src` | PASS; 55 files at the consolidated check, plus the later populated-upgrade verifier independently checked/formatted; 16 typed source modules. |
| `scripts/frontend.py lint`, `typecheck`, `api:check`; OpenAPI generation with explicit example deployment config | PASS; generated client matches actual OpenAPI. |
| `scripts/build_stage1.py` and wheel inspection | PASS; local browser assets, both project schemas and migrations 0003/0004 included. All bundled frontend bytes match the build; no private paths. Wheel SHA256 `9256a20a784eb1dd2b9aeea0be4e9cfe1a1d71e5cb30a97ff6a63cec50546f1e`. `checks/artifact.json`. |
| `scripts/audit_local_secrets.py --output verification/stage-2/secret-audit.json` | PASS: 30 distinct private values checked against 796 source/log/wheel entries (33 wheel members), zero matches. |
| Trusted local TLS `GET /api/v1/health/ready` | 200 with certificate/hostname verification enabled using the explicit local development certificate; no system trust-store change. `readiness.json`. |

`verification/stage-2/checks/commands.json` retains exact quality/build commands,
working directories and exit codes. Final light/dark topology, selected-process
and import-preview screenshots were visually inspected. Both themes retain the
reference tokens, clear system labels and unknown-health/access state. External
browser requests were blocked by the foundation tests and none were attempted.

Failures and corrections are retained separately: initial browser account-file
ACL access and internal-only Docker port routing; missing example-fixture mount
in the first integration attempt; React controlled-selection feedback crash
(fixed and covered by browser page-error assertions); exact implicit-label test
locators changed to accessible role locators; and a resize test pointer hitting
the details panel below the clipped canvas, corrected through the real Fit
diagram control. Repeated test runs exhausted only synthetic workspace leases;
the guarded fixture expires those accounts' test workspaces before reruns. No
production limit or assertion was relaxed. The first foundation regression used
its old Stage 01 screenshot destination; it now writes to the selected stage's
directory, and final Stage 02 screenshots were captured separately. Earlier
reports remain historical results. Routine tool invocation/cwd/OpenAPI-config
errors were corrected before the recorded successful checks.

Limits/unrun work: migration/upgrade checks used guarded synthetic MariaDB data;
no VM/production upgrade or existing database downgrade was performed.
Bookmarks/notes/log associations,
active-job archive races, SSH/historical/live behavior, Ansible file/bundle import,
Ubuntu/Rocky installation and the full offline release remain their later-stage
gates. AT12/AT43/AT78/AT101 are partial where they depend on those resources;
traceability records the implemented Stage 02 portions explicitly.

**Stage 02 completion gate passed. Stop for review before Stage 03.** Next scope:
`prompts/03_HISTORICAL_LOG_ENGINE.md`.

## 17 October 2026 — Stage 01 development app stopped

The user authorized shutting down the retained Stage 01 environment. Stopped only
the workspace Python process serving `127.0.0.1:8443` (PID 20640), after confirming
its executable path and listener ownership. The VM MariaDB, existing SSH tunnel,
retained data and Stage 02 Docker environment were left in place.

Changed files: `progress/STATUS.md` and `backend/README.md` identify Stage 02 as
current and Stage 01 as stopped. No application code, schema or credentials changed.

Commands actually run and results:

- Guarded PowerShell `Stop-Process -Id $stageOneProcess.Id -ErrorAction Stop`,
  followed by `Wait-Process`: PASS; confirmed Stage 01 PID 20640 exited.
- `netstat -ano -p tcp` with listener filtering: PASS; port 8443 has no listener,
  Stage 02 port 8444 remains listening (Docker PID 28756), and tunnel port 13306
  remains listening (PID 34064).
- Python `ssl.create_default_context(cafile='.secrets/stage2-browser/localhost-cert.pem')`
  and `urllib.request.urlopen('https://localhost:8444/api/v1/health/ready', ...)`:
  PASS, HTTP 200 with certificate/hostname verification. The initial restricted
  attempt could not read the protected certificate; the read-only elevated rerun passed.
- The optional `Get-CimInstance Win32_Process` query was denied by Windows;
  `Get-Process` executable identity and `netstat` ownership checks were used instead.

No automated tests were run for this process shutdown and documentation update.
No remaining shutdown blocker. Next stage remains Stage 03, pending its review gate.

## 17 October 2026 — Stage 03 historical investigation

The user authorized Stage 03. Implemented the production timestamp parser,
literal Unicode-casefold predicate, unchanged source/event identity, bounded
plain/ZIP/TAR.GZ readers, MariaDB event/provenance index and actual historical
browser viewer. Tests independently compare all fields of **38 golden events**
and all **17 expected query sequences**; production code does not import the
package oracle. Integer UTC microseconds and `[from,to)` apply throughout.
Unknown timestamps remain visible in the diagnostic lane.

Collection planning uses approved configuration through a local transport
interface. The supplied fixed synthetic manifest requires explicit deployment
opt-in `SI_LOCAL_HISTORY_DEMO=1`, disabled by default. Browser requests cannot
supply replacement hosts, local paths, parsers or credentials. Archive members
are streamed without extraction. Unsafe/corrupt archives and actual-byte,
metadata, member, ratio, line, event, time and cancellation budgets produce safe
errors or explicit partial coverage. ZIP64/multivolume and nested archives are
explicitly unsupported. Observed timestamp extrema do not imply continuity.

Retained collections provide preliminary owned offline investigations. Planning,
jobs, query cursors, context, event/source IDs and downloads bind project and
owner. MariaDB schema `0005_historical_capture` uses exact nullable BIGINT times,
large Unicode text, deterministic nullable ordering and composite foreign keys.
Snapshots exclude later events; source-local context marks unmatched/out-of-time
lines. Pages/context cap raw text at 8 MiB and continue with a cursor. Typed
tombstones preserve captured names after topology deletion. Active captures
block archiving only their own system. Logout requests cancellation; read scans
release authentication locks and recheck independent MariaDB authorization at
bounded intervals. Audited Administrator cancellation grants no private read.

The virtualised viewer supports process selection, UTC validation, plan/collect/
cancel/progress, retained deep links, merged/five-process split results, global
and per-process literal filters, diagnostic records, provenance, source-order
context and captured-source download. Filter limits count Unicode code points.
Each page owns its system/filter/query state; tests include same-account pages
in one browser context for different and duplicated systems. Shared themes use
the existing semantic tokens and original reference images.

Changed files/groups (full inventory: `verification/stage-3/checks/changed-files.txt`):

- `backend/src/inspector/log_engine/`, `history.py`, `history_cache.py`, models,
  migration 0005, app/config/auth/security/services/topology integration and
  generated OpenAPI; engine/cache/storage/worker/config unit tests and real
  MariaDB historical/lifecycle/cancellation cases.
- `frontend/src/components/HistoricalViewer.tsx`, App/SystemWorkspace/styles,
  generated API types and historical browser suite; topology report destination
  now respects the chosen stage.
- `scripts/stage3_local.py`, `verify_stage3.py`, `benchmark_history.py` and
  `benchmark_stage3.py`; read-only fixture/script mounts for the local runner;
  optional diagnostic query lane in `contracts/query.schema.json`.
- README/backend/frontend setup, docs 12/14 and this status. Package validation
  skips generated runtime trees; source-link test clones include the real file
  types referenced by documentation. No contract assertion was removed.

No dependencies, lockfiles, notices, original themes, golden inputs or event IDs
changed. A separate guarded local schema and `runtime-stage3` HTTPS service on
**https://localhost:8445** preserve the Stage 02 schema/service on 8444. Random
synthetic accounts remain in `.secrets/stage3-browser/accounts.json`; persistent
test cache is separate from the serving credentials. No VM/production host or
database was contacted or migrated.

Actual commands/results (Python is `backend/.venv/Scripts/python.exe` unless the
record names the Linux runner; GNU Make is unavailable on this Windows host):

| Command/check | Result |
|---|---|
| `scripts/stage3_local.py prepare`, `migrate`, `fixture`, `up`; later `stop`/`up` | PASS: isolated synthetic schema, separate DML/migration identities, schema 0005, fixture systems and trusted local HTTPS. Cache/data retained across restart. |
| `scripts/verify_stage3.py checks` | All 12 recorded commands passed; exact argv/cwd/exit codes in `checks/commands.json`. |
| `python -m pytest backend/tests/unit -q` | **321 passed in 6.39 s**, including 61 engine tests, complete golden comparisons, archive/metadata attacks, Unicode boundaries, immutable cache accounting/leases and deployment worker ceilings. |
| `scripts/verify_stage3.py integration --suffix s3_cancel_final_1017` | **47 passed in 50.18 s**, zero skips/pytest warnings, against actual Linux MariaDB 11.8.9/Python 3.13.16. Golden results, composite FK/forged-scope/download checks, exact time/large Unicode/nullable ordering, snapshot/byte budgets, auth revocation, single-connection-pool queries, cache boundaries, collisions and lifecycle regressions. Real barriers verify cancellation mid-copy and after committed index batches within two seconds, exact byte counts, temporary cleanup, partial coverage and no subsequent writes. `s3_cancel_final_1017.log`; earlier final-code 45-case run also passed. |
| `scripts/verify_stage3.py upgrade --suffix s2_upgrade_s3_1017` | PASS: populated 0002-to-0005 upgrade in a new disposable MariaDB schema; retains two systems/accounts, password verification, preferences, revisions and documentation; old workspaces intentionally detach. `s2_upgrade_s3_1017.log`. |
| `scripts/frontend.py e2e historical.spec.ts` with Stage 03 URL/account/report variables | **3 passed in 23.1 s** in the final keyboard/visual run; real plain/ZIP/TAR collection/query/context/download, Unicode 512/513-code-point boundaries, theme/filter persistence, same/different-system pages, forged job/cursor/downloads and invalid UTC. Tab/Enter/Space navigate and activate topology/history/preview controls; Escape closes context and returns focus. `browser-historical-keyboard-final.json`; the earlier expanded visual run also passed 3/3. |
| `scripts/frontend.py e2e topology.spec.ts`; `... foundation.spec.ts` | **4 topology** and **10 foundation** regressions passed. Includes role permissions, two-page isolation, global logout/theme, keyboard and 200% layout equivalent. `browser-topology-final.json`, `browser-foundation.json`. |
| `python -m unittest discover -s tests/package -q` | 128 run: **119 passed, nine POSIX-only permission cases skipped on Windows**. Assertions retained; Linux MariaDB tests above have no skips. |
| `tools/validate_package.py`, `tools/validate_schemas.py`, `tools/validate_deployment_examples.py` | PASS: source/traceability links, 18 schemas, 102 valid and 36 rejected instances, 44 static deployment checks. |
| Ruff check/format; `cd backend` then `.venv/Scripts/python.exe -m mypy src` | PASS: 73 formatted files at the consolidated run; no issues in 21 typed source files. |
| `scripts/frontend.py lint`, `typecheck`, `api:check`; `scripts/build_stage1.py` | PASS: generated API consistency and actual bundled frontend/Python distributions. Build retains a non-fatal Vite chunk-size advisory. |
| Wheel inspection | PASS: 39 members include engine, history/cache and migration 0005; all four bundled browser assets match build bytes; no private paths. SHA256 `3ede9c82ef43489019f6ae3b10b8d1e1c523dc9ff28f672a378773ef0f5f2dfd`. `checks/artifact.json`. |
| Independent original-input SHA256/size comparison | PASS: all 43 delivered fixture/theme files match `PACKAGE_MANIFEST.json`. `checks/original-inputs.json`. |
| `scripts/audit_local_secrets.py --output verification/stage-3/secret-audit.json` | PASS: 53 distinct private values against 1,013 source/log/wheel entries, zero matches. Values and value hashes were never emitted. |
| `scripts/benchmark_stage3.py` with only Stage 03 service stopped, then `scripts/stage3_local.py up` | PASS: final-code production collector/index/query benchmark below; server restored and trusted-TLS readiness returned HTTP 200. |
| Final documentation package validation/tests; `git diff --check` | PASS: 128 package cases with the same nine Windows/POSIX skips; repository-configured diff check reports no whitespace defects. `checks/diff-check.json`. |

Performance evidence: `verification/stage-3/mariadb-benchmark.json` and sanitized
command/stdout/stderr records. Generated input is **20,972,325 bytes across five
sources**, **102,575 indexed events**. Final-code cached ingestion took **9.717 s**.
Ten measured warmed queries after one declared warm-up produced p95 **73.968 ms**
unfiltered, **240.307 ms** full-interval literal and **23.718 ms** narrow literal;
exact matching totals are 102,575 / 105 / 5. Full literal cold cache build took
**3.375 s**, recorded separately. The immutable read-through cache uses
57,383,534 of 67,108,864 bytes, including builds/leased entries, with a 300-second
TTL; project/owner/snapshot/config/auth/process/time/lane scope and current DB
authorization apply on every hit. Cold/expired/evicted scopes use bounded SQL.

Machine: Linux WSL2 kernel 5.15.153.1, x86_64, Python 3.13.16, MariaDB 11.8.9;
16 logical CPUs exposed, no CPU quota, runner memory cap 512 MiB, local MariaDB
service cap 1 GiB. Peak process RSS **161,980,416 bytes**. Generation and network
download time are excluded. These local results meet the measured 10-second/
500-ms warmed targets. **The documented 4-vCPU/SSD reference qualification was
not run**; these results are not Ubuntu/Rocky release certification.

Visual evidence: 73 PNGs plus dimensions, SHA256 and viewport/full-page metadata
in `verification/stage-3/screenshots/manifest.json`. Both themes at 1280x720 and
1920x1080 cover merged logs, five split panes, filters, diagnostics and provenance/
context, alongside topology/import/foundation screenshots. Full-page split
overviews are identified separately from exact viewport captures. Representative
light/dark context, diagnostics and split panes were visually inspected.

Failures/corrections: initial restricted Docker/secret-file access required the
local-only elevated rerun. Source-link test clones initially omitted referenced
code/log file types; they now include actual targets. Browser fixes addressed
an implicit-label locator, a retained-investigation load race, sticky row actions,
readable UTC columns and Unicode UTF-16/code-point differences without weakening
assertions. The first topology screenshot run used its old Stage 02 destination;
the configurable report stage was fixed and the final suite recaptured Stage 03.
Only ignored same-named screenshot artifacts were affected, not Stage 02 data.

Early benchmark failures exposed transaction-context misuse, then slow SQL
ingestion/refiltering. Retained profiles led to compact indexed storage (full
public provenance preserved), bounded immutable raw-event caching, Core inserts,
one grant query and at most two already-queued worker batches per transaction.
No waiting for extra batches or cap increase was introduced. A redundant join
predicate causing SQLAlchemy warnings was corrected; the final 47-case run has
no pytest warnings. Compose identifies the intentionally retained Stage 03
service as an orphan when using an integration-only override; no remove-orphans
operation was performed. Earlier failed/slow measurements and sanitized diagnostics remain
in the Stage 03 evidence directory. No fixture/oracle/acceptance condition was
relaxed to make a test pass.

A supplementary Git check with `core.autocrlf=false` interpreted existing CRLF
terminators as trailing whitespace. The check with the repository's actual
configuration passed; line endings were preserved.

Limits/unrun work: no real SSH/SFTP or remote host testing (Stage 04), live/WS
monitoring (Stage 05), full saved layouts/notes/bookmarks/correlation/bundles or
retention management (Stage 06), Ansible uploads (Stage 07), production database
upgrade, Ubuntu/Rocky installation or complete offline release (Stage 08).
Those portions of cross-stage acceptance targets remain explicitly partial in
traceability. Serving app credentials have no migration/root authority.

No remaining Stage 03 implementation blocker. The final local TLS readiness
check passed HTTP 200 with explicit certificate/hostname verification;
`verification/stage-3/readiness.json` records the result. No system trust-store
change was made. The 4-vCPU/SSD and later release qualifications remain unrun as
specified above.

**Stage 03 completion gate passed. Stop for review before Stage 04.** Next scope:
`prompts/04_SSH_COLLECTION.md`.

## 17 October 2026 - Server SSH configuration correction

The user reported that Add server did not expose an SSH address or port. The
canonical model already stores these in project-scoped connection profiles, but
the server form showed only profile names and required creating one separately.
Corrected that Stage 02 workflow without starting Stage 04.

Changed files:

- `frontend/src/components/TopologyEditor.tsx`: SSH profile selection shows its
  endpoint; a new profile can be configured inline with host/IP, integer port
  (default 22), username, unresolved credential reference, optional jump and
  proposed log roots. Optional profile naming handles existing-name conflicts;
  generated names respect the 256-character limit. Existing profile edits explain
  their shared impact. Saving settings does not claim a working SSH connection.
- `frontend/src/components/SystemWorkspace.tsx`: Add server needs only a subsystem;
  server and new profile save through one revision-checked configuration PUT.
  Administrator server details expose host/port and Edit SSH connection.
- `frontend/src/styles.css`: semantic-token SSH section with normal form spacing.
- `frontend/e2e/topology.spec.ts`: regression for no-profile setup, native invalid
  ports, cancellation, atomic persistence/undo/redo, reload, endpoint editing and
  reuse, plus four light/dark desktop screenshots. Test cleanup logs out the
  synthetic account to release its retained workspace leases between cases.
- `backend/README.md`, `docs/12_TRACEABILITY.md` and this status: setup guidance,
  evidence and explicit remaining retrieval limits.

Commands actually run and results:

- `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/test_project_config.py -q`:
  **124 passed in 0.80 s**; existing canonical validation regressions.
- `backend/.venv/Scripts/python.exe scripts/frontend.py lint`: PASS.
- `backend/.venv/Scripts/python.exe scripts/frontend.py build`: PASS, including
  TypeScript compilation. `scripts/build_stage1.py` then rebuilt the actual
  served bundle and Python wheel/sdist successfully. Existing Vite chunk-size
  advisory remains non-fatal.
- `backend/.venv/Scripts/python.exe scripts/frontend.py e2e topology.spec.ts`
  against `https://localhost:8445`, protected Stage 03 synthetic accounts,
  `INSPECTOR_E2E_REPORT_STAGE=stage-3` and
  `INSPECTOR_E2E_REPORT_NAME=browser-server-ssh-final`: **5 passed in 14.9 s**.
  Covers the four existing topology/role/window regressions plus the new setup
  case against real local MariaDB. After the CSS spacing correction, the same
  command with report name `browser-server-ssh-visual-final` passed **5/5 in
  14.8 s**. Final light 1280x720 and dark 1920x1080 SSH screenshots were visually
  inspected; all four theme/size captures have clear fields and no page overflow.
- `backend/.venv/Scripts/python.exe -m unittest discover -s tests/package -q`:
  **128 run, 119 passed, nine POSIX-only permission tests skipped on Windows**.
- `backend/.venv/Scripts/python.exe tools/validate_package.py`: PASS, all 56
  requirements mapped. `git diff --check`: PASS.

The local screenshot manifest now includes 77 PNGs (the four new SSH form views
plus existing stage evidence). `verification/stage-3/checks/server-ssh-artifacts.json`
records the rebuilt wheel and served-bundle hashes separately from the original
Stage 03 artifact record.

Verification corrections: the initial restricted browser run could not read the
Windows-protected synthetic account file; local-only elevated execution resolved
it. The first executable run served the old packaged web bundle; rebuilding with
`build_stage1.py` fixed the asset mismatch. Repeated runs exhausted synthetic
workspace grace leases; `scripts/stage3_local.py fixture` expired only those test
accounts' leases in the guarded local test schema. Browser cleanup now uses real
account logout instead of changing any quota. An implicit select-label test
locator was changed to its accessible combobox role. No contract or application
limit was relaxed.

No schema, backend API, SSH transport, trust, secret storage or source approval
changed. No production host/database was contacted. This fixes configuration
entry only: remote data retrieval is still unavailable, and the current history
collector uses the explicitly enabled local synthetic fixture transport. The
Stage 03 gate remains passed; **Stage 04 SSH/SFTP is still the next stage**.

## 17 October 2026 - SSH password storage and connection testing

The user requested password storage and a connection test for a configured
server. Implemented that working Stage 04 setup slice. This is not completion of
the whole SSH collection stage: historical transport still uses local fixtures.

Administrators now open **Password & connection test** from server/profile
details or Connections. Password entry is write-only and cleared on submit.
AES-GCM ciphertext/nonces live in MariaDB VARBINARY columns, with separate
system-to-vault bindings. The 32-byte key is loaded from a protected service-owned
file, never an export/browser setting. Replacements advance credential versions.

Explicit host-key inspection rejects the target handshake before authentication;
approval requires an independent verification statement and an owned, expiring,
revision/route/session-bound inspection. Password authentication pins the key on
each hop. The test opens SFTP and closes both connections; no shell, exec, file
write, general forwarding endpoint, source discovery or log collection is added.
Address resolution validates and pins IPs; unsafe/metadata destinations fail
closed. All setup endpoints enforce Administrator role, CSRF, current account,
project, configuration, trust and credential state. A bounded watchdog cancels
pending network work after revocation, changed state, supervisor loss or failed
fresh persistence checks. Limits are four in-flight checks, ten/user/minute and
thirty/deployment/minute, with no unbounded pending queue.

Changed files/groups:

- `backend/src/inspector/ssh_access.py`, `ssh_transport.py`, persistence models,
  migration `0006_ssh_access`, app/config/database/security and generated OpenAPI;
  SSH/vault/config unit tests and MariaDB setup/revocation tests.
- `frontend/src/components/ConnectionAccess.tsx`, SystemWorkspace/TopologyEditor,
  semantic styles and generated API types. Common Modal now prevents native
  Escape closure when its caller declines closing an active operation.
- `frontend/e2e/ssh.spec.ts`; topology regression waits for the acknowledged
  collapsed state before asserting search reveal, retaining the reveal checks.
- `scripts/stage4_local.py`, `stage4_ssh_fixture.py`, `verify_stage4.py` and local
  helper tests. Runner/application Dockerfiles create the named unprivileged
  inspector account, UID/GID 10001. Only the local runner was rebuilt here.
- Real AsyncSSH 2.24.1 uv resolution/lock; 52 installed dependency notice entries.
  README/backend/frontend setup, docs 12/14, toolchain record and this status.

Local lifecycle: retained the previous runner image; stopped only runtime-stage3;
made a consistent `mariadb-dump --single-transaction --quick --hex-blob` backup
of the guarded existing Stage 03 schema to the protected ignored SSH secret
directory (1,312,010,469 bytes, checksum recorded). Added the tested migration
without resetting systems, accounts, profiles or retained log history, then
restored **https://localhost:8445**. The mounted key is copied into service-owned
tmpfs mode 0600 before ASGI starts. Stage 02 and VM services were not migrated or
reconfigured. No user/production SSH host or real SSH password was used.

Actual commands/results (Windows Python: `backend/.venv/Scripts/python.exe`):

| Command/check | Actual result |
|---|---|
| `.bootstrap/Scripts/uv.exe --cache-dir .cache/uv lock --project backend --python .toolchains/python/cpython-3.13.16-windows-x86_64-none/python.exe`; corresponding locked `sync` | PASS; only AsyncSSH 2.24.1 added, original versions retained. Initial sandbox networking denied; reviewed connected build rerun succeeded. |
| `python -m pytest backend/tests/unit -q` | **371 passed, one POSIX vault-permission test skipped on Windows**, 9.32 s. |
| `.cache/stage4_linux.py` via local non-root runner | Actual passwd identity check PASS; **50 SSH transport/vault/helper unit cases passed**, no skips, 2.63 s. Includes direct/jump network handshakes, no target authentication on inspection/rejected keys, wrong password, SFTP denial, timeouts/cancellation and read-only fixture boundaries. Pytest emitted a non-fatal cache warning because the source mount is read-only. |
| `scripts/verify_stage4.py integration --suffix s4_ssh_isolated_1017` | **61 passed in 74.49 s**, zero skips, on actual Linux MariaDB 11.8.9/Python 3.13.16. Includes all previous history/topology/account cases plus fourteen setup/revocation cases. Six barriers verify cancellation within two seconds after credential/trust/logout/config changes or failed/timed-out DB checks. |
| `scripts/verify_stage4.py upgrade --suffix s2_upgrade_ssh_1017` | PASS: populated 0002-to-0006 upgrade in a new disposable schema preserves two systems/accounts, password verification, preferences, immutable topology IDs and documentation; workspaces detach. |
| `scripts/stage4_local.py prepare`, `fixtures-up`, `up`; `stage3_local.py stop`, `migrate`; guarded `.cache/stage4_backup.py` | PASS; isolated local fixtures/key, protected backup, additive existing-schema migration and restored serving app. No reset/reseed or production operation. |
| Pinned Node `frontend/node_modules/@playwright/test/cli.js test e2e/ssh.spec.ts --max-failures=1` (cwd frontend; URL 8445, Stage 03 synthetic accounts, report stage-4/browser-ssh-setup-final) | **3 passed in 9.3 s**: actual direct/jump SSH/SFTP, incorrect password, cleared inputs, stored status/reload, no password export, same-context system isolation, trust revocation and Inspector 403s. Four screenshots cover both themes at 1280x720/1920x1080; final light/dark views visually inspected. No external browser requests or page errors. |
| `scripts/frontend.py e2e topology.spec.ts foundation.spec.ts -g 'administrator builds\|same-account pages\|Inspector safely\|diagram drag\|server setup\|unsaved form\|primary controls'` (same URL/accounts; browser-ssh-regressions-final) | **7 passed in 17.5 s**, including all five topology cases and keyboard/Escape/200% layout/draft-theme regressions. |
| Ruff check/format over backend/src/tests/migrations/scripts; `cd backend` then `.venv/Scripts/python.exe -m mypy src` | PASS; 84 formatted files, 23 typed source files. |
| `scripts/frontend.py lint`, `typecheck`, `api:generate`, `api:check`; OpenAPI generation with explicit example deployment config; `scripts/build_stage1.py` | PASS; real bundled frontend and wheel/sdist. Existing Vite chunk-size advisory remains non-fatal. |
| `python -m unittest discover -s tests/package -q`; package/schema/deployment validators | 128 run: **119 passed, nine POSIX permission skips on Windows**. All validators pass (18 schemas, 102 valid/36 rejected instances, 44 deployment checks). |
| `scripts/audit_local_secrets.py --output verification/stage-4/secret-audit.json` | Final PASS: 68 distinct private values compared with 1,087 source/log/wheel entries, 42 wheel members, zero matches. Values/ciphertexts were not emitted. |
| Trusted local TLS readiness request | HTTP 200 with certificate and hostname verification enabled. |

Final package/link tests, frontend lint/types/generated API check, Ruff and
`git diff --check` pass. The wheel contains both SSH modules and migration 0006;
all packaged web asset bytes match the served bundle. Evidence is in
`verification/stage-4/checks/artifacts.json`, `checks/changed-files.txt`,
`readiness.json` and the screenshot manifest (16 captured regression views,
including four SSH setup screenshots). Original theme/fixture files were not
changed. The existing Windows line-ending conversion advisories are non-fatal.

Failures/corrections retained in verification: initial SSH FK column collation
mismatch fixed before local migration; initial logout tests invalidated the
shared synthetic bootstrap actor, corrected to dedicated temporary Administrators;
wrong upgrade suffix rejected by its existing guard, then the required fresh
prefix used. Browser testing exposed a numeric-only container UID missing its
passwd entry; fixed with a named non-root account, then actual Linux transport
and browser tests passed. New fixture secret ACLs now include only the tool,
SYSTEM/Administrators and designated Docker Desktop account. One combined
topology run searched before its async collapse settled; the test now asserts
that prerequisite and keeps its original reveal assertions. No trust bypass,
contract deletion, quota increase or production secret was used.

Limits: no real target was contacted automatically; the user must explicitly
save their password, verify their host key and start their own connection test.
No configured log paths are checked by this test. Source/root approval, bounded
remote candidate planning/downloads, collection revision integration and the full
Stage 04 golden-log-through-jump gate remain pending, along with later live,
analysis, import and offline-release work. Full app-image, Ubuntu/Rocky,
key-rotation and full backup-restore qualification were not performed.

**The requested SSH setup/test slice is implemented. Stage 04 as a whole is not
complete; its remaining collection work is the next scope.**

## 17 October 2026 - Compact topology navigation

Implemented the user's UI rearrangement without advancing a stage gate. Removed
the Administrator workspace strip and large System workspace heading. Synthetic
demo data now appears in the top bar. Personal appearance is available only in
Settings for both roles; shared settings retain Administrator authorization.
Admin follows Settings and opens `/admin` for system creation, metadata editing,
archival and restoration.

The compact system bar contains a floating System menu, current name/identifier
and right-aligned selector. Its nine actions retain the existing real editors,
connection/parser lists, import preview and JSON/YAML exports. Undo/Redo moved
beside Documented topology; the old editing button bar is removed. Ordinary
system links support browser modifier clicks instead of Open separately. Menu
keyboard navigation, disabled prerequisites, Escape/outside dismissal and focus
restoration work in both themes. System selection remains URL/page scoped.

Changed files:

- `frontend/src/App.tsx`, `components/Catalogue.tsx`, `Management.tsx`,
  `SystemWorkspace.tsx`, new `ActionMenu.tsx`, and `styles.css`.
- All four `frontend/e2e/*.spec.ts` files and new `e2e/ui.ts`: real menu/Settings
  actions, Admin lifecycle forms, manual new-tab workspace ownership, compact
  canvas dimensions, role checks, screenshots and synthetic-session cleanup.
- `frontend/README.md`, `docs/06_UI_UX.md`, `docs/12_TRACEABILITY.md`, this status.

Commands actually run (Python: `backend/.venv/Scripts/python.exe`):

- `scripts/frontend.py lint` and `scripts/frontend.py typecheck`: PASS on final
  sources/tests. `scripts/build_stage1.py`: PASS, including TypeScript, Vite and
  rebuilt wheel/sdist. Existing Vite chunk-size advisory remains non-fatal.
- `scripts/frontend.py e2e foundation.spec.ts topology.spec.ts historical.spec.ts
  ssh.spec.ts --max-failures=3` with URL `https://localhost:8445`, protected Stage
  03 synthetic accounts and Stage 04 report output: the corrected broad run
  passed **18 scenarios**, then three topology sign-ins hit the real HTTP 429
  limit; one remaining test was not run. Report: `browser-compact-ui-final.json`.
- `scripts/frontend.py e2e topology.spec.ts --max-failures=1`: **4 passed**,
  including final Admin/Inspector Settings captures. The geometry prerequisite
  exposed Chromium's rounded intersection ratio (0.9999987483 for a fully visible
  scaled handle); the server setup test was not run after that failure. Report:
  `browser-compact-ui-topology-final.json`.
- `scripts/frontend.py e2e topology.spec.ts -g 'diagram drag|server setup'
  --max-failures=1`: **2 passed in 7.9 s**. The handle must fit completely inside
  both the canvas and browser bounds, without a numerical tolerance. Real drag,
  resize, model-parent, persisted-geometry and reload assertions remain intact.
  Report: `browser-compact-ui-geometry-final.json`.
- Final evidence reconciliation: **all 22 distinct browser scenarios have a
  passing final result across those runs**, not one all-green suite invocation.
  `verification/stage-4/checks/compact-ui-browser-coverage.json` records each
  scenario and its actual source report. No application limit was increased.
- `python -m unittest discover -s tests/package -q`: **128 run, 119 passed,
  nine POSIX-only permission cases skipped on Windows**.
- `tools/validate_package.py`: PASS, all 56 requirements mapped.
- Wheel/served/frontend byte comparison: PASS for all three built web assets;
  `verification/stage-4/checks/compact-ui-artifacts.json` records hashes.
- Local readiness and served-index request: HTTP 200 with explicit localhost
  certificate/hostname verification; the served index references the rebuilt UI.
- `git diff --check`: PASS; existing LF/CRLF conversion advisory is non-fatal.

Visual evidence includes topology, open System menu, Admin and Settings in both
themes at 1280x720/1920x1080, plus existing role/history/SSH regressions. The local
screenshot manifest now inventories 101 retained captures; representative final
light/dark menus, topology, Admin and both roles' Settings were visually inspected.

Earlier verification failures remain in the reports. The initial broad run also
exhausted retained synthetic workspace leases; foundation/history cleanup now
uses real account logout after each test. Login helpers wait for one bounded
60-second retry on 429, with the real rate limit unchanged. The compact canvas
test also exposed flex shrink at 1920x1080; its intended viewport-relative minimum
height is now enforced. No backend/API/schema/transport change was needed.

The requested UI work is complete with no remaining blocker. Full Stage 04 remote
collection, later live/investigation/import work and release qualification remain
pending. No production host, real SSH credential, infrastructure deployment or
remote repository operation was used. Next stage scope remains
`prompts/04_SSH_COLLECTION.md`.

## 17 October 2026 - Stage 04: approved SSH historical collection

Completed the remaining scope of `prompts/04_SSH_COLLECTION.md`. The earlier SSH
setup slice now feeds real historical collection through direct or one-jump
AsyncSSH/SFTP. Stage 05 live following has not started.

Administrators separately approve the configured target and log roots after
password/key setup. Imports never create this approval. It binds project,
connection, complete configuration revision, route, roots and credential/trust
versions, with a default 24-hour expiry (bounded API: 60 seconds to 30 days).
Nullable credential expiry fails closed; existing credentials retain their prior
indefinite lifetime. Inspectors can collect approved configured process sources
and see safe diagnostics, while approval and path-test endpoints reject them.

Remote planning validates canonical roots, regular files and configured
active/rotated/archive patterns; symlinks and expansion/traversal are rejected.
Listing entries/bytes, probe traffic, candidates, download/expanded bytes, time
and cancellation are bounded. One guarded operation reuses a pinned route for
compatible sources and closes both hops afterward. Jobs, systems and owners do
not share connections or mutable filters. There is no shell, target exec/write,
discovery or agent capability. Captures use generated private project/job cache
paths and the unchanged Stage 03 parser/archive/query engine.

Both direct and single-jump collection download all 21 golden sources, index 38
events including one unknown timestamp, and reproduce every golden query's raw
text, UTC/filter results, checksum and member/byte provenance. New immutable
captures get new snapshot/event identities; original fixture IDs are unchanged.
Observed append/truncate/replace changes reject a snapshot. Missing configured
sources remain visible in reopened partial coverage. Parser budget failures
retain accurate actual byte/checksum counts and stop further downloads.

Dispatch and reservation check current project/owner/login/configuration/access
state. A 250-ms watcher with bounded fresh persistence checks cancels work after
revocation/expiry, account logout, changed credentials/configuration or DB/
supervisor failure. Cancellation of a health-check caller now preserves the
shared, independently bounded supervisor probe; actual lost ownership still
fails closed without reconnection/reacquisition.

Changed files/groups:

- Backend: new `ssh_files.py`, `history_remote.py`, `source_access.py`; updated
  `history.py`, SSH transport/access, app/bootstrap, config, database supervisor,
  security and persistence models. New additive migration `0007_source_access`.
- Contracts: optional deployment scan ceilings in authoritative/bundled schemas,
  Administrator source actions in RBAC, generated OpenAPI and frontend types.
- UI: ConnectionAccess configured-root approval/revoke and path checks;
  HistoricalViewer actual SSH/demo transport selection/labels and scoped errors;
  App/SystemWorkspace bootstrap wiring and shared semantic styles.
- Tests: real SSH file unit cases, approval/config/supervisor unit cases, new
  MariaDB SSH history/source approval/supervisor cancellation suites, explicit
  demo selection in the existing history fixture helper, preserved package role
  assertions for the new Admin actions, and expanded SSH browser tests.
- Tooling/docs: `scripts/verify_stage4.py` with guarded Linux unit verification;
  README/backend/frontend setup, docs 05/12/13/14, toolchain/slice plan and status.
  Exact changed paths are retained in Stage 04 verification evidence.

Commands actually run (host Python below means
`backend/.venv/Scripts/python.exe`):

| Command/check | Actual result |
|---|---|
| `python scripts/verify_stage4.py integration --suffix s4_collect_final1017` | **89 passed in 120.46 s**, zero skips, real Linux MariaDB 11.8.9/Python 3.13.16. Includes actual direct/jump golden retrieval, cancellation/revocation during a blocked SFTP read, missing-source coverage, exhausted parse-budget accounting, scoped FKs, retained-ORM reservation races and supervisor cancellation/loss. |
| `python scripts/verify_stage4.py linux-unit` | **463 passed, one Windows-only DACL test skipped**, 15.42 s. Linux symlink and POSIX vault-permission tests ran. Only a disposable non-root runner was started, with read-only authoritative test mounts. |
| `python scripts/verify_stage4.py checks` | Windows units **462 passed, two skipped**, 13.77 s (POSIX vault permissions and privileged filesystem symlink creation; covered on Linux). Package suite **128 run, 119 passed, nine POSIX permission skips**. Package/schema/deployment validators, Ruff, mypy, frontend lint/types, generated API check and bundled build passed. One formatting follow-up was required as recorded below. |
| `python -m pytest backend/tests/unit/test_history_workers.py backend/tests/unit/test_history_event_storage.py backend/tests/unit/test_history_cache.py -q` | Final history follow-up **6 passed in 0.86 s** after the coverage/accounting fixes. Final Ruff check/format and `cd backend; .venv/Scripts/python.exe -m mypy src` pass (93 formatted files, 26 typed sources). |
| `python scripts/verify_stage4.py upgrade --suffix s2_upgrade_s4c1017` | PASS: populated **0002-to-0007** upgrade retains two systems/accounts, password verification, preferences, immutable topology IDs, metadata/documentation; old workspaces detach. Fresh disposable schema only. |
| `python scripts/frontend.py e2e ssh.spec.ts --max-failures=1` | **4 passed in 38.0 s** against local HTTPS/MariaDB and real synthetic SSH endpoints. Administrator approval/path checks, Inspector forged-request denials, jump history, golden results and independent same-context captures/filters. Report `browser-stage4-ssh-final.json`. |
| `python scripts/frontend.py e2e foundation.spec.ts topology.spec.ts historical.spec.ts --max-failures=2` | **19 passed in 2.3 min**. One real 429 triggered the existing bounded 60-second login retry; application limits were preserved. Report `browser-stage4-regressions-final.json`. |
| `python scripts/frontend.py e2e ssh.spec.ts -g 'approved jump-host' --max-failures=1` | Final backend restart smoke **1 passed in 27.6 s**, including both themes/sizes and retained same-context filter/capture identity. Report `browser-stage4-final-smoke.json`. Together the main suites cover **23 distinct scenarios**. |
| `python .cache/stage4_final_evidence.py` | Final format and real frontend/wheel/sdist build PASS. **41 packaged files** match current source/migrations/contracts/web; served index and two assets match the frontend build. TLS certificate/hostname-verified readiness HTTP **200** at `https://localhost:8445`. |
| `python scripts/audit_local_secrets.py --output verification/stage-4/collection-secret-audit.json` | PASS: **78 distinct private values** compared with **1,254 source/log/wheel entries**, including 46 wheel members; zero matches. Values/ciphertexts were not printed. |
| `git diff --check` | PASS; existing LF/CRLF conversion advisories remain non-fatal. |

Browser commands used `INSPECTOR_E2E_URL=https://localhost:8445`, protected
`.secrets/stage3-browser/accounts.json`, and report stage `stage-4`. The new
approval/path/results captures cover both themes at 1280x720 and 1920x1080;
representative light/dark source approval, path results and Inspector history
views were visually inspected. The final screenshot manifest retains 113 PNGs.
No page errors or external browser requests occurred in the SSH scenarios.

Local lifecycle: stopped only `runtime-stage3`, preserved its existing schema,
accounts, systems, credentials and raw cache, and made a protected consistent
`mariadb-dump --single-transaction --quick --hex-blob` pre-0007 database backup
of **1,312,942,582 bytes** with recorded checksum. Applied migration 0007 with
separate migration credentials, then restored **https://localhost:8445** and
finally restarted it to load the completed fixes. No reset/reseed was used.
Stage 02, the retained VM/tunnel and production infrastructure were untouched.
Evidence: `verification/stage-4/pre-0007-backup.json`,
`checks/collection-artifacts.json`, `collection-readiness.json`,
`collection-screenshots.json`, final integration/upgrade logs and browser reports.

Corrections/failures retained in verification: first integration run passed
77/78 but the legacy local-fixture helper did not explicitly select the newly
available transport; the original disabled-demo assertion was retained and the
helper now requests `local_demo`. The next run's actual revocation case exposed
the interrupted supervisor probe; the shared shielded probe and dedicated real
MariaDB cancellation tests fix it. A later 87-case run passed, then final review
added the two coverage/accounting regressions; the final 89-case run passes.
Initial Linux unit mounts lacked two authoritative test inputs, corrected with
read-only per-run mounts. The package's exact Administrator action set was
extended with the two new actions while preserving every Inspector denial.
The checks aggregate retained one format failure; final formatting/build
follow-ups pass in `checks/final-followups.json`. No contract, fixture oracle,
authorization, host-key check or deployment quota was relaxed.

Tested SSH capabilities: locked AsyncSSH **2.24.1**, independently pinned
Ed25519 target/jump keys, password-only auth, SFTP protocol **3**, direct and one
`direct-tcpip` jump, read-only open/read/close/stat/realpath/listing operations.
Synthetic servers recorded no target exec or file mutations. SFTP v3 cannot
prove absence of every transient path race/same-size rewrite; dedicated account
permissions and visible snapshot/coverage limitations remain essential. No
CentOS/Rocky OpenSSH distribution or real user/production SSH host was contacted.
Full vault-key rotation/recovery, complete backup restore, app-image/offline
release and Ubuntu/Rocky platform qualification remain Stage 08 work. Live
following/reconnect/WS/seed buffers remain Stage 05, full saved analysis Stage 06
and Ansible uploads/reconciliation Stage 07.

**Stage 04 completion gate passed. Stop for review before Stage 05.** Next scope:
`prompts/05_LIVE_MONITORING.md`. No remaining Stage 04 blocker.

### 17 October 2026 — Connection log-root diagnostics

Investigated the reported Edit connection error when replacing synthetic
`/var/log/demo` roots with `/tmp/log`. Whole-project validation correctly rejects
existing active/rotation/archive paths outside a proposed root before any SSH
attempt. A shared profile covers every referring server, not just the selected
server. The editor previously surfaced only the backend's indexed field error.

Changed files:

- `frontend/src/components/TopologyEditor.tsx`: list configured paths with
  process/server labels, mark exclusions as roots change, and prevent a known
  invalid save with instructions to retain old roots while adding/moving to a
  new root. Corrected the obsolete demo-only historical-collection notice.
- `frontend/src/styles.css`: bounded path list and semantic warning styles.
- `frontend/e2e/topology.spec.ts`: shared-profile active/rotation/archive,
  directory-prefix, no-write rejection and successful root-addition regression;
  draft persistence and overflow checks in both themes and desktop sizes.
- `backend/README.md`, `docs/12_TRACEABILITY.md`, `progress/STATUS.md`: setup
  sequence, requirement evidence and actual results.

Commands actually run, with Python = `backend/.venv/Scripts/python.exe`:

| Command/check | Actual result |
|---|---|
| `python -m pytest backend/tests/unit/test_project_config.py -q` | **124 passed in 1.10 s**. Existing backend containment/security validation remains unchanged. |
| `python scripts/frontend.py lint` | PASS, including the final browser test changes. |
| `python scripts/frontend.py typecheck` | PASS. |
| `python scripts/frontend.py build` | PASS, TypeScript and Vite. Existing bundle-size advisory remains. |
| `python scripts/frontend.py e2e connection-roots-local.spec.ts -g 'connection root edits\|server setup exposes SSH' --max-failures=1` | **2 passed in 13.3 s** against the existing local HTTPS API/MariaDB. Report `verification/stage-4/browser-connection-roots.json`. A temporary wrapper served the freshly built local index/assets through Playwright routing; API requests and persistence were real. Wrapper removed after verification. |
| `git diff --check` | PASS; pre-existing LF/CRLF advisories remain. |

Browser settings were `INSPECTOR_E2E_URL=https://localhost:8445`, protected
`INSPECTOR_E2E_ACCOUNTS=../.secrets/stage3-browser/accounts.json`, report stage
`stage-4`, report name `browser-connection-roots`. Initial sandbox execution
failed with EPERM opening the protected synthetic account fixture; the approved
elevated retry passed without printing credentials. Eight screenshots cover the
invalid root field/dependent paths in light/dark at 1280x720 and 1920x1080;
representative dark/light views were visually inspected. No browser page errors.

The running application bundle, user configuration and approvals were not
replaced. Tests changed only newly created synthetic systems and test-account
appearance/session state; no target SSH connection was attempted. The UI source
fix requires the normal application rebuild before appearing in the running
app. No new stage was started; Stage 05 remains the next review-gated scope.

### 17 October 2026 - UTC date/time entry follow-up

Historical From/To fields now display `YYYY-MM-DD HH:mm:ss`, with a calendar
button for a date/time selector. The selector includes seconds, explicitly uses
UTC and supports Apply, Cancel and Escape. Typed values and picker selections
use the existing inclusive From/exclusive To interval. Invalid calendar values
and non-increasing bounds prevent dispatch. Edits invalidate collection plans.
Existing precise API bounds remain exact until edited; API/event storage still
uses microseconds. Page drafts and selectors stay local to each workspace.

Changed files:

- `frontend/src/utcDateTime.ts`: exact API normalization, UTC calendar validation
  and second-precision display/defaults.
- `frontend/src/components/UtcDateTimeInput.tsx`: labelled text input, calendar
  button and native date/time controls in a keyboard-accessible modal.
- `frontend/src/components/HistoricalViewer.tsx`, `frontend/src/styles.css`:
  integrated both bounds and semantic theme/layout styles.
- `frontend/e2e/historical.spec.ts`, `frontend/e2e/ui.ts`: browser behavior and
  keyboard regressions plus opt-in context-wide built-asset routing against the
  real local API without replacing the running app's bundle.
- `frontend/README.md`, `docs/06_UI_UX.md`, `docs/12_TRACEABILITY.md` and this
  status entry: input format, behavior and requirement evidence.

Commands actually run, with Python = `backend/.venv/Scripts/python.exe`:

| Command/check | Actual result |
|---|---|
| `python scripts/frontend.py lint` | PASS, including browser helper/test changes. |
| `python scripts/frontend.py typecheck` | PASS. |
| `python scripts/frontend.py build` | PASS, TypeScript and Vite; existing bundle-size advisory remains. |
| `python scripts/frontend.py e2e historical.spec.ts --max-failures=1` | **4 passed in 38.9 s** against the local HTTPS API/MariaDB using the freshly rebuilt frontend assets. Includes golden historical results, reopening, same-context scope checks, keyboard traversal, UTC selectors and precision preservation/reset. Report `verification/stage-4/browser-utc-controls.json`. |
| `git diff --check` | PASS; existing LF/CRLF advisories remain non-fatal. |

Browser settings: `INSPECTOR_E2E_URL=https://localhost:8445`, protected synthetic
`INSPECTOR_E2E_ACCOUNTS=../.secrets/stage3-browser/accounts.json`, report stage
`stage-4`, report name `browser-utc-controls`, and
`INSPECTOR_E2E_LOCAL_ASSETS=1`. The new selector case runs with browser timezone
`America/Los_Angeles`; submitted bounds remain UTC. Ten new screenshots cover
the fields/picker in light/dark at 1280x720 and 1920x1080, plus picker layout at
640x720. Representative light fields, dark desktop picker and light narrow
picker were visually inspected. No browser page errors occurred.

The first sandbox browser attempt failed with EPERM reading the protected
synthetic-account fixture; the approved narrow retry ran successfully without
printing credentials. The first targeted test run exposed a test assumption:
filling a field with its identical displayed value does not produce a React
change. The test now makes an actual edit and additionally checks that Cancel
preserves fractional bounds while explicit picker Apply resets them to whole
seconds. The corrected targeted run passed **2/2 in 9.5 s**; the final four-case
run above includes those checks. Final lint/types/build also pass.

The running app's bundle was not replaced; the normal application rebuild is
required for these changes to appear there. No deployment, database migration
or new stage is part of this follow-up; Stage 05 remains the next review-gated
scope. No remaining follow-up blocker.

## 17 October 2026 — Conditional Administrator source confirmation

Implemented the requested global **Settings → Additional security measures**
checkbox. It defaults to checked, preserving existing behavior. When checked,
the current configuration needs the existing explicit, expiring target/root
approval. When unchecked and saved, configured path/parser changes are usable
automatically without another source-confirmation checkbox or approval record.
The backend enforces the setting; Inspectors cannot change it. SSH host keys,
project-bound credentials, root/path validation, ownership and CSRF remain
required. Saving configuration starts no remote work. Policy changes invalidate
guarded remote operations, and reenabling requires a valid current approval.

Changed files for this follow-up:

- `backend/src/inspector/foundation.py`, `persistence/models.py`,
  `database.py`, and `backend/migrations/versions/0008_security_setting.py`:
  revisioned persisted boolean, strict input validation, omitted-field
  compatibility and additive MariaDB migration with checked default true.
- `backend/src/inspector/source_access.py`: enforce the current setting during
  preparation, reservation and watched operations; return effective eligibility
  and `manual_confirmation_required` without fabricating approval rows.
- `frontend/src/components/Management.tsx`, `ConnectionAccess.tsx`,
  `TopologyEditor.tsx`: Administrator checkbox and conditional confirmation UI;
  refresh source readiness after host-key revocation.
- `frontend/src/components/Common.tsx`: unique dialog heading IDs for reliable
  accessible names when switching from the parser list to its editor.
- `backend/openapi.json`, `frontend/src/api/schema.d.ts`: regenerated contracts.
- `backend/tests/integration/test_security_setting.py`,
  `backend/tests/migrations/verify_populated_upgrade.py`,
  `frontend/e2e/ssh.spec.ts`: policy persistence/validation/permissions, actual
  automatic SSH collection, changed paths/parsers/roots, preserved host-key and
  credential checks, reenabling, expiry, cancellation and upgrade preservation.
- `backend/README.md`, docs 03/05/06/07/12/13/14 and this status: operating behavior,
  user-requested manual-confirmation override and traceability.

Commands actually run, with Python = `backend/.venv/Scripts/python.exe`:

| Command/check | Actual result |
|---|---|
| `python -m pytest backend/tests/unit -q` | **462 passed, 2 skipped** in 12.03 s on Windows. The POSIX permission contract applies to Linux; synthetic symlink creation is denied by Windows (`WinError 1314`, required privilege absent). Both checks pass in the Linux suite below. |
| `python scripts/verify_stage4.py linux-unit` | **463 passed, 1 skipped** in 15.44 s in the local Linux image; only the Windows DACL test is skipped. |
| `python scripts/verify_stage4.py integration --suffix s4_security_1017a` | **98 passed** in 128.56 s against fresh local MariaDB and synthetic direct/jump SSH. Includes all 9 new policy cases. Evidence `verification/stage-4/s4_security_1017a.log`. |
| `python scripts/verify_stage4.py upgrade --suffix s2_upgrade_sec1017a` | PASS from populated `0002_foundation_preferences` to `0008_security_setting`; existing settings/accounts/two systems preserved; `setting_default_preserved: true`. |
| `python -m unittest discover -s tests/package -q` | PASS, 128 tests run with 9 POSIX shell/permission skips on Windows. |
| `python -m ruff check --config backend/pyproject.toml backend/src backend/tests backend/migrations scripts` | PASS. |
| `python -m ruff format --check --config backend/pyproject.toml backend/src backend/tests backend/migrations scripts` | PASS, 95 files formatted. |
| `.venv/Scripts/python.exe -m mypy src` from `backend` | PASS, 26 source files. |
| `python scripts/frontend.py lint`, `typecheck`, `build`, `api:check` | PASS; existing Vite bundle-size advisory remains. |
| `python scripts/frontend.py e2e ssh.spec.ts --max-failures=1` with the isolated browser settings below | **5 passed** in 110.5 s. Covers the new setting and actual direct/jump SSH, Inspector restrictions, two pages in one browser context, and mandatory fingerprint verification. Report `verification/stage-4/browser-security-setting.json`. |
| `python scripts/frontend.py e2e ssh.spec.ts -g 'Additional security measures' --max-failures=1` | **1 passed** in 16.4 s in the focused run before the full suite. |
| `python tools/validate_schemas.py`, `tools/validate_package.py`, `tools/validate_deployment_examples.py` | PASS; package/schema/template scope only. |
| `git diff --check` | PASS; existing LF/CRLF advisories are non-fatal. |

Browser verification uses a separate disposable schema
`inspector_test_s3_web_sec1017a` and temporary service at
`https://localhost:8446`, prepared/migrated/seeded/started through the ignored
`.state/security-setting-browser/runner.py`. It uses protected synthetic account
and SSH fixtures only. The existing apps on 8444/8445 and their schemas were not
migrated or restarted. Fresh built assets are routed within the test browser
context using `INSPECTOR_E2E_LOCAL_ASSETS=1`.

The final browser environment used `INSPECTOR_E2E_URL=https://localhost:8446`,
protected synthetic `INSPECTOR_E2E_ACCOUNTS=../.secrets/stage3-browser/accounts.json`,
report stage `stage-4` and report name `browser-security-setting`. Four new
1280x720 screenshots cover Settings and automatic source access in both themes;
all four were visually inspected. The full suite also retains the desktop
direct/jump and multi-page coverage. No browser page errors or external requests
occurred. The temporary app was stopped after verification with
`python .state/security-setting-browser/runner.py stop`; test data is retained.

The initial browser attempt loaded the older bundled frontend. After enabling
built-asset routing, follow-up failures identified an unavailable diagram-only
test selector, reused dialog-title IDs and a populated textarea label selector
during parser editing. Tests now select the explorer and exact accessible
textbox, and dialogs use unique React IDs. Repeated suite execution also reached
the real SSH ceiling of 10 checks per account per minute; test helpers retain
that ceiling and retry once after 60 seconds only on an actual 429. Early standalone
OpenAPI CLI generation lacked deployment configuration and an initial mypy
invocation used the repository root; both were corrected using an explicit
synthetic example configuration and the documented backend working directory.
A supplemental diff check with `core.autocrlf=false` interpreted existing CRLF
line endings as trailing whitespace; the repository-configured
`git diff --check` was rerun and passed. No line-ending conversion was applied.

The application requires the rebuilt bundle/backend and migration
`0008_security_setting` before this appears in the existing running app.
Stage 05 remains the next separately authorized review-gated scope.

## 17 October 2026 — Install settings and UTC-control updates locally

The user explicitly requested completing installation after the implementation
and isolated verification above. Updated only the existing app at
**https://localhost:8445** and its verified local MariaDB schema from
`0007_source_access` to `0008_security_setting`. No new stage was started.

Stopped only `runtime-stage3`, made a consistent compressed
`mariadb-dump --single-transaction --quick --hex-blob` backup, and backed up the
raw cache, prior application bundle/distributions and deployment files. The
protected backup is `.secrets/stage4-ssh/pre-0008-security-setting/`; the SQL
gzip is **194,541,110 bytes**, with SHA256
`2ccfd2fe900a0d9f0390a24c22519ce46b41fe132fb46218c51bc125f5f72202`.
Cache backup includes **898 files / 230,858,663 bytes**. The existing vault key
was preserved separately and its private checksum checked without printing it.
The migration ran with the existing separate migration credentials.

Inspection found that 8444 shares the repository's backend/web folder. Built
the current frontend, backend wheel and sdist into the isolated artifact
`.state/stage4-ssh/installed-0008/backend` and changed only the `runtime-stage3`
backend bind mount to this artifact. Its application source matches the current
checkout; **42 packaged files** match the built wheel. The wheel SHA256 is
`9488f7d9c9dea808d4e6d49dc62ca86ef61a9711ee99b6ebffcb160faf0a9f78`.
The original shared web bundle was preserved, and 8444 remained running and
HTTPS-ready throughout. Existing accounts, topology, settings and cache were
not reset or reseeded. The installed snapshot is required for future restarts;
future code updates need a fresh artifact, not just a service restart.

Commands actually run, using `backend/.venv/Scripts/python.exe` as Python:

| Command/check | Actual result |
|---|---|
| `python .cache/install_security_setting.py backup` | PASS: schema guard, app-only stop, private consistent SQL/cache/artifact backups and checksums. |
| `python .cache/install_security_setting.py build` | PASS: pinned frontend build plus isolated Hatchling wheel/sdist; prior shared assets preserved. Existing Vite bundle-size advisory remains. |
| `python scripts/stage3_local.py migrate` | PASS: additive migration 0008 on the authorized existing local schema. |
| `python .cache/install_security_setting.py verify-migration` | PASS: **35 table row counts** and **33 unchanged-table checksums** preserved before restart, original settings unchanged, new boolean true, configuration and vault key unchanged. Only Alembic/version and the additive settings-column checksum differ as intended. |
| `python .cache/install_security_setting.py start` | PASS: updated 8445 app restarted, using the isolated artifact and existing secrets. |
| `python .cache/install_security_setting.py verify` | PASS: certificate/hostname-verified HTTPS readiness **200**, schema 0008, all 35 table counts preserved, 30 stable-table checksums preserved through startup, all cache file bytes/hashes preserved, two served assets match the build, 42 packaged files match, and 8444 remains ready with its prior assets. Startup may detach workspaces and mark unfinished collection state interrupted as documented. |
| `.toolchains/node-v24.22.0-win-x64/node.exe .cache/verify_security_setting_install.mjs` | PASS: actual served assets, Administrator checkbox checked and API true, Inspector personal-only Settings/API403, no configuration writes, external requests or page errors. Separate fresh browser contexts were closed without account-wide logout; existing user browser sessions were not revoked. |

Evidence: `verification/stage-4/pre-0008-security-setting-backup.json`,
`security-setting-installed-migration.json`, `security-setting-installation.json`,
the two `security-setting-install-*-build.log` files, and
`security-setting-install-browser.json` / `.png`. The actual installed Settings
dialog was visually inspected. Build/install/smoke helpers live in ignored
`.cache/`; the generated installation artifact and private backups are also
ignored. Updated `backend/README.md` and this status with the installed revision,
artifact location and restart behavior.

Installation is complete with **Additional security measures checked**. Uncheck
and save in Administrator Settings to permit automatic path/parser changes.
The retained Stage 02 app, VM/tunnel, SSH fixture identities and production
hosts were not changed. Stage 05 remains the next separately authorized scope.

## 17 October 2026 - Historical retrieval tolerates active-log appends

Corrected the reported `SOURCE_CHANGED` / "The log source changed while it was
planned" error when a configured active log receives new entries. The collector
previously compared mutable size/mtime/ctime as an immutable whole-file identity
at planning, path checks and collection. Active logs now freeze the initial
planned byte boundary and probe/copy that prefix while allowing later growth.
Appends do not change the planned byte budget or invalidate successful capture.
Later entries are available to a subsequent collection; existing investigations
retain their original bytes, events, offsets and checksums.

Observed truncation, replacement, ownership/permission changes, equal-size
metadata changes and captured-prefix rewrites still fail. Successive path/handle
observations must not shrink, including replacement after previously observed
growth. Rotated files and archives retain strict immutable validation. Bounded
SFTP probes cannot prove absence of every transient or middle-of-file rewrite
combined with growth; existing documented SFTP v3 limitations remain applicable.

Changed files for this follow-up:

- `backend/src/inspector/ssh_files.py`: append-compatible active metadata checks,
  fixed-boundary probes/fingerprints and latest-observation validation across
  planning, configured-path checks and copying. Existing stored candidate shape
  and fingerprint inputs remain compatible.
- `backend/tests/unit/test_ssh_files.py`: append races before open, during plan,
  between connections, during path checks and every collection/probe read;
  empty/small/large/unterminated sources; exact checksums/budgets; rewrite and
  observed-growth/replacement regressions; immutable plain/ZIP/TAR.GZ failures.
- `backend/tests/integration/test_history_ssh.py`: real synthetic SSH plus MariaDB
  regression appending during preview, between preview/create, during create
  planning and body copy. Checks exact cache/index bytes and a later collection
  containing new entries while the prior investigation remains unchanged.
- `backend/README.md`, `docs/12_TRACEABILITY.md` and this entry: corrected
  operating behavior, requirement evidence and actual verification.

Commands actually run, with Python = `backend/.venv/Scripts/python.exe`:

| Command/check | Actual result |
|---|---|
| `python -m pytest backend/tests/unit/test_ssh_files.py -q` | Final focused run: **62 passed, 1 skipped in 3.88 s**. The skipped test requires Windows symlink privilege, `WinError 1314`. |
| `python -m pytest backend/tests/unit -q` | Final full run: **492 passed, 2 skipped in 14.04 s**. POSIX permission check and Windows-denied synthetic symlink creation. |
| Linux `local_mariadb.compose('run', '--rm', '--no-deps', 'integration', 'python', '-m', 'pytest', 'tests/unit/test_ssh_files.py', '-q', '-p', 'no:cacheprovider')` via `python -c` | **63 passed in 2.91 s** using the current checkout's read-only backend mount in the existing local Linux runner. Includes actual POSIX replacement/symlink behavior. No application or schema changes. |
| `python scripts/verify_stage4.py integration --suffix s4_append_1017a` | **99 passed in 130.53 s** against fresh disposable `inspector_test_s4_append_1017a`, with synthetic direct/single-jump SSH. Evidence `verification/stage-4/s4_append_1017a.log` and command JSON. |
| `python -m ruff check --config backend/pyproject.toml backend/src/inspector/ssh_files.py backend/tests/unit/test_ssh_files.py backend/tests/integration/test_history_ssh.py` | PASS. |
| `python -m ruff format --check --config backend/pyproject.toml backend/src/inspector/ssh_files.py backend/tests/unit/test_ssh_files.py backend/tests/integration/test_history_ssh.py` | PASS, 3 files formatted. Initial formatting differences were corrected before the final run. |
| `.venv/Scripts/python.exe -m mypy src` from `backend` | PASS, 26 source files. |
| `python .cache/prepare_active_append.py` | PASS: isolated Hatchling wheel/sdist at `.state/stage4-ssh/active-append-fix/backend`. All 33 packaged source/asset files checked against wheel; the installed frontend bundle is preserved byte-for-byte. Only `ssh_files.py` differs among backend modules from the prior installed artifact. Wheel SHA256 `e77f42f40fd528c185a861e0e4121e75b8b7323d927b51e33b6e98ab08d3bdbc`. Evidence `verification/stage-4/active-append-package.json` and build log. |
| `git diff --check` | PASS; existing LF/CRLF advisories remain non-fatal. |

The first sandbox integration attempt could not access local Docker through its
protected configuration and failed before provisioning. The approved elevated
retry completed the isolated integration run successfully. Linux Docker checks
also used the approved elevated path. No credentials were printed. Peer review
found no remaining blocking issue.

No UI, API shape, dependency or database-schema change is required, so browser
tests, frontend builds and migration tests were not repeated for this backend
fix. Implementation and testing left the existing local apps and target hosts
unchanged. The user then explicitly authorized installing the prepared fix in
the local 8445 app; that completed installation is recorded below. Stage 05
remains the next separate review gate.

### Authorized local installation of the active-log append fix

Installed the prepared artifact at
`.state/stage4-ssh/active-append-fix/backend` into **https://localhost:8445** by
changing only the `runtime-stage3` backend bind mount and restarting that
service. No migration, dependency install, target SSH connection or frontend
rebuild was needed. Normal restarts continue to use `scripts/stage4_local.py up`.
The prior `.state/stage4-ssh/installed-0008/backend` artifact is retained.

Before the switch, stopped only that backend and made a consistent protected
database dump, raw-cache archive and previous-backend/deployment backup under
`.secrets/stage4-ssh/pre-active-append-fix/`. The SQL gzip is **194,541,979 bytes**
with SHA256 `fed97383885478d4d1c4aadfb376ad93111f2cafcae1df46c43f8388d12d75c4`.
The cache backup contains **898 files / 230,858,663 bytes**. The vault key and
application configuration remain unchanged.

Commands actually run:

| Command/check | Actual result |
|---|---|
| `python .cache/install_active_append.py` | Completed the consistent backup and switched/restarted the backend. Post-start verification hit Windows `PermissionError` traversing Linux-owned cache directories; the helper restored and started the previous backend automatically. No data permissions were changed. |
| One-file cache-access diagnostic via `python -c` | Confirmed Windows `WinError 5` on a generated private cache path, before reading log bytes. |
| `python .cache/install_active_append.py retry` | PASS using the completed backup and verifying cache hashes inside the Linux container under its existing UID. Installed wheel SHA256 `e77f42f40fd528c185a861e0e4121e75b8b7323d927b51e33b6e98ab08d3bdbc`; serving module SHA256 `49a714c58b795fcf967d931dfb9dae53aa25e7596b22c8a6b47061b75dfc8d4c`. |
| Installation preservation/readiness checks | PASS: certificate/hostname-verified HTTPS readiness **200**, actual imported module matches the tested artifact, schema remains `0008_security_setting`, **28 stable table counts/checksums** and all **898 original cache file byte counts/hashes** preserved. Settings, users/preferences, topology, credentials/trust, indexed events, vault and deployment application configuration remain unchanged. Startup/workspace/job/auth/query activity tables are deliberately excluded from stable checks. |
| Other local app and frontend checks | PASS: 8445 serves the preserved installed frontend; 8444 remains HTTPS-ready with its original served index. No shared bundle was replaced. |

Evidence: `verification/stage-4/active-append-install-backup.json` and
`active-append-installation.json`. Installation used the approved elevated
Docker/protected-fixture path without printing credentials. The Windows cache
verification issue was resolved by reading under the Linux UID; application
cache permissions stayed private. The final retry succeeded with no remaining
installation blocker. No new stage was started.

## 17 October 2026 - Automatic historical results, optional preview and deletion

Implemented the requested historical-viewer follow-up without starting Stage 05:

- Finished collections and retained collection opens automatically query and
  display **Timestamped events**. Per-page selection, filters and stale-response
  guards remain independent, including duplicated same-system pages.
- **Log entry** replaces **Original text** and removes only the exact parsed
  timestamp prefix, preserving all other characters. Unknown timestamps keep
  their original text. Context and literal filtering still use the full line.
- **Collect sources** works without Preview. A collection-plan panel appears
  only after an explicit preview request and invalidates with changed scope.
- **Delete collection** confirms the system and collection ID, and deletes only
  the current owner's terminal collection. Both roles have this personal-data
  action; active jobs return 409. Events, sources, cursors, download grants,
  cached snapshots and captured files are removed. Other collections survive.
  Capture guards serialize deletion with queries/context and bounded download
  chunks. Staging restores bytes on SQL rollback, including rollback cleanup
  failure, and request cancellation waits for the delete to finish safely.
- A final captured-file unlink failure returns a committed deletion with
  `cache_cleanup_pending: true` and a visible dismissible warning. Detached
  private bytes require operational cleanup; no automatic retry scheduler is
  claimed in this historical slice.

Changed files for this follow-up:

- `backend/src/inspector/history.py`, `history_cache.py`, new
  `history_retention.py`, and `security.py`: scoped deletion, guards, safe file
  lifecycle, read-cache invalidation and owner permission.
- `backend/tests/integration/test_history_deletion.py`,
  `backend/tests/unit/test_history_retention.py`, `test_history_cache.py` and
  `test_security.py`: persistence, authorization, concurrency and file boundaries.
- `frontend/src/components/HistoricalViewer.tsx`, `SystemWorkspace.tsx`,
  `frontend/src/styles.css`: automatic query, direct collection, Log entry,
  deletion confirmation/navigation and cleanup notices.
- `frontend/e2e/historical.spec.ts`, `ssh.spec.ts`: automatic/direct collection,
  exact Log entry/Context, delete confirmation and same-context page isolation.
- `backend/openapi.json`, `frontend/src/api/schema.d.ts`: generated DELETE
  operation and `HistoricalDeleteResponse` (including cleanup status).
- `backend/README.md`, `frontend/README.md`, `docs/05_API_AND_WEBSOCKET.md`,
  `docs/06_UI_UX.md`, `docs/12_TRACEABILITY.md`, `docs/14_MARIADB.md`, this entry.

Commands actually run, Python = `backend/.venv/Scripts/python.exe` unless stated:

| Command/check | Actual result |
|---|---|
| `python -m pytest backend/tests/unit -q` | Final **500 passed, 3 skipped in 13.71 s**. Skips: POSIX-only permission behavior, Windows-denied SSH symlink creation, and the new POSIX real-symlink retention test. Windows reparse-point rejection is tested separately. |
| `python .cache/collection_browser_check.py linux-unit` | **23 passed in 2.92 s** in the existing Linux runner: retention/cache/security tests, including actual POSIX symlinks and rollback-error restoration. |
| `python scripts/verify_stage4.py integration --suffix s4_coll_ui_1017` | **105 passed, 1 failed in 160.40 s** in fresh disposable MariaDB. Failure was the new cleanup-failure test's final test-only manual cleanup passing a string cache root instead of `Path`; all application deletion assertions passed. The source test was corrected and retained failure evidence was preserved. |
| `python .cache/verify_collection_deletion.py` | Final **20 passed in 41.77 s** in new `inspector_test_s4_coll_del_1017b`: every deletion test plus all historical query/context/cursor/ownership regressions. Includes corrected cleanup-failure test and latest rollback restoration. Log/command JSON: `verification/stage-4/s4_coll_del_1017b*`. The prior full run also passed the real direct/single-jump SSH cases. |
| `python scripts/frontend.py e2e historical.spec.ts` with `INSPECTOR_E2E_URL=https://localhost:8446`, `INSPECTOR_E2E_LOCAL_ASSETS=1` and protected synthetic accounts | **5 passed in 45.9 s**. Real API/MariaDB/plain/ZIP/TAR fixture collection, literal queries, Context/download, direct collection, automatic load/reopen, confirmed deletion, same-context different/same-system isolation and UTC controls. Report `verification/stage-4/collection-ui-browser.json`. Initial focused run caught missing implemented-action permission (403); added the owner permission and reran successfully. |
| Manual inspection of browser screenshots via image viewer | PASS: light Log entry/results and dark deletion dialog; browser captures exercise both themes and existing 1280x720/1920x1080 layouts. Captures are under `verification/stage-4/screenshots/`. |
| `python scripts/frontend.py lint`, `typecheck`, `build`, `api:check` | PASS. Final Vite build: 195 modules. Existing >500 kB minified chunk advisory remains. |
| `python -m ruff check --config backend/pyproject.toml backend/src backend/tests`; corresponding `ruff format --check` | PASS, **68 files formatted**. |
| `.venv/Scripts/python.exe -m mypy src` from `backend` | PASS, **27 source files**. |
| `python -m unittest discover -s tests/package -q` | **128 tests run, 9 skipped**, no failures. Package skips retain their existing conditional prerequisites. |
| `INSPECTOR_CONFIG_FILE=examples/deployment-policy.example.yaml python -m inspector.cli openapi --output backend/openapi.json`; `python scripts/frontend.py api:generate` | PASS, followed by generated API drift check. Initial OpenAPI invocation without a deployment config failed safely and was corrected with the example file. |
| `python .cache/prepare_collection_ui.py` | PASS: isolated wheel/sdist and exact frontend assets prepared at `.state/stage4-ssh/collection-ui/backend`. **34 packaged files** checked against wheel; SHA256 `5ebbe363cc104d300fed3002f261366d05f0d2b764064b765ce99485b31a8e09`. Evidence `verification/stage-4/collection-ui-package.json`. |
| `git diff --check` | PASS; existing LF/CRLF notices are non-fatal. |

Browser setup used new isolated `inspector_test_s3_web_cui_1017`, fresh file-only
synthetic accounts/TLS and a temporary app at **https://localhost:8446**. Its
helper commands were `prepare`, `migrate`, `seed`, `start`, `restart`,
`linux-unit`, and finally `stop` in `.cache/collection_browser_check.py`.
Sandbox Docker access was denied; approved elevated commands accessed only
the local daemon/test fixtures. No secret values were printed. The existing
8444/8445 services, database/cache and installed bundles were not replaced.

No schema/dependency change is required. At the end of source verification,
8445 remained on `.state/stage4-ssh/active-append-fix/backend` awaiting explicit
installation authorization. The subsequent authorized installation is below.
The SSH browser suite was adapted but not rerun: this new browser fixture has
no SSH vault/trust setup, while the full Linux integration run exercised the
real synthetic direct/single-jump collector. No production target, credential,
remote file or infrastructure was contacted or changed. Stage 05 remains next.

### Authorized local installation of the collection-viewer update

The user explicitly authorized deployment. Installed the previously tested
artifact `.state/stage4-ssh/collection-ui/backend` at **https://localhost:8445**
by changing only the `runtime-stage3` backend bind mount and restarting that
service with `--no-deps`. No migration, rebuild, dependency installation,
configuration/credential change or target SSH connection was required.
Normal restarts continue to use `scripts/stage4_local.py up`.

Before the switch, stopped only that backend and made consistent protected
database/raw-cache backups plus the exact prior Compose/application files and
backend artifact under `.secrets/stage4-ssh/pre-collection-ui/`. Database dump:
**194,590,817 bytes**, SHA256
`8d1db97abc0a35692a117cfa4d9f9109dfdd6b2b47362977ef202a763aaade4d`.
Raw cache: **900 files / 230,869,839 bytes**; archive SHA256
`3eb6cb0596c579c951c033438d665e0876114bad963924e643c21e27ea91c24d`.
The previous active-append-fix artifact and all older backups remain intact.
Installation was independently reviewed before execution; exact Compose-byte
rollback was available if any installation check failed. No rollback was needed.

Commands actually run:

| Command/check | Actual result |
|---|---|
| `backend/.venv/Scripts/python.exe -m py_compile .cache/install_collection_ui.py` | PASS. |
| `backend/.venv/Scripts/python.exe .cache/install_collection_ui.py` | PASS: complete backup, guarded mount switch, successful restart and preservation checks. Wheel SHA256 remains `5ebbe363cc104d300fed3002f261366d05f0d2b764064b765ce99485b31a8e09`. All 34 packaged source/assets matched the prepared wheel before switching. |
| HTTPS/backend verification | PASS: certificate/hostname-verified readiness 200, all **3 served frontend assets** match the tested hashes, imported history/cache/retention/security modules match the artifact, and the collection DELETE operation is present. Schema remains `0008_security_setting`. |
| Database/cache/configuration preservation | PASS: **28 stable table counts/checksums**, including indexed `history_events`, and **all 900 cached file byte counts/hashes** preserved. Vault and application configuration hashes unchanged. Startup/job/workspace/auth/query activity tables are deliberately excluded from stable checks. Cache verification ran under the existing Linux serving UID; private ACLs stayed unchanged. |
| Retained 8444 app | PASS: HTTPS readiness 200 and exact original index bytes preserved. No shared bundle or other service was replaced. |
| `.toolchains/node-v24.22.0-win-x64/node.exe --check .cache/verify_collection_ui_install.mjs` | PASS (helper preparation). |
| `.toolchains/node-v24.22.0-win-x64/node.exe .cache/verify_collection_ui_install.mjs` | PASS, **no limitations**: both synthetic Administrator/Inspector logins and settings roles, actual installed asset hashes, direct Collect sources button with hidden preview panel, automatic query of existing owned retained synthetic data, Log entry exact timestamp removal, original Context, and Delete collection control. No browser page errors or external requests. |
| Installed Inspector screenshot inspected via image viewer | PASS: automatic timestamped rows, Log entry heading/text, direct collection controls and deletion action visible. Screenshots contain only recognized synthetic fixture lines and no password inputs. |

Browser verification permitted only login, new smoke workspaces, retained-data
query/context and best-effort detach. It created no collection/plan, deleted no
collection, changed no configuration or theme, and performed no global logout.
The user's other browser sessions remain independent. Only fresh smoke
workspaces were detached. The existing app's runtime restart applied its normal
workspace-detachment/interrupted-job behavior; no remote collection was started.

Evidence: `verification/stage-4/collection-ui-install-backup.json`,
`collection-ui-installation.json`, `collection-ui-install-browser.json`, and
`collection-ui-install-administrator.png` / `collection-ui-install-inspector.png`.
The local Docker/protected-fixture and browser commands used approved elevation;
no secret values were printed. `backend/README.md` now identifies the installed
artifact and recovery backup. Stage 05 remains the next separately authorized
scope; there is no remaining installation blocker.

## 17–18 October 2026 — Stage 05 live monitoring review gate

The user authorized Stage 05. Implemented this stage and stopped before Stage 06.
No installation into 8444/8445, production connection, infrastructure change,
remote file write, repository push or real-data migration was performed.

Implemented supervised read-only SFTP following with approved direct/single-jump
routes, shared host connections and reference-counted unfiltered source capture
within complete matching project/owner/configuration/access contexts. Separate
sessions retain private filters, pane policies, replay and workspace leases.
Pinned seed boundaries preserve split UTF-8/partial lines and duplicate text at
different byte positions. Reverse matching scans honor byte/line/time limits,
per-pane measured rows, unknown-timestamp diagnostics and explicit older-history
requests. Unknown lines cannot satisfy the timestamped seed viewport.

Capture polls at 750 ms. New events wake a monotonic 500 ms merge deadline;
idle sources do not hold a watermark. Observed rename/copytruncate, reconnects,
gaps, backlog, retention eviction and late events remain visible. Raw buffers,
input/output frame bytes, per-client replay and stopped-session memory are
bounded. Refiltering uses retained raw data without SSH reconnection. Display
pause continues collection and counters; Stop releases only that monitor.

MariaDB `0009_live` adds scoped session/subscription and recording-owner foreign
keys. Atomic quota reservation covers workspace/system/account/deployment;
explicit transfer also checks destination workspace capacity. Stop, history,
save, refilter and transfer serialize against the control lease. WebSockets
validate protocol 2, exact Host/Origin, cookie/CSRF, owner/project/workspace/lease
and filter version before protected dispatch, with a silent watchdog and bounded
fail-closed database checks. Valid old-version ACKs queued across a filter reset
are discarded; invalid/future references fail. Denial audits contain IDs and
classification only. Database/supervisor loss and backend restart never restart
SSH automatically. Administrator cross-owner stop is audited and returns no
private snapshot/filter data.

Both roles can monitor through topology or the live logs workspace. The viewer
uses measured individual pane heights, TanStack virtualization, canonical UTC
ordering, literal global/per-process any/all inclusion/exclusion and Unicode
casefold, independent same-context pages, explicit detached resume and scoped
late-frame/HTTP-response fences. Theme changes preserve streams. Global logout
ends the shared login. Explicit recording saves retained nonmatches and new
original-byte ranges before publication into an owned offline historical
investigation. Stop/cancel/limits retain partial coverage. Byte limits plus a
200,000-event recording cap are explicit; original-range cache append rolls back
safely. These partial ranges cannot claim a complete-source raw download.

Changed source/document groups:

- `backend/src/inspector/live.py`, `live_engine.py`, `ssh_transport.py`, `app.py`,
  `auth.py`, `services.py`, `source_access.py`, `ssh_access.py`, `security.py`,
  `history.py`, `database.py`, `__main__.py`;
  `persistence/models.py`, migration `0009_live.py`, OpenAPI, pyproject/uv lock.
- New live engine/SFTP/control/authentication/real-TCP units and scoped live,
  filter-reset and terminal-state MariaDB/ASGI integration regressions.
- `frontend/src/components/LiveViewer.tsx`, `live.ts`, `SystemWorkspace.tsx`,
  `App.tsx`, API client/generated types, semantic styles and `e2e/live.spec.ts`.
- `scripts/prepare_stage5_runner.py`, `stage5_local.py`,
  `stage5_sftp_fixture.py`, `verify_stage5.py`, `verify_stage5_preservation.py`.
- Bounded Stage 05 capacity sampler and temporary diagnostic wrappers; normal
  runtime commands never enable diagnostic instrumentation.
- Root/backend/frontend READMEs, API/MariaDB/traceability documents,
  `progress/DECISIONS.md`, `TOOLCHAIN.md`, `V3_SLICE_PLAN.md` and this status.
  Original theme images, historical identity fixtures and interchange schemas
  remain unchanged. The actual resolver added BSD-3-Clause websockets 16.1.1
  for bounded runtime transport; MIT wsproto 1.3.2 is development-only for
  real TCP tests. Original notices and the 54-distribution inventory are kept.

Commands actually run (Python = `backend/.venv/Scripts/python.exe`):

| Command/check | Final recorded result |
|---|---|
| `python -m pytest backend/tests/unit -q -o junit_family=legacy --junitxml=verification/stage-5/guard-final-unit.xml` | **595 passed, 4 skipped in 25.33 s**; valid JUnit contains 599 cases, no failures/errors. Windows skips cover POSIX mode bits, two privileged/POSIX symlink cases and renaming a pinned open file. Linux live coverage below exercises actual rename. Five upstream legacy WebSocket deprecation warnings are retained. Exact argv/cwd/timing: `guard-final-unit-command.json`. |
| `python scripts/verify_stage5.py integration --suffix s5_final_all_1017` | **136 passed in 244.32 s**, no failures/skips/warnings, fresh disposable MariaDB 11.8.9 schema. Includes 106 prior integration cases and 30 live/filter/terminal cases. Full output/argv: `s5_final_all_1017.log` and `s5_final_all_1017-command.json`; independent container exit 0 also retained. |
| `python scripts/verify_stage5.py live --suffix s5_ctx3_1017 --match <recorded selection>` | **21 passed in 67.81 s**, no SQL warnings. Actual three-query source validation and one-query socket validation; 13 target/jump trust, credential, approval, root, revision and policy mutations; live security/recording, filter-reset fence, stale maintenance after Stop/attach and two startup/Stop outcomes. Full selection/argv: `s5_ctx3_1017-command.json`. |
| `python scripts/verify_stage5.py linux-unit` | **44 passed in 10.49 s**, including real SFTP rename/drain, copytruncate, reconnect/rekey, five sources plus idle peer, bounded proof overlap/cancellation and three real TCP message/fragment/queue tests. Five documented transport deprecations; no failures/skips. |
| `python scripts/verify_stage5.py upgrade --suffix s2_upgrade_s5_1017b` | PASS: populated `0002_foundation_preferences` → final `0009_live`, including recording-owner foreign key. Accounts/password verification/preferences, two systems, metadata/docs/scoped entities survive; old workspaces detach. DDL remained unchanged through final verification. |
| `python scripts/frontend.py e2e live.spec.ts`, protected synthetic accounts, `INSPECTOR_E2E_URL=https://localhost:8447`, final report `live-browser-final-eight-three-query` | **8 passed, 0 skipped/flaky/unexpected in 122.241 s**. Both roles, same/different-system same-context pages, measured pane heights, literal/per-process filters, retained refilter, pause/receipt, recording, theme stability, stale frames/HTTP, duplicate/reload/lease transfer, slow/closed page, logout, topology Monitor, real 21,000-line retention burst and concurrent capacity. |
| `python scripts/frontend.py lint`, `typecheck`, `api:check` | PASS; `frontend-*-final.log`. Disabled-origin discovery lists eight cases without reading protected fixture/account files. |
| `python -m ruff check --config backend/pyproject.toml backend/src backend/tests backend/migrations scripts`; corresponding `ruff format --check`; `python -m mypy src` from `backend/` | PASS: all scopes clean, **120 files formatted**, **29 source files** typed. Exact commands/logs: `guard-final-{ruff,format,mypy}-*`. |
| `python -m unittest discover -s tests/package -q`; `python tools/validate_package.py`; `validate_schemas.py`; `validate_deployment_examples.py` | PASS: **128 package tests, 9 platform skips**; 18 schemas, 102 valid and 36 rejected negative instances; 44 static deployment checks. `package-contracts-final.json` retains actual commands/results. These are package checks, not runtime acceptance substitutes. |
| Locked uv resolution/sync; `python scripts/collect_backend_notices.py` | Actual resolver installed runtime **websockets 16.1.1 (BSD-3-Clause)** and development **wsproto 1.3.2 (MIT)**; other locked versions preserved, **54** original distribution notice records retained. `websocket-transport-dependency.json` records evidence. |
| `python scripts/prepare_stage5_runner.py` | Separate Stage 05 image built: `sha256:668bfc011a595c63ea4f88c29eea56c326828662dbba1cd20a18a4eacdfcd8a8`. Existing pinned Linux base reused; original `:local` tag/image preserved. Initial Stage 05 image/build records remain as history. |
| `python scripts/stage5_local.py` with `prepare`, `migrate`, `fixture`, `up`, `configure`, `runner`, `archives`, `capacity-archive`, `paced`, `burst`, `resources`, `reset-active`, `restart`, `stop` | Guarded synthetic schema `inspector_test_s5_web_799802f49c`, generated TLS/accounts/vault and approved read-only SFTP. Only 8447/SFTP fixture services changed. Bounded reset restored five inactive generated files to 360 seed records and proved archive SHA unchanged; each full suite recreates the retention burst before capacity. Exact helper invocations/evidence retained under stage 5. |
| `python scripts/build_stage1.py` plus source/wheel/runtime-manifest comparison | PASS in **5.868 s**: 197-module Vite build, wheel/sdist; **36** packaged source/assets and migration 0009 match current bytes, all **29** runtime source hashes match the tested restart, JS/CSS hashes match tested assets. Wheel SHA256 `1a1c1fb7f0bd0f09a217fbd7bedb6bb8dcfaca228621ee1f928b4833fe9002e7`. `final-build.json` and `final-artifact-correspondence.json`. Existing >500 kB chunk advisory retained. No installation/release inferred. |
| Manual UI inspection | PASS: both roles/themes at 1920×1080 and 1280×720, latest five split panes, retention warnings and source coverage. Final burst: **21,373 received / 20,000 retained / 1,373 evicted**. `ui-review-final.json` and screenshots retained. |
| `python scripts/verify_stage5_preservation.py` after fixture stop | PASS: certificate/hostname-verified readiness **200** on 8444/8445; distinct original app images and original runner tag preserved; no authenticated/state-changing requests. Both Stage 05 fixtures exited. `retained-installations.json` and `fixture-completion.json`. |
| `git diff --check` | PASS; existing LF/CRLF conversion notices are non-fatal. Final package validator also passes after the documentation update. |

Final browser measurements use the source's UTC append timestamp and first
virtual-row DOM insertion, rather than Playwright assertion polling:

- Nominal two-window/two-system five-source monitoring: **p95 1,098 ms**,
  **16 physical appends / 32 DOM observations**, **3.99255 appends/s**. Each
  window has an idle fifth source. Evidence:
  `live-browser-final-eight-three-query-latency.json`.
- Concurrent capacity after the real retention burst: **p95 1,592 ms**,
  **8 qualifying samples**, **3.99543 physical appends/s**, **18 held frames**
  in the other page. Both investigations finish with six sources,
  **88,367 total events**, exactly **65,536 archive events / 16,777,216 expanded
  archive bytes**, **18,520,102 total expanded / 18,520,236 downloaded bytes**
  each. Probe boundaries prove two nonterminal jobs and five subscriptions per
  system; held-page delivery cannot stall the healthy page.
  `capacity-browser-final-eight-three-query-pass.json` and
  `final-workload-evidence.json` retain timing, source and job evidence.
- The separate clean focused run also passes: **p95 1,726 ms**, eight
  qualifying samples at 3.995 appends/s. It remains separate evidence in
  `capacity-browser-three-query-focused-pass.json`.

The qualified final capacity resource snapshot at 22:35:06.760 UTC records
application **159.1 MiB / 512 MiB**, instantaneous CPU **97.46%**, and MariaDB
**719.4 MiB / 1 GiB**, CPU **46.24%**. Both before/after probes confirm two active
jobs and ten subscriptions. Docker's Linux VM has **16,630,767,616 bytes**
allocated; the Windows host has **34,073,227,264 bytes** physical memory.
These are local snapshots, not peak RSS or full-browser/proxy measurements.
The final entry in `resources-capacity-sixteen-mib.json` is preserved separately
inside `final-workload-evidence.json`.

The exact tested source was hashed before/after the normal-command restart:
container start **22:32:21.357 UTC**, certificate/hostname-verified readiness
**22:32:26.394 UTC**. No diagnostics, source changes or backend restarts occurred
during the passing focused/full browser runs. The packaged frontend assets are
unchanged `index-BxWBxWdK.js` and `index-DoDRv8yT.css`; their hashes and current
wheel/source correspondence are recorded. The Stage 05 test services are now
stopped; retained 8444/8445 services were never upgraded.

Earlier failures and corrections remain in distinct artifacts:

- Initial transport/browser/fixture issues included absent WebSocket transport,
  Chromium fixture local-network permission, teardown ordering, SSH-identity
  assertions, recording cancellation, queued old ACKs, lease/quota races,
  oversized valid HTTP literals and merge/background-paint delay. Contracts
  and rejection expectations were preserved.
- The first two concurrent archive runs interrupted live capture with
  `DATABASE_UNAVAILABLE`; one archive retained partial data. Their exact
  original cause was not established. Fresh nonlocking validation, in-flight
  coalescing, scoped batching and bounded supervisor checks were added and
  tested, without caching completed grants or changing fail-closed deadlines.
  Failure-1/failure-2 browser/socket evidence is retained.
- Real paced runs then measured p95 **2,676 / 2,528 / 2,289 / 2,416 / 2,106 /
  2,305 / 2,238 / 2,194 ms**. An earlier low-rate diagnostic did not meet the
  required producer rate and is not a capacity pass. An extensive profiler
  timed out with partial investigations; its diagnostic impact remains
  unresolved and its missing original exception class is explicitly recorded.
- A lean diagnostic measured 1,787 ms but exposed an explicit Stop being
  overwritten by stale maintenance. Fresh locked intent/lease checks and
  guarded startup transitions now have deterministic real DB regressions.
  A later focused 1,953 ms pass was followed by a full-suite **2,079 ms**
  failure, preserved as failure-13. Neither was substituted for the final
  complete passing suite.
- Final fixes retain **750 ms polls / 500 ms merge deadlines**: bounded parallel
  fingerprint checks drain peers; unchanged cursors keep proved anchors;
  appends reuse only the full prefix proved in that poll. Fresh common
  source context plus two scoped joins reduce source validation to three
  reads; each socket check uses one fresh joined read. Shared pure validators
  preserve the ordinary locked controls' actor/login/owner/lease rules.
  Every protected dispatch/ACK rechecks authorization. Filter frames wait for
  the committed database version and engine reset to agree.
- The actual transport audit showed Uvicorn's wsproto/SansIO adapters ignore
  its receive-queue count setting. The explicit locked `websockets` adapter
  enforces **16 KiB messages / 16 queued messages**, proven by actual TCP
  fragmentation/backpressure tests. Upstream legacy deprecations are retained;
  upgrades must rerun these tests. Temporary diagnostic commands were removed
  before clean measurements. No failing threshold or fixture workload was
  weakened.

Remaining platform/release limits: verification uses local Linux containers on
a Windows development host, not a qualified Ubuntu/Rocky installation. Direct
Uvicorn fixture TLS does not qualify release-proxy/full-browser RSS. GNU Make is
absent, so the recorded commands ran directly rather than through Make.
Windows platform skips have their stated OS prerequisites; actual Linux live
rename and transport paths passed. Window-state checks used headless Chromium
pages in one browser context; native OS window-manager interaction was not
exercised by that driver run. Long-duration production soak, all-image
offline save/load/restart, OS installation, full backup/release qualification
remain later gates. SFTP cannot prove every hidden rewrite/rotation or exactly
once capture; transient replay is ephemeral and recordings are partial/bounded.

**Stage 05 is complete within the recorded local synthetic baseline. Stop at
this review gate. Next: `prompts/06_INVESTIGATION_TOOLS.md`, only after separate
authorization.** No full investigation editor, correlation, bookmarks/annotations,
bundle exchange, Ansible reconciliation or release deployment was implemented.
Using Stage 05 on retained 8445 requires a separately authorized backed-up
migration/install.

## 18 October 2026 — Stage 05 installed into retained local 8445

User authorization: “Deploy stage 5.” Upgraded only the existing local
`runtime-stage3` service at **https://localhost:8445**. The isolated test app on
8447 and its synthetic SFTP remain stopped; 8444 was neither restarted nor
reconfigured. No production host, configured target SSH connection, remote
repository or later-stage implementation was used.

Installed the already tested wheel unchanged, SHA256
`1a1c1fb7f0bd0f09a217fbd7bedb6bb8dcfaca228621ee1f928b4833fe9002e7`,
into `.state/stage5-install/backend`. All **48 packaged application files**,
including migrations and bundled assets, match the wheel. The served assets are
`index-BxWBxWdK.js` and `index-DoDRv8yT.css`, with the hashes recorded at the
review gate. The 8445 Compose override pins image
`sha256:668bfc011a595c63ea4f88c29eea56c326828662dbba1cd20a18a4eacdfcd8a8`
and isolated wrapper scripts. It explicitly runs one ASGI worker with the
`websockets` adapter, **16,384-byte messages / 16 queued messages**. The original
runner tag and all previous application artifacts remain retained.

Stopped only 8445 before taking consistent SQL/cache backups. Protected recovery
material is under `.secrets/stage5-install/pre-0009-live/`: SQL dump, raw-cache
archive, byte/SHA and UID/GID/mode manifests, exact prior Compose/application
files, prior backend and the unchanged vault key. The compressed SQL is
**194,569,190 bytes**, SHA256
`deb6df083c32ab53e381447eae5f7e902e93c791b9d86ae6cc9284b67a64e94c`.
It uses an explicit database positional argument with no CREATE DATABASE/USE.
Both backup archive hashes were rechecked before DDL. A matching-state recovery
procedure is retained in `.cache/stage5-rollback.txt`; no rollback or restore
drill was needed or performed during this deployment.

Applied `0008_security_setting` → **`0009_live`** with the separate schema
migrator while the serving supervisor was stopped. Before restart, all **35 old
table counts** and **34 non-Alembic table checksums** were identical; the only
new tables were empty `live_sessions` and `live_subscriptions`. After restart,
**27 stable table counts/checksums**, all **897 original cache files /
230,864,349 bytes**, and **957 file/directory ownership/mode entries** matched.
Startup workspace/job/source interruption and login/audit/query activity were
excluded from the later stable-table comparison. The earlier pre-start comparison
covered every old table. Accounts/password verifiers, preferences, systems,
topology, settings, credentials, trust/approval data and indexed events were
preserved. Application config and vault source hashes are unchanged, including
all explicit deployment limits. The runtime key is UID 10001, mode 0600 and the
same 32 bytes; its contents were never printed.

Commands actually run (repository root; locked local Python/Node; PASS):

- `backend/.venv/Scripts/python.exe -m py_compile .cache/install_stage5.py`.
- `backend/.venv/Scripts/python.exe .cache/install_stage5.py prepare`, then
  `backup`, `seal`, `migrate`, `start`, `verify`, each as a separate phase.
  Only `runtime-stage3` was stopped/recreated; migration used
  `compose run --rm --no-deps migrate` with the pinned image and snapshot.
- `.toolchains/node-v24.22.0-win-x64/node.exe --check .cache/verify_stage5_install.mjs`
  and `.toolchains/node-v24.22.0-win-x64/node.exe .cache/verify_stage5_install.mjs`:
  **PASS in 5.870 s**, no limitations. Both synthetic roles retained their saved
  themes and settings permissions. Two pages per role in one browser context
  received distinct fresh workspaces; local selections/filters/layout stayed
  independent. All four smoke workspaces were detached without global logout.
  Two original owned demo investigations queried successfully, including two
  source-context reads. Actual served asset hashes matched. Catalogue, topology,
  preferences and existing live lists were unchanged; zero external requests,
  page errors, forbidden writes or WebSocket attempts occurred. Root and UI agent
  inspected both installed light/dark screenshots with no visual blocker.
- Independent read-only Docker/SQL/TLS/WSS audit: **PASS**. Actual serving UID
  `10001:10001`, read-only root and snapshot, capability drop, no-new-privileges,
  512 MiB memory and 128 PID ceiling are retained. Runtime SQL privileges are
  exactly SELECT/INSERT/UPDATE/DELETE on this schema, with global USAGE only;
  no root/migration secret is mounted. No live sessions or subscriptions started.
  A real unauthenticated WSS upgrade with verified certificate/hostname and exact
  Origin returned HTTP **403** before acceptance. 8444 retained its container ID,
  start time, image and served index; its HTTPS readiness remained 200.
- `backend/.venv/Scripts/python.exe scripts/verify_stage5_preservation.py --installed-stage5`:
  **PASS in 4.59 s**, as did syntax and Ruff checks for the helper. The new
  explicit mode verifies the authorized 8445 image and unchanged 8444 container,
  original runner and stopped fixtures. Default pre-deployment expectations
  remain intact; `retained-installations.json` was not overwritten. Final
  `git diff --check`: **PASS**, with non-fatal LF/CRLF notices.

Changed files/artifacts: `README.md`, `backend/README.md`, this status and
`progress/V3_SLICE_PLAN.md`, `scripts/verify_stage5_preservation.py`; ignored
operator installers/browser checks/recovery
instructions under `.cache/`; isolated snapshot under `.state/stage5-install/`;
the existing generated `deploy/local-mariadb/stage3-browser.compose.local.yaml`;
protected backup files; and actual deployment evidence under
`verification/stage-5/deployment-*.json` with `deployment-screenshots/`.
No backend/frontend product implementation changed for installation. Earlier
unit/MariaDB/SFTP/capacity suites were not repeated: the installed wheel/image
are the exact tested artifacts, and the deployment ran actual migration,
preservation, installed-browser and transport checks instead. This remains a
local Linux-container installation, not Ubuntu/Rocky or offline-release
qualification. There is no deployment blocker. **Stop at Stage 05; next scope
is `prompts/06_INVESTIGATION_TOOLS.md`, only after separate authorization.**


## 18 October 2026 - Stage 06 investigation workflow complete

Authorization: "Proceed with stage 6." Completed only
`prompts/06_INVESTIGATION_TOOLS.md`. Existing HTTPS 8444/8445 backend containers,
images, accounts, configuration, vault and cache were preserved. The earlier
asset-preservation measurement below preceded the final frontend build: a later
deployment preflight found that 8444's shared frontend mount had advanced to that
build. See the separate deployment correction below. New disposable
MariaDB schemas and the synthetic HTTPS/SFTP fixture on 8448 were used; that
fixture and its SSH server are stopped. The retained 8445 application remains
Stage 05 at `0009_live`. No production host, real target credentials, remote
repository push or installation upgrade was used.

Implemented behavior:

- Both roles save/reopen private investigation titles, notes, process/time/filter
  selection and pane layout. Workspace/bookmark mutations share one optimistic
  revision and cannot overwrite a stale tab. Reopen/replay works after a real
  backend restart with SSH forbidden. Existing source/event IDs remain unchanged.
- Exact parsed-field correlation distinguishes golden **REQ-0042 (17 events)**
  from **REQ-00420**; literal search includes the longer identifier. Trace order
  and integer microsecond deltas are deterministic, with physical-source time
  inversions and explicit clock/causality limits. Real MariaDB tests cover dotted,
  quoted, Unicode and literal backslash-u metadata keys.
- Bookmarks/annotations retain original identity/name snapshots and source-order
  unmatched/out-of-range context, independently of match totals. Whole-capture
  pins block expiry; context pins preserve bounded independent event-text/
  provenance snapshots. Explicit unpinned expiry removes original source cache
  and indexed events while keeping notes/pinned context and precise unavailable
  status. Deletion cannot silently remove pinned investigations or bookmarks.
- Source details expose raw/index availability, observed extrema, retained parse
  counts, checksums, captured ranges and completeness limitations. Configured
  upstream/downstream neighbours can enter historical/live selection, with an
  explicit warning that possible flows do not prove observed causality.
- Bundle version 1.0 exchanges a typed logical topology/event/context/notes
  snapshot in two ZIP members with actual byte lengths and SHA-256 checksums.
  All-string literal redaction reaches metadata keys, labels, filenames, notes,
  context and topology text. Credentials, trust, approvals and active connection
  profiles are excluded by typed projections. Full owner/project/login-bound
  preview and explicit review precede download/import; cancellation and revoked/
  expired staging cleanup preserve the four-usable-preview quota.
- Upload admission, ZIP central-directory preflight, actual expanded bytes,
  member/name/type/CRC/hash/version/identity validation, line length, JSON depth/
  node limits and bounded workers reject unsafe input before commit. Redaction
  caches literal match positions and checks exact output bytes/nodes/deadline
  before writes, preventing suffix-rescan or replacement-expansion exhaustion.
  Technical identities which cannot be reopened through scoped routes are rejected.
- Foreign imports create separate owned offline rows in the selected project,
  without active topology/source associations or connection attempts. Original
  imported event documents stay immutable; separately revisioned analysis permits
  notes, bookmarks, filtering/layout, traces and re-export. No Administrator
  private-content bypass exists. Composite MariaDB FKs enforce parent owner/scope.
- UI operations reject stale response completions after navigation. Tests hold a
  bookmark response while selecting another investigation and prove the new
  resource's identity, draft and revision remain unchanged. All assets remain
  local, both reference themes are preserved, and no dependency was added.

Changed files:

- New backend `investigations.py`, `investigation_bundles.py`, persistence
  `investigation_models.py` / `bundle_models.py`, and frozen additive migrations
  `0010_investigations`, `0011_investigation_bundles`, `0012_offline_analysis`.
- Existing HTTP/security/database/history wiring, migration metadata imports and
  a backward-compatible ZIP preflight extension in `log_engine/reader.py`.
- Generated `backend/openapi.json`, frontend API types, both new bundle schemas;
  React `InvestigationTools`, `EventBookmark`, `BundleTransfer`, typed aliases,
  historical workspace, neighbour actions and semantic CSS.
- New unit/MariaDB/capacity/upgrade/browser tests; existing security and retention
  rollback test fixtures updated without weakening their original assertions.
- Isolated `prepare_stage6_runner.py`, `stage6_local.py`, `stage6_sftp_fixture.py`,
  `verify_stage6.py`, `verify_stage6_build.py`, `verify_stage6_preservation.py`;
  README/API/MariaDB/traceability/decision/slice-plan/status documentation.
  Ignored synthetic secrets/state/Compose files and verification evidence remain
  local. Original source fixtures, event IDs, images and dependency locks remain
  unchanged.

Commands actually run (repository root unless specified; Python is
`backend/.venv/Scripts/python.exe`):

| Command/check | Recorded result |
|---|---|
| `python scripts/verify_stage6.py checks` | Final **all 12 checks pass**; exact subprocess argv/cwd/exit codes in `verification/stage-6/checks/commands.json`. Final unit suite **629 passed, 4 skipped, 5 documented transport deprecations in 25.09 s**. Earlier runs and corrected failures are described below. |
| Checks helper: `python -m unittest discover -s tests/package -q`, package/schema/deployment validators | **128 tests, 9 platform skips**; 20 schemas, 102 valid and 36 rejected negative instances; 44 static deployment checks. These are package checks, not runtime acceptance substitutes. |
| Checks helper: backend Ruff, format, mypy; frontend `lint`, `typecheck`, `api:check` | PASS; **138 Python files formatted**, **33 runtime source files typed**. Generated OpenAPI/TypeScript types match current models. |
| Checks helper: `python scripts/build_stage1.py` | PASS: **200-module Vite build**, wheel and sdist. Existing >500 kB chunk advisory remains non-fatal. No installation/release is inferred. |
| `python scripts/verify_stage6.py integration` (fresh suffix recorded in command artifact) | **155 passed in 383.07 s** on Linux Python 3.13.16 / real MariaDB 11.8.9, including 136 prior regression cases and 19 Stage 06 cases. Direct/jump read-only SFTP, live/WS/auth/security/retention regression cases pass. `s6_9ebf3e77.log` and `-command.json`. |
| `python scripts/verify_stage6.py investigations` | Final expanded scope **21 passed in 75.82 s**, no skips/failures, including all 10 core, 10 bundle and one 12 MiB capacity case. `s6_45fc4f1b.log` / command artifact. Covers owner/project/session guessing, both roles, actual FK INSERT/UPDATE rejection, upload admission, quota/cancel lifecycle, revisions, offline edits/re-export and original cache/document immutability. |
| `python scripts/verify_stage6.py investigations --match <recorded four-case selection>` | **4 passed in 18.75 s** after bounded redaction/Unicode changes: capacity, logout during blocked worker, corrupted/unsafe/future/surrogate input, source-context pin/expiry and actual process/parser rename. `s6_e745e232.log` / command artifact. |
| `python scripts/verify_stage6.py investigations --match 'both_roles_redacted_exchange or corrupt_unsafe_or_future_bundle'` | Final technical-ID validation **3 passed in 12.98 s**, 18 deselected; both-role foreign offline exchange and rejection paths. `s6_155c5761.log` / command artifact. |
| `python scripts/verify_stage6.py upgrade` | PASS: populated `0009_live` -> `0012_offline_analysis`, **every existing row in 36 old tables preserved**, including two accounts, systems, preferences, policy and deliberately repeated scoped event/source/workspace IDs. `s6_upgrade_5c865fb7.log` / command artifact. |
| `python scripts/frontend.py e2e investigation.spec.ts` with protected synthetic accounts and explicit `INSPECTOR_E2E_URL=https://localhost:8448` | Final **4 passed, 0 skipped/flaky/unexpected in 35.552 s**. Both roles, same-context deep links, exact/literal five-process trace, note/context, preview cancellation/redaction/download, foreign A->B offline import/edit/re-export, expiry, actual five-neighbour Monitor/Stop and held response isolation. `investigation-browser-final-coverage.json`, exact argv in that report. |
| Manual UI inspection | PASS: saved workspace, source provenance/context, redacted preview, foreign imported analysis and expired-source pinned context. Both roles/themes at 1920x1080 and 1280x720; **18 screenshots** and source hashes in `frontend-ui-review.json`. Root independently viewed five representative screenshots; no blocking clipping/overlap. Browser asserts no horizontal overflow, page errors or external requests. |
| `python scripts/prepare_stage6_runner.py`; guarded `stage6_local.py` fixture phases | Built a separate Stage 06 image from cached locked layers; original runner tag retained. Only new synthetic schemas and 8448/SFTP services provisioned/migrated/started/configured/restarted/stopped. `runner-build.json`, generated fixture state and migration/command records retain details. |
| `python scripts/verify_stage6_preservation.py --baseline`, then without that flag | PASS at the recorded measurement: certificate/hostname-verified readiness **200** on 8444/8445; original container IDs, images, start times, restart counts and served assets unchanged against baseline and prior deployment evidence. This measurement preceded the final frontend build; see the later 8444 asset correction below. Zero authenticated/state-changing requests to retained apps. Original runner preserved; Stage 06 and earlier Stage 05 fixtures exited. `retained-baseline.json`, `retained-installations.json`. |
| `python scripts/verify_stage6_build.py` | PASS: **54 packaged files** match current source, browser-tested source hashes and exact JS/CSS assets match. `final-artifact-correspondence.json`; wheel SHA-256 `421e69e7d64f4a2b4f00fb3195938e4e374d47e7df4e87afad28422f00732fe6`. |
| `git diff --check` | PASS; existing LF/CRLF conversion notices are non-fatal. |

The final measured offline exchange contains **12,582,912 raw text bytes**, 96
128-KiB physical records, **12,671,407 uploaded ZIP bytes** and **12,671,412
redacted downloaded ZIP bytes**. Equal-length replacement preserves the actual
12 MiB export workload. Import took **2.202 s**, the complete test exchange
**6.433 s**, with process peak RSS **358,592,512 bytes** and **zero SSH attempts**.
`capacity-exchange.json` records this final run. This is the real ASGI/MariaDB
server-plus-test-client process measurement, not a production/browser memory
qualification or a new concurrent-live capacity claim. Earlier larger RSS samples
remain in their separate full/focused logs.

Corrected failures and limits are retained rather than treated as passes:

- Initial unit rollback fixture lacked the new pin lookup; its original rollback/
  restore assertions still pass after adding the required test-double methods.
- Real MariaDB caught a reserved unquoted cursor column; the corrected frozen
  migration is verified on fresh schemas, including populated upgrades.
- The first investigation router accidentally used a different transaction
  dependency scope from authentication, producing a second session/lock timeout.
  It now shares `scope="function"`; actual logout-during-guard and worker tests
  prove that locks are released and stale logins cannot commit private changes.
- MariaDB metadata paths require SQLAlchemy's escaped key representation; Unicode,
  punctuation, quote and literal escape identity tests now pass.
- Early test/API verb mismatches, accessible labels, download-prefix validation,
  generated nullable types, preview quota lifecycle, stale bookmark completions
  and post-expiry progress refresh were corrected. Earlier reports/logs under
  `verification/stage-6/` retain their failures. Invalid fixture field names and
  a naturally shortened redacted capacity output were corrected in fixtures;
  source validation and the 12 MiB workload were preserved, not relaxed.
- Windows unit skips cover POSIX permission bits, two privileged symlink cases
  and renaming an ordinary pinned Windows handle. Real Linux integration covers
  actual retention/SSH behavior. GNU Make is absent (`Get-Command make` found no
  command), so the documented underlying commands ran directly.
- This stage exchanges decoded retained event text with original identity/range/
  checksum provenance, not a binary-source archive for imported raw downloads.
  Context pins retain bounded event snapshots; they do not retain entire source
  files after explicit expiry. No redactor can identify unspecified sensitive
  values, and observed timestamps do not establish continuous coverage/causality.
- Ubuntu/Rocky installation, native OS window-manager checks, policy-maximum
  bundle sizes, full proxy/browser memory, long-duration soak and complete
  offline image save/load/cold-start/release qualification remain later gates.
  No full release or installation claim is made by this local container result.

**Stage 06 is complete within the recorded local synthetic baseline. Stop at
this review gate. Next: `prompts/07_INVENTORY_AND_UI.md`, only after separate
user authorization.** There is no current Stage 06 blocker and no retained
installation was upgraded by this work.


## 18 October 2026 - Stage 06 deployed to the retained local application

Authorization: "Deploy stage 6." Upgraded only **https://localhost:8445**
(`runtime-stage3`, database `inspector_test_s3_web_317d3a3c4a`) from `0009_live`
to **`0012_offline_analysis`**. The serving backend is the isolated tested artifact
at `.state/stage6-install/backend`, mounted read-only. No Stage 07 work,
production/target-host connection, repository push or external deployment occurred.

Installed wheel SHA-256:
`421e69e7d64f4a2b4f00fb3195938e4e374d47e7df4e87afad28422f00732fe6`.
The immutable runtime image is
`sha256:668bfc011a595c63ea4f88c29eea56c326828662dbba1cd20a18a4eacdfcd8a8`,
the same cached dependency image used by Stage 05 and the Stage 06 tests. No
dependency download, image pull or frontend rebuild was needed for deployment.
All **55 packaged runtime/migration/frontend files** match the wheel, all **33
runtime source modules** match the final source correspondence report, and the
three actual served frontend assets match the tested build.

Before stopping 8445, an independent audit established zero active historical
collections, live sessions or subscriptions. Only that service was stopped.
Consistent recovery material is retained privately under
`.secrets/stage6-install/pre-0012-offline-analysis/`: SQL dump, cache archive,
byte/hash/ownership manifests, exact Compose/application files, protected vault
copy, previous installed backend and a complete recovery-point marker. The
compressed SQL dump is **194,573,904 bytes**, SHA-256
`f82832c8d38f00b7717ac50ddd18d3af7c5261bc466e54842e19bd4a3d93c763`;
the cache archive SHA-256 is
`54843615c24bb079ae05708c86ee0fd5f5e509589138e243878499882e15819a`.
The SQL dump intentionally contains no database creation/selection statements.
Both archives and the protected vault copy were verified before migration.
Prior Stage 04/05 snapshots and backups remain available. The matching written
recovery procedure is `.cache/stage6-rollback.txt`; no rollback/restore drill was
performed or claimed.

Migration applied the three additive revisions and created exactly seven empty
tables. **All 37 pre-existing table counts and all 36 non-Alembic checksums
matched before startup.** The prior disposable upgrade report's "36 old tables"
explicitly excluded `alembic_version`; there is no unexplained table difference.
After startup, **27 stable old table counts/checksums** still matched; the other
tables hold deliberate startup/session/workspace/job/cursor/audit state. All
**897 original cache files (230,864,349 bytes)** and **957 ownership/mode entries**
matched the protected snapshot under Linux UID 10001. Existing account,
preference, system, topology, credential/trust, security policy, configuration
and vault data were preserved. No collection or monitor was restarted.

Commands actually run (Python is `backend/.venv/Scripts/python.exe`, repository
root; Docker operations used the authorized local Docker Desktop access):

| Command/check | Recorded result |
|---|---|
| `python .cache/install_stage6.py prepare` | PASS after granting the local Docker access required by the sandbox. Initial default-sandbox invocation failed safely before preparation (`SetupError`, Docker pipe access); the approved retry selected the exact wheel/image, copied an isolated artifact and recorded the current 8444 baseline. `deployment-prepared.json`. |
| `python scripts/audit_stage6_deployment.py pre` | PASS: verified TLS readiness, restricted runtime/DML grants, no active collection/live work, actual unauthenticated WebSocket **403**, existing service identities and pre-existing 8444 asset drift. `deployment-audit-pre.json`. |
| `python .cache/install_stage6.py backup`, then `seal` | PASS: only 8445 stopped; complete SQL/cache/application recovery point and independently rechecked archive/vault hashes. `deployment-backup.json`, `deployment-backup-verified.json`. |
| `python .cache/install_stage6.py migrate` | PASS: `0009_live` -> `0012_offline_analysis`; all 37 old counts and 36 non-Alembic checksums unchanged; seven new tables empty; configuration/vault unchanged. `deployment-migration.json`. |
| `python .cache/install_stage6.py start`, then `verify` | PASS: only `up --detach --no-deps runtime-stage3`; certificate/hostname-verified readiness **200**, installed file/module/served-asset hashes, retained stable table/cache/permission checks and 8444 preservation. `deployment-installation.json`. |
| `python scripts/audit_stage6_deployment.py post` | PASS: 55 wheel members/33 runtime modules, schema, service restrictions, TLS and WebSocket boundaries verified independently with the actual runtime DML credentials. `deployment-audit-post.json`. |
| `python scripts/verify_stage6_preservation.py --installed-stage6` | PASS: both local HTTPS services ready; authorized 8445 artifact verified; 8444 container/image/start/restart/assets preserved against deployment preparation; original runner tag retained; Stage 05/06 browser/SFTP fixtures stopped. New `deployment-preservation.json` preserves the earlier pre-deployment reports. |
| `.toolchains/node-v24.22.0-win-x64/node.exe --check .cache/verify_stage6_install.mjs`, then the same executable without `--check` | Syntax PASS; final browser **PASS in 10.468 s**: both roles, actual served assets, independent pages in one context, five-process exact/literal correlation, source provenance/context, redacted download and offline import, personal save/restore/bookmark create/delete and re-export preview/cancel. Four fresh workspaces detached; zero external/forbidden/WebSocket requests or page errors. `deployment-browser.json`, exact argv/helper hash in `deployment-browser-notes.json`. |
| `python scripts/audit_stage6_deployment.py post-browser` | PASS: **53 historical jobs, 2 terminal live sessions and 47 target-action audit rows** unchanged from pre-deployment; zero active jobs/live sessions/subscriptions. TLS readiness 200, unauthenticated WebSocket 403, runtime/file boundaries and both containers preserved. Separate `deployment-audit-post-browser.json` retains the initial post audit. |
| Independent installed UI review | PASS: eight screenshots cover both roles/themes at 1440x1000. Root viewed the Administrator light offline analysis and Inspector dark redacted preview; controls, provenance, warnings and trace are readable with no blocking clipping. `deployment-screenshots/`. Theme rendering used page-local DOM overrides; saved preferences were verified unchanged. |
| `python -m ruff check --config backend/pyproject.toml scripts/audit_stage6_deployment.py scripts/verify_stage6_preservation.py`; corresponding `ruff format --check --config backend/pyproject.toml` | PASS, both files formatted. An earlier check without the repository's backend config used the tool's 88-column default and reported both files would reformat; the established 100-column repository config passes. |
| `git diff --check` | PASS; existing LF/CRLF notices are non-fatal. |

The first three browser attempts failed in Chromium/Playwright response-body
retrieval, before any offline import commit or analysis mutation. Their reports
remain as `deployment-browser-attempt-1.json` through `-3.json`. The endpoint
returned **200 application/json**, and independent validation accepted the actual
downloaded ZIP (38 events, 21 sources). The corrected operator check captures a
receipt from an in-page fetch clone when DevTools reports
`CHROMIUM_RESPONSE_BODY_UNAVAILABLE`; the actual UI still parses the response and
performs preview/commit. No product or installed artifact changed. Three earlier
unparsed import previews remain bound to those test logins until normal expiry;
their IDs were unavailable, so no unrelated preview was cancelled. Earlier smoke
workspaces were detached, and no global logout was performed. The final attempt
cancelled its four remaining previews. Two HTTP 404s in that attempt are the
UI's ordinary-investigation lookup before its offline fallback, not failed imports.

Personal editing was limited to two newly imported, explicitly labelled private
offline smoke artifacts in `stage3-fixture-a`:

| Owner role | Label | Investigation ID |
|---|---|---|
| Administrator | `[Synthetic deployment smoke Stage 06] administrator` | `95368ba3-3526-4fb7-8f09-d6ca32e291a1` |
| Inspector | `[Synthetic deployment smoke Stage 06] inspector` | `ac9252ec-50ff-48ad-9657-14ef2e00786a` |

Their immutable imported documents and separate personal analysis remain. Notes
were restored to their labelled smoke baseline and created bookmarks removed.
Existing retained captures were read/query/export-only: their workspace,
bookmark and query hashes matched before/after, as did preferences, catalogue,
topology and existing live state. No configured-path check, SSH request,
collection, live start, shared settings write or preference write was issued.

**8444 preservation correction:** deployment preflight found that its backend
container/image/start time were unchanged, but its shared `frontend/dist` mount
already served the final Stage 06 build. Its earlier coding-baseline index hash
was `e746de41035ef97a72e38279767b7cfa5cfb9409c7afcb06dba0b4828117bbfc`;
the as-found deployment hash was
`d1ebf9d3c2e894c140a5e47179e632d915bc2ff4edb42c276e61ae529b0a8803`.
The earlier preservation report preceded that final shared build and cannot
prove unchanged assets throughout all Stage 06 coding. That report is retained
unchanged; the earlier prose above now states its temporal limit. This deployment
neither rebuilt nor restored 8444: its exact as-found assets, container ID, image,
start time, restart count and verified readiness were preserved. This does not
claim that 8444's backend was upgraded to Stage 06.

Changed deployment/support files: `README.md`, `backend/README.md`,
`docs/14_MARIADB.md`, `progress/V3_SLICE_PLAN.md`, this status entry, new
`scripts/audit_stage6_deployment.py` and the explicit installed mode in
`scripts/verify_stage6_preservation.py`; ignored operator scripts, isolated
snapshot, existing local Compose override, protected backup and deployment
evidence. No backend/frontend product implementation changed for deployment.
The exact installed artifact already passed the Stage 06 unit/MariaDB/SFTP and
browser suites recorded above; those broad suites were not rerun for installation.
Actual migration, preservation, transport, security and installed-browser checks
ran instead. Ubuntu/Rocky and offline-release qualification remain later gates.

**Stage 06 is installed locally on 8445. Stop at the Stage 06 gate; next scope is
`prompts/07_INVENTORY_AND_UI.md`, only after separate authorization.**

## 18 October 2026 — Stage 07 inventory and UI acceptance

The user authorized `prompts/07_INVENTORY_AND_UI.md`. Stage 07 was implemented in
source and verified at its stage gate before deployment. The separately
authorized installation is recorded in the following dated entry. Implementation
verification used fresh disposable MariaDB
schemas, a separate cached Linux runner and the generated HTTPS/SFTP fixture on
8449. No production targets, real credentials, remote repositories or external
services were contacted. The IDE-selected account secret was not read or used.

Implemented changes:

- Safe direct INI/extensionless, static YAML, canonical JSON and bounded ZIP
  companion-file parsing, with explicit source order, variable provenance,
  unsupported-input diagnostics and secret omission. No Ansible, plugins,
  uploaded code, external referenced files or SSH commands execute.
- Project/source/upload/owner/auth/revision-bound mapping previews and atomic
  reconciliation. Stable host/process identities survive reimport; descriptions,
  layouts, flows and manual processes remain intact. Missing inventory members
  are reported absent without deletion. Credential/parser/jump mappings remain
  local to the selected system; imports do not establish trust or approvals.
- Private staging, actual-byte/file/depth/time limits, configured lower ceilings,
  expiry/restart cleanup and cancellation. Preview-only cancellation supports
  Back/remapping while full cancellation removes the staged upload.
- The working four-step Administrator wizard, draft parser sample tests with
  exact UTC microseconds and unknown-time diagnostics, existing configured-path
  tests, search/undo shortcuts and focus/keyboard support. Inspector endpoints
  enforce shared-configuration denials independently of visible controls.
- Literal matches in both virtual log viewers use generated Python Unicode
  casefold data and acknowledged filters. Paused rows retain their matching
  context. Marks preserve escaped source text and bounded DOM work; live text
  selection preserves whitespace. Both supplied theme images remain original
  reference assets, implemented through semantic tokens and actual components.

Changed source groups: `backend/src/inspector/{inventory,inventory_parser,
diagnostics}.py`, inventory persistence models, additive `0013_inventory`
migration, app/config/security/schema wiring and generated API definitions;
`InventoryImport`, `ParserTestPanel`, `LogText`, workspace/editor/viewer integration,
shared styles and generated Unicode data/notices; parser/reconciliation/security/
diagnostic/limit/build tests, real MariaDB and populated-upgrade tests, inventory/
UI/browser regression cases; synthetic inventory fixtures and Stage 07 runner,
fixture/build/verification helpers. README, API/import/MariaDB documentation,
traceability, toolchain and progress records describe the implemented scope.

Commands actually run (root; `PY` means `backend/.venv/Scripts/python.exe`):

| Command | Actual result |
|---|---|
| `PY scripts/prepare_stage7_runner.py` | PASS: separate cached/pinned Linux runner built, original runner identity preserved; no dependency changes. |
| `PY scripts/stage7_local.py prepare`, `migrate`, `fixture`, `up`, `configure` | PASS: new synthetic 8449 fixture and schema `inspector_test_s7_web_a24a99fef4`; only generated target key/password/log-root approvals. Earlier draft schema retained. |
| `PY scripts/verify_stage7.py integration --suffix s7_59c5b714` | 168 real MariaDB regression cases passed in 420.37 s. Subsequent focused checks cover final inventory refinements. |
| `PY scripts/verify_stage7.py inventory --suffix s7_fff6e807` | 15 passed in 17.41 s, including lower deployment ceilings, Back/remapping lifecycle and parser-worker logout recheck. |
| `PY scripts/verify_stage7.py inventory --match mid_transaction_failure` | Fresh `s7_87adc442`: 1 passed, 15 deselected in 5.54 s. Failure after real topology/mapping SQL changes rolls back model/history/maps/revision; the same preview then commits successfully. |
| `PY scripts/verify_stage7.py upgrade --suffix s7_upgrade_b2f96b1d` | PASS: populated `0012_offline_analysis` → `0013_inventory`; all 43 existing tables/rows, two accounts/systems, repeated scoped event IDs and captured raw bytes preserved. |
| `PY scripts/verify_stage7.py checks` (initial) | Unit 784 passed/4 platform skips; package 128 run/9 POSIX skips; validators, Ruff, mypy, frontend lint/types/API and artifact check passed. Format check found two helper files; corrected and targeted format check passed. Original results retained under `checks-initial/`. |
| `PY scripts/verify_stage7_linux.py`; `PY scripts/verify_stage7_linux.py --package-only` | Linux units 787 passed/1 Windows-only skip. Initial package harness omitted linked documentation; after correcting source staging, all 128 Linux package cases passed. |
| `PY scripts/frontend.py test` | 10 behavioral/actual React renderer cases passed; generated API check passed. Exact full-Unicode Python parity and build-verifier tests also passed (11 targeted Python cases). |
| `PY scripts/frontend.py e2e inventory.spec.ts` | Initial full wizard run: 10/10 passed, five formats, mapping/conflicts, secret omission, reimport/manual preservation, same-context project isolation and all Inspector route denials. Source-switch regression added afterward. |
| `PY scripts/frontend.py e2e ui_acceptance.spec.ts investigation.spec.ts` | Investigation 4/4, two-subsystem role/theme/size matrix and public loading/login/logout matrix passed. Two live-selection cases caught collapsed whitespace; product CSS fixed, final rerun pending. |
| `PY scripts/frontend.py e2e topology.spec.ts --grep 'administrator builds'` | 1 passed: real create/edit/move/undo/redo/export/import workflow; save acknowledgements awaited before subsequent reads. Separate server/profile setup case also passed. |
| `PY scripts/build_stage7.py`; `PY scripts/verify_stage7_build.py` | Isolated frontend/wheel/sdist build and frozen source/assets verification passed. Final rebuild follows remaining verification refinements. Existing >500 kB frontend chunk warning remains; no build failure. |

Browser commands use only `INSPECTOR_E2E_URL=https://localhost:8449`, the protected
generated Stage 07 account file, and isolated `.state/stage7-build/frontend`
assets. Exact command arrays/cwd/exit results, earlier corrected failures and
screenshots are retained under `verification/stage-7/`. Browser routes reject
external requests. No response mocks provide inventory/log/SSH results.

Corrections found by actual checks include missing inventory permission action
registration; nullable inspected format serialization; preview cancellation
incorrectly discarding the upload needed for remapping; new-source selection
retaining the previous upload; exact parser sample labels; and live whitespace
selection. Test/harness corrections include awaiting completed saves, valid
synthetic paths, inaccessible Chromium upload-response bodies, fresh-schema
container mounts and complete Linux package source staging. Contracts and
production login/collection limits were not relaxed.

The follow-ups below close the focused backend, UI, resource and preservation
checks. Stage 08, native Ubuntu/Rocky installation, full offline-image release
lifecycle and production deployment remain outside this authorization.

Final backend follow-up: `PY scripts/verify_stage7.py inventory` used fresh
`s7_e968b222`: 19 passed and one newly added live-snapshot test failed because it
expected the wrong top-level state. The engine correctly reports
`interrupted / REVISION_CONFLICT` after configuration changes. With that test
checking the actual interruption or continued use of the old captured path,
`PY scripts/verify_stage7.py inventory --match changed_inventory_process_path`
passed in fresh `s7_45bf1803` (1 passed, 19 deselected, 7.36 s). All 20 distinct
focused inventory/diagnostic cases therefore pass across these two final runs
against the same product source. No source change or timeout increase was
needed for the test correction.

Final unit follow-up: Windows **800 passed / 4 platform skips** in 28.36 s.
The temporary package-test source copy initially missed the newly linked `.mjs`
test file; including that real source extension fixed the harness without
weakening validation. `PY -m unittest discover -s tests/package -q` then passed
all 128 cases with 9 POSIX skips in 13.985 s (observed output copied into
`windows-package-targeted.log`). `PY scripts/verify_stage7_linux.py` passed
**803 units / 1 Windows-only skip** in 27.61 s and **all 128 package cases** in
2.475 s. Five existing WebSocket transport deprecation warnings are retained.
The final isolated frontend/wheel/sdist build and frozen artifact check pass.

AT61 began at **00:50:23 UTC** using the existing generated system/account:
60 configured processes on three existing servers, five original approved SFTP
sources, one append/second total, navigation and live filter changes. Separate
app/MariaDB/browser CPU/memory/task/socket observations are recorded under
`soak-7a61b20c3d49.json`. No proxy is present in this direct-ASGI fixture. An
initial proposal to create another persistent Administrator/system was rejected
by automatic approval review; the accepted smaller setup creates neither and
restored the temporary configuration and exact generated log bytes. The
completed measurement and recovery results follow.

Final browser and resource results:

| Command / artifact | Actual result |
|---|---|
| `PY scripts/frontend.py e2e inventory.spec.ts ui_acceptance.spec.ts` | **17/17 passed**, no skips/flaky cases, 200.45 s; `browser-inventory-ui-final.json`. Thirteen inventory cases include all five file paths, stable reimport, conflicts/manual preservation, new-source Back navigation, real pending parse/preview cancellation, late-response isolation, two system windows and every Inspector endpoint denial. |
| `PY scripts/frontend.py e2e ui_acceptance.spec.ts --grep 'visual matrix'` | **2/2 passed**, 1.1 min; `browser-visible-highlight-review.json`. Both roles, themes and desktop sizes bring actual marks into view, measure contrast, select unchanged text, exercise keyboard filters/pause and retain independent five-source windows. |
| `PY scripts/frontend.py e2e ui_acceptance.spec.ts --grep 'two-subsystem reference'` | **1/1 passed**, 6.4 s; `browser-reference-fit-review.json`. The animated fit reaches a readable scale before eight role/theme/size captures. |
| `PY scripts/frontend.py e2e stage7_soak.spec.ts` with `INSPECTOR_E2E_SOAK_RUN=7a61b20c3d49` | Timed workload completed **1,811.677 s**, with 14 actual resource samples and five continuous real monitors. Initial final topology restoration returned 409 because the document carried its old embedded revision. This browser failure remains in `soak-browser-initial-cleanup-failure.*`; it is not reported as a passing browser run. |
| `PY scripts/frontend.py e2e stage7_soak.spec.ts --grep 'restores the completed'` (recovery mode) | **1/1 passed**: current embedded revision used for exact restoration; original configuration content restored at revision 4, only existing generated-root approvals refreshed, exact five log hashes restored. `soak-cleanup-recovery.*` records the actual recovery. |
| `PY scripts/verify_stage7_soak.py analyze --run-id 7a61b20c3d49` | **PASS**: completed measurement, stable resource trends, no reported gaps/reconnects/browser errors, one unchanged WebSocket, and verified restoration. Summary and exact exercised source copies are retained. |
| `PY scripts/stage7_local.py stop`; `PY scripts/verify_stage7_preservation.py` | **PASS**: only the 8449 synthetic browser/SFTP services stopped. Retained 8444/8445 readiness, verified TLS, index hashes, container/image/start/restart identities and original runner tags match their Stage 07 baseline. |

The final UI matrix covers both roles/themes at 1280×720 and 1920×1080,
system/details/menus/dialogs/settings/accounts, sample uploads and safe errors,
real historical/live filters and coverage, empty/loading/login/logout states,
two distinct titled systems, same-system duplicate pages, durable appearance,
unsaved drafts, focus traps, shortcuts, 200% CSS scaling and separate 640×360
responsive reflow. Actual rendered-text/focus reports contain **6,308 checked
text samples, zero contrast failures, and 29 focus measurements with minimum
5.23:1**. There are 257 retained screenshots across final and earlier attempts;
representative final images were inspected directly, including both themes,
selected/matching text, parser samples, inventory preview, compact settings and
the two-subsystem scene. Narrow split panes support horizontal scrolling; the
final captures explicitly bring the matching text into view. The earlier four
investigation browser regressions and complete topology CRUD/server-setup cases
also passed. Evidence is scoped to Chromium on this Windows client.

AT61 actual resource measurements (60 processes on three existing servers):

| Component | Observed memory | Observed CPU |
|---|---|---|
| Linux ASGI application | RSS 120.64 → 125.47 MiB; peak 125.47 MiB | Mean 12.77% of one core |
| Shared local MariaDB test container | 1,017–1,018 MiB, near its existing 1 GiB container ceiling | Samples 1.47–3.46%, mean 2.13% |
| Windows Chromium client | Working set 411.79 → 492.71 MiB; peak 525.65 MiB | Mean 5.42% of one core |
| Proxy | Absent; direct ASGI TLS fixture | No proxy process |

App OS threads/tasks remained 2, descriptors 17–19 and socket descriptors 12–14.
The producer appended 1,811 real records; final capture counted 1,827 including
seed history. App/database container caps total 1.5 GiB, with the measured
host/container budgets recorded separately. This finite baseline demonstrates
the Stage 07 60-process/five-monitor resource check; it does not qualify the
typical 10–20-host deployment, a production proxy, internal asyncio task counts,
native Ubuntu/Rocky installation or the cold offline release. No exactly-once
claim is made for other rotation/truncation scenarios.

Final refinements include working Cancel/Escape during upload/parse/preview,
immediate atomic-commit/double-submit guards, two real late-response cancellation
regressions, and explicit visible focus/highlight assertions. The soak harness
now guarantees writer cleanup, uses run-specific immutable IDs, validates Docker
resource identities and restores using the current revision. An additional
generated JSON receipt was converted from PowerShell UTF-16 to UTF-8 without
changing its data. Repository-configured Ruff/format and frontend lint pass;
the final build and frozen source/wheel/assets check pass. Existing frontend
chunk-size and five upstream WebSocket deprecation warnings remain documented.

Final receipts: `PY .state/stage7-final-checks.py` recorded the exact argv/cwd
and output under `verification/stage-7/final-checks/`. The latest ten checks all
pass: 128 package cases (9 POSIX skips, 17.305 s), package validation, Ruff,
format (163 files), mypy (37 source files), frontend lint/typecheck, 10 Node
behavior/component tests plus generated API consistency, and frozen artifact
verification. The initial diff harness incorrectly disabled Git's repository
CRLF conversion and reported carriage returns as whitespace; that failed
attempt remains separately recorded. The corrected repository-configured
`git -c core.safecrlf=false diff --check` passed. `ui-review.json` records the
representative images actually inspected and their current hashes. No failing
contract was removed or relaxed.

**Stage 07 complete at its review gate. No outstanding Stage 07 blocker.**
At that gate Stage 06 remained installed on 8445; no deployment was performed
by implementation verification. The subsequent explicit deployment authorization
and actual upgrade are recorded below. Stage 08 remains a separate scope.

## 18 October 2026 — Stage 07 deployed to the retained local application

Authorization: "Deploy stage 7." Upgraded only **https://localhost:8445**
(`runtime-stage3`, database `inspector_test_s3_web_317d3a3c4a`) from
`0012_offline_analysis` to **`0013_inventory`**. The isolated tested backend is
mounted read-only from `.state/stage7-install/backend`. Installed wheel SHA-256:
`908c3befbd0053da388c8d14916e7e40ff12efb99b2ff8d43fe1296cdb63c729`.
The pinned runtime image remains
`sha256:668bfc011a595c63ea4f88c29eea56c326828662dbba1cd20a18a4eacdfcd8a8`.
No dependency download, image pull, frontend rebuild, production/target-host
connection, repository push or Stage 08 release operation occurred.

Preflight verified zero active collections, live sessions and subscriptions.
Only 8445 was stopped. A consistent protected recovery point is retained under
`.secrets/stage7-install/pre-0013-inventory/`: SQL dump, raw-cache archive,
byte/hash/ownership manifests, exact previous Compose/application files,
previous backend and wrapper scripts, and a protected vault copy. The SQL dump
is **194,617,923 compressed bytes**, SHA-256
`e1996fc835f358471215d3e4926ea4872d75d12490ccd7adb83e7f4d1b180f80`.
It contains no database creation/selection statements. Cache archive SHA-256:
`54843615c24bb079ae05708c86ee0fd5f5e509589138e243878499882e15819a`.
Both archives and vault copy were checked before migration. Prior recovery
points remain intact. The matching written recovery procedure is
`.cache/stage7-rollback.txt`; no rollback/restore drill is claimed.

The stopped-service migration added exactly five empty inventory tables.
**All 44 old table counts and 43 non-Alembic checksums matched before startup.**
Post-start checks preserve all 34 stable table counts/checksums, original
configuration/vault, **897 cache files / 230,864,349 bytes**, and **957 directory/
file ownership and mode entries**. Normal startup authentication/workspace/job
recovery tables were checked separately. All 62 packaged runtime/migration/web
files and 40 runtime files match the validated wheel/frozen build. Three served
assets match over certificate-and-hostname-verified HTTPS. The two Python/Unicode
notices are verified in the installed bundle; this frozen app has no HTTP
license route. Runtime remains UID/GID 10001, read-only root, dropped capabilities,
one ASGI worker and DML-only database grants, without root/migration secret mounts.

Commands actually run (repository root; `PY` is
`backend/.venv/Scripts/python.exe`; Docker operations used approved local access):

| Command/check | Actual result |
|---|---|
| `PY scripts/verify_stage7_build.py --output verification/stage-7/deployment-build-verification.json` | PASS: all 106 frozen runtime/build inputs, wheel and bundled assets correspond; no rebuild. |
| `PY .cache/install_stage7.py prepare` | PASS: separate installation snapshot from the tested wheel; existing image/lock/wrapper and 8444 baseline verified. `deployment-prepared.json`. |
| `PY scripts/audit_stage7_deployment.py pre` | PASS: verified TLS readiness, no active collection/live work, restricted runtime grants, actual unauthenticated WebSocket 403 and retained identities. `deployment-audit-pre.json`. |
| `PY .cache/install_stage7.py backup`, then `seal` | PASS: only 8445 stopped; complete protected recovery point and independent archive/vault hash recheck. `deployment-backup.json`, `deployment-backup-verified.json`. |
| `PY .cache/install_stage7.py migrate` | PASS: `0012_offline_analysis` → `0013_inventory`; all 44 old counts / 43 data checksums unchanged; five new empty tables. `deployment-migration.json`. |
| `PY .cache/install_stage7.py start`, then `verify` | PASS: only `up --detach --no-deps runtime-stage3`; verified TLS/readiness 200, exact installed modules/assets, stable tables, cache hashes/permissions and 8444 preservation. `deployment-installation.json`. |
| `PY scripts/audit_stage7_deployment.py post` | Final PASS: exact wheel membership/runtime sources, separated migration/runtime grants, TLS/WS boundaries, 8444 assets/identity and stopped Stage 05/06/07 fixtures. Initial audit-layout error and correction are recorded below. `deployment-audit-post.json`. |
| `.toolchains/node-v24.22.0-win-x64/node.exe --check .cache/verify_stage7_install.mjs`, then that executable without `--check` | Syntax PASS; final installed browser PASS in **8.628 s**, both roles/themes at 1440×1000. Actual assets/notices, retained queries/highlights, same-context duplicate/different-system pages, draft parser known/unknown/limit diagnostics, inventory source draft/cancel and Inspector HTTP denials. All six new workspaces detached; no external/forbidden/WebSocket requests or page errors. `deployment-browser.json` records exact argv/helper SHA and ten screenshot hashes. |
| `PY scripts/audit_stage7_deployment.py post-browser` | PASS: **53 history jobs, two terminal live sessions and 47 target-action audit rows** unchanged from preflight; zero active collections/live sessions/subscriptions. TLS readiness 200, unauthenticated WebSocket 403, runtime and 8444 preservation pass. `deployment-audit-post-browser.json`. |
| Independent installed UI review | Root viewed the final Administrator light parser diagnostics, Administrator dark inventory wizard and Inspector dark literal-highlight screenshots. Text/actions are readable, inventory target and focus are visible, parser results scroll within the dialog. `deployment-ui-review.json`. |
| `PY .cache/finalize_stage7_deployment.py` | PASS: package validation, repository-configured audit Ruff/format, browser-helper Node syntax, frozen source/wheel correspondence and `git -c core.safecrlf=false diff --check`. All six exact commands/exit codes/logs are retained under `deployment-final-checks/`; `deployment-final-build-verification.json` still matches the tested artifact. |

Installed-browser verification used existing protected synthetic accounts
internally, without printing passwords, cookies or tokens or changing credentials.
Personal preferences, shared bootstrap settings, catalogue/topology in both
systems, retained investigation workspace/bookmarks/query results and live state
match before/after. Theme captures use page-local DOM overrides. No collection,
live start, configured-path check, SSH, import commit, inventory source creation,
shared settings change or global logout was issued. The installed inventory has
no source yet, so the smoke tests its source-name draft/cancel without creating
shared data. Actual file upload/preview/commit/reimport remain covered by the
completed isolated Stage 07 suite against this exact artifact.

Original failed operator checks are retained, not reported as passes:

- The first independent post audit compared the pre-wheel source tree with the
  extracted wheel, which also contains Hatch's force-included migrations and
  Alembic configuration. It now checks exact wheel membership plus separate
  runtime/migration correspondence, rejecting missing/extra files.
  `deployment-audit-post-attempt-1.json` records the original failure.
- The first browser attempt assumed an absent `stage3-fixture-b`. The helper
  now chooses another existing active catalogue system and tracks its exact
  workspace scope. The second attempt read parsers from the intentionally
  redacted Inspector projection; the valid 403 request now reuses the already
  validated Administrator draft in memory. Both failed reports/screenshots are
  retained as `deployment-browser-attempt-1.json` / `-2.json`; all their newly
  created workspaces detached. The product and installed artifact did not change.
- Verification initially expected the bundled license files to have HTTP routes.
  Static review corrected that check before startup: distribution hashes are
  checked on disk; served page/JS/CSS hashes are checked over HTTPS.

Changed deployment/support files: new `scripts/audit_stage7_deployment.py`,
README/backend setup, MariaDB/traceability documentation, slice plan and this
status; ignored guarded operator/browser helpers, isolated installed snapshot,
the existing local Compose override, protected backups and verification receipts.
No backend/frontend product implementation or dependency lock changed for this
deployment. Broad unit/MariaDB/browser suites already passed for the frozen
artifact; installation-specific migration, data, transport and browser checks
ran here. Native Ubuntu/Rocky installation, complete recovery drill, proxy and
offline release qualification remain Stage 08 work.

**Stage 07 is installed locally on 8445. Stop at this gate. Stage 08 has not
started and requires its separate scope authorization.**

## 18 October 2026 — Separate shared Settings from account Preferences

User-authorized UI follow-up: both Administrator and Inspector now open
**Preferences** by clicking the logged-in user and choosing Preferences.
Personal Appearance retains automatic persistence, Application default,
Light, Dark and System modes, account-wide propagation and explicit error/Retry.
**Settings** is visible/renderable only for Administrators and contains shared
application settings, including the default used by new accounts and signed-out
screens. Explicit personal themes stay unchanged. The existing MariaDB-backed
preferences/settings endpoints, permission checks and schema are unchanged.

Opening an account dialog closes the user menu; closing the dialog restores
keyboard focus to its trigger. Public bootstrap refresh now runs independently
of protected preference loading, so a mounted signed-out page can receive the
updated default without a failing personal-preferences request. Ending a session
also refreshes the safe public default. No workspace remount or selection change
was added.

Changed product files: `frontend/src/App.tsx` and
`frontend/src/components/Management.tsx`. Browser helpers/callers were updated in
`frontend/e2e/ui.ts`, `foundation.spec.ts`, `topology.spec.ts`, `ssh.spec.ts` and
`ui_acceptance.spec.ts`; new `preferences.spec.ts` covers this separation.
README, UI/access-control documentation, requirement traceability and this status
record the new entry points (R38/R39/R41; AT67/AT70/AT71). Existing unrelated Stage
07 work was preserved.

Verification (repository root; `PY` = `backend/.venv/Scripts/python.exe`):

| Command/check | Actual result |
|---|---|
| `PY scripts/frontend.py build --outDir C:/_Projects/system-monitor/.state/preferences-build/frontend --emptyOutDir` | PASS: isolated production frontend build, leaving installed/frozen release assets unchanged. Existing chunk-size warning remains. |
| `PY scripts/frontend.py lint`; `PY scripts/frontend.py typecheck` | Final PASS. Interim checks during test edits found an incomplete statement and a narrowed nullable test variable; both corrected before browser verification. |
| `PY scripts/frontend.py test` | PASS: generated API consistency and all 10 existing Node behavior/component tests. |
| `PY scripts/frontend.py e2e preferences.spec.ts` | Final **4/4 passed, 10.0 s**. Both roles, keyboard/menu/modal focus, Light/Dark at 1280×720 and 1920×1080, reload persistence, System mode, no admin requests from personal Preferences, real 409/retry, independent accounts, a genuinely new Inspector inheriting the default, mounted signed-out broadcasts and account-wide logout. Receipt: `verification/stage-7/preferences-browser.json`. |
| Initial same browser command | **2 passed / 2 failed**, retained in `preferences-browser-attempt-1.json`. Exact wrapping-label lookup included the select's option text. Tests now use the exact combobox role/accessibility name and retain named-dialog assertions; no contract/product accessibility was weakened. |
| Rendered UI review | Viewed `administrator-shared-settings-separated.png` (dark, 1920×1080) and `inspector-light-1280-personal-preferences.png`: readable controls and clear separation; screenshots reside in `verification/stage-7/screenshots/`. |
| `git -c core.safecrlf=false diff --check` | PASS across the working tree. |

Browser verification used only the existing synthetic Stage 07 MariaDB fixture
on **8449**, protected generated test accounts and the isolated fresh frontend
through the test asset-routing helper. Only its previously stopped
`stage7-browser` backend was started, then stopped again; SFTP stayed stopped.
Shared settings and existing personal appearance values were restored; the
generated new test Inspector was disabled, retaining its audit history. No
collection, SSH, inventory commit, migration, real credential, installed service
update or deployment was performed. Broader inventory/live/release suites were
not rerun for this UI-only follow-up. Stage 08 remains the next separate scope;
this preferences change is source-only and is not installed on 8445.

## 18 October 2026 — Preferences/Settings follow-up deployed locally

Authorization: user requested **"DEploy."** after reviewing the completed UI
change. The tested follow-up is now installed at **https://localhost:8445**.
Personal Appearance is under the logged-in user menu → Preferences for both
roles; shared Settings is Administrator-only. Refresh an existing browser page
to load the new frontend.

Deployment changes only `runtime-stage3`: a separate frozen read-only frontend
overlay at `.state/preferences-install/frontend` is mounted onto
`/workspace/backend/src/inspector/web`. The pinned runtime image, original
`.state/stage7-install/backend`, its wheel, scripts, configuration, secret mounts
and **`0013_inventory`** schema are unchanged. There was no migration, preference
backfill, image/package download or backend replacement. The rebuilt frontend
matches the four-test browser-verified build byte for byte. Its JS is
`assets/index-USN31lFM.js`; the previous hashed JS remains available for pages
which loaded the old index. Overlay manifest SHA-256 is
`ce6e7cb047c86f2f516b9b20eb5091707261a08bc4e4bbf48f60e90a1552ca16`.

Rollback retains the original frontend/backend/wheel in place and the exact
previous Compose file in `.secrets/preferences-install/previous-compose.yaml`.
`.state/preferences-install/ROLLBACK.txt` describes removing only this overlay
and recreating only 8445. The earlier Stage 07 SQL/cache recovery point remains
intact. No new database restore or full release operation is needed for this
asset-only change; rollback was prepared but not exercised.

Commands actually run from repository root (`PY` =
`backend/.venv/Scripts/python.exe`; `NODE` =
`.toolchains/node-v24.22.0-win-x64/node.exe`):

| Command/check | Actual result |
|---|---|
| `PY scripts/frontend.py build --outDir C:/_Projects/system-monitor/.state/preferences-deploy-check/frontend --emptyOutDir` | PASS; exact five-file equality with the previously tested `.state/preferences-build/frontend`. Existing chunk-size warning only. |
| `PY -m py_compile .cache/deploy_preferences.py`; `NODE --check .cache/verify_preferences_install.mjs` | PASS: guarded deployment and installed-browser helper syntax. |
| `PY .cache/deploy_preferences.py prepare` | PASS: verified TLS, DML-only runtime grants, zero active collections/live sessions/subscriptions, original package integrity, database/cache fingerprints, other-application identity/assets and protected Compose rollback snapshot. `preferences-deployment-prepared.json`. |
| `PY .cache/deploy_preferences.py deploy` | PASS: stopped only `runtime-stage3`, changed only its frontend mount, then `up --detach --no-deps runtime-stage3`. Ready with the exact overlay assets, original data/cache/backend/scripts and 8444 application intact. Automatic rollback was not needed. `preferences-deployment-installed.json`. |
| `NODE .cache/verify_preferences_install.mjs` | **PASS, 3.411 s**: actual installed assets without test substitution, both roles/themes at 1280×720, user menu, native modal focus/Escape, personal/shared separation, Inspector absence of Settings and HTTP 403, unchanged saved preferences/shared defaults/catalogue. Ten screenshot hashes retained in `preferences-deployment-browser.json`. |
| `PY .cache/deploy_preferences.py verify` | PASS after browser smoke: **44 stable table counts/checksums** and complete table set preserved; all **897 cache files / 230,864,349 bytes** plus 956 descendant ownership/mode entries preserved; original backend/wheel/scripts/configuration/vault unchanged. Certificate-and-hostname-verified readiness/assets, one restricted ASGI worker and unauthenticated WebSocket 403 pass. `preferences-deployment-verified.json`. |
| Installed UI inspection | Root viewed installed Administrator light Settings and Inspector dark Preferences: readable controls, clear separation and visible focus. Captures are under `verification/stage-7/preferences-deployment-screenshots/20261018T093600660Z/`. |
| `git -c core.safecrlf=false diff --check` | PASS. |

As-found operational counts remain **53 history jobs, three terminal live
sessions and 48 target-action audit rows**, with zero active work. Runtime stays
UID/GID 10001, read-only root, all capabilities dropped, one ASGI worker and
DML-only database grants; no root/migration secret is mounted. The 8444
application's container identity/image/start/restart count and all its served
assets match preflight. Test backend/SFTP services were not started.

Installed-browser verification used the protected generated local test accounts
without printing passwords/cookies/tokens. It made two logins and read-only
requests; stored preferences/defaults were not changed, no workspace was created,
and no logout, target/SSH/collection, inventory or other non-login write request
was issued. Theme screenshots use temporary DOM overrides. Authentication/audit
rows created by those logins are intentionally separate from the stable-table
comparison. No production host, repository push or Stage 08 release work occurred.

Updated documentation: README, backend setup, MariaDB/traceability docs, slice
plan and this status. Ignored operator helpers and immutable overlay/recovery/
verification files retain the deployment details. **The Preferences/Settings
follow-up is deployed; Stage 08 remains the next separately authorized scope.**

## 18 October 2026 — English/Polish application and personal language

User authorization: “Add support to Polish language. Add default language to
settings and individual selection to profile.” This is a separate source
follow-up to Stage 07, with no installation or Stage 08 authorization.

Administrators now choose **Settings → Application default language** (English
or Polski). Both roles choose **user menu → Preferences → Language** (English,
Polski or Application default). English remains the initial shared default.
The signed-out screen, genuinely new accounts and accounts following the default
use the shared choice. Explicit personal choices remain independent. Language
and appearance persist separately in MariaDB with revision checks, strict
partial updates, CSRF/RBAC enforcement and visible conflict/retry. Concurrent
personal controls are serialized, including authentication-boundary handling.

Bundled Polish catalogues cover navigation, accounts, preferences/settings,
topology/editing, imports, SSH/access, parser diagnostics, historical/live viewers,
investigation tools, UTC controls and common error messages. Document language
and accessible labels update at runtime. Names, IDs, UTC values, Markdown,
uploaded documentation and original log text remain data. Account broadcasts
update language without replacing page workspaces or changing independent search,
selection, queries or controls. Review found that split historical panes rebuilt
filtered arrays on rerender; memoized process arrays now preserve scroll anchors
when language changes. A browser regression verifies the retained query, original
row text and scroll position with no new query, workspace or capture request.

Additive migration **`0014_languages`** adds checked ASCII `default_language` and
personal `language` columns with `en` / `default` backfills. It preserves existing
preferences, settings, revisions and all other data. Optional deployment
`bootstrap_settings.default_language` initializes only a new settings row.
The populated MariaDB upgrade preserves all 48 original tables/rows and checks
constraints, downgrade and reupgrade. The serving application still receives no
migration credentials; future installation requires stopped serving plus matched
backend/frontend and migration.

Changed files:

- Backend: `config.py`, `database.py`, `foundation.py`, persistence models and
  bundled deployment schema; new `migrations/versions/0014_languages.py`;
  OpenAPI, preference/deployment contracts and examples.
- Frontend: `src/i18n/` translator/provider and four Polish catalogues;
  `App.tsx`, generated API schema, and the existing account/catalogue/common,
  topology/configuration/access/import/parser, history/live/investigation,
  UTC/log/Markdown components. No dependency or lockfile change was needed.
- Tests: new `frontend/tests/i18n.test.mjs`, `e2e/language.spec.ts`, updated
  preference conflict assertion and npm test command; new backend language
  unit/API/migration tests, existing config/API tests and original-schema
  migration fixtures; new `scripts/verify_languages.py`.
- Documentation: README/backend setup, requirements, domain/API/UI, roles,
  MariaDB/workspaces, traceability, slice plan and this status.

Commands actually run (`PY` = `backend/.venv/Scripts/python.exe`):

| Command/check | Actual result |
|---|---|
| `PY -m pytest backend/tests/unit -q -rs` (also captured as `verification/language-support/backend-unit.log`) | **817 passed / 4 skipped**, 30.56 s. Skips: two Windows symlink privilege cases, Windows rename of a pinned synthetic file, and Linux-only POSIX permissions. |
| `PY -m pytest backend/tests/unit/test_language_contract.py -q` | **16 passed** after final OpenAPI metadata refinement. |
| `PY scripts/verify_languages.py integration` | **13 passed**, 26.34 s, real disposable MariaDB/API/security tests including ownership, partial updates, invalid/null/empty/mass assignment, CSRF, shared-default permissions, fresh initialization/restart and unchanged workspace scope. Final receipt `verification/language-support/lang_3c8dfa-command.json` and `.log`; earlier passing run retained. |
| `PY scripts/verify_languages.py upgrade` | PASS: populated `0013_inventory` → `0014_languages`; **48 original tables and rows preserved**, language constraints, downgrade/reupgrade. `lang_upgrade_5fc4d6-command.json` / `.log`. |
| `PY -m ruff check --config backend/pyproject.toml backend/src backend/tests backend/migrations scripts`; corresponding `ruff format --check` | PASS; 169 files already formatted. |
| From `backend/`: `.venv/Scripts/python.exe -m mypy src` | PASS: 37 source files. |
| `PY tools/validate_schemas.py`; `PY tools/validate_deployment_examples.py` | PASS: 102 positive/36 negative schema validations; 44 deployment checks. |
| `PY -m inspector.cli openapi --output backend/openapi.json` with `INSPECTOR_CONFIG_FILE=examples/deployment-policy.example.yaml`; `PY scripts/frontend.py api:generate` | PASS; generated types match the final OpenAPI. |
| `PY scripts/frontend.py lint`; `PY scripts/frontend.py typecheck` | Final PASS across frontend/e2e. Interim automated-translation typing mistakes were corrected before final build/browser verification. |
| `PY scripts/frontend.py test` | **14 passed**: API type consistency, language resolution, safe interpolation/whitespace/fallback, bundled key/placeholder coverage and existing literal/log-rendering behavior. |
| `PY scripts/frontend.py build --outDir C:/_Projects/system-monitor/.state/language-build/frontend --emptyOutDir` | PASS: isolated production build, final JS `index-DoJrT-Rf.js`. Existing Vite chunk-size warning remains; installed assets were not changed. |
| `PY scripts/frontend.py e2e language.spec.ts preferences.spec.ts inventory.spec.ts` | **22/22 passed**, 196.54 s. Real synthetic 8449 backend/MariaDB and fresh local assets; both roles/themes at 1280×720 and 1920×1080; same-context independent windows, persistence, new-account/default inheritance, mounted signed-out broadcasts, real conflict/retry, split-log scrolling, appearance regressions and all 13 inventory cases. Report: `verification/stage-7/language-browser-final.json`. Real login limits returned 429 twice; each existing helper waited 60 seconds for one bounded retry. No limit was relaxed. |
| `PY tools/validate_package.py`; `PY -m unittest discover -s tests/package -q` (later `-v` to record skip reasons) | Package validator PASS; **128 tests run / 9 skipped**, no failures. All nine skips require POSIX secret-file permissions/shell behavior unavailable on Windows. Package checks do not prove release qualification. |
| Rendered UI inspection | Viewed Polish dark 1280 Preferences, light 1920 Preferences, shared Settings, signed-out login and scrolled split history. Readable translations, original log rows and accessible controls. Screenshots: `verification/language-support/screenshots/`. |
| `git -c core.safecrlf=false diff --check` | PASS. |

Original failed attempts remain explicit. The first browser run could not read
the protected synthetic account fixture under the sandbox (EPERM); the authorized
local test run used escalation without exposing credentials. Its second run
passed 7/8, with a test capturing the temporary “Unavailable” workspace placeholder;
it now waits for an actual server-issued UUID. The third run passed 8/9; the new
scroll test unnecessarily required a collection of 40 events despite needing eight
rows in one process. Correcting candidate selection retained that row requirement;
the focused real-data test then passed, followed by the complete **22/22** run.
Reports `language-browser-attempt-1/2/3.json` and
`language-history-attempt-1.json` are retained under `verification/stage-7/`.
These test fixes did not relax product contracts.

The existing synthetic 8449 schema alone was migrated and started using
`scripts/stage7_local.py migrate`, `up` and `stop-sftp`; after verification,
`scripts/stage7_local.py stop` passed and stopped both fixture services. Docker's
local named pipe initially returned sandbox Access denied, then the authorized
isolated commands succeeded with escalation. Browser tests restored existing
personal/shared settings and disabled newly generated test accounts. Inventory
tests use their established synthetic fixture systems. The browser language
checks start no collection/SSH/live session and the scroll check uses retained
synthetic data. The separate backend security integration still uses its local
test SFTP server. No production target, installed service, real credential,
repository push or deployment was involved.

**English/Polish support is implemented and verified in source. It is not
installed on 8445.** Active-live language switching and native Ubuntu/Rocky/offline
release qualification were not run as part of this follow-up. Retained-log state
and workspace preservation were checked as described above; static live UI
translations were compiled and typechecked. The next numbered scope remains
`prompts/08_OFFLINE_RELEASE.md`, separately authorized.

## 18 October 2026 — Language migration and application deployed locally

Authorization: user requested **“Install the migration, deploy.”** The matching
English/Polish frontend and backend are now installed at
**https://localhost:8445**, using **`0014_languages`**. Refresh existing pages to
load the new frontend. Administrators set the shared language in Settings; both
roles set their own language in user menu → Preferences. The shared default
remains English; personal languages initially follow Application default.
Existing appearance, security policy and other shared settings were preserved.

The frozen package was rebuilt independently, comparing all five new frontend
files byte for byte with the **22/22 browser-verified** source build. The new
wheel SHA-256 is
`84cc9889199138d76b6e3d63bc4ccf062e4ebe3fe95b64f8ba21adda8662387e`.
All 68 extracted wheel members, migration copies and bundled assets were checked;
the backend resides at `.state/language-install/backend`, with unchanged copied
startup scripts in `.state/language-install/scripts`. The original Stage 07
backend/wheel and Preferences overlay remain intact. Both earlier hashed JS
files are bundled for already-open pages; the new JS is `index-DoJrT-Rf.js`.
The old overlay mount was removed so it cannot hide the new language frontend.
No dependency, runner image, package/image download or external service changed.

Preflight checked verified TLS/readiness, strict runtime grants/security, old
artifacts, exact target database, zero active capture/live/subscription work and
the other 8444 application's container/image/start/restart/assets. Only
`runtime-stage3` was stopped. The protected, consistent pre-migration backup is
under `.secrets/language-install/pre-0014-languages/`: complete SQL, raw cache,
current Compose/configuration, vault key and verified copies of the old
backend/scripts/overlay. The SQL dump is **194,624,576 compressed bytes /
1,314,541,450 uncompressed bytes**, with no database-selection statements.
The cache holds **897 files / 230,864,349 bytes**, with 957 archive ownership/mode
entries including the root. Both gzip/archive integrity and checksums passed.

The one-shot migration ran with separate migration credentials and serving
stopped. It preserved all **49 table counts**, **46 unchanged-table checksums**,
and all original columns of the shared settings row and two personal preference
rows. It created only the two intended language columns and their checked
English/default backfills. After startup and browser smoke, **41 stable table
counts/checksums** still match; settings/preference values also match through
explicit old-column checks. The two synthetic smoke accounts each gained exactly
three preference revisions for English → Polish → original-default validation;
their original language and theme values were restored. All original cache bytes
and 956 descendant ownership/mode entries, original scripts, configuration and
vault matched after startup and smoke.

Commands actually run from the repository root (`PY` =
`backend/.venv/Scripts/python.exe`; `NODE` =
`.toolchains/node-v24.22.0-win-x64/node.exe`):

| Command/check | Actual result |
|---|---|
| `PY .cache/build_languages.py` | PASS: isolated rebuild at `.state/language-deploy-check/frontend`, exact tested-asset match, frozen wheel/extraction and migration/script/lock verification. `verification/language-support/deployment-package.json`. Existing Vite chunk-size warning only. |
| `PY -m py_compile .cache/deploy_languages.py`; `NODE --check .cache/verify_languages_install.mjs` | PASS. Initial unqualified `node --check` was unavailable on PATH; the recorded pinned executable passed. |
| `PY .cache/deploy_languages.py preflight` | PASS: reviewed target scope, safe runtime, old/new package and candidate Compose, protected rollback context, no active work and preserved 8444 baseline. `deployment-preflight.json`. |
| `PY .cache/deploy_languages.py backup` | PASS: stopped only 8445, verified consistent SQL/cache and complete matched recovery point. `deployment-backup.json`. |
| `PY .cache/deploy_languages.py migrate` | PASS: **`0013_inventory` → `0014_languages`**, counts/checksums/projections/defaults/constraints preserved or added exactly as intended. `deployment-migration.json`. |
| `PY .cache/deploy_languages.py start` | PASS: only `runtime-stage3` recreated, matching frozen backend/frontend without old overlay; verified TLS/readiness, grants, assets, modules, data/cache and unchanged 8444. `deployment-installed.json`. |
| `NODE .cache/verify_languages_install.mjs` | **PASS, 7.573 s**: actual served asset hashes with no substitution, both roles/languages/themes, same-context duplicate broadcasts/reload, Administrator shared language select, Inspector absence/403 and restored preference values. Exactly **two logins / six personal-language PATCHes**; zero emergency restores, external requests, page errors, workspaces, target actions or WebSockets. `deployment-browser.json` plus twelve screenshot hashes. |
| `PY .cache/deploy_languages.py finish` | PASS: post-smoke data/cache/configuration/vault and original-artifact preservation, exact allowed synthetic preference revisions, safe runtime/modules/assets and untouched 8444. `deployment-verified.json`. |
| Installed UI inspection | Root viewed Administrator Polish dark Settings with `0014_languages` diagnostics and Inspector Polish light Preferences; independent agent also viewed English and dark/light personal screens. Readable controls, diacritics and focus. Captures: `verification/language-support/deployment-screenshots/20261018T102644018Z/`. |
| `git -c core.safecrlf=false diff --check` | PASS. |

The pinned runtime image is unchanged. It remains UID/GID 10001, one restricted
ASGI worker, read-only root, all capabilities dropped and DML-only database
grants; no root/migration credential or Docker socket is mounted. Operational
counts remain **53 history jobs, three terminal live sessions and 48 target-action
audit rows**, with zero active capture/live subscriptions. Browser smoke changed
only the generated accounts' own language preference temporarily; shared settings,
catalogue and stored theme values stayed unchanged. No logout/revocation,
workspace/collection/live start, SSH, import, production-target operation,
repository push or other installed application change was performed.

Rollback preparation is documented in `.state/language-install/ROLLBACK.txt` and
retains the matched pre-0014 database/cache/configuration/vault/backend/overlay.
A restore must revoke restored web sessions before exposure. Old code must not
run against `0014_languages`. Rollback/full restore was prepared, **not exercised**;
the deployment required no recovery. Source unit/API/MariaDB/browser suites had
already passed for this exact artifact and were not rerun wholesale for this
installation; the deployment-specific checks above ran here. No implementation
feature or dependency changed during deployment. Native Ubuntu/Rocky installation,
cold offline lifecycle and Stage 08 qualification remain separate work.

**The language migration and matching application are deployed and verified on
8445. Stage 08 remains the next separately authorized scope.**

## 18 October 2026 — Compact event table and consistent UTC presentation

Authorization: user requested `%Y-%m-%d %H:%M:%S` timestamps, full-screen
historical results, a small context eye, compact terminal-like rows and column
management. Implemented in source; no deployment or migration was performed.

Changed files and behaviour:

- `frontend/src/utcDateTime.ts` centralizes second-precision UTC display.
  Historical/live rows, applied bounds, trace metadata, parser-normalized
  results, observed coverage and bundle/inventory/approval expiry use it. Exact
  API/storage microseconds, original timestamp evidence, raw/context text and
  downloadable document data are preserved.
- `HistoricalViewer.tsx`, `Common.tsx` and `styles.css` implement 20-pixel
  unwrapped monospace rows with minimal padding and a 12-pixel context eye.
  Columns toggles UTC time, process and host independently; Show all columns
  restores them. Log content/context remain available when metadata is hidden.
  Choices apply to all merged/split results in that page only.
- Full screen maximizes the existing results DOM within the browser using a
  native modal dialog; Exit/Escape restores inline results, focus and scroll.
  Context opens above it and returns to the eye. Query/context failures stay
  visible in the active modal. Presentation changes trigger no query/capture.
- Other updated consumers: `BundleTransfer.tsx`, `ConnectionAccess.tsx`,
  `InventoryImport.tsx`, `InvestigationTools.tsx`, `LiveViewer.tsx` and
  `ParserTestPanel.tsx`. New controls have offline Polish translations in
  `investigation.pl.ts`. Updated `frontend/README.md`, `docs/06_UI_UX.md` and
  `docs/12_TRACEABILITY.md` (R17/R18/R31/R34/R49).
- Added `frontend/tests/utc-date-time.test.mjs` and
  `frontend/e2e/events_table.spec.ts`. Browser tests use actual isolated Stage 07
  MariaDB/SFTP fixtures on 8449. One explicit next-query HTTP 503 mock checks
  full-screen error feedback. Final tests restore the synthetic account's theme
  present at test start and log out.

Commands actually run from the repository root (`PY` =
`backend/.venv/Scripts/python.exe`):

| Command/check | Actual result |
|---|---|
| `PY scripts/frontend.py test` | PASS: generated API consistency and **17/17** Node tests, including UTC truncation without rounding, exact-bound preservation, timezone independence and negative epoch microseconds. |
| `PY scripts/frontend.py lint` | PASS: all frontend sources/tests, zero warnings. |
| `PY scripts/frontend.py typecheck` | PASS; build also typechecks. |
| `PY scripts/frontend.py build` | PASS: 214 modules, bundled local assets. Existing Vite chunk-size advisory only. Rebuilt after review fixes for coverage formatting and modal error visibility. |
| `PY scripts/stage7_local.py up` | Initial sandbox failure; read-only Docker check confirmed named-pipe Access denied. The isolated start passed with reviewed escalation. No installed 8444/8445 service was targeted. |
| `PY scripts/frontend.py e2e events_table.spec.ts` | **PASS: 2/2 in 11.0 s**, no skips. Environment: `INSPECTOR_E2E_URL=https://localhost:8449`, protected `.secrets/stage7-browser/accounts.json`, report name `events-table-browser-final`. |
| UI inspection | Viewed actual dark 1280 full screen, light 640 full screen, Columns with all optional columns hidden, and full-screen query error. Eight captures: `verification/stage-7/screenshots/events-table-*.png`. |
| `PY scripts/stage7_local.py stop` | PASS with reviewed escalation; stopped both isolated fixture services, preserving their data. |
| `git -c core.safecrlf=false diff --check` | PASS. |

The browser cases verify raw context preservation, eye/row sizing, each optional
column and restore, no query/capture from presentation controls, nested-dialog
Escape/focus, retained scroll, both themes at 1280×720 / 1920×1080 / 640×720,
visible failed-query feedback, five split panes and same-context same-system
page independence. Browser attempt 1 failed before login because the sandbox
could not read generated accounts (`EPERM`); reviewed escalation resolved it.
Attempt 2 passed **2/2 in 11.2 s**. Final run added cleanup, restore-button and
error assertions without weakening earlier checks. Reports remain
`verification/stage-7/events-table-browser-attempt-1.json`,
`events-table-browser-attempt-2.json` and `events-table-browser-final.json`.

No real credentials or production target were used; non-origin browser requests
were blocked. Backend source, dependencies, schema and installed applications
are unchanged. Full backend/release suites were not rerun for this frontend-only
follow-up. No remaining blocker for this UI request. Next numbered scope remains
`prompts/08_OFFLINE_RELEASE.md`, separately authorized.

## 18 October 2026 — Events-table UI deployed locally

Authorization: user requested **“Deploy.”** The timestamp/compact-events-table
update above is installed and verified at **https://localhost:8445**. Refresh
existing pages to load it. Backend and schema remain **`0014_languages`**; no
migration, dependency change, image rebuild/pull or target connection occurred.
This deployment does not advance Stage 08.

The immutable frontend is `.state/events-table-install/frontend`, mounted
read-only at `/workspace/backend/src/inspector/web`. Its new JS/CSS are
`index-py9wcUsc.js` and `index-6JMvSv8j.css`. An isolated rebuild matched the
browser-verified `frontend/dist` byte for byte. The three older JS generations
and earlier CSS remain available for open pages. The original language
backend, wheel, scripts and bundled frontend remain unchanged. Only the
8445 `runtime-stage3` service was stopped/recreated with `--no-deps --pull never`;
the other installed application on 8444 retains its container/image/start time,
restart count and served assets.

Preflight confirmed zero active history/live work or subscriptions. Both
post-install and post-browser checks preserve all **44 stable table counts and
checksums**, including users/settings/preferences and schema, all **897 cached
files / 230,864,349 bytes**, cache ownership/mode metadata, backend/scripts,
configuration and vault. Operational totals remain **53 history jobs, three
terminal live sessions and 48 target-action audit rows**, with no active capture.
Runtime remains UID/GID 10001, one ASGI worker, read-only root, no capabilities,
DML-only database grants and no migration/root secret or Docker socket mount.
Verified TLS/readiness and actual current/older frontend asset hashes pass;
unauthenticated WebSocket access still returns 403.

Commands actually run from the repository root (`PY` =
`backend/.venv/Scripts/python.exe`; `NODE` =
`.toolchains/node-v24.22.0-win-x64/node.exe`):

| Command/check | Actual result |
|---|---|
| `PY -m py_compile .cache/deploy_events_table.py`; `NODE --check .cache/verify_events_table_install.mjs` | PASS. Helpers independently reviewed; no product source changed during deployment. |
| `PY .cache/deploy_events_table.py build` | PASS: isolated rebuild, exact tested-asset equality, immutable manifest and older-asset retention. Existing Vite chunk-size/outside-project-output advisories only; the new directory was not emptied. `verification/events-table/deployment-build.json`. |
| `PY .cache/deploy_events_table.py prepare` | PASS: runtime/scope preservation, no active work, previous Compose/private checksum snapshot, candidate with exactly one new read-only mount. `deployment-prepared.json`. |
| `PY .cache/deploy_events_table.py deploy` | PASS: only 8445 recreated, matching current/older assets and original backend/data/cache/security; 8444 preserved. `deployment-installed.json`. |
| `NODE .cache/verify_events_table_install.mjs` | **PASS, 4.682 s**: actual installed assets with no substitution, existing synthetic Inspector/20 cached events, UTC seconds despite Los Angeles browser timezone, 20-pixel rows/12-pixel eyes/zero vertical cell padding, column hiding/restore, raw source context, full-screen geometry, nested context/Escape/focus, both rendered themes at 1280×720 and 640×540 and independent same-context same-system windows. `deployment-browser.json`, five screenshot hashes. |
| `PY .cache/deploy_events_table.py verify` | PASS: repeated all preservation/security/asset/8444 checks after browser verification. `deployment-verified.json`. |
| Installed UI inspection | Viewed actual Polish dark full-screen results and the open Columns menu with all optional metadata hidden. Screenshots: `verification/events-table/deployment-screenshots/20261018T113029157Z/`. |
| `git -c core.safecrlf=false diff --check` | PASS. |

Docker/protected-file deployment and browser commands used reviewed escalation
because the sandbox restricts the local named pipe and generated credentials.
No credential values were printed. The first installed-browser helper failed
at its process-count assertion: it counted both the historical controls and the
hidden mounted live viewer. Its report is preserved as
`deployment-browser-attempt-1.json`. Scoping the helper to historical controls
retains the exact five-control assertion and avoids touching live controls; the
next run passed. No application requirement/test was weakened or runtime code
changed. The first attempt detached its one new workspace; the passing attempt
detached both of its new workspaces. Browser checks performed no logout,
preference/shared-setting change, capture, live connection or import. Theme
screenshots used only DOM rendering overrides. Stored preferences, catalogue,
topology, investigations, notes and bookmarks matched before/after digests.
Twenty retained rows do not exercise large vertical overflow in full screen;
the earlier isolated 37-row source browser tests provide that scroll evidence.

Rollback is prepared at `.state/events-table-install/ROLLBACK.txt`: restore the
exact `.secrets/events-table-install/previous-compose.yaml` and recreate only
`runtime-stage3` to remove the overlay. No SQL restore/migration is needed for
this frontend rollback. Original artifacts and the earlier separate schema
recovery remain retained. Automatic rollback was prepared, **not exercised**;
deployment required no recovery. Full backend/source suites were already passed
for the unchanged backend and tested frontend; this turn ran deployment-specific
checks. Native Ubuntu/Rocky/offline-release qualification remains Stage 08,
separately authorized.

## 18 October 2026 — Results pagination, process panes and column-picker correction

Authorization: the user reported that changing rows and result layout appeared
ineffective and requested outside-click dismissal of Columns. This is a narrow
frontend correction to the completed Stage 07 UI; Stage 08 remains separate.

**Changes:** `frontend/src/components/HistoricalViewer.tsx` now reloads page one
immediately when rows changes, preserving the applied time/process/literal query
and leaving unsubmitted edits untouched. Previous/next use the applied size.
Measured mode uses an individual log scroll viewport with the existing bounded
prefetch. Automatic results after collection/opening also honor the current
size instead of overriding it with 200. Loading disables competing page-size
changes; errors retain prior rows and visible feedback.

Split layout already grouped the current page correctly. A single process, as
in the supplied screenshot, therefore produces one pane. Distinct bordered pane
headings now show system/process, host and row count; a pane-count message
explains the one-process case. Layout changes remain local presentation.
Columns retains checkbox interactions and closes on outside pointerdown,
keyboard focus leaving or Escape. Escape restores its summary focus without
closing full-screen results. New text has bundled Polish translations.

Changed files:

- `frontend/src/components/HistoricalViewer.tsx`, `frontend/src/styles.css`,
  `frontend/src/i18n/investigation.pl.ts`.
- `frontend/e2e/events_table.spec.ts`: three additional behavioural cases,
  retaining the original two; useful result-region screenshot captures.
- `frontend/e2e/historical.spec.ts`: wait for the newly immediate resize query
  before the existing explicit Apply action; all previous assertions retained.
- `docs/06_UI_UX.md`, `docs/12_TRACEABILITY.md`, `progress/STATUS.md`.

Commands actually run from the repository root (`PY` =
`backend/.venv/Scripts/python.exe`):

| Command/check | Actual result |
|---|---|
| `PY scripts/stage7_local.py up` | First sandboxed attempt exited 1 (Compose access); reviewed escalation passed. Only the existing isolated 8449 application/SFTP fixture started. |
| `PY scripts/frontend.py test` | PASS: generated API types match; **17/17** Node cases, no skips. Repeated after final source edits, also passed. |
| `PY scripts/frontend.py lint` | PASS, including final browser test changes. |
| `PY scripts/frontend.py typecheck` | PASS during browser-test authoring and final test edits. |
| `PY scripts/frontend.py build` | PASS, including TypeScript; final assets `index-DjqF0-Cw.js` / `index-B92UrpVj.css`. Existing Vite >500 kB chunk advisory only. |
| `PY scripts/frontend.py e2e events_table.spec.ts` | Final **PASS: 5/5 in 26.4 s**, no skips. Real local MariaDB/read-only synthetic SFTP and fresh build substitution; report `verification/stage-7/events-table-controls-browser-final.json`. |
| UI inspection | Viewed actual five-pane and single-pane result-region captures, automatic ten-row collection results, light 1280×720 full screen and dark 1920×1080 full screen. Browser matrix also covers both themes at 1280×720 / 1920×1080 / 640×720. |
| `PY scripts/stage7_local.py stop` | PASS with reviewed escalation; both isolated fixture services stopped and their data retained. |
| `git -c core.safecrlf=false diff --check` | PASS. |

Browser environment: `INSPECTOR_E2E_URL=https://localhost:8449`, protected
`INSPECTOR_E2E_ACCOUNTS=../.secrets/stage7-browser/accounts.json`, final
`INSPECTOR_E2E_REPORT_NAME=events-table-controls-browser-final`. Non-origin
requests were blocked. Only generated synthetic accounts/sources were used.
Tests restore synthetic appearance and log out after each case.

Earlier attempts are retained. `events-table-controls-browser-attempt-1.json`
records all four then-existing cases failing before login because sandbox
access to the protected fixture accounts was denied (`EPERM`). Reviewed
escalation resolved access. `events-table-controls-browser-attempt-2.json`
records **3 passed / 1 failed**: the newly authored row test incorrectly assumed
more than 50 fixture matches; there are 37. The corrected test still requires
the exact limit-50 request, verifies all 37 available event IDs/rows and
exhaustion, and checks two ten-row pages. No existing contract was relaxed.
The fifth case then added ten-row automatic collection loading coverage.

Screenshots are `verification/stage-7/screenshots/events-table-*.png`, including
`separate-process-panes`, `single-process-pane` and `row-count-new-collection`.
The first new split screenshot showed setup instead of results; the final
capture helper targets the actual results region, which was visually inspected.

No backend, dependency, database schema or installed service changed. Full
backend/release suites were not rerun for this frontend-only change. The older
`historical.spec.ts` suite was not run: it targets `stage3-fixture-*` on the
retained 8445 installation, which is outside this correction's test scope.
Its resize path is exercised by the five passing isolated fixture cases.
No blocker remains for the source correction. Deployment requires separate
explicit authorization; the next numbered stage is still
`prompts/08_OFFLINE_RELEASE.md`.

## 18 October 2026 — Temporary results-controls preview left running

Authorization: **“Can you leave the temporary setup running so I can verify the
changes before deploying?”** The isolated setup is now running at
**https://localhost:8449**, serving the exact tested frontend directly to normal
browsers. The earlier browser-only asset substitution is unnecessary here.
The installed 8445 application and other services retain their container/image,
start/restart identities; no migration, seed, dependency/image download or
production target connection occurred.

Open the ready-to-review retained synthetic investigation:
https://localhost:8449/systems/stage7-fixture-a/investigations/1356d454-15fe-41e1-b2e8-25a276def55c

Sign in using the **Inspector** entry in
`.secrets/stage7-browser/accounts.json`. Credentials remain in that protected
file and were not printed. This collection has **37 timestamped matches** from
five synthetic processes, with UTC bounds `2026-10-13 00:00:00` through the
exclusive `2026-10-17 00:00:00`. New pages use their own workspace/presentation;
choose 10 rows, split panes or Columns to review the controls.

Only the generated `stage7-browser` Compose service gained a read-only mount at
`/workspace/backend/src/inspector/web`. The frozen web assets are under
`.state/stage7-browser/results-controls-preview/web`, with hashes and the previous
Compose file alongside. Both fixture services use the existing pinned local
image and remain detached/running on the loopback-only 8449 port. No product
source changed during preview setup. The backend remains the local test source.
Recreating this temporary fixture clears its raw-file cache; the newly collected
data is available while the current preview runs.

Commands actually run (`PY` = `backend/.venv/Scripts/python.exe`; `NODE` =
`.toolchains/node-v24.22.0-win-x64/node.exe`):

| Command/check | Actual result |
|---|---|
| `PY -m py_compile .cache/start_results_controls_preview.py`; `NODE --check .cache/verify_results_controls_preview.mjs` | PASS. Helpers are scoped to the existing synthetic fixture. |
| `PY .cache/start_results_controls_preview.py` | PASS with reviewed escalation: frozen five-file build, one read-only mount, only `stage7-browser`/`stage7-sftp` started using `--no-deps --pull never`. Verified TLS/hostname/readiness and HTTP index/JS/CSS hashes; other service identities unchanged. |
| `NODE .cache/verify_results_controls_preview.mjs` | PASS with reviewed escalation and real served assets, no substitutions: synthetic login/collection, limit 10→50→10 and rendered counts, five separate panes, outside-click/Escape dismissal and full-screen Escape ordering. Captured actual ten-row and split-pane screenshots. Services left running. |
| `PY .cache/start_results_controls_preview.py verify` | PASS: readiness/TLS/served hashes repeated after browser verification; other container/image/start/restart identities still match. |
| UI inspection | Viewed actual served ten-row results. Receipts and screenshots: `verification/results-controls-preview/started.json`, `browser.json`, `served-ten-rows.png`, `served-separate-panes.png`. |
| `git -c core.safecrlf=false diff --check` | PASS. |

The browser smoke creates only synthetic investigation/workspace state. Its
headless browser closed; the HTTP/SFTP preview services were deliberately **not
stopped**. To stop later, run `PY scripts/stage7_local.py stop`; the user requested
that it stay running for review now. Restoring
`.state/stage7-browser/results-controls-preview/previous-compose.yaml` to
`deploy/local-mariadb/stage7-browser.compose.local.yaml` removes the frontend
override on the next fixture recreation. Neither operation deploys to 8445.
The previous five-case source browser suite remains the full feature evidence;
this turn ran the served-preview smoke only. No blocker remains. Stage 08 and
deployment to the installed application remain separately authorized work.

## 18 October 2026 — Frame add actions, log-path defaults and remembered login

Authorization: user requested a **+** on subsystem frames to add a server and
on server frames to add a process, the first connection log root as the proposed
process path, and **Remember me** with a 30-day session. This is a source
follow-up to Stage 07; no installed-application deployment was requested.

Implemented behavior:

- Administrator frame **+** actions open the existing revision-checked forms
  with the clicked immutable parent selected, including collapsed frames.
  Creation expands ancestors in the current view. The buttons have parent-named
  English/Polish labels, preserve keyboard focus and do not trigger drag or
  selection. Inspector controls remain read-only; process creation requires an
  existing parser. Existing System-menu creation remains available.
- A new process proposes `<first connection log root>/app.log`. It uses the
  selected server's own connection, normalizes a trailing slash and follows
  server changes until the field is edited. Manual and existing paths are
  preserved. Without a proposed root the required field starts empty.
- Unchecked **Remember me** keeps configured ordinary idle/absolute timeouts
  (default 30 minutes/eight hours). Checked stores an explicit per-login flag
  and fixed 30-day expiry; inactivity and browser restart do not shorten it,
  and activity does not extend it. Session/CSRF cookies remain opaque,
  HttpOnly, Secure and SameSite=Strict. HTTP, SSH, live, historical dispatch and
  streamed-download authorization use the effective policy. Logout and
  account revocation still invalidate all affected windows and monitors.
- Additive MariaDB `0015_remember_login` over `0014_languages` adds the non-null
  boolean and 0/1 check, defaulting existing sessions to false. Downgrade revokes
  remembered sessions before removing the flag and preserves ordinary sessions.
  Serving needs the matching schema; migration credentials remain separate.

Changed files for this follow-up (earlier results-controls edits preserved):

- Backend: `app.py`, `auth.py`, `database.py`, `history.py`,
  `investigation_bundles.py`, `persistence/models.py`, `ssh_access.py`;
  `migrations/versions/0015_remember_login.py`; generated `backend/openapi.json`.
- Frontend: `Login.tsx`, `SystemWorkspace.tsx`, `TopologyGraph.tsx`,
  `TopologyEditor.tsx`, frame-action rules in `styles.css`, bundled
  `core.pl.ts`/`topology.pl.ts`, generated `src/api/schema.d.ts`.
- Tests/tooling: auth/source-access unit tests,
  `test_remember_login.py`, `verify_remember_login_upgrade.py`,
  `topology_add.spec.ts`, `remember_login.spec.ts`,
  `scripts/verify_topology_login.py`.
- Documentation: root/backend/frontend READMEs, `docs/05`, `06`, `07`, `12`,
  `14`, and this status record.

Commands actually run from the repository root (`PY` =
`backend/.venv/Scripts/python.exe`; Mypy ran from `backend`):

| Command/check | Actual result |
|---|---|
| `PY -m pytest backend/tests/unit -q` | Final **833 passed, 4 skipped**, 27.63 s. Existing Windows symlink privileges, pinned-file rename and POSIX permission restrictions; five existing WebSocket/uvicorn deprecation warnings. |
| `PY -m ruff check --config backend/pyproject.toml backend/src backend/tests backend/migrations scripts` | PASS. |
| `PY -m ruff format --check --config backend/pyproject.toml backend/src backend/tests backend/migrations scripts` | PASS: 173 files. |
| `.venv/Scripts/python.exe -m mypy src` | PASS: 37 source files. |
| `PY scripts/verify_topology_login.py integration` | Final **50/50 passed**, no skips, 65.93 s in new `inspector_test_login_bbebb1`, Linux Python 3.13.16/MariaDB. Covers login choice/inactivity/exact 30-day boundary, cookie flags, CSRF, global revocation, ordinary timeouts, roles, topology/revisions, SSH revocation and bundle download checks. |
| `PY scripts/verify_topology_login.py upgrade` | PASS in fresh populated `inspector_test_rem_upgrade_69bf5e`: all seeded preexisting rows preserved, false legacy-session backfill/timestamps, boolean constraint rejection, downgrade revocation and re-upgrade. Receipt is in the matching `verification/topology-login/rem_upgrade_69bf5e.log`. |
| OpenAPI + `PY scripts/frontend.py api:generate` | PASS: strict optional boolean with default false; generated frontend contract updated. |
| `PY scripts/frontend.py test` | PASS: API consistency and **17/17** Node tests, including all translation keys/placeholders. |
| `PY scripts/frontend.py lint` | PASS; repeated after the final browser locator correction, also passes. |
| `PY scripts/frontend.py typecheck`; `PY scripts/frontend.py build` | PASS, including final test sources; 214 modules, assets `index-CdDlftjp.js` / `index-CuSTed6f.css`. Existing Vite >500 kB chunk advisory. |
| `PY scripts/frontend.py e2e topology_add.spec.ts remember_login.spec.ts` | Final **3/3 passed in 8.0 s**, no skips; `verification/stage-7/topology-login-browser-final.json`. |
| UI inspection | Viewed actual login and topology captures in light/dark at 1280×720 / 1920×1080. Four login captures in `verification/topology-login/screenshots/`; four topology captures `verification/stage-7/screenshots/topology-frame-add-*.png`. |
| `PY -m unittest discover -s tests/package -q` | PASS: 128 cases, nine existing POSIX secret-permission/shell cases skipped on Windows. |
| `PY tools/validate_package.py`; `PY tools/validate_schemas.py` | PASS: all 56 requirements mapped; 20 schemas, 102 successful/36 rejected instances. Package consistency only. |
| `git -c core.safecrlf=false diff --check` | PASS. |

Browser environment: `INSPECTOR_E2E_URL=https://localhost:8450`,
`INSPECTOR_E2E_ACCOUNTS=../.secrets/stage7-browser/accounts.json`,
`INSPECTOR_E2E_REPORT_STAGE=stage-7`, report
`topology-login-browser-final`. The new loopback-only service uses its own
`inspector_test_ui_auth_1018` schema, current source, pinned local Stage 07 image
and synthetic accounts. No SSH/SFTP operation or Internet request is needed.
The tests cover same-context duplicated pages with distinct workspaces, correct
parent/path preselection, keyboard cancellation without writes, collapsed-parent
save, revision/undo/redo, multiple roots, empty roots, manual/existing paths,
Polish controls, Inspector visibility, persistent-cookie fresh-context login,
CSRF denial and global logout. Thirty-day expiry is verified using controlled
server time in MariaDB tests, rather than waiting 30 days.

Retained attempts and setup:

- The first sandboxed `local_mariadb.py new-test --suffix ui_auth_1018` failed.
  Read-only Docker diagnostics confirmed named-pipe/config Access denied;
  reviewed escalation then provisioned only the fresh test schema. No secret
  values were printed. Docker and protected-account browser checks used
  reviewed escalation; no automatic-approval rejection occurred.
- First API run (`login_9a584a.log`) had **49 passed / 1 failed**: the new test
  expected a read-only `/auth/session` GET to renew deliberate idle activity.
  The test now performs an actual CSRF-protected preference write and retains
  the unchanged-expiry and exact-expiry assertions. No production timeout or
  existing contract was relaxed. The final fresh-schema run passes all 50.
- First browser run had **2 passed / 1 failed**: exact `getByLabel` could not
  match a wrapping select label containing option text. The rendered form had
  the correct parent and path. Exact accessible combobox-role locators fixed
  only the new test, preserving every assertion; attempt two passed all three
  in 7.0 s. Inspection then found a topology capture scrolled below the new
  controls. Final screenshots scroll to the top and explicitly assert both
  frame actions are in the viewport in every theme/size; all three cases pass
  again in 8.0 s. Both earlier reports remain retained.
- Compiled ignored helpers `.cache/start_topology_login_fixture.py` and
  `.cache/seed_topology_login_fixture.py` created/seeded only the new 8450
  fixture. Its initial database-only internal network made the published HTTPS
  port unreachable; a separate browser network corrected the fixture without
  changing product code. TLS/readiness passed, and unchanged service identity,
  image, start/restart metadata is recorded in
  `verification/topology-login/fixture-started.json`.
- `PY .cache/start_topology_login_fixture.py stop` passed after browser checks:
  only 8450 stopped; the 8449 user-review preview, its previous schema/assets
  and cache, installed 8445/8444 applications and all other service identities
  match their preflight state. Disposable test databases are retained.

No blocker remains for this source request. The matching migration/backend/UI
must be installed together under a separate deployment authorization. Full
release/offline/native Ubuntu/Rocky qualification and unrelated browser/SFTP
suites were not rerun; the relevant targeted checks above passed. Stage 08
remains separately authorized work; existing 8449 review remains running.

## 18 October 2026 — Separate process navigation and pane arrangements

Authorization: user reported being unable to switch processes after choosing
Separate process panes and requested stacked panes or 2, 3 or 4 columns. This
is a historical-results source follow-up to Stage 07; existing unrelated
topology/login/results-control source changes were preserved.

The previous split view grouped only the current merged page. A page dominated
by one process hid the other processes entirely. Separate panes now covers all
processes in the applied query, with independent bounded pages, counts, context
and previous/next controls for each. Show process lists all queried processes
with name, host and immutable ID, or focuses one at full width. Pane arrangement
offers Stacked, 2 columns, 3 columns and 4 columns. Focus/arrangement/column
changes preserve mounted pane data and scroll and make no query or SSH request.
Each process table scrolls horizontally within its pane.

Incomplete merged pages load process pages with at most two concurrent retained
queries, 15-second timeouts, cancellation and project/process/lane/snapshot
validation. Complete first-page merged results seed panes without extra queries;
a final merged page is never mistaken for a complete seed. Per-process filters
are restricted to the requested process; merged cursors are never reused for a
different process selection. Each failed page retains its prior rows and offers
an independent retry of the failed cursor. Row-size changes use the applied
query and preserve focused process/arrangement and unsubmitted controls. Explicit
Apply/lane changes replace query scope and reset process focus. Merged paging
remains independent. These controls are page-local, including duplicate pages
in the same browser context. New text has bundled Polish translations.

Changed files for this follow-up:

- `frontend/src/components/HistoricalViewer.tsx`, new
  `HistoricalProcessPanes.tsx` and extracted unchanged virtual table in
  `HistoricalLogTable.tsx`; `frontend/src/styles.css`,
  `frontend/src/i18n/investigation.pl.ts`.
- `frontend/e2e/events_table.spec.ts`: retains the five existing regressions,
  extends duplicate-page isolation, and adds genuine missing-process/pagination
  and layout-matrix cases. Authentication uses the retained fixture's real
  CSRF-protected API, since its backend predates the optional remembered-login
  field; the separate login suite covers that matching newer backend/UI.
- `frontend/README.md`, `docs/06_UI_UX.md`, `docs/12_TRACEABILITY.md`, this record.

Commands actually run from the repository root (`PY` =
`backend/.venv/Scripts/python.exe`):

| Command/check | Actual result |
|---|---|
| Local HTTPS readiness request | PASS: existing isolated `https://localhost:8449/api/v1/health/ready` returned 200. No service restarted or changed. |
| `PY scripts/frontend.py test` | Final PASS: generated API consistency and **17/17** Node cases, no skips. Initial run during implementation caught four missing Polish keys; translations were added and the unchanged coverage passes. |
| `PY scripts/frontend.py lint` | PASS, including final test locator edits. |
| `PY scripts/frontend.py typecheck` | PASS. |
| `PY scripts/frontend.py build` | PASS: 216 modules; `index-ozuVJLUF.js` / `index-DOl-cgPf.css`. Existing Vite >500 kB chunk advisory. |
| `PY scripts/frontend.py e2e events_table.spec.ts -g 'separate panes query'` | PASS: **1/1**, 5.2 s after scoping the newly added locator to Historical investigation. |
| `PY scripts/frontend.py e2e events_table.spec.ts` | Final PASS: **7/7**, 36.2 s, no skips. Real local MariaDB/read-only synthetic SFTP; report `verification/stage-7/process-panes-browser-final.json`. |
| UI inspection | Viewed actual light 1920×1080 three-column, dark 1280×720 four-column full-screen, and dark 640×720 four-column result captures. Matrix covers both themes and 1280×720 / 1920×1080 / 640×720, all four arrangements plus full screen. |
| `git -c core.safecrlf=false diff --check` | Final PASS. Initial check found an extra blank line after table extraction; removed. |

Browser environment: `INSPECTOR_E2E_URL=https://localhost:8449`, protected
`INSPECTOR_E2E_ACCOUNTS=../.secrets/stage7-browser/accounts.json`, final
`INSPECTOR_E2E_REPORT_NAME=process-panes-browser-final`. Tests substitute only
fresh built web assets in their own browser context. Non-origin requests are
blocked; only generated synthetic sources/accounts are used. Tests restore
the synthetic theme and log out after each case. Screenshots are under
`verification/stage-7/screenshots/events-table-*`, including the layout matrix
and `process-pane-query-error`.

Earlier attempts remain recorded: attempt 1 failed all seven before login with
sandbox `EPERM` on the protected fixture accounts. Reviewed escalation resolved
access. Attempt 2 failed login because the unchanged 8449 backend rejects the
newer UI's optional `remember_me` field. The compatible real API sign-in helper
resolved that mismatch without modifying the running service/schema. Attempt 3
passed six/seven; the new test's unscoped Per-process literal filters locator
matched historical and live panels. Scoping it to Historical investigation
fixed the test without weakening its assertions; attempt 4 passed the targeted
case and the final full run passed all seven. No automatic-approval rejection
occurred.

No backend, dependency, schema or installed/review-preview assets changed in
this follow-up. The requested 8449 preview remains running with its previous
served assets; browser substitution did not publish the new build. Backend,
migration, unrelated live/SSH suites and full offline/native Ubuntu/Rocky release
checks were not rerun for this frontend-only correction. No source blocker
remains. Deployment still requires separate explicit authorization; the next
numbered stage remains `prompts/08_OFFLINE_RELEASE.md`.

## 18 October 2026 — Process-pane preview updated on port 8449

Authorization: **Update the preview on port 8449**. The running preview at
**https://localhost:8449** now serves Show process, Stacked/2/3/4-column pane
arrangements and independent per-process pagination directly to ordinary
browsers. Refresh existing pages. The retained review URL still works:
https://localhost:8449/systems/stage7-fixture-a/investigations/1356d454-15fe-41e1-b2e8-25a276def55c

Updated only files inside the existing read-only frontend directory mount;
new hashed assets were installed before atomically replacing `index.html`.
Previous hashed assets remain available for existing pages and rollback. Every
local Compose service's container/image/start/restart identity matches its
preflight state, including 8449, SFTP, MariaDB and installed 8444/8445. No service
restarted, schema/configuration changed, migration/seed ran or source collection
started. The existing 37-match/five-process investigation remains cached.

The current product Login component belongs to the separately tested
`0015_remember_login` follow-up, while the running preview uses its older strict
login API. An isolated copy of the frontend was therefore built with only its
Login component replaced by the exact compatible `git show
HEAD:frontend/src/components/Login.tsx` source. It keeps the preview's existing
two-field login and does not expose an unsupported Remember me control. Every
other staged source file matches the current product source by SHA-256,
including both pane components; product sources and `frontend/dist` remain
unchanged. The staging build first inherited the existing local dependencies
under `frontend/.cache/process-panes-preview`, then was moved with explicitly
verified workspace paths to
`.state/stage7-browser/process-panes-preview/staged-frontend` so it cannot affect
normal frontend tool scans. No dependency or image was downloaded.

Commands actually run (`PY` = `backend/.venv/Scripts/python.exe`, `NODE` =
`.toolchains/node-v24.22.0-win-x64/node.exe`):

| Command/check | Actual result |
|---|---|
| `PY .cache/build_process_panes_preview.py` | PASS: isolated TypeScript + Vite build, five assets, exact one-file staged compatibility difference, unchanged product source hashes. JS `index-DBw_qvq9.js`, CSS `index-DOl-cgPf.css`; existing chunk-size advisory only. |
| `PY -m py_compile .cache/build_process_panes_preview.py .cache/update_process_panes_preview.py`; `NODE --check .cache/verify_process_panes_preview.mjs` | PASS. |
| `PY .cache/update_process_panes_preview.py` | Final PASS with reviewed escalation: backup, atomic frontend update, pinned-certificate TLS/hostname/readiness and real HTTP index/JS/CSS hashes; every service and Compose file unchanged. |
| `NODE .cache/verify_process_panes_preview.mjs` | PASS with reviewed escalation and actual served assets, no substitutions: real browser UI login, retained 37 matches, ten-row merged page, five independently queried panes, scoped process pagination, process focus, all four arrangements, full screen, same-context duplicated pages with distinct workspaces and independent controls; logout after verification. No collection/preferences/configuration writes. |
| `PY .cache/update_process_panes_preview.py verify` | PASS after browser smoke: real served hashes/readiness and all service identities still match; services left running. |
| UI inspection | Viewed actual served four-column full-screen results and focused-process results. Captures: `verification/process-panes-preview/served-four-columns-fullscreen.png`, `served-focused-process.png`; inline four-column capture also retained. |
| Product-source hash comparison; `git -c core.safecrlf=false diff --check` | PASS. |

The first update-helper attempt stopped in read-only preflight with HTTP 404
when it tried to fetch bundled license files as public routes. The backend
publishes the SPA document and `/assets`, not standalone `/licenses` routes.
Correcting that preflight to the same index/asset checks as the prior preview
helper resolved it; both notice files remain bundled. No asset was changed by
the failed attempt. No automatic-approval rejection occurred.

Evidence is `verification/process-panes-preview/updated.json` and `browser.json`.
Build provenance, current manifest and the complete prior web directory are
under `.state/stage7-browser/process-panes-preview/`, including `previous-web/`
and `previous-asset-manifest.json`. Rollback can atomically restore the prior
`index.html` into `.state/stage7-browser/results-controls-preview/web/` and the
prior asset manifest; old hashed files remain in that mount, so a container
restart is unnecessary. Historical preview receipts were preserved.

The full source suite already passed 17 frontend unit and seven browser cases
in the preceding entry; this turn ran the served-preview smoke and isolated
build checks. Backend, migrations, unrelated SSH/live and release suites were
not rerun because this update changes only served frontend files. Installed
8445, the remembered-login backend migration and Stage 08 remain separate.
The updated 8449 preview is deliberately left running for review.

## 18 October 2026 — Events toolbar, checkbox visibility and footer paging

Authorization: user requested moving the results/page dropdown below the table,
moving Show process beside Result layout with process checkboxes in either
layout, and keeping Pane arrangement visible but locked in Merged. Refreshed
the already-authorized 8449 review preview with the verified frontend. The
existing source work and all installed 8444/8445 services were preserved.

Implemented:

- Rows per result page is always in the result footer, below the merged table
  or process panes and alongside merged pagination. It retains immediate
  repagination against the applied query and preserves unsubmitted controls.
- The toolbar orders Result layout, Show process, Pane arrangement, Columns and
  Full screen. Show process is a checkbox dropdown in both layouts, with an
  indeterminate All processes control and names/hosts/immutable IDs. Its full
  applied-query process option set remains available after hiding processes.
- Merged selection queries only the enabled subset, pruning per-process filters
  and resetting cursor/history. The original applied scope remains separate
  from this effective query, so previously hidden or absent-page processes can
  be restored. Counts and subsequent page/size requests describe that subset.
  No selected processes shows an explicit empty state and disables paging,
  without sending an empty process scope. A failed selection restores previous
  checks and retained rows; loading disables competing changes.
- Split checks hide/show mounted panes with no visibility query, preserving
  each pane's page and scroll. A subset merged result can seed only compatible
  included process panes; it cannot prove another process is empty. Existing
  bounded workers/cancellation/snapshot checks remain. Pane arrangement stays
  visible, disabled in Merged, with its prior value retained across layouts.
- Both dropdown pickers support outside click, focus exit and Escape. The
  process picker stays open through a loading checkbox change and restores its
  checkbox focus without overriding a deliberate outside action. First Escape
  closes the popup and retains full screen; the next exits full screen.
- Process visibility remains local to each browser page, including duplicated
  pages in one account/context. Successful Apply/lane changes replace the
  applied scope and restore all checks; failures retain the current selection.
  New labels/help are bundled in Polish.

Changed source files: `frontend/src/components/HistoricalViewer.tsx`,
`HistoricalProcessPanes.tsx`, new `ProcessVisibilityMenu.tsx`, `styles.css`,
`i18n/investigation.pl.ts`; `frontend/e2e/events_table.spec.ts`;
`frontend/README.md`, root `README.md`, `docs/06_UI_UX.md`,
`docs/12_TRACEABILITY.md` and this status record. No backend, dependency or schema
changed in this follow-up.

Commands actually run (`PY` = `backend/.venv/Scripts/python.exe`, `NODE` =
`.toolchains/node-v24.22.0-win-x64/node.exe`):

| Command/check | Actual result |
|---|---|
| `PY scripts/frontend.py test` | PASS, repeated after the final focus fix: API types match and **17/17** Node cases, no skips. |
| `PY scripts/frontend.py lint` | PASS, including final component/test edits. |
| `PY scripts/frontend.py typecheck` | PASS; also included in the final build. |
| `PY scripts/frontend.py build` | Final PASS: 217 modules, `index-DVfNnJMK.js` / `index-J_x-79Gp.css`. Existing >500 kB Vite advisory only. |
| `PY scripts/frontend.py e2e events_table.spec.ts -g 'process layouts\|process checkboxes\|page size changed'` | PASS: **2/2**, 11.2 s. The pattern matched the two corrected cases; the ninth resize regression is covered by the final full run. |
| `PY scripts/frontend.py e2e events_table.spec.ts` | Final PASS: **9/9**, 49.6 s, no skips; `verification/stage-7/event-controls-browser-final.json`. |
| `PY -m py_compile .cache/build_event_controls_preview.py .cache/update_event_controls_preview.py`; `NODE --check .cache/verify_event_controls_preview.mjs` | PASS. |
| `PY .cache/build_event_controls_preview.py` | PASS: isolated TypeScript/Vite preview build; only staged Login differs from current source, using the exact prior compatible login. Five assets; preview JS `index-CEkClDfy.js`, same CSS as source. Product sources and `frontend/dist` preserved. |
| `PY .cache/update_event_controls_preview.py` | PASS with reviewed escalation: backup, new assets then atomic index swap in the existing mount; real pinned-certificate HTTPS readiness/index/JS/CSS hashes match. Every service/container/image/start/restart identity and Compose file unchanged; no restart/migration/seed. |
| `NODE .cache/verify_event_controls_preview.mjs` | Final PASS with reviewed escalation: actual served assets, real UI login, retained 37 matches, footer/header geometry, merged subset counts/queries/full options, none/all, split page/scroll preservation, all arrangements, full-screen/Escape, same-context duplicate-window isolation and contained 640 px popup. No asset substitution, collection or configuration/preference writes. Logs out after checking. |
| `PY .cache/update_event_controls_preview.py verify` | PASS: readiness, served hashes and all local service identities still match. Preview remains running. |
| Product source/provenance comparison; `git -c core.safecrlf=false diff --check` | PASS. |

Browser environment: `INSPECTOR_E2E_URL=https://localhost:8449`, protected
`INSPECTOR_E2E_ACCOUNTS=../.secrets/stage7-browser/accounts.json`, final report
name `event-controls-browser-final`. The source suite uses built asset
substitution only in its own browser context and real local MariaDB/read-only
synthetic SFTP. Non-origin requests are blocked. Tests restore the synthetic
theme and log out. The separately served preview smoke uses no substitution
and reopens the unchanged cached investigation at:
https://localhost:8449/systems/stage7-fixture-a/investigations/1356d454-15fe-41e1-b2e8-25a276def55c

Preserved failed/corrected checks:

- `event-controls-browser-attempt-1.json`: **6 passed / 2 failed**. The new
  outside-click test targeted a log message covered by the larger process popup;
  it now clicks an unobscured timestamp cell and retains all dismissal/focus
  assertions. The merged case also found a real focus bug: disabling a changed
  checkbox during query loading closed the dropdown. The component now retains
  the focus anchor through that temporary blur and restores it after loading.
  The two-case attempt 2 passes; the final full run passes all nine.
- Review found all panes off → page size changed → panes restored → Merged
  could reuse an old limit because layout switching compared only process IDs.
  It now compares the full effective query excluding cursor. The added ninth
  browser regression requires a fresh exact limit-50 request and complete rows.
- The first served-preview smoke incorrectly expected horizontal scrolling in
  a full-width stacked table that fits at 1920 px. It now selects four columns
  before testing horizontal scroll. The next functional smoke passed; visual
  inspection then found the narrow screenshot captured above the events area.
  The final capture scrolls the results to the top and asserts the summary and
  popup are in the viewport before capture. The repeated served smoke passes.
  These helper corrections did not change the deployed frontend.
- No automatic-approval rejection occurred. Protected-account/browser and
  local Docker identity checks used reviewed escalation.

Visually inspected actual served dark merged partial-checkbox results with
footer, four-column full-screen results with footer, and the contained 640×720
process popup. Captures are in `verification/event-controls-preview/`:
`served-merged-checkbox-subset.png`, `served-four-columns-fullscreen.png`,
`served-narrow-process-menu.png`; inline four-column capture also retained.
The source browser matrix covers both themes at 1280×720 / 1920×1080 / 640×720
for all four arrangements and full screen, with existing context/column/UTC
regressions retained.

Preview receipts: `verification/event-controls-preview/updated.json` and
`browser.json`. Isolated build provenance/manifest/staged source and prior web
backup are under `.state/stage7-browser/event-controls-preview/`. As in the
prior update, preview retains the existing two-field Login from Git HEAD because
its backend predates `0015_remember_login`; all other staged source hashes match
the current product. The generated build directory was moved with verified
workspace paths out of `frontend/.cache` after building to avoid tool scans.
Rollback can atomically restore `previous-web/index.html` into the existing
`.state/stage7-browser/results-controls-preview/web/` mount and restore
`previous-asset-manifest.json`; old hashed assets remain present. No restart is
needed. Earlier preview receipts/backups remain intact.

No blocker remains. The updated 8449 preview is left running for review; port
8445 and the remembered-login backend/migration are unchanged. Backend,
migration, unrelated live/SSH suites and full offline/native Ubuntu/Rocky
qualification were not rerun for these frontend-only changes. Stage 08 remains
the next separately authorized numbered gate.

## 18 October 2026 ? events Filters window and grouped log pins; 8449 preview

User-authorized events-view follow-up, including the explicit choice that multiple selected logs form **one pin with one shared description**. The existing preview-update authorization applies to HTTPS 8449 only. Stage 08 remains separately gated; installed 8445/8444 and unrelated remembered-login deployment are unchanged.

Implemented behavior:

- **Filters** in the events toolbar opens a separate modal with exact UTC `[from,to)` bounds, existing global/per-process literal include/exclude filters, individual removal, and an Add filter form. Any/all and case rules remain available. Apply validates and queries retained data; Cancel/X discards the dialog draft. Live filtering is unchanged.
- Clicking a log row, Space or Enter toggles its marked state. Text selection/copy and the context eye preserve their behavior. Marks survive paging, process visibility and layout changes within that investigation, and remain local to each browser page. **Pin** opens a shared description form; successful atomic saving creates one investigation card containing all selected raw log entries and source snapshots. Failed saves preserve the selection and description. Cards support edit/delete and persist through reload, cache expiry and redacted offline bundle exchange.
- Group creation/edit/deletion is owner-, project-, CSRF- and revision-checked in both historical and imported investigations. Up to 100 selected anchors are saved atomically, within the existing aggregate 32 MiB pin budget and a cancellation-aware 30-second deadline. Server-owned group membership lives in existing MariaDB analysis JSON; no table or migration was added. Existing bookmarks remain supported.
- Process choices use `server name: process name`, with immutable IDs on hover. Imported process lists use the retained server-name snapshot. Removed the process-pane explanatory paragraph. **Rows** / **Viewport** sit at the right of the results footer. Existing Show process checkboxes, independent split pagination and disabled merged arrangement are retained.

Changed source groups: new `HistoricalFiltersDialog.tsx`, `InvestigationPinDialog.tsx`, `investigationPins.ts`; updated historical viewer/table/panes/process menu, investigation cards, CSS and bundled Polish translations; new grouped-pin API and offline bundle handling in `investigations.py` / `investigation_bundles.py`; bundle JSON schema, generated OpenAPI and TypeScript API; new `test_grouped_pins.py`, bundle unit regressions and `event_pins.spec.ts`; updated events-table browser coverage and existing historical/investigation/language/SSH/UI callers plus shared modal helpers. Updated root/frontend/backend READMEs and domain/API/UI/traceability/MariaDB docs. Pre-existing topology/authentication/SSH changes were preserved.

Commands actually run (root, using `backend/.venv/Scripts/python.exe` unless stated):

| Command | Result |
|---|---|
| `INSPECTOR_CONFIG_FILE=.state/stage7-browser/application.yaml python -m inspector.cli openapi --output backend/openapi.json`; `python scripts/frontend.py api:generate` | PASS: actual API schema and generated client include grouped pins. CLI creates OpenAPI without starting a database lifespan. |
| `python -m pytest backend/tests/unit -q` | **837 passed, 4 skipped** for Windows symlink/POSIX permission and pinned-file rename contracts; existing WebSocket deprecation warnings only. |
| `python -m ruff check --config backend/pyproject.toml backend/src backend/tests backend/migrations scripts`; corresponding `ruff format --check`; `.venv/Scripts/python.exe -m mypy src` from backend | PASS; 174 format-checked files and 37 mypy source files. |
| `python .cache/verify_grouped_pins.py` | **22/22** real Linux Python 3.13/MariaDB integration cases, no skips: investigation/bookmark compatibility, grouped ownership/system/CSRF/revision rules, atomic rollback, retention, redaction and offline import/re-export. Fresh disposable synthetic schema only. Logs `verification/grouped-pins/pins_b940b1d9*`. |
| `python scripts/frontend.py test` | **17/17** plus generated API consistency. |
| `python scripts/frontend.py typecheck`; `lint`; `build` | PASS. Build 219 modules; existing >500 kB chunk-size advisory remains. Repeated typecheck/lint after the final imported-label correction also PASS. |
| `python tools/validate_schemas.py`; `python tools/validate_package.py`; `git diff --check` | PASS: 20 schemas, 102 positive/36 negative instances, 56 requirement/120 acceptance mappings. Package validation is not runtime qualification. |
| `python scripts/frontend.py e2e events_table.spec.ts` with source assets / `pins-filters-events-attempt-1` | **10/10**, real synthetic 8449 MariaDB/SFTP, no skipped cases. |
| `python scripts/frontend.py e2e events_table.spec.ts event_pins.spec.ts` with `INSPECTOR_E2E_SERVED_ASSETS=1`, report `pins-filters-served-final` | **13/13**, no skips/flaky cases, 2.4 minutes. Uses actual HTTPS assets, not substitutions. Row keyboard/copy/context/scroll, grouped save/edit/reload/delete/atomic failure, same-account duplicated pages, modal filters and both-theme 1280/1920/640 layouts/full screen. Final imported-label follow-up is additionally checked below. |
| `python .cache/pins_preview_backend.py --freeze --unit` | PASS: **57** units against the exact frozen preview package. Git HEAD 0014 baseline plus only the two pin modules, excluding three unrelated remembered-login hunks. Actual frozen OpenAPI retains old Login and adds exactly six pin routes. |
| `python .cache/build_pins_preview.py --resume-staged`; `python .cache/build_pins_preview_final.py`; `python .cache/build_pins_preview_cleanup.py` | PASS: isolated frontend TSC/Vite builds. Only staged Login uses compatible HEAD source. Final CSS `index-A4MUdSNy.css`, JS `index-CYJqYCh2.js`; product sources untouched. |
| `python .cache/update_pins_preview.py inspect`; `update` | PASS: local synthetic scope verified, no active collection/live writer; full protected SQL and regular-file state/cache backups, ownership-preserving restoration into dedicated volumes, exact file/table checks, only 8449 service recreated. Schema stays `0014_languages`; 4 state and 1,107 cache entries preserved. |
| `python .cache/update_pins_preview_web.py`; `python .cache/update_pins_preview_web_final.py`; `python .cache/update_pins_preview_web_cleanup.py` | PASS: publish content-hashed assets before atomic index replacement; actual TLS/HTTPS bytes match manifests, all running container identities unchanged during frontend publication. Old assets retained. |

Browser environment: `INSPECTOR_E2E_URL=https://localhost:8449`, protected synthetic `INSPECTOR_E2E_ACCOUNTS=../.secrets/stage7-browser/accounts.json`, final two-file run `INSPECTOR_E2E_SERVED_ASSETS=1`. Non-origin requests are blocked. Credentials are excluded from output, screenshots, traces and video. Production targets and accounts were not used.

Preserved failed/corrected checks:

- First OpenAPI command omitted deployment configuration and failed before schema generation; rerun with the explicit local configuration succeeded, then API types were regenerated from the correct schema.
- The initial staged-build receipt assumed incorrect notice filenames after a successful compilation. It was corrected to the actual bundled Python/Unicode notices and the immutable staged build was revalidated.
- Initial full ESLint scanned the generated minified staging bundle under `frontend/.cache` and failed on generated code. The verified build was moved outside the frontend tree, staging helpers now retain builds there automatically, and full lint passes without changing rules.
- Actual-served attempt 1: **10 passed / 3 failed**. The selection test tried horizontal scroll where the table fit; it now explicitly uses an 800 px viewport and asserts a real overflow precondition. Two later cases hit the unchanged login rate limit; tests now wait 60 seconds for at most one bounded retry. The final 13-case run passes all assertions.
- No automatic approval rejection occurred. Local Docker operations and protected synthetic account reads used reviewed escalation.

Preview recovery/provenance: `.state/stage7-browser/pins-preview/` contains the frozen 0014 baseline, pin-only patch, source manifests, OpenAPI and 57-unit log, first staged assets and previous web. Final assets/build receipt are in `.state/stage7-browser/pins-preview-cleanup/`; the intermediate imported-label build remains in `pins-preview-final/`; backend and publication receipts are under `verification/pins-preview/`. Protected full SQL/state/cache snapshots and original/fallback Compose files are in `.secrets/stage7-browser/pins-preview-backup/`. The fallback Compose uses the previous 0014 backend and the preserved state/cache volumes, avoiding loss of the former tmpfs data. No serving application receives migration/root credentials. Frontend rollback restores the backed-up index/manifest atomically; old content hashes remain available.

Final actual-served preservation/visual check: repository Node ran `.cache/verify_pins_preview.mjs`, **PASS**. It uses the final served asset manifest (including the imported-server label correction), actual compatible UI login, no source substitutions, and the original retained investigation with **37 matches across five processes**. It verifies host/process labels and hover IDs, bottom-right Rows/Viewport, current Filters bounds/terms, row selection and a shared Pin description dialog. Both themes at 1280?720 and 1920?1080 plus full-screen results produce 12 screenshots. Filter/Pin Cancel leaves workspace and bookmarks exactly unchanged; no collection, pin write, extra query, external request or browser error occurred. Original preferences were restored and UI logout completed. `verification/pins-preview/browser.json` and adjacent PNGs preserve the evidence. Visually inspected the light 1280 Filters window, dark 1920 shared-description Pin window and light 1920 full-screen results; controls and selected rows are legible, Rows/Viewport is at the right, and the filter window scrolls to its matching/apply controls at 720 px height. Initial sandbox account reads failed before login; reviewed escalation permitted the authorized protected synthetic-account read without changing permissions or printing credentials.

Legacy investigation regression: `python scripts/frontend.py e2e investigation.spec.ts` with the same 8449 synthetic accounts, `INSPECTOR_E2E_SERVED_ASSETS=1`, `INSPECTOR_E2E_LOCAL_ASSETS=0`, report `pins-filters-investigations-final`: **4/4 PASS**, no skips/flakiness, 37.2 seconds. Both roles verify exact five-process traces, legacy pinned context, saved filters/layout, scoped offline bundle import, imported `server: process` labels and hover IDs, annotation re-export and context after source expiry. Dependency selection, unsafe bundle rejection and delayed bookmark response isolation also pass. First attempt **2 passed / 2 failed** was a relative locator error in the new label assertion; using the checkbox's parent label preserves all exact caption/ID/scope assertions. Attempt 1 is retained separately. All test sessions logged out. Inspected imported-offline and expired-source retained-context screenshots; the full existing saved-workspace/provenance/redaction captures were refreshed.

The 13-case suite ran before the final imported-label and pane-summary text cleanups. Imported labels are covered by the subsequent four-case suite and final served smoke; the last smoke additionally checks five split panes and absence of both the removed explanatory paragraph and remaining pane-count summary. Final typecheck/lint pass after these changes. No relevant functional check remains blocked. Older fixture-specific historical/SSH/live suites and complete Ubuntu/Rocky/offline-release qualification were not repeated; this work does not complete Stage 08. The updated 8449 preview is left running for review with existing data preserved.

Final cleanup smoke rerun: **PASS, 6.61 seconds**, exact served `index-CYJqYCh2.js` / `index-A4MUdSNy.css`; five split panes with no pane-count summary or explanatory paragraph. Thirteen captures include `served-split-clean-summary.png` and the refreshed 12 theme/resolution/dialog/full-screen views. The earlier smoke report remains `browser-before-summary-cleanup.json`; latest `browser.json` passes preservation and logout checks.

## 18 October 2026 — 8449 updated with remembered login and frame actions

Authorization: **“Update the 8449 environment.”** The retained review preview at
**https://localhost:8449** now serves the current matching frontend/backend,
including **Remember me**, subsystem/server **+** actions and first-connection-
root log-path suggestions. It retains the latest Filters, described grouped
pins, process selection, independent pagination and pane controls. The preview
schema is **`0015_remember_login`**. Refresh existing pages to load the new
login and controls; the checked login option gives a fixed 30-day session.
The installed 8445 application remains at `0014_languages` and is unchanged.

The new immutable package is
`.state/stage7-browser/topology-login-preview/backend`, containing the current
backend source, migrations and frontend, with source/asset/OpenAPI manifests
alongside. New JS is **`index-C04ZvtSv.js`**, CSS **`index-A4MUdSNy.css`**.
Previous content-hashed assets and notices are retained. The frozen OpenAPI
matches the current generated contract exactly: opt-in strict Remember-me
boolean plus all six grouped-pin routes and retained pin-group responses.

Only `stage7-browser` was stopped/recreated, using the already pinned local
image and `--no-deps --pull never`. Its existing dedicated persistent state and
cache volumes were reused. There was no fixture preparation, seed, reset,
dependency download or target connection. With serving stopped, a protected
full SQL dump, state/cache archives and ownership/mode manifests were retained
in `.secrets/stage7-browser/topology-login-preview/`, along with previous
Compose, frontend, configuration and rollback instructions. The state archive
includes the unchanged private vault; the prior frozen backend/web remain
untouched in their existing locations.

Migration used only the separate integration migrator credentials and the
exact frozen `0014_languages` → `0015_remember_login` migration. All **49 table
counts**, **47 unchanged table checksums** and exact old login-session columns
matched immediately afterward; existing sessions received false remember
flags. After startup and browser checks, **43 stable tables**, all **4 state
entries / 1,811 cache entries**, content hashes and UID/GID/modes still match.
Startup intentionally detaches old active page workspaces. Browser-generated
sessions, audit records, workspaces and query cursors are accounted for
separately. All other container/image/start/restart identities match preflight,
including the retained 8449 SFTP fixture and installed 8445/8444 applications.

Commands actually run from the repository root (`PY` =
`backend/.venv/Scripts/python.exe`; `NODE` =
`.toolchains/node-v24.22.0-win-x64/node.exe`):

| Command/check | Actual result |
|---|---|
| `PY scripts/frontend.py build` | PASS: TypeScript and Vite, 219 modules, actual current Login without the old compatibility overlay. Existing >500 kB chunk advisory only. |
| `PY -m py_compile .cache/build_topology_login_preview.py .cache/update_topology_login_preview.py`; `NODE --check .cache/verify_topology_login_8449.mjs` | PASS. Helpers independently reviewed before runtime changes. |
| `PY .cache/build_topology_login_preview.py` | PASS: 74 frozen package files, 14 web-manifest files, exact input/source equality, current OpenAPI equality, retained older assets and no product-source changes. |
| `PY -m pytest backend/tests/unit/test_auth_validation.py backend/tests/unit/test_source_access.py backend/tests/unit/test_investigation_bundles.py -q -p no:cacheprovider`, with frozen `PYTHONPATH` | **110/110 PASS**, no skips, 4.28 s, against the exact candidate source. |
| `PY .cache/update_pins_preview.py inspect` | PASS: exact synthetic 8449 identity, old schema `0014_languages`, no active collection/live work; read-only preflight. |
| `PY .cache/update_topology_login_preview.py update` | PASS: stopped-service backup, scoped migration, matching frontend/backend installation, pinned-certificate TLS/readiness, runtime security and data/service preservation. |
| `NODE .cache/verify_topology_login_8449.mjs` | PASS: actual served frontend, real synthetic local accounts, no asset substitution or external requests. New checked login issues secure HttpOnly Strict 30-day session/CSRF cookies and authenticates a fresh cookie-only browser context. Existing ordinary login also works. |
| `PY .cache/update_topology_login_preview.py cleanup` | PASS: only the two smoke-created authentication sessions removed by recorded hash and user ID; original session-column digest unchanged. No account-wide logout or revocation. |
| `PY .cache/update_topology_login_preview.py verify` | PASS after browser cleanup. Repeated with receipt-count clarification as `verified-final.json`: 12 actual public HTTPS files verified; two additional bundled license files are covered by the 14-file immutable manifest. |
| UI inspection | Viewed actual dark 1280 login with Remember me, light 1280 Add process form, dark 1920 topology with both frame **+** controls, and retained Filters/Pin captures. Browser matrix covers both themes at 1280×720 / 1920×1080. |
| `git -c core.safecrlf=false diff --check` | PASS. |

The actual-served browser smoke reopens the unchanged retained investigation:
https://localhost:8449/systems/stage7-fixture-a/investigations/1356d454-15fe-41e1-b2e8-25a276def55c

It verifies **37 retained matches across five processes**, current Filters and
two selected rows in the shared-description Pin dialog, draft cancellation
without saving/querying again, and preserved preferences/analysis/bookmarks.
Same-context duplicated/switching pages have distinct server workspaces and
leave the original page's two selected rows intact. Inspector frame additions
are absent; Administrator frame buttons open the correct parent forms and
propose the selected server connection's first root. Keyboard cancellation
restores focus without a topology write. Four smoke-created workspaces were
explicitly detached; test session cleanup is targeted and preserves all prior
sessions. No collection, pin, shared-configuration or preference write occurred.

Evidence is in `verification/topology-login-preview/`: `backup.json`,
`migration.json`, `installed.json`, `browser.json`, `session-cleanup.json`,
`verified-final.json` and 24 screenshots. The earlier `installed.json` and
`verified.json` report 14 manifest files in the HTTP-count field; the final
receipt separates the 12 actually fetched HTTP files from the two bundled
notices. This is a receipt-count correction only; every public file was checked
in each run. Source and runtime content did not change during that correction.
Docker/protected-account operations used reviewed escalation due to sandbox
access restrictions; no credential values were printed and no automatic
approval rejection occurred.

Recovery is concrete at
`.secrets/stage7-browser/topology-login-preview/ROLLBACK.txt`: stop only 8449,
explicitly downgrade to `0014_languages` with the frozen migration source and
separate migrator, restore previous Compose and restart that service. Downgrade
revokes remembered sessions. Do not run the old backend against schema 0015.
Full SQL restore, if needed, requires explicit scoped recovery and revocation
of restored web sessions before exposure. Automatic rollback was prepared and
reviewed, **not exercised**; this update required no recovery.

No blocker remains; **8449 is left running with the new login**. This operation
changed deployment artifacts and documentation, not product implementation or
dependencies. Existing full source/integration/migration evidence remains in
the earlier entries; this turn ran candidate and actual-deployment checks.
Full unrelated SSH/live suites and native Ubuntu/Rocky/offline-release
qualification were not repeated for this preview rollout. Stage 08 and any
8445 deployment remain separately authorized work.

## 18 October 2026 - authorized events-view installation on 8445

The user explicitly requested **Deploy** after reviewing the events Filters window, process panes and grouped selected-log pins. Scope is the reviewed events-view package on the retained local installation at https://localhost:8445. The independently updated 8449 topology/login preview is a separate operation; this deployment retains installed schema `0014_languages` and its matching login contract.

Deployment package and preservation work:

- `.cache/deploy_pins.py build` staged `.state/pins-install/backend` from the installed language package, changing only `investigations.py` and `investigation_bundles.py` to the exact frozen preview versions. All other source modules, migration files, dependency lock and runtime scripts remain the installed baseline. The staged OpenAPI equals the already tested frozen pin API, adds exactly six pin routes and retains the old login contract. No migration, image pull or dependency change is performed.
- The frontend is the exact approved cleanup build: `index-CYJqYCh2.js`, `index-A4MUdSNy.css`, matching the successful preview smoke and browser suites. Old hashed frontend assets are retained for already-open pages.
- Preflight verified the existing pinned image, read-only root/source, UID/GID 10001, dropped capabilities, no-new-privileges, single ASGI worker, loopback 8445 binding, runtime SELECT/INSERT/UPDATE/DELETE-only database grants, original configuration/vault, and **zero active historical/live captures**. Installed data has 54 historical jobs and three inactive live-session records.
- Protected consistent backups are under `.secrets/pins-install/`: a **194,663,366-byte compressed SQL backup**, all **899 raw-cache files / 230,872,292 bytes**, ownership/mode manifests, the `/var/lib/system-inspector` vault-state archive, original Compose/configuration and separate vault-key copy. The existing persistent cache bind is retained. Vault runtime state was copied with exact content/owner/mode validation into `system-inspector-pins-install-state`; temporary `/tmp` request staging remains temporary. No SQL restore is performed.
- Forty-nine tables are snapshotted; all **44 stable table counts and checksums** must match, including users, preferences, settings, topology, capture metadata/events, saved analyses and bookmarks. Auth/audit/page workspace/query-cursor/download-grant tables are explicitly volatile. File content and ownership/mode checks cover the entire retained cache and vault state.

Preserved corrected checks and recovery:

- First cutover attempt completed its SQL/cache/state backups and consistency checks, then the helper hit a `TypeError` while recording the backup receipt: `passed` was supplied twice. This occurred before the new package was installed. The automatic rollback successfully restarted the previous backend/frontend using the preserved state volume; **no database restore or data change** occurred. Its receipt remains `deployment-automatic-rollback.json`.
- Fixed the receipt writer to merge an existing `passed` field. A focused local helper check verifies receipt creation and refusal to overwrite prior evidence. The resumed phase revalidates all stable data, cache/state and all backup checksums before reusing the completed backup; previous receipts remain intact.
- A retry then stopped before cutover because the independent topology/login preview on 8449 was recreated concurrently. Read-only diagnosis confirmed unchanged 8445 database/cache/state/configuration/operational counts and old assets. The changed container's labels identify **stage7-browser.compose.local.yaml**, not the 8445 override, and its source is the separate topology/login preview. Recorded only that observed preview identity in `deployment-concurrent-preview-update.json`; all other service identities remain strict. This deployment never restarts or modifies the separate preview. Original preflight evidence is preserved.
- The guarded retry keeps stop inside its recovery block. Old-backend rollback is allowed only before new personal analysis writes, after stable checksum comparison. After any new `pin_groups` state exists, frontend-only rollback retains the compatible new backend so group metadata remains readable. The explicit recovery notes warn against starting the old strict workspace model over new pin state; full database/cache restore is a separate authorized recovery and must revoke restored sessions before exposure.

Commands and phase evidence so far: `python .cache/deploy_pins.py build`, `prepare`, `deploy` (receipt failure with successful automatic rollback), and `retry-after-backup` (strict concurrent-preview guard, then authorized retry). Reviewed local Docker/backup operations use escalation; no automatic-approval rejection occurred. Helpers inspect hashes/counts/metadata without printing credentials or raw data. Exact build, preflight, backups, independent preview observation and retry checks are in `verification/pins-install/deployment-*.json`.

Cutover result: **PASS**, `verification/pins-install/deployment-installed.json`. The installed runtime uses the reviewed pin backend/frontend, remains on `0014_languages`, passes verified TLS/readiness and rejects unauthenticated WebSocket upgrade with HTTP 403. All 44 stable table counts/checksums, accounts/preferences/settings/topology/analyses, 899 cached files with their metadata, configuration and vault match the backup. Other service identities match the separately recorded retry baseline; the 8444 application is unchanged throughout. The external 8449 preview update is recorded explicitly rather than attributed to this deployment.

Actual-installed browser verification: pinned repository Node ran `.cache/verify_pins_install.mjs` with reviewed access to the existing protected Stage 03 synthetic accounts. **PASS on the first installed-browser attempt, 14.063 seconds**. Receipt: `verification/pins-install/deployment-browser-20261018T153234850Z.json`.

- Administrator in English and Inspector in Polish, both light/dark at 1280x720 and 1920x1080; exact real HTTPS/browser asset hashes with no source substitution. Each role reopened its own existing synthetic capture: 20 cached matches across five processes.
- Verified Filters bounds/form, individually removable duplicate literal filters and Cancel; process labels/hover IDs; merged/split layout with stacked/2/3/4 columns, absent redundant pane text, Rows/Viewport at the right; click/Space/Enter selection and context eye; one shared Pin description dialog cancelled without saving; duplicated pages in the same context have independent selections and workspace IDs.
- Two empty-selection POST /pins probes return 422, confirming the installed group API without creating analysis or bookmarks. Successful grouped persistence/atomicity was already verified in the predeployment real MariaDB/browser suites against these exact two backend modules.
- Four fresh smoke workspaces created and detached, 12 retained queries and two retained contexts. No collection/SSH/target requests, WebSocket attempts, preference/configuration/analysis writes, saved pin, global logout, external requests or page errors. Existing catalogue/topology/live/history/workspace/bookmark/preference and raw-query digests are unchanged before/after. The browser contexts are closed.
- Twenty-four explicit authenticated captures are in `verification/pins-install/deployment-screenshots/20261018T153234850Z/`. Visually inspected the English light Filters window, Polish light shared Pin description and Polish dark full-screen results/footer; selected logs, labels, controls and right-aligned footer render correctly. Password fields were cleared and no traces/video were recorded.

Final post-browser audit: `python .cache/deploy_pins.py verify` **PASS**, `verification/pins-install/deployment-verified.json`. It rechecks all stable data, the full cache/state, runtime safety, TLS/assets and other service identities, and validates the actual two-role smoke receipt plus helper/approved-manifest hashes. The installed application is left running for review. `git -c core.safecrlf=false diff --check` passes. README documents the installed events slice separately from the newer 8449 remembered-login preview. No Stage 08 release or unrelated implementation/infrastructure work is claimed.

## 18 October 2026 — Copy a saved connection into a new profile

User-requested scope: add **Copy** to the connection view and open creation with
the current saved profile details. This is a source/UI follow-up to Stage 07;
no deployment or Stage 08 work is authorized by this request.

Changed files and behavior:

- `frontend/src/components/SystemWorkspace.tsx`: Administrator connection-list
  Copy action and page-local source snapshot for the existing editor.
- `frontend/src/components/TopologyEditor.tsx`: Copy in Edit connection opens
  Add connection with the saved name, host, port, username, credential reference,
  jump route and log roots. The generated stable ID is new and editable; saved
  profile values remain distinct from an existing edited item. Normal save uses
  the current system's existing revision-checked topology API. Opening/cancelling
  changes nothing. Credential references retain their meaning; no password is
  read or copied into the browser, and trust/approval records are not duplicated.
- `frontend/src/i18n/topology.pl.ts`: bundled Polish Copy/accessibility labels
  and unique-name guidance. Existing per-system name uniqueness is preserved;
  the name is initially identical, with a prompt to choose a unique one to save.
- `frontend/e2e/connection_copy.spec.ts`: two real local MariaDB/browser cases
  cover Administrator copy/cancel/save and Inspector restrictions. Coverage
  includes direct and jump profiles, empty/multiple roots, duplicate stable-ID
  errors, unchanged source/server assignments and another system, absent new
  host-key approval, same-context independent workspaces/drafts, and Polish Copy.
  Test-created systems are archived and original preferences restored at cleanup.
- `frontend/README.md`, `docs/06_UI_UX.md`, `docs/12_TRACEABILITY.md` and this
  status record document behavior and R13/R34/R39/R49 evidence. Existing unrelated
  working-tree changes are preserved.

Commands actually run from the repository root:

```powershell
backend/.venv/Scripts/python.exe scripts/frontend.py build
backend/.venv/Scripts/python.exe scripts/frontend.py lint
backend/.venv/Scripts/python.exe scripts/frontend.py test
backend/.venv/Scripts/python.exe scripts/frontend.py typecheck
$env:INSPECTOR_E2E_URL='https://localhost:8449'
$env:INSPECTOR_E2E_ACCOUNTS=Join-Path (Get-Location) '.secrets/stage7-browser/accounts.json'
$env:INSPECTOR_E2E_REPORT_STAGE='stage-7'
$env:INSPECTOR_E2E_REPORT_NAME='browser-connection-copy'
backend/.venv/Scripts/python.exe scripts/frontend.py e2e connection_copy.spec.ts
git -c core.safecrlf=false diff --check
```

Results: build/typecheck/lint **PASS**; generated API consistency and **17/17**
frontend unit cases **PASS**. The final browser run passes **2/2 in 7.1 seconds**,
with zero skips, unexpected cases, flaky cases or page/external-request errors.
Report: `verification/stage-7/browser-connection-copy.json`. Build was repeated
after adding the unique-name guidance, and includes final test TypeScript checks.
The existing Vite large-chunk advisory remains non-fatal.

Earlier attempts are preserved, rather than counted as successful:

- `browser-connection-copy-sandbox-denied.json`: both cases could not read the
  protected synthetic-account file (`EPERM`). The reviewed escalated test command
  subsequently obtained that fixture access without printing credentials; no
  automatic-approval rejection occurred.
- `browser-connection-copy-selector-attempt.json` and
  `browser-connection-copy-textarea-attempt.json`: Inspector passed; Administrator
  stopped at exact `getByLabel` selectors whose DOM labels include select/textarea
  content. Switched those two assertions to exact accessible role/name locators;
  the expected values and behavior assertions remain unchanged.
- `browser-connection-copy-name-attempt.json`: Inspector passed; the save attempt
  correctly hit existing backend duplicate-name validation. Added visible guidance
  to the copied draft and changed the save test to supply a distinct name. No
  domain or backend validation rule was relaxed.

Four authenticated screenshots at light/dark × 1280×720/1920×1080 are under
`verification/connection-copy/screenshots/`. Visually inspected the light 1280
and dark 1920 captures: prefilled fields, target system, new ID and name guidance
render correctly; the smaller modal scrolls to its remaining fields/actions.
The browser uses `serveBuiltAssets` to substitute this build only within its test
context on the existing isolated synthetic 8449 fixture. No running application's
assets/backend were installed or restarted. No SSH/collection/live-start request,
production host, infrastructure change or push was involved.

Blockers: none for this source change. Deployment remains a separately authorized
action. Next stage remains Stage 08 offline-release qualification; this follow-up
does not claim that stage or broader release gates are complete.

## 18 October 2026 — Connection Copy deployed to 8449

The explicit **Deploy to 8449** instruction authorized installing the reviewed
connection-copy frontend on the retained synthetic preview only. The deployment
is complete and **https://localhost:8449 is left running**. Refresh existing
pages to load the new controls. Ports 8444/8445 and Stage 08 are unchanged.

Deployment and preservation:

- `.cache/deploy_connection_copy_preview.py build` staged
  `.state/stage7-browser/connection-copy-preview/web` from the immutable existing
  web package and exact tested `frontend/dist` output. The current JS is
  `index-0Fov6-Er.js`, CSS `index-A4MUdSNy.css`; all prior hashed assets remain
  available. The manifest contains 15 files: 13 public HTTPS files and two
  bundled license notices. The successful source browser receipt and current
  source/backend hashes are frozen in the build record.
- Read-only preflight validated the exact synthetic 8449 service/database,
  schema `0015_remember_login`, loopback port, current frozen backend, runtime
  security and zero active historical/live captures. Deployment saved the exact
  previous Compose, table snapshot and state/cache manifests under protected
  `.secrets/stage7-browser/connection-copy-preview/`.
- Only the 8449 service gained a read-only nested web overlay. Only
  `stage7-browser` was stopped/recreated, using `--no-deps --pull never`; its
  backend, image, accounts/configuration, schema and persistent volumes remain
  unchanged. All other container/image/start/restart identities match preflight,
  including 8444/8445 and the existing SFTP fixture.
- Installation and final verification preserve **43 stable table counts and
  checksums**, the explicit schema revision and complete state/cache content,
  ownership and mode manifests. Configuration/vault/backend hashes and runtime
  restrictions match. The final session cleanup also verifies the original
  web-session column digest unchanged. Verified TLS/readiness and all **13 public
  HTTPS asset hashes** pass.

Commands actually run (`PY` is `backend/.venv/Scripts/python.exe`; `NODE` is
`.toolchains/node-v24.22.0-win-x64/node.exe`):

| Command | Result |
|---|---|
| `PY -m py_compile .cache/deploy_connection_copy_preview.py` | PASS. |
| `NODE --check .cache/verify_connection_copy_8449.mjs` | PASS. |
| `PY .cache/deploy_connection_copy_preview.py build` | PASS: exact existing tested build staged, no Docker/runtime change. |
| `PY .cache/deploy_connection_copy_preview.py inspect` | PASS: read-only scoped preflight, 49 tables. |
| `PY .cache/deploy_connection_copy_preview.py deploy` | PASS: frontend-only install, preservation and served-asset verification. |
| `NODE .cache/verify_connection_copy_8449.mjs` | Final PASS: actual served assets, Copy from list/edit, full saved fields/fresh editable IDs, cancel, independent same-context workspaces/drafts and Inspector restrictions. |
| `PY .cache/deploy_connection_copy_preview.py cleanup` | PASS after each smoke attempt: only its recorded authentication sessions removed, original sessions preserved; no global logout. |
| `PY .cache/deploy_connection_copy_preview.py verify` | PASS after final browser cleanup: stable tables, state/cache, backend/config/schema, other services, TLS and served assets. |
| `git -c core.safecrlf=false diff --check` | PASS. |

Actual-served browser evidence is `verification/connection-copy-preview/browser.json`.
The final run uses two synthetic accounts, creates three distinct page workspaces,
explicitly detaches those three through acknowledged owner/CSRF-checked HTTP, and
also retires the preceding attempt's three recorded workspaces. Both test-created
authentication sessions are then removed by exact hash/user ID. All copied drafts
and unsaved edits are cancelled; there are no configuration, preference, SSH,
collection or live-start writes, external requests, page errors or global logout.
Theme changes are DOM-only for visual checks. Ten actual-served captures cover
list/edit Copy and Add connection in light/dark, including 1280×720 and 1920×1080.
Visually inspected the light connection list, dark editor and dark 1280 copied
form. Source build/lint/typecheck/17-unit/2-browser evidence from the preceding
entry applies to the identical artifact; those unchanged source suites were not
unnecessarily repeated during deployment.

Retained smoke harness corrections:

- `browser-path-attempt.json`: first smoke checked `/index.html`, which is not
  a published document route. Corrected the test to fetch `/`; deployed assets
  already passed the independent TLS checker. The one smoke session was removed;
  receipt `session-cleanup-path-attempt.json`.
- `browser-allowlist-attempt.json`: Copy/role/independent-draft checks and ten
  screenshots passed, but the strict read-only browser allowlist blocked the
  hidden HistoricalViewer's two existing list GETs on each of three pages.
  Added only `/investigations` and `/bundle-investigations` GET paths, then
  reran successfully. Its two sessions were removed and its three recorded
  workspaces were explicitly retired in the successful next run. Receipt
  `session-cleanup-allowlist-attempt.json` is preserved. No application code or
  security policy changed to accommodate these harness fixes.

Deployment helpers were independently reviewed before cutover. Docker/protected
fixture operations used reviewed escalation; no credential values were printed
and no automatic-approval rejection occurred. Other receipts are `build.json`,
`preflight.json`, `installed.json`, `session-cleanup.json` and `verified.json`
under `verification/connection-copy-preview/`.

Recovery is concrete in
`.secrets/stage7-browser/connection-copy-preview/ROLLBACK.txt`: run the guarded
helper's `rollback` command to restore the saved Compose and recreate only 8449
against the same backend/schema/data. The previous frozen package is untouched;
no schema downgrade or SQL restore is needed. Automatic rollback was prepared
and reviewed, not exercised. Root/frontend README and traceability now describe
the actual deployment. No blocker remains; Stage 08 is still the next separate
release gate.

## 18 October 2026 — Pin editing and independent collection/display ranges

Implemented the requested source follow-up; no retained application was deployed,
restarted or migrated. Prior dirty changes were preserved. No new database
migration or dependency is needed for this follow-up.

- Pins are compact description/View rows. View shows one terminal block per
  process and editable description with Save/Cancel/Modify and Delete pin.
  Description-only operations preserve unrelated table marks. Pinned text and
  provenance survive source expiry.
- Modify restores anchors into the event table. Pin then asks whether to update
  or create a new pin. Atomic revision-checked replacement preserves group ID
  and creation time; failed lookups, limits, scope or revision checks preserve
  the existing group. Historical and offline investigations support both paths.
- Keep one stable investigation tools component across collection loads/changes,
  clearing stale metadata and resetting bundle-transfer state per investigation.
  Completion refreshes workspace availability; available partial captures may
  Modify. Browser assertions verify one tools panel after operations/reloads.
- Visible collection UTC bounds and pending process selection are independent
  of display UTC/literal filters. Filter scope uses the captured process list,
  including empty sources. Filtering neither starts collection nor invalidates
  a next-collection plan. Reopen restores original collection bounds separately
  from saved display state.
- Timestamped queries intersect exact integer UTC `[from,to)` acquisition and
  display bounds. Original bytes, out-of-range source context and unknown-time
  diagnostics remain retained. New bundle 1.0 exports preserve optional paired
  `origin.collection_from`/`collection_to` through import/list/query/correlation/
  reexport. Older bundles retain their existing replay semantics.

Changed files for this follow-up: HistoricalViewer, HistoricalFiltersDialog,
InvestigationTools, InvestigationPinDialog, new PinLogPreview, investigationPins,
styles and Polish dictionaries; new pin helper tests and collection_ranges
browser spec, event_pins spec, shared browser helpers and historical/events/
investigation/SSH/language/UI-acceptance setup callers; backend history,
investigations and investigation_bundles modules, history/bundle/grouped-pin
integration and bundle unit tests; regenerated OpenAPI, frontend API types and
bundle schema; README/frontend README and domain/API/UI/traceability docs.

Commands actually run (`PY` = `backend/.venv/Scripts/python.exe`; repository root
unless specified, `PYTHONPATH=backend/src` for backend checks):

| Command | Result |
|---|---|
| `PY -m pytest backend/tests/unit -q -rs -p no:cacheprovider` | PASS: 838, four Windows skips below. |
| `PY .cache/verify_grouped_pins.py` | PASS: first focused MariaDB run, 24/24. |
| `PY .cache/verify_pin_workflow.py` | PASS: final fresh-schema Linux/MariaDB regression, 39/39, zero skips, 105.41 s. |
| `PY -m mypy src` (cwd backend, same venv) | PASS: 37 source files. |
| `PY -m ruff check --config backend/pyproject.toml` + the seven changed backend source/test files | PASS. |
| `PY -m ruff format --check --config backend/pyproject.toml` + the same seven paths | PASS. |
| `PY -m inspector.cli openapi --output backend/openapi.json` with `INSPECTOR_CONFIG_FILE=examples/deployment-policy.example.yaml` | PASS, no lifespan/remote work. |
| `PY scripts/frontend.py api:generate` and `api:check` | PASS: types match. |
| `PY scripts/frontend.py lint`, `typecheck`, `test`, `build` | PASS: 20 Node tests and bundled build; existing Vite chunk-size advisory. |
| `PY tools/validate_schemas.py` | PASS: 20 schemas, 102 positive/36 negative validations. |
| `PY tools/validate_package.py` | PASS. |
| `PY -m unittest discover -s tests/package -q` | PASS: 128 tests, nine existing gated skips. |
| `PY .cache/pin_range_browser_check.py prepare`, `migrate`, `start`, `stop` | PASS: new disposable localhost:8450 fixture only, schema0015, DML app, generated accounts, synthetic local-demo logs. Corrected seeding succeeded through `.cache/pin_range_diagnose.py`. |
| `PY scripts/frontend.py e2e event_pins.spec.ts collection_ranges.spec.ts` | Final PASS: 6/6 in 27.0 s. |
| `PY scripts/frontend.py e2e event_pins.spec.ts --grep 'Modify restores'` | PASS: strengthened same-process grouping/availability/update/copy case, 1/1 in 7.3 s. |
| `git -c core.safecrlf=false diff --check` | PASS. |

Ruff's exact paths were `backend/src/inspector/{investigations,investigation_bundles,history}.py`,
`backend/tests/integration/{test_grouped_pins,test_history,test_investigation_bundles}.py`
and `backend/tests/unit/test_investigation_bundles.py` (expanded paths passed to
the commands). Browser environment was `INSPECTOR_E2E_URL=https://localhost:8450`,
`INSPECTOR_E2E_ACCOUNTS=C:\_Projects\system-monitor\.secrets\pin-range-check\accounts.json`,
`INSPECTOR_E2E_REPORT_STAGE=stage-7`, report names `pin-range-followup-final` and
`pin-range-same-process`. Current built assets were substituted within the test
context; no retained frontend was replaced. Same-context duplicate pages use
distinct server workspaces and independent selection/filter/acquisition state.
No external requests or browser errors occurred.

Reports: `verification/stage-7/pin-range-followup-final.json`,
`pin-range-same-process.json`; final database evidence:
`verification/pin-workflow/pin_flow_a974533f.log` and its exact-command JSON.
Visually inspected light/dark pin popups at 1280x720 and 1920x1080, the two-line
same-process terminal, and collection controls in both themes. Captures are in
`verification/pin-range-check/screenshots/` and
`verification/stage-7/screenshots/collection-ranges-*`.

Earlier failures are preserved: first browser run passed 5/6 and exposed stale
partial availability hiding Modify after completion. The metadata refresh and
partial-data eligibility fix pass the full rerun and stronger grouping case.
A first schema suffix exceeded the helper's 20-character maximum and was
refused before provisioning. Dedicated fixture setup also encountered
unsupported Compose `run --pull` syntax and a nested read-only script mount;
only the new test helper/override was corrected.

Four Windows unit skips: privileged history-retention symlink creation, Linux
open-handle rename behavior, POSIX SSH permissions and synthetic SSH-file
symlink creation (`WinError 1314`). The 39-case integration suite runs on Linux/
MariaDB with zero skips. Browser data is synthetic local-demo; this does not
requalify SSH transport, the full Stage 07 matrix or Stage 08 offline release.
The dedicated 8450 service is stopped (exit0); its database is retained for
review. Cleanup verified 8445/8449, MariaDB and existing SSH fixtures still
running. No implementation blocker remains. Next: separate deployment
authorization if requested, or the existing Stage 08 release gate.

## 18 October 2026 — Authorized pin/range deployment to 8449

User authorization: **“Apply changes to 8449 instance.”** The verified pin
editing and independent collection/display-range follow-up is now served at
**https://localhost:8449**. Refresh existing pages. Matching frontend/backend
are installed; schema remains `0015_remember_login`. Accounts, configuration,
saved investigations and captured data are preserved. 8445/8444 are unchanged.
This does not complete or begin the separate Stage 08 release gate.

Preparation and cutover:

- Independently reviewed the guarded deployment and installed-browser helpers.
  A new frozen package has 74 backend files, changing only `history.py`,
  `investigations.py` and `investigation_bundles.py`. The merged web directory
  has 17 files, including the exact browser-tested five-file build and retained
  older hashed assets. Existing dependency metadata, migrations and other
  Python modules match the preceding deployed package.
- Read-only preflight verified the exact loopback8449 service, schema0015,
  runtime security, expected backend/web mounts, no active capture/subscription
  work, no inventory uploads/previews or raw staging, and current served hashes.
  The target had 49 tables, 113 historical jobs, 21 saved investigations and 18
  bookmarks; these stable contents remain unchanged.
- Stopped only `stage7-browser` and made a consistent **10,498,617-byte SQL
  backup**, state/cache archives and exact Compose recovery files under protected
  `.secrets/stage7-browser/pin-range-preview/`. Before/after stopped-service
  snapshots and state/cache manifests match. Backup manifests cover four state
  and 1,811 cache entries, including ownership/mode and content checksums.
- Replaced only that service's two read-only backend/frontend mounts; the
  integration service and other Compose settings are unchanged. Recreated only
  8449 with `--no-deps --pull never`. No migration, image/dependency download,
  target-host connection or database/cache restore was performed.
- Installation and final verification preserve all **43 stable table counts and
  checksums**, schema, full state/cache manifests, configuration and original
  login identity/CSRF/auth-version/deadline/Remember me fields. Normal original
  session activity may only increase. Other containers retain identical IDs,
  image IDs, start times and restart counts, including 8445/8444 and SSH fixtures.
  Nonroot/read-only/capability/secret-mount restrictions remain intact. Verified
  TLS/readiness, all **15 public HTTPS file hashes** and the installed backend's
  optional pin replacement/bundle acquisition-bound contracts pass.

Commands actually run (`PY` = `backend/.venv/Scripts/python.exe`, `NODE` =
`.toolchains/node-v24.22.0-win-x64/node.exe`; repository root):

| Command | Result |
|---|---|
| `PY -m py_compile .cache/deploy_pin_range_preview.py` | PASS. |
| `NODE --check .cache/verify_pin_range_8449.mjs` | PASS; targeted helper lint also passes. |
| `PY .cache/deploy_pin_range_preview.py build` | PASS: frozen existing tested artifact, no Docker/runtime mutation. |
| `PY .cache/deploy_pin_range_preview.py inspect` | PASS: read-only preflight. |
| `PY .cache/deploy_pin_range_preview.py deploy` | PASS: consistent backups, scoped cutover, installation/preservation verification. |
| `SI_VERIFY_PIN_RANGE_8449=1 NODE .cache/verify_pin_range_8449.mjs` | PASS: actual served UI/assets, retained data and independent same-context pages. |
| `PY .cache/deploy_pin_range_preview.py cleanup` | PASS: only the one recorded temporary smoke login removed; original sessions preserved. |
| `PY .cache/deploy_pin_range_preview.py verify` | PASS after browser cleanup: data/cache/config/schema, original sessions, runtime contract, TLS/assets and other services. |
| `git -c core.safecrlf=false diff --check` | PASS. |

Actual-served browser evidence is `verification/pin-range-preview/browser.json`.
The smoke uses the generated Inspector account and existing retained evidence
only in `stage7-fixture-a`. It checks Remember me remains visible/unchecked,
one investigation tools panel, separate acquisition/display controls, captured
process choices despite editing the next collection, three retained queries,
and distinct workspaces in two pages of one browser context. It opens the new
terminal pin popup and cancels it. The inspected synthetic history did not have
grouped pins, so the existing-group Modify/update/create branch remains covered
by the preceding exact-artifact disposable-browser and MariaDB suites; the
installed smoke deliberately creates no saved content. No asset substitution,
external requests, browser errors, SSH/collection/live starts, preference/config
writes or global logout occurred. Both created workspaces were explicitly
detached before deleting only its recorded authentication session.

Six actual-served screenshots cover the selected-pin popup and investigation
controls in light/dark, including 1280x720 and 1920x1080. Visually inspected the
dark pin popup and light1280 investigation screen. Existing source verification
(6 browser cases plus strengthened grouping case, 39 MariaDB cases, 838 backend
and 20 frontend unit passes, lint/types/build) applies to this identical frozen
artifact; unchanged suites were not rerun during deployment. Receipts are
`build.json`, `preflight.json`, `backup.json`, `installed.json`, `browser.json`,
`session-cleanup.json` and `verified.json` under
`verification/pin-range-preview/`.

One preparation-only build attempt stopped safely before staging because the
previous frozen package contains no `uv.lock`. The helper now verifies unchanged
`pyproject.toml` and freezes the current lock hash; no dependency or runtime
change was involved. Independent review also separated old retained asset hashes
from current browser-loaded hashes and checks the new API through installed
runtime introspection rather than an older static OpenAPI snapshot. No cutover
or installed-browser check failed. Reviewed sandbox escalation was used for
local Docker/protected fixture operations; no credentials were printed and no
automatic-approval rejection occurred.

Recovery: `.secrets/stage7-browser/pin-range-preview/ROLLBACK.txt` documents
`PY .cache/deploy_pin_range_preview.py rollback`, which validates the retained
artifacts, restores the exact previous Compose and recreates only8449. It needs
no schema downgrade or SQL restore; old source/assets and current data remain.
Later bundles using the new optional origin bounds require the updated backend;
a future source rollback must account for later new-format imports rather than
discarding them. The read-only smoke created no such data. Automatic rollback
was prepared and reviewed, not exercised. No deployment blocker remains;
8449 is left running. Next gate remains the separate Stage 08 release scope.

## 18 October 2026 — Live monitor explanation and process labels (source only)

User reported gap/error notices after visiting Live monitor and requested
`server: process` references. Read-only lifecycle review confirms opening the
tab lists sessions/usage and does not create capture. Explicit Monitor (also
the topology Monitor action) creates it; an existing monitor stays mounted and
continues while another workspace section is visible. The screenshot alone
cannot establish the originating action or red error code. The old selection
summary said monitoring whenever any session existed, including ended sessions.
`TRANSPORT_DISCONNECTED` covers retryable source reads, including unavailable
files, rather than proving a network failure or process-health problem. The
red generic text discarded backend code-only guard/recording errors.

Changed `frontend/src/components/LiveViewer.tsx`: name-based process choices,
per-process filter labels, panes, status/details, detached monitors and copied
rows; previous-monitor summary after termination; readable gap explanation
and affected process when validated against the owned selection; backend error
code alongside the generic stream error. Updated bundled Polish strings in
`frontend/src/i18n/investigation.pl.ts`. Adjusted affected selectors in existing
`frontend/e2e/live.spec.ts` and `stage7_soak.spec.ts`, including detached-monitor
identity checked through its title attribute. Updated `docs/06_UI_UX.md` and
`docs/12_TRACEABILITY.md`. Preserved unrelated existing dirty work.

Added five explicitly TEST-ONLY `frontend/e2e/live_notices.*` files: real-component
harness, intercepted HTTP/WS regression cases and isolated Playwright/Vite
lifecycle. Vite uses `configFile: false`, loopback port5189 and no API proxy;
the default installed-application suite skips these cases. These are component
browser tests, not new MariaDB/SSH integration evidence. Tests cover no start
on visit/checkbox/tab return, one explicit start and continued existing capture,
all friendly labels/copy, process-attributed gaps, preserved error codes and
ended-session controls/summary. Inspected the full-page light/dark captures.

Commands actually run, from `frontend`, with
`.toolchains/node-v24.22.0-win-x64` prepended to PATH for npm:

| Command | Result |
|---|---|
| `../.toolchains/node-v24.22.0-win-x64/npm.cmd test` | PASS: API generated types match; 20/20 frontend unit tests, including complete bundled translation keys/placeholders. `verification/live-monitor-notices/unit.log`. |
| `../.toolchains/node-v24.22.0-win-x64/npm.cmd run lint` | PASS, including final browser harness/setup. `verification/live-monitor-notices/lint-final.log`. |
| `../.toolchains/node-v24.22.0-win-x64/npm.cmd run build` | PASS: TypeScript no-emit and production Vite build. Existing >500kB chunk warning; exit0. `verification/live-monitor-notices/build-final.log`. |
| `../.toolchains/node-v24.22.0-win-x64/node.exe node_modules/@playwright/test/cli.js test --config e2e/live_notices.playwright.config.ts` | Final PASS: 3/3, zero skips/flaky/unexpected, 3.554s reported duration with clean automatic shutdown. `verification/stage-7/browser-live-notices-test-only.json`. |
| `git diff --check -- frontend/src/components/LiveViewer.tsx frontend/e2e/live.spec.ts frontend/e2e/stage7_soak.spec.ts docs/06_UI_UX.md docs/12_TRACEABILITY.md progress/STATUS.md` (repository root) | PASS. |

Earlier browser assertions also passed, but Playwright's Windows webServer
child teardown hung; stopped only the test's Vite child and replaced that
harness lifecycle with in-process startup/cleanup. The final rerun above exits
without intervention. Independent review found the stale detached-monitor text
assertion, which was corrected before the final lint/build. No product tests
or assertions were removed or weakened.

Screenshots: `verification/stage-7/screenshots/live-notices-test-only-light.png`
and `live-notices-test-only-dark.png`. No real credentials or monitored hosts
were accessed. No retained application, backend, database, schema, installation
or infrastructure was changed. Full Stage05 SFTP/MariaDB/browser and Stage07
soak suites were not rerun: this follow-up changes frontend presentation only,
and those suites require separately generated running services and a prolonged
workload. No source-verification blocker remains. Deployment is not authorized
by this request and was not performed; Stage08 remains the next separate gate.

## 18 October 2026 — Match live-event presentation to historical logs (source only)

User request: **“Implement the same style of presenting events in live monitoring
as we have in logs.”** Live monitoring now shares the historical table's 20px
rows, 12px/18px monospace font, minimal cell padding, separate UTC time/process/
host/log-entry columns, sticky headings, hover treatment and horizontal
scrolling. Merged and separate live panes use shared presentation components;
historical context eyes, column visibility and row-selection behavior remain
in their existing viewer. Long log text remains selectable and rendered as text.
The distinct late-arrival label precedes the displayed message, retaining its
visibility in compact rows. Unknown timestamps stay in the diagnostic lane.

Changed files for this follow-up:

- Added `frontend/src/components/LogTablePresentation.tsx` with shared row height,
  column geometry, headings and metadata/message cells. Updated
  `HistoricalLogTable.tsx` and `LiveViewer.tsx` to use it; removed superseded live
  table rules from `frontend/src/styles.css`.
- Updated live seed/resize, visible-row, follow-threshold and scroll-anchor
  calculations together. Viewports subtract the measured sticky-header height;
  anchors retain project/event identity. Live pause/resume and source controls
  continue using the existing monitor and transport.
- Extended `frontend/e2e/live_notices.spec.ts` and its explicitly test-only
  harness with a real historical table reference, synthetic event updates,
  independent page workspaces and six browser regressions. The dedicated config
  writes new receipts/screenshots under `verification/live-events-presentation/`,
  preserving the earlier three-case evidence. Updated existing real-fixture
  `frontend/e2e/live.spec.ts` viewport assertions to measure row/header geometry
  instead of assuming 30px rows.
- Updated `frontend/README.md`, `docs/06_UI_UX.md` and `docs/12_TRACEABILITY.md`.
  Preserved all pre-existing unrelated working-tree changes.

Commands actually run from the repository root:

| Command | Result |
|---|---|
| `python scripts/frontend.py test` | PASS: generated API types match; all 20 frontend unit tests pass. Final log: `verification/live-events-presentation/unit.log`. |
| `python scripts/frontend.py lint` | Final PASS. `verification/live-events-presentation/lint.log`. An earlier run during unfinished test edits reported the then-unused `Locator` import; the finished helper uses it and the full rerun passes. |
| `python scripts/frontend.py build` | PASS: TypeScript no-emit plus production Vite build. Existing >500kB chunk warning; exit0. `verification/live-events-presentation/build.log`. |
| `python scripts/frontend.py e2e --config e2e/live_notices.playwright.config.ts` | PASS: 6/6, zero skips/flaky/unexpected, 10.5s reported duration; automatic Vite shutdown. `verification/live-events-presentation/browser-test-only.json` and `browser.log`. |
| `git diff --check` | PASS, exit0. Existing LF/CRLF normalization notices for other dirty files; no whitespace errors. `verification/live-events-presentation/diff-check.log`. |

The browser suite compares actual historical/live computed row styles, checks
UTC under America/Los_Angeles, distinct process/host cells, safe long markup-like
text with horizontal pane scrolling and no document overflow, late-arrival and
unknown-timestamp presentation, initial viewport seeds, automatic following,
anchored earlier inserts, display pause with continuing counters, resume/jump,
distinct per-process seed sizes and filter/stop isolation in two pages of the
same browser context. The previous no-automatic-start, friendly-label/copy and
gap/error/terminal regressions also pass. Independent read-only review found no
presentation regression; its stale real-fixture geometry assertion finding was
addressed in `live.spec.ts` before final checks.

Visually inspected `dense-live-light.png`, `dense-live-dark.png` and
`split-live-independent-stopped.png` under
`verification/live-events-presentation/screenshots/`: compact aligned metadata,
readable rows in both themes, visible late-arrival cue, selectable literal text
and independent scroll panes. These captures use synthetic test-only events and
intercepted HTTP/WebSockets. No real credentials, monitored hosts, SSH, retained
application data, database/schema or installation were accessed or changed.

Full backend/MariaDB/SFTP integration and installed-application browser suites
were not rerun: this is a frontend presentation follow-up, verified through real
components with isolated transport fixtures rather than running those separately
provisioned services. No source-verification blocker remains. Deployment was not
requested or performed. Next gate remains separate deployment authorization if
requested, or the existing Stage 08 offline-release scope.

## 18 October 2026 — Authorized live-event frontend deployment to 8449

User authorization: **“Deploy to 8449.”** The verified matching historical/live
event presentation is installed at **https://localhost:8449**. Refresh existing
pages. Only the frontend mount changed; the installed pin/range backend and
schema `0015_remember_login` remain unchanged. Accounts, configuration, existing
sessions, saved investigations and retained cache are preserved. 8445/8444 and
all other containers retain their previous identities, images, start/restart
state. This does not start or complete Stage 08 release qualification.

Preparation and cutover:

- Added guarded local helper `.cache/deploy_live_events_preview.py`, using the
  latest pin/range installation as its baseline. Its new frozen overlay contains
  19 files, including the exact five-file verified build and previous hashed
  assets. Frozen backend and original web directories remain unchanged.
- Read-only preflight verified loopback8449, schema0015, 49 tables, strict runtime
  restrictions, expected read-only mounts, served hashes and no active capture,
  subscriptions, pending sources or inventory staging. An initial sandboxed
  preflight could not access local Docker; reviewed escalation passed. No
  automatic-approval rejection occurred.
- Stopped only `stage7-browser` and retained a consistent **10,760,878-byte SQL
  backup**, matching state/cache archives, private baseline and exact previous
  Compose under `.secrets/stage7-browser/live-events-preview/`. Stopped-service
  snapshots before/after backup match. Manifests cover four state and 1,814 cache
  entries, including content hashes, ownership and modes.
- Replaced exactly one read-only frontend mount and recreated only8449 using
  `--no-deps --pull never`. Backend/configuration mounts, dependencies, images,
  schema and persistent volumes were preserved. No migration, pull, target-host
  connection or restore occurred.
- Installation and final verification preserve all **43 stable database table
  counts/checksums**, schema, state/cache manifests, configuration, original
  authentication identity/CSRF/auth-version/deadline/Remember me fields and other
  containers. Only nondecreasing normal original-session activity is permitted.
  Runtime remains nonroot/read-only with unchanged capability and secret-mount
  restrictions. Verified TLS/readiness and all **17 public HTTPS file hashes**
  pass; all 19 packaged files, including retained notices, match the frozen tree.

Commands actually run from the repository root (`PY` =
`backend/.venv/Scripts/python.exe`, `NODE` =
`.toolchains/node-v24.22.0-win-x64/node.exe`):

| Command | Result |
|---|---|
| `PY -m py_compile .cache/deploy_live_events_preview.py` | PASS, including final rollback/cleanup checks. |
| `NODE --check .cache/verify_live_events_8449.mjs` | PASS; targeted ESLint with `frontend/eslint.config.js` also passes. |
| `PY .cache/deploy_live_events_preview.py build` | PASS: exact frozen tested assets, six-case browser receipt and unchanged installed backend verified, no Docker mutation. |
| `PY .cache/deploy_live_events_preview.py inspect` | PASS with reviewed local-Docker access; initial sandboxed attempt stopped with `SetupError` before mutation. |
| `PY .cache/deploy_live_events_preview.py deploy` | PASS: scoped backups, frontend cutover, HTTPS/assets and preservation verification. |
| `SI_VERIFY_LIVE_EVENTS_8449=1 NODE .cache/verify_live_events_8449.mjs` | Final PASS: actual-served browser/asset verification, independent same-context workspaces and ten captures. First attempt's license-route assumption and correction are preserved below. |
| `PY .cache/deploy_live_events_preview.py cleanup` | PASS: removed only the two recorded test login sessions from both attempts; independently checked created workspaces detached/expired or reaped, and preserved original sessions. |
| `PY .cache/deploy_live_events_preview.py verify` | PASS after cleanup: final backend/schema/database/cache/configuration/original-session/other-service and served-asset checks. |

The installed smoke uses only the generated Inspector account and existing
retained synthetic evidence in `stage7-fixture-a`. It verifies actual loaded
HTML/JS/CSS hashes without substitution; retained historical rows measure20px
with 12px/18px monospace text and UTC under America/Los_Angeles. It opens empty
live merged/split tables with the four shared metadata/message columns, sticky
headings and horizontal scrolling. Two pages in one browser context receive
different server-issued workspaces; changing process selection, layout and
filter drafts in one leaves the other unchanged. It captures both themes at
1280x720 and1920x1080, starts no capture or WebSocket, writes no personal/shared
content or preferences and performs no global logout. Both created workspaces
were acknowledged detached before targeted test-session removal.

Ten screenshots and `browser.json` are under `verification/live-events-preview/`.
Visually inspected installed light historical rows and dark1280 merged live
headers. Actual live-row streaming/follow/anchor/pause remains covered by the
preceding six isolated exact-artifact browser cases; the installed smoke starts
no monitored-source connections and inserts no synthetic DOM rows. Existing
20-unit/type/lint/build evidence applies to the identical artifact; unchanged
backend/MariaDB/SFTP suites were not rerun for this frontend-only installation.

First smoke attempt: all17 existing public assets and the browser-loaded files
matched, then the helper incorrectly requested packaged license files as HTTP
routes. The backend exposes HTML and `/assets`, not `/licenses`. Corrected only
the helper's public-file selection, keeping all packaged notice files and their
hash checks. No product contract or endpoint was relaxed. The first failed
receipt remains `browser-attempt1.json`; final `browser.json` passes with zero
unexpected requests/browser errors. No deployment or preservation check failed.
Independent read-only reviews confirmed frontend-only scope and receipts, and
strengthened rollback to compare preserved DB/auth/cache/configuration and
cleanup to query actual workspace state.

Recovery: protected `ROLLBACK.txt` documents
`PY .cache/deploy_live_events_preview.py rollback`, which restores the exact
previous frontend Compose mount and recreates only8449. It preserves the current
backend/schema/data and requires no SQL restore or schema downgrade. Backups and
previous artifacts remain retained; automatic/manual rollback were prepared and
reviewed, not exercised. No blocker remains. 8449 is left running; the next
separate gate remains Stage 08 offline-release qualification.
