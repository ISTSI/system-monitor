# 01 — Product requirements

## Purpose and scope

An operator documents one of several configured system topologies, selects the processes involved in a known event, retrieves the relevant historical logs, and follows a transaction across processes live or retrospectively. This is not a general infrastructure-monitoring platform or a CMDB with automatic discovery. All requirements below are in scope for the final release, although the plan implements them incrementally.

## Environment

| ID | Requirement |
|---|---|
| R01 | Run the application on an Ubuntu or Rocky Linux server and expose a web UI to Windows 10/11 browsers. No installed desktop client is required. |
| R02 | Work without Internet access at runtime, including first page load after an offline restart. The application server may reach authorised monitored hosts/jump hosts over LAN/VPN. Cached investigations remain usable when those hosts are unavailable. |
| R03 | Support 10–20 hosts, 30–60 processes and at most ten processes per host **per configured system**; approximately 10–20 MB per investigation. One 16 GB application server must support two systems monitored concurrently from two windows by the same user, up to five live processes per window (ten total) at the stated low event rate. These are design targets, not arbitrary hard entity limits. |
| R04 | Support individually authenticated local accounts with exactly two roles: Administrator and Inspector. Multiple tabs/accounts may be active. Administrators edit shared configuration with optimistic concurrency; real-time collaborative editing is not required. |

## Topology and documentation

| ID | Requirement |
|---|---|
| R05 | Create, rename, document and delete subsystems, physical servers and configured process instances through the UI. Preserve stable internal identities. |
| R06 | Visually contain servers within one subsystem and processes within one server. A server cannot belong to multiple subsystems. Reparenting is explicit and validated, not an accidental drag side effect. |
| R07 | Add directed, labelled process-to-process data-transfer relationships within or across servers/subsystems. Store protocol and descriptive metadata where supplied. |
| R08 | Selecting an element opens a documentation/configuration inspector; read formatted Markdown safely. Documentation is shared across diagram views. |
| R09 | Search the complete **active system only**, not another window’s system, by server/process name, configured PCS resource name, tags and documentation. Selecting a result opens a relevant view, expands ancestors and centres/highlights it. |
| R10 | Provide pan/zoom, selection, multi-selection, drag/resize, collapse/expand, fit-to-selection, minimap, undo/redo and multiple named views. Do not duplicate model entities just to display them in another view. |
| R11 | Edit topology in UI, export/import editable versioned YAML/JSON, and read uploaded Ansible static INI/extensionless hosts files, YAML inventories, supported inventory bundles and canonical JSON with preview/reconciliation (R51–R54). Preserve stable IDs and metadata on reimport. |
| R12 | Highlight upstream/downstream dependencies and add selected neighbours to an investigation/live selection. Topology links describe possible transfers; they do not establish actual causality. |

## SSH, configuration and logs

| ID | Requirement |
|---|---|
| R13 | Configure reusable username/password SSH connection profiles, optionally through one jump host with its own credentials and host-key trust. Target Linux hosts include the user's current CentOS environment and Rocky Linux 9. Do not assume a particular CentOS release. |
| R14 | Be agentless and limited to UI-defined read-only inspection. No shell/terminal, arbitrary command input, remote agent, discovery or service control. Use a dedicated non-sudo log-read account. Clearly diagnose missing permissions. |
| R15 | Each process has one logical plain-text log source, an active path and optional rotated plain files, ZIP and TAR.GZ archive patterns/member selectors. Instances of the same executable remain distinct configured processes, optionally labelled with a PCS resource name. |
| R16 | Download/stream relevant sources into bounded server-side cache, decode supported archives, and parse one physical line per event. UTF-8 is the default, with an explicit configurable alternative encoding. Retain original bytes/provenance where collected. |
| R17 | Use full UTC event timestamps, including configured fixed-width variants. Preserve timestamp text, parse exactly and surface failures. Do not depend on log filename, mtime, browser timezone or ingestion time for event filtering. |
| R18 | Query selected processes over a from/to interval with deterministic merged ordering or separate panes. Use [from, to) throughout API/storage; the UI visibly explains the exclusive end. |
| R19 | Provide connection/path/archive-access checks, a parser preview with errors, and a collection-plan preview with counts, estimated bytes and warnings. |

