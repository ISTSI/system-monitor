# 14 — MariaDB persistence, configuration and lifecycle

## Selected database architecture

MariaDB replaces SQLite everywhere in the operational application: topology/config revisions, accounts/roles/preferences, encrypted SSH credential records, session verifiers, jobs, investigations, event/provenance indexes and operational audit. Raw collected bytes remain in a managed filesystem cache. This is not a database-per-user design.

Use the free official MariaDB community image, with the 11.8 maintained series as the initial compatibility baseline. Resolve a security-patched exact maintenance tag/digest at build time and test it; do not assume the example series tag is immutable or the newest available release. Maintenance references and the official entrypoint/healthcheck sources are listed in S18. An existing configured MariaDB server is supported as an alternative to the managed container; it must meet the tested version/charset/TLS/privilege contract.

Use SQLAlchemy asyncio with `asyncmy` and Alembic. SQLAlchemy documents the `mysql+asyncmy` dialect for both MySQL and MariaDB; the prefix does not mean switching the product to MySQL [S19]. Construct connection URLs through `sqlalchemy.URL.create`, not string concatenation, so passwords containing reserved URL characters work. Do not log even a constructed full URL. Pin and test the Python 3.13/driver/SQLAlchemy combination and Alembic's asynchronous connection workflow [S26].

No SQLite runtime fallback, dual-write mode, FTS5, WAL tuning or SQLite-based API/migration tests. Pure parsing/filter unit tests need no database; persistence/integration tests require actual MariaDB. If an existing v1 application/data exists, its SQLite reader belongs only to an explicit offline migration tool, not the serving app.

## Configuration available before database access

The application must read a deployment YAML file selected by `INSPECTOR_CONFIG_FILE` (default `/etc/system-inspector/application.yaml`). Validate against `contracts/deployment.schema.json`, reject unknown fields and duplicate YAML keys, then apply a documented environment allowlist. No arbitrary `eval`, variable expansion or implicit fallback to another config file.

Required connection fields are shown in `examples/deployment-policy.example.yaml`: `database.engine`, `driver`, `topology`, `host`, `port`, `name`, `username`, `password_file`, `charset`, `collation`, `connect_timeout_seconds`, `startup_timeout_seconds`, `pool`, and `tls`. Missing/unreadable/empty secrets or invalid endpoint/port fail startup with safe field-level diagnostics. Reject NUL/control characters and traversal in mounted file paths. A password-file payload is a single UTF-8 value; strip at most one final line terminator, preserve other characters, reject embedded newlines/NUL. Never replace the actual value with an empty/default password after an error.

An optional environment allowlist overrides only explicitly set fields: `SI_DB_HOST`, `SI_DB_PORT`, `SI_DB_NAME`, `SI_DB_USERNAME`, `SI_DB_PASSWORD_FILE`. Empty supplied variables are invalid, not missing. Validate the complete resulting configuration again, and show safe value origins in an Administrator-only diagnostic. TLS/pool/host safety rules still apply after overrides. Do not support a plain `DB_PASSWORD` or arbitrary raw DSN in project configuration. The migration CLI may explicitly override username/password-file, loading its own secret rather than requiring the runtime secret to be mounted.

DB location is deployment configuration because it is needed before MariaDB is available. The Administrator can read a sanitized endpoint/version/readiness summary in Settings, but changing the bootstrap location or key path requires a protected server file/environment change and restart. Do not store the only copy of the database address inside that same database or offer a live browser DB-switch textbox. This infrastructure boundary does not limit the Administrator's ability to edit normal application/topology settings.

Project YAML/JSON and investigation bundles must not contain database settings, passwords, user hashes, roles, auth sessions or vault keys. `bootstrap_settings.default_theme_mode` initializes the persisted global setting on a new installation only; subsequent restarts must not overwrite an Administrator's saved default or per-user preferences. Deployment resource limits are ceilings; Administrator UI overrides can reduce them and adjust validated defaults, not silently exceed them.

The Stage 03 local fixture transport has a separate explicit deployment-only
opt-in, `SI_LOCAL_HISTORY_DEMO=1` (`0` is the default; other values fail startup).
It authorizes only the bundled synthetic fixture mapping through configured
process/path selectors. Browser requests and project imports cannot enable it
or choose a local path. It does not authorize SSH or production target access.

