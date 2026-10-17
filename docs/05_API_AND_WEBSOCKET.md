# 05 — HTTP API and live protocol

Prefix all routes with `/api/v1`. Use same-origin HTTPS with server-side cookie sessions. Validation errors include field paths and a stable machine code; never expose stack traces, passwords or full connection strings. Generate OpenAPI from Pydantic and generate frontend types; do not maintain incompatible handwritten duplicates. JSON Schemas in `contracts/` define shared payload semantics.

## Route inventory and access

`Both` means an enabled authenticated Administrator or Inspector, not anonymous access. `Own` requires the resource owner to equal the current user even for an Administrator. The only cross-owner job permission is audited administrative stop/cancel plus safe operational metadata. Bind these surfaces to `contracts/rbac-policy.json`; see document 13.

| Method/path | Purpose | Access |
|---|---|---|
| `GET /ui/bootstrap` | Minimal public product/default-theme information; no inventory or auth metadata | Public, bounded |
| `GET /auth/session`, `GET /auth/csrf` | Safe account/role/preference state and session/pre-session CSRF token | Appropriate session/pre-session context |
| `POST /auth/login`, `POST /auth/logout` | Protected/rate-limited login/logout; logout ends protected sockets | Session lifecycle |
| `GET /me/preferences`, `PATCH /me/preferences` | Own appearance with revision precondition and field allowlist | Both, own |
| `POST /me/password` | Change own password; revoke sessions; special restricted forced-change flow | Both, own |
| `GET/POST /admin/users`, `PATCH /admin/users/{id}` | Account list/create/role/enabled state; last-Admin invariant | Administrator |
| `POST /admin/users/{id}/reset-password`, `/revoke-sessions` | Write-only reset/revocation; no password echo | Administrator |
| `GET/PATCH /admin/settings` | Revisioned application defaults and policy within deployment ceilings | Administrator |
| `GET /admin/database/status` | Sanitized configured endpoint/version/schema/readiness; no secrets | Administrator |
| `GET /admin/audit`, `GET /admin/operations` | Safe audit and cross-user job metadata | Administrator |
| `GET /projects` | System catalogue (Project IDs), active/archived state and own usage | Both |
| `POST /projects` | Create named system configuration | Administrator |
| `GET /projects/{project_id}` | Safe topology/documentation viewer projection | Both |
| `GET /projects/{project_id}/config`, `PUT /projects/{project_id}/topology` | Full secret-free configuration read / revisioned shared model/layout write | Administrator |
| `GET /projects/{project_id}/topology` | Full Administrator or safe Inspector diagram projection | Both |
| `POST /projects/{project_id}/topology/delete-preview` | Scoped affected entities, flows and views before deletion | Administrator |
| `POST /projects/{project_id}/topology/undo`, `/topology/redo` | Explicit saved change with current revision precondition | Administrator |
| `POST /projects/{project_id}/config/preview`, `/config/commit` | Previewed versioned config conversion/import | Administrator; own preview |
| `GET /projects/{project_id}/config/export` | Secret-free v2 YAML/JSON configuration export | Administrator |
| `POST /projects/{project_id}/search` | Model-wide search; terms in body, not URL/access logs | Both |
| `POST /projects/{project_id}/inventory/preview`, `/inventory/commit` | Safe inventory parsing, mapping and commit | Administrator; own preview |
| `POST /credentials`, `PUT/DELETE /credentials/{id}` | Write-only SSH credential management | Administrator |
| `POST /projects/{project_id}/connections/{id}/test` | Approved connection/access test | Administrator |
| `POST /projects/{project_id}/connections/{id}/host-key/inspect`, `/host-key/approve` | Fingerprint inspection and explicit trust approval | Administrator |
| `GET /projects/{project_id}/connections/{id}/source-access` | Safe configured-root/source approval status | Administrator |
| `POST /projects/{project_id}/connections/{id}/source-access/approve`, `/source-access/revoke` | Explicit configuration/route/credential/trust-bound target and root approval | Administrator |
| `POST /projects/{project_id}/connections/{id}/source-access/test` | Bounded configured path and archive-readability check; no replacement path payload | Administrator |
| `POST /projects/{project_id}/parsers/test` | Bounded sample parsing, no executable definitions | Administrator |
| `POST /projects/{project_id}/collections/plan`, `POST /projects/{project_id}/collections` | Preview/start collection against configured approved sources | Both; owner assigned server-side |
| `GET /projects/{project_id}/jobs/{id}` | Progress/coverage/errors | Both, own |
| `POST /projects/{project_id}/jobs/{id}/cancel` | Bounded cancellation | Owner or audited Administrator |
| `GET/POST /projects/{project_id}/investigations`, `GET/PUT/DELETE /projects/{project_id}/investigations/{id}` | Personal saved workspaces | Both, own |
| `POST /projects/{project_id}/investigations/{id}/query` | Historical process/time/filter query | Both, own |
| `POST /projects/{project_id}/investigations/{id}/events/{event_id}/context` | Source-order context; event must belong to permitted investigation | Both, own |
| `POST /projects/{project_id}/investigations/{id}/correlation` | Correlation search across authorized retained data | Both, own |
| `POST/PUT/DELETE /projects/{project_id}/investigations/{id}/bookmarks[/{bookmark_id}]` | Personal bookmarks/annotations | Both, own |
| `POST /projects/{project_id}/investigations/{id}/pin`, `/unpin` | Retention of own context within policy | Both, own |
| `POST /projects/{project_id}/live-sessions` | Create approved-source subscription and seed/filter policy | Both; owner assigned server-side |
| `GET /projects/{project_id}/live-sessions/{id}` | Personal session state | Both, own |
| `POST /projects/{project_id}/live-sessions/{id}/stop` | Explicit stop | Owner or audited Administrator |
| `PUT /projects/{project_id}/live-sessions/{id}/filters` | Versioned refilter without source reconnect | Both, own |
| `POST /projects/{project_id}/live-sessions/{id}/history`, `/save` | Backfill/retained data or save to own investigation | Both, own |
| `WS /projects/{project_id}/live-sessions/{id}/stream` | Authenticated, owner-checked live/replay stream | Both, own |
| `POST /projects/{project_id}/bundles/export/preview`, `/bundles/export` | Personal export with redaction preview | Both, own investigation/preview |
| `POST /projects/{project_id}/bundles/import/preview`, `/bundles/import` | Offline-only import into own new investigation | Both; own preview |
| `GET /projects/{project_id}/downloads/{opaque_id}` | Expiring, owner-checked generated artifact download | Both, own; ID alone is insufficient |
| `GET /health/live`, `GET /health/ready` | Minimal process/readiness; DB failure is 503 readiness | Public minimal or proxy-restricted |

