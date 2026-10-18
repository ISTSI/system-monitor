import { expect, test, type BrowserContext, type Locator, type Page, type Request } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { serveBuiltAssets, setAppearance, setHistoricalCollectionRange } from './ui';
import type { components } from '../src/api/schema';
import type { Preferences } from '../src/api/types';

type Results = components['schemas']['HistoricalQueryResponse'];
type Query = components['schemas']['HistoricalQueryInput'];
const enabled = process.env.INSPECTOR_E2E_URL === 'https://localhost:8449';
const root = resolve('..');
const fixture = enabled ? JSON.parse(readFileSync(resolve(root, '.state/stage7-browser/public-fixture.json'), 'utf8')) as { synthetic: boolean; host: string; projects: string[] } : null;
if (enabled && (!fixture?.synthetic || fixture.host !== 'stage7-sftp' || fixture.projects.join(',') !== 'stage7-fixture-a,stage7-fixture-b')) throw new Error('Only the isolated generated Stage 07 fixture is authorized.');
const system = fixture?.projects[0] ?? 'stage7-fixture-a';
const errors = new WeakMap<BrowserContext, string[]>();
const originalThemes = new WeakMap<BrowserContext, Preferences['theme_mode']>();
const displayUtc = (value: string) => value.slice(0, 19).replace('T', ' ');
const resultsSurface = (page: Page) => page.locator('[aria-label="Event results"]');

test.skip(!enabled, 'Requires the isolated generated Stage 07 real MariaDB/SFTP fixture.');
test.use({ timezoneId: 'America/Los_Angeles' });
test.beforeEach(async ({ page, context, baseURL }) => {
  const found: string[] = []; errors.set(context, found);
  page.on('pageerror', error => found.push(error.message)); context.on('page', extra => extra.on('pageerror', error => found.push(error.message)));
  await context.grantPermissions(['local-network-access'], { origin: baseURL! });
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin === baseURL) return route.fallback();
    found.push('External request blocked'); return route.abort();
  });
  await serveBuiltAssets(context, baseURL!);
});
test.afterEach(async ({ context, page, baseURL }) => {
  try { expect(errors.get(context)).toEqual([]); }
  finally {
    if ((await page.request.get('/api/v1/auth/session')).status() === 200) {
      const csrf = (await (await page.request.get('/api/v1/auth/csrf')).json()).csrf_token as string;
      const headers = { Origin: baseURL!, 'X-CSRF-Token': csrf };
      try {
        const original = originalThemes.get(context);
        if (original !== undefined) {
          const response = await page.request.get('/api/v1/me/preferences'); expect(response.status()).toBe(200);
          const current = await response.json() as Preferences;
          if (current.theme_mode !== original) {
            const restored = await page.request.patch('/api/v1/me/preferences', { headers, data: { theme_mode: original, expected_revision: current.revision } });
            expect(restored.status()).toBe(200); expect(await restored.json()).toMatchObject({ theme_mode: original });
          }
        }
      } finally {
        expect((await page.request.post('/api/v1/auth/logout', { headers, data: {} })).status()).toBe(200);
      }
    }
  }
});

async function login(page: Page) {
  const file = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!file) throw new Error('Protected synthetic accounts are required.');
  const account = (JSON.parse(readFileSync(resolve(file), 'utf8')) as Record<string, { username: string; password: string }>).inspector;
  // The retained review backend predates the optional remembered-login field.
  // Authenticate through its real CSRF-protected API; these tests exercise
  // results, while remember_login.spec.ts covers the matching login UI/backend.
  await page.goto('/');
  const csrf = await (await page.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
  const submit = () => page.request.post('/api/v1/auth/login', { headers: { Origin: new URL(page.url()).origin, 'X-CSRF-Token': csrf.csrf_token }, data: { username: account.username, password: account.password } });
  let signedIn = await submit();
  if (signedIn.status() === 429) {
    test.info().setTimeout(test.info().timeout + 65000);
    test.info().annotations.push({ type: 'rate-limit', description: 'Waited 60 seconds for one login retry without changing the limit.' });
    await page.waitForTimeout(60000); signedIn = await submit();
  }
  if (signedIn.status() !== 200) throw new Error(`Synthetic sign-in failed (${signedIn.status()}); protected values withheld.`);
  await page.reload();
  const preferences = await page.request.get('/api/v1/me/preferences'); expect(preferences.status()).toBe(200);
  originalThemes.set(page.context(), (await preferences.json() as Preferences).theme_mode);
  await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
}

