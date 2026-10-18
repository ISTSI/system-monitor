# System Inspector — Codex implementation package

The application includes the real backend, MariaDB migrations, local accounts, persistent appearance, independent system workspaces and the Stage 02 topology/configuration implementation. Administrators edit nested diagrams, documentation, flows and named views, with revision checks, undo/redo and explicit configuration import previews. Inspectors navigate a safe read-only projection. See [setup and scope](backend/README.md), [current verification status](progress/STATUS.md) and [incremental plan](progress/V3_SLICE_PLAN.md). Stage 03 adds the historical parser, safe archives, MariaDB event index and virtualised query/context viewer. Stage 04 adds encrypted passwords, explicit host-key and source/root approval, configured path checks, and bounded direct/single-jump SSH/SFTP historical collection. Stage 05 adds supervised live SFTP capture, scoped WebSockets, independent per-page controls, retained literal refiltering, split/merged panes and explicit recording. Stage 06 adds saved personal analysis, exact correlation traces, annotations, pinned context and previewed sanitized offline bundle exchange. Stage 07 adds the safe static Ansible file/ZIP setup wizard, system-scoped preview/reconciliation and parser draft diagnostics. Its verification is recorded in the status document; release qualification remains Stage 08. The original package description below is retained as the handoff baseline.

The matching live/log event presentation is installed at **https://localhost:8449**.
Refresh existing pages for compact live rows with separate UTC time, process,
host and log-entry columns in merged and split panes. This frontend-only update
preserves the backend, schema `0015_remember_login`, accounts, configuration and
retained investigations/cache. Installed-browser and preservation checks are
recorded in `verification/live-events-preview/` and [STATUS.md](progress/STATUS.md).

The connection **Copy** action is deployed on the **https://localhost:8449**
preview. Refresh existing pages to load it. Copy in the connection list or edit
screen opens Add connection with the saved details and a fresh stable ID;
choose a unique name before saving. The preview's backend/schema and retained
configuration/investigations are preserved. Deployment checks are recorded in
[STATUS.md](progress/STATUS.md).

The reviewed events-view follow-up is installed at **https://localhost:8445**
with schema `0014_languages`. Refresh existing pages to load it. Accounts,
configuration and cached investigations are preserved; deployment and recovery
evidence is recorded in [STATUS.md](progress/STATUS.md).

The collection form takes its own UTC range before collection starts. **Filters**
in the events table changes only the display of retained logs; its date range
and process choices stay independent of the next collection's settings.
Clicking rows marks up to 100 entries; **Pin** saves them as one personal
investigation row with a description and **View** button. The popup groups logs
by process and offers **Save**, **Cancel** and **Modify**. Modify restores the
selection in the table; pressing **Pin** then offers an update or a new pin.
Pins retain the selected text/provenance after source
expiry and participate in previewed, redacted offline bundles. Group metadata
uses existing MariaDB analysis JSON; no new DDL is required. **Rows** and
**Viewport** appear at the right of the results footer, and process choices use
`server name: process name` with immutable IDs on hover. Preview rollout and
verification are tracked separately in [STATUS.md](progress/STATUS.md).

The pin editing and separate collection/display range follow-up is now deployed
at **https://localhost:8449**. Refresh existing pages. Accounts, configuration,
saved investigations and log cache are preserved; schema remains
`0015_remember_login`. The 8445 installation is unchanged. Backup, rollback and
actual-served browser checks are recorded in [STATUS.md](progress/STATUS.md).

The 18 October topology/login source follow-up adds frame **+** actions for
servers/processes, connection-root-based log-path suggestions, and opt-in
30-day **Remember me** authentication. It requires additive migration
`0015_remember_login`. Isolated API, migration and browser checks pass; this
follow-up is now available on the **8449 preview**, with its matching frontend,
backend and migrated schema. **Remember me** is visible on login; checked logins
last 30 days. The installed 8445 backend retains schema `0014_languages`.
See the latest entry
in [STATUS.md](progress/STATUS.md).

The separate-process-pane preview is updated at **https://localhost:8449**.
It includes **Show process** checkboxes beside Result layout in both layouts,
an always-visible Pane arrangement control (disabled in Merged), page size
below the results, and independent process pagination. The latest preview adds
the Filters dialog and described groups of pinned log rows. Its current backend
uses schema `0015_remember_login`; cached investigations are preserved.
Refresh to load it.

Stage 07 with the language follow-up is installed locally at
**https://localhost:8445**, with schema `0014_languages`, following the separate
deployment authorization on 18 October
2026. The backed-up upgrade preserved existing accounts, systems, security
settings and cached investigations. Inventory import/reimport and parser-draft
diagnostics are available alongside the Stage 06 investigation tools. See the
dated deployment entry in [STATUS.md](progress/STATUS.md). This local upgrade
does not complete Stage 08 offline-release qualification.

