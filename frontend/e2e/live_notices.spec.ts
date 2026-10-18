import { expect, test, type Locator, type Page, type Request, type WebSocketRoute } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { components } from '../src/api/schema';
import type { LiveEvent, LiveSession } from '../src/live';

// All transport behavior is deliberately mocked in this isolated regression.
// The dedicated configuration serves source files with no backend API proxy.
const origin = 'http://127.0.0.1:5189';
const project = 'test-only-project';
const processIds = ['process-internal-one', 'process-internal-two'];
const labels = ['server-one: worker-one', 'server-two: worker-two'];
const literal = { include: [], exclude: [], include_mode: 'any' as const, case_sensitive: true };
const reminderText = 'An earlier monitor in this system was interrupted.';
const reportDirectory = resolve(process.env.INSPECTOR_LIVE_NOTICE_REPORT_DIR ?? '../verification/live-events-presentation');
const screenshotDirectory = resolve(reportDirectory, 'screenshots');
type HeldListing = { release: () => void; request: Request };

function event(index: number, processIndex = index % 2): LiveEvent {
  const timestamp = new Date(Date.UTC(2026, 9, 18, 10, 0, index)).toISOString().replace('.000Z', 'Z');
  return {
    schema_version: '1.0', project_id: project, event_id: `synthetic-event-${index}`, process_id: processIds[processIndex], server_id: `server-internal-${processIndex ? 'two' : 'one'}`,
    process_name_snapshot: `worker-${processIndex ? 'two' : 'one'}`, server_name_snapshot: `server-${processIndex ? 'two' : 'one'}`,
    raw_line: `${timestamp} synthetic line ${index + 1}`, timestamp_original: timestamp,
    timestamp_utc: timestamp.replace('Z', '.000000Z'), timestamp_us: null, received_at: '2026-10-18T10:00:01.000000Z', parse_status: 'parsed', metadata: {}, late_arrival: false,
    source: { source_revision_id: `synthetic-source-${processIndex}`, remote_path: '/test-only/app.log', archive_member: null, member_ordinal: null, byte_start: index * 100, byte_end: index * 100 + 44, line_number: index + 1, content_sha256: 'a'.repeat(64) },
  };
}

function interruptedSession(id: string): LiveSession {
  return {
    project_id: project, workspace_id: `historical-workspace-${id}`, session_id: id, lease_revision: 1, filter_version: 1,
    status: 'interrupted', process_ids: [processIds[0]], recording: false, investigation_id: null, layout: 'merged',
    global_filter: literal, per_process_filters: {}, requested_rows: 1, seed_rows_by_process: {}, detached: true,
    snapshot: { events: [], diagnostics: [], counters: {}, sources: [], coverage: {}, filter_version: 1, seq: 0 },
  };
}

