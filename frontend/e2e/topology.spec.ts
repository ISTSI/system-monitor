import { test, expect, type Page, type Locator } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { editSystemDetails, setAppearance, submitSignIn, systemAction } from './ui';
import type { Config, EntityKind, Topology } from '../src/topology';

const screenshots = resolve(`../verification/${process.env.INSPECTOR_E2E_REPORT_STAGE ?? 'stage-2'}/screenshots`);
type Role = 'administrator' | 'inspector';
const browserErrors = new WeakMap<Page, string[]>();
test.beforeEach(({ page }) => {
  const errors: string[] = [];
  browserErrors.set(page, errors);
  page.on('pageerror', error => errors.push(error.message));
});
test.afterEach(async ({ page, baseURL }) => {
  try { expect(browserErrors.get(page)).toEqual([]); } finally {
    // Release the synthetic account's leases between tests, including detached
    // pages retained by the real grace period. Keep production quotas intact.
    if ((await page.request.get('/api/v1/auth/session')).status() === 200) {
      const csrf = await page.request.get('/api/v1/auth/csrf');
      const { csrf_token } = await csrf.json() as { csrf_token: string };
      const loggedOut = await page.request.post('/api/v1/auth/logout', {
        headers: { Origin: new URL(baseURL!).origin, 'X-CSRF-Token': csrf_token }, data: {},
      });
      expect(loggedOut.status()).toBe(200);
    }
  }
});

async function login(page: Page, role: Role) {
  const filename = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!filename) throw new Error('Protected synthetic-account fixture is required.');
  const accounts = JSON.parse(readFileSync(resolve(filename), 'utf8')) as Record<Role, { username: string; password: string }>;
  await page.goto('/');
  await page.getByLabel('Username', { exact: true }).fill(accounts[role].username);
  await page.getByLabel('Password', { exact: true }).fill(accounts[role].password);
  // Never retain a failed password form in browser artifacts.
  const response = await submitSignIn(page);
  if (response.status() !== 200) {
    await page.locator('input[type="password"]').fill('');
    throw new Error(`Synthetic sign-in returned ${response.status()}; protected details withheld.`);
  }
  await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
}

async function createSystem(page: Page, name: string): Promise<string> {
  console.log('Creating a synthetic system through the catalogue form.');
  await page.getByRole('link', { name: 'Admin', exact: true }).click();
  await page.getByRole('button', { name: '+ Create system', exact: true }).click();
  await page.getByLabel('System name', { exact: true }).fill(name);
  await page.getByRole('textbox', { name: 'Description', exact: true }).fill('Synthetic Stage 02 browser acceptance.');
  await page.getByRole('button', { name: 'Create system', exact: true }).click();
  await expect(page).toHaveURL(/\/systems\/[^/]+\/topology$/);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  return decodeURIComponent(new URL(page.url()).pathname.split('/')[2]);
}

async function readTopology(page: Page, id: string): Promise<Topology> {
  const result = await page.request.get(`/api/v1/projects/${id}/topology`);
  expect(result.status()).toBe(200);
  return await result.json() as Topology;
}

async function createEntity(page: Page, kind: EntityKind, id: string, name: string, fill?: (dialog: Locator) => Promise<void>) {
  console.log(`Creating ${kind} ${id} through its form.`);
  if (kind === 'connection' || kind === 'parser') {
    await systemAction(page, kind === 'connection' ? 'List connections' : 'List Parsers');
    await page.getByRole('button', { name: `Add ${kind}`, exact: true }).click();
  } else if (kind === 'view') await page.getByRole('button', { name: 'Add view', exact: true }).click();
  else await systemAction(page, `Add ${kind}`);
  const dialog = page.getByRole('dialog', { name: `Add ${kind}`, exact: true });
  await dialog.getByLabel('Name', { exact: true }).fill(name);
  await dialog.getByLabel('Stable ID', { exact: true }).fill(id);
  if (fill) await fill(dialog);
  await dialog.getByRole('button', { name: `Save ${kind}`, exact: true }).click();
  await expect(dialog).not.toBeVisible();
  const manager = page.getByRole('dialog');
  if ((kind === 'connection' || kind === 'parser') && await manager.count()) await manager.getByRole('button', { name: 'Close dialog', exact: true }).click();
}

