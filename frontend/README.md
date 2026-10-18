# System Inspector web application

The shared historical/live event styling is deployed at **https://localhost:8449**.
Refresh for compact live rows and separate UTC time/process/host/log-entry
columns in merged and split views. The frontend-only overlay preserves the
backend, schema `0015_remember_login`, accounts and retained data. Actual served
asset hashes, browser checks and recovery evidence are recorded under
`verification/live-events-preview/` and in `progress/STATUS.md`.

The pin editing and independent collection/display range update is available
at **https://localhost:8449**. Refresh existing pages for compact description/View
pin rows, process-grouped previews and Modify/update/create flow. The matching
backend uses schema `0015_remember_login` without a new migration. Accounts,
configuration and retained investigations/cache are preserved; 8445 is unchanged.
Actual served-asset/browser and preservation checks are recorded under
`verification/pin-range-preview/` and in `progress/STATUS.md`.

**Copy** in the connection list or **Edit connection** opens **Add connection**
with the saved profile details and a new editable stable ID. Choose a unique
name, review the fields and choose **Save connection** to create the copy. The credential
reference is retained; the original profile and server assignments stay intact.
The authorized frontend-only rollout is available on **https://localhost:8449**;
refresh existing pages. Actual served-asset/browser and preservation checks are
recorded under `verification/connection-copy-preview/` and in the status record.

Administrator subsystem/server frames include **+** actions that open the
existing Add server/Add process form with that parent selected. New process
paths propose `app.log` under the first log root in the server's connection
profile, follow server changes while untouched and preserve typed/existing
paths. Login includes opt-in **Remember me** for 30 days; the matching backend
requires `0015_remember_login`. These controls are bundled in English/Polish.
These controls are now available on the 8449 review preview, with matching
backend and migration. Filters/grouped pins remain available and cached data is
preserved; the installed 8445 app is unchanged.

Stage 06 adds personal investigation tools to historical captures and explicit
live recordings. Save a title, notes, process/time/filter selection and pane
layout; reopen the investigation URL in a separate page without collection.
Exact correlation search compares a complete parsed metadata value; literal
search also finds longer strings. Chronological traces show integer microsecond
deltas with clock/causality limitations. Bookmarks preserve source labels and can
pin surrounding unmatched or out-of-range context independently of source cache.

The investigation panel exposes source provenance and explicit unpinned cache
expiry. Missing data is shown as unavailable. Pinned investigations cannot expire;
collection deletion requires unpinning and removing bookmarks. Bundle export
requires reviewing a redacted preview before download. Import requires preview
and creates a private offline copy with origin-system provenance, including under
a different selected system. It never offers active collection controls for that
copy. All state remains page-local until explicitly saved to the owned resource.

React/TypeScript/Vite sources compile to local static assets served by FastAPI on the same HTTPS origin. No runtime npm, CDN, cloud account, fonts or Internet access is needed. The current vertical slice includes authentication, system catalogue, revisioned topology editing, account management, appearance, historical investigation and live SFTP monitoring. Local fixture collection indexes real plain, ZIP and TAR.GZ events in MariaDB. Administrator SSH password storage, host-key approval and direct/single-jump connection tests are available through server details or Connections. Source access remains scoped to the system and configured roots. Log history labels the actual SSH or explicitly enabled local-demo transport.

The top bar contains Systems, Administrator-only Accounts, Settings for both roles, and Administrator-only Admin, followed by the synthetic-demo label when enabled and the account menu. Personal appearance is changed only in Settings; deployment settings remain Administrator-only. Admin (`/admin`) contains system creation, metadata editing, archival and restoration.

Set the **Collection time range** before **Collect sources**. Its UTC bounds
and process checkboxes configure the next collection. The collected range and
process snapshots remain visible with the current results, independently of
later changes to that form. Timestamped display queries stay within the original
collection interval; source context and diagnostic records remain available.

The events table's **Filters** button opens a separate dialog for display UTC bounds
and literal content filters. Its existing-filter list removes each include or
exclude term individually, globally or for one process. **Add filter** accepts
literal log content, an Include/Exclude action and its process scope; global
and per-process matching retain any/all and case-sensitivity controls. **Apply
filters** commits the draft; Cancel discards it. A failed query keeps the dialog
and its draft available. Clearing content filters preserves the time range;
**Reset time range** restores the retained collection's bounds.

From/To inputs display `YYYY-MM-DD HH:mm:ss` in UTC. Type a value or use the
adjacent calendar button to choose the date and time, including seconds. ISO
timestamps remain accepted on paste; retained bounds preserve exact stored
microseconds until edited. From is inclusive and To is exclusive. Invalid
dates/ranges cannot be applied or become collection bounds.