async function openHistory(page: Page, investigation?: string) {
  await page.goto(`/systems/${system}/${investigation ? `investigations/${investigation}` : 'logs'}`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await expect(page.getByRole('heading', { name: 'Historical investigation', exact: true })).toBeVisible();
  if (investigation) {
    await expect(page.getByTestId('investigation-id')).toHaveText(investigation);
    await expect(page.locator('.virtual-logs .log-event').first()).toBeVisible();
  }
}

async function collect(page: Page) {
  const choices = page.getByRole('group', { name: 'Configured processes', exact: true }).getByRole('checkbox');
  expect(await choices.count()).toBe(5);
  for (const choice of await choices.all()) await choice.check();
  // Include the dated rotations and archives so both compact and maximised
  // viewers have enough genuine fixture rows to exercise retained scrolling.
  await setHistoricalCollectionRange(page, { from: '2026-10-13 00:00:00', to: '2026-10-17 00:00:00' });
  await page.getByLabel('Rows', { exact: true }).selectOption('200');
  const loaded = page.waitForResponse(response => response.url().endsWith('/query') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Collect sources', exact: true }).click();
  await expect(page.getByTestId('collection-state')).toHaveText('completed', { timeout: 30000 });
  const response = await loaded; expect(response.status()).toBe(200);
  const body = await response.json() as Results;
  expect(body.items.length).toBeGreaterThan(20);
  await expect(page.locator('.virtual-logs .log-event').first()).toBeVisible();
  return { body, input: response.request().postDataJSON() as Query, investigation: await page.getByTestId('investigation-id').innerText() };
}

async function openFilters(page: Page): Promise<Locator> {
  const dialog = page.getByRole('dialog', { name: 'Filters', exact: true });
  if (!await dialog.count()) await resultsSurface(page).getByRole('button', { name: 'Filters', exact: true }).click();
  await expect(dialog).toBeVisible();
  return dialog;
}

async function addContentFilter(dialog: Locator, content: string, action = 'include', scope = '') {
  await dialog.getByLabel('Log content', { exact: true }).fill(content);
  await dialog.getByLabel('Filter action', { exact: true }).selectOption(action);
  await dialog.getByLabel('Filter scope', { exact: true }).selectOption(scope);
  await dialog.getByRole('button', { name: 'Add filter', exact: true }).click();
}

async function applyFilters(page: Page) {
  const dialog = await openFilters(page);
  await dialog.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect(dialog).toHaveCount(0);
}

async function cancelContentDraft(page: Page, content: string, from?: string) {
  const requests: string[] = [];
  const count = (request: Request) => { if (request.method() === 'POST' && request.url().endsWith('/query')) requests.push(request.url()); };
  page.on('request', count);
  try {
    const dialog = await openFilters(page);
    await addContentFilter(dialog, content);
    if (from) await dialog.getByLabel('From UTC (inclusive)', { exact: true }).fill(from);
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(requests).toEqual([]);
  } finally { page.off('request', count); }
}

async function expectDiscardedDraft(page: Page, content: string, appliedFrom: string) {
  const processMenuWasOpen = await resultsSurface(page).locator('.log-process-menu').getAttribute('open') !== null;
  const dialog = await openFilters(page);
  await expect(dialog.getByLabel('Log content', { exact: true })).toHaveValue('');
  await expect(dialog.getByLabel('From UTC (inclusive)', { exact: true })).toHaveValue(displayUtc(appliedFrom));
  await expect(dialog.locator('.history-filter-list code').filter({ hasText: content })).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  if (processMenuWasOpen) await processMenu(page);
}

async function columns(page: Page): Promise<Locator> {
  const surface = resultsSurface(page);
  const menu = surface.locator('details').filter({ has: page.locator('summary', { hasText: /^Columns$/ }) });
  if (await menu.getAttribute('open') === null) await menu.locator('summary').click();
  await expect(menu.getByRole('checkbox', { name: 'Log entry', exact: true })).toBeChecked();
  await expect(menu.getByRole('checkbox', { name: 'Log entry', exact: true })).toBeDisabled();
  return menu;
}

async function processMenu(page: Page): Promise<Locator> {
  const menu = resultsSurface(page).locator('details.log-process-menu');
  await expect(menu.locator('summary')).toHaveAttribute('aria-label', 'Show process');
  if (await menu.getAttribute('open') === null) await menu.locator('summary').click();
  await expect(menu.getByRole('group', { name: 'Visible processes', exact: true })).toBeVisible();
  return menu;
}

async function visibleProcesses(page: Page): Promise<string[]> {
  return await resultsSurface(page).locator('.log-process-menu input[data-process-id]').evaluateAll(inputs => inputs
    .filter(input => (input as HTMLInputElement).checked).map(input => input.getAttribute('data-process-id')!));
}

// Split-view choices are presentation controls, so changing several together
// must not issue retained queries or consume unsaved investigation controls.
async function showProcesses(page: Page, ids: string[]): Promise<Locator> {
  const menu = await processMenu(page);
  const all = menu.getByRole('checkbox', { name: 'All processes', exact: true });
  await all.check(); await all.uncheck();
  for (const id of ids) await menu.locator(`input[data-process-id="${id}"]`).check();
  await menu.locator('summary').click();
  return menu;
}

async function capture(page: Page, name: string, region?: Locator) {
  const directory = resolve(root, 'verification/stage-7/screenshots'); mkdirSync(directory, { recursive: true });
  await (region ?? page).screenshot({ path: resolve(directory, `events-table-${name}.png`), animations: 'disabled' });
}

test('dense events preserve raw context, UTC seconds, independent columns and full screen scrolling', async ({ page }) => {
  test.setTimeout(180000);
  await login(page); await openHistory(page); const { body, investigation } = await collect(page);
  const surface = resultsSurface(page); const table = surface.getByRole('table');
  const first = body.items[0]; const row = table.locator('.log-event').first();
  const inspect = row.getByRole('button', { name: /^Inspect source line / });
  await expect(surface).toHaveAttribute('role', 'region');
  await expect(table.getByRole('columnheader', { name: 'Event time UTC', exact: true })).toBeVisible();
  await expect(row.getByRole('cell').nth(1)).toHaveText(displayUtc(first.timestamp_utc!));
  expect(await row.locator('.log-message').textContent()).toBe(first.raw_line.slice(first.timestamp_original!.length));
  await expect(inspect).toHaveText(''); await expect(inspect.locator('svg')).toBeVisible();
  const density = await row.evaluate(element => {
    const button = element.querySelector('button')!; const message = element.querySelector('.log-message')!;
    const icon = button.querySelector('svg')!.getBoundingClientRect();
    return { row: element.getBoundingClientRect().height, font: parseFloat(getComputedStyle(message).fontSize), icon: icon.height,
      eyeBeforeTime: button.getBoundingClientRect().right <= element.querySelectorAll('[role="cell"]')[1].getBoundingClientRect().left };
  });
  expect(density.row).toBeLessThanOrEqual(22); expect(density.icon).toBeLessThanOrEqual(density.font); expect(density.eyeBeforeTime).toBe(true);

  const uiRequests: string[] = [];
  const count = (request: Request) => { if (/\/(query|collections|live-sessions)(\/|$)/.test(new URL(request.url()).pathname)) uiRequests.push(request.method()); };
  page.on('request', count);
  try {
    const menu = await columns(page);
    for (const name of ['Event time UTC', 'Host', 'Process']) {
      await menu.getByRole('checkbox', { name, exact: true }).uncheck();
      await expect(table.getByRole('columnheader', { name, exact: true })).toHaveCount(0);
    }
    await capture(page, 'columns-log-only');
    await menu.locator('summary').click();
    await expect(table.getByRole('columnheader', { name: 'Log entry', exact: true })).toBeVisible();
    // The eye remains reachable when every optional metadata column is hidden.
    await inspect.click();
    const context = page.getByRole('dialog', { name: 'Event provenance and source context', exact: true });
    await expect(context.locator('.event-raw')).toHaveText(first.raw_line);
    await expect(context.locator('.source-context .context-anchor pre')).toHaveText(first.raw_line);
    await expect(context.locator('.provenance')).toContainText(displayUtc(first.timestamp_utc!));
    await page.keyboard.press('Escape'); await expect(context).toHaveCount(0); await expect(inspect).toBeFocused();
    await columns(page);
    await menu.getByRole('button', { name: 'Show all columns', exact: true }).click();
    for (const name of ['Event time UTC', 'Host', 'Process']) {
      await expect(menu.getByRole('checkbox', { name, exact: true })).toBeChecked();
      await expect(table.getByRole('columnheader', { name, exact: true })).toBeVisible();
    }
    await menu.locator('summary').click();

    // At this size both forms overflow vertically; resizing must preserve the
    // virtualizer and source position, without fetching a replacement query.
    await page.setViewportSize({ width: 640, height: 540 });
    await table.scrollIntoViewIfNeeded();
    await table.evaluate(element => { element.scrollTop = 40; element.scrollLeft = 60; });
    await expect(table).toHaveJSProperty('scrollTop', 40); await expect(table).toHaveJSProperty('scrollLeft', 60);
    await surface.getByRole('button', { name: 'Full screen', exact: true }).click();
    await expect(surface).toHaveAttribute('role', 'dialog');
    const fullscreen = await surface.boundingBox();
    expect(fullscreen!.width).toBeGreaterThanOrEqual(638); expect(fullscreen!.height).toBeGreaterThanOrEqual(538);
    await expect(table).toHaveJSProperty('scrollTop', 40); await expect(table).toHaveJSProperty('scrollLeft', 60);
    await table.evaluate(element => { element.scrollLeft = 0; });
    await table.locator('.log-event').nth(5).getByRole('button', { name: /^Inspect source line / }).click();
    await expect(context).toBeVisible(); await page.keyboard.press('Escape'); await expect(context).toHaveCount(0);
    await expect(surface).toHaveAttribute('role', 'dialog');
    await table.evaluate(element => { element.scrollTop = 40; element.scrollLeft = 60; });
    await page.keyboard.press('Escape'); await expect(surface).toHaveAttribute('role', 'region');
    await expect(surface.getByRole('button', { name: 'Full screen', exact: true })).toBeFocused();
    await expect(table).toHaveJSProperty('scrollTop', 40); await expect(table).toHaveJSProperty('scrollLeft', 60);

    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }, { width: 640, height: 720 }]) {
        await page.setViewportSize(size);
        await surface.getByRole('button', { name: 'Full screen', exact: true }).click();
        await expect(surface).toHaveAttribute('role', 'dialog');
        await capture(page, `${theme}-${size.width}x${size.height}-full-screen`);
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
        await surface.getByRole('button', { name: 'Exit full screen', exact: true }).click();
        await expect(surface).toHaveAttribute('role', 'region');
      }
    }
    expect(uiRequests).toEqual([]);
  } finally { page.off('request', count); }

  // A query failure must remain visible inside the active modal surface.
  // Only this owned fixture collection's next query is mocked; collection,
  // authentication and every prior query still use the real local backend.
  const queryUrl = new URL(`/api/v1/projects/${system}/investigations/${investigation}/query`, page.url()).href;
  const failure = 'Synthetic test: retained event query is temporarily unavailable.';
  await page.route(queryUrl, route => route.fulfill({ status: 503, json: { error: { code: 'FIXTURE_QUERY_UNAVAILABLE', message: failure } } }), { times: 1 });
  await surface.getByRole('button', { name: 'Full screen', exact: true }).click();
  const failed = page.waitForResponse(response => response.url() === queryUrl && response.request().method() === 'POST');
  await surface.getByRole('button', { name: 'Timestamped events', exact: true }).click();
  expect((await failed).status()).toBe(503);
  await expect(surface.getByRole('alert')).toContainText(failure);
  await expect(surface.getByRole('alert')).toContainText(system);
  await expect(table).toHaveAttribute('aria-rowcount', String(body.items.length + 1));
  await capture(page, 'full-screen-query-error');
  await page.keyboard.press('Escape'); await expect(surface).toHaveAttribute('role', 'region');
});