async function capture(page: Page, filename: string) {
  mkdirSync(screenshots, { recursive: true });
  await page.screenshot({ path: resolve(screenshots, filename + '.png'), animations: 'disabled' });
}

test('compact topology keeps system actions in a dismissible menu and administration in its own view', async ({ page }) => {
  await login(page, 'administrator');
  await page.goto('/systems/demo-foundation-a/topology');
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  const workspace = await page.getByTestId('workspace-id').innerText();
  const topbar = page.locator('.topbar');
  await expect(topbar.getByText('SYNTHETIC DEMO DATA', { exact: true })).toBeVisible();
  await expect(topbar.getByLabel('Appearance', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Administrator workspace', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Open separately', { exact: true })).toHaveCount(0);
  await expect(page.locator('.topology-edit-toolbar, .mode-strip')).toHaveCount(0);
  await expect(page.locator('.canvas-toolbar').getByRole('button', { name: 'Undo', exact: true })).toBeVisible();
  await expect(page.locator('.canvas-toolbar').getByRole('button', { name: 'Redo', exact: true })).toBeVisible();
  const trigger = page.getByRole('button', { name: 'System', exact: true });
  const menu = page.getByRole('menu', { name: 'System', exact: true });
  await trigger.click();
  await expect(menu).toBeVisible();
  const actions = ['Add subsystem', 'Add server', 'Add process', 'Add flow', 'List connections', 'List Parsers', 'Import configuration', 'Export JSON', 'Export YAML'];
  await expect(menu.getByRole('menuitem')).toHaveCount(actions.length);
  for (const name of actions) await expect(menu.getByRole('menuitem', { name, exact: true })).toBeVisible();
  await expect(menu.getByRole('menuitem', { name: actions[0], exact: true })).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(menu.getByRole('menuitem', { name: actions[1], exact: true })).toBeFocused();
  await page.keyboard.press('End');
  await expect(menu.getByRole('menuitem', { name: actions.at(-1), exact: true })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(menu).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await trigger.click();
  await topbar.getByText('SYNTHETIC DEMO DATA', { exact: true }).click();
  await expect(menu).not.toBeVisible();
  await systemAction(page, 'Add subsystem');
  await expect(menu).not.toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Add subsystem', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(size);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
      await expect(page.getByRole('heading', { name: 'Documented topology', exact: true })).toBeVisible();
      const canvas = await page.locator('.reactflow-canvas').boundingBox();
      expect(canvas).not.toBeNull();
      expect(canvas!.y).toBeLessThan(size.height / 2);
      expect(canvas!.height).toBeGreaterThan(size.height / 2);
      expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
      await capture(page, `administrator-compact-${theme}-${size.width}x${size.height}`);
      await trigger.click();
      await expect(menu).toBeVisible();
      await capture(page, `administrator-compact-menu-${theme}-${size.width}x${size.height}`);
      await page.keyboard.press('Escape');
      await page.getByRole('button', { name: 'Settings', exact: true }).click();
      const settings = page.getByRole('dialog', { name: 'Settings', exact: true });
      await expect(settings.getByLabel('Appearance', { exact: true })).toBeEnabled();
      await expect(settings.getByRole('button', { name: 'Save application settings', exact: true })).toBeVisible();
      await capture(page, `administrator-settings-${theme}-${size.width}x${size.height}`);
      await settings.getByRole('button', { name: 'Close', exact: true }).click();
    }
  }
  const originalUrl = page.url();
  const openedPage = page.context().waitForEvent('page');
  await page.locator('.system-bar-title h1 a').click({ modifiers: ['Control'] });
  const duplicate = await openedPage;
  await expect(duplicate).toHaveURL(originalUrl);
  await expect(duplicate.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await expect(duplicate.getByTestId('workspace-id')).not.toHaveText(workspace);
  await expect(page).toHaveURL(originalUrl);
  await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
  await duplicate.close();
  await page.getByRole('link', { name: 'Admin', exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole('heading', { name: 'System administration', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '+ Create system', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'System', exact: true })).toHaveCount(0);
  await expect(page.locator('.system-card').first()).toBeVisible();
  for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(size);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await capture(page, `administrator-admin-${theme}-${size.width}x${size.height}`);
    }
  }
});

