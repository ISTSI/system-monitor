# Local MariaDB development setup

This is the project's actual local database setup for the existing backend
foundation. It is separate from the retained production templates in
`examples/deployment/`. One MariaDB database, `system_inspector`, holds every
System/Project. Integration runs get separate disposable schemas in the same
local container; those schemas never select a user's current System.

The official MariaDB 11.8 maintenance image and Python runner base are pinned by
platform manifest digest in `images.lock.json`. That file distinguishes registry
resolution from actual container testing. The database has no published host
port and runs only on an internal Docker network. Linux runner containers avoid
putting Windows filesystem paths into the deployment contract. Compose always
uses `pull_policy: never`.

From the repository root, use the locked backend Python environment:

```powershell
backend/.venv/Scripts/python.exe scripts/local_mariadb.py prepare
backend/.venv/Scripts/python.exe scripts/prepare_local_images.py --connected
backend/.venv/Scripts/python.exe scripts/local_mariadb.py up
backend/.venv/Scripts/python.exe scripts/local_mariadb.py migrate
backend/.venv/Scripts/python.exe scripts/local_mariadb.py new-test --run
backend/.venv/Scripts/python.exe scripts/local_mariadb.py status
```

On Linux the interpreter is `backend/.venv/bin/python`; prepare as an unprivileged
local account. The first command needs no Docker daemon. Image preparation is an explicit connected build
step; it downloads the pinned images and builds the local runner with locked
backend dependencies. Subsequent launch, migration and test commands use those
local images on the internal network. Docker Desktop must run Linux containers
and the invoking account must have permission to use its daemon.

`prepare` writes independent, cryptographically random root, migration and
runtime passwords under the ignored `.secrets/local-mariadb/` directory. On
Windows it installs a protected DACL for the current account, SYSTEM and local
Administrators before writing. On Linux the secret directory has mode 0700;
individually mounted secret files have mode 0444 so the image's `mysql` user and
the runner can read only their mounted files. Generated configuration and
Compose environment files are ignored and created with mode 0600. Repeating
`prepare` refuses to overwrite an existing setup or rotate its credentials.
An explicit `--image` must be an official exact `11.8.PATCH@sha256:DIGEST`
reference; normally the checked-in lock supplies it.

When the coding tool runs under a separate Windows sandbox account, designate
the actual Docker Desktop account with `prepare --windows-owner 'DOMAIN\\user'`.
For an already prepared setup, use `secure-secrets --windows-owner 'DOMAIN\\user'`.
This grants that one account access alongside the tool account, SYSTEM and
Administrators, without rotating any secret. The designated SID is retained
inside the private directory so later test provisioning preserves its access.

The generated `application.local.yaml` explicitly names host `mariadb`, port
3306, database `system_inspector`, runtime account `inspector_app` and
`/run/secrets/inspector_db_password`. TLS is disabled only for this managed,
single-host private-network setup. All deployment paths stay POSIX paths.
The root account is localhost-only and is used for bootstrap/provisioning.
`inspector_migrator` has privileges on the development schema; `inspector_app`
has only SELECT, INSERT, UPDATE and DELETE. Migration and runtime runner
containers receive only their own secret. No whole-repository mount exposes
the provisioning secrets to either runner.

Database underscores are escaped in privilege patterns: MariaDB treats those
names as patterns even inside backticks. Fresh-image bootstrap removes the
official entrypoint's initial migration-account grants and restores access to
the exact development schema, preserving the account's authentication.

`up` waits for the official image healthcheck. `migrate` is an explicit one-shot
Alembic invocation, separate from serving. Stop any runtime supervisor before
migration. It never drops or resets a schema after an error. The initial
revision supports a fresh schema; this setup is not an existing-data upgrade.

`new-test --run` creates a new `inspector_test_run_<random>` schema and two new
accounts restricted to it, then runs the real MariaDB integration suite in
the Linux runner. The tests themselves run the initial migration. A generated
`inspector_test_*.compose.local.yaml` supplies the opt-in, POSIX configuration
and two independent test secrets. Use `--suffix foundation` for the explicit
name `inspector_test_foundation`; it is refused if that schema already exists.
Every later test run needs a new suffix because the suite refuses populated
schemas and retains its synthetic data for review. Neither the helper nor the
suite drops schemas. Test provisioning SQL travels over stdin and root
authentication uses a temporary client-options file inside the database
container; passwords never appear in process arguments or normal output.

To stop the database while retaining every schema and credential:

```powershell
backend/.venv/Scripts/python.exe scripts/local_mariadb.py stop
```

Running `up` again uses the existing named volume. Init SQL and image
environment variables apply only to an empty data directory and do not rotate
credentials in retained volumes. There is deliberately no reset/delete command.
Credential rotation and full release backup/restore remain separately reviewed
lifecycle work. This development setup does not complete the Stage 01 browser
foundation, HTTPS proxy, first-Administrator interaction or offline release.

## Actual Stage 01 container verification — 17 October 2026

The local Docker Desktop Linux engine is now usable. The pinned MariaDB 11.8.9
and Python 3.13.16 images were pulled and the non-root runner was built. A fresh
`inspector_test_stage1_20261017` schema passed all 19 actual Linux integration
tests, including concurrent first/last Administrator guards, account lifecycle,
secure sessions/CSRF, composite scope constraints, quotas and cold app restart.
The helper preserved that schema and its synthetic history for review.

The development `system_inspector` database now also contains two explicitly
synthetic systems, synthetic Administrator/Inspector accounts, and distinct
persisted light/dark preferences. The serving account was checked against
actual grants; DDL and reading the separate test schema were rejected. The
app image ran as UID/GID 10001 with a read-only root filesystem, dropped
capabilities, no published ports, and only the runtime DB secret mounted.

Actual private-network HTTP checks exercised bundled assets, both account
roles, the safe system viewer and denied Inspector writes. Stopping MariaDB
left liveness at 200 and readiness/protected/CSRF responses at 503. Starting
the retained volume with no image pulls did not silently reacquire supervisor
ownership: a controlled app restart was required. Both systems, roles,
preferences and safe demo snapshots matched their prior digest afterward.

See [the verification artifacts](../../verification/stage-1/docker/) and
[the current stage status](../../progress/STATUS.md) for commands and scope.
These internal HTTP checks do not claim a Linux browser/HTTPS proxy test or
completion of the separate full offline release and Rocky/Podman gates.