test('column, process and full screen controls stay local to same-account pages and apply across split panes', async ({ page, context }) => {
  test.setTimeout(120000);
  await login(page); await openHistory(page); const { input, investigation } = await collect(page);
  const workspace = await page.getByTestId('workspace-id').innerText();
  const duplicate = await context.newPage();
  try {
    await openHistory(duplicate, investigation);
    expect(await duplicate.getByTestId('workspace-id').innerText()).not.toBe(workspace);
    const duplicateSurface = resultsSurface(duplicate);
    const menu = await columns(page);
    await menu.getByRole('checkbox', { name: 'Host', exact: true }).uncheck();
    await menu.getByRole('checkbox', { name: 'Process', exact: true }).uncheck();
    await menu.locator('summary').click();
    await page.getByLabel('Result layout', { exact: true }).selectOption('split');
    await expect(page.locator('.history-split .virtual-logs')).toHaveCount(5);
    for (const table of await page.locator('.history-split .virtual-logs').all()) {
      await expect(table.getByRole('columnheader', { name: 'Host', exact: true })).toHaveCount(0);
      await expect(table.getByRole('columnheader', { name: 'Process', exact: true })).toHaveCount(0);
      await expect(table.getByRole('columnheader', { name: 'Log entry', exact: true })).toBeVisible();
    }
    const processIds = input.process_ids;
    await resultsSurface(page).getByLabel('Pane arrangement', { exact: true }).selectOption('4');
    await showProcesses(page, [processIds[0]]);
    await expect(resultsSurface(page).locator('.history-split > section:visible')).toHaveCount(1);
    await resultsSurface(page).getByRole('button', { name: 'Full screen', exact: true }).click();
    await expect(resultsSurface(page)).toHaveAttribute('role', 'dialog');
    await expect(duplicateSurface).toHaveAttribute('role', 'region');
    await expect(duplicate.getByLabel('Result layout', { exact: true })).toHaveValue('merged');
    await expect(duplicateSurface.getByLabel('Show process', { exact: true })).toBeVisible();
    await expect(duplicateSurface.getByLabel('Pane arrangement', { exact: true })).toBeVisible();
    await expect(duplicateSurface.getByLabel('Pane arrangement', { exact: true })).toBeDisabled();
    await expect(duplicateSurface.getByRole('columnheader', { name: 'Host', exact: true })).toBeVisible();
    await expect(duplicateSurface.getByRole('columnheader', { name: 'Process', exact: true })).toBeVisible();
    await expect(duplicate.getByTestId('investigation-id')).toHaveText(investigation);
    const duplicateMenu = await columns(duplicate);
    await expect(duplicateMenu.getByRole('checkbox', { name: 'Host', exact: true })).toBeChecked();
    await expect(duplicateMenu.getByRole('checkbox', { name: 'Process', exact: true })).toBeChecked();
    await duplicateMenu.locator('summary').click();
    await duplicateSurface.getByLabel('Result layout', { exact: true }).selectOption('split');
    expect(await visibleProcesses(duplicate)).toEqual(processIds);
    await expect(duplicateSurface.getByLabel('Pane arrangement', { exact: true })).toHaveValue('1');
    await expect(duplicateSurface.locator('.history-split > section:visible')).toHaveCount(5);
    await duplicateSurface.getByLabel('Pane arrangement', { exact: true }).selectOption('2');
    await showProcesses(duplicate, [processIds[1], processIds[2]]);
    expect(await visibleProcesses(page)).toEqual([processIds[0]]);
    await expect(resultsSurface(page).getByLabel('Pane arrangement', { exact: true })).toHaveValue('4');
    await expect(duplicateSurface.locator('.history-split > section:visible')).toHaveCount(2);
    await page.keyboard.press('Escape'); await expect(resultsSurface(page)).toHaveAttribute('role', 'region');
    await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
  } finally { await duplicate.close(); }
});

test('row count immediately repaginates the applied query after filter-dialog edits are cancelled', async ({ page }) => {
  test.setTimeout(120000);
  await login(page); await openHistory(page); const { body, input, investigation } = await collect(page);
  expect(body.items.length).toBeGreaterThanOrEqual(20);
  const surface = resultsSurface(page); const table = surface.getByRole('table');
  const size = surface.getByLabel('Rows', { exact: true });
  const next = surface.getByRole('button', { name: 'Next result page', exact: true });
  const previous = surface.getByRole('button', { name: 'Previous result page', exact: true });
  const queryUrl = new URL(`/api/v1/projects/${system}/investigations/${investigation}/query`, page.url()).href;
  const draft = 'Unsubmitted synthetic filter with no matching records';
  await cancelContentDraft(page, draft);
  const collections: string[] = [];
  const countCollection = (request: Request) => { if (request.method() === 'POST' && /\/(collections|live-sessions)(\/|$)/.test(new URL(request.url()).pathname)) collections.push(request.url()); };
  page.on('request', countCollection);
  async function queried(action: () => Promise<unknown>, expected: Query) {
    const loaded = page.waitForResponse(response => response.url() === queryUrl && response.request().method() === 'POST');
    await action(); const response = await loaded; expect(response.status()).toBe(200);
    expect(response.request().postDataJSON()).toEqual(expected);
    const value = await response.json() as Results;
    await expect(table).toHaveAttribute('aria-rowcount', String(value.items.length + 1));
    await expect(surface.locator('.history-result-body')).toHaveAttribute('aria-busy', 'false');
    return value;
  }
  try {
    const first = await queried(() => size.selectOption('10'), { ...input, limit: 10, cursor: null });
    expect(first.items.map(event => event.event_id)).toEqual(body.items.slice(0, 10).map(event => event.event_id));
    await expect(surface.locator('.history-result-summary')).toContainText('10 rows on page 1');
    await expect(previous).toBeDisabled(); await expect(next).toBeEnabled();
    await expectDiscardedDraft(page, draft, input.from);
    const second = await queried(() => next.click(), { ...input, limit: 10, cursor: first.next_cursor });
    expect(second.items.map(event => event.event_id)).toEqual(body.items.slice(10, 20).map(event => event.event_id));
    await expect(surface.locator('.history-result-summary')).toContainText('10 rows on page 2');
    await expect(previous).toBeEnabled();
    const restored = await queried(() => previous.click(), { ...input, limit: 10, cursor: null });
    expect(restored.items.map(event => event.event_id)).toEqual(first.items.map(event => event.event_id));
    await expect(surface.locator('.history-result-summary')).toContainText('10 rows on page 1');
    await queried(() => next.click(), { ...input, limit: 10, cursor: restored.next_cursor });

    const fifty = await queried(() => size.selectOption('50'), { ...input, limit: 50, cursor: null });
    expect(fifty.items.map(event => event.event_id)).toEqual(body.items.slice(0, 50).map(event => event.event_id));
    await expect(surface.locator('.history-result-summary')).toContainText(`${Math.min(50, body.items.length)} rows on page 1`);
    await expect(previous).toBeDisabled();
    if (body.items.length <= 50) {
      expect(fifty.next_cursor).toBeNull(); await expect(next).toBeDisabled();
    }
    await expectDiscardedDraft(page, draft, input.from);

    const measured = page.waitForResponse(response => response.url() === queryUrl && response.request().method() === 'POST');
    await size.selectOption('0');
    const response = await measured; expect(response.status()).toBe(200);
    const request = response.request().postDataJSON() as Query;
    expect(request.limit).toBeGreaterThanOrEqual(40); expect(request.limit).toBeLessThanOrEqual(1000);
    expect(request).toEqual({ ...input, limit: request.limit, cursor: null });
    const value = await response.json() as Results;
    expect(value.items.map(event => event.event_id)).toEqual(body.items.slice(0, value.items.length).map(event => event.event_id));
    await expect(table).toHaveAttribute('aria-rowcount', String(value.items.length + 1));
    await expect(surface.locator('.history-result-summary')).toContainText(`${value.items.length} rows on page 1`);
    await expect(previous).toBeDisabled();

    // A failed resize keeps the retained rows visible and offers the ordinary
    // Apply action for retry. Only this next owned-fixture query is mocked.
    const failure = 'Synthetic test: result-page resize temporarily unavailable.';
    await page.route(queryUrl, route => route.fulfill({ status: 503, json: { error: { code: 'FIXTURE_PAGE_SIZE_UNAVAILABLE', message: failure } } }), { times: 1 });
    const failed = page.waitForResponse(result => result.url() === queryUrl && result.request().method() === 'POST');
    await size.selectOption('50'); expect((await failed).status()).toBe(503);
    await expect(page.getByRole('alert')).toContainText(failure);
    await expect(table).toHaveAttribute('aria-rowcount', String(value.items.length + 1));
    await expect(table.locator('.log-event').first()).toBeVisible();
    await queried(() => applyFilters(page), { ...input, limit: 50, cursor: null });
    await expect(page.getByRole('alert')).toHaveCount(0);
    expect(collections).toEqual([]);
  } finally { page.off('request', countCollection); }
});