Do not implement a route that accepts an arbitrary shell command, filesystem path, URL or SSH hostname for execution. Operational routes take approved entity IDs. Config creation/editing is Administrator-authorized and has a preview/trust/target-approval boundary. Inspector collection requests take process IDs only, never a replacement host/path/credential/parser. A denied request must have zero side effects. Use 202 plus a job/session ID for long operations, 409 for revision conflicts, 422 for invalid payloads, 413 for limits, and a structured partial result for per-source failures.

Stage 04 collection scope optionally accepts `transport: ssh|local_demo`. Omission
uses SSH in production; only the deployment opt-in enables/defaults the labelled
local demo. Plan and job `demo_mode` describes the actual transport. Source
approval writes require expected configuration and approval revisions, and
approval additionally requires `verified: true` with a bounded expiry duration.
Every remote dispatch revalidates the current source-confirmation policy,
credentials, host trust, login and configuration; retained historical queries
need no SSH approval.

Collection creation does not require a preceding `/collections/plan` request;
`POST /collections` performs the same bounded planning and authorization itself.
`DELETE /projects/{project_id}/investigations/{id}` deletes an owned, terminal
historical collection and returns `{project_id, investigation_id,
cache_cleanup_pending}`. Both roles
can delete only their own resources. Active jobs return 409; missing resources,
wrong-system references and another owner's collection return 404. Delete
requires the normal CSRF protection, invalidates retained cursors/download grants
and removes the collection's event/source records and managed captured files.
Deletion is serialized with local queries/context/download reads. If final
captured-file cleanup fails after the database commit, deletion still succeeds
with `cache_cleanup_pending: true`; the UI removes the deleted collection and
shows the cleanup warning. Deleting a retained collection never dispatches SSH
work.

The 17 October 2026 user-requested **Additional security measures** setting
controls the separate manual target/root confirmation. When enabled (the
default), the revision-bound, expiring approval above is required. When disabled,
saved path/parser changes are available for subsequent requested operations
without that confirmation. Credential bindings, credential expiry, explicit
target/jump host-key trust, configured-root validation and permissions still
apply. Saving configuration or importing data starts no connection. The
source-access response reports `manual_confirmation_required`; its
`approval.approved` indicates current eligibility under that policy, not a newly
created approval record. Disabling the policy creates no approval row or expiry;
reenabling it requires a valid approval for the current configuration. Policy
changes invalidate pending guarded remote operations.

## Revisions, queries and errors

Project update payloads include `expected_revision`; the commit atomically increments the revision. Import previews are server-held objects bound to the explicit project ID, inventory-source ID where applicable, current owner, authorization version, content/manifest hash, project revision and mapping choices, with a short expiry. A role change invalidates prior administrative previews. Commit cannot substitute different content. Use equivalent preconditions for filter and investigation updates to prevent stale tabs overwriting changes.

