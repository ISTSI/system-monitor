import { test, expect, type BrowserContext, type Page } from '@playwright/test';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

type Role = 'administrator' | 'inspector';
type Account = { username: string; password: string };
type Accounts = Record<Role, Account>;
const screenshots = resolve('../verification/stage-1/screenshots');
const systemA = 'demo-foundation-a';
const systemB = 'demo-foundation-b';
const workspacePattern = /^[0-9a-f]{8}-[0-9a-f-]{27}$/;

const createdWorkspaces = new WeakMap<BrowserContext, { project_id: string; workspace_id: string }[]>();
test.beforeEach(({ context }) => {
  const created: { project_id: string; workspace_id: string }[] = [];
  createdWorkspaces.set(context, created);
  context.on('response', response => {
    if (response.request().method() === 'POST' && /\/projects\/[^/]+\/workspaces$/.test(new URL(response.url()).pathname) && response.status() === 201) {
      void response.json().then((value: { project_id: string; workspace_id: string }) => created.push(value));
    }
  });
});
test.afterEach(async ({ context, baseURL }) => {
  const response = await context.request.get('/api/v1/auth/csrf');
  if (response.status() !== 200) return;
  const value = await response.json() as { csrf_token: string };
  for (const workspace of createdWorkspaces.get(context) ?? []) {
    await context.request.post(`/api/v1/projects/${workspace.project_id}/workspaces/${workspace.workspace_id}/detach`, {
      headers: { Origin: new URL(baseURL!).origin, 'X-CSRF-Token': value.csrf_token }, data: {},
    });
  }
});

function account(role: Role): Account {
  const filename = process.env.INSPECTOR_E2E_ACCOUNTS;
  if (!filename) throw new Error('Set INSPECTOR_E2E_ACCOUNTS to the protected synthetic-account fixture file.');
  const data = JSON.parse(readFileSync(resolve(filename), 'utf8')) as Accounts;
  if (!data[role]?.username || !data[role]?.password) throw new Error('Synthetic browser account fixture is incomplete.');
  return data[role];
}

async function login(page: Page, role: Role): Promise<void> {
  const credentials = account(role);
  await page.goto('/');
  await page.getByLabel('Username', { exact: true }).fill(credentials.username);
  try {
    await page.getByLabel('Password', { exact: true }).fill(credentials.password);
    const submit = async () => {
      const submitted = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/auth/login' && response.request().method() === 'POST');
      await page.getByRole('button', { name: 'Sign in', exact: true }).click();
      return submitted;
    };
    let response = await submit();
    if (response.status() === 429) {
      test.info().annotations.push({ type: 'rate-limit', description: 'The real login limit returned 429; waited 60 seconds for one bounded retry.' });
      test.info().setTimeout(test.info().timeout + 65000);
      console.log('Login limit returned 429; preserving the production limit and waiting 60 seconds for one retry.');
      await page.waitForTimeout(60000);
      response = await submit();
    }
    expect(response.status()).toBe(200);
    await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
  } catch {
    await page.evaluate(() => {
      document.querySelectorAll<HTMLInputElement>('input[type="password"]').forEach(input => { input.value = ''; });
    }).catch(() => { /* A closed page contains no accessible password control. */ });
    throw new Error('Synthetic sign-in failed; sensitive browser detail withheld.');
  }
}

async function openSystem(page: Page, id: string): Promise<string> {
  await page.goto(`/systems/${id}/topology`);
  await expect(page.getByLabel('System selector')).toHaveValue(id);
  const workspace = page.getByTestId('workspace-id');
  await expect(workspace).toHaveText(workspacePattern);
  return (await workspace.innerText()).trim();
}

async function screenshot(page: Page, name: string): Promise<void> {
  mkdirSync(screenshots, { recursive: true });
  await page.screenshot({ path: resolve(screenshots, name + '.png'), fullPage: false, animations: 'disabled' });
}

