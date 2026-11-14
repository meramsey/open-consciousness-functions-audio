const { test, expect } = require('@playwright/test');
const fs = require('node:fs/promises');
const path = require('node:path');

async function noAxeViolations(page, context = undefined) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') });
  const result = await page.evaluate(async contextSelector => axe.run(contextSelector || document, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
  }), context);
  const details = result.violations.map(({ id, impact, nodes }) => `${id} (${impact}): ${nodes.map(node => node.target.join(' ')).join(', ')}`).join('\n');
  expect(result.violations, details).toEqual([]);
}

function silentWavDataURI(seconds = 3) {
  const sampleRate = 8000;
  const sampleCount = sampleRate * seconds;
  const wav = Buffer.alloc(44 + sampleCount, 128);
  wav.write('RIFF', 0); wav.writeUInt32LE(36 + sampleCount, 4); wav.write('WAVE', 8);
  wav.write('fmt ', 12); wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22); wav.writeUInt32LE(sampleRate, 24);
  wav.writeUInt32LE(sampleRate, 28); wav.writeUInt16LE(1, 32); wav.writeUInt16LE(8, 34);
  wav.write('data', 36); wav.writeUInt32LE(sampleCount, 40);
  return `data:audio/wav;base64,${wav.toString('base64')}`;
}

