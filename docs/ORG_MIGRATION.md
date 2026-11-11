# Organization transfer and publication hold

This is a preparation checklist, not permission to execute a transfer, change
settings/DNS, push/merge, upload assets or resume publication. Transfer the existing
repositories to `ocfproject-org`, retaining their names. Do not create replacements.
The human publisher remains `meramsey`. This branch fixes the publishing destination
to the organization; activate it only as part of the reviewed transfer sequence.

## Verified preparation baseline (2026-11-11 UTC)

Read-only GitHub API inspection found:

| Repository | Stable repository ID | Remote main |
| --- | --- | --- |
| meramsey/open-consciousness-functions | 1367603146 | 0e7ca1199969f41f282b8cff5a5fb0ee459fdb46 |
| meramsey/open-consciousness-functions-audio | 1437852834 | f5bc91028e4008b290dbeb89068fc12ddde2710c |

Audio draft `441878809`, tag `audio-0.1.0-a6-20261111`, remains a draft,
authored by `meramsey`, with 481 assets. The owner's handoff records verified
transport assets and frozen manifest digest
`48cb39bcc3dfd7f7e211b3093cd927c3a790cd9ad28d6b47faad956014c85c14`.
The live marker matches that digest, and the draft targets
`ac70688831be3c02e582ce35ac41cf7585da42bd`. A paginated inventory found 481
unique asset IDs/names, all uploaded, all with SHA-256 server digests.
This preparation checks metadata only; it does not independently download those
assets or reinterpret the frozen approval. Keep the packet, approval and receipt
unchanged. Preserve approved media and historical evidence/URLs.

The owner's handoff records paused publisher/controllers, MainPID=0 and stopped
watchdog timers. A later read-only systemd check found the release service inactive
with MainPID=0, but `ocf-codex-release-20261111-watchdog.timer` active/waiting;
the continuation watchdog timer remained inactive. This is a transfer blocker
until the responsible operator reconciles the hold. No services were changed.
Recheck actual process identities before transfer; do not restart services. Prior release owner `01a1c834-7486-73c2-8c2f-13f7c512577b` stays paused.

## Pre-transfer go/no-go

1. Review and validate both isolated changes. Confirm source export stays
   destination-neutral and the audio publisher alone binds the organization
   repository. Preserve personal attribution and historical run/release links.
2. Reconcile actual writers, worktrees, HEADs and remote main again. Keep services
   held. Record branch/tag SHAs, open PRs/issues and repository IDs before transfer.
   Resolve newly advanced main without rewriting history. No forced pushes.
3. Read-only membership inspection found the authorized GitHub session active
   with org admin role; both destination repository lookups returned HTTP 404.
   These are point-in-time observations, not proof of every transfer policy.
   Have an organization owner confirm transfer acceptance rights, repository-name
   availability, organization policies and `meramsey` access. Inventory branch
   protection/rulesets, environments/reviewers, Actions permissions, Pages source,
   webhooks, GitHub Apps, deploy keys and runner access without revealing secrets.
4. Save a read-only, paginated inventory of draft 441878809: release/tag/target,
   draft state, marker, author, and each asset's ID, name, size and SHA-256. Compare
   it to the frozen receipt; stop on any drift. An asset count alone is insufficient.
5. Agree on Pages interruption/cutover and maintain the publication hold. Push and
   merge need later explicit instruction; no remote CI is claimed for local commits.
   Transfer only after the preceding gates and explicit operator authorization.

