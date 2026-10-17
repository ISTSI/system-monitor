# 11 — Deployment and operations specification

These are requirements for artifacts Codex must build, not instructions that can start an application from this specification alone.

## Deployment shape

Ship a Linux x86-64 OCI image containing the Python backend, migrations and compiled frontend assets. Serve the frontend/API from one origin behind a local HTTPS reverse proxy. Do not build the frontend or install Python/npm packages at production startup. Node.js is build-time only. The backend runs as a non-root service identity with writable state/cache volumes and a read-only application image.

Provide a Docker Compose v2 recipe for Ubuntu and a Podman/systemd (Quadlet where supported) recipe for Rocky Linux 9. Both use the same application artifact plus a managed MariaDB service or an explicitly configured existing MariaDB endpoint. Docker Compose must include database provisioning/health/migration dependencies. Pin database and reverse-proxy artifacts as well. Validate supported keys against the actual target runtime version, not only online latest documentation. Podman documents declarative systemd integration [S16]. Supply an equivalent documented systemd launch fallback only when a target runtime lacks a required Quadlet feature.

Do not disable SELinux on Rocky or make data directories world-writable to fix permissions. Document correct service-user ownership, SELinux labels, ports and rootless networking/volume semantics. No privileged container or host Docker socket mount. Constrain capabilities, process count, memory and writable directories. Bind the backend only to the internal proxy network/loopback; expose only the intended HTTPS port.

Ubuntu version was not specified. Establish and record the tested supported Ubuntu LTS version during implementation (Ubuntu 24.04 LTS is a baseline candidate), and test Rocky Linux 9. Exact host/container runtime versions belong in a release test matrix. Do not claim compatibility from the mere existence of a YAML recipe.

## Offline delivery

Build on an approved connected machine. Resolve and pin dependencies, run tests, compile local assets, scan dependency information, build the images and produce an SBOM/notice bundle. Export application/proxy/MariaDB images with checksums and a release manifest. Docker documents image save/load for moving images without a registry connection [S15]. Supply corresponding Podman instructions and disable image pulling in offline launch recipes.

A release directory should contain versioned image archives, manifest/checksums, Compose/Podman/proxy configuration, migration/admin tools, installation instructions, operator guide, test report, backup/restore scripts and license notices. Image archives/dependencies are **not included in this specification package**; generating them is Stage 08 work.

An offline server needs an approved container runtime, system facilities and trusted certificate available beforehand. Document those prerequisites and an offline bootstrap method appropriate to the selected OS repository packages. An app image does not install Docker/Podman, certificates or OS updates by itself. Avoid `curl | sh`, unpinned Internet installs and runtime registry pulls.

Provision an internal-CA or manually supplied certificate and key. No Internet ACME process. The administrator installs the trust chain in client browsers/OS as required. Use explicit base URL/allowed origins, configure reverse-proxy WebSocket upgrade and timeouts, and do not publish a default insecure password. Bootstrap the first Administrator interactively and provide protected database/vault secret generation on the server. Administrators provision Inspector accounts through the authenticated UI.

## Required configuration categories

Deployment policy: DB host/port/name/user/password-file/TLS/pool settings, state/cache paths, HTTPS/origin/proxy settings, resource ceilings, network policy, bootstrap defaults and secret-key path. Application settings/accounts/preferences: Administrator-managed shared defaults and individually owned appearance/workspaces in MariaDB. Project config: topology, logical connections/credential references, parsers, log paths and shared views. Local trust/vault: encrypted SSH passwords, host keys and approved target/root records. Do not merge these categories into one exportable YAML file.

The deployment policy has a strict schema and matching examples, while the app loader remains Codex implementation work. Concrete database-only templates and a safe local secret generator are in examples/deployment/. Implement strict validation and explicit environment/file precedence as in document 14. It must not silently widen limits because a project import asks for it.

## Network verification

