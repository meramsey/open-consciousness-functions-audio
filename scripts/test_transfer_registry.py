import copy
import tempfile
import unittest
from pathlib import Path

from catalog import append_release, transferred_release_entry
from publication import canonical_bytes
from reconcile_transfer import REPOSITORY_ID, build_attestation, identity
from refresh_catalog import build_catalog
from test_reconcile_transfer import evidence
from test_validate_site import empty_catalog
from transfer_registry import TransferRegistry, validate_bundle
from validate_site import validate_catalog


def registry_fixture(root):
    manifest, before, after = evidence()
    attestation = build_attestation(manifest, before, after)
    bundle = {
        "schema_version": 1,
        "manifest": manifest,
        "before": before,
        "after": after,
        "attestation": attestation,
    }
    index = {
        "schema_version": 1,
        "entries": [
            {
                "release_id": 17,
                "attestation_sha256": identity(attestation),
                "bundle_sha256": identity(bundle),
            }
        ],
    }
    (root / "index.json").write_bytes(canonical_bytes(index))
    (root / (identity(bundle) + ".json")).write_bytes(canonical_bytes(bundle))
    return bundle, index


def published(bundle):
    release = dict(
        bundle["after"]["release"],
        draft=False,
        author={"login": "meramsey"},
        published_at="2026-11-11T00:00:00Z",
    )
    assets = [
        {
            "id": a["id"],
            "name": a["name"],
            "size": a["size_bytes"],
            "digest": a["api_digest"],
            "state": a["state"],
        }
        for a in bundle["after"]["assets"]
    ]
    return release, assets


