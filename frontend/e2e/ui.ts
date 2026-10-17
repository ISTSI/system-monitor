import { expect, test, type Page } from '@playwright/test';

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

// Appearance is intentionally account-wide. A second page exercises the real
// Settings control without dismissing the first page's form or investigation.
export async function setAppearance(page: Page, mode: 'light' | 'dark' | 'system' | 'default'): Promise<void> {
  const settingsPage = await page.context().newPage();
  try {
    await settingsPage.goto('/');
    await settingsPage.getByRole('button', { name: 'Settings', exact: true }).click();
    const appearance = settingsPage.getByLabel('Appearance', { exact: true });
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
