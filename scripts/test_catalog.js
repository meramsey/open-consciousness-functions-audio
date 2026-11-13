const assert = require('assert');
const {safeURL, entries, normalizeSearch, filterEntries, downloadActionName, downloadList, supportedCatalog} = require('../site/assets/js/app.js');
assert.strictEqual(safeURL('javascript:alert(1)'), null);
assert.strictEqual(safeURL('https://user:pass@example.com/file'), null);
assert.strictEqual(safeURL('file:///private'), null);
const asset = {asset_id: 'a', format: 'mp3', filename: 'Example.mp3', sha256: 'a'.repeat(64), download_url: 'https://example.com/Example.mp3'};
const catalog = {releases: [{version:'1.0', date:'2026-01-01', release_url:'https://example.com/release', functions:[{function_id:'OCF-FND-001', title:'Example', sessions:[{locale:'en-US', voice_id:'voice-a', voice_name:'Example Voice', assets:[asset]}]}], preparations:[{title:'Preparation Learning', sessions:[{locale:'en-US', voice_id:'voice-a', assets:[asset]}]}]}]};
const rows = entries(catalog);
assert.strictEqual(rows.length, 2);
assert.strictEqual(rows[0].id, 'preparation-learning');
assert.strictEqual(filterEntries(rows, 'EXAMPLE', 'en-US', 'voice-a').length, 1);
assert.equal(normalizeSearch('  ＰＬＵＳ---RELAX  '), 'plus relax');
assert.strictEqual(filterEntries([{...rows[0], title: 'Relax', searchText: 'Plus Relax'}], ' Plus   Relax ', '', '').length, 1);
assert.strictEqual(filterEntries([{...rows[0], title: 'Relax', searchText: 'Plus Relax'}], 'PLUS-RELAX', '', '').length, 1);
assert.strictEqual(filterEntries(rows, '', 'fr-FR', '').length, 0);
assert.strictEqual(filterEntries(rows, 'OCF-FND-001', '', '').length, 1);
assert(downloadList([asset]).includes(asset.sha256));
assert(downloadList([asset]).includes(asset.download_url));
assert(supportedCatalog({schema_version: 3, releases: []}));
assert(supportedCatalog({schema_version: 2, releases: []}));
assert.strictEqual(supportedCatalog({schema_version: 4, releases: []}), false);
assert.strictEqual(supportedCatalog({schema_version: 3, releases: {}}), false);
for (const title of ['Relax', 'Brain Flow']) {
  for (const format of ['mp3', 'flac']) {
    const name = downloadActionName('Download', format, {title, locale: 'en-US', voice: 'Mike Original Voice', edition: '0.1.0'});
    assert.match(name, new RegExp(`Download ${format.toUpperCase()} for ${title}, en-US, Mike Original Voice, edition 0\\.1\\.0`));
  }
}
const currentStrongQuick = {id: 'OCF-PRF-006', title: 'Strong-Quick', description: '', searchText: 'Plus Strong Quick'};
const currentInnerPower = {id: 'OCF-PRF-002', title: 'Inner Power', description: '', searchText: 'Plus Inner Power'};
assert.deepEqual(filterEntries([currentStrongQuick, currentInnerPower], 'PLUS-STRONG', '', '').map(x => x.id), ['OCF-PRF-006']);
console.log('Catalog logic: 22 assertions passed');
