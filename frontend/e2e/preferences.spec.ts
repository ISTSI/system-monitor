import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { randomBytes } from 'node:crypto';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Preferences, Role, Settings, ThemeMode } from '../src/api/types';
import { openPreferences, serveBuiltAssets, submitSignIn } from './ui';

// These tests change only the disposable Stage 07 fixture's account preferences
// and shared default. Never run them against the installed local deployment.
test.skip(process.env.INSPECTOR_E2E_URL !== 'https://localhost:8449', 'Requires the isolated synthetic Stage 07 fixture.');
const screenshots = resolve('../verification/stage-7/screenshots');
const browserErrors = new WeakMap<BrowserContext, string[]>();

async function prepare(context: BrowserContext, baseURL: string) {
  const errors: string[] = []; browserErrors.set(context, errors);
  context.on('page', page => page.on('pageerror', error => errors.push(error.message)));
  for (const page of context.pages()) page.on('pageerror', error => errors.push(error.message));
  await context.grantPermissions(['local-network-access'], { origin: baseURL });
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin === baseURL) return route.fallback();
    errors.push('External request blocked'); return route.abort();
  });
  await serveBuiltAssets(context, baseURL);
}

test.beforeEach(async ({ context, baseURL }) => { await prepare(context, baseURL!); });
test.afterEach(async ({ context, baseURL }) => {
  try { expect(browserErrors.get(context)).toEqual([]); }
  finally { await logout(context, baseURL!); }
});

function account(role: Role) {
  const filename = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!filename) throw new Error('Protected synthetic-account fixture is required.');
  return (JSON.parse(readFileSync(resolve(filename), 'utf8')) as Record<Role, { username: string; password: string }>)[role];
}

async function signIn(page: Page, credentials: { username: string; password: string }) {
  await page.goto('/');
  await page.getByLabel('Username', { exact: true }).fill(credentials.username);
  try {
    await page.getByLabel('Password', { exact: true }).fill(credentials.password);
    if ((await submitSignIn(page)).status() !== 200) throw new Error('Sign-in failed.');
    await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
  } catch {
    await page.locator('input[type="password"]').fill('').catch(() => {});
    throw new Error('Synthetic sign-in failed; protected browser detail withheld.');
  }
}

async function headers(context: BrowserContext, baseURL: string) {
  const response = await context.request.get('/api/v1/auth/csrf');
  expect(response.status()).toBe(200);
  return { Origin: baseURL, 'X-CSRF-Token': (await response.json() as { csrf_token: string }).csrf_token };
}

async function logout(context: BrowserContext, baseURL: string) {
  if ((await context.request.get('/api/v1/auth/session')).status() !== 200) return;
  expect((await context.request.post('/api/v1/auth/logout', { headers: await headers(context, baseURL), data: {} })).status()).toBe(200);
}

async function preferences(page: Page): Promise<Preferences> {
  const response = await page.request.get('/api/v1/me/preferences'); expect(response.status()).toBe(200);
  return response.json() as Promise<Preferences>;
}

async function restoreAppearance(page: Page, mode: ThemeMode, baseURL: string) {
  const current = await preferences(page);
  expect((await page.request.patch('/api/v1/me/preferences', {
    headers: await headers(page.context(), baseURL), data: { expected_revision: current.revision, theme_mode: mode },
  })).status()).toBe(200);
}

async function selectAppearance(page: Page, mode: ThemeMode) {
  const dialog = await openPreferences(page);
  const saved = page.waitForResponse(response => response.url().endsWith('/api/v1/me/preferences') && response.request().method() === 'PATCH');
  await dialog.getByLabel('Appearance', { exact: true }).selectOption(mode);
  expect((await saved).status()).toBe(200);
  await expect(dialog.getByLabel('Appearance', { exact: true })).toBeEnabled();
  await expect(dialog.getByLabel('Appearance', { exact: true })).toHaveValue(mode);
  await page.keyboard.press('Escape');
}

async function saveDefault(page: Page, mode: Settings['default_theme_mode']) {
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Settings', exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel('Appearance', { exact: true })).toHaveCount(0);
  await dialog.getByRole('combobox', { name: 'Application default appearance', exact: true }).selectOption(mode);
  const saved = page.waitForResponse(response => response.url().endsWith('/api/v1/admin/settings') && response.request().method() === 'PATCH');
  await dialog.getByRole('button', { name: 'Save application settings', exact: true }).click();
  expect((await saved).status()).toBe(200);
  await expect(dialog.getByRole('status')).toContainText('Application settings saved.');
  await page.keyboard.press('Escape');
}

