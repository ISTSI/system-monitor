import { expect, test, type BrowserContext, type Locator, type Page } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { serveBuiltAssets, setAppearance, submitSignIn, systemAction } from './ui';
import type { InventoryParsed, InventoryPreview } from '../src/inventory';
import type { Topology } from '../src/topology';

const enabled = process.env.INSPECTOR_E2E_URL === 'https://localhost:8449';
const root = resolve('..');
const fixture = enabled ? JSON.parse(readFileSync(resolve(root, '.state/stage7-browser/public-fixture.json'), 'utf8')) as { synthetic: boolean; host: string; projects: string[] } : null;
if (enabled && (!fixture?.synthetic || fixture.host !== 'stage7-sftp' || fixture.projects.join(',') !== 'stage7-fixture-a,stage7-fixture-b')) throw new Error('Only the isolated generated Stage 07 fixture is authorized.');
const errors = new WeakMap<BrowserContext, string[]>(); const external = new WeakMap<BrowserContext, string[]>();
test.skip(!enabled, 'Requires the generated Stage 07 MariaDB fixture at https://localhost:8449.');
test.beforeEach(async ({ page, context, baseURL }) => {
  const failures: string[] = []; errors.set(context, failures); page.on('pageerror', error => failures.push(error.message)); context.on('page', current => current.on('pageerror', error => failures.push(error.message)));
  const requests: string[] = []; external.set(context, requests); const origin = new URL(baseURL!).origin;
  await context.grantPermissions(['local-network-access'], { origin });
  await context.route('**/*', route => { const url = new URL(route.request().url()); if (url.origin === origin) return route.fallback(); requests.push(url.origin); return route.abort(); });
  if (process.env.INSPECTOR_E2E_LOCAL_ASSETS === '1') await serveBuiltAssets(context, baseURL!);
});
test.afterEach(async ({ page, context, baseURL }) => {
  try { expect(errors.get(context)).toEqual([]); expect(external.get(context)).toEqual([]); }
  finally { if ((await page.request.get('/api/v1/auth/session')).status() === 200) { const headers = await mutationHeaders(page, baseURL!); expect((await page.request.post('/api/v1/auth/logout', { headers, data: {} })).status()).toBe(200); } }
});
async function mutationHeaders(page: Page, baseURL: string) { const { csrf_token } = await (await page.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string }; return { Origin: new URL(baseURL).origin, 'X-CSRF-Token': csrf_token }; }
async function login(page: Page, role: 'administrator' | 'inspector') {
  if (!process.env.INSPECTOR_E2E_ACCOUNTS) throw new Error('Protected Stage 07 synthetic account fixture is required.');
  const account = (JSON.parse(readFileSync(resolve(process.env.INSPECTOR_E2E_ACCOUNTS), 'utf8')) as Record<string, { username: string; password: string }>)[role];
  await page.goto('/'); await page.getByLabel('Username', { exact: true }).fill(account.username);
  try { await page.getByLabel('Password', { exact: true }).fill(account.password); if ((await submitSignIn(page)).status() !== 200) throw new Error(); }
  catch { await page.locator('input[type="password"]').fill('').catch(() => {}); throw new Error('Synthetic sign-in failed; protected values withheld.'); }
  await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
}
async function newSystem(page: Page, baseURL: string, name: string) {
  const headers = await mutationHeaders(page, baseURL); const response = await page.request.post('/api/v1/projects', { headers, data: { name: `Inventory ${name} ${crypto.randomUUID().slice(0, 8)}`, description: 'Synthetic Stage 07 browser inventory acceptance.' } }); expect(response.status()).toBe(201);
  const { project_id } = await response.json() as { project_id: string };
  const topology = await readTopology(page, project_id); topology.config.parsers = [{ id: 'parser-iso-utc', name: 'UTC prefix', timestamp: { kind: 'iso8601_prefix', naive_timezone: 'UTC' }, correlation_markers: [] }];
  const saved = await page.request.put(`/api/v1/projects/${project_id}/topology`, { headers, data: { expected_revision: topology.revision, config: topology.config } }); expect(saved.status()).toBe(200);
  await page.goto(`/systems/${project_id}/topology`); await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/); return project_id;
}
async function readTopology(page: Page, id: string): Promise<Topology> { const response = await page.request.get(`/api/v1/projects/${id}/topology`); expect(response.status()).toBe(200); return await response.json() as Topology; }
async function openWizard(page: Page) { await systemAction(page, 'Import Ansible inventory files'); const dialog = page.getByRole('dialog', { name: 'Import Ansible inventory files', exact: true }); await expect(dialog.getByLabel('Existing inventory source', { exact: true })).toBeEnabled(); return dialog; }
async function source(dialog: Locator, existing?: string) {
  if (existing) { await dialog.getByLabel('Existing inventory source', { exact: true }).selectOption(existing); await dialog.getByRole('button', { name: 'Continue to upload', exact: true }).click(); }
  else { await dialog.getByLabel('New inventory source name', { exact: true }).fill('Browser static inventory'); await dialog.getByRole('button', { name: 'Create inventory source', exact: true }).click(); }
  await expect(dialog.getByLabel('Inventory file or ZIP', { exact: true })).toBeVisible(); return await dialog.getByTestId('inventory-source-id').innerText();
}
async function upload(page: Page, dialog: Locator, name: string, content?: string) {
  await dialog.getByLabel('Inventory file or ZIP', { exact: true }).setInputFiles(content === undefined ? resolve(root, 'examples/ansible', name) : { name, mimeType: 'text/plain', buffer: Buffer.from(content) });
  const pending = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/inventory/uploads') && response.request().method() === 'POST');
  await dialog.getByRole('button', { name: 'Upload and inspect files', exact: true }).click(); expect((await pending).status()).toBe(200); await expect(dialog.getByRole('group', { name: 'Choose static source files in read order' })).toBeVisible();
}
async function parse(page: Page, dialog: Locator) {
  const pending = page.waitForResponse(response => response.url().endsWith('/inventory/parse')).then(async response => { await response.finished(); return { status: response.status(), body: await response.json() as InventoryParsed }; }); await dialog.getByRole('button', { name: 'Parse selected sources', exact: true }).click(); const result = await pending; expect(result.status).toBe(200); return result.body;
}
async function mapGroups(dialog: Locator) { for (const group of ['ingress', 'core', 'delivery']) await dialog.getByLabel(`Subsystem for group ${group}`, { exact: true }).fill(`s-${group}`); }
async function preview(page: Page, dialog: Locator) { const pending = page.waitForResponse(response => response.url().endsWith('/inventory/preview')).then(async response => { await response.finished(); return { status: response.status(), body: await response.json() as InventoryPreview }; }); await dialog.getByRole('button', { name: 'Preview exact changes', exact: true }).click(); const result = await pending; expect(result.status).toBe(200); return result.body; }
async function commit(page: Page, dialog: Locator) { await dialog.getByRole('checkbox', { name: /^I reviewed these exact changes for / }).check(); const pending = page.waitForResponse(response => response.url().endsWith('/inventory/commit')); await dialog.getByRole('button', { name: 'Commit reviewed inventory', exact: true }).click(); expect((await pending).status()).toBe(200); await expect(dialog).not.toBeVisible(); }
async function screenshot(page: Page, name: string) { const directory = resolve(root, 'verification/stage-7/screenshots'); mkdirSync(directory, { recursive: true }); await page.screenshot({ path: resolve(directory, `${name}.png`), fullPage: false, animations: 'disabled' }); }
async function matrixScreenshot(page: Page, name: string) {
  for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) { await page.setViewportSize(size); for (const theme of ['light', 'dark'] as const) { await setAppearance(page, theme); expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true); await screenshot(page, `${name}-${theme}-${size.width}x${size.height}`); } }
}

