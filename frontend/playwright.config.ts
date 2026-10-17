import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';

process.env.PLAYWRIGHT_BROWSERS_PATH ??= resolve('../.cache/playwright');
const reportName = process.env.INSPECTOR_E2E_REPORT_NAME ?? 'browser-results';
if (!/^[a-z0-9-]+$/.test(reportName)) throw new Error('Browser report name must contain lowercase letters, digits or hyphens.');
const reportStage = process.env.INSPECTOR_E2E_REPORT_STAGE ?? 'stage-1';
if (!/^stage-[0-8]$/.test(reportStage)) throw new Error('Browser report stage must be stage-0 through stage-8.');

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60000,
  expect: { timeout: 10000 },
  outputDir: './test-results',
  reporter: [
    ['list'],
    ['json', { outputFile: `../verification/${reportStage}/${reportName}.json` }],
  ],
  use: {
    actionTimeout: 15000,
    baseURL: process.env.INSPECTOR_E2E_URL ?? 'https://localhost:8443',
    browserName: 'chromium',
    ignoreHTTPSErrors: true,
    viewport: { width: 1280, height: 720 },
    trace: 'off',
    video: 'off',
    screenshot: 'off',
    testIdAttribute: 'data-testid',
  },
});
