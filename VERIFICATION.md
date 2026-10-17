# Version 3 package verification

**Prepared and checked: 17 October 2026. Scope: specification, reference assets, synthetic fixtures, schemas and package-only helper/template code.**

This package does not implement the application. Its **120 package unit tests** are different from its **120 future application acceptance targets**. The equal counts are coincidental; none of those application targets is claimed complete by these checks.

## Environment

Python **3.13.5**, Linux x86_64 (glibc 2.41); `jsonschema` **4.26.0**, `PyYAML` **6.0.3**, POSIX permissions and bash. Docker and Podman executables were unavailable. No application dependency/image build, Ansible installation, database deployment or external host access was performed.

## Checks actually executed

| Check | Result and exact scope |
|---|---|
| `python -m unittest discover -s tests/package -v` | **PASS: 120 test methods**, comprising the retained 72 package tests and 48 new v3 tests; no skips or failures. The v2 policy expectation was updated for added actions, not replaced by an application authorization claim. [Captured output](verification/package-unit-tests.log). |
| `python tools/validate_schemas.py` | **PASS: 18 schemas**, **102 successful instance validations**, **36 invalid instances rejected**, and 15 YAML files parsed. Project/deployment YAML and JSON are equivalent, including both complete example systems. [Captured output](verification/schema-validation.log). |
| `python tools/validate_package.py` | **PASS:** JSON parsing and local Markdown links; complete **56-requirement / 120-target / nine-stage** mapping; 21 original fixture source objects, 38 expected events and 17 fixed query cases. Source bytes, offsets, identities and hashes match the original oracle. [Captured output](verification/package-consistency.log). |
| Multi-system sample contracts | **PASS within the 48 new tests:** deliberately repeated IDs/addresses in two systems; composite event/cache identity; pure scope/ownership checks; workspace/frame/preview binding rejection; sample detach isolation; nominal capacity reservation arithmetic allowing two windows of five sources; rejection without mutating existing reservations; legacy-limit defaults. These are synthetic oracles, not concurrency, browser, API or SQL tests. |
| Inventory sample reader and reconciliation | **PASS within the 48 new tests:** direct INI/extensionless files, static YAML, canonical JSON and bounded ZIP companion-vars samples; host-only import examples; nested groups; redaction and unsupported/unsafe-input diagnostics; same-system/source matching, repeated import and preservation of other-system/manual sample fields. The packaged inventory ZIP matches its example directory. `tools/inventory_fixture_reader.py` is a limited sample reader, not the production importer or complete Ansible semantics. |
| `python tools/validate_deployment_examples.py` | **PASS: 44 static policy/consistency checks** on two Compose documents and their limited local map merge. No Compose CLI interpolation, optional official Compose-schema validation, image execution or MariaDB SQL was performed. [Captured output](verification/deployment-static-checks.log). |
| Source/helper checks | **PASS:** all **12 Python source files** parse with Python's AST parser; the one shell initialization helper passes `bash -n`. Retained unit tests also check the helper's non-executable mode and capture its generated SQL through a local mock of the official image helper. This is not execution against the actual image or database. [Captured output](verification/assets-and-source-checks.log). |
| Preserved fixtures | **PASS:** all **34 original fixture files** are byte-identical to the extracted v2 package. The new multi-system collision fixtures are additional synthetic contract data, not replacements for the original physical-byte log oracle. [Captured output](verification/assets-and-source-checks.log). |
| Supplied theme images | **PASS:** both packaged light/dark PNGs are byte-identical to the user's reference files. Neither image was generated, resized or edited. Their hashes/sizes also match [reference-manifest.json](assets/themes/reference-manifest.json). [Captured output](verification/assets-and-source-checks.log). |
| Retained v2 behaviour | **PASS within the package tests:** theme-token contrast arithmetic, preference/policy examples, ownership examples, v1 project conversion, deployment invariants and no-overwrite local secret generation. These do not establish rendered accessibility, production authorization or real database account grants. |

The captured consistency log intentionally used the non-handoff command before the final manifest was regenerated, so its `package_file_hashes_verified` field is zero. Handoff hashes are a separate check performed after all delivered file contents are final.

## Not executed; required during implementation

No real application authentication, HTTP handler, WebSocket endpoint, import-upload/commit workflow, browser UI, persistent client store or live-session control lease was exercised. In particular, **two browser pages using the same account/origin were not tested against a running application**. Tests in document 09 require a real shared Playwright BrowserContext plus the manual two-window workflow. A pure function accepting a project/workspace ID is not proof that production code derives and validates it correctly.

No real MariaDB instance, migrations, composite foreign keys, transaction isolation, account grants, TLS connection, backup/restore or live data upgrade was run. No Docker/Podman image, Compose command or Ubuntu/Rocky offline startup was run. The application image and bootstrap/migration CLIs referenced in deployment examples remain implementation work; image pins must be selected and tested before release.

No SSH/SFTP transport, monitored host, remote credentials, log rotation/reconnection, real concurrent capacity reservation, slow-client replay or measured 16 GB two-system workload was exercised. There was no production inventory import and no Ansible/plugin/script execution. Dynamic inventories, Vault, templating and full Ansible precedence are not claimed as capabilities of the package-only sample reader.

Actual production tests, migration rehearsals against authorized disposable copies, project/workspace isolation across every repository/cache/API layer, both themes, real target access and offline deployment remain explicit Codex stage/release gates. Do not convert an unexecuted target into a passing result because a specification, template or similarly named package test exists.

## Handoff and recheck

**Archive verification:** the assembled candidate ZIP passed its CRC check, was independently extracted, and passed all four checks again, including all 120 package tests and all 166 manifest-listed file hashes. The final ZIP was regenerated after recording this result and is subject to the same independent extraction/recheck before delivery. There are 167 delivered files including the manifest.

`PACKAGE_MANIFEST.json` records every delivered file other than itself with size and SHA-256. The external `.sha256` records the complete ZIP hash. Run the four commands above after receipt, and run `python tools/validate_package.py --verify-handoff` **before editing** to verify delivered bytes.

After Codex changes source/specifications/progress, the original handoff hashes are expected to differ. Continue ordinary package checks and actual stage tests; do not overwrite evidence to disguise edits.
