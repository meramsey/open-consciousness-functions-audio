# Official audio release readiness

Audit date: 2026-11-10. This is an engineering checkpoint, not publication approval.

## Repository state

- Source main: `0e7ca1199969f41f282b8cff5a5fb0ee459fdb46`.
  Its [22 checks passed](https://github.com/meramsey/open-consciousness-functions/actions/runs/42694360289).
- Distribution main: `eece8fc12dd8826d8f68230ab5d28df9f37a9c74`.
  Its [validation and Pages checks passed](https://github.com/meramsey/open-consciousness-functions-audio/actions/runs/40809316690).
- Both branch API responses report `protected: false`. This audit did not change
  repository settings or protections.
- Distribution has no GitHub releases. The existing version-1 catalog is empty.
- New distribution work is isolated on `engineering/official-audio-release-20261110`.
  No new code or audio has been pushed or published.
- Source artwork and descriptive guide-name fixes are committed locally at
  `38b3a63f7039b38e033b4108576a3403e50b103d`; their frozen final coverage gate
  was still running at this checkpoint. Earlier main CI does not validate them.

## Gaps to close

1. The source `audio release` pathway renders again. Public export must instead
   accept a verified existing master and preserve its actual resolution, with
   technical provenance and independent approvals.
2. The scaffold catalog validator does not enforce all production metadata or
   relationships. A distinct strict publication manifest and exact-hash owner
   record now have an offline implementation; integration is in progress.
3. The publisher state machine and GitHub CLI transport are local engineering
   work. Mock transport tests are not evidence of real upload/download behavior.
4. Local browsing/filter controls, per-function query links, edition listings,
   selection lists, catalog projection and optional ZIP packaging are implemented.
   Browser verification and cross-repository automation remain outstanding.
5. Current local recordings are private candidates. Exact public file selection,
   voice redistribution, artwork rights and final publication need owner review.
   Successful rendering, technical checks, or a draft release are not approval.
6. New-commit cross-platform CI, deployment smoke tests and a phone/browser
   release-candidate review remain outstanding.

## Publication contract and recovery

`scripts/publication.py` validates a separate publication schema version 1. It
accepts explicit public metadata only, rejects unknown fields, requires full
source commit and provenance digests, and enforces safe flat asset names and
GitHub size/count limits. Preparation Learning has kind `preparation-learning`
and no function ID. It is not represented as a fabricated function.

Owner records bind the canonical manifest SHA-256 and separately confirm public
assets, voice redistribution, artwork redistribution and final publication.
These records document an owner decision; they do not authenticate an identity
or make an automated legal determination. Never generate affirmative approval
records on behalf of the owner without their exact authorization.

The publisher uploads only after approval, verifies downloads, retains immutable
release identity, and reconciles uncertain responses before retrying. Metadata
includes deterministic publication JSON, release notes and checksums. Its
transport never clobbers assets, moves tags or deletes releases. An asset renamed
by GitHub is a blocking reconciliation error, not silently accepted.

Use one canonical receipt per tag and serialize writers with workflow concurrency
or the existing OCF production supervisor. GitHub offers no transaction spanning
our draft check and asset upload; another actor must not publish/edit the same
release concurrently. Interrupted receipt temporary files remain diagnostic data.
A stale execution lock must be checked against process ownership before recovery;
do not blindly delete it or start a competing publisher.

The CLI defaults to offline file verification. `--execute` requires an approval,
exact distribution commit and durable receipt; `--finalize` additionally requires
final publication approval. No credentials are extracted into manifests or logs.
Large uploads/read-backs require independent production supervision when run.

See GitHub's [release API](https://docs.github.com/en/rest/releases/releases) and
[asset API](https://docs.github.com/en/rest/releases/assets) for remote semantics.
Do not use a successful mock test as evidence that public assets exist.
