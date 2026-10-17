# Stage 03 — Implement the historical engine against fixtures

Read AGENTS.md and the relevant references below. Implement this stage only unless a higher-level user prompt explicitly authorises another stage.

## References

- `docs/03_DOMAIN_AND_CONFIG.md`
- `docs/04_LOG_ENGINE.md`
- `docs/05_API_AND_WEBSOCKET.md`
- `docs/07_SECURITY.md`
- `fixtures/README.md`

## Task

Implement the production timestamp parser, literal filter predicate, source/event identity, safe archive reader, event index and historical query/context APIs against a local transport interface. Use exact integer UTC microseconds and [from,to). Keep malformed entries available in a diagnostic lane. Implement local-source planning, cancellable ingestion and a working virtualised historical viewer.

Integrate all synthetic plain, ZIP and TAR.GZ sources; reproduce every expected query/event/provenance result. Implement limits, corrupt/archive-path rejection, actual-byte counting, source ordering, context outside the filter and snapshot-bound pagination. Use fixtures as input to production services; do not import the package oracle as production business logic. Implement useful progress and partial-coverage output.

## Version 2 gate

Use MariaDB production repositories with exact BIGINT timestamps, large Unicode lines and deterministic nullable source ordering; reproduce literal semantics without SQL LIKE/FULLTEXT approximations. Every collection/query/context source must be bound to the caller-owned job/investigation. Both roles may investigate only approved configuration.

## Version 3 gate

Pass project context through query/source/cache/context/bookmark paths; full event/source identity is composite. Add real MariaDB project-paired foreign-key tests and forged cross-scope query/download/ID tests. Retain original golden fixtures and use collision fixtures to prove the same local ID is not a global identifier.

## Completion gate

Production code independently passes the golden query cases, duplicate-text, Unicode, literal punctuation, invalid time, archive/member and coverage tests. A historical investigation can be queried, filtered and inspected in the browser with real indexed results. Benchmark a generated 20 MiB input and record the machine/result. SSH remains a separate next stage.

Acceptance targets: AT13, AT14, AT15, AT16, AT17, AT18, AT19, AT20, AT21, AT22, AT23, AT44, AT45, AT73, AT94, AT95, AT115. Run the tests that actually exist or implement the missing tests for this scope. Do not interpret an acceptance-test name as proof of a passing test. Update progress/STATUS.md with exact commands, results, blocked checks and the next stage.
