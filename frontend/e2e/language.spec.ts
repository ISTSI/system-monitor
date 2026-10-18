import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { randomBytes } from 'node:crypto';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Preferences, Role, Settings } from '../src/api/types';
import type { LanguagePreference } from '../src/i18n/translate';
import { serveBuiltAssets } from './ui';

// This suite mutates preferences/defaults only in the isolated synthetic fixture.
test.skip(process.env.INSPECTOR_E2E_URL !== 'https://localhost:8449', 'Requires the isolated synthetic fixture on 8449.');
const errors = new WeakMap<BrowserContext, string[]>();
const workspaces = new WeakMap<BrowserContext, { project_id: string; workspace_id: string }[]>();
const screenshots = resolve('../verification/language-support/screenshots');

async function prepare(context: BrowserContext, baseURL: string) {
  const messages: string[] = []; errors.set(context, messages); workspaces.set(context, []);
  const monitor = (page: Page) => {
    page.on('pageerror', error => messages.push(error.message));
    page.on('response', response => {
      if (response.request().method() === 'POST' && /\/projects\/[^/]+\/workspaces$/.test(new URL(response.url()).pathname) && response.status() === 201) {
        void response.json().then(value => workspaces.get(context)?.push(value as { project_id: string; workspace_id: string }));
      }
    });
  };
  context.on('page', monitor); context.pages().forEach(monitor);
  await context.grantPermissions(['local-network-access'], { origin: baseURL });
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin === baseURL) return route.fallback();
    messages.push('External request blocked'); return route.abort();
  });
  await serveBuiltAssets(context, baseURL);
}

async function headers(context: BrowserContext, baseURL: string) {
  const response = await context.request.get('/api/v1/auth/csrf'); expect(response.status()).toBe(200);
  return { Origin: baseURL, 'X-CSRF-Token': (await response.json() as { csrf_token: string }).csrf_token };
}

async function cleanup(context: BrowserContext, baseURL: string) {
  if ((await context.request.get('/api/v1/auth/session')).status() === 200) {
    for (const workspace of workspaces.get(context) ?? []) {
      expect((await context.request.post(`/api/v1/projects/${workspace.project_id}/workspaces/${workspace.workspace_id}/detach`, { headers: await headers(context, baseURL), data: {} })).status()).toBe(200);
    }
    expect((await context.request.post('/api/v1/auth/logout', { headers: await headers(context, baseURL), data: {} })).status()).toBe(200);
  }
  expect(errors.get(context)).toEqual([]);
}

test.beforeEach(async ({ context, baseURL }) => { await prepare(context, baseURL!); });
test.afterEach(async ({ context, baseURL }) => { await cleanup(context, baseURL!); });

function account(role: Role) {
  if (!process.env.INSPECTOR_E2E_ACCOUNTS) throw new Error('Protected synthetic accounts are required.');
  return (JSON.parse(readFileSync(resolve(process.env.INSPECTOR_E2E_ACCOUNTS), 'utf8')) as Record<Role, { username: string; password: string }>)[role];
}

async function signIn(page: Page, credentials: { username: string; password: string }) {
  await page.goto('/');
  try {
    await page.locator('input[name="username"]').fill(credentials.username);
    await page.locator('input[name="password"]').fill(credentials.password);
    const submit = async () => {
      const saved = page.waitForResponse(response => response.url().endsWith('/api/v1/auth/login') && response.request().method() === 'POST');
      await page.locator('.login-card form button').click();
      return saved;
    };
    let response = await submit();
    if (response.status() === 429) {
      test.info().annotations.push({ type: 'rate-limit', description: 'The real login limit returned 429; waited 60 seconds for one bounded retry.' });
      test.info().setTimeout(test.info().timeout + 65000);
      await page.waitForTimeout(60000); response = await submit();
    }
    if (response.status() !== 200) throw new Error('Sign-in failed.');
    await expect(page.locator('.catalogue-page h1')).toBeVisible();
  } catch {
    await page.locator('input[type="password"]').fill('').catch(() => {});
    throw new Error('Synthetic sign-in failed; protected browser detail withheld.');
  }
}

