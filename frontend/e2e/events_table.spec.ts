import { expect, test, type BrowserContext, type Locator, type Page, type Request } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { serveBuiltAssets, setAppearance, submitSignIn } from './ui';
import type { components } from '../src/api/schema';
import type { Preferences } from '../src/api/types';

type Results = components['schemas']['HistoricalQueryResponse'];
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
  await page.goto('/'); await page.getByLabel('Username', { exact: true }).fill(account.username);
  try { await page.getByLabel('Password', { exact: true }).fill(account.password); expect((await submitSignIn(page)).status()).toBe(200); }
  catch { throw new Error('Synthetic sign-in failed; protected values withheld.'); }
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
  await page.getByLabel('From UTC (inclusive)', { exact: true }).fill('2026-10-13 00:00:00');
  await page.getByLabel('To UTC (exclusive)', { exact: true }).fill('2026-10-17 00:00:00');
  await page.getByLabel('Rows per result page', { exact: true }).selectOption('200');
  const loaded = page.waitForResponse(response => response.url().endsWith('/query') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Collect sources', exact: true }).click();
  await expect(page.getByTestId('collection-state')).toHaveText('completed', { timeout: 30000 });
  const response = await loaded; expect(response.status()).toBe(200);
  const body = await response.json() as Results;
  expect(body.items.length).toBeGreaterThan(20);
  await expect(page.locator('.virtual-logs .log-event').first()).toBeVisible();
  return { body, investigation: await page.getByTestId('investigation-id').innerText() };
}

async function columns(page: Page): Promise<Locator> {
  const surface = resultsSurface(page);
  const menu = surface.locator('details').filter({ has: page.locator('summary', { hasText: /^Columns$/ }) });
  if (await menu.getAttribute('open') === null) await menu.locator('summary').click();
  await expect(menu.getByRole('checkbox', { name: 'Log entry', exact: true })).toBeChecked();
  await expect(menu.getByRole('checkbox', { name: 'Log entry', exact: true })).toBeDisabled();
  return menu;
}

async function capture(page: Page, name: string) {
  const directory = resolve(root, 'verification/stage-7/screenshots'); mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: resolve(directory, `events-table-${name}.png`), animations: 'disabled' });
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

test('column and full screen controls stay local to same-account pages and apply across split panes', async ({ page, context }) => {
  test.setTimeout(120000);
  await login(page); await openHistory(page); const { investigation } = await collect(page);
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
    await resultsSurface(page).getByRole('button', { name: 'Full screen', exact: true }).click();
    await expect(resultsSurface(page)).toHaveAttribute('role', 'dialog');
    await expect(duplicateSurface).toHaveAttribute('role', 'region');
    await expect(duplicate.getByLabel('Result layout', { exact: true })).toHaveValue('merged');
    await expect(duplicateSurface.getByRole('columnheader', { name: 'Host', exact: true })).toBeVisible();
    await expect(duplicateSurface.getByRole('columnheader', { name: 'Process', exact: true })).toBeVisible();
    await expect(duplicate.getByTestId('investigation-id')).toHaveText(investigation);
    const duplicateMenu = await columns(duplicate);
    await expect(duplicateMenu.getByRole('checkbox', { name: 'Host', exact: true })).toBeChecked();
    await expect(duplicateMenu.getByRole('checkbox', { name: 'Process', exact: true })).toBeChecked();
    await duplicateMenu.locator('summary').click();
    await page.keyboard.press('Escape'); await expect(resultsSurface(page)).toHaveAttribute('role', 'region');
    await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
  } finally { await duplicate.close(); }
});
