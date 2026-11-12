# Website build and maintenance

## Source authority

Update `site/source.json` only to pin an exact reviewed source-repository
commit on the main branch that contains the public guide-exporter contract. The
Pages workflow fetches the full OCF history and fails closed unless that exact
commit is an ancestor of OCF main. Preview PR builds may use an unmerged source
branch commit for cross-repository validation, but that pin must be advanced to
the merged main commit before production Pages deployment. Do not add hand-edited
function records to this repository. The main OCF repository owns canonical
function identity, localized title/description, command/cue distinctions,
procedures, lifecycle, safety, categories, tags, common uses and approved
directional relationships. This repository owns layout, static-page
presentation and general listening/device editorial guidance.

The generated guide snapshot records the exact source commit and the exporter,
schema, per-function resource digests and build receipt. A build rejects a
missing/duplicate function ID, a source-pin mismatch, unsafe procedure status,
unreviewed relationships, invalid release catalog or broken local page link.
Only the exact 58-function en-US export is currently supported; no locale is
silently substituted.

## Local verification

The Pages workflow checks out the pinned public source commit and derives the
guide export. It refreshes release metadata from verified published manifests,
then builds in a separate staging directory:

```bash
python scripts/refresh_catalog.py --output verified-catalog.json
PYTHONPATH=ocf-source/scripts python -m ocf_tools.public_site_export \
  --source-commit "$(python -c 'import json; print(json.load(open("site/source.json"))["source_commit"])')" \
  --output public-guide-export.json
python scripts/build_public_site.py \
  --site-root site --content-dir docs/website \
  --source-pin site/source.json \
  --guide-export public-guide-export.json \
  --catalog verified-catalog.json \
  --historical-reference ocf-source/docs/releases/OCF_HISTORICAL_LOOKUP_CURRENT.md \
  --output verified-site
python scripts/validate_site.py verified-site
node scripts/test_catalog.js
node scripts/test_docs.js
npm ci
npx playwright install chromium firefox webkit
npm run test:browser:guard
npm run test:browser
```

`npm run test:browser` starts a static server over the exact generated
`verified-site/` directory. Playwright runs real browser checks and axe-core
WCAG 2.0/2.1 A/AA scans on all 58 generated function pages. The test suite
checks spoken-only cues and copy names, inactive-cue exclusion, the Sleep
procedure, keyboard navigation, filters, deep links, themes, transcripts,
responsive widths and a printed Quick Reference PDF. An injected unlabeled
button is a negative accessibility regression: the same axe gate must reject
it. A separate negative server regression starts a test-owned service on port
4173 and confirms Playwright rejects it rather than reusing it; if that port is
already occupied before the test starts, the test fails without terminating
the existing listener. In Pages, these checks run before `verified-site` is
uploaded; the deploy job depends on the complete validation job. A browser or axe test failure
therefore fails validation and prevents deployment. The public-safe browser
artifact includes test results, a print PDF and an acceptance receipt bound to
the pinned source commit, PR head (or pushed audio commit), exact CI-tested
commit, catalog and generated-site inventory hashes, and browser/tool versions.
CI installs and gates Chromium; Firefox and WebKit can be run locally with
`BROWSER=firefox` or `BROWSER=webkit`.

The build copies only the `txt` and `vtt` companions present in the verified
catalog. Each asset must match the published size and SHA-256 and uniquely
match one session's declared audio-master fingerprint. No private or
unpublished transcript is fetched. Browser player URLs remain the original
release URLs; the build does not download, convert, or republish audio.
Transient HTTP 429/5xx errors during companion retrieval receive at most two
bounded, delayed retries; permanent errors, redirects outside GitHub, and any
size/hash mismatch fail the staged build closed.

The deployment job uploads only the successfully validated artifact and has
separate Pages permissions. The checked-in `site/catalog.json` remains a
bootstrap catalog; it is not the deployed catalog source. A failed build cannot
replace the live Pages artifact.

## Technical media and human/device checks

Browser checks cover responsive widths, deep-link reloads, search, transcript
expansion and layout. Technical MP3 playback/seek probes, when performed, must
use one exact public edition URL, cap each byte-range request and record the
edition-matched TXT/VTT companion master fingerprint; this is not a full
download test. Audio links stay pinned to release assets. Each audio row also
offers a hash-free, descriptive local filename to copy; cross-origin release
responses may keep the server's hash-bearing filename, in which case rename it
in the device's file manager after download. The page does not fetch audio into
a Blob or buffer large files. The repository's three-platform test matrix runs Python
3.11/3.12 and Node 22. None of these checks establish physical-device
playback, hearing experience, native operating-system setting behavior,
release/listening approval, or medical efficacy. Record those boundaries in
PR and release reports.