class RegistryTests(unittest.TestCase):
    def test_empty_registry_rejects_arbitrary_transfer(self):
        manifest, _, _ = evidence()
        with self.assertRaisesRegex(ValueError, "not in reviewed registry"):
            TransferRegistry().resolve(manifest, 17)

    def test_pinned_bundle_validates_and_returns_independent_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle, index = registry_fixture(root)
            registry = TransferRegistry(root)
            self.assertEqual(registry.index_sha256, identity(index))
            result = registry.resolve(bundle["manifest"], 17)
            result["manifest"]["tag"] = "wrong"
            self.assertEqual(registry.resolve(bundle["manifest"], 17), bundle)
            for release_id in (True, "17", 18):
                with self.assertRaises(ValueError):
                    registry.resolve(bundle["manifest"], release_id)

    def test_bad_pins_and_forged_bundle_rejected(self):
        for mutation in ("digest", "attestation", "id", "extra", "duplicate"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory).resolve()
                bundle, index = registry_fixture(root)
                if mutation == "digest":
                    bundle["after"]["observed_at"] = "2026-11-10T02:30:00Z"
                    (
                        root / (index["entries"][0]["bundle_sha256"] + ".json")
                    ).write_bytes(canonical_bytes(bundle))
                elif mutation == "attestation":
                    index["entries"][0]["attestation_sha256"] = "f" * 64
                elif mutation == "id":
                    index["entries"][0]["release_id"] = 18
                elif mutation == "extra":
                    index["approved"] = True
                else:
                    index["entries"].append(copy.deepcopy(index["entries"][0]))
                (root / "index.json").write_bytes(canonical_bytes(index))
                with self.assertRaises(ValueError):
                    TransferRegistry(root)
        manifest, before, after = evidence()
        bundle = {
            "schema_version": 1,
            "manifest": manifest,
            "before": before,
            "after": after,
            "attestation": build_attestation(manifest, before, after),
        }
        bundle["attestation"]["release_id"] = 18
        with self.assertRaises(ValueError):
            validate_bundle(bundle)

    def test_unsafe_registry_path_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            registry_fixture(root)
            link = root / "link"
            try:
                link.symlink_to(root, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(ValueError, "symlink"):
                TransferRegistry(link)

    def test_transferred_projection_binds_original_digest_and_new_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle, _ = registry_fixture(root)
            registry = TransferRegistry(root)
            release, assets = published(bundle)
            entry = transferred_release_entry(
                bundle["manifest"], release, assets, registry=registry
            )
            catalog = append_release(empty_catalog(), entry, registry=registry)
            self.assertEqual(catalog["schema_version"], 3)
            self.assertEqual(
                entry["publication_manifest_sha256"], identity(bundle["manifest"])
            )
            self.assertIn(
                "github.com/ocfproject-org/",
                entry["functions"][0]["sessions"][0]["assets"][0]["download_url"],
            )
            validate_catalog(catalog, registry=registry)
            with self.assertRaises(ValueError):
                validate_catalog(catalog)
            for key, value in (
                ("repository_id", 1),
                ("release_id", 18),
                ("manifest_repository", "other/repo"),
                ("download_repository", "meramsey/open-consciousness-functions-audio"),
                ("migration_attestation_sha256", "f" * 64),
                ("publication_manifest_sha256", "f" * 64),
            ):
                changed = copy.deepcopy(catalog)
                changed["releases"][0][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    validate_catalog(changed, registry=registry)
            changed = copy.deepcopy(catalog)
            changed["schema_version"] = 2
            with self.assertRaises(ValueError):
                validate_catalog(changed, registry=registry)

    def test_schema_three_preserves_ordinary_entries(self):
        from catalog import release_entry
        from test_catalog import evidence as ordinary_evidence
        from test_publication import fixture

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle, _ = registry_fixture(root)
            registry = TransferRegistry(root)
            release, assets = published(bundle)
            migrated = transferred_release_entry(
                bundle["manifest"], release, assets, registry=registry
            )
            ordinary = fixture()
            ordinary.update(tag="audio-v2", edition="2.0.0")
            ordinary["assets"][0]["asset_id"] = "second-edition"
            entry = release_entry(ordinary, *ordinary_evidence(ordinary))
            for first, second in ((entry, migrated), (migrated, entry)):
                catalog = append_release(empty_catalog(), first, registry=registry)
                catalog = append_release(catalog, second, registry=registry)
                self.assertEqual(catalog["schema_version"], 3)
                self.assertIn(entry, catalog["releases"])
                self.assertIn(migrated, catalog["releases"])
                validate_catalog(catalog, registry=registry)

    def test_live_release_drift_and_control_replacement_block_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle, _ = registry_fixture(root)
            registry = TransferRegistry(root)
            for key, value in (
                ("id", 18),
                ("draft", True),
                ("author", {"login": "other"}),
                ("target_commitish", "f" * 40),
                ("body", "wrong"),
                ("upload_url", bundle["before"]["release"]["upload_url"]),
            ):
                release, assets = published(bundle)
                release[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    transferred_release_entry(
                        bundle["manifest"], release, assets, registry=registry
                    )
            for key, value in (
                ("id", 999),
                ("size", 1),
                ("digest", None),
                ("state", "new"),
            ):
                release, assets = published(bundle)
                assets[-1][key] = value  # control asset
                with self.subTest(key=key), self.assertRaises(ValueError):
                    transferred_release_entry(
                        bundle["manifest"], release, assets, registry=registry
                    )
            release, assets = published(bundle)
            assets.pop()
            with self.assertRaises(ValueError):
                transferred_release_entry(
                    bundle["manifest"], release, assets, registry=registry
                )

    def test_refresh_uses_only_reviewed_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle, _ = registry_fixture(root)
            registry = TransferRegistry(root)
            release, assets = published(bundle)
            args = (
                empty_catalog(),
                [release],
                lambda _: assets,
                lambda _: canonical_bytes(bundle["manifest"]),
            )
            with self.assertRaises(ValueError):
                build_catalog(*args)
            for wrong_id in (None, True, REPOSITORY_ID + 1):
                with self.assertRaisesRegex(ValueError, "stable ID"):
                    build_catalog(*args, registry=registry, repository_id=wrong_id)
            catalog, ignored = build_catalog(
                *args, registry=registry, repository_id=REPOSITORY_ID
            )
            self.assertEqual(catalog["schema_version"], 3)
            self.assertEqual(ignored, [])
            assets.append(
                {
                    "id": 999,
                    "name": "attestation.json",
                    "size": 1,
                    "state": "uploaded",
                    "digest": "sha256:" + "f" * 64,
                }
            )
            with self.assertRaises(ValueError):
                build_catalog(*args, registry=registry, repository_id=REPOSITORY_ID)


if __name__ == "__main__":
    unittest.main()
