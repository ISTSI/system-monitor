# Stage 00 — Verify contracts and environment

Read AGENTS.md and the relevant references below. Implement this stage only unless a higher-level user prompt explicitly authorises another stage.

## References

- `README.md`
- `docs/01_PRODUCT_REQUIREMENTS.md`
- `docs/02_ARCHITECTURE.md`
- `docs/08_IMPLEMENTATION_PLAN.md`
- `docs/09_ACCEPTANCE_TESTS.md`

## Task

Read AGENTS.md, README.md and the numbered requirements. Inspect the actual repository and available tools. Run the package checks and independent JSON Schema validation. Resolve compatible supported dependencies and toolchains on the approved connected build environment; record real versions, license information and lockfiles as the foundation is created. Confirm how tests/builds will run. Identify genuine contradictions, not questions already answered by the user.

Produce a repository implementation plan aligned to stages 01–08, an initial toolchain record, a risk/assumption list and an acceptance-test map. Preserve the dedicated direct-read account, English/configurable branding and offline-runtime defaults. Do not connect to synthetic example IPs, production systems or external accounts. Do not rewrite supplied expected results simply to fit an implementation.

## Version 2 gate

Read the v2 change/upgrade documents and compare both supplied themes. Verify MariaDB/Docker availability, deployment schemas/templates, role matrix and palette contracts. Record selected image digest and dependency evidence, not an invented lock. Do not overwrite existing implementation progress when this is an upgrade.

## Version 3 gate

Inventory the current contracts/version dimensions and scope changes. Read documents 10, 16 and 17, both system examples, scope policy and inventory files. Resolve no questions already settled in the user requirements. Plan explicit project scopes before exposing a second system.

## Completion gate

Package checks pass or a precise, justified package defect is reported. No invented lockfiles or claims of runtime testing. Update progress/STATUS.md and progress/DECISIONS.md. When this stage was launched through CODEX_START_PROMPT.md, proceed only to the separately authorised Stage 01; otherwise stop.

Acceptance targets: AT01. Run the tests that actually exist or implement the missing tests for this scope. Do not interpret an acceptance-test name as proof of a passing test. Update progress/STATUS.md with exact commands, results, blocked checks and the next stage.
