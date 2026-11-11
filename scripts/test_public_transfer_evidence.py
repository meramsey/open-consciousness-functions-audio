"""Synthetic privacy and commitment checks; no actual approval or archive access."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from public_transfer_evidence import (
    build_public_bundle,
    validate_public_bundle,
    verify_private_evidence,
)
from publication import canonical_bytes
from reconcile_historical_transfer import MODE, build_attestation_v2
from reconcile_transfer import identity
from test_reconcile_historical_transfer import historical_fixture, registry_fixture_v2
from transfer_registry import TransferRegistry, validate_bundle


def private_fixture():
    manifest, historical, after = historical_fixture()
    historical["frozen_code"]["source_id"] = "/private/local/archive/code.py"
    historical["frozen_config"]["source_id"] = "/private/local/archive/config.json"
    historical["trusted_provenance"]["owner_message_ids"] = ["PRIVATE-OWNER-MESSAGE-ID"]
    historical["trusted_provenance"]["archive_source_id"] = (
        "/private/local/archive/evidence.json"
    )
    return {
        "schema_version": 2,
        "mode": MODE,
        "manifest": manifest,
        "historical": historical,
        "after": after,
        "attestation": build_attestation_v2(manifest, historical, after),
    }


class PublicEvidenceTests(unittest.TestCase):
    def test_registry_file_errors_hide_private_paths(self):
        secret = "/private/SECRET-OWNER-MESSAGE/archive.json"
        with (
            patch(
                "transfer_registry.load_json",
                side_effect=PermissionError(13, "denied", secret),
            ),
            self.assertRaises(ValueError) as caught,
        ):
            TransferRegistry(Path(secret))
        self.assertNotIn(secret, str(caught.exception))
        self.assertNotIn("SECRET-OWNER-MESSAGE", str(caught.exception))
        self.assertEqual(str(caught.exception), "invalid transfer registry JSON")

    def test_public_projection_deterministic_and_private_content_absent(self):
        private = private_fixture()
        original = copy.deepcopy(private)
        public = build_public_bundle(private)
        self.assertEqual(private, original)
        self.assertEqual(public, build_public_bundle(private))
        self.assertEqual(public["attestation"], private["attestation"])
        self.assertEqual(public["manifest"], private["manifest"])
        self.assertEqual(public["after"], private["after"])
        raw = canonical_bytes(public).decode()
        for private_text in (
            "PRIVATE-OWNER-MESSAGE-ID",
            "/private/local/archive",
            "Mike (repository owner; trusted conversation)",
            "public_assets",
            "voice_redistribution",
            "owner_message_ids",
            "verified_by",
            "source_id",
            "trusted_provenance",
        ):
            self.assertNotIn(private_text, raw)
        self.assertNotIn("historical", public)
        self.assertEqual(
            verify_private_evidence(public, private["historical"]),
            private["attestation"],
        )
        self.assertEqual(validate_public_bundle(public), private["attestation"])

    def test_fixed_role_inventory_commitment_is_precise(self):
        private = private_fixture()
        historical = private["historical"]
        hashes = {
            "manifest": historical["manifest_raw_file_sha256"],
            "original_rights": historical["rights_approval"]["raw_file_sha256"],
        }
        hashes.update(
            {
                role: historical[role]["raw_file_sha256"]
                for role in (
                    "download_receipt",
                    "terminal_inventory",
                    "frozen_code",
                    "frozen_config",
                    "prelaunch_tag_observation",
                )
            }
        )
        expected = {
            "schema_version": 1,
            "records": [
                {"role": role, "raw_file_sha256": hashes[role]}
                for role in sorted(hashes)
            ],
        }
        public = build_public_bundle(private)
        self.assertEqual(
            public["historical_commitments"]["raw_archive_inventory_canonical_sha256"],
            identity(expected),
        )

    def test_changed_private_evidence_and_opaque_commitments_cannot_finalize(self):
        private = private_fixture()
        public = build_public_bundle(private)
        for section, key, value in (
            ("rights_approval", "owner", "another owner"),
            ("frozen_code", "raw_file_sha256", "9" * 64),
            ("trusted_provenance", "owner_message_ids", ["different-private-message"]),
        ):
            historical = copy.deepcopy(private["historical"])
            historical[section][key] = value
            with self.subTest(section=section), self.assertRaises(ValueError):
                verify_private_evidence(public, historical)
        for key in (
            "archive_provenance_canonical_sha256",
            "raw_archive_inventory_canonical_sha256",
        ):
            changed = copy.deepcopy(public)
            changed["historical_commitments"][key] = "9" * 64
            # Public structure alone cannot authenticate this opaque value.
            validate_public_bundle(changed)
            with self.assertRaises(ValueError):
                verify_private_evidence(changed, private["historical"])

    def test_nested_private_fields_rejected_without_leaking_key_or_value(self):
        public = build_public_bundle(private_fixture())
        targets = (
            (),
            ("manifest",),
            ("manifest", "assets", 0),
            ("manifest", "assets", 0, "provenance"),
            ("manifest", "assets", 0, "session"),
            ("after",),
            ("after", "release"),
            ("after", "assets", 0),
            ("attestation",),
            ("attestation", "assets", 0),
            ("attestation", "uncertainty_acknowledgement"),
            ("historical_commitments",),
        )
        for path in targets:
            changed = copy.deepcopy(public)
            target = changed
            for part in path:
                target = target[part]
            target["PRIVATE-KEY-/home/owner"] = "PRIVATE-OWNER-MESSAGE-ID"
            with self.subTest(path=path), self.assertRaises(ValueError) as error:
                validate_public_bundle(changed)
            self.assertNotIn("PRIVATE", str(error.exception))
            self.assertNotIn("/home", str(error.exception))
        private = private_fixture()
        private["historical"]["PRIVATE-KEY"] = "PRIVATE-MESSAGE"
        with self.assertRaises(ValueError) as error:
            build_public_bundle(private)
        self.assertNotIn("PRIVATE", str(error.exception))

    def test_versions_visibility_and_mode_have_no_fallback(self):
        public = build_public_bundle(private_fixture())
        for key, value in (
            ("schema_version", 2),
            ("schema_version", True),
            ("mode", "v1"),
            ("evidence_visibility", "private"),
            ("historical_commitments", {}),
        ):
            changed = copy.deepcopy(public)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_public_bundle(changed)
        with self.assertRaises(ValueError):
            validate_bundle(private_fixture())
        with self.assertRaises(ValueError):
            build_public_bundle(public)

    def test_registry_unknown_keys_do_not_leak_private_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _, index = registry_fixture_v2(root)
            for nested in (False, True):
                changed = copy.deepcopy(index)
                target = changed["entries"][0] if nested else changed
                target["PRIVATE-OWNER-MESSAGE-ID"] = "/private/owner/approval.json"
                (root / "index.json").write_bytes(canonical_bytes(changed))
                with self.assertRaises(ValueError) as error:
                    TransferRegistry(root)
                self.assertNotIn("PRIVATE", str(error.exception))
                self.assertNotIn("/private", str(error.exception))

    def test_registry_requires_complete_public_visibility_pins(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            public, index = registry_fixture_v2(root)
            self.assertEqual(
                TransferRegistry(root).resolve(public["manifest"], 17), public
            )
            for key in ("bundle_schema_version", "evidence_visibility", "mode"):
                changed = copy.deepcopy(index)
                changed["entries"][0].pop(key)
                (root / "index.json").write_bytes(canonical_bytes(changed))
                with self.subTest(key=key), self.assertRaises(ValueError):
                    TransferRegistry(root)
            private = private_fixture()
            index["entries"][0]["bundle_sha256"] = identity(private)
            index["entries"][0]["attestation_sha256"] = identity(private["attestation"])
            (root / (identity(private) + ".json")).write_bytes(canonical_bytes(private))
            (root / "index.json").write_bytes(canonical_bytes(index))
            with self.assertRaises(ValueError):
                TransferRegistry(root)


if __name__ == "__main__":
    unittest.main()
