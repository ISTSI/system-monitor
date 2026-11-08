import { expect, test, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

test.skip(({ baseURL }) => baseURL !== 'http://127.0.0.1:5190', 'Requires the isolated source-only Help browser configuration.');

// Intercepts only test API fixtures; renders the real App, top bar and Help.
async function syntheticAccount(page: Page, role: 'administrator' | 'inspector', language: 'en' | 'pl') {
  const unexpected: string[] = [];
  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const bodies: Record<string, unknown> = {
      '/api/v1/ui/bootstrap': { branding: 'System Inspector', default_theme_mode: 'dark', default_language: language, demo_mode: false, historical_demo_enabled: false },
      '/api/v1/auth/session': { user_id: 'test-only-help-user', username: 'test-only-help', display_name: 'Synthetic Help account', role, must_change_password: false },
      '/api/v1/me/preferences': { theme_mode: 'dark', language, revision: 1 },
      '/api/v1/projects': { items: [] },
    };
    if (request.method() !== 'GET' || !Object.hasOwn(bodies, path)) { unexpected.push(`${request.method()} ${path}`); return route.fulfill({ status: 500, json: { error: { code: 'TEST_UNEXPECTED', message: 'Unexpected test operation.' } } }); }
    await route.fulfill({ json: bodies[path] });
  });
  return unexpected;
}

for (const role of ['administrator', 'inspector'] as const) for (const language of ['en', 'pl'] as const) {
  test(`${role} ${language}: top-menu Help works offline, is complete, searchable and preserves the page`, async ({ page }) => {
    const failures: string[] = []; const external: string[] = [];
    page.on('pageerror', error => failures.push(error.message));
    await page.route('**/*', async route => {
      if (new URL(route.request().url()).origin !== 'http://127.0.0.1:5190') { external.push(route.request().url()); return route.abort(); }
      return route.fallback();
    });
    const unexpected = await syntheticAccount(page, role, language);
    await page.goto('/');
    const find = page.getByRole('textbox', { name: language === 'en' ? 'Find a system' : 'Znajdź system', exact: true });
    await find.fill('page-owned-unsaved-search');
    const trigger = page.getByRole('button', { name: language === 'en' ? 'Help' : 'Pomoc', exact: true });
    await trigger.click();
    const dialog = page.getByRole('dialog', { name: language === 'en' ? 'Help' : 'Pomoc', exact: true });
    await expect(dialog).toBeVisible();
    const chapters = dialog.getByRole('navigation').getByRole('button');
    await expect(chapters).toHaveCount(9);
    for (let index = 0; index < 9; index++) {
      await chapters.nth(index).click();
      await expect(dialog.locator('article h3')).toHaveText(await chapters.nth(index).innerText());
      await expect(chapters.nth(index)).toHaveAttribute('aria-current', 'page');
      expect(await dialog.locator('article p').count()).toBeGreaterThan(0);
      expect(await chapters.nth(index).evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    }
    const search = dialog.getByRole('searchbox');
    await search.fill('FXF_READ');
    await expect(chapters).toHaveCount(1);
    await expect(dialog.locator('article')).toContainText(language === 'en' ? 'zero remote shell commands' : 'żadnych zdalnych poleceń powłoki');
    await expect(dialog.locator('dt')).toHaveCount(11);
    await expect(dialog.locator('article')).toContainText('handle.read(length, offset)');
    await search.fill('no-such-help-topic-94682');
    await expect(dialog.getByRole('status')).toHaveText(language === 'en' ? 'No Help chapters match. Try another term.' : 'Brak pasujących rozdziałów Pomocy. Spróbuj innego hasła.');
    await search.fill(language === 'en' ? 'server: prerequisites' : 'serwer: wymagania');
    await expect(chapters).toHaveCount(1);
    await expect(dialog.locator('article')).toContainText(language === 'en' ? 'No connection is the default' : 'Domyślne Brak połączenia');
    await search.fill('');
    await chapters.nth(7).click();
    mkdirSync(resolve('../verification/stage-8/screenshots'), { recursive: true });
    for (const theme of ['light', 'dark']) {
      await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
      await page.screenshot({ path: resolve(`../verification/stage-8/screenshots/help-${role}-${language}-${theme}.png`), animations: 'disabled' });
      expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    }
    await page.setViewportSize({ width: 640, height: 360 });
    expect(await dialog.evaluate(element => { const bounds = element.getBoundingClientRect(); return bounds.left >= 0 && bounds.right <= innerWidth && bounds.bottom <= innerHeight && element.scrollWidth <= element.clientWidth; })).toBe(true);
    await expect(dialog.getByRole('button', { name: language === 'en' ? 'Close dialog' : 'Zamknij okno dialogowe', exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expect(find).toHaveValue('page-owned-unsaved-search');
    expect(unexpected).toEqual([]); expect(external).toEqual([]); expect(failures).toEqual([]);
  });
}
