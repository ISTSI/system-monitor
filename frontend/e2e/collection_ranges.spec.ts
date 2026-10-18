import { expect, test, type BrowserContext, type Page, type Request } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { components } from '../src/api/schema';
import { applyHistoricalFilters, fillHistoricalFilters, openHistoricalFilters, serveBuiltAssets, setAppearance, setHistoricalCollectionRange } from './ui';

type Job = components['schemas']['HistoricalJobResponse'];
type Query = components['schemas']['HistoricalQueryInput'];
type Results = components['schemas']['HistoricalQueryResponse'];
const enabled = process.env.INSPECTOR_E2E_URL === 'https://localhost:8450';
const fixture = enabled ? JSON.parse(readFileSync(resolve('../.state/pin-range-check/public-fixture.json'), 'utf8')) as {
  synthetic: boolean; transport: string; projects: string[];
} : null;
if (enabled && (!fixture?.synthetic || fixture.transport !== 'local_demo' || fixture.projects.join(',') !== 'stage7-fixture-a,stage7-fixture-b')) {
  throw new Error('Only the disposable local-demo collection-range fixture is authorized.');
}
const project = fixture?.projects[0] ?? 'stage7-fixture-a';
const from = '2026-10-16T12:00:00.000000Z'; const to = '2026-10-16T12:00:02.000000Z';
const displayedFrom = '2026-10-16T12:00:00.500000Z'; const displayedTo = '2026-10-16T12:00:01.500000Z';
const nextFrom = '2026-10-13T00:00:00.000000Z'; const nextTo = '2026-10-17T00:00:00.000000Z';
const displayUtc = (value: string) => value.slice(0, 19).replace('T', ' ');
const errors = new WeakMap<BrowserContext, string[]>();
const created = new WeakMap<BrowserContext, string[]>();
test.skip(!enabled, 'Requires the disposable synthetic local-demo fixture at https://localhost:8450.');
test.use({ timezoneId: 'America/Los_Angeles' });

test.beforeEach(async ({ context, page, baseURL }) => {
  const found: string[] = []; errors.set(context, found); created.set(context, []);
  page.on('pageerror', error => found.push(error.message));
  context.on('page', extra => extra.on('pageerror', error => found.push(error.message)));
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin === baseURL) return route.fallback();
    found.push('External request blocked'); return route.abort();
  });
  await serveBuiltAssets(context, baseURL!);
});

