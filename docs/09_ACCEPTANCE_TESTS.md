# 09 — Application acceptance tests

**These are future application acceptance targets, not tests already passed by this package.** Package integrity/oracle tests are separately reported in VERIFICATION.md. Use synthetic data and an isolated local SSH/SFTP environment. Never run against actual monitored hosts without explicit approval.

Performance numbers below are engineering targets on a recorded reference environment, not measured results or unconditional guarantees. Use steady low-rate streams matching the brief, retain raw timing data and distinguish parsing/rendering time from network transfer.

## AT01 — Package and contract baseline
**Requirements:** R37.

**Exercise:** Parse all contract/example JSON, validate schema shapes and semantic references, read every fixture source, verify source-byte hashes and reproduce the fixed golden query IDs.

**Pass condition:** The specification is internally consistent; no production implementation is claimed.

## AT02 — Authenticated foundation
**Requirements:** R01,R04,R35.

**Exercise:** Bootstrap the first Administrator without a default password, create an Inspector, sign in as each, restart backend and reopen a saved project.

**Pass condition:** Authenticated API/UI work; unauthenticated operational routes reveal no inventory/logs; no shipped default password.

## AT03 — Local interface assets
**Requirements:** R02,R34.

**Exercise:** Build the frontend, serve it with external browser requests blocked and inspect network activity.

**Pass condition:** All icons, styles, scripts and fonts used by the application load locally; no analytics or external image calls.

## AT04 — Real API shell
**Requirements:** R03,R37.

**Exercise:** Persist a project as Administrator and a personal preference as either role, then refresh and inspect actual MariaDB-backed state.

**Pass condition:** Changes survive refresh/restart and are not only demo state in browser memory.

## AT05 — Ownership and reparenting
**Requirements:** R05,R06.

**Exercise:** Create subsystems/servers/processes; attempt invalid cross-parent drag and explicit valid move.

**Pass condition:** One server belongs to one subsystem, one process to one server; explicit moves update model and views coherently.

## AT06 — Cross-subsystem flows
**Requirements:** R07.

**Exercise:** Connect two processes in different groups, label the transfer, save/reload and collapse a parent.

**Pass condition:** Original directed relationship persists; any collapsed proxy does not create a new semantic edge.

## AT07 — Click-through documentation
**Requirements:** R08.

**Exercise:** Select an element and edit its Markdown description, then open its other diagram view.

**Pass condition:** Element-details panel opens on selection; documentation is shared; HTML/unsafe URLs do not execute.

## AT08 — Whole-project search
**Requirements:** R09.

**Exercise:** Search name, PCS resource metadata, tags and documentation for a process hidden in another collapsed view.

**Pass condition:** Correct result is revealed, centred and highlighted; the search is not limited to the current canvas.

## AT09 — Multiple views and editing controls
**Requirements:** R10.

**Exercise:** Pan/zoom, resize, collapse, create another view, undo/redo model edits, save and reload.

**Pass condition:** IDs remain stable and geometry is view-specific; later log updates do not rerender the entire graph.

## AT10 — Config round trip
**Requirements:** R11.

**Exercise:** Export YAML/JSON, edit a description and position externally, preview and commit.

**Pass condition:** Equivalent models round-trip without credential material or accidental ID replacement.

## AT11 — Stale/invalid config
**Requirements:** R11,R35.

**Exercise:** Submit duplicate IDs, missing parents, unknown parser, future schema version, unsafe path and stale revision.

**Pass condition:** Validation/409 errors are precise and no partial mutation occurs.

## AT12 — Rename/delete impact
**Requirements:** R05,R28,R30.

**Exercise:** Rename a bookmarked process; attempt deleting a server with flows/active sessions.

**Pass condition:** Snapshots/notes remain attributable; destructive impacts require explicit handling.

## AT13 — Exact UTC interval
**Requirements:** R17,R18.

**Exercise:** Query records exactly at from and to, fractions, equal times and a browser in non-UTC timezone.

**Pass condition:** From is included, to excluded, UTC unchanged and deterministic ordering preserved.

## AT14 — Timestamp failures
**Requirements:** R16,R17.

**Exercise:** Ingest invalid, timezone-nonzero, unsupported-precision and configured fixed-width timestamps.

**Pass condition:** Valid configured formats parse; malformed values stay visible as diagnostics without invented event times.

## AT15 — Literal filters
**Requirements:** R24.

**Exercise:** Run every golden include/any/all/exclude/case-sensitive/Unicode/metacharacter case.

**Pass condition:** Production query returns exactly the supplied event IDs; no regex/SQL wildcard/shell interpretation.

## AT16 — Process/time/filter composition
**Requirements:** R18,R24.

**Exercise:** Combine selected processes, global terms and per-process terms.

**Pass condition:** Predicates are ANDed correctly; generated host/process prefixes never match raw-line terms.

## AT17 — Source provenance and duplicates
**Requirements:** R16,R32.

**Exercise:** Ingest the two identical retry lines, Unicode lines and CRLF sample.

