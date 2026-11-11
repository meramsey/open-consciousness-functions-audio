"""Synthetic v2 archive projections only; no actual owner approval/evidence."""

import copy
import tempfile
import unittest
from pathlib import Path

from publication import canonical_bytes
from reconcile_historical_transfer import (
    APPROVAL_PURPOSE,
    MODE,
    UNCERTAINTY,
    build_attestation_v2,
    verify_reconciliation_v2,
)
from reconcile_transfer import identity
from test_reconcile_transfer import NOW, evidence
from transfer_registry import TransferRegistry


def historical_fixture():
    manifest, before, after = evidence()
    rights = {
        "schema_version": 1,
        "owner": "Mike (repository owner; trusted conversation)",
        "approved_at": "2026-11-10T00:00:00Z",
        "manifest_sha256": identity(manifest),
        "public_assets": True,
        "voice_redistribution": True,
        "artwork_redistribution": True,
        "publish": False,
    }
    controls = []
    from reconcile_transfer import expected_inventory, legacy_controls

    expected = expected_inventory(manifest, legacy_controls(manifest)[0])
    for asset in before["assets"]:
        controls.append(
            dict(expected[asset["name"]], name=asset["name"], remote_id=asset["id"])
        )
    historical = {
        "schema_version": 2,
        "mode": MODE,
        "repository_id": before["repository_id"],
        "repository": before["repository"],
        "historical_tag_state": "unknown",
        "historical_commit_api_resolution": "unobserved",
        "manifest_raw_file_sha256": expected["publication.json"]["sha256"],
        "rights_approval": {
            "raw_file_sha256": "a" * 64,
            "canonical_sha256": identity(rights),
            "manifest_canonical_sha256": identity(manifest),
            **{
                k: rights[k]
                for k in (
                    "owner",
                    "approved_at",
                    "public_assets",
                    "voice_redistribution",
                    "artwork_redistribution",
                    "publish",
                )
            },
        },
        "download_receipt": {
            "raw_file_sha256": "b" * 64,
            "verification_recorded_at": before["observed_at"],
            "observation_basis": "terminal-recorded-receipt-verification",
            "release_id": 17,
            "manifest_canonical_sha256": identity(manifest),
            "verification": "full-download-sha256",
            "assets": [dict(a, download_sha256=a["sha256"]) for a in controls],
        },
        "terminal_inventory": {
            "raw_file_sha256": "c" * 64,
            "observed_at": before["observed_at"],
            "release_api_url": before["release_api_url"],
            "release": before["release"],
            "assets": [
                dict(a, state="uploaded", api_digest="sha256:" + a["sha256"])
                for a in controls
            ],
        },
        "frozen_code": {
            "raw_file_sha256": "d" * 64,
            "source_id": "synthetic-code-archive",
        },
        "frozen_config": {
            "raw_file_sha256": "e" * 64,
            "source_id": "synthetic-config-archive",
        },
        "prelaunch_tag_observation": {
            "raw_file_sha256": "f" * 64,
            "source_id": "synthetic-prelaunch",
            "observation_time": {"state": "unknown"},
            "state": "absent",
            "ref": "refs/tags/" + manifest["tag"],
        },
        "trusted_provenance": {
            "verification": "authenticated-archive-and-owner-messages",
            "archive_source_id": "synthetic-archive",
            "owner_message_ids": ["synthetic-owner-message"],
            "verified_by": "synthetic-supervisor",
            "authenticated_owner": "meramsey",
            "verified_at": "2026-11-10T02:30:00Z",
        },
    }
    return manifest, historical, after


def synthetic_approval_v2(attestation):
    return {
        "schema_version": 2,
        "mode": MODE,
        "purpose": APPROVAL_PURPOSE,
        "owner": "meramsey",
        "approved_at": "2026-11-10T03:00:00Z",
        "attestation_canonical_sha256": identity(attestation),
        "uncertainty_acknowledgement_canonical_sha256": identity(UNCERTAINTY),
        "accept_unverified_historical_tag_continuity": True,
        "authorize_current_absent_tag_creation": True,
        "reconcile": True,
        "publish": False,
    }


def registry_fixture_v2(root):
    manifest, historical, after = historical_fixture()
    attestation = build_attestation_v2(manifest, historical, after, now=NOW)
    bundle = {
        "schema_version": 2,
        "mode": MODE,
        "manifest": manifest,
        "historical": historical,
        "after": after,
        "attestation": attestation,
    }
    from public_transfer_evidence import build_public_bundle

    bundle = build_public_bundle(bundle)
    index = {
        "schema_version": 1,
        "entries": [
            {
                "mode": MODE,
                "bundle_schema_version": 3,
                "evidence_visibility": "public-commitments",
                "release_id": 17,
                "attestation_sha256": identity(attestation),
                "bundle_sha256": identity(bundle),
            }
        ],
    }
    (root / "index.json").write_bytes(canonical_bytes(index))
    (root / (identity(bundle) + ".json")).write_bytes(canonical_bytes(bundle))
    return bundle, index