The SSH setup slice reads the existing `deployment.vault_key_file`: exactly 32
raw bytes in a regular, non-symlink file owned by the Linux service identity,
mode 0600 or 0400. SSH password ciphertext and nonces use MariaDB VARBINARY;
global vault rows require an explicit system credential-reference binding.
Password replacement is write-only and versioned, and invalidates pending checks.
Keep this key outside database/configuration exports and back it up separately.
Replacing the file does not re-encrypt existing records; automated key rotation
and a full vault-recovery/backup release workflow remain unimplemented.

Stage 04 migration `0007_source_access` stores explicit local target/root
approvals separately from imported configuration and host-key trust. They bind
the system, connection, complete configuration revision, route, root digest,
credential/trust versions and expiry. The default approval lifetime is 24 hours;
Administrators can choose 60 seconds through 30 days through the bounded API.
Configuration or access changes require approval again. A nullable vault
credential `expires_us` permits fail-closed credential expiry; existing passwords
retain their previous indefinite lifetime, and explicit replacement renews the
record. Neither approvals nor vault data enter project exports. Migration tools
remain separate from the serving application's restricted DML account.

The subsequent user-requested migration `0008_security_setting` adds the
non-null boolean `application_settings.additional_security_measures`, defaulting
to true for existing rows and new installations, with a 0/1 check constraint.
It preserves existing approvals and all project/account/preference data.
Administrator settings writes persist it with the existing revision/audit
transaction; restart does not overwrite it. This is deployment-wide application
policy, not a project field, workspace selector or interchange/export value.
When false, source dispatch skips only the separate manual target/root approval;
it neither writes approval records nor relaxes credentials, host keys or root
validation. When true, the current revision-bound approval/expiry rules above
apply. Guarded operations include this policy in their freshness checks so
changing it invalidates pending work.

Optional deployment scan ceilings preserve schema 2.0 compatibility:
`max_source_files_per_collection` defaults to 1,000,
`max_source_listing_entries` to 10,000, `max_source_listing_bytes` to 4,194,304
and `max_source_probe_bytes` to 33,554,432. Configured positive integer values
are preserved, including lower operator ceilings. These bound source candidates,
directory listings and snapshot/readability probes before downloads; actual
downloaded bytes retain the independent collection budget.

`SI_SSH_ALLOW_LOOPBACK=1` is a deployment-only exception for explicitly authorized
local SSH tests; `0` is the default and other values are rejected. It permits
loopback only, never link-local, metadata, multicast or unspecified destinations.
The browser and project imports cannot enable it. Normal LAN targets remain
subject to resolved-address validation and explicit host-key approval. Merely
starting the application, opening a system or saving a password starts no SSH.

## Managed and external connectivity

For the managed Docker stack, `host: mariadb`, port 3306, database `system_inspector`, and runtime user `inspector_app` are the reference values. `localhost` inside an application container is not the database container. The database has a private internal network, persistent named volume, healthcheck and no published port. The application additionally needs an egress-capable service network for its approved LAN/VPN SSH traffic; the DB does not. A private bridge is not encrypted: disabling DB TLS is an explicit managed-single-host exception, not an assertion of transport encryption.

For a separate/existing server, configure its actual DNS name/address and reachable port, provision accounts and use `tls.mode: verify_identity` with a mounted CA file. Build an SSL context with certificate and hostname checks required; test unknown CA, expiry and wrong hostname failures. No opportunistic downgrade to plaintext. The deployed MariaDB endpoint must itself be configured for TLS; setting a client field does not configure the server. Do not reuse the managed no-TLS example unmodified across LAN/VPN. No app-facing arbitrary-host database test API.

### Authorized temporary development tunnel — 17 October 2026

The user's existing local-VM replacement adds an explicit development-tooling
option, `database.topology: ssh_tunnel`, to deployment schema 2.0. It requires
the literal host `127.0.0.1` or `::1`, an explicitly configured forwarded port,
and `tls: {mode: disabled, ca_file: null}`. Select it deliberately; neither a
loopback address nor a VPN automatically downgrades `external` TLS requirements.
It represents an operator-managed SSH tunnel with a pinned SSH host key, not
the managed MariaDB container. The existing VPN and tunnel must remain running.
The application does not start, stop, discover or repair either connection.

