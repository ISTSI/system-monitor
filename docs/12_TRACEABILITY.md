# 12 — Requirement-to-acceptance traceability

All 56 requirements map to application acceptance targets. The requirement table is not a test-result report; implemented evidence and remaining limits appear below it.

The user-authorized compact navigation update (17 October 2026) retains R05/R10/R11
editing through the System menu, moves Undo/Redo beside Documented topology, and
originally placed personal R38 appearance in Settings for both roles. The
18 October 2026 user-requested separation moves it to Preferences under the
logged-in user menu, keeps Settings Administrator-only, and uses its shared
default for new accounts and signed-out screens. R39/R46 system lifecycle
controls now live in the dedicated Administrator view. R47/R49 retain ordinary
system links and fresh page workspaces; Ctrl-click replaces the dedicated Open
separately control at the user's request. Browser coverage in
`frontend/e2e/preferences.spec.ts`, `topology.spec.ts`, `foundation.spec.ts`, `historical.spec.ts` and
`ssh.spec.ts` checks menu actions, themes, roles, manual new-tab navigation and
same-context isolation. Actual results are recorded in `progress/STATUS.md`.

The Preferences/Settings follow-up is deployed on the retained local 8445
application. Its [installed-browser receipt](../verification/stage-7/preferences-deployment-browser.json)
checks the actual served asset hashes, both roles/themes, keyboard menu/dialog
focus, Inspector denial and unchanged saved preferences/shared defaults. It
performs no personal/shared writes, workspace creation or target operation.
The original Stage 07 backend/wheel and database schema are retained; this is
a frontend deployment, not Stage 08 release qualification.

Actual stage evidence and remaining gates are recorded in [the implementation status](../progress/STATUS.md) and [incremental slice plan](../progress/V3_SLICE_PLAN.md). Authentication, appearance, scoped topology/configuration, independent browser workspaces, historical indexing and approved SSH collection have executable unit, MariaDB and browser coverage. Live monitoring, personal investigation tools and static inventory reconciliation now have executable coverage. The complete offline release remains Stage 08. Passing a subset does not complete an entire acceptance target.

The authorized temporary VM now supplies actual MariaDB evidence for part of R42/R44/R46/R48/R56: the initial migration, binary identities, owner/role/scope behavior, composite FK rejection, exact BIGINT values and named migration locks pass in `backend/tests/vm/test_vm_mariadb.py`. Those rollback-only checks also prove the supplied migration account is refused for serving. They do not replace restricted-runtime/API/browser or disposable-schema integration targets.