**Pass condition:** Different offsets yield different events; byte offsets/checksums are exact; unknown absolute line numbers remain null.

## AT18 — Historical formats
**Requirements:** R15,R16.

**Exercise:** Collect plain rotations, ZIP and TAR.GZ fixtures, including misdated archive name.

**Pass condition:** Matching members are found and correct times/provenance used; filename dates do not override content.

## AT19 — Out-of-order records and coverage
**Requirements:** R18,R32.

**Exercise:** Query an unsorted source and a failed/skipped source with first/last times bracketing the interval.

**Pass condition:** Later physical matches are retained; coverage does not imply continuous completeness from min/max alone.

## AT20 — Archive safety
**Requirements:** R16,R35.

**Exercise:** Process traversal ZIP, symlink TAR.GZ, corrupt ZIP and generated limit-exceeding archives.

**Pass condition:** No outside writes/extraction; safe rejection/partial status; no unbounded memory or silent truncation.

## AT21 — Cancellable bounded ingestion
**Requirements:** R16,R27.

**Exercise:** Cancel during download/decode/index and exceed configured budgets.

**Pass condition:** Tasks stop within bounded chunk/deadline rules, temporary files are removed and committed coverage is marked partial.

## AT22 — Stable pagination
**Requirements:** R18.

**Exercise:** Page a historical snapshot while another capture adds events and try reusing a cursor with another filter.

**Pass condition:** No duplicate/skipped rows in the frozen result; incompatible cursor is rejected/resynchronised.

## AT23 — Historical performance
**Requirements:** R03,R37.

**Exercise:** Use tools/generate_load_fixture.py to create 20 MiB across five sources on a recorded reference machine.

**Pass condition:** Target cached ingestion ≤10 s and warmed query p95 ≤500 ms on a documented 4-vCPU/SSD reference; report actual values, excluding network download time.

## AT24 — Direct password SSH
**Requirements:** R13.

**Exercise:** Use a real isolated SSH/SFTP test endpoint with good and bad username/password values.

**Pass condition:** Good reads succeed; bad auth is diagnosed; no secret reaches logs/browser/exports.

## AT25 — Single jump hop and trust
**Requirements:** R13,R35.

**Exercise:** Use separately keyed jump and target endpoints; test unknown/changed keys independently and denied forwarding.

**Pass condition:** Both keys are verified; approvals are explicit; no trust-all workaround.

## AT26 — Read-only boundary
**Requirements:** R14.

**Exercise:** Instrument test server for SFTP writes and exec channels; attempt unsupported generic command/path API requests.

**Pass condition:** Only approved read operations occur; no sudo, terminal, write, discovery or command execution capability is exposed.

## AT27 — Permissions and path testing
**Requirements:** R14,R15,R19.

**Exercise:** Deny a directory/archive permission; test traversal and symlink escape from approved roots.

**Pass condition:** Specific access diagnostics and blocked escapes; application never escalates privileges.

## AT28 — Snapshot changes during collection
**Requirements:** R16,R32.

**Exercise:** Append, truncate or replace an active source while taking a historical snapshot.

**Pass condition:** Capture boundary and uncertainty/retry outcomes are honest; later appends do not corrupt the snapshot identity.

## AT29 — Pool lifecycle
**Requirements:** R13,R27.

**Exercise:** Open two process captures on one host, change credential version, then close subscriptions.

**Pass condition:** Appropriate connection reuse, invalidation and closure; no pooling across incompatible credential/trust contexts.

## AT30 — Five-process live monitoring
**Requirements:** R20,R21,R22.

**Exercise:** Follow five real test SFTP sources in split and merged views at 1–5 complete lines/s total.

**Pass condition:** Correct labels; healthy p95 append-to-display delay target ≤2 s on recorded LAN-equivalent conditions.

## AT31 — Measured matching seed
**Requirements:** R23.

**Exercise:** Open the same filtered monitor with 12-row and 36-row panes and sparse matches.

**Pass condition:** Initial history fills the respective matching rows where available; no fixed 100-line assumption or unlimited scan.

## AT32 — Seed/live boundary race
**Requirements:** R23,R26.

**Exercise:** Append and split a line across the pinned seeding size while backfill runs.

**Pass condition:** Exactly one event for every provable source byte range; pending partial line completed once.

## AT33 — Live refilter without reconnect
**Requirements:** R24,R27.

**Exercise:** Collect matching/nonmatching text; change/clear global and per-process filters.

**Pass condition:** Retained hidden events return; SSH stays connected; obsolete filter-version frames are ignored.

## AT34 — Pause versus stop
**Requirements:** R25.

**Exercise:** Pause display, append events, resume, then explicitly stop.

**Pass condition:** Acquisition continues while paused, counters advance, stop closes/releases the correct collector.

## AT35 — Partial UTF-8 and rotation
**Requirements:** R26.

**Exercise:** Run partial-write, rename-rotation and copytruncate scenarios through actual transport tests.

