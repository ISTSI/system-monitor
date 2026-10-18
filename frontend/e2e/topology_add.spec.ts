import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Preferences } from '../src/api/types';
import { defaultGeometry, type Config, type Topology } from '../src/topology';
import { serveBuiltAssets, setAppearance, submitSignIn } from './ui';

const enabled = ['https://localhost:8449', 'https://localhost:8450'].includes(process.env.INSPECTOR_E2E_URL ?? '');
const fixture = enabled ? JSON.parse(readFileSync(resolve('../.state/stage7-browser/public-fixture.json'), 'utf8')) as { synthetic: boolean; host: string; projects: string[] } : null;
if (enabled && (!fixture?.synthetic || fixture.host !== 'stage7-sftp' || fixture.projects.join(',') !== 'stage7-fixture-a,stage7-fixture-b')) throw new Error('Only the isolated generated Stage 07 fixture is authorized.');
const errors = new WeakMap<BrowserContext, string[]>();
const originals = new WeakMap<BrowserContext, Preferences>();
const created = new WeakMap<BrowserContext, string[]>();
test.skip(!enabled, 'Requires the isolated generated Stage 07 real MariaDB/SFTP fixture.');

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
        const response = await page.request.post(`/api/v1/projects/${id}/archive`, { headers: requestHeaders, data: { expected_revision: current.revision } });
        expect(response.status()).toBe(200);
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
  const response = await page.request.post('/api/v1/projects', { headers: requestHeaders, data: { name: `Frame add ${Date.now()}`, description: 'Synthetic frame add and log path defaults.' } });
  expect(response.status()).toBe(201);
  const id = (await response.json() as { project_id: string }).project_id; created.get(page.context())!.push(id);
  const { config } = await topology(page, fixture!.projects[0]);
  config.project = { ...config.project, id, revision: 1, name: 'Synthetic frame add' };
  config.subsystems = [
    { id: 'subsystem-first', name: 'First subsystem', description: '', tags: [] },
    { id: 'subsystem-target', name: 'Target subsystem', description: '', tags: [] },
  ];
  const connection = config.connections![0];
  config.connections = [
    { ...connection, id: 'connection-first', name: 'First connection', allowed_log_roots: ['/srv/first'] },
    { ...connection, id: 'connection-target', name: 'Target connection', allowed_log_roots: ['/srv/target/', '/srv/secondary'] },
    { ...connection, id: 'connection-empty', name: 'No proposed roots', allowed_log_roots: [] },
  ];
  config.servers = [
    { id: 'server-first', name: 'First server', subsystem_id: 'subsystem-first', connection_id: 'connection-first', description: '', tags: [] },
    { id: 'server-target', name: 'Target server', subsystem_id: 'subsystem-target', connection_id: 'connection-target', description: '', tags: [] },
    { id: 'server-empty', name: 'No roots server', subsystem_id: 'subsystem-target', connection_id: 'connection-empty', description: '', tags: [] },
  ];
  config.processes = []; config.flows = [];
  config.views = [{ id: 'overview', name: 'Overview', nodes: defaultGeometry(config), flow_ids: [] }];
  const saved = await page.request.put(`/api/v1/projects/${id}/topology`, { headers: requestHeaders, data: { expected_revision: 1, config } });
  expect(saved.status()).toBe(200);
  return (await saved.json() as Topology).config;
}

