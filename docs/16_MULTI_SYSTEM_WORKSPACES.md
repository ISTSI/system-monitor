# 16 — Multiple systems and independent browser workspaces

## Meaning of “instance” and terminology

One deployment means one HTTPS origin, application backend, supervisor, MariaDB database and configured cache. It can contain many named system configurations. Two browser windows are two **client workspaces**, not two backend installations or MariaDB containers. The user can use the same account in both without incognito mode, different ports or logging in again merely to select another system.

| Term | Meaning |
|---|---|
| System configuration / System | The existing Project domain entity, containing one documented system |
| `project_id` | Its immutable technical identifier, reused in DB/API/config/events; do not add a competing `system_id` |
| Subsystem | A segment **inside one System**, never a top-level alternative system |
| Workspace | One server-assigned page/session context bound to user and project |
| Live session | A private monitored-source selection with an owning workspace and independent filters/replay |
| Deployment | The application installation, containing all systems and global accounts/settings |

Keep `project.schema.json` at **2.0**: one project file already expresses one system. Its `project.id` is the runtime `project_id`. Package 3.0, project interchange 2.0, optional deployment fields, WebSocket protocol 2 and actual Alembic revisions are separate version dimensions. No bulk registry import is required to create a second system. Import into a newly created target remaps the file's outer project ID explicitly, with preview; it is never an implicit upsert by a source file's ID.

## Catalogue and system lifecycle

The landing page lists systems with name, description, immutable short identifier, revision, archived state and own active-session counts. Create, rename, edit and archive/restore are Administrator-only. Both roles can choose any configured system; the application-wide roles remain unchanged, and per-system access-control lists are **not** introduced. Private investigations remain owner-only within each system.

A System contains its subsystems, physical servers, configured processes, data flows, parsers, connections, saved shared views and import-source mappings. A server belongs to one subsystem in that system; do not reuse an entity record across systems just because its name/address matches. Identical local IDs/names/addresses in two systems are valid. Each system advances its own revision; a commit in B must not invalidate a preview or optimistic write for A.

Archive is the first-release non-destructive removal mechanism. It hides the system from the default active selector, retains its configuration/history and permits read-only cached investigation access. Block archive while that system has live/collection jobs unless an Administrator explicitly confirms audited cancellation **for that system only**. Drain those jobs, then archive transactionally; do not leave new starts racing the transition. Restoring does not restart SSH. Permanent system purge is not a new requirement and must not be implemented as an unconfirmed cascade.

## URL and user interface

Use `/systems/{project_id}/topology`, `/systems/{project_id}/logs` and `/systems/{project_id}/investigations/{id}`. An ordinary anchor with `target="_blank" rel="noopener noreferrer"` opens an independent browser tab/window according to browser settings. Context-menu Open in new window and copying the URL must work. Do not promise a browser can be forced to create an OS window. The acceptance test uses two page contexts and a manual two-window check.

Keep a system selector and current system name visible in both themes. The title is `System Inspector — <system name> — <workspace section>`. Display system labels on log panes, collection/error notices and copied/exported visible log output. Show a safe short ID where names could be confused. Search is system-local by default; do not add a cross-system log merge or implicit all-systems search. An Administrator must see the **target system** throughout every edit/import confirmation.

Selecting B in window A changes only A. Before navigation, explain whether A's active session will stop or remain detached for the grace period; no silent retargeting. Offer an Open separately link. Do not remount or cancel the workspace in another window when any selector changes. Same-system shared configuration changes may show a revision/banner in both windows; they never replace a live source snapshot silently.

## State boundaries

The language follow-up is another deliberate account-wide preference alongside
theme. Changing language may update other windows' UI text, but never their
selected system, workspace, queries, scroll anchors or live control leases.

| Scope | State |
|---|---|
| Deployment/global | MariaDB endpoint, encryption material, user accounts/roles, security ceilings, default appearance |
| System | Topology, source definitions/parsers, connection/jump definitions, target/root/trust approvals, import mappings, named layouts, revision |
| User | Authentication, personal theme and language preferences, own saved analysis data (with project scope) |
| Workspace/page | Active project URL, selected processes, active query/filter, viewport/panes/scroll, live control leases and unsaved drafts |
| User + system + resource | Saved investigations/bookmarks, import previews, jobs, export/download grants and source access |

A persisted `last_used_project_id` may at most suggest a choice on a blank landing page; do not require or use it as routing authority. Prefer no such field initially. No `/set-current-project` endpoint and no mutable `current_project` singleton in services.

Browser localStorage is shared across the origin; it must not hold authoritative active-system/filter/live state. SessionStorage is page-scoped but can be copied into newly opened pages; its survival through reload does not make a stored workspace handle authoritative [S28]. Use it only for non-secret UI drafts keyed by user + project, and treat copied values as initial preferences, not ownership. Query-cache keys include project and owner; live buffers also include workspace/session/filter version. Do not share a single mutable persisted store across browser pages. Theme preference changes may intentionally propagate, but must never reset a monitor or apply filters elsewhere.

## Workspace and monitor ownership

On each document bootstrap or change to another project, create a new server-assigned workspace through an authenticated, CSRF-protected POST; the server derives owner and project membership. An in-memory page nonce is useful for diagnostics only, not authentication. A new page must never claim the workspace/live session found in copied storage or a URL. Visiting a GET/deep link starts **no remote collection**.

New live sessions are created for that workspace and project. Authorize every start/refilter/pause-control/backfill/save/stop/WS operation by user, project and the session's current workspace control lease. A workspace ID is not a secret or a substitute for authentication. An Administrator's audited cross-owner stop exception is explicit; it does not grant content or filter access.

