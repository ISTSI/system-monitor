# Import one server and its services

Generate one UTF-8 JSON file per host, using
[server.example.json](server.example.json). The versioned contract is
[server-import.schema.json](../../contracts/server-import.schema.json).
The file describes configuration; it does not contain collected logs.

`format` must be `"system-inspector-server"` and `schema_version` must be
`"1.0"`. The top level contains exactly one `server` object and a `services`
array. Unknown fields and future versions are rejected. Do not wrap this format
in an Ansible inventory or a ZIP. Full project import/export remains version 2.0.

| Field | Required | Meaning |
|---|---|---|
| `server.id` | Yes | Permanent import key for this host within the selected inventory source. Keep it unchanged when the address, hostname or display name changes. |
| `server.address` | Yes | Literal DNS name or IP address used for SSH. No URL, user prefix or embedded port. |
| `server.name` | No | Display name; defaults to `server.id`. Maximum 256 characters. |
| `server.port` | No | Integer SSH port, 1–65535; defaults to 22. |
| `server.user` | No | Dedicated log-read SSH username. If omitted, the connection remains unresolved until configured separately. |
| `server.subsystem_id` | No | Existing subsystem ID, or a new ID to propose creating. If omitted, assign the host in the import wizard. A newly created subsystem initially uses its ID as its display name. |
| `services` | Yes | Configured service instances on this host. An empty array imports only the host. |
| `services[].id` | Yes | Permanent local service-instance key, unique within this host. Keep it unchanged through renames. |
| `services[].name` | Yes | Display name, unique among processes in the selected System, ignoring case. Prefix with the host name for common services. |
| `services[].pcs_resource_name` | No | Optional PCS resource label; omit or use `null` when unused. |
| `services[].log_source` | Yes | One logical plain-file log source, including any rotations/archives, as described below. |

All IDs start with an ASCII letter or digit and contain only ASCII letters,
digits, `_`, `.`, `:`, or `-`; maximum 128 characters. They are import keys,
not the generated internal topology IDs. A service ID may repeat on another
host. For templated unit names such as `worker@1.service`, generate a stable
allowed ID such as `worker-instance-1`; retain a mapping or use a collision-free
encoding. Do not use a PID, current IP, list index, timestamp or a new UUID on
every run. Use a JSON serializer so quotes, Unicode and backslashes are escaped
correctly. Names must be nonblank and contain no control characters.

Every `log_source` contains all six fields:

| Field | Meaning |
|---|---|
| `active_path` | Exact absolute Linux file path, e.g. `/var/log/orders-api/application.log`. No glob in this field. |
| `rotated_patterns` | Absolute Linux glob patterns for rotated plain files; use `[]` when unused. |
| `archives` | ZIP/TAR.GZ archive selectors, each containing an absolute `path_pattern` and nonempty `member_patterns` list. Use `[]` when unused. |
| `parser_id` | Parser reference; it must exist in the selected System or be mapped to an existing parser in the wizard. |
| `encoding` | Supported text encoding; normally `"utf-8"`. |
| `allow_symlink` | Boolean; normally `false`. |

Paths are literal configuration, with glob syntax only in pattern fields.
Traversal, shell expansion and unsafe paths are rejected. Archive member patterns
are relative paths inside the archive, not host paths. Set patterns to the actual
archive layout; the example's `application.log.*` matches files at archive root.
Rotation and archives belong to the same service, not separate service records.
The schema uses the existing project log-source contract; runtime path, encoding,
reference and uniqueness checks also apply.

`parser-iso-utc` in the example is a reference, not a built-in guarantee. Select
the parser that matches the service's actual timestamp format. This import does
not create parser definitions. A host/service-list dump alone cannot determine
application log paths or timestamp formats reliably. Include only service
instances for which you can supply a known plain-text file source. A service
logging exclusively to the systemd journal needs a separately configured supported
file source before it can be imported as a process. The app does not execute
the dump script or discover services on the host.

As an Administrator, open the target System's topology and choose **Import server
JSON**. A downloadable example is available in the wizard. Choose or create a
named inventory source, upload the file, parse, map its subsystem/parser, preview
the exact changes, then commit. You may reuse one source for all hosts produced
by the same exporter. Reuse that same source for later dumps; changing filenames
does not change identity. The selected System supplies `project_id`; do not put
a system ID or revision in this JSON.

Reimport reconciles by `(project_id, inventory_source_id, server.id,
services[].id)`. Renames and address changes retain existing internal identities.
Other servers and services missing from this file are reported as absent and
retained. Omission never means deletion. Documentation, diagrams, flows and
unrelated processes are preserved. Manual edits to importer-managed fields are
reported as conflicts; correct the input/configuration and obtain a new preview.
A content-identical reimport does not advance the topology revision. A stale
preview must be regenerated before commit.

Do not export passwords, private keys, tokens, connection commands or host-key
trust. Those fields are unsupported. Configure credentials, jump connections
and trust separately in the application. Import does not connect to the host or
approve it. Existing upload/parse/time/size limits and Administrator-only access
apply. The example uses a documentation-only IP address.