test('frame add buttons preserve their parent, save through revisions, and suggest that server connection first root', async ({ page, baseURL }) => {
  test.setTimeout(180000);
  await login(page, baseURL!, 'administrator');
  const config = await seed(page, baseURL!); const id = config.project.id;
  await page.goto(`/systems/${id}/topology`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  const workspace = await page.getByTestId('workspace-id').innerText();
  const duplicate = await page.context().newPage();
  try {
    await duplicate.goto(`/systems/${id}/topology`);
    await expect(duplicate.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
    await expect(duplicate.getByTestId('workspace-id')).not.toHaveText(workspace);
    await duplicate.getByRole('button', { name: 'Add process to Target server', exact: true }).click();
    await expect(duplicate.getByRole('dialog', { name: 'Add process', exact: true }).getByRole('combobox', { name: 'Server', exact: true })).toHaveValue('server-target');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
  } finally { await duplicate.close(); }
  await page.getByRole('button', { name: 'Select server First server', exact: true }).click();
  const collapse = page.getByRole('button', { name: 'Collapse Target subsystem', exact: true });
  await collapse.click();
  await expect(page.getByRole('button', { name: 'Expand Target subsystem', exact: true })).toBeVisible();
  const baseline = await topology(page, id);
  const addServer = page.getByRole('button', { name: 'Add server to Target subsystem', exact: true });
  await addServer.focus(); await page.keyboard.press('Enter');
  let dialog = page.getByRole('dialog', { name: 'Add server', exact: true });
  await expect(dialog.getByRole('combobox', { name: 'Subsystem', exact: true })).toHaveValue('subsystem-target');
  await expect(page.locator('.details-title code')).toHaveText('server-first');
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(addServer).toBeFocused();
  expect(await topology(page, id)).toEqual(baseline);
  await addServer.click(); dialog = page.getByRole('dialog', { name: 'Add server', exact: true });
  await dialog.getByLabel('Name', { exact: true }).fill('Added server');
  await dialog.getByLabel('Stable ID', { exact: true }).fill('server-added');
  await dialog.getByRole('combobox', { name: 'Connection profile', exact: true }).selectOption('connection-target');
  await dialog.getByRole('button', { name: 'Save server', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  let saved = await topology(page, id);
  expect(saved.revision).toBe(baseline.revision + 1);
  expect(saved.config.servers.find(server => server.id === 'server-added')).toMatchObject({ subsystem_id: 'subsystem-target', connection_id: 'connection-target' });
  expect(saved.config.views[0].nodes.find(node => node.element_id === 'subsystem-target')!.collapsed).toBe(false);
  await expect(page.getByRole('button', { name: 'Add process to Added server', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Collapse Target server', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Expand Target server', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Add process to Target server', exact: true }).click();
  dialog = page.getByRole('dialog', { name: 'Add process', exact: true });
  const server = dialog.getByRole('combobox', { name: 'Server', exact: true }); const path = dialog.getByLabel('Active log path', { exact: true });
  await expect(server).toHaveValue('server-target'); await expect(path).toHaveValue('/srv/target/app.log');
  await server.selectOption('server-first'); await expect(path).toHaveValue('/srv/first/app.log');
  await server.selectOption('server-empty'); await expect(path).toHaveValue(''); await expect(path).toHaveAttribute('required', '');
  await server.selectOption('server-target'); await expect(path).toHaveValue('/srv/target/app.log');
  await path.fill('/srv/target/custom.log');
  await server.selectOption('server-first'); await expect(path).toHaveValue('/srv/target/custom.log');
  await server.selectOption('server-target');
  await dialog.getByLabel('Name', { exact: true }).fill('Added process');
  await dialog.getByLabel('Stable ID', { exact: true }).fill('process-added');
  await dialog.getByRole('button', { name: 'Save process', exact: true }).click(); await expect(dialog).not.toBeVisible();
  saved = await topology(page, id);
  expect(saved.config.processes).toHaveLength(1);
  expect(saved.config.processes[0]).toMatchObject({ id: 'process-added', server_id: 'server-target', log_source: { active_path: '/srv/target/custom.log' } });
  expect(saved.config.views[0].nodes.find(node => node.element_id === 'server-target')!.collapsed).toBe(false);
  await expect(page.getByRole('button', { name: 'Select process Added process', exact: true })).toBeVisible();
  await page.locator('.canvas-toolbar').getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Select process Added process', exact: true })).toHaveCount(0);
  await page.locator('.canvas-toolbar').getByRole('button', { name: 'Redo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Select process Added process', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Select process Added process', exact: true }).click();
  await page.locator('.process-details').getByRole('button', { name: 'Edit selected', exact: true }).click();
  dialog = page.getByRole('dialog', { name: 'Edit process', exact: true });
  await expect(dialog.getByLabel('Active log path', { exact: true })).toHaveValue('/srv/target/custom.log');
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();

  const screenshots = resolve('../verification/stage-7/screenshots'); mkdirSync(screenshots, { recursive: true });
  for (const theme of ['light', 'dark'] as const) {
    await setAppearance(page, theme);
    for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
      await page.setViewportSize(size);
      await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
      await expect(page.getByRole('button', { name: 'Add server to Target subsystem', exact: true })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Add process to Target server', exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
      await expect(page.getByRole('button', { name: 'Add server to Target subsystem', exact: true })).toBeInViewport();
      await expect(page.getByRole('button', { name: 'Add process to Target server', exact: true })).toBeInViewport();
      await page.screenshot({ path: resolve(screenshots, `topology-frame-add-${theme}-${size.width}x${size.height}.png`), animations: 'disabled' });
    }
  }
  const current = await (await page.request.get('/api/v1/me/preferences')).json() as Preferences;
  expect((await page.request.patch('/api/v1/me/preferences', { headers: await headers(page, baseURL!), data: { language: 'pl', expected_revision: current.revision } })).status()).toBe(200);
  await page.reload(); await expect(page.getByRole('button', { name: 'Dodaj serwer do Target subsystem', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Dodaj proces do Target server', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Dodaj proces', exact: true }).getByRole('combobox', { name: 'Serwer', exact: true })).toHaveValue('server-target');
});

test('inspectors retain expand and select controls without shared frame add actions', async ({ page, baseURL }) => {
  await login(page, baseURL!, 'inspector');
  await page.goto(`/systems/${fixture!.projects[0]}/topology`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await expect(page.locator('.node-add-button')).toHaveCount(0);
  const collapsed = page.getByRole('button', { name: /^Collapse / }).first();
  await expect(collapsed).toBeVisible();
  const label = await collapsed.getAttribute('aria-label');
  await collapsed.click(); await expect(page.getByRole('button', { name: label!.replace(/^Collapse /, 'Expand '), exact: true })).toBeVisible();
  await expect(page.locator('.node-add-button')).toHaveCount(0);
});