test.afterEach(async ({ context, page, baseURL }) => {
  try { expect(errors.get(context)).toEqual([]); }
  finally {
    if ((await page.request.get('/api/v1/auth/session')).status() === 200) {
      const { csrf_token } = await (await page.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
      const headers = { Origin: baseURL!, 'X-CSRF-Token': csrf_token };
      for (const id of created.get(context) ?? []) {
        const removed = await page.request.delete(`/api/v1/projects/${project}/investigations/${id}`, { headers });
        expect(removed.status()).toBe(200);
      }
      expect((await page.request.post('/api/v1/auth/logout', { headers, data: {} })).status()).toBe(200);
    }
  }
});

async function login(page: Page) {
  const filename = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!filename) throw new Error('Protected synthetic accounts are required.');
  const account = (JSON.parse(readFileSync(resolve(filename), 'utf8')) as Record<string, { username: string; password: string }>).inspector;
  await page.goto('/');
  const { csrf_token } = await (await page.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
  const response = await page.request.post('/api/v1/auth/login', {
    headers: { Origin: new URL(page.url()).origin, 'X-CSRF-Token': csrf_token },
    data: { username: account.username, password: account.password },
  });
  if (response.status() !== 200) throw new Error(`Synthetic sign-in failed (${response.status()}); protected values withheld.`);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
}

async function open(page: Page, id?: string) {
  await page.goto(`/systems/${project}/${id ? `investigations/${id}` : 'logs'}`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  await expect(page.getByRole('heading', { name: 'Historical investigation', exact: true })).toBeVisible();
  if (id) await expect(page.getByTestId('investigation-id')).toHaveText(id);
}

async function collect(page: Page, expected: { from: string; to: string; process_ids: string[] }) {
  const creation = page.waitForResponse(response => response.url().endsWith('/collections') && response.request().method() === 'POST');
  const loaded = page.waitForResponse(response => response.url().endsWith('/query') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Collect sources', exact: true }).click();
  const response = await creation; expect(response.status()).toBe(202);
  expect(response.request().postDataJSON()).toMatchObject({ ...expected, transport: 'local_demo' });
  const job = await response.json() as Job;
  created.get(page.context())!.push(job.investigation_id);
  await expect(page.getByTestId('collection-state')).toHaveText('completed', { timeout: 30000 });
  const query = await loaded; expect(query.status()).toBe(200);
  const input = query.request().postDataJSON() as Query;
  expect(input).toMatchObject({ ...expected, filter: { include: [], exclude: [] }, per_process_filters: {}, lane: 'events' });
  const body = await query.json() as Results;
  expect(body.items.length).toBeGreaterThan(0);
  await expect(page.locator('.history-result-body')).toHaveAttribute('aria-busy', 'false');
  return { job, body, input };
}

test('collection range and processes stay separate from retained display filters, saved state and same-account pages', async ({ page, context }) => {
  test.setTimeout(180000); await login(page); await open(page);
  const range = page.getByRole('group', { name: 'Collection time range', exact: true });
  await expect(page.getByRole('button', { name: 'Filters', exact: true })).toBeDisabled();
  const choices = page.getByRole('group', { name: 'Configured processes', exact: true }).getByRole('checkbox');
  await expect(choices).toHaveCount(5);
  for (const choice of await choices.all()) await choice.check();
  const ids = await choices.evaluateAll(elements => elements.map(element => element.getAttribute('data-process-id')!));
  await setHistoricalCollectionRange(page, { from, to });
  const initial = await collect(page, { from, to, process_ids: ids });
  const initialWorkspace = await page.getByTestId('workspace-id').innerText();

  // Draft a different next acquisition; retained filtering must keep all five sources.
  for (const choice of (await choices.all()).slice(1)) await choice.uncheck();
  await setHistoricalCollectionRange(page, { from: nextFrom, to: nextTo });
  const preview = page.waitForResponse(response => response.url().endsWith('/collections/plan') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Preview collection plan', exact: true }).click();
  const planned = await preview; expect(planned.status()).toBe(200);
  expect(planned.request().postDataJSON()).toMatchObject({ process_ids: [ids[0]], from: nextFrom, to: nextTo });
  const plan = page.getByRole('region', { name: 'Collection plan', exact: true });
  await expect(plan).toBeVisible();
  const collected = page.getByRole('group', { name: 'Collected processes', exact: true });
  await expect(collected.locator('span')).toHaveCount(5);
  for (const id of ids) await expect(collected.locator(`[title="${id}"]`)).toHaveCount(1);

  const operations: string[] = [];
  const count = (request: Request) => { if (request.method() === 'POST' && /\/(collections(?:\/plan)?|live-sessions)$/.test(new URL(request.url()).pathname)) operations.push(request.url()); };
  context.on('request', count);
  const duplicate = await context.newPage();
  try {
    const dialog = await fillHistoricalFilters(page, { from: displayedFrom, to: displayedTo,
      filter: { include: ['REQ-0042'], exclude: [], include_mode: 'all', case_sensitive: true }, per_process_filters: {} });
    await expect(dialog.getByLabel('Filter scope', { exact: true }).locator('option')).toHaveCount(6);
    const filtered = page.waitForResponse(response => response.url().endsWith('/query') && response.request().method() === 'POST');
    await applyHistoricalFilters(page);
    const response = await filtered; expect(response.status()).toBe(200);
    expect(response.request().postDataJSON()).toMatchObject({ process_ids: ids, from: displayedFrom, to: displayedTo });
    const body = await response.json() as Results;
    const expected = initial.body.items.filter(event => event.timestamp_utc! >= displayedFrom && event.timestamp_utc! < displayedTo && event.raw_line.includes('REQ-0042'));
    expect(body.items.map(event => event.event_id)).toEqual(expected.map(event => event.event_id));
    await expect(plan).toBeVisible();
    await expect(range.getByLabel('From UTC (inclusive)', { exact: true })).toHaveValue(displayUtc(nextFrom));
    await expect(range.getByLabel('To UTC (exclusive)', { exact: true })).toHaveValue(displayUtc(nextTo));

    await page.getByLabel('Investigation title', { exact: true }).fill('Independent collection and display ranges');
    const saved = page.waitForResponse(response => response.url().endsWith('/workspace') && response.request().method() === 'PATCH');
    await page.getByRole('button', { name: 'Save investigation workspace', exact: true }).click();
    expect((await saved).status()).toBe(200);
    await open(duplicate, initial.job.investigation_id);
    expect(await duplicate.getByTestId('workspace-id').innerText()).not.toBe(initialWorkspace);
    await expect(duplicate.getByTestId('match-count')).toHaveText(`${expected.length} matches`);
    const duplicateRange = duplicate.getByRole('group', { name: 'Collection time range', exact: true });
    await expect(duplicateRange.getByLabel('From UTC (inclusive)', { exact: true })).toHaveValue(displayUtc(from));
    await expect(duplicateRange.getByLabel('To UTC (exclusive)', { exact: true })).toHaveValue(displayUtc(to));
    const restored = await openHistoricalFilters(duplicate);
    await expect(restored.getByLabel('From UTC (inclusive)', { exact: true })).toHaveAttribute('title', `Exact UTC bound: ${displayedFrom}`);
    await expect(restored.getByLabel('To UTC (exclusive)', { exact: true })).toHaveAttribute('title', `Exact UTC bound: ${displayedTo}`);
    expect(await restored.locator('.history-filter-list code').allTextContents()).toEqual(['REQ-0042']);
    await restored.getByRole('button', { name: 'Cancel', exact: true }).click();

    // A display query cannot expand the acquisition interval into captured context.
    await fillHistoricalFilters(page, { from: nextFrom, to: nextTo,
      filter: { include: [], exclude: [], include_mode: 'all', case_sensitive: true }, per_process_filters: {} });
    const broadened = page.waitForResponse(value => value.url().endsWith('/query') && value.request().method() === 'POST');
    await applyHistoricalFilters(page);
    const broadResponse = await broadened; expect(broadResponse.status()).toBe(200);
    const broadBody = await broadResponse.json() as Results;
    expect(broadBody.items.map(event => event.event_id)).toEqual(initial.body.items.map(event => event.event_id));
    expect(broadBody.items.every(event => event.timestamp_utc! >= from && event.timestamp_utc! < to)).toBe(true);
    await expect(duplicate.getByTestId('match-count')).toHaveText(`${expected.length} matches`);
    expect(operations).toEqual([]);

    const directory = resolve('../verification/stage-7/screenshots'); mkdirSync(directory, { recursive: true });
    for (const size of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
      await page.setViewportSize(size);
      for (const theme of ['light', 'dark'] as const) {
        await setAppearance(page, theme); await range.scrollIntoViewIfNeeded();
        await page.screenshot({ path: resolve(directory, `collection-ranges-${theme}-${size.width}x${size.height}.png`), animations: 'disabled' });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      }
    }
    expect(operations).toEqual([]);
  } finally { context.off('request', count); await duplicate.close(); }

  const next = await collect(page, { from: nextFrom, to: nextTo, process_ids: [ids[0]] });
  expect(next.job.investigation_id).not.toBe(initial.job.investigation_id);
  await expect(page.getByRole('group', { name: 'Collected processes', exact: true }).locator('span')).toHaveCount(1);
});

test('invalid collection bounds fail before collection while display validation leaves the collection draft intact', async ({ page }) => {
  test.setTimeout(90000); await login(page); await open(page);
  const choice = page.getByRole('group', { name: 'Configured processes', exact: true }).getByRole('checkbox').first();
  await choice.check(); const id = await choice.getAttribute('data-process-id');
  const requests: string[] = [];
  const count = (request: Request) => { if (request.method() === 'POST' && /\/(collections(?:\/plan)?|query)$/.test(new URL(request.url()).pathname)) requests.push(request.url()); };
  page.on('request', count);
  try {
    for (const invalidFrom of ['2026-02-30 12:00:00', '2026-10-16 24:00:00', displayUtc(to)]) {
      await setHistoricalCollectionRange(page, { from: invalidFrom, to });
      for (const action of ['Preview collection plan', 'Collect sources']) {
        await page.getByRole('button', { name: action, exact: true }).click();
        await expect(page.getByRole('alert')).toContainText(invalidFrom === displayUtc(to) ? 'From must be earlier' : 'invalid');
      }
    }
    expect(requests).toEqual([]);
  } finally { page.off('request', count); }
  await setHistoricalCollectionRange(page, { from, to });
  await collect(page, { from, to, process_ids: [id!] });
  await setHistoricalCollectionRange(page, { from: nextFrom, to: nextTo });
  requests.length = 0; page.on('request', count);
  try {
    const dialog = await fillHistoricalFilters(page, { from: to, to: from });
    await dialog.getByRole('button', { name: 'Apply filters', exact: true }).click();
    await expect(dialog.getByRole('alert')).toContainText('The exclusive end must follow the inclusive start.');
    expect(requests).toEqual([]);
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    const range = page.getByRole('group', { name: 'Collection time range', exact: true });
    await expect(range.getByLabel('From UTC (inclusive)', { exact: true })).toHaveValue(displayUtc(nextFrom));
    await expect(range.getByLabel('To UTC (exclusive)', { exact: true })).toHaveValue(displayUtc(nextTo));
  } finally { page.off('request', count); }
});