The **Linux server**, not merely the user's Windows laptop, must be able to resolve/reach the configured target or jump host. For jump connections, the jump host must be permitted to forward to the selected target. Both SSH legs need independent host-key trust. Tests should distinguish DNS failure, routing/VPN failure, rejected forwarding, bad credentials, host-key mismatch, SFTP unavailable and file permission failure.

No discovery scan or automated connection to all hosts is needed at startup. Connect only through explicit operations against configured approved sources. Verify an offline cold start with all Internet egress blocked while permitting LAN/VPN and DNS required by the deployment. Inspect browser and server traffic for external calls, including fonts, analytics, update checks and icons.

## Backup, restore and updates

Quiesce app collection, edits and retention, then back up MariaDB using a consistent InnoDB dump or a tested MariaDB backup mechanism. Coordinate the source manifests and pinned/cache files in the same backup point; a live datadir file copy is not a consistent backup. Include user roles/preferences, schema/version information and protected deployment recovery metadata. See document 14 for details. Store vault master-key backups separately with appropriate access control; document that a data-only restore leaves credentials unusable without the key. Do not put that key into investigation bundles.

Restore into a test directory first, validate schema/version/checksums and confirm offline access to a saved investigation. Existing SSH trust and credentials should be restored only through the protected administrative backup path, not ordinary project import.

Before upgrade: stop/start or quiesce captures visibly, take a consistent backup, verify artifact checksums, run migrations and start the new version. Keep the old artifact and matching pre-migration backup for rollback; rolling back an image against an incompatible upgraded DB is not a valid rollback procedure. A failed migration does not leave the UI pretending startup succeeded.

## Operations guide content

Document adding an approved target and verifying its fingerprint, assigning direct-read credentials, testing active/rotated/archive access, defining/testing a parser, importing inventory, creating a time investigation, live filters and pause/stop, interpreting coverage/rotation warnings, recording/saving data, redaction/export, cache/pin policy, backup/restore and application updates. Describe common failures with remedies that do not weaken SSH trust or filesystem permissions.

Operational diagnostics expose the application version, job/session counts and safe errors; no raw source data or passwords. Restarted jobs/sessions report interrupted state and do not silently resume connections on the operator's behalf.

## Version 2 deployment acceptance additions

The managed startup sequence is MariaDB initialized/healthy → scoped migration succeeds → first Administrator provisioned (no public setup or default login) → app/proxy usable. The templates permit the app to be started before interactive bootstrap but it must remain protected with no usable accounts until bootstrap completes. An existing-database variant skips managed DB creation and validates the configured endpoint/TLS/grants. The serving app has no root/migration credential mounts or Docker socket.

Test retained-volume restarts, password rotation, unhealthy DB, wrong TLS identity, schema mismatch and privilege limits. All DB API tests run on MariaDB, not SQLite. Verify byte-for-byte original theme assets and both rendered themes in the offline build. Add accounts/roles, personal settings and permission/ownership checks to the operations guide. Never reuse or modify any unrelated MariaDB volume on the host.


## Version 3 one deployment, several systems

The existing Compose stack starts one MariaDB service, one serving backend, migrations and HTTPS proxy. Do not launch a second backend/database for the second system or change the DB endpoint when selecting it. Accounts/default theme are global; topology/log configuration/imports/workspaces are project-scoped as in document 16.

New deployment examples permit 10 live subscriptions per user and global, 5 per page workspace, and 10 per project. Test two pages with five low-rate processes each on the stated 16 GB baseline. The historical concurrency pool remains separately bounded and cannot hold a four-host semaphore for every live source indefinitely. Existing custom limits are preserved on upgrade, with a compatibility warning and explicit change workflow where they are too low. Measure memory/latency rather than assuming linear capacity.

Release smoke test: create Systems A and B; import direct INI into A and companion-file YAML into B; approve only synthetic local SFTP endpoints; open two same-account windows; verify filters and stop/close isolation; back up; restart offline without restarting SSH automatically; reopen each system's saved cached investigation. Include all systems, source mappings and cache namespaces in backup/restore verification, and reject ambiguous orphan data in upgrade preflight. No added runtime Ansible dependency.
