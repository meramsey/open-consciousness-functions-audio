# Preparing official audio releases

This implementation is in development. No recordings have been published by
these changes. Technical verification, public asset/voice/artwork permission,
and final publication are separate gates.

Python 3.11+ and GitHub CLI are required for the publisher. Offline validation
uses only Python's standard library. Node is needed only for browser-logic tests.
Credentials remain in the normal authenticated GitHub CLI environment; never
put tokens in manifests, approval records, command arguments or Git.

## Contracts

The publication manifest (`scripts/publication.py`) is schema version 1, separate
from the website catalog. Its required fields are `schema_version`, `repository`,
`tag`, `edition`, `source_commit`, `source_version`, and `assets`. The repository
is fixed to this audio repository; source commit is a full 40-hex Git SHA.

Each asset has `asset_id`, a safe flat local `filename`, an explicit ASCII
`remote_filename` for GitHub, `format`, `size_bytes`, `sha256`
and `provenance`. Provenance contains `source_manifest_sha256` and
`technical_receipt_sha256`; audio additionally requires `master_sha256`.
Non-audio files do not invent an audio master hash. Optional `export_commit`
records the later packaging implementation separately. Optional `render_source`
records `state` (`committed` or `frozen-working-tree`), `base_commit`,
`snapshot_sha256`, `snapshot_scope: public-repository-files`, and an optional
`audio_code_equivalent_commit`. A later equivalent commit is not misrepresented
as the HEAD used during rendering. Unknown fields are rejected.

Audio has a `session` object: `kind`, nullable `function_id`, `title`, `locale`,
`voice_id`, `voice_name`, `edition`, measured `duration_seconds`, `sample_rate_hz`,
`channels`, `encoding`, and optional measured `bit_depth`. The kind is `function`
or `preparation-learning`; Preparation Learning must have a null function ID.
Public voice identifiers and labels must be deliberate public metadata, never
copied automatically from a private voice profile or model path.

A canonical manifest digest hashes UTF-8 JSON with sorted keys, compact
separators, unescaped Unicode and a final LF. Asset arrays preserve order.
Approval binds that exact digest, including metadata, repository and tag.

An owner approval record contains `schema_version: 1`, `manifest_sha256`, `owner`,
a timezone-aware `approved_at`, and Boolean `public_assets`,
`voice_redistribution`, `artwork_redistribution`, `publish`. The first three
permissions must be true even for draft upload. `publish` must also be true for
finalization. Do not infer these decisions from tests or fabricate an affirmative
record. Keep the approval record private; the publisher does not upload it.

## Offline and remote execution

Start with offline verification (no GitHub calls):

```sh
python scripts/github_publisher.py /path/to/publication.json /path/to/staged-assets
```

Only after exact public asset permission, stage an approved draft:

```sh
python scripts/github_publisher.py /path/to/publication.json /path/to/staged-assets \
  --execute --approval /path/to/owner-approval.json \
  --distribution-commit FULL_AUDIO_REPOSITORY_COMMIT \
  --receipt /path/to/durable/publication-receipt.json
```

After separate final approval, repeat with `--finalize`. To propose a catalog
snapshot after confirmed publication, add `--catalog site/catalog.json` and
`--catalog-output /path/to/new-catalog.json`. Existing catalog output is never
overwritten. Review and integrate the proposal through normal Git review before
Pages deployment. Draft assets never appear as public downloads.

Do not run competing publishers for the same tag. Use one durable receipt and
external serialized workflow/production supervision. A crashed local execution
lock requires process-identity reconciliation before removal. Network errors
never mean a release is absent. Retry resumes by reading remote state and
hashing downloaded bytes, not by clobbering an asset. A missing or replaced
previously recorded release is a blocker; it is not automatically recreated.

All assets are verified locally before upload and copied into temporary verified
staging immediately before each write. Only one staged audio file is needed at
a time. Remote downloads are streamed to temporary storage and hashed. Allow
scratch headroom for one upload snapshot and one read-back. Readable local and ZIP-entry names remain unchanged. The approval manifest binds
the GitHub-compatible transport filename separately, with the same descriptive
components. Checksums for GitHub downloads use those remote names. Uploaded names must
match exactly; GitHub filename normalization is a blocking error requiring a
new reviewed manifest, not an automatic rename.