async function useSilentWavFixture(page, fixtureURL = silentWavDataURI()) {
  await page.context().route(url => {
    let decoded;
    try { decoded = decodeURIComponent(url.href); } catch (_) { return false; }
    if (!/(?:\.mp3|\.flac)(?:$|[?#])/i.test(decoded)) return false;
    return /(?:^|\.)github\.com$|(?:^|\.)githubusercontent\.com$/.test(url.hostname) || /release-assets\.githubusercontent\.com$/i.test(url.hostname);
  }, route => route.abort());
  await page.addInitScript(fixture => {
    Object.defineProperty(HTMLAudioElement.prototype, 'src', {
      configurable: true,
      get() { return this.getAttribute('src') || ''; },
      set() { this.setAttribute('src', fixture); },
    });
  }, fixtureURL);
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
    await expect(page.locator('.draft-badge, .review-status, .status-line')).toHaveCount(0);
    const pageText = await page.locator('body').innerText();
    expect(pageText).not.toContain('Draft metadata — not reviewed guidance');
    expect(pageText).not.toContain('description review status not recorded');
    expect(pageText).not.toContain('Procedure wording is not published while review is pending.');
    await expect(page.locator('.function-intro .lead')).toHaveText(row.description);
    await expect(page.locator('.function-intro .lead')).toHaveCount(1);
    await expect(page.getByRole('heading', {name: 'Intended purpose', exact: true})).toHaveCount(0);
    await expect(page.getByRole('heading', {name: 'Purpose', exact: true})).toHaveCount(0);
      await expect(page.locator('.source-details')).toBeAttached();
    const blocks = page.locator('.command-block');
    for (const block of await blocks.all()) {
      const cue = block.locator('.spoken-cue strong');
      await expect(cue).toHaveCount(1);
      const text = await cue.textContent();
      expect(row.cues).toContain(text.trim());
      await expect(block.locator('button.copy-cue, button[aria-label^="Copy cue:"]')).toHaveCount(0);
    }
    expect(await blocks.locator('.spoken-cue strong').allTextContents()).toEqual(row.cues);
    expect(new Set(row.cues).size).toBe(row.cues.length);
    await noAxeViolations(page);
  }
  const intuition = index.functions.find(row => row.function_id === 'OCF-EXP-006');
  expect(intuition.search_terms).toEqual([]);
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

test('Insulate hold guidance uses the spoken Cancel cue without cue copy controls', async ({ page }) => {
  await page.goto('/functions/OCF-EXP-002/');
  const cancelCommand = page.locator('.command-block').filter({ has: page.locator('.spoken-cue strong', { hasText: 'Plus Cancel' }) });
  await expect(cancelCommand).toHaveCount(1);
  await expect(cancelCommand.locator('.spoken-cue strong')).toHaveText('Plus Cancel');
  await expect(cancelCommand.locator('button.copy-cue, button[aria-label^="Copy cue:"]')).toHaveCount(0);

  const releaseCommand = page.locator('.command-block').filter({ has: page.locator('.spoken-cue strong', { hasText: 'Plus Release' }) });
  await expect(releaseCommand).toHaveCount(1);
  const guidance = await releaseCommand.innerText();
  expect(guidance).toContain('Places Insulate on hold; Plus Cancel ends the current adjustment.');
  expect(guidance).not.toContain('PLUS-CANCEL');
  await expect(releaseCommand.locator('button.copy-cue, button[aria-label^="Copy cue:"]')).toHaveCount(0);
});

test('Start Here renders the approved suggestion as an ordered list and presents Preparation Learning first', async ({ page }) => {
  await page.goto('/start/');
  const headings = await page.locator('#main h2').allTextContents();
  expect(headings.indexOf('Preparation Learning')).toBeLessThan(headings.indexOf('Choose one practice'));
  expect(headings.indexOf('Choose one practice')).toBeLessThan(headings.indexOf('A suggested way to explore'));
  const text = await page.locator('#main').innerText();
  expect(text).toContain('Complete Preparation Learning before using any OCF function.');
  expect(text).toContain('Only people who have already learned the official Human Plus preparation track may skip it.');
  expect(text).not.toContain('Michael');
  expect(text).not.toContain('not a verified official OCF policy');
  const sequence = page.locator('#main ol');
  await expect(sequence).toHaveCount(1);
  const items = await sequence.locator('li').allTextContents();
  expect(items).toHaveLength(3);
  expect(items[0]).toContain('Relax — OCF-FND-004');
  expect(items[1]).toContain('Focus — OCF-FND-002');
  expect(items[2]).toContain('Think Fast — OCF-COG-007');
  expect(text).not.toContain('distinguishes displayed cues from spoken cues');
  expect(text).toContain('separate introductory session, not one of the 58 function records');
  expect(text).toContain('After Preparation Learning, these three functions can be approachable starting points:');
  expect(text).toContain('You can explore these functions in any order;');
  expect(text).toContain('not a required sequence among them');
  await noAxeViolations(page);
  await page.goto('/');
  const homeText = await page.locator('main').innerText();
  const hero = await page.locator('.docs-hero').innerText();
  expect(homeText).toContain('Complete Preparation Learning before using any OCF function.');
  expect(homeText).toContain('Only people who have already learned the official Human Plus preparation track may skip it.');
  expect(homeText).not.toContain('Michael');
  expect(homeText).not.toContain('not a verified official OCF policy');
  await expect(page.locator('.desktop-nav a').first()).toHaveAttribute('href', 'start/');
  await expect(page.locator('.path-card').first()).toHaveAttribute('href', 'start/');
  await expect(page.locator('.desktop-nav a[href="preparation-learning/"]')).toHaveCount(0);
  await expect(page.locator('.path-card[href="preparation-learning/"]')).toHaveCount(0);
  await expect(page.locator('.docs-hero .button-light')).toHaveAttribute('href', 'start/');
  await expect(page.locator('.docs-hero a[href="preparation-learning/"]')).toHaveCount(0);
  await expect(page.locator('.desktop-nav a[href="functions/"]')).toHaveCount(1);
  const quickPath = page.locator('.home-utilities a[href="quick-reference/"]');
  await expect(quickPath).toContainText('current spoken cues');
  await expect(quickPath).not.toContainText('display/spoken');
});

test('historical names appear only in their source-authoritative lookup page', async ({ page }) => {
  await page.goto('/historical-names/');
  const receipt = await page.request.get('/site-build-receipt.json').then(response => response.json());
  await expect(page.locator('[data-historical-name-entry]')).toHaveCount(43);
  expect(receipt.historical_mapping_count).toBe(43);
  expect(receipt.historical_name_count).toBe(94);
  await expect(page.locator('[data-also-current="true"]')).toHaveCount(4);
  expect(receipt.historical_name_kind_counts).toEqual({
    'former-primary': 24,
    'former-teaching': 34,
    'former-title': 34,
    'legacy-phrase': 2,
  });
  const smell = page.locator('[data-historical-name-entry][data-function-id="OCF-SEN-003"]');
  await expect(smell).toContainText('Sensory: Smell');
  await expect(smell.locator('[data-historical-kind="former-title"]')).toContainText('Former title');
  await expect(smell).not.toContainText('PLUS-SMELL GREATER');
  await expect(smell).not.toContainText('PLUS-SMELL LESSER');
  await expect(page.locator('[data-historical-name-entry][data-function-id="OCF-SEN-005"]')).not.toContainText('PLUS-TOUCH MORE');
  const historicalRow = (functionId, text) => page
    .locator(`[data-historical-name-entry][data-function-id="${functionId}"]`)
    .locator('.historical-name-text')
    .filter({ hasText: new RegExp(`^${text}$`, 'i') })
    .locator('..');
  const detox = historicalRow('OCF-BOD-004', 'PLUS-DETOX');
  await expect(detox).toHaveAttribute('data-historical-kind', 'former-primary');
  await expect(detox).toHaveAttribute('data-also-current', 'true');
  await expect(detox.locator('.historical-name-kind')).toHaveText('Former primary cue · Also current');
  const breathe = historicalRow('OCF-BOD-009', 'Plus Breathe Better');
  await expect(breathe).toHaveAttribute('data-historical-kind', 'former-teaching');
  await expect(breathe).toHaveAttribute('data-also-current', 'true');
  await expect(breathe.locator('.historical-name-kind')).toHaveText('Former teaching phrase · Also current');
  const sleepTitle = historicalRow('OCF-SLP-005', 'Sleep Easy');
  await expect(sleepTitle).toHaveAttribute('data-historical-kind', 'former-title');
  await expect(sleepTitle).toHaveAttribute('data-also-current', 'true');
  await expect(sleepTitle.locator('.historical-name-kind')).toHaveText('Former title · Also current');
  const sleepCue = historicalRow('OCF-SLP-005', 'PLUS-SLEEP EASY');
  await expect(sleepCue).toHaveAttribute('data-historical-kind', 'former-primary');
  await expect(sleepCue).toHaveAttribute('data-also-current', 'true');
  await expect(sleepCue.locator('.historical-name-kind')).toHaveText('Former primary cue · Also current');
  const innerPower = page.locator('[data-historical-name-entry][data-function-id="OCF-PRF-002"]');
  await expect(innerPower).toContainText('Eight-Great');
  await expect(innerPower).toContainText('Plus Eight Great');
  await expect(innerPower).not.toContainText('PLUS-STRONG');
  await expect(page.locator('a[href*="OCF_HISTORICAL_LOOKUP_CURRENT.md"]')).toHaveAttribute('href', /704440da8e0379cee8dfd332203bc0001c0a5f27/);
  await expect(page.getByText('A match never selects an activation target.')).toBeVisible();
  const unmapped = page.locator('.page-intro');
  await expect(unmapped).toContainText('these 15 functions');
  for (const id of ['OCF-BOD-010', 'OCF-BOD-012', 'OCF-COG-003', 'OCF-COG-006', 'OCF-COG-007', 'OCF-COM-001', 'OCF-EMO-001', 'OCF-EXP-003', 'OCF-EXP-005', 'OCF-EXP-006', 'OCF-FND-001', 'OCF-FND-006', 'OCF-PRF-001', 'OCF-PRF-005', 'OCF-PRF-006']) {
    await expect(page.locator(`.page-intro a[href="../functions/${id}/"]`)).toHaveCount(1);
  }
  await expect(unmapped).toContainText('Absence from this reference does not establish that no historical counterpart exists.');
  await page.setViewportSize({ width: 375, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375);
  await noAxeViolations(page);

  for (const id of ['OCF-BOD-004', 'OCF-BOD-009', 'OCF-SLP-005', 'OCF-PRF-002']) {
    await page.goto(`/functions/${id}/`);
    await expect(page.locator('[data-historical-name-entry], [data-also-current]')).toHaveCount(0);
    await expect(page.locator('main')).not.toContainText('Also current');
  }
  await expect(page.locator('.spoken-cue strong')).toContainText('Plus Inner Power');
});

test('related-practice directory retains all approved one-way records and their reasons', async ({ page }) => {
  await page.goto('/relationships/');
  const receipt = await page.request.get('/site-build-receipt.json').then(response => response.json());
  const rows = page.locator('.relationship-card');
  await expect(rows).toHaveCount(33);
  expect(receipt.approved_relationship_count).toBe(33);
  for (const row of await rows.all()) {
    await expect(row.locator('h3 a')).toHaveCount(2);
    await expect(row.locator('h3')).toContainText('→');
    await expect(row.locator('p').last()).not.toBeEmpty();
  }
  await expect(page.locator('.page-intro')).toContainText('optional and one-way');
});

test('Start Here leads the home paths while Preparation Learning stays available inside onboarding', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.docs-hero .button-light')).toHaveAttribute('href', 'start/');
  await expect(page.locator('.path-card').first()).toHaveAttribute('href', 'start/');
  await expect(page.locator('.path-card[href="preparation-learning/"]')).toHaveCount(0);
  await expect(page.locator('.desktop-nav a[href="preparation-learning/"]')).toHaveCount(0);
  await page.goto('/start/');
  await expect(page.locator('#main')).toContainText('Complete Preparation Learning before using any OCF function.');
  await expect(page.locator('#main')).toContainText('Only people who have already learned the official Human Plus preparation track may skip it.');
  await expect(page.locator('#main a[href="../preparation-learning/"]')).toBeVisible();
  await page.goto('/preparation-learning/');
  await expect(page.locator('.edition-card audio')).toBeVisible();
});

test('homepage stays concise, keeps the legacy library fragment, and sends old function queries to Browse & Listen', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('audio')).toHaveCount(0);
  await expect(page.locator('script[src$="/assets/js/app.js"]')).toHaveCount(0);
  await expect(page.locator('#library')).toBeVisible();
  await expect(page.locator('.hero-actions a[href="functions/"]')).toContainText('Browse & Listen');
  await expect(page.locator('.category-link').first()).toBeVisible();
  await page.goto('/index.html#library');
  await expect(page).toHaveURL(/\/index\.html#library$/);
  await page.goto('/index.html?function=OCF-FND-004');
  await page.waitForURL(/\/functions\/\?function=OCF-FND-004$/);
  await expect(page.locator('#search')).toHaveValue('OCF-FND-004');
  await expect(page.locator('.session-card:visible h3')).toContainText('Relax');
});

test('Browse & Listen stays truthful without JavaScript or when catalog loading fails', async ({ page, browser, context }) => {
  const noScriptContext = await browser.newContext({javaScriptEnabled: false});
  const noScriptPage = await noScriptContext.newPage();
  await noScriptPage.goto('/functions/');
  await expect(noScriptPage.locator('.function-card')).toHaveCount(58);
  await expect(noScriptPage.locator('.function-card').first()).toContainText('Published recording available');
  await expect(noScriptPage.locator('.function-card').first().locator('.browse-action[href^="https://github.com/"]')).toHaveCount(2);
  await expect(noScriptPage.locator('audio')).toHaveCount(0);
  await noScriptContext.close();

  await context.route('**/catalog.json', route => route.abort());
  await page.goto('/functions/');
  await expect(page.locator('.function-card')).toHaveCount(58);
  await expect(page.locator('#empty-state')).toContainText('could not be loaded');
  await expect(page.locator('#empty-state')).not.toContainText('No published recordings');
  await expect(page.locator('.function-card').first().locator('.browse-action[href^="https://github.com/"]')).toHaveCount(2);
  await expect(page.locator('audio')).toHaveCount(0);
});

test('mobile navigation stays readable, in-flow, keyboard-operable, and overflow-free through zoom widths', async ({ page }) => {
  await page.goto('/');
  for (const width of [160, 320, 360, 375, 390, 414, 760, 768, 820, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const viewportOverflow = await page.evaluate(() => ({
      width: document.documentElement.scrollWidth,
      nodes: [...document.querySelectorAll('body *')]
        .map(element => ({
          tag: element.tagName,
          className: String(element.className || ''),
          text: element.innerText?.slice(0, 60),
          rect: (() => { const {left, right, width: elementWidth} = element.getBoundingClientRect(); return {left, right, width: elementWidth}; })(),
          scrollWidth: element.scrollWidth,
          clientWidth: element.clientWidth,
        }))
        .filter(element => element.rect.left < -1 || element.rect.right > innerWidth + 1 || element.scrollWidth > element.clientWidth + 1)
        .slice(0, 12),
    }));
    expect(viewportOverflow.width, `horizontal overflow at ${width}px: ${JSON.stringify(viewportOverflow.nodes)}`).toBeLessThanOrEqual(width);
    const header = await page.locator('.site-header').evaluate(element => {
      const rect = element.getBoundingClientRect();
      return { left: rect.left, right: rect.right, width: rect.width, scrollWidth: element.scrollWidth, clientWidth: element.clientWidth };
    });
    expect(header.left).toBeGreaterThanOrEqual(0);
    expect(header.right).toBeLessThanOrEqual(width + 1);
    expect(header.scrollWidth).toBeLessThanOrEqual(header.clientWidth + 1);
    if (width <= 1080) {
      await expect(page.locator('.mobile-nav > summary')).toBeVisible();
      await expect(page.locator('.desktop-nav')).toBeHidden();
    } else {
      await expect(page.locator('.mobile-nav')).toBeHidden();
      await expect(page.locator('.desktop-nav')).toBeVisible();
    }
  }

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1280);
  expect(await page.locator('.site-header').evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  await page.evaluate(() => { document.documentElement.style.removeProperty('font-size'); });
  await page.goto('/start/');
  await expect(page.locator('.desktop-nav a[aria-current="page"]')).toHaveText('Start Here');
  await page.goto('/functions/');
  await expect(page.locator('.desktop-nav a[aria-current="page"]')).toHaveText('Browse & Listen');
  await page.goto('/functions/OCF-BOD-001/');
  await expect(page.locator('.desktop-nav a[aria-current="location"]')).toHaveText('Browse & Listen');
  await expect(page.locator('.breadcrumbs [aria-current="page"]')).toHaveText('Brain Flow');
  await page.goto('/downloads/');
  await expect(page.locator('.desktop-nav .more-links a[aria-current="page"]')).toHaveText('Downloads');

  await page.goto('/');
  await page.setViewportSize({ width: 375, height: 812 });
  await page.evaluate(() => localStorage.setItem('ocf-theme', 'light'));
  await page.reload();
  const menu = page.locator('.mobile-nav');
  const summary = menu.locator(':scope > summary');
  await summary.focus();
  await page.keyboard.press('Enter');
  await expect(menu).toHaveAttribute('open', '');
  expect(await menu.locator('nav').evaluate(element => getComputedStyle(element).position)).toBe('static');
  expect(await menu.locator('nav').evaluate(element => element.getBoundingClientRect().bottom)).toBeLessThanOrEqual(
    await page.locator('main').evaluate(element => element.getBoundingClientRect().top),
  );
  await page.keyboard.press('Tab');
  await expect(menu.locator('a').first()).toBeFocused();
  await expect(menu.locator('a').first()).toHaveAttribute('href', 'start/');
  await expect(menu.locator('a[href="preparation-learning/"]')).toHaveCount(0);
  expect(await menu.locator('a').count()).toBe(9);
  const primaryLinks = menu.locator('nav[aria-label="Main navigation"] > a');
  await expect(primaryLinks).toHaveCount(4);
  const linkRects = await primaryLinks.evaluateAll(links => links.map(link => {
    const { x, right, height } = link.getBoundingClientRect();
    return { x, right, height };
  }));
  for (const rect of linkRects) {
    expect(rect.height).toBeGreaterThanOrEqual(44);
    expect(rect.x).toBeGreaterThanOrEqual(0);
    expect(rect.right).toBeLessThanOrEqual(375);
  }
  expect((await summary.boundingBox()).height).toBeGreaterThanOrEqual(44);
  for (const link of await primaryLinks.all()) await expect(link).toBeVisible();
  const more = menu.locator('.more-menu');
  await more.locator('summary').click();
  await expect(more.locator('.more-links a')).toHaveCount(5);
  for (const link of await more.locator('.more-links a').all()) await expect(link).toBeVisible();
  await more.locator('summary').click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await fs.mkdir('browser-artifacts', { recursive: true });
  await page.screenshot({ path: path.join('browser-artifacts', 'mobile-menu-light-375.png'), fullPage: false });
  await page.keyboard.press('Escape');
  await expect(menu).not.toHaveAttribute('open', '');
  await expect(summary).toBeFocused();

  await summary.click();
  await expect(menu).toHaveAttribute('open', '');
  await page.locator('.site-footer p').click();
  await expect(menu).not.toHaveAttribute('open', '');

  await page.locator('.theme-toggle').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await summary.click();
  await page.screenshot({ path: path.join('browser-artifacts', 'mobile-menu-dark-375.png'), fullPage: false });
  await noAxeViolations(page, '.site-header');
  await page.keyboard.press('Escape');
});

test('Downloads cards keep every individual format action visible and named across viewport widths', async ({ page }) => {
  await page.goto('/downloads/');
  const receipt = await page.request.get('/site-build-receipt.json').then(response => response.json());
  await expect(page.locator('.download-card')).toHaveCount(receipt.published_session_count);
  await expect(page.locator('.reference-table')).toHaveCount(0);

  const catalog = await page.request.get('/catalog.json').then(response => response.json());
  const release = catalog.releases[0];
  for (const [functionId, title] of [['OCF-FND-004', 'Relax'], ['OCF-BOD-001', 'Brain Flow']]) {
    const session = release.functions.find(row => row.function_id === functionId).sessions[0];
    const card = page.locator(`.download-card[data-function-id="${functionId}"]`);
    await expect(card.locator('h2')).toContainText(title);
    for (const format of ['mp3', 'flac']) {
      const asset = session.assets.find(item => item.format === format);
      const link = card.getByRole('link', { name: new RegExp(`^Download ${format.toUpperCase()} for ${title},`) });
      await expect(link).toHaveAttribute('href', asset.download_url);
      await expect(link).toContainText(`Download ${format.toUpperCase()}`);
      await expect(card).toContainText(asset.sha256);
    }
  }

  for (const width of [320, 375, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const layout = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      pageWidth: document.documentElement.scrollWidth,
      cards: [...document.querySelectorAll('.download-card')].map(card => {
        const cardRect = card.getBoundingClientRect();
        const actions = [...card.querySelectorAll('.download-action')].map(link => {
          const rect = link.getBoundingClientRect();
          return { left: rect.left, right: rect.right, width: rect.width };
        });
        return { width: cardRect.width, scrollWidth: card.scrollWidth, clientWidth: card.clientWidth, actions };
      }),
    }));
    expect(layout.pageWidth, `document overflow at ${width}px`).toBeLessThanOrEqual(width);
    expect(layout.cards).toHaveLength(receipt.published_session_count);
    for (const card of layout.cards) {
      expect(card.width).toBeGreaterThan(0);
      expect(card.scrollWidth, `card overflow at ${width}px`).toBeLessThanOrEqual(card.clientWidth + 1);
      expect(card.actions.length).toBeGreaterThanOrEqual(1);
      for (const action of card.actions) {
        expect(action.width).toBeGreaterThan(0);
        expect(action.left).toBeGreaterThanOrEqual(-1);
        expect(action.right).toBeLessThanOrEqual(layout.viewport + 1);
      }
    }
    if (width === 390 || width === 1440) {
      await fs.mkdir('browser-artifacts', { recursive: true });
      await page.screenshot({ path: path.join('browser-artifacts', `checkpoint1-downloads-${width}.png`), fullPage: true });
    }
  }
  await noAxeViolations(page);
});

test('manual and system theme combinations keep banner, hover and focus contrast; forced colors and reduced motion remain usable', async ({ page }) => {
  const contrast = (foreground, background) => {
    const channel = value => {
      const n = value / 255;
      return n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4;
    };
    const rgb = value => value.match(/[\d.]+/g).slice(0, 3).map(Number);
    const luminance = color => {
      const [r, g, b] = rgb(color).map(channel);
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
    return (values[0] + 0.05) / (values[1] + 0.05);
  };
  for (const osTheme of ['light', 'dark']) {
    for (const preference of ['light', 'dark', 'system']) {
      await page.emulateMedia({ colorScheme: osTheme });
      await page.goto('/functions/');
      await page.evaluate(value => localStorage.setItem('ocf-theme', value), preference);
      await page.reload();
      const expected = preference === 'system' ? 'System' : preference[0].toUpperCase() + preference.slice(1);
      const themeButton = page.getByRole('button', { name: `Color theme: ${expected}. Activate to change.` });
      await expect(themeButton).toBeVisible();
      const resolved = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
      expect(resolved).toBe(preference === 'system' ? null : preference);
      const banner = page.locator('.release-banner');
      await expect(banner).toBeVisible();
      const colors = await page.evaluate(() => {
        const banner = document.querySelector('.release-banner');
        const background = getComputedStyle(banner).backgroundColor;
        return ['h2', '.eyebrow', 'p:not(.eyebrow)', '.text-link'].map(selector => ({
          selector, foreground: getComputedStyle(banner.querySelector(selector)).color, background,
        }));
      });
      for (const item of colors) expect(contrast(item.foreground, item.background), `${preference}/${osTheme} ${item.selector}`).toBeGreaterThanOrEqual(4.5);
      const releaseLink = banner.locator('.text-link');
      await releaseLink.hover();
      const hoverColors = await releaseLink.evaluate(link => ({
        foreground: getComputedStyle(link).color,
        background: getComputedStyle(link.closest('.release-banner')).backgroundColor,
      }));
      expect(contrast(hoverColors.foreground, hoverColors.background), `${preference}/${osTheme} hovered link`).toBeGreaterThanOrEqual(4.5);
      await themeButton.focus();
      const focusColors = await themeButton.evaluate(button => ({ ring: getComputedStyle(button).outlineColor, background: getComputedStyle(button).backgroundColor }));
      expect(contrast(focusColors.ring, focusColors.background), `${preference}/${osTheme} focus ring`).toBeGreaterThanOrEqual(3);
      await page.goto('/functions/OCF-BOD-001/');
      await page.locator('.source-details summary').click();
      const documentationLink = page.locator('.docs-content .source-details a').first();
      await documentationLink.hover();
      const documentationHover = await page.evaluate(link => ({
        foreground: getComputedStyle(link).color,
        background: getComputedStyle(document.body).backgroundColor,
      }), await documentationLink.elementHandle());
      expect(contrast(documentationHover.foreground, documentationHover.background), `${preference}/${osTheme} documentation-link hover`).toBeGreaterThanOrEqual(4.5);

      await page.goto('/downloads/');
      const cardSurfaces = await page.evaluate(() => {
        const root = getComputedStyle(document.documentElement);
        const expectedValue = root.getPropertyValue('--card').trim();
        const probe = document.createElement('div');
        probe.style.backgroundColor = expectedValue;
        document.body.append(probe);
        const expected = getComputedStyle(probe).backgroundColor;
        probe.remove();
        const card = document.querySelector('.download-card');
        return {
          expected,
          card: getComputedStyle(card).backgroundColor,
          foreground: getComputedStyle(card.querySelector('h2')).color,
        };
      });
      expect(cardSurfaces.card, `${preference}/${osTheme} Downloads card surface`).toBe(cardSurfaces.expected);
      expect(contrast(cardSurfaces.foreground, cardSurfaces.card), `${preference}/${osTheme} Downloads card title`).toBeGreaterThanOrEqual(4.5);
      const moreMenu = page.locator('.desktop-nav .more-menu');
      await moreMenu.locator(':scope > summary').click();
      const menuSurfaces = await moreMenu.locator('.more-links').evaluate(menu => ({
        background: getComputedStyle(menu).backgroundColor,
        foreground: getComputedStyle(menu.querySelector('a')).color,
      }));
      expect(menuSurfaces.background, `${preference}/${osTheme} More menu must be opaque`).toBe(cardSurfaces.expected);
      expect(contrast(menuSurfaces.foreground, menuSurfaces.background), `${preference}/${osTheme} More menu text`).toBeGreaterThanOrEqual(4.5);
    }
  }
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  await page.keyboard.press('Tab');
  await page.getByRole('button', { name: /Color theme/ }).focus();
  const modes = await page.evaluate(() => ({
    forcedColors: matchMedia('(forced-colors: active)').matches,
    reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
    outlineStyle: getComputedStyle(document.activeElement).outlineStyle,
    outlineWidth: getComputedStyle(document.activeElement).outlineWidth,
    scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
    transitionDuration: getComputedStyle(document.activeElement).transitionDuration,
  }));
  expect(modes.forcedColors).toBe(true);
  expect(modes.reducedMotion).toBe(true);
  expect(modes.outlineStyle).not.toBe('none');
  expect(parseFloat(modes.outlineWidth)).toBeGreaterThan(0);
  expect(modes.scrollBehavior).toBe('auto');
  await noAxeViolations(page, '.site-header');
});

test('current-cue search normalizes separators, offers clear/no-results, and keeps historical labels out', async ({ page }) => {
  await page.goto('/functions/');
  const search = page.locator('#search');
  for (const query of ['PLUS-RELAX', '  Plus   Relax  ', 'plus—relax']) {
    await search.fill(query);
    await expect(page.locator('.session-card:visible')).toHaveCount(1);
    await expect(page.locator('.session-card:visible h3')).toContainText('Relax');
  }
  await search.fill('no-such-current-cue');
  await expect(page.locator('#catalog-no-results')).toBeVisible();
  await expect(page.locator('#clear-library-filters')).toBeVisible();
  await page.locator('#clear-library-filters').click();
  await expect(search).toHaveValue('');
  await expect(page.locator('.session-card:visible')).toHaveCount(59);

  await search.fill('PLUS-STRONG');
  await expect(page.locator('.session-card:visible')).toHaveCount(1);
  await expect(page.locator('.session-card:visible h3')).toContainText('Strong-Quick');

  const directory = await page.request.get('/documentation-index.json').then(response => response.json());
  const relaxCategory = directory.functions.find(row => row.function_id === 'OCF-FND-004').categories[0];
  await page.locator('#clear-library-filters').click();
  await page.locator('#category-filter').selectOption(relaxCategory);
  const categoryFunctionIds = directory.functions.filter(row => row.categories.includes(relaxCategory)).map(row => row.function_id);
  const visibleFunctionIds = await page.locator('.session-card:visible').evaluateAll(cards => cards.map(card => card.dataset.functionId));
  expect(visibleFunctionIds.length).toBeGreaterThan(0);
  expect(visibleFunctionIds.every(id => categoryFunctionIds.includes(id))).toBe(true);
  await expect(page.locator('.session-card[data-function-id="OCF-FND-004"]')).toBeVisible();

  await page.goto('/quick-reference/');
  const referenceSearch = page.locator('[data-reference-search]');
  await referenceSearch.fill('  PLUS---RELAX  ');
  await expect(page.locator('[data-reference-row]:visible')).toHaveCount(1);
  await expect(page.locator('[data-reference-row]:visible')).toContainText('Plus Relax');
  await referenceSearch.fill('no-such-current-cue');
  await expect(page.locator('[data-reference-no-results]')).toBeVisible();
  await expect(page.locator('[data-reference-clear]')).toBeVisible();
  await page.locator('[data-reference-clear]').click();
  await expect(referenceSearch).toHaveValue('');
  await expect(page.locator('[data-reference-row]:visible')).toHaveCount(58);
  await noAxeViolations(page, '.reference-tools');
});

test('filtered-out synthetic media remains focused, understandable, seekable and resumable after pause and end', async ({ page }) => {
  const audioRequests = [];
  page.on('request', request => { if (/\.(?:mp3|flac)(?:$|[?#])/i.test(request.url())) audioRequests.push(request.url()); });
  await useSilentWavFixture(page);
  await page.goto('/functions/');
  const relax = page.locator('.session-card').filter({ has: page.getByRole('link', { name: 'Relax', exact: true }) });
  const player = relax.locator('audio');
  await expect(player).toBeAttached();
  await player.evaluate(audio => audio.load());
  await expect.poll(() => player.evaluate(audio => audio.duration)).toBeGreaterThan(2.9);
  await player.evaluate(audio => { audio.dataset.fixtureIdentity = 'relax-synthetic-wav'; });
  const fixtureControl = await relax.evaluate(card => {
    const player = card.querySelector('audio');
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.fixturePlaybackControl = '';
    button.textContent = 'Play synthetic test media';
    button.addEventListener('click', async () => {
      if (player.paused || player.ended) await player.play();
      else player.pause();
    });
    card.append(button);
    return button.dataset.fixturePlaybackControl;
  });
  expect(fixtureControl).toBe('');
  const fixtureButton = relax.locator('[data-fixture-playback-control]');
  await fixtureButton.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => player.evaluate(audio => audio.paused)).toBe(false);
  await player.evaluate(audio => { audio.currentTime = 0.6; });
  await player.evaluate(audio => audio.dispatchEvent(new Event('timeupdate')));
  const positionBeforeFilter = await player.evaluate(audio => audio.currentTime);
  await player.focus();
  const focusedBeforeFilter = await player.evaluate(audio => document.activeElement === audio);
  expect(focusedBeforeFilter).toBe(true);
  await page.locator('#search').evaluate(input => {
    input.value = 'OCF-BOD-001';
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await expect(page.locator('#results-count')).toContainText('1 matching');
  await expect(relax).toBeVisible();
  await expect(relax.locator('[data-filter-pinned]')).toContainText('Playing Relax');
  expect(await player.evaluate(audio => audio.isSameNode(document.querySelector('.session-card[data-function-id="OCF-FND-004"] audio')))).toBe(true);
  expect(await player.evaluate(audio => document.activeElement === audio)).toBe(true);
  await fixtureButton.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => player.evaluate(audio => audio.paused)).toBe(true);
  await expect(relax.locator('[data-filter-pinned]')).toContainText('Paused at 0:');
  const pausedPosition = await player.evaluate(audio => audio.currentTime);
  expect(pausedPosition).toBeGreaterThanOrEqual(positionBeforeFilter);
  expect(pausedPosition).toBeLessThan(2.9);
  expect(await player.evaluate(audio => audio.isConnected)).toBe(true);
  expect(await fixtureButton.evaluate(button => document.activeElement === button)).toBe(true);
  await page.locator('#search').evaluate(input => {
    input.value = 'OCF-FND-004';
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await expect(relax).toBeVisible();
  await expect(relax.locator('[data-filter-pinned]')).toBeHidden();
  await page.locator('#search').focus();
  await page.locator('#search').evaluate(input => {
    input.value = 'OCF-BOD-001';
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await expect(relax).toBeVisible();
  await expect(relax.locator('[data-filter-pinned]')).toContainText('Paused at 0:');
  await fixtureButton.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => player.evaluate(audio => audio.paused)).toBe(false);
  expect(await player.evaluate(audio => audio.currentTime)).toBeGreaterThanOrEqual(pausedPosition);
  await expect(relax.locator('[data-filter-pinned]')).toContainText('Playing Relax');
  await expect.poll(() => player.evaluate(audio => audio.ended), { timeout: 5000 }).toBe(true);
  await expect(relax).toBeVisible();
  await expect(relax.locator('[data-filter-pinned]')).toContainText('Playback ended');
  expect(await player.evaluate(audio => audio.isConnected)).toBe(true);
  expect(await fixtureButton.evaluate(button => document.activeElement === button)).toBe(true);
  await page.keyboard.press('Enter');
  await expect.poll(() => player.evaluate(audio => !audio.paused && !audio.ended)).toBe(true);
  await expect(relax).toBeVisible();
  expect(await player.evaluate(audio => audio.isConnected)).toBe(true);
  expect(await player.evaluate(audio => audio.currentTime)).toBeLessThan(0.5);
  expect(await player.evaluate(audio => audio !== document.querySelector('.session-card[data-function-id="OCF-BOD-001"] audio'))).toBe(true);
  expect(await player.evaluate(audio => audio === document.querySelector('.session-card[data-function-id="OCF-FND-004"] audio'))).toBe(true);
  expect(await player.getAttribute('data-fixture-identity')).toBe('relax-synthetic-wav');
  await page.locator('#clear-library-filters').click();
  await expect(relax.locator('[data-filter-pinned]')).toBeHidden();
  expect(await player.evaluate(audio => audio.isConnected && !audio.paused)).toBe(true);
  expect(audioRequests).toEqual([]);

  const directorySearch = page.locator('#search');
  await directorySearch.fill('PLUS-RELAX');
  await page.evaluate(() => window.scrollTo(0, 300));
  await page.getByRole('link', { name: 'Relax', exact: true }).click();
  await expect(page).toHaveURL(/\/functions\/OCF-FND-004\/$/);
  await page.goBack();
  await expect(directorySearch).toHaveValue('PLUS-RELAX');
  await expect(page.locator('.session-card:visible h3')).toContainText('Relax');
});

test('Back navigation preserves the same active synthetic player position and filter state', async ({ page }) => {
  const audioResponses = [];
  page.on('response', response => {
    if (!/\.(?:mp3|flac)(?:$|[?#])/i.test(response.url())) return;
    audioResponses.push({host: new URL(response.url()).hostname, status: response.status()});
  });
  await useSilentWavFixture(page);
  await page.goto('/functions/');
  const relax = page.locator('.session-card').filter({has: page.getByRole('link', {name: 'Relax', exact: true})});
  const player = relax.locator('audio');
  await player.evaluate(audio => audio.load());
  await expect.poll(() => player.evaluate(audio => audio.duration)).toBeGreaterThan(2.9);
  await player.evaluate(audio => { audio.dataset.fixtureIdentity = 'back-navigation-synthetic-wav'; });
  await relax.evaluate(card => {
    const audio = card.querySelector('audio');
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.backNavigationControl = '';
    button.textContent = 'Play synthetic back-navigation fixture';
    button.addEventListener('click', async () => {
      if (audio.paused || audio.ended) await audio.play();
      else audio.pause();
    });
    card.append(button);
  });
  await relax.locator('[data-back-navigation-control]').focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => player.evaluate(audio => !audio.paused && !audio.ended)).toBe(true);
  await player.evaluate(audio => { audio.currentTime = 1.1; });
  await expect.poll(() => player.evaluate(audio => audio.currentTime)).toBeGreaterThan(1);
  const positionBeforeNavigation = await player.evaluate(audio => audio.currentTime);
  await page.locator('#search').fill('OCF-BOD-001');
  await expect(relax).toBeVisible();
  await expect(relax.locator('[data-filter-pinned]')).toContainText('Playing Relax');

  await relax.getByRole('link', {name: 'Relax', exact: true}).click();
  await expect(page).toHaveURL(/\/functions\/OCF-FND-004\/$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/functions\/$/);
  const restoredPlayer = page.locator('.session-card[data-function-id="OCF-FND-004"] audio');
  await expect(restoredPlayer).toBeAttached();
  await expect(page.locator('#search')).toHaveValue('OCF-BOD-001');
  expect(await restoredPlayer.evaluate(audio => audio.currentSrc.startsWith('data:audio/wav'))).toBe(true);
  const nativePosition = await restoredPlayer.evaluate(audio => audio.currentTime);
  let pendingPosition = Number(await restoredPlayer.getAttribute('data-ocf-resume-position')) || 0;
  await expect(restoredPlayer).toHaveAttribute('data-ocf-restored-bookmark-pending', 'true');
  expect(Math.max(nativePosition, pendingPosition)).toBeGreaterThanOrEqual(positionBeforeNavigation - 0.2);
  await expect(relax).toBeVisible();
  expect(await restoredPlayer.evaluate(audio => audio.paused)).toBe(true);
  await expect(relax.locator('[data-playback-status]')).toContainText('Paused at');

  const firstRestorePosition = Math.max(nativePosition, pendingPosition);
  await relax.getByRole('link', {name: 'Relax', exact: true}).click();
  await expect(page).toHaveURL(/\/functions\/OCF-FND-004\/$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/functions\/$/);
  const secondRestorePlayer = page.locator('.session-card[data-function-id="OCF-FND-004"] audio');
  await expect(secondRestorePlayer).toBeAttached();
  await expect(page.locator('#search')).toHaveValue('OCF-BOD-001');
  pendingPosition = Number(await secondRestorePlayer.getAttribute('data-ocf-resume-position')) || 0;
  const secondNativePosition = await secondRestorePlayer.evaluate(audio => audio.currentTime);
  await expect(secondRestorePlayer).toHaveAttribute('data-ocf-restored-bookmark-pending', 'true');
  expect(Math.max(secondNativePosition, pendingPosition)).toBeGreaterThanOrEqual(firstRestorePosition - 0.2);
  expect(await secondRestorePlayer.evaluate(audio => audio.paused)).toBe(true);
  await expect(relax).toBeVisible();
  await expect(relax.locator('[data-playback-status]')).toContainText('Paused at');
  const expectedResumePosition = Math.max(secondNativePosition, pendingPosition);

  let restoredControl = relax.locator('[data-back-navigation-control]');
  if (await restoredControl.count() === 0) {
    await relax.evaluate(card => {
      const audio = card.querySelector('audio');
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.backNavigationControl = '';
      button.textContent = 'Resume synthetic back-navigation fixture';
      button.addEventListener('click', async () => { if (audio.paused) await audio.play(); else audio.pause(); });
      card.append(button);
    });
    restoredControl = relax.locator('[data-back-navigation-control]');
  }
  await restoredControl.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => secondRestorePlayer.evaluate(audio => !audio.paused && !audio.ended)).toBe(true);
  await expect.poll(() => secondRestorePlayer.evaluate((audio, expected) => audio.currentTime >= expected - 0.2, expectedResumePosition)).toBe(true);
  await expect(secondRestorePlayer).not.toHaveAttribute('data-ocf-restored-bookmark-pending');
  await page.keyboard.press('Enter');
  await expect.poll(() => secondRestorePlayer.evaluate(audio => audio.paused)).toBe(true);
  expect(await secondRestorePlayer.evaluate((audio, expected) => audio.isConnected && audio.currentTime >= expected - 0.2, expectedResumePosition)).toBe(true);

  await secondRestorePlayer.evaluate(audio => { audio.currentTime = 0; });
  await expect.poll(() => page.evaluate(() => {
    const saved = JSON.parse(sessionStorage.getItem('ocf-library-playback:/functions/') || 'null');
    return saved?.position === 0 && saved.positionIsExplicit === true;
  })).toBe(true);
  await expect.poll(() => secondRestorePlayer.evaluate(audio => audio.currentTime)).toBe(0);
  await relax.getByRole('link', {name: 'Relax', exact: true}).click();
  await expect(page).toHaveURL(/\/functions\/OCF-FND-004\/$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/functions\/$/);
  let zeroPositionPlayer = page.locator('.session-card[data-function-id="OCF-FND-004"] audio');
  await expect(zeroPositionPlayer).toBeAttached();
  await expect.poll(() => zeroPositionPlayer.getAttribute('data-ocf-resume-position-explicit')).toBe('true');
  await expect(zeroPositionPlayer).toHaveAttribute('data-ocf-restored-bookmark-pending', 'true');
  expect(await zeroPositionPlayer.evaluate(audio => audio.paused && audio.currentTime === 0)).toBe(true);
  await expect(page.locator('.session-card[data-function-id="OCF-FND-004"] [data-playback-status]')).toContainText('Paused at 0:00');
  await relax.getByRole('link', {name: 'Relax', exact: true}).click();
  await page.goBack();
  await expect(page).toHaveURL(/\/functions\/$/);
  zeroPositionPlayer = page.locator('.session-card[data-function-id="OCF-FND-004"] audio');
  await expect(zeroPositionPlayer).toBeAttached();
  expect(await zeroPositionPlayer.evaluate(audio => audio.paused && audio.currentTime === 0)).toBe(true);
  await zeroPositionPlayer.evaluate(audio => { audio.dataset.fixtureIdentity = 'back-navigation-synthetic-wav'; });
  const zeroResumeControl = page.locator('.session-card[data-function-id="OCF-FND-004"] [data-back-navigation-control]');
  if (await zeroResumeControl.count() === 0) {
    await page.locator('.session-card[data-function-id="OCF-FND-004"]').evaluate(card => {
      const audio = card.querySelector('audio');
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.backNavigationControl = '';
      button.textContent = 'Resume from zero synthetic fixture';
      button.addEventListener('click', async () => { if (audio.paused) await audio.play(); else audio.pause(); });
      card.append(button);
    });
  }
  await zeroResumeControl.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => zeroPositionPlayer.evaluate(audio => !audio.paused && audio.currentTime < 0.5)).toBe(true);
  await expect(zeroPositionPlayer).not.toHaveAttribute('data-ocf-restored-bookmark-pending');
  await page.keyboard.press('Enter');
  await expect.poll(() => zeroPositionPlayer.evaluate(audio => audio.paused)).toBe(true);

  await secondRestorePlayer.evaluate(audio => { audio.currentTime = audio.duration - 0.5; });
  await expect.poll(() => secondRestorePlayer.evaluate(audio => audio.paused && audio.currentTime > 2.4)).toBe(true);
  await restoredControl.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => secondRestorePlayer.evaluate(audio => audio.ended), {timeout: 5000}).toBe(true);
  await expect(relax.locator('[data-playback-status]')).toContainText('Playback ended');
  await relax.getByRole('link', {name: 'Relax', exact: true}).click();
  await expect(page).toHaveURL(/\/functions\/OCF-FND-004\/$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/functions\/$/);
  const endedPlayer = page.locator('.session-card[data-function-id="OCF-FND-004"] audio');
  await expect(endedPlayer).toBeAttached();
  await expect(page.locator('#search')).toHaveValue('OCF-BOD-001');
  expect(await endedPlayer.evaluate(audio => audio.paused && !audio.ended)).toBe(true);
  await expect(page.locator('.session-card[data-function-id="OCF-FND-004"] [data-playback-status]')).toContainText('Playback ended');
  let replayControl = page.locator('.session-card[data-function-id="OCF-FND-004"] [data-back-navigation-control]');
  if (await replayControl.count() === 0) {
    await page.locator('.session-card[data-function-id="OCF-FND-004"]').evaluate(card => {
      const audio = card.querySelector('audio');
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.backNavigationControl = '';
      button.textContent = 'Replay synthetic back-navigation fixture';
      button.addEventListener('click', async () => { if (audio.paused || audio.ended) await audio.play(); else audio.pause(); });
      card.append(button);
    });
    replayControl = page.locator('.session-card[data-function-id="OCF-FND-004"] [data-back-navigation-control]');
  }
  await replayControl.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => endedPlayer.evaluate(audio => !audio.paused && !audio.ended)).toBe(true);
  await expect.poll(() => endedPlayer.evaluate(audio => audio.currentTime < 0.5)).toBe(true);
  await page.keyboard.press('Enter');
  await expect.poll(() => endedPlayer.evaluate(audio => audio.paused)).toBe(true);

  await endedPlayer.evaluate(audio => { audio.currentTime = audio.duration - 0.5; });
  await expect.poll(() => endedPlayer.evaluate(audio => audio.currentTime > 2.4 && !audio.seeking)).toBe(true);
  await replayControl.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => endedPlayer.evaluate(audio => audio.ended), {timeout: 5000}).toBe(true);
  await endedPlayer.evaluate(audio => { audio.currentTime = 1.25; });
  await expect.poll(() => page.evaluate(() => {
    const saved = JSON.parse(sessionStorage.getItem('ocf-library-playback:/functions/') || 'null');
    return saved?.ended === false && saved?.positionIsExplicit === true && saved.position > 1;
  })).toBe(true);
  await relax.getByRole('link', {name: 'Relax', exact: true}).click();
  await expect(page).toHaveURL(/\/functions\/OCF-FND-004\/$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/functions\/$/);
  let soughtAfterEndPlayer = page.locator('.session-card[data-function-id="OCF-FND-004"] audio');
  await expect(soughtAfterEndPlayer).toBeAttached();
  await expect.poll(() => soughtAfterEndPlayer.getAttribute('data-ocf-resume-position')).toBe('1.25');
  await expect(soughtAfterEndPlayer).toHaveAttribute('data-ocf-restored-bookmark-pending', 'true');
  expect(await soughtAfterEndPlayer.evaluate(audio => audio.paused && !audio.ended)).toBe(true);
  await expect(page.locator('.session-card[data-function-id="OCF-FND-004"] [data-playback-status]')).toContainText('Paused at 0:01');
  await relax.getByRole('link', {name: 'Relax', exact: true}).click();
  await page.goBack();
  await expect(page).toHaveURL(/\/$/);
  soughtAfterEndPlayer = page.locator('.session-card[data-function-id="OCF-FND-004"] audio');
  await expect.poll(() => soughtAfterEndPlayer.getAttribute('data-ocf-resume-position')).toBe('1.25');
  await expect(soughtAfterEndPlayer).toHaveAttribute('data-ocf-restored-bookmark-pending', 'true');
  expect(await soughtAfterEndPlayer.evaluate(audio => audio.paused && !audio.ended)).toBe(true);
  expect(audioResponses.filter(response => response.status >= 200 && response.status < 300)).toEqual([]);
});

test('catalog selection and download controls identify session and format', async ({ page }) => {
  await page.goto('/functions/');
  for (const title of ['Relax', 'Brain Flow']) {
    const card = page.locator('.session-card').filter({ has: page.getByRole('link', { name: title, exact: true }) });
    await expect(card).toBeVisible();
    await expect(card.locator('.function-status')).toHaveText('Published recording available');
    for (const summary of await card.locator('details summary').allTextContents()) {
      expect(summary).toMatch(/^(?:MP3|FLAC) file details$/);
    }
    for (const format of ['MP3', 'FLAC']) {
      const checkboxName = new RegExp(`^Select ${format} for ${title}, en-US, Mike — Original Voice, edition 0\\.1\\.0$`);
      await expect(card.getByRole('checkbox', { name: checkboxName })).toBeAttached();
      await expect(card.getByRole('link', { name: new RegExp(`^Download ${format} for ${title},`) })).toBeAttached();
    }
  }
});

test('catalog keeps one synthetic player active and announces a controlled media error', async ({ page }) => {
  const audioRequests = [];
  page.on('request', request => { if (/\.(?:mp3|flac)(?:$|[?#])/i.test(request.url())) audioRequests.push(request.url()); });
  await useSilentWavFixture(page);
  await page.goto('/functions/');
  const relax = page.locator('.session-card').filter({ has: page.getByRole('link', { name: 'Relax', exact: true }) });
  const brain = page.locator('.session-card').filter({ has: page.getByRole('link', { name: 'Brain Flow', exact: true }) });
  const relaxPlayer = relax.locator('audio');
  const brainPlayer = brain.locator('audio');
  await Promise.all([relaxPlayer.evaluate(audio => audio.load()), brainPlayer.evaluate(audio => audio.load())]);
  await expect.poll(() => relaxPlayer.evaluate(audio => audio.duration)).toBeGreaterThan(2.9);
  await expect.poll(() => brainPlayer.evaluate(audio => audio.duration)).toBeGreaterThan(2.9);

  const addFixtureControl = async (card, label) => {
    await card.evaluate((element, buttonLabel) => {
      const player = element.querySelector('audio');
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = buttonLabel;
      button.dataset.syntheticPlayControl = '';
      button.addEventListener('click', async () => {
        if (player.paused || player.ended) await player.play();
        else player.pause();
      });
      element.append(button);
    }, label);
    return card.locator('[data-synthetic-play-control]');
  };
  const relaxControl = await addFixtureControl(relax, 'Play synthetic Relax fixture');
  const brainControl = await addFixtureControl(brain, 'Play synthetic Brain Flow fixture');

  for (const [control, active, other] of [
    [relaxControl, relaxPlayer, brainPlayer],
    [brainControl, brainPlayer, relaxPlayer],
    [relaxControl, relaxPlayer, brainPlayer],
    [brainControl, brainPlayer, relaxPlayer],
  ]) {
    await control.focus();
    await page.keyboard.press('Enter');
    await expect.poll(() => active.evaluate(audio => !audio.paused && !audio.ended)).toBe(true);
    await expect.poll(() => other.evaluate(audio => audio.paused)).toBe(true);
    expect(await page.locator('.session-card audio').evaluateAll(players => players.filter(audio => !audio.paused && !audio.ended).length)).toBe(1);
  }
  await brainControl.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => relaxPlayer.evaluate(audio => audio.paused)).toBe(true);
  await expect.poll(() => brainPlayer.evaluate(audio => audio.paused)).toBe(true);

  await relaxPlayer.evaluate(audio => {
    Object.defineProperty(audio, 'error', { configurable: true, value: { code: 4 } });
    audio.dispatchEvent(new Event('error'));
  });
  await expect(relax.locator('[data-playback-status]')).toContainText('Audio could not be played');
  await expect(relax.getByRole('link', { name: /^Download MP3 for Relax/ })).toBeAttached();
  expect(audioRequests).toEqual([]);
});

test('selected files hidden by filters remain reviewable and removable', async ({ page }) => {
  await page.goto('/functions/');
  const relax = page.locator('.session-card').filter({ has: page.getByRole('link', { name: 'Relax', exact: true }) });
  const brain = page.locator('.session-card').filter({ has: page.getByRole('link', { name: 'Brain Flow', exact: true }) });
  const catalog = await page.request.get('/catalog.json').then(response => response.json());
  const relaxMp3Asset = catalog.releases.flatMap(release => release.functions)
    .find(row => row.function_id === 'OCF-FND-004').sessions[0].assets.find(asset => asset.format === 'mp3');
  const relaxAssetURL = relaxMp3Asset.download_url;
  const relaxMp3 = page.locator(`[data-selected-asset-id="${relaxMp3Asset.asset_id}"]`);
  const brainFlac = brain.getByRole('checkbox', { name: /^Select FLAC for Brain Flow,/ });
  await relaxMp3.check();
  await brainFlac.check();
  await expect(page.locator('#selection-count')).toHaveText('2 files selected');
  const review = page.locator('#selected-files-review');
  await expect(review).toBeVisible();

  await page.locator('#search').fill('OCF-BOD-001');
  await expect(relax).toBeHidden();
  await expect(page.locator('#selection-count')).toHaveText('2 files selected (1 hidden by filters)');
  await review.locator(':scope > summary').focus();
  await page.keyboard.press('Enter');
  await expect(review).toHaveAttribute('open', '');
  await expect(review.locator('#selected-files-summary')).toContainText('1 hidden by filters');
  await expect(review).toContainText('Relax, en-US, Mike — Original Voice, edition 0.1.0 — MP3 (hidden by filters)');
  await expect(review.getByRole('link', { name: 'Open MP3 download for Relax, en-US, edition 0.1.0' })).toHaveAttribute('href', relaxAssetURL);

  await review.getByRole('button', { name: 'Remove MP3 for Relax, edition 0.1.0 from selected files' }).click();
  await expect(page.locator('#selection-count')).toHaveText('1 file selected');
  expect(await relaxMp3.evaluate(checkbox => checkbox.checked)).toBe(false);
  await expect(page.locator('#selection-count')).toBeFocused();
  await page.locator('#clear-library-filters').click();
  await expect(relax).toBeVisible();
  await expect(review.locator('#selected-files-summary')).toContainText('Review selected files (1)');
  await page.locator('#clear-selection').click();
  await expect(page.locator('#selection-count')).toHaveText('0 files selected');
  await expect(review).toBeHidden();
  await expect(page.locator('#selection-count')).toBeFocused();
  expect(await brainFlac.evaluate(checkbox => checkbox.checked)).toBe(false);

  await brain.getByRole('checkbox', { name: /^Select MP3 for Brain Flow,/ }).check();
  await brainFlac.check();
  await page.locator('#clear-selection').click();
  await expect(page.locator('#selection-count')).toHaveText('0 files selected');
  await expect(page.locator('#selection-count')).toBeFocused();
  expect(await brain.getByRole('checkbox', { name: /^Select MP3 for Brain Flow,/ }).evaluate(checkbox => checkbox.checked)).toBe(false);
});

test('function titles expose direct Listen/MP3/FLAC actions for each published edition', async ({ page }) => {
  await page.goto('/functions/OCF-FND-004/');
  const catalog = await page.request.get('/catalog.json').then(response => response.json());
  const session = catalog.releases.flatMap(release => release.functions)
    .find(row => row.function_id === 'OCF-FND-004').sessions[0];
  const anchorAsset = session.assets[0];
  const actions = page.locator('.function-audio-actions');
  const label = `Relax, en-US, edition ${session.edition}`;
  await expect(actions).toBeVisible();
  await expect(actions.getByRole('link', { name: `Listen to ${label}` })).toHaveAttribute('href', `#session-${anchorAsset.asset_id}`);
  for (const format of ['mp3', 'flac']) {
    const asset = session.assets.find(row => row.format === format);
    await expect(actions.getByRole('link', { name: `Download ${format.toUpperCase()} for ${label}` })).toHaveAttribute('href', asset.download_url);
  }
  await expect(page.locator(`#session-${anchorAsset.asset_id} audio`)).toBeAttached();
  await noAxeViolations(page, '.function-audio-actions');
});

test('bounded public release MP3 playback or unavailable-media fallback is verified in this browser', async ({ page, browserName }) => {
  test.skip(process.env.OCF_REAL_AUDIO_TESTS !== '1', 'Set OCF_REAL_AUDIO_TESTS=1 to allow a capped public release-media probe.');
  test.setTimeout(90000);
  const catalog = await page.request.get('/catalog.json').then(response => response.json());
  const fn = catalog.releases.flatMap(release => release.functions).find(row => row.function_id === 'OCF-FND-004');
  const session = fn.sessions.find(row => row.title === 'Relax');
  const asset = session.assets.find(row => row.format === 'mp3');
  const anchorAsset = session.assets[0];
  expect(asset).toBeTruthy();
  expect(asset.sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(asset.size_bytes).toBeGreaterThan(0);
  const maxRangeBytes = 256 * 1024;
  const maxRequests = 32;
  const maxTotalBytes = maxRangeBytes * maxRequests;
  let budgetExceeded = false;
  const ranges = [];
  const rangeResponses = [];
  const mediaRequests = [];
  const mediaFailures = [];
  const audioResponses = [];
  const budgetFailures = [];
  const matchesAudioURL = rawURL => {
    try { return decodeURIComponent(rawURL).includes(asset.filename); }
    catch (_) { return false; }
  };
  await page.route(url => matchesAudioURL(url.href), async route => {
    if (ranges.length >= maxRequests) {
      budgetExceeded = true;
      budgetFailures.push('request-count-cap');
      await route.abort();
      return;
    }
    const headers = route.request().headers();
    const match = /^bytes=(\d+)-(\d*)$/i.exec(headers.range || 'bytes=0-');
    if (!match) {
      budgetExceeded = true;
      budgetFailures.push(`unsupported-range:${headers.range || 'missing'}`);
      await route.abort();
      return;
    }
    const start = Number(match[1]);
    const requestedEnd = match[2] ? Number(match[2]) : start + maxRangeBytes - 1;
    const end = Math.min(requestedEnd, start + maxRangeBytes - 1, asset.size_bytes - 1);
    if (end < start) {
      budgetExceeded = true;
      budgetFailures.push(`invalid-range:${start}-${end}`);
      await route.abort();
      return;
    }
    headers.range = `bytes=${start}-${end}`;
    ranges.push({host: new URL(route.request().url()).hostname, start, end});
    await route.continue({headers});
  });
  page.on('request', request => {
    if (!matchesAudioURL(request.url())) return;
    const url = new URL(request.url());
    mediaRequests.push({host: url.hostname, resourceType: request.resourceType(), range: request.headers().range || null});
  });
  page.on('requestfailed', request => {
    if (!matchesAudioURL(request.url())) return;
    const url = new URL(request.url());
    mediaFailures.push({host: url.hostname, error: request.failure()?.errorText || 'unknown'});
  });
  page.on('response', response => {
    if (!matchesAudioURL(response.url())) return;
    const headers = response.headers();
    const url = new URL(response.url());
    audioResponses.push({host: url.hostname, status: response.status(), resourceType: response.request().resourceType(), contentType: headers['content-type'] || null, contentRange: headers['content-range'] || null});
    const contentRange = /^bytes (\d+)-(\d+)\/(\d+)$/i.exec(headers['content-range'] || '');
    if (contentRange) rangeResponses.push({host: url.hostname, status: response.status(), start: Number(contentRange[1]), end: Number(contentRange[2]), total: Number(contentRange[3])});
  });
  const assertMediaBudget = () => {
    expect(budgetExceeded, `bounded public media request guard: ${budgetFailures.join(', ')} (${ranges.length} ranges)`).toBe(false);
    expect(ranges.length).toBeGreaterThan(0);
    expect(ranges.length).toBeLessThanOrEqual(maxRequests);
    expect(ranges.every(range => range.end - range.start + 1 <= maxRangeBytes)).toBe(true);
    expect(rangeResponses.length).toBeGreaterThan(0);
    expect(rangeResponses.every(range => range.status === 206 && range.end - range.start + 1 <= maxRangeBytes && range.total === asset.size_bytes)).toBe(true);
    const bytes = rangeResponses.reduce((total, range) => total + range.end - range.start + 1, 0);
    expect(bytes).toBeLessThanOrEqual(maxTotalBytes);
    return bytes;
  };

  await page.goto('/functions/OCF-FND-004/');
  const actions = page.locator('.function-audio-actions');
  const editionLabel = `Relax, en-US, edition ${session.edition}`;
  await expect(actions.getByRole('link', {name: `Listen to ${editionLabel}`})).toHaveAttribute('href', `#session-${anchorAsset.asset_id}`);
  await expect(actions.getByRole('link', {name: `Download MP3 for ${editionLabel}`})).toHaveAttribute('href', asset.download_url);
  const player = page.locator(`#session-${anchorAsset.asset_id} audio`);
  const playbackStatus = page.locator(`#session-${anchorAsset.asset_id} [data-playback-status]`);
  await expect(player).toHaveAttribute('preload', 'none');
  await expect(player.locator('source')).toHaveAttribute('src', asset.download_url);
  await player.evaluate(audio => audio.load());
  let metadataReady = false;
  try {
    await expect.poll(() => player.evaluate(audio => Number.isFinite(audio.duration) && audio.readyState >= HTMLMediaElement.HAVE_METADATA), {timeout: 12000}).toBe(true);
    metadataReady = true;
  } catch (error) {
    if (browserName !== 'webkit') {
      const state = await player.evaluate(audio => ({readyState: audio.readyState, networkState: audio.networkState, duration: audio.duration, error: audio.error?.code || null}));
      throw new Error(`Public audio metadata did not load: ${JSON.stringify({state, mediaRequests, mediaFailures, audioResponses, ranges, rangeResponses})}; ${error.message}`);
    }
    const state = await player.evaluate(audio => ({readyState: audio.readyState, networkState: audio.networkState, noSource: audio.networkState === HTMLMediaElement.NETWORK_NO_SOURCE, duration: audio.duration, error: audio.error?.code || null}));
    expect(state.readyState, `WebKit must surface native unavailability: ${JSON.stringify(state)}`).toBe(0);
    expect(state.noSource).toBe(true);
    await expect(playbackStatus).toContainText('Audio could not be played', {timeout: 3000});
    await expect(actions.getByRole('link', {name: `Download MP3 for ${editionLabel}`})).toHaveAttribute('href', asset.download_url);
    const bytes = assertMediaBudget();
    console.log(`WebKit direct-media outcome: browser could not select this release stream; accessible error and direct download are available. ${rangeResponses.length} HTTP 206 ranges, ${bytes} bytes, each capped at ${maxRangeBytes}.`);
    return;
  }
  expect(metadataReady).toBe(true);
  expect(await player.evaluate(audio => audio.duration)).toBeGreaterThan(1000);

  await page.locator('.page-intro').evaluate(intro => {
    const player = document.querySelector('.edition-card audio');
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.publicMediaProbe = '';
    button.textContent = 'Start bounded public playback probe';
    button.addEventListener('click', async () => {
      if (player.paused || player.ended) await player.play();
      else player.pause();
    });
    intro.append(button);
  });
  const probe = page.locator('[data-public-media-probe]');
  await probe.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => player.evaluate(audio => !audio.paused && !audio.ended), {timeout: 12000}).toBe(true);
  await expect.poll(() => player.evaluate(audio => audio.currentTime), {timeout: 12000}).toBeGreaterThan(0.5);
  await page.keyboard.press('Enter');
  await expect.poll(() => player.evaluate(audio => audio.paused), {timeout: 5000}).toBe(true);
  const pausedAt = await player.evaluate(audio => audio.currentTime);
  const seekTo = pausedAt + 5;
  await player.evaluate((audio, target) => { audio.currentTime = target; }, seekTo);
  await expect.poll(() => player.evaluate((audio, target) => !audio.seeking && audio.currentTime >= target - 0.25, seekTo), {timeout: 15000}).toBe(true);
  const seekedTo = await player.evaluate(audio => audio.currentTime);
  expect(seekedTo).toBeGreaterThanOrEqual(seekTo - 0.25);
  await page.keyboard.press('Enter');
  await expect.poll(() => player.evaluate(audio => !audio.paused && !audio.ended), {timeout: 8000}).toBe(true);
  await expect.poll(() => player.evaluate((audio, previous) => audio.currentTime > previous + 0.25, seekedTo), {timeout: 10000}).toBe(true);
  await page.keyboard.press('Enter');
  await expect.poll(() => player.evaluate(audio => audio.paused), {timeout: 5000}).toBe(true);

  const boundedResponseBytes = assertMediaBudget();
  console.log(`Public release media probe (${asset.format}): ${rangeResponses.length} HTTP 206 ranges, ${boundedResponseBytes} response bytes; per-range cap ${maxRangeBytes}, total cap ${maxTotalBytes}.`);
  await expect(playbackStatus).toContainText('Paused at');
});

test('Android-like touch users can open and follow the primary mobile navigation', async ({ browser, browserName }) => {
  test.skip(browserName !== 'chromium', 'Playwright mobile emulation is Chromium-only');
  const context = await browser.newContext({ viewport: { width: 320, height: 640 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  try {
    const mobilePage = await context.newPage();
    await mobilePage.goto('http://127.0.0.1:4173/');
    await mobilePage.locator('.mobile-nav > summary').tap();
    await expect(mobilePage.locator('.mobile-nav')).toHaveAttribute('open', '');
    await mobilePage.locator('.mobile-nav a[href="start/"]').tap();
    await expect(mobilePage).toHaveURL(/\/start\/$/);
    await expect(mobilePage.locator('#main')).toContainText('Complete Preparation Learning before using any OCF function.');
  } finally {
    await context.close();
  }
});

test('Listening Guide and Preparation Learning clearly state preparation-first guidance and exception limits', async ({ page }) => {
  await page.goto('/listening/');
  const guidance = page.locator('#preparation-learning-first').locator('..');
  await expect(guidance).toBeVisible();
  await expect(guidance).toContainText('Complete Preparation Learning before using any OCF function.');
  await expect(guidance).toContainText('Only people who have already learned the official Human Plus preparation track may skip it.');
  await expect(page.locator('.preparation-first-link a')).toHaveAttribute('href', '../preparation-learning/');
  await expect(guidance).not.toContainText('Michael');
  await expect(guidance).not.toContainText('not a verified official OCF policy');
  await expect(page.locator('main')).not.toContainText('Function guides distinguish exact display cues from exact spoken cues.');
  await expect(page.locator('main')).not.toContainText('Michael');
  await expect(page.locator('main')).not.toContainText('not a verified official OCF policy');
  const guideText = await page.locator('main').innerText();
  expect(guideText.match(/Stereo headphones or stereo earbuds with separate left\/right playback are required/g)).toHaveLength(1);
  expect(guideText.match(/Do not listen while driving, operating equipment, or doing anything requiring vigilance\./g)).toHaveLength(1);
  expect(guideText).not.toContain('What OCF is');
  expect(guideText).not.toContain('mono mixing does not provide equivalent delivery. Separately');
  expect(guideText).not.toContain('Preserve separate left/right stereo playback for intended');
  for (const id of ['welcome-to-ocf', 'what-ocf-is', 'a-comfortable-environment']) {
    await expect(page.locator(`[id="${id}"]`)).toHaveCount(1);
  }

  expect(guideText).toContain('58 of 58 canonical function guides have at least one published recording');
  expect(guideText).toContain('audio-0.1.0-a6-20261111 (edition 0.1.0)');
  await noAxeViolations(page);
  await page.goto('/preparation-learning/');
  const intro = page.locator('.page-intro');
  await expect(intro).toContainText('Complete Preparation Learning before using any OCF function.');
  await expect(intro).toContainText('Only people who have already learned the official Human Plus preparation track may skip it.');
  await expect(intro).not.toContainText('Michael');
  await expect(intro).not.toContainText('not a verified official OCF policy');
  await expect(page.locator('main')).not.toContainText('Michael');
  await expect(page.locator('main')).not.toContainText('not a verified official OCF policy');
  await noAxeViolations(page);
});

test('generated listening and all platform guides require stereo for binaural delivery without changing assets', async ({ page }) => {
  const required = 'Stereo headphones or stereo earbuds with separate left/right playback are required for the intended binaural/channel-separated audio.';
  await page.goto('/listening/');
  const guide = await page.locator('main').innerText();
  expect(guide).toContain(required);
  expect(guide).toContain('Speakers, mono mixing, or a single earpiece are not equivalent delivery of that audio.');
  expect(guide).toContain('use the written guide or an edition-matched transcript if available, or skip the audio');
  expect(guide).toContain('no equivalent effects are promised');
  expect(guide).not.toContain('Can I listen without stereo headphones?');
  expect(guide).not.toContain('Yes. Speakers, mono playback');

  const settings = page.locator('#recommended-audio-settings');
  await expect(settings).toContainText('Headphones and stereo');
  await expect(settings.locator('h3')).toHaveText('Processing preferences');

  for (const platform of ['android', 'ios', 'linux', 'macos', 'windows']) {
    await page.goto(`/listening/${platform}/`);
    const text = await page.locator('main').innerText();
    expect(text, platform).toContain(required);
    expect(text, platform).toContain('not equivalent delivery of that audio');
    expect(text, platform).toContain('or skip the audio');
    expect(text, platform).not.toContain('stereo baseline is optional');
  }

  const receipt = await page.request.get('/site-build-receipt.json').then(response => response.json());
  expect(receipt.catalog_sha256).toBe('db878436e6e15fc64bd9f4b96a398d2612fbc78cf34033ff11f6a526ce137eac');
  expect(receipt.published_session_count).toBe(59);
  expect(receipt.audio_asset_count).toBe(118);
  expect(receipt.published_releases[0].publication_manifest_sha256).toBe('48cb39bcc3dfd7f7e211b3093cd927c3a790cd9ad28d6b47faad956014c85c14');
  await page.goto('/historical-names/');
  await expect(page.locator('[data-historical-name-entry]')).toHaveCount(43);
  expect(receipt.historical_name_count).toBe(94);
  await noAxeViolations(page);
});

test('release downloads stay direct and mobile users get a truthful copy-and-rename filename suggestion', async ({ page, context, browserName }) => {
  const catalog = await page.request.get('/catalog.json').then(response => response.json());
  const release = catalog.releases[0];
  const session = release.functions.find(row => row.function_id === 'OCF-FND-004').sessions[0];
  const mp3 = session.assets.find(asset => asset.format === 'mp3');
  const routeHit = [];
  await page.route(mp3.download_url, async route => {
    routeHit.push(true);
    await route.fulfill({
      status: 200,
      contentType: 'audio/mpeg',
      headers: { 'Content-Disposition': `attachment; filename="${mp3.filename}"` },
      body: Buffer.from([0x49]),
    });
  });
  if (browserName === 'chromium') {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  }

  await page.setViewportSize({ width: 320, height: 900 });
  await page.goto('/functions/OCF-FND-004/');
  const row = page.locator('.asset-download[data-download-format="mp3"]');
  await expect(row).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
  expect(await row.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);

  await row.locator('.file-details summary').click();
  const suggested = await row.locator('.file-details code').nth(1).textContent();
  expect(suggested).toContain('OCF-FND-004');
  expect(suggested).toContain('Relax');
  expect(suggested).toContain(session.locale);
  expect(suggested).toContain('Mike');
  expect(suggested).toContain(`v${session.edition}`);
  expect(suggested).toContain(release.tag);
  expect(suggested.endsWith('.mp3')).toBe(true);
  expect(suggested).not.toContain(mp3.filename.slice(-16, -4));

  const link = row.locator('a.download-link');
  await expect(link).toHaveAttribute('href', mp3.download_url);
  await expect(link).toHaveAttribute('download', suggested);
  await expect(page.locator('main')).toContainText('rename it locally if needed');
  await expect(page.locator('main')).toContainText('does not buffer audio');
  const copy = row.getByRole('button', { name: 'Copy suggested filename for MP3' });
  await expect(copy).toBeVisible();
  await expect(copy).toHaveAttribute('data-copy', suggested);
  if (browserName === 'chromium') {
    await copy.click();
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(suggested);
  } else {
    await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: async () => { throw new Error('clipboard unavailable'); } },
    }));
    await copy.click();
    await expect(copy).toHaveText(suggested);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
  }

  if (browserName === 'webkit') {
    const requestPromise = page.waitForRequest(mp3.download_url);
    const responsePromise = page.waitForResponse(mp3.download_url);
    await link.click();
    const [request, response] = await Promise.all([requestPromise, responsePromise]);
    expect(request.url()).toBe(mp3.download_url);
    expect(response.status()).toBe(200);
    expect(response.headers()['content-disposition']).toContain(mp3.filename);
    expect(routeHit).toHaveLength(1);
    return;
  }
  const [download] = await Promise.all([page.waitForEvent('download'), link.click()]);
  expect(routeHit).toHaveLength(1);
  expect(download.suggestedFilename()).toBe(mp3.filename);
  expect(download.suggestedFilename()).not.toBe(suggested);
});

test('cross-origin release response behavior is explicit without buffering the release asset', async ({ page, browserName }) => {
  const catalog = await page.request.get('/catalog.json').then(response => response.json());
  const release = catalog.releases[0];
  const session = release.functions.find(row => row.function_id === 'OCF-FND-004').sessions[0];
  const mp3 = session.assets.find(asset => asset.format === 'mp3');
  const deliveredBytes = Buffer.from([0x49]);
  await page.route(mp3.download_url, route => route.fulfill({
    status: 200,
    contentType: 'audio/mpeg',
    headers: { 'Content-Disposition': `attachment; filename="${mp3.filename}"` },
    body: deliveredBytes,
  }));
  await page.goto('/functions/OCF-FND-004/');
  const row = page.locator('.asset-download[data-download-format="mp3"]');
  const friendly = await row.locator('.download-link').getAttribute('download');
  expect(friendly).not.toBe(mp3.filename);
  if (browserName === 'webkit') {
    const requestPromise = page.waitForRequest(mp3.download_url);
    const responsePromise = page.waitForResponse(mp3.download_url);
    await row.locator('.download-link').click();
    const [request, response] = await Promise.all([requestPromise, responsePromise]);
    expect(request.url()).toBe(mp3.download_url);
    expect(response.status()).toBe(200);
    expect(response.headers()['content-disposition']).toContain(mp3.filename);
    expect(deliveredBytes.byteLength).toBe(1);
    return;
  }
  const [download] = await Promise.all([page.waitForEvent('download'), row.locator('.download-link').click()]);
  expect(download.suggestedFilename()).toBe(mp3.filename);
  expect(download.suggestedFilename()).not.toBe(friendly);
  expect(deliveredBytes.byteLength).toBe(1);
  expect(browserName).toMatch(/^(chromium|firefox|webkit)$/);
});

test('Quick Reference filters, keyboard controls, narrow widths, print, themes, transcript and deep links work', async ({ page, browserName }) => {
  for (const width of [320, 375, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/quick-reference/');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    await expect(page.locator('.reference-table tbody tr')).toHaveCount(58);
    await expect(page.getByRole('table', {name: 'Current cues, function descriptions, and audio availability'})).toBeVisible();
    await expect(page.locator('.reference-table tbody tr').first().locator('td[data-label="Description"]')).toBeVisible();
    await expect(page.locator('.reference-table tbody tr').first().locator('td[data-label="Published audio availability"]')).toContainText('Published audio available');
    expect(await page.locator('.reference-table').evaluate(table => table.scrollWidth <= table.clientWidth)).toBe(true);
    await expect(page.locator('.historical-cue')).toHaveCount(0);
    await expect(page.locator('.reference-table .copy-cue')).toHaveCount(0);
    await expect(page.locator('.reference-table strong').first()).toHaveText('Plus Automate');
  }

  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto('/quick-reference/');
  const search = page.getByLabel('Search title, ID, spoken cue or description');
  await search.focus();
  await page.keyboard.type('OCF-EXP-001');
  await expect(page.locator('[data-reference-count]')).toHaveText('1 function');
  await search.fill('Plus Focus');
  await expect(page.locator('[data-reference-count]')).toHaveText('1 function');
  const domain = page.getByLabel('Category');
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
  const initialTheme = await page.locator('[data-theme-toggle]').getAttribute('data-theme-preference');
  await page.locator('[data-theme-toggle]').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('[data-theme-toggle]')).not.toHaveAttribute('data-theme-preference', initialTheme);

  await page.goto('/functions/OCF-FND-004/');
  const transcript = page.locator('[data-transcript]').first();
  await transcript.locator(':scope > summary').click();
  await expect(transcript.locator('.transcript-body')).not.toContainText('Transcript loads when expanded.');
  await expect(transcript.locator('.transcript-search input')).toBeEnabled();
  const transcriptHeight = await transcript.locator('.transcript-body').evaluate(el => el.scrollHeight);
  expect(transcriptHeight).toBeGreaterThan(512);
  expect(await transcript.locator('.transcript-body').evaluate(el => getComputedStyle(el).maxHeight)).toBe('none');
  expect(await transcript.locator('.transcript-body').evaluate(el => getComputedStyle(el).overflowY)).toBe('visible');
  expect(await transcript.locator('.transcript-body').evaluate(el => el.scrollHeight <= el.clientHeight + 1)).toBe(true);
  await transcript.locator('.transcript-body').evaluate(el => el.scrollIntoView({block: 'end'}));
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

test('mobile Quick Reference cards retain descriptions, cues, and accurate audio status', async ({ page }) => {
  await page.setViewportSize({width: 320, height: 900});
  await page.goto('/quick-reference/');
  const rows = page.locator('.quick-reference-table tbody tr[data-reference-row]');
  await expect(rows).toHaveCount(58);
  await expect(page.getByRole('columnheader', {name: 'Description'})).toHaveCount(1);
  await expect(page.getByRole('columnheader', {name: 'Audio availability'})).toHaveCount(1);
  for (const row of await rows.all()) {
    for (const label of ['Current spoken cues', 'Description', 'Published audio availability']) {
      const cell = row.locator(`td[data-label="${label}"]`);
      await expect(cell).toBeVisible();
      await expect(cell).toContainText(/\S/);
    }
  }
  await expect(page.getByRole('table', {name: 'Current cues, function descriptions, and audio availability'})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
  expect(await page.locator('.quick-reference-table').evaluate(table => table.scrollWidth <= table.clientWidth)).toBe(true);
});

test('all five device baselines render the exact source checklist as semantic lists', async ({ page }) => {
  for (const platform of ['android', 'ios', 'windows', 'macos', 'linux']) {
    const markdown = await fs.readFile(path.join(__dirname, '../docs/website/listening', `${platform}.md`), 'utf8');
    const lines = markdown.split(/\r?\n/);
    const start = lines.indexOf('## Baseline');
    expect(start, `${platform} baseline heading exists in source`).toBeGreaterThanOrEqual(0);
    const expected = [];
    for (const line of lines.slice(start + 1)) {
      if (/^## /.test(line)) break;
      if (line.startsWith('- ')) expected.push(line.slice(2));
      else if (expected.length && /^\s{2,}\S/.test(line)) expected[expected.length - 1] += ` ${line.trim()}`;
      else if (line.trim()) throw new Error(`Unexpected non-list baseline content in ${platform}: ${line}`);
    }
    const pageResponse = await page.goto(`/listening/${platform}/`);
    expect(pageResponse?.ok()).toBe(true);
    const baseline = page.locator('#baseline');
    const list = baseline.locator('xpath=following-sibling::ul[1]');
    await expect(list).toBeVisible();
    const actual = (await list.locator('li').allTextContents()).map(text => text.replace(/\s+/g, ' ').trim());
    expect(actual).toEqual(expected.map(text => text.replace(/\s+/g, ' ').trim()));
  }
});

test('mobile transcript expands into natural page reading and retries a failed exact-edition load', async ({ page }) => {
  await page.setViewportSize({width: 375, height: 900});
  let transcriptRequests = 0;
  await page.route('**/transcripts/*.txt', async route => {
    transcriptRequests += 1;
    if (transcriptRequests === 1) await route.abort();
    else await route.continue();
  });
  await page.goto('/functions/OCF-FND-004/');
  const transcript = page.locator('[data-transcript]').first();
  const summary = transcript.locator(':scope > summary');
  await summary.scrollIntoViewIfNeeded();
  const scrollBeforeExpansion = await page.evaluate(() => window.scrollY);
  await summary.click();
  await expect(transcript.locator('[data-transcript-status]')).toContainText('Transcript unavailable');
  expect(Math.abs(await page.evaluate(() => window.scrollY) - scrollBeforeExpansion)).toBeLessThan(24);
  const retry = transcript.locator('[data-transcript-retry]');
  await expect(retry).toBeVisible();
  await noAxeViolations(page);
  await retry.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => transcript.locator('.transcript-body').textContent()).not.toContain('Transcript loads when expanded.');
  await expect(transcript.locator('[data-transcript-status]')).toContainText('transcript loaded');
  await expect(retry).toBeHidden();
  expect(Math.abs(await page.evaluate(() => window.scrollY) - scrollBeforeExpansion)).toBeLessThan(24);
  const body = transcript.locator('.transcript-body');
  const mediaLayout = await body.evaluate(element => ({
    maxHeight: getComputedStyle(element).maxHeight,
    overflowY: getComputedStyle(element).overflowY,
    scrollHeight: element.scrollHeight,
    clientHeight: element.clientHeight,
  }));
  expect(mediaLayout.maxHeight).toBe('none');
  expect(mediaLayout.overflowY).toBe('visible');
  expect(mediaLayout.scrollHeight).toBeLessThanOrEqual(mediaLayout.clientHeight + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375);
  await expect(transcript.getByRole('link', {name: /Download transcript text for Relax, edition 0.1.0, en-US/})).toHaveAttribute('href', /\/transcripts\/.*\.txt$/);
  await expect(transcript.getByRole('link', {name: /Original release asset, TXT for Relax, edition 0.1.0, en-US/})).toHaveAttribute('href', /^https:\/\/github\.com\//);
  const timed = page.getByRole('link', {name: /Download timed subtitles for Relax, edition 0.1.0, en-US/});
  await expect(timed).toHaveAttribute('href', /\/transcripts\/.*\.vtt$/);
  await expect(page.getByRole('link', {name: /Original release asset, VTT for Relax, edition 0.1.0, en-US/})).toHaveAttribute('href', /^https:\/\/github\.com\//);
  expect(transcriptRequests).toBe(2);
});

test('About leads with reader context and keeps provenance in native disclosure', async ({ page }) => {
  await page.goto('/about/');
  await expect(page.locator('h1')).toHaveText('About OCF');
  const introText = await page.locator('.page-intro').innerText();
  expect(introText).toContain('independent, open-source library');
  expect(introText).toContain('Read the guide');
  expect(introText).toContain('Report a website or catalog issue');
  expect(introText).not.toContain('source commit');
  const transparency = page.locator('.technical-transparency');
  await expect(transparency).not.toHaveAttribute('open', '');
  await transparency.locator(':scope > summary').click();
  await expect(transparency).toContainText('704440da8e0379cee8dfd332203bc0001c0a5f27');
  await expect(transparency).toContainText('audio-0.1.0-a6-20261111');
  await expect(page.locator('main')).toContainText('not healthcare or emergency advice');
  await noAxeViolations(page);
});

test('mobile navigation, spoken cue text without redundant cue copy controls, focus order, and accessibility', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto('/functions/OCF-SLP-002/');
  await expect(page.locator('.spoken-cue strong').first()).toHaveText('Plus Sleep');
  await expect(page.locator('button.copy-cue, button[aria-label^="Copy cue:"]')).toHaveCount(0);
  await page.locator('.mobile-nav > summary').focus();
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
