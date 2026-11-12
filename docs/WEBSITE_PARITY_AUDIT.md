# Public website parity audit

Audited against the deployed Pages artifact from audio-repository main commit
`704c8438f9ad644f9efbca66806c4b28f6d26c49`, the published release
`audio-0.1.0-a6-20261111`, and the main OCF guide services. The checked-in
`site/catalog.json` is an empty base catalog; the Pages workflow refreshes the
deployed catalog from verified published manifests. The deployed catalog was
therefore inspected rather than treating the checked-in placeholder as the live
state.

| Capability | Offline guide/source | Current live site | Website target |
| --- | --- | --- | --- |
| 58 function records and stable IDs | Canonical locale resources and generated 58-function portable guide | Release catalog contains all 58 audio-bearing functions | All 58 documentation pages, whether audio is present or not |
| Preparation Learning | Separate session concept; not one of the 58 functions | One published preparation session | Separate page and playback entry; never assign a function ID |
| Categories, guide index, cue reference | Portable guide has category directory, cue reference, tags, and relationships | Audio cards only | Searchable canonical directory and quick reference |
| Function instructions and lifecycle | Generated from command documentation and canonical locale resources | Not present | Structured instructions, cue distinction, scope, lifecycle and precautions |
| Approved relationships | Directional approved links generated from canonical records; drafts separate | Not present | Outgoing approved links only; no reverse or inferred links |
| General/device listening guidance | Main OCF listening guide | Not present | Start Here, full guide, and platform-specific setup |
| Audio editions/downloads | Private package tooling; not a public audio catalog | Live JS catalog is generated from verified release manifest; 59 sessions (58 functions plus preparation), MP3/FLAC players and original asset URLs | Preserve this system and its stable release URLs/checksums |
| Edition-matched transcripts | Guide source text and private bundle tooling are distinct from release transcripts | Public companion assets (TXT/LRC/SRT/VTT) linkable; not inline | Expand exact selected-edition transcript, with optional timed subtitle download |
| Provenance/build | Portable guide manifest/checksums | Release manifest, verification receipt and generated catalog | Add pinned OCF source SHA and deterministic static-site build receipt |

The live page's initial HTML contains an empty-state placeholder, but JavaScript
loads the generated catalog. A headless browser with virtual time observed the
published release, 59 audio elements, and 478 direct release-asset links. The
live browser DOM confirmed that the empty state is hidden after catalog load.
No audio was played or downloaded during this audit.

## Architecture decision

- OCF main is the only function-documentation authority. Its public website
  exporter projects an explicit field allowlist from canonical locale data;
  it does not export narration text, source evidence paths, draft procedures,
  historical aliases as active commands, or draft relationship proposals.
- This repository owns only website-specific editorial text and presentation.
  Its build consumes the OCF export pinned to an exact commit and the existing
  verified release catalog. It does not define a second function registry.
- Audio availability is joined to documentation by stable function ID.
  Preparation Learning is joined by its separate session-kind marker.
- Transcript text is fetched at build time only from the TXT/VTT companion
  assets of published catalog entries, and every downloaded byte is checked
  against the catalog's size and SHA-256. Unpublished, private, or missing text
  is not substituted.
- The existing Pages workflow validates and uploads one generated artifact.
  The deploy job receives only that artifact and retains its separate Pages
  write/id-token permissions. No release upload, release tag, or audio bytes are
  modified.

## Remaining verification gates

The checked-in task branch must pass its own CI before merge. A local browser
build may be exercised with Chromium, but CI does not establish native-device
audio-settings behavior. Physical playback/device tests are reported only if
actually run. Deployment is verified against the Pages environment's exact
deployment SHA and the live public site after the approved PR merge.
