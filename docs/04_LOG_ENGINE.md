# 04 — Log-engine behavioural contract

This document is normative. It defines results, not just implementation suggestions. Use the same predicate, timestamp parser and event identity logic in historical, live, context, export and correlation workflows.

## 1. Physical records, timestamps and identity

One physical line is one event. Preserve original bytes and the newline convention in captured source data. `raw_line` omits the line terminator but otherwise preserves text. Source `byte_start` is inclusive and `byte_end` exclusive and includes the original terminator when one was present. Offsets are bytes, not Unicode character indices. A line number may be null when a range was read without its prefix; never fabricate an absolute line number.

Default timestamp parsing recognises a bounded ISO8601 prefix with full date/time, 0–6 fractional digits, and `Z` or `+00:00`. The unknown-offset form `-00:00` is not accepted as an assertion of UTC. A fixed-width prefix plus an explicit `strptime` format supports examples such as `2026-10-16 12:00:00,123`. Timestamp-free-zone formats are allowed only with configured `naive_timezone: UTC`. Reject nonzero offsets rather than silently treating them as UTC in this release. More than six fractional digits, impossible dates and leap-second strings are preserved but reported as unsupported/invalid; do not silently truncate precision.

Normalise valid times to six fractional digits with `Z` and integer microseconds. The query interval is **from inclusive, to exclusive: `from_us <= event_us < to_us`**. The UI states this convention. A convenience “whole second/minute” selection must transform its end explicitly and display the actual resulting interval.

Sort historical valid events by `(timestamp_us, process_id, source_revision_id, member_ordinal_or_minus_one, byte_start, event_id)`. Equal times are deterministic, not evidence of causality. Unknown timestamps are counted and accessible in a separate lane; they never enter a time-filtered result through an invented ingestion time.

An event ID derives from process ID, source revision/generation, archive member ordinal/name and byte range. Display names and message text are not identities. A source revision tracks a stable captured object or observed file generation; do not use file size alone, since active files grow. Multiple identical messages at different offsets remain separate events. Deduplicate only a repeated acquisition of the same proven source range. Similar text in an archive and active file is not enough proof of identity.

## 2. Exact filter semantics

The primary control is **Contains string**. Advanced controls expose `include[]`, `include_mode: any|all`, `exclude[]` and `case_sensitive`. V1 uses literal substrings only. `%`, `_`, `.`, `*`, `[`, quotes, backslashes, pipes and shell punctuation have no special meaning.

An event matches when all three conditions hold: its process/time scope matches; the inclusion predicate matches; no exclusion term matches. With no include terms, inclusion is true. Otherwise, include-mode `any` requires at least one included term, and `all` requires every included term. An exclusion match always rejects. Exact empty strings are ignored; meaningful leading/trailing whitespace is preserved. Limit to 20 include and 20 exclude terms, with 512 characters per term, and report a validation error beyond those limits.

Case-sensitive is the default. For case-insensitive mode apply Unicode casefold to raw text and terms with the same backend implementation; do not implement a different browser lowercasing approximation. Matching is against `raw_line`, including its original timestamp/text, **not against the UI-added process/host prefix**. To select a process, use the process selector.

Global and per-process filters are ANDed. Within each filter, use its own include mode. Changing a filter replaces a subscription's view predicate, increments `filter_version`, and refilters retained raw events without reconnecting SSH or erasing history. Messages from old filter versions must not append stale results after a reset. Historical and live APIs must return the same matching event IDs for the same captured records.

Filter settings do not restrict acquisition at the SSH shell. There is no `grep` command containing user input, no `eval`, and no user-supplied regular expression in V1. Changing a filter can only recover data that was captured and retained; mark scan/retention limits and offer a bounded historical refill when older data is required.

## 3. Historical collection

1. Freeze the project/source/parser configuration revision and selected process/time scope. Check credentials, approved host keys and allowed roots. Enumerate only the configured directories/patterns via SFTP. The UI previews planned sources, approximate transferred bytes, archive types and unresolved date coverage.
2. Treat archive names/mtime only as hints unless an Administrator explicitly defines and validates an authoritative naming convention. Do not skip unknown-date candidates and call the result complete. At the baseline size, a correctness-first bounded scan of all configured relevant candidates is acceptable. Enforce declared limits and ask for a narrower scope/explicit revised budget rather than silently omitting files.
3. Download immutable historical files/archives to generated local paths. Record remote stat before/after, bytes obtained and checksums. For an active file, pin a handle and a maximum observed length, collecting a snapshot up to that boundary. Appends after the boundary belong to another capture; changed/truncated sources are marked unstable and retried or reported partial.
4. Decode only validated regular archive members matching the process selectors. Parse streaming lines, index candidates, preserve original byte/member provenance and collect parse-error statistics. Do not stop at the first timestamp beyond `to` unless source ordering has been established; out-of-order physical records may still match.
5. Retain the collected unfiltered candidate bytes so filters/context can change. The investigation query selects rows by time/process and literal text. Context retrieval remains separate from match counts. On cancellation, commit a clearly partial manifest; temporary files are cleaned up safely.