for (const [filename, count] of [['inventory.hosts.ini', 0], ['hosts', 0], ['inventory.static.yaml', 5], ['inventory.canonical.json', 5], ['inventory-with-vars.zip', 5]] as const) test(`Administrator directly imports ${filename} with exact host mapping and stable same-source reimport`, async ({ page, baseURL }) => {
  test.setTimeout(120000); await login(page, 'administrator'); const projectId = await newSystem(page, baseURL!, filename); const dialog = await openWizard(page); if (filename === 'inventory.static.yaml') await matrixScreenshot(page, 'inventory-source-identity'); const sourceId = await source(dialog);
  await upload(page, dialog, filename); await expect(dialog.getByLabel('Inventory import target', { exact: true })).toContainText(projectId); await expect(dialog.getByTestId('inventory-source-id')).toHaveText(sourceId);
  if (filename === 'inventory.static.yaml' || filename.endsWith('.zip')) await matrixScreenshot(page, filename.endsWith('.zip') ? 'inventory-zip-manifest' : 'inventory-direct-upload');
  if (filename.endsWith('.zip')) { await expect(dialog.getByRole('group', { name: 'Choose static source files in read order' })).toContainText('group_vars/all.yaml'); }
  const parsed = await parse(page, dialog); expect(parsed.hosts.map(host => host.alias)).toEqual(['demo-core-01', 'demo-delivery-01', 'demo-ingest-01']); expect(parsed.process_count).toBe(count);
  expect(parsed.hosts.map(host => host.address)).toEqual(['192.0.2.21', '192.0.2.22', '192.0.2.20']);
  await mapGroups(dialog); if (filename === 'inventory.static.yaml') await matrixScreenshot(page, 'inventory-group-host-parser-mapping'); const proposed = await preview(page, dialog); expect(proposed.can_commit).toBe(true); expect(proposed.records.filter(record => record.kind === 'host' && record.status === 'added')).toHaveLength(3); expect(proposed.records.filter(record => record.kind === 'process')).toHaveLength(count);
  await expect(dialog.getByRole('button', { name: 'Commit reviewed inventory', exact: true })).toBeDisabled();
  if (filename === 'inventory.static.yaml') await matrixScreenshot(page, 'inventory-preview');
  await commit(page, dialog); const first = await readTopology(page, projectId); expect(first.config.servers).toHaveLength(3); expect(first.config.processes).toHaveLength(count); const ids = first.config.servers.map(server => server.id);
  expect(first.config.servers.map(server => server.subsystem_id).sort()).toEqual(['s-core', 's-delivery', 's-ingress']);
  const repeated = await openWizard(page); await source(repeated, sourceId); await upload(page, repeated, filename); await parse(page, repeated); await mapGroups(repeated); const again = await preview(page, repeated); expect(again.can_commit).toBe(true); expect(again.records.every(record => record.status === 'unchanged')).toBe(true); await commit(page, repeated); const after = await readTopology(page, projectId); expect(after.config.servers.map(server => server.id)).toEqual(ids); expect(after.config.processes.map(process => process.id)).toEqual(first.config.processes.map(process => process.id));
});

