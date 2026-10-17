# Shared contracts — package version 3

All `*.schema.json` files use JSON Schema Draft 2020-12 with local self-contained definitions. They do not require Internet schema resolution. Structural checks are necessary but do not replace semantic validation, authentication, ownership, revisions, host approval or TLS/runtime tests.

| Contract | Purpose |
|---|---|
| `project.schema.json` | Current project format 2.0: topology, views, parsers, log-source/connection references; no credentials, user accounts, theme setting or database location |
| `project-v1.schema.json` | Preserved legacy format 1.0 accepted only through explicit Administrator import conversion |
| `event.schema.json` | Parsed event plus exact original-byte provenance |
| `filter.schema.json` | Exact literal include/exclude/any/all/case behaviour |
| `query.schema.json` | Selected processes, UTC interval and filter request |
| `live-request.schema.json` | Live source selection, filter and measured viewport history request |
| `deployment.schema.json` | Server bootstrap configuration including MariaDB location/secret-file/TLS/pool fields and policy ceilings |
| `theme-catalog.schema.json` | Two semantic palettes and unchanged reference-asset locations |
| `user-preference.schema.json` | Own appearance response with `revision` and `theme_mode` |
| `user-preference-update.schema.json` | Own appearance update with `expected_revision` and `theme_mode`, no mass assignment |
| `rbac-policy.schema.json` | Structure of the deny-by-default permission matrix in `rbac-policy.json` |

Examples use exact UTC timestamps; `received_at` is acquisition metadata, never a replacement time filter. `source.content_sha256` hashes original physical-line bytes including its terminator; manifest checksums describe whole file/member bytes separately. Golden query/event identities are unchanged from v1.

The HTTP inventory and authorization boundary are in document 05. Implement complete Pydantic/OpenAPI types and strict WebSocket/bundle/account schemas as the relevant stages land. The matrix, schemas and route table are not an existing API server or production authentication implementation. `acceptance-index.json` lists 120 future tests mapped to 56 requirements; it is not a result file.

Project format version, deployment format version, MariaDB Alembic schema revision and release version are separate concepts. User preferences and shared appearance defaults live in MariaDB, not imported project files. The v1 converter preserves IDs/content and reports removal of the obsolete project theme; actual SQLite data transfer is separately conditional on real legacy code/data.

The explicitly authorized temporary VM development path adds deployment topology `ssh_tunnel` within schema 2.0: literal loopback only, disabled database TLS and null CA. Ordinary `external` endpoints still require verified TLS. Bounded database/account identifiers can contain hyphens, and host-tooling files can use safe drive-qualified Windows paths with forward slashes. See [the transport boundary](../docs/14_MARIADB.md). These additions do not change project interchange or Linux production requirements.


## Version 3 added contracts

`system-catalog.schema.json` describes safe multi-system metadata; `workspace.schema.json` describes a server-owned page workspace. `inventory-import.schema.json`, `inventory-preview-binding.schema.json` and `inventory-commit.schema.json` bind file import to a selected project and stored preview. `scope-policy.json/.schema.json` adds system/owner/workspace isolation to the existing role matrix. `live-frame.schema.json` is a protocol-2 **server envelope**, with typed event batches; other payload variants need complete implementation validators. Its matching example is synthetic.

`live-request.schema.json` is now request version 2 and requires `workspace_id`. Project interchange stays 2.0, event schema 1.0 and historical query schema 1.0; scope is explicit in the route and existing `project_id` event field. Deployment schema stays 2.0 with optional v3 limit fields/defaults. Do not confuse package version with each independent wire/interchange contract version. All new schemas are self-contained, requiring no network resolution.
