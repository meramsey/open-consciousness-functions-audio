# Open Consciousness Functions — Audio Library

This repository is the public audio distribution companion to the [Open Consciousness Functions (OCF) project](https://github.com/ocfproject-org/open-consciousness-functions). It hosts the library website, catalog metadata, release information, and future publishing automation. Audio is generated and reviewed in the main project—not here—and published as GitHub Release assets rather than committed to Git.

**Planned website:** https://ocfproject.org (domain cutover pending).

Migration preparation targets `ocfproject-org`; publication remains held. See
[the transfer checklist](docs/ORG_MIGRATION.md) before activating these changes.

**Releases:** https://github.com/ocfproject-org/open-consciousness-functions-audio/releases

## Publication status

Preparing the first public audio release. No audio downloads are available yet. Future editions may offer individual MP3 and lossless FLAC sessions, with supported language and voice variants described in the catalog. No release date or edition is promised.

OCF is an independent, open-source project. It is not affiliated with The Monroe Institute or Hemi-Sync.

## Local development

Serve the static site without a build system:

```sh
cd site
python3 -m http.server 8000 --bind 127.0.0.1
```

Open http://127.0.0.1:8000/. Validate the catalog and referenced site files with:

```sh
python3 scripts/validate_site.py
python3 -m unittest discover -s scripts -p 'test_*.py'
```

GitHub Actions validates pull requests and default-branch changes. A separate Pages workflow deploys only `site/` after validation; it can also be run manually. The site uses relative asset paths and requires no Node.js, database, account, tracking, or third-party runtime service.

## Catalog and future releases

`site/catalog.json` is an empty, versioned catalog until an authorized release exists. Its contract is documented in [docs/release-format.md](docs/release-format.md). It is designed for stable function identifiers, historical versions, languages, voices, session assets, checksums, technical metadata, provenance, companion files, artwork, and verified mirrors. Unchanged audio need not be re-uploaded for unrelated OCF software releases.

Future release assets may include separate MP3/FLAC sessions, artwork, collection packs of individual playable files, M3U8 playlists, release notes, machine-readable manifests, and `SHA256SUMS.txt`. Verify a downloaded file against a trusted release checksum with `sha256sum -c SHA256SUMS.txt`. Large collections may need splitting to respect GitHub Release asset limits; individual assets remain separately downloadable. Internet Archive and optional MEGA mirrors are planned only with verification and clear provenance.

Rendering, listening approval, licensing review, and public distribution authorization are separate gates. A successful render never grants permission to publish. Do not add private recordings, reference material, voice models, training data, or unapproved audio/artwork here.

## Contributing

Contributions to the website, schema, documentation, and validation are welcome through pull requests. Keep the catalog truthful, preserve stable IDs and published URLs, and run both validation commands above. Future main-repository documentation should link here with **“Listen & Download OCF Audio”**; corresponding OCF source releases may link to the sister repository's audio release without duplicating audio assets.

See [architecture](docs/architecture.md) and the [publishing roadmap](docs/publishing-roadmap.md) for boundaries and planned work.

## Release engineering

See [publication contracts and workflow](docs/PUBLICATION.md) and the
[readiness checkpoint](docs/release-readiness.md). The publisher defaults to offline
verification; public audio requires explicit asset, voice, artwork and final approval.