async function mockTransport(page: Page, seed: { events: LiveEvent[]; diagnostics?: LiveEvent[] } = { events: processIds.map((_, index) => event(index)) }, historicalSessions: LiveSession[] = []) {
  const starts: components['schemas']['LiveCreateInput'][] = [];
  const filters: components['schemas']['LiveFilterInput'][] = [];
  const mutations: { method: string; path: string }[] = [];
  const unexpected: string[] = [];
  const sockets: WebSocketRoute[] = [];
  const listingHolds: ((listing: HeldListing) => void)[] = [];
  let historical = historicalSessions;
  let session: LiveSession | null = null;
  let seq = 0;
  function holdNextListing() {
    return new Promise<HeldListing>(resolve => { listingHolds.push(resolve); });
  }
  function send(type: string, payload: Record<string, unknown>) {
    if (!session || !sockets.length) throw new Error('Start the synthetic monitor before sending a frame.');
    sockets.at(-1)!.send(JSON.stringify({ protocol_version: 2, project_id: project, workspace_id: session.workspace_id, session_id: session.session_id, filter_version: session.filter_version, type, seq: ++seq, sent_at: '2026-10-18T10:00:02.000000Z', payload }));
  }
  function append(items: LiveEvent[]) {
    if (!session) throw new Error('Start the synthetic monitor before appending test events.');
    const events = [...(session.snapshot.events ?? []), ...items.filter(item => item.timestamp_utc !== null)];
    const diagnostics = [...(session.snapshot.diagnostics ?? []), ...items.filter(item => item.timestamp_utc === null)];
    const counters = { received: events.length + diagnostics.length, retained: events.length + diagnostics.length, matched: events.length + diagnostics.length };
    session.snapshot = { ...session.snapshot, events, diagnostics, counters };
    send('events', { items }); send('counters', { counters });
  }
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) { unexpected.push('External request blocked'); await route.abort(); return; }
    if (!url.pathname.startsWith('/api/')) { await route.continue(); return; }
    const method = route.request().method();
    if (method !== 'GET') mutations.push({ method, path: url.pathname });
    if (url.pathname === '/api/v1/auth/csrf' && method === 'GET') { await route.fulfill({ json: { csrf_token: 'test-only-token' } }); return; }
    const base = `/api/v1/projects/${project}`;
    if (url.pathname === `${base}/usage` && method === 'GET') { await route.fulfill({ json: { project_id: project, workspace_id: url.searchParams.get('workspace_id'), counts: { workspace: session?.process_ids.length ?? 0 }, limits: { workspace: 5 } } }); return; }
    if (url.pathname === `${base}/live-sessions` && method === 'GET') {
      const items = structuredClone([...(session ? [session] : []), ...historical]);
      const hold = listingHolds.shift();
      if (hold) await new Promise<void>(release => { hold({ release, request: route.request() }); });
      await route.fulfill({ json: { project_id: project, items } }); return;
    }
    if (url.pathname === `${base}/live-sessions` && method === 'POST') {
      const input = route.request().postDataJSON() as components['schemas']['LiveCreateInput']; starts.push(input);
      session = {
        project_id: project, workspace_id: input.workspace_id, session_id: `test-only-monitor-${input.workspace_id}-${starts.length}`, lease_revision: 1, filter_version: 1,
        status: 'running', process_ids: input.process_ids, recording: false, investigation_id: null, layout: input.mode,
        global_filter: input.filter, per_process_filters: input.per_process_filters, requested_rows: input.seed_rows,
        seed_rows_by_process: input.seed_rows_by_process, detached: false,
        snapshot: { events: seed.events.filter(item => input.process_ids.includes(item.process_id)), diagnostics: (seed.diagnostics ?? []).filter(item => input.process_ids.includes(item.process_id)), counters: { received: seed.events.length + (seed.diagnostics?.length ?? 0), retained: seed.events.length + (seed.diagnostics?.length ?? 0), matched: seed.events.length + (seed.diagnostics?.length ?? 0) }, sources: input.process_ids.map(process_id => ({ process_id, state: 'reading', seed_status: 'complete' })), coverage: {}, filter_version: 1, seq: 0 },
      };
      await route.fulfill({ json: session }); return;
    }
    if (url.pathname.endsWith('/filters') && method === 'PUT' && session) {
      const input = route.request().postDataJSON() as components['schemas']['LiveFilterInput'];
      filters.push(input);
      session = { ...session, filter_version: session.filter_version + 1, global_filter: input.global_filter ?? literal, per_process_filters: input.per_process_filters ?? {}, requested_rows: input.requested_rows, layout: input.layout, seed_rows_by_process: input.seed_rows_by_process };
      session.snapshot = { ...session.snapshot, filter_version: session.filter_version };
      await route.fulfill({ json: session }); return;
    }
    if (url.pathname.endsWith('/stop') && method === 'POST' && session) {
      session = { ...session, status: 'stopped' }; await route.fulfill({ json: session }); return;
    }
    unexpected.push(`${method} ${url.pathname}`); await route.fulfill({ status: 500, json: { error: { code: 'UNEXPECTED_TEST_REQUEST', message: 'Unexpected API request in test-only harness.' } } });
  });
  await page.routeWebSocket('**/live-sessions/*/stream', socket => {
    sockets.push(socket);
    socket.onMessage(message => {
      const frame = JSON.parse(String(message)) as { type: string };
      if (frame.type === 'hello' && session) send('snapshot', { ...session.snapshot });
    });
  });
  return { starts, filters, mutations, unexpected, sockets, send, append, holdNextListing, setHistoricalSessions: (items: LiveSession[]) => { historical = items; } };
}

