import { test, expect, type Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { setAppearance, submitSignIn } from './ui';
import type { components } from '../src/api/schema';

type Query = components['schemas']['HistoricalQueryInput'];
type Results = components['schemas']['HistoricalQueryResponse'];
type Role = 'administrator' | 'inspector';
const systemA = 'stage3-fixture-a'; const systemB = 'stage3-fixture-b';
const from = '2026-10-16T12:00:00.000000Z'; const to = '2026-10-16T12:00:02.000000Z';
const cases = JSON.parse(readFileSync(resolve('../fixtures/expected/query-cases.json'), 'utf8')) as { id: string; request: Query; expected_event_ids: string[] }[];
const errors = new WeakMap<Page, string[]>();
test.beforeEach(({ page }) => { const found: string[] = []; errors.set(page, found); page.on('pageerror', error => found.push(error.message)); });
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

async function collect(page: Page) {
  const processes = page.getByRole('group', { name: 'Configured processes' }).getByRole('checkbox');
  expect(await processes.count()).toBe(5);
  for (const process of await processes.all()) await process.check();
  await page.getByLabel('From UTC (inclusive)', { exact: true }).fill(from);
  await page.getByLabel('To UTC (exclusive)', { exact: true }).fill(to);
  await page.getByRole('button', { name: 'Preview collection plan', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toContainText('SYNTHETIC LOCAL FIXTURES');
  await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toContainText('zip');
  await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toContainText('tar.gz');
  await page.getByRole('button', { name: 'Collect planned sources', exact: true }).click();
  await expect(page.getByTestId('collection-state')).toHaveText('completed', { timeout: 30000 });
  await expect(page.getByRole('region', { name: 'Collection progress', exact: true })).toContainText('complete_for_scanned_candidates');
  await expect(page).toHaveURL(/\/investigations\/[^/]+$/);
  return await page.getByTestId('investigation-id').innerText();
}

async function apply(page: Page, input: Query) {
  await page.getByLabel('From UTC (inclusive)', { exact: true }).fill(input.from);
  await page.getByLabel('To UTC (exclusive)', { exact: true }).fill(input.to);
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
  await expect(page.getByLabel('From UTC (inclusive)', { exact: true })).toHaveValue(from);
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
  await page.getByLabel('From UTC (inclusive)', { exact: true }).fill('2026-02-30T12:00:00.000000Z');
  await page.getByLabel('To UTC (exclusive)', { exact: true }).focus();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Preview collection plan', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('alert')).toContainText('invalid');
  await page.getByLabel('From UTC (inclusive)', { exact: true }).fill(to);
  await page.getByLabel('To UTC (exclusive)', { exact: true }).fill(from);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Preview collection plan', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('alert')).toContainText('earlier');
  await expect(page.getByRole('button', { name: 'Collect planned sources', exact: true })).toHaveCount(0);
  for (const theme of ['light', 'dark'] as const) {
    await setAppearance(page, theme);
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    await page.getByRole('alert').scrollIntoViewIfNeeded();
    await capture(page, `inspector-invalid-utc-${theme}`);
  }
  await page.getByLabel('From UTC (inclusive)', { exact: true }).fill(from);
  await page.getByLabel('To UTC (exclusive)', { exact: true }).fill(to);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Preview collection plan', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toContainText('/var/log/inspector-demo/ingest/app.log');
  await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
});
