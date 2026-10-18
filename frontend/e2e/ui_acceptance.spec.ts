import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { applyHistoricalFilters, fillHistoricalFilters, openPreferences, serveBuiltAssets, setAppearance, setHistoricalCollectionRange, submitSignIn, systemAction } from './ui';
import type { Config } from '../src/topology';

const enabled = process.env.INSPECTOR_E2E_URL === 'https://localhost:8449';
const root = resolve('..'); const output = resolve(root, 'verification/stage-7');
const fixture = enabled ? JSON.parse(readFileSync(resolve(root, '.state/stage7-browser/public-fixture.json'), 'utf8')) as { synthetic: boolean; host: string; projects: string[] } : null;
if (enabled && (!fixture?.synthetic || fixture.host !== 'stage7-sftp' || fixture.projects.join(',') !== 'stage7-fixture-a,stage7-fixture-b')) throw new Error('Only the isolated generated Stage 07 fixture is authorized.');
const [systemA, systemB] = fixture?.projects ?? ['stage7-fixture-a', 'stage7-fixture-b'];
const errors = new WeakMap<BrowserContext, string[]>();
test.skip(!enabled, 'Requires the isolated generated Stage 07 real MariaDB/SFTP fixture.');
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
      expect((await page.request.post('/api/v1/auth/logout', { headers: { Origin: baseURL!, 'X-CSRF-Token': csrf }, data: {} })).status()).toBe(200);
    }
  }
});
async function login(page: Page, role: 'administrator' | 'inspector') {
  const file = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!file) throw new Error('Protected synthetic accounts are required.');
  const account = (JSON.parse(readFileSync(resolve(file), 'utf8')) as Record<string, { username: string; password: string }>)[role];
  await page.goto('/'); await page.getByLabel('Username', { exact: true }).fill(account.username);
  try { await page.getByLabel('Password', { exact: true }).fill(account.password); expect((await submitSignIn(page)).status()).toBe(200); }
  catch { throw new Error('Synthetic sign-in failed; protected values withheld.'); }
  await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
}
async function capture(page: Page, name: string) {
  const directory = resolve(output, 'screenshots'); mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: resolve(directory, `${name}.png`), fullPage: /five-split|merged-live|system-b-live|filter-drawer|historical-merged|coverage|two-subsystem-reference/.test(name), animations: 'disabled' });
}
async function contrast(page: Page, name: string) {
  const report = await page.evaluate(() => {
    function rgba(value: string): number[] { return value.match(/[\d.]+/g)?.map(Number) ?? [0, 0, 0, 0]; }
    function blend(foreground: number[], background: number[]): number[] {
      const alpha = foreground[3] ?? 1; return [0, 1, 2].map(i => foreground[i] * alpha + background[i] * (1 - alpha)).concat(1);
    }
    function background(element: Element | null): number[] {
      if (!element) return [255, 255, 255, 1];
      const color = rgba(getComputedStyle(element).backgroundColor);
      return (color[3] ?? 1) === 1 ? color : blend(color, background(element.parentElement));
    }
    function luminance(color: number[]): number {
      const linear = color.slice(0, 3).map(c => c / 255 <= .04045 ? c / 255 / 12.92 : ((c / 255 + .055) / 1.055) ** 2.4);
      return linear[0] * .2126 + linear[1] * .7152 + linear[2] * .0722;
    }
    const failures: { text: string; ratio: number; target: number; color: string; background: number[] }[] = []; let checked = 0;
    for (const element of document.querySelectorAll('body *')) {
      if (!(element instanceof HTMLElement) || element.closest('svg,option,[inert],button:disabled,input:disabled,select:disabled')) continue;
      const bounds = element.getBoundingClientRect(); const style = getComputedStyle(element);
      if (!bounds.width || !bounds.height || bounds.bottom < 0 || bounds.top > innerHeight || style.visibility === 'hidden' || style.display === 'none' || Number(style.opacity) < 1) continue;
      const text = [...element.childNodes].filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent).join('').trim();
      if (!text) continue;
      const bg = background(element); const fg = blend(rgba(style.color), bg);
      const first = luminance(fg); const second = luminance(bg); const ratio = (Math.max(first, second) + .05) / (Math.min(first, second) + .05);
      const size = parseFloat(style.fontSize); const target = size >= 24 || size >= 18.66 && Number(style.fontWeight) >= 700 ? 3 : 4.5;
      checked += 1;
      if (ratio + .03 < target) failures.push({ text: text.slice(0, 80), ratio, target, color: style.color, background: bg });
    }
    const focused = document.activeElement;
    let focus: { ratio: number; width: number; style: string } | null = null;
    if (focused instanceof HTMLElement && focused.matches(':focus-visible')) {
      const style = getComputedStyle(focused); const bg = background(focused.parentElement);
      const first = luminance(blend(rgba(style.outlineColor), bg)); const second = luminance(bg);
      focus = { ratio: (Math.max(first, second) + .05) / (Math.min(first, second) + .05), width: parseFloat(style.outlineWidth), style: style.outlineStyle };
    }
    return { checked, failures, focus };
  });
  mkdirSync(output, { recursive: true }); writeFileSync(resolve(output, `contrast-${name}.json`), JSON.stringify(report, null, 2));
  expect(report.checked).toBeGreaterThan(10); expect(report.failures).toEqual([]);
  if (/keyboard-focus$/.test(name)) expect(report.focus).not.toBeNull();
  if (report.focus) { expect(report.focus.style).not.toBe('none'); expect(report.focus.width).toBeGreaterThanOrEqual(2); expect(report.focus.ratio).toBeGreaterThanOrEqual(3); }
}
async function openSystem(page: Page, id = systemA, section = 'topology') {
  await page.goto(`/systems/${id}/${section}`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await expect(page).toHaveTitle(id === systemA ? /— .*A —/ : id === systemB ? /— .*B —/ : /System Inspector —/);
}
async function startFive(page: Page) {
  await page.getByRole('button', { name: /^Live monitor/ }).click();
  const choices = page.getByRole('group', { name: 'Processes to monitor', exact: true }).getByRole('checkbox');
  expect(await choices.count()).toBe(5);
  for (const box of await choices.all()) await box.check();
  const pending = page.waitForResponse(response => response.url().endsWith('/live-sessions') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Monitor selected', exact: true }).click();
  const response = await pending; expect(response.status()).toBe(202);
  const body = response.request().postDataJSON() as { seed_rows: number };
  expect(body.seed_rows).toBeGreaterThan(1);
  await expect(page.getByText('Stream connected', { exact: true })).toBeVisible();
  await expect(page.locator('.live-event').first()).toBeVisible();
  return await page.getByTestId('live-session-id').innerText();
}

for (const role of ['administrator', 'inspector'] as const) test(`${role} visual matrix, keyboard, parser diagnostics, zoom, independent five-source windows and durable themes`, async ({ page, context }) => {
  test.setTimeout(240000); await login(page, role);
  const observations: unknown[] = [];
  await openSystem(page);
  for (const theme of ['light', 'dark'] as const) {
    await setAppearance(page, theme);
    for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
      await page.setViewportSize(size); const label = `${role}-${theme}-${size.width}`;
      await page.getByRole('button', { name: 'Select process ingest-instance-a', exact: true }).click();
      await expect(page.getByRole('region', { name: 'Process details', exact: true })).toContainText('Unknown');
      await capture(page, `${label}-topology-process`); await contrast(page, `${label}-topology`);
      const preferences = await openPreferences(page);
      await expect(preferences.getByLabel('Appearance', { exact: true })).toBeEnabled();
      await expect(preferences.getByRole('combobox', { name: 'Application default appearance', exact: true })).toHaveCount(0);
      await capture(page, `${label}-preferences`); await contrast(page, `${label}-preferences`);
      await page.keyboard.press('Escape');
      if (role === 'administrator') {
        await page.getByRole('button', { name: 'Settings', exact: true }).click();
        const settings = page.getByRole('dialog', { name: 'Settings', exact: true });
        await expect(settings.getByLabel('Appearance', { exact: true })).toHaveCount(0);
        await expect(settings.getByRole('combobox', { name: 'Application default appearance', exact: true })).toBeEnabled();
        await capture(page, `${label}-settings`); await contrast(page, `${label}-settings`);
        await page.keyboard.press('Escape');
        const menu = page.getByRole('button', { name: 'System', exact: true }); await menu.focus();
        await page.keyboard.press('ArrowDown'); await expect(page.getByRole('menuitem').first()).toBeFocused();
        await capture(page, `${label}-system-menu`); await contrast(page, `${label}-menu`);
        await page.keyboard.press('End'); await expect(page.getByRole('menuitem').last()).toBeFocused();
        await page.keyboard.press('Escape'); await expect(menu).toBeFocused();
        expect(await menu.evaluate(element => getComputedStyle(element).outlineStyle)).not.toBe('none');
        await contrast(page, `${label}-keyboard-focus`);
        for (const action of ['Add subsystem', 'Add server', 'Add process', 'Add flow']) {
          await systemAction(page, action); await capture(page, `${label}-${action.toLowerCase().replaceAll(' ', '-')}`); await page.keyboard.press('Escape');
        }
        await systemAction(page, 'List connections'); await capture(page, `${label}-connection-list`);
        await page.getByRole('button', { name: /^Password and test / }).first().click();
        const connectionTest = page.getByRole('dialog', { name: 'SSH password & connection test', exact: true });
        await expect(connectionTest.getByRole('button', { name: 'Test configured log paths', exact: true })).toBeEnabled();
        await connectionTest.getByRole('button', { name: 'Test configured log paths', exact: true }).click();
        await expect(connectionTest.locator('.source-path-results')).toContainText('Accessible');
        await capture(page, `${label}-configured-path-checks`); await page.keyboard.press('Escape');
        await systemAction(page, 'Import Ansible inventory files');
        await expect(page.getByRole('dialog', { name: 'Import Ansible inventory files', exact: true })).toBeVisible();
        await expect(page.getByLabel('Existing inventory source', { exact: true })).toBeEnabled();
        await contrast(page, `${label}-inventory`); await page.keyboard.press('Escape');
        await systemAction(page, 'Import configuration'); await capture(page, `${label}-config-import-empty`);
        const importDialog = page.getByRole('dialog', { name: 'Import configuration', exact: true });
        await importDialog.getByLabel('Configuration content', { exact: true }).fill('{invalid');
        await importDialog.getByRole('button', { name: 'Preview configuration', exact: true }).click();
        await expect(importDialog.getByRole('alert')).toBeVisible(); await capture(page, `${label}-config-import-error`); await page.keyboard.press('Escape');
        await page.getByRole('button', { name: 'Accounts', exact: true }).click();
        await expect(page.locator('.account-row').first()).toBeVisible(); await capture(page, `${label}-accounts`);
        await page.getByRole('button', { name: '+ Create account', exact: true }).click(); await capture(page, `${label}-account-create`); await page.keyboard.press('Escape');
        await systemAction(page, 'List Parsers');
        await page.getByRole('button', { name: /^Edit parser / }).first().click();
        const dialog = page.getByRole('dialog', { name: 'Edit parser', exact: true });
        await expect(dialog).toBeVisible();
        await dialog.getByLabel('Parser sample', { exact: true }).fill('2026-10-16T12:00:00.123456Z request_id=REQ-0042\ninvalid');
        const request = page.waitForResponse(response => response.url().endsWith('/parsers/test'));
        await dialog.getByRole('button', { name: 'Test parser sample', exact: true }).click(); expect((await request).status()).toBe(200);
        await expect(dialog.getByRole('region', { name: 'Parser sample results', exact: true })).toContainText('Unknown timestamp');
        await capture(page, `${label}-parser-preview`); await contrast(page, `${label}-parser`);
        await dialog.getByLabel('Parser sample', { exact: true }).fill('x'.repeat(4097));
        await dialog.getByRole('button', { name: 'Test parser sample', exact: true }).click();
        await expect(dialog.getByRole('alert')).toContainText('4 KiB'); await capture(page, `${label}-parser-limit-error`);
        const uploadedSample = '2026-10-16T12:00:00.654321Z INFO request_id=UPLOAD-0123\nuntimed uploaded text';
        await dialog.getByLabel('Upload parser sample', { exact: true }).setInputFiles({ name: 'parser-sample.txt', mimeType: 'text/plain', buffer: Buffer.from(uploadedSample) });
        await expect(dialog.getByLabel('Parser sample', { exact: true })).toHaveValue(uploadedSample);
        const uploadedTest = page.waitForResponse(response => response.url().endsWith('/parsers/test'));
        await dialog.getByRole('button', { name: 'Test parser sample', exact: true }).click(); expect((await uploadedTest).status()).toBe(200);
        await expect(dialog.getByRole('region', { name: 'Parser sample results', exact: true })).toContainText('UPLOAD-0123');
        await expect(dialog.getByRole('region', { name: 'Parser sample results', exact: true })).toContainText('2026-10-16T12:00:00.654321Z');
        await expect(dialog.getByRole('region', { name: 'Parser sample results', exact: true })).toContainText('Unknown timestamp');
        await capture(page, `${label}-parser-uploaded-sample`);
        await page.keyboard.press('Escape');
      } else {
        await expect(page.getByRole('button', { name: 'Settings', exact: true })).toHaveCount(0);
        await expect(page.getByRole('button', { name: 'System', exact: true })).toHaveCount(0);
        await page.getByRole('link', { name: 'Systems', exact: true }).click();
        await page.getByLabel('Find a system', { exact: true }).fill('no-synthetic-system-matches-this');
        await capture(page, `${label}-catalogue-empty`);
        await openSystem(page);
      }
      // A native dialog keeps keyboard focus within its controls in both themes.
      await openPreferences(page);
      await page.getByLabel('Appearance', { exact: true }).focus();
      await page.keyboard.press('Tab');
      expect(await page.evaluate(() => !!document.activeElement?.closest('dialog[open]'))).toBe(true);
      await contrast(page, `${label}-dialog-keyboard-focus`);
      await page.keyboard.press('Escape');
      await page.locator('.account-menu > summary').click(); await capture(page, `${label}-account-menu`);
      await page.getByRole('button', { name: 'Change password', exact: true }).click();
      await capture(page, `${label}-password-dialog`); await page.keyboard.press('Escape');
    }
  }
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.locator('body').click({ position: { x: 1, y: 1 } }); await page.keyboard.press('Control+k');
  await expect(page.getByRole('textbox', { name: /Search (this|system|topology)/i })).toBeFocused();
  await page.keyboard.type('ingest-instance-a'); await expect(page.locator('.search-results')).toContainText('ingest-instance-a');
  await page.getByRole('textbox', { name: /Search (this|system|topology)/i }).fill('');
  // Exercise 200% text/component scaling and separately the 640x360 CSS
  // viewport used by desktop zoom, so responsive media queries are tested too.
  await page.evaluate(() => { document.documentElement.style.zoom = '2'; });
  await openPreferences(page);
  await expect(page.getByLabel('Appearance', { exact: true })).toBeInViewport();
  await capture(page, `${role}-zoom-200-preferences`); await page.keyboard.press('Escape');
  await page.evaluate(() => { document.documentElement.style.zoom = ''; });
  await page.setViewportSize({ width: 640, height: 360 });
  await openPreferences(page);
  await expect(page.getByLabel('Appearance', { exact: true })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await capture(page, `${role}-zoom-logical-reflow-preferences`); await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 1280, height: 720 });
  await openSystem(page, systemA, 'logs'); const first = await startFive(page);
  const secondPage = await context.newPage(); await openSystem(secondPage, systemB, 'logs'); const second = await startFive(secondPage);
  expect(first).not.toBe(second);
  const firstWorkspace = await page.getByTestId('workspace-id').innerText(); const otherWorkspace = await secondPage.getByTestId('workspace-id').innerText(); expect(firstWorkspace).not.toBe(otherWorkspace);
  const filterChange = page.waitForResponse(response => response.url().endsWith('/filters') && response.request().method() === 'PUT');
  await page.getByLabel('Live contains string', { exact: true }).focus(); await page.keyboard.type('REQ-0042'); expect((await filterChange).status()).toBe(200); await expect(page.locator('.live-filter-state')).toHaveText(/^Applied version/);
  await expect(page.locator('.live-message mark').first()).toHaveText('REQ-0042');
  await expect(secondPage.getByLabel('Live contains string', { exact: true })).toHaveValue('');
  await page.getByRole('button', { name: 'Pause display', exact: true }).focus(); await page.keyboard.press('Space');
  for (const theme of ['light', 'dark'] as const) {
    await expect(page.locator('.live-filter-state')).toHaveText(/^Applied version/);
    const filterVersion = await page.getByTestId('live-filter-version').innerText();
    if (role === 'administrator') {
      await systemAction(page, 'Add subsystem');
      const draft = page.getByRole('dialog', { name: 'Add subsystem', exact: true });
      await draft.getByLabel('Name', { exact: true }).fill('Unsaved local draft');
      await setAppearance(page, theme); await expect(draft.getByLabel('Name', { exact: true })).toHaveValue('Unsaved local draft');
      await page.keyboard.press('Escape');
    } else await setAppearance(page, theme);
    await expect(page.getByTestId('live-session-id')).toHaveText(first); await expect(page.getByTestId('live-filter-version')).toHaveText(filterVersion);
    await expect(page.getByRole('button', { name: 'Resume display', exact: true })).toBeVisible();
    await expect(secondPage.getByRole('button', { name: 'Pause display', exact: true })).toBeVisible();
    for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
      await page.setViewportSize(size); await secondPage.setViewportSize(size);
      const prefix = `${role}-${theme}-${size.width}`;
      await capture(page, `${prefix}-system-a-merged-live`); await capture(secondPage, `${prefix}-system-b-live`);
      const splitChange = page.waitForResponse(response => response.url().endsWith('/filters') && response.request().method() === 'PUT');
      await page.getByLabel('Live pane layout', { exact: true }).selectOption('split'); expect((await splitChange).status()).toBe(200);
      await expect(page.locator('.live-filter-state')).toHaveText(/^Applied version/);
      await expect(page.locator('.live-panes.split > section')).toHaveCount(5);
      await expect(page.locator('.live-message mark').first()).toHaveText('REQ-0042');
      await capture(page, `${prefix}-five-split-live`);
      await page.locator('.live-message mark').first().scrollIntoViewIfNeeded();
      await expect(page.locator('.live-message mark').first()).toBeInViewport();
      await capture(page, `${prefix}-literal-highlights`); await contrast(page, `${prefix}-log-highlights`);
      const selectedText = await page.locator('.live-message').first().evaluate(element => {
        const range = document.createRange(); range.selectNodeContents(element);
        const selection = window.getSelection(); selection?.removeAllRanges(); selection?.addRange(range);
        return { selected: selection?.toString(), original: element.textContent };
      });
      expect(selectedText.selected).toBe(selectedText.original); await capture(page, `${prefix}-selected-log-text`);
      await page.evaluate(() => window.getSelection()?.removeAllRanges());
      await page.getByRole('region', { name: 'Live monitor', exact: true }).getByText('Advanced literal filters', { exact: true }).first().click(); await capture(page, `${prefix}-live-filter-drawer`);
      await page.getByRole('region', { name: 'Live monitor', exact: true }).getByText('Advanced literal filters', { exact: true }).first().click();
      const mergedChange = page.waitForResponse(response => response.url().endsWith('/filters') && response.request().method() === 'PUT');
      await page.getByLabel('Live pane layout', { exact: true }).selectOption('merged'); expect((await mergedChange).status()).toBe(200);
      await expect(page.locator('.live-filter-state')).toHaveText(/^Applied version/);
    }
  }
  observations.push({ first, second, firstWorkspace, otherWorkspace, independent_filters: true, themes_preserve_lease: true });
  await page.getByRole('button', { name: 'Stop this monitor', exact: true }).click(); await expect(page.getByTestId('live-session-state')).toHaveText('stopped');
  await expect(secondPage.getByTestId('live-session-state')).toHaveText('following');
  await secondPage.getByRole('button', { name: 'Stop this monitor', exact: true }).click(); await expect(secondPage.getByTestId('live-session-state')).toHaveText('stopped');
  const duplicate = await context.newPage(); await openSystem(duplicate, systemA, 'logs');
  expect(await duplicate.getByTestId('workspace-id').innerText()).not.toBe(firstWorkspace);
  await expect(duplicate.getByTestId('live-session-id')).toHaveCount(0);
  await duplicate.close(); await secondPage.close();
  await page.getByRole('link', { name: 'Log history', exact: true }).click();
  const processes = page.getByRole('group', { name: 'Configured processes', exact: true }).getByRole('checkbox');
  for (const box of await processes.all()) await box.check();
  await setHistoricalCollectionRange(page, { from: '2026-10-16T12:00:00.000000Z', to: '2026-10-16T12:00:02.000000Z' });
  await page.getByRole('button', { name: 'Collect sources', exact: true }).click();
  await expect(page.getByTestId('collection-state')).toHaveText('completed', { timeout: 30000 });
  await expect(page.getByTestId('match-count')).toContainText('matches');
  await fillHistoricalFilters(page, { filter: { include: ['REQ-0042'], exclude: [], include_mode: 'all', case_sensitive: true }, per_process_filters: {} });
  const historicalFilter = page.waitForResponse(response => response.url().endsWith('/query') && response.request().method() === 'POST');
  await applyHistoricalFilters(page); expect((await historicalFilter).status()).toBe(200);
  await expect(page.locator('.log-message mark').first()).toHaveText('REQ-0042');
  for (const theme of ['light', 'dark'] as const) {
    await setAppearance(page, theme);
    for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
      await page.setViewportSize(size); const label = `${role}-${theme}-${size.width}`;
      await capture(page, `${label}-historical-merged`);
      await page.locator('.log-message mark').first().scrollIntoViewIfNeeded();
      await expect(page.locator('.log-message mark').first()).toBeInViewport(); await contrast(page, `${label}-historical-highlights`);
      await page.getByText('Per-source coverage and failures', { exact: true }).click();
      await capture(page, `${label}-coverage`); await page.getByText('Per-source coverage and failures', { exact: true }).click();
      await page.getByRole('button', { name: 'Import offline bundle', exact: true }).click();
      await capture(page, `${label}-offline-import`);
      await page.getByRole('button', { name: 'Validate and preview bundle', exact: true }).click();
      await expect(page.getByRole('dialog').getByRole('alert')).toBeVisible(); await capture(page, `${label}-offline-import-error`); await page.keyboard.press('Escape');
    }
  }
  mkdirSync(output, { recursive: true }); writeFileSync(resolve(output, `${role}-ui-observations.json`), JSON.stringify(observations, null, 2));
});

