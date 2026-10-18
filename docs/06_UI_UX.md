# 06 — Interface and interaction design

## Visual direction: two equivalent themes

The current references are `assets/themes/light-cool-slate.png` (**Light — Cool Slate**) and `assets/themes/dark-graphite-dusk.png` (**Dark — Graphite Dusk**). The original `assets/style-reference.png` is retained only as a legacy attachment. Do not blend the old navy/gold treatment into these themes.

The light concept uses cool off-white/slate surfaces, navy text, thin blue-gray group boundaries, medium-blue arrows and clear blue selection. The dark concept uses charcoal/graphite surfaces, subtly elevated blue-gray headers, light text and brighter blue connections. Both share nested rectangular subsystem/server cards, compact process rows, recognisable subsystem/server/process icons and a prominent process-details/log panel. Keep layout and information hierarchy the same when switching modes.

Implement one set of components using `assets/themes/tokens.json` and its CSS translation. Resolve the user's preference to `light` or `dark`, set the root `data-theme` and React Flow `colorMode` consistently [S20]. Apply tokens to menus, popovers rendered through portals, scrollbars where supported, dialogs, controls, tooltips, minimap, node/edge states, tables, log highlights and error/empty states. Do not simply invert a screenshot or remount the workspace with a new React key.

Use local system sans-serif and monospace stacks; do not fetch external fonts or copy workstation font files. Normal text should meet a 4.5:1 contrast target; large text and essential UI graphics/focus targets require their applicable 3:1 checks [S22]. Actual browser rendering, transparency and overlays must be inspected; token tests alone do not establish accessibility. Indicators always include text or an icon with an accessible name, not colour alone. Keep transitions short and honour reduced-motion preferences.

Branding remains configurable, initially System Inspector, and initial UI language remains English. The SYSTEM MONITOR heading and example addresses do not mandate branding or data; the separately authorized English/Polish language controls are described below. IP/Port fields appear only when corresponding service endpoint metadata exists; never substitute the SSH port for an application port or invent addresses. The reference's RUNNING/OPERATIONAL values are illustrative. With no process-health probe in scope, show documented/unknown health separately from observed log-access states (Not checked, Reading, Disconnected, Permission denied). A live SSH session or recent log event does not prove an entire subsystem is operational.

## Theme preferences and Administrator settings

The 18 October 2026 language follow-up adds English and Polish using bundled
translation catalogues. **Settings → Application default language** is
Administrator-only and initially English. **User menu → Preferences → Language**
is personal for both roles: English, Polski or Application default. The signed-out
screen and accounts following the default use the saved shared language. Explicit
personal choices remain unchanged when the default changes. Language and theme
persist independently, propagate across account windows, update document language
and accessibility labels, and preserve workspaces, selections, drafts, filters and
investigation controls. Logs, Markdown, names, identifiers, UTC values and uploaded
content remain original data. Preference conflicts show a retry action.

Provide an Appearance control in **Preferences**, accessible to both roles by clicking the logged-in user and choosing Preferences: Light, Dark, System, and Application default. Personal theme selection is available only in Preferences. Keep **Settings** Administrator-only, containing shared application settings without personal appearance controls. The application default starts as Dark — Graphite Dusk and is editable in Settings. It applies to new accounts, the signed-out screen and accounts using Application default. `default` follows that global default; `system` follows `prefers-color-scheme`; the other values are explicit. Account preferences are stored in MariaDB and survive login/restart. Login uses a safe public branding/theme bootstrap response without exposing inventory.

Changing theme updates CSS and control state without navigation, refresh, loss of selection, new SSH connection, changed live filter version or WebSocket reconnect. Preserve scroll anchors, unsaved Administrator forms, selections, bookmarks, time bounds and display pause. Avoid a wrong-theme flash before preference resolution. System-preference changes are observed only while the user has selected System. Changes to the global default do not overwrite explicit per-user choices.

Theme preference writes are personal preferences, not permission to edit system settings. Reject arbitrary fields on `/me/preferences`; a forged role, default theme, connection or cache limit is not silently accepted. A failed preference save gives a clear retry state without breaking log collection.

