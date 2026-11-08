# Offline installation and operation

System Inspector serves all Systems through one backend and one MariaDB. A
Windows 10/11 browser is a client; install the containers on a Linux x86-64
server. The release test report is authoritative about tested hosts. Linux
containers exercised on Docker Desktop do **not** qualify an Ubuntu or Rocky
host. Ubuntu 24.04 LTS/Docker Compose and Rocky Linux 9/rootless Podman are the
provided target recipes; an unexecuted target remains a release limitation.

The delivery directory contains `manifest.json`, `SHA256SUMS`, three image
archives, `runtime/`, notices/SBOM and the test report. Keep it immutable and
retain the previous delivery. Archives contain the built frontend, backend,
migrations, runtime dependencies, nginx and MariaDB; startup never installs
packages, builds assets, resolves tags or pulls images. `runtime/manage.py`
checks every archive and the loaded image IDs before serving. Checksums detect
changes; verify their provenance through the approved delivery channel.
Launch recipes use the verified local content IDs after checking delivery
references, so a later local tag change cannot substitute a different image.

## Host preparation and certificate

Provide at least the documented 16 GB host baseline and enough disk for the
configured 10 GiB cache, database, images and a separate complete recovery copy.
Stage OS packages and dependencies through the organisation's approved offline
APT repository/media for Ubuntu, or signed DNF repository/media for Rocky.
Required host tools are Python 3.9 or newer, OpenSSL, a supported container
runtime and its networking/storage dependencies; Compose must be v2.24 or
newer. Stage the matching runtime packages and their full dependency closure on
a connected machine of the **same OS/version/architecture**, verify package
signatures, then install through that OS package manager against the offline
repository. This delivery does not bootstrap an OS or replace its security
update process. Do not use an Internet installer or bypass signature checks.

