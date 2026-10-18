import { expect, test, type BrowserContext, type Locator, type Page } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { components } from '../src/api/schema';
import type { Preferences } from '../src/api/types';
import { defaultGeometry, type Config, type Connection, type Topology } from '../src/topology';
import { serveBuiltAssets, setAppearance, submitSignIn, systemAction } from './ui';

const enabled = process.env.INSPECTOR_E2E_URL === 'https://localhost:8449';
const fixture = enabled ? JSON.parse(readFileSync(resolve('../.state/stage7-browser/public-fixture.json'), 'utf8')) as { synthetic: boolean; host: string; projects: string[] } : null;
if (enabled && (!fixture?.synthetic || fixture.host !== 'stage7-sftp' || fixture.projects.join(',') !== 'stage7-fixture-a,stage7-fixture-b')) throw new Error('Only the isolated generated Stage 07 fixture is authorized.');
const errors = new WeakMap<BrowserContext, string[]>();
const originals = new WeakMap<BrowserContext, Preferences>();
const created = new WeakMap<BrowserContext, string[]>();
test.skip(!enabled, 'Requires the isolated generated Stage 07 real MariaDB fixture on https://localhost:8449.');

async function headers(page: Page, baseURL: string) {
  const response = await page.request.get('/api/v1/auth/csrf'); expect(response.status()).toBe(200);
  return { Origin: baseURL, 'X-CSRF-Token': (await response.json() as { csrf_token: string }).csrf_token };
}

async function topology(page: Page, id: string): Promise<Topology> {
  const response = await page.request.get(`/api/v1/projects/${id}/topology`); expect(response.status()).toBe(200);
  return await response.json() as Topology;
}

test.beforeEach(async ({ page, context, baseURL }) => {
  const found: string[] = []; errors.set(context, found); created.set(context, []);
  page.on('pageerror', error => found.push(error.message)); context.on('page', extra => extra.on('pageerror', error => found.push(error.message)));
  await context.grantPermissions(['local-network-access'], { origin: baseURL! });
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin === baseURL) return route.fallback();
    found.push('External request blocked'); return route.abort();
  });
  await serveBuiltAssets(context, baseURL!);
});

test.afterEach(async ({ page, context, baseURL }) => {
  try {
    if ((await page.request.get('/api/v1/auth/session')).status() === 200) {
      const requestHeaders = await headers(page, baseURL!);
      for (const id of created.get(context) ?? []) {
        const current = await topology(page, id);
        expect((await page.request.post(`/api/v1/projects/${id}/archive`, { headers: requestHeaders, data: { expected_revision: current.revision } })).status()).toBe(200);
      }
      const original = originals.get(context);
      if (original) {
        const current = await (await page.request.get('/api/v1/me/preferences')).json() as Preferences;
        expect((await page.request.patch('/api/v1/me/preferences', { headers: requestHeaders, data: { theme_mode: original.theme_mode, language: original.language, expected_revision: current.revision } })).status()).toBe(200);
      }
      expect((await page.request.post('/api/v1/auth/logout', { headers: requestHeaders, data: {} })).status()).toBe(200);
    }
  } finally { expect(errors.get(context)).toEqual([]); }
});

async function login(page: Page, baseURL: string, role: 'administrator' | 'inspector') {
  const file = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!file) throw new Error('Protected synthetic accounts are required.');
  const account = (JSON.parse(readFileSync(resolve(file), 'utf8')) as Record<string, { username: string; password: string }>)[role];
  await page.goto('/'); await page.locator('input[name="username"]').fill(account.username);
  try { await page.locator('input[name="password"]').fill(account.password); expect((await submitSignIn(page)).status()).toBe(200); }
  catch { await page.locator('input[type="password"]').fill('').catch(() => {}); throw new Error('Synthetic sign-in failed; protected values withheld.'); }
  const response = await page.request.get('/api/v1/me/preferences'); expect(response.status()).toBe(200);
  const preference = await response.json() as Preferences; originals.set(page.context(), preference);
  expect((await page.request.patch('/api/v1/me/preferences', { headers: await headers(page, baseURL), data: { language: 'en', expected_revision: preference.revision } })).status()).toBe(200);
}

