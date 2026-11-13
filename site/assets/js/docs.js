/* Progressive enhancement for generated OCF documentation pages. */
(() => {
  'use strict';
  const normalize = value => String(value || '')
    .normalize('NFKC')
    .toLocaleLowerCase('en-US')
    .replace(/[\p{P}\p{S}]+/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
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

  const managedPlayers = new Set();
  const startedPlayers = new WeakSet();
  const failedPlayers = new WeakSet();
  const playbackTimers = new WeakMap();
  const playbackTime = seconds => {
    const value = Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds) : 0;
    return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
  };
  const updatePlaybackStatus = audio => {
    const status = audio.closest('.edition-card, .session-card')?.querySelector('[data-playback-status]');
    if (!status) return;
    const title = audio.dataset.sessionTitle || audio.getAttribute('aria-label') || 'This session';
    const edition = audio.dataset.sessionEdition ? `, edition ${audio.dataset.sessionEdition}` : '';
    const filtered = audio.closest('.session-card')?.dataset.filteredOut === 'true';
    const filteredNote = filtered ? ' This edition does not match the current filters; its controls remain available.' : '';
    let message = '';
    if (audio.error || failedPlayers.has(audio)) {
      message = `Audio could not be played. Check your connection or use the direct download link below.${filteredNote}`;
    } else if (audio.ended || audio.dataset.ocfResumeEnded === 'true') {
      message = `Playback ended for ${title}${edition}. Use the player controls to replay.${filteredNote}`;
    } else if (!audio.paused && audio.readyState < HTMLMediaElement.HAVE_FUTURE_DATA) {
      message = `Loading audio for ${title}${edition}.${filteredNote}`;
    } else if (!audio.paused) {
      message = `Playing ${title}${edition}.${filteredNote}`;
    } else if (startedPlayers.has(audio) || Number(audio.dataset.ocfResumePosition) > 0) {
      const position = Number(audio.dataset.ocfResumePosition) > 0 ? Number(audio.dataset.ocfResumePosition) : audio.currentTime;
      message = `Paused at ${playbackTime(position)}. Use the player controls to resume.${filteredNote}`;
    } else if (filtered && audio.closest('.session-card')?.contains(document.activeElement)) {
      message = `This edition does not match the current filters; its player remains available while focused.`;
    }
    status.textContent = message;
    status.hidden = !message;
  };
  const registerMediaPlayer = audio => {
    if (managedPlayers.has(audio)) return;
    const status = audio.closest('.edition-card, .session-card')?.querySelector('[data-playback-status]');
    if (!status) return;
    managedPlayers.add(audio);
    const cancelPlaybackTimer = () => {
      const timer = playbackTimers.get(audio);
      if (timer) window.clearTimeout(timer);
      playbackTimers.delete(audio);
    };
    const monitorPlaybackStart = () => {
      if (playbackTimers.has(audio)) return;
      playbackTimers.set(audio, window.setTimeout(() => {
        playbackTimers.delete(audio);
        const noSource = audio.networkState === HTMLMediaElement.NETWORK_NO_SOURCE;
        const stalledDuringPlayback = startedPlayers.has(audio) && !audio.paused && audio.readyState < HTMLMediaElement.HAVE_FUTURE_DATA;
        if (noSource || stalledDuringPlayback) {
          failedPlayers.add(audio);
          updatePlaybackStatus(audio);
        }
      }, 8000));
    };
    audio.querySelectorAll('source').forEach(source => source.addEventListener('error', () => {
      failedPlayers.add(audio);
      cancelPlaybackTimer();
      updatePlaybackStatus(audio);
    }));
    audio.addEventListener('play', () => {
      startedPlayers.add(audio);
      if (audio.dataset.ocfResumeEnded === 'true') delete audio.dataset.ocfResumeEnded;
      const resumePosition = Number(audio.dataset.ocfResumePosition);
      if (Number.isFinite(resumePosition) && resumePosition > 0) {
        const restorePosition = () => {
          try {
            audio.currentTime = resumePosition;
            delete audio.dataset.ocfResumePosition;
          } catch (_) { /* Leave native controls available if this browser cannot restore a seek yet. */ }
        };
        if (audio.readyState >= HTMLMediaElement.HAVE_METADATA) restorePosition();
        else audio.addEventListener('loadedmetadata', restorePosition, {once: true});
      }
      for (const other of managedPlayers) if (other !== audio && !other.paused) other.pause();
      monitorPlaybackStart();
      updatePlaybackStatus(audio);
    });
    audio.addEventListener('loadstart', monitorPlaybackStart);
    audio.addEventListener('waiting', monitorPlaybackStart);
    ['pause', 'ended', 'seeked', 'error'].forEach(event => audio.addEventListener(event, () => {
      cancelPlaybackTimer();
      if (event === 'error') failedPlayers.add(audio);
      updatePlaybackStatus(audio);
    }));
    ['loadedmetadata', 'canplay', 'playing'].forEach(event => audio.addEventListener(event, () => {
      cancelPlaybackTimer();
      failedPlayers.delete(audio);
      updatePlaybackStatus(audio);
    }));
    updatePlaybackStatus(audio);
  };
  window.ocfRegisterMediaPlayer = registerMediaPlayer;
  window.ocfUpdateMediaPlayerStatus = updatePlaybackStatus;
  document.querySelectorAll('audio').forEach(registerMediaPlayer);

  const themeButton = document.querySelector('[data-theme-toggle]');
  if (themeButton) {
    const themes = ['system', 'light', 'dark'];
    const setThemePreference = preference => {
      if (preference === 'system') document.documentElement.removeAttribute('data-theme');
      else document.documentElement.dataset.theme = preference;
      const label = preference[0].toUpperCase() + preference.slice(1);
      themeButton.textContent = `Theme: ${label}`;
      themeButton.setAttribute('aria-label', `Color theme: ${label}. Activate to change.`);
      themeButton.dataset.themePreference = preference;
    };
    let preference = 'system';
    try {
      const saved = localStorage.getItem('ocf-theme');
      if (themes.includes(saved)) preference = saved;
      setThemePreference(preference);
      themeButton.addEventListener('click', () => {
        preference = themes[(themes.indexOf(preference) + 1) % themes.length];
        setThemePreference(preference);
        try { localStorage.setItem('ocf-theme', preference); } catch (_) { /* Keep the theme control usable without storage. */ }
      });
    } catch (_) {
      setThemePreference(preference);
      themeButton.addEventListener('click', () => {
        preference = themes[(themes.indexOf(preference) + 1) % themes.length];
        setThemePreference(preference);
      });
    }
  }

  const filterState = (scope, controls) => {
    const key = `ocf-filters:${location.pathname}:${scope}`;
    try {
      const saved = JSON.parse(sessionStorage.getItem(key) || '{}');
      for (const control of controls) {
        if (control && typeof saved[control.id] === 'string') control.value = saved[control.id];
      }
    } catch (_) { /* Filtering remains usable if session storage is unavailable. */ }
    return () => {
      try {
        sessionStorage.setItem(key, JSON.stringify(Object.fromEntries(
          controls.filter(Boolean).map(control => [control.id, control.value]),
        )));
      } catch (_) { /* Do not block filtering when storage is unavailable. */ }
    };
  };
  if ('scrollRestoration' in history) history.scrollRestoration = 'auto';

  const directorySearch = document.querySelector('[data-function-search]');
  const categoryFilter = document.querySelector('[data-category-filter]');
  const audioFilter = document.querySelector('[data-audio-filter]');
  const languageFilter = document.querySelector('[data-directory-language]');
  const voiceFilter = document.querySelector('[data-directory-voice]');
  const directoryCount = document.querySelector('[data-directory-count]');
  const directoryClear = document.querySelector('[data-function-clear]');
  const directoryNoResults = document.querySelector('[data-function-no-results]');
  const functionCards = [...document.querySelectorAll('[data-function-card]')];
  const domainGroups = [...document.querySelectorAll('[data-domain-group]')];
  const directoryControls = [directorySearch, categoryFilter, audioFilter, languageFilter, voiceFilter].filter(Boolean);
  const saveDirectoryFilters = filterState('directory', directoryControls);
  const updateDirectory = () => {
    if (!directorySearch) return;
    let shown = 0;
    for (const card of functionCards) {
      const visible = matches(card, directorySearch.value, categoryFilter?.value || '', audioFilter?.value || '', languageFilter?.value || '', voiceFilter?.value || '');
      card.hidden = !visible;
      if (visible) shown += 1;
    }
    for (const group of domainGroups) {
      group.hidden = !group.querySelector('[data-function-card]:not([hidden])');
    }
    if (directoryCount) directoryCount.textContent = `${shown} ${shown === 1 ? 'function' : 'functions'}`;
    if (directoryNoResults) directoryNoResults.hidden = shown > 0;
    if (directoryClear) directoryClear.hidden = !directoryControls.some(control => control.value);
  };
  directoryControls.forEach(control => {
    control.addEventListener('input', () => { saveDirectoryFilters(); updateDirectory(); });
    control.addEventListener('change', () => { saveDirectoryFilters(); updateDirectory(); });
  });
  directoryClear?.addEventListener('click', () => {
    directoryControls.forEach(control => { control.value = ''; });
    saveDirectoryFilters(); updateDirectory(); directorySearch?.focus();
  });
  updateDirectory();

  const referenceSearch = document.querySelector('[data-reference-search]');
  const referenceCategory = document.querySelector('[data-reference-category]');
  const referenceCount = document.querySelector('[data-reference-count]');
  const referenceClear = document.querySelector('[data-reference-clear]');
  const referenceNoResults = document.querySelector('[data-reference-no-results]');
  const referenceRows = [...document.querySelectorAll('[data-reference-row]')];
  const referenceControls = [referenceSearch, referenceCategory].filter(Boolean);
  const saveReferenceFilters = filterState('quick-reference', referenceControls);
  const updateReference = () => {
    if (!referenceSearch) return;
    let shown = 0;
    for (const row of referenceRows) {
      const visible = matches(row, referenceSearch.value, referenceCategory?.value || '');
      row.hidden = !visible;
      if (visible) shown += 1;
    }
    if (referenceCount) referenceCount.textContent = `${shown} ${shown === 1 ? 'function' : 'functions'}`;
    if (referenceNoResults) referenceNoResults.hidden = shown > 0;
    if (referenceClear) referenceClear.hidden = !referenceControls.some(control => control.value);
  };
  referenceControls.forEach(control => {
    control.addEventListener('input', () => { saveReferenceFilters(); updateReference(); });
    control.addEventListener('change', () => { saveReferenceFilters(); updateReference(); });
  });
  referenceClear?.addEventListener('click', () => {
    referenceControls.forEach(control => { control.value = ''; });
    saveReferenceFilters(); updateReference(); referenceSearch?.focus();
  });
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
  if (nav) {
    const summary = nav.querySelector('summary');
    nav.querySelectorAll('a').forEach(link => link.addEventListener('click', () => { nav.open = false; }));
    document.addEventListener('pointerdown', event => {
      if (nav.open && !nav.contains(event.target)) nav.open = false;
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && nav.open) {
        nav.open = false;
        summary.focus();
      }
    });
  }

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