## Live monitoring and filtering

| ID | Requirement |
|---|---|
| R20 | A single selected process exposes Monitor; multiple selected processes expose Monitor selected. Both use the same collector and viewer components. |
| R21 | Show separate internal panes or one aggregated view with host and process labels; labels must remain identifiable in copied visible output. Split panes are internal UI panels. Separately, R47–R50 require two real browser windows/tabs, each with its own selected system and live sessions. |
| R22 | At the baseline rate on a responsive LAN, target a 1–2 second display delay. Record actual measured latency in tests; do not promise that latency during network failure or overload. |
| R23 | Seed monitoring with enough recent matching lines to fill the measured visible rows, not a fixed arbitrary count. Bound scanning; show why fewer lines were found and offer Load older. |
| R24 | Apply literal substring inclusion and exclusion filters while monitoring, globally and optionally per process. Support any/all inclusion, case sensitivity and clearing/changing filters without restarting SSH. The simple primary control is Contains string. Apply the same semantics to historical views. |
| R25 | Pause display without stopping collection; resume to the current retained position; stop collection explicitly. Expose counters for received, matching, rendered/visible, filtered and evicted events. |
| R26 | Reconnect with bounded backoff; handle observed rotation/truncation and partial writes; expose gaps and uncertain continuity. Distinguish connection, source accessibility, parsing and process-health concepts. Never infer a process has stopped solely from silence. |
| R27 | Bound buffers and queues, retain unfiltered captured data for changing filters/context, and allow explicit recording of live sessions into an investigation. No silent event dropping. |

## Investigation features accepted by the user

| ID | Requirement |
|---|---|
| R28 | Save investigation workspaces: process selection, time bounds, filter state, pane layout and collection references. Reopen offline against retained data; identify expired sources rather than presenting incomplete data as complete. |
| R29 | Search a selected/configured correlation identifier across processes and show a chronological trace. Show observed time deltas without claiming they prove network latency or causality. |
| R30 | Bookmark events and attach annotations without changing source logs. Preserve the source identity/name snapshot. Explicitly pin needed cached context or warn before its removal. |
| R31 | Expand before/after context in source order, even when surrounding lines fail the main filter. Label context outside time bounds and do not silently merge it into match counts. |
| R32 | Show per-source collection coverage, read/parse errors, scanned boundaries, provenance and completeness limitations. No matching events is different from no available data. |
| R33 | Export/import investigations with selected log data, notes, topology snapshot, provenance, checksums and version metadata. Support redaction with preview; exclude credentials, active connection details and SSH trust from bundles. Import never starts a connection. |

## Presentation, security and delivery

| ID | Requirement |
|---|---|
| R34 | Implement Light — Cool Slate and Dark — Graphite Dusk, following the two new images in assets/themes/. Use consistent nested subsystem/server/process cards, blue data-flow arrows and a selectable process-details/log workspace. The new references supersede the original navy/gold direction. Keep log text readable, keyboard navigation and accessible state indicators. |
| R35 | Authenticate and authorise sensitive routes and object access, protect sessions/CSRF/WebSockets, encrypt stored SSH secrets, strictly verify host keys, sanitise untrusted rendering and validate archives/configuration. Application roles never grant shell/sudo/target write access. |
| R36 | Supply offline-installable release artifacts, local assets, backup/restore and update/rollback procedures; document tested Ubuntu and Rocky environments. |
| R37 | Supply automated unit, API, SSH integration and browser tests plus a labelled synthetic demo. Record requirement-to-test traceability and measured performance. |

## Version 2 additions