Refresh and browser crash detach the old page. The new page lists its owner's still-detached sessions in that system and offers **Resume in this window**. Resume is an explicit, atomic transfer to the new workspace, requiring owner/project match, a detached control lease and expected lease revision. A live controller cannot be stolen silently; an occupied lease returns 409 `WORKSPACE_IN_USE`. Reattachment revalidates source/permission state and uses retained replay or a visible resync. It does not imply lossless replay. Alternatively start a new independent session. Duplicating a tab never auto-reattaches or stops the original.

Socket disconnection does not immediately stop capture. The existing 300-second reconnect lease bounds detached capture; expiry releases only that session/subscription. Closing a page may send best-effort detach, but browser unload delivery is not assumed. An explicit **Stop this monitor** is reliable through its acknowledged API; closing A is never logout, account-wide stop, project-wide stop or cancellation of B. Background/hidden/minimized pages continue collecting on the server; do not stop based on visibility or short client timer delays. Bound replay and slow-client queues; show resync/gaps as required.

If an owner uses two windows for the same project/process, give them separate live-session objects and filter versions. Immutable source capture/SSH may be reused only with matching project, owner, process/source/configuration revision, full route, credential version and approval/trust context. Refcount consumers; stopping one releases only its reference. A source collector never owns a single shared filter that one window can mutate for another.

Login cookies represent the account, not the selected system. Logout/password reset/disable/role revocation intentionally invalidate every affected window/session under the existing security rules. A theme preference is also intentionally account-wide. Explain these exceptions rather than calling the windows separate authentication sessions.

## End-to-end system scoping

All project-owned HTTP paths use `/api/v1/projects/{project_id}/...`, including private jobs/investigations/downloads and live streams. The service receives an explicit immutable ProjectContext; it cannot infer project from login, previous request, hostname or process ID. Client/body IDs must agree with the route and server-owned parents.

Resource keys are composite: `(project_id, entity_id)`, `(project_id, event_id)` and `(project_id, source_revision_id)`. Existing event IDs remain unchanged and may repeat between systems. Every referencing row/index/FK uses the same scope; examples in `contracts/scope-policy.json` refine this. Process → server, server → subsystem/connection, flow → both processes, source → process, event → source and investigation-event/source joins must reject cross-project relationships at the database level. Workspace/private resources also enforce server-owned user relationships. Query/index prefixes include project and permitted parent resource, not just process/timestamp.

Prefix generated cache namespaces by a validated/mapped project storage key; include project in hashes for cache/cursor/replay/idempotency identities. Do not concatenate an uploaded display name into a path. No cross-system raw-source deduplication in the first implementation. A cache checksum alone never grants access. Existing content can be moved through an explicit manifest-backed migration without changing event identities.

Bind opaque cursors and preview/download tokens to project, user, permitted parent ID, snapshot/filter/content revision and expiry. Guessed IDs in the wrong project return 404 without revealing another project's existence/content; mismatch of an explicitly repeated route/body project returns 422. Binding/expiry/revision failures within an authorized scope are 409/410 as documented. WebSocket handshake and **every frame** carry and validate project/workspace/session; frames from an old system/filter are rejected before rendering.

Global vault records may be reused only via explicit Administrator-managed project credential bindings. Imports cannot create bindings or approvals implicitly. Connection/jump profiles and effective host-key/root/target approvals remain project-specific; a known address in A is not approval for B. A changed profile/trust entry invalidates affected contexts, not all windows indiscriminately.

## Capacity, fairness and operation

On the stated 16 GB baseline, test two low-rate systems with five live processes each, each investigation 10–20 MB. Defaults: 5 process subscriptions per workspace, 10 per project, 10 per user and 10 deployment-wide; 8 workspaces per user, 64 global. For omitted new limit fields in an older configuration, clamp nominal defaults to explicitly configured lower ceilings and report when they cannot support the two × five target. Do not raise custom limits without approval. Count a process per live-session subscription even when physical reads can be shared, preventing quota bypass. Reserve capacity atomically before starting SSH and release on stop/expiry/failure. The same user's windows contribute to their common cap; changing systems does not reset usage.

Historical collection jobs remain 2/user and 4/global, with an initial 2/project ceiling. Global archive/read/executor pools remain bounded. `concurrent_hosts` governs historical task concurrency, not a semaphore held for the life of every live connection; otherwise it would incorrectly cap required ten-source live operation at four. Schedule bounded work fairly between projects/workspaces, not one queue that can be monopolized by a large archive scan. A rejected eleventh live subscription returns a clear 429 `LIMIT_REACHED`; never evict an established window's monitor to make room. Display own usage with scope and limit.

One DB supervisor lock still guards the deployment; two browser windows do not acquire it. Backup/restore covers all project scopes, import mapping provenance, workspaces marked interrupted, raw-cache namespaces and owned investigations. Startup leaves old workspaces detached/interrupted and does not restart target SSH. Account/DB defaults are shared by design; no database switching per selected system.

## Required evidence

Use two Playwright pages from **one browser context/account/origin**. A distinct context per window alone misses shared-cookie/storage bugs. Fixtures intentionally repeat host/process IDs, names, source IDs, IPs, timestamps and correlation IDs between systems. Test different-system and same-system pages, forged cross-scope references, out-of-order old frames, duplicate/reload, minimized/slow page, refilter/stop/close isolation, per-system imports, stale previews, two × five healthy live sources and global logout. Add MariaDB composite-FK and upgrade tests, not just a frontend selector test. See AT91–AT120.