async function preferences(page: Page): Promise<Preferences> {
  const response = await page.request.get('/api/v1/me/preferences'); expect(response.status()).toBe(200); return response.json() as Promise<Preferences>;
}

async function patchPreferences(page: Page, values: Partial<Pick<Preferences, 'theme_mode' | 'language'>>, baseURL: string) {
  const current = await preferences(page);
  expect((await page.request.patch('/api/v1/me/preferences', { headers: await headers(page.context(), baseURL), data: { ...values, expected_revision: current.revision } })).status()).toBe(200);
}

async function openPreferences(page: Page) {
  if (await page.locator('.account-menu').getAttribute('open') === null) await page.locator('.account-menu > summary').click();
  await page.getByRole('button', { name: /^(Preferences|Preferencje)$/ }).click();
  const dialog = page.getByRole('dialog', { name: /^(Preferences|Preferencje)$/ }); await expect(dialog).toBeVisible(); return dialog;
}

async function setLanguage(page: Page, language: LanguagePreference) {
  const dialog = await openPreferences(page);
  const saved = page.waitForResponse(response => response.url().endsWith('/api/v1/me/preferences') && response.request().method() === 'PATCH');
  await dialog.getByRole('combobox', { name: /^(Language|Język)$/ }).selectOption(language);
  expect((await saved).status()).toBe(200);
  await expect(dialog.getByRole('combobox', { name: /^(Language|Język)$/ })).toBeEnabled();
  await page.keyboard.press('Escape');
}

async function saveDefault(page: Page, language: 'en' | 'pl') {
  await page.getByRole('button', { name: /^(Settings|Ustawienia)$/ }).click();
  const dialog = page.getByRole('dialog', { name: /^(Settings|Ustawienia)$/ });
  await dialog.getByRole('combobox', { name: /^(Application default language|Domyślny język aplikacji)$/ }).selectOption(language);
  const saved = page.waitForResponse(response => response.url().endsWith('/api/v1/admin/settings') && response.request().method() === 'PATCH');
  await dialog.getByRole('button', { name: /^(Save application settings|Zapisz ustawienia aplikacji)$/ }).click();
  expect((await saved).status()).toBe(200);
  await expect(dialog.getByRole('status')).toContainText(/Application settings saved|Ustawienia aplikacji zostały zapisane/);
  await page.keyboard.press('Escape');
}