test.skip(({ baseURL }) => baseURL !== origin, 'Run only with e2e/live_notices.playwright.config.ts; this fixture must never contact an installed application.');

test.use({ timezoneId: 'America/Los_Angeles' });

test.beforeEach(async ({ page, context }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  context.on('page', extra => extra.on('pageerror', error => errors.push(error.message)));
  Object.assign(page, { testOnlyPageErrors: errors });
});

test.afterEach(async ({ page }) => {
  expect((page as Page & { testOnlyPageErrors: string[] }).testOnlyPageErrors).toEqual([]);
});

async function visitLive(page: Page, reference = false) {
  await page.goto(`/e2e/live_notices.harness.html${reference ? '?reference=1' : ''}`);
  await page.getByRole('button', { name: 'Live monitor', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Live monitor', exact: true })).toBeVisible();
}

async function chooseBoth(page: Page) {
  const choices = page.getByRole('group', { name: 'Processes to monitor', exact: true });
  for (const label of labels) await choices.getByRole('checkbox', { name: label, exact: true }).check();
}

async function revisitLive(page: Page, waitForListing = true) {
  const listing = waitForListing ? page.waitForResponse(response => response.request().method() === 'GET' && response.url().endsWith(`/projects/${project}/live-sessions`)) : null;
  await page.getByRole('button', { name: 'Topology', exact: true }).click();
  await page.getByRole('button', { name: 'Live monitor', exact: true }).click();
  if (listing) { await (await listing).finished(); await flushRendering(page); }
}

async function flushRendering(page: Page) {
  await page.evaluate(() => new Promise<void>(resolve => { requestAnimationFrame(() => requestAnimationFrame(() => resolve())); }));
}

async function finishListing(page: Page, listing: HeldListing) {
  listing.release();
  const response = await listing.request.response();
  if (!response) throw new Error('The delayed synthetic listing did not return a response.');
  await response.finished();
  await flushRendering(page);
}

async function measuredRows(table: Locator): Promise<number> {
  return table.evaluate(element => {
    const heading = element.querySelector<HTMLElement>('[role="row"]')!;
    const row = element.querySelector<HTMLElement>('.live-event') ?? document.querySelector<HTMLElement>('.live-event')!;
    const rowHeight = row.getBoundingClientRect().height;
    return Math.min(500, Math.max(1, Math.ceil((element.clientHeight - heading.offsetHeight) / rowHeight)));
  });
}

async function startSynthetic(page: Page) {
  await chooseBoth(page);
  await page.getByRole('button', { name: 'Monitor selected', exact: true }).click();
  await expect(page.getByText('Stream connected', { exact: true })).toBeVisible();
  await expect(page.getByTestId('live-session-state')).toHaveText('running');
}

async function capturePresentation(page: Page, name: string) {
  mkdirSync(screenshotDirectory, { recursive: true });
  await page.locator('.live-panes').screenshot({ path: resolve(screenshotDirectory, `${name}.png`), animations: 'disabled' });
}

test('live rows match historical density, metadata and safe unwrapped text in both themes', async ({ page }) => {
  const long = event(79);
  const text = '<img src="https://test.invalid/image" onerror="window.syntheticUnsafe=true"> literal=.*[x] <script>window.syntheticUnsafe=true</script>' + ' wide text'.repeat(70);
  long.raw_line = `${long.timestamp_original} ${text}`; long.late_arrival = true;
  const unknown = { ...event(80), event_id: 'synthetic-unknown', timestamp_utc: null, timestamp_original: null, raw_line: '2026-looking-but-unparsed <b>diagnostic remains literal</b>', parse_status: 'unknown' };
  const transport = await mockTransport(page, { events: [...Array.from({ length: 79 }, (_, index) => event(index)), long], diagnostics: [unknown] });
  await visitLive(page, true); await startSynthetic(page);
  const table = page.getByRole('table', { name: 'Merged live logs', exact: true });
  const row = table.locator(`[data-event-id="${long.event_id}"]`);
  const reference = page.getByRole('table', { name: 'Historical presentation reference', exact: true });
  await expect(table).toHaveAttribute('aria-colcount', '4');
  expect(await table.getByRole('columnheader').allTextContents()).toEqual(['Event time UTC', 'Process', 'Host', 'Log entry']);
  await expect(row.locator('.log-timestamp')).toHaveText('2026-10-18 10:01:19');
  await expect(row.getByRole('cell').nth(1)).toHaveText('worker-two');
  await expect(row.getByRole('cell').nth(2)).toHaveText('server-two');
  await expect(row.locator('.live-late')).toContainText('Late arrival');
  expect(await row.locator('.live-message > span').last().textContent()).toBe(` ${text}`);
  expect(await table.locator('img, script, b').count()).toBe(0);
  expect(await page.evaluate(() => Reflect.get(window, 'syntheticUnsafe'))).toBeUndefined();
  const style = async (target: Locator) => target.evaluate(element => {
    const message = element.querySelector<HTMLElement>('.log-message')!; const css = getComputedStyle(message);
    return { height: element.getBoundingClientRect().height, font: css.fontSize, lineHeight: css.lineHeight, padding: css.paddingLeft, wrapping: css.whiteSpace };
  });
  await expect(reference.locator('.log-event')).toBeVisible();
  expect(await style(row)).toEqual(await style(reference.locator('.log-event')));
  expect((await style(row)).height).toBe(20);
  expect((await style(row)).wrapping).toBe('pre');
  expect(await table.evaluate(element => element.scrollWidth > element.clientWidth)).toBe(true);
  await table.evaluate(element => { element.scrollLeft = 240; });
  await expect(table).toHaveJSProperty('scrollLeft', 240);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await table.evaluate(element => { element.scrollLeft = 0; });
  for (const theme of ['light', 'dark']) {
    await page.getByRole('button', { name: `${theme === 'light' ? 'Light' : 'Dark'} test theme`, exact: true }).click();
    await expect(row.locator('.log-timestamp')).toHaveText('2026-10-18 10:01:19');
    await capturePresentation(page, `dense-live-${theme}`);
  }
  await page.getByRole('button', { name: 'Unknown timestamps (1)', exact: true }).click();
  const diagnostic = table.locator('[data-event-id="synthetic-unknown"]');
  await expect(diagnostic.locator('.log-timestamp')).toHaveText('Unknown timestamp');
  await expect(diagnostic.locator('.live-message')).toHaveText(unknown.raw_line);
  await expect(diagnostic.locator('b')).toHaveCount(0);
  await expect(table).toHaveAttribute('aria-rowcount', '2');
  expect(transport.unexpected).toEqual([]);
});

test('compact viewport seeding, following, anchored updates and display pause retain live behavior', async ({ page }) => {
  const transport = await mockTransport(page, { events: Array.from({ length: 100 }, (_, index) => event(index)) });
  await visitLive(page); await startSynthetic(page);
  const table = page.getByRole('table', { name: 'Merged live logs', exact: true });
  expect(transport.starts[0].seed_rows).toBe(await measuredRows(table));
  const distanceFromLatest = () => table.evaluate(element => element.scrollHeight - element.scrollTop - element.clientHeight);
  await expect.poll(distanceFromLatest).toBeLessThanOrEqual(1);
  transport.append([event(100)]);
  await expect(table.locator('[data-event-id="synthetic-event-100"]')).toBeVisible();
  await expect.poll(distanceFromLatest).toBeLessThanOrEqual(1);

  await table.evaluate(element => { element.scrollTop = 407; });
  await expect(table).toHaveJSProperty('scrollTop', 407);
  const anchored = await table.evaluate(element => {
    const top = element.getBoundingClientRect().top + element.querySelector<HTMLElement>('[role="row"]')!.offsetHeight;
    const row = [...element.querySelectorAll<HTMLElement>('.live-event')].find(item => item.getBoundingClientRect().top >= top)!;
    return { id: row.dataset.eventId!, top: row.getBoundingClientRect().top - element.getBoundingClientRect().top };
  });
  const earlier = { ...event(101), event_id: 'synthetic-earlier', timestamp_utc: '2026-10-18T09:59:59.000000Z' };
  transport.append([earlier]);
  await expect(page.getByTestId('live-received')).toHaveText('102');
  const anchor = table.locator(`[data-event-id="${anchored.id}"]`);
  await expect.poll(async () => anchor.evaluate(element => element.getBoundingClientRect().top - element.closest('.live-log-scroll')!.getBoundingClientRect().top)).toBe(anchored.top);
  const frozen = await table.locator('.live-event').evaluateAll(rows => rows.map(row => row.getAttribute('data-event-id')));
  await page.getByRole('button', { name: 'Pause display', exact: true }).click();
  transport.append([event(102)]);
  await expect(page.getByTestId('live-received')).toHaveText('103');
  await expect(page.getByTestId('live-retained')).toHaveText('103');
  expect(await table.locator('.live-event').evaluateAll(rows => rows.map(row => row.getAttribute('data-event-id')))).toEqual(frozen);
  await expect(table.locator('[data-event-id="synthetic-event-102"]')).toHaveCount(0);
  await page.getByRole('button', { name: 'Resume display', exact: true }).click();
  await expect.poll(async () => anchor.evaluate(element => element.getBoundingClientRect().top - element.closest('.live-log-scroll')!.getBoundingClientRect().top)).toBe(anchored.top);
  await page.getByRole('button', { name: 'Jump to latest', exact: true }).click();
  await expect(table.locator('[data-event-id="synthetic-event-102"]')).toBeVisible();
  await expect.poll(distanceFromLatest).toBeLessThanOrEqual(1);
  await expect(page.getByLabel('Live contains string', { exact: true })).toHaveValue('');
  await expect.poll(async () => Number(await page.getByTestId('live-visible').innerText())).toBeGreaterThan(0);
  expect(transport.starts).toHaveLength(1); expect(transport.sockets).toHaveLength(1); expect(transport.unexpected).toEqual([]);
});

test('same-context pages keep compact split panes, viewport seeds and controls independent', async ({ page, context }) => {
  const seed = { events: Array.from({ length: 80 }, (_, index) => event(index)) };
  const first = await mockTransport(page, seed);
  await visitLive(page); await chooseBoth(page);
  await page.getByLabel('Live pane layout', { exact: true }).selectOption('split');
  await expect(page.locator('.live-log-scroll')).toHaveCount(2);
  await page.locator('.live-log-scroll').nth(0).evaluate(element => { (element as HTMLElement).style.height = '420px'; });
  await page.locator('.live-log-scroll').nth(1).evaluate(element => { (element as HTMLElement).style.height = '150px'; });
  await startSynthetic(page);
  const tables = page.locator('.live-log-scroll');
  const expected = { [processIds[0]]: await measuredRows(tables.nth(0)), [processIds[1]]: await measuredRows(tables.nth(1)) };
  expect(first.starts[0].seed_rows_by_process).toEqual(expected);
  for (let index = 0; index < labels.length; index += 1) {
    const table = page.getByRole('table', { name: `${labels[index]} live logs`, exact: true });
    expect(await table.getByRole('columnheader').allTextContents()).toEqual(['Event time UTC', 'Process', 'Host', 'Log entry']);
    await expect(table.locator('.log-event').first()).toHaveCSS('height', '20px');
  }
  const second = await context.newPage();
  const other = await mockTransport(second, seed);
  await visitLive(second); await startSynthetic(second);
  expect(first.starts[0].workspace_id).not.toBe(other.starts[0].workspace_id);
  expect(await page.getByTestId('live-session-id').innerText()).not.toBe(await second.getByTestId('live-session-id').innerText());
  await expect(second.locator('.live-panes')).toHaveClass(/merged/);
  await expect(second.locator('.live-log-scroll')).toHaveCount(1);
  const otherVersion = await second.getByTestId('live-filter-version').innerText();
  await page.getByLabel('Live contains string', { exact: true }).fill('only-first-page');
  await expect.poll(() => first.filters.at(-1)?.global_filter?.include).toEqual(['only-first-page']);
  await expect(page.getByText(/Applied version/)).toBeVisible();
  await expect(second.getByTestId('live-filter-version')).toHaveText(otherVersion);
  await expect(second.getByLabel('Live contains string', { exact: true })).toHaveValue('');
  await page.getByRole('button', { name: 'Stop this monitor', exact: true }).click();
  await expect(page.getByTestId('live-session-state')).toHaveText('stopped');
  await expect(second.getByTestId('live-session-state')).toHaveText('running');
  await expect(second.getByRole('button', { name: 'Stop this monitor', exact: true })).toBeEnabled();
  other.append([{ ...event(81), raw_line: '2026-10-18T10:01:21Z SECOND-PAGE-SURVIVES' }]);
  await expect(second.locator('.live-message').filter({ hasText: 'SECOND-PAGE-SURVIVES' })).toBeVisible();
  await expect(page.locator('.live-message').filter({ hasText: 'SECOND-PAGE-SURVIVES' })).toHaveCount(0);
  await capturePresentation(page, 'split-live-independent-stopped');
  expect(first.unexpected).toEqual([]); expect(other.unexpected).toEqual([]);
  expect(first.starts).toHaveLength(1); expect(other.starts).toHaveLength(1);
  await second.close();
});

test('visiting Live, choosing sources and returning from another tab require an explicit monitor action', async ({ page }) => {
  const transport = await mockTransport(page);
  await visitLive(page);
  await chooseBoth(page);
  await page.getByRole('button', { name: 'Topology', exact: true }).click();
  await page.getByRole('button', { name: 'Live monitor', exact: true }).click();
  await expect(page.locator('.live-selection > summary')).toHaveText('Process selection');
  expect(transport.starts).toEqual([]); expect(transport.sockets).toHaveLength(0);
  await page.getByRole('button', { name: 'Monitor selected', exact: true }).click();
  await expect(page.getByTestId('live-session-state')).toHaveText('running');
  await expect.poll(() => transport.sockets.length).toBe(1);
  await expect(page.locator('.live-selection > summary')).toHaveText('Process selection (monitoring 2)');
  expect(transport.starts).toHaveLength(1); expect(transport.starts[0].process_ids).toEqual(processIds);
  await page.getByRole('button', { name: 'Topology', exact: true }).click();
  await page.getByRole('button', { name: 'Live monitor', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Stop this monitor', exact: true })).toBeEnabled();
  await expect(page.getByRole('status').filter({ hasText: /^Test page capture active$/ })).toBeVisible();
  expect(transport.starts).toHaveLength(1); expect(transport.sockets).toHaveLength(1); expect(transport.unexpected).toEqual([]);
});

test('earlier interrupted monitors have a page-local dismissible reminder; new interrupted IDs remain visible', async ({ page, context }) => {
  const earlier = interruptedSession('test-only-earlier-monitor');
  const transport = await mockTransport(page, undefined, [earlier]);
  await visitLive(page);
  const reminder = page.locator('.live-interrupted-notice');
  await expect(reminder).toContainText(reminderText);
  await expect(reminder).toContainText(`System: Synthetic test system (${project})`);
  await expect(page.getByTestId('live-session-id')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Monitor', exact: true })).toBeEnabled();
  expect(transport.starts).toEqual([]); expect(transport.mutations).toEqual([]); expect(transport.sockets).toHaveLength(0);
  mkdirSync(screenshotDirectory, { recursive: true });
  for (const theme of ['light', 'dark']) {
    await page.getByRole('button', { name: `${theme === 'light' ? 'Light' : 'Dark'} test theme`, exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    await page.screenshot({ path: resolve(screenshotDirectory, `live-interrupted-reminder-${theme}.png`), fullPage: true, animations: 'disabled' });
  }

  const second = await context.newPage();
  const other = await mockTransport(second, undefined, [earlier]);
  await visitLive(second);
  await expect(second.locator('.live-interrupted-notice')).toContainText(reminderText);

  const pending = transport.holdNextListing();
  await revisitLive(page, false);
  const delayed = await pending;
  await reminder.getByRole('button', { name: 'Dismiss previous monitor notice', exact: true }).click();
  await expect(reminder).toHaveCount(0);
  await expect(second.locator('.live-interrupted-notice')).toBeVisible();
  await finishListing(page, delayed);
  await expect(reminder).toHaveCount(0);
  await revisitLive(page);
  await expect(reminder).toHaveCount(0);

  transport.setHistoricalSessions([interruptedSession('test-only-newly-interrupted-monitor'), earlier]);
  await revisitLive(page);
  await expect(reminder).toContainText(reminderText);
  await reminder.getByRole('button', { name: 'Dismiss previous monitor notice', exact: true }).click();
  await expect(reminder).toHaveCount(0);
  await revisitLive(page);
  await expect(reminder).toHaveCount(0);
  expect(transport.starts).toEqual([]); expect(transport.mutations).toEqual([]); expect(transport.sockets).toHaveLength(0);
  expect(transport.unexpected).toEqual([]); expect(other.mutations).toEqual([]); expect(other.unexpected).toEqual([]);
  await second.close();
});

test('explicit monitoring clears the historical reminder, ignores delayed listings and starts a fresh ID after stop', async ({ page }) => {
  const transport = await mockTransport(page, undefined, [interruptedSession('test-only-interrupted-before-start')]);
  await visitLive(page);
  const reminder = page.locator('.live-interrupted-notice');
  await expect(reminder).toContainText(reminderText);
  expect(transport.starts).toEqual([]); expect(transport.mutations).toEqual([]);

  const pending = transport.holdNextListing();
  await revisitLive(page, false);
  const delayed = await pending;
  await startSynthetic(page);
  const firstId = await page.getByTestId('live-session-id').innerText();
  expect(firstId).not.toBe(project);
  await expect(reminder).toHaveCount(0);
  await finishListing(page, delayed);
  await expect(reminder).toHaveCount(0);
  await revisitLive(page);
  await expect(reminder).toHaveCount(0);
  await expect(page.getByTestId('live-session-id')).toHaveText(firstId);
  expect(transport.starts).toHaveLength(1);

  transport.send('gap', { process_id: processIds[0], reason: 'TRANSPORT_DISCONNECTED' });
  const gap = page.locator('.live-notice:not(.live-interrupted-notice)').filter({ hasText: 'TRANSPORT_DISCONNECTED' });
  await expect(gap).toContainText('Continuity gap');
  await expect(gap).toContainText('some log entries may be missing');
  await revisitLive(page);
  await expect(gap).toContainText('TRANSPORT_DISCONNECTED');
  await expect(reminder).toHaveCount(0);

  await page.getByRole('button', { name: 'Stop this monitor', exact: true }).click();
  await expect(page.getByTestId('live-session-state')).toHaveText('stopped');
  await expect(gap).toContainText('TRANSPORT_DISCONNECTED');
  await revisitLive(page);
  await expect(page.getByTestId('live-session-id')).toHaveText(firstId);
  expect(transport.starts).toHaveLength(1);
  await startSynthetic(page);
  await expect(page.getByTestId('live-session-id')).not.toHaveText(firstId);
  await expect(reminder).toHaveCount(0);
  await expect(gap).toHaveCount(0);
  expect(transport.starts).toHaveLength(2);
  expect(transport.mutations.filter(item => item.path.endsWith('/stop'))).toHaveLength(1);
  expect(transport.mutations.filter(item => item.path.endsWith('/attach'))).toHaveLength(0);
  expect(transport.unexpected).toEqual([]);
});

test('process choices, filters, pane headings, source details and copied rows use server: process names', async ({ page }) => {
  const transport = await mockTransport(page);
  await visitLive(page); await chooseBoth(page);
  await page.getByLabel('Live pane layout', { exact: true }).selectOption('split');
  await page.getByRole('button', { name: 'Monitor selected', exact: true }).click();
  await expect(page.locator('.live-event')).toHaveCount(2);
  for (const label of labels) {
    await expect(page.getByRole('table', { name: `${label} live logs`, exact: true })).toBeVisible();
    await expect(page.getByRole('list', { name: 'Live source states', exact: true })).toContainText(label);
  }
  await page.getByText('Per-process literal filters', { exact: true }).click();
  for (const label of labels) await expect(page.getByLabel(`${label} Live contains string`, { exact: true })).toBeVisible();
  await page.getByText('Source access, seed coverage and continuity', { exact: true }).click();
  for (const label of labels) await expect(page.locator('.live-source-status')).toContainText(label);
  const visible = await page.locator('body').innerText();
  for (const id of processIds) expect(visible).not.toContain(id);
  await page.getByRole('button', { name: 'Copy retained view', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Copied retained view', exact: true })).toBeVisible();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  for (const label of labels) expect(copied).toContain(label);
  for (const id of processIds) expect(copied).not.toContain(id);
  expect(transport.starts).toHaveLength(1); expect(transport.unexpected).toEqual([]);
});

test('source interruption and code-only stream failure retain useful notices and stop claiming active monitoring', async ({ page }) => {
  const transport = await mockTransport(page);
  await visitLive(page); await chooseBoth(page);
  await page.getByRole('button', { name: 'Monitor selected', exact: true }).click();
  await expect(page.locator('.live-event')).toHaveCount(2);
  await expect.poll(() => transport.sockets.length).toBe(1);
  transport.send('gap', { process_id: processIds[1], reason: 'TRANSPORT_DISCONNECTED' });
  const gap = page.locator('.live-notice').filter({ hasText: 'TRANSPORT_DISCONNECTED' });
  await expect(gap).toContainText(labels[1]);
  await expect(gap).toContainText('Reading the log source was interrupted; some log entries may be missing. This does not indicate process health.');
  transport.send('error', { code: 'LIVE_GUARD_FAILED' });
  const error = page.getByRole('alert');
  await expect(error).toContainText('The live stream reported an error.');
  await expect(error).toContainText('LIVE_GUARD_FAILED');
  transport.send('stopped', { reason: 'LIVE_GUARD_FAILED' });
  await expect(page.getByTestId('live-session-state')).toHaveText('stopped');
  await expect(page.locator('.live-selection > summary')).toHaveText('Process selection (previous monitor: 2 sources)');
  await expect(page.getByRole('button', { name: 'Stop this monitor', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Monitor selected', exact: true })).toBeEnabled();
  mkdirSync(screenshotDirectory, { recursive: true });
  for (const theme of ['light', 'dark']) {
    await page.getByRole('button', { name: `${theme === 'light' ? 'Light' : 'Dark'} test theme`, exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    await page.screenshot({ path: resolve(screenshotDirectory, `live-notices-test-only-${theme}.png`), fullPage: true, animations: 'disabled' });
  }
  await page.getByRole('button', { name: 'Topology', exact: true }).click();
  await page.getByRole('button', { name: 'Live monitor', exact: true }).click();
  await expect(error).toContainText('LIVE_GUARD_FAILED'); await expect(gap).toContainText('TRANSPORT_DISCONNECTED');
  expect(transport.starts).toHaveLength(1); expect(transport.unexpected).toEqual([]);
});