**Pass condition:** No premature line; old/new generations visible; gap/uncertainty reported where continuity cannot be proved.

## AT36 — Disconnect and retry
**Requirements:** R26.

**Exercise:** Interrupt transport, append/rotate, reconnect; also change host key during outage.

**Pass condition:** Bounded backoff and coverage warnings; changed key blocks retry until corrected.

## AT37 — Idle and late streams
**Requirements:** R18,R22,R26.

**Exercise:** Keep four sources idle; publish equal-time, out-of-order and very late lines on another.

**Pass condition:** No idle watermark stall; deterministic ties and visible late arrivals with stable scroll anchoring.

## AT38 — Retention and slow clients
**Requirements:** R27.

**Exercise:** Reach both raw byte/event limits and stall one WebSocket subscriber.

**Pass condition:** Bounded queues/memory and explicit eviction/reset boundary; other collection remains responsive.

## AT39 — Socket resume/filter versions
**Requirements:** R25,R26.

**Exercise:** Disconnect browser inside/outside replay retention and reconnect with old seq/filter version.

**Pass condition:** Compatible replay or explicit snapshot/resync; never silently merge incompatible epochs.

## AT40 — Live recording
**Requirements:** R27,R28.

**Exercise:** Record a session, save it and reopen after all monitored hosts are disconnected.

**Pass condition:** Persisted investigation works with coverage and original source labels; transient sessions are not misrepresented as durable.

## AT41 — Backend lifecycle
**Requirements:** R26,R36.

**Exercise:** Restart backend with a collection/live session active and leave a tab disconnected beyond its lease.

**Pass condition:** Jobs show interrupted state; no silent remote auto-resume or indefinitely orphaned collector.

## AT42 — HTTP session/CSRF security
**Requirements:** R35.

**Exercise:** Test expired/revoked cookies, wrong origin, missing/wrong CSRF and rate-limited logins.

**Pass condition:** Sensitive operations fail closed without information leakage.

## AT43 — Untrusted text rendering
**Requirements:** R08,R34,R35.

**Exercise:** Use markup/unsafe-link strings in logs, descriptions, names and notes.

**Pass condition:** All logs render as text; safe Markdown cannot load remote assets or execute code.

## AT44 — Decompression/resource limits
**Requirements:** R16,R35.

**Exercise:** Generate archive headers with misleading sizes, many members and high expansion, plus oversized lines.

**Pass condition:** Actual-byte/time/count limits are enforced; no negative match claim is made from a truncated preview.

## AT45 — Parser/config input safety
**Requirements:** R35.

**Exercise:** Submit unsafe YAML tags/recursive aliases, duplicate keys and executable parser expressions.

**Pass condition:** Bounded rejection; no code/object/Jinja evaluation.

## AT46 — Secret and target lifecycle
**Requirements:** R13,R35.

**Exercise:** Import profiles with unresolved credentials and inspect API/export/audit traces; rotate vault key/credential.

**Pass condition:** No secrets/ciphertext in project/bundles; approvals required; rotation/recovery tested with correct access control.

## AT47 — WebSocket security
**Requirements:** R35.

**Exercise:** Try missing session, foreign Origin, wrong hello-CSRF, oversized frames and logout midstream.

**Pass condition:** No data before authentication, limits enforced, sessions revoked promptly.

## AT48 — Saved workspace
**Requirements:** R28.

**Exercise:** Save process/time/filter/pane state; reopen after restart and after unpinned source expiry.

**Pass condition:** State restored; missing retained data is clearly unavailable rather than a misleading empty match set.

## AT49 — Correlation identity
**Requirements:** R29.

**Exercise:** Trace exact request_id REQ-0042 and compare with substring REQ-0042 in golden fixtures.

**Pass condition:** Exact field search excludes REQ-00420; trace timestamps/deltas are observable facts, not inferred network latency.

## AT50 — Notes and context pinning
**Requirements:** R30,R31.

**Exercise:** Bookmark a transient event, annotate it, save surrounding unmatched/out-of-range context and expire other cache.

**Pass condition:** Original bytes unchanged, context identified separately and preserved or explicitly declared unavailable.

## AT51 — Dependency selection
**Requirements:** R12.

**Exercise:** Highlight upstream/downstream neighbours and add them to historical/live selection.

**Pass condition:** Configured directions respected; no assumption that highlighted flow actually occurred.

## AT52 — Coverage detail
**Requirements:** R32.

**Exercise:** Display unavailable host, parser errors, unknown candidate dates, partial active source and proven source bytes.

**Pass condition:** Distinct accessible states with counts/provenance; no false all-green completeness.

## AT53 — Redacted bundle export
**Requirements:** R33,R35.

**Exercise:** Export raw/context/notes/topology with an explicit synthetic value-redaction rule and inspect every member.

**Pass condition:** Redaction applies consistently; credentials/trust/active connections absent; checksums regenerated; source cache unchanged.

## AT54 — Safe offline bundle import
**Requirements:** R33.