Historical queries use process IDs, exact canonical UTC `from` and `to`, global/per-process filters, `limit` (default 200, maximum 1000), and an opaque cursor bound to the project ID, owner, investigation ID, query hash and snapshot revision. Cursor pagination uses the deterministic sort key, not OFFSET over a mutating live table. `items`, `next_cursor`, `matched_count` when known, `coverage`, `parse_issue_count` and `source_snapshot_revision` are distinct fields. A query over an unfinished collection is explicitly partial and cannot provide a falsely final count.

Return errors as `{"error":{"code":"ACCESS_DENIED","message":"...","details":{},"request_id":"..."}}`. Required codes include AUTH_REQUIRED, CSRF_FAILED, FORBIDDEN, NOT_FOUND, DATABASE_UNAVAILABLE, SESSION_REVOKED, LAST_ADMIN_REQUIRED, REVISION_CONFLICT, HOST_KEY_UNKNOWN, HOST_KEY_CHANGED, CREDENTIALS_REJECTED, ACCESS_DENIED, SOURCE_MISSING, UNSUPPORTED_ARCHIVE, ARCHIVE_REJECTED, PARSE_FAILED, LIMIT_REACHED, CANCELLED, CURSOR_EXPIRED, SOURCE_CHANGED, RESYNC_REQUIRED, WORKSPACE_IN_USE, PROJECT_ARCHIVED, INVENTORY_UNSUPPORTED, INVENTORY_CONFLICT and PREVIEW_EXPIRED. `details` is sanitised and contains only useful field/source IDs and safe diagnostics.

## WebSocket authentication

Validate cookie session, current account state/role and session ownership, plus exact allowed Origin, route project and owning workspace/control lease during handshake. Do not enable wildcard origins. Require an initial `hello` within five seconds containing the session-bound CSRF token, protocol version, optional last sequence and current filter version. Send no log data before it validates. No passwords, session tokens or CSRF values belong in socket URLs/access logs. Recheck session expiry/auth-version/enabled state before protected dispatch and with a watchdog no slower than two seconds. Close on logout, revocation, role change or DB loss; do not wait for the ordinary 15-second heartbeat. Recheck ownership on replay/backfill and reject cross-user session IDs. Apply message-size/rate limits. This follows the threat model in [S10, S11].

## Frame contract

All frames have `protocol_version: 2`, `type`, `project_id`, `workspace_id`, `session_id`, `filter_version` and `payload`. Validate these scope fields against the authenticated socket context before processing any frame, including hello/replay. `contracts/live-frame.schema.json` defines the server envelope; payload-specific validation is also mandatory. Server frames additionally have `seq` and `sent_at` UTC. Client hello/ack frames do not invent a server sequence.

| Frame | Meaning |
|---|---|
| `hello` | Client authentication proof, resume cursor and requested protocol |
| `snapshot` | New retained/seed result set, coverage, source states and reset reason |
| `events` | Bounded event batch; includes canonical event records and late-arrival flags |
| `status` | Source connection/read/parse status, scan progress or seed exhaustion |
| `filter_applied` | New filter version and refilter status; followed by replacement snapshot |
| `gap` | Known loss or uncertain continuity with source IDs, reason and observed bounds |
| `resync_required` | Replay unavailable; client must replace its view, not append unknown duplicates |
| `counters` | Received/matched/filtered/evicted/retained counters and scope semantics |
| `heartbeat` | Transport health, not process health; initial cadence 15 seconds |
| `ack` | Client's last applied sequence; optional viewport row request update |
| `error`, `stopped` | Sanitised error or terminal session state |

A replacement snapshot identifies its sequence boundary. A browser discards queued frames from older filter versions and only appends newer compatible frames. A reset and subsequent batch cannot double-add the same event ID. Filter changes are sent via the CSRF-protected HTTP route; WebSocket control messages are deliberately narrow.

## State machines

Collection: queued → planning → collecting → indexing → completed, partial, failed or cancelled. Cancel requested is a real intermediate condition, with bounded stopping latency. Any nonterminal job interrupted by a backend restart becomes interrupted/partial and needs explicit resume/recollect.

Live source: starting → seeding → following ↔ reconnecting; access/trust failures → blocked; observed loss → following with gap state; stop → stopped. Session state aggregates sources without hiding one source's failure. Display pause is client presentation state, not a source transition.

Record precise transitions in tests. Do not treat HTTP 200 with a text error string as a successful collection, or a functioning WebSocket as proof that source collection is working.

## Settings, projections and account responses

`/auth/session` returns only the current user's safe ID/name/role, preference revision/resolved mode and permitted action identifiers; no password hash, encrypted credentials or session verifier. An Inspector-visible project projection includes IDs, display names, documentation, geometry, data flows and approved display source/status information. It excludes connection usernames, credential references, jump routing, trust/approval material, database configuration and administrative policy. The full `project.schema.json` is an Administrator interchange contract, not an Inspector response model. Generate explicit separate Pydantic read/write models and schema tests; do not serialize ORM objects wholesale.

