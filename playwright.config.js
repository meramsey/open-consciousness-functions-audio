const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './browser-tests',
  globalSetup: './browser-tests/global-setup.js',
  fullyParallel: false,
  reporter: [['list'], ['json', { outputFile: 'browser-artifacts/results.json' }]],
  outputDir: 'browser-artifacts/test-output',
  use: {
    baseURL: 'http://127.0.0.1:4173/',
    browserName: process.env.BROWSER || 'chromium',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'python3 -m http.server 4173 --bind 127.0.0.1 --directory verified-site',
    url: 'http://127.0.0.1:4173/',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
