# Package verification tools — version 3

These are specification consistency, independent semantic-oracle and template tests. They are **not** the implemented application, production authorization, a database adapter, a rendered UI or an SSH client.

From the package root, using Python 3.11 or newer (the planned app toolchain is Python 3.13):

```sh
python -m unittest discover -s tests/package -v
python tools/validate_package.py
python tools/validate_schemas.py
python tools/validate_deployment_examples.py
```

The original unit/oracle checks use the standard library; the new inventory sample-reader checks also require locally installed PyYAML and report skips when unavailable. The other new scope/budget oracles are standard-library only. POSIX permission/initialization-helper tests require a POSIX host and bash; Windows reports those tests skipped, not passed. The schema and deployment-template commands require locally available `jsonschema` and `PyYAML`. Missing dependencies are reported; no command downloads packages, images or data. Tests create only temporary local synthetic files and invoke a **mock SQL capture function**, never MariaDB.

| Tool | Actual scope |
|---|---|
| `reference_contracts.py` | Original log/time/filter/source/provenance oracle |
| `reference_v2_contracts.py` | Pure theme resolution/opaque-colour contrast, role-policy examples, selected DB configuration invariants and v1 project conversion |
| `validate_package.py` | JSON, source hashes, golden query IDs, requirement/acceptance/stage mapping and local Markdown links |
| `validate_schemas.py` | All supplied JSON Schemas; positive and invalid payloads; equivalent YAML/JSON project/deployment examples |
| `validate_deployment_examples.py` | Static service/health/secret/network/configuration consistency; no Docker interpolation/runtime validation |
| `generate_load_fixture.py` | Bounded synthetic local log generation with no-overwrite policy |

`validate_deployment_examples.py --compose-schema /path/to/compose-spec.json` optionally accepts a locally supplied official Compose schema. It never fetches that schema. A passed optional structural check would still not be `docker compose config`, image boot, grant validation or a TLS/database test. See document 09 for those required implementation gates.

The colour tests cover opaque token combinations only. Actual shadows, gradients, alpha blending, disabled states and rendered keyboard focus must be tested in the implemented browser UI. Policy-oracle tests do not authenticate accounts, read trusted resource ownership or revoke real streams. Codex must independently implement those mechanisms rather than import these oracles as production code.

For a separate synthetic 20 MiB input:

```sh
python tools/generate_load_fixture.py --output-dir /tmp/inspector-load-fixture --size-mib 20 --processes 5
```

The generator refuses nonempty output directories and never deletes existing data. Generating files is not an application performance test.

Before modifying the package, run `python tools/validate_package.py --verify-handoff` to verify all delivered file hashes against `PACKAGE_MANIFEST.json`. Omit the flag after Codex edits source/spec/progress; it describes the handoff, not future application versions.


## Version 3 additions

`reference_v3_contracts.py` provides **pure sample oracles**, not authenticated services: composite keys, project-filtered rows, frame and preview binding checks, default-limit validation/reservation arithmetic, detach isolation and a non-mutating host-address reconciliation preview. Authoritative user/project/owner values are supplied by tests; these functions do not obtain trustworthy context themselves and must not be treated as production security.

`inventory_fixture_reader.py` reads the **supplied synthetic examples** conservatively: single static INI/YAML/canonical JSON and an in-memory bounded ZIP with selected companion data. It has no browser upload, full production-compatible static grammar, network/Ansible integration, file discovery, authorization, transaction, timeout supervisor or web preview UI. The production importer must implement document 10 and be tested separately; do not import these helpers into the application. The unit tests prove only the covered sample paths and negative cases, not compatibility with every Ansible inventory.

`tests/package/test_v3_contracts.py` checks independent synthetic project/frame/preview/limit/reconciliation semantics and direct-file/companion-data examples. Real two-window interaction, controller leases, cross-project foreign keys and concurrent database reservations remain **unrun** until the app exists. The original fixture tree is preserved, with new collision examples placed in a separate subdirectory.
