# Frozen-draft transfer reconciliation protocol

Status: offline reconciliation, guarded finalization-only transport and trusted
catalog integration are implemented. The committed registry is empty and no real
final approval exists; real release execution remains disabled. Migration comes first, publication later. The offline reconciliation tool
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

Historical transfer snapshot construction is an explicit projection of authenticated
API/byte-read results. The finalizer also implements fresh current-state network
collection; it never fabricates historical before-transfer observations. Do not feed the metadata-only
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

## Reviewed registry and catalog integration

`migration-attestations/index.json` is the trust anchor in the reviewed code
checkout. It starts as `{ "schema_version": 1, "entries": [] }`. Each future entry
has exactly `release_id`, `attestation_sha256` and `bundle_sha256`. A bundle named
`<bundle_sha256>.json` has exactly `schema_version: 1`, `manifest`, `before`, `after`
and `attestation`. Both digests hash canonical JSON, not formatting. The loader
checks all fields, hashes, release IDs and the reconstructed attestation; unknown
entries, renamed bundles, forged pins, symlinks and inconsistent evidence fail.
No private approval is committed or embedded in that public bundle.

Only reviewed repository commits may add an authenticated real evidence bundle
and its index entry. Release assets and manifests cannot add themselves to this
registry. The native finalizer requires this checkout's default registry, a clean
working tree, and HEAD equal to its approved distribution CI commit. An arbitrary
caller-supplied directory is accepted by offline test/library interfaces only;
it cannot substitute for the native execution trust anchor.

Catalog schema 3 supports ordinary schema-2-shaped entries plus transferred
entries with `manifest_repository`, `download_repository`, `repository_id`,
`release_id` and `migration_attestation_sha256`. Validation reconstructs the
original manifest and compares it to the pinned bundle while keeping new
organization URLs separate from the original manifest digest. Ordinary schema-2
validation is unchanged. Browser code recognizes schema 3's same display shape.

Refresh requires the live distribution repository ID, an already-published release
by `meramsey`, the unchanged marker/target/upload identity, all pinned remote asset
IDs, exact names/sizes/states, and every original content/control digest. It then
projects the original manifest with organization download URLs. Drafts remain
excluded. A self-attached attestation never establishes catalog trust. This is
GitHub API digest verification; full byte verification belongs to finalization.

## Finalization-only adapter

`scripts/transfer_finalizer.py` implements the dedicated adapter. Ordinary
`github_publisher.py` still rejects legacy manifests. The new adapter cannot create
releases, upload/delete/replace assets, edit markers or move existing tags. Its
only native mutation shape is PATCH of the exact existing release with
`draft: false` and `make_latest: false`.

It requires THREE separately authenticated private records:

1. The unchanged original approval, validated against the ORIGINAL manifest
   digest and public asset/voice/artwork rights. Its old `publish` value supplies
   no permission for the organization destination.
2. The exact reconciliation approval defined above (`publish: false`).
3. A new final approval defined below, granting this specific publication at the
   organization destination and explicitly lifting the owner-directed release hold.

All records come from the authenticated supervising approval channel. The tool
never manufactures them or proves authenticity merely by parsing an `owner`
string. Source-code access and a successful test/CI run do not grant approval.

The final approval contains exactly:

- `schema_version`: integer 1; `purpose`: `publish-transferred-draft`;
  `owner`: `meramsey`.
- `approved_at`, `expires_at`: timezone-aware timestamps after reconciliation;
  approval must be currently valid and last no more than 24 hours.
- `repository`: the fixed organization audio name; `repository_id`: 1437852834;
  `release_id`, `tag`, `distribution_commit`: exact attested draft identity.
- `original_manifest_sha256`, `destination_manifest_sha256`,
  `attestation_sha256`, `bundle_sha256`, `registry_sha256`,
  `original_approval_sha256`, `reconciliation_approval_sha256`: exact canonical
  hashes binding the complete public evidence and private approval records.