Distinguish `complete_for_scanned_candidates`, `partial`, `unavailable` and `unknown_candidate_coverage`. A min/max observed timestamp is **not proof that no events are missing between those times**. The UI reports candidates scanned/skipped, byte ranges and failures. It must not show a continuous green time bar solely because first/last timestamps bracket the requested interval.

Results of 10–20 MB do not imply archives of 10–20 MB. Preview source sizes, expose cache reuse and enforce budgets. Archive parsing occurs on the application server, not on the operator's browser and not by installing tools on target hosts. This is the functional equivalent of searching unpacked logs without unsafe remote shell interpolation.

## 4. Archive policy

Supported initial archive types: ZIP (stored/deflate members), TAR.GZ (regular file members) and rotated plain files. Unsupported compression methods, encrypted/password-protected archives, nested archives, duplicate/ambiguous members and corrupt checksums require explicit diagnostic outcomes. Duplicate names can be supported safely by member ordinal; never silently select the last duplicate.

Do not call a general-purpose extraction operation on untrusted archives. Stream members with `ZipFile.open` or `TarFile.extractfile` only after validating member type and name. Reject absolute paths, `..`, backslash traversal, drive prefixes, NUL characters, symbolic/hard links, devices, FIFOs and sparse metadata requiring unsupported handling. Directory entries may be ignored after safe validation. Archives supplied in this package's rejection fixtures contain only harmless marker text and must never be extracted into a working directory.

Enforce both declared and actual limits: member count, total expanded bytes, member bytes, decompression ratio, CPU/wall deadline and maximum line bytes. Do not trust archive header sizes alone. Read in bounded chunks and check cancellation. Initial deployment caps are defined in the example deployment policy; project preferences cannot raise administrator caps. Python's documentation documents archive extraction and decompression hazards; secure behaviour is an application obligation, not a promise supplied by a file extension [S07, S08].

## 5. Live source acquisition

Use read-only SFTP polling, initially every 750 ms per active source, with a 500 ms merge/display buffer and small nonblocking batches. This is agentless and does not require an interactive shell. Reuse host connections for several processes. The 1–2 second target applies to complete lines under healthy baseline conditions; poll/transfer/backlog delays are exposed.

Open a read handle, capture size and file attributes, and track a generation ID, offset, decoder state and bounded fingerprints of the file beginning and overlap near the cursor. Poll for appended complete lines. Keep bytes after the last newline as pending state; a later append may complete them. At historical EOF a final non-newline line is permitted and flagged. In live mode do not publish a partial line as complete merely because one poll ended.

SFTP metadata does not universally expose a reliable inode or change counter. Do **not** pretend that `size + mtime` gives exactly-once delivery. Compare the pinned handle and currently named file, inspect configured plain rotations where useful and detect shrink/fingerprint changes. On observed rename rotation, drain the old handle within a deadline and open the new path as a new generation. On detected copytruncate/rewrite, reset the generation, report a gap/uncertain overlap and resume. If identity cannot be proved, prefer a visible continuity warning over silent deduplication.

Truncation followed by regrowth between polls can be inherently unobservable through some metadata/fingerprint combinations. Retained/deleted rotations and the producer's rotation policy bound what the application can recover. Warn about this limitation; do not advertise lossless monitoring. A source-status panel should explain current uncertainty and the evidence behind any attempted recovery.

On transport failure, keep committed cursors/retained data, reconnect with exponential backoff plus jitter capped at 15 seconds, and attempt only proven offset recovery. Surface the disconnect interval even when backfill succeeds. Unknown/changed host keys, bad credentials and permission denial are non-retryable until an Administrator corrects the configuration/trust/credential issue. No log events is not a retry trigger by itself.

## 6. Viewport-aware initial history

The browser measures usable log-body height and line height, subtracting headers/toolbars. Default unwrapped rows use `ceil(body_height / row_height)` as requested seed rows, clamped to 1–500. Wrapped mode measures rows separately and may request incremental top-ups. The server still caps requests.

Pin a live source boundary `S` and begin buffering new bytes from that boundary while a bounded backward scan finds recent **matching** complete lines before `S`. Use chunked byte reads and handle a split first line. If `S` ends inside a line, preserve that line's starting offset and partial bytes; after completion emit it once. Resolve seed/live overlap by source identity and byte range, not timestamp/text.