Choose a dedicated service/operator identity and private runtime directory.
Docker lifecycle commands require a root operator shell (`sudo -i` through the
site's approved host procedure) to set UID/GID 10001 on private application data.
The tool rejects an ordinary Docker-group shell for lifecycle operations;
membership of Docker's group alone does not permit the host ownership change.
Membership of Docker's group also conveys host administrative power.
Rootless Podman uses an ordinary dedicated account with allocated subuid/subgid
ranges and a private home. Runtime and recovery parents must be owned by their
operator, mode 0700, and local to the server. No Docker socket enters a container.

Obtain a certificate for the exact public origin from the internal CA. The
optional helper creates only a key and signing request:

```sh
python3 /opt/system-inspector-release/runtime/certificate-request.py \
  --hostname inspector.internal.example --output /srv/inspector-certificate-request
```

Send `server.csr` through the internal CA process; keep `server.key` private.
Receive a PEM server certificate including intermediate chain as required, and
distribute the CA trust through the Windows/browser administration process.
Never transfer the CA's private key to the application. There is no ACME client.
`init` verifies expiry (at least one day), hostname/IP and private-key match;
the operator verifies the CA and approved trust chain. Certificates are mounted
as individual read-only files into the proxy. Keep the containing directory
0700; the tool uses individual 0444 files so non-root container identities can
read them without exposing the private host parent. Replace certificates
through the protected operator process and restart only the proxy.

## Ubuntu 24.04 LTS and Docker Compose

The following commands use an example origin and loopback bind. To permit LAN
clients, pass the approved host interface address to `--bind-address`, align DNS
and the certificate, and authorize only the HTTPS port in the host firewall.
Database port 3306 and backend port 8000 are never published. Target/jump LAN
SFTP and required DNS must remain reachable from the Linux host/container
network. Allow no runtime Internet egress; a disconnected laptop alone is
insufficient evidence.

Run from the approved Linux root operator shell, substituting actual delivery and
certificate paths:

```sh
python3 /opt/system-inspector-release/runtime/manage.py \
  --release /opt/system-inspector-release --runtime /srv/system-inspector \
  init --origin https://inspector.internal.example:8443 \
  --bind-address 127.0.0.1 \
  --certificate /srv/inspector-certificate-request/server.crt \
  --private-key /srv/inspector-certificate-request/server.key
python3 /opt/system-inspector-release/runtime/manage.py \
  --release /opt/system-inspector-release --runtime /srv/system-inspector verify
python3 /opt/system-inspector-release/runtime/manage.py \
  --release /opt/system-inspector-release --runtime /srv/system-inspector load
python3 /opt/system-inspector-release/runtime/manage.py \
  --release /opt/system-inspector-release --runtime /srv/system-inspector start
python3 /opt/system-inspector-release/runtime/manage.py \
  --release /opt/system-inspector-release --runtime /srv/system-inspector bootstrap-admin
```

`init` requires a new/empty directory. It generates independent database
passwords and a 32-byte vault key without displaying them. `start` validates
locally loaded identities, stops serving, fixes private state/cache ownership,
starts and waits for MariaDB, recreates and waits for a one-shot migration, then
starts app/proxy. A failed migration leaves serving stopped. The first
Administrator command prompts for username, display name and password twice;
there is no default account, public setup or password argument. Create
Inspectors through the Administrator account UI and require their initial
password change. Restarting never automatically resumes SSH jobs.

Docker uses a unique Compose project recorded in private `settings.json` and a
**named persistent database volume**. Application state/cache use the private
`data/state` and `data/cache` binds, UID/GID 10001 and modes 0700/0600. App/proxy
have read-only images, dropped capabilities, no-new-privileges, bounded memory,
processes and tmpfs. The official MariaDB entrypoint runs its required
initialization and switches to its mysql identity; it receives only its own
database secrets. The serving app receives only runtime SQL and vault secrets;
the migration job receives only its scoped migration secret.

The vault key is exactly **32 raw binary bytes**, never base64 text. Its serving
copy is `data/state/ssh-vault.key`, owned by UID/GID 10001 with mode 0600; backend
validation rejects the wrong owner or group/other access. Its separate recovery
source is `secrets/inspector_vault_key`, mode 0600, owned by the host operator.
The state snapshot explicitly excludes `ssh-vault.key` and rejects a backup
which attempts to include that member. Recovery binds the separate raw key
through the mapped ownership helper before starting the app.

The generated `application.yaml` is JSON, which is valid YAML, so Python's
standard library can safely retain it without a host YAML dependency. Edit it
only while serving is stopped, retain the strict schema and explicit DB
host/port/name/user/password-file/TLS fields, and restart through `manage.py`.
Do not replace custom limits with defaults during updates. Runtime configuration
is deployment policy, distinct from database-backed shared settings and
project import/export. SQL credentials/root/vault material are excluded from
ordinary configuration and investigation exports.

For protected diagnosis, inspect the private Compose stack:

```sh
docker compose --project-directory /srv/system-inspector \
  --env-file /srv/system-inspector/images.env \
  -f /srv/system-inspector/compose.yaml ps
```

Use the external recipe filename below where applicable. App readiness validates
MariaDB, exact schema and DML-only runtime grants. A healthy database alone is
insufficient. Authenticated diagnostics expose safe version/count/status
information. Proxy access logging is disabled; app logs omit raw events,
search/correlation terms and passwords. Treat database/container diagnostics as
protected operator information.

## Rocky Linux 9 and rootless Podman/systemd

Use the same release images. Select `--engine podman` **before** each command,
including `init`. Ports must be at least 1024. Verify your exact Podman version
is 4.4 or newer and that rootless networking, subuid/subgid mappings and container
DNS operate before installing. `load` uses `podman image load`; every `run`
uses `--pull=never`. It creates an internal database network, a service network
for proxy/app and explicit LAN egress, and the same named database volume.
There is no second backend/database for the second System.

`manage.py` supplies a systemd fallback rather than assuming an installed Rocky
Quadlet generator supports every required feature. It uses Podman's stable
container/network commands and waits for database health and migration success
before exposing HTTPS. The packaged `system-inspector.service.in` is a **user**
unit. Replace `@RELEASE@` and `@RUNTIME@` with the actual absolute, space-free
paths, install as `~/.config/systemd/user/system-inspector.service`, then run:

```sh
systemctl --user daemon-reload
systemctl --user enable --now system-inspector.service
systemctl --user status system-inspector.service
```

The host administrator may enable login linger for the dedicated service
account through the approved host process so the user manager starts at boot.
The unit coordinates startup/shutdown and retains state. It is a oneshot
orchestrator: inspect container health separately; `active (exited)` alone does
not prove application health. Use `systemctl --user restart` for controlled
recovery. Do not run a parallel root and rootless stack against the same data.

Keep SELinux enforcing. Shared read-only config/secrets use `:z`; each private
state/cache bind and the database volume use `:Z`. `podman unshare` sets the
mapped UID/GID 10001 on private application state and performs recovery copies;
do not chown those files to an unmapped host UID, disable SELinux, or make data
world-writable. Host runtime/secrets/tls/data parents stay 0700. Verify actual
mounted file readability with the service identity and review SELinux audit
denials for labeling problems. Rootless port publishing exposes only the
chosen HTTPS address; apply the same firewall restrictions as Docker. Never
use privileged containers or a host socket mount to bypass permissions.

Native Ubuntu/Rocky qualification must record OS release, kernel, runtime,
Compose/Podman, storage/network backend, cgroup and SELinux state, cold start,
retained restart, role/browser checks, backup/restore and blocked Internet
traffic. A recipe's presence or YAML parse is not that evidence.

## Existing verified-TLS MariaDB endpoint

The DBA first creates an empty approved database and separate schema-scoped
migration and DML-only runtime accounts. The serving account must have exactly
SELECT/INSERT/UPDATE/DELETE on that schema, no DDL/global grants/grant option.
Provide a private JSON descriptor with these exact fields:

```json
{
  "host": "mariadb.internal.example",
  "port": 3306,
  "name": "system_inspector",
  "username": "inspector_app",
  "migration_username": "inspector_migrator",
  "ca_file": "/srv/protected/database-ca.crt",
  "password_file": "/srv/protected/runtime-password",
  "migration_password_file": "/srv/protected/migration-password"
}
```

Use `init ... --external-db /srv/protected/external-db.json`. A password file
contains one nonempty UTF-8 value (at most 4096 bytes), optionally ending in one
LF/CRLF. Spaces and reserved characters are preserved; embedded CR/LF and NUL
are rejected. The protected MariaDB client-options writer quotes and escapes
these values as data. The descriptor contains paths, never password values.
The generated `compose.external.yaml`
omits the managed database and mounts the CA into migration/app. TLS certificate
chain and hostname verification are mandatory; never change to disabled TLS to
work around a mismatch. Host and port remain explicit; selecting a System never
changes them. The migration account is supplied only to the migration job and
the explicit operator backup client. Existing-DB provisioning/restore is a DBA
action, not an arbitrary web endpoint.

## First investigation and read-only access

Administrator shared Settings controls application default appearance/language,
security policy and accounts; personal Preferences controls theme and language
for either role. Personal theme/language can be shared across the account's
windows. Current System, filters, live sessions and page workspaces remain
independent. Logout and account revocation intentionally affect every window.

1. Create/select the intended System. Create a subsystem, a server inside it,
   then configured process instances inside that server. A server may be
   documented with **No connection**; collection requires a saved connection.
   Each process has a single logical log source with rotations/archives.
2. Add a direct or one-jump connection and dedicated read-only SSH credentials.
   Verify **both** host-key fingerprints against an independent trusted source,
   then approve them. Unknown/changed keys fail closed. Check Linux-host DNS,
   VPN/routing, target port and jump forwarding; the Windows browser's network
   access does not establish server access.
3. Grant the read account directory traversal and read access to configured
   active, rotated and archive files, including future rotations. Configure
   allowed roots and source paths. With Additional security measures enabled,
   verify and confirm the current source revision. Turning that setting off
   never grants trust, credentials, sudo or shell permissions.
4. Define/test a timestamp parser against representative synthetic/sample text.
   Event times use UTC and `[from,to)`; unknown timestamps stay in the
   diagnostic lane. Parse failures must remain visible rather than receive
   fabricated times. Import static INI/YAML, companion-file ZIP or canonical
   JSON through the System-targeted preview wizard; commit only reviewed
   changes. Uploaded inventories never execute Ansible/plugins/scripts.
5. Select configured processes and a UTC collection range; collection is an
   explicit action. View retained events in merged/split panes, filter literal
   text, inspect context and pin described groups. Display filters are
   independent of the next collection's UTC inputs.
6. Start a live monitor explicitly. Filters operate over retained raw events;
   refiltering uses the existing collection without SSH reconnect. Pause
   changes presentation; stop ends that monitor's collection; disconnect and
   page close have a bounded reconnect grace period. Resume in a new page is
   explicit. Stopping one page never stops another page's monitor.
7. Read coverage and truncation/rotation/resync/scan-budget notices. Identical
   text at different source positions remains distinct. No exactly-once claim
   is made through arbitrary rotation/truncation. Narrow a range or request an
   explicit policy-bounded increase where a limit is reached.
8. Save investigations, notes/bookmarks, correlation traces and pinned context.
   Enable recording explicitly for retained live data. Cache expiry/limits can
   remove unpinned history; saved/pinned content and coverage show what remains.
   Test reopening saved data with target hosts disconnected.
9. Preview redaction before a deliberate offline export. The preview explains
   residual exposure; it is not a complete anonymisation guarantee. Bundles
   omit passwords/vault data. Import validates content/checksums into a new
   offline investigation and does not enable network sources or replace shared
   topology. Inspectors manage their own investigations, never shared config.

The backend SSH module sends **no remote shell commands** and offers no terminal,
sudo, restart, discovery, writes or agent. Its remote operations are SSH
handshake/authentication and read-only SFTP metadata/list/open/read/close,
including approved path resolution. Optional jump forwarding is restricted to
the approved target. A web Administrator cannot manage target-host processes.
The application's top-menu Help describes the complete UI and these boundaries.

## Backup and restore

Schedule an operator-visible maintenance window. `backup` stops the proxy and
application, so collection, edits and retention are quiescent. It then runs the
pinned MariaDB `mariadb-dump --single-transaction --quick --hex-blob
--no-tablespaces`, using a temporary protected client-options file rather than
password arguments, and copies **all** System state/cache namespaces. There
must be no concurrent migration or other direct database writer during backup.
Never copy a live datadir as a backup. The named volume is not copied.

```sh
python3 /opt/system-inspector-release/runtime/manage.py \
  --release /opt/system-inspector-release --runtime /srv/system-inspector \
  backup --output /srv/inspector-recovery-2026-10-18
```

The new private backup contains SQL, schema/table-count metadata, non-secret
deployment recovery policy and every raw-cache/state file with SHA-256 and byte
size. `backup.json` is written only after successful completion. Verification
rejects changed, extra, missing, duplicated, symlink, hardlink and unsafe-path
members and enforces 64 GiB/200,000-file safety limits. Exceeding a backup limit
fails visibly; plan a reviewed larger recovery method for larger installations.
Failures leave the app stopped and preserve original data. Backups may contain
raw logs, hashes and encrypted SSH credential records: protect them like the
original deployment. They contain neither SQL password files nor the vault key.

Copy `secrets/inspector_vault_key` to a **separate**, access-controlled recovery
location through your site's secret-handling procedure. The key is essential
for decrypting retained SSH credentials, and must never enter an investigation
bundle or the data backup directory. Back up SQL provisioning secrets separately
if your recovery policy requires them. Reprovision SQL accounts from protected
new-runtime secrets; an app-schema dump is not a backup of MariaDB system tables.
Restart the original app explicitly with `start` after verifying the snapshot.

Always restore a test copy first. Keep the matching release loaded, initialize
a **fresh** private runtime on a new origin/HTTPS port with the same release,
then restore before starting it:

```sh
python3 /opt/system-inspector-release/runtime/manage.py \
  --release /opt/system-inspector-release --runtime /srv/inspector-restore-test \
  restore --backup /srv/inspector-recovery-2026-10-18 \
  --vault-key /srv/separate-protected-recovery/inspector_vault_key
```

The command refuses an existing database volume or nonempty state/cache. It
verifies all bytes, restores scoped files, rebinds the separate key, retains
custom limits/auth/retention policy, initializes new SQL accounts, loads the
dump, compares schema/table counts, revokes every restored login and marks old
workspaces/unfinished jobs interrupted. It leaves app/proxy stopped. If restore
fails, keep the failed test runtime private for diagnosis and initialize another
fresh target; never delete the original application's volume to retry.

Run `start`, sign in separately under Administrator and Inspector, verify both
themes/language/preferences, Systems A/B topology/import mappings, owner-only
investigations, raw hashes, exact event query results and saved disconnected
investigations. Check that original web cookies no longer work and no SSH
connection starts until explicitly requested. Metadata counts alone do not
establish application recovery correctness. Promote a recovered copy only after
these checks and separate deployment authorization.

External database restore requires a DBA-controlled **fresh schema**: stop all
serving instances, validate the same backup manifest and bytes, provision new
scoped accounts, load only `database.sql` using a protected client-options file
and verified TLS, restore the `files/state` and `files/cache` trees using
`runtime/fileops.py restore`, rebind the separate vault key, preserve custom
policy, and run the fixed `runtime/db-client.sh revoke` operation against the
restored schema before exposure. Compare `db-client.sh inspect` output with
`database-metadata.txt`, then perform the same application checks. The automated
`restore` command deliberately rejects an external endpoint so it cannot
overwrite an unrelated populated schema.

## Upgrade and rollback

Retain previous images, delivery manifest and its matching pre-migration
DB/cache backup. Stop serving/collection, take and verify a coordinated backup,
then verify and `load` the new delivery. Keep the existing runtime and its
settings, secrets, volume identity, custom policy and all System IDs. Review
new runtime template changes and apply them deliberately to the private
runtime; never replace `settings.json`, `application.yaml`, secrets or data from
a fresh `init`. Running a new delivery's script path alone does **not** update
the Compose/file-copy/database-client tools copied into the existing runtime.

After the coordinated backup, run the **old** delivery's `stop` command to stop
the whole stack, including managed MariaDB. Retain the old runtime tools as
well as its images and DB/cache backup. In the approved root operator shell for
Docker, use concrete protected paths for the reviewed template refresh:

```sh
mkdir -m 0700 /srv/inspector-tools-before-upgrade
for inspector_tool in compose.yaml compose.external.yaml 20-runtime-user.sh \
  mariadb.cnf db-client.sh fileops.py manage.py application.template.json
do
  cp -p "/srv/system-inspector/$inspector_tool" /srv/inspector-tools-before-upgrade/
  install -m 0444 "/opt/system-inspector-release-new/runtime/$inspector_tool" \
    "/srv/system-inspector/$inspector_tool"
  cmp "/opt/system-inspector-release-new/runtime/$inspector_tool" \
    "/srv/system-inspector/$inspector_tool"
done
```

The template JSON is a tool reference; retain the existing **application.yaml**
and deliberately reconcile any newly required policy fields without resetting
custom ceilings. Do not copy defaults over the live policy. Keep `settings.json`
unchanged so the exact stack and named database volume retain their identity.

Remove only the stopped containers for this recorded private stack, retaining
all data volumes. This also replaces stale bind-mount inodes and makes the
managed database container use the newly selected image. For managed Docker:

```sh
docker compose --project-directory /srv/system-inspector \
  --env-file /srv/system-inspector/images.env \
  -f /srv/system-inspector/compose.yaml rm --force proxy app migrate mariadb
python3 /opt/system-inspector-release-new/runtime/manage.py \
  --release /opt/system-inspector-release-new --runtime /srv/system-inspector start
```

For an external database use `compose.external.yaml` and remove only `proxy app
migrate`; the DBA controls any database-server upgrade. Never add `--volumes` or
use `down -v`. The new tool refreshes the image-ID environment, runs the current
migration and waits for success before exposing the app.

For rootless Podman, perform the same file refresh as the dedicated service
account, stop the systemd user unit and remove only its stopped containers.
Read the validated private stack identity first:

```sh
INSPECTOR_UPGRADE_STACK="$(python3 -c 'import json,re,sys; v=json.load(open(sys.argv[1]))["stack"]; assert re.fullmatch("inspector-[a-f0-9]{10}",v); print(v)' /srv/system-inspector/settings.json)"
podman rm "${INSPECTOR_UPGRADE_STACK}-proxy" "${INSPECTOR_UPGRADE_STACK}-app" \
  "${INSPECTOR_UPGRADE_STACK}-migrate"
# Managed database only; retain its named volume.
podman rm "${INSPECTOR_UPGRADE_STACK}-mariadb"
```

Review the new systemd unit template and update its `@RELEASE@` path to the new
immutable delivery while preserving the runtime path and service identity.
Run `systemctl --user daemon-reload` and start the unit. Otherwise a later boot
could select the previous image manifest. No container removal above deletes a
named data volume. Keep the old tools and unit for matching-state rollback.

Recheck roles, saved data, imported mappings and independent same-account pages.

If migration fails, serving remains unavailable. Keep protected diagnostics and
use the exact pre-migration recovery snapshot. To roll back, load the retained
previous delivery, initialize a fresh private runtime using that release,
restore its matching snapshot/key and validate it before changing the intended
origin. An old image over a newer incompatible schema is not a rollback.
Schema downgrade and deletion of populated volumes are not routine rollback
steps. Deployment, host firewall changes and any production switch need their
own authorization.

Database password changes are explicit DBA operations. Editing secret files
does not rotate accounts in an existing volume; initialization scripts only run
on first boot. Stop consumers, change the scoped password through the approved
protected client, atomically replace the matching secret file, then restart and
verify old credentials are rejected. For a vault-key replacement, do not
overwrite the current key: existing ciphertext is bound to it. Retain the
current recovery key and use only a separately reviewed, tested re-encryption
migration. This release does not provide a vault rotation command.

## Failures and safe remedies

| Symptom | Checks and response |
|---|---|
| Login/stream returns persistence unavailable | Check DB health/reachability, verified TLS, exact schema/runtime grants and supervisor lock. Protected operations fail closed during an outage. Restore DB service, then use controlled app restart if its lock was lost. No cached grant/database fallback exists. |
| `NOT_READY`: `Supervisor is unavailable.` after host standby | Compare the backend's `Persistence supervisor` warning with host/VM suspend/resume events. Suspending the host can time out the dedicated lock probe even when MariaDB later appears healthy. Confirm DB health and no competing supervisor, preserve retained state, then perform a controlled restart of only the affected application with its existing image/configuration/mounts. Docker's restart policy does not recover a process that remains alive returning 503. Refresh the page afterward; start any new monitor explicitly. Keep lock verification and fail-closed behaviour enabled. |
| Unknown or changed SSH key | Compare the independently obtained fingerprint and approve the intended key through Administrator trust controls. Never disable host verification. |
| SSH timeout/DNS/jump failure | Verify Linux-side DNS, route/VPN, target port and explicitly approved jump forwarding. Compare all engine bridge subnets with target/LAN/VPN ranges, including networks left by stopped test stacks; a bridge route can capture a target despite a correct application default route. Preserve metadata before removing only a confirmed unused test network. No startup discovery scan occurs. |
| SFTP unavailable or permission denied | Enable the target account's approved read-only SFTP service and narrow traversal/read permissions for active and future rotated files. Do not add sudo or broad root access. |
| Collection partial or bounded scan exhausted | Inspect coverage, parser diagnostics and budget warning. Narrow time/process selection or request an explicit bounded policy change. Do not infer missing lines from filtered results. |
| HTTPS untrusted/hostname mismatch | Install the approved CA chain, correct DNS/origin/certificate and restart the proxy. Do not use an insecure permanent browser exception. |
| Native SELinux denial or bind permission failure | Keep enforcing; correct `z/Z` labels, private parents and mapped UID/GID. Check actual non-root container access. Do not use 0777, privileged mode or socket mounts. |
| Missing/mismatched offline image | Recheck trusted delivery checksums, load **all three** archives and compare exact local IDs. No runtime pull fallback is enabled. |
| Interrupted monitor after restart | Start a new monitor explicitly or follow the UI's permitted detached-session workflow. Historical/pinned data remains scoped to its System and owner. |

Inspectors can investigate approved logs and manage personal saved state.
Administrators additionally manage shared topology, imports, accounts,
credentials/trust and defaults; neither role authorizes writes on a target host.
The last enabled Administrator cannot be disabled/demoted/removed, including
concurrent edits. Revocation/logout invalidates account-wide sessions and jobs;
ordinary window closure, refilter or System selection is page-local.