test('process layouts visibly regroup retained rows and Columns dismisses outside or with Escape', async ({ page }) => {
  test.setTimeout(120000);
  await login(page); await openHistory(page); const { body } = await collect(page);
  const surface = resultsSurface(page); const tables = surface.getByRole('table');
  const processes = [...new Map(body.items.map(event => [event.process_id, event.process_name_snapshot])).entries()];
  expect(processes.length).toBe(5);
  await expect(tables).toHaveCount(1);
  await expect(tables).toHaveAttribute('aria-rowcount', String(body.items.length + 1));
  const requests: string[] = [];
  const count = (request: Request) => { if (/\/(query|collections|live-sessions)(\/|$)/.test(new URL(request.url()).pathname)) requests.push(request.method()); };
  page.on('request', count);
  try {
    await surface.getByLabel('Result layout', { exact: true }).selectOption('split');
    await expect(tables).toHaveCount(processes.length);
    await expect(surface.locator('.history-layout-help')).toHaveCount(0);
    for (const [id, name] of processes) {
      const pane = surface.locator('.history-split > section').filter({ has: page.getByRole('heading', { name: new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }) });
      await expect(pane).toHaveCount(1);
      await expect(pane).toBeVisible();
      const table = pane.getByRole('table');
      await expect(table).toHaveAttribute('aria-rowcount', String(body.items.filter(event => event.process_id === id).length + 1));
      for (const row of await table.locator('.log-event').all()) await expect(row.getByRole('cell').nth(2)).toHaveText(name);
    }
    await capture(page, 'separate-process-panes', surface);
    await surface.getByLabel('Result layout', { exact: true }).selectOption('merged');
    await expect(surface.locator('.history-split')).toHaveCount(0); await expect(tables).toHaveCount(1);
    await expect(tables).toHaveAttribute('aria-rowcount', String(body.items.length + 1));

    const menu = await columns(page);
    await menu.getByRole('checkbox', { name: 'Host', exact: true }).uncheck();
    await expect(menu).toHaveAttribute('open', '');
    // Clicking a retained row is outside the picker and must remain a normal
    // table interaction rather than requiring a second click on Columns.
    await tables.locator('.log-message').first().click();
    await expect(menu).not.toHaveAttribute('open');
    await expect(tables.getByRole('columnheader', { name: 'Host', exact: true })).toHaveCount(0);
    await columns(page);
    await page.keyboard.press('Escape'); await expect(menu).not.toHaveAttribute('open');
    await expect(menu.locator('summary')).toBeFocused();

    await surface.getByRole('button', { name: 'Full screen', exact: true }).click();
    await expect(surface).toHaveAttribute('role', 'dialog');
    await columns(page);
    await page.keyboard.press('Escape'); await expect(menu).not.toHaveAttribute('open');
    await expect(menu.locator('summary')).toBeFocused(); await expect(surface).toHaveAttribute('role', 'dialog');
    await columns(page);
    await tables.locator('.log-message').first().click();
    await expect(menu).not.toHaveAttribute('open'); await expect(surface).toHaveAttribute('role', 'dialog');
    const processesMenu = await processMenu(page);
    await page.keyboard.press('Escape'); await expect(processesMenu).not.toHaveAttribute('open');
    await expect(processesMenu.locator('summary')).toBeFocused(); await expect(surface).toHaveAttribute('role', 'dialog');
    await processMenu(page);
    await tables.locator('.log-event [role="cell"]').nth(1).click();
    await expect(processesMenu).not.toHaveAttribute('open'); await expect(surface).toHaveAttribute('role', 'dialog');
    await page.keyboard.press('Escape'); await expect(surface).toHaveAttribute('role', 'region');
    expect(requests).toEqual([]);
  } finally { page.off('request', count); }

  // A page containing one process still has a visibly labelled pane and an
  // explanation when split. Reuse this retained collection without SFTP work.
  const single = body.items[0];
  await surface.getByLabel('Result layout', { exact: true }).selectOption('split');
  await showProcesses(page, [single.process_id]);
  const loaded = page.waitForResponse(response => response.url().endsWith('/query') && response.request().method() === 'POST');
  await surface.getByLabel('Result layout', { exact: true }).selectOption('merged');
  const response = await loaded; expect(response.status()).toBe(200);
  expect((response.request().postDataJSON() as Query).process_ids).toEqual([single.process_id]);
  const filtered = await response.json() as Results;
  expect(filtered.items.length).toBeGreaterThan(0);
  expect(filtered.items.every(event => event.process_id === single.process_id)).toBe(true);
  await expect(tables).toHaveAttribute('aria-rowcount', String(filtered.items.length + 1));
  await expect(surface.locator('.history-layout-help')).toHaveCount(0);
  requests.length = 0; page.on('request', count);
  try {
    await surface.getByLabel('Result layout', { exact: true }).selectOption('split');
    await expect(surface.locator('.history-split > section')).toHaveCount(1);
    await expect(surface.locator('.history-process-heading')).toContainText(single.process_name_snapshot);
    await expect(surface.locator('.history-process-heading')).toContainText(single.server_name_snapshot);
    await expect(surface.locator('.history-process-heading')).toContainText(`${filtered.items.length} rows on this page`);
    await expect(surface.locator('.history-layout-help')).toHaveCount(0);
    await expect(tables).toHaveAttribute('aria-rowcount', String(filtered.items.length + 1));
    await capture(page, 'single-process-pane', surface);
    await surface.getByLabel('Result layout', { exact: true }).selectOption('merged');
    await expect(surface.locator('.history-split')).toHaveCount(0);
    await expect(surface.locator('.history-layout-help')).toHaveCount(0);
    await expect(tables).toHaveAttribute('aria-rowcount', String(filtered.items.length + 1));
    expect(requests).toEqual([]);
  } finally { page.off('request', count); }
});