- `ci_commits`: exactly `source` and `distribution`, each a full commit SHA.
  These are approved CODE main commits, separate from the frozen render/source
  provenance and the existing release target. No old provenance/target is changed.
- `allow_tag_creation`: Boolean true only if the attested tag ref was absent.
  Finalization can create that missing lightweight tag at the frozen target;
  a pre-existing tag must retain its exact ref/object identity.
- `public_assets`, `voice_redistribution`, `artwork_redistribution`,
  `release_hold_lifted`, `publish`: all explicitly Boolean true.

The native transport checks the current IDs and main SHAs of both repositories.
It requires successful completed push-to-main runs at those exact SHAs for source
`test.yml`, `lint.yml`, `validate.yml`, `generated-index-check.yml`, and audio
`validate.yml`. Missing, pending, failed, wrong-event, wrong-path or wrong-commit
runs fail closed. All matching run pages are checked within a bounded inventory; active attempts
block execution, and latest update time selects reruns even when their original
run ID is older. A newer failed attempt cannot be replaced by an older success.
The running clean code HEAD must equal the approved audio CI SHA. No caller's
self-reported `ci_passed` flag is accepted.

Before mutation, the adapter verifies downloaded bytes for every asset, including
all original controls, between consistent full metadata observations. It repeats
current identity/inventory and CI/main checks at the mutation boundary. Byte hashes
may be cached only within that transport instance and only while every ID/name/
size/state/API digest stays unchanged. Cache reuse is not a new byte download.
A changed inventory invalidates the cache and blocks mutation.

Use fresh receipt paths outside the code checkout, separate from the frozen
packet's receipt. Defaults perform verification only; the extra `--execute` flag
is necessary but not sufficient for publication:

```sh
python scripts/transfer_finalizer.py ORIGINAL_MANIFEST --release-id RELEASE_ID \
  --original-approval ORIGINAL_APPROVAL --reconciliation-approval NEW_RECONCILIATION_APPROVAL \
  --final-approval NEW_FINAL_APPROVAL --receipt NEW_TRANSFER_RECEIPT
```

Do not add `--execute` until the exact final owner decision exists, the hold is
lifted, the registry is reviewed/merged and exact-main CI has passed. Both the
orchestrator and the native PATCH method validate those gates. No actual approval
record is supplied or generated by this implementation or its synthetic tests.

The supervisor must serialize this release across hosts and use one canonical
new receipt path. An exclusive local lock blocks duplicate local owners; unknown
stale locks require reconciliation, not deletion by the tool. A durable
`finalize-requested` intent is fsynced before PATCH. The native boundary also
exclusively creates and fsyncs a permanent `.attempt` marker and records
`mutation-attempted` before PATCH. Neither direct calls nor a restored stale intent
can reuse that attempt marker. Never delete it to force a retry. A lost response is reconciled
read-only. If the draft still appears unpublished or readback fails, the intent
stays pending; rerunning cannot issue a second PATCH. A replay may only verify
that the matching pending operation is already published with unchanged assets.
An already-published release without matching intent cannot be silently adopted.
Expired approvals or changed main/CI also stop execution; the supervisor must
reconcile such cases explicitly, without inventing approval or replacing intent.

After finalization, the same inventory, marker, target, publisher and expected
tag ref are checked again before a new `published-verified` transfer receipt is
written. It is a separate receipt schema; it never overwrites the original record
or substitutes for an ordinary publisher receipt.

## Remaining live gates

Migration engineering authorization permits reviewed PRs and CI, not publication.
The registry deliberately contains no real entries. The supervisor must prepare
authenticated real before/after full-byte evidence, route its exact new approval,
and review/merge its public registry entry. Then it must prepare the final approval
against exact green main SHAs and keep the release held until the owner grants
that decision. No media reupload or old control rewrite is needed for this path.

## Explicit historical-receipt mode (v2)

