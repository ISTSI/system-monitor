# 03 — Domain model and configuration lifecycle

The structural contract is `contracts/project.schema.json`; the examples in YAML and JSON represent the same project. JSON Schema validates shape. Application validation must also enforce referential, permission and lifecycle rules.

## Identity and entities

| Entity | Essential fields and rules |
|---|---|
| Project | Stable ID, name, schema version, revision, documentation, shared branding/view defaults; no credentials, users or database settings |
| Subsystem | Stable ID, unique project-level name, documentation/tags |
| Server | Stable ID, unique project-level name, exactly one subsystem ID and one target connection ID |
| Process | Stable ID, unique project-level display name, exactly one server ID; optional `pcs_resource_name`; documentation/tags; one log-source definition |
| Connection profile | Stable ID, display name, host, port, username, credential reference, optional jump connection ID, proposed allowed log roots |
| Credential | Separate server-owned record; reference ID and safe label are visible; encrypted password and nonce/key version are not exported |
| Parser profile | Stable ID, timestamp strategy, encoding policy, optional correlation markers and severity tokens; no executable code |
| Flow | Stable ID, source and target process IDs, label/protocol/documentation; direction is meaningful |
| View | Stable ID, displayed element IDs and per-view geometry/collapse state, selected flow IDs; entity descriptions are not duplicated here |
| Investigation | Stable ID, server-assigned owner_user_id, revision, selected process IDs and name snapshots, exact time bounds, filter, pane layout, collection/job references, notes, pin state |
| Source revision | Stable identity of collected remote content/generation, source configuration snapshot, remote path/member identity, available byte intervals and checksum metadata |
| Event | Identity based on process/source/member/byte range; original line, exact UTC time or parse issue, byte/line provenance, optional parsed metadata |
| Live session | Server-assigned owner_user_id, selected sources, subscriber/filter revisions, state, cursors, bounded raw retention, recording flag, coverage/gap records |
| Bookmark | Parent investigation ownership, event/source identity and name snapshot, annotation, saved context/pin reference; never a mutable row number in the UI |

IDs in examples are readable strings for fixture clarity. The implementation may use UUIDs for newly created records; IDs are immutable and cannot be reused to refer to a different object. A renamed process is still the same configured instance. Multiple instances of the same program are distinct records, not inferred by PID or executable name.

A log source includes the active file, rotated plain files and historical archives for that process. These are not separate process objects. A profile can specify an exact archive member or safe glob patterns; never assume the first member is the intended log. Duplicate archive member names require ordinal identity, not name alone.

## Canonical state and editing

MariaDB is authoritative while the application runs. The UI edits through revision-checked API transactions. YAML/JSON is exported, edited outside the application, then imported with validation, preview and commit. There is **no automatic filesystem watcher** that silently overwrites live edits.

A config file's project revision records the export point. Import into an existing project requires the current server revision (optimistic concurrency). A stale import returns 409 with a previewable conflict, not last-write-wins. Unknown future schema versions are rejected. Increment schema version only for schema changes, and project revision for successful content/layout transactions.

Deletion must list affected processes, flows, views, saved investigations and active sessions. It either requires explicit cascade confirmation or refuses. Historical snapshots and notes keep original identity/name information even when the current topology changes. Editing a log path, connection or parser never silently retargets an already running session; stop/restart or fork it with the new configuration revision.

Only Administrators write the shared semantic model and named view geometry. Inspectors may pan/zoom, expand/collapse and change personal pane layouts without writing the project. Separate semantic model undo/redo from transient viewport movement. Save transactions and explicit undo operations advance revisions. Debounce geometry persistence while dragging; do not emit a write for every animation frame.

## Configuration validation

Check unique IDs and names, existing references, single ownership, valid connection chains and no jump cycles. The current release permits at most one jump hop: a target may reference a jump profile whose own jump ID is null. A jump profile need not correspond to a diagram server.

Paths must be absolute Linux paths within configured roots. Reject NUL/control characters, traversal components and expansion syntax. Allow glob metacharacters only in the explicitly typed pattern fields; do not expand shell expressions or environment variables. Validate symlink policy and canonical paths at access time, not only during import. With **Additional security measures** enabled, roots and target enablement require local Administrator approval, which an imported file cannot supply. With that global setting disabled, saved path/parser definitions are usable without separate source confirmation; credentials, explicit host-key trust and root confinement still apply. Import starts no connection and creates no approval record.

Every process references an existing parser. Unsupported encodings, timestamp formats, future schema versions, unknown mandatory fields and unsafe Markdown assets produce useful line/field errors. Parse YAML with a safe loader, duplicate-key detection and depth/size/alias limits. Do not resolve YAML tags into objects, evaluate Jinja or merge arbitrary Python objects.

## Suggested database indexes