class HistoricalTests(unittest.TestCase):
    def test_valid_v2_preserves_unknowns_and_inputs_and_never_publishes(self):
        manifest, historical, after = historical_fixture()
        original = copy.deepcopy((manifest, historical, after))
        attestation = build_attestation_v2(manifest, historical, after, now=NOW)
        result = verify_reconciliation_v2(
            manifest,
            historical,
            after,
            attestation,
            synthetic_approval_v2(attestation),
            now=NOW,
        )
        self.assertEqual((manifest, historical, after), original)
        self.assertEqual(
            attestation["uncertainty_acknowledgement"]["historical_tag_state"],
            "unknown",
        )
        self.assertIs(result["publication_allowed"], False)
        self.assertEqual(result["mode"], MODE)

    def test_unknown_history_cannot_be_replaced_with_absence_or_v1(self):
        for key, value in (
            ("historical_tag_state", None),
            ("historical_tag_state", "absent"),
            ("historical_commit_api_resolution", "verified"),
            ("mode", "v1"),
            ("schema_version", 1),
            ("repository_id", True),
            ("repository_id", 99),
        ):
            manifest, historical, after = historical_fixture()
            historical[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                build_attestation_v2(manifest, historical, after, now=NOW)

    def test_malformed_provenance_hashes_and_rights_rejected(self):
        for group, key, value in (
            ("trusted_provenance", "owner_message_ids", []),
            ("trusted_provenance", "owner_message_ids", ["x", "x"]),
            ("trusted_provenance", "verification", "self-approved"),
            ("trusted_provenance", "archive_source_id", ""),
            ("trusted_provenance", "verified_by", ""),
            ("trusted_provenance", "authenticated_owner", "synthetic-supervisor"),
            ("trusted_provenance", "verified_at", "2026-11-10T00:00:00Z"),
            ("frozen_code", "raw_file_sha256", "bad"),
            ("frozen_config", "source_id", ""),
            ("rights_approval", "canonical_sha256", "f" * 64),
            ("rights_approval", "public_assets", False),
            ("download_receipt", "verification", "github-api-digest"),
        ):
            manifest, historical, after = historical_fixture()
            historical[group][key] = value
            with self.subTest(group=group, key=key), self.assertRaises(ValueError):
                build_attestation_v2(manifest, historical, after, now=NOW)
        manifest, historical, after = historical_fixture()
        historical["frozen_code"].pop("raw_file_sha256")
        with self.assertRaises(ValueError):
            build_attestation_v2(manifest, historical, after, now=NOW)

    def test_complete_historical_join_required_including_controls(self):
        for group in ("download_receipt", "terminal_inventory"):
            for mutation in (
                "missing",
                "duplicate",
                "renamed",
                "replaced",
                "changed",
                "extra",
            ):
                manifest, historical, after = historical_fixture()
                assets = historical[group]["assets"]
                if mutation == "missing":
                    assets.pop()
                elif mutation == "duplicate":
                    assets[-1] = copy.deepcopy(assets[0])
                elif mutation == "renamed":
                    assets[-1]["name"] = "other"
                elif mutation == "replaced":
                    assets[-1]["remote_id"] = 999
                elif mutation == "changed":
                    assets[-1]["sha256"] = "f" * 64
                else:
                    assets[-1]["approved"] = True
                with (
                    self.subTest(group=group, mutation=mutation),
                    self.assertRaises(ValueError),
                ):
                    build_attestation_v2(manifest, historical, after, now=NOW)

    def test_current_tag_commit_and_time_must_be_exact(self):
        for key, value in (
            (
                "tag_ref",
                {
                    "ref": "refs/tags/audio-v1.0.0",
                    "object_type": "commit",
                    "object_sha": "d" * 40,
                    "peeled_commit": "d" * 40,
                },
            ),
            ("distribution_commit_sha", "f" * 40),
            ("verification", "api-only"),
            ("observed_at", "2026-11-10T00:00:00Z"),
        ):
            manifest, historical, after = historical_fixture()
            after[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_attestation_v2(manifest, historical, after, now=NOW)

    def test_approval_requires_exact_mode_and_explicit_uncertainty_acceptance(self):
        manifest, historical, after = historical_fixture()
        attestation = build_attestation_v2(manifest, historical, after, now=NOW)
        for key, value in (
            ("mode", "v1"),
            ("schema_version", 1),
            ("publish", True),
            ("accept_unverified_historical_tag_continuity", 1),
            ("authorize_current_absent_tag_creation", False),
            ("uncertainty_acknowledgement_canonical_sha256", "f" * 64),
            ("attestation_canonical_sha256", "f" * 64),
            ("approved_at", "2026-11-10T00:00:00Z"),
        ):
            approval = synthetic_approval_v2(attestation)
            approval[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_reconciliation_v2(
                    manifest, historical, after, attestation, approval, now=NOW
                )
        from test_reconcile_transfer import synthetic_approval

        with self.assertRaises(ValueError):
            verify_reconciliation_v2(
                manifest,
                historical,
                after,
                attestation,
                synthetic_approval(attestation),
                now=NOW,
            )

    def test_changed_raw_archive_hash_requires_new_approval(self):
        manifest, historical, after = historical_fixture()
        old = build_attestation_v2(manifest, historical, after, now=NOW)
        approval = synthetic_approval_v2(old)
        self.assertEqual(
            old["original_rights_approval_canonical_sha256"],
            historical["rights_approval"]["canonical_sha256"],
        )
        self.assertNotEqual(
            historical["rights_approval"]["raw_file_sha256"],
            historical["rights_approval"]["canonical_sha256"],
        )
        historical["frozen_code"]["raw_file_sha256"] = "9" * 64
        new = build_attestation_v2(manifest, historical, after, now=NOW)
        with self.assertRaisesRegex(ValueError, "approval attestation mismatch"):
            verify_reconciliation_v2(
                manifest, historical, after, new, approval, now=NOW
            )

    def test_original_owner_label_and_unknown_prelaunch_time_are_preserved(self):
        manifest, historical, after = historical_fixture()
        original_owner = historical["rights_approval"]["owner"]
        attestation = build_attestation_v2(manifest, historical, after, now=NOW)
        self.assertNotEqual(original_owner, "meramsey")
        self.assertEqual(historical["rights_approval"]["owner"], original_owner)
        self.assertEqual(
            historical["prelaunch_tag_observation"]["observation_time"],
            {"state": "unknown"},
        )
        self.assertEqual(
            attestation["original_rights_approval_canonical_sha256"],
            historical["rights_approval"]["canonical_sha256"],
        )
        historical["rights_approval"]["owner"] = "meramsey"
        with self.assertRaisesRegex(ValueError, "canonical projection mismatch"):
            build_attestation_v2(manifest, historical, after, now=NOW)

    def test_unknown_time_cannot_hide_unsupported_or_invented_timestamp(self):
        for value in (
            None,
            {"state": "absent"},
            {"state": "unknown", "observed_at": "2026-11-10T00:00:00Z"},
            {"state": "recorded", "observed_at": "2026-11-10T02:00:00Z"},
        ):
            manifest, historical, after = historical_fixture()
            historical["prelaunch_tag_observation"]["observation_time"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_attestation_v2(manifest, historical, after, now=NOW)
        manifest, historical, after = historical_fixture()
        historical["download_receipt"]["verification_recorded_at"] = (
            "2026-11-10T00:45:00Z"
        )
        with self.assertRaisesRegex(ValueError, "terminal receipt observation"):
            build_attestation_v2(manifest, historical, after, now=NOW)

    def test_supervisor_verifier_is_distinct_from_authenticated_owner(self):
        manifest, historical, after = historical_fixture()
        provenance = historical["trusted_provenance"]
        self.assertEqual(provenance["verified_by"], "synthetic-supervisor")
        self.assertEqual(provenance["authenticated_owner"], "meramsey")
        build_attestation_v2(manifest, historical, after, now=NOW)
        provenance.pop("authenticated_owner")
        with self.assertRaises(ValueError):
            build_attestation_v2(manifest, historical, after, now=NOW)

    def test_registry_explicit_mode_pin_and_no_version_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle, index = registry_fixture_v2(root)
            registry = TransferRegistry(root)
            self.assertEqual(registry.resolve(bundle["manifest"], 17), bundle)
            for mode in (None, "v1", "unknown"):
                changed = copy.deepcopy(index)
                if mode is None:
                    changed["entries"][0].pop("mode")
                else:
                    changed["entries"][0]["mode"] = mode
                (root / "index.json").write_bytes(canonical_bytes(changed))
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    TransferRegistry(root)


if __name__ == "__main__":
    unittest.main()