| ID | Requirement |
|---|---|
| R38 | Switch light/dark themes at runtime across every page, dialog, graph, log viewer and overlay without reloading, reconnecting SSH/WebSockets, resetting filters, losing selection or changing shared topology. Persist appearance per user; support an Administrator-managed shared default and optional system-following mode. |
| R39 | Administrators manage shared topology, documentation, named view layouts, connections, credentials, host-key/target approvals, parsers, inventory/config imports and application settings. Inspectors may view/search approved topology and collect, filter, monitor and investigate its logs, but cannot change any of those shared definitions. Enforce this on the server and in the UI. |
| R40 | Administrators create/disable accounts, assign either role, reset credentials and revoke sessions. No public registration or default password. Protect the last enabled Administrator and audit security/configuration changes. Account/role changes revoke existing sessions and subscriptions before another protected response is sent. |
| R41 | Retain saved investigations, bookmarks, notes, context, bundle operations and personal viewer/appearance preferences for both roles as personal analysis state, not shared system settings. Enforce ownership of jobs, live sessions, investigations and downloads; do not accept client-supplied ownership. Shared raw-source caches must not bypass ownership. Cross-account sharing is by explicit sanitized bundle exchange, not implicit visibility. |
| R42 | Use MariaDB as the only operational database for model/configuration, users/roles/preferences, sessions, jobs, investigations, events/provenance and audit metadata. Provide validated server-side configuration for DB host, port, database, username, password file, TLS policy, timeouts and pool limits. Keep database credentials/coordinates outside project and investigation exports. |
| R43 | Include launching/configuring the free official MariaDB Docker image in the deployment process: persistent named volume, isolated network, secret files, readiness health check, separate application/migration credentials, initialization and offline save/load/start. Support an explicitly configured existing MariaDB endpoint as an alternative; never assume localhost inside an app container refers to MariaDB. |
| R44 | Implement and test MariaDB-native migrations, exact UTC microsecond/provenance storage, Unicode literal semantics independent of collation, revision/ownership constraints and bounded reconnect/fail-closed behaviour. No silent SQLite fallback. Preserve v1 project imports through an explicit previewed conversion; migrate actual SQLite data only if an existing implementation requires it. |
| R45 | Back up and restore MariaDB plus consistent log-cache/manifests, account preferences/roles, configuration and separate vault-key recovery material. Test DB outages, protected schema upgrades and rollback, persistent-volume restarts and an Internet-blocked release including all three images (app, proxy, database). |

## Version 3 additions — inventory files and parallel systems

