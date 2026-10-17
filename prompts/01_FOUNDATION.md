# Stage 01 — MariaDB, role-aware and themed foundation

Read AGENTS.md. Implement this stage only unless a higher-level prompt explicitly authorises more.

## References

Read documents 02, 03, 05, 06, 07, 13 and 14; deployment and RBAC contracts; both assets/themes reference images and tokens; examples/deployment/README.md.

## Task

Create the real Python/FastAPI and React/TypeScript workspaces with compatible recorded dependency versions, actual lockfiles, generated API types, SQLAlchemy asyncio/asyncmy repositories and Alembic migrations. MariaDB is the only operational database. Launch a disposable pinned official MariaDB Docker image, adapt/verify supplied initialization and Compose recipes, await readiness and test database persistence, exact types and separate runtime/migration grants. Never install on a production server or connect to a production database without separate authorization. When Docker is unavailable, record a blocker rather than substituting SQLite or reporting success.

Implement validated managed/external database configuration with host/port/schema/user/password-file and TLS/pool settings. Build a single-worker lifespan with locked supervisor ownership and fail-closed readiness. Separate migrations from serving; app receives no root/migration credential. Implement local Administrator and Inspector accounts, one-time protected first-Administrator bootstrap, secure sessions/CSRF, centralized deny-by-default authorization, owner assignment/checks, account lifecycle, last-Administrator transaction guard, auth_version and redacted audit. No public registration, universal seed password or UI-only authorization. Test actual routes against both roles including forbidden writes.

Build the responsive web shell in Light — Cool Slate and Dark — Graphite Dusk using semantic tokens. Use actual nested component structures, not full-window screenshot backgrounds. Include global default and per-account default/light/dark/system preferences, safe unauthenticated theme bootstrap, keyboard focus and preference revision checks. Inspector cannot change shared default. Keep branding configurable and do not add unrequested process-health probes or infer RUNNING from log access.

Load a clearly labelled synthetic demo through the real backend, persist safe state in MariaDB, and deliver a local-asset non-root OCI app build plus repeatable dev/lint/typecheck/test/build commands. No remote fonts/scripts/telemetry. Future controls can be disabled with truthful explanations, never simulated as operational. Add production unit/API tests and browser foundation screenshots in both themes/roles at both viewport sizes.

## Version 3 gate

Build the multiple-System catalogue on the existing Project concept, per-page workspace foundation, explicit project context and MariaDB migration skeleton. Account sessions must not contain mutable current-project selection. Seed two synthetic systems in labelled demo mode and preserve both through DB restart. Retain roles/themes/MariaDB prerequisites.

## Completion gate

Each account can authenticate, read permitted demo data and persist only allowed changes through the database. Denied requests have no effect; cold restart preserves model/users/preferences. Secret/migration/authorization and actual MariaDB tests pass with evidence, or explicit blockers remain. No SSH or terminal functionality is added. Stop before Stage 02.

Acceptance targets: AT02, AT03, AT04, AT42, AT67, AT69, AT71, AT72, AT75, AT77, AT79, AT80, AT81, AT84, AT91. Run production-scope tests and record exact commands, results and unexecuted checks in progress/STATUS.md. Acceptance names alone do not prove completion.
