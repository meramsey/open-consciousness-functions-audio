import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate_site


def empty_catalog():
    return {
        "schema_version": 1,
        "catalog_id": "ocf-audio-library",
        "project_name": "Open Consciousness Functions",
        "source_repository": "https://github.com/meramsey/open-consciousness-functions",
        "distribution_repository": "https://github.com/meramsey/open-consciousness-functions-audio",
        "releases": [],
    }


def catalog_with_assets():
    data = empty_catalog()
    data["releases"] = [
        {
            "version": "1.0.0",
            "channel": "stable",
            "date": "2026-01-01",
            "source_ocf_commit": "abc",
            "source_ocf_version": "1.0.0",
            "release_url": "https://github.com/example/release",
            "release_notes_url": "https://github.com/example/notes",
            "functions": [
                {
                    "function_id": "OCF-0001",
                    "title": "Example",
                    "languages": ["en"],
                    "voices": ["voice-a"],
                    "sessions": [
                        {
                            "assets": [
                                {
                                    "asset_id": "asset-one",
                                    "filename": "one.mp3",
                                    "format": "mp3",
                                    "download_url": "https://example.com/one.mp3",
                                    "sha256": "a" * 64,
                                },
                                {
                                    "asset_id": "asset-one",
                                    "filename": "two.flac",
                                    "format": "flac",
                                    "download_url": "https://example.com/two.flac",
                                    "sha256": "b" * 64,
                                },
                            ]
                        }
                    ],
                }
            ],
        }
    ]
    return data


class CatalogValidationTests(unittest.TestCase):
    def test_empty_catalog_is_valid(self):
        validate_site.validate_catalog(empty_catalog())

    def test_malformed_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name in validate_site.REQUIRED:
                target = site / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    '{"schema_version":' if name == "catalog.json" else "",
                    encoding="utf-8",
                )
            with (
                patch.object(validate_site, "SITE", site),
                self.assertRaisesRegex(ValueError, "catalog.json is invalid"),
            ):
                validate_site.validate_site()

    def test_unsupported_schema_is_rejected(self):
        data = empty_catalog()
        data["schema_version"] = 3
        with self.assertRaisesRegex(ValueError, "unsupported schema_version"):
            validate_site.validate_catalog(data)

    def test_duplicate_asset_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate asset identifier"):
            validate_site.validate_catalog(catalog_with_assets())

    def test_invalid_sha256_is_rejected(self):
        data = catalog_with_assets()
        data["releases"][0]["functions"][0]["sessions"][0]["assets"][1]["asset_id"] = (
            "asset-two"
        )
        data["releases"][0]["functions"][0]["sessions"][0]["assets"][1]["sha256"] = (
            "not-a-checksum"
        )
        with self.assertRaisesRegex(ValueError, "invalid SHA-256"):
            validate_site.validate_catalog(data)

    def test_malformed_required_url_is_rejected(self):
        data = empty_catalog()
        data["source_repository"] = "javascript:alert(1)"
        with self.assertRaisesRegex(ValueError, "source_repository"):
            validate_site.validate_catalog(data)

    def test_missing_local_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name in validate_site.REQUIRED:
                target = site / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    "{}" if name == "catalog.json" else "", encoding="utf-8"
                )
            (site / "catalog.json").write_text(
                json.dumps(empty_catalog()), encoding="utf-8"
            )
            (site / "index.html").write_text(
                '<a href="missing.css">x</a>', encoding="utf-8"
            )
            with (
                patch.object(validate_site, "SITE", site),
                self.assertRaisesRegex(ValueError, "missing local href"),
            ):
                validate_site.validate_site()

    def test_broken_internal_navigation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name in validate_site.REQUIRED:
                target = site / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    "{}" if name == "catalog.json" else "", encoding="utf-8"
                )
            (site / "catalog.json").write_text(
                json.dumps(empty_catalog()), encoding="utf-8"
            )
            (site / "index.html").write_text(
                '<a href="#missing">x</a>', encoding="utf-8"
            )
            with (
                patch.object(validate_site, "SITE", site),
                self.assertRaisesRegex(ValueError, "broken internal navigation"),
            ):
                validate_site.validate_site()


if __name__ == "__main__":
    unittest.main()