test('two-subsystem reference layout remains readable for both roles, themes and desktop sizes', async ({ page, baseURL }) => {
  test.setTimeout(120000); await login(page, 'administrator');
  const csrf = (await (await page.request.get('/api/v1/auth/csrf')).json()).csrf_token as string;
  const headers = { Origin: baseURL!, 'X-CSRF-Token': csrf };
  const created = await page.request.post('/api/v1/projects', { headers, data: { name: '[Synthetic] Two-subsystem visual acceptance', description: 'Isolated visual fixture; no target approved or accessed.' } });
  expect(created.status()).toBe(201); const id = (await created.json()).project_id as string;
  const config = (await (await page.request.get(`/api/v1/projects/${systemA}/topology`)).json()).config as Config;
  config.project = { ...config.project, id, name: '[Synthetic] Two-subsystem visual acceptance', revision: 1 };
  const [gateway, processing] = config.subsystems;
  gateway.name = 'Gateway'; processing.name = 'Processing'; config.subsystems = [gateway, processing];
  config.servers.forEach((server, index) => { server.subsystem_id = index === 0 ? gateway.id : processing.id; });
  const nodes = [
    { element_id: gateway.id, x: 20, y: 20, width: 380, height: 600, collapsed: false },
    { element_id: processing.id, x: 440, y: 20, width: 800, height: 600, collapsed: false },
    ...config.servers.map((server, index) => ({ element_id: server.id, x: index === 2 ? 410 : 20, y: 70, width: 340, height: 480, collapsed: false })),
    ...config.processes.map(process => ({ element_id: process.id, x: 20, y: 80 + config.processes.filter(other => other.server_id === process.server_id).findIndex(other => other.id === process.id) * 110, width: 290, height: 85, collapsed: false })),
  ];
  config.views = [{ id: 'visual-reference', name: 'Two subsystems', nodes, flow_ids: config.flows.map(flow => flow.id) }];
  const saved = await page.request.put(`/api/v1/projects/${id}/topology`, { headers, data: { expected_revision: 1, config } }); expect(saved.status()).toBe(200);
  for (const role of ['administrator', 'inspector'] as const) {
    if (role === 'inspector') { expect((await page.request.post('/api/v1/auth/logout', { headers, data: {} })).status()).toBe(200); await login(page, role); }
    await openSystem(page, id);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
        await page.setViewportSize(size);
        await page.getByRole('button', { name: 'Select process parser-instance-a', exact: true }).click();
        await page.getByRole('button', { name: 'Fit diagram', exact: true }).click();
        await expect(page.locator('.diagram-node.subsystem-card')).toHaveCount(2);
        await expect.poll(async () => (await page.locator('.diagram-node.subsystem-card').first().boundingBox())?.width ?? 0).toBeGreaterThan(160);
        await capture(page, `${role}-${theme}-${size.width}-two-subsystem-reference`);
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
      }
    }
  }
});