The separate `historical-receipt-v2` mode supports a historical full-download
receipt when terminal-time tag and commit API observations were not retained.
Version 1 remains strict. There is no fallback from a failed v1 validation.
Unknown historical tag state is never encoded as observed absence, and current
Git objects or API results are never backdated as historical observations.

V2 binds the historical manifest, full receipt/inventory, frozen verifier-code
hashes and archived provenance. Raw archived file hashes and canonical normalized
JSON hashes are distinct domains. The supervisor must authenticate the archive and
original owner messages; matching hashes and strings cannot authenticate themselves.
The new destination evidence still requires full byte verification, exact repository
and release identities, resolved target commit, and a currently absent tag. An
existing tag stops this narrow mode for separate review, even if it resolves to the
same target. Metadata observations around byte verification must remain consistent.

The new reconciliation approval must explicitly acknowledge unverified historical
tag continuity and authorize the exact current absent-tag creation scope, while
keeping `publish: false`. Final approval is a separate decision. Mode and the
uncertainty acknowledgement are bound through attestations, registry entries,
approvals, finalization receipts and catalog entries. Unknown modes and cross-version
substitutions fail closed. The committed registry remains empty; synthetic tests
never create real approvals or historical evidence.

Before finalization, the current tag must still be absent. After publication, only
the approved newly created lightweight tag at the exact frozen commit is accepted.
Response loss permits read-only reconciliation; it cannot cause another PATCH.
The native adapter also serializes writers per repository/release in
`~/.local/state/ocf-transfer-finalizer` and retains a permanent per-release attempt
marker. Changing receipt paths cannot bypass that marker. Do not remove markers
or stale locks automatically. Across hosts, the supervisor must enforce one writer
and keep competing release/tag services held. GitHub does not offer an atomic tag
compare-and-swap through release PATCH; unresolved competing writers block release.

The owner must see the concrete historical uncertainty in the eventual approval
request. Migration engineering authorization does not accept that uncertainty on
the owner's behalf or grant publication permission.

## Public registry commitments and private finalization inputs

Historical-receipt reconciliation remains mode v2, but its **public envelope is
schema 3**. The complete schema-2 bundle is private evidence and is rejected by
the public registry. A schema number must never implicitly select a different
approval mode. Strict v1 remains unchanged and contains only its public manifest,
public release snapshots and attestation, with no owner approval embedded.

`public_transfer_evidence.build_public_bundle(private_bundle)` validates the private
bundle, preserves its exact attestation, and derives a closed public envelope with
`evidence_visibility: public-commitments`. It contains only the original public
manifest, destination snapshot, attestation and commitments to historical evidence,
original rights approval, archive provenance and the fixed-role archive-hash inventory.
No original approval content, historical object, message IDs or local archive paths
belong in the public envelope, registry, PR body or logs. Existing public manifest
content is preserved, not silently redacted or rewritten.

A public commitment proves consistency with reviewed bytes, not authenticity of
archived evidence or owner identity. An authorized independent reviewer must privately
rebuild and compare the exact projection before a public index can pin its bundle,
attestation, release ID, mode, envelope schema and visibility. This repository's
index remains empty until separate exact reconciliation authorization.

The finalizer requires `--private-historical` for schema-3/v2 records, alongside the
separate original rights, reconciliation and final approvals. It rederives the exact
attestation and all historical commitments at both high-level and native mutation
boundaries. Public registry data alone cannot satisfy this private-evidence gate.
The catalog validates only the public envelope and never loads private records.
Validation failures involving private evidence suppress input fields, contents and
paths rather than echoing them into errors. Full private evidence stays in owner-only
local storage and must not be submitted to public CI for real releases.

Freeze and independently inspect the proposed public envelope and index hashes before
routing the owner decision. Reconciliation authorizes only the exact transfer binding
and acknowledged historical uncertainty; it does not publish. Later final approval
binds that public bundle/index and successful current-main commits. If any binding
changes, obtain new scoped approval rather than reusing an earlier decision.