| Requirement | Contract | Acceptance targets |
|---|---|---|
| R01 | Run the application on an Ubuntu or Rocky Linux server and expose a web UI to Windows 10/11 browsers. No installed desktop client is required. | AT02, AT62 |
| R02 | Work without Internet access at runtime, including first page load after an offline restart. The application server may reach authorised monitored hosts/jump hosts over LAN/VPN. Cached investigations remain usable when those hosts are unavailable. | AT03, AT63, AT87, AT120 |
| R03 | Support 10–20 hosts, 30–60 processes and at most ten processes per host **per configured system**; approximately 10–20 MB per investigation. One 16 GB application server must support two systems monitored concurrently from two windows by the same user, up to five live processes per window (ten total) at the stated low event rate. These are design targets, not arbitrary hard entity limits. | AT04, AT23, AT61, AT90, AT100 |
| R04 | Support individually authenticated local accounts with exactly two roles: Administrator and Inspector. Multiple tabs/accounts may be active. Administrators edit shared configuration with optimistic concurrency; real-time collaborative editing is not required. | AT02, AT71 |
| R05 | Create, rename, document and delete subsystems, physical servers and configured process instances through the UI. Preserve stable internal identities. | AT05, AT12 |
| R06 | Visually contain servers within one subsystem and processes within one server. A server cannot belong to multiple subsystems. Reparenting is explicit and validated, not an accidental drag side effect. | AT05, AT57 |
| R07 | Add directed, labelled process-to-process data-transfer relationships within or across servers/subsystems. Store protocol and descriptive metadata where supplied. | AT06 |
| R08 | Selecting an element opens a documentation/configuration inspector; read formatted Markdown safely. Documentation is shared across diagram views. | AT07, AT43 |
| R09 | Search the complete **active system only**, not another window’s system, by server/process name, configured PCS resource name, tags and documentation. Selecting a result opens a relevant view, expands ancestors and centres/highlights it. | AT08, AT93 |
| R10 | Provide pan/zoom, selection, multi-selection, drag/resize, collapse/expand, fit-to-selection, minimap, undo/redo and multiple named views. Do not duplicate model entities just to display them in another view. | AT09 |
| R11 | Edit topology in UI, export/import editable versioned YAML/JSON, and read uploaded Ansible static INI/extensionless hosts files, YAML inventories, supported inventory bundles and canonical JSON with preview/reconciliation (R51–R54). Preserve stable IDs and metadata on reimport. | AT10, AT11, AT55, AT56, AT57, AT58, AT102, AT117 |
| R12 | Highlight upstream/downstream dependencies and add selected neighbours to an investigation/live selection. Topology links describe possible transfers; they do not establish actual causality. | AT51 |
| R13 | Configure reusable username/password SSH connection profiles, optionally through one jump host with its own credentials and host-key trust. Target Linux hosts include the user's current CentOS environment and Rocky Linux 9. Do not assume a particular CentOS release. | AT24, AT25, AT29, AT46, AT111 |
| R14 | Be agentless and limited to UI-defined read-only inspection. No shell/terminal, arbitrary command input, remote agent, discovery or service control. Use a dedicated non-sudo log-read account. Clearly diagnose missing permissions. | AT26, AT27 |
| R15 | Each process has one logical plain-text log source, an active path and optional rotated plain files, ZIP and TAR.GZ archive patterns/member selectors. Instances of the same executable remain distinct configured processes, optionally labelled with a PCS resource name. | AT18, AT27, AT113 |
| R16 | Download/stream relevant sources into bounded server-side cache, decode supported archives, and parse one physical line per event. UTF-8 is the default, with an explicit configurable alternative encoding. Retain original bytes/provenance where collected. | AT14, AT17, AT18, AT20, AT21, AT28, AT44 |
| R17 | Use full UTC event timestamps, including configured fixed-width variants. Preserve timestamp text, parse exactly and surface failures. Do not depend on log filename, mtime, browser timezone or ingestion time for event filtering. | AT13, AT14 |
| R18 | Query selected processes over a from/to interval with deterministic merged ordering or separate panes. Use [from, to) throughout API/storage; the UI visibly explains the exclusive end. | AT13, AT16, AT19, AT22, AT37, AT95 |
| R19 | Provide connection/path/archive-access checks, a parser preview with errors, and a collection-plan preview with counts, estimated bytes and warnings. | AT27, AT59 |
| R20 | A single selected process exposes Monitor; multiple selected processes expose Monitor selected. Both use the same collector and viewer components. | AT30 |
| R21 | Show separate internal panes or one aggregated view with host and process labels; labels must remain identifiable in copied visible output. Split panes are internal UI panels. Separately, R47–R50 require two real browser windows/tabs, each with its own selected system and live sessions. | AT30 |
| R22 | At the baseline rate on a responsive LAN, target a 1–2 second display delay. Record actual measured latency in tests; do not promise that latency during network failure or overload. | AT30, AT37, AT100 |
| R23 | Seed monitoring with enough recent matching lines to fill the measured visible rows, not a fixed arbitrary count. Bound scanning; show why fewer lines were found and offer Load older. | AT31, AT32 |
| R24 | Apply literal substring inclusion and exclusion filters while monitoring, globally and optionally per process. Support any/all inclusion, case sensitivity and clearing/changing filters without restarting SSH. The simple primary control is Contains string. Apply the same semantics to historical views. | AT15, AT16, AT33, AT68, AT96 |
| R25 | Pause display without stopping collection; resume to the current retained position; stop collection explicitly. Expose counters for received, matching, rendered/visible, filtered and evicted events. | AT34, AT39, AT97 |
| R26 | Reconnect with bounded backoff; handle observed rotation/truncation and partial writes; expose gaps and uncertain continuity. Distinguish connection, source accessibility, parsing and process-health concepts. Never infer a process has stopped solely from silence. | AT32, AT35, AT36, AT37, AT39, AT41, AT78, AT97 |
| R27 | Bound buffers and queues, retain unfiltered captured data for changing filters/context, and allow explicit recording of live sessions into an investigation. No silent event dropping. | AT21, AT29, AT33, AT38, AT40, AT100 |
| R28 | Save investigation workspaces: process selection, time bounds, filter state, pane layout and collection references. Reopen offline against retained data; identify expired sources rather than presenting incomplete data as complete. | AT12, AT40, AT48, AT64, AT76, AT85 |
| R29 | Search a selected/configured correlation identifier across processes and show a chronological trace. Show observed time deltas without claiming they prove network latency or causality. | AT49, AT76 |
| R30 | Bookmark events and attach annotations without changing source logs. Preserve the source identity/name snapshot. Explicitly pin needed cached context or warn before its removal. | AT12, AT50, AT76 |
| R31 | Expand before/after context in source order, even when surrounding lines fail the main filter. Label context outside time bounds and do not silently merge it into match counts. | AT50, AT76, AT95 |
| R32 | Show per-source collection coverage, read/parse errors, scanned boundaries, provenance and completeness limitations. No matching events is different from no available data. | AT17, AT19, AT28, AT52, AT76, AT95 |
| R33 | Export/import investigations with selected log data, notes, topology snapshot, provenance, checksums and version metadata. Support redaction with preview; exclude credentials, active connection details and SSH trust from bundles. Import never starts a connection. | AT53, AT54, AT76, AT118 |
| R34 | Implement Light — Cool Slate and Dark — Graphite Dusk, following the two new images in assets/themes/. Use consistent nested subsystem/server/process cards, blue data-flow arrows and a selectable process-details/log workspace. The new references supersede the original navy/gold direction. Keep log text readable, keyboard navigation and accessible state indicators. | AT03, AT43, AT60, AT61, AT67, AT70, AT78, AT88, AT119 |
| R35 | Authenticate and authorise sensitive routes and object access, protect sessions/CSRF/WebSockets, encrypt stored SSH secrets, strictly verify host keys, sanitise untrusted rendering and validate archives/configuration. Application roles never grant shell/sudo/target write access. | AT02, AT11, AT20, AT25, AT42, AT43, AT44, AT45, AT46, AT47, AT53, AT58, AT64, AT71, AT73, AT74, AT75, AT77, AT80, AT83, AT84, AT94, AT110, AT111, AT112 |
| R36 | Supply offline-installable release artifacts, local assets, backup/restore and update/rollback procedures; document tested Ubuntu and Rocky environments. | AT41, AT62, AT63, AT64, AT65, AT120 |
| R37 | Supply automated unit, API, SSH integration and browser tests plus a labelled synthetic demo. Record requirement-to-test traceability and measured performance. | AT01, AT04, AT23, AT61, AT66 |
| R38 | Switch light/dark themes at runtime across every page, dialog, graph, log viewer and overlay without reloading, reconnecting SSH/WebSockets, resetting filters, losing selection or changing shared topology. Persist appearance per user; support an Administrator-managed shared default and optional system-following mode. | AT67, AT68, AT69, AT70, AT88, AT99, AT119 |
| R39 | Administrators manage shared topology, documentation, named view layouts, connections, credentials, host-key/target approvals, parsers, inventory/config imports and application settings. Inspectors may view/search approved topology and collect, filter, monitor and investigate its logs, but cannot change any of those shared definitions. Enforce this on the server and in the UI. | AT69, AT71, AT73, AT75, AT78, AT88, AT89, AT114 |
| R40 | Administrators create/disable accounts, assign either role, reset credentials and revoke sessions. No public registration or default password. Protect the last enabled Administrator and audit security/configuration changes. Account/role changes revoke existing sessions and subscriptions before another protected response is sent. | AT72, AT74, AT77, AT99 |
| R41 | Retain saved investigations, bookmarks, notes, context, bundle operations and personal viewer/appearance preferences for both roles as personal analysis state, not shared system settings. Enforce ownership of jobs, live sessions, investigations and downloads; do not accept client-supplied ownership. Shared raw-source caches must not bypass ownership. Cross-account sharing is by explicit sanitized bundle exchange, not implicit visibility. | AT69, AT73, AT76, AT90, AT114, AT118 |
| R42 | Use MariaDB as the only operational database for model/configuration, users/roles/preferences, sessions, jobs, investigations, events/provenance and audit metadata. Provide validated server-side configuration for DB host, port, database, username, password file, TLS policy, timeouts and pool limits. Keep database credentials/coordinates outside project and investigation exports. | AT79, AT80, AT82, AT115 |
| R43 | Include launching/configuring the free official MariaDB Docker image in the deployment process: persistent named volume, isolated network, secret files, readiness health check, separate application/migration credentials, initialization and offline save/load/start. Support an explicitly configured existing MariaDB endpoint as an alternative; never assume localhost inside an app container refers to MariaDB. | AT81, AT82, AT84, AT87 |
| R44 | Implement and test MariaDB-native migrations, exact UTC microsecond/provenance storage, Unicode literal semantics independent of collation, revision/ownership constraints and bounded reconnect/fail-closed behaviour. No silent SQLite fallback. Preserve v1 project imports through an explicit previewed conversion; migrate actual SQLite data only if an existing implementation requires it. | AT79, AT83, AT86, AT89, AT90, AT115, AT116, AT117 |
| R45 | Back up and restore MariaDB plus consistent log-cache/manifests, account preferences/roles, configuration and separate vault-key recovery material. Test DB outages, protected schema upgrades and rollback, persistent-volume restarts and an Internet-blocked release including all three images (app, proxy, database). | AT83, AT85, AT87, AT120 |
| R46 | Store multiple named **system configurations in one application deployment and one MariaDB database**. Each has its own topology, connections, parsers, views, inventory sources and revision. Administrators create/rename/archive/restore systems; both roles can select and inspect them. The existing Project entity is the system configuration; retain `project_id` as its technical identifier. No second backend/container/database is required per system. | AT91, AT101, AT114, AT120 |
| R47 | Allow the same authenticated user to open System A in one browser window and System B in another, on the same origin/profile, and inspect/monitor both concurrently. Encode the selected system in `/systems/{project_id}/...` URLs, headings and window titles. Provide an ordinary Open in new window/tab link. Never store authoritative current-system selection in a shared user record, auth session, cookie or global localStorage key. | AT92, AT98, AT119 |
| R48 | Scope all model and operational lookups, source/cache identities, SSH contexts, query cursors, jobs, imports, investigations, downloads and WebSocket frames to the system. Repeated host/process names, entity IDs, addresses and event IDs in different systems are permitted and must not cause cross-system matches, cache reuse, retargeting or data leakage. Enforce composite relationships and project membership in the backend and MariaDB. | AT91, AT93, AT94, AT95, AT101, AT108, AT115, AT118 |
| R49 | Give each browser-page workspace independent process selection, filters, time bounds, pane/scroll state and controllable live sessions, including two workspaces for the same system. Refresh/duplicate/reopen must not automatically adopt copied session handles or start new SSH jobs. Use server-assigned workspaces and explicit owner/project-checked reattachment. Pause, stop, close, switch or disconnect in A must not modify B; authentication logout/revocation is intentionally shared. | AT92, AT96, AT97, AT98, AT99 |
| R50 | Provide bounded per-workspace, per-system, per-account and deployment-wide concurrency/retention with fair scheduling. Default ceilings must permit one user with five live processes in each of two windows (ten total). A rejected start leaves established sessions running; a slow/minimized window must not stall the other. Show scope-specific limits/usage without exposing another owner’s content. | AT100 |
| R51 | Make **Import Ansible inventory files** a first-class Administrator system-setup wizard: accept ordinary static INI (including extensionless hosts files), YAML/YML, safe ZIP bundles containing selected static sources plus relative group_vars/host_vars, and `ansible-inventory --list` JSON. Ordinary supported static files must not require Ansible installation or manual JSON conversion. Document the supported subset and diagnose unsupported constructs without guessing. | AT102, AT103, AT104, AT105, AT106, AT114 |
| R52 | Preview host aliases/addresses/ports/users, nested group membership, subsystem assignment and optional `inspector_processes`/PCS/log definitions. Map groups explicitly to one subsystem per host, resolve ambiguities, preserve tags and import host-only files without inventing processes. Allow manual credential/jump/parser mapping; no imported approval or secret becomes active automatically. | AT102, AT103, AT107, AT111, AT113 |
| R53 | Bind inventory uploads, mappings, previews and commits to a selected system, authorizing account/version, stable inventory-source ID, hashes and expected system revision. Reimport reconciles `(project_id, inventory_source_id, inventory_hostname)` and process keys, not filenames/IP alone. Preserve manual documentation/layout/flows and unrelated processes; no implicit deletion of missing hosts. Commit atomically or leave the system unchanged. | AT108, AT109, AT110 |
| R54 | Treat inventories as untrusted data: never execute Ansible, playbooks, plugins, scripts, Jinja/lookups, ProxyCommand or uploaded ansible.cfg; never fetch referenced local/remote files outside an uploaded bundle. Reject unsafe YAML/ZIP, unsupported precedence, unresolved required templates and encrypted Vault input. Omit credential values without echoing them. Complex trusted inventories can be resolved externally to canonical JSON; application runtime remains Internet-free and agentless. | AT104, AT105, AT106, AT111, AT112 |
| R55 | Upgrade actual v1/v2 code incrementally without resetting stored systems, ownership, logs, notes, themes, roles, database settings or immutable IDs. Preserve existing project IDs as system IDs and retain version 2.0 single-system YAML/JSON interchange. Backfill missing scope only from verified parent relationships; fail on ambiguous/orphaned rows. Never attach every old record to an arbitrary default system. | AT116, AT117 |
| R56 | Add same-browser-context two-page tests, real MariaDB composite-scope/migration tests, inventory-file/bundle and reconciliation tests, scoped backend/WS/download tests, and two-system backup/offline restart gates. Include collision fixtures and document actual results separately from specification/oracle checks. Do not claim multi-window isolation from testing two separate browser profiles alone. | AT92, AT94, AT100, AT116, AT120 |


