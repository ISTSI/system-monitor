import { expect, test, type BrowserContext } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { serveBuiltAssets, submitSignIn } from './ui';

test.skip(!['https://localhost:8449', 'https://localhost:8450'].includes(process.env.INSPECTOR_E2E_URL ?? ''), 'Requires an isolated synthetic fixture on 8449 or 8450.');
const screenshots = resolve('../verification/topology-login/screenshots');
const sessionCookie = '__Host-si-session';
const csrfCookie = '__Host-si-csrf';

async function prepare(context: BrowserContext, baseURL: string) {
  await context.grantPermissions(['local-network-access'], { origin: baseURL });
  await context.route('**/*', route => new URL(route.request().url()).origin === baseURL ? route.fallback() : route.abort());
  await serveBuiltAssets(context, baseURL);
}

test('remember me keeps secure cookies across a fresh browser context and logout revokes both pages', async ({ browser, context, page, baseURL }) => {
  await prepare(context, baseURL!);
  await page.goto('/');
  const remember = page.getByRole('checkbox', { name: /Remember me|Zapamiętaj mnie/ });
  await expect(remember).not.toBeChecked();
  await expect(page.locator('#remember-help')).toBeVisible();
  mkdirSync(screenshots, { recursive: true });
  for (const viewport of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(viewport);
    for (const theme of ['light', 'dark']) {
      await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
      await page.screenshot({ path: resolve(screenshots, `remember-login-${theme}-${viewport.width}.png`), animations: 'disabled' });
    }
  }
  const file = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!file) throw new Error('Protected synthetic account fixture is required.');
  const account = (JSON.parse(readFileSync(resolve(file), 'utf8')) as { inspector: { username: string; password: string } }).inspector;
  try {
    await page.locator('input[name="username"]').fill(account.username);
    await page.locator('input[name="password"]').fill(account.password);
    await remember.check();
    expect((await submitSignIn(page)).status()).toBe(200);
  } catch {
    await page.locator('input[name="password"]').fill('').catch(() => {});
    throw new Error('Synthetic sign-in failed; sensitive browser detail withheld.');
  }
  await expect(page.locator('.login-card')).toHaveCount(0);
  const cookies = await context.cookies();
  const expectedEnd = Date.now() / 1000 + 30 * 24 * 60 * 60;
  for (const name of [sessionCookie, csrfCookie]) {
    const cookie = cookies.find(value => value.name === name)!;
    expect(cookie.secure && cookie.httpOnly && cookie.sameSite === 'Strict').toBe(true);
    expect(Math.abs(cookie.expires - expectedEnd)).toBeLessThan(20);
  }
  // Carry only persisted cookies to a fresh context. No local/session storage,
  // page workspace or in-memory CSRF state survives this browser restart model.
  const restarted = await browser.newContext({ baseURL, ignoreHTTPSErrors: true, storageState: { cookies, origins: [] } });
  try {
    await prepare(restarted, baseURL!);
    const newPage = await restarted.newPage();
    await newPage.goto('/');
    await expect(newPage.locator('.account-menu')).toBeVisible();
    expect((await restarted.request.get('/api/v1/auth/session')).status()).toBe(200);
    expect((await restarted.request.post('/api/v1/auth/logout', { data: {}, headers: { Origin: baseURL! } })).status()).toBe(403);
    const csrf = await (await restarted.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
    expect((await restarted.request.post('/api/v1/auth/logout', { data: {}, headers: { Origin: baseURL!, 'X-CSRF-Token': csrf.csrf_token } })).status()).toBe(200);
    expect((await context.request.get('/api/v1/auth/session')).status()).toBe(401);
    await page.reload();
    await expect(page.getByRole('checkbox', { name: /Remember me|Zapamiętaj mnie/ })).not.toBeChecked();
  } finally {
    await restarted.close();
    if ((await context.request.get('/api/v1/auth/session')).status() === 200) {
      const csrf = await (await context.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
      await context.request.post('/api/v1/auth/logout', { data: {}, headers: { Origin: baseURL!, 'X-CSRF-Token': csrf.csrf_token } });
    }
  }
});