The Administrator-only shared application settings include **Additional security
measures**, checked by default and persisted globally. When checked, require the
existing manual target/log-root confirmation after configuration changes,
including path and parser changes. When unchecked, saving valid changes makes
them available automatically for the next requested operation. Explain that
explicit SSH host-key verification and valid credentials remain required.
Hide the per-source confirmation checkbox/actions while manual confirmation is
disabled, and show that the saved setting controls it. Reenabling requires a
current valid source approval. Saving the setting does not start collection or
change another page's system, filters or selection.

## Workspace

Administrator subsystem frames expose a **+** button that opens Add server with
that subsystem selected. Server frames expose **+** for Add process with that
server selected. These actions also work on collapsed frames, use accessible
names identifying the parent and keep expand/collapse as a separate control.
Saving a child expands its ancestors in the current view. Inspectors do not see
these configuration actions.

A new process proposes `app.log` under the first proposed log root of its
server's connection profile. Changing the server updates this suggestion until
the path is edited. A typed path or an existing process path is preserved. With
no configured root, the required path starts empty.

Login includes an unchecked **Remember me** checkbox, labelled with its 30-day
duration. Selecting it persists the authenticated cookie and session for a
maximum of 30 days, including inactivity and browser restarts. Ordinary logins
retain the configured idle and absolute limits. Logout and account revocation
still apply across windows; no workspace or system selection is remembered by
this option.

Top bar: configurable product branding, Systems, Accounts (Administrator only), Settings (Administrator only), Admin (Administrator only), the Synthetic demo data label when enabled, and the current user/account menu. Admin follows Settings and opens a dedicated `/admin` view for system creation, metadata editing, archival and restoration. Both roles find Preferences in the user menu for personal appearance; shared application settings and account management remain Administrator-only. Closing Preferences returns keyboard focus to the user menu trigger. Do not show an Administrator workspace status strip.

Below the top bar, use a compact system header: System action menu and system name on the left, system selector on the right. The floating Administrator menu contains Add subsystem, Add server, Add process, Add flow, List connections, List Parsers, Import configuration, Export JSON and Export YAML. Put Undo and Redo in the Documented topology bar alongside the existing view controls; remove the separate topology editing button bar. Read-only views remain explicitly labelled and omit shared editing actions.

Left resizable pane: searchable subsystem/server/process tree and investigation list. Centre: interactive diagram or the selected full-width investigation view. Dockable process-details panel: documentation, safe properties, current log access status and related flows. Default to below the selected subsystem/left diagram region as in the concepts when space allows, with a resizable lower log area; also allow docking at the right. Configuration editing is Administrator-only. Bottom resizable workspace: log panes/merged view, timeline controls, filters, capture status and notes. Every panel can be collapsed; the log workspace can maximise within the browser.

Support desktop sizes from 1280×720 through 1920×1080 and larger. At the smallest size, collapse side panels instead of shrinking all log columns beyond usability. At 200% zoom, primary actions and selected log text remain reachable. Native OS windows are not required.

## Topology editing

Only Administrators may persist topology edits, drag shared nodes, create edges or save named layouts. Inspectors retain pan/zoom, multi-select, search, dependency highlight, group expand/collapse and personal panel sizes, without shared writes. Disable React Flow mutation handlers as well as UI edit controls, and enforce the same restrictions server-side.

Subsystems are outer labelled groups; servers are nested groups with a header; processes are compact custom nodes. Use group geometry and valid parent relationships, not just visually overlapping rectangles. A process drag remains within its parent by default. Explicit Move to server opens a target picker and confirms the change. Moving a server between subsystems is likewise explicit.

Selecting one process opens documentation immediately and exposes Inspect history and Monitor. Multi-select opens Inspect selected and Monitor selected. Clicking a flow displays its metadata. Connection handles create valid directed relationships. Renaming does not sever flow, bookmark or log associations.

Provide save state, undo/redo and delete impact preview. Multiple views reference the same entities. Collapsing a group hides child graphics but preserves the underlying flows; a group-level connection proxy may show a count, never create a new model edge. Search results reveal the real process and its ancestors. Keep diagram nodes independent from high-frequency log rendering so new lines do not rerender the entire graph.

## Historical investigation

Select processes → open **Filters** from the Timestamped events table → choose
explicit UTC from/to and optional literal filters → apply → collect → inspect
automatically loaded events. Preview candidate sources/budget is optional;
display the collection-plan panel only after an explicit preview request.
Direct collection performs the same bounded planning and approval checks on the
backend. Persist a named workspace when requested. Explain end-exclusive bounds
near the time control, not only in documentation. Invalid times and from ≥ to
cannot be applied as query or collection bounds.

