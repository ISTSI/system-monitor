import { expect, test, type BrowserContext, type Locator, type Page } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { serveBuiltAssets } from './ui';
import type { components } from '../src/api/schema';
import type { BookmarksWithPins } from '../src/investigationPins';

type Results = components['schemas']['HistoricalQueryResponse'];
type Query = components['schemas']['HistoricalQueryInput'];
type Event = Results['items'][number];
const isolatedRangeCheck = process.env.INSPECTOR_E2E_URL === 'https://localhost:8450';
const enabled = isolatedRangeCheck || process.env.INSPECTOR_E2E_URL === 'https://localhost:8449';
const root = resolve('..');
const fixture = enabled ? JSON.parse(readFileSync(resolve(root, isolatedRangeCheck ? '.state/pin-range-check/public-fixture.json' : '.state/stage7-browser/public-fixture.json'), 'utf8')) as { synthetic: boolean; host?: string; transport?: string; projects: string[] } : null;
if (enabled && (!fixture?.synthetic || (isolatedRangeCheck ? fixture.transport !== 'local_demo' : fixture.host !== 'stage7-sftp') || fixture.projects.join(',') !== 'stage7-fixture-a,stage7-fixture-b')) throw new Error('Only the isolated generated fixture is authorized.');
const system = fixture?.projects[0] ?? 'stage7-fixture-a';
const failures = new WeakMap<BrowserContext, string[]>();
const surface = (page: Page) => page.locator('[aria-label="Event results"]');
const pinButton = (page: Page) => surface(page).getByRole('button', { name: 'Pin', exact: true });
const row = (table: Locator, index = 0) => table.locator(`.log-event[aria-rowindex="${index + 2}"]`);
const queryResponse = (page: Page, id: string) => page.waitForResponse(response => response.url().endsWith(`/investigations/${id}/query`) && response.request().method() === 'POST');

test.skip(!enabled, 'Requires the isolated generated Stage 07 real MariaDB/SFTP fixture and grouped-pin API.');
test.use({ timezoneId: 'America/Los_Angeles' });
test.beforeEach(async ({ page, context, baseURL }) => {
  const found: string[] = []; failures.set(context, found);
  page.on('pageerror', () => found.push('Browser error'));
  context.on('page', current => current.on('pageerror', () => found.push('Browser error')));
  await context.grantPermissions(['local-network-access'], { origin: baseURL! });
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin === baseURL) return route.fallback();
    found.push('External request blocked'); return route.abort();
  });
  await serveBuiltAssets(context, baseURL!);
});
test.afterEach(async ({ context, page, baseURL }) => {
  try { expect(failures.get(context)).toEqual([]); }
  finally {
    if ((await page.request.get('/api/v1/auth/session')).status() === 200) {
      const csrf = (await (await page.request.get('/api/v1/auth/csrf')).json()).csrf_token as string;
      expect((await page.request.post('/api/v1/auth/logout', { headers: { Origin: baseURL!, 'X-CSRF-Token': csrf }, data: {} })).status()).toBe(200);
    }
  }
});

async function login(page: Page) {
  const filename = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!filename) throw new Error('Protected synthetic accounts are required.');
  const account = (JSON.parse(readFileSync(resolve(filename), 'utf8')) as Record<string, { username: string; password: string }>).inspector;
  await page.goto('/');
  const csrf = await (await page.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
  const submit = () => page.request.post('/api/v1/auth/login', { headers: { Origin: new URL(page.url()).origin, 'X-CSRF-Token': csrf.csrf_token }, data: { username: account.username, password: account.password } });
  let signedIn = await submit();
  if (signedIn.status() === 429) {
    test.info().setTimeout(test.info().timeout + 65000);
    test.info().annotations.push({ type: 'rate-limit', description: 'Waited 60 seconds for one login retry without changing the limit.' });
    await page.waitForTimeout(60000); signedIn = await submit();
  }
  if (signedIn.status() !== 200) throw new Error(`Synthetic sign-in failed (${signedIn.status()}); protected values withheld.`);
  await page.reload(); await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
}