SSH protects the connection to the tunnel's SSH endpoint. This exception does
not assert end-to-end MariaDB TLS or encryption on any forwarding segment after
that endpoint. Verified TLS remains required for ordinary external deployments;
this temporary path does not complete that deployment or release gate. Host-side
tools connect to the workstation's explicit loopback endpoint. A container or
another machine has a different localhost; tools must not guess or rewrite it.

Database and account names may also contain hyphens within their existing
bounded lowercase ASCII identifier syntax. Use `URL.create` for connections
and quote any database identifier in SQL. Existing schema defaults need not be
rewritten: migrations explicitly select the required binary table/column
collations. The supplied full-schema account is for explicit migrations and
scoped checks only. Serving still requires a separate restricted DML account;
do not remove integration-suite account or disposable-schema safeguards.

To support Windows host-side tooling, protected configuration accepts absolute
POSIX paths or drive-qualified Windows paths written with forward slashes,
such as `C:/project/.secrets/database-password`. It rejects UNC/device paths,
backslashes, drive-relative paths, traversal and control characters. Paths are
preserved without aliases or environment expansion. Production remains Linux
and uses POSIX paths; credentials remain in ignored, access-restricted files.

## Storage and query contract

Stage 05 revision `0009_live` adds `live_sessions` and `live_subscriptions`.
Composite foreign keys bind sessions to project revision, workspace/owner, and
optional recorded investigation/owner; subscriptions bind to the same session
owner and same-system process identity. The existing singleton security lock
serializes quota reservations across workspace/project/account/deployment scopes.
Moving a detached session checks the target workspace's remaining quota too.
Interrupted/stopped sessions retain metadata but consume no subscription slots.
Startup detaches pages, marks old monitors interrupted and clears reservations
without opening SSH. Collection deletion clears terminal recording links in the
same transaction before removing the owned investigation.

Background live validation and established-socket dispatch use fresh nonlocking
reads, including current login/account versions and workspace ownership/lease.
Each socket validation obtains the security singleton, login/account, scoped
monitor and workspace in one fresh joined read. Shared pure validators preserve
the same account, expiry, ownership and lease rules used by locked controls;
every protected frame and ACK performs its own check. Filter frames wait until
the committed database version and engine reset agree.
Selected source routes share one bounded transaction for project-scoped trust,
credential bindings and approvals; they use the same rules as individual source
checks. Only simultaneous unfinished validations may share work; completed
grants are never cached. Control mutations and quota reservations retain locks.
The bounded authorization/supervisor deadlines still fail closed.

Explicit recordings reuse `history_jobs`, `history_sources` and `history_events`.
They preserve exact original bytes in generated private cache files and record
the mapping from original byte ranges to retained cache offsets. SQL stores the
canonical original provenance and IDs. File writes finish and fsync before the
event transaction commits and before publication; rollback restores the prior
file length. These are partial captured ranges, with explicit scan/retention/gap
limitations, rather than complete original files. Offline queries need no target
access. Active recording cancellation stops the relevant live subscription and
retains a cancelled partial investigation. Normal monitor stop retains a partial
investigation; complete-source raw downloads remain unavailable for these ranges.
Enabling recording settles activation and retained-history backfill together,
even when the HTTP caller cancels. Shared capture rechecks newly enabled
recorders after awaited peer callbacks before making new events visible. A
recording failure stops that monitor, retains its partial investigation and
leaves another consumer of the same source running.

Use InnoDB tables, utf8mb4 and a deliberate binary collation. Normalize unique usernames/entity-name keys with the same application Unicode casefold rule instead of depending on database default case/accent matching. IDs remain immutable ASCII strings or UUIDs with binary/ASCII comparison; preserve imported fixture IDs exactly. Use lowercase snake_case schema identifiers and explicit index names. Table name case rules must not depend on the build OS.

Store canonical event time as signed BIGINT integer UTC microseconds, nullable for parse errors. Keep `timestamp_original`, raw text, source IDs, member ordinal, offsets and original-byte hashes. Preserve the existing deterministic order `(timestamp_us, process_id, source_revision_id, member ordinal with null mapped to -1, byte_start, event_id)` from the engine contract; do not introduce DB collation ordering that changes golden results. Internal timestamps remain exact, never floating point. Render UTC strings and keep `[from,to)` semantics unchanged.