test('login, real loading and account-wide logout states follow both application defaults', async ({ page, context, baseURL }) => {
  test.setTimeout(180000); await login(page, 'administrator');
  const original = await (await page.request.get('/api/v1/admin/settings')).json() as { branding: string; revision: number; default_theme_mode: string; additional_security_measures: boolean };
  async function updateDefault(mode: string) {
    const settings = await (await page.request.get('/api/v1/admin/settings')).json() as typeof original;
    const csrf = (await (await page.request.get('/api/v1/auth/csrf')).json()).csrf_token as string;
    expect((await page.request.patch('/api/v1/admin/settings', { headers: { Origin: baseURL!, 'X-CSRF-Token': csrf }, data: { expected_revision: settings.revision, branding: original.branding, default_theme_mode: mode, additional_security_measures: original.additional_security_measures } })).status()).toBe(200);
    return csrf;
  }
  try {
    for (const theme of ['light', 'dark'] as const) {
      const csrf = await updateDefault(theme);
      expect((await page.request.post('/api/v1/auth/logout', { headers: { Origin: baseURL!, 'X-CSRF-Token': csrf }, data: {} })).status()).toBe(200);
      let release!: () => void;
      const gate = new Promise<void>(resolveGate => { release = resolveGate; });
      await context.route('**/api/v1/ui/bootstrap', async route => { await gate; await route.continue(); });
      try {
        await page.goto('/', { waitUntil: 'domcontentloaded' });
        await expect(page.getByText('Preparing your workspace…', { exact: true })).toBeVisible();
        await capture(page, `public-${theme}-loading-real-bootstrap`);
      } finally { release(); }
      await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
      await context.unroute('**/api/v1/ui/bootstrap');
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) { await page.setViewportSize(size); await capture(page, `public-${theme}-${size.width}-login`); await contrast(page, `public-${theme}-${size.width}-login`); }
      await page.getByLabel('Username', { exact: true }).fill('synthetic-missing-account');
      await page.getByLabel('Password', { exact: true }).fill('Synthetic-invalid-example-0123');
      expect((await submitSignIn(page)).status()).toBe(401); await expect(page.getByRole('alert')).toBeVisible(); await capture(page, `public-${theme}-login-error`);
      await login(page, 'administrator'); await openSystem(page);
      const other = await context.newPage(); await openSystem(other, systemB);
      await page.locator('.account-menu > summary').click(); await page.getByRole('button', { name: 'Sign out all windows', exact: true }).click();
      await expect(page.getByLabel('Username', { exact: true })).toBeVisible(); await expect(other.getByLabel('Username', { exact: true })).toBeVisible();
      await capture(page, `public-${theme}-logout-own-window`); await capture(other, `public-${theme}-logout-other-window`);
      await other.close(); await login(page, 'administrator');
    }
  } finally { await updateDefault(original.default_theme_mode); }
});
