# MariaDB Docker provisioning and application integration

`compose.mariadb.yaml` is a concrete database-only template. `compose.application.example.yaml` describes the application/CLI interface Codex must implement and test; it cannot start an application from this specification alone. No images, actual credentials or database data are bundled. Commands below are for an authorized local staging/deployment host, not automatic actions taken by this package.

## Directory and configuration preparation

Run from this `examples/deployment/` directory, or copy it intact to a dedicated deployment directory. Do not reuse another application's MariaDB volume/container. Install or stage Docker Engine and **Docker Compose v2** by the approved OS process. The package does not install the container runtime. Rocky/Podman recipes are still required Codex release work; do not assume Compose secrets/permissions transfer unchanged to rootless Podman.

```sh
cp .env.example .env
cp ../deployment-policy.example.yaml application.yaml
python3 prepare_secrets.py --output-dir secrets
```

Use a new/empty private directory. The generator refuses overwrites and does not print secret values. Three independent 64-hex-character passwords and a base64-encoded 32-byte vault key are created. Secret files use mode 0444 inside a mode-0700 parent so both the official image's mysql user and the non-root app can read individually mounted files. The parent directory is the host access boundary; never move these files into a publicly traversable directory. Containers receive only their explicitly listed files, read-only. Local Compose file-backed secrets do not universally implement requested uid/gid/mode remapping, so do not rely on such remapping [S23]. On rootless/user-namespace/SELinux deployments, verify actual service access and apply appropriate labels/ACLs without weakening host directory access.

Edit `application.yaml`: public origin, state/cache paths if needed, database host/port/name/user/password file and operational policy. Its schema is `contracts/deployment.schema.json`. `database.host: mariadb` means the Compose service; `localhost` in the app container means the app itself and will not reach this DB. The sample schema name (`system_inspector`) and usernames must match the Compose bootstrap settings and migration command. The app CLI must validate that mismatch visibly, not create a different database silently.

## Stage images before going offline

The example `.env` uses `mariadb:11.8` as the selected baseline and `caddy:2` as an illustration; both are mutable series tags. On a connected build host, resolve a tested maintenance release/digest and record it. Pull only there, test the image and save it. The offline launch recipe has `pull_policy: never` [S15, S18]. Example database-only staging commands, after setting `MARIADB_IMAGE` to the approved concrete reference:

```sh
# Connected preparation host only; set this to the approved image reference.
docker pull "$MARIADB_IMAGE"
docker image save -o mariadb-image.tar "$MARIADB_IMAGE"
sha256sum mariadb-image.tar > mariadb-image.tar.sha256

# Offline target after securely transferring both files:
sha256sum -c mariadb-image.tar.sha256
docker image load -i mariadb-image.tar
```

A Docker archive's retained tags/digests can differ from registry lookup metadata. Verify that the exact reference used by the offline Compose file resolves locally after loading. The final release must provide tested local tags/image IDs, archive hashes and registry digests where applicable; do not invent hashes or rely on a digest reference that was not restored by the load test. Stage app and proxy images the same way after Codex creates the application.

## Start and verify the database

With the approved image present, `.env` configured, and secrets in place:

```sh
docker compose --env-file .env -f compose.mariadb.yaml config --quiet
docker compose --env-file .env -f compose.mariadb.yaml up -d --wait
docker compose --env-file .env -f compose.mariadb.yaml ps
```

First boot creates the schema and the **migration account** using `MARIADB_DATABASE`, `MARIADB_USER` and password-file variables. A non-executable sourced initialization script creates the separate **runtime account** with SELECT/INSERT/UPDATE/DELETE privileges on that schema only. Root is localhost-only; it is not the app account. The script is intentionally limited to generated hex passwords and validated identifiers. `INSPECTOR_DB_APP_PASSWORD_FILE` may override only its bootstrap secret-file path; the default matches the template. It depends on the official image initialization helper and must be integration-tested against the pinned image [S18]. Keep it non-executable after copying/extracting the package.

Health uses `healthcheck.sh --connect --innodb_initialized`. A healthy MariaDB is a prerequisite, not proof that application migrations ran or that runtime grants are correct. The application must verify both schema version and connectivity [S18, S24]. Port 3306 is not published to the host/LAN. The database-only internal network is later shared with app/migrate, not the proxy/browser.

**Initialization variables/scripts only apply to a fresh data directory. Changing `.env` or a password file does not change accounts in an existing database.** Rotate existing credentials through an explicit authorized database operation, update the secret file atomically, restart affected consumers and verify the old credential is rejected. Do not delete a populated volume to make changed variables take effect. `docker compose down` without `-v` keeps the database; `down -v` destroys data and is not an upgrade/recovery step.

## Full application startup after implementation

Provide a certificate/key from your internal CA under `tls/server.crt` and `tls/server.key`. Align the Caddy hostname and `deployment.public_origin`; port 8443 is the default published HTTPS port. The proxy configuration disables automatic ACME and reads supplied certificates [S29]. The default loopback bind is for setup; explicitly change `INSPECTOR_BIND_ADDRESS` to the approved LAN interface for Windows browser access, with host firewall rules.

Codex must implement the CLI commands referenced by the templates, create/chown the non-root state/cache directories in the image, validate configuration, run Alembic using only migration credentials, expose safe readiness, and provide interactive `users bootstrap-admin` provisioning. The serving app never receives the root or migration password file.

```sh
# Only after app/proxy images, CLI, config and certificates exist:
docker compose --env-file .env -f compose.mariadb.yaml -f compose.application.example.yaml config --quiet
docker compose --env-file .env -f compose.mariadb.yaml -f compose.application.example.yaml up -d --wait
# This first-admin command is an application interface to implement, not supplied Python code:
docker compose --env-file .env -f compose.mariadb.yaml -f compose.application.example.yaml exec app \
  python -m inspector.cli users bootstrap-admin --username admin
```

Startup order is database healthy → one-shot schema migration success → app ready → proxy. No public bootstrap endpoint/default credentials. On later upgrades, quiesce captures, back up, explicitly recreate/run the migration service and then start the new app; a completed stale migration container is not evidence that a new migration ran. The final release must include a tested wrapper for this sequence.

## Existing MariaDB alternative and operations

`../application.external-db.example.yaml` shows an existing endpoint with verified TLS. Provision the same scoped accounts/schema there. The managed Compose template is not an external-server variant; Codex must provide a separate tested app/proxy recipe that omits the local database and its dependencies, mounts the CA, and uses the configured hostname. No browser-facing arbitrary DB-connect endpoint is required.

See documents 11 and 14 for backup/restore, image updates, outage behaviour, grant verification, connection-pool limits and SELinux. Docker/Podman/MariaDB execution was not performed while preparing this package; see VERIFICATION.md for exactly what was checked.


## Version 3 multiple systems

Use this same stack for all named system configurations. A second browser window selects a different Project/System within the same database; it does not start another app/MariaDB container. The current configuration example raises `max_live_processes_per_user` to 10 while retaining a global 10, with per-workspace 5 and project 10 limits. Existing deployments must review custom ceilings explicitly, not reset them. Inventory file parsing is in the app, with no Ansible binary/plugin execution. Test both systems through backup/restart and independent live sessions as specified in documents 16 and 17.