## Stage 01 foundation evidence - 17 October 2026

Stage 01 implements the foundation portions of R01/R02/R04/R34/R35/R37-R44 and
R46-R50/R55/R56. This does not mark later engine, SSH, topology/import or release
targets as completed.

| Target | Implemented evidence | Limit |
|---|---|---|
| AT02, AT03, AT04 | Actual roles/authentication and UI writes, persisted systems/preferences, backend cold restart, blocked external browser requests, local bundled assets | Labelled synthetic documentation, no log collection |
| AT42 | Actual CSRF/Origin/cookie/revocation/expiry/forced-change tests; delayed-response browser race regressions | WebSockets are later-stage scope |
| AT67 | Both reference themes at both desktop sizes/roles, selected process inspector and dialog, keyboard and 200% layout equivalent | Live/log visual states remain later stages |
| AT69 | Per-account preference revisions/mass-assignment/defaults and shared appearance with page-state preservation | Future streaming state tested when implemented |
| AT71, AT72, AT75, AT77 | Real role-forbidden HTTP requests, safe viewer/diagnostics, account lifecycle, concurrent last-Administrator guard, redacted audit and route permission/CSRF declarations | Future operations must add the same checks |
| AT79, AT91, AT94 | Real MariaDB types/composite FKs/revisions; two same-context pages; UI-created same-name systems with independent IDs/revisions; retained two-system demo through restart | Event ingestion/ordering and production topology/entity collisions are Stage 02/03 |
| AT80, AT84 | Validated password-file/URL construction, local certificate identity checks, actual UTF-8/URL-reserved DB password authentication, actual restricted-grant/DDL/out-of-schema denials and runtime-only mounts | Ordinary external deployment PKI and real operator endpoints are not provisioned here |
| AT81 | Pinned MariaDB service initialized/migrated, retained-volume restart, fail-closed app outage/restart and local offline image lifecycle | Full Ubuntu/Rocky installation/backup/release acceptance remains Stage 08 |

Production evidence: backend/tests/stage1 (23 actual VM API tests),
backend/tests/integration (19 actual Linux MariaDB tests), backend/tests/unit,
frontend/e2e/foundation.spec.ts, verification/stage-1 browser/Docker/artifact logs.
Original golden fixtures, IDs, expected outcomes and image references are retained.

## Stage 02 topology/configuration evidence — 17 October 2026

Verification on the implemented application: **253 backend unit tests passed**;
**30 integration tests passed against real Linux MariaDB 11.8.9**, including ten
topology tests and the legacy startup-backfill test; **four topology browser
tests passed in 10.7 seconds**, including persisted drag/resize, and **ten
foundation browser regressions passed**. Exact timings are retained in the reports.

| Target | Implemented evidence | Remaining limit |
|---|---|---|
| AT05, AT06, AT07 | Administrator graph CRUD, explicit process reparent, directed labelled flows, stable IDs through rename/reload, shared Markdown descriptions and multiple views in [topology browser tests](../frontend/e2e/topology.spec.ts); invalid ownership and scoped relationships in [MariaDB topology tests](../backend/tests/integration/test_topology.py) | SSH/access checks are later stages |
| AT08, AT93 | Whole-system name/PCS/tag/documentation search, collapsed-process reveal, repeated IDs/names in different systems, and page-local searches in the topology API/browser suites | No historical/live log search is implemented |
| AT09 | Named geometry, collapse/reveal, transactional undo/redo, real drag/resize and persisted layout through reload are exercised by the browser suite | Log-update rendering behavior awaits the log engine |
| AT10, AT11 | YAML export/preview/commit through real API, JSON download/edit/preview/commit through browser, revision conflicts, explicit deletions, preview owner/project/digest/expiry checks, duplicate-ID guard, and rejected invalid imports | Project interchange only; Ansible inventory is Stage 07 |
| AT12 (partial) | Delete-impact preview lists model/flow/view dependencies; confirmed deletion, undo, immutable-ID tombstones, bounded full history and retained name snapshots are tested in MariaDB | Bookmarks, notes, event/log associations and active-session impacts require Stages 03–06; empty investigation/session lists do not prove those behaviors |
| AT43, AT78 (partial) | [Configuration unit tests](../backend/tests/unit/test_project_config.py) reject unsafe Markdown/assets without reflecting secrets; browser renders safe documentation as React text, preserves Inspector navigation and selection, and checks both themes/desktop sizes without external requests | Log/note rendering, collection errors and live controls await their stages; health remains explicitly unknown |
| AT86, AT117 | Explicit v1-to-v2 conversion retains IDs/content/layout, warns about legacy theme removal, forbids account/DB/secret fields, and requires explicit outer-project remapping. Fresh migrations, [startup backfill](../backend/tests/integration/test_topology_upgrade.py) and [populated 0002-to-0004 upgrade](../backend/tests/migrations/verify_populated_upgrade.py) preserve two systems, accounts/password verification, preferences, revisions and documentation | Upgrade uses guarded synthetic MariaDB data; no VM/production upgrade or legacy SQLite migration was performed |
| AT89 | Concurrent real MariaDB edits yield one committed winner and one 409; stale same-context browser drafts remain visible; direct Inspector writes fail and full configuration uses an Administrator-only projection | New SSH/live operations must preserve the same permission/revision boundary |
| AT101 (partial) | Archive/restore updates only the selected system and its revision, blocks shared mutations while archived and retains configuration | Active-job drain/start races and cached investigation access cannot be tested before those resources exist |

