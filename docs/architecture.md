# Distribution architecture

The main [OCF repository](https://github.com/meramsey/open-consciousness-functions) owns function definitions, narration/localization, rendering and DSP, voice adapters, validation, artwork generation, development documentation, and software releases. This sister repository owns the public audio library, release metadata, download catalog, announcements, checksums, companion-file specifications, collections, mirrors, and eventual publishing integration. It does not generate audio.

The Git-tracked `site/` contains only static pages and small public metadata. Audio belongs in versioned GitHub Releases (or explicitly approved mirrors), never ordinary Git history or Git LFS by default. The website links to assets and must not copy large media into Pages. Releases retain historical URLs; updated audio receives a new immutable asset identity and release reference rather than silently replacing a published file.

The site loads `catalog.json` relative to its own path so it works at the GitHub Pages project subpath. Catalog schema changes are versioned and validated before deployment. Pages deploys only `site/` using GitHub's artifact/deployment actions after validation succeeds.

Publication has independent gates: generation eligibility, successful rendering, listening approval, licensing/rights approval, and explicit public distribution authorization. Rendering is not approval to publish. Only approved, verified assets and metadata may enter a public release. Private voice models, source recordings, and training/reference data remain outside this repository.

Future stable function URLs should resolve by stable function ID and, where appropriate, an explicit audio release version. They should point users to immutable release material and remain useful as catalog history grows.
