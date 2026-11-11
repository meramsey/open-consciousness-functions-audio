import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from prepare_review import prepare_review
from publication import control_artifacts, verify_approval, verify_files
from test_import_candidates import candidate


class ReviewPacketTests(unittest.TestCase):
    def test_collections_controls_checksums_and_pending_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, document = candidate(root / "source", preparation=True)
            original = source.read_bytes()
            output = root / "review"
            report = prepare_review(
                [source],
                output,
                tag="audio-review-v1",
                edition=document["session"]["edition"],
                collections=True,
            )
            assets = output / "assets"
            manifest = json.loads((assets / "publication.json").read_text())
            verify_files(manifest, assets)
            self.assertEqual(
                len([a for a in manifest["assets"] if a["format"] == "zip"]), 2
            )
            self.assertFalse(report["publication_approved"])
            self.assertEqual(report["state"], "local-review-only")
            self.assertEqual(source.read_bytes(), original)
            for name, data in control_artifacts(manifest).items():
                self.assertEqual((assets / name).read_bytes(), data)
            remote_to_local = {
                a["remote_filename"]: a["filename"] for a in manifest["assets"]
            }
            for checksum_file in ("SHA256SUMS.txt", "LOCAL-SHA256SUMS.txt"):
                for line in (assets / checksum_file).read_text().splitlines():
                    checksum, name = line.split("  ", 1)
                    if checksum_file == "SHA256SUMS.txt":
                        name = remote_to_local.get(name, name)
                    self.assertEqual(
                        hashlib.sha256((assets / name).read_bytes()).hexdigest(),
                        checksum,
                    )
            with self.assertRaisesRegex(ValueError, "missing required fields"):
                verify_approval(manifest, report, publication=True)
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare_review(
                    [source],
                    output,
                    tag="audio-review-v1",
                    edition=document["session"]["edition"],
                )

    def test_tampered_input_preserves_original_and_failed_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, document = candidate(root / "source")
            audio = source.parent / document["artifacts"][0]["file"]
            audio.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "size|checksum"):
                prepare_review(
                    [source],
                    root / "review",
                    tag="audio-v1",
                    edition=document["session"]["edition"],
                )
            self.assertFalse((root / "review").exists())
            self.assertEqual(audio.read_bytes(), b"changed")
            self.assertEqual(len(list(root.glob(".ocf-review-stage-*"))), 1)


if __name__ == "__main__":
    unittest.main()
