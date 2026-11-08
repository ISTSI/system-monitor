import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { applyHistoricalFilters, fillHistoricalFilters, openPreferences, setHistoricalCollectionRange, submitSignIn, systemAction } from './ui';
import type { Topology } from '../src/topology';
import type { Preferences } from '../src/api/types';
import type { components } from '../src/api/schema';
import type { LiveSession } from '../src/live';
import type { InventoryParsed } from '../src/inventory';

type Fixture = { synthetic: true; origin: string; accounts_file: string; project_ids: [string, string]; from: string; to: string; phase?: 'source' | 'restored' };
type HistoricalQueryResponse = components['schemas']['HistoricalQueryResponse'];
const fixtureFile = process.env.INSPECTOR_STAGE8_FIXTURE;
const fixture = fixtureFile ? JSON.parse(readFileSync(resolve(fixtureFile), 'utf8')) as Fixture : null;
if (fixture && (fixture.synthetic !== true || fixture.origin !== 'https://localhost:8460' || fixture.project_ids.join(',') !== 'stage8-fixture-a,stage8-fixture-b' || !fixture.accounts_file || !fixture.from || !fixture.to)) throw new Error('Stage 08 browser tests require the explicitly generated loopback synthetic release fixture.');
test.skip(!fixture, 'Set INSPECTOR_STAGE8_FIXTURE to the generated isolated Stage 08 qualification manifest.');
const errors = new WeakMap<BrowserContext, string[]>();
const outbound = new WeakMap<BrowserContext, string[]>();
const report = resolve('../verification/stage-8/screenshots');