test('selected row count survives automatic results loading for a new collection', async ({ page }) => {
  test.setTimeout(120000);
  await login(page); await openHistory(page); const { body, input, investigation } = await collect(page);
  const surface = resultsSurface(page); const size = surface.getByLabel('Rows', { exact: true });
  const oldQueryUrl = new URL(`/api/v1/projects/${system}/investigations/${investigation}/query`, page.url()).href;
  const resized = page.waitForResponse(response => response.url() === oldQueryUrl && response.request().method() === 'POST');
  await size.selectOption('10');
  const resizedResponse = await resized; expect(resizedResponse.status()).toBe(200);
  expect(resizedResponse.request().postDataJSON()).toEqual({ ...input, limit: 10, cursor: null });
  await expect(surface.locator('.history-result-body')).toHaveAttribute('aria-busy', 'false');
  await expect(surface.getByRole('table')).toHaveAttribute('aria-rowcount', '11');

  // Exclude the completed prior query explicitly: these assertions belong to
  // the distinct collection created with the current ten-row preference.
  const queryPrefix = new URL(`/api/v1/projects/${system}/investigations/`, page.url()).href;
  const loaded = page.waitForResponse(response => response.url().startsWith(queryPrefix) && response.url().endsWith('/query') && response.url() !== oldQueryUrl && response.request().method() === 'POST');
  const collectionUrl = new URL(`/api/v1/projects/${system}/collections`, page.url()).href;
  const created = page.waitForResponse(response => response.url() === collectionUrl && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Collect sources', exact: true }).click();
  const createdResponse = await created; expect(createdResponse.ok()).toBe(true);
  const job = await createdResponse.json() as components['schemas']['HistoricalJobResponse'];
  expect(job.investigation_id).not.toBe(investigation);
  await expect(page.getByTestId('investigation-id')).toHaveText(job.investigation_id);
  await expect(page.getByTestId('collection-state')).toHaveText('completed', { timeout: 30000 });
  const response = await loaded; expect(response.status()).toBe(200);
  expect(response.url()).toBe(new URL(`/api/v1/projects/${system}/investigations/${job.investigation_id}/query`, page.url()).href);
  expect(response.request().postDataJSON()).toEqual({ ...input, limit: 10, cursor: null });
  const results = await response.json() as Results;
  expect(results.items).toHaveLength(10);
  expect(results.matched_count).toBe(body.matched_count); expect(results.next_cursor).not.toBeNull();
  await expect(size).toHaveValue('10'); await expect(size).toBeEnabled();
  await expect(surface.getByRole('table')).toHaveAttribute('aria-rowcount', '11');
  await expect(surface.locator('.history-result-summary')).toContainText('10 rows on page 1');
  await expect(surface.getByRole('button', { name: 'Previous result page', exact: true })).toBeDisabled();
  await expect(surface.getByRole('button', { name: 'Next result page', exact: true })).toBeEnabled();
  await capture(page, 'row-count-new-collection', surface);
});

test('separate panes query every applied process and page independently without consuming draft controls', async ({ page }) => {
  test.setTimeout(180000);
  await login(page); await openHistory(page); const { body, input, investigation } = await collect(page);
  const surface = resultsSurface(page);
  const queryUrl = new URL(`/api/v1/projects/${system}/investigations/${investigation}/query`, page.url()).href;
  const target = body.items.find(event => event.process_id === 'p-ingest-a')!;
  const other = body.items.find(event => event.process_id === 'p-parser-a')!;
  expect(target).toBeDefined(); expect(other).toBeDefined();
  const filter = (exclude: string) => ({ include: [], include_mode: 'all' as const, exclude: [exclude], case_sensitive: input.filter!.case_sensitive });
  const perProcess = { [target.process_id]: filter('archive_type='), [other.process_id]: filter('Absent synthetic exclusion') };
  const scoped = (query: Query, id: string, cursor: string | null = null): Query => ({
    ...query, process_ids: [id], cursor,
    per_process_filters: Object.fromEntries(Object.entries(query.per_process_filters ?? {}).filter(([processId]) => processId === id)),
  });
  async function queried(action: () => Promise<unknown>, expected: Query) {
    const loaded = page.waitForResponse(response => response.url() === queryUrl && response.request().method() === 'POST');
    await action(); const response = await loaded; expect(response.status()).toBe(200);
    expect(response.request().postDataJSON()).toEqual(expected);
    await expect(surface.locator('.history-result-body')).toHaveAttribute('aria-busy', 'false');
    return await response.json() as Results;
  }

  const processFilters = await openFilters(page);
  await addContentFilter(processFilters, 'archive_type=', 'exclude', target.process_id);
  await addContentFilter(processFilters, 'Absent synthetic exclusion', 'exclude', other.process_id);
  const applied: Query = { ...input, per_process_filters: perProcess, cursor: null };
  await queried(() => applyFilters(page), applied);
  const ten: Query = { ...applied, limit: 10 };
  const merged = await queried(() => surface.getByLabel('Rows', { exact: true }).selectOption('10'), ten);
  expect(merged.items).toHaveLength(10); expect(merged.next_cursor).not.toBeNull();
  // The process still has later retained matches, even though the merged page
  // has none of its rows. Separate panes must not be built from that page alone.
  expect(merged.items.some(event => event.process_id === target.process_id)).toBe(false);
  const expectedTarget = body.items.filter(event => event.process_id === target.process_id && !event.raw_line.includes('archive_type='));
  expect(expectedTarget.length).toBeGreaterThan(10);

  const draft = 'Unsubmitted synthetic literal with no matches';
  const draftFrom = '2026-10-16 12:00:00';
  await cancelContentDraft(page, draft, draftFrom);
  const targetChoice = page.getByRole('group', { name: 'Configured processes', exact: true }).getByRole('checkbox', { name: new RegExp(target.process_name_snapshot) });
  await targetChoice.uncheck();

  const loadedPanes = input.process_ids.map(id => page.waitForResponse(response => {
    if (response.url() !== queryUrl || response.request().method() !== 'POST') return false;
    const query = response.request().postDataJSON() as Query;
    return query.process_ids.length === 1 && query.process_ids[0] === id;
  }));
  await surface.getByLabel('Result layout', { exact: true }).selectOption('split');
  const responses = await Promise.all(loadedPanes);
  const paneResults = new Map<string, Results>();
  for (const [index, response] of responses.entries()) {
    expect(response.status()).toBe(200);
    const id = input.process_ids[index]; expect(response.request().postDataJSON()).toEqual(scoped(ten, id));
    paneResults.set(id, await response.json() as Results);
  }
  const panes = surface.locator('.history-split > section');
  await expect(panes).toHaveCount(input.process_ids.length);
  for (const id of input.process_ids) {
    const pane = surface.locator(`.history-split > section[data-process-id="${id}"]`);
    await expect(pane).toHaveAttribute('aria-busy', 'false');
    await expect(pane.getByRole('table')).toHaveAttribute('aria-rowcount', String(paneResults.get(id)!.items.length + 1));
  }
  await expect(surface.getByRole('button', { name: 'Next result page', exact: true })).toBeHidden();
  const picker = await processMenu(page);
  const arrangement = surface.getByLabel('Pane arrangement', { exact: true });
  expect(await visibleProcesses(page)).toEqual(input.process_ids); await expect(arrangement).toHaveValue('1');
  await expect(picker.getByRole('checkbox', { name: 'All processes', exact: true })).toBeChecked();
  for (const id of input.process_ids) {
    const event = body.items.find(item => item.process_id === id)!;
    await expect(picker.locator(`input[data-process-id="${id}"]`)).toBeChecked();
    await expect(picker.locator(`input[data-process-id="${id}"]`)).toHaveAccessibleName(`${event.server_name_snapshot}: ${event.process_name_snapshot}`);
    await expect(picker.locator(`input[data-process-id="${id}"]`)).toHaveAttribute('title', id);
  }
  await picker.locator('summary').click();
  await expectDiscardedDraft(page, draft, input.from);
  await expect(targetChoice).not.toBeChecked();

  const presentationRequests: string[] = [];
  const count = (request: Request) => { if (/\/(query|collections|live-sessions)(\/|$)/.test(new URL(request.url()).pathname)) presentationRequests.push(request.method()); };
  page.on('request', count);
  try {
    await arrangement.selectOption('3'); await showProcesses(page, [target.process_id]);
    await expect(surface.locator('.history-split > section:visible')).toHaveCount(1);
    await expect(surface.locator(`.history-split > section[data-process-id="${target.process_id}"]`)).toBeVisible();
    await showProcesses(page, [other.process_id]); await showProcesses(page, input.process_ids);
    await expect(surface.locator('.history-split > section:visible')).toHaveCount(input.process_ids.length);
    await showProcesses(page, [target.process_id]); expect(presentationRequests).toEqual([]);
  } finally { page.off('request', count); }

  const pane = surface.locator(`.history-split > section[data-process-id="${target.process_id}"]`);
  const table = pane.getByRole('table');
  const next = pane.getByRole('button', { name: `Next page for ${target.process_name_snapshot}`, exact: true });
  const previous = pane.getByRole('button', { name: `Previous page for ${target.process_name_snapshot}`, exact: true });
  const first = paneResults.get(target.process_id)!; expect(first.next_cursor).not.toBeNull();
  await expect(previous).toBeDisabled(); await expect(next).toBeEnabled();
  const second = await queried(() => next.click(), scoped(ten, target.process_id, first.next_cursor));
  expect(second.items.map(event => event.event_id)).toEqual(expectedTarget.slice(10).map(event => event.event_id));
  await expect(table).toHaveAttribute('aria-rowcount', String(second.items.length + 1));
  await expect(pane.locator('.history-pane-pagination')).toContainText('Page 2');
  await expect(previous).toBeEnabled(); await expect(next).toBeDisabled();
  expect(await visibleProcesses(page)).toEqual([target.process_id]); await expect(arrangement).toHaveValue('3');
  const retainedPage = await table.locator('.log-event').allTextContents();
  await table.evaluate(element => { element.scrollLeft = 60; });
  const retainedScroll = await table.evaluate(element => element.scrollLeft);
  presentationRequests.length = 0; page.on('request', count);
  try {
    await showProcesses(page, [other.process_id]); await showProcesses(page, [target.process_id]);
    await expect(pane.locator('.history-pane-pagination')).toContainText('Page 2');
    await expect(table.locator('.log-event')).toHaveText(retainedPage);
    await expect(table).toHaveJSProperty('scrollLeft', retainedScroll);
    expect(presentationRequests).toEqual([]);
  } finally { page.off('request', count); }
  const restored = await queried(() => previous.click(), scoped(ten, target.process_id));
  expect(restored.items.map(event => event.event_id)).toEqual(first.items.map(event => event.event_id));
  await expect(table).toHaveAttribute('aria-rowcount', '11');

  const failure = 'Synthetic test: this process page is temporarily unavailable.';
  await page.route(queryUrl, route => route.fulfill({ status: 503, json: { error: { code: 'FIXTURE_PROCESS_PAGE_UNAVAILABLE', message: failure } } }), { times: 1 });
  const failed = page.waitForResponse(response => response.url() === queryUrl && response.request().method() === 'POST');
  await next.click(); const failedResponse = await failed; expect(failedResponse.status()).toBe(503);
  expect(failedResponse.request().postDataJSON()).toEqual(scoped(ten, target.process_id, restored.next_cursor));
  await expect(pane.getByRole('alert')).toContainText(failure);
  await expect(table).toHaveAttribute('aria-rowcount', '11'); await expect(table.locator('.log-event').first()).toBeVisible();
  await expect(pane.locator('.history-pane-pagination')).toContainText('Page 1');
  expect(await visibleProcesses(page)).toEqual([target.process_id]); await expect(arrangement).toHaveValue('3');
  await capture(page, 'process-pane-query-error', surface);
  await queried(() => pane.getByRole('button', { name: `Retry ${target.process_name_snapshot}`, exact: true }).click(), scoped(ten, target.process_id, restored.next_cursor));
  await expect(pane.getByRole('alert')).toHaveCount(0);
  await expect(pane.locator('.history-pane-pagination')).toContainText('Page 2');

  // The shared row-count control repaginates the original five-process query;
  // the focused pane and unrelated draft inputs keep their local state.
  await queried(() => surface.getByLabel('Rows', { exact: true }).selectOption('50'), { ...applied, limit: 50 });
  await expect(table).toHaveAttribute('aria-rowcount', String(expectedTarget.length + 1));
  expect(await visibleProcesses(page)).toEqual([target.process_id]); await expect(arrangement).toHaveValue('3');
  await expectDiscardedDraft(page, draft, input.from);
  await expect(targetChoice).not.toBeChecked();
  presentationRequests.length = 0; page.on('request', count);
  try {
    await showProcesses(page, input.process_ids); await expect(surface.locator('.history-split > section:visible')).toHaveCount(5);
    expect(presentationRequests).toEqual([]);
  } finally { page.off('request', count); }

  // Only an explicit Apply replaces the applied scope with edited controls.
  const edited: Query = { ...applied, process_ids: input.process_ids.filter(id => id !== target.process_id), from: '2026-10-16T12:00:00.000000Z', filter: { ...input.filter!, include: [draft] }, per_process_filters: { [other.process_id]: perProcess[other.process_id] }, limit: 50 };
  await showProcesses(page, [other.process_id]);
  const editedFilters = await openFilters(page);
  await editedFilters.getByLabel('From UTC (inclusive)', { exact: true }).fill(draftFrom);
  await addContentFilter(editedFilters, draft);
  await queried(() => applyFilters(page), edited);
  expect(await visibleProcesses(page)).toEqual(edited.process_ids); await expect(picker.locator('input[data-process-id]')).toHaveCount(edited.process_ids.length);
  await expect(picker.locator(`input[data-process-id="${target.process_id}"]`)).toHaveCount(0);
  await showProcesses(page, [other.process_id]);
  await queried(() => surface.getByRole('button', { name: /^Diagnostic lane/ }).click(), { ...edited, lane: 'diagnostic' });
  expect(await visibleProcesses(page)).toEqual(edited.process_ids);
});

test('process checkboxes query retained merged subsets, preserve drafts and recover from empty or failed selections', async ({ page }) => {
  test.setTimeout(180000);
  await login(page); await openHistory(page); const { body, input, investigation } = await collect(page);
  const surface = resultsSurface(page);
  const queryUrl = new URL(`/api/v1/projects/${system}/investigations/${investigation}/query`, page.url()).href;
  const target = body.items.find(event => event.process_id === 'p-ingest-a')!;
  const other = body.items.find(event => event.process_id === 'p-parser-a')!;
  const filter = (exclude: string) => ({ include: [], include_mode: 'all' as const, exclude: [exclude], case_sensitive: input.filter!.case_sensitive });
  const perProcess = { [target.process_id]: filter('archive_type='), [other.process_id]: filter('Absent synthetic exclusion') };
  const applied: Query = { ...input, per_process_filters: perProcess, cursor: null };
  const ten: Query = { ...applied, limit: 10 };
  const subset = (query: Query, ids: string[]): Query => ({ ...query,
    process_ids: query.process_ids.filter(id => ids.includes(id)), cursor: null,
    per_process_filters: Object.fromEntries(Object.entries(query.per_process_filters ?? {}).filter(([id]) => ids.includes(id))),
  });
  async function queried(action: () => Promise<unknown>, expected: Query) {
    const loaded = page.waitForResponse(response => response.url() === queryUrl && response.request().method() === 'POST');
    await action(); const response = await loaded; expect(response.status()).toBe(200);
    expect(response.request().postDataJSON()).toEqual(expected);
    await expect(surface.locator('.history-result-body')).toHaveAttribute('aria-busy', 'false');
    return await response.json() as Results;
  }
  const processFilters = await openFilters(page);
  await addContentFilter(processFilters, 'archive_type=', 'exclude', target.process_id);
  await addContentFilter(processFilters, 'Absent synthetic exclusion', 'exclude', other.process_id);
  await queried(() => applyFilters(page), applied);
  const merged = await queried(() => surface.getByLabel('Rows', { exact: true }).selectOption('10'), ten);
  expect(merged.items.some(event => event.process_id === target.process_id)).toBe(false);
  const draft = 'Unsubmitted synthetic literal with no matches';
  const draftFrom = '2026-10-16 12:00:00';
  await cancelContentDraft(page, draft, draftFrom);
  const menu = await processMenu(page);
  const all = menu.getByRole('checkbox', { name: 'All processes', exact: true });
  await expect(all).toBeChecked(); await expect(all).toHaveJSProperty('indeterminate', false);
  await expect(menu.locator('input[data-process-id]')).toHaveCount(input.process_ids.length);
  for (const id of input.process_ids) {
    const event = body.items.find(item => item.process_id === id)!;
    await expect(menu.locator(`input[data-process-id="${id}"]`)).toBeChecked();
    await expect(menu.locator(`input[data-process-id="${id}"]`)).toHaveAccessibleName(`${event.server_name_snapshot}: ${event.process_name_snapshot}`);
  }
  const requests: string[] = [];
  const count = (request: Request) => { if (request.url() === queryUrl && request.method() === 'POST') requests.push(request.url()); };
  page.on('request', count);
  try {
    await all.uncheck();
    await expect(surface.getByText('No processes selected', { exact: true })).toBeVisible();
    await expect(surface.locator('.log-event:visible')).toHaveCount(0);
    await expect(surface.getByRole('button', { name: 'Previous result page', exact: true })).toBeDisabled();
    await expect(surface.getByRole('button', { name: 'Next result page', exact: true })).toBeDisabled();
    expect(await visibleProcesses(page)).toEqual([]); expect(requests).toEqual([]);
    await expect(menu.locator('input[data-process-id]')).toHaveCount(input.process_ids.length);
    await expect(all).not.toBeChecked(); await expect(all).toHaveJSProperty('indeterminate', false);
  } finally { page.off('request', count); }

  // This process was absent from the merged page, yet the menu still scopes a
  // genuine retained query for all of its matching rows, using applied controls.
  const targetRows = await queried(() => menu.locator(`input[data-process-id="${target.process_id}"]`).click(), subset(ten, [target.process_id]));
  expect(targetRows.items).toHaveLength(10); expect(targetRows.items.every(event => event.process_id === target.process_id)).toBe(true);
  await expect(surface.getByRole('table')).toHaveAttribute('aria-rowcount', '11');
  await expect(surface.locator('.history-result-summary')).toContainText(`${targetRows.matched_count} matches`);
  await expect(surface.getByRole('button', { name: 'Next result page', exact: true })).toBeEnabled();
  await expect(all).toHaveJSProperty('indeterminate', true);
  const pair = input.process_ids.filter(id => id === target.process_id || id === other.process_id);
  const pairRows = await queried(() => menu.locator(`input[data-process-id="${other.process_id}"]`).click(), subset(ten, pair));
  expect(await visibleProcesses(page)).toEqual(pair); await expect(all).toHaveJSProperty('indeterminate', true);
  // Reinsert the earlier ID last: request order follows the applied query,
  // rather than the order in which checkboxes happened to be clicked.
  await queried(() => menu.locator(`input[data-process-id="${pair[0]}"]`).click(), subset(ten, pair.slice(1)));
  await queried(() => menu.locator(`input[data-process-id="${pair[0]}"]`).click(), subset(ten, pair));
  await expect(menu.locator('input[data-process-id]')).toHaveCount(input.process_ids.length);
  await expectDiscardedDraft(page, draft, input.from);

  const failure = 'Synthetic test: process selection temporarily unavailable.';
  let releaseFailure!: () => void;
  let queryStarted!: () => void;
  const holdFailure = new Promise<void>(resolve => { releaseFailure = resolve; });
  const started = new Promise<void>(resolve => { queryStarted = resolve; });
  await page.route(queryUrl, async route => {
    queryStarted(); await holdFailure;
    await route.fulfill({ status: 503, json: { error: { code: 'FIXTURE_PROCESS_SELECTION_UNAVAILABLE', message: failure } } });
  }, { times: 1 });
  const failed = page.waitForResponse(response => response.url() === queryUrl && response.request().method() === 'POST');
  await menu.locator(`input[data-process-id="${other.process_id}"]`).click();
  await started;
  try {
    for (const toggle of await menu.getByRole('checkbox').all()) await expect(toggle).toBeDisabled();
  } finally { releaseFailure(); }
  const failedResponse = await failed; expect(failedResponse.status()).toBe(503);
  expect(failedResponse.request().postDataJSON()).toEqual(subset(ten, [target.process_id]));
  await expect(page.getByRole('alert')).toContainText(failure);
  expect(await visibleProcesses(page)).toEqual(pair);
  await expect(surface.getByRole('table')).toHaveAttribute('aria-rowcount', String(pairRows.items.length + 1));
  await expect(surface.locator('.history-result-summary')).toContainText(`${pairRows.matched_count} matches`);
  await expect(all).toBeEnabled(); await expect(all).toHaveJSProperty('indeterminate', true);
  await menu.locator('summary').click();

  // Both layouts retain the same independent selection. Split choices only
  // hide mounted panes; merged layout and page size use the effective subset.
  await surface.getByLabel('Result layout', { exact: true }).selectOption('split');
  await expect(surface.locator('.history-split > section:visible')).toHaveCount(2);
  await expect(surface.locator('.history-split > section[aria-busy="false"]')).toHaveCount(input.process_ids.length);
  const arrangement = surface.getByLabel('Pane arrangement', { exact: true });
  await arrangement.selectOption('4');
  await expect(surface.locator('.history-split')).toHaveCSS('grid-template-columns', /\S+\s+\S+\s+\S+\s+\S+/);
  const splitMenu = await processMenu(page);
  requests.length = 0; page.on('request', count);
  try {
    await splitMenu.locator(`input[data-process-id="${other.process_id}"]`).uncheck();
    await expect(surface.locator('.history-split > section:visible')).toHaveCount(1);
    expect(await surface.locator('.history-split').evaluate(element => getComputedStyle(element).gridTemplateColumns.split(/\s+/).length)).toBe(1);
    await splitMenu.locator(`input[data-process-id="${other.process_id}"]`).check();
    await expect(surface.locator('.history-split > section:visible')).toHaveCount(2);
    expect(requests).toEqual([]);
  } finally { page.off('request', count); }
  await splitMenu.locator('summary').click();
  await surface.getByLabel('Result layout', { exact: true }).selectOption('merged');
  await expect(arrangement).toBeDisabled(); await expect(arrangement).toHaveValue('4');
  expect(await visibleProcesses(page)).toEqual(pair);
  await queried(() => surface.getByLabel('Rows', { exact: true }).selectOption('50'), subset({ ...ten, limit: 50 }, pair));
  expect(await visibleProcesses(page)).toEqual(pair);
  await expectDiscardedDraft(page, draft, input.from);
  const edited: Query = { ...applied, from: '2026-10-16T12:00:00.000000Z', filter: { ...input.filter!, include: [draft] }, limit: 50 };
  const editedFilters = await openFilters(page);
  await editedFilters.getByLabel('From UTC (inclusive)', { exact: true }).fill(draftFrom);
  await addContentFilter(editedFilters, draft);
  await page.route(queryUrl, route => route.fulfill({ status: 503, json: { error: { code: 'FIXTURE_APPLY_UNAVAILABLE', message: failure } } }), { times: 1 });
  const failedApply = page.waitForResponse(response => response.url() === queryUrl && response.request().method() === 'POST');
  await editedFilters.getByRole('button', { name: 'Apply filters', exact: true }).click(); expect((await failedApply).status()).toBe(503);
  await expect(editedFilters).toBeVisible(); await expect(editedFilters.getByRole('alert')).toContainText(failure);
  expect(await visibleProcesses(page)).toEqual(pair);
  await queried(() => applyFilters(page), edited);
  expect(await visibleProcesses(page)).toEqual(input.process_ids);
  const editedMenu = await processMenu(page);
  await queried(() => editedMenu.locator(`input[data-process-id="${other.process_id}"]`).click(), subset(edited, input.process_ids.filter(id => id !== other.process_id)));
  await editedMenu.locator('summary').click();
  await queried(() => surface.getByRole('button', { name: /^Diagnostic lane/ }).click(), { ...edited, lane: 'diagnostic' });
  expect(await visibleProcesses(page)).toEqual(input.process_ids);
  await capture(page, 'merged-process-checkboxes', surface);
});

test('merged layout refreshes its limit after all panes are hidden and resized', async ({ page }) => {
  test.setTimeout(120000);
  await login(page); await openHistory(page); const { body, input, investigation } = await collect(page);
  const surface = resultsSurface(page);
  const size = surface.getByLabel('Rows', { exact: true });
  const layout = surface.getByLabel('Result layout', { exact: true });
  const queryUrl = new URL(`/api/v1/projects/${system}/investigations/${investigation}/query`, page.url()).href;
  const loadedTen = page.waitForResponse(response => response.url() === queryUrl && response.request().method() === 'POST');
  await size.selectOption('10');
  const tenResponse = await loadedTen; expect(tenResponse.status()).toBe(200);
  expect(tenResponse.request().postDataJSON()).toEqual({ ...input, limit: 10, cursor: null });
  const ten = await tenResponse.json() as Results;
  expect(ten.items).toHaveLength(10); expect(ten.next_cursor).not.toBeNull();
  await layout.selectOption('split');
  await expect(surface.locator('.history-split > section[aria-busy="false"]')).toHaveCount(input.process_ids.length);
  const menu = await processMenu(page);
  const all = menu.getByRole('checkbox', { name: 'All processes', exact: true });
  await all.uncheck(); await menu.locator('summary').click();
  await expect(surface.getByText('No processes selected', { exact: true })).toBeVisible();
  await size.selectOption('50');
  await expect(size).toHaveValue('50'); expect(await visibleProcesses(page)).toEqual([]);
  await processMenu(page); await all.check(); await menu.locator('summary').click();
  await expect(surface.locator('.history-split > section:visible')).toHaveCount(input.process_ids.length);
  const loadedFifty = page.waitForResponse(response => response.url() === queryUrl && response.request().method() === 'POST'
    && (response.request().postDataJSON() as Query).process_ids.length === input.process_ids.length);
  await layout.selectOption('merged');
  const response = await loadedFifty; expect(response.status()).toBe(200);
  expect(response.request().postDataJSON()).toEqual({ ...input, limit: 50, cursor: null });
  const fifty = await response.json() as Results;
  expect(fifty.items.map(event => event.event_id)).toEqual(body.items.slice(0, 50).map(event => event.event_id));
  expect(fifty.matched_count).toBe(body.matched_count);
  await expect(surface.getByRole('table')).toHaveAttribute('aria-rowcount', String(fifty.items.length + 1));
  await expect(surface.locator('.history-result-summary')).toContainText(`${fifty.items.length} rows on page 1`);
  await expect(surface.getByRole('button', { name: 'Previous result page', exact: true })).toBeDisabled();
  expect(await visibleProcesses(page)).toEqual(input.process_ids);
  await expect(surface.getByLabel('Pane arrangement', { exact: true })).toBeDisabled();
});

test('stacked and two to four column panes fit both themes and narrow or full screen result surfaces', async ({ page }) => {
  test.setTimeout(180000);
  await login(page); await openHistory(page); const { body } = await collect(page);
  const surface = resultsSurface(page);
  const arrangement = surface.getByLabel('Pane arrangement', { exact: true });
  await expect(arrangement).toBeVisible(); await expect(arrangement).toBeDisabled(); await expect(arrangement).toHaveValue('1');
  await expect(surface.getByLabel('Show process', { exact: true })).toBeVisible();
  await expect(surface.locator('.history-table-actions').getByLabel('Rows', { exact: true })).toHaveCount(0);
  await expect(surface.locator('.history-results-footer').getByLabel('Rows', { exact: true })).toBeVisible();
  await expect(surface.getByLabel('Rows', { exact: true }).locator('option')).toHaveText(['Viewport', '10', '50', '200']);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const toolbar = await surface.locator('.history-table-actions').evaluate(element => {
    const layout = element.querySelector('[aria-label="Result layout"]')!;
    const processes = element.querySelector('[aria-label="Show process"]')!;
    const panes = element.querySelector('[aria-label="Pane arrangement"]')!;
    return { layoutBeforeProcesses: Boolean(layout.compareDocumentPosition(processes) & Node.DOCUMENT_POSITION_FOLLOWING),
      processesBeforePanes: Boolean(processes.compareDocumentPosition(panes) & Node.DOCUMENT_POSITION_FOLLOWING),
      layoutRight: layout.getBoundingClientRect().right, processLeft: processes.getBoundingClientRect().left,
      processRight: processes.getBoundingClientRect().right, paneLeft: panes.getBoundingClientRect().left };
  });
  expect(toolbar.layoutBeforeProcesses).toBe(true); expect(toolbar.processesBeforePanes).toBe(true);
  expect(toolbar.processLeft).toBeGreaterThanOrEqual(toolbar.layoutRight); expect(toolbar.paneLeft).toBeGreaterThanOrEqual(toolbar.processRight);
  const requests: string[] = [];
  const count = (request: Request) => { if (/\/(query|collections|live-sessions)(\/|$)/.test(new URL(request.url()).pathname)) requests.push(request.method()); };
  page.on('request', count);
  try {
    await surface.getByLabel('Result layout', { exact: true }).selectOption('split');
    const grid = surface.locator('.history-split');
    await expect(arrangement).toHaveValue('1');
    await expect(arrangement.locator('option')).toHaveText(['Stacked', '2 columns', '3 columns', '4 columns']);
    await expect(grid.locator(':scope > section')).toHaveCount(new Set(body.items.map(event => event.process_id)).size);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }, { width: 640, height: 720 }]) {
        await page.setViewportSize(size);
        for (const columns of [1, 2, 3, 4]) {
          await arrangement.selectOption(String(columns));
          const geometry = await grid.evaluate(element => {
            const style = getComputedStyle(element);
            const panes = [...element.querySelectorAll(':scope > section')].map(pane => pane.getBoundingClientRect());
            return { tracks: style.gridTemplateColumns.split(/\s+/).length, columns: style.getPropertyValue('--history-pane-columns').trim(),
              starts: panes.map(pane => ({ left: pane.left, top: pane.top })), documentOverflow: document.documentElement.scrollWidth > innerWidth };
          });
          expect(geometry.tracks).toBe(columns); expect(geometry.columns).toBe(String(columns)); expect(geometry.documentOverflow).toBe(false);
          if (columns === 1) expect(geometry.starts[1].top).toBeGreaterThan(geometry.starts[0].top);
          else { expect(geometry.starts[1].top).toBe(geometry.starts[0].top); expect(geometry.starts[1].left).toBeGreaterThan(geometry.starts[0].left); }
          await capture(page, `${theme}-${size.width}x${size.height}-${columns}-pane-columns`, surface);
          const footer = await surface.locator('.history-results-footer').boundingBox();
          const data = await surface.locator('.history-result-body').boundingBox();
          expect(footer!.y).toBeGreaterThanOrEqual(data!.y + data!.height - 1);
          const rows = await surface.getByLabel('Rows', { exact: true }).boundingBox();
          expect(Math.abs(rows!.x + rows!.width - data!.x - data!.width)).toBeLessThanOrEqual(16);
        }
        await surface.getByRole('button', { name: 'Full screen', exact: true }).click();
        await expect(surface).toHaveAttribute('role', 'dialog');
        await expect(arrangement).toHaveValue('4');
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
        await capture(page, `${theme}-${size.width}x${size.height}-four-panes-full-screen`);
        await page.keyboard.press('Escape'); await expect(surface).toHaveAttribute('role', 'region');
      }
    }
    await surface.getByLabel('Result layout', { exact: true }).selectOption('merged');
    await expect(arrangement).toBeVisible(); await expect(arrangement).toBeDisabled(); await expect(arrangement).toHaveValue('4');
    await expect(surface.getByLabel('Show process', { exact: true })).toBeVisible();
    await surface.getByLabel('Result layout', { exact: true }).selectOption('split');
    await expect(surface.getByLabel('Pane arrangement', { exact: true })).toHaveValue('4');
    expect(requests).toEqual([]);
  } finally { page.off('request', count); }
});

