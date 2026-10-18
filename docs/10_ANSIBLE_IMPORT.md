# 10 — Import Ansible inventory files into system setup

## Stage 07 implementation and operator workflow

The application now provides **Import Ansible inventory files** on the selected
System's topology page for Administrators. Choose a persistent inventory source,
upload a direct file or companion ZIP, select its format/source entries, parse,
map and review before committing. The wizard displays the target system ID and
expected revision throughout. Inspectors cannot invoke any importer endpoint.
The actual routes and request/response fields are documented in
`docs/05_API_AND_WEBSOCKET.md`; OpenAPI is generated from the implemented models.
This describes Stage 07 source and synthetic verification, not an installed
upgrade or an offline production release.

Direct INI (including extensionless `hosts`), static YAML/YML, canonical JSON and
ZIP companions are implemented without Ansible. ZIP sources are processed in
the explicitly selected order; inventory-relative variable files use
lexicographic order. Only supported uploaded files can contribute values.
Duplicate keys, group cycles, unsafe archive members, executable/plugin input,
Vault, YAML tags/anchors/aliases, unsupported ranges/complex INI literals and
required templating produce sanitized diagnostics. Unsupported ZIP extras are
listed as ignored; explicitly selecting an unsupported source fails.

Effective defaults/hard bounds are 10 MiB uploaded bytes, 20 MiB expanded data,
200 archive entries, path depth 8, tree depth 32, 100,000 parse nodes and
64 KiB per line/field. `limits.inventory_upload_bytes`,
`limits.inventory_expanded_bytes` and `limits.inventory_file_limit` preserve
explicit lower deployment ceilings. The upload ceiling also respects
`limits.config_upload_bytes`; higher configured values do not raise parser hard
bounds. API host/group/process counts are bounded by 5,000 and the complete
topology remains subject to its 5,000-total-entity limit. Streaming has a
30-second limit, parsing a 10-second budget, and CPU work uses two bounded
workers. There are two upload slots, ten pending uploads per account and at
most 100 named inventory sources per system.

An explicit host mapping overrides group mapping. Mapping a new subsystem ID
creates an empty subsystem named with that ID; rename/document it through normal
topology editing. An unambiguous `inspector_subsystem` is a proposal when no
explicit mapping is present. Accepted tag-only groups become tags while manual
tags survive. Missing `ansible_user` produces an unresolved-account warning and
placeholder, not a usable imported account. Credential mappings require existing
project bindings; jump profiles and parsers must already exist in this system.
No process is invented for host-only inventories, and missing parsers remain
unassigned until mapped. Log-source schema/path validation applies to optional
processes; proposed roots derive from their literal path prefixes, including
directory patterns. No credential, root, target or host key is approved here.

Reimport uses the selected source and stable host alias/local process ID.
Changing a filename does not change identity, and a distinct source never adopts
an unrelated object at the proposed ID. Address changes can update the imported
profile while retaining documentation, layouts, flows and unrelated processes.
Tag changes appear in the exact preview. Missing hosts/processes are reported as
absent and retained. Manual edits to imported managed fields block commit with
`MANUAL_EDIT`; there is no force-overwrite switch. Resolve the affected
configuration/input or supported subsystem mapping and obtain a fresh preview.
Only subsystem-value ambiguity can be resolved by an explicit subsystem mapping;
other static-variable conflicts require corrected input or trusted canonical
JSON. Structural moves must still satisfy the normal view-ancestor constraints;
the importer does not invent or rearrange diagram geometry. A content-identical
reimport leaves the topology revision unchanged.

Raw uploads use generated filenames under restricted
`deployment.state_dir/inventory-staging` (Linux directory mode 0700, file mode
0600). MariaDB holds sanitized summaries, normalized previews, digests and field
baselines. Staging expires 15 minutes after upload; commit or upload/wizard cancel
removes its raw file, and a 30-second reaper removes expired files/rows. Cancelling
only a preview retains the bound upload for Back/remapping. Startup also removes
orphaned incomplete files. Cancellation is allowed after system archival.
Long streaming/parsing releases database/account locks and rechecks the current
login, authorization, project revision and upload ownership before accepting a
result. Project/upload-scoped parser callbacks also stop work on HTTP/task
cancellation, upload cancellation or expiry while retaining the worker reservation
until exit. Commit checks the raw digest and stored bindings before one MariaDB
transaction updates configuration, mappings and revision.

## Required workflow and scope

**Import Ansible inventory files** is a required Administrator action on a selected System, not merely an external conversion recommendation. Both single-file static INI/YAML and uploaded companion-file bundles must work with no Ansible installation on the application server. Canonical JSON is an additional compatibility path for complex inventories.

The wizard is: choose/create a target System → choose a new or existing inventory-source identity → upload files/bundle → select source files/format → parse safely → map groups/hosts/optional processes → review warnings and exact changes → revision-bound atomic commit. Display the target system name/ID and expected revision on every screen and confirmation. Inspectors cannot upload, preview, map, commit or invoke configuration import through forged endpoints. The process requires no target SSH until a separate approved access test/collection.

