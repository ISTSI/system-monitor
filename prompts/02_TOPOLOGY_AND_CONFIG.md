# Stage 02 — Implement topology, documentation and configuration

Read AGENTS.md and the relevant references below. Implement this stage only unless a higher-level user prompt explicitly authorises another stage.

## References

- `docs/01_PRODUCT_REQUIREMENTS.md`
- `docs/03_DOMAIN_AND_CONFIG.md`
- `docs/06_UI_UX.md`
- `contracts/project.schema.json`

## Task

Implement full subsystem/server/process CRUD, nested React Flow diagrams, directed labelled flows, selectable documentation/configuration, model-wide search with reveal/centre, multiple views, undo/redo and explicit validated reparenting. Keep stable model IDs separate from per-view geometry. Implement safe Markdown, config YAML/JSON export, import preview/commit and optimistic revision checks.

Use contracts/project.schema.json and equivalent examples, plus semantic validation for ownership, references, connection cycles and path fields. Credentials remain unresolved references in project config. Implement delete impact previews and preserve historical name snapshots. Validate coordinates and ancestor presence in each view. Store diagram state through real API transactions, not browser local storage only. Add unit and browser tests for the actual actions.

## Version 2 gate

Shared model/documentation/view/import/export mutations are Administrator-only; Inspector gets a safe viewer projection and personal navigation/selection. Enforce revisions in MariaDB transactions. Implement explicit v1-to-v2 project preview/conversion without importing users, DB endpoints or legacy theme defaults. Test direct forbidden API requests, not only disabled buttons.

## Version 3 gate

Implement independent project revisions, scoped entity/name uniqueness and validated references, catalogue metadata/archive/restore, system-scoped search and explicit-target config imports. UI routes include /systems/{project_id}; no global store may synchronize current-system selection across pages. Keep source/event IDs unchanged and disallow silent cross-project reparenting.

## Completion gate

An Administrator creates and edits the complete demo graph, opens descriptions, searches a collapsed process, changes its name without losing flows and round-trips config without losing IDs/layout. Stale revisions and invalid parents are rejected. Reimport cannot smuggle a password or enable a target silently. Stop before historical or live implementation.

Acceptance targets: AT05, AT06, AT07, AT08, AT09, AT10, AT11, AT12, AT43, AT78, AT86, AT89, AT93, AT101, AT117. Run the tests that actually exist or implement the missing tests for this scope. Do not interpret an acceptance-test name as proof of a passing test. Update progress/STATUS.md with exact commands, results, blocked checks and the next stage.
