import { test, expect, type BrowserContext, type Locator, type Page } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { serveBuiltAssets, setAppearance, submitSignIn, systemAction } from './ui';
import type { Config, Connection, Topology } from '../src/topology';
import type { components } from '../src/api/schema';

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
    if (url.origin === origin) return route.fallback();
    external.push(url.origin);
    return route.abort();
  });
  if (process.env.INSPECTOR_E2E_LOCAL_ASSETS === '1') await serveBuiltAssets(context, baseURL!);
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
    const response = await submitSignIn(page);
    if (response.status() !== 200) throw new Error('Synthetic sign-in failed.');
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

async function createSystem(page: Page, viaJump = false, withLogs = false): Promise<string> {
  const requestHeaders = await headers(page);
  const name = `[Synthetic SSH] ${viaJump ? 'Jump' : 'Direct'} ${Date.now()}`;
  const response = await page.request.post('/api/v1/projects', { headers: requestHeaders, data: { name, description: 'Local password/SFTP connection verification only.' } });
  expect(response.status()).toBe(201);
  const { project_id: id } = await response.json() as { project_id: string };
  const initial = await page.request.get(`/api/v1/projects/${id}/topology`);
  expect(initial.status()).toBe(200);
  const current = await initial.json() as Topology;
  const example = JSON.parse(readFileSync(resolve('../examples/project.example.json'), 'utf8')) as Config;
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
    processes: withLogs ? example.processes.map(process => ({ ...process, server_id: 'synthetic-server' })) : [],
    parsers: withLogs ? example.parsers : [], flows: [], connections: viaJump ? [profile('jump'), profile('target')] : [profile('target')],
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
  await systemAction(page, 'List connections');
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

async function sshCheck(button: Locator, suffix: string) {
  async function submit() {
    const response = button.page().waitForResponse(value => new URL(value.url()).pathname.endsWith(suffix) && value.request().method() === 'POST');
    await button.click();
    return response;
  }
  let response = await submit();
  if (response.status() === 429) {
    test.info().annotations.push({ type: 'rate-limit', description: 'The real SSH check limit returned 429; waited 60 seconds for one bounded retry.' });
    test.info().setTimeout(test.info().timeout + 65000);
    console.log('SSH check returned 429; preserving the production limit and waiting 60 seconds for one retry.');
    await button.page().waitForTimeout(60000);
    response = await submit();
  }
  return response;
}

async function approveKey(dialog: Locator, role: 'target' | 'jump') {
  expect((await sshCheck(dialog.getByRole('button', { name: 'Inspect host key', exact: true }), '/host-key/inspect')).status()).toBe(200);
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
  expect((await sshCheck(dialog.getByRole('button', { name: 'Test connection', exact: true }), '/test')).status()).toBe(200);
  await expect(dialog.getByRole('status')).toContainText('Connection test passed: SSH authentication and SFTP are available.');
}

async function setSecurityMeasures(page: Page, enabled: boolean) {
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  const settings = page.getByRole('dialog', { name: 'Settings', exact: true });
  const checkbox = settings.getByRole('checkbox', { name: 'Additional security measures', exact: true });
  await expect(checkbox).toBeEnabled();
  await checkbox.setChecked(enabled);
  const saved = page.waitForResponse(response => response.url().endsWith('/admin/settings') && response.request().method() === 'PATCH');
  await settings.getByRole('button', { name: 'Save application settings', exact: true }).click();
  expect((await saved).status()).toBe(200);
  await expect(settings.getByText('Application settings saved.', { exact: true })).toBeVisible();
  await settings.getByRole('button', { name: 'Close dialog', exact: true }).click();
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
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
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
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  const settings = page.getByRole('dialog', { name: 'Settings', exact: true });
  await expect(settings.getByRole('checkbox', { name: 'Additional security measures', exact: true })).toHaveCount(0);
  await settings.getByRole('button', { name: 'Close dialog', exact: true }).click();
  await openSystem(page, id);
  await page.getByRole('button', { name: 'Select server Synthetic SSH server', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Password & connection test', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Connections', exact: true })).toHaveCount(0);
  const base = `/api/v1/projects/${id}/connections/ssh-shared-id`;
  expect((await page.request.get(`${base}/access`)).status()).toBe(403);
  expect((await page.request.get(`${base}/source-access`)).status()).toBe(403);
  const forgedHeaders = await headers(page);
  expect((await page.request.patch('/api/v1/admin/settings', { headers: forgedHeaders, data: {
    expected_revision: 1, branding: 'FORGED', default_theme_mode: 'dark', additional_security_measures: false,
  } })).status()).toBe(403);
  const revision = { expected_config_revision: 2 };
  const password = await page.request.put(`${base}/password`, { headers: forgedHeaders, data: { ...revision, expected_credential_revision: 0, password: 'synthetic-forged-password' } });
  expect(password.status()).toBe(403);
  const forbidden = [
    { suffix: 'test', data: revision },
    { suffix: 'host-key/inspect', data: revision },
    { suffix: 'host-key/approve', data: { ...revision, expected_trust_revision: 0, inspection_token: 'x'.repeat(43), verified: true } },
    { suffix: 'revoke', data: { ...revision, expected_trust_revision: 0 } },
    { suffix: 'source-access/test', data: revision },
    { suffix: 'source-access/approve', data: { ...revision, expected_approval_revision: 0, verified: true } },
    { suffix: 'source-access/revoke', data: { ...revision, expected_approval_revision: 0 } },
  ];
  for (const { suffix, data } of forbidden) {
    const response = await page.request.post(`${base}/${suffix}`, { headers: forgedHeaders, data });
    expect(response.status()).toBe(403);
  }
});

