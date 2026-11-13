/* Public catalog presentation: no private paths, tracking, or HTML interpolation. */
(() => {
  'use strict';
  const safeURL = value => {
    try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; }
    catch (_) { return null; }
  };
  const entries = (catalog, documentation = {}) => (catalog.releases || []).flatMap(release =>
    [...(release.preparations || []), ...(release.functions || [])].flatMap(fn =>
      (fn.sessions || []).map(session => ({
        id: fn.function_id || 'preparation-learning', title: session.title || fn.title,
        description: documentation.byId?.[fn.function_id]?.description || fn.description || '',
        searchText: documentation.byId?.[fn.function_id]?.searchText || '',
        href: fn.function_id ? `functions/${encodeURIComponent(fn.function_id)}/` : 'preparation-learning/',
        locale: session.locale || session.language || '',
        voice: session.voice_name || session.voice_id || '', voiceId: session.voice_id || '',
        edition: session.edition || release.version, date: release.date,
        releaseURL: safeURL(release.release_url), assets: (session.assets || []).filter(a => safeURL(a.download_url))
      }))));
  const normalizeSearch = value => String(value || '')
    .normalize('NFKC')
    .toLocaleLowerCase('en-US')
    .replace(/[\p{P}\p{S}]+/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const filterEntries = (items, query, locale, voice) => {
    const terms = normalizeSearch(query);
    return items.filter(item =>
      (!terms || normalizeSearch(`${item.id} ${item.title} ${item.description} ${item.searchText}`).includes(terms)) &&
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
  const locale = document.getElementById('language-filter');
  const voice = document.getElementById('voice-filter');
  const resultsCount = document.getElementById('results-count');
  const noResults = document.getElementById('catalog-no-results');
  const clearFilters = document.getElementById('clear-library-filters');
  const filterStateKey = `ocf-library-filters:${location.pathname}`;
  const filterControls = [['search', search], ['locale', locale], ['voice', voice]].filter(([, control]) => control);
  const selection = new Map();
  const selectionCount = document.getElementById('selection-count');
  let catalogItems = [];
  let catalogCards = [];
  const pinnedItems = new Set();
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
    selectionCount.textContent = `${selection.size} files selected`;
    document.getElementById('download-selection').disabled = selection.size === 0;
    document.getElementById('playlist-selection').disabled = ![...selection.values()].some(a => a.format === 'mp3');
  }
  function render() {
    const visible = new Set(filterEntries(catalogItems, search.value, locale.value, voice.value));
    let pinned = 0;
    catalogItems.forEach((item, index) => {
      const card = catalogCards[index];
      const player = card.querySelector('audio');
      const playing = player && !player.paused && !player.ended;
      if (!visible.has(item) && (playing || card.contains(document.activeElement))) pinnedItems.add(item);
      const keepPinned = !visible.has(item) && pinnedItems.has(item);
      card.hidden = !visible.has(item) && !keepPinned;
      const note = card.querySelector('[data-filter-pinned]');
      if (note) {
        note.hidden = !keepPinned;
        if (keepPinned) {
          pinned += 1;
          note.textContent = playing
            ? 'Currently playing; this edition does not match the current filters.'
            : player?.ended
              ? 'Playback ended; this edition does not match the current filters. Its player remains available to replay.'
              : player && !player.paused
                ? 'Player active; this edition does not match the current filters. Its controls remain available.'
                : player
                  ? `Paused at ${formatPlaybackTime(player.currentTime)}; this edition does not match the current filters. Its controls remain available to resume.`
                  : 'This edition does not match the current filters but remains available while its controls have focus.';
        }
      }
    });
    resultsCount.textContent = visible.size
      ? `${visible.size} matching session ${visible.size === 1 ? 'edition' : 'editions'}${pinned ? `; ${pinned} nonmatching ${pinned === 1 ? 'edition remains' : 'editions remain'} available below` : ''}`
      : `No session editions match these filters${pinned ? `; ${pinned} nonmatching ${pinned === 1 ? 'edition remains' : 'editions remain'} available below` : ''}.`;
    if (noResults) noResults.hidden = visible.size > 0;
    if (clearFilters) clearFilters.hidden = !filterControls.some(([, control]) => control.value);
  }

  function formatPlaybackTime(seconds) {
    const value = Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds) : 0;
    return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
  }

  function createSessionCard(item) {
    const card = el('article', undefined, 'session-card');
    card.dataset.functionId = item.id;
    const title = el('h3'); const page = el('a', item.title);
    page.href = item.href; title.append(page); card.append(title);
    card.append(el('p', `${item.id} · ${item.locale} · ${item.voice} · v${item.edition}`, 'session-meta'));
    const pinned = el('p', 'Currently playing; this edition does not match the current filters.', 'filter-pinned-status');
    pinned.hidden = true; pinned.setAttribute('data-filter-pinned', ''); pinned.setAttribute('role', 'status');
    card.append(pinned);
    if (item.description) card.append(el('p', item.description));
    const mp3 = item.assets.find(a => a.format === 'mp3');
    if (mp3) {
      const player = el('audio'); player.controls = true; player.preload = 'none'; player.src = mp3.download_url;
      player.setAttribute('aria-label', `Listen to ${item.title}, ${item.locale}, ${item.voice}, edition ${item.edition}`);
      ['play', 'pause', 'ended', 'seeked'].forEach(event => player.addEventListener(event, render));
      card.append(player);
    }
    item.assets.forEach(asset => {
      const format = String(asset.format || 'file').toUpperCase();
      const row = el('div', undefined, 'asset-row');
      const label = el('label'); const checkbox = el('input'); checkbox.type = 'checkbox'; checkbox.checked = selection.has(asset.asset_id);
      checkbox.setAttribute('aria-label', downloadActionName('Select', format, item));
      checkbox.addEventListener('change', () => { if (checkbox.checked) selection.set(asset.asset_id, asset); else selection.delete(asset.asset_id); updateSelection(); });
      label.append(checkbox, document.createTextNode(` Select ${format}`));
      const link = el('a', `Download ${format}`); link.href = asset.download_url;
      link.setAttribute('aria-label', downloadActionName('Download', format, item));
      row.append(label, link); card.append(row);
      const detail = el('details'); detail.append(el('summary', `${asset.filename} — checksum and details`));
      detail.append(el('code', asset.sha256));
      const measurements = [asset.size_bytes ? `${(asset.size_bytes / 1048576).toFixed(1)} MiB` : '', asset.duration_seconds ? `${Math.floor(Math.round(asset.duration_seconds) / 60)}m ${Math.round(asset.duration_seconds) % 60}s` : '', asset.sample_rate_hz ? `${asset.sample_rate_hz} Hz` : ''].filter(Boolean);
      detail.append(el('p', measurements.join(' · '))); card.append(detail);
    });
    if (item.releaseURL) { const link = el('a', 'Release notes and original files'); link.href = item.releaseURL; card.append(link); }
    return card;
  }
  Promise.all([
    fetch('catalog.json').then(response => { if (!response.ok) throw new Error('Catalog unavailable'); return response.json(); }),
    fetch('documentation-index.json').then(response => response.ok ? response.json() : {functions: []}).catch(() => ({functions: []})),
    fetch('source.json').then(response => response.ok ? response.json() : {}).catch(() => ({}))
  ]).then(([catalog, documentationIndex, sourcePin]) => {
    if (!supportedCatalog(catalog)) throw new Error('Unsupported catalog');
    if (documentationIndex.source_commit !== sourcePin.source_commit) documentationIndex = {functions: []};
    const documentation = {
      byId: Object.fromEntries((documentationIndex.functions || []).map(row => [row.function_id, {
        description: row.description,
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
    count.textContent = `${catalog.releases.length} ${catalog.releases.length === 1 ? 'release' : 'releases'}`;
    status.hidden = items.length > 0;
    if (items.length) {
      document.getElementById('release-title').textContent = 'Published audio editions';
      document.getElementById('release-description').textContent = 'Choose a session below. Previous editions remain available with their original files and checksums.';
    }
    [...new Set(items.map(i => i.locale))].sort().forEach(value => { const option = el('option', value); option.value = value; locale.append(option); });
    const voices = new Map(items.map(i => [i.voiceId, i.voice]));
    [...voices].sort().forEach(([value, name]) => { const option = el('option', name); option.value = value; voice.append(option); });
    restoreFilterState();
    const functionId = new URLSearchParams(location.search).get('function');
    if (functionId) search.value = functionId;
    search.disabled = false;
    catalogItems = items;
    catalogCards = items.map(createSessionCard);
    results.replaceChildren(...catalogCards);
    const onFilter = () => { saveFilterState(); render(); };
    filterControls.forEach(([, control]) => {
      control.addEventListener('input', onFilter);
      control.addEventListener('change', onFilter);
    });
    clearFilters?.addEventListener('click', () => {
      filterControls.forEach(([, control]) => { control.value = ''; });
      pinnedItems.clear();
      const url = new URL(location.href); url.searchParams.delete('function');
      history.replaceState({}, '', url);
      saveFilterState(); render(); search.focus();
    });
    render(); updateSelection();
  }).catch(() => {
    count.textContent = 'Catalog unavailable'; status.hidden = false;
    status.replaceChildren(el('h3', 'The catalog could not be loaded'), el('p', 'Please retry, or use the GitHub Releases link above.'));
  });
})();