test('Wizard omits secrets, blocks conflicting subsystem memberships, preserves manual fields and invalidates stale revisions', async ({ page, baseURL }) => {
  test.setTimeout(120000); await login(page, 'administrator'); const projectId = await newSystem(page, baseURL!, 'conflicts'); const dialog = await openWizard(page); const sourceId = await source(dialog);
  const hosts = JSON.stringify({ _meta: { hostvars: { shared: { ansible_host: '192.0.2.30', ansible_user: 'reader', ansible_password: 'synthetic-password-omit', inspector_processes: [{ id: 'managed-process', name: 'Imported process', pcs_resource_name: null, log_source: { active_path: '/var/log/manual/app.log', rotated_patterns: [], archives: [], parser_id: 'parser-iso-utc', encoding: 'utf-8', allow_symlink: false } }] } } }, east: { hosts: ['shared'] }, west: { hosts: ['shared'] } });
  await upload(page, dialog, 'hosts.json', hosts); const parsed = await parse(page, dialog); expect(parsed.process_count).toBe(1); expect(parsed.omitted_variables.some(item => item.name === 'ansible_password')).toBe(true); expect(JSON.stringify(parsed)).not.toContain('synthetic-password-omit'); await expect(dialog).not.toContainText('synthetic-password-omit');
  await dialog.getByLabel('Subsystem for group east', { exact: true }).fill('east-subsystem'); await dialog.getByLabel('Subsystem for group west', { exact: true }).fill('west-subsystem'); const conflict = await preview(page, dialog); expect(conflict.can_commit).toBe(false); await expect(dialog.getByRole('button', { name: 'Commit reviewed inventory', exact: true })).toBeDisabled(); await matrixScreenshot(page, 'inventory-conflicting-memberships');
  await dialog.getByRole('button', { name: 'Back', exact: true }).click(); await dialog.getByLabel('Subsystem for host shared', { exact: true }).fill('east-subsystem'); expect((await preview(page, dialog)).can_commit).toBe(true); await commit(page, dialog);
  const current = await readTopology(page, projectId); current.config.servers[0].description = 'Manual documentation survives inventory reimport.'; current.config.processes.push({ id: 'manual-process', server_id: current.config.servers[0].id, name: 'Manual process', description: 'Manual process survives', tags: [], pcs_resource_name: null, log_source: { active_path: '/var/log/manual/manual.log', rotated_patterns: [], archives: [], parser_id: 'parser-iso-utc', encoding: 'utf-8', allow_symlink: false } });
  const headers = await mutationHeaders(page, baseURL!); const manual = await page.request.put(`/api/v1/projects/${projectId}/topology`, { headers, data: { expected_revision: current.revision, config: current.config } }); expect(manual.status(), JSON.stringify(await manual.json())).toBe(200);
  await page.reload(); await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/); const repeated = await openWizard(page); await source(repeated, sourceId); await upload(page, repeated, 'renamed.json', hosts); await parse(page, repeated); await repeated.getByLabel('Subsystem for host shared', { exact: true }).fill('east-subsystem'); const stored = await preview(page, repeated); expect(stored.can_commit).toBe(true); expect(stored.records.every(record => record.status === 'unchanged')).toBe(true);
  const beforeStale = await readTopology(page, projectId); expect((await page.request.patch(`/api/v1/projects/${projectId}/metadata`, { headers, data: { name: beforeStale.config.project.name, description: 'Synthetic revision bump', expected_revision: beforeStale.revision } })).status()).toBe(200);
  await repeated.getByRole('checkbox', { name: /^I reviewed these exact changes for / }).check(); const stale = page.waitForResponse(response => response.url().endsWith('/inventory/commit')); await repeated.getByRole('button', { name: 'Commit reviewed inventory', exact: true }).click(); expect((await stale).status()).toBe(409); await expect(repeated.getByRole('alert')).toBeVisible();
  const after = await readTopology(page, projectId); expect(after.config.servers[0].description).toBe(current.config.servers[0].description); expect(after.config.processes.find(process => process.id === 'manual-process')?.description).toBe('Manual process survives'); await repeated.getByRole('button', { name: 'Cancel inventory import', exact: true }).click();
  await page.reload(); await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/); const fresh = await openWizard(page); await source(fresh, sourceId); await upload(page, fresh, 'renamed-again.json', hosts); await parse(page, fresh); await fresh.getByLabel('Subsystem for host shared', { exact: true }).fill('east-subsystem'); expect((await preview(page, fresh)).can_commit).toBe(true); await commit(page, fresh); const preserved = await readTopology(page, projectId); expect(preserved.config.servers[0].description).toBe(current.config.servers[0].description); expect(preserved.config.processes.find(process => process.id === 'manual-process')?.description).toBe('Manual process survives');
});

