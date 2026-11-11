# Historical receipt evidence schema (v2)

This schema is implemented by `scripts/reconcile_historical_transfer.py`. It is
an explicit alternative mode, `historical-receipt-v2`, never a fallback from failed
v1 validation. All objects below have closed fields. Boolean/integer distinctions,
complete inventory joins and fixed destination restrictions are enforced. It
creates proposals and validates supplied approvals; it cannot authenticate an
archive or owner message, collect remote evidence or authorize publication.

## Digest domains and trust

`raw_file_sha256` always identifies immutable archived source bytes. New normalized
records use canonical JSON SHA-256 via `publication.canonical_bytes`, explicitly
named `canonical_sha256`. These domains are never substituted. The one deliberate
comparison of original manifest raw bytes with canonical manifest identity follows
the existing publication contract: uploaded `publication.json` must be canonical.
Noncanonical original manifest bytes are rejected, not rewritten.

The supervisor must verify source-file hashes, archived receipt authenticity,
owner messages and exact normalized projection before proposing the bundle.
A hash-shaped string, `verified_by`, or `verification` assertion cannot prove its
own authenticity. The trusted local registry and authenticated approval channel
supply that trust. A changed raw hash changes the attestation and invalidates the
prior reconciliation approval. No actual archive or approval is created by tests.

## Historical object

The top-level object contains exactly:

- `schema_version`: integer 2; `mode`: `historical-receipt-v2`.
- `repository_id`: integer 1437852834; `repository`:
  `meramsey/open-consciousness-functions-audio`.
- `historical_tag_state`: literal `unknown`.
- `historical_commit_api_resolution`: literal `unobserved`.
- `manifest_raw_file_sha256`: hash of original uploaded manifest bytes.
- `rights_approval`, `download_receipt`, `terminal_inventory`, `frozen_code`,
  `frozen_config`, `prelaunch_tag_observation`, `trusted_provenance`: objects below.

`rights_approval` contains `raw_file_sha256`, `canonical_sha256`,
`manifest_canonical_sha256`, original nonempty `owner` label, timezone-aware `approved_at`,
`public_assets`, `voice_redistribution`, `artwork_redistribution` (all true), and
Boolean `publish`. Its canonical digest is verified by reconstructing the original
schema-1 approval with `manifest_sha256`, preserving the six approval fields.
The original publication permission never authorizes transfer publication.

`download_receipt` contains `raw_file_sha256`, timezone-aware `verification_recorded_at`,
`observation_basis` (`receipt-recorded-verification` or
`terminal-recorded-receipt-verification`),
positive integer `release_id`, `manifest_canonical_sha256`, `verification`
(`full-download-sha256`), and `assets`. Each asset contains exactly `remote_id`,
`name`, `asset_id`, `size_bytes`, `sha256`, `download_sha256`.

`terminal_inventory` contains `raw_file_sha256`, timezone-aware `observed_at`,
`release_api_url`, `release`, and `assets`. Its release contains exactly `id`,
`tag_name`, `target_commitish`, `draft` (true), `author` (`meramsey`), `body`,
`upload_url`. Old repository API/upload URLs are checked exactly. Each asset
contains `remote_id`, `name`, `asset_id`, `size_bytes`, `sha256`, `state`
(`uploaded`), `api_digest` (`sha256:` plus expected hash).

Both inventories must include every manifest asset and all three original
controls, with unique names and positive integer remote IDs. Their joins must
match exactly by identity, size and hash, including controls. Missing, extra,
duplicate, replaced or renamed entries fail. The current complete byte snapshot
must match the same full inventory and release metadata.

`frozen_code` and `frozen_config` each contain `raw_file_sha256` and nonempty
`source_id`. These records document frozen execution provenance, not proof that
code ran or granted permission.

`prelaunch_tag_observation` contains `raw_file_sha256`, nonempty `source_id`,
`observation_time`, `state` (`absent`) and `ref` (exact `refs/tags/<tag>`).
Time is explicitly `{state: unknown}` when the archive does not record it; otherwise
it is `{state: recorded, observed_at: <timezone-aware actual timestamp>}` and must
predate terminal evidence. Neither form fills the unknown
historical terminal tag state or proves continuity.