Raw text may reach the configured 256 KiB physical-line cap, so use an adequate MEDIUMTEXT/LONGTEXT column or separate validated text storage rather than a too-small TEXT/VARCHAR. Original byte buffers/crypto material use appropriate BLOB/VARBINARY types, never charset conversion. JSON-shaped metadata is validated by the application and stored in MariaDB-compatible JSON/text columns; do not assume MySQL's binary-JSON implementation. Large archive bytes stay outside DB blobs.

Use explicit foreign keys, revision checks, unique event identity constraints and user ownership columns/indexes. Suggested indexes: process/investigation/timestamp plus stable tiebreakers, source byte-offset lookup, owner/update-time for workspaces, session/user/expiry and username normalized key. Bound composite index sizes; do not index full raw log lines or long unbounded path strings. Plan Alembic constraints/indexes against actual MariaDB, not merely a generic ORM metadata test.

Historical queries narrow by authorized investigation/process/time indexes and use the existing Python exact literal predicate over candidate raw lines. Neither database collation, SQL LIKE wildcards nor FULLTEXT token matching may change contains/casefold semantics. Test `%`, `_`, `[x]`, `a.*b`, `Straße`/`STRASSE`, non-ASCII and identical message text at different source positions. Filtering remains independent of generated host/process prefixes.

## Accounts and privileges

Database root is provisioning/recovery only. The fresh-image bootstrap creates `inspector_migrator` with schema-level privileges, not global root grants. The supplied init script creates `inspector_app` with SELECT, INSERT, UPDATE, DELETE on the one schema, without DDL, FILE, GRANT OPTION, CREATE USER or global administration privileges. Verify grants against the real image after initialization; never use root in the serving app to avoid a failed migration.

The migrator's secret is mounted only into the one-shot migration tool, not the API. The app must not invoke migrations while serving requests. Init variables/scripts only initialize an empty datadir; they do not rotate users/passwords in an existing volume [S18]. Retain the volume on restart, provide explicit credential rotation, and never delete data as a troubleshooting shortcut. A web Administrator role is independent of these SQL account names.

## Lifecycle, isolation and connection loss

Deleting a finished historical collection is an owner/project-scoped DML
operation, with bulk removal of its events, sources, cursors, download grants
and job. It does not require a migration. Validate the managed capture directory,
stage it by rename, and restore it if the SQL transaction rolls back. After a
successful commit, invalidate its in-memory snapshots and unlink only validated
regular captured files. A failed final unlink is reported as pending cleanup
without resurrecting the deleted database resource. Other collections and
their cache namespaces remain intact.

Use one ASGI worker. One AsyncSession per operation/task; never share a session across concurrent tasks. Pool defaults are five connections plus five overflow, pre-ping, 10-second acquisition/connect bounds and 30-minute recycle. Reserve capacity for the dedicated supervisor lock, migrations, health and administration. Global MariaDB and application memory limits must fit the 16 GB server baseline. Do not leave a database transaction open while downloading an archive or waiting on a WebSocket.

Take a database-specific supervisor lock using `GET_LOCK` on a dedicated, non-pooled connection, and a local state lock. MariaDB releases this advisory lock when its connection ends; transactions do not hold it [S25]. Do not silently reconnect the lock holder and assume ownership survived. On lock-connection loss, stop protected collection/dispatch, mark readiness unhealthy, persist interruption/gaps when safe, and require reacquisition through a controlled supervisor restart. A second serving process against the same database must not create competing collectors.

Migrations use a separate named migration lock, refuse while a serving supervisor is active and fail if the expected current schema/version is incompatible. MariaDB DDL is not promised to roll back transactionally: test interrupted migrations and preserve pre-upgrade backups. The app starts only after a successful explicit migration job and schema check; a failed migration never triggers a destructive reset. Document forward/backward application/schema compatibility.

At startup, bounded readiness retries wait for MariaDB and the expected schema. During DB outage, `/health/live` may report the process alive but readiness returns 503. Auth/permission checks fail closed; no cached grants authorize continued sensitive streaming. Stop/cancel collections visibly, retain bounded partial state and report gaps on recovery. Do not automatically restart production SSH jobs after DB recovery/backend restart. Retry only safe/idempotent DB operations with bounded backoff; uncertain commits need idempotency/reconciliation, not blind duplicate inserts.

## Docker workflow and offline release