Result artifacts: [unit output](../verification/stage-2/checks/unit.log),
[MariaDB integration output](../verification/stage-2/s2_final_1017.log),
[topology browser report](../verification/stage-2/browser-final.json), and
[foundation browser report](../verification/stage-2/browser-foundation.json).
Configuration parsing is bounded to 10 MiB UTF-8/serialized content, depth 32,
200,000 tree nodes and 5,000 configured entities; project descriptions are at
most 10,000 characters and finite canvas coordinates/dimensions at most
10,000,000 in magnitude. Root lists and credential references remain proposals;
imports create no approvals, trust, bindings or target connections. Stop at the
Stage 02 gate before historical/log implementation.

## Stage 03 historical investigation evidence — 17 October 2026

The production parser and local transport feed MariaDB and the actual browser
viewer. Expected fixture files are used only by tests; production parsing,
filtering and identity code do not import the package oracle. This stage does
not implement SSH, live monitoring, bookmark editing or investigation bundles.

| Targets | Implemented evidence | Scope and limits |
|---|---|---|
| AT13–AT18 | [Engine tests](../backend/tests/unit/test_log_engine.py) compare every field of all 38 golden events and all 17 query sequences; [MariaDB API tests](../backend/tests/integration/test_history.py) independently reproduce those results, exact BIGINT UTC time, Unicode literals and large lines | Local plain/ZIP/TAR.GZ transport; event IDs retain their original derivation |
| AT19–AT21, AT44 | Actual-byte/download/member/line/count/ratio/deadline limits, corrupt CRC/trailer and unsafe member rejection, cancellation before indexing and [during partial copy/after committed batches](../backend/tests/integration/test_history_cancellation.py), partial manifests and temporary-file cleanup | Coverage is complete only for scanned candidates; observed timestamp extrema never prove continuity. ZIP64/multivolume and nested archives return explicit unsupported diagnostics |
| AT22, AT95 | Snapshot keyset pagination pins sequence/revision/filter/owner/project; later indexed events do not enter an old cursor. Byte-limited pages continue without skipped events. Context remains in source order with outside-filter/time labels | Diagnostic records receive no invented timestamp; truncated oversized previews retain unknown literal-match state |
| AT23 | Generated five-source 20 MiB benchmark exercises the production collector, MariaDB bulk index and warmed queries, with exact machine/limits and cold/warm timings in [benchmark evidence](../verification/stage-3/mariadb-benchmark.json) | Development WSL2/Docker measurement; not a certified 4-vCPU Ubuntu/Rocky installation or SSH latency measurement |
| AT45 | Existing bounded configuration parsing rejects executable/unsafe YAML; fixed parser strategies accept no executable expressions. Archive metadata allocation and literal term sizes are bounded | Connection/parser-preview workflows that require SSH remain Stage 04 |
| AT73, AT94, AT115 | Forged project/job/event/source/cursor/download/owner checks; real composite FK rejection of source type, source-process, source-job, job-workspace-owner and download-owner pairings. Administrators may audit-cancel another owner's job without private read access | HTTP historical paths implemented; WebSocket/live/bundle paths remain their later stages |
| R31, R32, R38, R47–R49 | [Historical browser tests](../frontend/e2e/historical.spec.ts) exercise real query/filter/context/download results, themes, merged/split panes, Unicode, and different/same-system pages in one browser context | Pages own their selection/filter/query state; account logout/theme preferences remain intentionally shared |
| R28, R41, R44, R55 | Retained collection deep links, interruption on restart, bounded auth/session freshness, typed tombstones preserving captured event names after topology deletion, and [lifecycle tests](../backend/tests/integration/test_history_lifecycle.py) | Full saved analysis layouts/notes/bookmarks and retention management remain Stage 06; populated upgrade verification preserves two systems/accounts/preferences to schema 0005 |

Current execution results: **321 backend unit tests**, **47 Linux MariaDB
integration tests**, **three historical browser tests**, **four topology browser
regressions**, and **ten foundation browser regressions** passed. The package
suite ran 128 cases with nine POSIX-only permission skips on Windows; those skips
are not represented as Linux runtime evidence. Ruff, mypy, frontend lint/types,
generated API consistency and the bundled build passed. Final stage status and
the performance record are maintained in [STATUS.md](../progress/STATUS.md).

The optional `lane` field added to the query schema defaults to `events`, keeping
existing golden request payloads valid. The immutable read-through cache is
bounded to 64 MiB including builds and leases, with a five-minute TTL. Its full
scope includes project, owner, capture/config/snapshot/auth revisions,
process/time scope and lane. Every hit rechecks MariaDB authorization and current
session state. Cold, expired or evicted scopes use the bounded SQL scan.

## Server SSH setup correction - 17 October 2026

R05 and the configuration portion of R13 now expose the canonical SSH endpoint
inside Add/Edit server. An Administrator can create a connection profile and its
server in one revision, inspect the host/port of reused profiles, and edit the
profile from server details. No connection data was added to Inspector responses.
The [topology browser suite](../frontend/e2e/topology.spec.ts) verifies invalid
ports, cancellation without writes, one-transaction server/profile persistence,
atomic undo/redo, endpoint editing/reload and reuse without duplicate profiles.
Its four existing topology/role/window regressions also pass; five cases passed
in the [browser report](../verification/stage-3/browser-server-ssh-final.json).
Both themes and desktop sizes are captured in the new server-ssh screenshots.

This is configuration evidence only. R13 credentials/jump transport/trust and
AT24-AT29/AT46 remote retrieval remain Stage 04; saving a profile creates neither
password storage nor target/root/host-key approval. The current collector still
uses the explicitly enabled synthetic local transport. See
[status](../progress/STATUS.md) for actual commands and verification limits.

## SSH password and connection-test slice - 17 October 2026

| Requirements/targets | Implemented evidence | Remaining limit |
|---|---|---|
| R13, AT24/AT29 (setup portion) | Encrypted write-only passwords, explicit project bindings, direct/single-jump SSH/SFTP tests in [transport tests](../backend/tests/unit/test_ssh_transport.py) and [browser tests](../frontend/e2e/ssh.spec.ts) | No remote historical planning/download or source/root approval yet |
| R14/R35, AT25/AT26/AT46 (setup portion) | Target/jump strict keys, no target authentication during inspect/rejected-key paths, validated pinned addresses, password-only auth, bounded connections and no exec/write; independent host-key approval and revoke | Full collection permissions/archive/root checks remain Stage 04 |
| R39/R42/R44/R48, AT73/AT94/AT115 | [MariaDB SSH setup tests](../backend/tests/integration/test_ssh_access.py) cover write-only ciphertext VARBINARY, scoped aliases/trust, Inspector denials, concurrent password changes and wrong-type scoped FKs | These checks do not authorize remote log collection or claim full vault rotation/recovery |
| R35/R40, AT74/AT77 (setup portion) | [Barrier tests](../backend/tests/integration/test_ssh_revocation.py) cancel pending checks within two seconds after credential/trust/config/logout changes or failed/timed-out fresh DB checks | Full live stream revocation remains later scope |
| R34/R38/R47-R49 | Three real browser setup cases, same-context system collision isolation, four inspected light/dark desktop screenshots; seven topology/keyboard/modal regressions | No live monitor implementation or latency claim |