async function appearance(page: Page, theme: 'light' | 'dark' | 'system' | 'default'): Promise<void> {
  await expect(page.getByLabel('Appearance', { exact: true })).toBeEnabled();
  await page.getByLabel('Appearance', { exact: true }).selectOption(theme);
  await expect(page.getByLabel('Appearance', { exact: true })).toBeEnabled();
  if (theme === 'light' || theme === 'dark') await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
}

async function csrf(page: Page): Promise<string> {
  const response = await page.request.get('/api/v1/auth/csrf');
  expect(response.status()).toBe(200);
  const body = await response.json() as { csrf_token: string };
  return body.csrf_token;
}

function forbidExternalRequests(context: BrowserContext): string[] {
  const external: string[] = [];
  context.on('request', request => {
    const url = new URL(request.url());
    if (!['localhost', '127.0.0.1'].includes(url.hostname) && url.protocol !== 'data:') external.push(url.origin);
  });
  return external;
}

for (const role of ['administrator', 'inspector'] as const) {
  test(`${role} uses both themes at supported desktop sizes with local assets`, async ({ page, context }) => {
    const external = forbidExternalRequests(context);
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      return ['localhost', '127.0.0.1'].includes(url.hostname) ? route.continue() : route.abort();
    });
    await login(page, role);
    for (const viewport of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
      await page.setViewportSize(viewport);
      for (const theme of ['light', 'dark'] as const) {
        await appearance(page, theme);
        await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
        await screenshot(page, `${role}-${theme}-${viewport.width}x${viewport.height}-catalogue`);
      }
    }
    await openSystem(page, systemA);
    const firstProcess = page.getByRole('button', { name: /^Select process / }).first();
    await firstProcess.focus();
    await page.keyboard.press('Enter');
    await expect(firstProcess).toHaveAttribute('aria-pressed', 'true');
    for (const viewport of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
      await page.setViewportSize(viewport);
      for (const theme of ['light', 'dark'] as const) {
        await appearance(page, theme);
        await expect(page.locator('.subsystem-card')).toHaveCount(2);
        await expect(page.getByRole('region', { name: 'Process details' })).toBeVisible();
        await expect(page.getByRole('button', { name: 'Edit system details', exact: true })).toHaveCount(role === 'administrator' ? 1 : 0);
        await expect(page.getByRole('button', { name: 'Settings', exact: true })).toHaveCount(role === 'administrator' ? 1 : 0);
        await screenshot(page, `${role}-${theme}-${viewport.width}x${viewport.height}-topology-process`);
        const hasHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
        expect(hasHorizontalOverflow).toBe(false);
      }
    }
    expect(external).toEqual([]);
  });
}

test('two pages in one browser context keep different systems and searches independent', async ({ page, context }) => {
  await login(page, 'inspector');
  const firstWorkspace = await openSystem(page, systemA);
  const separate = page.getByRole('link', { name: 'Open this system in a new tab' });
  await expect(separate).toHaveAttribute('target', '_blank');
  await expect(separate).toHaveAttribute('rel', 'noopener noreferrer');
  const second = await context.newPage();
  const secondWorkspace = await openSystem(second, systemB);
  expect(secondWorkspace).not.toBe(firstWorkspace);
  const wrongScope = await second.request.get(`/api/v1/projects/${systemA}/workspaces/${secondWorkspace}`);
  expect(wrongScope.status()).toBe(404);
  const mismatchedScope = await second.request.post(`/api/v1/projects/${systemA}/workspaces`, {
    headers: { Origin: new URL(second.url()).origin, 'X-CSRF-Token': await csrf(second) },
    data: { project_id: systemB },
  });
  expect(mismatchedScope.status()).toBe(422);
  await page.getByLabel('Search this system', { exact: true }).fill('only-in-window-a');
  await expect(second.getByLabel('Search this system', { exact: true })).toHaveValue('');
  await expect(second.locator('.process-card')).not.toHaveCount(0);
  await page.getByLabel('System selector').selectOption(systemB);
  await expect(page.getByLabel('System selector')).toHaveValue(systemB);
  await expect(second.getByTestId('workspace-id')).toHaveText(secondWorkspace);
  await expect(second).toHaveURL(new RegExp(`/systems/${systemB}/topology$`));
  await second.close();
});

