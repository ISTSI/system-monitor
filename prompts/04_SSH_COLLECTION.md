# Stage 04 — Connect the real read-only SSH/SFTP collector

Read AGENTS.md and the relevant references below. Implement this stage only unless a higher-level user prompt explicitly authorises another stage.

## References

- `docs/02_ARCHITECTURE.md`
- `docs/04_LOG_ENGINE.md`
- `docs/05_API_AND_WEBSOCKET.md`
- `docs/07_SECURITY.md`
- `docs/11_DEPLOYMENT_AND_OPERATIONS.md`

## Task

Implement AsyncSSH direct and single-jump transports, password vault records, host-key inspection/explicit approval, strict verification on both hops, bounded connection reuse, SFTP path/permission tests, remote candidate planning and cancellable file retrieval. Direct-read dedicated accounts only: no sudo, terminal, remote agents or arbitrary shell execution.

Create an isolated local SSH/SFTP integration environment with independently keyed target and jump endpoints and synthetic log roots. Test failed authentication, unknown/changed target/jump keys, denied forwarding, inaccessible paths, expired credentials, cancellation and a changed active-file snapshot. Bind collection jobs to configuration and source revisions. Require explicit target/root approval after config import.

## Version 2 gate

Only Administrator manages secrets, host-key/target approval, connection/path test and parser/configuration actions. Inspector can initiate normal collection of already approved sources and see safe access diagnostics, never arbitrary host/path test payloads. Enforce approval/revocation at dispatch; never give either role target-write capabilities.

## Version 3 gate

Scope SSH pools, routing, credentials/trust and target approvals by project/owner/config revision. Equal addresses/log paths in two systems must not share approval or source identity accidentally. Keep physical raw capture reuse separate from mutable per-workspace filters and test only authorized synthetic target/jump hosts.

## Completion gate

A real AsyncSSH connection through a test jump host downloads the approved synthetic historical logs and produces the same indexed results as Stage 03. Wrong/unknown keys fail before credentials are sent where supported by the handshake contract. No remote file mutation or exec channel is used. Record tested server capabilities and actual test output. Stop before live following.

Acceptance targets: AT24, AT25, AT26, AT27, AT28, AT29, AT46. Run the tests that actually exist or implement the missing tests for this scope. Do not interpret an acceptance-test name as proof of a passing test. Update progress/STATUS.md with exact commands, results, blocked checks and the next stage.