Unique `(project_id, entity_id)` and project-level names per entity type. Foreign keys for ownership and relationships. Events indexed by `(investigation_id, process_id, timestamp_us)` and stable tie-breakers; source byte offsets indexed for context lookup. Use nullable exact timestamps for malformed entries, with a separate error/diagnostic query. Store source checksums, archived-member ordinal and available ranges. Query text through parameterised statements; literal text matching must preserve the engine contract.

Use signed 64-bit integer UTC microseconds internally. Supported date ranges must be constrained so frontend values remain safely representable or sent as strings; the public API always includes a canonical RFC3339 string. Do not compute microseconds through float `datetime.timestamp()` rounding.

## Import/export distinction

Project configuration includes network target names/addresses but **no passwords, ciphertext, encryption keys, session tokens or trusted host-key material**. It is still sensitive operational information. Credential references appear as unresolved references on a different installation and must be mapped explicitly.

An investigation bundle is more restricted: it contains the selected logical topology snapshot and sanitised source labels, not reusable active connection profiles. Bundle import defaults to archived/offline viewing and cannot create enabled hosts. Raw or redacted source data, annotations and provenance are versioned separately from configuration.

See `docs/10_ANSIBLE_IMPORT.md` for inventory-specific mapping and `docs/07_SECURITY.md` for approvals and secret storage.

## Additional version 2 entities

The language follow-up adds `ApplicationSetting.default_language` (`en` or `pl`,
initially `en`) and `UserPreference.language` (`default`, `en` or `pl`, initially
`default`). They share the existing settings/preference revision boundaries;
partial writes preserve omitted fields. Language is independent of system and
workspace selection and is excluded from topology/investigation interchange.

`User`: immutable ID, normalized unique username, display name, Argon2 password hash, role (`administrator` or `inspector`), enabled state, force-password-change flag, authentication version, created/updated times. `UserPreference`: user ID, revision, theme mode (`default`, `light`, `dark`, `system`), personal viewport/pane settings; never shared topology. `ApplicationSetting`: revisioned global appearance/defaults and permitted runtime policy, changed only by an Administrator. `AuthSession`: user ID, verifier hash, auth version, expiry/revocation. `AuditEvent`: actor ID/role snapshot, action, safe target IDs and result; no secrets/raw log/filter values.

The persisted `ApplicationSetting.additional_security_measures` boolean defaults
to true. It controls manual source confirmation across systems, stays outside
project interchange and personal preferences, and is rechecked during remote
operations. It never retargets an existing source snapshot.

Jobs, import previews, downloads and bundles also carry server-assigned ownership. User deletion is disabled in the first release; deactivation preserves audit/investigation ownership. Administrators can stop a user's jobs for operational reasons but cannot silently read or edit that user's personal investigation contents. Table access rules are in document 13.

## Versioned interchange and bootstrap configuration

Current project export schema is `2.0`. Version 1 is supported only as an import input through a visible, tested conversion. Remove the old fixed `settings.ui.theme: navy_cyan_gold` with a warning; theme choice now belongs to user/global appearance settings. Preserve all entity IDs, views, descriptions, processes, filters and source definitions. The old schema/example are in `contracts/project-v1.schema.json` and `examples/legacy/` for compatibility tests, not as alternate runtime requirements.

Deployment config has its own `schema_version: 2.0` and `contracts/deployment.schema.json`. It supplies database location before the app can read MariaDB, and is not accepted through project/import endpoints. File/environment precedence is explicit in document 14. User credentials, DB endpoints, roles and deployment paths are forbidden project fields.


## Version 3 system scoping and workspace entities

UI **System configuration** is exactly the Project above. Retain `project_id` as the canonical scope field and keep single-system config schema 2.0. Do not add independent System/Project identities. All project-owned entities and relationships use `(project_id, id)`; local IDs and names can repeat between systems. Every related row must agree on project, including endpoints of a flow and cached event/source associations. A migration must not regenerate old IDs. See document 16 for required composite FK/index relationships and document 17 for migration.

Add `Workspace`: server-issued ID, project ID, server-derived owner user ID, revision/control-lease state, creation/last-activity/detachment timestamps and private viewer state references. A workspace is never created by GET navigation and never inferred from copied browser storage. `LiveSession` and interactive `CollectionJob` record their originating workspace/project/owner; controlled live actions require the active workspace lease. A saved Investigation has project+owner but need not remain bound to the page that created it. All pages querying it use the current authoritative ownership/revision.

`InventorySource` is scoped by project; `InventoryHostMapping` is unique on `(project_id, inventory_source_id, inventory_hostname)`. Optional process mapping adds host alias and extension item ID. `ImportPreview` binds project, source, owner/auth version, expected project revision, normalized content/mapping digests and expiry. Project archival preserves existing snapshots/notes and blocks new collection; explicit restore does not reconnect SSH.

Global vault credentials require an explicit project credential binding before use; connection definitions and trust/root/target approvals are project-specific. Exporting one system includes only that system's definitions and unresolved reference labels, never another system's bindings or any secrets. Bundle import creates a private offline investigation in a selected project context; foreign source project identifiers remain provenance, not permission to overwrite an active project.
