import { test, expect, type BrowserContext, type Locator, type Page } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Config, Connection, Topology } from '../src/topology';

type Role = 'administrator' | 'inspector';
type Fixture = { synthetic: boolean; username: string; endpoints: Record<'target' | 'jump', { host: string; port: number; fingerprint: string }> };
const fixture = JSON.parse(readFileSync(resolve('../.state/stage4-ssh/public-fixture.json'), 'utf8')) as Fixture;
if (!fixture.synthetic || fixture.username !== 'synthetic-log-reader' || fixture.endpoints.target.host !== 'ssh-target' || fixture.endpoints.jump.host !== 'ssh-jump' || Object.values(fixture.endpoints).some(endpoint => endpoint.port !== 8022)) throw new Error('Only the isolated synthetic SSH fixture is authorized.');
const screenshots = resolve(`../verification/${process.env.INSPECTOR_E2E_REPORT_STAGE ?? 'stage-4'}/screenshots`);
const browserErrors = new WeakMap<BrowserContext, string[]>();
const externalRequests = new WeakMap<BrowserContext, string[]>();

test.beforeEach(async ({ context, page, baseURL }) => {
  const errors: string[] = [];
  const external: string[] = [];
  browserErrors.set(context, errors);
  externalRequests.set(context, external);
  page.on('pageerror', error => errors.push(error.message));
  context.on('page', extra => extra.on('pageerror', error => errors.push(error.message)));
  const origin = new URL(baseURL!).origin;
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin === origin) return route.continue();
    external.push(url.origin);
    return route.abort();
  });
});

test.afterEach(async ({ context, page, baseURL }) => {
  for (const current of context.pages()) await current.evaluate(() => {
    document.querySelectorAll<HTMLInputElement>('input[type="password"]').forEach(input => { input.value = ''; });
  }).catch(() => {});
  try {
    expect(browserErrors.get(context)).toEqual([]);
    expect(externalRequests.get(context)).toEqual([]);
  } finally {
    if ((await page.request.get('/api/v1/auth/session')).status() === 200) {
      const { csrf_token } = await (await page.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
      const logout = await page.request.post('/api/v1/auth/logout', {
        headers: { Origin: new URL(baseURL!).origin, 'X-CSRF-Token': csrf_token }, data: {},
      });
      expect(logout.status()).toBe(200);
    }
  }
});

async function login(page: Page, role: Role) {
  const filename = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!filename) throw new Error('The protected synthetic-account fixture is required.');
  const accounts = JSON.parse(readFileSync(resolve(filename), 'utf8')) as Record<Role, { username: string; password: string }>;
  await page.goto('/');
  await page.getByLabel('Username', { exact: true }).fill(accounts[role].username);
  try {
    await page.getByLabel('Password', { exact: true }).fill(accounts[role].password);
    const response = page.waitForResponse(value => value.url().endsWith('/api/v1/auth/login') && value.request().method() === 'POST');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    if ((await response).status() !== 200) throw new Error('Synthetic sign-in failed.');
    await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
  } catch {
    await page.evaluate(() => document.querySelectorAll<HTMLInputElement>('input[type="password"]').forEach(input => { input.value = ''; })).catch(() => {});
    throw new Error('Synthetic sign-in failed; protected details withheld.');
  }
}

async function headers(page: Page) {
  const response = await page.request.get('/api/v1/auth/csrf');
  expect(response.status()).toBe(200);
  const { csrf_token } = await response.json() as { csrf_token: string };
  return { Origin: new URL(page.url()).origin, 'X-CSRF-Token': csrf_token };
}

async function createSystem(page: Page, viaJump = false): Promise<string> {
  const requestHeaders = await headers(page);
  const name = `[Synthetic SSH] ${viaJump ? 'Jump' : 'Direct'} ${Date.now()}`;
  const response = await page.request.post('/api/v1/projects', { headers: requestHeaders, data: { name, description: 'Local password/SFTP connection verification only.' } });
  expect(response.status()).toBe(201);
  const { project_id: id } = await response.json() as { project_id: string };
  const initial = await page.request.get(`/api/v1/projects/${id}/topology`);
  expect(initial.status()).toBe(200);
  const current = await initial.json() as Topology;
  const profile = (kind: 'target' | 'jump'): Connection => ({
    id: kind === 'target' ? 'ssh-shared-id' : 'ssh-jump-id', name: `Synthetic ${kind}`,
    host: fixture.endpoints[kind].host, port: fixture.endpoints[kind].port, username: fixture.username,
    credential_ref: `synthetic-${kind}-password`, jump_connection_id: kind === 'target' && viaJump ? 'ssh-jump-id' : null,
    allowed_log_roots: kind === 'target' ? ['/var/log/inspector-demo'] : [],
  });
  const config: Config = {
    ...current.config,
    subsystems: [{ id: 'synthetic-subsystem', name: 'Synthetic logs', description: '', tags: [] }],
    servers: [{ id: 'synthetic-server', name: 'Synthetic SSH server', description: '', tags: [], subsystem_id: 'synthetic-subsystem', connection_id: 'ssh-shared-id' }],
    processes: [], flows: [], connections: viaJump ? [profile('jump'), profile('target')] : [profile('target')],
    views: [{ id: 'synthetic-view', name: 'Synthetic SSH setup', flow_ids: [], nodes: [
      { element_id: 'synthetic-subsystem', x: 0, y: 0, width: 540, height: 340, collapsed: false },
      { element_id: 'synthetic-server', x: 20, y: 65, width: 490, height: 240, collapsed: false },
    ] }],
  };
  const saved = await page.request.put(`/api/v1/projects/${id}/topology`, { headers: requestHeaders, data: { expected_revision: current.revision, config } });
  expect(saved.status()).toBe(200);
  return id;
}