**Filters** opens a separate modal with a local draft. **Existing filters**
lists each global/per-process include or exclude term and an individual
**Remove filter** action, including repeated terms. **Log content**, Include or
Exclude, and **Filter scope** form a new literal term through **Add filter**.
Keep terms as arrays; newline characters within a term never become a second
filter. Each scope supports any/all inclusion, case sensitivity and shared
Unicode-casefold behavior, with at most 20 include and 20 exclude terms of 512
Unicode characters each. **Clear content filters** preserves time bounds;
**Reset time range** uses the retained collection bounds. **Apply filters**
submits a retained query when a collection is open and closes only on success.
Cancel discards the draft. Query errors keep the draft open and leave the prior
applied bounds/predicate intact. Filters remain independent across pages.

From and To fields display `YYYY-MM-DD HH:mm:ss`. Each has a calendar button
opening date and time selectors, including seconds, with an explicit UTC label.
Typing and selecting use UTC regardless of the browser timezone. Cancelling the
nested date/time picker leaves the dialog's bound unchanged; cancelling Filters
discards the entire draft. Committing Filters invalidates an existing collection
plan. Existing retained bounds keep exact API microseconds until edited.

Show match count, scanned sources, parse issues and coverage beside the results. A failed host stays visible in the process selection/status panel; successful sources are not discarded. Show each event's original source through a details drawer. Context, bookmark, annotate, copy literal text, trace correlation and add dependency neighbours are row/context actions.

Click a row, or press Space/Enter on its focused row, to mark or unmark it for
saving. Keep selected state visible and accessible in merged and separate panes,
including across result pages, process visibility changes and refiltering in the
same collection. The context eye and copying selected text do not toggle a mark.
**Clear selection** removes the unsaved marks; changing collections clears them.
The **Pin** button opens selected original log text and one shared editable
description. Save 1–100 distinct entries as one pin group in the personal
investigation workspace. Retain each entry's event identity and name snapshot;
use the exact query bounds/predicate from when it was marked to label its saved
context. A failed save retains the marks and description; an acknowledged save
clears the saved selection.
Each **Pins** entry is one row with its description and **View** button. View
opens a popup with one terminal-style text block per process, an editable
description, **Save**, **Cancel**, **Modify** and **Delete pin**. Modify returns
to the event table with the saved entries selected. Pressing Pin then asks
**Update the pin or create a new one?**; an update preserves the pin identity
and atomically replaces its selection. Keep one investigation tools panel
mounted while collections load or change; pin operations never create another
personal workspace panel. Grouped entries retain single-anchor text/provenance after
source-cache expiry; ordinary source-context bookmarks still offer surrounding
lines separately. Group descriptions/membership are part of the sanitized,
previewed offline bundle and remain editable on a private imported copy.

Load Timestamped events automatically after collection finishes and when opening
a retained collection. The **Log entry** column omits only the successfully parsed
original timestamp prefix; diagnostics retain their complete visible text.
Context shows the original line, including its timestamp. Literal filters still
operate on the retained original text. Both roles can delete their own finished
collections after confirming the system and collection identity; remove retained
events, captured files and download grants. Active collections must finish or be
cancelled first. Other collections and page workspaces remain independent.

The collection setup has visible **Collection time range** UTC inputs before
collection starts. The event table's **Filters** dialog controls a separate
display time range over retained data. Applying display filters does not change
the acquisition inputs, invalidate a prepared next-collection plan or contact
SSH. Show the current collection's original UTC interval and collected process
list, even while the next-collection form has different choices. Filter process
options come from that collection, including processes with zero events.

All displayed timestamp metadata uses `YYYY-MM-DD HH:mm:ss` in UTC, including
historical/live rows, applied intervals, correlation traces, parser-normalized
times, observed coverage and preview/approval expiry. Exact API timestamps,
stored microseconds and the original source text remain unchanged; original
timestamp evidence and downloadable documents retain their source format.

