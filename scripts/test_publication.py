import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

import publication as p


def fixture():
    return {
        "schema_version": 1,
        "repository": p.REPOSITORY,
        "tag": "audio-v1.0.0",
        "edition": "1.0.0",
        "source_commit": "a" * 40,
        "source_version": "1.0.0",
        "assets": [
            {
                "asset_id": "example-flac-1",
                "filename": "OCF-FND-001 - Example.flac",
                "remote_filename": "OCF-FND-001-Example.flac",
                "format": "flac",
                "size_bytes": 7,
                "sha256": hashlib.sha256(b"fixture").hexdigest(),
                "provenance": {
                    k: "b" * 64
                    for k in (
                        "source_manifest_sha256",
                        "master_sha256",
                        "technical_receipt_sha256",
                    )
                },
                "session": {
                    "kind": "function",
                    "function_id": "OCF-FND-001",
                    "title": "Example",
                    "locale": "en-US",
                    "voice_id": "example",
                    "voice_name": "Example",
                    "edition": "1.0.0",
                    "duration_seconds": 1.25,
                    "sample_rate_hz": 44100,
                    "channels": 2,
                    "encoding": "FLAC",
                    "bit_depth": 24,
                },
            }
        ],
    }


def approval(manifest):
    return {
        "schema_version": 1,
        "manifest_sha256": p.manifest_digest(manifest),
        "owner": "Test fixture only",
        "approved_at": "2026-01-01T00:00:00Z",
        "public_assets": True,
        "voice_redistribution": True,
        "artwork_redistribution": True,
        "publish": False,
    }


class PublicationTests(unittest.TestCase):
    def test_exact_approval_and_separate_publication(self):
        manifest = fixture()
        record = approval(manifest)
        p.verify_approval(manifest, record)
        with self.assertRaisesRegex(ValueError, "final publication"):
            p.verify_approval(manifest, record, publication=True)
        record["publish"] = True
        p.verify_approval(manifest, record, publication=True)
        manifest["assets"][0]["session"]["title"] = "Changed title"
        with self.assertRaisesRegex(ValueError, "exact manifest"):
            p.verify_approval(manifest, record)

    def test_each_right_is_explicit_boolean(self):
        for key in ("public_assets", "voice_redistribution", "artwork_redistribution"):
            for value in (False, 1, "true", None):
                with self.subTest(key=key, value=value):
                    manifest = fixture()
                    record = approval(manifest)
                    record[key] = value
                    with self.assertRaises(ValueError):
                        p.verify_approval(manifest, record)

    def test_preparation_is_not_fake_function(self):
        manifest = fixture()
        session = manifest["assets"][0]["session"]
        session.update(
            kind="preparation-learning", function_id=None, title="Preparation Learning"
        )
        p.validate_manifest(manifest)
        session["function_id"] = "OCF-FND-001"
        with self.assertRaises(ValueError):
            p.validate_manifest(manifest)

    def test_malformed_contracts_rejected(self):
        for key, value in (
            ("size_bytes", True),
            ("size_bytes", 2**31),
            ("sha256", "a"),
            ("filename", "../secret.flac"),
            ("filename", "C:\\secret.flac"),
            ("filename", "CON.flac"),
            ("filename", "foo\nbar.flac"),
            ("format", "exe"),
            ("private_path", "/private"),
        ):
            with self.subTest(key=key, value=value):
                manifest = fixture()
                manifest["assets"][0][key] = value
                with self.assertRaises(ValueError):
                    p.validate_manifest(manifest)
        for value in (float("nan"), float("inf"), True, 0):
            manifest = fixture()
            manifest["assets"][0]["session"]["duration_seconds"] = value
            with self.assertRaises(ValueError):
                p.validate_manifest(manifest)

    def test_duplicate_names_case_insensitive(self):
        manifest = fixture()
        duplicate = copy.deepcopy(manifest["assets"][0])
        duplicate.update(asset_id="other", filename=duplicate["filename"].upper())
        manifest["assets"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            p.validate_manifest(manifest)

    def test_files_verified_and_symlinks_rejected(self):
        manifest = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / manifest["assets"][0]["filename"]
            path.write_bytes(b"fixture")
            p.verify_files(manifest, root)
            path.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "checksum"):
                p.verify_files(manifest, root)
            path.unlink()
            target = root / "target"
            target.write_bytes(b"fixture")
            try:
                path.symlink_to(target)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(ValueError, "symlink"):
                p.verify_files(manifest, root)

    def test_canonical_digest_and_encoded_url(self):
        manifest = fixture()
        reordered = dict(reversed(list(manifest.items())))
        self.assertEqual(p.manifest_digest(manifest), p.manifest_digest(reordered))
        self.assertTrue(
            p.asset_url(manifest, manifest["assets"][0]).endswith(
                "OCF-FND-001-Example.flac"
            )
        )
        self.assertEqual(
            p.checksums(manifest),
            manifest["assets"][0]["sha256"] + "  OCF-FND-001-Example.flac\n",
        )


if __name__ == "__main__":
    unittest.main()
