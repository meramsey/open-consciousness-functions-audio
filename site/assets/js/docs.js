/* Progressive enhancement for generated OCF documentation pages. */
(() => {
  'use strict';
  const normalize = value => String(value || '').normalize('NFKC').toLocaleLowerCase();
  const matches = (node, query, category = '', audio = '', language = '', voice = '') => {
    const terms = normalize(query);
    const categoryMatches = !category || (node.dataset.category || '').split(/\s+/).includes(category);
    const audioMatches = !audio || node.dataset.audio === audio;
    const languageMatches = !language || (node.dataset.language || '').split('|').includes(language);
    const voiceMatches = !voice || (node.dataset.voice || '').split('|').includes(voice);
    return categoryMatches && audioMatches && languageMatches && voiceMatches && (!terms || normalize(node.dataset.search).includes(terms));
  };
  const safeTranscript = (value, currentURL) => {
    try {
      const url = new URL(value, currentURL);
      return url.origin === new URL(currentURL).origin && url.pathname.includes('/transcripts/') ? url.href : null;
    } catch (_) { return null; }
  };
  const highlight = (pre, text, query) => {
    pre.replaceChildren();
    if (!query) { pre.textContent = text; return; }
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const expression = new RegExp(escaped, 'giu');
    let cursor = 0;
    for (const match of text.matchAll(expression)) {
      const index = match.index ?? cursor;
      if (index > cursor) pre.append(document.createTextNode(text.slice(cursor, index)));
      const mark = document.createElement('mark'); mark.textContent = match[0]; pre.append(mark);
      cursor = index + match[0].length;
    }
    if (cursor < text.length) pre.append(document.createTextNode(text.slice(cursor)));
  };
  if (typeof module !== 'undefined') module.exports = {normalize, matches, safeTranscript, highlight};
  if (typeof document === 'undefined') return;

  const themeButton = document.querySelector('[data-theme-toggle]');
  if (themeButton) {
    try {
      const saved = localStorage.getItem('ocf-theme');
      if (saved === 'light' || saved === 'dark') document.documentElement.dataset.theme = saved;
      themeButton.addEventListener('click', () => {
        const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        document.documentElement.dataset.theme = next;
        try { localStorage.setItem('ocf-theme', next); } catch (_) { /* Keep theme toggle usable without storage. */ }
      });
    } catch (_) {
      themeButton.addEventListener('click', () => {
        document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      });
    }
  }

  const directorySearch = document.querySelector('[data-function-search]');
  const categoryFilter = document.querySelector('[data-category-filter]');
  const audioFilter = document.querySelector('[data-audio-filter]');
  const languageFilter = document.querySelector('[data-directory-language]');
  const voiceFilter = document.querySelector('[data-directory-voice]');
  const directoryCount = document.querySelector('[data-directory-count]');
  const functionCards = [...document.querySelectorAll('[data-function-card]')];
  const updateDirectory = () => {
    if (!directorySearch) return;
    let shown = 0;
    for (const card of functionCards) {
      const visible = matches(card, directorySearch.value, categoryFilter?.value || '', audioFilter?.value || '', languageFilter?.value || '', voiceFilter?.value || '');
      card.hidden = !visible;
      if (visible) shown += 1;
    }
    if (directoryCount) directoryCount.textContent = `${shown} ${shown === 1 ? 'function' : 'functions'}`;
  };
  [directorySearch, categoryFilter, audioFilter, languageFilter, voiceFilter].filter(Boolean).forEach(control => control.addEventListener('input', updateDirectory));
  updateDirectory();

  const referenceSearch = document.querySelector('[data-reference-search]');
  const referenceCategory = document.querySelector('[data-reference-category]');
  const referenceCount = document.querySelector('[data-reference-count]');
  const referenceRows = [...document.querySelectorAll('[data-reference-row]')];
  const updateReference = () => {
    if (!referenceSearch) return;
    let shown = 0;
    for (const row of referenceRows) {
      const visible = matches(row, referenceSearch.value, referenceCategory?.value || '');
      row.hidden = !visible;
      if (visible) shown += 1;
    }
    if (referenceCount) referenceCount.textContent = `${shown} ${shown === 1 ? 'function' : 'functions'}`;
  };
  [referenceSearch, referenceCategory].filter(Boolean).forEach(control => control.addEventListener('input', updateReference));
  updateReference();

  for (const details of document.querySelectorAll('details[data-transcript]')) {
    let loaded = false;
    let transcriptText = '';
    const pre = details.querySelector('[data-transcript-src]');
    const search = details.querySelector('[data-transcript-search]');
    if (search) search.addEventListener('input', () => highlight(pre, transcriptText, search.value));
    details.addEventListener('toggle', async () => {
      if (!details.open || loaded) return;
      const path = safeTranscript(pre?.dataset.transcriptSrc, location.href);
      if (!pre || !path) {
        if (pre) pre.textContent = 'This transcript path is not available.';
        loaded = true;
        return;
      }
      pre.textContent = 'Loading edition-matched transcript…';
      try {
        const response = await fetch(path, {credentials: 'omit'});
        if (!response.ok) throw new Error('Transcript unavailable');
        transcriptText = await response.text();
        highlight(pre, transcriptText, search?.value || '');
        if (search) search.disabled = false;
        loaded = true;
      } catch (_) {
        pre.textContent = 'The published transcript could not be loaded. Use the original release asset link below.';
        if (search) search.disabled = true;
      }
    });
  }

  for (const button of document.querySelectorAll('[data-copy]')) {
    button.addEventListener('click', async () => {
      const value = button.dataset.copy || '';
      try {
        await navigator.clipboard.writeText(value);
        button.textContent = 'Copied';
      } catch (_) {
        button.textContent = value;
      }
      window.setTimeout(() => { button.textContent = 'Copy'; }, 1200);
    });
  }

  const nav = document.querySelector('.mobile-nav');
  if (nav) nav.querySelectorAll('a').forEach(link => link.addEventListener('click', () => { nav.open = false; }));

  const tocLinks = [...document.querySelectorAll('.desktop-toc a, .mobile-toc a')];
  const sections = tocLinks.map(link => document.getElementById(decodeURIComponent(link.hash.slice(1)))).filter(Boolean);
  if ('IntersectionObserver' in window && sections.length) {
    const observer = new IntersectionObserver(entries => {
      const visible = entries.filter(entry => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      for (const link of tocLinks) {
        if (link.hash === `#${visible.target.id}`) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      }
    }, {rootMargin: '-12% 0px -70% 0px', threshold: [0, 0.25, 0.5]});
    sections.forEach(section => observer.observe(section));
  }
})();
