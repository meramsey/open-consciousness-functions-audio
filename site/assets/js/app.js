/* Public catalog presentation: no private paths, tracking, or HTML interpolation. */
(() => {
  'use strict';
  const safeURL = value => {
    try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; }
    catch (_) { return null; }
  };
  const entries = catalog => (catalog.releases || []).flatMap(release =>
    [...(release.preparations || []), ...(release.functions || [])].flatMap(fn =>
      (fn.sessions || []).map(session => ({
        id: fn.function_id || 'preparation-learning', title: session.title || fn.title,
        description: fn.description || '', locale: session.locale || session.language || '',
        voice: session.voice_name || session.voice_id || '', voiceId: session.voice_id || '',
        edition: session.edition || release.version, date: release.date,
        releaseURL: safeURL(release.release_url), assets: (session.assets || []).filter(a => safeURL(a.download_url))
      }))));
  const filterEntries = (items, query, locale, voice) => items.filter(item =>
    `${item.id} ${item.title} ${item.description}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()) &&
    (!locale || item.locale === locale) && (!voice || item.voiceId === voice));
  const downloadList = assets => assets.map(a => `${a.sha256}  ${a.filename}\n${a.download_url}`).join('\n\n') + '\n';
  const supportedCatalog = catalog => [1, 2, 3].includes(catalog.schema_version) && Array.isArray(catalog.releases);
  if (typeof module !== 'undefined') module.exports = {safeURL, entries, filterEntries, downloadList, supportedCatalog};
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
  const selection = new Map();
  const selectionCount = document.getElementById('selection-count');
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
  function render(items) {
    results.replaceChildren();
    const visible = filterEntries(items, search.value, locale.value, voice.value);
    document.getElementById('results-count').textContent = `${visible.length} session editions`;
    if (!visible.length && items.length) results.append(el('p', 'No sessions match these filters.'));
    visible.forEach(item => {
      const card = el('article', undefined, 'session-card');
      const title = el('h3'); const page = el('a', item.title);
      page.href = `?function=${encodeURIComponent(item.id)}#library`; title.append(page); card.append(title);
      card.append(el('p', `${item.id} · ${item.locale} · ${item.voice} · v${item.edition}`, 'session-meta'));
      if (item.description) card.append(el('p', item.description));
      const mp3 = item.assets.find(a => a.format === 'mp3');
      if (mp3) { const player = el('audio'); player.controls = true; player.preload = 'none'; player.src = mp3.download_url; player.setAttribute('aria-label', `Listen to ${item.title}`); card.append(player); }
      item.assets.forEach(asset => {
        const row = el('div', undefined, 'asset-row');
        const label = el('label'); const checkbox = el('input'); checkbox.type = 'checkbox'; checkbox.checked = selection.has(asset.asset_id);
        checkbox.addEventListener('change', () => { if (checkbox.checked) selection.set(asset.asset_id, asset); else selection.delete(asset.asset_id); updateSelection(); });
        label.append(checkbox, document.createTextNode(` Select ${asset.format.toUpperCase()}`));
        const link = el('a', `Download ${asset.format.toUpperCase()}`); link.href = asset.download_url;
        row.append(label, link); card.append(row);
        const detail = el('details'); detail.append(el('summary', `${asset.filename} — checksum and details`));
        detail.append(el('code', asset.sha256));
        const measurements = [asset.size_bytes ? `${(asset.size_bytes / 1048576).toFixed(1)} MiB` : '', asset.duration_seconds ? `${Math.floor(Math.round(asset.duration_seconds) / 60)}m ${Math.round(asset.duration_seconds) % 60}s` : '', asset.sample_rate_hz ? `${asset.sample_rate_hz} Hz` : ''].filter(Boolean);
        detail.append(el('p', measurements.join(' · '))); card.append(detail);
      });
      if (item.releaseURL) { const link = el('a', 'Release notes and original files'); link.href = item.releaseURL; card.append(link); }
      results.append(card);
    });
  }
  fetch('catalog.json').then(response => {
    if (!response.ok) throw new Error('Catalog unavailable'); return response.json();
  }).then(catalog => {
    if (!supportedCatalog(catalog)) throw new Error('Unsupported catalog');
    const items = entries(catalog);
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
    const functionId = new URLSearchParams(location.search).get('function');
    if (functionId) search.value = functionId;
    search.disabled = false;
    [search, locale, voice].forEach(control => control.addEventListener('input', () => render(items)));
    render(items); updateSelection();
  }).catch(() => {
    count.textContent = 'Catalog unavailable'; status.hidden = false;
    status.replaceChildren(el('h3', 'The catalog could not be loaded'), el('p', 'Please retry, or use the GitHub Releases link above.'));
  });
})();