`trusted_provenance` contains `verification`
(`authenticated-archive-and-owner-messages`), nonempty `archive_source_id`,
nonempty unique text `owner_message_ids`, nonempty `verified_by` (the actual
supervisor/verifier identity), `authenticated_owner` (`meramsey`), and
timezone-aware `verified_at`. Verification must be at or after terminal evidence
and no later than now. The verifier is not attributed to the owner merely because it inspected owner
messages. This is the supervisor's projection of separately verified
provenance, not an authentication mechanism.

The original rights owner label is preserved exactly; authenticated provenance
separately identifies the human publisher. Original rights approval precedes or
coincides with the recorded receipt-verification observation. That observation
precedes or coincides with terminal evidence; with terminal-derived observation
basis its timestamp must equal the actual terminal timestamp. No asset-download
time or missing receipt timestamp is invented. Terminal evidence strictly precedes
the current snapshot. Current evidence uses the unchanged v1 snapshot validator
and requires actual commit resolution/full downloaded hashes. Its `tag_ref` must
be null for explicitly observed current absence. Any existing current tag stops
this narrow mode, even when its commit matches. No historical snapshot is invented.

## Attestation and reconciliation approval

`build_attestation_v2(manifest, historical, after, now=None)` returns schema 2,
mode, purpose `ocf-historical-receipt-transfer-evidence`, fixed repository/owner
identities, expected publisher, release ID/tag/distribution commit, current
`tag_ref: null`, and full immutable assets. It binds:

- `original_manifest_sha256` and `destination_manifest_sha256`: compatibility
  field names for canonical manifest identities only.
- `original_rights_approval_canonical_sha256`: the verified original rights object.
- `historical_canonical_sha256` and `after_snapshot_canonical_sha256`.
- `uncertainty_acknowledgement` and its
  `uncertainty_acknowledgement_canonical_sha256`.

The fixed uncertainty object has schema 2, mode, `historical_tag_state: unknown`,
`historical_commit_api_resolution: unobserved`,
`historical_tag_continuity: unverified`,
`current_tag_requirement: observed-absent`, and
`authorized_tag_transition: absent-to-approved-distribution-commit`.

`verify_reconciliation_v2` accepts those three inputs, the exact attestation and a
separately authenticated approval containing exactly `schema_version: 2`, mode,
`purpose: approve-ocf-historical-transfer-reconciliation`, `owner: meramsey`,
`approved_at`, `attestation_canonical_sha256`,
`uncertainty_acknowledgement_canonical_sha256`,
`accept_unverified_historical_tag_continuity: true`,
`authorize_current_absent_tag_creation: true`, `reconcile: true`, `publish: false`.
Approval must follow current observation and provenance verification, and not be
in the future. Its output remains `reconciled-publication-held` with
`publication_allowed: false`, carrying explicit mode and canonical approval,
attestation and uncertainty hashes.

## Reviewed registry and freshness

A schema-2 bundle contains exactly `schema_version`, `mode`, `manifest`,
`historical`, `after`, `attestation`. Registry index schema remains 1; its v2 entry
must additionally contain the exact `mode`. Bundle filename/index digest and
attestation digest use canonical JSON. Missing/mismatched/unknown modes fail;
v1 entries and bundles retain their original strict schema. The committed index
remains empty until a separately reviewed real evidence entry is authorized.

Historical bundles remain verifiable over time. Execution freshness comes from
new authenticated reads, not retroactive timestamps or an age limit on durable
history. Finalization separately requires fresh absent-tag checks, fresh downloads,
exact approved target and CI, explicit final permission and uncertainty binding,
and the release-wide single-attempt guard. After publication the tag must be the
exact approved commit; an existing post-publication tag cannot be replayed as
pre-publication absence. Competing writers and ambiguous outcomes remain blockers.

## Visibility boundary

The schema-2 historical bundle described here is **private-only**. It is not a
public registry artifact. Keep original owner labels, approval values, message IDs
and archive paths unchanged in private evidence. Derive the separate schema-3
`public-commitments` envelope using `public_transfer_evidence.build_public_bundle`;
its attestation remains byte-identical. See [TRANSFER_PROTOCOL.md](TRANSFER_PROTOCOL.md)
for public pinning and separately supplied private finalizer evidence.
