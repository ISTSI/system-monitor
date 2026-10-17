# Package changelog

## Version 3.0 — 17 October 2026

**Native Ansible file import:** strengthened the existing inventory requirement into a direct-file system-setup wizard: static INI/extensionless hosts, YAML/YML, ZIP companion variables and canonical JSON. Defined supported/non-executing semantics, safe limits, optional process metadata, field mapping, scoped source identities and transactional idempotent preview/commit. Added direct/bundle examples, typed contracts and bounded package-only sample-reader checks. Full Ansible/plugin/script execution is not supported.

**Multiple systems and windows:** several named configurations share one backend and MariaDB database. UI System retains existing Project/project_id identity; each browser-page workspace chooses its system by URL and has independent selection, filters, panes, live sessions and controller leases. Added duplicate/reload/reattach, stop/close/background behaviour, scoped identities/cache/pools/cursors/downloads, composite database relationships and same-browser-context tests. Global logout/revocation and personal theme preference remain intentionally shared. Roles remain Administrator/Inspector across all systems, not per-system ACLs.

**Capacity and compatibility:** defaults now permit five live subscriptions per workspace and ten per user/project/deployment, with bounded fairness and no eviction of established monitors. Single-system project interchange remains 2.0; deployment config stays 2.0 with optional fields/defaults. Existing custom limits are not reset silently. Live creation adds workspace_id and WS envelopes use protocol 2. Preserve IDs; event/resource identity is composite. The v3 upgrade guide prohibits arbitrary default-system backfill and covers existing-code migration without claiming a deployed database was migrated here.

**Coverage:** R46–R56 and AT91–AT120 added; earlier contracts and all staged prompts updated. Both original theme PNGs and all original fixture files are unchanged. Package tests now include synthetic project/window/preview/budget/Ansible cases. The v2 generic role test was updated to check the expanded Administrator action set and correctly support an Administrator-only owned upload-cancel action; existing ownership/denial assertions remain. No production application/runtime tests have run; see VERIFICATION.md.


## Version 2.0 — 17 October 2026

This is a complete revised Codex specification package, not a patch installer or a deployed application.

**Visual design:** added the original Light — Cool Slate and Dark — Graphite Dusk attachments, semantic JSON/CSS tokens, per-user light/dark/system/default preference rules, full-workspace theme coverage and theme-switch-without-reconnect tests. The older SPDN image remains as a superseded historical reference. The sample SYSTEM MONITOR/PL branding and green health labels remain illustrative; no new automatic process-health monitoring is invented.

**Roles:** replaced the single-operator assumption with local Administrator and Inspector accounts. Added a permission matrix/contract, account lifecycle, last-Administrator protection, per-dispatch authorization and bounded session/stream revocation, safe Inspector model projections and object ownership. Inspectors retain approved log collection/filter/live and personal investigation features; they cannot change shared topology, connections, trust, users or system settings. Personal appearance is available to both roles.

**Database:** replaced operational SQLite with MariaDB and specified SQLAlchemy asyncio/asyncmy/Alembic integration. Added validated host/port/database/user/password-file/TLS/pool configuration, Docker database service, persistent storage/private networking, separate runtime/migration accounts, a fresh-volume init script, secret generator, app/proxy startup interface and offline procedures. Added MariaDB outage, permissions, migration, backup/restore and image-lifecycle targets. Existing-server configuration is supported; bootstrap DB endpoints are not browser-editable settings.

**Compatibility:** current project configuration is schema 2.0, with a preserved v1 import schema/fixture and an explicit previewed conversion. Added fresh-start and existing-code upgrade prompts. Actual SQLite data transfer is conditional on a real implementation/data being present and must be tested separately; no data migration has been performed here.

**Coverage:** revised the original 37 requirements and 66 acceptance targets where necessary, then added R38–R45 and AT67–AT90. Original SSH/log/archive/filter/time/correlation/provenance fixtures and expected query results are retained. Documentation, staged prompts, API/security/deployment guidance, schemas and package tooling are updated together. See VERIFICATION.md for actual package-only checks and unexecuted runtime work.

## Version 1.0 — 16 October 2026

Initial Linux-hosted web specification: one operator, SQLite, original SPDN visual reference, read-only SSH/SFTP, historical/live log investigation and the accepted analysis features. Retained only as history where explicitly identified.
