# Observed toolchain — 17 October 2026

SSH setup follow-up: the real uv resolution added **AsyncSSH 2.24.1** only;
existing locked dependency versions were retained. Python 3.13 compatibility was
tested in Windows and the Linux runner. Its original EPL-2.0/GPL-2.0-or-later
notices are preserved in the installed backend notice inventory, now 52 entries.
This remains a free dependency from the required stack. The runner now creates
the named, non-root `inspector` account (UID/GID 10001), which AsyncSSH needs for
local username resolution; the application Dockerfile applies the same fix.

Host: Windows PowerShell 5.1, Windows x86-64. Initial Python was 3.14.0 with pip 25.2 only. Python 3.13, uv, Node/npm, Make and database clients were absent from PATH. `py -0p` listed only 3.14. No application or dependencies were initially supplied.

An isolated `.bootstrap` virtual environment now contains uv **0.13.1**, installed from the registry after the sandbox network restriction required a reviewed escalation. uv downloaded **CPython 3.13.16**, the current resolved 3.13 maintenance interpreter, into repository-local `.toolchains/python`. It did not replace the machine Python. uv reported that it could not replace a pre-existing unmanaged user-bin launcher; all recorded commands used explicit local paths. Cache is repository-local `.cache/uv`. These generated trees are ignored and excluded from source/package validation.

`backend/.python-version` records 3.13.16. `backend/uv.lock` is an actual uv resolution with registry artifact hashes and supported-platform wheel metadata, not fabricated checksums. Backend interpreter: `backend/.venv/Scripts/python.exe`. Direct dependencies resolved: FastAPI 0.143.3, Uvicorn 0.54.0, SQLAlchemy 2.0.55, asyncmy 0.2.16, Alembic 1.20.0, argon2-cffi 25.1.0, PyYAML 6.0.3, jsonschema 4.26.0. Pydantic 2.14.1 and Starlette 1.8.0 are locked transitively. Build/test tools include hatchling 1.32.4, pytest 9.1.1, pytest-asyncio 1.4.0, Ruff 0.17.1 and mypy 1.20.2. Full installed version/license evidence is in `third_party/backend/inventory.json`.

License metadata/notices were collected from the 50 installed runtime/build/test distributions using `scripts/collect_backend_notices.py`. Mandatory dependencies use free/open-source licenses; no paid library is introduced. Retained licenses include MIT, Apache-2.0, BSD, PSF, and MPL notices for dev dependencies. Distribution notice contents are preserved under `third_party/backend/`. This is a Windows development-environment inventory, not a complete Linux release SBOM or vulnerability audit. OpenTelemetry API is a transitive library; no SDK, exporter, telemetry configuration or outbound telemetry is implemented.

Docker CLI **27.1.1** exists, but `docker version` cannot open `//./pipe/docker_engine` (“The system cannot find the file specified”); it also cannot read the user Docker config under the sandbox. There is no reachable local daemon. `wsl --list --quiet` returns `Wsl/EnumerateDistros/Service/E_ACCESSDENIED`. Podman, MariaDB/MySQL clients, Node/npm and GNU Make are unavailable. No official image tag/digest has been selected/tested and no container was started. React/TypeScript/Node 24 LTS tooling remains the next foundation slice.

