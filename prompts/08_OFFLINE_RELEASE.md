# Stage 08 — Harden, verify and produce an offline release

Read AGENTS.md and the relevant references below. Implement this stage only unless a higher-level user prompt explicitly authorises another stage.

## References

- `docs/07_SECURITY.md`
- `docs/09_ACCEPTANCE_TESTS.md`
- `docs/11_DEPLOYMENT_AND_OPERATIONS.md`
- `docs/12_TRACEABILITY.md`
- `docs/SOURCES.md`

## Task

Complete non-root OCI builds, pinned application/proxy artifacts, Docker Compose and Podman/systemd recipes, private state/secret mounts, offline load/start scripts, internal-certificate setup, migrations and one-operator provisioning. Write operator, backup/restore and upgrade/rollback documentation. Produce the actual release images, checksums, manifest, SBOM/notices and test report.

Run all earlier stage gates and security regressions. Test a cold offline start with Internet egress blocked, all assets cached locally by design, authenticated browser access, LAN/SFTP and a saved disconnected investigation. Test coordinated MariaDB/cache backup and restore with roles/preferences and a separately protected vault key. Verify the chosen Ubuntu LTS and Rocky Linux 9 runtime recipes and SELinux/rootless constraints. Do not claim a target platform passed without running it.

## Version 2 gate

Validate managed Docker MariaDB and a verified-TLS external database endpoint. Transfer and cold-load all three image archives with no network pulls; run Ubuntu and Rocky recipes, least-privilege checks, MariaDB/cache coordinated backup and restored account/ownership/theme state. Exercise last-Administrator concurrency, DB outage locks, session revocation and v1 project conversion. Actual SQLite data migration is conditional on discovered real legacy data, never assumed from v1 specification.

## Version 3 gate

Rerun all gates including same-browser-context parallel pages, real MariaDB cross-project constraints and data-upgrade copies, two-system imports and backup/restore, 10-source low-rate capacity, blocked-Internet cold startup and no automatic SSH on restart. A second System must require no second backend/database. Package checks are not application evidence.

## Completion gate

All R01–R56 have implementation and test evidence; the final application is not a mock. Offline release artifacts exist and their hashes verify. Report any untested OS/runtime or environmental blocker explicitly as a release limitation. Do not deploy, push, expose production ports or contact actual monitored hosts without separate authorisation.

Acceptance targets: AT62, AT63, AT64, AT65, AT66, AT82, AT85, AT87, AT116, AT120. Run the tests that actually exist or implement the missing tests for this scope. Do not interpret an acceptance-test name as proof of a passing test. Update progress/STATUS.md with exact commands, results, blocked checks and the next stage.