Historical results use compact, unwrapped monospace rows with minimal padding
and horizontal scrolling. A text-height eye before each timestamp opens source
context; it remains available when timestamp metadata is hidden. **Columns**
toggles UTC time, process and host independently, with **Show all columns** to
restore them; log content stays visible. The same choices apply to split panes
in that page. **Full screen** in the top-right maximizes results within the
browser; **Exit full screen** or Escape restores the inline viewer. Preserve
rows, filters and scroll when changing presentation. Native modal focus stays
inside the maximized viewer; opening context and closing it returns to the row.
Column/full-screen choices belong to the page and never update another window
or trigger collection/refiltering.

**Rows** sits in the right corner below the data table/panes with the result
paging controls; its measured-size option is **Viewport**. Changing it
immediately reloads page one of the applied query with the selected limit,
preserving unapplied filter, time and process
edits. Viewport uses an individual log scroll viewport and bounded
prefetch. Pagination retains the applied page size. Separate panes include every
process in the applied query, with distinct process/host headings and independent
bounded result pages. A process absent from the merged page still has a pane;
an empty pane reports no matches or unavailable data explicitly. Immediately to
the right of **Result layout**, **Show process** is a checkbox dropdown in both
layouts. It offers all queried processes as `server name: process name`, with
immutable process IDs available on hover, and permits any subset or none. The
same labels apply to configured-process and filter-scope lists. Its options
remain the full applied-query process set so hidden processes can always be
enabled again. Merged results
query the enabled subset using the applied predicates, reset pagination and
show that subset's actual match count. Unsubmitted edits remain unapplied.
With no enabled processes show a clear empty state and disable result paging;
do not send an empty process scope to the backend. In split view, checkboxes
hide/show mounted panes while retaining their pages and scroll. **Pane
arrangement** is always visible: disabled in Merged, enabled in Separate process
panes, retaining the Stacked/2/3/4-column choice across layout changes. Changing
arrangement makes no query. Loading split pages uses bounded concurrent cached
queries; a failed pane retains its rows and offers its own retry. Merged paging
remains separate. These controls are local to each browser page, including
same-system duplicated pages. Log tables scroll horizontally within their panes.
The **Show process** and **Columns** pickers stay open for checkbox changes and close on outside
click, keyboard focus leaving, or Escape. Escape first closes the picker and
restores its trigger focus, keeping a full-screen results dialog open.

The trace view is a time-ordered table with process, timestamp, correlation field, message and observed delta. It is not a fabricated animation claiming an unobserved transfer occurred. Dependency highlighting on the diagram can accompany a trace without presenting it as proof.

## Live viewer

Use one viewer implementation in split or merged mode. Merged rows display UTC time, process and host in columns; process references and copied visible text use `server: process`. Keep that generated prefix out of raw substring matching. Split panes share global controls but allow a per-process literal filter and show an active filter badge. Use the same process label in selection, accessible filter names, source status, detached monitors and pane headings; immutable IDs remain internal identities.

Live events share the historical table's compact 20-pixel rows, monospace text,
minimal cell padding and separate UTC time, process, host and log-entry columns.
Both layouts use the same column geometry, sticky headings, hover treatment and
horizontal scrolling. Preserve the live follow/scroll anchor and display-pause
behavior; measure seed rows using the actual heading and viewport heights.
Unknown timestamps remain in their diagnostic lane. A distinct late-arrival
label precedes the displayed message so the compact timestamp column cannot
hide it. Copied rows retain system and `server: process` labels and original text.

Opening Live monitor or selecting checkboxes starts no capture. Starting requires
an explicit Monitor action (including Monitor this process from topology) or
explicit Resume. Switching workspace sections keeps an existing monitor running;
Stop this monitor ends it. Once it ends, label its selection as a previous monitor
rather than claiming it is still monitoring. Preserve backend error codes in
stream-error notices. A `TRANSPORT_DISCONNECTED` gap identifies the affected
`server: process` when supplied and explains interrupted source reading and
potentially missing entries. It is not proof of a network failure or process
health; missing files and other retryable SFTP failures can produce this reason.

The primary filter is a single Contains string field with a clear button and a case-sensitive toggle. An Advanced drawer exposes multiple include/exclude terms and any/all inclusion. Filter edits debounce briefly, apply on the backend and show applying/applied state. Make literal behaviour discoverable; do not label the field Regex. Clearing the filter restores retained unmatched events.

