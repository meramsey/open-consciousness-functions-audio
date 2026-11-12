# Website build and maintenance

## Source authority

Update `site/source.json` only to pin an exact reviewed source-repository
commit that contains the public guide-exporter contract. Do not add hand-edited
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
  --catalog verified-catalog.json --output verified-site
python scripts/validate_site.py verified-site
node scripts/test_catalog.js
node scripts/test_docs.js
```

The build copies only the `txt` and `vtt` companions present in the verified
catalog. Each asset must match the published size and SHA-256 and uniquely
match one session's declared audio-master fingerprint. No private or
unpublished transcript is fetched. Browser player URLs remain the original
release URLs; the build does not download, convert, or republish audio.

The deployment job uploads only the successfully validated artifact and has
separate Pages permissions. The checked-in `site/catalog.json` remains a
bootstrap catalog; it is not the deployed catalog source. A failed build cannot
replace the live Pages artifact.

## Human/device checks

Automated Chrome checks cover responsive widths, deep-link reloads, search,
transcript expansion, and a technical MP3 playback/decode request. The
repository's three-platform test matrix runs Python 3.11/3.12 and Node 22.
These checks do not establish physical-device playback, hearing experience,
native operating-system setting behavior, release/listening approval, or
medical efficacy. Record those boundaries in PR and release reports.
