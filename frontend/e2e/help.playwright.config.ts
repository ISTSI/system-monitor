// Isolated source-browser regression: no backend, SSH or retained deployment.
import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';

process.env.PLAYWRIGHT_BROWSERS_PATH ??= resolve('../.cache/playwright');
export default defineConfig({
  testDir: '.', testMatch: 'help.spec.ts', workers: 1, retries: 0,
  timeout: 30000, expect: { timeout: 5000 },
  outputDir: '../test-results/stage8-help',
  globalSetup: './help.setup.ts',
  reporter: [['list'], ['json', { outputFile: resolve('../verification/stage-8/help-browser-source.json') }]],
  use: { baseURL: 'http://127.0.0.1:5190', browserName: 'chromium', viewport: { width: 1280, height: 720 }, trace: 'off', video: 'off', screenshot: 'off' },
});