Implementation references checked: [SQLAlchemy composite constraints](https://docs.sqlalchemy.org/en/20/core/constraints.html) and [FastAPI dependency cleanup scope](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/). The current code uses a single composite ForeignKeyConstraint and function-scoped transaction cleanup before HTTP responses. Local asyncmy source inspection also showed string passwords use Latin-1; the engine passes UTF-8 secret bytes as an explicit connection override while retaining URL.create for safely constructed URLs. Actual MariaDB Unicode-password acceptance remains an integration gate.

## MariaDB setup follow-up

The local setup now has actual official registry references for MariaDB 11.8.9 and Python 3.13.16-slim, selected for Linux amd64 and stored in `deploy/local-mariadb/images.lock.json` with descriptor evidence in `verification/mariadb-setup/registry-manifests.json`. The Linux uv 0.13.1 bootstrap wheel has a real PyPI-provided SHA256 in `runner-bootstrap.requirements.txt`. These artifacts are prepared, not container-tested. Docker Compose v2.29.1 validates the generated setup. Docker Desktop startup remains blocked by the signed-in account's `docker-users` membership check; the engine pipe is absent. The user is resolving that host prerequisite. No OS/runtime install, image pull, running database or migration is claimed.

## Temporary VM validation follow-up

The user supplied a running temporary VM as a replacement for Docker Desktop. The workstation Python 3.13.16/locked asyncmy+SQLAlchemy stack successfully connected through the existing loopback tunnel to `12.3.3-MariaDB-ubu2404`, initialized the empty approved schema and passed four direct database checks. No new dependencies or container images were needed. This verifies the existing Windows build tooling against that database version for the current slice; it does not establish Linux runtime, full MariaDB 12.3 compatibility, offline images or release acceptance. The prepared MariaDB 11.8.9 container baseline remains untested and unchanged.


## Stage 01 browser and Linux validation

Added cryptography **49.0.0** through an actual uv resolution for local development
TLS certificates and the selected future secret stack. Backend notice collection
now covers **51** installed runtime/build/test distributions. Portable Node
**24.22.0** / npm **11.19.1** was downloaded from the official distribution and
SHA256-verified locally. The real npm lock pins React/React DOM **19.3.1**, Vite
**8.3.4**, TypeScript **5.9.3**, React Flow **12.12.0**, TanStack Virtual **3.14.21**,
Playwright **1.64.1** and its Chromium **156.0.8078.4**, build **1248**. TypeScript 5
satisfies the API generator's declared peer range; no peer checks were overridden.

All 171 installed npm packages have recorded license metadata/notices. The 28
runtime dependencies have separate original license texts preserved; MIT/ISC/BSD
licenses cover them. Required React Flow/TanStack components are free/open source.
No build-machine fonts were copied. Evidence is under verification/stage-1 and
third_party/frontend. This is not a full release security-advisory audit.

Docker Engine **27.1.1** / Compose **2.29.1** is reachable using the signed-in
account and explicit local Linux-engine pipe. The repository's pinned MariaDB
**11.8.9** and Python **3.13.16-slim** images are pulled and the Linux runner built;
**19 actual MariaDB integration tests pass without skips**. This supersedes the
previous daemon blocker. The VM MariaDB **12.3.3** is retained independently and
passes the broader runtime-identity API/browser checks. Exact app image digest,
restart/offline results and platform limits are recorded in STATUS.md; Ubuntu/
Rocky host and full release validation remain separate.

Stage 04 historical collection (17 October 2026) retains the existing locks and
AsyncSSH 2.24.1; no dependency or paid library was added. Actual tests use Python
3.13.16 and MariaDB 11.8.9 in the local non-root Linux runner, plus Node 24.22.0
and the pinned Playwright Chromium on Windows. The independently keyed
synthetic target/jump support password-only authentication, pinned Ed25519 keys,
SFTP protocol 3 and one `direct-tcpip` jump. Read-only OPEN/READ/CLOSE,
LSTAT/FSTAT, REALPATH and directory listing were exercised; target exec and file
mutation counters remain zero. Tested data includes plain/rotated files, ZIP
and TAR.GZ archives. SFTP v3 lacks portable atomic open-beneath/inode guarantees;
snapshot metadata/probes detect observed changes without promising every race
can be detected. Actual CentOS/Rocky OpenSSH distributions and production SSH
endpoints were not contacted. Full offline/platform release qualification remains
Stage 08. See STATUS.md and verification/stage-4 for executed checks.

Stage 05 (17 October 2026) resolves **websockets 16.1.1** (BSD-3-Clause) for
Uvicorn 0.54.0's explicit `websockets` adapter. Installed source forwards both
the 16 KiB message-byte ceiling and 16-message receive queue; its legacy
protocol applies backpressure at the queue limit. Uvicorn's wsproto and SansIO
adapters do not honor this queue setting. **wsproto 1.3.2** (MIT) remains a
development dependency for raw-wire transport tests. Actual uv resolution and
locked synchronization preserve the other dependency versions. Original
licenses are retained under `third_party/backend/`, with the refreshed
**54-distribution** inventory. No paid library, font, telemetry or runtime
Internet dependency is added.

The selected legacy adapter emits upstream deprecation warnings. Its compatible
major range is bounded; an upgrade must rerun the real TCP fragmented-message
and queue/backpressure tests rather than assume a future Uvicorn adapter alias
preserves these limits. `websocket-transport-dependency.json` retains the actual
version, license and warnings. Offline runtime never resolves a newer version.

The separate `system-inspector-runner:stage5` image uses the existing pinned
Python 3.13.16 Linux base plus the updated uv lock. Build evidence records both
actual image IDs and verifies that `system-inspector-runner:local` remains
unchanged. The existing 8444/8445 services are not recreated by Stage 05 tests.
The synthetic browser fixture uses 8447 and grants Chromium's local-network
permission only for that test origin; this is test setup, not an application or
SSH trust exception. Actual results are in STATUS.md and verification/stage-5.

Stage 07 retains the existing dependency locks and toolchain versions. Browser
literal highlighting bundles a generated casefold table from the locked Python
3.13.16 runtime's Unicode 15.1.0 database; a full-table parity test prevents drift
from backend matching. Original Python and Unicode notices are included in
`frontend/public/licenses/` and the built assets. No new dependency or font is
introduced. `scripts/generate_casefold.py --check` reproduces the data offline.

The separate `system-inspector-runner:stage7` image and 8449 synthetic fixture
leave the retained runner tags and installations intact. Stage 07 builds to
`.state/stage7-build/`; an artifact verifier compares frozen inputs, packaged
backend modules/migrations, frontend assets and wheel contents. This avoids
changing the frontend directories mounted by retained local services. These are
local verification artifacts, not Stage 08 offline release qualification.