Actual results: 61 Linux MariaDB integration tests, 371 Windows unit passes
(one POSIX permission skip), 50 Linux SSH/vault/helper passes with no skips,
three SSH browser cases and seven topology/keyboard regressions. A populated
0002-to-0006 upgrade preserves existing identities/accounts/preferences, and the
running local development schema was separately backed up before migration.
See [current status](../progress/STATUS.md) for commands, failures corrected and
unrun gates. This is a user-requested connection setup slice, not a passed full
Stage 04 historical collection gate.

## Stage 04 approved historical SSH collection - 17 October 2026

| Requirements / targets | Implemented evidence | Limits |
|---|---|---|
| R13/R35, AT24/AT25/AT46 | Existing vault/trust checks plus explicit project/configuration/route/credential/root-bound source approvals in [source access](../backend/src/inspector/source_access.py); independent target/jump keys, expired credentials and revoked approvals tested | Imports never approve targets. Automatic vault-key rotation/recovery and real distribution interoperability remain release work |
| R14/R15/R19, AT26/AT27 | [SFTP tests](../backend/tests/unit/test_ssh_files.py) cover configured candidates, canonical roots, regular files, permissions, traversal/symlink rejection and byte/count/time limits. Inspector setup requests fail; normal approved collection succeeds | Dedicated read credentials remain required. Symlinks are rejected. No general command, arbitrary test path or target-write API |
| R16/R17/R18/R24/R31/R32, AT28 | [Real SSH/MariaDB tests](../backend/tests/integration/test_history_ssh.py) download all 21 golden sources directly and through one jump and compare all query results, exact UTC/time/filter behavior, raw text, checksums and byte/member provenance with Stage 03; 38 events and one unknown-timestamp diagnostic | Captures receive new snapshot/event identities; existing fixture event IDs are unchanged. Snapshot probes cannot prove every transient or same-size rewrite |
| R13/R27/R39/R40/R47-R49, AT29 | One compatible route is reused per guarded operation and closed on completion/failure/cancel; no cross-system/owner/job connection sharing. [Approval tests](../backend/tests/integration/test_source_access.py) cover revocation/expiry/configuration changes and final reservation freshness | Live subscriptions, reconnect and reference-counted live capture reuse remain Stage 05 |
| R42/R44/R48 | Migration 0007 adds scoped approval composite FKs and nullable credential expiry. Populated 0002-to-0007 migration preserves systems/accounts/preferences/immutable entities. [Supervisor cancellation tests](../backend/tests/integration/test_supervisor_cancellation.py) verify cancellation preserves the dedicated lock connection and lost ownership fails closed | No production migration or full backup-restore/release qualification |
| R34/R38/R47-R49 | [SSH browser suite](../frontend/e2e/ssh.spec.ts) exercises real configured-path checks and Inspector jump-host history with two pages in one browser context; both themes/sizes preserve workspace, capture and filters | No live monitoring or latency claim |

The full Linux MariaDB integration run passed **89 tests** without skips. Linux
unit tests passed **463**, with one Windows-only DACL skip. Four SSH browser
scenarios passed. Commands, final regression results, preserved failures and
qualification limits are recorded in [STATUS.md](../progress/STATUS.md).

The 17 October connection-editor follow-up adds R13/R15/R19 setup diagnostics:
active, rotated and archive paths are labelled with their process/server across
a shared profile, and excluded paths explain how to add a root before moving
sources. The focused browser case in `frontend/e2e/topology.spec.ts` verifies
rejected saves leave configuration/revision unchanged, component boundaries,
successful root additions preserving sources, and both-theme draft/layout
behaviour. Backend validation and explicit source approvals remain enforced;
the running app bundle was not replaced by this source-only follow-up.

The UTC-control follow-up covers R17/R18/R34/R49 in
`frontend/e2e/historical.spec.ts`: second-precision space-separated entry and
date/time selectors send canonical UTC bounds even from a non-UTC browser;
invalid dates/times and empty or reversed intervals stop before dispatch.
Selector edits invalidate collection plans; Cancel and Escape preserve bounds,
and duplicated same-context pages retain independent drafts. Existing precise
API bounds retain microseconds until edited. Both-theme desktop and narrow
picker captures exercise the actual component with the real local API. See
`progress/STATUS.md` for executed checks and results.

## Conditional manual source confirmation - 17 October 2026

The explicit user request adds the global Administrator setting **Additional
security measures** (`additional_security_measures`, default true). It makes
the Stage 04 manual target/root confirmation conditional: when disabled, saved
path/parser changes are usable automatically for subsequently requested
operations. This updates the manual-confirmation rule; explicit target/jump
host-key trust, valid project-bound credentials, root/path validation, imports
without network activity, ownership, RBAC and CSRF continue to apply.

| Requirements / targets | Implementation and focused coverage | Limits |
|---|---|---|
| R13/R19/R35/R39, AT24/AT25/AT26/AT73 | Revisioned Administrator-only settings and source snapshots enforce the saved policy; [security setting tests](../backend/tests/integration/test_security_setting.py) cover both modes, source revisions, credential/trust failures, policy-change cancellation and denied writes | Disabled mode creates no synthetic approval; reenabling requires a valid current source approval |
| R42/R44 | Migration `0008_security_setting` persists a checked non-null boolean with an enabled default, retaining existing settings/approval rows | No production migration or release qualification is implied |
| R34/R38/R47-R49 | Settings and configured-source access controls explain the effective policy and preserve page-local system/filter state; `frontend/e2e/ssh.spec.ts` covers persisted off/on modes, actual path/parser edits, SSH collection and mandatory host-key verification | Browser coverage and actual command results are recorded in [STATUS.md](../progress/STATUS.md); live monitoring remains Stage 05 |

## Active-log append correction - 17 October 2026

R16/R19/R31/R32 and AT26/AT27/AT28 use the active-file snapshot contract in
document 04: freeze a byte boundary and collect that prefix while later entries
continue arriving. [SFTP regression tests](../backend/tests/unit/test_ssh_files.py)
cover appends before open, during planning, between connections, during path
checks and every copy/probe read, including empty files and unterminated lines.
They verify unchanged byte budgets and checksums, and retained rejection of
truncation, replacement after observed growth, prefix rewrites, equal-size
metadata changes and changes to rotated/archive sources.
[SSH/MariaDB integration](../backend/tests/integration/test_history_ssh.py)
checks exact cached bytes, indexed rows, offsets and coverage across simultaneous
appends, then retrieves the new rows with another collection while the earlier
investigation stays unchanged. This does not add live following or prove absence
of every transient rewrite/path race; the SFTP v3 limitations remain explicit.
Actual verification results are recorded in [STATUS.md](../progress/STATUS.md).

The table identifies the scope and test locations, not a passing test report.

## Historical collection usability and deletion - 17 October 2026

| Requirements | Implementation and behavior coverage |
|---|---|
| R16/R17/R18/R19/R24/R31/R34 | HistoricalViewer loads Timestamped events after collection and retained reopen, supports direct collection with optional preview, and displays Log entry without its parsed timestamp. Original raw text remains in Context and literal predicates. `frontend/e2e/historical.spec.ts` asserts the golden event IDs, exact remaining text, raw Context and absence of preview requests on direct collection. |
| R35/R41/R42/R44/R48 | Owned terminal deletion removes scoped SQL events/sources/cursors/grants/job, invalidates cached snapshots, safely removes captured files, and audits the action. `backend/tests/integration/test_history_deletion.py` tests both roles, ownership/project/CSRF denial, active jobs, stale resources, concurrent queries/downloads, cancellation, rollback and cleanup failures against MariaDB. Unit tests cover cache accounting, filesystem boundaries and rollback-error restoration. |
| R38/R47/R49 | Browser tests use two pages in one context/account/system: deleting one collection preserves the other's workspace, results and filters. Light/dark captures cover the Log entry table and deletion confirmation. |

Actual commands, test results, initial corrected failures, prepared artifact and
installation status are recorded in [STATUS.md](../progress/STATUS.md). This
follow-up stays within historical collection; Stage 05 remains the next gate.

## Stage 05 — live capture and independent monitor controls

