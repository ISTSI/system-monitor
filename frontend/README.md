# System Inspector web application

React/TypeScript/Vite sources compile to local static assets served by FastAPI on the same HTTPS origin. No runtime npm, CDN, cloud account, fonts or Internet access is needed. The current vertical slice includes authentication, system catalogue, revisioned topology editing, account management, appearance and a virtualised historical viewer. Local fixture collection indexes real plain, ZIP and TAR.GZ events in MariaDB. Administrator SSH password storage, host-key approval and direct/single-jump connection tests are available through server details or Connections. Remote historical collection remains pending Stage 04 work.

The recorded connected-build toolchain is Node **24.22.0**, npm **11.19.1**, TypeScript **5.9.3**, React **19.3.1** and Vite **8.3.4**. The generated package-lock.json locks the full dependency tree with actual registry integrity values. TypeScript 5 is required by the API generator's declared peer dependency; the lock does not bypass peer checks. React Flow renders the editable topology; TanStack Virtual renders historical log rows.

On Windows, bootstrap the official checksum-verified portable Node archive and install packages from the repository root:

```powershell
powershell -File scripts/bootstrap_node.ps1 -Connected
backend/.venv/Scripts/python.exe scripts/frontend.py install --connected
```

The helper uses repository-local Node when present, and requires recorded Node 24.22.0 otherwise. All its npm/browser caches stay under .cache. An already provisioned Linux build environment can use Node 24.22.0 and `npm ci --ignore-scripts --no-audit --no-fund` from this directory. The Linux runtime serves the build; it does not need Node.

```powershell
backend/.venv/Scripts/python.exe scripts/frontend.py lint
backend/.venv/Scripts/python.exe scripts/frontend.py typecheck
backend/.venv/Scripts/python.exe scripts/frontend.py api:generate
backend/.venv/Scripts/python.exe scripts/frontend.py api:check
backend/.venv/Scripts/python.exe scripts/frontend.py build
```

Generate API types after regenerating backend/openapi.json. The check compares generated output and fails on drift. `src/api/schema.d.ts` is a generated artifact, never a hand-maintained API contract.

Browser checks use Playwright **1.64.1** and its Chromium **156.0.8078.4** build **1248**. Connected browser setup is `node node_modules/@playwright/test/cli.js install chromium` with PLAYWRIGHT_BROWSERS_PATH set to the repository .cache/playwright directory. The test configuration uses this same directory and never downloads at test runtime.

Run the isolated Stage 03 local Docker fixture setup and HTTPS server documented in [backend setup](../backend/README.md), then set INSPECTOR_E2E_ACCOUNTS to the absolute path of the ignored synthetic account fixture and run:

```powershell
backend/.venv/Scripts/python.exe scripts/frontend.py e2e
```

Tests use one browser context for parallel pages and check both different-system and duplicated same-system workspaces. The screenshot matrix covers both roles, both themes and 1280×720/1920×1080. Traces, videos and automatic failure screenshots are disabled to keep password entry out of artifacts. Deliberate screenshots capture authenticated views and cleared password forms only. The tests block external browser requests and assert none were attempted. Browser certificate verification is bypassed only by the local test configuration, for the generated loopback certificate.

The browser regressions also delay real preference/session responses through logout and a subsequent login, checking that stale responses cannot restore protected content or clear the new session/CSRF token. The targeted 200% layout equivalent uses CSS 640×360 with deviceScaleFactor 2: the same layout and physical pixel budget as a 1280×720 viewport at 200% zoom. This is explicitly a layout equivalent, not browser toolbar zoom automation. Keyboard focus, dialog scrolling, process selection and horizontal overflow are checked. Set INSPECTOR_E2E_URL=https://localhost:8445, INSPECTOR_E2E_REPORT_STAGE=stage-3 and INSPECTOR_E2E_ACCOUNTS to .secrets/stage3-browser/accounts.json (absolute path). Reports are under verification/stage-3; set INSPECTOR_E2E_REPORT_NAME to a distinct lowercase basename when preserving separate runs. Repeated runs against the temporary VM need fresh synthetic account fixtures or expiry of the bounded workspace grace period; deployment quotas are retained during tests.

Dependency/license evidence is in [the collected inventory](../third_party/frontend/README.md). Package notices are copied from the actual installed artifacts; packages without separate license texts retain their published package metadata and README. These are development-platform notices; release assembly must collect notices for its own platform as well.

Version/engine references: [official Node release index](https://nodejs.org/dist/index.json), [Vite compatibility](https://vite.dev/guide/), [Playwright browsers](https://playwright.dev/docs/browsers). These are connected build references, not runtime dependencies.