**Exercise:** Import a valid bundle, modified checksum, unsafe member and future version; watch network attempts.

**Pass condition:** Valid offline investigation opens; invalid bundle rolls back; zero automatic SSH or external requests.

## AT55 — Ansible input formats
**Requirements:** R11.

**Exercise:** Import supplied canonical JSON, static YAML and host-only INI using the mapping.

**Pass condition:** Same three host/subsystem mappings; optional process extension is explicit; INI does not invent processes.

## AT56 — Idempotent inventory reconciliation
**Requirements:** R11.

**Exercise:** Reimport unchanged inventory, then change one address and remove one host.

**Pass condition:** No duplicate identities; layout/docs/processes preserved; absence does not auto-delete.

## AT57 — Inventory subgroup conflicts
**Requirements:** R06,R11.

**Exercise:** Map overlapping groups to two subsystems and supply ambiguous inherited vars.

**Pass condition:** Operator resolves membership or supplies canonical JSON; importer does not guess full Ansible precedence.

## AT58 — Inventory execution/secret rejection
**Requirements:** R11,R35.

**Exercise:** Upload plugin/script/Jinja/ProxyCommand fields and synthetic password-named fields.

**Pass condition:** Nothing executes; secrets omitted without echo; any suggested jump is explicitly configured.

## AT59 — Parser/config preview
**Requirements:** R19.

**Exercise:** Test ISO/fixed-width samples, invalid lines, archive selectors and actual access failure.

**Pass condition:** Preview shows extracted UTC/metadata/errors and actionable safe source diagnostics.

## AT60 — Desktop accessibility/layout
**Requirements:** R34.

**Exercise:** Inspect both themes and roles at 1280×720, 1920×1080, 200% zoom and keyboard-only paths for search, filters and panes.

**Pass condition:** Usable controls, visible focus, labelled states, readable logs, no giant decorative background or colour-only status.

## AT61 — Integrated UI/resource baseline
**Requirements:** R03,R34,R37.

**Exercise:** Navigate a 60-process model while five low-rate monitors run for 30 minutes and change filters/views.

**Pass condition:** No runaway memory/tasks; target backend RSS <1 GiB on this baseline; separately record app, MariaDB, proxy and browser memory/CPU, with headroom within the 16 GB server design budget. Report actual metrics, not a combined SQLite-era assumption.

## AT62 — Ubuntu/Rocky deployment
**Requirements:** R01,R36.

**Exercise:** Load/start the app, proxy and MariaDB images on documented Ubuntu LTS and Rocky Linux 9 with respective runtime recipes.

**Pass condition:** Both are actually exercised, non-root application and correct SELinux/permissions; untested environments explicitly listed.

## AT63 — Offline cold start
**Requirements:** R02,R36.

**Exercise:** Block Internet on server/client, cold-start without registry/npm/pip access and use UI, cached investigation and permitted LAN SSH.

**Pass condition:** All functions required for this scenario work; no hidden Internet dependency.

## AT64 — Backup and restore
**Requirements:** R28,R35,R36.

**Exercise:** Quiesce collection/cache cleanup and writes, make a consistent MariaDB backup with matching cache/manifests, and restore with separately protected vault key to an isolated test instance.

**Pass condition:** Saved investigations and intended secrets work; data-only restore explains missing key; no keys in ordinary bundles.

## AT65 — Upgrade and rollback
**Requirements:** R36.

**Exercise:** Upgrade a persisted test installation with migration then restore pre-upgrade artifact/DB snapshot.

**Pass condition:** No inconsistent old-image/new-schema rollback; interrupted work and compatibility state are visible.

## AT66 — Final release evidence
**Requirements:** R37.

**Exercise:** Run complete suites and verify release image hashes, notices, SBOM, offline scripts and traceability.

**Pass condition:** Every requirement has actual implementation/test evidence or an explicit release blocker; no fictitious completion claims.

## Version 2 acceptance targets

Run role/ownership tests against production authorization code, MariaDB tests against real MariaDB, and visual tests against the implemented browser UI. The supplied policy/theme oracles and deployment-template checks do not satisfy these runtime targets.

## AT67 — Both visual themes
**Requirements:** R34,R38.

**Exercise:** Render the same synthetic topology, selection, inspector and logs in both supplied theme directions.

**Pass condition:** Both references are recognisable without using screenshots as control backgrounds; semantic tokens style every component and original reference assets remain unchanged.

## AT68 — Switch theme during live work
**Requirements:** R38,R24.

**Exercise:** While five fixture processes stream, enter filters and unsaved permitted edits, switch themes repeatedly and follow system appearance changes.

**Pass condition:** No page reload, SSH/WebSocket reconnect, selection loss, form reset or duplicated/missed event occurs solely because appearance changes.

## AT69 — Appearance ownership and defaults
**Requirements:** R38,R39,R41.

**Exercise:** Use two accounts with default/light/dark/system preferences; change shared default as Administrator and attempt it as Inspector, including mass-assignment fields.