| Requirements / targets | Implemented behavior and test locations |
|---|---|
| R20–R24, AT30–AT33/AT37 | `live_engine.py` pins source boundary S, retains unfiltered original bytes, seeds timestamped matching rows (including distinct pane targets), preserves partial UTF-8/lines and source-range identity, and refilters without reconnecting. `test_live_engine.py` covers sparse/unknown history, limits, boundary races, late/equal ordering and Unicode/literal predicates; `test_live_sftp.py` runs the actual pinned SFTP adapter, five low-rate sources and an idle peer. |
| R25–R27/R32, AT34–AT41 | Raw event/byte retention, actual serialized frame/replay limits, visible eviction/backlog/continuity, deadline-based 500 ms merge buffering, bounded reconnect, old-handle rotation drain and copytruncate generation changes. Unit plus actual SFTP tests cover failures, rekey blocking, retention, slow replay and shared source refcounts. Transient capture makes no durable/lossless claim. |
| R27/R28/R41/R42/R44, AT40 | Explicit recording saves retained nonmatches and new original ranges before publication into owned MariaDB historical jobs/events. Recording byte/event caps, cancellation, rollback-safe cache append, offline query, recorded history top-up and deletion/link cleanup have unit and actual MariaDB/SFTP coverage in `test_live_controls.py` and `test_live.py`. Full investigation editing remains Stage 06. |
| R35/R39–R41/R48/R49, AT47/AT74/AT83/AT90/AT96–AT99 | Protocol 2 validates exact Origin/Host, cookie/CSRF, owner/project/workspace/lease and filter epochs; each protected dispatch and silent watchdog reauthorize with bounded fail-closed DB checks. Queued obsolete ACKs cannot reset filters. Private content stays owner-only; audited Administrator stop returns operational metadata only. `test_live.py` covers stale/forged references, revocation, actual supervisor loss, explicit transfer/quota races, detached expiry and real backend restart without SSH resumption. |
| R42/R44/R48/R50 | Frozen `0009_live` DDL adds scoped session/workspace/owner/revision/recording and subscription/process foreign keys. Atomic reservation checks workspace, system, account and deployment limits, including transfer to a full workspace. Real MariaDB tests reject cross-scope/owner associations; populated upgrade preserves the preexisting accounts/preferences/two-system state. |
| R21/R23–R25/R34/R38/R47/R49/R50, AT30/AT31/AT34/AT38/AT68/AT92/AT96–AT100 | `LiveViewer` measures each pane, virtualizes exact UTC order, applies independent literal overrides, distinguishes receipt/pause/stop, reports retained/filtered/evicted/visible counts and offers explicit resume. `frontend/e2e/live.spec.ts` uses same-context pages for both roles, different/same systems, stale frames/responses, theme persistence, duplication/reload, slow/closed pages, account-wide logout, two × five sources, bounded history/archive work and visible eviction. Screenshots and first-DOM-insertion timing/resource artifacts are under `verification/stage-5`. |

Executed commands and actual results, including initial failures and remaining
platform/release limits, are recorded in [STATUS.md](../progress/STATUS.md).
Local container/browser evidence does not qualify Ubuntu/Rocky deployment,
the full proxy/browser process memory envelope, sustained production operation,
or the Stage 08 offline release gate. The paced capacity scenario reserves two
times five subscriptions in one browser context/account, holds one page's
delivery and runs two simultaneous historical investigations, each containing
an exact 16 MiB/65,536-event archive. It requires first-DOM p95 at most 2 seconds
at 1–5 physical appends/s, matching active-job/resource evidence, complete
archive counts and stable Stop. Stage 06 investigation tooling and Stage 07
Ansible reconciliation are not marked complete by these tests.


## Stage 06 investigation implementation

Stage 06 adds executable coverage below. Actual commands/counts, corrected
failures and platform limits are recorded in `progress/STATUS.md` and
`verification/stage-6/`; this table alone is not a passing-test report.

| Requirements / acceptance | Implementation and executable evidence |
|---|---|
| R12 / AT51 | Existing directed dependency traversal now offers Inspect/Monitor highlighted neighbours. Browser tests verify directional selection and five configured downstream processes, with an explicit causality limitation. |
| R28 / AT48 | Saved workspace process/time/filter/layout/notes state shares optimistic revisions with bookmarks. MariaDB tests reopen through a real backend restart with SSH forbidden and retain unavailable status after explicit expiry; browser tests reopen same-context deep links and restore filters/panes. |
| R29 / AT49 | Exact parsed metadata equality distinguishes golden REQ-0042 from REQ-00420; literal search uses the shared casefold engine. Deterministic chronological traces expose exact integer deltas and physical-source time inversions. Tests cover punctuation, quoted and Unicode marker keys. |
| R30-R31 / AT50 | Owned source-order bookmarks/annotations preserve event/name snapshots. Context includes unmatched/out-of-range lines independently of totals; separate context pins survive original cache expiry. Whole-investigation pins prevent expiry, and deletion cannot silently discard bookmarks. |
| R32 / AT52 | Source details expose raw/index availability, checksums, captured ranges, retained parse counts and observed extrema with completeness limitations. Unavailable queries return null match counts and partial coverage. Existing SSH/parser/partial-capture regression cases remain applicable. |
| R33/R35 / AT53-AT54 | Typed bundle projections, all-string literal redaction preview, regular-member streaming, actual-byte/count/deadline/ratio bounds, checksums and version checks. Tests preserve original cache hashes, reject corrupt/unsafe/future input before commit and prove import/replay does not connect to hosts. |
| R33/R41/R48 / AT76/AT118 | Both roles perform private analysis and sanitized exchange. Every content route checks project/owner; Administrator has no private-content bypass. Foreign imported identities remain provenance in separate offline tables, with separately revisioned personal edits and immutable event documents. MariaDB rejects composite owner/project FK forgeries. |
| R42/R44/R48 | Additive migrations through 0012 preserve all existing Stage 05 table rows, accounts, preferences, policy, project IDs and repeated scoped source/event IDs. Verification uses new disposable MariaDB schemas, never SQLite or the retained installation. |

Bundle version 1.0 exchanges retained decoded event text and source identity/
byte-range/checksum provenance. It does not provide an original binary-source
archive or enable a raw source download from imported provenance. Redaction
changes exported copies only; unchanged original cache bytes and the immutable
imported event document remain separate from personal analysis.

## Stage 07 — static inventory, diagnostics and UI acceptance

Stage 07 adds the implementation and evidence below on 18 October 2026.
Earlier stage sections remain historical evidence for their stated scope.
The source expects `0013_inventory`. Implementation verification preserved the
then-installed Stage 06 artifact and retained data; the subsequent separately
authorized local Stage 07 deployment is recorded below. Acceptance IDs identify
the behavior exercised, not an automatic declaration that every part of that
target or the Stage 08 release gate is complete.

