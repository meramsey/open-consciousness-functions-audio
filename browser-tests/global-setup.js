const fs = require('node:fs/promises');
const { execFileSync } = require('node:child_process');
const { chromium, firefox, webkit } = require('playwright');

module.exports = async () => {
  const browserName = process.env.BROWSER || 'chromium';
  const browserType = { chromium, firefox, webkit }[browserName];
  if (!browserType) throw new Error(`Unsupported browser: ${browserName}`);
  const browser = await browserType.launch();
  try {
    const receipt = JSON.parse(await fs.readFile('verified-site/site-build-receipt.json', 'utf8'));
    await fs.mkdir('browser-artifacts', { recursive: true });
    await fs.writeFile('browser-artifacts/acceptance-receipt.json', `${JSON.stringify({
      source_commit: receipt.source_commit,
      audio_commit: process.env.GITHUB_SHA || execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
      catalog_sha256: receipt.catalog_sha256,
      site_inventory_sha256: receipt.site_inventory_sha256,
      generated_file_count: receipt.file_count,
      playwright_version: require('@playwright/test/package.json').version,
      axe_core_version: require('axe-core/package.json').version,
      browser: browserName,
      browser_version: browser.version(),
      command: `BROWSER=${browserName} npm run test:browser`,
      viewport_widths: [375, 768, 1024, 1440],
      automated_accessibility: 'axe-core WCAG 2.0/2.1 A and AA on all generated function pages plus primary flows',
    }, null, 2)}\n`);
  } finally {
    await browser.close();
  }
};
