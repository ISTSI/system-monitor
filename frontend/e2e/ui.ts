import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import type { components } from '../src/api/schema';

type HistoricalFiltersInput = Partial<Pick<components['schemas']['HistoricalQueryInput'], 'from' | 'to' | 'filter' | 'per_process_filters'>>;

export async function setHistoricalCollectionRange(page: Page, input: { from: string; to: string }): Promise<void> {
  const range = page.getByRole('group', { name: 'Collection time range', exact: true });
  await range.getByLabel('From UTC (inclusive)', { exact: true }).fill(input.from);
  await range.getByLabel('To UTC (exclusive)', { exact: true }).fill(input.to);
}

export async function openHistoricalFilters(page: Page) {
  await page.getByRole('button', { name: 'Filters', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Filters', exact: true });
  await expect(dialog).toBeVisible();
  return dialog;
}

export async function fillHistoricalFilters(page: Page, input: HistoricalFiltersInput) {
  const dialog = await openHistoricalFilters(page);
  if (input.from !== undefined) await dialog.getByLabel('From UTC (inclusive)', { exact: true }).fill(input.from);
  if (input.to !== undefined) await dialog.getByLabel('To UTC (exclusive)', { exact: true }).fill(input.to);
  if (input.filter !== undefined || input.per_process_filters !== undefined) {
    const clear = dialog.getByRole('button', { name: 'Clear content filters', exact: true });
    if (await clear.isEnabled()) await clear.click();
    const scopes: [string, components['schemas']['HistoricalFilter'] | undefined][] = [['', input.filter], ...Object.entries(input.per_process_filters ?? {})];
    for (const [scope, filter] of scopes) {
      if (!filter) continue;
      await dialog.getByLabel('Filter scope', { exact: true }).selectOption(scope);
      if (scope) {
        const matching = dialog.locator('details');
        if (await matching.getAttribute('open') === null) await matching.locator('summary').click();
        await dialog.getByLabel('Process include matching', { exact: true }).selectOption(filter.include_mode);
        await dialog.getByLabel('Process case sensitive', { exact: true }).setChecked(filter.case_sensitive);
      } else {
        await dialog.getByLabel('Global include matching', { exact: true }).selectOption(filter.include_mode);
        await dialog.getByLabel('Global case sensitive', { exact: true }).setChecked(filter.case_sensitive);
      }
      for (const kind of ['include', 'exclude'] as const) {
        await dialog.getByLabel('Filter action', { exact: true }).selectOption(kind);
        for (const term of filter[kind] ?? []) {
          await dialog.getByLabel('Log content', { exact: true }).fill(term);
          await dialog.getByRole('button', { name: 'Add filter', exact: true }).click();
        }
      }
    }
  }
  return dialog;
}

export async function applyHistoricalFilters(page: Page): Promise<void> {
  const dialog = page.getByRole('dialog', { name: 'Filters', exact: true });
  await dialog.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect(dialog).toHaveCount(0);
}

export async function setHistoricalFilters(page: Page, input: HistoricalFiltersInput): Promise<void> {
  await fillHistoricalFilters(page, input);
  await applyHistoricalFilters(page);
}

export async function expectHistoricalContentFilters(page: Page, expected: string[]): Promise<void> {
  const dialog = await openHistoricalFilters(page);
  expect(await dialog.locator('.history-filter-list code').allTextContents()).toEqual(expected);
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(dialog).toHaveCount(0);
}

// Opt-in source verification against a running local API without replacing its
// deployed bundle. Every page in the context uses the same fresh build.
export async function serveBuiltAssets(context: BrowserContext, baseURL: string): Promise<void> {
  // Installed-preview verification must exercise the files served by HTTPS.
  if (process.env.INSPECTOR_E2E_SERVED_ASSETS === '1') return;
  const directory = resolve(process.env.INSPECTOR_E2E_ASSET_DIR ?? 'dist');
  if (!existsSync(resolve(directory, 'index.html'))) throw new Error('Build the frontend before enabling local browser assets.');
  const origin = new URL(baseURL).origin;
  await context.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin || request.method() !== 'GET' || url.pathname.startsWith('/api/')) return route.fallback();
    if (request.resourceType() === 'document') return route.fulfill({ path: resolve(directory, 'index.html'), contentType: 'text/html' });
    if (/^\/assets\/[a-zA-Z0-9_.-]+$/.test(url.pathname)) {
      const filename = resolve(directory, url.pathname.slice(1));
      if (existsSync(filename)) return route.fulfill({ path: filename });
    }
    return route.fallback();
  });
}

export async function submitSignIn(page: Page) {
  const submit = async () => {
    const response = page.waitForResponse(value => new URL(value.url()).pathname === '/api/v1/auth/login' && value.request().method() === 'POST');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    return response;
  };
  let response = await submit();
  if (response.status() === 429) {
    test.info().annotations.push({ type: 'rate-limit', description: 'The real login limit returned 429; waited 60 seconds for one bounded retry.' });
    test.info().setTimeout(test.info().timeout + 65000);
    console.log('Login limit returned 429; preserving the production limit and waiting 60 seconds for one retry.');
    await page.waitForTimeout(60000);
    response = await submit();
  }
  return response;
}

export async function systemAction(page: Page, name: string): Promise<void> {
  await page.getByRole('button', { name: 'System', exact: true }).click();
  await page.getByRole('menuitem', { name, exact: true }).click();
}

export async function openPreferences(page: Page) {
  if (await page.locator('.account-menu').getAttribute('open') === null) await page.locator('.account-menu > summary').click();
  await page.getByRole('button', { name: 'Preferences', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Preferences', exact: true });
  await expect(dialog).toBeVisible();
  return dialog;
}

// Appearance is intentionally account-wide. A second page exercises the real
// Preferences control without dismissing the first page's form or investigation.
export async function setAppearance(page: Page, mode: 'light' | 'dark' | 'system' | 'default'): Promise<void> {
  const settingsPage = await page.context().newPage();
  try {
    await settingsPage.goto('/');
    const preferences = await openPreferences(settingsPage);
    const appearance = preferences.getByLabel('Appearance', { exact: true });
    await expect(appearance).toBeEnabled();
    await appearance.selectOption(mode);
    await expect(appearance).toBeEnabled();
    if (mode === 'light' || mode === 'dark') await expect(page.locator('html')).toHaveAttribute('data-theme', mode);
  } finally {
    await settingsPage.close();
  }
}

export async function editSystemDetails(page: Page, projectId: string): Promise<void> {
  await page.getByRole('link', { name: 'Admin', exact: true }).click();
  const card = page.locator(`.system-card[data-project-id="${projectId}"]`);
  await card.getByRole('button', { name: /^Edit system details for / }).click();
}
