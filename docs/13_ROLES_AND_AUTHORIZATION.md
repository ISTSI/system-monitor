# 13 — Administrator and Inspector roles

## Scope and explicit defaults

Version 2 replaces the one-operator account assumption with individually authenticated local accounts. There are exactly two application roles: **Administrator** (`administrator`) and **Inspector** (`inspector`). A small number of accounts may be active together; there is one backend worker and shared global resource budgets. No SSO/LDAP, per-project ACL engine, custom roles or collaborative-editing protocol is required.

All authenticated accounts may view the approved shared system model and investigate its configured logs. Only Administrators alter that model and the application's shared settings. Neither role grants remote shell, sudo, service control, target file writes, database root access or access to the container daemon. Authorisation is deny-by-default and checked on each backend action, including object-level access [S21].

The existing accepted features remain available to Inspectors: saved investigations, bookmarks, annotations, context, correlation searches, redacted bundle exchange and live capture. These are **personal investigation data**, not changes to the documented/monitored system. Inspector is read-only with respect to shared configuration and all target hosts, not a prohibition on saving a personal note or initiating a read-only log retrieval. This interpretation preserves the previously approved functionality.

## Permission matrix

| Operation | Administrator | Inspector |
|---|---|---|
| View/search shared topology, docs, approved source/access status | Yes | Yes |
| Select processes, inspect time ranges, filter/monitor, copy permitted results | Yes | Yes |
| Create/save personal investigations, notes/bookmarks/context, captures | Own resources | Own resources |
| Export personal investigation bundles / import offline bundles | Own resources | Own resources |
| Change own appearance, panel layout, password | Yes | Yes |
| Edit shared topology/docs/flows/log paths/parsers/named views | Yes | No |
| Import/export active project configuration; import Ansible | Yes | No |
| Manage SSH profiles, credentials, allowed roots, host-key trust | Yes | No |
| Approve/revoke current system target and log roots; test configured source access | Yes | No |
| Test/edit a connection or parser configuration | Yes | No; normal collection reports its own access errors |
| Change shared settings, global default theme, retention/limits | Yes, within deployment ceilings | No |
| Create/disable users, assign roles, reset credentials, revoke sessions | Yes | No |
| View audit and aggregate operational job metadata | Yes | No |
| Read another user's private notes/captured investigation via web API | No implicit access | No |
| Stop another user's job/live session for operational reasons | Yes, audited | No |
| Change database bootstrap endpoint or keys from browser | No; server deployment action | No |
| Modify target hosts, run commands, mount Docker socket | No | No |

The user-requested **Additional security measures** option is an
Administrator-only global shared setting, not an Inspector preference or a
per-window active-system value. Its default is enabled. Enabled requires the
existing manual source target/root confirmation for the current revision;
disabled allows saved path/parser changes to be used without that extra
confirmation. Inspectors retain normal collection access under the effective
policy and never gain configuration, approval, credential or host-key write
permissions. SSH host-key approval and valid project-bound credentials remain
required in both modes. Turning the option on again requires a valid current
source approval; turning it off does not manufacture one.

`contracts/rbac-policy.json` defines stable action identifiers and ownership modes. It is not a production authorization implementation. Bind every API/service operation to one action. A route missing a permission declaration must fail tests rather than inherit permissive access.

## Account lifecycle

Bootstrap the first Administrator using a server-side interactive CLI after DB migrations. No shipped login/password, self-registration or public first-run privilege assignment. The first-account operation is transactional and refuses if an enabled Administrator already exists, unless an explicit protected recovery workflow is being used.

Administrators create local accounts with a unique normalized username, display name, role, initial password and optional forced password change. Default role for a newly created account is Inspector; the role is explicitly displayed before submission. Use Argon2 password hashes. Password inputs are write-only, rate-limited and never reflected in validation responses or audit data. Forced-change sessions can only access the restricted password-change/logout flow until completed.

Provide enable/disable, role change, temporary password reset and explicit session revoke. Deactivation preserves ownership/history; no hard account deletion in this release. Never disable, demote or otherwise remove the last enabled Administrator. Serialize last-admin checks with a locked security-configuration row plus the account changes in one DB transaction, including concurrent requests. An Administrator may demote their own account only when another enabled Administrator remains; their sessions then end. Do not permit role self-assignment through preference/profile updates.

Each security change increments `auth_version`. Session records capture that version. Revoke sessions and cancel the affected user's live sessions/jobs on disablement, role change, password reset/change or explicit global revoke; preserve partial results with coverage flags. Every protected dispatch checks current enabled/version/role state, and open streams cease emitting within two seconds of the committed change, without waiting for the ordinary 15-second heartbeat. Clear client caches of protected data on logout/expiry. A browser can still retain previously viewed data; do not claim revocation erases exports or screenshots.

