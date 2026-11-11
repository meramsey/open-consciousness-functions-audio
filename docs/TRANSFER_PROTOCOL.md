# Frozen-draft transfer reconciliation protocol

Status: offline validation implemented; remote reuse/finalization and catalog
activation remain disabled. Migration comes first, publication later. This tool
never calls GitHub, copies media, generates approval, edits an old packet/receipt,
or accepts a new destination for ordinary publication. No real transfer evidence
or approval has been created by the synthetic tests.

## Fixed policy and trust boundary

Only repository ID `1437852834`, transferring from
`meramsey/open-consciousness-functions-audio` to
`ocfproject-org/open-consciousness-functions-audio`, is supported. The human
publisher and approval operator remain `meramsey`. No caller-supplied destination
allowlist exists. The proposal binds a specific release ID, full distribution
commit, tag/ref identity, original manifest digest, virtual destination manifest
digest, both evidence snapshots and every content/control asset identity.

A proposal is untrusted data. A release manifest, GitHub release body or a Boolean
inside either cannot authorize itself. The separate approval file is trusted only
when the supervising operator obtained it through the authenticated owner approval
channel and matched it to the reviewed proposal. A JSON `owner` string is not
identity authentication; this offline validator does not provide signatures or
prove that files came from GitHub. Never discover an approval automatically from
an asset directory, generate one from a manifest, or treat successful validation
as proof of identity. The supervisor retains the approval's authenticated source
and controls access to its file. The code validates the contents of that supplied
trusted approval, including its exact digest binding and scope.

The existing original approval remains immutable historical evidence. It does not
authorize the new destination. Reconciliation approval is a new, separate decision
with `publish: false`; original rights and a later explicit final-publication
decision are separate gates. The result is not a publisher receipt, and neither
`publisher.py` nor the catalog accepts it as one.

## Evidence collection owned by the supervisor

The supervisor must preserve the original packet/approval/receipt and prepare
new evidence files elsewhere. Do not read credentials or change live state.
The currently frozen draft is `441878809`, with 481 transport assets, target
`ac70688831be3c02e582ce35ac41cf7585da42bd` and original manifest digest
`48cb39bcc3dfd7f7e211b3093cd927c3a790cd9ad28d6b47faad956014c85c14`.
The reusable validator does not hardcode this release: the exact original
manifest, before/after snapshots and separate approval bind the chosen release.
For this migration the supervisor must compare these values to that frozen record.

1. Before transfer, capture the repository ID, draft metadata, full paginated
   asset inventory, exact tag ref (or verified absence) and resolved distribution
   commit. Hash every remote asset's downloaded bytes, including all three control
   assets. Existing frozen full-download receipt evidence may be used only if its
   authenticated provenance binds the same remote IDs, bytes and observation;
   never invent a historical timestamp or upgrade API digests into download proof.
2. Native-transfer the existing repository only after the operational hold and
   transfer gates in [ORG_MIGRATION.md](ORG_MIGRATION.md) are satisfied.
3. At the new destination, fetch repository ID and the same release ID, resolve
   the full distribution commit and tag, paginate all assets, stream-download and
   hash each asset, then repeat release/tag/inventory reads. Require identical
   identities, sizes, states and digests across the reads. A failed, partial,
   changing or ambiguous read is a blocker, not an absent release or asset.
4. Save a snapshot only after those reads finish consistently. Record the actual
   timezone-aware observation time. Streaming hashes need no permanent duplicate
   media and no uploads. API digests alone cannot satisfy the implemented protocol.
5. Compare with the authenticated frozen record, run `propose`, review the exact
   proposal, then obtain a separate authenticated reconciliation approval. The
   supervisor prepares and routes this evidence; the owner is not asked to perform
   a manual technical continuation.

Snapshot construction is an explicit projection of authenticated API/byte-read
results, not implemented network collection. Do not feed the metadata-only
preparation inventory to the tool as full-download evidence. Offline consistency
checks cannot establish remote freshness; repeat read-only checks if remote state
may have changed. A proposed new observation changes its snapshot/attestation hash
and cannot silently reuse an earlier reconciliation approval.

## Exact snapshot schema (version 1)

Unknown fields, duplicate JSON keys, nonfinite numbers, symlink input/output paths,
non-files and JSON inputs over 8 MiB are rejected. Numeric repository, release and remote asset IDs are positive integers,
not Boolean or text substitutes; logical asset IDs retain the manifest schema. Both snapshots contain exactly:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer 1 |
| `observed_at` | Actual timezone-aware timestamp, not in the future |
| `repository_id` | Integer 1437852834 |
| `repository` | Fixed old name before, fixed organization name after |
| `release_api_url` | Exact HTTPS GitHub API URL for that repository and release ID |
| `verification` | `full-download-sha256`; asserted evidence level, not self-authentication |
| `distribution_commit_sha` | SHA returned by the distribution commit lookup |
| `tag_ref` | null for verified absence, or the object described below |
| `release` | Draft metadata object described below |
| `assets` | Complete inventory, including the three unchanged controls |

`release` has exactly `id`, `tag_name`, `target_commitish` (full 40-hex SHA),
`draft` (true), `author` (`meramsey` login), `body` (the unchanged original digest
marker), and `upload_url`. Upload URL must be the exact GitHub uploads host/path
for that repository and release ID, optionally with `{?name,label}`. A redirect,
old-owner after URL, query, fragment, other host/repository/release is rejected.

