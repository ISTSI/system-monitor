import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { serveBuiltAssets, setAppearance, submitSignIn } from './ui';
import type { components } from '../src/api/schema';
import type { BundlePreview, Trace } from '../src/investigation';

const stage = process.env.INSPECTOR_E2E_URL === 'https://localhost:8449' ? 7 : 6;
const enabled = process.env.INSPECTOR_E2E_URL === `https://localhost:${stage === 7 ? 8449 : 8448}`;
const root = resolve('..');
const fixture = enabled ? JSON.parse(readFileSync(resolve(root, `.state/stage${stage}-browser/public-fixture.json`), 'utf8')) as { synthetic: boolean; host: string; projects: string[] } : null;
if (enabled && (!fixture?.synthetic || fixture.host !== `stage${stage}-sftp` || !Array.isArray(fixture.projects) || fixture.projects.join(',') !== `stage${stage}-fixture-a,stage${stage}-fixture-b`)) throw new Error(`Only the isolated generated Stage 0${stage} fixture is authorized.`);
const [systemA, systemB] = fixture?.projects ?? [`stage${stage}-fixture-a`, `stage${stage}-fixture-b`];
const from = '2026-10-16T12:00:00.000000Z'; const to = '2026-10-16T12:00:02.000000Z';
const oracle = JSON.parse(readFileSync(resolve(root, 'fixtures/expected/events.json'), 'utf8')) as components['schemas']['HistoricalEvent'][];
const expected = oracle.filter(event => event.timestamp_utc && event.timestamp_utc >= from && event.timestamp_utc < to);
const failures = new WeakMap<BrowserContext, string[]>();
const external = new WeakMap<BrowserContext, string[]>();
test.skip(!enabled, 'Requires the generated Stage 06 or Stage 07 real SFTP/MariaDB fixture at https://localhost:8448 or https://localhost:8449.');
test.beforeEach(async ({ page, context, baseURL }) => {
  const found: string[] = []; failures.set(context, found); page.on('pageerror', error => found.push(error.message));
  context.on('page', current => current.on('pageerror', error => found.push(error.message)));
  const requests: string[] = []; external.set(context, requests); const origin = new URL(baseURL!).origin;
  await context.grantPermissions(['local-network-access'], { origin });
  await context.route('**/*', route => { const url = new URL(route.request().url()); if (url.origin === origin) return route.fallback(); requests.push(url.origin); return route.abort(); });
  if (process.env.INSPECTOR_E2E_LOCAL_ASSETS === '1') await serveBuiltAssets(context, baseURL!);
});
test.afterEach(async ({ context, page, baseURL }) => {
  try { expect(failures.get(context)).toEqual([]); expect(external.get(context)).toEqual([]); }
  finally {
    if ((await page.request.get('/api/v1/auth/session')).status() === 200) {
      const { csrf_token } = await (await page.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
      expect((await page.request.post('/api/v1/auth/logout', { headers: { Origin: new URL(baseURL!).origin, 'X-CSRF-Token': csrf_token }, data: {} })).status()).toBe(200);
    }
  }
});
async function login(page: Page, role: 'administrator' | 'inspector') {
  const filename = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!filename) throw new Error(`Protected generated Stage 0${stage} account fixture is required.`);
  const account = (JSON.parse(readFileSync(resolve(filename), 'utf8')) as Record<string, { username: string; password: string }>)[role];
  await page.goto('/'); await page.getByLabel('Username', { exact: true }).fill(account.username);
  try { await page.getByLabel('Password', { exact: true }).fill(account.password); if ((await submitSignIn(page)).status() !== 200) throw new Error(); }
  catch { await page.locator('input[type="password"]').fill('').catch(() => {}); throw new Error('Synthetic sign-in failed; protected values withheld.'); }
  await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
}
async function collect(page: Page) {
  await page.goto(`/systems/${systemA}/logs`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  const processes = page.getByRole('group', { name: 'Configured processes', exact: true }).getByRole('checkbox'); expect(await processes.count()).toBe(5);
  for (const process of await processes.all()) await process.check();
  await page.getByLabel('From UTC (inclusive)', { exact: true }).fill(from);
  await page.getByLabel('To UTC (exclusive)', { exact: true }).fill(to);
  const creation = page.waitForResponse(response => response.url().endsWith('/collections') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Collect sources', exact: true }).click();
  expect((await creation).status()).toBe(202);
  await expect(page.getByTestId('collection-state')).toHaveText('completed', { timeout: 30000 });
  await expect(page.getByTestId('match-count')).toHaveText(`${expected.length} matches`);
  await expect(page.getByRole('button', { name: 'Save investigation workspace', exact: true })).toBeEnabled();
  return await page.getByTestId('investigation-id').innerText();
}
async function correlation(page: Page, mode: 'exact' | 'literal') {
  await page.getByLabel('Correlation search mode', { exact: true }).selectOption(mode);
  await page.getByLabel('Correlation value', { exact: true }).fill('REQ-0042');
  const pending = page.waitForResponse(response => response.url().endsWith('/correlation'));
  await page.getByRole('button', { name: 'Find chronological trace', exact: true }).click();
  const response = await pending; expect(response.status()).toBe(200);
  return await response.json() as Trace;
}
async function screenshot(page: Page, name: string) {
  const directory = resolve(root, `verification/stage-${stage}/screenshots`); mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: resolve(directory, `${name}.png`), fullPage: false, animations: 'disabled' });
}