## Inputs and boundaries

| Input | Required support |
|---|---|
| Static INI | `[group]`, `[group:children]`, `[group:vars]`, ungrouped host lines, comments, quoted scalar key=value; `.ini`, extensionless `hosts` or equivalent |
| Static YAML/YML | `all`, top-level groups, nested `children`, `hosts`, literal host/group vars, supported structured inspector extensions |
| Inventory ZIP | Explicitly chosen static inventory source files plus inventory-relative `group_vars/` and `host_vars/` YAML/JSON/extensionless variable files |
| Canonical JSON | Host-expanded `ansible-inventory --list` with `_meta.hostvars`, group `hosts`, `children` and `vars`; no command execution in the app |

Ansible supports INI/YAML inventory and separate host/group variables; its complete precedence/plugin behaviour is broader than this non-executing importer [S14]. This package intentionally supports a documented safe subset. It must accept the supplied ordinary examples directly, not silently degrade everything to “convert to JSON.” Unsupported dynamic scripts/plugin configs, host ranges, complex INI Python literals, unresolved required Jinja/lookups, Vault data, custom vars plugins or ambiguous precedence require a specific diagnostic and external resolution. No Ansible binary, playbook run, inventory plugin, uploaded Python, shell call, network lookup or remote include is executed.

Do not run `ansible-inventory` against an untrusted upload even in a subprocess. For complex **trusted** inventories, an Administrator may resolve them in their existing Ansible environment, inspect the output for secrets and upload canonical JSON. A documented example command is `ansible-inventory -i ./trusted-inventory --list > inventory.resolved.json`. Use normal `--list`; Ansible documents that `--export` optimizes export rather than exactly representing processed inventory, so do not add that flag here [S14]. Do not add `--yaml` to the JSON workflow. This is outside application runtime, not an importer implementation.

## File/bundle handling

Upload single files through the browser. For companion vars, upload a ZIP preserving inventory-relative paths; folder/multi-file selection may be offered additionally only when those paths are retained. Show all selected/ignored file names and counts. The browser never sends an arbitrary server filesystem path for the backend to read. A filename or suffix alone is not proof of type; validate the content and allow explicit INI/YAML/JSON selection on ambiguity.

The user selects the static source entries inside a ZIP; multiple sources are read in that explicit order and shown in the provenance. Variable companions are loaded only from the same uploaded inventory root. `ansible.cfg`, playbooks, `.git`, roles, scripts and other files are never executed or followed. Unsupported extra files may be ignored with explicit names/counts; reject an explicitly selected unsupported source. Plain-text inventories have no access to unuploaded `host_vars`/`group_vars`; show that companions were not supplied rather than read the application host's directories.

Validate all members before committing anything. Reject absolute paths, traversal, links/hardlinks, special files, duplicate/normalization-colliding member paths, encrypted archives and nested archive recursion. Stream only bounded regular members, without general extraction. Defaults: 10 MiB upload, 20 MiB expanded inventory data, 200 files, depth ≤8, bounded parse nodes and line/field sizes. Enforce actual bytes, timeouts and cancellation, not archive headers alone. Host/group counts also respect configured import limits. Do not echo source contents in parser exceptions. Use safe YAML with duplicate-key checking; reject object/custom tags, anchors/aliases and recursive structures in this initial static subset. Reject `$ANSIBLE_VAULT`/`!vault` input with an explicit supported-format message; do not accept a Vault password in the UI.

## Static variable rules

Within the supported subset, resolve literal values from `all` → ancestor group → child group → host. Inventory-relative `group_vars/<group>` and `host_vars/<inventory_hostname>` supplement those corresponding entities. Supported companion extensions are `.yml`, `.yaml`, `.json` and none; directories of such variable files use explicit lexicographic order. No playbook-directory vars or custom merge/hash behaviour is inferred. Lists/maps such as `inspector_processes` replace a value as a unit; do not concatenate lists or invent deep-merge semantics.

Retain provenance of each relevant value and all groups; a host in multiple inventory groups remains one host. Groups must form a DAG, never cycles. Identical repeated declarations merge membership. Different values for the same relevant key from unrelated/sibling groups or repeated same-level declarations are conflicts; require operator resolution via explicit wizard mapping for supported fields, or canonical JSON. Do not pretend to implement Ansible's full alphabetical/group-priority semantics. An explicit `ansible_group_priority`, conflicting complex overrides, unsupported literal types or required templating triggers a documented unsupported/conflict outcome. Unknown non-sensitive vars may be omitted with a names/count summary; never silently omit a value required to build the requested connection/process definition.