test('Filters dialog validates UTC bounds and individual literal rules, applies scoped filters and discards closed drafts', async ({ page }) => {
  test.setTimeout(180000);
  await login(page); await openHistory(page); const { body, input, investigation } = await collect(page);
  const surface = resultsSurface(page);
  await expect(page.getByRole('group', { name: 'Collection time range', exact: true }).getByLabel('From UTC (inclusive)', { exact: true })).toHaveValue('2026-10-13 00:00:00');
  await expect(surface.getByLabel('From UTC (inclusive)', { exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Contains string', { exact: true })).toHaveCount(0);
  const queryUrl = new URL(`/api/v1/projects/${system}/investigations/${investigation}/query`, page.url()).href;
  const requests: string[] = [];
  const count = (request: Request) => { if (request.url() === queryUrl && request.method() === 'POST') requests.push(request.url()); };
  page.on('request', count);
  try {
    const dialog = await openFilters(page);
    await expect(dialog.getByRole('button', { name: 'Clear content filters', exact: true })).toBeDisabled();
    await dialog.getByLabel('From UTC (inclusive)', { exact: true }).fill('2026-10-18 00:00:00');
    await dialog.getByRole('button', { name: 'Apply filters', exact: true }).click();
    await expect(dialog.getByRole('alert')).toContainText('The exclusive end must follow the inclusive start.');
    expect(requests).toEqual([]);
    await dialog.getByRole('button', { name: 'Reset time range', exact: true }).click();
    await expect(dialog.getByLabel('From UTC (inclusive)', { exact: true })).toHaveValue(displayUtc(input.from));
    await expect(dialog.getByLabel('To UTC (exclusive)', { exact: true })).toHaveValue(displayUtc(input.to));
    await dialog.getByRole('button', { name: 'Add filter', exact: true }).click();
    await expect(dialog.getByRole('alert')).toContainText('Enter log content');
    await dialog.getByLabel('Log content', { exact: true }).fill('x'.repeat(513));
    await dialog.getByRole('button', { name: 'Add filter', exact: true }).click();
    await expect(dialog.getByRole('alert')).toContainText('Enter log content');
    const literal = body.items[0].raw_line.slice(-60);
    const absent = 'Synthetic absent literal! [brackets].* $()';
    const ownAbsent = 'Synthetic absent process exclusion';
    const processId = body.items[0].process_id;
    await addContentFilter(dialog, literal);
    await addContentFilter(dialog, literal);
    await addContentFilter(dialog, absent, 'exclude');
    await addContentFilter(dialog, ownAbsent, 'exclude', processId);
    await expect(dialog.locator('.history-filter-list > li')).toHaveCount(4);
    await dialog.getByRole('button', { name: 'Remove include filter 2 for All processes', exact: true }).click();
    await expect(dialog.locator('.history-filter-list > li')).toHaveCount(3);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await expect(dialog.locator('.history-filter-list > li')).toHaveCount(3);
      await capture(page, `${theme}-filters-dialog`, dialog);
    }
    expect(requests).toEqual([]);
    const filtered = page.waitForResponse(response => response.url() === queryUrl && response.request().method() === 'POST');
    await dialog.getByRole('button', { name: 'Apply filters', exact: true }).click();
    const response = await filtered; expect(response.status()).toBe(200);
    const expected: Query = { ...input, filter: { ...input.filter!, include: [literal], exclude: [absent] }, per_process_filters: {
      [processId]: { include: [], exclude: [ownAbsent], include_mode: input.filter!.include_mode, case_sensitive: input.filter!.case_sensitive },
    } };
    expect(response.request().postDataJSON()).toEqual(expected);
    const matches = await response.json() as Results;
    expect(matches.items.length).toBeGreaterThan(0);
    expect(matches.items.every(event => event.raw_line.includes(literal) && !event.raw_line.includes(absent))).toBe(true);
    await expect(dialog).toHaveCount(0);
    const reopened = await openFilters(page);
    await expect(reopened.locator('.history-filter-list > li')).toHaveCount(3);
    await reopened.getByRole('button', { name: 'Clear content filters', exact: true }).click();
    await expect(reopened.locator('.history-filter-list > li')).toHaveCount(0);
    const cleared = page.waitForResponse(value => value.url() === queryUrl && value.request().method() === 'POST');
    await reopened.getByRole('button', { name: 'Apply filters', exact: true }).click();
    const clearedResponse = await cleared; expect(clearedResponse.status()).toBe(200);
    expect(clearedResponse.request().postDataJSON()).toEqual(input);
    await expect(surface.getByRole('table')).toHaveAttribute('aria-rowcount', String(body.items.length + 1));
    const beforeClose = requests.length;
    await openFilters(page); await addContentFilter(reopened, 'Discarded when the dialog closes');
    await reopened.getByRole('button', { name: 'Close dialog', exact: true }).click();
    await expectDiscardedDraft(page, 'Discarded when the dialog closes', input.from);
    expect(requests.length).toBe(beforeClose);
  } finally { page.off('request', count); }
});