Appearance PATCH input contains `expected_revision` and `theme_mode` only. Global defaults are changed through Administrator settings, not `/me/preferences`. Account role values are exactly `administrator` and `inspector`; account mutation inputs have explicit allowed fields and reject extra keys. Record user/settings/account writes and enforce revision/invariant constraints in MariaDB transactions. All owner fields in responses are server-derived; reject owner fields in create/update requests rather than trusting them.

Administrator settings responses include the global boolean
`additional_security_measures`. The revisioned, CSRF-protected settings PATCH
accepts a strict boolean for that field; omission preserves the saved value.
It is Administrator-only policy for every system, not a personal preference,
project-import field or public bootstrap value. Record changes in the settings
audit; stale revisions return 409.

## Appearance payloads

`GET /me/preferences` follows `contracts/user-preference.schema.json` and returns `revision` plus `theme_mode`. `PATCH /me/preferences` follows `contracts/user-preference-update.schema.json`, accepts only `expected_revision` plus `theme_mode`, and returns the updated response object. Unknown fields are rejected, not ignored; a stale precondition produces 409. The account ID comes only from the authenticated session. Global default changes use the separate Administrator settings route.


## Version 3 system catalogue, workspace and import additions

All routes below retain the `/api/v1` prefix. The browser routes `/systems/{project_id}` are presentation paths; their technical scope is the same immutable `project_id`.

| Method/path | Contract |
|---|---|
| `PATCH /projects/{project_id}/metadata` | Administrator rename/description with expected revision |
| `POST /projects/{project_id}/archive`, `/restore` | Administrator lifecycle; guarded stop/drain for this project's active jobs only |
| `POST /projects/{project_id}/workspaces` | Both roles, server-derived owner and new workspace ID; no remote collection |
| `GET /projects/{project_id}/workspaces/{workspace_id}` | Owner-only workspace state |
| `POST /projects/{project_id}/workspaces/{workspace_id}/detach` | Best-effort detach, never account logout or blanket monitor cancellation |
| `POST /projects/{project_id}/live-sessions/{id}/attach` | Explicit owner/project-checked transfer to a new workspace; expected lease revision; 409 on occupied controller |
| `GET /projects/{project_id}/usage` | Own per-workspace/project/account limits and counts; no another owner's log/filter data |
| `GET/POST /projects/{project_id}/inventory/sources` | Administrator persistent source list/creation; file basename is not identity |
| `POST /projects/{project_id}/inventory/uploads` | Administrator multipart staging of direct file or bounded ZIP; server-created opaque upload ID, no arbitrary server path |
| `POST /projects/{project_id}/inventory/preview` | `inventory-import.schema.json`; validate selected files, source, mapping, hashes and expected revision |
| `POST /projects/{project_id}/inventory/commit` | Own server-held preview ID + expected revision only; no replacement upload/mapping accepted |
| `POST /projects/{project_id}/inventory/uploads/{id}/cancel` | Owner-only staged-data deletion; commit/cancel/expiry delete raw staged uploads |
| `GET/POST/DELETE /projects/{project_id}/credential-bindings[/{id}]` | Administrator explicit binding of a global vault reference to this project; never returns secret values |

A System selector is not an authorization check. Resolve every nested object in its route project and verify its permitted parent and owner. Repeated body project IDs must match the route (422); an object/preview from a different project or owner is not found (404). Live controls include workspace context and verify the current control lease, not only the user ID. Authoritative owner/project/lease values are read on the server. Explicit audited Administrator stop remains the narrowly defined exception.

`live-request.schema.json` adds required `workspace_id`; existing `project_id` must match the route. All lifecycle/query responses for project-owned resources identify `project_id`; workspace/live responses also include their workspace/session/lease revision. HTTP historical query shape is unchanged because the route and investigation provide scope. Per-process filter keys and requested process IDs must belong to that same project and selection.

Do not leave unscoped `/collections`, `/jobs`, `/investigations`, `/live-sessions`, `/connections`, `/parsers`, `/bundles` or `/downloads` compatibility endpoints that select a project from a session/default. Version upgrades must update callers/generated clients and reject unsupported protocol versions safely. Global `/credentials`, account/settings and registry routes stay global by design, but using a credential for SSH additionally requires a project binding.

WebSocket server envelope example is `contracts/live-frame.example.json`. Each event must have the same `project_id` as the envelope; validate the payload through the existing event schema and authoritative session selection. Envelope shape validation alone does not enforce that relational rule. The client checks project, workspace, session, filter version and sequence before appending any frame; stale old-project frames must never appear after navigation. See document 16 for detach/resume and no-automatic-collection semantics.