Personal appearance and language are under the logged-in user menu →
Preferences; Settings is Administrator-only. The earlier Preferences frontend
overlay is now included in the matching language package. Its original backend,
overlay and pre-migration recovery material remain available for rollback.

The language follow-up is deployed on 8445: English and Polish are bundled
offline. Administrators choose **Settings → Application default language**;
each user chooses **user menu → Preferences → Language**, including Application
default. Preferences persist in MariaDB and apply across that account's windows
without resetting investigations. The signed-out screen follows the shared
default. The authorized deployment applied `0014_languages`, installed the
matching backend/frontend, and passed actual installed-browser and preservation
checks. Refresh existing pages to load it. See the dated deployment entry in
[STATUS.md](progress/STATUS.md).

The timestamp/events-table UI follow-up is also installed on **8445** following
the separate **“Deploy”** authorization on 18 October 2026. Refresh to load UTC
timestamps in `YYYY-MM-DD HH:mm:ss` format, compact rows with context eyes,
optional columns and full-screen results. It uses a read-only frontend overlay;
the existing language backend, schema `0014_languages`, accounts, settings and
cached investigations are preserved. Previous frontend assets remain available
and the exact Compose rollback is retained under `.secrets/events-table-install`.

**Package version 3.0 · 17 October 2026**

A complete revised specification, reference-asset, configuration/deployment-template and synthetic-test package—not an implemented application, migration run or installer. No production credentials, populated database, dependencies or prebuilt images are included. The specified Linux-hosted web app works without runtime Internet access and reaches approved Linux hosts/jump hosts over LAN/VPN; Windows browsers are clients.

## This iteration

**Native Ansible inventory-file import** is now an explicit system-setup workflow: direct static INI/extensionless hosts files, YAML/YML, uploaded ZIP bundles with inventory-relative group_vars/host_vars, and canonical JSON. It includes target-system selection, group/subsystem and optional process/log mapping, safe preview and idempotent reconciliation. Ansible/plugin/script execution is forbidden. Ordinary supported static files require no Ansible installation or manual JSON conversion; complex unsupported semantics have a documented trusted canonical fallback. See [inventory import](docs/10_ANSIBLE_IMPORT.md).

**Several system configurations share one deployment and MariaDB database.** The same account can open System A in one browser window and System B in another and monitor both concurrently. Each page has its own selected system, process set, filters, pane/scroll state and live sessions. The system is encoded in the page URL; it is not a shared account “current system.” Browser close/stop/filter changes affect only the relevant workspace, while account logout/revocation intentionally affects all of that account's sessions. See [multiple systems and workspaces](docs/16_MULTI_SYSTEM_WORKSPACES.md).

The existing Project entity represents a System; keep `project_id` as the technical identifier. Do not create a second incompatible model or a separate backend/database per system. End-to-end scope checks cover HTTP, WebSockets, MariaDB foreign keys, SSH pools, caches, imports, investigations and downloads. A system-selector UI alone does not meet the requirement.

There are **56 numbered requirements and 120 future application acceptance targets**. These are implementation obligations, not passed application tests. Actual package verification is recorded in [VERIFICATION.md](VERIFICATION.md). [CHANGELOG.md](CHANGELOG.md) describes v3 and the retained history.

## Start or upgrade

For a **fresh build**, open the extracted directory as the Codex workspace and submit [CODEX_START_PROMPT.md](CODEX_START_PROMPT.md). It authorizes Stage 00 and Stage 01 only; proceed through the numbered prompts after each review gate.

For **existing v1/v2 code**, merge this package deliberately and submit [CODEX_UPGRADE_PROMPT.md](CODEX_UPGRADE_PROMPT.md). Read [the v3 upgrade guide](docs/17_UPGRADING_TO_V3.md); document 15 retains conditional v1 MariaDB/role/theme prerequisites. Never overwrite source, secrets, real progress or data merely by extracting the package over a repository. Repository guidance remains in `AGENTS.md` [S01 in SOURCES].

## Preserved architecture and functionality

| Layer | Decision |
|---|---|
| Browser | React/TypeScript/Vite, React Flow, TanStack Virtual; Cool Slate light and Graphite Dusk dark themes |
| Backend | Python 3.13, FastAPI/Pydantic/AsyncSSH, one ASGI worker and supervised bounded tasks |
| Authentication | Local Administrator/Inspector accounts; application-wide roles; per-resource ownership and explicit project/workspace scope |
| SSH | Agentless read-only SFTP, password authentication, strict host keys, direct or one jump hop; no terminal/sudo |
| Persistence | One MariaDB database, SQLAlchemy asyncio/asyncmy and Alembic; scoped raw-file cache on server disk |
| Deployment | App + HTTPS proxy + MariaDB images; Docker Compose plus required-to-test Rocky Podman/systemd path; configured DB endpoint |
| Verification target | Actual unit/API/MariaDB/SSH/browser tests, including two pages in one browser context and offline release checks |

