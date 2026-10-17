# Implementation status — version 3

**Current: Stage 03 historical investigation is complete at its review gate.** The local Stage 03 Docker app is running at `https://localhost:8445`. Stage 02 data and the service on port 8444 are retained. The Stage 01 app on port 8443 remains stopped at the user's request; its VM database, SSH tunnel and data are preserved. Exact results and remaining later-stage gates are recorded below. Earlier blockers remain as dated history.

**Starting point: specification package only.** The dated entries preserve the inspection and implementation history.

| Stage | State | Evidence |
|---|---|---|
| 00 — Verify and plan | Complete for the foundation scope | Real toolchain/locks/notices; Linux package checks; plan and traceability |
| 01 — Foundation | Complete | 127 units, 23 VM API tests, 19 Linux DB tests, 10 browser cases, container lifecycle |
| 02 — Topology/config | Complete; review gate | 253 units, 30 Linux DB tests, populated upgrade, topology/foundation browser tests; evidence below |
| 03 — Historical log engine | Complete; review gate | 321 units, 47 Linux DB tests, 17 browser cases, populated upgrade; 20 MiB ingest 9.72 s and warmed query p95 at most 240.307 ms on the recorded development machine |
| 04 — SSH and collection | Not started | — |
| 05 — Live monitoring | Not started | — |
| 06 — Investigation tools | Not started | — |
| 07 — Import and UI completion | Not started | — |
| 08 — Release and hardening | Not started | — |

For each stage record changed files, requirement IDs, exact commands run, actual results, unexecuted checks and reasons, unresolved blockers and the next stage. Keep a distinction between a unit-tested adapter, an SSH integration tested in a local fixture environment, and a deployment verified on a real target OS.


Package handoff baseline: version 3 supplied scope/import contracts and synthetic helpers. Implementation evidence is in the dated entries below. Live-controller/SSH and production Ansible import remain later stages.

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
