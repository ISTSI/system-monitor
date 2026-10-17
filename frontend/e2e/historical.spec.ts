import { test, expect, type Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { serveBuiltAssets, setAppearance, submitSignIn } from './ui';
import type { components } from '../src/api/schema';

type Query = components['schemas']['HistoricalQueryInput'];
type Results = components['schemas']['HistoricalQueryResponse'];
type Role = 'administrator' | 'inspector';
const systemA = 'stage3-fixture-a'; const systemB = 'stage3-fixture-b';
const from = '2026-10-16T12:00:00.000000Z'; const to = '2026-10-16T12:00:02.000000Z';
const displayUtc = (value: string) => value.slice(0, 19).replace('T', ' ');
const cases = JSON.parse(readFileSync(resolve('../fixtures/expected/query-cases.json'), 'utf8')) as { id: string; request: Query; expected_event_ids: string[] }[];
const events = JSON.parse(readFileSync(resolve('../fixtures/expected/events.json'), 'utf8')) as components['schemas']['HistoricalQueryResponse']['items'];
const timestampedEvents = events.filter(event => event.timestamp_utc !== null && event.timestamp_utc >= from && event.timestamp_utc < to);
const errors = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page, context, baseURL }) => {
  const found: string[] = []; errors.set(page, found); page.on('pageerror', error => found.push(error.message));
  if (process.env.INSPECTOR_E2E_LOCAL_ASSETS === '1') await serveBuiltAssets(context, baseURL!);
});
test.afterEach(async ({ page, baseURL }) => {
  try { expect(errors.get(page)).toEqual([]); } finally {
    // Closing a page retains its workspace for reconnect. Authenticated logout
    // releases only this synthetic account's leases before the next test.
    if ((await page.request.get('/api/v1/auth/session')).status() === 200) {
      const response = await page.request.get('/api/v1/auth/csrf');
      expect(response.status()).toBe(200);
      const { csrf_token } = await response.json() as { csrf_token: string };
      const loggedOut = await page.request.post('/api/v1/auth/logout', {
        headers: { Origin: new URL(baseURL!).origin, 'X-CSRF-Token': csrf_token }, data: {},
      });
      expect(loggedOut.status()).toBe(200);
    }
  }
});

async function login(page: Page, role: Role) {
  const filename = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!filename) throw new Error('Protected synthetic-account fixture is required.');
  const accounts = JSON.parse(readFileSync(resolve(filename), 'utf8')) as Record<Role, { username: string; password: string }>;
  await page.goto('/');
  await page.getByLabel('Username', { exact: true }).fill(accounts[role].username);
  await page.getByLabel('Password', { exact: true }).fill(accounts[role].password);
  const result = await submitSignIn(page);
  if (result.status() !== 200) { await page.locator('input[type="password"]').fill(''); throw new Error(`Synthetic sign-in returned ${result.status()}; protected details withheld.`); }
  await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
}