Click a historical row to mark/unmark it; keyboard Space also toggles a focused
row. **Pin** saves up to 100 marked entries together with one shared description.
Selections can span pages, processes and changed filters in the same collection.
Each entry is pinned using the exact query context from when it was marked.
A successful save creates one compact description-and-**View** row under **Pins**
in a single personal investigation workspace. **View** opens the saved text,
grouped in one terminal block per process, and an editable description.
**Save** persists it; **Cancel** discards the edit. **Modify** restores the pin's
selection to the event table. Pressing **Pin** again explicitly offers **Update
the pin** or **Create a new pin**. Updating replaces the selection atomically and
preserves the pin ID; creating a copy leaves the original intact. **Delete pin**
is available inside the saved pin popup. Its selected
text and original provenance remain available after source-cache expiry.
Existing bookmarks with surrounding context remain separate. Pin creation is
atomic and preserves marks on error; a different collection clears the draft
selection. Group descriptions/membership also survive previewed redacted bundle
export/import, including private offline copies in another system.

**Collect sources** works directly; **Preview collection plan** is optional.
The plan panel appears only after preview is requested. Finished and reopened
collections automatically load Timestamped events. **Log entry** displays the
line without its parsed timestamp prefix; **Context** retains the original.
Both roles can delete their own finished collection with **Delete collection**
and the confirmation dialog. Deletion removes that collection's retained data.

Timestamp metadata throughout the UI displays `YYYY-MM-DD HH:mm:ss` in UTC.
Source log text, original parser evidence and exact API microseconds are
preserved. Historical results use compact monospace rows; the eye immediately
before the timestamp opens source context. **Columns** hides/shows UTC time,
host and process independently; **Show all columns** restores them. Choices
apply across that page's merged/split results. **Full screen** maximizes results
within the browser, with **Exit full screen** or Escape to return. Presentation
changes retain scroll/results and stay independent in other browser pages.

Live monitoring uses the same compact rows, text rendering and separate UTC time,
process, host and log-entry columns in merged and separate panes. Sticky headings
and horizontal scrolling keep long lines readable. Its live scroll following,
Pause/Resume display, timestamp diagnostics and late-arrival labels remain
available; initial history requests use the measured compact-row viewport.

**Rows**, with **Viewport** as its measured-size option, sits at the right of the
footer below the table/panes. **Show process**, immediately
right of **Result layout**, has checkboxes for any subset of the applied query's
processes in both layouts. Merged results query the enabled subset and paginate
its matches; split results hide/show the existing independent process panes.
All processes can be unchecked, displaying an explicit empty state. **Pane
arrangement** remains visible, disabled in Merged and enabled in Separate process
panes, with Stacked/2/3/4-column choices. Process choices display
`server name: process name`; immutable IDs appear on hover. These controls stay
local to the page; filter/time drafts wait for **Apply filters**. Hidden
split panes retain their loaded page/scroll and their own pagination/retry.

Choose **Monitor** or **Monitor selected** from a topology selection, or open
**Live monitor** and choose configured processes. The viewer measures its pane
height for recent matching history. Merged and separate process panes share
literal global filters and optional per-process filters; advanced controls
support any/all include terms, exclude terms and server-side Unicode casefold.
Filter changes refilter retained raw capture without reconnecting SSH.
**Pause display** freezes displayed rows while receipt and recording continue;
**Resume display**, **Stop this monitor**, **Record** and **Load older** have
separate actions. Counters and source details expose retention, seed limits,
disconnects and uncertain continuity. Unknown times have their own lane.

Live controls belong to a server-issued page workspace and control lease.
Reload/duplicate starts no collection and adopts no copied handle. A detached
monitor appears under **Your detached monitors** with explicit **Resume in this
window**. System switching detaches this page's monitor for its bounded lease.
Other pages retain their filters and controls; global logout intentionally ends
the account session in every page. Appearance updates preserve live sockets,
session identity, filters, display pause and stream ordering.

An open system uses a compact header with the System action menu and system name on the left and the system selector on the right. The Administrator menu contains Add subsystem, Add server, Add process, Add flow, List connections, List Parsers, Import configuration, Export JSON and Export YAML. Undo and Redo sit beside Documented topology. The former workspace status strip and separate topology editing button bar are removed. Use ordinary system links and the browser's tab/window actions to open another page; there is no Open separately button. Each page retains its own system and workspace state.

The recorded connected-build toolchain is Node **24.22.0**, npm **11.19.1**, TypeScript **5.9.3**, React **19.3.1** and Vite **8.3.4**. The generated package-lock.json locks the full dependency tree with actual registry integrity values. TypeScript 5 is required by the API generator's declared peer dependency; the lock does not bypass peer checks. React Flow renders the editable topology; TanStack Virtual renders historical log rows.

On Windows, bootstrap the official checksum-verified portable Node archive and install packages from the repository root:

```powershell
powershell -File scripts/bootstrap_node.ps1 -Connected
backend/.venv/Scripts/python.exe scripts/frontend.py install --connected
```

The helper uses repository-local Node when present, and requires recorded Node 24.22.0 otherwise. All its npm/browser caches stay under .cache. An already provisioned Linux build environment can use Node 24.22.0 and `npm ci --ignore-scripts --no-audit --no-fund` from this directory. The Linux runtime serves the build; it does not need Node.