Original functionality remains: subsystem → physical server → process diagrams, data transfers, click-through documentation, search, UI/config editing, historical UTC `[from,to)` queries, plain/ZIP/TAR.GZ logs, split/merged live viewers, literal include/exclude filters with viewport-sized matching history, saved investigations, correlation searches, notes/bookmarks/context, provenance/coverage, redacted bundles and parser/access tests. No runtime cloud/AI/telemetry/CDN dependency, remote agent or automatic process-health monitoring is added.

## Themes, roles and database remain unchanged in purpose

The two original references remain byte-for-byte unchanged: [Light — Cool Slate](assets/themes/light-cool-slate.png) and [Dark — Graphite Dusk](assets/themes/dark-graphite-dusk.png), with shared [tokens](assets/themes/tokens.json) and [CSS](assets/themes/tokens.css). Theme changes cannot reset live sessions. Working branding is configurable System Inspector; English is the initial UI language. Mockup green badges are not health telemetry.

Both roles change their own theme through the logged-in user menu → Preferences.
Administrator-only Settings contains the shared default for new accounts, the
signed-out screen and accounts following Application default.

Administrators manage all shared system definitions/settings, users, credentials/trust and inventory imports. Inspectors select systems and inspect approved topology/logs but cannot change shared configuration. Both roles keep their own investigations, notes/bookmarks and appearance. These remain global roles across systems, not new per-system ACLs or a multi-tenant isolation claim. Private ownership still applies. [Full role rules](docs/13_ROLES_AND_AUTHORIZATION.md).

[Deployment configuration](examples/deployment-policy.example.yaml) explicitly specifies MariaDB host/port/name/user/password-file/TLS/pool/timeouts. All systems use that endpoint; system selection never switches databases. The [MariaDB Docker templates](examples/deployment/README.md), persistent volume, separated runtime/migration credentials, offline image workflow and [existing verified-TLS endpoint example](examples/application.external-db.example.yaml) remain included. Actual application/container startup is still Codex implementation/testing work.

## Capacity and backward compatibility

Baseline **per system**: 10–20 hosts, 30–60 configured processes, at most ten per host and 10–20 MB per investigation. Test two systems/windows with up to five low-rate live sources each, ten total, on one 16 GB server. New default ceilings are 5 subscriptions/workspace, 10/system, 10/user and 10/deployment. Limits are bounded and enforced atomically; a rejected start must not evict an established monitor. Existing custom deployment limits are preserved and incompatibilities reported explicitly.

Single-system project YAML/JSON interchange remains **schema 2.0**, retaining v1 previewed conversion. Existing project IDs become the system IDs; event IDs remain unchanged and are addressed as `(project_id,event_id)`. New workspace-scoped live requests and WebSocket protocol 2 require coordinated frontend/backend changes. The upgrade guide covers actual data migration only when real code/data exists, with no arbitrary default-system backfill or production changes authorized here.

## Package map

| Location | Contents |
|---|---|
| `AGENTS.md`, `CODEX_*_PROMPT.md`, `prompts/` | Current fresh/upgrade workflows and nine staged gates |
| `docs/01`–`docs/14` | Updated requirements, architecture, domain/engine/API/UI/security, plan/tests, Ansible, deployment, roles and MariaDB |
| `docs/15`, `docs/16`, `docs/17` | Conditional v1 prerequisites; multi-system/workspace contract; incremental v3 upgrade |
| `contracts/` | Original compatible schemas plus scoped workspaces, inventory preview/commit, live envelopes and scope policy |
| `examples/systems/` | Two complete configs with intentionally repeated internal IDs/addresses and safe workspace examples |
| `examples/ansible/` | Direct files, optional process extension, companion variable tree and equivalent inventory ZIP |
| `examples/deployment/` | Retained MariaDB/app/proxy templates, initialization and protected secret generation |
| `assets/themes/` | Unchanged references and existing semantic theme tokens; no bundled font files |
| `fixtures/`, `tests/package/`, `tools/` | Original fixed log oracle plus collision data and package-only scope/inventory/budget checks |
| `VERIFICATION.md`, `verification/` | Actual package check results; runtime checks explicitly unexecuted |
| `progress/` | Initial templates only; preserve real implementation history on upgrade |

## Verify this handoff

```sh
python -m unittest discover -s tests/package -v
python tools/validate_package.py
python tools/validate_schemas.py
python tools/validate_deployment_examples.py
```

Use `python tools/validate_package.py --verify-handoff` before changing any delivered file to verify hashes. Omit the hash flag after Codex edits the repository. The JSON Schema/YAML and inventory-example checks need locally available `jsonschema`/`PyYAML`; nothing downloads them. Read [tooling scope](tools/README.md).

Passing these commands proves package consistency and the tested synthetic oracles only. It does **not** prove production authorization, MariaDB/FK migration behaviour, multi-window browser isolation, live SSH performance, real inventory import/commit or offline deployment. Those are explicit stage/release gates.
