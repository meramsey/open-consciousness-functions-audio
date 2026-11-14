/* Public catalog presentation: no private paths, tracking, or HTML interpolation. */
(() => {
  'use strict';
  const safeURL = value => {
    try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; }
    catch (_) { return null; }
  };
  const entries = (catalog, documentation = {}) => {
    const items = (catalog.releases || []).flatMap(release =>
    [...(release.preparations || []), ...(release.functions || [])].flatMap(fn =>
      (fn.sessions || []).map(session => ({
        id: fn.function_id || 'preparation-learning', title: session.title || fn.title,
        description: documentation.byId?.[fn.function_id]?.description || fn.description || '',
        searchText: documentation.byId?.[fn.function_id]?.searchText || '',
        category: documentation.byId?.[fn.function_id]?.category || 'preparation-learning',
        categoryLabel: documentation.byId?.[fn.function_id]?.categoryLabel || 'Preparation Learning',
        categories: documentation.byId?.[fn.function_id]?.categories || ['preparation-learning'],
        href: fn.function_id ? `${encodeURIComponent(fn.function_id)}/` : '../preparation-learning/',
        locale: session.locale || session.language || '',
        voice: session.voice_name || session.voice_id || '', voiceId: session.voice_id || '',
        edition: session.edition || release.version, date: release.date,
        releaseURL: safeURL(release.release_url), assets: (session.assets || []).filter(a => safeURL(a.download_url))
      }))));
    const documented = Object.entries(documentation.byId || {});
    const available = new Set(items.map(item => item.id));
    for (const [id, functionDoc] of documented) {
      if (available.has(id)) continue;
      items.push({
        id, title: functionDoc.title, description: functionDoc.description,
        searchText: functionDoc.searchText, category: functionDoc.category,
        categoryLabel: functionDoc.categoryLabel,
        categories: functionDoc.categories, href: `${encodeURIComponent(id)}/`,
        locale: '', voice: '', voiceId: '', edition: '', releaseURL: null, assets: [],
      });
    }
    return items;
  };
  const normalizeSearch = value => String(value || '')
    .normalize('NFKC')
    .toLocaleLowerCase('en-US')
    .replace(/[\p{P}\p{S}]+/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const filterEntries = (items, query, category, audio, locale, voice) => {
    const terms = normalizeSearch(query);
    return items.filter(item =>
      (!terms || normalizeSearch(`${item.id} ${item.title} ${item.description} ${item.searchText}`).includes(terms)) &&
      (!category || (item.categories || []).includes(category)) &&
      (!audio || (item.assets.length ? 'yes' : 'no') === audio) &&
      (!locale || item.locale === locale) && (!voice || item.voiceId === voice));
  };
  const downloadActionName = (action, format, item) =>
    `${action} ${String(format || 'file').toUpperCase()} for ${item.title}, ${item.locale}, ${item.voice}, edition ${item.edition}`;
  const downloadList = assets => assets.map(a => `${a.sha256}  ${a.filename}\n${a.download_url}`).join('\n\n') + '\n';
  const supportedCatalog = catalog => [1, 2, 3].includes(catalog.schema_version) && Array.isArray(catalog.releases);
  if (typeof module !== 'undefined') module.exports = {safeURL, entries, normalizeSearch, filterEntries, downloadActionName, downloadList, supportedCatalog};
  if (typeof document === 'undefined') return;
  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const status = document.getElementById('empty-state');
  const count = document.getElementById('release-count');
  const results = document.getElementById('catalog-results');
  const search = document.getElementById('search');
  const category = document.getElementById('category-filter');
  const audioFilter = document.getElementById('audio-filter');
  const locale = document.getElementById('language-filter');
  const voice = document.getElementById('voice-filter');
  const resultsCount = document.getElementById('results-count');
  const noResults = document.getElementById('catalog-no-results');
  const clearFilters = document.getElementById('clear-library-filters');
  const filterStateKey = `ocf-library-filters:${location.pathname}`;
  const playbackStateKey = `ocf-library-playback:${location.pathname}`;
  const navigationEntry = performance.getEntriesByType?.('navigation')?.[0];
  const returningThroughHistory = navigationEntry?.type === 'back_forward';
  const filterControls = [['search', search], ['category', category], ['audio', audioFilter], ['locale', locale], ['voice', voice]].filter(([, control]) => control);
  const selection = new Map();
  const selectionCount = document.getElementById('selection-count');
  const selectedFilesReview = document.getElementById('selected-files-review');
  const selectedFilesSummary = document.getElementById('selected-files-summary');
  const selectedFilesList = document.getElementById('selected-files-list');
  const clearSelection = document.getElementById('clear-selection');
  let catalogItems = [];
  let catalogCards = [];
  const pinnedItems = new Set();
  let lastPlayedItem = null;
  function saveFilterState() {
    try {
      sessionStorage.setItem(filterStateKey, JSON.stringify(Object.fromEntries(filterControls.map(([key, control]) => [key, control.value]))));
    } catch (_) { /* Filtering remains usable when storage is unavailable. */ }
  }
  function restoreFilterState() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(filterStateKey) || '{}');
      for (const [key, control] of filterControls) if (typeof saved[key] === 'string') control.value = saved[key];
    } catch (_) { /* Ignore unavailable or invalid session state. */ }
  }
  function savePlaybackState(item, player, {liveSeek = false} = {}) {
    if (!item || !player) return;
    let previous = null;
    try {
      previous = JSON.parse(sessionStorage.getItem(playbackStateKey) || 'null');
    } catch (_) { /* Continue with live media state when storage is unavailable. */ }
    const previousMatches = previous && previous.functionId === item.id && previous.title === item.title && previous.locale === item.locale && previous.voiceId === item.voiceId && previous.edition === item.edition && Date.now() - previous.savedAt <= 30 * 60 * 1000;
    const previousExplicitPosition = previousMatches && previous.positionIsExplicit === true;
    const explicitPosition = liveSeek || player.dataset.ocfResumePositionExplicit === 'true' || previousExplicitPosition;
    const restoredBookmarkPending = !liveSeek && player.dataset.ocfRestoredBookmarkPending === 'true';
    const restoredPosition = Number(player.dataset.ocfRestoredBookmarkPosition);
    const ended = !liveSeek && (restoredBookmarkPending ? player.dataset.ocfRestoredBookmarkEnded === 'true' : player.ended || player.dataset.ocfResumeEnded === 'true' || (previousMatches && previous.ended === true && !player.dataset.ocfResumePosition && !player.dataset.ocfResumePositionExplicit));
    const currentPosition = Number.isFinite(player.currentTime) && player.currentTime >= 0 ? player.currentTime : 0;
    const pendingPosition = Number(player.dataset.ocfResumePosition);
    const previousPosition = previousMatches && Number.isFinite(previous.position) && previous.position > 0 ? previous.position : 0;
    const position = ended ? 0 : restoredBookmarkPending && Number.isFinite(restoredPosition) ? restoredPosition : explicitPosition ? currentPosition : currentPosition > 0 ? currentPosition : (Number.isFinite(pendingPosition) && pendingPosition > 0 ? pendingPosition : previousPosition);
    if (position === 0 && !lastPlayedItem) return;
    try {
      sessionStorage.setItem(playbackStateKey, JSON.stringify({
        functionId: item.id,
        title: item.title,
        locale: item.locale,
        voiceId: item.voiceId,
        edition: item.edition,
        position,
        ended,
        positionIsExplicit: !ended && Boolean(explicitPosition),
        filteredOut: catalogCards[catalogItems.indexOf(item)]?.dataset.filteredOut === 'true',
        savedAt: Date.now(),
      }));
    } catch (_) { /* Playback remains available if session storage is unavailable. */ }
  }
  function restorePlaybackState(items) {
    try {
      if (!returningThroughHistory) {
        sessionStorage.removeItem(playbackStateKey);
        return;
      }
      const saved = JSON.parse(sessionStorage.getItem(playbackStateKey) || 'null');
      if (!saved || Date.now() - saved.savedAt > 30 * 60 * 1000) return;
      const item = items.find(candidate => candidate.id === saved.functionId && candidate.title === saved.title && candidate.locale === saved.locale && candidate.voiceId === saved.voiceId && candidate.edition === saved.edition);
      const index = item ? items.indexOf(item) : -1;
      const player = index >= 0 ? catalogCards[index]?.querySelector('audio') : null;
      if (!item || !player) return;
      if (saved.ended) player.dataset.ocfResumeEnded = 'true';
      else if (saved.positionIsExplicit === true && saved.position === 0) player.dataset.ocfResumePositionExplicit = 'true';
      else if (!Number.isFinite(saved.position) || saved.position <= 0) return;
      else player.dataset.ocfResumePosition = String(saved.position);
      player.dataset.ocfRestoredBookmarkPending = 'true';
      player.dataset.ocfRestoredBookmarkPosition = String(saved.position);
      player.dataset.ocfRestoredBookmarkEnded = String(saved.ended === true);
      lastPlayedItem = item;
      if (saved.filteredOut) pinnedItems.add(item);
    } catch (_) { /* Ignore invalid or unavailable session playback state. */ }
  }
  function save(name, content, type) {
    const url = URL.createObjectURL(new Blob([content], {type}));
    const link = el('a'); link.href = url; link.download = name; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  document.getElementById('download-selection').addEventListener('click', () => {
    save('OCF-download-selection.txt', downloadList([...selection.values()]), 'text/plain;charset=utf-8');
  });
  document.getElementById('playlist-selection').addEventListener('click', () => {
    save('OCF-selection.m3u8', '#EXTM3U\n' + [...selection.values()].filter(a => a.format === 'mp3').map(a => a.download_url).join('\n') + '\n', 'audio/x-mpegurl');
  });
  function updateSelection() {
    const visible = new Set(filterEntries(catalogItems, search.value, category?.value || '', audioFilter?.value || '', locale?.value || '', voice?.value || ''));
    const hiddenCount = [...selection.values()].filter(file => !visible.has(file.sessionItem)).length;
    selectionCount.textContent = `${selection.size} ${selection.size === 1 ? 'file' : 'files'} selected${hiddenCount ? ` (${hiddenCount} hidden by filters)` : ''}`;
    document.getElementById('download-selection').disabled = selection.size === 0;
    document.getElementById('playlist-selection').disabled = ![...selection.values()].some(a => a.format === 'mp3');
    if (!selectedFilesReview || !selectedFilesSummary || !selectedFilesList) return;
    selectedFilesReview.hidden = selection.size === 0;
    selectedFilesSummary.textContent = `Review selected files (${selection.size}${hiddenCount ? `; ${hiddenCount} hidden by filters` : ''})`;
    selectedFilesList.replaceChildren();
    for (const [assetId, file] of selection) {
      const row = el('li');
      const hidden = !visible.has(file.sessionItem);
      const label = `${file.sessionTitle}, ${file.locale}, ${file.voice}, edition ${file.edition} — ${file.format.toUpperCase()}${hidden ? ' (hidden by filters)' : ''}`;
      const link = el('a', `Open ${file.format.toUpperCase()} download`);
      link.href = file.download_url;
      link.setAttribute('aria-label', `Open ${file.format.toUpperCase()} download for ${file.sessionTitle}, ${file.locale}, edition ${file.edition}`);
      const remove = el('button', `Remove ${file.format.toUpperCase()}`);
      remove.type = 'button';
      remove.setAttribute('aria-label', `Remove ${file.format.toUpperCase()} for ${file.sessionTitle}, edition ${file.edition} from selected files`);
      remove.addEventListener('click', () => removeSelectedFile(assetId));
      row.append(document.createTextNode(`${label} · `), link, document.createTextNode(' · '), remove);
      selectedFilesList.append(row);
    }
  }

  function removeSelectedFile(assetId) {
    selection.delete(assetId);
    for (const checkbox of document.querySelectorAll('[data-selected-asset-id]')) {
      if (checkbox.dataset.selectedAssetId === assetId) checkbox.checked = false;
    }
    updateSelection();
    selectionCount.focus();
  }

  clearSelection?.addEventListener('click', () => {
    selection.clear();
    for (const checkbox of document.querySelectorAll('[data-selected-asset-id]')) checkbox.checked = false;
    updateSelection();
    selectionCount.focus();
  });
  function render() {
    const visible = new Set(filterEntries(catalogItems, search.value, category?.value || '', audioFilter?.value || '', locale?.value || '', voice?.value || ''));
    let pinned = 0;
    catalogItems.forEach((item, index) => {
      const card = catalogCards[index];
      const player = card.querySelector('audio');
      const playing = player && !player.paused && !player.ended;
      if (!visible.has(item) && (playing || card.contains(document.activeElement))) pinnedItems.add(item);
      const keepPinned = !visible.has(item) && pinnedItems.has(item);
      card.hidden = !visible.has(item) && !keepPinned;
      card.dataset.filteredOut = String(!visible.has(item));
      const note = card.querySelector('[data-playback-status]');
      if (note) {
        note.classList.toggle('filter-pinned-status', keepPinned);
        note.toggleAttribute('data-filter-pinned', keepPinned);
        if (player) window.ocfUpdateMediaPlayerStatus?.(player);
        if (keepPinned) pinned += 1;
      }
    });
    resultsCount.textContent = visible.size
      ? `${visible.size} matching session ${visible.size === 1 ? 'edition' : 'editions'}${pinned ? `; ${pinned} nonmatching ${pinned === 1 ? 'edition remains' : 'editions remain'} available below` : ''}`
      : `No session editions match these filters${pinned ? `; ${pinned} nonmatching ${pinned === 1 ? 'edition remains' : 'editions remain'} available below` : ''}.`;
    if (noResults) noResults.hidden = visible.size > 0;
    if (clearFilters) clearFilters.hidden = !filterControls.some(([, control]) => control.value);
  }

  function createSessionCard(item) {
    const card = el('article', undefined, 'session-card');
    card.dataset.functionId = item.id;
    const title = el('h3'); const page = el('a', item.title);
    page.href = item.href; title.append(page); card.append(title);
    const metadata = [item.categoryLabel || item.category, item.id, item.locale, item.voice, item.edition && `v${item.edition}`].filter(Boolean).join(' · ');
    card.append(el('p', metadata, 'session-meta'));
    const pinned = el('p', undefined, 'playback-status');
    pinned.hidden = true; pinned.setAttribute('data-playback-status', ''); pinned.setAttribute('role', 'status'); pinned.setAttribute('aria-live', 'polite');
    card.append(pinned);
    if (item.description) card.append(el('p', item.description));
    card.append(el('p', item.assets.length ? 'Published recording available' : 'No recording in the verified catalog', 'function-status'));
    const mp3 = item.assets.find(a => a.format === 'mp3');
    if (mp3) {
      const player = el('audio'); player.controls = true; player.preload = 'none'; player.src = mp3.download_url;
      player.setAttribute('aria-label', `Listen to ${item.title}, ${item.locale}, ${item.voice}, edition ${item.edition}`);
      player.dataset.sessionTitle = item.title;
      player.dataset.sessionEdition = item.edition;
      player.dataset.sessionLocale = item.locale;
      card.append(player);
      window.ocfRegisterMediaPlayer?.(player);
      ['play', 'pause', 'ended', 'waiting', 'playing', 'error'].forEach(event => player.addEventListener(event, render));
      player.addEventListener('play', () => {
        lastPlayedItem = item;
        try { sessionStorage.removeItem(playbackStateKey); } catch (_) { /* Keep playback usable if storage is unavailable. */ }
      });
      ['pause', 'ended'].forEach(event => player.addEventListener(event, () => savePlaybackState(item, player)));
      player.addEventListener('seeking', () => {
        if (player.dataset.ocfApplyingResume !== 'true') player.dataset.ocfLiveSeek = 'true';
      });
      player.addEventListener('seeked', () => {
        const liveSeek = player.dataset.ocfLiveSeek === 'true';
        if (liveSeek) {
          delete player.dataset.ocfResumePosition;
          delete player.dataset.ocfResumeEnded;
          delete player.dataset.ocfResumePositionExplicit;
          delete player.dataset.ocfRestoredBookmarkPending;
          delete player.dataset.ocfRestoredBookmarkPosition;
          delete player.dataset.ocfRestoredBookmarkEnded;
        }
        savePlaybackState(item, player, {liveSeek});
        if (liveSeek) delete player.dataset.ocfLiveSeek;
      });
    }
    item.assets.forEach(asset => {
      const format = String(asset.format || 'file').toUpperCase();
      const row = el('div', undefined, 'asset-row');
      const label = el('label'); const checkbox = el('input'); checkbox.type = 'checkbox'; checkbox.checked = selection.has(asset.asset_id);
      checkbox.dataset.selectedAssetId = asset.asset_id;
      checkbox.setAttribute('aria-label', downloadActionName('Select', format, item));
      checkbox.addEventListener('change', () => {
        if (checkbox.checked) selection.set(asset.asset_id, {...asset, sessionTitle: item.title, locale: item.locale, voice: item.voice, edition: item.edition, functionId: item.id, sessionItem: item});
        else selection.delete(asset.asset_id);
        updateSelection();
      });
      label.append(checkbox, document.createTextNode(` Select ${format}`));
      const link = el('a', `Download ${format}`); link.href = asset.download_url;
      link.setAttribute('aria-label', downloadActionName('Download', format, item));
      row.append(label, link); card.append(row);
      const detail = el('details'); detail.append(el('summary', `${format} file details`));
      const filename = el('p'); filename.append(document.createTextNode('Release filename: '), el('code', asset.filename));
      const checksum = el('p'); checksum.append(document.createTextNode('SHA-256: '), el('code', asset.sha256));
      detail.append(filename, checksum);
      const measurements = [asset.size_bytes ? `${(asset.size_bytes / 1048576).toFixed(1)} MiB` : '', asset.duration_seconds ? `${Math.floor(Math.round(asset.duration_seconds) / 60)}m ${Math.round(asset.duration_seconds) % 60}s` : '', asset.sample_rate_hz ? `${asset.sample_rate_hz} Hz` : ''].filter(Boolean);
      detail.append(el('p', measurements.join(' · '))); card.append(detail);
    });
    if (item.releaseURL) { const link = el('a', 'Release notes and original files'); link.href = item.releaseURL; card.append(link); }
    return card;
  }
  Promise.all([
    fetch('../catalog.json').then(response => { if (!response.ok) throw new Error('Catalog unavailable'); return response.json(); }),
    fetch('../documentation-index.json').then(response => response.ok ? response.json() : {functions: []}).catch(() => ({functions: []})),
    fetch('../source.json').then(response => response.ok ? response.json() : {}).catch(() => ({}))
  ]).then(([catalog, documentationIndex, sourcePin]) => {
    if (!supportedCatalog(catalog)) throw new Error('Unsupported catalog');
    if (documentationIndex.source_commit !== sourcePin.source_commit) documentationIndex = {functions: []};
    const documentation = {
      byId: Object.fromEntries((documentationIndex.functions || []).map(row => [row.function_id, {
        title: row.title,
        description: row.description,
        category: row.primary_category,
        categoryLabel: row.primary_category_label,
        categories: row.categories,
        searchText: `${row.categories.join(' ')} ${row.cues.join(' ')} ${row.search_terms.join(' ')}`
      }]))
    };
    const items = entries(catalog, documentation);
    const extras = document.getElementById('release-extras');
    catalog.releases.forEach(release => {
      const files = [...(release.collections || []), ...(release.companions || [])].filter(a => safeURL(a.download_url));
      if (!files.length) return;
      const details = el('details'); details.append(el('summary', `Collections and companion files — v${release.version}`));
      files.forEach(asset => {
        const row = el('p'); const link = el('a', asset.filename); link.href = asset.download_url;
        row.append(link, el('code', asset.sha256)); details.append(row);
      });
      extras.append(details);
    });
    const audioItems = items.filter(item => item.assets.length);
    count.textContent = `${audioItems.length} recordings`;
    status.hidden = audioItems.length > 0;
    if (!audioItems.length) status.textContent = 'No published recordings are listed in the verified catalog; function guides remain available.';
    [...new Set(audioItems.map(i => i.locale).filter(Boolean))].sort().forEach(value => {
      if (!locale) return;
      const option = el('option', value); option.value = value; locale.append(option);
    });
    const voices = new Map(audioItems.filter(i => i.voiceId).map(i => [i.voiceId, i.voice]));
    [...voices].sort((a, b) => a[1].localeCompare(b[1])).forEach(([value, name]) => {
      if (!voice) return;
      const option = el('option', name); option.value = value; voice.append(option);
    });
    restoreFilterState();
    const params = new URLSearchParams(location.search);
    const functionId = params.get('function');
    if (functionId) search.value = functionId;
    if (params.get('category') && category) category.value = params.get('category');
    search.disabled = false;
    catalogItems = items;
    catalogCards = items.map(createSessionCard);
    results.replaceChildren(...catalogCards);
    restorePlaybackState(items);
    window.addEventListener('pagehide', () => {
      if (!lastPlayedItem) return;
      const index = catalogItems.indexOf(lastPlayedItem);
      const player = index >= 0 ? catalogCards[index]?.querySelector('audio') : null;
      if (!player) return;
      savePlaybackState(lastPlayedItem, player);
      if (!player.paused && !player.ended) player.pause();
    });
    const onFilter = () => { saveFilterState(); render(); updateSelection(); };
    filterControls.forEach(([, control]) => {
      control.addEventListener('input', onFilter);
      control.addEventListener('change', onFilter);
    });
    clearFilters?.addEventListener('click', () => {
      filterControls.forEach(([, control]) => { control.value = ''; });
      pinnedItems.clear();
      const url = new URL(location.href); url.searchParams.delete('function'); url.searchParams.delete('category');
      history.replaceState({}, '', url); saveFilterState(); render(); updateSelection(); search.focus();
    });
    render(); updateSelection();
  }).catch(() => {
    count.textContent = 'Published audio details unavailable';
    status.hidden = false;
    status.textContent = 'Published audio details could not be loaded. The function guides and build-time direct download links remain available.';
    document.querySelector('.library-tools')?.setAttribute('hidden', '');
    document.querySelector('.selection-tools')?.setAttribute('hidden', '');
    resultsCount.textContent = '';
  });
})();
