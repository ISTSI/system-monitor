# 17 — Incremental v3 adoption: multiple systems and inventory files

## Determine the real starting point

This is a specification/templates/fixture package, not a deployed application. Inspect real code and data before choosing a migration. A fresh build uses the v3 foundation directly. Existing v2 implementations already using projects may need scoping fixes rather than a new top-level table. Existing v1 code also needs the roles/themes/MariaDB path in document 15; preserve that guide as a conditional prerequisite. Do not rewrite completed features or assume a populated SQLite/MariaDB deployment exists.

## Required implementation slices

1. Inventory actual project relationships, API routes, query caches, auth/session state, live ownership, foreign keys and files. Find every singleton/current-project variable, globally keyed source/process lookup and unscoped operational route. Record proposed compatibility changes and test against synthetic data.
2. Introduce explicit ProjectContext and project-scoped repositories/foreign keys/cache namespaces, retaining existing project IDs. Add catalogue/lifecycle and separate user/project/workspace records. Scope service operations before enabling the second system in the UI.
3. Route browser workspaces through `/systems/{project_id}` and project-scoped API paths. Implement independent monitors, control leases, replay/filter keys, duplicate/reload behaviour and explicit resume. Raise the default per-user live ceiling from 5 to 10 within the existing global 10, with per-workspace 5 and actual budget reservation.
4. Upgrade inventory upload to the direct INI/YAML/file-bundle wizard; preserve existing canonical support and import-source keys by adding project scope. Preview/reconcile/commit into the explicitly selected system only.
5. Complete two-page, real MariaDB, import/upgrade, performance and offline backup/restore gates; update release docs and contract-generated clients together.

Use CODEX_UPGRADE_PROMPT.md; implement the first reviewable vertical slice and stop, rather than claiming all stages from a selector screenshot. Only explicitly authorized local test database/container actions are permitted. No production data/schema/SSH changes are authorized by these instructions.

## Data migration and identity

System = Project, with technical `project_id`. Do not create a second unrelated System table with duplicated project IDs. Retain current `project.schema.json` **2.0** exports and legacy v1 conversion. Existing v2 YAML/server configuration remains valid; new limit fields have defaults. Document and visibly confirm any deployment-limit adjustment rather than resetting all settings.

Derive scope from existing parent chains. A process follows its actual server/project; events follow verified source/process; investigation-source associations must agree. If there was genuinely only one unscoped project, require an explicit operator-confirmed mapping to a named system. If there are already multiple projects, preserve each separately. Ambiguous/orphaned or cross-project relations block migration and produce a safe report; never guess the most recently opened system or mass-assign every row to a default.

Add composite unique keys and foreign keys (project + entity/resource ID) after data validation. Keep old IDs, timestamp integers, annotations and source bytes unchanged. Event IDs may repeat across projects: full identity is `(project_id, event_id)`, so there is no need to rehash every legacy event and break bookmarks. Cache movement uses generated project namespaces and a checksummed manifest; validate source bytes and dependent pins, and retain a rollback copy. Do not deduplicate across projects merely because source hashes/paths match.

Preserve account/global theme/DB preferences and owned notes/investigations. Do not migrate active SSH handles as live processes. On protocol/schema upgrade, stop/drain safely, mark sessions interrupted and require explicit owner reconnection. Saved layout/query preferences remain available per user/project; do not migrate a user-global “active system” as runtime authority.

## API and protocol compatibility

UI paths gain project context. Every project-owned operation, including jobs/live/downloads, gains `/api/v1/projects/{project_id}/...`; registry/auth/global admin/vault endpoints remain global. Keep explicit `project_id` in existing live-request payloads and reject route/body mismatch; add required `workspace_id`. Event and historical query shape remain unchanged when the route supplies scope. WebSocket protocol becomes **2** with explicit project/workspace/session on all frames, including hello and replay.

The bundled frontend/backend are released together. Do not keep an unsafe legacy unscoped operational route that guesses a default project, even on a one-system instance. Disable with a documented upgrade response or implement a temporary shim only when it resolves an immutable resource-to-project relation server-side and enforces ownership; never choose from session/current project. Old socket clients receive an explicit unsupported-protocol result and no data. Version/project scope in cursors and download grants must prevent replay of old ambiguous tokens.

## Upgrade acceptance and rollback

Back up matching MariaDB/cache/config/key state before a real authorized upgrade. MariaDB schema changes are not assumed transactional; dry-run against disposable copies and test interrupted migration. Verify per-system counts, immutable IDs, raw hashes, owner memberships and fixed queries before/after. Test duplicates/overlapping networks and named system selection after restart. Confirm all privileges/themes/SSH safety survive.

Use two pages in one browser context for regression, not just two independent sessions. Reimport the same inventory into A and B, then change only A. Verify B's topology, revision, notes and live filters are untouched. Exercise restore with both systems' cached investigations while monitored hosts and Internet are unavailable. Roll back using the matching pre-upgrade database/cache and images, not an old frontend over new incompatible contracts.
