import { expect, test, type BrowserContext, type Page, type WebSocketRoute } from '@playwright/test';
import { execFile, execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { serveBuiltAssets, setAppearance, submitSignIn } from './ui';
import type { components } from '../src/api/schema';

type Role = 'administrator' | 'inspector';
type TimingObservation = { delay_ms: number; append_to_receive_ms: number; receive_to_display_ms: number; source_timestamp_utc: string; received_at_utc: string; first_dom_at_utc: string };
const root = resolve('..');
const liveEnabled = process.env.INSPECTOR_E2E_URL === 'https://localhost:8447';
const fixture = liveEnabled ? JSON.parse(readFileSync(resolve(root, '.state/stage5-browser/public-fixture.json'), 'utf8')) as { synthetic: boolean; host: string; projects: string[] } : null;
if (liveEnabled && (!fixture || !fixture.synthetic || fixture.host !== 'stage5-sftp' || !Array.isArray(fixture.projects) || fixture.projects.join(',') !== 'stage5-fixture-a,stage5-fixture-b')) throw new Error('Only the generated isolated Stage 05 synthetic fixture is authorized.');
const [systemA, systemB] = fixture?.projects ?? ['stage5-fixture-a', 'stage5-fixture-b'];
test.skip(!liveEnabled, 'Requires the generated Stage 05 fixture at https://localhost:8447.');
const report = resolve(root, 'verification/stage-5');
const failures = new WeakMap<BrowserContext, string[]>();
const external = new WeakMap<BrowserContext, string[]>();
const socketErrors = new WeakMap<BrowserContext, string[]>();

test.beforeEach(async ({ context, page, baseURL }) => {
  await context.addInitScript(() => {
    const diagnostics: { event: string; at_utc: string; sent_at_utc?: string; code?: number; reason?: string; type?: string; seq?: number; filter_version?: number }[] = [];
    Object.defineProperty(window, '__siLiveSocketDiagnostics', { value: diagnostics });
    const NativeSocket = window.WebSocket;
    window.WebSocket = class extends NativeSocket {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols);
        this.addEventListener('open', () => diagnostics.push({ event: 'open', at_utc: new Date().toISOString() }));
        this.addEventListener('close', event => diagnostics.push({ event: 'close', at_utc: new Date().toISOString(), code: event.code, reason: event.reason }));
        this.addEventListener('message', event => {
          if (typeof event.data !== 'string') return;
          try { const frame = JSON.parse(event.data) as { type: string; seq: number; filter_version: number; sent_at?: string; payload?: { reason?: unknown } }; const reason = typeof frame.payload?.reason === 'string' && /^[A-Z0-9_]+$/.test(frame.payload.reason) ? frame.payload.reason : undefined; const sent = typeof frame.sent_at === 'string' && /^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/.test(frame.sent_at) ? frame.sent_at : undefined; diagnostics.push({ event: 'frame', at_utc: new Date().toISOString(), sent_at_utc: sent, type: frame.type, seq: frame.seq, filter_version: frame.filter_version, reason }); } catch { diagnostics.push({ event: 'invalid-json', at_utc: new Date().toISOString() }); }
        });
      }
    };
  });
  const errors: string[] = []; const requests: string[] = []; const transportErrors: string[] = []; failures.set(context, errors); external.set(context, requests); socketErrors.set(context, transportErrors);
  const consoleErrors = (current: Page) => current.on('console', message => { const value = message.text(); if (value.includes('WebSocket connection')) transportErrors.push(value.replace(/wss?:\/\/[^\s']+/g, '<local-test-stream>')); });
  consoleErrors(page); context.on('page', consoleErrors);
  page.on('pageerror', error => errors.push(error.message)); context.on('page', extra => extra.on('pageerror', error => errors.push(error.message)));
  const origin = new URL(baseURL!).origin;
  if (origin !== 'https://localhost:8447') throw new Error('Stage 05 live tests require the isolated generated local fixture origin.');
  // Chromium protects local-network WebSockets separately from HTTPS requests.
  // Grant this browser-test permission only to our generated loopback origin.
  await context.grantPermissions(['local-network-access'], { origin });
  await context.route('**/*', route => { const url = new URL(route.request().url()); if (url.origin === origin) return route.fallback(); requests.push(url.origin); return route.abort(); });
  if (process.env.INSPECTOR_E2E_LOCAL_ASSETS === '1') await serveBuiltAssets(context, baseURL!);
});
test.afterEach(async ({ context, page, baseURL }) => {
  if (test.info().status !== test.info().expectedStatus) {
    const diagnostic = await Promise.all(context.pages().map(current => current.evaluate(() => Reflect.get(window, '__siLiveSocketDiagnostics')).catch(() => null)));
    mkdirSync(report, { recursive: true }); writeFileSync(resolve(report, `${test.info().title.split(' ')[0]}-socket-diagnostics.json`), JSON.stringify({ pages: diagnostic, transport_errors: socketErrors.get(context) }, null, 2));
  }
  try { expect(failures.get(context)).toEqual([]); expect(external.get(context)).toEqual([]); }
  finally {
    if ((await page.request.get('/api/v1/auth/session')).status() === 200) {
      const { csrf_token } = await (await page.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
      expect((await page.request.post('/api/v1/auth/logout', { headers: { Origin: new URL(baseURL!).origin, 'X-CSRF-Token': csrf_token }, data: {} })).status()).toBe(200);
    }
  }
});
async function login(page: Page, role: Role) {
  const accountsFile = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!accountsFile) throw new Error('Protected synthetic Stage 05 accounts are required.');
  const account = (JSON.parse(readFileSync(resolve(accountsFile), 'utf8')) as Record<Role, { username: string; password: string }>)[role];
  await page.goto('/'); await page.getByLabel('Username', { exact: true }).fill(account.username);
  try { await page.getByLabel('Password', { exact: true }).fill(account.password); if ((await submitSignIn(page)).status() !== 200) throw new Error(); }
  catch { await page.locator('input[type="password"]').fill('').catch(() => {}); throw new Error('Synthetic sign-in failed; protected values withheld.'); }
  await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
}
async function open(page: Page, project = systemA) {
  await page.goto(`/systems/${project}/logs`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await page.getByRole('button', { name: /^Live monitor/ }).click();
  await expect(page.getByRole('region', { name: 'Live monitor', exact: true })).toBeVisible();
}
async function start(page: Page, amount = 1) {
  const processes = page.getByRole('group', { name: 'Processes to monitor', exact: true }).getByRole('checkbox');
  for (let index = 0; index < amount; index += 1) await processes.nth(index).check();
  const pending = page.waitForResponse(response => response.url().endsWith('/live-sessions') && response.request().method() === 'POST');
  await page.getByRole('button', { name: amount > 1 ? 'Monitor selected' : 'Monitor', exact: true }).click();
  const response = await pending; expect(response.status()).toBe(202);
  expect(response.request().postDataJSON().seed_rows).toBeGreaterThan(1);
  const value = await response.json() as components['schemas']['LiveSessionResponse'];
  await expect(page.getByTestId('live-session-id')).toHaveText(value.session_id);
  await expect(page.locator('.live-event').first()).toBeVisible();
  await expect(page.getByText('Stream connected', { exact: true })).toBeVisible();
  return value;
}
async function apply(page: Page, term: string) {
  const pending = page.waitForResponse(response => response.url().endsWith('/filters') && response.request().method() === 'PUT');
  await page.getByLabel('Live contains string', { exact: true }).fill(term);
  expect((await pending).status()).toBe(200);
  await expect(page.locator('.live-filter-state')).toContainText('Applied version');
}
async function changeFilter(page: Page, action: () => Promise<unknown>) {
  const response = page.waitForResponse(value => value.url().endsWith('/filters') && value.request().method() === 'PUT');
  await action(); expect((await response).status()).toBe(200);
  await expect(page.locator('.live-filter-state')).toContainText('Applied version');
}
function append(source: number, text: string) {
  execFileSync(process.env.INSPECTOR_TEST_PYTHON ?? resolve(root, 'backend/.venv/Scripts/python.exe'), [resolve(root, 'scripts/stage5_local.py'), 'append', '--source', String(source), '--text', text], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000, windowsHide: true });
}
async function appendBatch(items: { source: number; token: string }[]) {
  await new Promise<void>((fulfill, reject) => execFile(process.env.INSPECTOR_TEST_PYTHON ?? resolve(root, 'backend/.venv/Scripts/python.exe'), [resolve(root, 'scripts/stage5_local.py'), 'append-batch', '--items-json', JSON.stringify(items.map(item => ({ source: item.source, text: item.token }))), '--interval-ms', '250'], { cwd: root, timeout: 30000, windowsHide: true }, error => {
    if (error) reject(new Error('The bounded synthetic paced producer failed.')); else fulfill();
  }));
}
function burst(source: number, count: number, text: string) {
  execFileSync(process.env.INSPECTOR_TEST_PYTHON ?? resolve(root, 'backend/.venv/Scripts/python.exe'), [resolve(root, 'scripts/stage5_local.py'), 'burst', '--source', String(source), '--count', String(count), '--text', text], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000, windowsHide: true });
}
async function capture(page: Page, name: string) {
  mkdirSync(resolve(report, 'screenshots'), { recursive: true });
  await page.screenshot({ path: resolve(report, `screenshots/${name}.png`), fullPage: true });
}

for (const role of ['administrator', 'inspector'] as const) test(`${role} monitors independent same-system pages, refilters retained bytes, pauses receipt and records`, async ({ page, context }) => {
  test.setTimeout(180000);
  await login(page, role); await open(page);
  await page.getByLabel('Live contains string', { exact: true }).fill('VISIBLE');
  let socketStarts = 0; page.on('websocket', () => { socketStarts += 1; });
  const monitor = await start(page); const workspace = await page.getByTestId('workspace-id').innerText();
  const initialRows = monitor.requested_rows;
  expect((monitor.snapshot.events ?? []).length).toBeGreaterThanOrEqual(initialRows);
  expect((monitor.snapshot.events ?? []).every(event => event.raw_line.includes('VISIBLE'))).toBe(true);
  const second = await context.newPage(); await open(second);
  const secondMonitor = await start(second);
  expect(secondMonitor.session_id).not.toBe(monitor.session_id);
  expect(await second.getByTestId('workspace-id').innerText()).not.toBe(workspace);
  const secondVersion = await second.getByTestId('live-filter-version').innerText();

  await apply(page, 'HIDDEN');
  await expect(page.locator('.live-event .live-message').first()).toContainText('HIDDEN');
  await expect(second.getByTestId('live-filter-version')).toHaveText(secondVersion);
  await expect(second.getByLabel('Live contains string', { exact: true })).toHaveValue('');
  await apply(page, '.*[x]');
  await expect(page.locator('.live-event .live-message').first()).toContainText('literal=.*[x]');
  await apply(page, 'STRASSE');
  await expect(page.locator('.live-event')).toHaveCount(0);
  await page.getByLabel('Live case sensitive', { exact: true }).uncheck();
  await expect(page.locator('.live-event .live-message').first()).toContainText('Straße');
  await page.getByRole('button', { name: 'Clear live filter', exact: true }).click();
  await expect(page.getByLabel('Live contains string', { exact: true })).toHaveValue('');
  await expect(page.locator('.live-event').first()).toBeVisible();
  await page.getByRole('region', { name: 'Live monitor', exact: true }).getByText('Advanced literal filters', { exact: true }).click();
  await changeFilter(page, () => page.getByLabel('Live additional includes', { exact: true }).fill('VISIBLE\nHIDDEN'));
  await changeFilter(page, () => page.getByLabel('Live include mode', { exact: true }).selectOption('all'));
  await expect(page.locator('.live-event')).toHaveCount(0);
  await changeFilter(page, () => page.getByLabel('Live include mode', { exact: true }).selectOption('any'));
  await expect(page.locator('.live-event').first()).toBeVisible();
  await changeFilter(page, () => page.getByLabel('Live excludes', { exact: true }).fill('VISIBLE'));
  await expect(page.locator('.live-message').first()).toContainText('HIDDEN');
  await changeFilter(page, () => page.getByRole('button', { name: 'Clear live filter', exact: true }).click());
  await page.getByRole('region', { name: 'Live monitor', exact: true }).getByText('Per-process literal filters', { exact: true }).click();
  await changeFilter(page, () => page.getByLabel('p-ingest-a Live contains string', { exact: true }).fill('VISIBLE'));
  await apply(page, 'HIDDEN'); await expect(page.locator('.live-event')).toHaveCount(0);
  await apply(page, ''); await expect(page.locator('.live-message').first()).toContainText('VISIBLE');
  await changeFilter(page, () => page.getByRole('button', { name: 'p-ingest-a Clear live filter', exact: true }).click());
  await page.getByRole('region', { name: 'Live monitor', exact: true }).getByText('Per-process literal filters', { exact: true }).click();
  await page.getByRole('region', { name: 'Live monitor', exact: true }).getByText('Advanced literal filters', { exact: true }).click();

  const received = Number(await page.getByTestId('live-received').innerText());
  const frozenIds = await page.locator('.live-event').evaluateAll(rows => rows.map(row => row.getAttribute('data-event-id')));
  await page.getByRole('button', { name: 'Pause display', exact: true }).click();
  const token = `PAUSED-${role}-${Date.now()}`; append(0, token);
  await expect.poll(async () => Number(await page.getByTestId('live-received').innerText())).toBeGreaterThan(received);
  expect(await page.locator('.live-event').evaluateAll(rows => rows.map(row => row.getAttribute('data-event-id')))).toEqual(frozenIds);
  await expect(page.locator('.live-message').filter({ hasText: token })).toHaveCount(0);
  await page.getByRole('button', { name: 'Resume display', exact: true }).click();
  await expect(page.locator('.live-message').filter({ hasText: token })).toBeVisible();
  await expect(second.locator('.live-message').filter({ hasText: token })).toBeVisible();
  await page.getByLabel('Live pane layout', { exact: true }).selectOption('split');
  await expect(page.locator('.live-panes')).toHaveClass(/split/);
  const filterVersion = await page.getByTestId('live-filter-version').innerText();
  for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(size);
    // A resized pane may request a larger seed without reconnecting capture.
    await expect.poll(async () => {
      const measured = await page.locator('.live-log-scroll').first().evaluate(element => Math.ceil((element.clientHeight - 30) / 30));
      const state = await (await page.request.get(`/api/v1/projects/${systemA}/live-sessions/${monitor.session_id}`)).json() as components['schemas']['LiveSessionResponse'];
      return state.requested_rows === measured;
    }).toBe(true);
    await expect(page.locator('.live-filter-state')).toContainText('Applied version');
    for (const theme of ['light', 'dark'] as const) {
      const themeVersion = await page.getByTestId('live-filter-version').innerText();
      await setAppearance(page, theme);
      await expect(page.getByTestId('live-session-id')).toHaveText(monitor.session_id);
      await expect(page.getByTestId('live-filter-version')).toHaveText(themeVersion);
      await capture(page, `${role}-live-${theme}-${size.width}x${size.height}`);
    }
  }
  expect(Number(await page.getByTestId('live-filter-version').innerText())).toBeGreaterThanOrEqual(Number(filterVersion));
  expect(socketStarts).toBe(1);
  await page.getByRole('button', { name: 'Record', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Recording', exact: true })).toBeDisabled();
  // A successful old filter response may arrive after Stop is acknowledged.
  // It must never restore a following state or reconnect this stopped monitor.
  let releaseFilter!: () => void; const heldFilter = new Promise<void>(resolve => { releaseFilter = resolve; });
  let filterReady!: () => void; const filterCaptured = new Promise<void>(resolve => { filterReady = resolve; });
  await page.route('**/live-sessions/*/filters', async route => { const response = await route.fetch(); filterReady(); await heldFilter; await route.fulfill({ response }); });
  await page.getByLabel('Live contains string', { exact: true }).fill('LATE-FILTER-RESPONSE');
  await filterCaptured;
  await page.getByRole('button', { name: 'Stop this monitor', exact: true }).click();
  await expect(page.getByTestId('live-session-state')).toHaveText('stopped');
  const released = page.waitForResponse(response => response.url().endsWith('/filters') && response.request().method() === 'PUT');
  releaseFilter(); await released;
  await expect(page.getByTestId('live-session-state')).toHaveText('stopped');
  expect(socketStarts).toBe(1);
  await expect(second.getByRole('button', { name: 'Stop this monitor', exact: true })).toBeEnabled();
  const afterStop = `SURVIVES-${role}-${Date.now()}`; append(0, afterStop);
  await expect(second.locator('.live-message').filter({ hasText: afterStop })).toBeVisible();
  await expect(page.locator('.live-message').filter({ hasText: afterStop })).toHaveCount(0);
  await second.getByRole('button', { name: 'Stop this monitor', exact: true }).click(); await second.close();
});

test('reload and duplicate never start SSH or steal an occupied controller; explicit resume transfers only a detached lease', async ({ page, context }) => {
  test.setTimeout(120000);
  await login(page, 'inspector'); await open(page); const original = await start(page);
  const duplicate = await context.newPage(); let duplicateStarts = 0;
  duplicate.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/live-sessions')) duplicateStarts += 1; });
  await open(duplicate);
  await expect(duplicate.getByTestId('live-session-id')).toHaveCount(0);
  await expect(duplicate.getByRole('region', { name: 'Your detached monitors' })).toHaveCount(0);
  expect(duplicateStarts).toBe(0);
  const csrf = await (await page.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
  const duplicateWorkspace = await duplicate.getByTestId('workspace-id').innerText();
  const forged = await duplicate.request.post(`/api/v1/projects/${systemA}/live-sessions/${original.session_id}/attach`, { headers: { Origin: new URL(page.url()).origin, 'X-CSRF-Token': csrf.csrf_token }, data: { workspace_id: duplicateWorkspace, expected_lease_revision: original.lease_revision } });
  expect(forged.status()).toBe(409);
  expect((await forged.json()).error.code).toBe('WORKSPACE_IN_USE');
  let reloadStarts = 0; page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/live-sessions')) reloadStarts += 1; });
  await page.reload(); await page.getByRole('button', { name: /^Live monitor/ }).click();
  await expect(page.getByTestId('live-session-id')).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Your detached monitors' })).toContainText(original.session_id);
  expect(reloadStarts).toBe(0);
  await page.getByRole('button', { name: 'Resume in this window', exact: true }).click();
  await expect(page.getByTestId('live-session-id')).toHaveText(original.session_id);
  await expect(page.getByText('Stream connected', { exact: true })).toBeVisible();
  await expect(duplicate.getByTestId('live-session-id')).toHaveCount(0);
  await page.getByRole('button', { name: 'Stop this monitor', exact: true }).click(); await duplicate.close();
});

test('same-account different-system pages keep two times five sources including idle source within latency and quota limits', async ({ page, context }) => {
  test.setTimeout(180000);
  await login(page, 'inspector'); await open(page, systemA);
  const firstMetrics = await context.newCDPSession(page); await firstMetrics.send('Performance.enable');
  const firstBefore = await firstMetrics.send('Performance.getMetrics');
  const first = await start(page, 5);
  const second = await context.newPage(); await open(second, systemB);
  const secondMetrics = await context.newCDPSession(second); await secondMetrics.send('Performance.enable');
  const secondBefore = await secondMetrics.send('Performance.getMetrics');
  const other = await start(second, 5);
  await page.getByLabel('Live pane layout', { exact: true }).selectOption('split');
  await second.getByLabel('Live pane layout', { exact: true }).selectOption('split');
  await expect(page.locator('.live-pane')).toHaveCount(5); await expect(second.locator('.live-pane')).toHaveCount(5);
  await page.locator('.live-log-scroll').nth(0).evaluate(element => { (element as HTMLElement).style.height = '420px'; });
  await page.locator('.live-log-scroll').nth(1).evaluate(element => { (element as HTMLElement).style.height = '150px'; });
  await expect.poll(async () => {
    const state = await (await page.request.get(`/api/v1/projects/${systemA}/live-sessions/${first.session_id}`)).json() as components['schemas']['LiveSessionResponse'];
    return state.seed_rows_by_process?.['p-ingest-a'] === 13 && state.seed_rows_by_process?.['p-parser-a'] === 4;
  }).toBe(true);
  for (const currentPage of [page, second]) await currentPage.evaluate(() => {
    const observations: Record<string, TimingObservation> = {};
    Object.defineProperty(window, '__siLiveLatency', { value: observations });
    const observer = new MutationObserver(() => {
      document.querySelectorAll<HTMLElement>('.live-event').forEach(row => {
        const token = /LATENCY-\d+-\d+/.exec(row.textContent ?? '')?.[0];
        const eventTime = row.dataset.eventTime;
        const receivedAt = row.dataset.receivedAt;
        if (token && eventTime && receivedAt && observations[token] === undefined) {
          const now = Date.now(); const source = Date.parse(eventTime); const received = Date.parse(receivedAt);
          observations[token] = { delay_ms: now - source, append_to_receive_ms: received - source, receive_to_display_ms: now - received, source_timestamp_utc: eventTime, received_at_utc: receivedAt, first_dom_at_utc: new Date(now).toISOString() };
        }
      });
    });
    observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['data-event-id', 'data-event-time'] });
  });
  const idleBefore = Number(await page.getByTestId('live-received').innerText());
  const measurementStarted = Date.now();
  const measurements: (TimingObservation & { system: string; source: number })[] = [];
  const producerId = Date.now();
  const batch = Array.from({ length: 16 }, (_, index) => ({ source: index % 4, token: `LATENCY-${index % 4}-${producerId + Math.floor(index / 4)}` }));
  await appendBatch(batch);
  await Promise.all(batch.flatMap(item => [page, second].map(current => expect(current.locator('.live-event').filter({ hasText: item.token })).toBeVisible())));
  for (const item of batch) for (const [currentPage, system] of [[page, systemA], [second, systemB]] as const) {
    const measurement = await currentPage.evaluate(value => (Reflect.get(window, '__siLiveLatency') as Record<string, TimingObservation>)[value], item.token);
    expect(Number.isFinite(measurement.delay_ms)).toBe(true); measurements.push({ system, source: item.source, ...measurement });
  }
  // Source 4 remains entirely idle; it must not stall the other four sources.
  await expect.poll(async () => Number(await page.getByTestId('live-received').innerText())).toBeGreaterThan(idleBefore);
  const ordered = measurements.map(item => item.delay_ms).sort((a, b) => a - b);
  const p95 = ordered[Math.ceil(ordered.length * .95) - 1];
  const physical = measurements.filter(item => item.system === systemA).toSorted((a, b) => a.source_timestamp_utc.localeCompare(b.source_timestamp_utc));
  const producerSpan = (Date.parse(physical.at(-1)!.source_timestamp_utc) - Date.parse(physical[0].source_timestamp_utc)) / 1000;
  const producerRate = (physical.length - 1) / producerSpan;
  const domTimes = measurements.map(item => Date.parse(item.first_dom_at_utc));
  const latencyReport = JSON.stringify({ method: 'Synthetic source UTC timestamp to first virtual row DOM insertion; observer runs in each page, before Playwright assertion polling. Receipt timing separates SFTP and merge/transport/render delay. Physical rate is (N-1)/first-to-last producer span, counting each shared-source append once.', sources_per_window: 5, windows_same_context: 2, idle_sources_per_window: 1, producer_appends: physical.length, producer_first_at_utc: physical[0].source_timestamp_utc, producer_last_at_utc: physical.at(-1)!.source_timestamp_utc, producer_span_seconds: producerSpan, physical_appends_per_second: producerRate, first_to_last_dom_span_seconds: (Math.max(...domTimes) - Math.min(...domTimes)) / 1000, measurement_window_seconds: (Date.now() - measurementStarted) / 1000, measurements, p95_ms: p95 }, null, 2);
  mkdirSync(report, { recursive: true }); writeFileSync(resolve(report, 'browser-live-latency.json'), latencyReport);
  writeFileSync(resolve(report, `${process.env.INSPECTOR_E2E_REPORT_NAME ?? 'live-browser'}-latency.json`), latencyReport);
  const firstAfter = await firstMetrics.send('Performance.getMetrics'); const secondAfter = await secondMetrics.send('Performance.getMetrics');
  const allowedMetrics = new Set(['JSHeapUsedSize', 'JSHeapTotalSize', 'TaskDuration', 'ScriptDuration', 'LayoutDuration', 'RecalcStyleDuration', 'Nodes', 'Documents']);
  const safeMetrics = (value: { metrics: { name: string; value: number }[] }) => Object.fromEntries(value.metrics.filter(metric => allowedMetrics.has(metric.name)).map(metric => [metric.name, metric.value]));
  writeFileSync(resolve(report, 'browser-live-resources.json'), JSON.stringify({ scope: 'Chromium CDP Performance metrics for two pages in one context. JS heap is not full browser process RSS; task durations are cumulative seconds.', producer_appends: physical.length, physical_appends_per_second: producerRate, measured_window_seconds: (Date.now() - measurementStarted) / 1000, sources_per_page: 5, pages: [{ project_id: systemA, before: safeMetrics(firstBefore), after: safeMetrics(firstAfter) }, { project_id: systemB, before: safeMetrics(secondBefore), after: safeMetrics(secondAfter) }] }, null, 2));
  execFileSync(process.env.INSPECTOR_TEST_PYTHON ?? resolve(root, 'backend/.venv/Scripts/python.exe'), [resolve(root, 'scripts/stage5_local.py'), 'resources', '--label', 'two-systems-five'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000, windowsHide: true });
  await firstMetrics.detach(); await secondMetrics.detach();
  expect(p95).toBeLessThanOrEqual(2000);
  expect(producerRate).toBeGreaterThanOrEqual(1); expect(producerRate).toBeLessThanOrEqual(5);
  await apply(page, 'ONLY-A'); await expect(second.getByLabel('Live contains string', { exact: true })).toHaveValue('');
  await page.getByRole('button', { name: 'Stop this monitor', exact: true }).click();
  await expect(second.getByTestId('live-session-id')).toHaveText(other.session_id);
  const remaining = `SYSTEM-B-${Date.now()}`; append(0, remaining);
  await expect(second.locator('.live-event').filter({ hasText: remaining })).toBeVisible();
  expect(first.project_id).not.toBe(other.project_id);
  await capture(second, 'two-system-five-source-capture');
  await second.close();
});

test('old-scope frames are rejected; a delayed or closed page cannot stall another, while global logout ends both', async ({ page, context }) => {
  test.setTimeout(120000);
  await login(page, 'inspector'); await open(page); await start(page);
  const slow = await context.newPage(); let client: WebSocketRoute | undefined; let held = false;
  const queued: (string | Buffer)[] = [];
  let previous: components['schemas']['LiveFrame'] | undefined;
  await slow.routeWebSocket('**/stream', route => {
    client = route;
    const server = route.connectToServer();
    server.onMessage(data => {
      if (typeof data === 'string') { const frame = JSON.parse(data) as components['schemas']['LiveFrame']; if (frame.type === 'snapshot') previous = frame; }
      if (held) queued.push(data); else route.send(data);
    });
  });
  await open(slow); const monitored = await start(slow); const firstFrame = previous;
  expect(firstFrame).toBeDefined();
  await apply(slow, 'VISIBLE');
  const oldVersion = monitored.filter_version;
  const stale = { ...firstFrame!, type: 'events', seq: 99999999, filter_version: oldVersion, payload: { items: [{ ...monitored.snapshot.events![0], event_id: 'injected-stale-event', raw_line: 'FORBIDDEN-OLD-FRAME' }] } };
  client!.send(JSON.stringify(stale));
  client!.send(JSON.stringify({ ...stale, filter_version: Number(await slow.getByTestId('live-filter-version').innerText()), project_id: systemB }));
  client!.send(JSON.stringify({ ...stale, workspace_id: 'wrong-page-workspace' }));
  await expect(slow.locator('.live-message').filter({ hasText: 'FORBIDDEN-OLD-FRAME' })).toHaveCount(0);
  held = true;
  const csrfResponse = await page.request.get('/api/v1/auth/csrf');
  const { csrf_token } = await csrfResponse.json() as { csrf_token: string };
  const requestHeaders = { Origin: new URL(page.url()).origin, 'X-CSRF-Token': csrf_token };
  const history = await page.request.post(`/api/v1/projects/${systemA}/collections`, { headers: requestHeaders, data: { workspace_id: await page.getByTestId('workspace-id').innerText(), process_ids: ['p-ingest-a'], from: '2026-01-01T00:00:00.000000Z', to: '2027-01-01T00:00:00.000000Z', transport: 'ssh' } });
  expect(history.status()).toBe(202);
  const collection = await history.json() as components['schemas']['HistoricalJobResponse'];
  const token = `VISIBLE-DELAYED-${Date.now()}`; append(0, token);
  await expect(page.locator('.live-message').filter({ hasText: token })).toBeVisible();
  await expect(slow.locator('.live-message').filter({ hasText: token })).toHaveCount(0);
  expect(queued.length).toBeGreaterThan(0);
  held = false; queued.splice(0).forEach(data => client!.send(data));
  await expect(slow.locator('.live-message').filter({ hasText: token })).toBeVisible();
  let completed: components['schemas']['HistoricalJobResponse'] | undefined;
  await expect.poll(async () => {
    const response = await page.request.get(`/api/v1/projects/${systemA}/jobs/${collection.job_id}`); expect(response.status()).toBe(200);
    completed = await response.json() as components['schemas']['HistoricalJobResponse'];
    return ['completed', 'partial'].includes(completed.status);
  }, { timeout: 30000 }).toBe(true);
  expect(completed!.downloaded_bytes).toBeGreaterThan(0);
  expect(completed!.coverage.some(source => source.remote_path.endsWith('/source0.zip') && source.bytes > 0 && source.events > 0)).toBe(true);
  expect((await page.request.delete(`/api/v1/projects/${systemA}/investigations/${collection.investigation_id}`, { headers: requestHeaders })).status()).toBe(200);
  await slow.close();
  const afterClose = `AFTER-CLOSE-${Date.now()}`; append(0, afterClose);
  await expect(page.locator('.live-message').filter({ hasText: afterClose })).toBeVisible();
  const sharedLogin = await context.newPage(); await open(sharedLogin, systemB); await start(sharedLogin);
  await page.locator('.account-menu > summary').click();
  await page.getByRole('button', { name: 'Sign out all windows', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await expect(sharedLogin.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await expect(sharedLogin.locator('.live-event')).toHaveCount(0); await sharedLogin.close();
});

test('an Inspector starts the selected topology process only through an explicit Monitor action', async ({ page }) => {
  await login(page, 'inspector');
  let starts = 0;
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/live-sessions')) starts += 1; });
  await page.goto(`/systems/${systemA}/topology`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await page.getByRole('button', { name: 'Select process ingest-instance-a', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Monitor this process', exact: true })).toBeVisible();
  expect(starts).toBe(0);
  const pending = page.waitForResponse(response => response.url().endsWith('/live-sessions') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Monitor this process', exact: true }).click();
  const response = await pending; expect(response.status()).toBe(202);
  expect(response.request().postDataJSON().process_ids).toEqual(['p-ingest-a']);
  await expect(page).toHaveURL(new RegExp(`/systems/${systemA}/logs$`));
  await expect(page.getByTestId('live-session-id')).toBeVisible();
  await expect(page.getByText('Stream connected', { exact: true })).toBeVisible();
  expect(starts).toBe(1);
  await page.getByRole('button', { name: 'Stop this monitor', exact: true }).click();
});

test('retention eviction stays visible during pause and retained refiltering after a bounded synthetic burst', async ({ page }) => {
  test.setTimeout(150000);
  await login(page, 'inspector'); await open(page); await start(page);
  await page.getByRole('button', { name: 'Pause display', exact: true }).click();
  const token = `RETENTION-${Date.now()}`;
  burst(0, 21000, token);
  await expect.poll(async () => Number(await page.getByTestId('live-evicted').innerText()), { timeout: 60000 }).toBeGreaterThan(0);
  await expect(page.getByText(/Retention evicted \d+ raw events\./)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Resume display', exact: true })).toBeVisible();
  expect(Number(await page.getByTestId('live-retained').innerText())).toBeLessThanOrEqual(20000);
  await page.getByRole('button', { name: 'Resume display', exact: true }).click();
  await apply(page, token);
  await expect(page.locator('.live-message').first()).toContainText(token);
  await page.getByText('Source access, seed coverage and continuity', { exact: true }).click();
  for (const theme of ['light', 'dark'] as const) {
    await setAppearance(page, theme); await capture(page, `retention-eviction-coverage-${theme}`);
  }
  await page.getByRole('button', { name: 'Stop this monitor', exact: true }).click();
});

test('capacity baseline keeps two five-source windows responsive during concurrent sixteen MiB archive collections and a held page', async ({ page, context }) => {
  test.setTimeout(240000);
  const controller = (...args: string[]) => execFileSync(process.env.INSPECTOR_TEST_PYTHON ?? resolve(root, 'backend/.venv/Scripts/python.exe'), [resolve(root, 'scripts/stage5_local.py'), ...args], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000, windowsHide: true });
  controller('capacity-archive');
  const archiveFixture = JSON.parse(readFileSync(resolve(report, 'capacity-fixture.json'), 'utf8')) as { synthetic: boolean; expanded_bytes: number; records: number };
  expect(archiveFixture).toMatchObject({ synthetic: true, expanded_bytes: 16777216, records: 65536 });
  let held = false; let slowClient: WebSocketRoute | undefined; const heldFrames: (string | Buffer)[] = [];
  await page.routeWebSocket('**/stream', route => {
    slowClient = route;
    const server = route.connectToServer();
    server.onMessage(data => { if (held) { if (heldFrames.length >= 512) throw new Error('The bounded test delivery hold exceeded 512 frames.'); heldFrames.push(data); } else route.send(data); });
  });
  await login(page, 'inspector'); await open(page, systemA); const first = await start(page, 5);
  const healthy = await context.newPage(); await open(healthy, systemB); const second = await start(healthy, 5);
  await page.getByLabel('Live pane layout', { exact: true }).selectOption('split');
  await healthy.getByLabel('Live pane layout', { exact: true }).selectOption('split');
  await expect(page.locator('.live-pane')).toHaveCount(5); await expect(healthy.locator('.live-pane')).toHaveCount(5);
  const usage = await (await page.request.get(`/api/v1/projects/${systemA}/usage?workspace_id=${first.workspace_id}`)).json() as components['schemas']['LiveUsageResponse'];
  expect(usage.counts).toMatchObject({ global_: 10, user: 10, project: 5, workspace: 5 });
  await healthy.evaluate(() => {
    const observations: Record<string, TimingObservation> = {};
    Object.defineProperty(window, '__siCapacityLatency', { value: observations });
    const observer = new MutationObserver(() => {
      document.querySelectorAll<HTMLElement>('.live-event').forEach(row => {
        const token = /CAPACITY-\d+-\d+/.exec(row.textContent ?? '')?.[0]; const source = row.dataset.eventTime; const received = row.dataset.receivedAt;
        if (token && source && received && observations[token] === undefined) { const now = Date.now(); observations[token] = { delay_ms: now - Date.parse(source), append_to_receive_ms: Date.parse(received) - Date.parse(source), receive_to_display_ms: now - Date.parse(received), source_timestamp_utc: source, received_at_utc: received, first_dom_at_utc: new Date(now).toISOString() }; }
      });
    });
    observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['data-event-id', 'data-event-time'] });
  });
  const { csrf_token } = await (await page.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
  const headers = { Origin: new URL(page.url()).origin, 'X-CSRF-Token': csrf_token };
  const selected = [{ project_id: systemA, monitor: first }, { project_id: systemB, monitor: second }];
  const created = await Promise.all(selected.map(item => page.request.post(`/api/v1/projects/${item.project_id}/collections`, { headers, data: { workspace_id: item.monitor.workspace_id, process_ids: item.monitor.process_ids, from: '2026-10-16T00:00:00.000000Z', to: '2026-10-18T00:00:00.000000Z', transport: 'ssh' } })));
  for (const response of created) expect(response.status()).toBe(202);
  const jobs = await Promise.all(created.map(response => response.json() as Promise<components['schemas']['HistoricalJobResponse']>));
  const jobsAcceptedAt = new Date().toISOString();
  console.log(`Capacity fixture: both historical jobs accepted at ${jobsAcceptedAt}; ten live subscriptions reserved.`);
  held = true; const holdStartedAt = new Date().toISOString(); const frozenReceived = await page.getByTestId('live-received').innerText();
  const states = async () => Promise.all(jobs.map(async job => {
    const response = await page.request.get(`/api/v1/projects/${job.project_id}/jobs/${job.job_id}`); expect(response.status()).toBe(200);
    return await response.json() as components['schemas']['HistoricalJobResponse'];
  }));
  const activeStates = new Set(['queued', 'planning', 'collecting', 'indexing']);
  const summary = (items: components['schemas']['HistoricalJobResponse'][]) => items.map(item => ({ project_id: item.project_id, job_id: item.job_id, status: item.status, event_count: item.event_count, downloaded_bytes: item.downloaded_bytes, expanded_bytes: item.expanded_bytes, archive_events: item.coverage.filter(source => source.remote_path.endsWith('/source0.zip')).reduce((total, source) => total + source.events, 0) }));
  const resourceWindowPromise = (async () => {
    const before = await states(); const started = new Date().toISOString();
    await new Promise<void>((fulfill, reject) => execFile(process.env.INSPECTOR_TEST_PYTHON ?? resolve(root, 'backend/.venv/Scripts/python.exe'), [resolve(root, 'scripts/stage5_local.py'), 'resources', '--label', 'capacity-sixteen-mib'], { cwd: root, timeout: 30000, windowsHide: true }, error => { if (error) reject(new Error('The bounded synthetic resource controller failed.')); else fulfill(); }));
    return { started_at: started, completed_at: new Date().toISOString(), before: summary(before), after: summary(await states()) };
  })();
  void resourceWindowPromise.catch(() => {});
  await expect.poll(async () => { const current = await states(); return current.every(job => activeStates.has(job.status) && job.coverage.some(source => source.remote_path.endsWith('/source0.zip') && source.events >= 1000)); }, { timeout: 60000 }).toBe(true);
  const startedAt = Date.now();
  const windows: { started_at: string; completed_at: string; before: ReturnType<typeof summary>; after: ReturnType<typeof summary>; qualifies: boolean; samples: (TimingObservation & { source: number; token: string })[] }[] = [];
  const tokens: string[] = [];
  {
    const before = await states(); expect(before.every(job => activeStates.has(job.status))).toBe(true);
    const windowStarted = new Date().toISOString(); const batch: { source: number; token: string }[] = [];
    const producerId = Date.now();
    for (let index = 0; index < 8; index += 1) { const source = index % 4; const token = `CAPACITY-${source}-${producerId + Math.floor(index / 4)}`; tokens.push(token); batch.push({ source, token }); }
    await appendBatch(batch);
    try { await Promise.all(batch.map(item => expect(healthy.locator('.live-event').filter({ hasText: item.token })).toBeVisible())); }
    catch (error) {
      const stoppedMonitors = await Promise.all(selected.map(async item => {
        const response = await page.request.get(`/api/v1/projects/${item.project_id}/live-sessions/${item.monitor.session_id}`);
        if (response.status() !== 200) return { project_id: item.project_id, http_status: response.status() };
        const value = await response.json() as components['schemas']['LiveSessionResponse'];
        return { project_id: value.project_id, session_id: value.session_id, status: value.status, error_code: value.error_code, counters: value.snapshot.counters, sources: value.snapshot.sources };
      }));
      writeFileSync(resolve(report, 'capacity-sixteen-mib-browser.json'), JSON.stringify({ phase: 'live delivery failed during archive indexing', elapsed_ms: Date.now() - startedAt, fixture: archiveFixture, usage, jobs_before: summary(before), jobs_after: summary(await states()), live_states: stoppedMonitors, resources: await resourceWindowPromise.catch(() => null) }, null, 2));
      throw error;
    }
    const samples = await Promise.all(batch.map(async item => ({ ...item, ...await healthy.evaluate(token => (Reflect.get(window, '__siCapacityLatency') as Record<string, TimingObservation>)[token], item.token) })));
    const after = await states();
    windows.push({ started_at: windowStarted, completed_at: new Date().toISOString(), before: summary(before), after: summary(after), qualifies: after.every(job => activeStates.has(job.status)), samples });
  }
  const measurementEndedAt = Date.now();
  const resourceWindow = await resourceWindowPromise;
  const samples = windows.filter(window => window.qualifies).flatMap(window => window.samples);
  writeFileSync(resolve(report, 'capacity-sixteen-mib-browser.json'), JSON.stringify({ phase: 'live measurement completed', fixture: archiveFixture, usage, windows, resources: resourceWindow, qualifying_samples: samples.length }, null, 2));
  expect(samples.length).toBeGreaterThanOrEqual(4);
  expect(samples.every(sample => Number.isFinite(sample.delay_ms))).toBe(true);
  const delays = samples.map(sample => sample.delay_ms).sort((a, b) => a - b); const p95 = delays[Math.ceil(delays.length * .95) - 1];
  const producerSamples = windows.flatMap(window => window.samples).toSorted((a, b) => a.source_timestamp_utc.localeCompare(b.source_timestamp_utc));
  const producerSpan = (Date.parse(producerSamples.at(-1)!.source_timestamp_utc) - Date.parse(producerSamples[0].source_timestamp_utc)) / 1000;
  const producerRate = (producerSamples.length - 1) / producerSpan;
  await expect(page.getByTestId('live-received')).toHaveText(frozenReceived);
  await expect.poll(() => heldFrames.length).toBeGreaterThan(0);
  for (const token of tokens) await expect(page.locator('.live-event').filter({ hasText: token })).toHaveCount(0);
  const heldFrameCount = heldFrames.length; const holdEndedAt = new Date().toISOString();
  held = false; heldFrames.splice(0).forEach(data => slowClient!.send(data));
  await expect(page.locator('.live-event').filter({ hasText: tokens.at(-1)! })).toBeVisible();
  await capture(healthy, 'capacity-sixteen-mib-healthy-five-panes');
  const liveStates = await Promise.all(selected.map(async item => await (await page.request.get(`/api/v1/projects/${item.project_id}/live-sessions/${item.monitor.session_id}`)).json() as components['schemas']['LiveSessionResponse']));
  for (const [index, live] of liveStates.entries()) {
    expect(live.status).toBe('following');
    const initialIdle = selected[index].monitor.snapshot.sources?.find(source => source.process_id === 'p-audit-a');
    expect(live.snapshot.sources?.find(source => source.process_id === 'p-audit-a')?.received).toBe(initialIdle?.received);
  }
  let completed = await states();
  await expect.poll(async () => { completed = await states(); return completed.every(job => !activeStates.has(job.status)); }, { timeout: 150000 }).toBe(true);
  for (const job of completed) {
    expect(job.status).toBe('completed'); expect(job.source_count).toBe(6); expect(job.scanned_sources).toBe(6);
    expect(job.downloaded_bytes).toBeGreaterThanOrEqual(16777216); expect(job.downloaded_bytes).toBeLessThanOrEqual(20971520);
    expect(job.expanded_bytes).toBeGreaterThanOrEqual(16777216); expect(job.expanded_bytes).toBeLessThanOrEqual(20971520);
    const archive = job.coverage.filter(source => source.remote_path.endsWith('/source0.zip'));
    expect(archive).toHaveLength(1); expect(archive[0]).toMatchObject({ status: 'completed', events: 65536, expanded_bytes: 16777216, error_code: null });
  }
  const evidence = { scope: 'Two systems in one browser context/account, five SFTP subscriptions each; two simultaneous 16–20 MiB historical investigations and held delivery in System A.', fixture: archiveFixture, usage, historical_jobs_accepted_at: jobsAcceptedAt, held_delivery_started_at: holdStartedAt, held_delivery_ended_at: holdEndedAt, held_delivery_frames: heldFrameCount, held_display_received_counter: frozenReceived, producer_pacing_interval_ms: 250, producer_appends: tokens.length, producer_first_at_utc: producerSamples[0].source_timestamp_utc, producer_last_at_utc: producerSamples.at(-1)!.source_timestamp_utc, producer_span_seconds: producerSpan, physical_appends_per_second: producerRate, measured_window_seconds: (measurementEndedAt - startedAt) / 1000, first_to_last_dom_span_seconds: (Math.max(...producerSamples.map(item => Date.parse(item.first_dom_at_utc))) - Math.min(...producerSamples.map(item => Date.parse(item.first_dom_at_utc)))) / 1000, healthy_first_dom_p95_ms: p95, qualifying_samples: samples.length, windows, resources: resourceWindow, completed_jobs: completed, live_source_states: liveStates.map(live => ({ project_id: live.project_id, session_id: live.session_id, status: live.status, sources: live.snapshot.sources })), healthy_socket_timing: await healthy.evaluate(() => Reflect.get(window, '__siLiveSocketDiagnostics')), proxy: 'Direct fixture TLS; release proxy and full-browser RSS remain separate release evidence.' };
  writeFileSync(resolve(report, 'capacity-sixteen-mib-browser.json'), JSON.stringify(evidence, null, 2));
  expect(resourceWindow?.before.every(job => activeStates.has(job.status))).toBe(true);
  expect(resourceWindow?.after.every(job => activeStates.has(job.status))).toBe(true);
  expect(p95).toBeLessThanOrEqual(2000);
  expect(producerRate).toBeGreaterThanOrEqual(1); expect(producerRate).toBeLessThanOrEqual(5);
  for (const currentPage of [page, healthy]) { await currentPage.getByRole('button', { name: 'Stop this monitor', exact: true }).click(); await expect(currentPage.getByTestId('live-session-state')).toHaveText('stopped'); }
  for (const job of completed) expect((await page.request.delete(`/api/v1/projects/${job.project_id}/investigations/${job.investigation_id}`, { headers })).status()).toBe(200);
  await healthy.close();
});