test('administrator builds and edits a complete graph, preserves identity and round-trips configuration', async ({ page }) => {
  test.setTimeout(180000);
  await login(page, 'administrator');
  const id = await createSystem(page, `Stage 02 editing ${Date.now()}`);
  await createEntity(page, 'subsystem', 'alpha', 'Gateway', async dialog => {
    await dialog.getByLabel('Documentation (Markdown)').fill('# Gateway\nShared **gateway** documentation.');
  });
  await createEntity(page, 'subsystem', 'beta', 'Processing');
  const beforeDuplicate = (await readTopology(page, id)).revision;
  await systemAction(page, 'Add subsystem');
  await page.getByRole('dialog').getByLabel('Name', { exact: true }).fill('Attempted replacement');
  await page.getByRole('dialog').getByLabel('Stable ID', { exact: true }).fill('alpha');
  await page.getByRole('button', { name: 'Save subsystem', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('already belongs');
  expect((await readTopology(page, id)).revision).toBe(beforeDuplicate);
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await createEntity(page, 'connection', 'connection-one', 'Synthetic SSH proposal', async dialog => {
    await dialog.getByLabel('SSH host', { exact: true }).fill('192.0.2.10');
    await dialog.getByLabel('Username', { exact: true }).fill('logreader');
    await dialog.getByLabel('Credential reference', { exact: true }).fill('unresolved-secret');
    await dialog.getByLabel(/Proposed log roots/).fill('/var/log');
  });
  await createEntity(page, 'parser', 'parser-one', 'UTC parser');
  await createEntity(page, 'server', 'host-one', 'Gateway host', async dialog => {
    await dialog.getByRole('combobox', { name: 'Subsystem', exact: true }).selectOption('alpha');
  });
  await createEntity(page, 'server', 'host-two', 'Processing host', async dialog => {
    await dialog.getByRole('combobox', { name: 'Subsystem', exact: true }).selectOption('beta');
  });
  for (const [processId, name, host] of [['ingest', 'Ingest', 'host-one'], ['worker', 'Worker', 'host-two']]) {
    await createEntity(page, 'process', processId, name, async dialog => {
      await dialog.getByRole('combobox', { name: 'Server', exact: true }).selectOption(host);
      await dialog.getByLabel('Active log path', { exact: true }).fill(`/var/log/${processId}.log`);
      await dialog.getByLabel('PCS resource name (optional)', { exact: true }).fill(`pcs-${processId}`);
      await dialog.getByLabel('Documentation (Markdown)').fill(`## ${name}\nShared **transaction** documentation.`);
      await dialog.getByLabel('Tags (comma separated)').fill('synthetic, transaction');
    });
  }
  await createEntity(page, 'flow', 'transfer', 'Requests', async dialog => {
    await dialog.getByRole('combobox', { name: 'Source process', exact: true }).selectOption('ingest');
    await dialog.getByRole('combobox', { name: 'Target process', exact: true }).selectOption('worker');
    await dialog.getByLabel('Protocol', { exact: true }).fill('HTTPS');
  });
  const initial = await readTopology(page, id);
  expect(initial.config.flows[0]).toMatchObject({ id: 'transfer', source_process_id: 'ingest', target_process_id: 'worker' });
  await page.getByRole('button', { name: 'Select process Ingest', exact: true }).click();
  await expect(page.locator('.safe-markdown strong')).toContainText('transaction');
  await page.getByRole('button', { name: 'Edit selected', exact: true }).click();
  await page.getByRole('dialog').getByLabel('Name', { exact: true }).fill('Renamed ingress');
  await page.getByRole('button', { name: 'Save process', exact: true }).click();
  let current = await readTopology(page, id);
  expect(current.config.processes.find(process => process.id === 'ingest')?.name).toBe('Renamed ingress');
  expect(current.config.flows).toEqual(initial.config.flows);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Select process Ingest', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Redo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Select process Renamed ingress', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Move to server', exact: true }).click();
  await page.getByRole('combobox', { name: 'New server', exact: true }).selectOption('host-two');
  await page.getByRole('button', { name: 'Confirm move', exact: true }).click();
  current = await readTopology(page, id);
  expect(current.config.processes.find(process => process.id === 'ingest')?.server_id).toBe('host-two');
  expect(current.config.flows).toEqual(initial.config.flows);
  await createEntity(page, 'view', 'detail-view', 'Detail');
  await page.getByLabel('Named view', { exact: true }).selectOption('detail-view');
  await page.getByRole('button', { name: 'Collapse Processing', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Expand Processing', exact: true })).toBeVisible();
  await page.getByLabel('Search this system', { exact: true }).fill('pcs-ingest');
  await page.getByRole('button', { name: /Renamed ingress.*process|process.*Renamed ingress/i }).click();
  await expect(page.getByRole('button', { name: 'Select process Renamed ingress', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Expand Processing', exact: true })).toHaveCount(0);
  await page.getByLabel('Search this system', { exact: true }).fill('');
  const pendingDownload = page.waitForEvent('download');
  await systemAction(page, 'Export JSON');
  const download = await pendingDownload;
  const downloaded = JSON.parse(readFileSync((await download.path())!, 'utf8')) as Config;
  expect(downloaded.project.id).toBe(id);
  expect(downloaded.processes.map(process => process.id).sort()).toEqual(['ingest', 'worker']);
  expect(JSON.stringify(downloaded)).not.toContain('password');
  downloaded.processes[0].description = 'Externally edited **documentation**.';
  downloaded.views[0].nodes[0].x += 25;
  const revisionBefore = (await readTopology(page, id)).revision;
  await systemAction(page, 'Import configuration');
  await page.getByRole('combobox', { name: 'Configuration format', exact: true }).selectOption('json');
  await page.getByLabel('Configuration content', { exact: true }).fill(JSON.stringify(downloaded));
  await page.getByRole('button', { name: 'Preview configuration', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Commit configuration', exact: true })).toBeVisible();
  expect((await readTopology(page, id)).revision).toBe(revisionBefore);
  await capture(page, 'administrator-import-preview');
  await page.getByRole('button', { name: 'Commit configuration', exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  current = await readTopology(page, id);
  expect(current.config.processes[0].description).toBe(downloaded.processes[0].description);
  expect(current.config.views).toEqual(downloaded.views);
  await page.reload();
  current = await readTopology(page, id);
  expect(current.config.flows).toEqual(initial.config.flows);
  await expect(page.getByLabel('Named view')).toBeVisible();
  await capture(page, 'administrator-persisted-edited-graph');
  await page.getByRole('button', { name: 'Select process Renamed ingress', exact: true }).click();
  await page.getByRole('button', { name: 'Delete selected', exact: true }).click();
  const impact = page.getByRole('dialog', { name: 'Delete impact preview' });
  await expect(impact).toContainText('Requests');
  const beforeDelete = (await readTopology(page, id)).revision;
  await impact.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect((await readTopology(page, id)).revision).toBe(beforeDelete);
  await page.getByRole('button', { name: 'Delete selected', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm deletion', exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  current = await readTopology(page, id);
  expect(current.config.processes.map(process => process.id)).toEqual(['worker']);
  expect(current.config.flows).toEqual([]);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Select process Renamed ingress', exact: true })).toBeVisible();
  expect((await readTopology(page, id)).config.flows).toEqual(initial.config.flows);
});

test('same-account pages keep selection and search private and reject stale shared edits', async ({ page, context }) => {
  await login(page, 'administrator');
  await page.goto('/systems/demo-foundation-a/topology');
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  const duplicate = await context.newPage();
  await duplicate.goto(page.url());
  await expect(duplicate.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  const workspace = await page.getByTestId('workspace-id').innerText();
  expect(await duplicate.getByTestId('workspace-id').innerText()).not.toBe(workspace);
  await page.getByRole('button', { name: /^Select process / }).first().click();
  await page.getByLabel('Search this system', { exact: true }).fill('transaction-only-page-a');
  await expect(duplicate.getByLabel('Search this system', { exact: true })).toHaveValue('');
  await expect(duplicate.getByRole('heading', { name: 'Select a process', exact: true })).toBeVisible();
  await editSystemDetails(duplicate, 'demo-foundation-a');
  await duplicate.getByRole('textbox', { name: 'Description', exact: true }).fill('Stale draft from independent page');
  await editSystemDetails(page, 'demo-foundation-a');
  await page.getByRole('textbox', { name: 'Description', exact: true }).fill('New shared revision from page A');
  await page.getByRole('button', { name: 'Save system details', exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await duplicate.getByRole('button', { name: 'Save system details', exact: true }).click();
  await expect(duplicate.getByRole('alert')).toContainText(/changed|reload/i);
  await expect(duplicate.getByRole('textbox', { name: 'Description', exact: true })).toHaveValue('Stale draft from independent page');
  await duplicate.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.goto('/systems/demo-foundation-a/topology');
  await duplicate.goto('/systems/demo-foundation-a/topology');
  await expect(duplicate.getByLabel('System selector')).toHaveValue('demo-foundation-a');
  await duplicate.getByLabel('System selector').selectOption('demo-foundation-b');
  await expect(duplicate).toHaveURL(/demo-foundation-b\/topology$/);
  await expect(page.getByLabel('System selector')).toHaveValue('demo-foundation-a');
  await expect(page.getByTestId('workspace-id')).not.toHaveText(await duplicate.getByTestId('workspace-id').innerText());
  await duplicate.close();
});

test('Inspector safely navigates real topology in both themes without shared mutations', async ({ page, context }) => {
  const external: string[] = [];
  context.on('request', request => {
    const url = new URL(request.url());
    if (url.protocol.startsWith('http') && url.origin !== new URL(process.env.INSPECTOR_E2E_URL ?? 'https://localhost:8444').origin) external.push(url.origin);
  });
  await login(page, 'inspector');
  await page.goto('/systems/demo-foundation-b/topology');
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  const before = await readTopology(page, 'demo-foundation-b');
  expect(before.editable).toBe(false);
  expect(before.config.connections).toBeUndefined();
  expect(before.config.processes.every(process => process.log_source === undefined)).toBe(true);
  await expect(page.getByRole('button', { name: 'Add subsystem', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Import configuration', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'System', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Admin', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Settings', exact: true })).toBeVisible();
  const select = page.getByRole('button', { name: /^Select process / }).first();
  await select.focus();
  await page.keyboard.press('Enter');
  await expect(select).toHaveAttribute('aria-pressed', 'true');
  for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(size);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await expect(select).toHaveAttribute('aria-pressed', 'true');
      await capture(page, `inspector-${theme}-${size.width}x${size.height}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
      await page.getByRole('button', { name: 'Settings', exact: true }).click();
      const settings = page.getByRole('dialog', { name: 'Settings', exact: true });
      await expect(settings.getByLabel('Appearance', { exact: true })).toBeEnabled();
      await expect(settings.getByRole('button', { name: 'Save application settings', exact: true })).toHaveCount(0);
      await capture(page, `inspector-settings-${theme}-${size.width}x${size.height}`);
      await settings.getByRole('button', { name: 'Close', exact: true }).click();
    }
  }
  const after = await readTopology(page, 'demo-foundation-b');
  expect(after.revision).toBe(before.revision);
  expect(after.config).toEqual(before.config);
  expect(external).toEqual([]);
});

test('diagram drag and resize persist view geometry and preserve model parents', async ({ page }) => {
  await login(page, 'administrator');
  const origin = new URL(page.url()).origin;
  const csrfResponse = await page.request.get('/api/v1/auth/csrf');
  const headers = { Origin: origin, 'X-CSRF-Token': (await csrfResponse.json() as { csrf_token: string }).csrf_token };
  const created = await page.request.post('/api/v1/projects', { headers, data: { name: `Geometry ${Date.now()}`, description: 'Synthetic geometry interaction test.' } });
  expect(created.status()).toBe(201);
  const id = (await created.json() as { project_id: string }).project_id;
  const source = await readTopology(page, 'demo-foundation-b');
  const config = source.config;
  config.project = { ...config.project, id, name: 'Synthetic geometry interaction', revision: 1 };
  const seeded = await page.request.put(`/api/v1/projects/${id}/topology`, { headers, data: { expected_revision: 1, config } });
  expect(seeded.status()).toBe(200);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`/systems/${id}/topology`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await page.getByRole('button', { name: 'Select subsystem Orders Gateway', exact: true }).click();
  const group = page.locator('.react-flow__node[data-id="subsystem-0"]');
  const before = await readTopology(page, id);
  const header = await group.locator('.node-header').boundingBox();
  expect(header).not.toBeNull();
  const dragged = page.waitForResponse(response => response.request().method() === 'PUT' && response.url().endsWith(`/projects/${id}/topology`));
  await page.mouse.move(header!.x + 3, header!.y + 16);
  await page.mouse.down();
  await page.mouse.move(header!.x + 43, header!.y + 36, { steps: 8 });
  await page.mouse.up();
  expect((await dragged).status()).toBe(200);
  const moved = await readTopology(page, id);
  const nodeBefore = before.config.views[0].nodes.find(node => node.element_id === 'subsystem-0')!;
  const nodeMoved = moved.config.views[0].nodes.find(node => node.element_id === 'subsystem-0')!;
  expect(nodeMoved.x).not.toBe(nodeBefore.x);
  expect(nodeMoved.y).not.toBe(nodeBefore.y);
  // The details panel changes the canvas height; use the real navigation
  // control to bring its clipped resize handle back into the canvas.
  await page.getByRole('button', { name: 'Fit diagram', exact: true }).click();
  await page.waitForTimeout(250); // The explicit fit transition lasts 150 ms.
  const handle = group.locator('.react-flow__resize-control.bottom.right.handle');
  await expect(handle).toBeVisible();
  await expect(handle).toBeInViewport();
  const box = await handle.boundingBox();
  const canvas = await page.locator('.reactflow-canvas').boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull(); expect(canvas).not.toBeNull(); expect(viewport).not.toBeNull();
  // Assert full visibility directly: Chromium can report an intersection ratio
  // of 0.9999987 for a fully contained handle transformed by fractional zoom.
  expect(box!.x).toBeGreaterThanOrEqual(Math.max(0, canvas!.x));
  expect(box!.y).toBeGreaterThanOrEqual(Math.max(0, canvas!.y));
  expect(box!.x + box!.width).toBeLessThanOrEqual(Math.min(viewport!.width, canvas!.x + canvas!.width));
  expect(box!.y + box!.height).toBeLessThanOrEqual(Math.min(viewport!.height, canvas!.y + canvas!.height));
  const resized = page.waitForResponse(response => response.request().method() === 'PUT' && response.url().endsWith(`/projects/${id}/topology`));
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(box!.x + box!.width / 2 + 30, box!.y + box!.height / 2 + 20, { steps: 8 });
  await page.mouse.up();
  expect((await resized).status()).toBe(200);
  const changed = await readTopology(page, id);
  const nodeResized = changed.config.views[0].nodes.find(node => node.element_id === 'subsystem-0')!;
  expect(nodeResized.width).toBeGreaterThan(nodeMoved.width);
  expect(nodeResized.height).toBeGreaterThan(nodeMoved.height);
  expect(changed.config.servers).toEqual(before.config.servers);
  expect(changed.config.processes).toEqual(before.config.processes);
  await page.reload();
  expect((await readTopology(page, id)).config.views).toEqual(changed.config.views);
});

test('server setup exposes SSH endpoints and saves a new profile atomically with its server', async ({ page }) => {
  test.setTimeout(180000);
  await login(page, 'administrator');
  const id = await createSystem(page, `Server SSH setup ${Date.now()}`);
  await createEntity(page, 'subsystem', 'ssh-subsystem', 'Synthetic SSH subsystem');
  const baseline = await readTopology(page, id);
  expect(baseline.config.connections).toEqual([]);
  await page.getByRole('button', { name: 'System', exact: true }).click();
  await expect(page.getByRole('menuitem', { name: 'Add server', exact: true })).toBeEnabled();
  await page.keyboard.press('Escape');

  async function openServerForm() {
    await systemAction(page, 'Add server');
    return page.getByRole('dialog', { name: 'Add server', exact: true });
  }
  async function fillNewServer(dialog: Locator, serverId: string, name: string) {
    await dialog.getByLabel('Name', { exact: true }).fill(name);
    await dialog.getByLabel('Stable ID', { exact: true }).fill(serverId);
    await dialog.getByLabel('SSH host', { exact: true }).fill('192.0.2.44');
    await dialog.getByLabel('SSH port', { exact: true }).fill('2022');
    await dialog.getByLabel('Username', { exact: true }).fill('logreader');
    await dialog.getByLabel('Credential reference', { exact: true }).fill('unresolved-ssh-test');
    await dialog.getByLabel(/Proposed log roots/).fill('/var/log/application');
  }

  for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(size);
    for (const theme of ['light', 'dark'] as const) {
      await setAppearance(page, theme);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      const dialog = await openServerForm();
      await expect(dialog.getByRole('combobox', { name: 'Connection profile', exact: true })).toHaveValue('');
      await expect(dialog.getByLabel('SSH port', { exact: true })).toHaveValue('22');
      await fillNewServer(dialog, 'cancelled-server', 'Synthetic application host');
      await dialog.getByLabel('SSH host', { exact: true }).scrollIntoViewIfNeeded();
      await capture(page, `administrator-${theme}-${size.width}x${size.height}-server-ssh`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
      await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    }
  }
  const cancelled = await readTopology(page, id);
  expect(cancelled.revision).toBe(baseline.revision);
  expect(cancelled.config).toEqual(baseline.config);

  await page.setViewportSize({ width: 1280, height: 720 });
  const dialog = await openServerForm();
  await fillNewServer(dialog, 'ssh-server', 'Synthetic application host');
  const topologyWrites: string[] = [];
  page.on('request', request => {
    if (request.method() === 'PUT' && new URL(request.url()).pathname === `/api/v1/projects/${id}/topology`) topologyWrites.push(request.url());
  });
  for (const port of ['0', '65536', '22.5']) {
    await dialog.getByLabel('SSH port', { exact: true }).fill(port);
    await dialog.getByRole('button', { name: 'Save server', exact: true }).click();
    await expect(dialog).toBeVisible();
    expect(await dialog.getByLabel('SSH port', { exact: true }).evaluate((element: HTMLInputElement) => element.validity.valid)).toBe(false);
    expect((await readTopology(page, id)).revision).toBe(baseline.revision);
    expect(topologyWrites).toEqual([]);
  }
  await dialog.getByLabel('SSH port', { exact: true }).fill('2022');
  await dialog.getByRole('button', { name: 'Save server', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  const saved = await readTopology(page, id);
  expect(saved.revision).toBe(baseline.revision + 1);
  expect(topologyWrites).toHaveLength(1);
  expect(saved.config.connections).toHaveLength(1);
  expect(saved.config.servers).toHaveLength(1);
  const profile = saved.config.connections![0];
  expect(profile).toMatchObject({ name: 'Synthetic application host SSH', host: '192.0.2.44', port: 2022, username: 'logreader', credential_ref: 'unresolved-ssh-test', jump_connection_id: null, allowed_log_roots: ['/var/log/application'] });
  expect(saved.config.servers[0]).toMatchObject({ id: 'ssh-server', subsystem_id: 'ssh-subsystem', connection_id: profile.id });

  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Select server Synthetic application host', exact: true })).toHaveCount(0);
  const undone = await readTopology(page, id);
  expect(undone.revision).toBe(saved.revision + 1);
  expect(undone.config.connections).toEqual([]);
  expect(undone.config.servers).toEqual([]);
  await page.getByRole('button', { name: 'Redo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Select server Synthetic application host', exact: true })).toBeVisible();
  const redone = await readTopology(page, id);
  expect(redone.revision).toBe(undone.revision + 1);
  expect(redone.config.connections).toEqual(saved.config.connections);
  expect(redone.config.servers).toEqual(saved.config.servers);

  await page.reload();
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await page.getByRole('button', { name: 'Select server Synthetic application host', exact: true }).click();
  const details = page.locator('.process-details');
  await expect(details.getByText('SSH host', { exact: true })).toBeVisible();
  await expect(details.getByText('192.0.2.44', { exact: true })).toBeVisible();
  await expect(details.getByText('SSH port', { exact: true })).toBeVisible();
  await expect(details.getByText('2022', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Edit selected', exact: true }).click();
  const editServer = page.getByRole('dialog', { name: 'Edit server', exact: true });
  await expect(editServer.getByLabel('SSH host', { exact: true })).toHaveValue('192.0.2.44');
  await expect(editServer.getByLabel('SSH host', { exact: true })).not.toBeEditable();
  await expect(editServer.getByLabel('SSH port', { exact: true })).toHaveValue('2022');
  await expect(editServer.getByLabel('SSH port', { exact: true })).not.toBeEditable();
  await expect(editServer.getByRole('combobox', { name: 'Connection profile', exact: true }).locator('option:checked')).toContainText('192.0.2.44');
  await expect(editServer.getByRole('combobox', { name: 'Connection profile', exact: true }).locator('option:checked')).toContainText('2022');
  await editServer.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect((await readTopology(page, id)).revision).toBe(redone.revision);

  await details.getByRole('button', { name: 'Edit SSH connection', exact: true }).click();
  const editConnection = page.getByRole('dialog', { name: 'Edit connection', exact: true });
  await editConnection.getByLabel('SSH host', { exact: true }).fill('192.0.2.45');
  await editConnection.getByLabel('SSH port', { exact: true }).fill('2223');
  await editConnection.getByRole('button', { name: 'Save connection', exact: true }).click();
  await expect(editConnection).not.toBeVisible();
  const edited = await readTopology(page, id);
  expect(edited.config.connections).toHaveLength(1);
  expect(edited.config.connections![0]).toMatchObject({ ...profile, host: '192.0.2.45', port: 2223 });
  expect(edited.config.servers[0].connection_id).toBe(profile.id);
  await page.reload();
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await page.getByRole('button', { name: 'Select server Synthetic application host', exact: true }).click();
  await expect(details.getByText('192.0.2.45', { exact: true })).toBeVisible();
  await expect(details.getByText('2223', { exact: true })).toBeVisible();

  await createEntity(page, 'server', 'reused-ssh-server', 'Synthetic shared-profile host', async dialog => {
    await dialog.getByRole('combobox', { name: 'Connection profile', exact: true }).selectOption(profile.id);
    await expect(dialog.getByLabel('SSH host', { exact: true })).toHaveValue('192.0.2.45');
    await expect(dialog.getByLabel('SSH host', { exact: true })).not.toBeEditable();
    await expect(dialog.getByLabel('SSH port', { exact: true })).toHaveValue('2223');
    await expect(dialog.getByLabel('SSH port', { exact: true })).not.toBeEditable();
  });
  const reused = await readTopology(page, id);
  expect(reused.revision).toBe(edited.revision + 1);
  expect(reused.config.connections).toEqual(edited.config.connections);
  expect(reused.config.servers).toHaveLength(2);
  expect(reused.config.servers.every(server => server.connection_id === profile.id)).toBe(true);
});