| ID | Requirement |
|---|---|
| R46 | Store multiple named **system configurations in one application deployment and one MariaDB database**. Each has its own topology, connections, parsers, views, inventory sources and revision. Administrators create/rename/archive/restore systems; both roles can select and inspect them. The existing Project entity is the system configuration; retain `project_id` as its technical identifier. No second backend/container/database is required per system. |
| R47 | Allow the same authenticated user to open System A in one browser window and System B in another, on the same origin/profile, and inspect/monitor both concurrently. Encode the selected system in `/systems/{project_id}/...` URLs, headings and window titles. Provide an ordinary Open in new window/tab link. Never store authoritative current-system selection in a shared user record, auth session, cookie or global localStorage key. |
| R48 | Scope all model and operational lookups, source/cache identities, SSH contexts, query cursors, jobs, imports, investigations, downloads and WebSocket frames to the system. Repeated host/process names, entity IDs, addresses and event IDs in different systems are permitted and must not cause cross-system matches, cache reuse, retargeting or data leakage. Enforce composite relationships and project membership in the backend and MariaDB. |
| R49 | Give each browser-page workspace independent process selection, filters, time bounds, pane/scroll state and controllable live sessions, including two workspaces for the same system. Refresh/duplicate/reopen must not automatically adopt copied session handles or start new SSH jobs. Use server-assigned workspaces and explicit owner/project-checked reattachment. Pause, stop, close, switch or disconnect in A must not modify B; authentication logout/revocation is intentionally shared. |
| R50 | Provide bounded per-workspace, per-system, per-account and deployment-wide concurrency/retention with fair scheduling. Default ceilings must permit one user with five live processes in each of two windows (ten total). A rejected start leaves established sessions running; a slow/minimized window must not stall the other. Show scope-specific limits/usage without exposing another owner’s content. |
| R51 | Make **Import Ansible inventory files** a first-class Administrator system-setup wizard: accept ordinary static INI (including extensionless hosts files), YAML/YML, safe ZIP bundles containing selected static sources plus relative group_vars/host_vars, and `ansible-inventory --list` JSON. Ordinary supported static files must not require Ansible installation or manual JSON conversion. Document the supported subset and diagnose unsupported constructs without guessing. |
| R52 | Preview host aliases/addresses/ports/users, nested group membership, subsystem assignment and optional `inspector_processes`/PCS/log definitions. Map groups explicitly to one subsystem per host, resolve ambiguities, preserve tags and import host-only files without inventing processes. Allow manual credential/jump/parser mapping; no imported approval or secret becomes active automatically. |
| R53 | Bind inventory uploads, mappings, previews and commits to a selected system, authorizing account/version, stable inventory-source ID, hashes and expected system revision. Reimport reconciles `(project_id, inventory_source_id, inventory_hostname)` and process keys, not filenames/IP alone. Preserve manual documentation/layout/flows and unrelated processes; no implicit deletion of missing hosts. Commit atomically or leave the system unchanged. |
| R54 | Treat inventories as untrusted data: never execute Ansible, playbooks, plugins, scripts, Jinja/lookups, ProxyCommand or uploaded ansible.cfg; never fetch referenced local/remote files outside an uploaded bundle. Reject unsafe YAML/ZIP, unsupported precedence, unresolved required templates and encrypted Vault input. Omit credential values without echoing them. Complex trusted inventories can be resolved externally to canonical JSON; application runtime remains Internet-free and agentless. |
| R55 | Upgrade actual v1/v2 code incrementally without resetting stored systems, ownership, logs, notes, themes, roles, database settings or immutable IDs. Preserve existing project IDs as system IDs and retain version 2.0 single-system YAML/JSON interchange. Backfill missing scope only from verified parent relationships; fail on ambiguous/orphaned rows. Never attach every old record to an arbitrary default system. |
| R56 | Add same-browser-context two-page tests, real MariaDB composite-scope/migration tests, inventory-file/bundle and reconciliation tests, scoped backend/WS/download tests, and two-system backup/offline restart gates. Include collision fixtures and document actual results separately from specification/oracle checks. Do not claim multi-window isolation from testing two separate browser profiles alone. |

## Defaults and exclusions

Branding is configurable; English is the initial UI language. The 18 October 2026 user-authorized follow-up adds bundled Polish translations, an Administrator-managed default language in Settings, and personal English/Polish/Application default selection in Preferences for both roles. The signed-out screen and accounts following the default use the shared language. Choices persist in MariaDB and propagate across account windows without changing workspace state, UTC semantics, logs or user/imported content. The reference images do not mandate renaming to SYSTEM MONITOR. The deployment default theme starts as dark; each user may override it with light, dark or system-following mode. Administrators alone set shared defaults. Authorisation defaults and personal-workspace exceptions are specified in document 13. Time is always displayed as UTC, never silently converted to browser local time. Cached raw logs are access-controlled server files, not automatically encrypted by the application; encrypted host storage is an operational option. Stored SSH secrets are encrypted separately. Default cache retention is 14 days/10 GiB and can be changed. Bookmarks and explicitly pinned investigations need clear retention behaviour.

One jump hop is required; more hops are not. Password authentication is required; keys/MFA are not part of this release. Initial operation assumes a dedicated account can read all configured log paths without sudo; current sudo-only access is a deployment prerequisite to resolve, not a hidden implemented capability. No Pacemaker/PCS queries or service discovery are required: a PCS resource name is optional metadata only.

Not required: Windows executable, mobile UI, SSO/LDAP, per-project ACLs, real-time collaborative editing, Internet connectivity, telemetry, AI analysis, arbitrary regex filters, multi-line event assembly, streaming journals, Docker/Kubernetes discovery, automatic process-health monitoring or operations that modify target hosts.