async function openSystem(page: Page, id: string) {
  await page.goto(`/systems/${id}/topology`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
}

async function openAccess(page: Page): Promise<Locator> {
  await page.getByRole('button', { name: 'Select server Synthetic SSH server', exact: true }).click();
  await page.getByRole('button', { name: 'Password & connection test', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'SSH password & connection test', exact: true });
  await expect(dialog.getByTestId('ssh-password-status')).toBeVisible();
  return dialog;
}

async function openManagerAccess(page: Page): Promise<Locator> {
  await page.getByRole('button', { name: 'Connections', exact: true }).click();
  await page.getByRole('button', { name: 'Password and test Synthetic target', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'SSH password & connection test', exact: true });
  await expect(dialog.getByTestId('ssh-password-status')).toBeVisible();
  return dialog;
}

async function savePassword(dialog: Locator, role: 'target' | 'jump', incorrect = false) {
  const password = incorrect ? 'synthetic-deliberately-wrong-password' : readFileSync(resolve(`../.secrets/stage4-ssh/${role}-password`), 'utf8').trim();
  const input = dialog.locator('input[type="password"]');
  try {
    await input.fill(password);
    await dialog.getByRole('button', { name: 'Save SSH password', exact: true }).click();
  } catch {
    throw new Error('The write-only SSH password action failed; protected details withheld.');
  } finally {
    await input.fill('').catch(() => {});
  }
  await expect(dialog.getByRole('status')).toContainText('SSH password saved.');
  await expect(input).toHaveValue('');
  await expect(dialog.getByTestId('ssh-password-status')).toContainText('A password is stored');
}

async function approveKey(dialog: Locator, role: 'target' | 'jump') {
  await dialog.getByRole('button', { name: 'Inspect host key', exact: true }).click();
  const preview = dialog.locator('.host-key-preview');
  await expect(preview.locator('.ssh-fingerprint')).toHaveText(fixture.endpoints[role].fingerprint);
  const approve = preview.getByRole('button', { name: 'Approve host key', exact: true });
  await expect(approve).toBeDisabled();
  // Approve only after comparing the observation with the independently
  // generated public fixture metadata, never with a value echoed by the API.
  await preview.getByRole('checkbox', { name: /I verified this fingerprint against an independent trusted source/ }).check();
  await approve.click();
  await expect(dialog.getByRole('status')).toContainText('Host key approved');
}

async function connectionPasses(dialog: Locator) {
  await dialog.getByRole('button', { name: 'Test connection', exact: true }).click();
  await expect(dialog.getByRole('status')).toContainText('Connection test passed: SSH authentication and SFTP are available.');
}

test('password setup tests real SFTP, clears write-only secrets, persists safely and stays scoped between pages', async ({ page, context }) => {
  test.setTimeout(120000);
  await login(page, 'administrator');
  const id = await createSystem(page);
  await openSystem(page, id);
  let dialog = await openAccess(page);
  await expect(dialog).toContainText('Stored encrypted in the server database.');
  await expect(dialog.getByRole('button', { name: 'Test connection', exact: true })).toBeDisabled();
  await savePassword(dialog, 'target');
  await expect(dialog.getByRole('button', { name: 'Test connection', exact: true })).toBeDisabled();
  await approveKey(dialog, 'target');
  await connectionPasses(dialog);
  await savePassword(dialog, 'target', true);
  await dialog.getByRole('button', { name: 'Test connection', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('SSH password authentication failed.');
  await expect(dialog.locator('input[type="password"]')).toHaveValue('');
  await savePassword(dialog, 'target');
  await connectionPasses(dialog);
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await page.reload();
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  dialog = await openManagerAccess(page);
  await expect(dialog.getByTestId('ssh-password-status')).toContainText('A password is stored');
  await expect(dialog.locator('input[type="password"]')).toHaveValue('');
  await expect(dialog.getByRole('button', { name: 'Test connection', exact: true })).toBeEnabled();
  const accessResponse = await page.request.get(`/api/v1/projects/${id}/connections/ssh-shared-id/access`);
  expect(accessResponse.status()).toBe(200);
  const accessText = await accessResponse.text();
  const exportResponse = await page.request.get(`/api/v1/projects/${id}/config/export?format=json`);
  expect(exportResponse.status()).toBe(200);
  const exportText = await exportResponse.text();
  const secret = readFileSync(resolve('../.secrets/stage4-ssh/target-password'), 'utf8').trim();
  expect(accessText.includes(secret) || exportText.includes(secret)).toBe(false);
  expect(accessText.includes('ciphertext') || exportText.includes('ciphertext')).toBe(false);
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  for (const viewport of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(viewport);
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('Appearance', { exact: true }).selectOption(theme);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      dialog = await openAccess(page);
      await expect(dialog.locator('input[type="password"]')).toHaveValue('');
      mkdirSync(screenshots, { recursive: true });
      await page.screenshot({ path: resolve(screenshots, `ssh-setup-${theme}-${viewport.width}.png`), animations: 'disabled' });
      await dialog.getByRole('button', { name: 'Close', exact: true }).click();
    }
  }
  const otherId = await createSystem(page);
  const otherPage = await context.newPage();
  await openSystem(otherPage, otherId);
  const otherDialog = await openAccess(otherPage);
  await expect(otherDialog.getByTestId('ssh-password-status')).toContainText('No password is stored');
  await expect(otherDialog.getByRole('button', { name: 'Test connection', exact: true })).toBeDisabled();
  dialog = await openAccess(page);
  await expect(dialog.getByTestId('ssh-password-status')).toContainText('A password is stored');
  await dialog.getByRole('button', { name: 'Revoke host-key approval', exact: true }).click();
  await expect(dialog.getByRole('status')).toContainText('Host-key approval revoked');
  await expect(dialog.getByRole('button', { name: 'Test connection', exact: true })).toBeDisabled();
  const blocked = await page.request.post(`/api/v1/projects/${id}/connections/ssh-shared-id/test`, { headers: await headers(page), data: { expected_config_revision: 2 } });
  expect(blocked.status()).toBe(409);
  expect((await blocked.json() as { error: { code: string } }).error.code).toBe('HOST_KEY_REQUIRED');
});

test('a saved jump route requires its own password and independently approved key before target inspection', async ({ page }) => {
  await login(page, 'administrator');
  const id = await createSystem(page, true);
  await openSystem(page, id);
  let dialog = await openAccess(page);
  await savePassword(dialog, 'target');
  await dialog.getByRole('button', { name: 'Inspect host key', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('host key before testing');
  await dialog.getByRole('button', { name: 'Configure jump host', exact: true }).click();
  dialog = page.getByRole('dialog', { name: 'SSH password & connection test', exact: true });
  await expect(dialog.locator('.connection-target')).toContainText('Synthetic jump');
  await savePassword(dialog, 'jump');
  await approveKey(dialog, 'jump');
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  dialog = await openAccess(page);
  await approveKey(dialog, 'target');
  await connectionPasses(dialog);
});

test('Inspector cannot view or mutate SSH setup through either UI or forged requests', async ({ page }) => {
  await login(page, 'administrator');
  const id = await createSystem(page);
  const requestHeaders = await headers(page);
  expect((await page.request.post('/api/v1/auth/logout', { headers: requestHeaders, data: {} })).status()).toBe(200);
  await login(page, 'inspector');
  await openSystem(page, id);
  await page.getByRole('button', { name: 'Select server Synthetic SSH server', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Password & connection test', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Connections', exact: true })).toHaveCount(0);
  const base = `/api/v1/projects/${id}/connections/ssh-shared-id`;
  expect((await page.request.get(`${base}/access`)).status()).toBe(403);
  const forgedHeaders = await headers(page);
  const revision = { expected_config_revision: 2 };
  const password = await page.request.put(`${base}/password`, { headers: forgedHeaders, data: { ...revision, expected_credential_revision: 0, password: 'synthetic-forged-password' } });
  expect(password.status()).toBe(403);
  const forbidden = [
    { suffix: 'test', data: revision },
    { suffix: 'host-key/inspect', data: revision },
    { suffix: 'host-key/approve', data: { ...revision, expected_trust_revision: 0, inspection_token: 'x'.repeat(43), verified: true } },
    { suffix: 'revoke', data: { ...revision, expected_trust_revision: 0 } },
  ];
  for (const { suffix, data } of forbidden) {
    const response = await page.request.post(`${base}/${suffix}`, { headers: forgedHeaders, data });
    expect(response.status()).toBe(403);
  }
});