async function headers(page: Page) {
  const response = await page.request.get('/api/v1/auth/csrf'); expect(response.status()).toBe(200);
  return { Origin: fixture!.origin, 'X-CSRF-Token': (await response.json() as { csrf_token: string }).csrf_token };
}
async function login(page: Page, role: 'administrator' | 'inspector') {
  const credentials = (JSON.parse(readFileSync(resolve(fixture!.accounts_file), 'utf8')) as Record<string, { username: string; password: string }>)[role];
  await page.goto('/');
  await page.getByLabel('Username', { exact: true }).fill(credentials.username);
  try {
    await page.getByLabel('Password', { exact: true }).fill(credentials.password);
    if ((await submitSignIn(page)).status() !== 200) throw new Error();
  } catch { await page.locator('input[type="password"]').fill('').catch(() => {}); throw new Error('Synthetic release sign-in failed; protected details withheld.'); }
  await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
}
async function open(page: Page, project: string, section = 'topology') {
  await page.goto(`/systems/${project}/${section}`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  return page.getByTestId('workspace-id').innerText();
}
async function screenshot(page: Page, name: string) { mkdirSync(report, { recursive: true }); const phase = process.env.INSPECTOR_E2E_REPORT_NAME === 'browser-cold' ? 'cold' : fixture!.phase ?? 'source'; await page.screenshot({ path: resolve(report, `${phase}-${name}.png`), animations: 'disabled' }); }

test.beforeEach(async ({ page, context, baseURL }) => {
  if (!fixture) return;
  if (baseURL !== fixture.origin || process.env.INSPECTOR_E2E_LOCAL_ASSETS === '1') throw new Error('Qualification must exercise the actual release HTTPS frontend, backend and proxy.');
  const found: string[] = []; errors.set(context, found);
  const blocked: string[] = []; outbound.set(context, blocked);
  page.on('pageerror', error => found.push(error.message));
  context.on('page', current => current.on('pageerror', error => found.push(error.message)));
  await context.grantPermissions(['local-network-access'], { origin: fixture.origin });
  await context.route('**/*', route => {
    const origin = new URL(route.request().url()).origin;
    if (origin === fixture.origin) return route.fallback();
    blocked.push(origin); return route.abort();
  });
});
test.afterEach(async ({ page, context }) => {
  if (!fixture) return;
  try { expect(errors.get(context)).toEqual([]); expect(outbound.get(context)).toEqual([]); }
  finally { if ((await page.request.get('/api/v1/auth/session')).status() === 200) expect((await page.request.post('/api/v1/auth/logout', { headers: await headers(page), data: {} })).status()).toBe(200); }
});

for (const role of ['administrator', 'inspector'] as const) test(`${role}: release login, independent System pages, Help, EN/PL and retained investigations`, async ({ page, context }) => {
  test.setTimeout(120000); await login(page, role);
  await expect(page.getByRole('button', { name: 'Settings', exact: true })).toHaveCount(role === 'administrator' ? 1 : 0);
  if (role === 'inspector') expect((await page.request.get('/api/v1/admin/settings')).status()).toBe(403);
  const first = await open(page, fixture!.project_ids[0]);
  const second = await context.newPage(); const secondId = await open(second, fixture!.project_ids[1]);
  const duplicate = await context.newPage(); const duplicateId = await open(duplicate, fixture!.project_ids[0]);
  expect(new Set([first, secondId, duplicateId]).size).toBe(3);
  await page.locator('.explorer-search input').fill('window-A-draft');
  await second.locator('.explorer-search input').fill('window-B-draft');
  await duplicate.locator('.explorer-search input').fill('same-system-draft');
  const original = await (await page.request.get('/api/v1/me/preferences')).json() as Preferences;
  expect(original.theme_mode).toBe(role === 'administrator' ? 'dark' : 'light');
  expect(original.language).toBe('en');
  await expect(page.locator('html')).toHaveAttribute('data-theme', role === 'administrator' ? 'dark' : 'light');
  try {
    await page.bringToFront();
    const preferenceDialog = await openPreferences(page);
    const changed = page.waitForResponse(response => response.url().endsWith('/me/preferences') && response.request().method() === 'PATCH');
    await preferenceDialog.getByLabel('Language', { exact: true }).selectOption('pl'); expect((await changed).status()).toBe(200);
    await expect(second.locator('html')).toHaveAttribute('lang', 'pl');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog', { name: 'Preferencje', exact: true })).toHaveCount(0);
    const trigger = page.getByRole('button', { name: 'Pomoc', exact: true });
    await page.bringToFront(); await trigger.focus(); await trigger.press('Enter');
    const help = page.getByRole('dialog', { name: 'Pomoc', exact: true });
    await expect(help.getByRole('navigation').getByRole('button')).toHaveCount(9);
    await help.getByRole('searchbox').fill('FXF_READ');
    await expect(help.locator('dt')).toHaveCount(11);
    await expect(help.locator('article')).toContainText('żadnych zdalnych poleceń powłoki');
    await screenshot(page, `${role}-release-help-pl`);
    await page.keyboard.press('Escape');
    // Native search inputs consume the first Escape to clear a nonempty query.
    await expect(help.getByRole('searchbox')).toHaveValue('');
    await page.keyboard.press('Escape'); await expect(help).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expect(page.getByTestId('workspace-id')).toHaveText(first); await expect(second.getByTestId('workspace-id')).toHaveText(secondId); await expect(duplicate.getByTestId('workspace-id')).toHaveText(duplicateId);
    await expect(page.locator('.explorer-search input')).toHaveValue('window-A-draft'); await expect(second.locator('.explorer-search input')).toHaveValue('window-B-draft'); await expect(duplicate.locator('.explorer-search input')).toHaveValue('same-system-draft');
  } finally {
    const current = await (await page.request.get('/api/v1/me/preferences')).json() as Preferences;
    expect((await page.request.patch('/api/v1/me/preferences', { headers: await headers(page), data: { expected_revision: current.revision, language: original.language, theme_mode: original.theme_mode } })).status()).toBe(200);
    await duplicate.close(); await second.close();
  }
  for (const project of fixture!.project_ids) {
    const response = await page.request.get(`/api/v1/projects/${project}/investigations`); expect(response.status()).toBe(200);
    let saved = (await response.json() as { items: { investigation_id: string; event_count: number; status: string }[] }).items.find(item => item.event_count > 0 && ['completed', 'partial'].includes(item.status));
    if (!saved) {
      if (fixture!.phase === 'restored') throw new Error('Restored release must include a cached investigation in each System.');
      await open(page, project, 'logs');
      const processes = page.getByRole('group', { name: 'Configured processes', exact: true }).getByRole('checkbox');
      expect(await processes.count()).toBe(5); for (const process of await processes.all()) await process.check();
      await setHistoricalCollectionRange(page, { from: fixture!.from, to: fixture!.to });
      await page.getByRole('button', { name: 'Collect sources', exact: true }).click();
      await expect(page.getByTestId('collection-state')).toHaveText('completed', { timeout: 45000 });
      await expect(page.locator('.virtual-logs .log-event').first()).toBeVisible();
      await page.getByLabel('Investigation title', { exact: true }).fill(`Stage8 ${role} ${project} restore evidence`);
      await page.getByLabel('Private investigation notes', { exact: true }).fill(`Synthetic ${role}-owned disconnected investigation in ${project}.`);
      await page.getByLabel('Pin captured sources against expiry', { exact: true }).check();
      const save = page.waitForResponse(value => value.url().endsWith('/workspace') && value.request().method() === 'PATCH');
      await page.getByRole('button', { name: 'Save investigation workspace', exact: true }).click(); expect((await save).status()).toBe(200);
      saved = { investigation_id: await page.getByTestId('investigation-id').innerText(), event_count: 1, status: 'completed' };
    }
    let remoteStarts = 0; const observe = (request: { method(): string; url(): string }) => { if (request.method() === 'POST' && /\/(collections|live-sessions|connection-tests)$/.test(new URL(request.url()).pathname)) remoteStarts++; }; page.on('request', observe);
    await page.goto(`/systems/${project}/investigations/${saved.investigation_id}`);
    await expect(page.locator('.virtual-logs .log-event').first()).toBeVisible();
    expect(remoteStarts).toBe(0); page.off('request', observe);
    await page.locator('.virtual-logs').first().scrollIntoViewIfNeeded();
    await screenshot(page, `${role}-${project}-cached-investigation`);
  }
});

test('release history uses real SFTP, literal filters, provenance, saved analysis and redacted offline exchange', async ({ page }) => {
  test.skip(fixture?.phase === 'restored', 'Restored phase deliberately keeps source SSH disconnected.');
  test.setTimeout(180000); await login(page, 'inspector'); await open(page, fixture!.project_ids[0], 'logs');
  const processes = page.getByRole('group', { name: 'Configured processes', exact: true }).getByRole('checkbox'); expect(await processes.count()).toBe(5);
  for (const process of await processes.all()) await process.check();
  await setHistoricalCollectionRange(page, { from: fixture!.from, to: fixture!.to });
  await page.getByRole('button', { name: 'Preview collection plan', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Collection plan', exact: true })).toContainText('zip');
  const queried = page.waitForResponse(response => response.url().endsWith('/query') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Collect sources', exact: true }).click();
  await expect(page.getByTestId('collection-state')).toHaveText('completed', { timeout: 45000 });
  const queryResponse = await queried; expect(queryResponse.status()).toBe(200);
  const completePage = page.waitForResponse(response => response.url().endsWith('/query') && response.request().method() === 'POST');
  await page.getByLabel('Rows', { exact: true }).selectOption('200');
  const completeResponse = await completePage; expect(completeResponse.status()).toBe(200); const result = await completeResponse.json() as HistoricalQueryResponse;
  expect(result.items.length).toBeGreaterThan(0);
  expect(new Set(result.items.map(item => item.process_id)).size).toBe(5);
  for (const term of ['REQ-0042', 'a.*b [x]', 'STRASSE']) {
    await fillHistoricalFilters(page, { filter: { include: [term], exclude: [], include_mode: 'all', case_sensitive: false }, per_process_filters: {} });
    const pending = page.waitForResponse(response => response.url().endsWith('/query') && response.request().method() === 'POST'); await applyHistoricalFilters(page);
    const response = await pending; expect(response.status()).toBe(200);
    const filtered = await response.json() as HistoricalQueryResponse;
    expect(filtered.items.length).toBeGreaterThan(0);
    expect(filtered.items.every(item => item.raw_line.toLowerCase().includes(term.toLowerCase()) || term === 'STRASSE' && item.raw_line.includes('Straße'))).toBe(true);
  }
  await fillHistoricalFilters(page, { filter: { include: [], exclude: [], include_mode: 'all', case_sensitive: true }, per_process_filters: {} }); await applyHistoricalFilters(page);
  await page.locator('.log-context-button').first().click();
  const detail = page.getByRole('dialog', { name: 'Event provenance and source context', exact: true }); await expect(detail.locator('.source-context li').first()).toBeVisible();
  await detail.getByLabel('Annotation for this event', { exact: true }).fill('Stage8 retained note');
  await detail.getByRole('button', { name: 'Bookmark event with context', exact: true }).click(); await expect(detail.getByRole('button', { name: 'Bookmark saved', exact: true })).toBeDisabled(); await page.keyboard.press('Escape');
  await page.getByLabel('Investigation title', { exact: true }).fill('Stage8 offline release history');
  await page.getByLabel('Private investigation notes', { exact: true }).fill('Stage8 retained note');
  await page.getByLabel('Pin captured sources against expiry', { exact: true }).check();
  await page.getByRole('button', { name: 'Save investigation workspace', exact: true }).click(); await expect(page.getByText('Workspace saved.', { exact: false })).toBeVisible();
  const savedURL = page.url();
  await page.getByRole('button', { name: 'Export investigation bundle', exact: true }).click();
  const exporting = page.getByRole('dialog', { name: 'Preview redacted investigation bundle', exact: true });
  await exporting.getByLabel('Redact literal values (one per line)', { exact: true }).fill('REQ-0042');
  await exporting.getByRole('button', { name: 'Preview redacted bundle', exact: true }).click(); await expect(exporting.getByTestId('bundle-preview-document')).toContainText('[REDACTED]');
  await exporting.getByLabel('I reviewed this exact preview', { exact: true }).check(); const downloadPending = page.waitForEvent('download'); await exporting.getByRole('button', { name: 'Download previewed bundle', exact: true }).click();
  const filename = test.info().outputPath('synthetic-stage8-redacted.zip'); await (await downloadPending).saveAs(filename);
  await open(page, fixture!.project_ids[1], 'logs'); await page.getByRole('button', { name: 'Import offline bundle', exact: true }).click();
  const importing = page.getByRole('dialog', { name: 'Preview offline investigation import', exact: true }); await importing.getByLabel('Investigation bundle ZIP', { exact: true }).setInputFiles(filename);
  await importing.getByRole('button', { name: 'Validate and preview bundle', exact: true }).click(); await expect(importing.getByTestId('bundle-preview-document')).toContainText('[REDACTED]');
  await importing.getByLabel('I reviewed this exact preview', { exact: true }).check(); await importing.getByRole('button', { name: 'Import private offline copy', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Private offline investigation', exact: true })).toBeVisible(); await expect(page.getByText('Offline bundle | no SSH', { exact: true })).toBeVisible();
  await page.goto(savedURL); await expect(page.getByLabel('Private investigation notes', { exact: true })).toHaveValue('Stage8 retained note'); await screenshot(page, 'release-saved-analysis');
});

test('release Administrator imports direct INI into A and companion YAML ZIP into B', async ({ page }) => {
  test.skip(fixture?.phase === 'restored', 'Restore smoke preserves restored configuration.');
  test.setTimeout(120000); await login(page, 'administrator');
  for (const project of fixture!.project_ids) {
    await open(page, project); await systemAction(page, 'Import Ansible inventory files');
    const dialog = page.getByRole('dialog', { name: 'Import Ansible inventory files', exact: true });
    const sources = await (await page.request.get(`/api/v1/projects/${project}/inventory/sources`)).json() as { items: { id: string; name: string }[] };
    const existing = sources.items.find(item => item.name.startsWith('Stage8 browser source '));
    if (existing) {
      await expect(dialog.getByLabel('Existing inventory source', { exact: true })).toBeEnabled();
      await dialog.getByLabel('Existing inventory source', { exact: true }).selectOption(existing.id);
      await dialog.getByRole('button', { name: 'Continue to upload', exact: true }).click();
    } else {
      await dialog.getByLabel('New inventory source name', { exact: true }).fill('Stage8 browser source qualification');
      await dialog.getByRole('button', { name: 'Create inventory source', exact: true }).click();
    }
    const companionZip = project === fixture!.project_ids[1];
    await dialog.getByLabel('Inventory file or ZIP', { exact: true }).setInputFiles(companionZip ? resolve('../fixtures/inventory/stage8-companion-yaml.zip') : { name: 'hosts', mimeType: 'text/plain', buffer: Buffer.from('[stage8_browser]\nstage8-documented-only ansible_host=192.0.2.250 ansible_user=logreader\n') });
    await dialog.getByRole('button', { name: 'Upload and inspect files', exact: true }).click(); await expect(dialog.getByRole('group', { name: 'Choose static source files in read order', exact: true })).toBeVisible();
    if (companionZip) {
      await expect(dialog.getByRole('group', { name: 'Choose static source files in read order', exact: true })).toContainText('group_vars/all.yaml');
      await expect(dialog.getByRole('group', { name: 'Choose static source files in read order', exact: true })).toContainText('host_vars/stage8-documented-only.yaml');
    }
    const parsed = page.waitForResponse(response => response.url().endsWith('/inventory/parse')); await dialog.getByRole('button', { name: 'Parse selected sources', exact: true }).click();
    const parseResponse = await parsed; expect(parseResponse.status()).toBe(200);
    const summary = await parseResponse.json() as InventoryParsed;
    expect(summary.hosts.map(host => [host.alias, host.address, host.user])).toEqual([['stage8-documented-only', '192.0.2.250', 'logreader']]); expect(summary.process_count).toBe(0);
    if (companionZip) expect(summary.provenance.companion_files.sort()).toEqual(['group_vars/all.yaml', 'host_vars/stage8-documented-only.yaml']);
    await dialog.getByLabel('Subsystem for group stage8_browser', { exact: true }).fill('stage8-browser-subsystem');
    await dialog.getByRole('button', { name: 'Preview exact changes', exact: true }).click(); await expect(dialog.getByRole('checkbox', { name: /^I reviewed these exact changes for / })).toBeVisible();
    await dialog.getByRole('checkbox', { name: /^I reviewed these exact changes for / }).check(); const committed = page.waitForResponse(response => response.url().endsWith('/inventory/commit')); await dialog.getByRole('button', { name: 'Commit reviewed inventory', exact: true }).click(); expect((await committed).status()).toBe(200);
    await expect(dialog).toHaveCount(0);
    const topology = await (await page.request.get(`/api/v1/projects/${project}/topology`)).json() as Topology;
    expect(topology.config.servers.some(item => item.name === 'stage8-documented-only')).toBe(true); expect(topology.config.processes).toHaveLength(5);
    // This fixture’s separately verified SFTP target/root is unchanged. Review
    // and explicitly renew only its revision-bound source approval after import.
    const connection = topology.config.connections?.find(item => item.id === 'c-live');
    expect(connection?.host).toBe('stage8-sftp'); expect(connection?.port).toBe(8022); expect(connection?.allowed_log_roots).toEqual(['/var/log/inspector-demo']);
    const sourcePath = `/api/v1/projects/${project}/connections/c-live/source-access`;
    const source = await (await page.request.get(sourcePath)).json() as components['schemas']['SourceAccessResponse'];
    if (source.manual_confirmation_required && !source.approval.approved) expect((await page.request.post(`${sourcePath}/approve`, { headers: await headers(page), data: { expected_config_revision: topology.revision, expected_approval_revision: source.approval.revision, verified: true } })).status()).toBe(200);
  }
});

test('release proxy supports ten live SFTP subscriptions and independent same-account control', async ({ page, context }) => {
  test.skip(fixture?.phase === 'restored', 'Restored phase deliberately keeps source SSH disconnected.');
  test.setTimeout(180000); await login(page, 'inspector');
  async function start(current: Page, project: string, count = 5) {
    await open(current, project, 'logs'); await current.getByRole('button', { name: 'Live monitor', exact: true }).click();
    const processes = current.getByRole('group', { name: 'Processes to monitor', exact: true }).getByRole('checkbox');
    for (const process of (await processes.all()).slice(0, count)) await process.check();
    const pending = current.waitForResponse(response => response.url().endsWith('/live-sessions') && response.request().method() === 'POST'); await current.getByRole('button', { name: count > 1 ? 'Monitor selected' : 'Monitor', exact: true }).click(); const response = await pending; expect(response.status()).toBe(202);
    const monitor = await response.json() as LiveSession; expect(monitor.process_ids).toHaveLength(count);
    await expect(current.getByText('Stream connected', { exact: true })).toBeVisible(); await expect(current.locator('.live-event').first()).toBeVisible(); return monitor;
  }
  const a = await start(page, fixture!.project_ids[0]); const second = await context.newPage(); const b = await start(second, fixture!.project_ids[1]);
  const bVersion = await second.getByTestId('live-filter-version').innerText();
  const pending = page.waitForResponse(response => response.url().endsWith('/filters') && response.request().method() === 'PUT'); await page.getByLabel('Live contains string', { exact: true }).fill('REQ-0042'); expect((await pending).status()).toBe(200);
  await expect(second.getByTestId('live-filter-version')).toHaveText(bVersion); await expect(second.getByLabel('Live contains string', { exact: true })).toHaveValue('');
  const workspace = await page.getByTestId('workspace-id').innerText(); await page.getByRole('button', { name: 'Help', exact: true }).click(); await expect(page.getByRole('dialog', { name: 'Help', exact: true })).toBeVisible(); await page.keyboard.press('Escape'); await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
  expect((await page.request.get(`/api/v1/projects/${fixture!.project_ids[0]}/live-sessions/${a.session_id}`)).status()).toBe(200);
  await page.getByRole('button', { name: 'Pause display', exact: true }).click(); await expect(page.getByRole('button', { name: 'Resume display', exact: true })).toBeVisible();
  await expect(second.getByText('Stream connected', { exact: true })).toBeVisible(); await screenshot(second, 'ten-source-live-release-proxy');
  await page.getByRole('button', { name: 'Stop this monitor', exact: true }).click(); await expect(page.getByRole('button', { name: 'Monitor selected', exact: true })).toBeEnabled();
  expect((await second.request.get(`/api/v1/projects/${fixture!.project_ids[1]}/live-sessions/${b.session_id}`)).status()).toBe(200);
  const duplicate = await context.newPage(); const same = await start(duplicate, fixture!.project_ids[1], 1); expect(same.session_id).not.toBe(b.session_id);
  await duplicate.getByRole('button', { name: 'Stop this monitor', exact: true }).click(); await duplicate.close(); await expect(second.getByText('Stream connected', { exact: true })).toBeVisible();
  await second.getByRole('button', { name: 'Stop this monitor', exact: true }).click(); await second.close();
});

