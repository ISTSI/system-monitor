# 15 — Conditional v1 prerequisites: MariaDB, roles and themes

This guide retains the v1→v2 prerequisite work. For the **current v3** adoption sequence, scope migration and wire changes, use [document 17](17_UPGRADING_TO_V3.md) and CODEX_UPGRADE_PROMPT.md. References to v2 below describe that earlier transition, not the current package version.

## Determine the actual starting point

The delivered v1 archive was a specification, not a running application or populated database. Do not invent an installed SQLite system. When there is no implementation yet, use the current complete package and CODEX_START_PROMPT.md. The revised initial stages implement MariaDB, roles and both themes directly.

When Codex has already produced code from v1, extract the current package beside that repository, inspect its actual state and use CODEX_UPGRADE_PROMPT.md. Copy/merge specifications, contracts, reference assets and prompts deliberately. Do not overwrite working source, uncommitted edits, real configuration, secrets or an existing progress/STATUS.md with the package's initial templates. Keep a local reviewable checkpoint and report every compatibility issue. The latest user requirement and current contracts supersede old SQLite/single-account/navy-gold assumptions.

## Incremental implementation order

First identify current persistence schema, dependencies, account model, authorization gaps, UI theming and working tests. Map completed features to v2 requirements and preserve them. Implement MariaDB repositories/migrations and database deployment/configuration in a local fixture environment. Add account roles/ownership and server authorization before exposing multi-account access. Integrate the supplied themes and preferences without remounting the log workspace. Complete upgrade/release/backup tests and offline image packaging. A slice that changes only screenshots is not complete.

No real DB changes, infrastructure changes, external pushes or production SSH access are authorized by preparing the code. Test against isolated synthetic copies. Stop at each documented upgrade review gate and maintain the existing evidence log.

## Version 1 project file conversion (always required)

Accept `schema_version: 1.0` only through an Administrator's import preview. Validate the source against `contracts/project-v1.schema.json`, then convert to current project schema `2.0`. Remove the superseded fixed `settings.ui.theme` field with a visible warning; do not set a new global/user preference through the project import. Preserve all other project fields, IDs, names, relationships, documentation, parsers, log sources and view geometry. The current example and legacy example provide a fixed conversion case.

The import still requires local credential mapping, target/root approval and independent host trust. No version converter may turn source files into active credentials, create users/roles or change a database endpoint. Current exports use v2; unknown future versions are rejected. Query/event/live request schemas keep their existing versions when their wire semantics have not changed. Package version, project schema version and DB Alembic revision are different concepts.

## Actual SQLite data migration (conditional on existing code/data)

If real v1 SQLite data exists, implement a deliberate one-time server CLI after inspecting the implemented schema. Alembic alone does not copy data between engines, and an SQLite SQL dump is not a MariaDB migration plan. Do not simply pipe it into MariaDB or perform blind textual substitution.

Quiesce the old application and take a consistent SQLite backup, accounting for its actual WAL state. Keep the source immutable; operate on a backup/copy, using a read-only source connection. Back up/cache-manifest files and separately protect the vault key. Target a new empty MariaDB schema created by current migrations. Produce a preflight report for unsupported old revisions, missing source files, name/collation conflicts, unknown encodings, owner assignments and secret-key compatibility; fail before activation when unresolved.

Transfer in foreign-key-safe order through typed conversion, preserving stable entity/event/source IDs, timestamps/UTC microseconds, log bytes/hash/provenance, documentation/geometry, notes, workspaces and pin references. Never recreate IDs by reparsing names. Assign the legacy single user's resources to an explicitly confirmed migrated Administrator account. Preserve supported password hashes and encrypted SSH secrets with the original key, or require an explicit safe conversion/re-encryption procedure; do not invent default passwords. Invalidate all old web sessions and never migrate active SSH handles/live connections as running sessions. Account/role transfer and old theme conversion must be reported.

Give the CLI an explicit source path, empty target endpoint configuration, owner mapping, dry-run mode and confirmation. Do not put target passwords in arguments. Record a migration manifest, rows/counts per table, IDs/hashes, failed rows and fixed-query comparisons; reject unknown/inconsistent schemas. DDL may partially commit in MariaDB, so migration must not modify a populated target or mark success early. A failed target remains isolated and does not become the live database.

Verify foreign keys, exact fixture and real-copy query samples, repeated-identical-text events, malformed timestamps, private ownership, both roles, both theme preferences, historical cache access and secret recovery. Activate the new deployment only after approval. Retain the original app/database/cache snapshot and image for rollback. Do not delete the original database or reuse it for writes during migration.

If no real SQLite data exists, implement/test the fresh MariaDB path and v1 project conversion, and record the data-transfer step as not applicable—not as a passed production migration.

## Release and rollback

Extend existing application tests rather than replacing them. Replace all operational SQLite-specific sessions/PRAGMA/FTS/WAL/backup assumptions; any remaining SQLite dependency must be isolated to the explicitly conditional offline migration tool. Keep original log fixture outputs unchanged. Test MariaDB container bootstrap/grants, schema creation/upgrade, outages, persistent volume, permission enforcement and restored sessions/roles.

Capture both new themes in the existing UI while live filters run. Test per-account preference persistence, Inspector denied mutations and Administrator configuration workflow. Perform a clean offline load/start of app/proxy/database images. Rollback requires the corresponding pre-upgrade database/cache and key compatibility, not an old binary over the newly migrated schema. Report skipped/unavailable environment tests explicitly.
