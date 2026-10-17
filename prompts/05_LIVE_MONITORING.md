# Stage 05 — Implement live capture and literal filters

Read AGENTS.md and the relevant references below. Implement this stage only unless a higher-level user prompt explicitly authorises another stage.

## References

- `docs/04_LOG_ENGINE.md`
- `docs/05_API_AND_WEBSOCKET.md`
- `docs/06_UI_UX.md`
- `docs/07_SECURITY.md`
- `fixtures/live-scenarios.json`

## Task

Implement supervised SFTP polling with source cursors, pending UTF-8/partial lines, generation/continuity tracking, bounded raw buffers and authenticated WebSocket delivery. Implement viewport-sized matching history, merged/split panes, live include/exclude filters, per-process overrides, pause/resume/stop and recording into an investigation.

Apply the exact engine semantics for seeding at boundary S, append races, filter-version resets, late arrivals, equal timestamps, replay/expired cursors, slow clients and interrupted backends. Handle observed rename/copytruncate and surface uncertain continuity rather than claiming lossless capture. Reuse collectors safely across tabs. Add automated real SFTP integration and browser scenarios, including five simultaneous sources and an idle source.

## Version 2 gate

Test both roles with separate owned sessions, per-user/global budgets, stop/cancel administrative exception and content-read denial. Revalidate auth_version before protected dispatch with a <=2-second silent-connection watchdog; fail closed on DB loss. Verify theme changes and Inspector preference updates do not reconnect, reset or reorder a live stream. No automatic resumption of collection after loss of database supervisor ownership.

## Version 3 gate

Implement the full per-page workspace/control lease model in document 16. Test two pages in the same browser context/account/origin, both different-system and same-system monitoring. Cover independent filters/stop/close, duplicate/reload without automatic SSH, explicit resume, late old frames, background/slow clients, global logout and two × five source capacity. Use WebSocket protocol 2 and typed scope envelopes.

## Completion gate

All live scenarios and security checks pass. Demonstrate changing/clearing a literal filter without an SSH reconnect, enough matching initial rows for two pane heights, preserving duplicate text, pause with ongoing receipt, visible retention eviction and disconnected-source recovery. Measure healthy p95 line-to-display delay at five low-rate sources; target ≤2 seconds. Stop before additional investigation tooling.

Acceptance targets: AT30, AT31, AT32, AT33, AT34, AT35, AT36, AT37, AT38, AT39, AT40, AT41, AT47, AT68, AT74, AT83, AT90, AT92, AT96, AT97, AT98, AT99, AT100. Run the tests that actually exist or implement the missing tests for this scope. Do not interpret an acceptance-test name as proof of a passing test. Update progress/STATUS.md with exact commands, results, blocked checks and the next stage.
