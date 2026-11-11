import copy
import hashlib
import unittest

from catalog import append_release, release_entry
from publication import control_artifacts, manifest_digest
from test_publication import fixture
from test_validate_site import empty_catalog


def evidence(manifest):
    receipt = {
        "manifest_sha256": manifest_digest(manifest),
        "phase": "published-verified",
        "release_id": 1,
        "verified_assets": [
            {"asset_id": a["asset_id"], "sha256": a["sha256"]}
            for a in manifest["assets"]
        ],
    }
    receipt["verified_assets"].extend(
        {"asset_id": "control:" + name, "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in control_artifacts(manifest).items()
    )
    remote = {
        "id": 1,
        "draft": False,
        "tag_name": manifest["tag"],
        "body": "OCF publication manifest SHA-256: " + manifest_digest(manifest),
        "published_at": "2026-01-01T00:00:00Z",
    }
    return receipt, remote


class CatalogProjectionTests(unittest.TestCase):
    def test_published_projection_and_idempotent_append(self):
        manifest = fixture()
        receipt, remote = evidence(manifest)
        release = release_entry(manifest, receipt, remote)
        catalog = append_release(empty_catalog(), release)
        self.assertEqual(append_release(catalog, release), catalog)
        self.assertEqual(
            catalog["releases"][0]["functions"][0]["sessions"][0]["assets"][0][
                "bit_depth"
            ],
            24,
        )
        changed = copy.deepcopy(release)
        changed["source_ocf_version"] = "different"
        with self.assertRaisesRegex(ValueError, "immutable"):
            append_release(catalog, changed)

    def test_draft_or_incomplete_evidence_rejected(self):
        manifest = fixture()
        receipt, remote = evidence(manifest)
        remote["draft"] = True
        with self.assertRaises(ValueError):
            release_entry(manifest, receipt, remote)
        remote["draft"] = False
        receipt["verified_assets"].pop()
        with self.assertRaisesRegex(ValueError, "asset set"):
            release_entry(manifest, receipt, remote)

    def test_preparation_stays_separate(self):
        manifest = fixture()
        manifest["assets"][0]["session"].update(
            kind="preparation-learning", function_id=None, title="Preparation Learning"
        )
        release = release_entry(manifest, *evidence(manifest))
        self.assertEqual(release["functions"], [])
        self.assertNotIn("function_id", release["preparations"][0])
        self.assertEqual(
            release["preparations"][0]["session_kind"], "preparation-learning"
        )

    def test_production_catalog_rejects_inconsistent_or_private_fields(self):
        from validate_site import validate_catalog

        manifest = fixture()
        release = release_entry(manifest, *evidence(manifest))
        original = append_release(empty_catalog(), release)
        for field, value in (
            ("sample_rate_hz", True),
            ("download_url", "https://example.com/wrong.flac"),
            ("private_path", "/private"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                changed["releases"][0]["functions"][0]["sessions"][0]["assets"][0][
                    field
                ] = value
                with self.assertRaises(ValueError):
                    validate_catalog(changed)
        changed = copy.deepcopy(original)
        changed["releases"][0]["functions"][0]["voices"] = ["different"]
        with self.assertRaisesRegex(ValueError, "selectors"):
            validate_catalog(changed)

    def test_same_identity_different_titles_rejected(self):
        manifest = fixture()
        second = copy.deepcopy(manifest["assets"][0])
        second.update(
            asset_id="second",
            filename="Example.mp3",
            remote_filename="Example.mp3",
            format="mp3",
        )
        second["session"]["title"] = "Conflicting"
        manifest["assets"].append(second)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            release_entry(manifest, *evidence(manifest))


if __name__ == "__main__":
    unittest.main()