| Requirements / acceptance | Implementation and executable evidence |
|---|---|
| R11/R51/R52 / AT55, AT102–AT105 | [Production static parser](../backend/src/inspector/inventory_parser.py), [parser unit tests](../backend/tests/unit/test_inventory_parser.py), [actual MariaDB inventory tests](../backend/tests/integration/test_inventory.py) and [inventory browser tests](../frontend/e2e/inventory.spec.ts) use supplied INI, extensionless `hosts`, nested YAML, canonical JSON and companion ZIP directly. Expected output is three aliases/host mappings; INI/extensionless input has zero processes, while the supplied YAML/JSON/ZIP extensions have five. Tests cover literal all/ancestor/child/host precedence, explicit ZIP source order, uploaded-relative companions, ignored files and value/declaration provenance. No Ansible installation or server-filesystem fallback is used. |
| R06/R52 / AT57, AT107, AT113 | [Wizard](../frontend/src/components/InventoryImport.tsx) and [reconciliation tests](../backend/tests/unit/test_inventory_reconcile.py) require one subsystem per host, allow an explicit host override, retain accepted cross-cutting/manual tags and show exact tag differences. New mapped subsystem IDs create empty named definitions. Optional process IDs/log sources are validated; parser/jump/credential references resolve in the selected system. A real MariaDB test maps five initially missing parser references to an existing same-system parser and rejects an existing foreign-system parser. Explicit subsystem mapping resolves only subsystem ambiguity; other unsupported static conflicts require corrected input or trusted canonical JSON. |
| R11/R48/R53 / AT56, AT108–AT109 | [Inventory service](../backend/src/inspector/inventory.py) persists source+alias/local-process mappings rather than matching filenames/IPs. Unit/MariaDB/browser cases cover same-source renamed-file reimport, independent systems/sources, stable IDs, address updates, exact changes, preserved descriptions/geometry/flows/unrelated processes/manual tags, absent host/process retention and blocked manual-field conflicts. An unchanged accepted import does not increment topology revision. Unmapped predictable-ID collisions cannot adopt manually configured entities. A real approved SFTP monitor remains bound to its original stored snapshot when reimport changes an optional process path; the test verifies the new path is never opened and the existing monitor retains its old revision/snapshot with an honest revision-conflict interruption. |
| R35/R39/R41/R48/R53 / AT110, AT114 | Every source/upload/parse/preview/commit/cancel route checks Administrator authority and project/owner scope; HTTP mutations require CSRF. MariaDB tests reject wrong project/owner/source upload relations, stale revisions, modified mapping digests, expired staging and forged Inspector requests without topology changes. In-flight upload revocation releases auth locks and rejects the result. Preview-only cancellation preserves the upload for Back/remapping; upload/wizard cancellation removes it and all previews. A dedicated injected-failure test observes real uncommitted topology/mapping/revision SQL, proves rollback restores all of them and keeps the preview/raw upload retryable, then commits the same preview successfully. Its [isolated result](../verification/stage-7/s7_87adc442.log) passes. |
| R13/R35/R52/R54 / AT58, AT106, AT111–AT112 | Recursive secret omission excludes password/key/become/token values and unsafe SSH arguments from normalized data, responses and diagnostics. Tests reject dynamic/script/plugin/required-template/Vault semantics; duplicate JSON/YAML keys, tags/anchors/aliases/cycles; unsafe, linked, encrypted, normalized-colliding or nested archive members; and actual byte/file/depth/node/line/field/time limits. [Configured-limit tests](../backend/tests/unit/test_inventory_limits.py) plus real upload cases prove lower deployment upload/expanded/file ceilings are enforced and rejected uploads leave no staging. Restricted raw files expire after 15 minutes; commit/upload cancel/expiry cleanup is exercised. [Worker cancellation tests](../backend/tests/unit/test_inventory_workers.py) exercise actual parser callbacks on HTTP/task cancellation and project-scoped staging removal; the shared worker slot is held until exit. Real MariaDB/API cases pass for cooperative parser termination after upload cancellation and expiry/reaping. Import creates no SSH trust or source-approval rows and starts no connection. |
| R17/R19/R35/R39 / AT59 | [Parser diagnostics](../backend/src/inspector/diagnostics.py) uses the collection timestamp/metadata engine for unsaved drafts. [Unit tests](../backend/tests/unit/test_diagnostics.py) assert ISO and fixed-width UTC results, exact integer microseconds, original text/physical-line framing, null invalid timestamps and safe errors. Bounds are 64 KiB UTF-8, 100 physical lines and 4 KiB per line. [MariaDB API tests](../backend/tests/integration/test_diagnostics.py) check role/CSRF/project/revision, no persisted sample/draft and logout while the off-loop worker runs. Configured path/archive access diagnostics retain the Stage 04 approved-ID SFTP boundary; the expanded UI test exercises the actual path check and pasted/uploaded sample panels. |
| R24/R34/R35/R38 / AT60, AT67–AT70 | [Log highlight helper](../frontend/src/logHighlight.ts) and shared React log rendering apply only acknowledged historical/live global and owning-process filters. [Ten Node cases](../frontend/tests/log-highlight.test.mjs) cover literal punctuation, Unicode expansions/sigma/Turkish forms, UTF-16/astral offsets, overlapping terms, hidden timestamp prefixes, draft-versus-applied state, clearing, bounded mark counts, escaped text and preservation of every source character. [One generated-table parity test](../backend/tests/unit/test_casefold_generated.py) verifies the bundled browser casefold data exactly matches the locked Python 3.13 Unicode table. Highlighting does not change backend matching, source text or event identity. |
| R42/R44/R48/R53/R55 / AT83, AT110, AT115–AT117 | [Migration 0013](../backend/migrations/versions/0013_inventory.py) adds scoped source/upload/preview/host/process mapping tables. Preview-to-upload FKs include project, upload, source and owner; mapping targets reference same-project immutable identities. [Populated upgrade verifier](../backend/tests/migrations/verify_stage7_upgrade.py) upgrades a new guarded Stage 06 schema and checks all existing rows, accounts, system IDs, repeated scoped event IDs and raw bytes. [Recorded result](../verification/stage-7/s7_upgrade_b2f96b1d.log) preserves all 43 existing tables and their data. No SQLite or retained installation is used. |
| R34/R38/R39/R47/R49 / AT60, AT70, AT88, AT119 | [Expanded UI acceptance suite](../frontend/e2e/ui_acceptance.spec.ts) passes its four cases in the [final combined browser run](../verification/stage-7/browser-inventory-ui-final.json). It exercises both roles/themes at 1280×720 and 1920×1080, measured rendered text/focus contrast, keyboard navigation, 200% CSS zoom and 640×360 responsive reflow, menus/dialogs/error/empty/loading states, durable appearance, public login/defaults and account-wide logout. Same-context five-plus-five monitors verify pause/theme/filter-draft/Stop isolation and unambiguous system titles; a two-subsystem scene checks the reference layout. The [focused visible-mark/selected-text rerun](../verification/stage-7/browser-visible-highlight-review.json) passes 2/2 after scrolling matches into view and asserting actual visibility. The [reference-fit review](../verification/stage-7/browser-reference-fit-review.json) passes 1/1 after awaiting animated Fit and readable node widths. [Manual review](../verification/stage-7/ui-review.json) covers nine representative final images, with 257 retained screenshots including earlier attempts, 60 contrast reports, 6,308 rendered-text samples with zero failures and 29 focus measurements with minimum contrast 5.23. |
| R03/R34/R37 / AT61 | [Thirty-minute synthetic workload](../frontend/e2e/stage7_soak.spec.ts) navigates a 60-process model while five real SFTP sources append at a combined one line/second. [Measurement/analyzer result](../verification/stage-7/soak-7a61b20c3d49-summary.json) passes after 1,811.677 actual seconds with no observed source errors, gaps or reconnects. This uses the existing three-server fixture, not the full 10–20-host or native-OS deployment baseline. Measurement completion and the separate successful cleanup recovery are distinguished below from the original browser flow's cleanup failure. |

The [raw AT61 observations](../verification/stage-7/soak-7a61b20c3d49.json)
contain 14 resource samples across 1,811.677 seconds. Actual component results
are reported separately; the browser is a Windows client and MariaDB is a
shared synthetic-test container.

| Component | Observed memory | Observed CPU |
|---|---|---|
| Linux ASGI application | RSS 120.64 → 125.47 MiB; peak 125.47 MiB | Average 12.77% of one core |
| Windows Chromium client processes | Working set 411.79 → 492.71 MiB; peak 525.65 MiB | Average 5.42% of one core |
| Shared MariaDB fixture | Docker memory 1,017–1,018 MiB under its 1 GiB container cap | Sampled 1.47–3.46%; mean 2.13% |
| HTTPS proxy | Absent; 0 bytes in this direct-ASGI-TLS fixture | 0; no proxy qualification |

