# Implementation status — version 3

**Current: Stage 01 foundation is complete and verified. Stop before Stage 02.** The approved VM app runs at `https://localhost:8443`; independent Linux Docker integration, runtime and offline lifecycle checks pass. Exact results and remaining later-stage gates are recorded below. Earlier blockers remain as dated history.

**Starting point: specification package only.** The dated entries preserve the inspection and implementation history.

| Stage | State | Evidence |
|---|---|---|
| 00 — Verify and plan | Complete for the foundation scope | Real toolchain/locks/notices; Linux package checks; plan and traceability |
| 01 — Foundation | Complete; review gate | 127 units, 23 VM API tests, 19 Linux DB tests, 10 browser cases, container lifecycle |
| 02 — Topology/config | Not started | — |
| 03 — Historical log engine | Not started | — |
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