test('Static unsupported YAML is rejected without rendering uploaded contents or executing plugins', async ({ page, baseURL }) => {
  await login(page, 'administrator'); await newSystem(page, baseURL!, 'unsupported'); const dialog = await openWizard(page); await source(dialog); await upload(page, dialog, 'inventory.yaml', 'plugin: synthetic-do-not-execute\nsecret_token: synthetic-unsupported-value\n');
  const pending = page.waitForResponse(response => response.url().endsWith('/inventory/parse')); await dialog.getByRole('button', { name: 'Parse selected sources', exact: true }).click(); expect((await pending).status()).toBe(422); await expect(dialog.getByRole('alert')).toBeVisible(); await expect(dialog).not.toContainText('synthetic-unsupported-value'); await expect(dialog.getByRole('button', { name: 'Commit reviewed inventory', exact: true })).toHaveCount(0); await matrixScreenshot(page, 'inventory-unsupported-static-error');
});

test('ZIP source selection preserves explicit read order and names ignored executable extras', async ({ page, baseURL }) => {
  await login(page, 'administrator'); const projectId = await newSystem(page, baseURL!, 'source order'); const dialog = await openWizard(page); await source(dialog);
  await dialog.getByLabel('Inventory file or ZIP', { exact: true }).setInputFiles(resolve(root, 'fixtures/inventory/browser-source-order.zip'));
  const uploaded = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/inventory/uploads'));
  await dialog.getByRole('button', { name: 'Upload and inspect files', exact: true }).click(); expect((await uploaded).status()).toBe(200);
  const manifest = dialog.getByRole('group', { name: 'Choose static source files in read order' }); await expect(manifest).toContainText('roles/ignored.py');
  await expect(dialog.getByRole('button', { name: 'Parse selected sources', exact: true })).toBeDisabled();
  await manifest.getByRole('checkbox', { name: /^first.ini / }).check(); await manifest.getByRole('checkbox', { name: /^second.ini / }).check();
  await dialog.getByRole('button', { name: 'Read second.ini earlier', exact: true }).click(); const result = await parse(page, dialog); expect(result.provenance.source_files).toEqual(['second.ini', 'first.ini']); expect(result.provenance.ignored_files).toEqual(['roles/ignored.py']);
  await dialog.getByLabel('Subsystem for group app', { exact: true }).fill('subsystem-app'); expect((await preview(page, dialog)).can_commit).toBe(true); await commit(page, dialog); expect((await readTopology(page, projectId)).config.servers.map(server => server.name).sort()).toEqual(['first-host', 'second-host']);
});