for (const role of ['administrator', 'inspector'] as const) test(`${role} opens personal Preferences from the user menu with keyboard focus and no shared settings requests`, async ({ page, baseURL }) => {
  const administrativeRequests: string[] = [];
  page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/v1/admin/')) administrativeRequests.push(request.method() + ' ' + new URL(request.url()).pathname); });
  await signIn(page, account(role));
  const original = await preferences(page);
  try {
    await expect(page.getByRole('button', { name: 'Settings', exact: true })).toHaveCount(role === 'administrator' ? 1 : 0);
    await expect(page.getByRole('button', { name: 'Preferences', exact: true })).not.toBeVisible();
    const summary = page.locator('.account-menu > summary');
    await summary.focus(); await page.keyboard.press('Enter');
    const trigger = page.getByRole('button', { name: 'Preferences', exact: true });
    await page.keyboard.press('Tab'); await expect(trigger).toBeFocused();
    await page.keyboard.press('Enter');
    const dialog = page.getByRole('dialog', { name: 'Preferences', exact: true });
    await expect(dialog).toBeVisible();
    await expect(page.locator('.account-menu')).not.toHaveAttribute('open');
    await expect(dialog.getByRole('combobox', { name: 'Application default appearance', exact: true })).toHaveCount(0);
    await expect(dialog.getByRole('button', { name: 'Save application settings', exact: true })).toHaveCount(0);
    const appearance = dialog.getByLabel('Appearance', { exact: true });
    await appearance.focus(); await page.keyboard.press('Tab');
    expect(await page.evaluate(() => Boolean(document.activeElement?.closest('dialog[open]')))).toBe(true);
    await page.keyboard.press('Escape'); await expect(dialog).toHaveCount(0); await expect(summary).toBeFocused();
    for (const mode of ['light', 'dark'] as const) {
      await selectAppearance(page, mode);
      await page.reload(); await expect(page.locator('html')).toHaveAttribute('data-theme', mode);
      for (const viewport of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
        await page.setViewportSize(viewport);
        const current = await openPreferences(page); await expect(current.getByLabel('Appearance', { exact: true })).toHaveValue(mode);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        mkdirSync(screenshots, { recursive: true });
        await page.screenshot({ path: resolve(screenshots, `${role}-${mode}-${viewport.width}-personal-preferences.png`), animations: 'disabled' });
        await page.keyboard.press('Escape');
      }
    }
    await selectAppearance(page, 'system');
    for (const colorScheme of ['light', 'dark'] as const) {
      await page.emulateMedia({ colorScheme }); await expect(page.locator('html')).toHaveAttribute('data-theme', colorScheme);
    }
    expect(administrativeRequests).toEqual([]);
    if (role === 'administrator') {
      await page.getByRole('button', { name: 'Settings', exact: true }).click();
      const settings = page.getByRole('dialog', { name: 'Settings', exact: true });
      await expect(settings).toBeVisible();
      await expect(settings.getByLabel('Appearance', { exact: true })).toHaveCount(0);
      await expect(settings.getByRole('combobox', { name: 'Application default appearance', exact: true })).toBeEnabled();
      await expect(settings.getByRole('button', { name: 'Save application settings', exact: true })).toBeVisible();
      await page.screenshot({ path: resolve(screenshots, 'administrator-shared-settings-separated.png'), animations: 'disabled' });
      await page.keyboard.press('Escape');
    }
  } finally { await restoreAppearance(page, original.theme_mode, baseURL!); }
});

