const { test, expect } = require('@playwright/test');
const fs = require('node:fs/promises');
const path = require('node:path');

async function noAxeViolations(page) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') });
  const result = await page.evaluate(async () => axe.run(document, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
  }));
  const details = result.violations.map(({ id, impact, nodes }) => `${id} (${impact}): ${nodes.map(node => node.target.join(' ')).join(', ')}`).join('\n');
  expect(result.violations, details).toEqual([]);
}

test('accessibility failure is detected by the same fail-closed gate', async ({ page }) => {
  await page.goto('/quick-reference/');
  await page.evaluate(() => document.body.insertAdjacentHTML('beforeend', '<button></button>'));
  await expect(noAxeViolations(page)).rejects.toThrow();
});

test('all 58 generated function pages expose spoken cues only and pass axe', async ({ page }) => {
  const index = await page.request.get('/documentation-index.json').then(response => response.json());
  expect(index.functions).toHaveLength(58);
  for (const row of index.functions) {
    const id = row.function_id;
    await page.goto(`/functions/${id}/`);
    await expect(page.locator('h1')).toBeVisible();
    await expect(page.locator('.display-cue, .historical-commands, .historical-cue')).toHaveCount(0);
    const blocks = page.locator('.command-block');
    for (const block of await blocks.all()) {
      const cue = block.locator('.spoken-cue strong');
      await expect(cue).toHaveCount(1);
      const text = await cue.textContent();
      expect(row.cues).toContain(text.trim());
      const copy = block.locator('button[data-copy]');
      await expect(copy).toHaveAttribute('data-copy', text.trim());
      await expect(copy).toHaveAttribute('aria-label', `Copy cue: ${text.trim()}`);
    }
    expect(await blocks.locator('.spoken-cue strong').allTextContents()).toEqual(row.cues);
    expect(new Set(row.cues).size).toBe(row.cues.length);
    await noAxeViolations(page);
  }
});

test('Sleep has no duplicate step or generic command filler, while distinct guidance remains', async ({ page }) => {
  await page.goto('/functions/OCF-SLP-002/');
  expect(await page.locator('.command-block ol li').allTextContents()).toEqual([
    'Choose the purpose for using this function.',
    'Breathe slowly and deeply.',
    'Think the command during exhalation.',
    'Continue breathing normally.',
  ]);
  const sleepText = await page.locator('#cues').evaluate(element => element.parentElement.textContent);
  expect(sleepText).not.toContain('Display cues and spoken cues are different fields');
  expect(sleepText).not.toContain('Use only when you choose to activate the documented function.');
  expect(sleepText).not.toContain('This is the primary command for the function.');
  expect(sleepText.match(/Choose the purpose for using this function\./g)).toHaveLength(1);
  expect(await page.locator('#behavior').evaluate(element => element.parentElement.textContent)).toContain('temporary');
  expect(await page.locator('#behavior').evaluate(element => element.parentElement.textContent)).not.toContain('No additional lifecycle scopes are declared.');
  expect(await page.locator('#safety').evaluate(element => element.parentElement.textContent)).not.toBe('');
});

test('Quick Reference filters, keyboard controls, narrow widths, print, themes, transcript and deep links work', async ({ page, browserName }) => {
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/quick-reference/');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    await expect(page.locator('.reference-table tbody tr')).toHaveCount(58);
    await expect(page.locator('.historical-cue')).toHaveCount(0);
    await expect(page.locator('.reference-table strong').first()).toHaveText('Plus Automate');
  }

  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto('/quick-reference/');
  const search = page.getByLabel('Search title, ID, spoken cue, tag or use');
  await search.focus();
  await page.keyboard.type('OCF-EXP-001');
  await expect(page.locator('[data-reference-count]')).toHaveText('1 function');
  await search.fill('Plus Focus');
  await expect(page.locator('[data-reference-count]')).toHaveText('1 function');
  const domain = page.getByLabel('Canonical domain');
  await domain.selectOption('foundation');
  await search.fill('OCF-EXP-001');
  await expect(page.locator('[data-reference-count]')).toHaveText('1 function');
  await page.keyboard.press('Tab');
  await expect(page.locator(':focus')).toHaveAttribute('data-reference-category');

  await page.goto('/functions/OCF-SLP-002/#cues');
  await page.reload();
  await expect(page).toHaveURL(/#cues$/);
  await expect(page.locator('#cues')).toBeInViewport();
  await page.locator('.mobile-toc summary').focus();
  await page.keyboard.press('Space');
  await expect(page.locator('.mobile-toc')).toHaveAttribute('open', '');
  await page.locator('.mobile-toc a[href="#behavior"]').focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#behavior$/);

  await page.goto('/');
  const initialTheme = await page.locator('html').getAttribute('data-theme');
  await page.locator('[data-theme-toggle]').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('html')).not.toHaveAttribute('data-theme', initialTheme);

  await page.goto('/functions/OCF-FND-004/');
  const transcript = page.locator('[data-transcript]').first();
  await transcript.locator('summary').click();
  await expect(transcript.locator('.transcript-body')).not.toContainText('Transcript loads when expanded.');
  await expect(transcript.locator('.transcript-search input')).toBeEnabled();
  const transcriptHeight = await transcript.locator('.transcript-body').evaluate(el => el.scrollHeight);
  expect(transcriptHeight).toBeGreaterThan(512);
  expect(await transcript.locator('.transcript-body').evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);
  await transcript.locator('.transcript-body').evaluate(el => { el.scrollTop = el.scrollHeight; });
  expect(await transcript.locator('.transcript-body').evaluate(el => el.scrollTop)).toBeGreaterThan(0);
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);

  await page.goto('/quick-reference/');
  if (browserName === 'chromium') {
    await page.emulateMedia({ media: 'print' });
    expect(await page.evaluate(() => getComputedStyle(document.body).color)).toBe('rgb(17, 17, 17)');
    expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe('rgb(255, 255, 255)');
    expect(await page.locator('.reference-table').evaluate(table => getComputedStyle(table).minWidth)).toBe('0px');
    expect(await page.locator('.reference-table').evaluate(table => table.scrollWidth <= table.clientWidth)).toBe(true);
    const pdf = await page.pdf({ printBackground: true, preferCSSPageSize: true });
    await fs.mkdir('browser-artifacts', { recursive: true });
    await fs.writeFile(path.join('browser-artifacts', 'quick-reference-print.pdf'), pdf);
    expect(pdf.byteLength).toBeGreaterThan(10_000);
  }
  await noAxeViolations(page);
});

test('mobile navigation, function copy control, focus order, and page accessibility', async ({ page, context, browserName }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  if (browserName === 'chromium') {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  }
  await page.goto('/functions/OCF-SLP-002/');
  const copyButton = page.getByRole('button', { name: 'Copy cue: Plus Sleep' });
  await expect(copyButton).toBeVisible();
  await copyButton.focus();
  await page.keyboard.press('Enter');
  if (browserName === 'chromium') {
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe('Plus Sleep');
  } else {
    await expect.poll(() => copyButton.textContent()).toMatch(/^(Copied|Plus Sleep)$/);
  }
  await page.locator('.mobile-nav summary').focus();
  await page.keyboard.press('Space');
  await expect(page.locator('.mobile-nav')).toHaveAttribute('open', '');
  await page.locator('.mobile-nav a[href$="quick-reference/"]').focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/quick-reference\/$/);
  await expect(page.locator('.mobile-nav')).not.toHaveAttribute('open', '');
  await page.keyboard.press('Tab');
  await expect(page.locator(':focus')).toBeVisible();
  await noAxeViolations(page);
});