test('Creating a new inventory source after Back clears the old upload and commits only fresh source data', async ({ page, baseURL }) => {
  await login(page, 'administrator'); const projectId = await newSystem(page, baseURL!, 'replacement source'); const dialog = await openWizard(page); const sourceA = await source(dialog);
  await upload(page, dialog, 'hosts', '[app]\nfirst-source-host ansible_host=192.0.2.91 ansible_user=reader\n'); await parse(page, dialog); await dialog.getByLabel('Subsystem for group app', { exact: true }).fill('first-subsystem'); const previous = await preview(page, dialog); expect(previous.can_commit).toBe(true);
  await dialog.getByRole('button', { name: 'Back', exact: true }).click(); await dialog.getByRole('button', { name: 'Back', exact: true }).click(); await dialog.getByRole('button', { name: 'Back', exact: true }).click();
  await expect(dialog.getByLabel('Existing inventory source', { exact: true })).toHaveValue(sourceA);
  await dialog.getByLabel('New inventory source name', { exact: true }).fill('Replacement static inventory'); await dialog.getByRole('button', { name: 'Create inventory source', exact: true }).click();
  await expect(dialog.getByLabel('Inventory file or ZIP', { exact: true })).toBeVisible(); const sourceB = await dialog.getByTestId('inventory-source-id').innerText(); expect(sourceB).not.toBe(sourceA);
  await expect(dialog.getByLabel('Inventory import target', { exact: true })).toContainText('Replacement static inventory'); await expect(dialog.getByRole('group', { name: 'Choose static source files in read order' })).toHaveCount(0);
  await expect(dialog.getByRole('button', { name: 'Parse selected sources', exact: true })).toBeDisabled(); await expect(dialog.getByRole('button', { name: 'Upload and inspect files', exact: true })).toBeDisabled();
  await upload(page, dialog, 'hosts', '[app]\nsecond-source-host ansible_host=192.0.2.92 ansible_user=reader\n');
  const headers = await mutationHeaders(page, baseURL!); expect((await page.request.post(`/api/v1/projects/${projectId}/inventory/commit`, { headers, data: { preview_id: previous.preview_id, expected_revision: previous.expected_revision } })).status()).toBe(404);
  const parsed = await parse(page, dialog); expect(parsed.inventory_source_id).toBe(sourceB); expect(parsed.hosts.map(host => host.alias)).toEqual(['second-source-host']);
  await dialog.getByLabel('Subsystem for group app', { exact: true }).fill('second-subsystem'); const proposed = await preview(page, dialog); expect(proposed.inventory_source_id).toBe(sourceB); expect(proposed.can_commit).toBe(true); await commit(page, dialog);
  const saved = await readTopology(page, projectId); expect(saved.config.servers.map(server => [server.name, server.subsystem_id])).toEqual([['second-source-host', 'second-subsystem']]); expect(saved.config.processes).toHaveLength(0);
});