**Pass condition:** Personal preference persists per account and device session; default followers respond to shared changes; Inspector cannot change default/role/owner through preference payloads; stale revisions return 409.

## AT70 — Contrast and keyboard paths in both modes
**Requirements:** R34,R38.

**Exercise:** Measure actual rendered contrast and keyboard focus for graph controls, log highlights, tooltips, dialogs, disabled controls and errors in both modes.

**Pass condition:** Ordinary text meets 4.5:1 and relevant controls/focus indicators meet 3:1 under the specified WCAG criteria; no colour-only status, unreadable overlays or missing focus. Token arithmetic alone is not UI evidence.

## AT71 — Server-enforced permission matrix
**Requirements:** R04,R39,R35.

**Exercise:** Exercise every implemented HTTP command against contracts/rbac-policy.json with both roles, including direct crafted requests not exposed by UI.

**Pass condition:** Administrator can edit shared definitions; Inspector can only perform approved read/analysis operations; unknown actions default to deny and denied writes make no persistent or remote changes.

## AT72 — Account lifecycle and last Administrator
**Requirements:** R40.

**Exercise:** Create/disable accounts, change roles and reset credentials; race two requests to remove the remaining enabled Administrator accounts.

**Pass condition:** No public registration/default password; default created role is Inspector; the database transaction guard prevents zero enabled Administrators even under concurrency; account IDs/history remain stable.

## AT73 — Object ownership across protocols
**Requirements:** R35,R39,R41.

**Exercise:** Guess another account's investigation/job/live/download IDs over HTTP, WebSocket subscribe/resume/filter and generated download tickets; repeat as Administrator.

**Pass condition:** Non-owner content remains unavailable even to Administrator by default; shared cache does not bypass this; ownership is server-assigned; only the documented audited administrative stop/cancel exception succeeds.

## AT74 — Revocation while streaming
**Requirements:** R40,R35.

**Exercise:** Disable an account, change its role/password or revoke sessions while HTTP downloads, queued tasks and a silent live connection exist.

**Pass condition:** Sessions/auth_version are rechecked before protected dispatch; downloads and jobs stop at bounded chunk boundaries; live authorization watchdog closes/revokes within 2 seconds. Reconnecting cannot restore revoked access.

## AT75 — Safe Inspector projection
**Requirements:** R39,R35.

**Exercise:** Read all Inspector routes, errors, bootstrap fields and browser network responses; probe full config, trust, credential and database-status endpoints.

**Pass condition:** Only approved viewer metadata/log access diagnostics are returned; no credentials, connection internals, privileged configuration or cross-owner private payloads leak. Admin-only endpoints deny Inspector regardless of UI visibility.

## AT76 — Inspector investigation workflow
**Requirements:** R28,R29,R30,R31,R32,R33,R41.

**Exercise:** As Inspector collect/query/monitor approved processes, save a workspace, correlate, annotate, expand context and exchange a sanitized bundle.

**Pass condition:** All accepted personal investigation tools work without permission to alter topology, parsers, credentials or global settings; imported bundles create owned offline artifacts and never activate targets.

## AT77 — Audit trail without secrets
**Requirements:** R40,R35.

**Exercise:** Change roles/settings/topology, approve a key, reset credentials and cancel another owner's session; inspect structured audit and error records.

**Pass condition:** Audit identifies actor, action, time, outcome and safe affected IDs with redacted summaries; no passwords, cookies, private keys, log bodies or credential ciphertext appears. Audit read is Administrator-only.

## AT78 — Role-aware controls and honest state
**Requirements:** R34,R39,R26.

**Exercise:** Open identical projects as both roles, keyboard-trigger editing controls and inspect idle/unreachable log sources.

**Pass condition:** Inspector retains navigation/selection/search/live controls but not shared edits. Unknown health is not rendered as RUNNING merely because the reference image is green or an SSH/log read succeeded.

## AT79 — MariaDB-native persistence correctness
**Requirements:** R42,R44.

**Exercise:** Run migrations and production repositories against real pinned MariaDB, ingest all golden sources and boundary/long Unicode/nullable ordering cases, restart the app.

**Pass condition:** Exact integer UTC/provenance and event ordering survive round trip; literal casefold/metacharacter results match fixtures independently of database collation. No SQLite test substitute or fallback is used.

## AT80 — Database configuration, files and TLS
**Requirements:** R42,R35.

**Exercise:** Validate managed/external endpoints, missing secret files, wrong certificates/hostnames, invalid ports and secret values containing URL-reserved characters.

**Pass condition:** Password-file loading and structured connection construction are safe; external TLS verifies identity; invalid config fails before network use; no password/DSN appears in browser, logs or exports.

## AT81 — Docker database provisioning and restart
**Requirements:** R43.

**Exercise:** Using disposable fresh storage, load the pinned official image, apply supplied configuration/init hook, await health, run migrations, insert data and recreate containers.

**Pass condition:** Persistent volume retains records; health gates startup; runtime/migrator grants match policy; MariaDB has no host-published port; an existing volume is never silently reinitialized or password-rotated.

