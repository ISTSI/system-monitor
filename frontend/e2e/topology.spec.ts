import { test, expect, type Page, type Locator } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Config, EntityKind, Topology } from '../src/topology';

const screenshots = resolve(`../verification/${process.env.INSPECTOR_E2E_REPORT_STAGE ?? 'stage-2'}/screenshots`);
type Role = 'administrator' | 'inspector';
const browserErrors = new WeakMap<Page, string[]>();
test.beforeEach(({ page }) => {
  const errors: string[] = [];
  browserErrors.set(page, errors);
  page.on('pageerror', error => errors.push(error.message));
});
test.afterEach(({ page }) => { expect(browserErrors.get(page)).toEqual([]); });

async function login(page: Page, role: Role) {
  const filename = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!filename) throw new Error('Protected synthetic-account fixture is required.');
  const accounts = JSON.parse(readFileSync(resolve(filename), 'utf8')) as Record<Role, { username: string; password: string }>;
  await page.goto('/');
  await page.getByLabel('Username', { exact: true }).fill(accounts[role].username);
  await page.getByLabel('Password', { exact: true }).fill(accounts[role].password);
  const result = page.waitForResponse(response => response.url().endsWith('/api/v1/auth/login') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  // Never retain a failed password form in browser artifacts.
  const response = await result;
  if (response.status() !== 200) {
    await page.locator('input[type="password"]').fill('');
    throw new Error(`Synthetic sign-in returned ${response.status()}; protected details withheld.`);
  }
  await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
}

async function createSystem(page: Page, name: string): Promise<string> {
  console.log('Creating a synthetic system through the catalogue form.');
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
  if (kind === 'connection' || kind === 'parser') await page.getByRole('button', { name: kind === 'connection' ? 'Connections' : 'Parsers', exact: true }).click();
  await page.getByRole('button', { name: `Add ${kind}`, exact: true }).click();
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

test('administrator builds and edits a complete graph, preserves identity and round-trips configuration', async ({ page }) => {
  test.setTimeout(180000);
  await login(page, 'administrator');
  const id = await createSystem(page, `Stage 02 editing ${Date.now()}`);
  await createEntity(page, 'subsystem', 'alpha', 'Gateway', async dialog => {
    await dialog.getByLabel('Documentation (Markdown)').fill('# Gateway\nShared **gateway** documentation.');
  });
  await createEntity(page, 'subsystem', 'beta', 'Processing');
  const beforeDuplicate = (await readTopology(page, id)).revision;
  await page.getByRole('button', { name: 'Add subsystem', exact: true }).click();
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
  await page.getByLabel('Search this system', { exact: true }).fill('pcs-ingest');
  await page.getByRole('button', { name: /Renamed ingress.*process|process.*Renamed ingress/i }).click();
  await expect(page.getByRole('button', { name: 'Select process Renamed ingress', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Expand Processing', exact: true })).toHaveCount(0);
  await page.getByLabel('Search this system', { exact: true }).fill('');
  const pendingDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export JSON', exact: true }).click();
  const download = await pendingDownload;
  const downloaded = JSON.parse(readFileSync((await download.path())!, 'utf8')) as Config;
  expect(downloaded.project.id).toBe(id);
  expect(downloaded.processes.map(process => process.id).sort()).toEqual(['ingest', 'worker']);
  expect(JSON.stringify(downloaded)).not.toContain('password');
  downloaded.processes[0].description = 'Externally edited **documentation**.';
  downloaded.views[0].nodes[0].x += 25;
  const revisionBefore = (await readTopology(page, id)).revision;
  await page.getByRole('button', { name: 'Import configuration', exact: true }).click();
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
  await duplicate.getByRole('button', { name: 'Edit system details', exact: true }).click();
  await duplicate.getByRole('textbox', { name: 'Description', exact: true }).fill('Stale draft from independent page');
  await page.getByRole('button', { name: 'Edit system details', exact: true }).click();
  await page.getByRole('textbox', { name: 'Description', exact: true }).fill('New shared revision from page A');
  await page.getByRole('button', { name: 'Save system details', exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await duplicate.getByRole('button', { name: 'Save system details', exact: true }).click();
  await expect(duplicate.getByRole('alert')).toContainText(/changed|reload/i);
  await expect(duplicate.getByRole('textbox', { name: 'Description', exact: true })).toHaveValue('Stale draft from independent page');
  await duplicate.getByRole('button', { name: 'Cancel', exact: true }).click();
  await duplicate.getByLabel('System selector').selectOption('demo-foundation-b');
  await expect(duplicate).toHaveURL(/demo-foundation-b\/topology$/);
  await expect(page.getByLabel('System selector')).toHaveValue('demo-foundation-a');
  await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
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
  const select = page.getByRole('button', { name: /^Select process / }).first();
  await select.focus();
  await page.keyboard.press('Enter');
  await expect(select).toHaveAttribute('aria-pressed', 'true');
  for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(size);
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('Appearance', { exact: true }).selectOption(theme);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await expect(select).toHaveAttribute('aria-pressed', 'true');
      await capture(page, `inspector-${theme}-${size.width}x${size.height}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
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
  await expect(handle).toBeInViewport({ ratio: 1 });
  const box = await handle.boundingBox();
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
