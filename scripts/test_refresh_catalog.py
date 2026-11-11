import copy
import hashlib
import unittest

from publication import REPOSITORY, canonical_bytes, control_artifacts
from refresh_catalog import build_catalog
from test_catalog import evidence
from test_publication import fixture
from test_validate_site import empty_catalog


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.manifest = fixture()
        _, self.release = evidence(self.manifest)
        self.release["author"] = {"login": "meramsey"}
        self.files = {
            a["remote_filename"]: (a["size_bytes"], a["sha256"])
            for a in self.manifest["assets"]
        }
        self.files.update(
            {
                name: (len(data), hashlib.sha256(data).hexdigest())
                for name, data in control_artifacts(self.manifest).items()
            }
        )
        self.assets = [
            {
                "id": i,
                "name": name,
                "size": size,
                "digest": "sha256:" + sha,
                "state": "uploaded",
            }
            for i, (name, (size, sha)) in enumerate(self.files.items(), 1)
        ]

    def build(self, releases=None):
        return build_catalog(
            empty_catalog(),
            releases if releases is not None else [self.release],
            lambda _: self.assets,
            lambda _: canonical_bytes(self.manifest),
        )

    def test_org_destination_with_human_publisher_projects_without_audio_download(self):
        self.assertEqual(REPOSITORY, "ocfproject-org/open-consciousness-functions-audio")
        result, ignored = self.build()
        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(len(result["releases"]), 1)
        self.assertEqual(ignored, [])

    def test_drafts_and_unmarked_releases_are_not_listed(self):
        draft = copy.deepcopy(self.release)
        draft["draft"] = True
        unmarked = copy.deepcopy(self.release)
        unmarked["body"] = "not an approved OCF manifest"
        result, ignored = self.build([draft, unmarked])
        self.assertEqual(result["releases"], [])
        self.assertEqual(len(ignored), 1)

    def test_missing_digest_blocks_catalog(self):
        self.assets[0]["digest"] = None
        with self.assertRaisesRegex(ValueError, "digest"):
            self.build()

    def test_wrong_publisher_blocks_catalog(self):
        self.release["author"]["login"] = "other"
        with self.assertRaisesRegex(ValueError, "not authorized"):
            self.build()

    def test_org_identity_is_not_a_publisher(self):
        self.release["author"]["login"] = "ocfproject-org"
        with self.assertRaisesRegex(ValueError, "not authorized"):
            self.build()

    def test_asset_omission_or_extra_is_rejected(self):
        self.assets.pop()
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.build()

    def test_changed_manifest_is_rejected(self):
        self.manifest["edition"] = "2.0.0"
        with self.assertRaisesRegex(ValueError, "marker"):
            self.build()


if __name__ == "__main__":
    unittest.main()