test('Additional security measures persists and controls path and parser confirmations while host keys remain explicit', async ({ page }) => {
  test.setTimeout(180000);
  await login(page, 'administrator');
  const initialResponse = await page.request.get('/api/v1/admin/settings');
  expect(initialResponse.status()).toBe(200);
  const initial = await initialResponse.json() as components['schemas']['SettingsResponse'];
  const id = await createSystem(page, false, true);
  await openSystem(page, id);
  try {
    await setSecurityMeasures(page, false);
    await page.reload();
    await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await page.getByRole('button', { name: 'Settings', exact: true }).click();
      const settings = page.getByRole('dialog', { name: 'Settings', exact: true });
      await expect(settings.getByRole('checkbox', { name: 'Additional security measures', exact: true })).not.toBeChecked();
      await expect(settings).toContainText('SSH host keys always require explicit verification.');
      mkdirSync(screenshots, { recursive: true });
      await page.screenshot({ path: resolve(screenshots, `additional-security-settings-${theme}-1280x720.png`), animations: 'disabled' });
      await settings.getByRole('button', { name: 'Close dialog', exact: true }).click();
    }
    let dialog = await openAccess(page);
    await expect(dialog.getByRole('checkbox', { name: /I verified this target and these configured log roots/ })).toHaveCount(0);
    await expect(dialog.getByRole('button', { name: 'Approve target and log roots', exact: true })).toHaveCount(0);
    await expect(dialog.getByRole('button', { name: 'Test configured log paths', exact: true })).toBeDisabled();
    await savePassword(dialog, 'target');
    await expect(dialog.getByRole('button', { name: 'Test configured log paths', exact: true })).toBeDisabled();
    await approveKey(dialog, 'target');

    async function pathsPassWithoutConfirmation(current: Locator) {
      await expect(current.getByTestId('source-approval-status')).toHaveText('Ready for remote collection. Manual source confirmation is disabled.');
      await expect(current.getByRole('checkbox', { name: /I verified this target and these configured log roots/ })).toHaveCount(0);
      await expect(current.getByRole('button', { name: 'Revoke source approval', exact: true })).toHaveCount(0);
      const response = await sshCheck(current.getByRole('button', { name: 'Test configured log paths', exact: true }), '/source-access/test');
      expect(response.status()).toBe(200);
      const checked = await response.json() as components['schemas']['SourcePathTestResponse'];
      expect(checked.processes).toHaveLength(5);
      expect(checked.processes.every(process => process.accessible && process.candidate_count > 0)).toBe(true);
    }
    await pathsPassWithoutConfirmation(dialog);
    await dialog.getByRole('button', { name: 'Close', exact: true }).click();
    const topologyResponse = await page.request.get(`/api/v1/projects/${id}/topology`);
    expect(topologyResponse.status()).toBe(200);
    const topology = await topologyResponse.json() as Topology;
    const process = topology.config.processes[0];
    const replacementPath = topology.config.processes.find(item => item.log_source?.active_path !== process.log_source?.active_path)!.log_source!.active_path;
    await page.locator('.explorer').getByRole('button', { name: process.name, exact: true }).click();
    await page.getByRole('button', { name: 'Edit selected', exact: true }).click();
    const processEditor = page.getByRole('dialog', { name: 'Edit process', exact: true });
    await processEditor.getByLabel('Active log path', { exact: true }).fill(replacementPath);
    await processEditor.getByRole('button', { name: 'Save process', exact: true }).click();
    await expect(processEditor).toHaveCount(0);
    dialog = await openManagerAccess(page);
    await pathsPassWithoutConfirmation(dialog);
    await dialog.getByRole('button', { name: 'Close', exact: true }).click();

    async function changeParser(prefix: string) {
      const parser = topology.config.parsers![0];
      await systemAction(page, 'List Parsers');
      await page.getByRole('button', { name: `Edit parser ${parser.name}`, exact: true }).click();
      const editor = page.getByRole('dialog', { name: 'Edit parser', exact: true });
      await expect(editor).toBeVisible();
      await expect(page.locator('dialog[open]')).toHaveCount(1);
      await editor.getByRole('textbox', { name: 'Correlation markers (JSON)', exact: true }).fill(JSON.stringify([
        ...parser.correlation_markers, { key: 'security_test', prefix, terminators: ' ' },
      ]));
      await editor.getByRole('button', { name: 'Save parser', exact: true }).click();
      await expect(editor).toHaveCount(0);
    }
    await changeParser('automatic_test=');
    dialog = await openManagerAccess(page);
    await pathsPassWithoutConfirmation(dialog);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await dialog.getByRole('heading', { name: 'Configured target and log roots', exact: true }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: resolve(screenshots, `automatic-source-confirmation-${theme}-1280x720.png`), animations: 'disabled' });
    }
    await dialog.getByRole('button', { name: 'Close', exact: true }).click();

    await page.goto(`/systems/${id}/logs`);
    await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
    const transport = page.getByLabel('Collection transport', { exact: true });
    if (await transport.count()) await transport.selectOption('ssh');
    for (const process of await page.getByRole('group', { name: 'Configured processes' }).getByRole('checkbox').all()) await process.check();
    await page.getByLabel('From UTC (inclusive)', { exact: true }).fill('2026-10-16T12:00:00.000000Z');
    await page.getByLabel('To UTC (exclusive)', { exact: true }).fill('2026-10-16T12:00:02.000000Z');
    await page.getByRole('button', { name: 'Preview collection plan', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toContainText('Approved SSH/SFTP');
    await page.getByRole('button', { name: 'Collect sources', exact: true }).click();
    await expect(page.getByTestId('collection-state')).toHaveText('completed', { timeout: 30000 });
    await openSystem(page, id);
    dialog = await openManagerAccess(page);
    await dialog.getByRole('button', { name: 'Revoke host-key approval', exact: true }).click();
    await expect(dialog.getByTestId('source-approval-status')).toHaveText('Remote collection requires stored credentials and explicitly verified SSH host keys.');
    await expect(dialog.getByRole('button', { name: 'Test configured log paths', exact: true })).toBeDisabled();
    await approveKey(dialog, 'target');
    await expect(dialog.getByTestId('source-approval-status')).toHaveText('Ready for remote collection. Manual source confirmation is disabled.');
    await dialog.getByRole('button', { name: 'Close', exact: true }).click();

    await setSecurityMeasures(page, true);
    dialog = await openManagerAccess(page);
    const approve = dialog.getByRole('button', { name: 'Approve target and log roots', exact: true });
    await expect(dialog.getByTestId('source-approval-status')).toContainText('Remote collection is blocked');
    await expect(approve).toBeDisabled();
    await expect(dialog.getByRole('button', { name: 'Test configured log paths', exact: true })).toBeDisabled();
    await dialog.getByRole('checkbox', { name: /I verified this target and these configured log roots/ }).check();
    await approve.click();
    await expect(dialog.getByTestId('source-approval-status')).toHaveText('Approved for remote collection.');
    await dialog.getByRole('button', { name: 'Close', exact: true }).click();
    await changeParser('manual_test=');
    dialog = await openManagerAccess(page);
    await expect(dialog.getByTestId('source-approval-status')).toContainText('Remote collection is blocked');
    await expect(dialog.getByRole('checkbox', { name: /I verified this target and these configured log roots/ })).not.toBeChecked();
    await expect(dialog.getByRole('button', { name: 'Approve target and log roots', exact: true })).toBeDisabled();
    await expect(dialog.getByRole('button', { name: 'Test configured log paths', exact: true })).toBeDisabled();
  } finally {
    const response = await page.request.get('/api/v1/admin/settings');
    expect(response.status()).toBe(200);
    const current = await response.json() as components['schemas']['SettingsResponse'];
    if (current.additional_security_measures !== initial.additional_security_measures) {
      const restored = await page.request.patch('/api/v1/admin/settings', { headers: await headers(page), data: {
        branding: current.branding, default_theme_mode: current.default_theme_mode,
        expected_revision: current.revision, additional_security_measures: initial.additional_security_measures,
      } });
      expect(restored.status()).toBe(200);
    }
  }
});