for (const role of ['administrator', 'inspector'] as const) test(`${role}: Polish persists across reload and same-account windows without replacing workspace state`, async ({ page, context, baseURL }) => {
  await signIn(page, account(role)); const original = await preferences(page);
  const targetActions: string[] = [];
  context.on('request', request => { if (/\/(collections|live-sessions|inventory\/commit|source-access\/test)(?:\?|$)/.test(new URL(request.url()).pathname) && request.method() === 'POST') targetActions.push(request.url()); });
  try {
    await setLanguage(page, 'en');
    await page.getByRole('link', { name: 'Open system', exact: true }).first().click();
    const workspace = page.getByTestId('workspace-id'); await expect(workspace).toHaveText(/^[0-9a-f]{8}-[0-9a-f-]{27}$/); const id = await workspace.innerText();
    const duplicate = await context.newPage(); await duplicate.goto(new URL(page.url()).pathname);
    await expect(duplicate.getByTestId('workspace-id')).toHaveText(/^[0-9a-f]{8}-[0-9a-f-]{27}$/); const duplicateId = await duplicate.getByTestId('workspace-id').innerText(); expect(duplicateId).not.toBe(id);
    const firstSearch = page.locator('.explorer-search input'); const secondSearch = duplicate.locator('.explorer-search input');
    await firstSearch.fill('language-state-A'); await secondSearch.fill('language-state-B');
    let newWorkspaces = 0; const count = (request: { url(): string; method(): string }) => { if (/\/workspaces$/.test(new URL(request.url()).pathname) && request.method() === 'POST') newWorkspaces++; }; context.on('request', count);
    await setLanguage(page, 'pl');
    await expect(page.locator('html')).toHaveAttribute('lang', 'pl'); await expect(duplicate.locator('html')).toHaveAttribute('lang', 'pl');
    await expect(page.getByRole('button', { name: 'Ustawienia', exact: true })).toHaveCount(role === 'administrator' ? 1 : 0);
    await expect(page.getByTestId('workspace-id')).toHaveText(id); await expect(duplicate.getByTestId('workspace-id')).toHaveText(duplicateId);
    await expect(firstSearch).toHaveValue('language-state-A'); await expect(secondSearch).toHaveValue('language-state-B');
    expect(newWorkspaces).toBe(0); context.off('request', count);
    expect((await preferences(page)).theme_mode).toBe(original.theme_mode);
    for (const mode of ['light', 'dark'] as const) {
      const dialog = await openPreferences(page); const saved = page.waitForResponse(response => response.url().endsWith('/api/v1/me/preferences') && response.request().method() === 'PATCH');
      await dialog.getByLabel('Wygląd', { exact: true }).selectOption(mode); expect((await saved).status()).toBe(200);
      await expect(page.locator('html')).toHaveAttribute('data-theme', mode);
      for (const width of [1280, 1920]) {
        await page.setViewportSize({ width, height: width === 1280 ? 720 : 1080 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        mkdirSync(screenshots, { recursive: true }); await page.screenshot({ path: resolve(screenshots, `${role}-pl-${mode}-${width}.png`), animations: 'disabled' });
      }
      await page.keyboard.press('Escape');
    }
    await page.reload(); await expect(page.locator('html')).toHaveAttribute('lang', 'pl');
    const dialog = await openPreferences(page); await expect(dialog.getByLabel('Język', { exact: true })).toHaveValue('pl'); await page.keyboard.press('Escape');
    if (role === 'inspector') expect((await page.request.get('/api/v1/admin/settings')).status()).toBe(403);
    expect(targetActions).toEqual([]); await duplicate.close();
  } finally { await patchPreferences(page, { theme_mode: original.theme_mode, language: original.language }, baseURL!); }
});

test('real language revision conflict retries while preserving appearance', async ({ page, baseURL }) => {
  await signIn(page, account('inspector')); const original = await preferences(page);
  try {
    await setLanguage(page, 'en'); const dialog = await openPreferences(page);
    await patchPreferences(page, { theme_mode: 'light' }, baseURL!);
    const rejected = page.waitForResponse(response => response.url().endsWith('/api/v1/me/preferences') && response.request().method() === 'PATCH');
    await dialog.getByLabel('Language', { exact: true }).selectOption('pl'); expect((await rejected).status()).toBe(409);
    await expect(dialog.getByRole('alert')).toContainText('Preferences changed in another window');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    const retried = page.waitForResponse(response => response.url().endsWith('/api/v1/me/preferences') && response.request().method() === 'PATCH');
    await dialog.getByRole('button', { name: 'Retry', exact: true }).click(); expect((await retried).status()).toBe(200);
    await expect(page.locator('html')).toHaveAttribute('lang', 'pl'); await expect(dialog.getByRole('alert')).toHaveCount(0);
    expect((await preferences(page)).theme_mode).toBe('light');
  } finally { await patchPreferences(page, { theme_mode: original.theme_mode, language: original.language }, baseURL!); }
});

test('shared language default reaches new accounts and mounted signed-out pages; explicit choices stay personal', async ({ page, context, browser, baseURL }) => {
  test.setTimeout(120000);
  const signedOut = await context.newPage(); await signedOut.goto('/'); await expect(signedOut.locator('.login-card form')).toBeVisible();
  await signIn(page, account('administrator')); const original = await preferences(page);
  const currentSettings = async () => { const response = await page.request.get('/api/v1/admin/settings'); expect(response.status()).toBe(200); return response.json() as Promise<Settings>; };
  const originalSettings = await currentSettings();
  const personalContext = await browser.newContext({ baseURL, ignoreHTTPSErrors: true }); await prepare(personalContext, baseURL!); const personal = await personalContext.newPage();
  let created: { user_id: string; auth_version: number } | null = null;
  const fresh = { username: `synthetic-language-${randomBytes(8).toString('hex')}`, password: randomBytes(32).toString('base64url') };
  try {
    await setLanguage(page, 'en'); await saveDefault(page, 'pl');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en'); await expect(signedOut.locator('html')).toHaveAttribute('lang', 'pl');
    await expect(signedOut.getByRole('button', { name: 'Zaloguj się', exact: true })).toBeVisible();
    mkdirSync(screenshots, { recursive: true });
    await signedOut.screenshot({ path: resolve(screenshots, 'signed-out-pl-login.png'), animations: 'disabled' });
    await setLanguage(page, 'pl');
    await page.getByRole('button', { name: 'Ustawienia', exact: true }).click();
    await expect(page.getByRole('dialog', { name: 'Ustawienia', exact: true })).toBeVisible();
    await page.screenshot({ path: resolve(screenshots, 'administrator-pl-settings.png'), animations: 'disabled' });
    await page.keyboard.press('Escape'); await setLanguage(page, 'en');
    const response = await page.request.post('/api/v1/admin/users', { headers: await headers(context, baseURL!), data: { ...fresh, display_name: 'Synthetic language verification', role: 'inspector', must_change_password: false } });
    expect(response.status()).toBe(201); created = await response.json() as { user_id: string; auth_version: number };
    await signIn(personal, fresh); expect((await preferences(personal)).language).toBe('default');
    await expect(personal.locator('html')).toHaveAttribute('lang', 'pl');
    await setLanguage(personal, 'en'); await saveDefault(page, 'en'); await saveDefault(page, 'pl'); await personal.reload();
    await expect(personal.locator('html')).toHaveAttribute('lang', 'en');
    await setLanguage(personal, 'default'); await expect(personal.locator('html')).toHaveAttribute('lang', 'pl');
    await saveDefault(page, 'en'); await personal.reload(); await expect(personal.locator('html')).toHaveAttribute('lang', 'en');
  } finally {
    if (created) expect((await page.request.patch(`/api/v1/admin/users/${created.user_id}`, { headers: await headers(context, baseURL!), data: { expected_auth_version: created.auth_version, enabled: false } })).status()).toBe(200);
    const current = await currentSettings(); expect((await page.request.patch('/api/v1/admin/settings', { headers: await headers(context, baseURL!), data: { expected_revision: current.revision, default_language: originalSettings.default_language } })).status()).toBe(200);
    await patchPreferences(page, { theme_mode: original.theme_mode, language: original.language }, baseURL!);
    await personalContext.close(); await signedOut.close(); expect(errors.get(personalContext)).toEqual([]);
  }
});

test('Polish switch preserves scrolled split historical panes and retained query state', async ({ page, context, baseURL }) => {
  test.setTimeout(90000);
  await signIn(page, account('administrator')); const original = await preferences(page);
  const project = 'stage7-fixture-a';
  type RetainedJob = { investigation_id: string; process_ids: string[]; from: string; to: string; event_count: number; status: string };
  try {
    await setLanguage(page, 'en');
    const list = await page.request.get(`/api/v1/projects/${project}/investigations`); expect(list.status()).toBe(200);
    const candidates = (await list.json() as { items: RetainedJob[] }).items.filter(item => item.event_count >= 8 && ['completed', 'partial'].includes(item.status)).sort((a, b) => b.event_count - a.event_count);
    let chosen: RetainedJob | undefined;
    for (const candidate of candidates.slice(0, 10)) {
      const result = await page.request.post(`/api/v1/projects/${project}/investigations/${candidate.investigation_id}/query`, {
        headers: await headers(context, baseURL!), data: { process_ids: candidate.process_ids, from: candidate.from, to: candidate.to, limit: 200, lane: 'events', filter: { include: [], exclude: [], include_mode: 'all', case_sensitive: true }, per_process_filters: {} },
      });
      if (result.status() !== 200) continue;
      const body = await result.json() as { items: { process_id: string }[] };
      const counts = new Map<string, number>(); for (const event of body.items) counts.set(event.process_id, (counts.get(event.process_id) ?? 0) + 1);
      if ([...counts.values()].some(amount => amount >= 8)) { chosen = candidate; break; }
    }
    expect(chosen, 'Synthetic cached history with at least eight retained rows in one process is required; this test starts no collection.').toBeDefined();
    const retained = chosen!;
    await page.goto(`/systems/${project}/investigations/${retained.investigation_id}`);
    await expect(page.locator('.virtual-logs').first()).toBeVisible();
    const workspace = await page.getByTestId('workspace-id').innerText();
    for (const process of await page.getByRole('group', { name: 'Configured processes', exact: true }).getByRole('checkbox').all()) await process.check();
    await page.getByLabel('From UTC (inclusive)', { exact: true }).fill(retained.from);
    await page.getByLabel('To UTC (exclusive)', { exact: true }).fill(retained.to);
    const clear = page.getByRole('button', { name: 'Clear filter', exact: true }); if (await clear.isEnabled()) await clear.click();
    await page.getByLabel('Rows per result page', { exact: true }).selectOption('200');
    const queried = page.waitForResponse(response => response.url().endsWith('/query') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Apply filter', exact: true }).click(); expect((await queried).status()).toBe(200);
    await page.getByLabel('Result layout', { exact: true }).selectOption('split');
    const panes = page.locator('.history-split .virtual-logs'); await expect(panes.first()).toBeVisible();
    let paneIndex = -1;
    for (let index = 0; index < await panes.count(); index++) if (Number(await panes.nth(index).getAttribute('aria-rowcount')) >= 9) { paneIndex = index; break; }
    expect(paneIndex).toBeGreaterThanOrEqual(0); const pane = panes.nth(paneIndex);
    await pane.evaluate(element => { element.style.height = '136px'; element.style.minHeight = '136px'; element.style.maxHeight = '136px'; element.scrollTop = 136; });
    await expect.poll(() => pane.evaluate(element => element.scrollTop)).toBe(136);
    const firstText = await pane.locator('.log-message').first().innerText();
    const unchangedRequests: string[] = []; const requests = (request: { method(): string; url(): string }) => {
      if (request.method() === 'POST' && /\/(query|collections|live-sessions|workspaces)(?:\/|$)/.test(new URL(request.url()).pathname)) unchangedRequests.push(request.url());
    };
    context.on('request', requests);
    await setLanguage(page, 'pl');
    await expect(page.locator('html')).toHaveAttribute('lang', 'pl');
    await expect(page.getByRole('heading', { name: 'Analiza historyczna', exact: true })).toBeVisible();
    await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
    await expect(page.getByLabel('Układ wyników', { exact: true })).toHaveValue('split');
    await expect.poll(() => pane.evaluate(element => element.scrollTop)).toBe(136);
    await expect(pane.locator('.log-message').first()).toHaveText(firstText);
    expect(unchangedRequests).toEqual([]); context.off('request', requests);
    mkdirSync(screenshots, { recursive: true });
    await pane.scrollIntoViewIfNeeded(); await page.screenshot({ path: resolve(screenshots, 'administrator-pl-split-history-preserved.png'), animations: 'disabled' });
  } finally { await patchPreferences(page, { theme_mode: original.theme_mode, language: original.language }, baseURL!); }
});
