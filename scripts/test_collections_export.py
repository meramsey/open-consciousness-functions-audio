import copy
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from collections_export import build_collections
from test_publication import fixture


class CollectionsTests(unittest.TestCase):
    def test_deterministic_parts_preserve_individual_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest = fixture()
            first = manifest["assets"][0]
            first.update(
                size_bytes=3000, sha256=hashlib.sha256(b"a" * 3000).hexdigest()
            )
            second = copy.deepcopy(first)
            second.update(
                asset_id="second", filename="Second.flac", remote_filename="Second.flac"
            )
            second["session"]["function_id"] = "OCF-FND-002"
            manifest["assets"].append(second)
            for asset in manifest["assets"]:
                (root / asset["filename"]).write_bytes(b"a" * 3000)
            a = build_collections(manifest, root, root / "first", max_part_bytes=13000)
            b = build_collections(manifest, root, root / "second", max_part_bytes=13000)
            self.assertEqual(a, b)
            self.assertEqual(len(a), 2)
            for record in a:
                self.assertLess(record["size_bytes"], 13000)
                with zipfile.ZipFile(root / "first" / record["filename"]) as archive:
                    audio = [n for n in archive.namelist() if n.endswith(".flac")]
                    self.assertEqual(len(audio), 1)
                    self.assertEqual(archive.read(audio[0]), b"a" * 3000)
                    self.assertIn("playlist.m3u8", archive.namelist())
            with self.assertRaisesRegex(ValueError, "already exists"):
                build_collections(manifest, root, root / "first")

    def test_remote_names_handle_plus_and_group_collisions(self):
        from publication import validate_manifest

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest = fixture()
            base = manifest["assets"][0]
            manifest["assets"] = []
            for index, (locale, voice) in enumerate(
                (("en-US", "voice"), ("en", "US-voice"), ("en-US", "voice+v1"))
            ):
                asset = copy.deepcopy(base)
                asset.update(
                    asset_id=f"track-{index}",
                    filename=f"Track-{index}.flac",
                    remote_filename=f"Track-{index}.flac",
                )
                asset["session"].update(locale=locale, voice_id=voice)
                manifest["assets"].append(asset)
                (root / asset["filename"]).write_bytes(b"fixture")
            records = build_collections(manifest, root, root / "output")
            self.assertEqual(len({a["remote_filename"] for a in records}), 3)
            validate_manifest({**manifest, "assets": records})

    def test_tampered_input_rejected_before_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest = fixture()
            (root / manifest["assets"][0]["filename"]).write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "checksum"):
                build_collections(manifest, root, root / "output")
            self.assertFalse((root / "output").exists())
            self.assertFalse(list(root.glob(".ocf-collection-stage-*")))


if __name__ == "__main__":
    unittest.main()