async function collect(page: Page) {
  await page.goto(`/systems/${system}/logs`);
  await expect(page.getByTestId('workspace-id')).toHaveText(/^[0-9a-f-]{36}$/);
  const processes = page.getByRole('group', { name: 'Configured processes', exact: true }).getByRole('checkbox');
  expect(await processes.count()).toBe(5); for (const choice of await processes.all()) await choice.check();
  const range = page.getByRole('group', { name: 'Collection time range', exact: true });
  await range.getByLabel('From UTC (inclusive)', { exact: true }).fill('2026-10-13 00:00:00');
  await range.getByLabel('To UTC (exclusive)', { exact: true }).fill('2026-10-17 00:00:00');
  await surface(page).getByLabel('Rows', { exact: true }).selectOption('200');
  const loaded = page.waitForResponse(response => response.url().endsWith('/query') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Collect sources', exact: true }).click();
  await expect(page.getByTestId('collection-state')).toHaveText('completed', { timeout: 30000 });
  await expect(page.getByTestId('investigation-availability')).toHaveText('retained');
  const response = await loaded; expect(response.status()).toBe(200);
  const body = await response.json() as Results; expect(body.items.length).toBeGreaterThan(20);
  await expect(surface(page).getByRole('table')).toHaveAttribute('aria-rowcount', String(body.items.length + 1));
  await expect(pinButton(page)).toBeDisabled();
  return { body, input: response.request().postDataJSON() as Query, id: await page.getByTestId('investigation-id').innerText() };
}

async function resize(page: Page, id: string, size = '10') {
  const loaded = queryResponse(page, id); await surface(page).getByLabel('Rows', { exact: true }).selectOption(size);
  const response = await loaded; expect(response.status()).toBe(200);
  await expect(surface(page).locator('.history-result-body')).toHaveAttribute('aria-busy', 'false');
  return { body: await response.json() as Results, input: response.request().postDataJSON() as Query };
}

async function processMenu(page: Page) {
  const picker = surface(page).locator('.log-process-menu');
  if (await picker.getAttribute('open') === null) await picker.locator('summary').click();
  return picker;
}

async function bookmarks(page: Page, id: string) {
  const response = await page.request.get(`/api/v1/projects/${system}/investigations/${id}/bookmarks`);
  expect(response.status()).toBe(200); return await response.json() as BookmarksWithPins;
}

async function deletePin(page: Page, id: string, pinId: string) {
  const card = page.locator(`.pin-card[data-pin-id="${pinId}"]`);
  await card.getByRole('button', { name: 'View', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'View pin', exact: true });
  const deleted = page.waitForResponse(response => response.url().endsWith(`/investigations/${id}/pins/${pinId}/delete`) && response.request().method() === 'POST');
  await dialog.getByRole('button', { name: 'Delete pin', exact: true }).click(); expect((await deleted).status()).toBe(200); await expect(card).toHaveCount(0);
}

function expectedPinEvent(event: Event, query: Query) {
  return { event_id: event.event_id, from: query.from, to: query.to, filter: query.filter,
    per_process_filters: query.per_process_filters?.[event.process_id] ? { [event.process_id]: query.per_process_filters[event.process_id] } : {} };
}

test('row selection preserves copy, keyboard and context behavior and stays independent in duplicate pages', async ({ page, context }) => {
  test.setTimeout(180000); await login(page); const { id } = await collect(page); await resize(page, id);
  const table = surface(page).getByRole('table'); const first = row(table); const second = row(table, 1); const third = row(table, 2);
  await first.getByRole('cell').nth(1).click(); await expect(first).toHaveAttribute('aria-selected', 'true');
  await expect(first).toHaveClass(/log-event-selected/); await expect(pinButton(page)).toContainText('1');
  await second.focus(); await page.keyboard.press('Space'); await expect(second).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('Enter'); await expect(second).toHaveAttribute('aria-selected', 'false');
  await third.getByRole('button', { name: /^Inspect source line / }).click();
  await expect(page.getByRole('dialog', { name: 'Event provenance and source context', exact: true })).toBeVisible();
  await page.keyboard.press('Escape'); await expect(third).toHaveAttribute('aria-selected', 'false'); await expect(pinButton(page)).toContainText('1');
  const message = third.locator('.log-message'); await message.scrollIntoViewIfNeeded();
  const text = await message.boundingBox(); const bounds = await table.boundingBox();
  const start = Math.max(text!.x + 8, bounds!.x + 12); const end = Math.min(start + 90, bounds!.x + bounds!.width - 12);
  expect(end - start).toBeGreaterThan(20);
  await page.mouse.move(start, text!.y + text!.height / 2); await page.mouse.down();
  await page.mouse.move(end, text!.y + text!.height / 2, { steps: 8 }); await page.mouse.up();
  expect(await third.evaluate(element => { const selection = window.getSelection(); return !!selection && !selection.isCollapsed && !!selection.anchorNode && element.contains(selection.anchorNode); })).toBe(true);
  await expect(third).toHaveAttribute('aria-selected', 'false'); await expect(pinButton(page)).toContainText('1');
  await page.evaluate(() => window.getSelection()?.removeAllRanges());
  await page.setViewportSize({ width: 800, height: 720 });
  await expect.poll(() => table.evaluate(element => element.scrollWidth - element.clientWidth)).toBeGreaterThan(60);
  await table.evaluate(element => { element.scrollLeft = 60; });
  await first.evaluate(element => (element as HTMLElement).focus({ preventScroll: true }));
  await page.keyboard.press('Enter'); await expect(first).toHaveAttribute('aria-selected', 'false'); await expect(table).toHaveJSProperty('scrollLeft', 60);
  await page.keyboard.press('Space'); await expect(first).toHaveAttribute('aria-selected', 'true'); await expect(table).toHaveJSProperty('scrollLeft', 60);
  const duplicate = await context.newPage();
  try {
    const loaded = queryResponse(duplicate, id); await duplicate.goto(`/systems/${system}/investigations/${id}`); expect((await loaded).status()).toBe(200);
    await expect(duplicate.getByTestId('workspace-id')).not.toHaveText(await page.getByTestId('workspace-id').innerText());
    await expect(pinButton(duplicate)).toBeDisabled();
    await row(surface(duplicate).getByRole('table'), 1).getByRole('cell').nth(1).click();
    await expect(pinButton(duplicate)).toContainText('1'); await expect(pinButton(page)).toContainText('1');
    await expect(first).toHaveAttribute('aria-selected', 'true'); await expect(second).toHaveAttribute('aria-selected', 'false');
    await row(surface(duplicate).getByRole('table'), 1).focus(); await duplicate.keyboard.press('Enter');
    await expect(pinButton(duplicate)).toBeDisabled(); await expect(pinButton(page)).toBeEnabled();
  } finally { await duplicate.close(); }
});

test('selected logs span pages and process panes, persist as one described pin and support edit and deletion', async ({ page }) => {
  test.setTimeout(180000); await login(page); const { body, id } = await collect(page); const { input } = await resize(page, id);
  const results = surface(page); const selected: { event: Event; query: Query }[] = [{ event: body.items[0], query: input }];
  await row(results.getByRole('table')).getByRole('cell').nth(1).click();
  const next = queryResponse(page, id); await results.getByRole('button', { name: 'Next result page', exact: true }).click();
  const nextResponse = await next; expect(nextResponse.status()).toBe(200); const secondPage = await nextResponse.json() as Results;
  selected.push({ event: secondPage.items[0], query: nextResponse.request().postDataJSON() as Query });
  await row(results.getByRole('table')).getByRole('cell').nth(1).click(); await expect(pinButton(page)).toContainText('2');
  await results.getByLabel('Result layout', { exact: true }).selectOption('split');
  await expect(results.locator('.history-split > section[aria-busy="false"]')).toHaveCount(input.process_ids.length);
  const targetId = input.process_ids.find(processId => {
    const first = body.items.find(event => event.process_id === processId); return first && selected.every(entry => entry.event.event_id !== first.event_id);
  })!;
  expect(targetId).toBeTruthy();
  const target = results.locator(`.history-split > section[data-process-id="${targetId}"]`);
  const targetEvent = body.items.find(event => event.process_id === targetId)!;
  selected.push({ event: targetEvent, query: { ...input, process_ids: [targetId], cursor: null, per_process_filters: {} } });
  await row(target.getByRole('table')).getByRole('cell').nth(1).click(); await expect(pinButton(page)).toContainText('3');
  const picker = await processMenu(page); const choice = picker.locator(`input[data-process-id="${targetId}"]`);
  await choice.uncheck(); await expect(target).toBeHidden(); await expect(pinButton(page)).toContainText('3');
  await choice.check(); await expect(row(target.getByRole('table'))).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('Escape');
  await pinButton(page).click(); const dialog = page.getByRole('dialog', { name: 'Pin selected logs', exact: true });
  await expect(dialog.locator('[data-pin-event-id]')).toHaveCount(3);
  for (const { event } of selected) await expect(dialog.locator(`[data-pin-event-id="${event.event_id}"]`)).toHaveText(event.raw_line);
  await expect(dialog.locator('.pin-process-log')).toHaveCount(new Set(selected.map(entry => entry.event.process_id)).size);
  for (const group of await dialog.locator('.pin-process-log').all()) await expect(group.locator('pre')).toHaveCount(1);
  const description = 'Synthetic grouped pin: one description for three retained log entries.';
  await dialog.getByLabel('Pin description', { exact: true }).fill(description);
  const created = page.waitForResponse(response => response.url().endsWith(`/investigations/${id}/pins`) && response.request().method() === 'POST');
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  const saved = await created; expect(saved.status()).toBe(201);
  const payload = saved.request().postDataJSON() as { expected_revision: number; description: string; events: ReturnType<typeof expectedPinEvent>[] };
  expect(payload.description).toBe(description); expect(payload.events).toEqual(selected.map(({ event, query }) => expectedPinEvent(event, query)));
  const pins = await saved.json() as BookmarksWithPins; const group = pins.pin_groups!.find(pin => pin.description === description)!;
  expect(group.bookmark_ids).toHaveLength(3); expect(pins.items.filter(bookmark => group.bookmark_ids.includes(bookmark.bookmark_id)).every(bookmark => bookmark.pin_context && bookmark.context?.items.length === 1)).toBe(true);
  await expect(dialog).toHaveCount(0); await expect(pinButton(page)).toBeDisabled();
  const card = page.locator(`.pin-card[data-pin-id="${group.id}"]`);
  await expect(card).toContainText(description); await expect(card.locator('[data-pin-event-id], textarea')).toHaveCount(0);
  await expect(card.getByRole('button')).toHaveCount(1);
  await expect(page.getByRole('region', { name: 'Personal investigation tools', exact: true })).toHaveCount(1);
  const loaded = queryResponse(page, id); await page.reload(); expect((await loaded).status()).toBe(200);
  await expect(card).toContainText(description);
  await row(surface(page).getByRole('table')).getByRole('cell').nth(1).click();
  await expect(pinButton(page)).toContainText('1');
  await card.getByRole('button', { name: 'View', exact: true }).click();
  const view = page.getByRole('dialog', { name: 'View pin', exact: true });
  await expect(view.getByLabel('Pin description', { exact: true })).toHaveValue(description);
  for (const { event } of selected) await expect(view.locator(`[data-pin-event-id="${event.event_id}"]`)).toHaveText(event.raw_line);
  const edited = 'Edited shared description — all three pinned entries stay in this group.';
  await view.getByLabel('Pin description', { exact: true }).fill('Cancelled description');
  await view.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(card).toContainText(description);
  await card.getByRole('button', { name: 'View', exact: true }).click();
  await view.getByLabel('Pin description', { exact: true }).fill(edited);
  const updated = page.waitForResponse(response => response.url().endsWith(`/investigations/${id}/pins/${group.id}`) && response.request().method() === 'PATCH');
  await view.getByRole('button', { name: 'Save', exact: true }).click();
  const update = await updated; expect(update.status()).toBe(200); expect(update.request().postDataJSON()).toEqual({ expected_revision: pins.revision, description: edited });
  const editedState = await bookmarks(page, id); expect(editedState.pin_groups!.find(pin => pin.id === group.id)).toMatchObject({ description: edited, bookmark_ids: group.bookmark_ids });
  await expect(pinButton(page)).toContainText('1');
  const directory = resolve(root, 'verification/stage-7/screenshots'); mkdirSync(directory, { recursive: true });
  await card.screenshot({ path: resolve(directory, 'event-pin-described-group.png'), animations: 'disabled' });
  await expect(page.getByRole('region', { name: 'Personal investigation tools', exact: true })).toHaveCount(1);
  await deletePin(page, id, group.id);
  const removed = await bookmarks(page, id); expect(removed.pin_groups).toEqual([]); expect(removed.items).toHaveLength(0);
  await expect(pinButton(page)).toContainText('1');
});

test('one invalid selected event rejects the whole pin and leaves the dialog ready to retry', async ({ page }) => {
  test.setTimeout(180000); await login(page); const { id } = await collect(page);
  const table = surface(page).getByRole('table');
  await row(table).getByRole('cell').nth(1).click(); await row(table, 1).getByRole('cell').nth(1).click();
  const original = await bookmarks(page, id); expect(original.pin_groups).toEqual([]); expect(original.items).toHaveLength(0);
  await pinButton(page).click(); const dialog = page.getByRole('dialog', { name: 'Pin selected logs', exact: true });
  await dialog.getByLabel('Pin description', { exact: true }).fill('Synthetic atomic pin retry');
  const url = new URL(`/api/v1/projects/${system}/investigations/${id}/pins`, page.url()).href;
  // Forward the first request to the real API with one valid and one absent
  // event. The server must reject it before retaining any group or bookmark.
  await page.route(url, route => {
    const payload = route.request().postDataJSON() as { events: { event_id: string }[] };
    payload.events[1] = { ...payload.events[1], event_id: 'synthetic-missing-pin-event' };
    return route.continue({ postData: JSON.stringify(payload) });
  }, { times: 1 });
  const failed = page.waitForResponse(response => response.url() === url && response.request().method() === 'POST');
  await dialog.getByRole('button', { name: 'Save', exact: true }).click(); expect((await failed).status()).toBe(404);
  await expect(dialog.getByRole('alert')).toBeVisible(); await expect(dialog.locator('[data-pin-event-id]')).toHaveCount(2);
  await expect(dialog.getByLabel('Pin description', { exact: true })).toHaveValue('Synthetic atomic pin retry');
  expect(await bookmarks(page, id)).toEqual(original); await expect(dialog.getByRole('button', { name: 'Save', exact: true })).toBeEnabled();
  const retried = page.waitForResponse(response => response.url() === url && response.request().method() === 'POST');
  await dialog.getByRole('button', { name: 'Save', exact: true }).click(); const response = await retried; expect(response.status()).toBe(201);
  const saved = await response.json() as BookmarksWithPins; expect(saved.pin_groups).toHaveLength(1); expect(saved.items).toHaveLength(2);
  await expect(dialog).toHaveCount(0); await deletePin(page, id, saved.pin_groups![0].id);
});

test('Modify restores selection, then Pin explicitly updates the same pin or creates an independent copy', async ({ page }) => {
  test.setTimeout(180000); await login(page); const { id } = await collect(page);
  const { body } = await resize(page, id);
  const table = surface(page).getByRole('table');
  const sameProcessIndex = body.items.findIndex((event, index) => index > 0 && event.process_id === body.items[0].process_id);
  expect(sameProcessIndex).toBeGreaterThan(0);
  const replacementIndex = body.items.findIndex((_, index) => index > 0 && index !== sameProcessIndex);
  for (const index of [0, sameProcessIndex]) await row(table, index).getByRole('cell').nth(1).click();
  await pinButton(page).click();
  const editor = page.getByRole('dialog', { name: 'Pin selected logs', exact: true });
  await editor.getByLabel('Pin description', { exact: true }).fill('Original pin');
  const create = page.waitForResponse(response => response.url().endsWith(`/investigations/${id}/pins`) && response.request().method() === 'POST');
  await editor.getByRole('button', { name: 'Save', exact: true }).click();
  const initial = await (await create).json() as BookmarksWithPins;
  const original = initial.pin_groups![0];
  const card = page.locator(`.pin-card[data-pin-id="${original.id}"]`);
  await card.getByRole('button', { name: 'View', exact: true }).click();
  const view = page.getByRole('dialog', { name: 'View pin', exact: true });
  await expect(view.locator('.pin-process-log')).toHaveCount(1);
  await expect(view.locator('.pin-process-log pre')).toHaveCount(1);
  await expect(view.locator('.pin-process-log pre [data-pin-event-id]')).toHaveCount(2);
  const directory = resolve(root, 'verification/pin-range-check/screenshots'); mkdirSync(directory, { recursive: true });
  await view.screenshot({ path: resolve(directory, 'pin-same-process.png'), animations: 'disabled' });
  await view.getByLabel('Pin description', { exact: true }).fill('Updated pin and selection');
  const restored = queryResponse(page, id);
  await view.getByRole('button', { name: 'Modify', exact: true }).click();
  expect((await restored).status()).toBe(200);
  await expect(pinButton(page)).toContainText('2');
  await expect(row(table)).toHaveAttribute('aria-selected', 'true');
  await expect(row(table, sameProcessIndex)).toHaveAttribute('aria-selected', 'true');
  await row(table).getByRole('cell').nth(1).click();
  await row(table, replacementIndex).getByRole('cell').nth(1).click();
  await pinButton(page).click();
  const choice = page.getByRole('dialog', { name: 'Update the pin or create a new one?', exact: true });
  await expect(choice).toBeVisible();
  await choice.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect(await bookmarks(page, id)).toEqual(initial);
  await pinButton(page).click(); await choice.getByRole('button', { name: 'Update the pin', exact: true }).click();
  await expect(editor.getByLabel('Pin description', { exact: true })).toHaveValue('Updated pin and selection');
  const patched = page.waitForResponse(response => response.url().endsWith(`/investigations/${id}/pins/${original.id}`) && response.request().method() === 'PATCH');
  await editor.getByRole('button', { name: 'Save', exact: true }).click();
  const response = await patched; expect(response.status()).toBe(200);
  const changed = await response.json() as BookmarksWithPins;
  expect(changed.pin_groups).toHaveLength(1);
  expect(changed.pin_groups![0]).toMatchObject({ id: original.id, created_us: original.created_us, description: 'Updated pin and selection' });
  expect(changed.items.map(bookmark => bookmark.event_id).sort()).toEqual([body.items[sameProcessIndex].event_id, body.items[replacementIndex].event_id].sort());
  await expect(card).toContainText('Updated pin and selection');
  await card.getByRole('button', { name: 'View', exact: true }).click();
  const again = queryResponse(page, id); await view.getByRole('button', { name: 'Modify', exact: true }).click(); expect((await again).status()).toBe(200);
  await pinButton(page).click(); await choice.getByRole('button', { name: 'Create a new pin', exact: true }).click();
  await editor.getByLabel('Pin description', { exact: true }).fill('Independent copy');
  const copied = page.waitForResponse(value => value.url().endsWith(`/investigations/${id}/pins`) && value.request().method() === 'POST');
  await editor.getByRole('button', { name: 'Save', exact: true }).click(); expect((await copied).status()).toBe(201);
  const final = await bookmarks(page, id);
  expect(final.pin_groups).toHaveLength(2); expect(final.pin_groups!.find(pin => pin.id === original.id)).toEqual(changed.pin_groups![0]);
  await expect(page.getByRole('region', { name: 'Personal investigation tools', exact: true })).toHaveCount(1);
  await expect(page.locator('.pin-card')).toHaveCount(2);
  for (const theme of ['light', 'dark']) {
    await page.evaluate(value => document.documentElement.dataset.theme = value, theme);
    for (const width of [1280, 1920]) {
      await page.setViewportSize({ width, height: width === 1280 ? 720 : 1080 });
      await card.getByRole('button', { name: 'View', exact: true }).click();
      await view.screenshot({ path: resolve(directory, `pin-${theme}-${width}.png`), animations: 'disabled' });
      await view.getByRole('button', { name: 'Cancel', exact: true }).click();
    }
  }
  for (const pin of final.pin_groups!) await deletePin(page, id, pin.id);
  for (let reopen = 0; reopen < 3; reopen += 1) {
    const loaded = queryResponse(page, id); await page.reload(); expect((await loaded).status()).toBe(200);
    await expect(page.getByRole('region', { name: 'Personal investigation tools', exact: true })).toHaveCount(1);
    await expect(page.locator('.pin-card')).toHaveCount(0);
  }
});
