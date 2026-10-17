# Implementation status — version 3

**Current: Stage 04 approved SSH historical collection is complete at its review gate.** The updated local Docker app is running at `https://localhost:8445`, with the existing Stage 03 data preserved. Stage 02 data and the service on port 8444 are retained. The Stage 01 app on port 8443 remains stopped at the user's request; its VM database, SSH tunnel and data are preserved. Stage 05 has not started. Exact results and later-stage gates are recorded below; earlier blockers remain as dated history.

The UTC controls and **Additional security measures** follow-ups are now
installed on 8445 at schema `0008_security_setting`. The checkbox defaults to
checked; installation preserved the existing data and security policy. See the
installation entry at the end of this file.

**Starting point: specification package only.** The dated entries preserve the inspection and implementation history.

| Stage | State | Evidence |
|---|---|---|
| 00 — Verify and plan | Complete for the foundation scope | Real toolchain/locks/notices; Linux package checks; plan and traceability |
| 01 — Foundation | Complete | 127 units, 23 VM API tests, 19 Linux DB tests, 10 browser cases, container lifecycle |
| 02 — Topology/config | Complete; review gate | 253 units, 30 Linux DB tests, populated upgrade, topology/foundation browser tests; evidence below |
| 03 — Historical log engine | Complete; review gate | 321 units, 47 Linux DB tests, 17 browser cases, populated upgrade; 20 MiB ingest 9.72 s and warmed query p95 at most 240.307 ms on the recorded development machine |
| 04 — SSH and collection | Complete; review gate | 463 Linux units (one platform skip), 89 real Linux DB/SSH tests, 23 distinct browser cases, populated upgrade and inspected UI; final evidence below |
| 05 — Live monitoring | Not started | — |
| 06 — Investigation tools | Not started | — |
| 07 — Import and UI completion | Not started | — |
| 08 — Release and hardening | Not started | — |

For each stage record changed files, requirement IDs, exact commands run, actual results, unexecuted checks and reasons, unresolved blockers and the next stage. Keep a distinction between a unit-tested adapter, an SSH integration tested in a local fixture environment, and a deployment verified on a real target OS.


Package handoff baseline: version 3 supplied scope/import contracts and synthetic helpers. Implementation evidence is in the dated entries below. Live controllers/following and Ansible import remain later stages.

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