async function seed(page: Page, baseURL: string): Promise<Config> {
  const requestHeaders = await headers(page, baseURL);
  const response = await page.request.post('/api/v1/projects', { headers: requestHeaders, data: { name: `Connection copy ${Date.now()}`, description: 'Synthetic connection-copy browser verification.' } });
  expect(response.status()).toBe(201);
  const id = (await response.json() as { project_id: string }).project_id; created.get(page.context())!.push(id);
  const { config } = await topology(page, fixture!.projects[0]);
  config.project = { ...config.project, id, revision: 1, name: 'Synthetic connection copy' };
  config.subsystems = [{ id: 'copy-subsystem', name: 'Copy subsystem', description: '', tags: [] }];
  config.connections = [
    { id: 'copy-jump', name: 'Synthetic jump', host: '192.0.2.10', port: 2222, username: 'jump-reader', credential_ref: 'copy-jump-password', jump_connection_id: null, allowed_log_roots: [] },
    { id: 'copy-source', name: 'Synthetic source', host: '192.0.2.44', port: 2022, username: 'copy-logreader', credential_ref: 'copy-source-password', jump_connection_id: 'copy-jump', allowed_log_roots: ['/srv/copy', '/var/log/copy'] },
  ];
  config.servers = [{ id: 'copy-server', name: 'Source server', subsystem_id: 'copy-subsystem', connection_id: 'copy-source', description: '', tags: [] }];
  config.processes = []; config.flows = [];
  config.views = [{ id: 'overview', name: 'Overview', nodes: defaultGeometry(config), flow_ids: [] }];
  const saved = await page.request.put(`/api/v1/projects/${id}/topology`, { headers: requestHeaders, data: { expected_revision: 1, config } });
  expect(saved.status()).toBe(200);
  return (await saved.json() as Topology).config;
}

function connectionRow(page: Page, name: string) {
  return page.locator('.profile-list > div').filter({ has: page.getByText(name, { exact: true }) });
}

async function expectCopiedFields(dialog: Locator, source: Connection) {
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel('Name', { exact: true })).toHaveValue(source.name);
  await expect(dialog.getByText('Choose a unique name for the new connection before saving.', { exact: true })).toBeVisible();
  await expect(dialog.getByLabel('SSH host', { exact: true })).toHaveValue(source.host);
  await expect(dialog.getByLabel('SSH port', { exact: true })).toHaveValue(String(source.port));
  await expect(dialog.getByLabel('Username', { exact: true })).toHaveValue(source.username);
  await expect(dialog.getByLabel('Credential reference', { exact: true })).toHaveValue(source.credential_ref);
  await expect(dialog.getByRole('combobox', { name: 'Jump connection', exact: true })).toHaveValue(source.jump_connection_id ?? '');
  await expect(dialog.getByRole('textbox', { name: 'Proposed log roots (one absolute Linux path per line)', exact: true })).toHaveValue(source.allowed_log_roots.join('\n'));
  const id = dialog.getByLabel('Stable ID', { exact: true });
  await expect(id).toBeEditable(); await expect(id).not.toHaveValue(source.id);
  expect(await id.inputValue()).not.toBe('');
}

