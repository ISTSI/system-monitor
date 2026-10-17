# 08 — Staged implementation plan

The final scope includes every numbered requirement, including all accepted investigation suggestions. Stages are delivery gates, not excuses to leave later features unimplemented. Each stage should produce a working vertical slice and relevant tests.

| Stage | Deliverable | Primary acceptance targets |
|---|---|---|
| 00 | Verify contracts and environment | AT01 |
| 01 | Build the MariaDB, role-aware and themed web foundation | AT02, AT03, AT04, AT42, AT67, AT69, AT71, AT72, AT75, AT77, AT79, AT80, AT81, AT84, AT91 |
| 02 | Implement topology, documentation and configuration | AT05, AT06, AT07, AT08, AT09, AT10, AT11, AT12, AT43, AT78, AT86, AT89, AT93, AT101, AT117 |
| 03 | Implement the historical engine against fixtures | AT13, AT14, AT15, AT16, AT17, AT18, AT19, AT20, AT21, AT22, AT23, AT44, AT45, AT73, AT94, AT95, AT115 |
| 04 | Connect the real read-only SSH/SFTP collector | AT24, AT25, AT26, AT27, AT28, AT29, AT46 |
| 05 | Implement live capture and literal filters | AT30, AT31, AT32, AT33, AT34, AT35, AT36, AT37, AT38, AT39, AT40, AT41, AT47, AT68, AT74, AT83, AT90, AT92, AT96, AT97, AT98, AT99, AT100 |
| 06 | Complete the investigation workflow | AT48, AT49, AT50, AT51, AT52, AT53, AT54, AT76, AT118 |
| 07 | Finish safe Ansible import and UI acceptance | AT55, AT56, AT57, AT58, AT59, AT60, AT61, AT70, AT88, AT102, AT103, AT104, AT105, AT106, AT107, AT108, AT109, AT110, AT111, AT112, AT113, AT114, AT119 |
| 08 | Harden, verify and produce an offline release | AT62, AT63, AT64, AT65, AT66, AT82, AT85, AT87, AT116, AT120 |

## Working method

For a fresh repository begin with CODEX_START_PROMPT.md, which authorises Stage 00 then Stage 01. For already implemented v1/v2 code, use CODEX_UPGRADE_PROMPT.md instead and preserve real progress. Thereafter use the next numbered file in prompts/ as a separate Codex request. Preserve progress/STATUS.md so a new session can continue without relying on chat memory. Do not spend an entire stage producing only another plan when implementation is requested.

Before each stage, review its dependency gates and the relevant contracts. Implement domain logic with unit tests, wire it through real API services, then test the browser workflow. Keep presentation, transport, parsing and persistence separate enough to test independently. A mock transport is not evidence of SSH support, and generated deployment files are not evidence of offline operation.

Create real lockfiles and reproducible commands at the foundation stage. Choose compatible maintained dependencies, record selected versions and retain their licenses. No hand-invented hashes or copied paid example implementations. The final release transfers app, reverse-proxy and pinned MariaDB images. The app image bundles frontend assets and Python dependencies; no npm, pip, registry or CDN request is needed at runtime.

## Cross-stage quality gates

Require formatting/lint/type checks, relevant unit/API tests and fixture contract checks at every change. Every persistence stage uses a disposable real MariaDB instance, never SQLite as a substitute. UI stages add both-role/both-theme Playwright checks and visual inspection. All later features inherit backend authorization and ownership tests; foundation mocks are not later-stage evidence. SSH/live stages use a local, independently keyed jump/target environment. Release gates rerun every earlier suite, verify Internet-blocked operation and report measured resource/latency data. Unrun tests remain unrun in the report.

The baseline is deliberately modest; first implement bounded correct behaviour rather than adding distributed infrastructure. Do not add Redis, workers in multiple Uvicorn processes, an external search cluster or remote grep commands to avoid understanding the actual query semantics.

## Stage evidence template

Record: requirement IDs implemented; files changed; commands executed; tests passed/failed/skipped with reasons; screenshots where relevant; benchmark environment/results; security or compatibility limitations; and exactly which next stage is ready. A summary saying “all tests pass” without commands/scope is insufficient.


## Version 3 cross-cutting sequence

System scoping is part of the foundation/data/API design, not a final cosmetic selector. Implement the catalogue/workspace shell early, then carry project context through every later feature. Direct Ansible static upload already begins with project/config validation; Stage 07 completes its mapping/companion-file/commit UX and adversarial tests. The version-3 gates in every stage and AT91–AT120 are required in addition to the unchanged original tests. Document 17 defines an incremental existing-code path; never rewrite an established repository as a fresh project.