INI host tokens are parsed lexically, not executed. Ports are validated integers. `:vars` lines contain one key/value each; values are not evaluated as Python. Complex `inspector_processes` is supported through YAML/canonical JSON or companion host-vars, not guessed from INI string literals. Standard `host:port` syntax may be supported only with unambiguous IPv4/DNS forms; direct IPv6 addresses are literal `ansible_host` with separate `ansible_port`. Reject ranges rather than connecting to a range expression.

## Mapping to the system model

`inventory_hostname` is the stable alias/import key, not necessarily a reachable address. Use literal `ansible_host` when given, otherwise the alias; `ansible_port` defaults to 22 and `ansible_user` can be mapped/defaulted explicitly. A non-SSH `ansible_connection` is unsupported for activation. `ansible_become` never enables sudo; show the dedicated read-account prerequisite. Recognize common password/key/become/token fields and omit their values recursively before storing preview summaries or error logs. Uploaded raw content is short-lived restricted staging only, never included in exported config/audit; delete it on commit/cancel/expiry.

Ansible groups are not automatically subsystems. Cross-cutting groups such as Linux/region/environment usually become tags. The wizard maps chosen groups or individual hosts to subsystems **in the selected system**. Each host must resolve to exactly one subsystem; list conflicting/unassigned hosts and block unresolved commit. A supplied `inspector_subsystem` can propose a subsystem, but cannot override explicit mappings silently. Preserve unselected groups as tags when accepted. Do not infer the top-level System from a group name: the operator already chose it.

Connection passwords and jump profiles are mapped from approved application entries. No imported `ansible_ssh_common_args`, `ansible_ssh_extra_args`, `ProxyCommand` or shell string is passed through. A simple ProxyJump hint may be displayed as untrusted metadata only, never executed/approved. Imported profiles start disabled/unapproved until project credential binding, target/root approval and independent host-key trust are complete. Approval in another system is not approval here.

## Process/log metadata extension

A normal inventory can contain only hosts. Import such a file successfully with **zero process definitions found**, and allow the Administrator to add processes afterwards. Never invent processes, log paths, ports or data-transfer relationships from group labels, installed package variables or roles.

Optional `inspector_processes` is an application-specific literal list of records: stable local `id`, distinct display `name`, optional `pcs_resource_name`, and `log_source` matching `project.schema.json` (`active_path`, rotated patterns, archive/member selectors, parser ID, encoding, symlink policy). The same configured executable instance must retain identity on reimport. All parser/connection/process/flow references resolve **inside the target system**. A missing parser can be mapped to a same-system parser in the wizard; absent definitions do not create an executable parser. Read the structured sample under `examples/ansible/`.

## Reconciliation and transactions

The application allocates a stable `inventory_source_id` per target system. Select it on repeat imports; a changed filename does not create a new source automatically, and two distinct inventories named `hosts` are not merged. A host mapping key is `(project_id, inventory_source_id, inventory_hostname)`. Optional process identity adds host alias plus extension `id`. Do not match by IP alone, including the common case of overlapping addresses in two environments.

Preview classifies added/unchanged/changed/conflicting/unassigned/omitted/absent records and proposed target IDs. Show field provenance and preserve existing documentation, manually changed values, view geometry, flows and unrelated process records by default. Imported structural changes require explicit acceptance. Missing hosts/processes are **not** deleted; report them and require separate lifecycle/edit action for removal. A subsequent manual edit to an imported field is a conflict to review, not permission for silent overwrite.

The server keeps a sanitized normalized preview, mapping hash, content/manifest digest, project ID/revision, source ID, actor/auth version and expiry. Resolve credentials through references without staging secret values in the preview. Changing files/mappings/project requires a new preview. Commit uses only the stored normalized data plus the precondition; no client-supplied replacement payload. Cross-project or another owner's preview lookup returns 404; stale revision/auth/mapping/content or expiry is rejected. One MariaDB transaction reconciles model rows, source mappings and revision, or leaves all unchanged. In-flight sessions retain their original source snapshot; accepted edits cannot retarget them. Inventory import never edits accounts, DB location, global settings or another system.

## Contract and test assets

See `contracts/inventory-import.schema.json`, `contracts/inventory-preview-binding.schema.json`, the direct-file examples, `examples/ansible/bundle/`, and its reproducible ZIP. `tools/inventory_fixture_reader.py` remains a bounded **package-only sample oracle**. The production parser is `backend/src/inspector/inventory_parser.py`; `inventory.py` implements staging, scope/authorization, reconciliation and commit. Unit tests cover the parser/reconciliation/bounds, MariaDB integration tests cover actual upload/commit and relational/permission boundaries, and browser tests exercise the mapping wizard. Exact executed commands/results belong in `progress/STATUS.md` and `verification/stage-7/`.

Test ordinary INI (including extensionless), YAML nested groups, host-only imports, canonical JSON, companion-file bundles, repeated same-source imports, different target systems with identical aliases, address changes, preserved manual fields, stale/cross-project preview commits, unsupported/dangerous inputs and all role checks. The importer must continue working when Internet access is blocked. See AT102–AT114.
