# Website UX/accessibility audit progress

**Audit:** `OCF_Website_UX_Accessibility_Audit_2026-11-13..txt` (362 lines), supplied for implementation on 2026-11-13. The referenced ZIP/screenshots were not supplied; no claims below rely on independent inspection of those screenshots.

**Audited inputs:** audio deployment/main `09293ca7e5003f13e959fcdc39e57acb091c7c98`; source main/pin `704440da8e0379cee8dfd332203bc0001c0a5f27`.

**Checkpoint 1 branch:** `fix/website-ux-restore-usability-20261113`, based on audio `origin/main` at `09293ca7e5003f13e959fcdc39e57acb091c7c98`. Draft PR [#16](https://github.com/ocfproject-org/open-consciousness-functions-audio/pull/16) is open for independent review. Its initial head is `593e6ce0953233447145035224b1255574554e4d`; PR CI was still running when this record was prepared. No merge, deployment or live-domain verification has occurred.

## Finding ledger (all 26)

| # | Status | Evidence / boundary |
|---|---|---|
| 01 Mobile Downloads columns | **Implemented; automated browser verified** | Replaced the six-column Downloads table with responsive session cards and separate MP3/FLAC links. Chromium, Firefox and WebKit checked all cards/actions at 320, 375, 390, 768 and 1440 CSS px; direct catalog URLs, release links and checksums retained. Screenshot evidence is private (see below). |
| 02 Theme contrast | **Implemented; automated contrast verified** | System/Light/Dark preference and component colors now use one resolved CSS-variable scheme. Automated measurements cover OS light/dark × site system/light/dark, banner normal/hover text (4.5:1) and focus ring (3:1), plus forced-colors/reduced-motion state. Axe is supplementary, not certification. |
| 03 Header/navigation clipping | **Implemented; automated browser verified** | Content-driven 1080px desktop/mobile transition; four primary destinations and a “More” menu preserve the existing destination URLs. Current route/page state is exposed visually and with `aria-current`; theme control has a descriptive accessible name. Tested 760, 768, 820, 1024, 1280, 1440, small widths and 200% text sizing; keyboard and Chromium mobile emulation also pass. No physical device tested. |
| 04 Filtering destroys player | **Partial; carry to checkpoint 2** | Library cards/player nodes are now stable across filtering; an engine-neutral controlled media-element fixture verifies node identity, mocked playing/current-time state, and no released audio request. Actual audio playback, seeking, interruption, and multi-player coordination remain unverified and out of checkpoint-1 scope. |
| 05 Cue search normalization | **Implemented; automated browser verified** | Trim, NFKC/case, repeated spaces and punctuation/symbol separators are normalized for matching only. Exact display wording is unchanged. Clear and no-result states, inner-power/Strong-Quick distinction, directory/library/reference search, and Back-state behavior have regressions. |
| 06 Mobile Quick Reference descriptions/audio status | **Deferred to checkpoint 4** | Existing responsive information omission remains; do not silently remove information. |
| 07 Semantic device checklists | **Deferred to checkpoint 4** | Audit evidence describes flattened checklist markup; preserve source wording and correct semantic rendering in its focused checkpoint. |
| 08 Canonical instruction/availability discrepancies | **Blocked on per-item owner approval; not implemented** | The audit attachment does not authorize canonical instruction changes. Brain Flow and other instruction edits require explicit approval under the canonical source process. Inventory-derived availability can be separately addressed later without rewriting narration. |
| 09 Homepage/catalog length | **Deferred to checkpoint 3** | No broad homepage redesign in checkpoint 1. |
| 10 Function-page listening placement | **Deferred to checkpoint 3** | Detailed page hierarchy remains unchanged. |
| 11 Duplicate function summaries | **Deferred to checkpoint 3** | Canonical descriptions unchanged. |
| 12 Implementation terminology | **Deferred to checkpoint 3** | Technical content has not been reorganized. |
| 13 Download metadata/filename guidance | **Partially addressed; remaining simplification deferred to checkpoint 3** | Downloads directory gives prominent format actions and places release/checksum details in disclosure; function-page filename/detail presentation is otherwise unchanged. No asset URL/bytes changed. |
| 14 Consolidated browse paths | **Deferred to checkpoint 3** | Existing paths remain available; no catalog consolidation beyond checkpoint-1 header labels/layout. |
| 15 Directory filter density | **Deferred to checkpoint 3** | Existing filters remain, with normalized search/clear behavior from finding 05. |
| 16 Alignment/type system | **Partially addressed for header/Downloads; broad system deferred** | No global typography or spacing redesign. |
| 17 Focus/theme semantics | **Implemented for shared theme control; other controls verified** | Theme control names its selected preference and next action without contradictory pressed state. Focus colors are theme variables; keyboard/forced-color behavior covered in browser tests. |
| 18 Screen-reader context/status | **Partially addressed; further review deferred** | Session/format context added to catalog checkboxes/download links and Downloads actions; current-page state, clear/no-results and result messages improved. Full assistive-technology testing remains for checkpoint 5. |
| 19 Transcript reader | **Deferred to checkpoint 4** | Existing collapsed transcript behavior retained; no new scrolling/search UI. |
| 20 Onboarding/listening repetition | **Deferred to checkpoint 4** | No editorial copy changed. |
| 21 Relationships presentation | **Deferred to checkpoint 3** | Relationship records and wording untouched. |
| 22 About introduction | **Deferred to checkpoint 4** | No About content changes. |
| 23 Runtime catalog dependence | **Deferred to checkpoint 3** | No framework or runtime data architecture change. Existing native player approach retained. |
| 24 No-JavaScript/failure truthfulness | **Deferred to checkpoint 5** | Existing fail-closed publication tests are retained; no broader no-JS redesign in this checkpoint. |
| 25 Canonical domain/legacy routes | **Deferred to checkpoint 5; live status unknown** | No DNS, TLS, redirect, CNAME or security-setting changes. Live behavior was not inferred from local artifact tests. |
| 26 Test coverage | **Checkpoint-1 regressions added; remainder deferred to checkpoints 2–5** | New Python/JS/browser coverage targets findings 01–05 and accessible repeated download names. Full list below. Physical-device, assistive-technology, real-audio and live deployment tests remain unrun. |

## Five-checkpoint plan

1. **Restore usability (this draft):** findings 01, 02, 03, 05; contextual format names from 18; stable DOM during filtering only as a preliminary safeguard for 04. Validate and open a draft PR for independent review; stop before merge/deploy.
2. **Protect listening:** finish 04 with actual public-audio playback/seeking in supported browsers, coordinate players, direct format actions near titles, and playback/error messaging. Use public released audio only in this separately authorized stage; do not claim this checkpoint-1 fixture verified audio.
3. **Consolidate experience:** findings 09–16 as applicable, 21, 23; preserve static pages, stable routes, source IDs and audio-release integrity.
4. **Improve reference material:** findings 06, 07, 19, 20, 22; assess finding 08 only after separate explicit canonical-content approval. No transcript/function wording edits by inference.
5. **Deployment and quality:** findings 24–26 and 25 live routing/canonical checks; exact-head CI, no-JS/network failures, performance, real Android Chrome/iPhone Safari, keyboard and assistive technology. No DNS/security mutation without explicit authorization.

## Checkpoint-1 validation/evidence

- Source inputs: public guide export from exact source commit `704440da8e0379cee8dfd332203bc0001c0a5f27` (58 functions); previously verified catalog SHA-256 `d05349671e0b1d054db8133b891217cfc2f0fca8bd70765609cb0d3d3fea7807` (schema 3; 59 sessions, 118 assets). No private audio bytes were accessed.
- Deterministic build and `scripts/validate_site.py`: **PASS**; 58 functions, 59 sessions, 118 assets, 200 files, 59 edition-matched TXT and 59 VTT transcripts. Audio bytes, URLs, manifests, tags, artwork and transcript texts were not modified.
- Focused Python: `scripts/test_build_public_site.py` **24 passed, 7 subtests passed**. Focused JavaScript: catalog **22 assertions passed**; docs UI **13 assertions passed**; JS syntax and `git diff --check` **PASS**.
- Browser: Chromium **20/20 passed**; Firefox **19 passed, 1 Chromium-only mobile emulation test skipped**; WebKit **19 passed, 1 Chromium-only mobile emulation test skipped**. Covered responsive action geometry, contrast/hover/focus, keyboard navigation/current-page state, forced-colors/reduced-motion, cue search/clear/no-results and controlled player DOM continuity. Axe checks are not an accessibility certification.
- Browser guard: occupied-port safety regression **PASS**. The first guard invocation used the absent default `verified-site` and returned 404; rerun against the temporary generated site passed without terminating any pre-existing listener.
- Representative Chromium browser screenshots (not uploaded; emulator/render only):
  - `/tmp/opencode/website-ux-checkpoint1-20261113/screenshots/checkpoint1-downloads-390.png`
  - `/tmp/opencode/website-ux-checkpoint1-20261113/screenshots/checkpoint1-downloads-1440.png`
- Not run: physical phones/tablets, native Safari outside Playwright WebKit, actual listening/seeking, VoiceOver/TalkBack, live public site/DNS/TLS/redirect behavior, CI on the eventual commit, merge or deployment. The source repository and private function-page audit deliverables are untouched. The separately queued Inner Power public-reference cleanup is excluded.
