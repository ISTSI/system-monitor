// TEST-ONLY: no backend, credentials, deployed application or SFTP server.
import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';

process.env.PLAYWRIGHT_BROWSERS_PATH ??= resolve('../.cache/playwright');

export default defineConfig({
  testDir: '.',
  testMatch: 'live_notices.spec.ts',
  workers: 1,
  retries: 0,
  timeout: 30000,
  expect: { timeout: 5000 },
  outputDir: '../test-results/live-notices',
  globalSetup: './live_notices.setup.ts',
  reporter: [['list'], ['json', { outputFile: resolve('../verification/live-events-presentation/browser-test-only.json') }]],
  use: {
    baseURL: 'http://127.0.0.1:5189',
    browserName: 'chromium',
    viewport: { width: 1280, height: 900 },
    permissions: ['clipboard-read', 'clipboard-write'],
    trace: 'off', video: 'off', screenshot: 'off',
  },
});