Use GitHub's native transfer for each existing repository. It preserves repository
history and associated issues/PRs; still verify the stable IDs and release inventory
on arrival. Do not recreate the old names: that can disrupt redirects. Repository
redirects do not provide a redirect for the old GitHub Pages site.
[GitHub transfer documentation](https://docs.github.com/en/repositories/creating-and-managing-repositories/transferring-a-repository).

## Post-transfer verification (release remains no-go)

1. Read `repos/ocfproject-org/open-consciousness-functions` and
   `repos/ocfproject-org/open-consciousness-functions-audio`; require IDs above,
   expected default branches and preserved branch/tag ancestry. Confirm issues,
   PRs, releases and protected settings against the pre-transfer inventory.
2. Re-read draft 441878809 under the new owner, using paginated asset listing.
   Require unchanged ID, draft state, tag, target and all 481 asset IDs/names/sizes/
   digests. Verify full bytes against the frozen receipt before any later release
   action. Stop on missing digests, asset drift or an unexpected published state.
3. After explicit authorization, update origins in every real checkout/worktree,
   service and agent environment to the matching `ocfproject-org` repository.
   Check fetch/push destinations and credentials via normal GitHub tooling, never
   printing tokens. Revalidate app installation, SSO/token scope, Actions permissions,
   protected environments, runners and Pages access as the actual service identity.
4. Integrate reviewed commits and verify complete CI on the exact new main SHAs.
   Verify `meramsey` remains an authorized release author. An organization login,
   arbitrary collaborator or bot is not automatically accepted by the catalog.
   Confirm wrong repository and upload URL rejection remains enforced.
5. Validate the Pages artifact and browser behavior at the project path and custom
   domain root. Local CSS/JS/catalog paths are relative; release asset URLs remain
   absolute GitHub URLs. Do not add a root-relative asset base or rewrite historical
   downloads. Confirm filters, query links, MP3 controls and playlist downloads.

## Frozen packet and destination-bound approval

The new publisher rejects the old repository manifest. Changing `repository`
changes the canonical manifest digest and generated `publication.json` and
`SHA256SUMS.txt`; the old approval cannot authorize that change. Never patch the
frozen packet, transplant its approval/receipt, or replace uploaded control assets
in the existing draft to make the new publisher accept it.

Prepare a separate proposal only after migration, in a new directory. Preserve
content asset IDs, names, sizes, hashes, source/render/export provenance and byte
content exactly. Diff old/new manifests and inventories explicitly. A new tag or
edition also changes the manifest and needs approval. Record the old digest and
release ID as reconciliation evidence outside the strict publication manifest;
do not add unsupported schema fields. Obtain explicit destination-bound approval
for the complete new manifest, rights and final publication, with a new receipt.

The current publisher intentionally cannot adopt draft 441878809 with a different
marker or inventory. If a new approved packet is chosen, it requires a separately
authorized new draft/tag and uploads, leaving the frozen draft intact. If reusing
the existing draft without changing any uploaded bytes is required, stop: a
separately reviewed migration attestation/protocol is needed to bind the old
manifest to the new destination. No such attestation is implemented or implied by
this change. Transfer alone grants neither path authorization.

## ocfproject.org / Cloudflare cutover

The intended domain is `ocfproject.org`, registered through Cloudflare. No DNS,
Pages setting, CNAME or organization setting is changed by this branch.
An organization owner should verify the Pages domain under `ocfproject-org`
before associating it with this repository. Add the exact GitHub-issued TXT
record in Cloudflare and retain it; do not guess the challenge. This is Pages
custom-domain verification, separate from a general organization verified badge.
[GitHub domain verification](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/verifying-your-custom-domain-for-github-pages).

At the authorized cutover, use the current GitHub Pages DNS instructions for the
apex and any chosen www alias, reconcile conflicting records, configure the Pages
custom domain, and verify DNS, certificate issuance and HTTPS. Check Cloudflare
proxy/TLS behavior explicitly rather than assuming successful DNS means Pages is
serving the site. Do not advertise the domain as live until verified. Plan how to
communicate the old Pages URL break; GitHub does not automatically redirect it.
[GitHub custom-domain setup](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site).

Release is no-go until transfer verification, exact-main CI, destination approval,
frozen-draft reconciliation, actual runtime permissions and owner authorization
are all complete. Domain availability is a separate verified website milestone.