test('Copy opens an independent prefilled create form; cancel preserves the source and save adds only the new connection', async ({ page, baseURL }) => {
  test.setTimeout(180000);
  await login(page, baseURL!, 'administrator');
  const config = await seed(page, baseURL!); const id = config.project.id;
  const source = config.connections!.find(connection => connection.id === 'copy-source')!;
  const otherSystem = await topology(page, fixture!.projects[1]);
  await page.goto(`/systems/${id}/topology`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  const workspace = await page.getByTestId('workspace-id').innerText();
  const baseline = await topology(page, id);
  const writes: string[] = []; const remoteRequests: string[] = [];
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (request.method() === 'PUT' && path === `/api/v1/projects/${id}/topology`) writes.push(path);
    if (request.method() === 'POST' && (/\/connections\/[^/]+\/(?:test|host-key|source-access|credential)(?:\/|$)/.test(path) || /\/(?:collections|live-sessions)(?:\/|$)/.test(path))) remoteRequests.push(path);
  });
  const duplicate = await page.context().newPage();
  try {
    await duplicate.goto(`/systems/${id}/topology`);
    await expect(duplicate.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
    await expect(duplicate.getByTestId('workspace-id')).not.toHaveText(workspace);
    const direct = config.connections!.find(connection => connection.id === 'copy-jump')!;
    await systemAction(page, 'List connections');
    await connectionRow(page, direct.name).getByRole('button', { name: /^Copy\b/ }).click();
    const directCopy = page.getByRole('dialog', { name: 'Add connection', exact: true });
    await expectCopiedFields(directCopy, direct);
    await directCopy.getByRole('button', { name: 'Cancel', exact: true }).click();
    expect(await topology(page, id)).toEqual(baseline); expect(writes).toEqual([]);
    await systemAction(page, 'List connections');
    await connectionRow(page, source.name).getByRole('button', { name: /^Copy\b/ }).click();
    let dialog = page.getByRole('dialog', { name: 'Add connection', exact: true });
    await expectCopiedFields(dialog, source);
    const cancelledId = await dialog.getByLabel('Stable ID', { exact: true }).inputValue();
    await expect(dialog.locator('.target-system')).toContainText(id);
    await expect(duplicate.getByRole('dialog')).toHaveCount(0);
    expect(await topology(page, id)).toEqual(baseline); expect(writes).toEqual([]);
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(await topology(page, id)).toEqual(baseline); expect(writes).toEqual([]);

    await systemAction(page, 'List connections');
    await connectionRow(page, source.name).getByRole('button', { name: /^Edit\b/ }).click();
    const edit = page.getByRole('dialog', { name: 'Edit connection', exact: true });
    await expect(edit.getByLabel('Stable ID', { exact: true })).toHaveValue(source.id);
    await edit.getByRole('button', { name: 'Copy', exact: true }).click();
    dialog = page.getByRole('dialog', { name: 'Add connection', exact: true });
    await expectCopiedFields(dialog, source);
    await expect(dialog.getByLabel('Stable ID', { exact: true })).not.toHaveValue(cancelledId);
    await expect(page.getByRole('dialog', { name: 'Edit connection', exact: true })).toHaveCount(0);

    const screenshots = resolve('../verification/connection-copy/screenshots'); mkdirSync(screenshots, { recursive: true });
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
        await page.setViewportSize(size);
        await expectCopiedFields(dialog, source);
        await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
        await page.screenshot({ path: resolve(screenshots, `connection-copy-${theme}-${size.width}x${size.height}.png`), animations: 'disabled' });
      }
    }
    await dialog.getByLabel('Stable ID', { exact: true }).fill(source.id);
    await dialog.getByRole('button', { name: 'Save connection', exact: true }).click();
    await expect(dialog.getByRole('alert')).toContainText('already belongs');
    expect(writes).toEqual([]); expect(await topology(page, id)).toEqual(baseline);
    await dialog.getByLabel('Stable ID', { exact: true }).fill('connection-copy-saved');
    await dialog.getByLabel('Name', { exact: true }).fill('Synthetic source copy');
    await dialog.getByRole('button', { name: 'Save connection', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    const saved = await topology(page, id);
    expect(writes).toHaveLength(1); expect(saved.revision).toBe(baseline.revision + 1);
    expect(saved.config.connections).toEqual([...baseline.config.connections!, { ...source, id: 'connection-copy-saved', name: 'Synthetic source copy' }]);
    expect({ ...saved.config, connections: baseline.config.connections, project: baseline.config.project }).toEqual(baseline.config);
    const accessResponse = await page.request.get(`/api/v1/projects/${id}/connections/connection-copy-saved/access`);
    expect(accessResponse.status()).toBe(200);
    const access = await accessResponse.json() as components['schemas']['AccessResponse'];
    expect(access.host_key.approved).toBe(false);
    expect(await topology(page, fixture!.projects[1])).toEqual(otherSystem);
    await expect(duplicate.getByRole('dialog')).toHaveCount(0);
    expect(remoteRequests).toEqual([]);

    const preference = await (await page.request.get('/api/v1/me/preferences')).json() as Preferences;
    expect((await page.request.patch('/api/v1/me/preferences', { headers: await headers(page, baseURL!), data: { language: 'pl', expected_revision: preference.revision } })).status()).toBe(200);
    await page.reload();
    await page.getByRole('button', { name: 'System', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Lista połączeń', exact: true }).click();
    await connectionRow(page, source.name).getByRole('button', { name: /^Kopiuj\b/ }).click();
    const localized = page.getByRole('dialog', { name: 'Dodaj połączenie', exact: true });
    await expect(localized.getByLabel('Nazwa', { exact: true })).toHaveValue(source.name);
    await localized.getByRole('button', { name: 'Anuluj', exact: true }).click();
    expect(await topology(page, id)).toEqual(saved);
  } finally { await duplicate.close(); }
});

test('Inspector has no connection-copy or configuration-management controls', async ({ page, baseURL }) => {
  await login(page, baseURL!, 'inspector');
  await page.goto(`/systems/${fixture!.projects[0]}/topology`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await expect(page.getByRole('button', { name: 'System', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^Copy(?: connection)?(?:\s|$)/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Edit SSH connection', exact: true })).toHaveCount(0);
});