Separate-pane mode requests enough matches for each pane. Merged mode obtains bounded recent candidates per selected source, merges deterministically and selects the newest requested number overall. Historical seed is displayed immediately; the small reorder wait applies only to new arrivals. The unfiltered scanned slice is retained within the raw buffer budget for refilter/context.

Stop seed scanning when the requested number is found or a byte/line/time limit is hit. If fewer matches exist in scanned data, show the scanned coverage and `seed_limit_reached`/`source_exhausted` status. Offer Load older; do not scan unlimited archives automatically to fill a window. Resizing may fetch additional retained/backfill rows but must not restart a collector.

## 7. Merge, resume and backpressure

All event timestamps are UTC but messages can arrive out of order. Hold newly received complete events for at most 500 ms of monotonic receipt time, sort available batches and publish. Never wait forever for an idle process to advance a watermark. A late event is marked and inserted into the chronological result with stable scroll anchoring; receipt/sequence order remains available. Stable tie-breaks match historical queries.

Transport `seq` is a monotonically increasing per-session delivery sequence, not an event timestamp. Keep a bounded replay window. The client reconnects with the last acknowledged sequence and filter version; replay only compatible retained frames. Otherwise send a `resync_required` status and a fresh retained snapshot, with explicit lost coverage if any. Backend restart invalidates ephemeral replay state and is visible.

Bound backend raw buffers, per-client queues and rendered/client caches. Default raw limits per process: 20,000 events **or** 32 MiB, whichever is reached first. Eviction advances a documented retention boundary. Slow clients receive a reset/gap notice instead of causing unlimited memory growth. Do not let an unconsumed WebSocket queue block remote acquisition indefinitely. Recording, when enabled, persists before publication as required for its durability contract; transient sessions do not claim durable capture.

Pause freezes rendering, not collection. Resume shows the retained backlog/current position with a count of evicted events. Stop cancels subscriptions/collectors according to reference counts. After the last client disconnects, keep a five-minute reconnect lease by default, then stop non-recorded sessions; recorded sessions have an explicit configurable lifetime. No forever-running orphaned SSH tasks.

## 8. Context, correlation, notes and bundles

Context is source-local before/after by physical order, not just neighbouring timestamps in the merged view. It may include unmatched or out-of-range lines; mark them, preserve provenance and exclude them from match totals. Read missing context only within configured roots/retention and with visible collection status.

Correlation markers are bounded literal prefixes/terminators, not executable parser code. A selected text value can also be used directly as a literal cross-process filter. Distinguish exact extracted-field matching from substring searching. Show a chronological trace and observed deltas, flag inversions and avoid claiming a data-flow edge proves the relation.

Annotations never mutate original bytes. A bundle manifest includes version, file sizes/checksums, event/source identity mapping, included coverage, topology/name snapshots, saved filters/layout, notes and redaction metadata. Redaction affects exported copies only and must apply consistently to raw lines, context, filenames, source labels, notes and topology descriptions. Show a preview and residual-risk warning: no automatic redactor can guarantee it identifies every sensitive value. Exclude credentials, session data, host-key trust, private keys and active connection configuration regardless of redaction settings. Import validates sizes/checksums/member safety and opens an offline investigation only.


## Version 3 project and workspace context

Every engine input has an explicit authorized `project_id`; there is no global active project. Historical queries additionally resolve an owned investigation, and live operations resolve owner + workspace + session. Never pass a process list from a second project into the same merged query or live session. Existing event IDs can repeat across projects; use `(project_id,event_id)` as identity everywhere, including React keys, cursor sort context, deduplication, context lookup and bookmark targets. Preserve original fixture event IDs.

Storage/cache/cursor/replay and source-discovery keys include project plus source/configuration revision. A matching path/checksum/hostname in another project is not a cache hit or authorization. Raw source bytes are stored in per-project generated namespaces initially. Validate all source/investigation joins against project membership before reading bytes. Filter semantics remain unchanged, but filters are attached to a live session owned by one workspace, never to a mutable process-wide global collector.

Provide independent raw-retained/refiltered views for two windows, even when both monitor the same configured process. Reference-count raw capture; stop/close/filter in one cannot affect the other's collector subscription. Detached lease expiry releases only that workspace's sessions. Background tab timers do not control remote polling. Apply fair bounded scheduling and the two-window ten-process aggregate budget in document 16, without bypassing original memory/archive/backpressure limits. Measure two × five low-rate sources, including one delayed client; do not claim old five-source measurements prove this requirement.