```powershell
backend/.venv/Scripts/python.exe scripts/frontend.py lint
backend/.venv/Scripts/python.exe scripts/frontend.py typecheck
backend/.venv/Scripts/python.exe scripts/frontend.py api:generate
backend/.venv/Scripts/python.exe scripts/frontend.py api:check
backend/.venv/Scripts/python.exe scripts/frontend.py build
```

Generate API types after regenerating backend/openapi.json. The check compares generated output and fails on drift. `src/api/schema.d.ts` is a generated artifact, never a hand-maintained API contract.

Browser checks use Playwright **1.64.1** and its Chromium **156.0.8078.4** build **1248**. Connected browser setup is `node node_modules/@playwright/test/cli.js install chromium` with PLAYWRIGHT_BROWSERS_PATH set to the repository .cache/playwright directory. The test configuration uses this same directory and never downloads at test runtime.

Run the isolated Stage 03 local Docker fixture setup and HTTPS server documented in [backend setup](../backend/README.md), then set INSPECTOR_E2E_ACCOUNTS to the absolute path of the ignored synthetic account fixture and run:

```powershell
backend/.venv/Scripts/python.exe scripts/frontend.py e2e
```

Tests use one browser context for parallel pages and check both different-system and duplicated same-system workspaces. The screenshot matrix covers both roles, both themes and 1280×720/1920×1080. Traces, videos and automatic failure screenshots are disabled to keep password entry out of artifacts. Deliberate screenshots capture authenticated views and cleared password forms only. The tests block external browser requests and assert none were attempted. Browser certificate verification is bypassed only by the local test configuration, for the generated loopback certificate.

The browser regressions also delay real preference/session responses through logout and a subsequent login, checking that stale responses cannot restore protected content or clear the new session/CSRF token. The targeted 200% layout equivalent uses CSS 640×360 with deviceScaleFactor 2: the same layout and physical pixel budget as a 1280×720 viewport at 200% zoom. This is explicitly a layout equivalent, not browser toolbar zoom automation. Keyboard focus, dialog scrolling, process selection and horizontal overflow are checked. Set INSPECTOR_E2E_URL=https://localhost:8445, INSPECTOR_E2E_REPORT_STAGE=stage-3 and INSPECTOR_E2E_ACCOUNTS to .secrets/stage3-browser/accounts.json (absolute path). Reports are under verification/stage-3; set INSPECTOR_E2E_REPORT_NAME to a distinct lowercase basename when preserving separate runs. Repeated runs against the temporary VM need fresh synthetic account fixtures or expiry of the bounded workspace grace period; deployment quotas are retained during tests.

Dependency/license evidence is in [the collected inventory](../third_party/frontend/README.md). Package notices are copied from the actual installed artifacts; packages without separate license texts retain their published package metadata and README. These are development-platform notices; release assembly must collect notices for its own platform as well.

The Stage 05 browser suite uses the isolated generated SFTP fixture and HTTPS
origin `https://localhost:8447`; see `scripts/stage5_local.py`. Set
`INSPECTOR_E2E_URL=https://localhost:8447`,
`INSPECTOR_E2E_REPORT_STAGE=stage-5`,
`INSPECTOR_E2E_ACCOUNTS` to the absolute protected
`.secrets/stage5-browser/accounts.json` path and
`INSPECTOR_E2E_LOCAL_ASSETS=1` after building, then run
`python scripts/frontend.py e2e live.spec.ts`. The suite writes only through
the local synthetic fixture controller; application SSH remains read-only.
It checks both roles, same-context independent pages, explicit reattachment,
late stale frames, delayed clients, global logout and two five-source systems
including an idle source. Chromium's local-network-access test permission is
granted only to the generated loopback fixture origin for its WSS stream.
Latency uses the synthetic line's UTC timestamp and a MutationObserver at first
DOM insertion, with separate receipt and display timings. Actual results are
recorded in `progress/STATUS.md`.

The capacity case creates a bounded 16 MiB regular ZIP member through the fixture
controller, then collects it in both systems while ten live subscriptions remain
active and one page's delivery is held. Its producer writes at 250 ms intervals
inside one asynchronous fixture process, preserving browser responsiveness and
recording the actual write rate. Resource evidence includes the surrounding job
states; direct fixture TLS and page JavaScript heap measurements do not qualify
the release proxy or full browser process memory.

This suite is opt-in: any other origin skips the live cases without reading the
ignored fixture metadata or protected account fixture. Generated test accounts are
never application defaults.

Version/engine references: [official Node release index](https://nodejs.org/dist/index.json), [Vite compatibility](https://vite.dev/guide/), [Playwright browsers](https://playwright.dev/docs/browsers). These are connected build references, not runtime dependencies.

For the events-table and grouped-pin preview checks, set `INSPECTOR_E2E_URL=https://localhost:8449` and the protected synthetic account path, then run `python scripts/frontend.py e2e events_table.spec.ts event_pins.spec.ts`. Set `INSPECTOR_E2E_SERVED_ASSETS=1` to exercise the assets served by HTTPS; otherwise these two suites substitute the local build within their browser context. Login retries respect the unchanged rate limit.
