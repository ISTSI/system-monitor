# Stage 08 release candidate qualification

Stage 08 implementation is available as **0.1.0 offline candidate rc3**. The
stage gate remains open. Native Ubuntu 24.04 LTS and Rocky Linux 9/rootless
Podman with enforcing SELinux have not been run. Building and qualifying the
candidate did not change existing installations. A subsequent explicit
19 October authorization installed the verified Help frontend on local 8445,
retaining its existing backend, runtime image and schema 0016. That deployment
is recorded in [status](../progress/STATUS.md); it does not exercise the new
release runtime or close the remaining qualification gates. 8449 and 8444
remain unchanged.

The later **19 October connectivity repair** is recorded separately in
[status](../progress/STATUS.md). It removes an overlapping retired test bridge,
restores cache access and pins the older 8444 source to its original image/schema.
Qualification fixture retirement now releases project networks while retaining
named data volumes. Those source-tool changes do not rebuild or requalify rc3;
native and strict offline gates remain open.

## Artifacts and reproduction

The generated directory is `dist/system-inspector-0.1.0-offline-rc3/`. Its
`manifest.json` binds all three image archives, exact Linux amd64 image IDs,
packaged runtime/tools/docs/notices, installed package inventory, CycloneDX
SBOM and test report. `SHA256SUMS` covers the manifest and every distributed
file. Original Debian/Ubuntu/Alpine, CPython, nginx/modules and MariaDB notices
are preserved alongside Python/npm notices. The inventory is not a CVE scan.
It preserves bundled texts and does not establish complete corresponding-source
or source-offer coverage for redistribution.

From the locked backend environment, run:

```sh
python scripts/release_offline.py verify --output dist/system-inspector-0.1.0-offline-rc3
```

Build preparation uses `python scripts/release_offline.py build --connected`
when locked build dependencies are not cached; base images must already be
staged by their recorded digest. Omit `--connected` to disable build network.
`make release-offline RELEASE_ARGS="verify --output <directory>"` exposes the
same verification. Generated release directories are immutable: select a new
`--output` for another candidate. An isolated wheel/asset build never replaces
files mounted by retained local services. Final assembly verifies that the
application image's actual modules/migrations/assets match that wheel.

The candidate uses application UID/GID 10001, one ASGI worker, a separate
non-root nginx HTTPS proxy and managed MariaDB with a persistent named volume.
Serving has no SQL root/migration secrets, runtime socket, writable image or
effective Linux capabilities. Startup never installs packages or pulls images.
Both managed and verified-TLS external database recipes are supplied. Follow
[the operator guide](OFFLINE_OPERATIONS.md) for private mounts, certificates,
provisioning, backups, restore, template reconciliation and rollback.

## Executed evidence

Receipts are under `verification/stage-8/`; they are local generated artifacts,
not original specification tests. The release's `TEST_REPORT.json` includes
the combined command/result summary and selected recovery receipts.

| Check actually run | Result |
|---|---|
| Windows `pytest backend/tests/unit -q` | 858 passed, 5 platform skips. |
| `python scripts/stage8_linux.py` | Non-root, read-only, network-none Linux runner: 862 unit passed, one Windows-DACL-only skip; all 129 package tests passed. |
| `python scripts/stage8_regressions.py integration` | 194 actual MariaDB/SSH integration tests passed in 470.56 seconds. |
| `stage8_regressions.py foundation-upgrade`, `upgrade`, `optional-upgrade` | Populated 0002, 0012 and 0015 copies upgrade to 0016; identities, owners, themes, raw bytes and relevant downgrade/refusal/reupgrade behavior preserved. |
| `python scripts/stage8_external_tls.py` | Production asyncmy and authenticated API persistence passed through a pre-provisioned custom DNS endpoint. Wrong CA/name/expired certificates and plaintext rejected. Complex UTF-8/whitespace/quoted passwords also work through the shipped DB client. |
| Linux `unittest discover -s deploy/offline -p test_runtime.py -v` | 14 operator/recovery security tests passed without skips. |
| Actual Docker Compose 2.29.1 config validation | Managed and external recipes passed; no native OS claim. |
| Ruff, formatting, mypy, frontend lint/typecheck/API consistency | Passed; backend mypy checks 37 modules. Runtime helpers use Python 3.9 rules. |
| Frontend unit tests | 20 passed; no new runtime dependency. |
| Help browser suite | 4 role/language cases passed; light/dark/narrow screenshots inspected. This suite intercepts synthetic HTTP and is labelled source evidence. |
| Existing live presentation browser suite | 8 component cases passed; explicitly mocked HTTP/WebSocket harness. |
| Actual release-image browser, `browser-source.json` | 5 passed: both roles, same-context different/same-system pages, EN/PL Help, retained history, literal/context/bookmark/pin/bundle operations, INI A/companion-YAML ZIP B and ten healthy live subscriptions through nginx. |
| Actual restored browser, `browser-restored.json` | Both role cases passed; 3 source-only cases deliberately skipped. Both systems' owned investigations reopen without remote-start requests. |
| Actual archive-reload/cold browser, `browser-cold.json` | Both role cases passed, same 3 deliberate skips; retained event text and preferences work with SFTP stopped. |
| Production image/network inspection | UID 10001, zero capabilities, read-only filesystems, no-new-privileges and secret/socket boundaries passed; bounded app/proxy public TCP probes failed as required by the isolated test networks. |

