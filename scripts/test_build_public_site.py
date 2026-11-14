"""Tests for the pinned, fail-closed documentation site build."""

import copy
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_public_site import (
    _asset_specification,
    _catalog_sessions,
    _discovery_section,
    _downloads_page,
    _function_audio_actions,
    _function_page,
    _functions_index,
    _home_page,
    _historical_names_page,
    _inline,
    _historical_lookup_rows,
    _public_description,
    _public_historical_name,
    _quick_reference,
    _relationships_page,
    _recommended_settings,
    _shell,
    _request_public_asset,
    _suggested_download_filename,
    _validate_suggested_download_filenames,
    _spoken_cue_references,
    digest,
    fetch_transcript,
    render_markdown,
    validate_guide_export,
)


class PublicSiteBuildTests(unittest.TestCase):
    def test_function_title_actions_link_to_edition_player_and_direct_formats(self):
        rows = []
        for title, asset_suffix, edition in (
            ("Relax", "a" * 64, "0.1.0"),
            ("Relax", "b" * 64, "0.2.0"),
        ):
            rows.append({
                "session": {
                    "asset_id": f"asset-{asset_suffix}",
                    "title": title,
                    "locale": "en-US",
                    "voice_name": "Example Voice",
                    "edition": edition,
                },
                "group": {"title": title},
                "release": {"version": edition},
                "audio_assets": [
                    {"format": "mp3", "download_url": f"https://github.com/example/{edition}/relax.mp3"},
                    {"format": "flac", "download_url": f"https://github.com/example/{edition}/relax.flac"},
                ],
            })

        html = _function_audio_actions(rows)

        self.assertEqual(html.count('class="function-audio-action-group"'), 2)
        for asset_suffix, edition in (("a" * 64, "0.1.0"), ("b" * 64, "0.2.0")):
            self.assertIn(f'href="#session-asset-{asset_suffix}"', html)
            self.assertIn(f'aria-label="Listen to Relax, en-US, edition {edition}"', html)
            for fmt in ("mp3", "flac"):
                self.assertIn(f'href="https://github.com/example/{edition}/relax.{fmt}"', html)
                self.assertIn(f'aria-label="Download {fmt.upper()} for Relax, en-US, edition {edition}"', html)
        self.assertEqual(_function_audio_actions([]), "")

    def test_download_directory_cards_are_responsive_and_contextual(self):
        groups = []
        for function_id, title in (("OCF-FND-004", "Relax"), ("OCF-BOD-001", "Brain Flow")):
            assets = [
                {
                    "asset_id": f"{function_id}-{fmt}",
                    "format": fmt,
                    "filename": f"{function_id}.{fmt}",
                    "encoding": encoding,
                    "download_url": f"https://github.com/example/{function_id}.{fmt}",
                    "sha256": "a" * 64 if fmt == "mp3" else "b" * 64,
                    "size_bytes": 1_000_000,
                    "duration_seconds": 120,
                }
                for fmt, encoding in (("mp3", "MP3 320 kbps"), ("flac", "FLAC lossless"))
            ]
            groups.append({
                "function_id": function_id,
                "title": title,
                "sessions": [{
                    "title": title,
                    "locale": "en-US",
                    "voice_name": "Example Voice",
                    "edition": "0.1.0",
                    "assets": assets,
                }],
            })
        page = _downloads_page({"releases": [{
            "version": "0.1.0",
            "tag": "audio-test-release",
            "release_url": "https://github.com/example/release",
            "functions": groups,
            "preparations": [],
        }]}, [])

        self.assertEqual(page.count('class="download-card"'), 2)
        self.assertNotIn("reference-table", page)
        for title, function_id in (("Relax", "OCF-FND-004"), ("Brain Flow", "OCF-BOD-001")):
            for fmt in ("MP3", "FLAC"):
                self.assertIn(
                    f'aria-label="Download {fmt} for {title}, en-US, Example Voice, edition 0.1.0"',
                    page,
                )
                self.assertIn(f'href="https://github.com/example/{function_id}.{fmt.lower()}"', page)
            self.assertIn(f"{function_id}.mp3", page)
            self.assertIn(f"{function_id}.flac", page)
        self.assertIn("audio-test-release", page)
        self.assertIn("320 kbps", page)
        self.assertNotIn("MP3 · MP3", page)
        self.assertNotIn("FLAC · flac", page)

    def test_shell_navigation_keeps_routes_and_marks_current_location(self):
        page = _shell("Function list", "<p>Directory</p>", "functions", "a" * 40)
        for href in (
            "../start/", "../functions/", "../quick-reference/", "../listening/",
            "../historical-names/", "../relationships/", "../functions/#library", "../downloads/", "../about/",
        ):
            self.assertIn(f'href="{href}"', page)
        self.assertIn('<a href="../functions/" aria-current="page">Browse &amp; Listen</a>', page)
        detail = _shell("Function", "<p>Detail</p>", "functions/OCF-BOD-001", "a" * 40)
        self.assertIn('<a href="../../functions/" aria-current="location">Browse &amp; Listen</a>', detail)
        self.assertIn('<details class="more-menu">', page)

    def test_download_directory_cards_preserve_each_format_with_contextual_names(self):
        sessions = []
        for function_id, title in (
            ("OCF-FND-004", "Relax"),
            ("OCF-BOD-001", "Brain Flow"),
        ):
            assets = [
                {
                    "asset_id": f"{function_id}-{fmt}",
                    "format": fmt,
                    "filename": f"{function_id}.{fmt}",
                    "encoding": encoding,
                    "download_url": f"https://github.com/example/{function_id}.{fmt}",
                    "sha256": "a" * 64 if fmt == "mp3" else "b" * 64,
                    "size_bytes": 1_000_000,
                    "duration_seconds": 120,
                }
                for fmt, encoding in (("mp3", "MP3 320 kbps"), ("flac", "FLAC lossless"))
            ]
            sessions.append({
                "function_id": function_id,
                "title": title,
                "sessions": [{
                    "title": title,
                    "locale": "en-US",
                    "voice_name": "Example Voice",
                    "edition": "0.1.0",
                    "assets": assets,
                }],
            })
        page = _downloads_page({"releases": [{
            "version": "0.1.0",
            "tag": "audio-test-release",
            "release_url": "https://github.com/example/release",
            "functions": sessions,
            "preparations": [],
        }]}, [])

        self.assertEqual(page.count('class="download-card"'), 2)
        self.assertNotIn("reference-table", page)
        for title, function_id in (("Relax", "OCF-FND-004"), ("Brain Flow", "OCF-BOD-001")):
            for fmt in ("MP3", "FLAC"):
                self.assertIn(f'Download {fmt} for {title}, en-US, Example Voice, edition 0.1.0', page)
                self.assertIn(f'href="https://github.com/example/{function_id}.{fmt.lower()}"', page)
            self.assertIn(f"{function_id}.mp3", page)
            self.assertIn(f"{function_id}.flac", page)
        self.assertIn("audio-test-release", page)

    def test_render_markdown_keeps_wrapped_ordered_steps_semantic(self):
        rendered = render_markdown(
            "## Suggested way to explore\n\n"
            "1. [Relax](../functions/OCF-FND-004/) — gentle introduction to\n"
            "   guided relaxation and listening.\n"
            "2. [Focus](../functions/OCF-FND-002/) — attention-oriented\n"
            "   practice.\n"
            "3. [Think Fast](../functions/OCF-COG-007/) — thinking-oriented\n"
            "   practice."
        )
        self.assertEqual(rendered.count("<ol>"), 1)
        self.assertEqual(rendered.count("<li>"), 3)
        self.assertIn("guided relaxation and listening.", rendered)
        self.assertIn("</li><li>", rendered)
        self.assertNotIn("<p>1. ", rendered)

    def test_historical_lookup_projection_uses_only_exact_source_names(self):
        import yaml

        function = {
            "function_id": "OCF-SEN-003",
            "title": {"text": "Smell"},
            "commands": [{"display_cue": {"text": "PLUS-SMELL MORE"}}],
            "canonical_resource": "locales/en-US/OCF-SEN-003-Smell.yaml",
        }
        record = {
            "locale": "en-US",
            "function_id": "OCF-SEN-003",
            "record_metadata": {
                "historical_lookup": [
                    {"text": "Sensory: Smell", "kind": "former-title", "decision": "test"},
                    {"text": "PLUS-SMELL MORE", "kind": "former-primary", "decision": "test"},
                ]
            },
        }
        raw_resource = yaml.safe_dump(record, sort_keys=True).encode()
        function["canonical_resource_sha256"] = hashlib.sha256(raw_resource).hexdigest()
        reference = (
            "# Historical lookup\n\n## Migrated vocabulary\n\n"
            "- OCF-SEN-003 → Smell / `PLUS-SMELL MORE`; "
            "historical matches: Sensory: Smell; PLUS-SMELL MORE.\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resource = root / function["canonical_resource"]
            resource.parent.mkdir(parents=True)
            resource.write_bytes(raw_resource)
            rows = _historical_lookup_rows(reference, [function], root)
            self.assertEqual(
                rows,
                [{
                    "function_id": "OCF-SEN-003",
                    "title": "Smell",
                    "names": [
                        {
                            "text": "Sensory: Smell",
                            "kind": "former-title",
                            "label": "Former title",
                            "also_current": False,
                        },
                        {
                            "text": "PLUS-SMELL MORE",
                            "kind": "former-primary",
                            "label": "Former primary cue · Also current",
                            "also_current": True,
                        },
                    ],
                }],
            )
            page = _historical_names_page(
                rows,
                [function],
                "a" * 40,
                historical_reference_sha256="b" * 64,
            )
            self.assertIn('data-historical-kind="former-title"', page)
            self.assertIn("Former title", page)
            self.assertIn('data-also-current="true"', page)
            self.assertIn("Former primary cue · Also current", page)
            self.assertIn("mappings for 1 functions and 2 historical strings", page)
            self.assertIn("Absence from this reference does not establish", page)
        wrong_title = reference.replace("→ Smell /", "→ Taste /")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resource = root / function["canonical_resource"]
            resource.parent.mkdir(parents=True)
            resource.write_bytes(raw_resource)
            with self.assertRaisesRegex(ValueError, "title does not match"):
                _historical_lookup_rows(wrong_title, [function], root)
        unknown_target = reference.replace("OCF-SEN-003", "OCF-SEN-004")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resource = root / function["canonical_resource"]
            resource.parent.mkdir(parents=True)
            resource.write_bytes(raw_resource)
            with self.assertRaisesRegex(ValueError, "unknown function"):
                _historical_lookup_rows(unknown_target, [function], root)

    def test_historical_overlap_is_exact_normalized_and_same_function_only(self):
        import yaml

        function = {
            "function_id": "OCF-PRF-002",
            "title": {"text": "Inner Power"},
            "commands": [{
                "display_cue": {"text": "PLUS-INNER POWER"},
                "spoken_cue": "Plus Inner Power",
            }],
            "canonical_resource": "locales/en-US/OCF-PRF-002-Inner-Power.yaml",
        }
        record = {
            "function_id": function["function_id"],
            "record_metadata": {
                "historical_lookup": [
                    {"text": "PLUS-STRONG", "kind": "former-primary", "decision": "test"},
                    {"text": "pLuS   inner power", "kind": "former-teaching", "decision": "test"},
                ]
            },
        }
        raw_resource = yaml.safe_dump(record, sort_keys=True).encode()
        function["canonical_resource_sha256"] = hashlib.sha256(raw_resource).hexdigest()
        reference = (
            "# Historical lookup\n\n## Migrated vocabulary\n\n"
            "- OCF-PRF-002 → Inner Power / `PLUS-INNER POWER`; "
            "historical matches: PLUS-STRONG; pLuS   inner power.\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resource = root / function["canonical_resource"]
            resource.parent.mkdir(parents=True)
            resource.write_bytes(raw_resource)
            rows = _historical_lookup_rows(reference, [function], root)
        self.assertEqual(
            [(name["text"], name["also_current"]) for name in rows[0]["names"]],
            [("pLuS   inner power", True)],
        )

    def test_public_history_exclusion_is_exact_and_function_scoped(self):
        self.assertFalse(_public_historical_name(
            "OCF-PRF-002", {"kind": "former-primary", "text": "PLUS-STRONG"}
        ))
        for function_id, kind, text in (
            ("OCF-PRF-006", "former-primary", "PLUS-STRONG"),
            ("OCF-PRF-002", "former-teaching", "PLUS-STRONG"),
            ("OCF-PRF-002", "former-primary", "PLUS-STRONG QUICK"),
            ("OCF-PRF-002", "former-primary", "PLUS-STRONG-QUICK"),
            ("OCF-PRF-002", "former-primary", "PLUS-INNER POWER"),
        ):
            with self.subTest(function_id=function_id, kind=kind, text=text):
                self.assertTrue(_public_historical_name(
                    function_id, {"kind": kind, "text": text}
                ))

    def test_relationship_directory_preserves_direction_and_reason_without_graph_claims(self):
        functions = [
            {
                "function_id": "OCF-FND-004", "title": {"text": "Relax"},
                "primary_category": "foundation", "related_functions": [{
                    "function_id": "OCF-FND-002", "title": "Focus",
                    "relationship_type": "complementary", "description": "An approved reason.",
                }],
            },
            {
                "function_id": "OCF-FND-002", "title": {"text": "Focus"},
                "primary_category": "foundation", "related_functions": [],
            },
        ]
        page = _relationships_page(functions)
        self.assertEqual(page.count('class="relationship-card"'), 1)
        self.assertIn('Relax</a> <span aria-hidden="true">→</span> <a href="../functions/OCF-FND-002/">Focus', page)
        self.assertIn("An approved reason.", page)
        self.assertIn("one-way", page)
        self.assertNotIn("OCF-FND-002</a> <span aria-hidden", page)
        self.assertNotIn("complementary", page)

    def test_home_is_a_short_entry_page_and_browse_has_only_real_filters(self):
        categories = [{"id": "focus", "label": "focus"}]
        functions = [{
            "function_id": "OCF-FND-002", "slug": "focus", "title": {"text": "Focus"},
            "description": {"text": "A short approved description."}, "categories": categories,
            "primary_category": "focus", "commands": [], "tags": [], "common_uses": [],
        }]
        self.assertIn("official Human Plus preparation track", _home_page(
            functions, {"releases": [{"functions": [], "preparations": []}]}, "a" * 40
        ))
        self.assertIn('id="library"', _home_page(
            functions, {"releases": [{"functions": [], "preparations": []}]}, "a" * 40
        ))
        page = _functions_index(functions, {"OCF-FND-002": []}, [])
        self.assertIn("Browse &amp; Listen", page)
        self.assertIn('id="category-filter"', page)
        self.assertNotIn('id="language-filter"', page)
        self.assertNotIn('id="voice-filter"', page)

    def test_draft_discovery_and_pending_procedure_are_hidden_without_mutating_metadata(self):
        function = {
            "function_id": "OCF-EXP-006",
            "title": {"text": "Intuition", "status": "reviewed"},
            "description": {"text": "A documented purpose.", "status": "reviewed"},
            "categories": [],
            "tags": [
                {"text": "draft-tag", "status": "draft"},
                {"text": "machine-tag", "status": "machine"},
                {"text": "canonical-tag", "status": "canonical"},
            ],
            "common_uses": [
                {"text": "draft-use", "status": "draft"},
                {"text": "machine-use", "status": "machine"},
                {"text": "reviewed-use", "status": "reviewed"},
            ],
            "commands": [{
                "command_id": "OCF-CMD-EXP-006-PRIMARY",
                "designation": "primary",
                "spoken_cue": "Plus Intuition",
                "procedure_status": "review-pending",
                "procedure_steps": [
                    {"operation": "draft-only", "instruction": "Unapproved steps stay hidden."}
                ],
                "usage": None,
                "explanation": None,
                "effect_scope": None,
            }],
            "lifecycle": {
                "scopes": [],
                "activation": "manual",
                "persistence": "temporary",
                "trigger_conditions": [],
                "release_command": None,
            },
            "safety_notes": [],
            "related_functions": [],
            "canonical_resource": "locales/en-US/OCF-EXP-006-Intuition.yaml",
        }
        original = copy.deepcopy(function)
        html = _function_page(function, [], {}, "a" * 40)
        tags_html = _discovery_section("Tags", function["tags"])
        self.assertIn("canonical-tag", tags_html)
        self.assertNotIn("draft-tag", tags_html)
        self.assertNotIn("machine-tag", tags_html)
        self.assertNotIn("Draft metadata", html)
        self.assertNotIn("draft-tag", html)
        self.assertNotIn("machine-tag", html)
        self.assertNotIn("draft-use", html)
        self.assertNotIn("machine-use", html)
        self.assertIn("canonical-tag", html)
        self.assertIn("reviewed-use", html)
        self.assertNotIn("Unapproved steps stay hidden.", html)
        self.assertIn("No activation steps are published for this command.", html)
        self.assertNotIn("review-pending", html)
        self.assertNotIn("Title: reviewed", html)
        self.assertNotIn("Description: reviewed", html)
        self.assertEqual(html.count("A documented purpose."), 1)
        self.assertNotIn("Intended purpose", html)
        self.assertIn('<details class="source-details">', html)
        self.assertEqual(function, original)

    def test_spoken_cue_reference_replaces_only_the_approved_whole_cue(self):
        commands = [
            {
                "display_cue": {"text": "PLUS-CANCEL"},
                "spoken_cue": "Plus Cancel",
            }
        ]
        usage = "Places Insulate on hold; PLUS-CANCEL ends this adjustment."
        self.assertEqual(
            _spoken_cue_references(usage, commands),
            "Places Insulate on hold; Plus Cancel ends this adjustment.",
        )
        self.assertEqual(
            _spoken_cue_references("PLUS-CANCELLED is not PLUS-CANCEL", commands),
            "PLUS-CANCELLED is not Plus Cancel",
        )
        self.assertEqual(usage, "Places Insulate on hold; PLUS-CANCEL ends this adjustment.")

    def test_suggested_download_filename_is_descriptive_safe_and_hash_free(self):
        suggested = _suggested_download_filename(
            {"function_id": "OCF-FND-004"},
            {
                "title": "Relax / Recover",
                "locale": "en-US",
                "voice_name": "Mike: Original Voice",
                "edition": "0.1.0",
            },
            {"tag": "audio-0.1.0-release"},
            {"format": "MP3", "filename": "release-abcdef123456.mp3"},
        )
        self.assertEqual(
            suggested,
            "OCF-FND-004 - Relax - Recover - en-US - Mike- Original Voice - v0.1.0 - audio-0.1.0-release.mp3",
        )
        self.assertNotIn("abcdef123456", suggested)
        self.assertNotRegex(suggested, r'[<>:"/\\|?*\x00-\x1f]')
        with self.assertRaisesRegex(ValueError, "unsupported suggested-download extension"):
            _suggested_download_filename(
                {"function_id": "OCF-FND-004"},
                {"title": "Relax", "locale": "en-US", "voice_name": "Voice", "edition": "0.1"},
                {"tag": "release"},
                {"format": "../../mp3"},
            )

    def test_suggested_audio_filename_collision_fails_closed(self):
        row = {
            "group": {"function_id": "OCF-FND-004", "title": "Relax"},
            "session": {
                "title": "Relax",
                "locale": "en-US",
                "voice_name": "Mike",
                "edition": "0.1.0",
            },
            "release": {"tag": "audio-0.1.0"},
            "audio_assets": [
                {"asset_id": "asset-one", "format": "mp3"},
                {"asset_id": "asset-two", "format": "MP3"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "share a suggested local filename"):
            _validate_suggested_download_filenames([row])

    def test_public_description_removes_only_matching_display_cue_suffix(self):
        function = {
            "description": {
                "text": "Sleep deliberately; activation cue PLUS-SLEEP.",
            },
            "commands": [
                {"display_cue": {"text": "PLUS-SLEEP"}},
            ],
        }
        original = copy.deepcopy(function)
        self.assertEqual(_public_description(function), "Sleep deliberately")
        function["description"]["text"] = "Use PLUS-SLEEP safely."
        self.assertEqual(_public_description(function), "Use PLUS-SLEEP safely.")
        self.assertEqual(original["description"]["text"], "Sleep deliberately; activation cue PLUS-SLEEP.")

    @staticmethod
    def valid_pin():
        return {
            "schema_version": 1,
            "source_repository": "https://github.com/ocfproject-org/open-consciousness-functions",
            "source_commit": "a" * 40,
            "source_version": "0.1.0",
            "locale": "en-US",
            "exporter": "ocf.public-site-guides/1",
        }

    @staticmethod
    def valid_export(pin):
        functions = [
            {
                "function_id": f"OCF-FND-{index:03}",
                "documentation_status": "canonical-function-resource",
                "canonical_resource_sha256": "b" * 64,
                "commands": [],
                "historical_commands": [],
                "related_functions": [],
            }
            for index in range(1, 59)
        ]
        guide = {"markdown": "# Listening guide\n", "source_sha256": ""}
        guide["source_sha256"] = hashlib.sha256(guide["markdown"].encode()).hexdigest()
        document = {
            "schema_version": 1,
            "exporter": "ocf.public-site-guides/1",
            "source_repository": pin["source_repository"],
            "source_commit": pin["source_commit"],
            "locale": "en-US",
            "functions": functions,
            "listening_guide": guide,
        }
        document["build_receipt"] = {
            "function_count": 58,
            "narration_text_included": False,
            "source_evidence_paths_included": False,
            "draft_procedures_included": False,
            "relationship_proposals_included": False,
            "functions_sha256": digest(functions),
            "export_content_sha256": digest(document),
        }
        return document

    def test_markdown_escaping_blocks_html_and_unsafe_links(self):
        rendered = _inline(
            "<script>alert(1)</script> [bad](javascript:alert(1)) [good](https://example.org/a)"
        )
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn('href="javascript:', rendered)
        self.assertNotIn('href="..\\..\\outside', rendered)
        self.assertIn('href="https://example.org/a"', rendered)

    def test_transcript_requires_manifest_size_digest_and_utf8(self):
        text = b"edition-matched transcript\n"
        asset = {
            "format": "txt",
            "asset_id": "asset-" + "a" * 64,
            "size_bytes": len(text),
            "sha256": hashlib.sha256(text).hexdigest(),
        }
        self.assertEqual(fetch_transcript(asset, fetcher=lambda _: text), text)
        with self.assertRaisesRegex(ValueError, "size verification"):
            fetch_transcript(asset, fetcher=lambda _: text + b"bad")
        invalid = b"\xff"
        asset.update(size_bytes=1, sha256=hashlib.sha256(invalid).hexdigest())
        with self.assertRaisesRegex(ValueError, "valid UTF-8"):
            fetch_transcript(asset, fetcher=lambda _: invalid)

    def test_transcript_rejects_unmanifested_format(self):
        with self.assertRaisesRegex(ValueError, "only published TXT/VTT"):
            fetch_transcript({"format": "wav"}, fetcher=lambda _: b"")

    def test_public_asset_fetch_retries_transient_502_with_a_fixed_bound(self):
        url = "https://github.com/ocfproject-org/open-consciousness-functions-audio/releases/download/tag/transcript.txt"
        payload = b"approved public release companion"

        class Response(io.BytesIO):
            def geturl(self):
                return "https://release-assets.githubusercontent.com/transcript.txt"

        transient = HTTPError(url, 502, "proxy unavailable", {}, io.BytesIO())
        with (
            patch(
                "build_public_site.urllib.request.urlopen",
                side_effect=[transient, Response(payload)],
            ) as opener,
            patch("build_public_site.time.sleep") as pause,
        ):
            self.assertEqual(_request_public_asset({"download_url": url}), payload)
        self.assertEqual(opener.call_count, 2)
        pause.assert_called_once_with(0.25)

    def test_public_asset_fetch_does_not_retry_permanent_http_errors(self):
        url = "https://github.com/ocfproject-org/open-consciousness-functions-audio/releases/download/tag/transcript.txt"
        permanent = HTTPError(url, 404, "missing", {}, io.BytesIO())
        with (
            patch(
                "build_public_site.urllib.request.urlopen", side_effect=permanent
            ) as opener,
            self.assertRaises(HTTPError),
        ):
            _request_public_asset({"download_url": url})
        self.assertEqual(opener.call_count, 1)

    def test_quick_reference_marks_audio_unavailable_separately(self):
        function = {
            "function_id": "OCF-FND-001",
            "title": {"text": "Example"},
            "description": {"text": "Documented purpose."},
            "categories": [{"id": "foundation", "label": "Foundation"}],
            "primary_category": "foundation",
            "tags": [],
            "common_uses": [],
            "commands": [],
            "historical_commands": [],
        }
        unavailable = _quick_reference([function], {})
        available = _quick_reference([function], {"OCF-FND-001": [object()]})
        self.assertIn("Audio unavailable", unavailable)
        self.assertIn("Published audio available", available)

    def test_quick_reference_filter_includes_secondary_canonical_domains(self):
        function = {
            "function_id": "OCF-EXP-001",
            "title": {"text": "Imagination"},
            "description": {"text": "A documented purpose."},
            "categories": [
                {"id": "experimental", "label": "Experimental"},
                {"id": "foundation", "label": "Foundation"},
            ],
            "primary_category": "experimental",
            "tags": [],
            "common_uses": [],
            "commands": [],
            "historical_commands": [],
        }
        page = _quick_reference([function], {})
        assert 'data-category="experimental foundation"' in page

    def test_recommended_settings_include_loudness_and_speed_controls(self):
        content = _recommended_settings("a" * 40)
        self.assertIn("automatic loudness normalization", content)
        self.assertIn("normal playback speed (1.0x)", content)
        self.assertIn(
            "Stereo headphones or stereo earbuds with separate left/right playback are required for the intended binaural/channel-separated audio.",
            content,
        )
        self.assertIn(
            "Speakers, mono mixing, or a single earpiece are not equivalent delivery of that audio.",
            content,
        )
        self.assertIn("no equivalent effects are promised", content)
        self.assertLess(
            content.index("required for the intended binaural/channel-separated audio"),
            content.index("Optional processing preferences"),
        )
        self.assertLess(
            content.index("Preserve separate left/right playback"),
            content.index("Optional processing preferences"),
        )
        self.assertNotIn("when the selected edition is designed", content)

    def test_platform_guides_all_state_required_stereo_delivery_and_accessible_alternatives(self):
        required = (
            "Stereo headphones or stereo earbuds with separate left/right playback are\n"
            "  required for the intended binaural/channel-separated audio."
        )
        for platform in ("android", "ios", "linux", "macos", "windows"):
            with self.subTest(platform=platform):
                content = Path(f"docs/website/listening/{platform}.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn(required, content)
                self.assertIn(
                    "Speakers, mono\n  mixing, or a single earpiece are not equivalent delivery of that audio.",
                    content,
                )
                self.assertIn("or skip the audio", content)
                self.assertNotIn("stereo baseline is optional", content)

    def test_audio_asset_specs_include_format_rate_channels_size_and_duration(self):
        specification = _asset_specification(
            {
                "format": "mp3",
                "encoding": "MP3 320 kbps",
                "sample_rate_hz": 44100,
                "channels": 2,
                "size_bytes": 1048576,
                "duration_seconds": 125,
            }
        )
        self.assertEqual(
            specification,
            "MP3 · MP3 320 kbps · 44,100 Hz · 2 channels · 1.0 MiB · 2m 5s",
        )

    def test_guide_export_fails_closed_on_source_pin_or_receipt_drift(self):
        pin = self.valid_pin()
        document = self.valid_export(pin)
        self.assertIs(validate_guide_export(document, pin), document)
        wrong_pin = {**pin, "source_commit": "c" * 40}
        with self.assertRaisesRegex(ValueError, "source commit differs"):
            validate_guide_export(document, wrong_pin)
        tampered = copy.deepcopy(document)
        tampered["build_receipt"]["narration_text_included"] = True
        with self.assertRaisesRegex(ValueError, "narration text is forbidden"):
            validate_guide_export(tampered, pin)
        tampered = copy.deepcopy(document)
        tampered["functions"][0]["title"] = "unauthenticated text"
        with self.assertRaisesRegex(ValueError, "functions hash mismatch"):
            validate_guide_export(tampered, pin)
        for field, message in (
            ("draft_procedures_included", "draft procedure text is forbidden"),
            ("relationship_proposals_included", "draft relationship proposals are forbidden"),
        ):
            tampered = copy.deepcopy(document)
            tampered["build_receipt"][field] = True
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                validate_guide_export(tampered, pin)

    def test_release_catalog_companion_join_uses_manifest_master_hash(self):
        release = {
            "tag": "example-release",
            "functions": [
                {
                    "function_id": "OCF-FND-001",
                    "sessions": [
                        {
                            "title": "Example",
                            "assets": [
                                {
                                    "format": "mp3",
                                    "provenance": {"master_sha256": "a" * 64},
                                }
                            ],
                        }
                    ],
                }
            ],
            "preparations": [],
            "companions": [
                {
                    "asset_id": "asset-" + "b" * 64,
                    "format": "txt",
                    "provenance": {"master_sha256": "a" * 64},
                }
            ],
        }
        by_function, preparation = _catalog_sessions({"releases": [release]})
        self.assertEqual(preparation, [])
        self.assertEqual(
            by_function["OCF-FND-001"][0]["companions"]["txt"]["asset_id"],
            "asset-" + "b" * 64,
        )

    def test_unmatched_or_ambiguous_companion_fails_closed(self):
        release = {
            "tag": "example-release",
            "functions": [],
            "preparations": [],
            "companions": [
                {
                    "asset_id": "asset-" + "b" * 64,
                    "format": "txt",
                    "provenance": {"master_sha256": "c" * 64},
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "lacks a unique manifest-bound"):
            _catalog_sessions({"releases": [release]})


if __name__ == "__main__":
    unittest.main()