## AT82 — Existing MariaDB endpoint
**Requirements:** R42,R43.

**Exercise:** Deploy an isolated pre-provisioned MariaDB endpoint using a hostname other than the Compose service name and verified TLS.

**Pass condition:** App reaches configured host/port/schema with correct least-privilege credentials; no managed DB is unnecessarily launched and localhost is not hard-coded. Include a tested external-endpoint recipe.

## AT83 — Database outage and single-worker ownership
**Requirements:** R44,R45,R35.

**Exercise:** Disconnect MariaDB during active operations and attempt a second app instance or migration while the first owns the supervisor lock.

**Pass condition:** Readiness returns 503; protected dispatch fails closed; no in-memory auth bypass, duplicate collectors or silent supervisor-lock reacquisition after disconnect; operators see interrupted work and explicitly restart collection after recovery.

## AT84 — Separate database privileges
**Requirements:** R43,R35.

**Exercise:** Connect with runtime account and attempt DDL/GRANT/out-of-schema access; inspect serving-container mounts and migration credentials.

**Pass condition:** Runtime has only required DML and cannot administer database/accounts; app lacks root/migration secrets; one-shot migrator performs schema work only while serving app is stopped and migration lock held.

## AT85 — MariaDB and cache disaster recovery
**Requirements:** R45,R28.

**Exercise:** Quiesce jobs/cleanup, back up database/cache/manifests/config and separate vault key; restore to isolated installation with two accounts and different themes.

**Pass condition:** Roles/preferences, owned investigations, notes, source checksums and approved secret recovery are consistent; missing key is explicit; unrelated account content remains unavailable after restore.

## AT86 — Version 1 compatibility and conditional data migration
**Requirements:** R44.

**Exercise:** Preview/import supplied v1 project; if actual legacy SQLite application data exists, run documented dry-run and typed migration on a copy.

**Pass condition:** Project IDs, content and geometry are preserved; obsolete theme becomes an explained presentation change. No actual legacy DB is invented; existing-data migration verifies owners/counts/checksums and has tested rollback before any production cutover.

## AT87 — Three-image offline cold release
**Requirements:** R02,R43,R45.

**Exercise:** Transfer app, proxy and database image archives to an Internet-blocked disposable host; restore local certificates/secrets and start from zero local images.

**Pass condition:** Hash-verified image load works with pull_policy never, no registry/package/CDN/ACME request; database readiness/migrations and both theme/login/approved LAN log workflows operate.

## AT88 — Complete visual regression matrix
**Requirements:** R34,R38,R39.

**Exercise:** Capture both roles in both themes at target sizes: topology, details, historical/merged live, filters, settings/users where allowed, login, empty/loading/error/revoked states.

**Pass condition:** All required state combinations are usable and consistent; no stray old navy/gold panels, hidden controls revealed by theme change or mocked green health defaults; screenshots come from implemented UI.

## AT89 — Transactional shared settings and topology
**Requirements:** R39,R44.

**Exercise:** Race Administrator edits from stale revisions while an Inspector submits the same mutation; exercise project import and global default changes.

**Pass condition:** Only valid authorized transactions commit; stale writes return 409 with no partial update; Inspector requests change nothing and ownership/authorization decisions cannot be raced by changing accounts mid-operation.

## AT90 — Global and per-account resource budgets
**Requirements:** R03,R41,R44.

**Exercise:** Run five-process baseline and additional accounts up to configured global caps, then exceed per-user and global collection/live limits.

**Pass condition:** Budgets are enforced centrally without cross-account content disclosure; cancellation releases capacity; measurements include app, MariaDB, proxy and browser separately and fit the stated 16 GB host design budget.



## AT91 — Two independent named system configurations
**Requirements:** R46,R48.

Create Systems A and B through the Administrator UI, using duplicate local host/process IDs and names. Edit their descriptions/layouts separately, restart the backend, and verify both configurations and independent revisions persist in the same MariaDB database. No second serving app/database container is created.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT92 — Two windows using the same account and browser context
**Requirements:** R47,R49,R56.

Open two Playwright pages in one BrowserContext on the same origin/account; A selects System Alpha and B selects System Beta. Start approved local-test live logs in both. Changing system selection/search in A leaves B’s route, selected processes, live session and rendered log source unchanged. Also perform a manual two-OS-window check.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT93 — System-scoped search with colliding entity names
**Requirements:** R09,R48.

Search an identical host/process name in both systems. Each page returns only records from its own project and opens that project’s view/ancestors. A phrase unique to B produces zero matches in A; the UI never treats a globally matching name as the same entity.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT94 — Forged cross-project API and download references
**Requirements:** R35,R48,R56.

Under one user entitled to view both systems, submit an A route with B job/investigation/source/event/download IDs, and combine A/B process selections. Repeat with a second owner and both roles. Resolve objects by scoped parents, return sanitized 404/422 as specified, and assert zero reads/writes/connections/download bytes outside the selected project.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT95 — Scoped event identities caches and query cursors
**Requirements:** R18,R31,R32,R48.

