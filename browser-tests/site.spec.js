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
  expect(hero).toContain('Complete Preparation Learning before using any OCF function.');
  expect(hero).toContain('Only people who have already learned the official Human Plus preparation track may skip it.');
  expect(homeText).not.toContain('Michael');
  expect(homeText).not.toContain('not a verified official OCF policy');
  await expect(page.locator('.desktop-nav a').first()).toHaveAttribute('href', 'start/');
  await expect(page.locator('.path-card').first()).toHaveAttribute('href', 'start/');
  await expect(page.locator('.desktop-nav a[href="preparation-learning/"]')).toHaveCount(0);
  await expect(page.locator('.path-card[href="preparation-learning/"]')).toHaveCount(0);
  await expect(page.locator('.docs-hero .button-light')).toHaveAttribute('href', 'start/');
  await expect(page.locator('.docs-hero a[href="preparation-learning/"]')).toHaveCount(0);
  await expect(page.locator('.desktop-nav a[href="functions/"]')).toHaveCount(1);
  const quickPath = page.locator('.path-card[href="quick-reference/"]');
  await expect(quickPath).toContainText('current spoken cues');
  await expect(quickPath).not.toContainText('display/spoken');
});

test('historical names appear only in their source-authoritative lookup page', async ({ page }) => {
  await page.goto('/historical-names/');
  const receipt = await page.request.get('/site-build-receipt.json').then(response => response.json());
  await expect(page.locator('[data-historical-name-entry]')).toHaveCount(43);
  expect(receipt.historical_mapping_count).toBe(43);
  expect(receipt.historical_name_count).toBe(95);
  await expect(page.locator('[data-also-current="true"]')).toHaveCount(4);
  expect(receipt.historical_name_kind_counts).toEqual({
    'former-primary': 25,
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
  const strong = historicalRow('OCF-PRF-002', 'PLUS-STRONG');
  await expect(strong).toHaveAttribute('data-historical-kind', 'former-primary');
  await expect(strong).toHaveAttribute('data-also-current', 'false');
  await expect(strong.locator('.historical-name-kind')).toHaveText('Former primary cue');
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

test('mobile navigation stays readable, in-flow, keyboard-operable, and overflow-free through zoom widths', async ({ page }) => {
  await page.goto('/');
  for (const width of [160, 320, 360, 375, 390, 414, 760, 768, 820, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth), `horizontal overflow at ${width}px`).toBeLessThanOrEqual(width);
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
      await page.goto('/');
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
      const documentationLink = page.locator('.docs-content .source-link a').first();
      await documentationLink.hover();
      const documentationHover = await page.evaluate(link => ({
        foreground: getComputedStyle(link).color,
        background: getComputedStyle(document.body).backgroundColor,
      }), await documentationLink.elementHandle());
      expect(contrast(documentationHover.foreground, documentationHover.background), `${preference}/${osTheme} documentation-link hover`).toBeGreaterThanOrEqual(4.5);
    }
  }
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
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
  const search = page.locator('[data-function-search]');
  for (const query of ['PLUS-RELAX', '  Plus   Relax  ', 'plus—relax']) {
    await search.fill(query);
    await expect(page.locator('[data-function-card]:visible')).toHaveCount(1);
    await expect(page.locator('[data-function-card]:visible h2')).toContainText('Relax');
  }
  await search.fill('no-such-current-cue');
  await expect(page.locator('[data-function-no-results]')).toBeVisible();
  await expect(page.locator('[data-function-clear]')).toBeVisible();
  await page.locator('[data-function-clear]').click();
  await expect(search).toHaveValue('');
  await expect(page.locator('[data-function-card]:visible')).toHaveCount(58);

  await search.fill('PLUS-STRONG');
  await expect(page.locator('[data-function-card][data-search*="inner power"]')).toBeHidden();
  await expect(page.locator('[data-function-card]:visible h2')).toContainText('Strong-Quick');

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

test('catalog filters preserve the active player element and search state without fetching audio bytes', async ({ page }) => {
  const audioRequests = [];
  page.on('request', request => { if (/\.(?:mp3|flac)(?:$|[?#])/i.test(request.url())) audioRequests.push(request.url()); });
  await page.addInitScript(() => {
    Object.defineProperty(HTMLMediaElement.prototype, 'src', {
      configurable: true,
      get() { return this.dataset.fixtureSource || ''; },
      set(value) { this.dataset.fixtureSource = String(value); },
    });
  });
  await page.goto('/');
  const relax = page.locator('.session-card').filter({ has: page.getByRole('link', { name: 'Relax', exact: true }) });
  const player = relax.locator('audio');
  await expect(player).toBeAttached();
  await player.evaluate(audio => {
    Object.defineProperty(audio, 'paused', { configurable: true, value: false });
    Object.defineProperty(audio, 'ended', { configurable: true, value: false });
    Object.defineProperty(audio, 'currentTime', { configurable: true, writable: true, value: 42.25 });
    audio.dataset.fixtureIdentity = 'controlled-mock-player';
  });
  await page.locator('#search').fill('OCF-BOD-001');
  await expect(page.locator('#results-count')).toContainText('1 matching session edition');
  await expect(relax).toBeVisible();
  await expect(relax.locator('[data-filter-pinned]')).toBeVisible();
  const state = await player.evaluate(audio => ({ connected: audio.isConnected, currentTime: audio.currentTime, paused: audio.paused, fixture: audio.dataset.fixtureIdentity }));
  expect(state).toEqual({ connected: true, currentTime: 42.25, paused: false, fixture: 'controlled-mock-player' });
  await page.locator('#clear-library-filters').click();
  await expect(relax.locator('[data-filter-pinned]')).toBeHidden();
  expect(await player.evaluate(audio => audio.isConnected && audio.currentTime === 42.25 && !audio.paused)).toBe(true);
  expect(audioRequests).toEqual([]);

  await page.goto('/functions/');
  const directorySearch = page.locator('[data-function-search]');
  await directorySearch.fill('PLUS-RELAX');
  await page.evaluate(() => window.scrollTo(0, 300));
  await page.getByRole('link', { name: 'Relax', exact: true }).click();
  await expect(page).toHaveURL(/\/functions\/OCF-FND-004\/$/);
  await page.goBack();
  await expect(directorySearch).toHaveValue('PLUS-RELAX');
  await expect(page.locator('[data-function-card]:visible h2')).toContainText('Relax');
});

test('catalog selection and download controls identify session and format', async ({ page }) => {
  await page.goto('/');
  for (const title of ['Relax', 'Brain Flow']) {
    const card = page.locator('.session-card').filter({ has: page.getByRole('link', { name: title, exact: true }) });
    await expect(card).toBeVisible();
    for (const format of ['MP3', 'FLAC']) {
      const checkboxName = new RegExp(`^Select ${format} for ${title}, en-US, Mike — Original Voice, edition 0\\.1\\.0$`);
      await expect(card.getByRole('checkbox', { name: checkboxName })).toBeAttached();
      await expect(card.getByRole('link', { name: new RegExp(`^Download ${format} for ${title},`) })).toBeAttached();
    }
  }
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
  await expect(settings).toContainText(required);
  await expect(settings.locator('h3')).toHaveText('Optional processing preferences');

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
  expect(receipt.historical_name_count).toBe(95);
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

  const suggested = await row.locator('.download-name-note code').textContent();
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
  await expect(row).toContainText('rename the downloaded file locally');
  await expect(row).toContainText('not buffered by this page');
  const copy = row.getByRole('button', { name: `Copy name: ${suggested}` });
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
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/quick-reference/');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    await expect(page.locator('.reference-table tbody tr')).toHaveCount(58);
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
  const initialTheme = await page.locator('[data-theme-toggle]').getAttribute('data-theme-preference');
  await page.locator('[data-theme-toggle]').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('[data-theme-toggle]')).not.toHaveAttribute('data-theme-preference', initialTheme);

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
