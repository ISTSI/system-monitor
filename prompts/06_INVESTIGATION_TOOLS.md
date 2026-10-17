# Stage 06 — Complete the investigation workflow

Read AGENTS.md and the relevant references below. Implement this stage only unless a higher-level user prompt explicitly authorises another stage.

## References

- `docs/01_PRODUCT_REQUIREMENTS.md`
- `docs/03_DOMAIN_AND_CONFIG.md`
- `docs/04_LOG_ENGINE.md`
- `docs/05_API_AND_WEBSOCKET.md`
- `docs/07_SECURITY.md`

## Task

Implement saved workspaces, exact correlation-field and literal searches, chronological traces, bookmarks/annotations, pinned surrounding context, source provenance/coverage details and dependency-neighbour selection. Implement versioned investigation bundle export/import with redaction preview and checksums. All accepted investigation features are required for the final release.

Keep notes and redacted exports separate from original bytes. Ensure redaction reaches metadata, labels, filenames, notes, context and topology text, and exclude all credentials/trust/active connection profiles unconditionally. Import is offline and cannot enable hosts. Implement pin/cache expiry interactions, precise unavailable-data status, live-to-investigation save and replay after host disconnection. Add bundle schemas and generated API types alongside tests.

## Version 2 gate

Preserve all personal investigation functions for Inspector as well as Administrator. Enforce ownership for annotations, source cache access, bundle previews/download tickets and imported bundles. Administrator has no implicit private content read bypass; sanitized exchange is explicit. Test ID guessing across every content route.

## Version 3 gate

Saved investigations, notes, contexts, pins and sanitized bundles are owned and project-scoped. Loading/exporting an A object through B must fail even for the same user. An imported foreign bundle creates only private offline data in a selected context and retains origin provenance without enabling connections.

## Completion gate

An operator follows REQ-0042 through five processes, distinguishes REQ-00420 in exact correlation search, adds a note/context, saves the capture, exports a previewed redacted bundle and imports it offline with no connection attempts. Original cache remains unchanged. Corrupted or unsafe bundles are rejected before commit. Stop before inventory/UI completion.

Acceptance targets: AT48, AT49, AT50, AT51, AT52, AT53, AT54, AT76, AT118. Run the tests that actually exist or implement the missing tests for this scope. Do not interpret an acceptance-test name as proof of a passing test. Update progress/STATUS.md with exact commands, results, blocked checks and the next stage.