async function open(page: Page, id = systemA) {
  await page.goto(`/systems/${id}/logs`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await expect(page.getByRole('heading', { name: 'Historical investigation', exact: true })).toBeVisible();
}

async function collect(page: Page, preview = true) {
  const processes = page.getByRole('group', { name: 'Configured processes' }).getByRole('checkbox');
  expect(await processes.count()).toBe(5);
  for (const process of await processes.all()) await process.check();
  await page.getByLabel('From UTC (inclusive)', { exact: true }).fill(displayUtc(from));
  await page.getByLabel('To UTC (exclusive)', { exact: true }).fill(displayUtc(to));
  await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toHaveCount(0);
  if (preview) {
    await page.getByRole('button', { name: 'Preview collection plan', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toContainText('SYNTHETIC LOCAL FIXTURES');
    await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toContainText('zip');
    await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toContainText('tar.gz');
  }
  const loaded = page.waitForResponse(result => result.url().endsWith('/query') && result.request().method() === 'POST');
  await page.getByRole('button', { name: 'Collect sources', exact: true }).click();
  await expect(page.getByTestId('collection-state')).toHaveText('completed', { timeout: 30000 });
  const response = await loaded;
  expect(response.status()).toBe(200);
  const results = await response.json() as Results;
  expect(results.matched_count).toBe(timestampedEvents.length);
  expect(results.items.map(event => event.event_id).sort()).toEqual(timestampedEvents.map(event => event.event_id).sort());
  await expect(page.getByRole('button', { name: 'Timestamped events', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('match-count')).toHaveText(`${timestampedEvents.length} matches`);
  await expect(page.locator('.virtual-logs .log-event').first()).toBeVisible();
  if (!preview) await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Collection progress', exact: true })).toContainText('complete_for_scanned_candidates');
  await expect(page).toHaveURL(/\/investigations\/[^/]+$/);
  return await page.getByTestId('investigation-id').innerText();
}

async function apply(page: Page, input: Query) {
  await page.getByLabel('From UTC (inclusive)', { exact: true }).fill(displayUtc(input.from));
  await page.getByLabel('To UTC (exclusive)', { exact: true }).fill(displayUtc(input.to));
  await page.getByLabel('Contains string', { exact: true }).fill(input.filter?.include?.[0] ?? '');
  const advanced = page.locator('.advanced-filter').first();
  if (!(await advanced.evaluate(element => element.hasAttribute('open')))) await advanced.locator('summary').click();
  await page.getByLabel('Additional include terms (one per line)', { exact: true }).fill(input.filter?.include?.slice(1).join('\n') ?? '');
  await page.getByLabel('Exclude terms (one per line)', { exact: true }).fill(input.filter?.exclude?.join('\n') ?? '');
  await page.getByLabel('Include mode', { exact: true }).selectOption(input.filter?.include_mode ?? 'any');
  await page.getByLabel('Case sensitive', { exact: true }).setChecked(input.filter?.case_sensitive ?? true);
  const personal = page.locator('.advanced-filter').nth(1);
  if (!(await personal.evaluate(element => element.hasAttribute('open')))) await personal.locator('summary').click();
  const configuration = JSON.parse(readFileSync(resolve('../examples/project.example.json'), 'utf8')) as { processes: { id: string; name: string }[] };
  for (const process of configuration.processes) {
    await page.getByLabel(`Contains string for ${process.name}`, { exact: true }).fill(input.per_process_filters?.[process.id]?.include?.[0] ?? '');
    await page.getByLabel(`Exclude string for ${process.name}`, { exact: true }).fill(input.per_process_filters?.[process.id]?.exclude?.[0] ?? '');
  }
  const response = page.waitForResponse(result => result.url().endsWith('/query') && result.request().method() === 'POST');
  await page.getByRole('button', { name: 'Apply filter', exact: true }).click();
  const result = await response;
  expect(result.status()).toBe(200);
  const body = await result.json() as Results;
  await expect(page.getByTestId('match-count')).toHaveText(`${body.matched_count} matches`);
  return body;
}

function golden(id: string) { const value = cases.find(item => item.id === id); if (!value) throw new Error('Missing fixture case.'); return value; }
async function capture(page: Page, name: string, fullPage = false) {
  const directory = resolve(`../verification/${process.env.INSPECTOR_E2E_REPORT_STAGE ?? 'stage-3'}/screenshots`); mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: resolve(directory, `${name}.png`), animations: 'disabled', fullPage });
  const metadataFile = resolve(directory, 'capture-metadata.json');
  const metadata = existsSync(metadataFile) ? JSON.parse(readFileSync(metadataFile, 'utf8')) as Record<string, unknown> : {};
  metadata[`${name}.png`] = { viewport: page.viewportSize(), full_page: fullPage };
  writeFileSync(metadataFile, JSON.stringify(metadata, null, 2) + '\n');
}

test('Inspector collects real plain/ZIP/TAR fixtures, refilters literal Unicode text, and inspects source context', async ({ page, context }) => {
  test.setTimeout(180000);
  const external: string[] = [];
  context.on('request', request => { const url = new URL(request.url()); if (url.protocol.startsWith('http') && url.origin !== new URL(process.env.INSPECTOR_E2E_URL ?? 'https://localhost:8445').origin) external.push(url.origin); });
  await login(page, 'inspector'); await open(page); const investigation = await collect(page);
  await expect(page.getByRole('button', { name: 'Add process', exact: true })).toHaveCount(0);
  for (const id of ['literal-correlation-substring', 'include-all', 'include-any', 'exclude-overrides', 'regex-looking-is-literal', 'sql-looking-is-literal', 'unicode-casefold', 'case-sensitive-miss', 'generated-prefix-excluded', 'duplicate-text-retained', 'per-process-filter', 'filename-not-authority', 'markup-plain-text']) {
    const fixture = golden(id); const body = await apply(page, fixture.request);
    expect(body.items.map(event => event.event_id), id).toEqual(fixture.expected_event_ids);
  }
  expect(await page.locator('.log-message b').count()).toBe(0);
  const emoji512 = '\u{1f642}'.repeat(512); const emoji513 = emoji512 + '\u{1f642}';
  const unicodeQuery: Query = { ...golden('literal-correlation-substring').request, filter: { include: [emoji512], include_mode: 'all', exclude: [], case_sensitive: true } };
  expect((await apply(page, unicodeQuery)).matched_count).toBe(0);
  async function rejectsOversizedTerm(label: string) {
    let sent = 0; const count = (request: { url: () => string }) => { if (request.url().endsWith('/query')) sent += 1; };
    page.on('request', count);
    try {
      await page.getByLabel(label, { exact: true }).fill(emoji513);
      await page.getByRole('button', { name: 'Apply filter', exact: true }).click();
      await expect(page.getByRole('alert')).toContainText('512 Unicode characters');
      expect(sent).toBe(0);
    } finally { page.off('request', count); }
  }
  await rejectsOversizedTerm('Contains string');
  const unicodeProcessQuery: Query = { ...unicodeQuery, filter: { include: ['phase=accepted'], include_mode: 'all', exclude: [], case_sensitive: true }, per_process_filters: { 'p-ingest-a': { include: [emoji512], include_mode: 'all', exclude: [], case_sensitive: true } } };
  expect((await apply(page, unicodeProcessQuery)).matched_count).toBe(0);
  await rejectsOversizedTerm('Contains string for ingest-instance-a');
  const csrf = await page.request.get('/api/v1/auth/csrf');
  const headers = { Origin: new URL(page.url()).origin, 'X-CSRF-Token': (await csrf.json() as { csrf_token: string }).csrf_token };
  for (const body of [unicodeQuery, unicodeProcessQuery]) {
    const accepted = await page.request.post(`/api/v1/projects/${systemA}/investigations/${investigation}/query`, { headers, data: body }); expect(accepted.status()).toBe(200);
    const invalid = structuredClone(body);
    if (Object.keys(invalid.per_process_filters ?? {}).length) invalid.per_process_filters!['p-ingest-a'].include = [emoji513];
    else invalid.filter!.include = [emoji513];
    const rejected = await page.request.post(`/api/v1/projects/${systemA}/investigations/${investigation}/query`, { headers, data: invalid }); expect(rejected.status()).toBe(422);
  }
  await page.getByLabel('Rows per result page', { exact: true }).selectOption('10');
  const fixture = golden('literal-correlation-substring');
  const firstPage = await apply(page, fixture.request);
  expect(firstPage.items.map(event => event.event_id)).toEqual(fixture.expected_event_ids.slice(0, 10));
  const nextResponse = page.waitForResponse(result => result.url().endsWith('/query') && result.request().method() === 'POST');
  await page.getByRole('button', { name: 'Next result page', exact: true }).click();
  const nextPage = await (await nextResponse).json() as Results;
  expect(nextPage.items.map(event => event.event_id)).toEqual(fixture.expected_event_ids.slice(10));
  await expect(page.getByRole('button', { name: 'Next result page', exact: true })).toBeDisabled();
  const previousResponse = page.waitForResponse(result => result.url().endsWith('/query') && result.request().method() === 'POST');
  await page.getByRole('button', { name: 'Previous result page', exact: true }).click();
  const previousPage = await (await previousResponse).json() as Results;
  expect(previousPage.items.map(event => event.event_id)).toEqual(fixture.expected_event_ids.slice(0, 10));
  await page.getByLabel('Rows per result page', { exact: true }).selectOption('0');
  await apply(page, { ...golden('literal-correlation-substring').request, filter: { include: ['phase=accepted'], include_mode: 'all', exclude: [], case_sensitive: true } });
  await page.locator('.virtual-logs').scrollIntoViewIfNeeded();
  await expect(page.locator('.virtual-logs')).toHaveJSProperty('scrollLeft', 0);
  await expect(page.getByRole('button', { name: 'Inspect source line 2 from ingest-instance-a', exact: true })).toBeInViewport();
  await page.getByRole('button', { name: 'Inspect source line 2 from ingest-instance-a', exact: true }).click();
  const drawer = page.getByRole('dialog', { name: 'Event provenance and source context' });
  const accepted = events.find(event => event.process_id === 'p-ingest-a' && event.source.line_number === 2 && event.source.archive_member === null)!;
  await expect(drawer.locator('.event-raw')).toHaveText(accepted.raw_line);
  await expect(drawer).toContainText('byte [66, 146)');
  await expect(drawer.locator('.source-context')).toContainText('Outside time bounds');
  await expect(drawer.locator('.source-context')).toContainText('Outside literal filter');
  await expect(drawer.locator('.source-context')).toContainText('noise=heartbeat');
  const waiting = page.waitForEvent('download'); await drawer.getByRole('button', { name: 'Download captured source', exact: true }).click();
  const downloaded = await waiting; const source = readFileSync((await downloaded.path())!);
  expect(createHash('sha256').update(source).digest('hex')).toBe('3e025a80a6cde6ac72c9ca4149156cd644e8138163fde42ad832b0c37aa93081');
  await capture(page, 'inspector-source-context');
  await page.keyboard.press('Escape');
  await expect(drawer).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Inspect source line 2 from ingest-instance-a', exact: true })).toBeFocused();
  await expect(page.locator('.virtual-logs')).toHaveJSProperty('scrollLeft', 0);
  for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(size);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await page.getByRole('button', { name: 'Inspect source line 2 from ingest-instance-a', exact: true }).click();
      await expect(drawer.locator('.source-context')).toContainText('Outside time bounds');
      await capture(page, `inspector-provenance-${theme}-${size.width}x${size.height}`);
      await drawer.locator('.source-context').scrollIntoViewIfNeeded();
      await capture(page, `inspector-context-${theme}-${size.width}x${size.height}`);
      await drawer.getByRole('button', { name: 'Close dialog', exact: true }).click();
    }
  }
  await page.getByRole('button', { name: 'Clear filter', exact: true }).click();
  await page.getByRole('button', { name: /^Diagnostic lane/ }).click();
  await expect(page.getByTestId('match-count')).toContainText('diagnostic records');
  await expect(page.locator('.virtual-logs')).toContainText('NOT_A_TIMESTAMP');
  await expect(page.locator('.virtual-logs')).toContainText('Unknown timestamp');
  await capture(page, 'inspector-diagnostics');
  for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(size);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await page.getByTestId('match-count').scrollIntoViewIfNeeded();
      await capture(page, `inspector-diagnostics-${theme}-${size.width}x${size.height}`);
    }
  }
  await page.getByRole('button', { name: 'Timestamped events', exact: true }).click();
  const merged = await apply(page, golden('literal-correlation-substring').request);
  expect(merged.items.every(event => event.timestamp_utc !== null && event.timestamp_utc >= from && event.timestamp_utc < to)).toBe(true);
  for (const drawer of await page.locator('.advanced-filter').all()) if (await drawer.evaluate(element => element.hasAttribute('open'))) await drawer.locator('summary').click();
  await expect(page.locator('.virtual-logs')).toHaveJSProperty('scrollLeft', 0);
  for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(size);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await page.getByTestId('match-count').scrollIntoViewIfNeeded();
      await capture(page, `inspector-merged-${theme}-${size.width}x${size.height}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
    }
  }
  await page.getByLabel('Result layout', { exact: true }).selectOption('split');
  await expect(page.locator('.history-split > section')).toHaveCount(5);
  await capture(page, 'inspector-five-process-panes');
  for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(size);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await expect(page.getByTestId('match-count')).toHaveText('18 matches');
      await capture(page, `inspector-five-panes-${theme}-${size.width}x${size.height}-full-page`, true);
      const panes = page.locator('.history-split > section');
      for (let index = 0; index < 5; index += 1) {
        await panes.nth(index).scrollIntoViewIfNeeded();
        await capture(page, `inspector-split-pane-${index + 1}-${theme}-${size.width}x${size.height}`);
      }
    }
  }
  await page.reload(); await expect(page.getByTestId('investigation-id')).toHaveText(investigation);
  await expect(page.getByTestId('match-count')).toHaveText(`${timestampedEvents.length} matches`);
  await expect(page.locator('.virtual-logs .log-event').first()).toBeVisible();
  await expect(page.getByLabel('From UTC (inclusive)', { exact: true })).toHaveValue(displayUtc(from));
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await expect(page.getByRole('button', { name: 'Preview collection plan', exact: true })).toBeEnabled();
  expect(external).toEqual([]);
});

test('same-account pages isolate different/same-system history and reject forged jobs, cursors and downloads', async ({ page, context }) => {
  test.setTimeout(180000);
  await login(page, 'administrator'); await open(page); const first = await collect(page);
  const firstWorkspace = await page.getByTestId('workspace-id').innerText();
  const other = await context.newPage(); const otherErrors: string[] = []; other.on('pageerror', error => otherErrors.push(error.message)); await open(other, systemB); const second = await collect(other);
  expect(await other.getByTestId('workspace-id').innerText()).not.toBe(firstWorkspace);
  await apply(page, golden('unicode-casefold').request);
  await apply(other, golden('duplicate-text-retained').request);
  await expect(page.getByLabel('Contains string', { exact: true })).toHaveValue('STRASSE');
  await expect(page.getByTestId('match-count')).toHaveText('1 matches');
  const origin = new URL(page.url()).origin;
  const csrfResponse = await page.request.get('/api/v1/auth/csrf');
  const headers = { Origin: origin, 'X-CSRF-Token': (await csrfResponse.json() as { csrf_token: string }).csrf_token };
  const request = { ...golden('literal-correlation-substring').request, limit: 1 };
  const result = await page.request.post(`/api/v1/projects/${systemA}/investigations/${first}/query`, { headers, data: request });
  expect(result.status()).toBe(200); const body = await result.json() as Results; expect(body.next_cursor).toBeTruthy();
  const forgedJob = await page.request.get(`/api/v1/projects/${systemB}/investigations/${first}`); expect(forgedJob.status()).toBe(404);
  const forgedQuery = await page.request.post(`/api/v1/projects/${systemB}/investigations/${second}/query`, { headers, data: { ...request, cursor: body.next_cursor } }); expect(forgedQuery.status()).toBe(404);
  const event = body.items[0];
  const grant = await page.request.post(`/api/v1/projects/${systemA}/investigations/${first}/sources/${event.source.source_revision_id}/download`, { headers, data: {} });
  expect(grant.status()).toBe(200); const download = await grant.json() as components['schemas']['HistoricalDownloadResponse'];
  const forgedDownload = await page.request.get(`/api/v1/projects/${systemB}/downloads/${download.download_id}`); expect(forgedDownload.status()).toBe(404);
  const duplicate = await context.newPage(); const duplicateErrors: string[] = []; duplicate.on('pageerror', error => duplicateErrors.push(error.message)); await duplicate.goto(page.url());
  await expect(duplicate.getByTestId('investigation-id')).toHaveText(first);
  expect(await duplicate.getByTestId('workspace-id').innerText()).not.toBe(firstWorkspace);
  await expect(duplicate.getByLabel('Contains string', { exact: true })).toHaveValue('');
  await apply(duplicate, golden('duplicate-text-retained').request);
  await expect(page.getByTestId('match-count')).toHaveText('1 matches');
  await expect(page.getByLabel('Contains string', { exact: true })).toHaveValue('STRASSE');
  for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(size);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await page.locator('.advanced-filter').first().scrollIntoViewIfNeeded();
      await capture(page, `administrator-filter-${theme}-${size.width}x${size.height}`);
      await expect(page.getByLabel('Contains string', { exact: true })).toHaveValue('STRASSE');
      await expect(other.getByLabel('Contains string', { exact: true })).toHaveValue('phase=retried');
      await expect(duplicate.getByLabel('Contains string', { exact: true })).toHaveValue('phase=retried');
    }
  }
  expect(otherErrors).toEqual([]); expect(duplicateErrors).toEqual([]);
  await other.close(); await duplicate.close();
  await expect(page.getByTestId('investigation-id')).toHaveText(first);
});

test('direct collection loads log entries, reopens retained results, and deletes only the confirmed collection', async ({ page, context }) => {
  test.setTimeout(180000);
  await login(page, 'inspector'); await open(page);
  let previews = 0;
  const countPreview = (request: { url: () => string }) => { if (request.url().endsWith('/collections/plan')) previews += 1; };
  page.on('request', countPreview);
  const first = await collect(page, false);
  expect(previews).toBe(0);
  await expect(page.getByRole('columnheader', { name: 'Log entry', exact: true })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Original text', exact: true })).toHaveCount(0);
  const accepted = events.find(event => event.process_id === 'p-ingest-a' && event.source.line_number === 2 && event.source.archive_member === null)!;
  const inspect = page.getByRole('button', { name: 'Inspect source line 2 from ingest-instance-a', exact: true });
  const row = page.getByRole('row').filter({ has: inspect });
  expect(await row.locator('.log-message').textContent()).toBe(accepted.raw_line.slice(accepted.timestamp_original!.length));
  await inspect.click();
  const source = page.getByRole('dialog', { name: 'Event provenance and source context', exact: true });
  await expect(source.locator('.event-raw')).toHaveText(accepted.raw_line);
  await source.getByRole('button', { name: 'Close dialog', exact: true }).click();

  // A second page shares the account and system but owns independent results.
  const other = await context.newPage();
  const otherErrors: string[] = []; other.on('pageerror', error => otherErrors.push(error.message));
  try {
    await open(other);
    const second = await collect(other, false);
    expect(second).not.toBe(first);
    const otherWorkspace = await other.getByTestId('workspace-id').innerText();
    await apply(other, golden('unicode-casefold').request);
    await expect(other.getByTestId('match-count')).toHaveText('1 matches');

    await open(page);
    await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toHaveCount(0);
    await page.getByLabel('Open your retained collection', { exact: true }).selectOption(first);
    await expect(page.getByTestId('investigation-id')).toHaveText(first);
    await expect(page.getByTestId('match-count')).toHaveText(`${timestampedEvents.length} matches`);
    await expect(page.locator('.virtual-logs .log-event').first()).toBeVisible();
    expect(previews).toBe(0);

    const remove = page.getByRole('region', { name: 'Collection progress', exact: true }).getByRole('button', { name: 'Delete collection', exact: true });
    await remove.click();
    const confirmation = page.getByRole('dialog', { name: 'Delete retained collection', exact: true });
    await expect(confirmation).toContainText(systemA);
    await expect(confirmation).toContainText(first);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await expect(confirmation).toBeVisible();
      await capture(page, `inspector-delete-collection-confirmation-${theme}`);
    }
    await confirmation.getByRole('button', { name: 'Keep collection', exact: true }).click();
    await expect(confirmation).toHaveCount(0);
    expect((await page.request.get(`/api/v1/projects/${systemA}/investigations/${first}`)).status()).toBe(200);
    await expect(page.getByTestId('match-count')).toHaveText(`${timestampedEvents.length} matches`);

    await remove.click();
    const deletion = page.waitForResponse(response => response.url().endsWith(`/investigations/${first}`) && response.request().method() === 'DELETE');
    await confirmation.getByRole('button', { name: 'Delete collection', exact: true }).click();
    const deleted = await deletion;
    expect(deleted.status()).toBe(200);
    expect(await deleted.json()).toEqual({ project_id: systemA, investigation_id: first, cache_cleanup_pending: false });
    await expect(confirmation).toHaveCount(0);
    await expect(page).toHaveURL(new RegExp(`/systems/${systemA}/logs$`));
    await expect(page.getByTestId('investigation-id')).toHaveCount(0);
    await expect(page.getByTestId('match-count')).toHaveCount(0);
    await expect(page.getByLabel('Open your retained collection', { exact: true }).locator(`option[value="${first}"]`)).toHaveCount(0);
    expect((await page.request.get(`/api/v1/projects/${systemA}/investigations/${first}`)).status()).toBe(404);
    expect((await page.request.get(`/api/v1/projects/${systemA}/investigations/${second}`)).status()).toBe(200);
    await expect(other.getByTestId('workspace-id')).toHaveText(otherWorkspace);
    await expect(other.getByTestId('investigation-id')).toHaveText(second);
    await expect(other.getByLabel('Contains string', { exact: true })).toHaveValue('STRASSE');
    await expect(other.getByTestId('match-count')).toHaveText('1 matches');
    await apply(other, golden('duplicate-text-retained').request);
    await expect(other.getByTestId('match-count')).toHaveText('2 matches');
    expect(otherErrors).toEqual([]);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await capture(page, `inspector-deleted-collection-${theme}`);
    }
  } finally { page.off('request', countPreview); await other.close(); }
});

test('invalid UTC input blocks collection and topology selection opens page-local historical scope', async ({ page }) => {
  await login(page, 'inspector');
  await page.goto(`/systems/${systemA}/topology`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  const workspace = await page.getByTestId('workspace-id').innerText();
  async function tabTo(name: string) {
    const button = page.getByRole('button', { name, exact: true });
    for (let index = 0; index < 150; index += 1) {
      if (await button.evaluate(element => element === document.activeElement)) break;
      await page.keyboard.press('Tab');
    }
    await expect(button).toBeFocused();
  }
  await page.getByLabel('Search this system', { exact: true }).focus();
  await tabTo('Select process ingest-instance-a');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Select process ingest-instance-a', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await tabTo('Inspect this process history');
  await page.keyboard.press('Space');
  await expect(page).toHaveURL(new RegExp(`/systems/${systemA}/logs$`));
  await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
  await expect(page.getByRole('group', { name: 'Configured processes' }).getByRole('checkbox', { checked: true })).toHaveCount(1);
  await page.getByLabel('From UTC (inclusive)', { exact: true }).fill('2026-02-30 12:00:00');
  await page.getByLabel('To UTC (exclusive)', { exact: true }).focus();
  await tabTo('Preview collection plan');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('alert')).toContainText('invalid');
  await page.getByLabel('From UTC (inclusive)', { exact: true }).fill(displayUtc(to));
  await page.getByLabel('To UTC (exclusive)', { exact: true }).fill(displayUtc(from));
  await tabTo('Preview collection plan');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('alert')).toContainText('earlier');
  await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Collect sources', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('earlier');
  await expect(page.getByTestId('collection-state')).toHaveCount(0);
  for (const theme of ['light', 'dark'] as const) {
    await setAppearance(page, theme);
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    await page.getByRole('alert').scrollIntoViewIfNeeded();
    await capture(page, `inspector-invalid-utc-${theme}`);
  }
  await page.getByLabel('From UTC (inclusive)', { exact: true }).fill(displayUtc(from));
  await page.getByLabel('To UTC (exclusive)', { exact: true }).fill(displayUtc(to));
  await tabTo('Preview collection plan');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toContainText('/var/log/inspector-demo/ingest/app.log');
  await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
});

test.describe('UTC date and time controls', () => {
  test.use({ timezoneId: 'America/Los_Angeles' });

  test('manual seconds and date/time selectors keep UTC bounds and plans local to each page', async ({ page, context }) => {
    test.setTimeout(120000);
    await login(page, 'inspector'); await open(page);
    expect(await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone)).toBe('America/Los_Angeles');
    const start = page.getByLabel('From UTC (inclusive)', { exact: true });
    const end = page.getByLabel('To UTC (exclusive)', { exact: true });
    await expect(start).toHaveValue(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
    await expect(end).toHaveValue(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
    await expect(page.locator('.history-time-help').first()).toContainText('To is excluded');
    await page.getByRole('group', { name: 'Configured processes' }).getByRole('checkbox').first().check();
    await start.fill('2026-10-16 11:59:59'); await end.fill('2026-10-16 12:00:03');

    const duplicate = await context.newPage();
    const duplicateErrors: string[] = []; duplicate.on('pageerror', error => duplicateErrors.push(error.message));
    try {
      await open(duplicate);
      expect(await duplicate.getByTestId('workspace-id').innerText()).not.toBe(await page.getByTestId('workspace-id').innerText());
      const duplicateStart = await duplicate.getByLabel('From UTC (inclusive)', { exact: true }).inputValue();
      const duplicateEnd = await duplicate.getByLabel('To UTC (exclusive)', { exact: true }).inputValue();
      await expect(duplicate.getByRole('group', { name: 'Configured processes' }).getByRole('checkbox', { checked: true })).toHaveCount(0);

      for (const [bound, time, expected] of [['From', '12:00:00', displayUtc(from)], ['To', '12:00:02', displayUtc(to)]] as const) {
        await page.getByRole('button', { name: `Choose ${bound} UTC date and time`, exact: true }).click();
        const picker = page.getByRole('dialog', { name: `Choose ${bound} UTC date and time`, exact: true });
        const date = picker.getByLabel(`${bound} UTC date`, { exact: true });
        const clock = picker.getByLabel(`${bound} UTC time`, { exact: true });
        await expect(date).toHaveAttribute('type', 'date'); await expect(clock).toHaveAttribute('type', 'time');
        await expect(clock).toHaveAttribute('step', '1');
        await date.fill('2026-10-16'); await clock.fill(time);
        await picker.getByRole('button', { name: 'Use date and time', exact: true }).click();
        await expect(bound === 'From' ? start : end).toHaveValue(expected);
      }

      async function previewBounds(expectedFrom: string, expectedTo: string) {
        const pending = page.waitForResponse(result => result.url().endsWith('/collections/plan') && result.request().method() === 'POST');
        await page.getByRole('button', { name: 'Preview collection plan', exact: true }).click();
        const result = await pending; expect(result.status()).toBe(200);
        expect(result.request().postDataJSON()).toMatchObject({ from: expectedFrom, to: expectedTo, transport: 'local_demo' });
        await expect(page.getByRole('button', { name: 'Collect sources', exact: true })).toBeVisible();
        await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toBeVisible();
      }
      await previewBounds(from, to);

      await page.getByRole('button', { name: 'Choose From UTC date and time', exact: true }).click();
      let picker = page.getByRole('dialog', { name: 'Choose From UTC date and time', exact: true });
      await picker.getByLabel('From UTC time', { exact: true }).fill('12:00:01');
      await picker.getByRole('button', { name: 'Cancel', exact: true }).click();
      await expect(start).toHaveValue(displayUtc(from));
      await expect(page.getByRole('button', { name: 'Collect sources', exact: true })).toBeVisible();
      await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Choose From UTC date and time', exact: true })).toBeFocused();
      await page.getByRole('button', { name: 'Choose From UTC date and time', exact: true }).click();
      picker = page.getByRole('dialog', { name: 'Choose From UTC date and time', exact: true });
      await picker.getByLabel('From UTC time', { exact: true }).fill('12:00:01');
      await picker.getByRole('button', { name: 'Use date and time', exact: true }).click();
      await expect(start).toHaveValue('2026-10-16 12:00:01');
      await expect(page.getByRole('button', { name: 'Collect sources', exact: true })).toBeVisible();
      await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toHaveCount(0);
      await expect(duplicate.getByLabel('From UTC (inclusive)', { exact: true })).toHaveValue(duplicateStart);
      await expect(duplicate.getByLabel('To UTC (exclusive)', { exact: true })).toHaveValue(duplicateEnd);
      await expect(duplicate.getByRole('dialog')).toHaveCount(0);
      await expect(duplicate.getByRole('region', { name: 'Collection plan', exact: true })).toHaveCount(0);

      let invalidPlans = 0;
      const countPlan = (request: { url: () => string }) => { if (request.url().endsWith('/collections/plan')) invalidPlans += 1; };
      page.on('request', countPlan);
      try {
        for (const [invalid, reason] of [['2026-02-30 12:00:00', 'invalid'], ['2026-10-16 24:00:00', 'invalid'], [displayUtc(to), 'earlier'], ['2026-10-16 12:00:03', 'earlier']]) {
          await start.fill(invalid);
          await page.getByRole('button', { name: 'Preview collection plan', exact: true }).click();
          await expect(page.getByRole('alert')).toContainText(reason);
          await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toHaveCount(0);
        }
        expect(invalidPlans).toBe(0);
      } finally { page.off('request', countPlan); }

      // Existing canonical values remain usable when pasted; displaying seconds
      // does not discard an untouched precise API bound.
      const preciseFrom = '2026-10-16T12:00:00.123456Z'; const preciseTo = '2026-10-16T12:00:02.987654Z';
      await start.fill(preciseFrom); await end.fill(preciseTo);
      await expect(start).toHaveValue(displayUtc(from)); await expect(end).toHaveValue(displayUtc(to));
      await previewBounds(preciseFrom, preciseTo);
      await page.getByRole('button', { name: 'Choose From UTC date and time', exact: true }).click();
      picker = page.getByRole('dialog', { name: 'Choose From UTC date and time', exact: true });
      await picker.getByRole('button', { name: 'Cancel', exact: true }).click();
      await previewBounds(preciseFrom, preciseTo);
      for (const bound of ['From', 'To']) {
        await page.getByRole('button', { name: `Choose ${bound} UTC date and time`, exact: true }).click();
        await page.getByRole('dialog', { name: `Choose ${bound} UTC date and time`, exact: true }).getByRole('button', { name: 'Use date and time', exact: true }).click();
        await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toHaveCount(0);
      }
      await previewBounds(from, to);
      await start.fill('2026-10-16 11:59:59'); await end.fill('2026-10-16 12:00:03');
      await start.fill(displayUtc(from)); await end.fill(displayUtc(to));
      await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toHaveCount(0);

      for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
        await page.setViewportSize(size);
        for (const theme of ['light', 'dark'] as const) {
          await setAppearance(page, theme);
          await start.scrollIntoViewIfNeeded();
          await capture(page, `inspector-utc-seconds-${theme}-${size.width}x${size.height}`);
          await page.getByRole('button', { name: 'Choose From UTC date and time', exact: true }).click();
          picker = page.getByRole('dialog', { name: 'Choose From UTC date and time', exact: true });
          await expect(picker.getByLabel('From UTC date', { exact: true })).toHaveValue('2026-10-16');
          await capture(page, `inspector-utc-picker-${theme}-${size.width}x${size.height}`);
          expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
          await page.keyboard.press('Escape');
          await expect(picker).not.toBeVisible();
          await expect(start).toHaveValue(displayUtc(from));
        }
      }
      await page.setViewportSize({ width: 640, height: 720 });
      for (const theme of ['light', 'dark'] as const) {
        await setAppearance(page, theme);
        await page.getByRole('button', { name: 'Choose To UTC date and time', exact: true }).click();
        const narrowPicker = page.getByRole('dialog', { name: 'Choose To UTC date and time', exact: true });
        await expect(narrowPicker).toBeVisible();
        expect(await narrowPicker.evaluate(element => {
          const bounds = element.getBoundingClientRect();
          return bounds.left >= 0 && bounds.right <= window.innerWidth && element.scrollWidth <= element.clientWidth;
        })).toBe(true);
        await capture(page, `inspector-utc-picker-${theme}-640x720`);
        await narrowPicker.getByRole('button', { name: 'Cancel', exact: true }).click();
      }
      expect(duplicateErrors).toEqual([]);
    } finally { await duplicate.close(); }
  });
});