The coordinated recovery stops app/proxy/SFTP, dumps InnoDB consistently and
copies the matching bounded cache/state through the shipped `fileops.py`.
The raw vault key is excluded. Restore creates fresh SQL accounts/volumes,
rebinds the separately protected key, verifies identical stable table digests
and **126 raw-source checksums**, and decrypts **two credential records** in
memory. Before exposure it verifies zero authentication sessions, active
workspaces, collection jobs or live sessions. Both-role browser tests follow.

Cold restart removes only stopped test containers, verifies and loads all three
archives, runs the explicit migrator and recreates app/proxy against retained
volumes. SFTP stays stopped. The app/database networks are internal; the proxy
has a separate loopback ingress bridge with outbound masquerading disabled.
This is Docker Desktop Linux-container evidence on Windows, with outbound TCP
and browser-origin guards, not a host-wide firewall/native-install claim.

## Corrections and retained failed attempts

Actual runs exposed and corrected: a diagnostics regression logging out its
shared Administrator fixture; strict synthetic CA extensions; tmpfs commas
being parsed as separate YAML values; sourced MariaDB helpers inheriting
incompatible nounset; wildcard runtime grants instead of exact escaped schema
grants; raw vault-key format/ownership; fresh init/restore key handling;
external password quoting; and recovery SQL naming a nonexistent column.
Windows qualification additionally needs real Linux volume/script modes and
LF line endings. Failed receipts/volumes are retained, never relabelled passed.
The native search box consumes Escape to clear nonempty search before a second
Escape closes Help; browser assertions now exercise that behavior explicitly.

## Remaining gate

* AT62: execute the provided Ubuntu 24.04 LTS Docker and Rocky Linux 9 rootless
  Podman/systemd recipes, including enforcing SELinux and host permissions.
  Only Docker Desktop's WSL distro is available; no target host/VM or Podman
  runtime was available. Container base OS names do not satisfy this check.
* AT63/AT87/AT120 strict transfer: use a disposable target with **zero local
  images**, block server/client Internet while permitting approved LAN/DNS,
  transfer/load all archives, and repeat setup/restore/browser scenarios.
  The shared local daemon contains retained installations, so its images were
  not deleted and it was not reconfigured. Isolated egress tests are narrower.
* AT65: run a complete previous-release image plus matching pre-migration
  DB/cache upgrade and rollback on the target host. Populated migration and
  matching-current-artifact restore tests are evidence for parts of this gate.
* The actual-image ten-source browser run verifies simultaneous healthy initial
  subscriptions and independent controls. It does not remeasure sustained
  paced-producer latency/RSS at the specified 16 GB baseline. Earlier stage
  performance evidence remains separately labelled.
* Earlier unit/integration/security gates were rerun in full; historical
  stage-specific Playwright suites tied to retained fixture origins were not
  all rerun against the final images. The new actual-image cases above are the
  stated release browser coverage, not a claim that every earlier browser
  acceptance target passed again.

No real legacy SQLite data was discovered or inferred. No production host,
real credential, upload, remote push or deployment was used. Remaining work is
the outstanding Stage 08 qualification gate; no later stage is claimed.