for (const stage of ['parse', 'preview'] as const) test(`Cancelling a pending inventory ${stage} discards staging and ignores its late real response`, async ({ page, baseURL }) => {
  test.setTimeout(120000);
  const projectId = await (async () => { await login(page, 'administrator'); return newSystem(page, baseURL!, `cancel ${stage}`); })();
  const dialog = await openWizard(page); const sourceId = await source(dialog); await upload(page, dialog, 'hosts', '[app]\ncancelled-host ansible_host=192.0.2.93 ansible_user=reader\n');
  if (stage === 'preview') { await parse(page, dialog); await dialog.getByLabel('Subsystem for group app', { exact: true }).fill('cancelled-subsystem'); }
  let release!: () => void; let started = false; let browserAborted = false;
  const held = new Promise<void>(resolve => { release = resolve; });
  let observed!: (value: { request: { inventory_source_id: string; upload_id: string; expected_revision: number; format: string; source_files: string[] }; previewId?: string }) => void;
  let rejectObserved!: (error: unknown) => void; let finished!: () => void;
  const realResponse = new Promise<{ request: { inventory_source_id: string; upload_id: string; expected_revision: number; format: string; source_files: string[] }; previewId?: string }>((resolve, reject) => { observed = resolve; rejectObserved = reject; });
  const completed = new Promise<void>(resolve => { finished = resolve; });
  const routePattern = `**/api/v1/projects/${projectId}/inventory/${stage}`;
  await page.route(routePattern, async route => {
    started = true;
    try {
      const response = await route.fetch(); expect(response.status()).toBe(200);
      const body = await response.json() as { preview_id?: string };
      const { inventory_source_id, upload_id, expected_revision, format, source_files } = route.request().postDataJSON() as { inventory_source_id: string; upload_id: string; expected_revision: number; format: string; source_files: string[] };
      observed({ request: { inventory_source_id, upload_id, expected_revision, format, source_files }, previewId: body.preview_id });
      await held;
      // The response came from the real parser/MariaDB service. Cancellation
      // may abort its browser request before this unchanged response is released.
      await route.fulfill({ response }).catch(error => { if (!browserAborted) throw error; });
    } catch (error) { rejectObserved(error); throw error; } finally { finished(); }
  });
  try {
    await dialog.getByRole('button', { name: stage === 'parse' ? 'Parse selected sources' : 'Preview exact changes', exact: true }).click();
    const pending = await realResponse;
    await expect(dialog.getByRole('status')).toContainText(stage === 'parse' ? 'Parsing static inventory' : 'Preparing exact changes');
    await expect(dialog.getByRole('button', { name: 'Cancel inventory import', exact: true })).toBeEnabled();
    const cancelled = page.waitForResponse(response => response.url().endsWith(`/inventory/uploads/${pending.request.upload_id}/cancel`));
    const aborted = page.waitForEvent('requestfailed', request => request.method() === 'POST' && request.url().endsWith(`/inventory/${stage}`));
    if (stage === 'parse') await dialog.getByRole('button', { name: 'Cancel inventory import', exact: true }).click(); else await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible(); expect((await cancelled).status()).toBe(200);
    expect((await aborted).failure()?.errorText).toMatch(/aborted|cancelled/i); browserAborted = true;
    release(); await completed; await page.unroute(routePattern);
    const headers = await mutationHeaders(page, baseURL!);
    expect((await page.request.post(`/api/v1/projects/${projectId}/inventory/parse`, { headers, data: pending.request })).status()).toBe(404);
    if (pending.previewId) expect((await page.request.post(`/api/v1/projects/${projectId}/inventory/commit`, { headers, data: { preview_id: pending.previewId, expected_revision: pending.request.expected_revision } })).status()).toBe(404);
    expect((await readTopology(page, projectId)).config.servers).toHaveLength(0);
    const fresh = await openWizard(page); await expect(fresh.getByLabel('Existing inventory source', { exact: true })).toHaveValue(''); await source(fresh, sourceId);
    await expect(fresh.getByRole('group', { name: 'Choose static source files in read order' })).toHaveCount(0);
    await upload(page, fresh, 'hosts', '[app]\nfresh-host ansible_host=192.0.2.94 ansible_user=reader\n'); const result = await parse(page, fresh); expect(result.hosts.map(host => host.alias)).toEqual(['fresh-host']);
    await fresh.getByLabel('Subsystem for group app', { exact: true }).fill('fresh-subsystem'); expect((await preview(page, fresh)).can_commit).toBe(true); await commit(page, fresh);
    expect((await readTopology(page, projectId)).config.servers.map(server => server.name)).toEqual(['fresh-host']);
  } finally { release(); if (started) await completed; await page.unroute(routePattern); }
});