Use equal event/source/process IDs, paths, timestamps and request IDs in both projects. Verify composite identity, correct source-byte/context/bookmark lookup, project-partitioned cache/index keys and separate query results. Replay a cursor from B in A and reject it; neither checksum equality nor an old local ID grants access.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT96 — Independent filters for both different and identical systems
**Requirements:** R24,R49.

Two same-account pages monitor different systems, then two pages monitor the same process in one system. Apply/clear include/exclude/case filters in A while B has a different filter. B’s filter revision/result set/connection stay unchanged; A refilters retained events without reconnecting SSH.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT97 — Pause stop close and background-page isolation
**Requirements:** R25,R26,R49.

Pause display, explicitly stop a monitor, detach/close a page and throttle/minimize a page in separate scenarios. The other page keeps collecting and rendering its selected sources. Shared raw collectors keep valid refcounts, background visibility is not a stop signal, slow queues resync visibly, and lease expiry releases only detached subscriptions.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT98 — Refresh duplicate deep link and explicit resume
**Requirements:** R47,R49.

Refresh a page, duplicate it with copied storage and open a deep link. Each document receives a fresh workspace and starts no SSH through GET/bootstrap. Only explicit owner/project-checked Resume attaches a detached session; an occupied controller gives 409 and cannot be stolen. Old frames from a prior workspace/project are rejected before rendering.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT99 — Shared authentication and appearance exceptions
**Requirements:** R38,R40,R49.

Changing the personal theme may propagate to both pages without resetting selection/filters/live IDs. Logout, disablement or role revocation intentionally closes both affected authenticated windows under existing deadlines. Closing one page or changing its system does not invoke logout or account-wide cancellation.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT100 — Two times five live sources and bounded fairness
**Requirements:** R03,R22,R27,R50,R56.

On a documented 16 GB local-test environment, run five low-rate processes in each of two same-user windows/systems; reserve ten subscriptions. Measure healthy p95 line-to-render latency against the 2-second target. Test one slow page plus a bounded archive job, per-workspace/project/account/global limits and rejection of an eleventh source without evicting established monitors. Report actual memory/CPU/rates and unavailable tests.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT101 — System archive and restore affect only their target
**Requirements:** R46,R48.

Attempt to archive A while it has active jobs: reject or require explicit audited confirmation to stop/drain A only. B continues unchanged. Cached A history remains readable, new A collection is blocked, and restore never restarts SSH automatically. Race a new start against archive and verify no untracked live task survives.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT102 — Direct INI and extensionless inventory files
**Requirements:** R11,R51,R52.

Upload inventory.hosts.ini and extensionless hosts directly through the setup wizard without Ansible on the server. Parse groups, child groups, ordinary quoted scalar variables and aliases. Preview exactly three supplied hosts with their expected addresses/users and zero processes; commit only after target-system mapping/approval workflow.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT103 — Direct YAML inventory with nested groups and processes
**Requirements:** R51,R52.

Upload the supplied YAML directly, resolve supported all/parent/child/host variables and preview three hosts/five explicit process records with PCS/log metadata. Top-level/nested groups are represented without inventing system boundaries. Required-field errors identify file/field safely and prevent unresolved commit.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT104 — Inventory ZIP with relative host and group variables
**Requirements:** R51,R54.

Upload inventory-with-vars.zip, select hosts.ini and consume only its uploaded relative group_vars/host_vars companions. Verify the expected three hosts/five processes, file provenance, explicit selected-source order and omitted-file summary. A missing companion produces a warning/absence, never a server-filesystem fallback. Test multiple explicitly selected safe sources.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT105 — Canonical inventory JSON remains a safe compatibility path
**Requirements:** R51,R54.

Import supplied canonical JSON and a trusted externally resolved complex example with expanded _meta.hostvars. The application invokes no Ansible binary/plugins/network resolution. Its help uses normal --list, not --export. Canonical data is still validated, secret-scrubbed and approval-gated; it cannot trigger code execution.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT106 — Unsupported static constructs never guessed or executed
**Requirements:** R51,R54.

Submit dynamic plugin/script/playbook data, uploaded ansible.cfg, ranges, unsupported INI structures, group-priority/precedence ambiguity, required templates/lookups and Vault contents. Produce precise safe unsupported/conflict diagnostics and offer the documented trusted canonical workflow. Never evaluate/execute input or silently substitute a different host/user.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT107 — Explicit subsystem mapping and honest import counts
**Requirements:** R52.

Place one host in OS/location and two subsystem candidate groups. Keep cross-cutting tags, flag conflicting/unassigned membership and require one same-project subsystem. Show added/unchanged/changed/omitted/absent counts. Import a legitimate host-only inventory successfully with zero processes and no fabricated data-transfer arrows.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT108 — Per-system idempotent inventory reimport
**Requirements:** R48,R53.