A present `tag_ref` has exactly `ref` (`refs/tags/` plus the original tag),
`object_type` (`commit` or `tag`), `object_sha` (full SHA) and `peeled_commit`.
The peeled commit must equal the distribution target; a lightweight ref's object
SHA must also equal that target. Ref presence and object identity must be unchanged
across transfer. Commit lookup results must match the full release target.

Each asset has exactly `id`, `name`, `size_bytes`, `state` (`uploaded`),
`api_digest` (`sha256:` plus GitHub's digest), and `download_sha256` (measured
full-byte hash). IDs/names must be unique and unchanged, and the complete set must
match the old manifest and its old controls. Missing, extra, renamed, replaced,
partial or hash-mismatched assets fail. Media is never re-encoded. The original
`publication.json`, `release-notes.md` and `SHA256SUMS.txt` are verified as their
original bytes; destination-bound control files are not substituted.

## Commands and approval schema

Run from the distribution checkout, using new local output paths:

```sh
python scripts/reconcile_transfer.py propose ORIGINAL_MANIFEST BEFORE_JSON AFTER_JSON \
  --output NEW_ATTESTATION_JSON
python scripts/reconcile_transfer.py verify ORIGINAL_MANIFEST BEFORE_JSON AFTER_JSON \
  NEW_ATTESTATION_JSON --approval TRUSTED_NEW_APPROVAL_JSON --output NEW_RESULT_JSON
```

`propose` writes no approval and cannot authorize anything. Its canonical digest
is SHA-256 of `publication.canonical_bytes(proposal)` (sorted keys, compact UTF-8,
final LF). The proposal includes the complete inventory with stable logical asset
IDs and remote numeric IDs; raw snapshot digests bind observation times and order.
The virtual destination manifest differs only in `repository` and is only hashed,
never written into the old packet or uploaded. Its digest makes the changed
intended destination explicit without misrepresenting old uploaded bytes.

The independently supplied approval has exactly `schema_version` (integer 1),
`purpose` (`approve-ocf-transfer-reconciliation`), `owner` (`meramsey`),
`approved_at` (timezone-aware, at/after the after-snapshot and not in the future),
`attestation_sha256` (exact proposed digest), `reconcile` (Boolean true), and
`publish` (Boolean false). The tool has no approval-creation command. A copy of
an old publication approval cannot satisfy this schema or binding. A changed
proposal requires new approval. Outputs use exclusive creation and never overwrite
existing records. Retain any failed output as diagnostics; do not infer success.

`verify` produces `state: reconciled-publication-held` and
`publication_allowed: false`, binding repository/release IDs and the attestation,
approval and original manifest digests. This means the supplied approved evidence
is internally consistent, not that current GitHub state or approval authenticity
has been independently established by the offline program.

## Implementable later reuse/finalization design

The implemented protocol resolves evidence and destination approval without
changing media or draft bytes. It intentionally does not enable publication. A
future mutation adapter and catalog integration need the following exact design
review and activation after migration is confirmed; they are not implied by the
new reconciliation result:

1. Retain the original manifest/marker/control assets and draft ID. Store the
   canonical attestation as a separate durable, reviewed record. Recommended public
   location: an append-only `migration-attestations/<sha256>.json` in the distribution
   repository, pinned by a reviewed commit/index. Selecting and approving that
   public trust/retention mechanism is a consequential publication-policy decision;
   no registry or real attestation is created here. Private approval stays private.
2. Add a dedicated finalization-only adapter, not a bypass in ordinary publication.
   Require the exact original rights approval plus a new authenticated approval
   whose purpose is `publish-transferred-draft`, binding repository ID/name, release
   ID/tag/target, original/virtual-destination manifest digests, attestation digest,
   authorized human, rights flags and explicit publication permission. It must also
   require the supervising owner-directed publication hold to have been lifted.
3. Validate the approved reconciliation inputs with this module. Independently
   read current repository ID, tag/commit and draft metadata, then stream-verify
   every asset again and compare the immutable identity set with the attestation.
   Fresh observation timestamps go into a new execution receipt; they do not
   replace the approved historical snapshots. Any invariant drift stops execution
   and requires a new reconciliation/approval, never automatic repair.
4. Permit only the final `draft: false` transition on the exact existing release.
   Forbid create, upload, delete, asset replacement, marker edits and tag movement
   in this adapter. Recheck metadata and inventory immediately before mutation.
   Reconcile uncertain responses by GET; never blindly retry. After confirmed
   publication, re-read the same identity/inventory and persist a new, atomic
   migration-specific receipt. Do not overwrite the original receipt.
5. Ordinary catalog schema 2 cannot represent an old manifest digest reconstructed
   with a new repository. Specify schema 3 fields `manifest_repository`,
   `download_repository`, `repository_id`, `release_id` and
   `migration_attestation_sha256`. Only the fixed legacy-to-org mapping and a pinned,
   reviewed attestation may activate it. Validate the original manifest/control
   hashes, unchanged asset IDs, authorized author, marker and published state;
   project new destination URLs separately. Never trust a release's self-attached
   attestation or loosen ordinary schema-2 validation. Preserve historical entries.
6. Synthetic tests must cover every blocked mutation, old approval rejection,
   forged registry/approval, wrong repo ID/author/tag/target, changed media or
   controls, pagination omissions, published-state drift, concurrent mutation,
   uncertain finalization, receipt replay and catalog digest/URL separation.

Until that separately reviewed publication policy and adapter/catalog work exist,
transferred-draft reuse stays blocked even if offline reconciliation passes.
There is no technical reason to reupload or delete the preserved draft merely to
complete the repository migration. Transfer readiness, reconciled evidence and
publication readiness are three separate states owned by the supervisor.