## Object ownership and resource isolation

Assign owner IDs on the server from the authenticated session; clients may not set or change them. Jobs, live sessions, investigations, bundle previews and download grants are user-owned. Bookmarks/context/pins inherit their investigation owner. A source cache can deduplicate immutable bytes, but access always requires a permitted parent resource; knowledge of a source/event ID or cache checksum is not authorization.

Return 404 for another user's private resource and 403 for a known but role-forbidden shared action. Administrative operational lists expose IDs, owners, timestamps, state and safe counts only—not another user's query strings, log text or notes. Stop/cancel is a separate permission, not broad read access.

Do not pool a live-session/filter object across different users. A physical SSH pool may be internal, but subscriptions, replay buffers, per-user limits and authorization must remain separated; simplest initial choice is one collector context per user/source. Global concurrency and buffer ceilings still apply to the sum of all accounts.

The account holding the Administrator role is a technical administrator, not an isolated tenant. The service/host administrator can ultimately access storage; private UI ownership is an application rule, not a claim of cryptographic separation from the system operator. Cross-account exchange uses an explicit sanitized bundle download/upload; imported bundles become owned by the importer and never overwrite shared topology.

## API and browser rules

Require a backend dependency/service permission check for every HTTP and WebSocket operation. Validate owner access at creation, query, refilter, backfill, live replay, save, stop, download generation and download delivery. A user's role in a JWT/local-storage field or an Inspector-hidden button is not authoritative. Use opaque server-side sessions as in document 07.

`GET /projects/{id}` returns a safe viewer projection to both roles. Full project configuration is Administrator-only via `/projects/{id}/config` and export; the viewer response must not accidentally include usernames, credential IDs, jump-host routing, trust stores, approval flags or operational ceilings. Approved display addresses and log paths may be shown as documentation. Logs themselves can contain sensitive data; roles do not automatically redact source contents.

Personal `/me/preferences` is an explicit allowlist (`theme_mode` plus `expected_revision` in update requests; `revision` in responses). It cannot accept `role`, `owner_user_id`, database settings, policy limits or a shared default theme. Admin settings have their own API and revision/validation/audit boundary. Bootstrap DB location and vault-key files remain server-managed, with a safe Administrator-only read-only diagnostics summary and restart instructions; do not build a dangerous live DB-switch control.

Inspectors have no shared drag/reparent/edit/connection handles, while selection, pan/zoom, collapse/expand, search and log actions remain available. Do not disable the whole diagram. Hide/admin-label routes and controls for clarity, then test forged HTTP/WS requests because visual restrictions are not a security boundary.

## Audit and acceptance

Audit account/role/session operations, authorization denials, settings/config/trust/credential changes, collection start/stop and bundle exports. Include actor ID, role snapshot, target IDs, UTC time and outcome; exclude passwords, hashes, tokens, credential ciphertext, raw log lines and filter values. The operational audit is not advertised as tamper-proof.

Test both roles, anonymous clients, two Inspector accounts, an Administrator account, disabled accounts, concurrent last-admin changes, stale sessions after demotion, every ID-bearing nested route, forged owner IDs and theme/settings mass assignment. Apply those tests to HTTP, socket replay and authenticated downloads, not just navigation menus.


## Version 3 systems and workspaces

Roles stay global to the application: every enabled Administrator or Inspector can select all configured systems, subject to existing approved-source and private ownership rules. This is multi-configuration support, **not tenant isolation or per-system ACLs**. Administrator-only actions now also include system create/rename/archive/restore, inventory-source/upload management and project credential binding. Both roles can create their own page workspaces and monitor different systems concurrently. System choice is not stored in the login session.

Add project checks in addition to role/owner checks on every operation. A permitted user cannot use a preview/live/event/source/download from B under an A route or associate it with A data. Read `contracts/scope-policy.json`; the role matrix alone is insufficient. Live controls additionally enforce the owning workspace's current controller lease, with explicit resume after detachment. This protects another window's monitor even for the same account. Global logout, account revocation and account theme preference are the deliberate cross-window exceptions.

Global vault management remains Administrator-only; use in a system requires an explicit same-system binding and approvals. Administrative aggregate operation listings retain sanitized metadata only. System archival can cancel that system's jobs with confirmation/audit, never all jobs in other systems. The import wizard is denied to Inspectors at upload, preview, mapping, commit and raw-staging access, not just the final write.