Three generated files are also uploaded and read back: `publication.json`,
`release-notes.md`, and `SHA256SUMS.txt`. Checksums cover the manifest, notes and
all content assets; the checksum file does not recursively hash itself. The
manifest permits at most 997 content assets, reserving the three metadata slots.

## Collections and library

`collections_export.build_collections` optionally creates deterministic ZIP
parts grouped by voice, language and format. Each contains separate recordings,
a relative M3U8 playlist and a member checksum manifest. Audio is stored without
recompression. Byte hashes are checked during creation and archive read-back.
GitHub transport names include a deterministic hash suffix to avoid collisions
between language/voice groups. The output directory must be new; failed staging is retained for diagnosis.
Collection assets need their own exact public approval before upload.

Production catalog snapshots use schema version 2, validated by
`scripts/catalog_contract.py`. Version 1 remains readable for the existing
scaffold and historical data; a nonempty version-1 catalog requires an explicit
migration. New releases are immutable, with separate `functions`, `preparations`
`collections` and `companions` arrays. Selectors must match session languages/voices and
all primary asset URLs must match the approved release tag. Canonical asset order
is retained so the validator can reconstruct the approved manifest and check its
exact digest, including local-to-remote filename mappings.

The site supports search, voice/language filters, per-function query links,
HTML5 MP3 controls, individual downloads, checksums, edition listings, selection
download lists and MP3 playlists. It does not claim to build ZIPs in the browser.
A published collection must exist before it can be offered for download.
Browser/display/playback verification and cross-repository publication automation
remain release gates; passing the JavaScript logic tests is not that evidence.

## Catalog deployment

The Pages workflow rebuilds the catalog from owner-published release manifests.
It verifies the canonical manifest digest against the release marker and every
asset's stored GitHub SHA-256, size and uploaded state. This is explicitly API
digest verification, not another full audio download; the publisher performs
full download verification before finalization. Missing server digests block
deployment for reconciliation rather than silently weakening checks.

Unmarked releases and drafts are not listed. Only releases authored by the
repository owner are accepted by the initial automation; additional publishing
principals need an explicit reviewed policy change. The workflow uploads and
deploys the exact verified site artifact. It does not commit generated catalogs
directly to main or rewrite historical releases.

After approved publication, explicitly dispatch the existing Pages workflow:

```sh
gh workflow run pages.yml --repo meramsey/open-consciousness-functions-audio --ref main -f release_tag=AUDIO_TAG
```

This explicit handoff also works when the release was created with a workflow
token whose ordinary events do not start another workflow. Reconcile an
uncertain dispatch response against Actions runs before retrying. Confirm the
exact run and deployed catalog before reporting a release as available.

A read-only local check is available with:

```sh
python scripts/refresh_catalog.py --output /path/to/new-catalog.json
```

This never uploads audio, edits a release, or deploys Pages.

## Import verified source exports

Run the source repository's `audio export-public` command first. Then import the
explicit `export-candidate.json` files into a new local bundle:

```bash
python scripts/import_candidates.py /path/to/session/export-candidate.json \
  /path/to/preparation/export-candidate.json \
  --tag audio-example-v1 --edition 1.0.0 --output /path/to/new-bundle
```

The importer verifies every copied byte, the technical receipt, source revision,
edition and session identity. Preparation Learning remains separate and sorts
first. Human-readable local filenames are retained. Explicit ASCII remote names
include a filename digest to prevent Unicode normalization collisions on GitHub.
The resulting `publication.json` is suitable for publisher preflight; it supplies
no owner approval and uploads nothing. Existing outputs are never overwritten,
and failed staging is retained for diagnosis. Do not import private delivery
receipts directly or add the local asset bundle to Git.

## Assemble the owner review packet

Prepare individual files, optional collection ZIPs, publication metadata and an
exact proposed asset list in one fresh local directory:

```sh
python scripts/prepare_review.py /path/to/export-candidate.json \
  --tag audio-review-v1 --edition 0.1.0 --collections --output /path/to/new-review
```

The `assets/` directory contains the publisher input, release notes and public
checksums. Public `SHA256SUMS.txt` uses the approved transport names; local
`LOCAL-SHA256SUMS.txt` uses readable local names and can be checked from `assets/`.
`review.json` lists exact sizes, digests, sessions and proposed URLs. Those URLs
do not claim that assets exist remotely. The packet is not an approval record:
listening, content/artwork rights, voice redistribution and final publication
remain owner decisions. No remote API is called. Preserve failed assembly
directories for diagnosis. Keep the complete packet outside Git.
