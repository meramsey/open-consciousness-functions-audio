"""Tests for the pinned, fail-closed documentation site build."""

import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_public_site import (
    _asset_specification,
    _catalog_sessions,
    _inline,
    _quick_reference,
    _recommended_settings,
    digest,
    fetch_transcript,
    validate_guide_export,
)


class PublicSiteBuildTests(unittest.TestCase):
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

    def test_recommended_settings_include_loudness_and_speed_controls(self):
        content = _recommended_settings("a" * 40)
        self.assertIn("automatic loudness normalization", content)
        self.assertIn("normal playback speed (1.0x)", content)

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