The application used two OS tasks/threads, 12–14 socket descriptors and
17–19 total descriptors; the monitor retained one WebSocket with no reconnects.
These are measured OS counts, not an assertion about unexposed asyncio task
objects. The finite workload stayed below the application RSS target and showed
bounded trends; it does not establish the full native Ubuntu/Rocky, 10–20-host,
proxy-inclusive release resource envelope.

The measurement and analyzer pass are **not an original soak-browser pass**.
The [initial browser failure](../verification/stage-7/soak-browser-initial-cleanup-failure.log)
occurred only during post-measurement cleanup: restoration submitted the original
embedded project revision 2 while the current expected revision was 3, receiving
409. The [separate real cleanup recovery](../verification/stage-7/soak-cleanup-recovery.json)
passed **1/1** after normalizing that embedded revision. It restored the exact
configuration content at revision 4, the same target/root approval and original
log-byte hashes. Original failure artifacts remain preserved.

Recorded verification separates the complete regression run from the final
focused tests added after it:

- [Full Linux MariaDB/SFTP regression](../verification/stage-7/s7_59c5b714.log):
  **168 passed**, using a new disposable schema.
- [Final focused inventory/diagnostics run](../verification/stage-7/s7_e968b222.log):
  **19 passed, 1 failed** in 31.50 seconds. Cooperative cancellation/reaping,
  lower ceilings, remapping, positive same-system parser mapping, injected
  rollback/retry and parser logout-after-worker pass. The new live-path test
  incorrectly required top-level `blocked`; the existing guard actually records
  `interrupted` / `REVISION_CONFLICT`. This was a test assumption, not a product
  retargeting defect.
- [Corrected live-path isolated rerun](../verification/stage-7/s7_45bf1803.log):
  **1 passed, 19 deselected** in 7.36 seconds. The test now appends a distinct
  sentinel to the old path, verifies old-path continuation or an honest
  revision-conflict interruption, and rejects any new-path open/data while
  preserving the stored source snapshot. Serving source is identical across
  these two runs: **all 20 distinct focused cases have passing evidence**, not
  a single 20-pass run. The earlier [15-pass run](../verification/stage-7/s7_fff6e807.log)
  and [isolated injected rollback check](../verification/stage-7/s7_87adc442.log)
  remain preserved as earlier verification.
- [Windows backend units](../verification/stage-7/checks/unit.log):
  **800 passed, 4 skipped** in 28.36 seconds. The final
  [combined Linux verification](../verification/stage-7/linux-unit-package.log)
  reports **803 unit tests passed, 1 skipped**, with five known warnings, in
  27.61 seconds, followed by **all 128 package cases passing** in 2.475 seconds.
  These are recorded platform-specific runs, not a claim that skipped checks ran.
  The earlier [128-pass Linux package-only check](../verification/stage-7/linux-package-only.log)
  remains earlier evidence; the combined run is now the final Linux result.
- [Final Windows package run](../verification/stage-7/final-checks/package.log):
  **128 tests, 9 skipped; exit 0**, in 17.305 seconds. The earlier
  [corrected targeted receipt](../verification/stage-7/windows-package-targeted.log)
  records the same counts in 13.985 seconds. The earlier
  [package log](../verification/stage-7/checks/package.log) retains a temporary
  source-copy failure because the newly linked `.mjs` test was omitted from that
  copy. Including `.mjs` in the verification source copy fixes that harness
  failure; no application requirement or assertion was removed. Earlier Linux
  source-copy/link failures and their corrected reruns are recorded in
  `progress/STATUS.md`; the final combined Linux log contains the successful run.
- [Final combined inventory/UI browser run](../verification/stage-7/browser-inventory-ui-final.json):
  **17/17 passed** in 200.45 seconds, with no skips, unexpected or flaky cases.
  All 13 inventory and four UI cases use the same final built artifact. Inventory
  coverage includes the five inputs/reimports, conflicts/manual preservation,
  Back/source switching, cancellation during parse/preview followed by a fresh
  retry, two system-scoped windows and Inspector endpoint denials. Non-origin
  requests are blocked. The earlier [10-pass inventory run](../verification/stage-7/browser-inventory.json)
  remains historical evidence. Additional same-artifact focused reviews pass
  [2/2 visible-mark/text cases](../verification/stage-7/browser-visible-highlight-review.json)
  in 68.31 seconds and [1/1 reference-fit case](../verification/stage-7/browser-reference-fit-review.json)
  in 6.40 seconds; these are focused reruns, not additional distinct cases in
  the 17-case combined count.
- [Frontend Node tests](../verification/stage-7/frontend-tests-final.log):
  **10 passed**, including generated API consistency. Final
  [Ruff](../verification/stage-7/final-checks/ruff.log),
  [format](../verification/stage-7/final-checks/format.log) (163 files),
  [mypy](../verification/stage-7/final-checks/mypy.log) (37 source files), frontend
  lint/types, API/Node tests, artifact verification, package validation and normal
  repository-configured diff checks all pass in the
  [ten-command final receipt](../verification/stage-7/final-checks/commands.json).
  The earlier diff harness incorrectly overrode `core.autocrlf=false`, producing
  CRLF whitespace errors; its [receipt](../verification/stage-7/final-checks/commands-with-crlf-override.json)
  and [output](../verification/stage-7/final-checks/diff-crlf-override.log) are
  retained. The corrected diff uses the repository's line-ending configuration
  and exits 0; prior attempts are not relabelled as passes.

The combined visual matrix/contrast/keyboard/zoom run, focused visible-text and
reference-layout captures, and representative manual review are complete.
AT61's thirty-minute 60-process/five-monitor workload
has the measured evidence and separate cleanup recovery above. Native
Ubuntu/Rocky installation, the full 10–20-host/proxy-inclusive resource baseline
and AT120's final three-image cold offline
backup/restore release remain outside that evidence. Stage 08 remains separate.
Exact commands, corrected failures and
remaining gates are maintained in [STATUS.md](../progress/STATUS.md).

The Stage 07 synthetic fixture services are stopped. The
[retained-installation comparison](../verification/stage-7/retained-comparison.json)
matches the recorded 8444/8445 container/image identities, start/restart state,
served asset hashes and existing runner tags at the source/verification gate.
Building and verifying Stage 07 did not install it over those retained applications.

The later explicit "Deploy stage 7" authorization on 18 October 2026 upgraded
only **https://localhost:8445** from `0012_offline_analysis` to
`0013_inventory`. The exact tested wheel
`908c3befbd0053da388c8d14916e7e40ff12efb99b2ff8d43fe1296cdb63c729`
is installed read-only under `.state/stage7-install/backend`, using the same
pinned runtime image. The [backup receipt](../verification/stage-7/deployment-backup.json)
records a consistent 194,617,923-byte SQL dump, its checksum and matching cache;
protected recovery material remains under
`.secrets/stage7-install/pre-0013-inventory/`. The
[migration receipt](../verification/stage-7/deployment-migration.json)
preserves all 44 old table counts and 43 non-Alembic checksums and verifies five
new empty inventory tables. The
[installation receipt](../verification/stage-7/deployment-installation.json)
checks the installed module/assets against the wheel, verified TLS/readiness,
all 34 stable table checksums, 897 original cache files (230,864,349 bytes),
957 ownership/mode entries and unchanged configuration/vault. Port 8444's
container, image, start/restart state and assets remain unchanged. Exact
wheel membership and installed-runtime checks also pass in the
[independent post-deployment audit](../verification/stage-7/deployment-audit-post.json):
62 wheel members, 40 runtime files, three served assets and two bundled notices;
unauthenticated WebSockets return 403 and runtime database grants remain
DML-only. Installed browser results, preserved failed helper attempts and their
scope are recorded in
[STATUS.md](../progress/STATUS.md). Stage 08 has not started; this local upgrade
does not qualify the offline release or native Ubuntu/Rocky installation.