for (const role of ['inspector', 'administrator'] as const) test(`${role} follows exact five-process trace, pins context, restores saved workspace and imports previewed redacted bundle offline`, async ({ page, context, baseURL }) => {
  test.setTimeout(180000); await login(page, role); const investigation = await collect(page);
  const exact = await correlation(page, 'exact');
  expect(exact.items.length).toBe(expected.filter(event => event.metadata.request_id === 'REQ-0042').length);
  expect(new Set(exact.items.map(event => event.process_id)).size).toBe(5);
  expect(exact.items.every(event => event.metadata.request_id === 'REQ-0042')).toBe(true);
  expect(exact.items.some(event => event.raw_line.includes('REQ-00420'))).toBe(false);
  expect(exact.deltas.length).toBe(exact.items.length);
  const literal = await correlation(page, 'literal'); expect(literal.items.length).toBeGreaterThan(exact.items.length);
  expect(literal.items.some(event => event.metadata.request_id === 'REQ-00420')).toBe(true);
  await correlation(page, 'exact');
  const trace = page.getByRole('list', { name: 'Chronological correlation trace', exact: true });
  await expect(trace).toContainText('ingest-instance-a');
  await trace.getByRole('button', { name: 'Inspect trace event', exact: true }).first().click();
  const detail = page.getByRole('dialog', { name: 'Event provenance and source context', exact: true });
  await expect(detail.locator('.source-context li').first()).toBeVisible();
  await expect(detail.getByRole('region', { name: 'Captured source coverage', exact: true })).toContainText('Retained index');
  for (const theme of ['light', 'dark'] as const) { await setAppearance(page, theme); await screenshot(page, `${role}-provenance-context-${theme}`); }
  await detail.getByLabel('Annotation for this event', { exact: true }).fill('secret-operator-note: follow REQ-0042');
  await expect(detail.getByLabel('Pin five lines before and after', { exact: true })).toBeChecked();
  const bookmarkPending = page.waitForResponse(response => response.url().endsWith('/bookmarks') && response.request().method() === 'POST');
  await detail.getByRole('button', { name: 'Bookmark event with context', exact: true }).click(); expect((await bookmarkPending).status()).toBe(201);
  await expect(detail.getByRole('button', { name: 'Bookmark saved', exact: true })).toBeDisabled();
  await detail.getByRole('button', { name: 'Close dialog', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Saved bookmarks', exact: true })).toContainText('secret-operator-note');
  await page.getByLabel('Investigation title', { exact: true }).fill('Follow REQ-0042');
  await page.getByLabel('Private investigation notes', { exact: true }).fill('secret-operator-note: observed cross-process handoff');
  await page.getByLabel('Contains string', { exact: true }).fill('REQ-0042');
  await page.getByLabel('Result layout', { exact: true }).selectOption('split');
  await page.getByLabel('Pin captured sources against expiry', { exact: true }).check();
  const save = page.waitForResponse(response => response.url().endsWith('/workspace') && response.request().method() === 'PATCH');
  await page.getByRole('button', { name: 'Save investigation workspace', exact: true }).click(); expect((await save).status()).toBe(200);
  await expect(page.getByText('Workspace saved.', { exact: false })).toBeVisible();
  for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(size);
    for (const theme of ['light', 'dark'] as const) { await setAppearance(page, theme); await page.getByLabel('Investigation title', { exact: true }).scrollIntoViewIfNeeded(); expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true); await screenshot(page, `${role}-saved-investigation-${theme}-${size.width}x${size.height}`); }
  }
  const duplicate = await context.newPage();
  try {
    await duplicate.goto(`/systems/${systemA}/investigations/${investigation}`);
    await expect(duplicate.getByTestId('match-count')).toHaveText(`${literal.items.length} matches`);
    await expect(duplicate.getByLabel('Contains string', { exact: true })).toHaveValue('REQ-0042');
    await expect(duplicate.getByLabel('Result layout', { exact: true })).toHaveValue('split');
    await expect(duplicate.getByLabel('Private investigation notes', { exact: true })).toHaveValue('secret-operator-note: observed cross-process handoff');
    expect(await duplicate.getByTestId('workspace-id').innerText()).not.toBe(await page.getByTestId('workspace-id').innerText());
    await duplicate.getByLabel('Contains string', { exact: true }).fill('only this duplicated page');
    await expect(page.getByLabel('Contains string', { exact: true })).toHaveValue('REQ-0042');
  } finally { await duplicate.close(); }
  const firstSource = exact.items[0].source.source_revision_id;
  const { csrf_token } = await (await page.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
  const headers = { Origin: new URL(baseURL!).origin, 'X-CSRF-Token': csrf_token };
  async function sourceHash() {
    const grant = await page.request.post(`/api/v1/projects/${systemA}/investigations/${investigation}/sources/${firstSource}/download`, { headers, data: {} }); expect(grant.status()).toBe(200);
    const { url } = await grant.json() as { url: string }; const result = await page.request.get(url); expect(result.status()).toBe(200);
    return createHash('sha256').update(await result.body()).digest('hex');
  }
  const originalHash = await sourceHash();
  await page.getByRole('button', { name: 'Export investigation bundle', exact: true }).click();
  const exporting = page.getByRole('dialog', { name: 'Preview redacted investigation bundle', exact: true });
  await exporting.getByLabel('Redact literal values (one per line)', { exact: true }).fill('REQ-0042\nsecret-operator-note');
  const previewPending = page.waitForResponse(response => response.url().endsWith('/bundles/export/preview'));
  await exporting.getByRole('button', { name: 'Preview redacted bundle', exact: true }).click();
  const previewResponse = await previewPending; expect(previewResponse.status()).toBe(200); const preview = await previewResponse.json() as BundlePreview;
  expect(JSON.stringify(preview.document)).not.toContain('REQ-0042'); expect(JSON.stringify(preview.document)).not.toContain('secret-operator-note');
  await expect(exporting.getByTestId('bundle-preview-document')).toContainText('[REDACTED]');
  const cancelling = page.waitForResponse(response => response.url().endsWith(`/bundles/previews/${preview.preview_id}/cancel`));
  await exporting.getByLabel('Redact literal values (one per line)', { exact: true }).fill('REQ-0042\nsecret-operator-note\nunused-sensitive-value');
  expect((await cancelling).status()).toBe(200);
  await expect(exporting.getByTestId('bundle-preview-document')).toHaveCount(0);
  const revisedPreview = page.waitForResponse(response => response.url().endsWith('/bundles/export/preview'));
  await exporting.getByRole('button', { name: 'Preview redacted bundle', exact: true }).click(); expect((await revisedPreview).status()).toBe(200);
  await expect(exporting.getByTestId('bundle-preview-document')).toBeVisible();
  await expect(exporting.getByRole('button', { name: 'Download previewed bundle', exact: true })).toBeDisabled();
  await exporting.getByLabel('I reviewed this exact preview', { exact: true }).check();
  await screenshot(page, `${role}-redacted-bundle-preview`);
  const downloadPending = page.waitForEvent('download');
  await exporting.getByRole('button', { name: 'Download previewed bundle', exact: true }).click();
  const download = await downloadPending; const filename = test.info().outputPath(`${role}-redacted-investigation.zip`); await download.saveAs(filename);
  expect(await sourceHash()).toBe(originalHash);
  await page.goto(`/systems/${systemB}/logs`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  let connectionRequests = 0;
  const countConnections = (request: { method: () => string; url: () => string }) => { if (request.method() === 'POST' && /\/(collections|live-sessions|connection-tests)(?:\/|$)/.test(new URL(request.url()).pathname)) connectionRequests += 1; };
  page.on('request', countConnections);
  try {
    await page.getByRole('button', { name: 'Import offline bundle', exact: true }).click();
    const importing = page.getByRole('dialog', { name: 'Preview offline investigation import', exact: true });
    await importing.getByLabel('Investigation bundle ZIP', { exact: true }).setInputFiles(filename);
    await importing.getByRole('button', { name: 'Validate and preview bundle', exact: true }).click();
    await expect(importing.getByTestId('bundle-preview-document')).toContainText('[REDACTED]');
    await importing.getByLabel('I reviewed this exact preview', { exact: true }).check();
    await importing.getByRole('button', { name: 'Import private offline copy', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Private offline investigation', exact: true })).toBeVisible();
    await expect(page.getByText('Offline bundle | no SSH', { exact: true })).toBeVisible();
    await expect(page.getByTestId('match-count')).toContainText('matches');
    await expect(page.getByLabel('Private investigation notes', { exact: true })).not.toHaveValue(/secret-operator-note/);
    await expect(page.getByRole('button', { name: 'Collect sources', exact: true })).toBeDisabled();
    await page.getByLabel('Investigation title', { exact: true }).fill('Offline private follow-up');
    await page.getByLabel('Private investigation notes', { exact: true }).fill('Follow-up after disconnected import');
    await page.getByRole('button', { name: 'Save investigation workspace', exact: true }).click();
    await expect(page.getByText('Workspace saved.', { exact: false })).toBeVisible();
    const importedBookmarks = page.getByRole('region', { name: 'Saved bookmarks', exact: true });
    await importedBookmarks.getByLabel('Bookmark annotation', { exact: true }).fill('Offline personal annotation');
    await importedBookmarks.getByRole('button', { name: 'Save annotation', exact: true }).click();
    await page.getByLabel('Correlation value', { exact: true }).fill('[REDACTED]');
    await page.getByRole('button', { name: 'Find chronological trace', exact: true }).click();
    await expect(page.getByTestId('trace-count')).toHaveText(`${exact.items.length} trace matches`);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Private offline investigation', exact: true })).toBeVisible();
    await expect(page.getByTestId('match-count')).toContainText('matches');
    await expect(page.getByLabel('Investigation title', { exact: true })).toHaveValue('Offline private follow-up');
    await expect(page.getByLabel('Private investigation notes', { exact: true })).toHaveValue('Follow-up after disconnected import');
    await expect(page.getByRole('region', { name: 'Saved bookmarks', exact: true }).getByLabel('Bookmark annotation', { exact: true })).toHaveValue('Offline personal annotation');
    await page.getByRole('button', { name: 'Export investigation bundle', exact: true }).click();
    const offlineExport = page.getByRole('dialog', { name: 'Preview redacted investigation bundle', exact: true });
    await offlineExport.getByRole('button', { name: 'Preview redacted bundle', exact: true }).click();
    await expect(offlineExport.getByTestId('bundle-preview-document')).toContainText('Follow-up after disconnected import');
    const discarded = page.waitForResponse(response => /\/bundles\/previews\/[^/]+\/cancel$/.test(response.url()));
    await offlineExport.getByRole('button', { name: 'Close dialog', exact: true }).click(); expect((await discarded).status()).toBe(200);
    expect(connectionRequests).toBe(0);
    await screenshot(page, `${role}-imported-offline-investigation`);
  } finally { page.off('request', countConnections); }
  expect((await page.request.get(`/api/v1/projects/${systemB}/investigations/${investigation}/workspace`)).status()).toBe(404);
  await page.goto(`/systems/${systemA}/investigations/${investigation}`);
  await expect(page.getByLabel('Pin captured sources against expiry', { exact: true })).toBeChecked();
  await expect(page.getByRole('button', { name: 'Expire captured source cache', exact: true })).toBeDisabled();
  await page.getByLabel('Pin captured sources against expiry', { exact: true }).uncheck();
  await page.getByRole('button', { name: 'Save investigation workspace', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Expire captured source cache', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Expire captured source cache', exact: true }).click();
  const expiry = page.getByRole('dialog', { name: 'Expire captured source cache', exact: true });
  await expect(expiry).toContainText('pinned bookmark context remain');
  await expiry.getByRole('button', { name: 'Remove unpinned source cache', exact: true }).click();
  await expect(page.getByTestId('investigation-availability')).toHaveText('unavailable');
  await expect(page.getByRole('heading', { name: 'Retained source data unavailable', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Collection progress', exact: true })).toContainText('Coverage: unavailable');
  const retainedBookmarks = page.getByRole('region', { name: 'Saved bookmarks', exact: true });
  await expect(retainedBookmarks.getByLabel('Bookmark annotation', { exact: true })).toHaveValue('secret-operator-note: follow REQ-0042');
  await retainedBookmarks.getByText(/Retained source context \(\d+ lines\)/).click();
  await expect(retainedBookmarks.locator('.source-context li').first()).toBeVisible();
  await screenshot(page, `${role}-expired-source-pinned-context`);
});

test('dependency neighbours follow configured direction and unsafe bundle is rejected before commit', async ({ page }) => {
  await login(page, 'inspector'); await page.goto(`/systems/${systemA}/topology`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await page.getByRole('button', { name: 'Select process ingest-instance-a', exact: true }).click();
  await page.getByRole('button', { name: 'Highlight downstream', exact: true }).click();
  await expect(page.getByText('Possible transfers, not observed causality', { exact: true })).toBeVisible();
  const monitorPending = page.waitForResponse(response => response.url().endsWith('/live-sessions') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Monitor highlighted neighbours', exact: true }).click();
  const monitor = await monitorPending; expect(monitor.status()).toBe(202);
  expect((monitor.request().postDataJSON() as { process_ids: string[] }).process_ids).toHaveLength(5);
  await expect(page.getByTestId('live-session-id')).toHaveText(/^[0-9a-f-]{36}$/);
  const stopped = page.waitForResponse(response => response.url().endsWith('/stop') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Stop this monitor', exact: true }).click(); expect((await stopped).status()).toBe(200);
  await page.getByRole('link', { name: 'Topology', exact: true }).click();
  await page.getByRole('button', { name: 'Inspect highlighted neighbours', exact: true }).click();
  const selected = page.getByRole('group', { name: 'Configured processes', exact: true }).getByRole('checkbox', { checked: true });
  await expect(selected).toHaveCount(5);
  await page.getByRole('button', { name: 'Import offline bundle', exact: true }).click();
  const importing = page.getByRole('dialog', { name: 'Preview offline investigation import', exact: true });
  await importing.getByLabel('Investigation bundle ZIP', { exact: true }).setInputFiles({ name: 'corrupted.zip', mimeType: 'application/zip', buffer: Buffer.from('not a ZIP; ../unsafe') });
  await importing.getByRole('button', { name: 'Validate and preview bundle', exact: true }).click();
  await expect(importing.getByRole('alert')).toBeVisible();
  await expect(importing.getByRole('button', { name: 'Import private offline copy', exact: true })).toHaveCount(0);
});

test('a delayed bookmark response cannot replace the investigation opened later in the same page', async ({ page, context }) => {
  test.setTimeout(120000); await login(page, 'inspector'); const first = await collect(page); const second = await collect(page);
  await page.getByLabel('Open your retained collection', { exact: true }).selectOption(first);
  await expect(page.getByTestId('investigation-id')).toHaveText(first);
  await expect(page.getByTestId('match-count')).toHaveText(`${expected.length} matches`);
  await page.getByRole('button', { name: /^Inspect source line / }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Event provenance and source context', exact: true });
  await expect(dialog.locator('.source-context li').first()).toBeVisible();
  await dialog.getByLabel('Annotation for this event', { exact: true }).fill('Late response remains with the first investigation');
  let release = () => {}; const gate = new Promise<void>(resolve => { release = resolve; });
  let reached = () => {}; const requested = new Promise<void>(resolve => { reached = resolve; });
  const pattern = `**/api/v1/projects/${systemA}/investigations/${first}/bookmarks`;
  await context.route(pattern, async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    const response = await route.fetch(); expect(response.status()).toBe(201); reached(); await gate; await route.fulfill({ response });
  });
  try {
    await dialog.getByRole('button', { name: 'Bookmark event with context', exact: true }).click(); await requested;
    await dialog.getByRole('button', { name: 'Close dialog', exact: true }).click();
    await page.getByLabel('Open your retained collection', { exact: true }).selectOption(second);
    await expect(page.getByTestId('investigation-id')).toHaveText(second);
    await expect(page.getByRole('button', { name: 'Save investigation workspace', exact: true })).toBeEnabled();
    await page.getByLabel('Investigation title', { exact: true }).fill('Second capture stays selected');
    const completed = page.waitForResponse(response => response.url().endsWith(`/investigations/${first}/bookmarks`) && response.request().method() === 'POST');
    release(); await completed;
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    await expect(page.getByTestId('investigation-id')).toHaveText(second);
    await expect(page.getByLabel('Investigation title', { exact: true })).toHaveValue('Second capture stays selected');
    const saving = page.waitForResponse(response => response.url().endsWith(`/investigations/${second}/workspace`) && response.request().method() === 'PATCH');
    await page.getByRole('button', { name: 'Save investigation workspace', exact: true }).click();
    const saved = await saving; expect(saved.status()).toBe(200); expect(saved.request().postDataJSON().expected_revision).toBe(0);
  } finally { release(); await context.unroute(pattern); }
});