The viewer measures its body/row height to request initial matching rows. Default is no line wrapping with horizontal scrolling, so row calculation is deterministic; wrapping is optional. During seed scanning display scanning coverage, not a blank “live” panel. Fewer lines than the window can hold is a valid result when sources are exhausted or a scan cap is reached.

Controls distinguish Pause display, Resume, Stop collection, Record and Load older. Pausing does not hide the accumulating/evicted count. Jump to latest never silently clears a filter. A late-arrival marker and gap row are not ordinary source log messages. Unknown timestamps appear in an explicit diagnostic lane, not incorrectly sorted among valid events.

## Shared configuration/import/test tools (Administrator only)

Connection editor: label, target/port/user, existing credential reference or secure write-only password update, jump profile, host-key fingerprint/trust and Test access. Never return a stored password to a prefilled field. Clearing a password field without an explicit replacement action must not erase the credential.

**Copy** in the connection list or saved connection editor opens **Add connection** with the saved name, endpoint, username, credential reference, jump profile and log roots prefilled. Generate a new editable stable ID and prompt for a unique name before saving through the normal revision-checked create flow. Opening or cancelling the draft changes no shared configuration. The copied credential reference can reuse its existing stored password; host-key and source approvals are not copied.

Parser test: paste a bounded anonymised sample or upload a small file; show original line, extracted time, normalised UTC, level/correlation extraction and per-line errors. Process configuration shows one active path and its rotations/archive selectors.

Inventory import: format selection, parsing warnings, group→subsystem mapping, host/connection diff, explicit confirmation, unresolved secret references and target-trust requirements. Do not silently overwrite documentation, view positions or configured processes.

## Personal investigation bundles (both roles)

Bundle export offers selection, data size/coverage, redaction rules/preview and explicit final confirmation for the current user's own investigation. Both roles may import a sanitized bundle into a new owned offline investigation. Bundle operations are not Administrator-only configuration imports and never change shared topology or activate connections.

## Required visual acceptance

Capture implemented pages in **both light and dark themes** at 1920×1080 and 1280×720, for both Administrator and Inspector roles where actions differ: topology with two subsystems, a clicked process inspector, merged logs, five split panes, filter drawer, an import diff and a coverage/error state. Test keyboard-only selection/search/actions and screen-reader labels for primary controls. Screenshots are acceptance evidence only after the corresponding backend actions work. Do not mark a static UI mock as a completed vertical slice.

Add visual regressions for open menus/dialogs/portals, selected processes, unknown/disconnected states, text selections, match highlights and focus rings in each theme. Capture the same two-subsystem sample layout as the references, but label all synthetic health data as demo-only. Check switching while five filtered streams are active and while an Administrator form has unsaved changes.


## Version 3 system selector, import and parallel-window behaviour

Add a system catalogue/selector without changing the supplied light/dark palettes. Keep the system name visible, use `/systems/{project_id}/...` deep links and title `System Inspector — <system> — <section>`. Ordinary system links support the browser's new-window/new-tab actions; users open separate pages manually without a dedicated Open separately button. The supplied images remain style references, not evidence of system selection or automatic health features.

Each page owns selected processes, time/filter/search inputs, panes/scroll and monitor controls. Switching a system in one page changes only that page and requires confirmation about its own active capture. A page for A must never draw a tooltip, search result, banner or log entry from B. Same-system shared configuration updates may prompt reload/review of that system's revision but must not retarget running sessions. Theme changes may follow the existing account preference but cannot reset these workspace states.

System setup → **Import Ansible inventory files** opens an Administrator-only wizard that accepts direct INI/hosts/YAML and inventory ZIP companions as well as canonical JSON. The target system name and import-source ID stay visible. Display selected/ignored file names, detected format, groups/hosts/process counts, omitted-secret warnings without values, subsystem conflicts, credentials/parser/jump mapping and per-field changes. Host-only import is a successful supported outcome with zero processes, not an invented process diagram. The final confirmation is bound to the shown project/revision/preview.

On refresh or duplicated page, load the named system and safe personal layout; do not inherit live-control handles from copied storage or start SSH automatically. Offer explicit resume of owned detached sessions. Closing/stopping A must not stop B; logout is visibly account-wide. Add UI acceptance screenshots in **both themes**, two same-account pages in one browser context (two systems and the same system), including active filters, background slow page, imports and permission-denied states. See document 16 and AT91–AT120.