test('duplicate same-system page has a fresh workspace and isolated selection; logout clears both', async ({ page, context }) => {
  await login(page, 'inspector');
  const original = await openSystem(page, systemA);
  const duplicate = await context.newPage();
  const firstDuplicateWorkspace = await openSystem(duplicate, systemA);
  await duplicate.reload();
  await expect(duplicate.getByTestId('workspace-id')).toHaveText(workspacePattern);
  await expect(duplicate.getByTestId('workspace-id')).not.toHaveText(firstDuplicateWorkspace);
  const duplicateWorkspace = (await duplicate.getByTestId('workspace-id').innerText()).trim();
  expect(duplicateWorkspace).not.toBe(original);
  await page.getByRole('button', { name: /^Select process / }).first().click();
  await expect(duplicate.getByRole('heading', { name: 'Select a process', exact: true })).toBeVisible();
  await page.getByLabel('Search this system', { exact: true }).fill('kept in this page');
  await appearance(page, 'light');
  await expect(duplicate.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.getByTestId('workspace-id')).toHaveText(original);
  await expect(duplicate.getByTestId('workspace-id')).toHaveText(duplicateWorkspace);
  await expect(page.getByLabel('Search this system', { exact: true })).toHaveValue('kept in this page');
  await page.locator('.account-menu summary').click();
  await page.getByRole('button', { name: 'Sign out all windows', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await expect(duplicate.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await expect(duplicate.getByTestId('workspace-id')).toHaveCount(0);
  await duplicate.close();
});

test('administrator unsaved form and workspace survive theme change and keyboard focus', async ({ page, context }) => {
  await login(page, 'administrator');
  const workspace = await openSystem(page, systemA);
  await page.getByRole('button', { name: 'Edit system details', exact: true }).click();
  await page.getByLabel('System name', { exact: true }).fill('Unsaved synthetic draft');
  const second = await context.newPage();
  await second.goto('/');
  await appearance(second, 'dark');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.getByLabel('System name', { exact: true })).toHaveValue('Unsaved synthetic draft');
  await expect(page.getByTestId('workspace-id')).toHaveText(workspace);
  await page.bringToFront();
  await page.getByLabel('System name', { exact: true }).focus();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('textbox', { name: 'Description', exact: true })).toBeFocused();
  await screenshot(page, 'administrator-dark-unsaved-system-dialog');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await second.close();
  await appearance(page, 'system');
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

test('forged Inspector writes and missing CSRF cannot change shared state', async ({ page }) => {
  await login(page, 'inspector');
  const origin = new URL(page.url()).origin;
  const token = await csrf(page);
  const before = await page.request.get(`/api/v1/projects/${systemA}`);
  expect(before.status()).toBe(200);
  const prior = await before.json() as { name: string; revision: number };
  const denied = await page.request.patch(`/api/v1/projects/${systemA}/metadata`, {
    headers: { Origin: origin, 'X-CSRF-Token': token },
    data: { name: 'FORGED', description: '', expected_revision: prior.revision },
  });
  expect(denied.status()).toBe(403);
  const absentCsrf = await page.request.post('/api/v1/projects', {
    headers: { Origin: origin }, data: { name: 'FORGED', description: '' },
  });
  expect(absentCsrf.status()).toBe(403);
  const preferences = await page.request.get('/api/v1/me/preferences');
  const prefs = await preferences.json() as { revision: number };
  const massAssignment = await page.request.patch('/api/v1/me/preferences', {
    headers: { Origin: origin, 'X-CSRF-Token': token },
    data: { theme_mode: 'light', expected_revision: prefs.revision, role: 'administrator' },
  });
  expect(massAssignment.status()).toBe(422);
  const after = await page.request.get(`/api/v1/projects/${systemA}`);
  const current = await after.json() as { name: string; revision: number };
  expect(current.name).toBe(prior.name);
  expect(current.revision).toBe(prior.revision);
});

test('late preference bootstrap cannot restore protected content after account-wide logout', async ({ page, context }) => {
  await login(page, 'inspector');
  const stalled = await context.newPage();
  let releaseResponse!: () => void;
  let capturedResponse!: () => void;
  const released = new Promise<void>(resolve => { releaseResponse = resolve; });
  const captured = new Promise<void>(resolve => { capturedResponse = resolve; });
  await stalled.route('**/api/v1/me/preferences', async route => {
    const response = await route.fetch();
    capturedResponse();
    await released;
    await route.fulfill({ response });
  });
  try {
    await stalled.goto('/');
    await captured;
    await page.locator('.account-menu summary').click();
    await page.getByRole('button', { name: 'Sign out all windows', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
    await stalled.evaluate(() => {
      const state = { protectedRendered: false };
      Object.assign(window, { __authRegression: state });
      new MutationObserver(() => {
        if (document.querySelector('.application, .mode-strip, .workspace-page')) state.protectedRendered = true;
      }).observe(document.documentElement, { childList: true, subtree: true });
    });
    const delivered = stalled.waitForResponse('**/api/v1/me/preferences');
    releaseResponse();
    await (await delivered).finished();
    await stalled.evaluate(async () => {
      await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
    });
    await expect(stalled.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
    expect(await stalled.evaluate(() => (window as unknown as { __authRegression: { protectedRendered: boolean } }).__authRegression.protectedRendered)).toBe(false);
    await expect(stalled.locator('.application, .mode-strip, .workspace-page')).toHaveCount(0);
  } finally {
    releaseResponse();
    await stalled.close();
  }
});

test('old unauthorized response cannot clear a new login or its CSRF token', async ({ page }) => {
  await login(page, 'inspector');
  let capturedRequest!: () => void;
  let fetchOld!: () => void;
  let capturedResponse!: () => void;
  let releaseResponse!: () => void;
  const requestCaptured = new Promise<void>(resolve => { capturedRequest = resolve; });
  const mayFetch = new Promise<void>(resolve => { fetchOld = resolve; });
  const responseCaptured = new Promise<void>(resolve => { capturedResponse = resolve; });
  const released = new Promise<void>(resolve => { releaseResponse = resolve; });
  let held = false;
  await page.route('**/api/v1/auth/session', async route => {
    if (held) { await route.continue(); return; }
    held = true;
    capturedRequest();
    await mayFetch;
    const response = await route.fetch();
    if (response.status() !== 401) throw new Error('Expected a real revoked-session response.');
    capturedResponse();
    await released;
    await route.fulfill({ response });
  });
  try {
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await requestCaptured;
    await page.locator('.account-menu summary').click();
    await page.getByRole('button', { name: 'Sign out all windows', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
    fetchOld();
    await responseCaptured;
    const credentials = account('inspector');
    await page.getByLabel('Username', { exact: true }).fill(credentials.username);
    try {
      await page.getByLabel('Password', { exact: true }).fill(credentials.password);
      await page.getByRole('button', { name: 'Sign in', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
    } catch {
      await page.evaluate(() => {
        document.querySelectorAll<HTMLInputElement>('input[type="password"]').forEach(input => { input.value = ''; });
      }).catch(() => {});
      throw new Error('Synthetic reauthentication failed; sensitive browser detail withheld.');
    }
    await page.evaluate(() => {
      const state = { loginRendered: false };
      Object.assign(window, { __stale401: state });
      new MutationObserver(() => {
        if (document.querySelector('.login-layout')) state.loginRendered = true;
      }).observe(document.documentElement, { childList: true, subtree: true });
    });
    const delivered = page.waitForResponse('**/api/v1/auth/session');
    releaseResponse();
    await (await delivered).finished();
    await page.evaluate(async () => {
      await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
    });
    expect(await page.evaluate(() => (window as unknown as { __stale401: { loginRendered: boolean } }).__stale401.loginRendered)).toBe(false);
    await expect(page.getByRole('heading', { name: 'Your systems, in context.' })).toBeVisible();
    const preferenceSaved = page.waitForResponse(response => response.url().endsWith('/api/v1/me/preferences') && response.request().method() === 'PATCH');
    await appearance(page, 'light');
    expect((await preferenceSaved).status()).toBe(200);
    expect((await page.request.get('/api/v1/projects')).status()).toBe(200);
  } finally {
    fetchOld();
    releaseResponse();
  }
});

test.describe('200 percent layout equivalent', () => {
  test.use({ viewport: { width: 640, height: 360 }, deviceScaleFactor: 2 });

  test('primary controls and process details remain reachable at CSS 640x360 and DPR 2', async ({ page }) => {
    const noHorizontalOverflow = async () => {
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    };
    await login(page, 'administrator');
    await noHorizontalOverflow();
    const settings = page.getByRole('button', { name: 'Settings', exact: true });
    await settings.focus();
    await page.keyboard.press('Enter');
    const dialog = page.getByRole('dialog', { name: 'Application settings', exact: true });
    await expect(dialog).toBeVisible();
    const save = page.getByRole('button', { name: 'Save application settings', exact: true });
    await save.scrollIntoViewIfNeeded();
    await save.focus();
    await expect(save).toBeFocused();
    await expect(save).toBeInViewport();
    await noHorizontalOverflow();
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await page.getByLabel('Appearance', { exact: true }).focus();
    await expect(page.getByLabel('Appearance', { exact: true })).toBeFocused();
    await appearance(page, 'light');
    await openSystem(page, systemA);
    const process = page.getByRole('button', { name: /^Select process / }).first();
    await process.focus();
    await expect(process).toBeInViewport();
    await page.keyboard.press('Enter');
    await expect(process).toHaveAttribute('aria-pressed', 'true');
    const details = page.getByRole('heading', { name: 'Process details', exact: true });
    await details.scrollIntoViewIfNeeded();
    await expect(details).toBeInViewport();
    await noHorizontalOverflow();
    await screenshot(page, 'administrator-light-zoom-200-css640x360-dpr2');
  });
});

test('Administrator creates and edits two colliding system names through real forms with independent persistence', async ({ page, context }) => {
  await login(page, 'administrator');
  const second = await context.newPage();
  const suffix = Date.now().toString(36);
  const sharedName = `[Synthetic browser test] Collision ${suffix}`;
  const descriptionA = `Synthetic browser system A original ${suffix}`;
  const descriptionB = `Synthetic browser system B original ${suffix}`;
  const editedA = `Synthetic browser system A revised ${suffix}`;
  const createdIds: string[] = [];
  const retained: { project_id: string; name: string; description: string; revision: number; archived: boolean }[] = [];
  let verified = false;
  async function createThroughForm(target: Page, description: string): Promise<string> {
    await target.goto('/');
    await target.getByRole('button', { name: '+ Create system', exact: true }).click();
    const dialog = target.getByRole('dialog', { name: 'Create system', exact: true });
    await dialog.getByRole('textbox', { name: 'System name', exact: true }).fill(sharedName);
    await dialog.getByRole('textbox', { name: 'Description', exact: true }).fill(description);
    const saved = target.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/projects' && response.request().method() === 'POST');
    await dialog.getByRole('button', { name: 'Create system', exact: true }).click();
    const response = await saved;
    expect(response.status()).toBe(201);
    const created = await response.json() as { project_id: string; revision: number };
    createdIds.push(created.project_id);
    expect(created.revision).toBe(1);
    await expect(target.getByLabel('System selector')).toHaveValue(created.project_id);
    await expect(target.getByTestId('workspace-id')).toHaveText(workspacePattern);
    await expect(target.getByRole('heading', { name: sharedName, exact: true })).toBeVisible();
    await expect(target.locator('.workspace-heading .muted')).toHaveText(description);
    await expect(target.getByRole('heading', { name: 'Your system starts here', exact: true })).toBeVisible();
    await expect(target.locator('.subsystem-card')).toHaveCount(0);
    return created.project_id;
  }
  try {
    const firstId = await createThroughForm(page, descriptionA);
    const secondId = await createThroughForm(second, descriptionB);
    expect(firstId).not.toBe(secondId);
    await page.getByRole('button', { name: 'Edit system details', exact: true }).click();
    const edit = page.getByRole('dialog', { name: 'Edit system details', exact: true });
    await expect(edit.locator('.target-system code')).toHaveText(firstId);
    await edit.getByRole('textbox', { name: 'Description', exact: true }).fill(editedA);
    await edit.getByRole('button', { name: 'Save system details', exact: true }).click();
    await expect(edit).toHaveCount(0);
    await expect(page.locator('.workspace-heading .muted')).toHaveText(editedA);
    await expect(page.locator('.workspace-toolbar .revision')).toHaveText('Revision 2');
    await expect(second.locator('.workspace-heading .muted')).toHaveText(descriptionB);
    await expect(second.locator('.workspace-toolbar .revision')).toHaveText('Revision 1');
    await Promise.all([page.reload(), second.reload()]);
    for (const [target, id, description, revision] of [
      [page, firstId, editedA, 2], [second, secondId, descriptionB, 1],
    ] as const) {
      await expect(target.getByLabel('System selector')).toHaveValue(id);
      await expect(target.getByTestId('workspace-id')).toHaveText(workspacePattern);
      await expect(target.getByRole('heading', { name: sharedName, exact: true })).toBeVisible();
      await expect(target.locator('.workspace-heading .muted')).toHaveText(description);
      await expect(target.locator('.workspace-toolbar .revision')).toHaveText(`Revision ${revision}`);
      await expect(target).toHaveURL(new RegExp(`/systems/${id}/topology$`));
      const response = await target.request.get(`/api/v1/projects/${id}`);
      expect(response.status()).toBe(200);
      const persisted = await response.json() as { project_id: string; name: string; description: string; revision: number; subsystems: unknown[] };
      expect(persisted).toMatchObject({ project_id: id, name: sharedName, description, revision, subsystems: [] });
    }
    verified = true;
  } finally {
    const origin = new URL(page.url()).origin;
    const token = await csrf(page);
    for (const id of createdIds) {
      const response = await page.request.get(`/api/v1/projects/${id}`);
      expect(response.status()).toBe(200);
      const current = await response.json() as { revision: number; archived: boolean };
      if (!current.archived) {
        const archived = await page.request.post(`/api/v1/projects/${id}/archive`, {
          headers: { Origin: origin, 'X-CSRF-Token': token }, data: { expected_revision: current.revision },
        });
        expect(archived.status()).toBe(200);
      }
      const kept = await page.request.get(`/api/v1/projects/${id}`);
      expect(kept.status()).toBe(200);
      const value = await kept.json() as { project_id: string; name: string; description: string; revision: number; archived: boolean };
      expect(value.archived).toBe(true);
      retained.push({ project_id: value.project_id, name: value.name, description: value.description, revision: value.revision, archived: value.archived });
    }
    writeFileSync(resolve('../verification/stage-1/browser-mutation-state.json'), JSON.stringify({
      verified, created_via_browser_forms: createdIds, same_display_name: sharedName,
      independent_description_and_revision_after_refresh: verified,
      cleanup: 'Archived only these newly created synthetic systems; history retained.', retained,
    }, null, 2) + '\n');
    await second.close();
  }
});
