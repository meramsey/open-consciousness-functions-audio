# Website UX/accessibility audit progress

**Audit:** `OCF_Website_UX_Accessibility_Audit_2026-11-13..txt` (362 lines), supplied for implementation on 2026-11-13. The supervisor confirms the companion evidence ZIP was supplied and independently inspected: Library reference `libfile_fde3f_a72e6671c7ac8191a3e049bfb956e921_0ac91c1086208191b42021296d42efb8` (corrected underscore delimiter), SHA-256 `42b0d8ab0e80c96df1f7adb471ae5ac5fa92a395dcfc29e4bc73554b292d8fbc`. The ZIP contains nine screenshots and four JSON baseline files about the local artifact. This session did not materialize/view the images. The evidence is local Chromium rendering, not deployed-site, physical-device, native-Safari, or real-audio proof.

**Audited inputs:** audio main now `655e23b81f186f0267ae2a5da19d2d7f230b77a1` (PR16 checkpoint 1 merged; merge is not deployment proof); original audit deployment `09293ca7e5003f13e959fcdc39e57acb091c7c98`; source main/pin `704440da8e0379cee8dfd332203bc0001c0a5f27`.

**Checkpoint 1:** Draft PR [#16](https://github.com/ocfproject-org/open-consciousness-functions-audio/pull/16) merged at `655e23b81f186f0267ae2a5da19d2d7f230b77a1`. No deployment or live-domain verification is implied.

### Independent-review correction packet

Continued the same PR16 worktree from exact clean head `4a886869f872f4ae816b04e675ae3155a8b2c6f0`; this is a distinct scoped repair, not replay of checkpoint 1.

- System theme now supplies an opaque `--card` default and an OS-dark System override. Explicit Light/Dark and print values remain authoritative. Browser assertions compare computed card/menu surfaces against the resolved variable and check open-menu text contrast across OS light/dark × site system/light/dark.
- Filtered playback stays pinned when a currently playing item stops, pauses or ends. Status distinguishes playback, pause time and completion; the pin survives subsequent filters, keeps focused controls accessible, and explicit Clear filters removes the pins. Cross-browser tests use a generated three-second silent WAV data URI and a keyboard-operable test-only play/pause control. They verify the actual DOM node, seek/current-time continuity, playing/paused/ended transitions, focus, resume and replay. This synthetic fixture is not released audio or physical-device evidence.
- Full local browser results for this correction: Chromium **20 passed**; Firefox **19 passed, 1 Chromium-only mobile-emulation skip**; WebKit **19 passed, 1 Chromium-only mobile-emulation skip**. Build, site validation and focused Python/JS tests passed as recorded below.
- PR16 correction head `e25991c9b250dc1bbb07f15d415747e642384105` passed all six CI matrix jobs in https://github.com/ocfproject-org/open-consciousness-functions-audio/actions/runs/43489377349. GitHub annotations noted pinned-action Node.js 20 deprecation and hosted macOS runner queue capacity; no CI test failures.

## Finding ledger (all 26)

| # | Status | Evidence / boundary |
|---|---|---|
| 01 Mobile Downloads columns | **Implemented; automated browser verified** | Replaced the six-column Downloads table with responsive session cards and separate MP3/FLAC links. Chromium, Firefox and WebKit checked all cards/actions at 320, 375, 390, 768 and 1440 CSS px; direct catalog URLs, release links and checksums retained. Screenshot evidence is private (see below). |
| 02 Theme contrast | **Implemented; automated contrast verified** | System/Light/Dark preference and component colors now use one resolved CSS-variable scheme. Checkpoint-1 review found System-mode `--card` was missing, leaving cards and More menus transparent; System card surface and open-menu contrast are now tested in OS light/dark × site system/light/dark, alongside banner normal/hover text (4.5:1), focus ring (3:1), forced-colors and reduced-motion. Axe is supplementary, not certification. |
| 03 Header/navigation clipping | **Implemented; automated browser verified** | Content-driven 1080px desktop/mobile transition; four primary destinations and a “More” menu preserve the existing destination URLs. Current route/page state is exposed visually and with `aria-current`; theme control has a descriptive accessible name. Tested 760, 768, 820, 1024, 1280, 1440, small widths and 200% text sizing; keyboard and Chromium mobile emulation also pass. No physical device tested. |
| 04 Filtering destroys player | **Implemented with explicit WebKit limitation** | Stable player node/position and focused controls survive filtering; Back restores the filter and a paused position without autoplay. Nonmatching paused/ended media stay accessible, and starting one player pauses another. Exact catalog Relax MP3 played/paused/sought/resumed in Chromium and Firefox using capped byte ranges. WebKit received capped HTTP 206 ranges but reported `NETWORK_NO_SOURCE`; accessible playback-error and direct-download fallback work. No human listening or physical-device behavior is claimed. |
| 05 Cue search normalization | **Implemented; automated browser verified** | Trim, NFKC/case, repeated spaces and punctuation/symbol separators are normalized for matching only. Exact display wording is unchanged. Clear and no-result states, inner-power/Strong-Quick distinction, directory/library/reference search, and Back-state behavior have regressions. |
| 06 Mobile Quick Reference descriptions/audio status | **Deferred to checkpoint 4** | Existing responsive information omission remains; do not silently remove information. |
| 07 Semantic device checklists | **Deferred to checkpoint 4** | Audit evidence describes flattened checklist markup; preserve source wording and correct semantic rendering in its focused checkpoint. |
| 08 Canonical instruction/availability discrepancies | **Blocked on per-item owner approval; not implemented** | The audit attachment does not authorize canonical instruction changes. Brain Flow and other instruction edits require explicit approval under the canonical source process. Inventory-derived availability can be separately addressed later without rewriting narration. |
| 09 Homepage/catalog length | **Deferred to checkpoint 3** | No broad homepage redesign in checkpoint 1. |
| 10 Function-page listening placement | **Partially implemented; broader reorganization deferred to checkpoint 3** | Near-title Listen anchors target each published edition player and direct MP3/FLAC links preserve verified catalog URLs and edition context. Broader page order/provenance simplification remains deferred. |
| 11 Duplicate function summaries | **Deferred to checkpoint 3** | Canonical descriptions unchanged. |
| 12 Implementation terminology | **Deferred to checkpoint 3** | Technical content has not been reorganized. |
| 13 Download metadata/filename guidance | **Partially addressed; remaining simplification deferred to checkpoint 3** | Downloads directory and new function-title actions expose direct MP3/FLAC choices; existing function-page filename/checksum details otherwise remain. No asset URL/bytes changed. |
| 14 Consolidated browse paths | **Deferred to checkpoint 3** | Existing paths remain available; no catalog consolidation beyond checkpoint-1 header labels/layout. |
| 15 Directory filter density | **Deferred to checkpoint 3** | Existing filters remain, with normalized search/clear behavior from finding 05. |
| 16 Alignment/type system | **Partially addressed for header/Downloads; broad system deferred** | No global typography or spacing redesign. |
| 17 Focus/theme semantics | **Implemented for shared theme control; other controls verified** | Theme control names its selected preference and next action without contradictory pressed state. Focus colors are theme variables; keyboard/forced-color behavior covered in browser tests. |
| 18 Screen-reader context/status | **Partially addressed; further review deferred** | Session/format context, polite loading/playing/paused/ended/error messages, title-level actions, and review/removal of selected filtered-out files are implemented. Full assistive-technology testing remains for checkpoint 5. |
| 19 Transcript reader | **Deferred to checkpoint 4** | Existing collapsed transcript behavior retained; no new scrolling/search UI. |
| 20 Onboarding/listening repetition | **Deferred to checkpoint 4** | No editorial copy changed. |
| 21 Relationships presentation | **Deferred to checkpoint 3** | Relationship records and wording untouched. |
| 22 About introduction | **Deferred to checkpoint 4** | No About content changes. |
| 23 Runtime catalog dependence | **Deferred to checkpoint 3** | No framework or runtime data architecture change. Existing native player approach retained. |
| 24 No-JavaScript/failure truthfulness | **Deferred to checkpoint 5** | Existing fail-closed publication tests are retained; no broader no-JS redesign in this checkpoint. |
| 25 Canonical domain/legacy routes | **Deferred to checkpoint 5; live status unknown** | No DNS, TLS, redirect, CNAME or security-setting changes. Live behavior was not inferred from local artifact tests. |
| 26 Test coverage | **Checkpoint-1 and checkpoint-2 regressions added; remainder deferred to checkpoints 3–5** | New tests cover direct function actions, player coordination, filter/Back state, selected-file review, capped released-media playback and unavailable-media fallback. Physical-device, human listening, assistive-technology and live deployment tests remain unrun. |

## Checkpoint 2: protect listening

**Status:** Draft PR [#17](https://github.com/ocfproject-org/open-consciousness-functions-audio/pull/17) is open for independent review on `fix/website-ux-protect-listening-20261113`, based on merged audio main `655e23b81f186f0267ae2a5da19d2d7f230b77a1`. The implementation commit `972949da5e6af7fabb6ab4ecc57dbb2c01bbcc6f` passed all six OS/Python matrix jobs in https://github.com/ocfproject-org/open-consciousness-functions-audio/actions/runs/43507430396. A subsequent progress-ledger-only commit records this evidence; exact CI for the final PR head is verified before stopping. No merge or deployment in this checkpoint.

- Intended scope: single active player per page; stable player/state across filters and Back; accessible loading/playing/paused/ended/error status; per-edition title actions for Listen/MP3/FLAC; review/remove/clear selected files, including those hidden by filters.
- Deterministic build/site validation: **PASS**; 58 functions, 59 sessions, 118 assets, 200 files, 59 TXT and 59 VTT sidecars. Build receipt retained catalog SHA-256 `db878436e6e15fc64bd9f4b96a398d2612fbc78cf34033ff11f6a526ce137eac`, release manifest SHA-256 `48cb39bcc3dfd7f7e211b3093cd927c3a790cd9ad28d6b47faad956014c85c14`, tag `audio-0.1.0-a6-20261111`; source remains `704440da8e0379cee8dfd332203bc0001c0a5f27`.
- Focused tests: Python **25 passed, 7 subtests passed**; offline Python unittest discovery **188 passed**; catalog JavaScript **22 assertions passed**; docs JavaScript **13 assertions passed**; syntax/diff and occupied-port guard **PASS**.
- Full local default browser suite: Chromium **24 passed, 1 opt-in real-media test skipped**; Firefox **23 passed, 2 skipped** (real-media opt-in and Chromium-only mobile emulation); WebKit **23 passed, 2 skipped**. Explicit real public MP3 probe: Chromium **16 HTTP 206 ranges / 4,194,304 bytes**, Firefox **11 / 2,883,584 bytes**; each range <=262,144 bytes and per-browser aggregate <=8 MiB. Both engines verified metadata/decode, playback, pause, seek, resume, continued time, and pause using the unchanged catalog URL. WebKit returned two capped 206 ranges / **263,590 bytes** but remained `NETWORK_NO_SOURCE`; its accessible failure message and direct download link were verified. Response type observed was `application/octet-stream`; the underlying WebKit source-selection cause is not established.
- These are technical browser probes only. No human listening, listening approval, physical phone/tablet, or native Safari proof is claimed.
- Existing safety boundary: no source repository, audio build, voice/conditioning asset, release tag/manifest, catalog content, artwork, transcript, DNS, security, proxy, or queued Inner Power change is part of this checkpoint.

## Five-checkpoint plan

1. **Restore usability (merged in PR16):** findings 01, 02, 03, 05 and contextual format names from 18. Merge did not imply deployment.
2. **Protect listening (this draft):** findings 04 and applicable parts of 10, 18 and 26. Public-media playback was verified in Chromium/Firefox; WebKit’s nonselection result and accessible fallback are recorded. No listening/device approval is inferred.
3. **Consolidate experience:** findings 09–16 as applicable, 21, 23; preserve static pages, stable routes, source IDs and audio-release integrity.
4. **Improve reference material:** findings 06, 07, 19, 20, 22; assess finding 08 only after separate explicit canonical-content approval. No transcript/function wording edits by inference.
5. **Deployment and quality:** findings 24–26 and 25 live routing/canonical checks; exact-head CI, no-JS/network failures, performance, real Android Chrome/iPhone Safari, keyboard and assistive technology. No DNS/security mutation without explicit authorization.

## Checkpoint-1 validation/evidence

- Source inputs: public guide export from exact source commit `704440da8e0379cee8dfd332203bc0001c0a5f27` (58 functions); previously verified catalog SHA-256 `d05349671e0b1d054db8133b891217cfc2f0fca8bd70765609cb0d3d3fea7807` (schema 3; 59 sessions, 118 assets). No private audio bytes were accessed.
- Deterministic build and `scripts/validate_site.py`: **PASS**; 58 functions, 59 sessions, 118 assets, 200 files, 59 edition-matched TXT and 59 VTT transcripts. Audio bytes, URLs, manifests, tags, artwork and transcript texts were not modified.
- Focused Python: `scripts/test_build_public_site.py` **24 passed, 7 subtests passed**. Focused JavaScript: catalog **22 assertions passed**; docs UI **13 assertions passed**; JS syntax and `git diff --check` **PASS**.
- Browser: Chromium **20/20 passed**; Firefox **19 passed, 1 Chromium-only mobile emulation test skipped**; WebKit **19 passed, 1 Chromium-only mobile emulation test skipped**. Covered responsive action geometry, contrast/hover/focus, keyboard navigation/current-page state, forced-colors/reduced-motion, cue search/clear/no-results and controlled player DOM continuity. Axe checks are not an accessibility certification.
- Independent-review correction: System-mode card backgrounds and filtered-player pause/end/focus continuity were verified after PR review using automated cross-browser tests; the player test uses only its declared synthetic silent-WAV fixture. It is not evidence from released audio.
- Browser guard: occupied-port safety regression **PASS**. The first guard invocation used the absent default `verified-site` and returned 404; rerun against the temporary generated site passed without terminating any pre-existing listener.
- Representative Chromium browser screenshots (not uploaded; emulator/render only):
  - `/tmp/opencode/website-ux-checkpoint1-20261113/screenshots/checkpoint1-downloads-390.png`
  - `/tmp/opencode/website-ux-checkpoint1-20261113/screenshots/checkpoint1-downloads-1440.png`
- At checkpoint 1, not run: physical phones/tablets, native Safari outside Playwright WebKit, released-audio probes, VoiceOver/TalkBack, live public site/DNS/TLS/redirect behavior, merge or deployment. Checkpoint 2 adds bounded Chromium/Firefox released-audio probes; it still does not establish human listening, physical-device or native Safari behavior. The source repository and private function-page audit deliverables are untouched. The separately queued Inner Power public-reference cleanup is excluded.