Concrete database artifacts are in `examples/deployment/`: Compose service, MariaDB config, initialization script, no-secret environment template and local secret generator. The application/proxy overlay is a CLI/deployment interface to implement. Source references cover the official entrypoint/healthcheck, Compose secrets and healthy/completed dependency ordering [S18, S23, S24].

Codex must implement and exercise: prepare fresh volume/secrets → load exact local image → start MariaDB and wait healthy → verify scoped accounts → run schema migration once → bootstrap Administrator interactively → start app and HTTPS proxy. No runtime registry/CDN access. Docker Compose is the primary required DB launch path on an approved Docker host; retain a tested equivalent Podman/systemd route for Rocky Linux 9. Do not disable SELinux or mount the Docker socket into the app. External-DB deployment omits local MariaDB and verifies the specified endpoint/CA instead.

## Backup, restore and upgrade

Quiesce app writes, collection and retention first; an InnoDB consistent dump alone does not synchronize external cache files. Use the pinned image's `mariadb-dump --single-transaction --quick --hex-blob` with a protected client-options file, not a password exposed in argv. Include the schema/Alembic version, cache/manifests/pinned data, account roles/preferences, encrypted credential records and checksums. No schema changes during a consistent dump [S27]. A live datadir file copy is not an acceptable backup.

Keep vault-master-key recovery material separately access-controlled. Reprovision SQL users/grants from protected deployment secrets on a fresh restore; app-schema backups are not backups of every server's mysql system tables. Restore app data into a test volume first, verify row counts, IDs, raw hashes and exact query results, sign in under both roles and reopen saved investigations with remote hosts disconnected. Restore/rebind vault keys explicitly; revoke restored web sessions before exposure.

Before upgrades, retain the previous images and a matching pre-migration DB/cache snapshot. A rollback restores that matching state, not merely an old image over an incompatible new schema. Test clean-volume startup, retained-volume restart, password change, database outage/recovery, failed migration, complete restore and cold Internet-blocked startup with all app/proxy/database artifacts loaded.


## Version 3 multi-system constraints and operation

Continue using **one configured MariaDB database** for all systems. A selected system changes query scope, not DB credentials, connection pool or schema. The existing Project row is the system record; retain project IDs and do not create a database/container per environment. The deployment supervisor lock guards the serving process; browser workspaces never acquire it.

Every project-owned table has non-null `project_id` and project-leading indexes. Use composite unique keys and `ForeignKeyConstraint` relationships, not independent unpaired foreign keys: SQLAlchemy documents composite constraints as a single constraint over a column group [S29]. Required examples: `(project_id,server_id)` → servers; `(project_id,subsystem_id)` → subsystems; each flow `(project_id,source_process_id/target_process_id)` → processes; sources → processes; events → sources; investigation-source/event joins → both scoped parents. Private parent access additionally matches owner. Verify MariaDB rejects cross-project inserts/updates directly, not just through API validation.

Local entity/event/source IDs can repeat across systems; full identity includes project. Preserve existing IDs during migration and use `(project_id,event_id)` for bookmark/context references. Global users/preferences and vault rows remain global; credential bindings connect them explicitly to a project. Add project/owner/workspace/lease columns and indexes to live state, uploads, previews, jobs and download grants. Import-source aliases are unique by project/source/alias, not filename/IP. All project revisions are independent, with row locks/expected revisions and transactional preview commit.

The optional v3 deployment limit fields default to workspace 5, project 10, user 10, global 10 live subscriptions, plus workspace and inventory upload ceilings. When a new field is omitted, its nominal default is capped by explicit lower legacy/global ceilings; never raise a configured ceiling implicitly. Older valid schema-2.0 configs can still be read; show any lower pre-existing per-user limit as incompatible with the requested two × five workload until an Administrator explicitly adjusts it. Never rewrite custom ceilings silently. New examples use the required 10/user default and preserve all MariaDB Docker/settings interfaces.

Backup/restore includes every project's namespace, inventory mapping provenance and owner relationships. Mark restored workspaces/jobs interrupted and invalidate auth sessions as before. Cache migration uses manifests/checksums; do not infer project from directory basename or a user's current selection. Full v3 migration/rollback requirements are in document 17. Test isolated copies and authorized local MariaDB; do not execute schema migrations on a real server merely to build this package.