Import the same aliases/file into A and B under each project’s source identity. Reimport A under the same source with a renamed filename: no duplicate hosts/processes, and B’s IDs/revision/source map remain unchanged. A different source with the same filename/address is not silently merged by filename/IP.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT109 — Inventory changes preserve manually maintained documentation
**Requirements:** R53.

Change an inventory host address and optional process path, while the application has manual descriptions, layouts, flows and unrelated processes. Preview the exact differences/conflicts and preserve unaffected/manual fields by default. Missing source hosts are marked absent, not deleted. Accepted source edits do not retarget existing live sessions.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT110 — Tamper stale or cross-system previews cannot commit
**Requirements:** R35,R53.

Attempt commit with another project/owner/source preview, changed files/mapping hashes, stale project/auth revisions or expiry. Reject each with no partial model/source-map mutation. Inject a mid-transaction failure and verify full rollback of data/revision. A commit in B alone must not stale A’s valid preview.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT111 — Imported secrets jump hints and targets stay unapproved
**Requirements:** R13,R35,R52,R54.

Provide password/key/become/token values, jump command strings and permissive roots. Never echo or export secrets or execute hints. Require explicit same-project credential binding, jump/parser mapping, target/root approval and host-key trust before collection. Approval of an equal address in B does not enable A. Delete restricted raw uploads on commit/cancel/expiry.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT112 — Bounded malicious inventory files and archives
**Requirements:** R35,R54.

Exercise duplicate YAML/JSON keys, tags/aliases/recursive input, excessive depth/nodes/bytes, encrypted ZIP, traversal, links, duplicate-normalized members and nested archives. Enforce actual expanded-byte/file/time limits and cancellation. Inspect logs and responses for secret sentinels and assert no writes outside staging/no remote or external-file access.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT113 — Process extension is explicit and system-local
**Requirements:** R15,R52.

Verify inspector_processes uses literal validated records with stable local IDs, distinct configured names and optional PCS metadata. Missing parser references can be mapped only within the target system; unsupported structured INI strings do not create fake processes. Reimport retains process IDs; process absence does not erase manually configured sources.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT114 — Roles enforced on every system setup surface
**Requirements:** R39,R41,R46,R51.

Under Inspector, attempt system create/edit/archive/restore and inventory source/upload/preview/map/commit/config APIs, including forged requests: all denied without side effects. Both roles can select/read approved systems and own investigations. Administrator uses the full wizard but still cannot read another user’s private content. No new per-system ACL restriction is implied.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT115 — MariaDB enforces project-paired relationships
**Requirements:** R42,R44,R48.

Use real MariaDB migrations/repositories. Insert/update a server/subsystem/connection, process/server/parser, flow endpoint, source/process, event/source and investigation-source/event association with mismatched project keys; composite foreign keys reject each. Duplicate local IDs across two valid projects are accepted. Tests cannot be satisfied by SQLite or service mocks.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT116 — Upgrade existing projects without arbitrary scope backfill
**Requirements:** R44,R55,R56.

Dry-run against synthetic single-project and multi-project v2 copies with events/notes/caches/import mappings; preserve their IDs, owners, raw hashes, preferences and rows. Ambiguous/orphaned parent relationships fail preflight. Do not create competing System/Project identity tables or assign all rows to one default. Test interrupted migration and matching backup rollback.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT117 — Legacy configuration import selects one explicit system
**Requirements:** R11,R44,R55.

Import v1 through its documented conversion and existing schema-2.0 project files into a selected existing/new system. Preserve internal identities and explicitly map a new outer project ID on create-as-new; no overwrite of another project by file ID. Keep DB/accounts/themes outside imports. Existing 2.0 server configs remain readable and custom caps are not reset silently.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT118 — Investigation bundle exchange preserves system provenance
**Requirements:** R33,R41,R48.

Export an owned A investigation with A-only selected topology/source labels, redaction and provenance. Import as a new private offline investigation under a selected context, retaining original project as provenance but creating no enabled topology/credentials or B associations. IDs/paths from B cannot be substituted in A export/download requests.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT119 — Both themes show unambiguous active system context
**Requirements:** R34,R38,R47.

Inspect light and dark UI at required sizes with A and B open concurrently. Window title, selector, inspector, log panes and import confirmations identify their current system. Same-origin storage/theme updates never change another page’s system/filter/scroll. Keyboard/new-window links and no false health badges remain correct.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.


## AT120 — Two-system offline release backup and cold restart
**Requirements:** R02,R36,R45,R46,R56.

With the final authorized app/proxy/MariaDB images, block Internet and test first-page load, native inventory imports, two named systems and local-test parallel streams. Back up all system/cache/mapping/owner state, restore to disposable volumes and reopen both saved investigations with hosts offline. Auth is revoked, old sessions are interrupted and no target SSH restarts automatically. Report actual OS/runtime checks; specification oracles do not count as release evidence.

**Evidence required:** implemented automated test(s), command/results and relevant API/DB/browser artifact; not a package-oracle result.
