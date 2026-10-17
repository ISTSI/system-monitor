# System Inspector — Codex implementation package

The application includes the real backend, MariaDB migrations, local accounts, persistent appearance, independent system workspaces and the Stage 02 topology/configuration implementation. Administrators edit nested diagrams, documentation, flows and named views, with revision checks, undo/redo and explicit configuration import previews. Inspectors navigate a safe read-only projection. See [setup and scope](backend/README.md), [current verification status](progress/STATUS.md) and [incremental plan](progress/V3_SLICE_PLAN.md). Stage 03 adds the historical parser, safe archives, MariaDB event index and virtualised query/context viewer. Stage 04 adds encrypted passwords, explicit host-key and source/root approval, configured path checks, and bounded direct/single-jump SSH/SFTP historical collection. Stage 05 adds supervised live SFTP capture, scoped WebSockets, independent per-page controls, retained literal refiltering, split/merged panes and explicit recording. Full investigation tools, Ansible inventory reconciliation and release hardening remain later work. The original package description below is retained as the handoff baseline.

Stage 05 is installed locally at **https://localhost:8445**, with schema
`0009_live`. The backed-up upgrade preserved existing accounts, systems,
security settings and cached investigations. See the dated deployment entry in
[STATUS.md](progress/STATUS.md). Stage 06 has not started.

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

The two original references remain byte-for-byte unchanged: [Light — Cool Slate](assets/themes/light-cool-slate.png) and [Dark — Graphite Dusk](assets/themes/dark-graphite-dusk.png), with shared [tokens](assets/themes/tokens.json) and [CSS](assets/themes/tokens.css). Theme changes cannot reset live sessions. Working branding is configurable System Inspector, English UI; mockup green badges are not health telemetry.

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