test('Same-account pages keep separate project previews and reject cross-project commit', async ({ page, context, baseURL }) => {
  test.setTimeout(120000); await login(page, 'administrator'); const projectA = await newSystem(page, baseURL!, 'window A'); const dialogA = await openWizard(page); await source(dialogA); await upload(page, dialogA, 'hosts', '[app]\nsame-alias ansible_host=192.0.2.60\n'); await parse(page, dialogA); await dialogA.getByLabel('Subsystem for group app', { exact: true }).fill('subsystem-app'); const previewA = await preview(page, dialogA);
  const second = await context.newPage(); try { await second.goto('/'); const projectB = await newSystem(second, baseURL!, 'window B'); const dialogB = await openWizard(second); await source(dialogB); await upload(second, dialogB, 'hosts', '[app]\nsame-alias ansible_host=192.0.2.60\n'); await parse(second, dialogB); await dialogB.getByLabel('Subsystem for group app', { exact: true }).fill('subsystem-app'); const previewB = await preview(second, dialogB);
    expect(previewA.project_id).toBe(projectA); expect(previewB.project_id).toBe(projectB); expect(previewA.preview_id).not.toBe(previewB.preview_id); expect(await second.title()).not.toBe(await page.title());
    const headers = await mutationHeaders(page, baseURL!); expect((await page.request.post(`/api/v1/projects/${projectB}/inventory/commit`, { headers, data: { preview_id: previewA.preview_id, expected_revision: previewA.expected_revision } })).status()).toBe(404);
    await setAppearance(page, 'dark'); await screenshot(page, 'inventory-two-system-window-a-dark'); await screenshot(second, 'inventory-two-system-window-b-dark'); await setAppearance(page, 'light'); await screenshot(page, 'inventory-two-system-window-a-light'); await screenshot(second, 'inventory-two-system-window-b-light');
    await commit(page, dialogA); await expect(dialogB.getByTestId('inventory-preview-id')).toHaveText(previewB.preview_id); await commit(second, dialogB); expect((await readTopology(page, projectA)).config.servers).toHaveLength(1); expect((await readTopology(second, projectB)).config.servers).toHaveLength(1);
  } finally { await second.close(); }
});

test('Inspector cannot open inventory tools or forge any inventory endpoint', async ({ page, baseURL }) => {
  await login(page, 'inspector'); const projectId = fixture!.projects[0]; await page.goto(`/systems/${projectId}/topology`); await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/); await expect(page.getByRole('button', { name: 'System', exact: true })).toHaveCount(0); await expect(page.getByRole('button', { name: 'Import Ansible inventory files', exact: true })).toHaveCount(0);
  const base = `/api/v1/projects/${projectId}/inventory`; const headers = await mutationHeaders(page, baseURL!); expect((await page.request.get(`${base}/sources`)).status()).toBe(403);
  for (const [path, data] of [['sources', { name: 'Forbidden' }], ['parse', { inventory_source_id: 'missing', upload_id: 'missing', expected_revision: 1, format: 'ini', source_files: ['hosts'] }], ['preview', { project_id: projectId, inventory_source_id: 'missing', upload_id: 'missing', expected_revision: 1, format: 'ini', source_files: ['hosts'], mapping: { group_to_subsystem: {}, host_to_subsystem: {}, tag_only_groups: [], credential_mapping: {}, jump_mapping: {}, parser_mapping: {}, preserve_existing_documentation: true, preserve_existing_layout: true, delete_missing_hosts: false } }], ['commit', { preview_id: 'missing', expected_revision: 1 }], ['uploads/missing/cancel', {}], ['previews/missing/cancel', {}]] as const) expect((await page.request.post(`${base}/${path}`, { headers, data })).status()).toBe(403);
  expect((await page.request.post(`${base}/uploads?inventory_source_id=missing&expected_revision=1`, { headers: { ...headers, 'Content-Type': 'application/octet-stream', 'X-Inventory-Filename': 'hosts' }, data: Buffer.from('[app]\nhost\n') })).status()).toBe(403);
});