test('approved jump-host sources collect real history for Inspector with independent same-context pages', async ({ page, context }) => {
  test.setTimeout(180000);
  await login(page, 'administrator');
  const id = await createSystem(page, true, true);
  await openSystem(page, id);
  let dialog = await openAccess(page);
  await savePassword(dialog, 'target');
  await dialog.getByRole('button', { name: 'Configure jump host', exact: true }).click();
  dialog = page.getByRole('dialog', { name: 'SSH password & connection test', exact: true });
  await expect(dialog.locator('.connection-target')).toContainText('Synthetic jump');
  await savePassword(dialog, 'jump'); await approveKey(dialog, 'jump');
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  dialog = await openAccess(page);
  await approveKey(dialog, 'target');
  const sources = dialog.getByRole('region', { name: 'Configured source approval', exact: true });
  await expect(sources).toContainText('/var/log/inspector-demo');
  await expect(sources).toContainText('ingest-instance-a');
  await expect(sources.getByRole('button', { name: 'Test configured log paths', exact: true })).toBeDisabled();
  const approve = sources.getByRole('button', { name: 'Approve target and log roots', exact: true });
  await expect(approve).toBeDisabled();
  await sources.getByRole('checkbox', { name: /I verified this target and these configured log roots/ }).check();
  await approve.click();
  await expect(sources.getByTestId('source-approval-status')).toHaveText('Approved for remote collection.');
  const pathResponse = await sshCheck(sources.getByRole('button', { name: 'Test configured log paths', exact: true }), '/source-access/test');
  expect(pathResponse.status()).toBe(200);
  const checked = await pathResponse.json() as components['schemas']['SourcePathTestResponse'];
  expect(checked.processes).toHaveLength(5);
  expect(checked.processes.every(process => process.accessible && process.candidate_count > 0)).toBe(true);
  await expect(sources.getByRole('status')).toContainText('Accessible');
  mkdirSync(screenshots, { recursive: true });
  for (const viewport of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(viewport);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await expect(sources.getByTestId('source-approval-status')).toHaveText('Approved for remote collection.');
      await expect(sources.getByRole('status')).toContainText('Accessible');
      await sources.getByRole('heading', { name: 'Approve target and log roots', exact: true }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: resolve(screenshots, `approved-jump-source-access-${theme}-${viewport.width}x${viewport.height}.png`), animations: 'disabled' });
      await sources.getByRole('status').scrollIntoViewIfNeeded();
      await page.screenshot({ path: resolve(screenshots, `configured-source-path-checks-${theme}-${viewport.width}x${viewport.height}.png`), animations: 'disabled' });
    }
  }
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  const otherId = await createSystem(page, true, true);
  const other = await context.newPage();
  await openSystem(other, otherId);
  const otherDialog = await openAccess(other);
  await expect(otherDialog.getByTestId('source-approval-status')).toContainText('Remote collection is blocked');
  await otherDialog.getByRole('button', { name: 'Close', exact: true }).click();
  // A password replacement invalidates this system's source approval, while
  // the independently verified host key remains usable for explicit setup.
  dialog = await openAccess(page);
  await savePassword(dialog, 'target');
  await expect(dialog.getByTestId('source-approval-status')).toContainText('Remote collection is blocked');
  await dialog.getByRole('checkbox', { name: /I verified this target and these configured log roots/ }).check();
  await dialog.getByRole('button', { name: 'Approve target and log roots', exact: true }).click();
  await expect(dialog.getByTestId('source-approval-status')).toHaveText('Approved for remote collection.');
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  expect((await page.request.post('/api/v1/auth/logout', { headers: await headers(page), data: {} })).status()).toBe(200);
  await login(page, 'inspector');

  async function openLogs(current: Page, projectId: string) {
    await current.goto(`/systems/${projectId}/logs`);
    await expect(current.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
    const transport = current.getByLabel('Collection transport', { exact: true });
    if (await transport.count()) await transport.selectOption('ssh');
    for (const process of await current.getByRole('group', { name: 'Configured processes' }).getByRole('checkbox').all()) await process.check();
    await current.getByLabel('From UTC (inclusive)', { exact: true }).fill('2026-10-16T12:00:00.000000Z');
    await current.getByLabel('To UTC (exclusive)', { exact: true }).fill('2026-10-16T12:00:02.000000Z');
  }
  await openLogs(other, otherId);
  await other.getByRole('button', { name: 'Preview collection plan', exact: true }).click();
  await expect(other.getByRole('alert')).toBeVisible();
  await expect(other.getByRole('region', { name: 'Collection plan', exact: true })).toHaveCount(0);
  await other.getByRole('button', { name: 'Collect sources', exact: true }).click();
  await expect(other.getByRole('alert')).toBeVisible();
  await expect(other.getByTestId('collection-state')).toHaveCount(0);
  await openLogs(page, id);
  expect((await page.request.get(`/api/v1/projects/${id}/connections/ssh-shared-id/source-access`)).status()).toBe(403);
  async function collect(current: Page, preview = true) {
    const plan = current.getByRole('region', { name: 'Collection plan', exact: true });
    await expect(plan).toHaveCount(0);
    if (preview) {
      await current.getByRole('button', { name: 'Preview collection plan', exact: true }).click();
      await expect(plan).toContainText('Approved SSH/SFTP');
      await expect(plan).not.toContainText('SYNTHETIC LOCAL FIXTURES');
      await expect(plan).toContainText('zip'); await expect(plan).toContainText('tar.gz');
    }
    await current.getByRole('button', { name: 'Collect sources', exact: true }).click();
    await expect(current.getByTestId('collection-state')).toHaveText('completed', { timeout: 30000 });
    await expect(current.getByTestId('match-count')).toHaveText(/^[1-9]\d* matches$/);
    await expect(current.locator('.virtual-logs .log-event').first()).toBeVisible();
    if (!preview) await expect(plan).toHaveCount(0);
    await expect(current.getByRole('region', { name: 'Collection progress', exact: true })).toContainText('complete_for_scanned_candidates');
    return current.getByTestId('investigation-id').innerText();
  }
  const first = await collect(page);
  await openLogs(other, id);
  expect(await page.getByTestId('workspace-id').innerText()).not.toBe(await other.getByTestId('workspace-id').innerText());
  const second = await collect(other, false);
  expect(first).not.toBe(second);
  await page.getByLabel('Contains string', { exact: true }).fill('request_id=REQ-0042');
  const queryResponse = page.waitForResponse(response => response.url().endsWith('/query') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Apply filter', exact: true }).click();
  const queried = await queryResponse;
  expect(queried.status()).toBe(200);
  const results = await queried.json() as components['schemas']['HistoricalQueryResponse'];
  const cases = JSON.parse(readFileSync(resolve('../fixtures/expected/query-cases.json'), 'utf8')) as { id: string; expected_event_ids: string[] }[];
  const expectedIds = cases.find(item => item.id === 'literal-correlation-substring')!.expected_event_ids;
  const events = JSON.parse(readFileSync(resolve('../fixtures/expected/events.json'), 'utf8')) as { event_id: string; raw_line: string; timestamp_utc: string; process_id: string }[];
  const expected = expectedIds.map(id => events.find(event => event.event_id === id)!);
  expect(results.items.map(event => [event.process_id, event.timestamp_utc, event.raw_line])).toEqual(expected.map(event => [event.process_id, event.timestamp_utc, event.raw_line]));
  await other.getByLabel('Contains string', { exact: true }).fill('NO-SYNTHETIC-MATCH');
  await other.getByRole('button', { name: 'Apply filter', exact: true }).click();
  await expect(other.getByTestId('match-count')).toHaveText('0 matches');
  await expect(page.getByTestId('match-count')).toHaveText(`${expectedIds.length} matches`);
  await expect(page.getByLabel('Contains string', { exact: true })).toHaveValue('request_id=REQ-0042');
  await other.close();
  await expect(page.getByTestId('collection-state')).toHaveText('completed');
  await expect(page.getByTestId('match-count')).toHaveText(`${expectedIds.length} matches`);
  const workspace = await page.getByTestId('workspace-id').innerText();
  for (const viewport of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(viewport);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await expect(page.getByTestId('investigation-id')).toHaveText(first);
      await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
      await expect(page.getByTestId('match-count')).toHaveText(`${expectedIds.length} matches`);
      await expect(page.getByLabel('Contains string', { exact: true })).toHaveValue('request_id=REQ-0042');
      await page.getByTestId('match-count').scrollIntoViewIfNeeded();
      await page.screenshot({ path: resolve(screenshots, `inspector-ssh-history-${theme}-${viewport.width}x${viewport.height}.png`), animations: 'disabled' });
      expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
    }
  }
});