test('Preferences reports real revision conflicts and retries without losing the account scope', async ({ page, baseURL }) => {
  await signIn(page, account('inspector')); const original = await preferences(page);
  try {
    const dialog = await openPreferences(page);
    await restoreAppearance(page, 'light', baseURL!);
    const rejected = page.waitForResponse(response => response.url().endsWith('/api/v1/me/preferences') && response.request().method() === 'PATCH');
    await dialog.getByLabel('Appearance', { exact: true }).selectOption('dark');
    expect((await rejected).status()).toBe(409);
    await expect(dialog.getByRole('alert')).toContainText('Preferences changed in another window');
    await expect(dialog.getByLabel('Appearance', { exact: true })).toHaveValue(original.theme_mode);
    const retried = page.waitForResponse(response => response.url().endsWith('/api/v1/me/preferences') && response.request().method() === 'PATCH');
    await dialog.getByRole('button', { name: 'Retry', exact: true }).click();
    expect((await retried).status()).toBe(200);
    await expect(dialog.getByRole('alert')).toHaveCount(0);
    await expect(dialog.getByLabel('Appearance', { exact: true })).toHaveValue('dark');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.reload(); await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  } finally { await restoreAppearance(page, original.theme_mode, baseURL!); }
});

test('shared default controls new accounts and existing signed-out pages while explicit user themes remain personal', async ({ page, context, browser, baseURL }) => {
  test.setTimeout(120000);
  // Keep a real signed-out page mounted before the other page signs in; it
  // receives public-default broadcasts without obtaining personal preferences.
  const signedOut = await context.newPage(); await signedOut.goto('/');
  await expect(signedOut.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await signIn(page, account('administrator'));
  const originalSettings = await (await page.request.get('/api/v1/admin/settings')).json() as Settings;
  const originalAppearance = await preferences(page);
  const personalContext = await browser.newContext({ baseURL, ignoreHTTPSErrors: true });
  await prepare(personalContext, baseURL!); const personal = await personalContext.newPage();
  let created: { user_id: string; auth_version: number } | null = null;
  const fresh = { username: `synthetic-preferences-${randomBytes(8).toString('hex')}`, password: randomBytes(32).toString('base64url') };
  try {
    await selectAppearance(page, 'dark'); await saveDefault(page, 'light');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect(signedOut.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
    await expect(signedOut.locator('html')).toHaveAttribute('data-theme', 'light');
    const response = await page.request.post('/api/v1/admin/users', { headers: await headers(context, baseURL!), data: { ...fresh, display_name: 'Synthetic preferences verification', role: 'inspector', must_change_password: false } });
    expect(response.status()).toBe(201); created = await response.json() as { user_id: string; auth_version: number };
    await signIn(personal, fresh);
    expect((await preferences(personal)).theme_mode).toBe('default');
    await expect(personal.locator('html')).toHaveAttribute('data-theme', 'light');
    await expect(personal.getByRole('button', { name: 'Settings', exact: true })).toHaveCount(0);
    await selectAppearance(personal, 'light');
    await saveDefault(page, 'dark'); await personal.reload();
    await expect(personal.locator('html')).toHaveAttribute('data-theme', 'light');
    await expect(signedOut.locator('html')).toHaveAttribute('data-theme', 'dark');
    await selectAppearance(personal, 'default'); await expect(personal.locator('html')).toHaveAttribute('data-theme', 'dark');
    await saveDefault(page, 'light'); await personal.reload();
    await expect(personal.locator('html')).toHaveAttribute('data-theme', 'light');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect(signedOut.locator('html')).toHaveAttribute('data-theme', 'light');
    await page.locator('.account-menu > summary').click();
    await page.getByRole('button', { name: 'Sign out all windows', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await expect(personal.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
    await signIn(page, account('administrator'));
  } finally {
    if ((await page.request.get('/api/v1/auth/session')).status() !== 200) await signIn(page, account('administrator'));
    if (created) expect((await page.request.patch(`/api/v1/admin/users/${created.user_id}`, { headers: await headers(context, baseURL!), data: { expected_auth_version: created.auth_version, enabled: false } })).status()).toBe(200);
    const current = await (await page.request.get('/api/v1/admin/settings')).json() as Settings;
    expect((await page.request.patch('/api/v1/admin/settings', { headers: await headers(context, baseURL!), data: { branding: originalSettings.branding, default_theme_mode: originalSettings.default_theme_mode, additional_security_measures: originalSettings.additional_security_measures, expected_revision: current.revision } })).status()).toBe(200);
    await restoreAppearance(page, originalAppearance.theme_mode, baseURL!);
    expect(browserErrors.get(personalContext)).toEqual([]);
    await logout(personalContext, baseURL!); await personalContext.close(); await signedOut.close();
  }
});
