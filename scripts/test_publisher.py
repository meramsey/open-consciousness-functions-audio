import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from publisher import publish
from test_publication import approval, fixture


class Remote:
    repository = "meramsey/open-consciousness-functions-audio"

    def __init__(self):
        self.release = None
        self.assets = []
        self.content = {}
        self.uploads = 0
        self.finishes = 0
        self.interrupt = False
        self.corrupt = False

    def find_release(self, tag):
        return copy.deepcopy(self.release)

    def create_draft(self, tag, marker):
        self.release = {"id": 1, "tag_name": tag, "body": marker, "draft": True}
        return copy.deepcopy(self.release)

    def list_assets(self, release_id):
        return copy.deepcopy(self.assets)

    def upload(self, release_id, path):
        self.uploads += 1
        number = len(self.assets) + 1
        self.content[number] = path.read_bytes()
        self.assets.append(
            {
                "id": number,
                "name": path.name,
                "state": "uploaded",
                "size": path.stat().st_size,
            }
        )
        if self.interrupt:
            self.interrupt = False
            raise ConnectionError("connection lost after server accepted upload")

    def sha256(self, asset_id):
        return (
            "0" * 64
            if self.corrupt
            else hashlib.sha256(self.content[asset_id]).hexdigest()
        )

    def finalize(self, release_id):
        self.finishes += 1
        self.release["draft"] = False


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.manifest = fixture()
        (self.root / self.manifest["assets"][0]["filename"]).write_bytes(b"fixture")
        self.approval = approval(self.manifest)
        self.remote = Remote()
        self.receipt = self.root / "receipt.json"

    def run_publish(self, **kwargs):
        return publish(
            self.manifest, self.root, self.approval, self.remote, self.receipt, **kwargs
        )

    def test_draft_resume_publish_and_immutable_repeat(self):
        self.assertEqual(self.run_publish()["phase"], "draft-verified")
        self.assertEqual(self.remote.uploads, 4)
        self.run_publish()
        self.assertEqual(self.remote.uploads, 4)
        with self.assertRaisesRegex(ValueError, "final publication"):
            self.run_publish(finalize=True)
        self.assertEqual(self.remote.finishes, 0)
        self.approval["publish"] = True
        self.assertEqual(self.run_publish(finalize=True)["phase"], "published-verified")
        self.run_publish(finalize=True)
        self.assertEqual(self.remote.finishes, 1)
        self.assertEqual(self.remote.uploads, 4)

    def test_lost_upload_response_is_reconciled(self):
        self.remote.interrupt = True
        with self.assertRaises(ConnectionError):
            self.run_publish()
        self.assertEqual(self.run_publish()["phase"], "draft-verified")
        self.assertEqual(self.remote.uploads, 4)

    def test_corrupt_remote_never_published(self):
        self.remote.corrupt = True
        self.approval["publish"] = True
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.run_publish(finalize=True)
        self.assertTrue(self.remote.release["draft"])
        self.assertEqual(self.remote.finishes, 0)

    def test_no_remote_calls_without_approval(self):
        self.approval["voice_redistribution"] = False
        with self.assertRaises(ValueError):
            self.run_publish()
        self.assertIsNone(self.remote.release)

    def test_no_mutation_of_missing_published_asset(self):
        self.run_publish()
        self.remote.assets.clear()
        self.remote.release["draft"] = False
        with self.assertRaisesRegex(ValueError, "never modify"):
            self.run_publish()
        self.assertEqual(self.remote.uploads, 4)

    def test_foreign_release_or_unexpected_assets_blocked(self):
        self.run_publish()
        self.remote.release["body"] = "someone else's release"
        with self.assertRaisesRegex(ValueError, "identity"):
            self.run_publish()

    def test_upload_uses_verified_snapshot_not_live_source(self):
        original = self.remote.upload
        source = self.root / self.manifest["assets"][0]["filename"]

        def replace_source_then_upload(release_id, path):
            source.write_bytes(b"private")
            original(release_id, path)

        self.remote.upload = replace_source_then_upload
        self.run_publish()
        self.assertEqual(self.remote.content[1], b"fixture")

    def test_draft_published_during_run_blocks_next_upload(self):
        original = self.remote.upload

        def publish_after_upload(release_id, path):
            original(release_id, path)
            self.remote.release["draft"] = False

        self.remote.upload = publish_after_upload
        with self.assertRaisesRegex(ValueError, "expected draft"):
            self.run_publish()
        self.assertEqual(self.remote.uploads, 1)

    def test_manifest_and_checksum_files_are_verified(self):
        result = self.run_publish()
        self.assertEqual(len(result["verified_assets"]), 4)
        self.assertEqual(
            {a["name"] for a in self.remote.assets},
            {
                self.manifest["assets"][0]["remote_filename"],
                "publication.json",
                "SHA256SUMS.txt",
                "release-notes.md",
            },
        )

    def test_published_release_is_never_recreated(self):
        self.approval["publish"] = True
        self.run_publish(finalize=True)
        self.remote.release = None
        with self.assertRaisesRegex(ValueError, "never recreate"):
            self.run_publish()
        self.assertIsNone(self.remote.release)

    def test_lost_creation_and_finalization_responses_resume(self):
        create = self.remote.create_draft

        def lost_creation(tag, marker):
            create(tag, marker)
            raise ConnectionError("created but response lost")

        self.remote.create_draft = lost_creation
        with self.assertRaises(ConnectionError):
            self.run_publish()
        self.remote.create_draft = create
        self.run_publish()
        finalize = self.remote.finalize

        def lost_finalization(release_id):
            finalize(release_id)
            raise ConnectionError("published but response lost")

        self.remote.finalize = lost_finalization
        self.approval["publish"] = True
        with self.assertRaises(ConnectionError):
            self.run_publish(finalize=True)
        self.remote.finalize = finalize
        self.assertEqual(self.run_publish(finalize=True)["phase"], "published-verified")
        self.assertEqual(self.remote.finishes, 1)
        self.assertEqual(self.remote.uploads, 4)

    def test_replaced_published_release_is_not_adopted(self):
        self.approval["publish"] = True
        self.run_publish(finalize=True)
        self.remote.release["id"] = 999
        with self.assertRaisesRegex(ValueError, "replaced"):
            self.run_publish()
        self.assertEqual(self.remote.uploads, 4)

    def test_wrong_repository_blocked_before_remote_write(self):
        self.remote.repository = "wrong/repository"
        with self.assertRaisesRegex(ValueError, "repository mismatch"):
            self.run_publish()
        self.assertIsNone(self.remote.release)

    def test_interrupted_temporary_receipt_does_not_block_resume(self):
        stale = self.root / "receipt.json.interrupted.tmp"
        stale.write_text('{"partial":', encoding="utf-8")
        self.run_publish()
        self.assertTrue(stale.exists())

    def test_receipt_cannot_be_reused_for_new_manifest(self):
        self.run_publish()
        self.manifest["edition"] = "2.0.0"
        self.approval = approval(self.manifest)
        with self.assertRaisesRegex(ValueError, "another manifest"):
            self.run_publish()

    def test_identity_persisted_before_initial_asset_lookup(self):
        import json

        def interrupted_lookup(release_id):
            raise ConnectionError("asset lookup interrupted")

        self.remote.list_assets = interrupted_lookup
        with self.assertRaises(ConnectionError):
            self.run_publish()
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt["release_id"], self.remote.release["id"])
        self.assertEqual(receipt["verified_assets"], [])
        self.assertEqual(self.remote.uploads, 0)

    def test_identity_persisted_before_first_asset_verification(self):
        import json

        self.remote.interrupt = True
        with self.assertRaises(ConnectionError):
            self.run_publish()
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt["release_id"], self.remote.release["id"])
        self.assertEqual(receipt["verified_assets"], [])

    def test_missing_release_after_first_upload_failure_is_never_recreated(self):
        self.remote.interrupt = True
        with self.assertRaises(ConnectionError):
            self.run_publish()
        self.remote.release = None
        with self.assertRaisesRegex(ValueError, "never recreate"):
            self.run_publish()
        self.assertIsNone(self.remote.release)
        self.assertEqual(self.remote.uploads, 1)

    def test_replaced_release_after_first_readback_failure_is_never_adopted(self):
        self.remote.corrupt = True
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.run_publish()
        self.remote.release["id"] = 999
        self.remote.corrupt = False
        with self.assertRaisesRegex(ValueError, "replaced"):
            self.run_publish()
        self.assertEqual(self.remote.uploads, 1)

    def _terminal_mutation_fails(self, change, message):
        import json

        self.approval["publish"] = True
        original = self.remote.finalize

        def mutate(release_id):
            original(release_id)
            change()

        self.remote.finalize = mutate
        with self.assertRaisesRegex(ValueError, message):
            self.run_publish(finalize=True)
        self.assertNotEqual(
            json.loads(self.receipt.read_text())["phase"], "published-verified"
        )
        self.assertEqual(self.remote.finishes, 1)
        self.assertEqual(self.remote.uploads, 4)

    def test_finalization_rechecks_manifest_marker(self):
        self._terminal_mutation_fails(
            lambda: self.remote.release.update(body="foreign manifest"), "not confirmed"
        )

    def test_finalization_rechecks_release_tag(self):
        self._terminal_mutation_fails(
            lambda: self.remote.release.update(tag_name="another-tag"), "not confirmed"
        )

    def test_finalization_rechecks_asset_identity(self):
        self._terminal_mutation_fails(
            lambda: self.remote.assets[0].update(id=999), "inventory changed"
        )

    def test_finalization_rechecks_asset_size(self):
        self._terminal_mutation_fails(
            lambda: self.remote.assets[0].update(size=999), "inventory changed"
        )


if __name__ == "__main__":
    unittest.main()
