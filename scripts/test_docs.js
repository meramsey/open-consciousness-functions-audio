'use strict';
const assert = require('node:assert/strict');
const {matches, normalize, safeTranscript} = require('../site/assets/js/docs.js');

const card = {
  dataset: {
    search: 'relax plus-relax attention',
    category: 'foundation sleep',
    audio: 'yes',
    language: 'en-US|es-ES',
    voice: 'Mike — Original Voice',
  },
};
assert.equal(normalize('ＰＬＵＳ-ＲＥＬＡＸ'), 'plus-relax');
assert.equal(matches(card, 'PLUS-RELAX'), true);
assert.equal(matches(card, '', 'foundation', 'yes', 'en-US', 'Mike — Original Voice'), true);
assert.equal(matches(card, '', 'cognition'), false);
assert.equal(matches(card, '', '', 'no'), false);
assert.equal(matches(card, '', '', '', 'fr-FR'), false);
assert.equal(matches(card, '', '', '', 'en-US', 'Mike — Original Voice'), true);
assert.equal(safeTranscript('../../transcripts/asset-a.txt', 'https://example.test/functions/OCF-FND-004/'), 'https://example.test/transcripts/asset-a.txt');
assert.equal(safeTranscript('https://attacker.test/transcripts/a.txt', 'https://example.test/'), null);
assert.equal(safeTranscript('../../outside.txt', 'https://example.test/functions/OCF-FND-004/'), null);
console.log('Documentation UI logic: 10 assertions passed');
