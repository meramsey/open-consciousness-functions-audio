"""Synthetic mode-binding and post-publication lifecycle regression tests."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import transfer_finalizer as f
from catalog import append_release, transferred_release_entry
from publication import canonical_bytes
from reconcile_historical_transfer import MODE
from reconcile_transfer import identity
from refresh_catalog import build_catalog
from test_reconcile_historical_transfer import (
    registry_fixture_v2,
    synthetic_approval_v2,
)
from test_reconcile_transfer import NOW
from test_transfer_finalizer import FakeRemote, approvals
from test_transfer_registry import published
from test_validate_site import empty_catalog
from transfer_registry import TransferRegistry


def approvals_v2(bundle, registry):
    _, _, final = approvals(bundle, registry)
    rights = bundle["historical"]["rights_approval"]
    original = {
        k: rights[k]
        for k in (
            "owner",
            "approved_at",
            "public_assets",
            "voice_redistribution",
            "artwork_redistribution",
            "publish",
        )
    }
    original.update(schema_version=1, manifest_sha256=identity(bundle["manifest"]))
    reconciliation = synthetic_approval_v2(bundle["attestation"])
    final.update(
        schema_version=2,
        mode=MODE,
        uncertainty_acknowledgement_canonical_sha256=bundle["attestation"][
            "uncertainty_acknowledgement_canonical_sha256"
        ],
        original_approval_sha256=identity(original),
        reconciliation_approval_sha256=identity(reconciliation),
    )
    return original, reconciliation, final


class V2FinalizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bundle, _ = registry_fixture_v2(self.root)
        self.registry = TransferRegistry(self.root)
        self.approvals = approvals_v2(self.bundle, self.registry)
        self.remote = FakeRemote(self.bundle)
        self.path = self.root / "intent.json"

    def run_finalizer(self, execute=True):
        return f.finalize_transfer(
            self.bundle["manifest"],
            17,
            self.registry,
            *self.approvals,
            self.remote,
            self.path,
            execute=execute,
            now=NOW,
        )

    def test_absent_to_exact_tag_and_mode_bound_receipt(self):
        frozen = canonical_bytes(self.bundle)
        result = self.run_finalizer()
        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(result["mode"], MODE)
        self.assertEqual(
            result["tag_ref"]["peeled_commit"],
            self.bundle["attestation"]["distribution_commit"],
        )
        self.assertEqual(canonical_bytes(self.bundle), frozen)
        self.run_finalizer()
        self.assertEqual(self.remote.calls, 1)

    def test_cross_version_or_unknown_uncertainty_approval_rejected(self):
        for key, value in [
            ("schema_version", 1),
            ("mode", "strict-v1"),
            ("uncertainty_acknowledgement_canonical_sha256", "f" * 64),
        ]:
            with self.subTest(key=key):
                self.approvals = approvals_v2(self.bundle, self.registry)
                self.approvals[2][key] = value
                with self.assertRaises(ValueError):
                    self.run_finalizer()
        self.assertEqual(self.remote.calls, 0)

    def test_original_rights_substitution_rejected_even_if_final_hash_rebound(self):
        self.approvals[0]["owner"] = "another historical label"
        self.approvals[2]["original_approval_sha256"] = identity(self.approvals[0])
        with self.assertRaisesRegex(ValueError, "historical provenance"):
            self.run_finalizer()

    def test_missing_acknowledgement_and_cross_mode_receipt_rejected(self):
        self.approvals[1]["accept_unverified_historical_tag_continuity"] = False
        self.approvals[2]["reconciliation_approval_sha256"] = identity(
            self.approvals[1]
        )
        with self.assertRaises(ValueError):
            self.run_finalizer()
        self.approvals = approvals_v2(self.bundle, self.registry)
        self.run_finalizer()
        receipt = json.loads(self.path.read_text())
        receipt["mode"] = "strict-v1"
        self.path.write_bytes(canonical_bytes(receipt))
        with self.assertRaisesRegex(ValueError, "another operation"):
            self.run_finalizer()
        self.assertEqual(self.remote.calls, 1)

    def test_existing_tag_before_or_wrong_tag_after_rejected(self):
        target = self.bundle["attestation"]["distribution_commit"]
        tag = {
            "ref": "refs/tags/" + self.bundle["manifest"]["tag"],
            "object_type": "commit",
            "object_sha": target,
            "peeled_commit": target,
        }
        self.remote.current["tag_ref"] = tag
        with self.assertRaisesRegex(ValueError, "tag reference drift"):
            self.run_finalizer()
        self.remote.current["tag_ref"] = None
        self.remote.drift = (
            4,
            lambda value: value["tag_ref"].update(
                object_sha="f" * 40, peeled_commit="f" * 40
            ),
        )
        # Three reads: initial, fresh, terminal.
        self.remote.reads = 0
        self.remote.drift = (3, self.remote.drift[1])
        with self.assertRaisesRegex(ValueError, "tag"):
            self.run_finalizer()
        self.assertEqual(self.remote.calls, 1)
        self.assertEqual(
            json.loads(self.path.read_text())["state"], "finalize-requested"
        )

    def test_ambiguous_outcome_never_retries(self):
        self.remote.mode = "timeout-before"
        with self.assertRaises(ValueError):
            self.run_finalizer()
        with self.assertRaises(ValueError):
            self.run_finalizer()
        self.assertEqual(self.remote.calls, 1)

    def test_native_v2_boundary_requires_mode_bound_intent(self):
        remote = f.TransferGitHub(self.bundle["attestation"], execute=True)
        remote.verify_execution_context = Mock()
        remote.verify_ci = Mock(return_value=[])
        remote._api.api = Mock()
        fresh = copy.deepcopy(self.bundle["after"])
        fresh["observed_at"] = NOW.isoformat()
        remote.snapshot = Mock(return_value=fresh)
        original, reconciliation, final = self.approvals
        pending = {
            "schema_version": 2,
            "purpose": f.RECEIPT_PURPOSE,
            "state": "finalize-requested",
            "repository_id": f.REPOSITORY_ID,
            "release_id": 17,
            "attestation_sha256": identity(self.bundle["attestation"]),
            "final_approval_sha256": identity(final),
            "registry_sha256": self.registry.index_sha256,
        }
        kwargs = {
            "registry": self.registry,
            "original_approval": original,
            "reconciliation_approval": reconciliation,
            "final_approval": final,
            "intent_path": self.path,
        }
        with (
            patch.object(f, "RELEASE_STATE_ROOT", self.root / "native-state"),
            patch.object(f, "datetime") as clock,
        ):
            clock.now.return_value = NOW
            self.path.write_bytes(canonical_bytes(pending))
            with self.assertRaisesRegex(ValueError, "intent mode"):
                remote.finalize_existing(17, **kwargs)
            remote._api.api.assert_not_called()
            pending.update(
                mode=MODE,
                uncertainty_acknowledgement_canonical_sha256=final[
                    "uncertainty_acknowledgement_canonical_sha256"
                ],
            )
            self.path.write_bytes(canonical_bytes(pending))
            remote.finalize_existing(17, **kwargs)
            self.assertEqual(remote._api.api.call_count, 1)
            marker = json.loads(
                (f.RELEASE_STATE_ROOT / f"{f.REPOSITORY_ID}-17.attempt").read_text()
            )
            self.assertEqual(marker["mode"], MODE)
            self.assertEqual(
                marker["uncertainty_acknowledgement_canonical_sha256"],
                final["uncertainty_acknowledgement_canonical_sha256"],
            )

    def test_catalog_requires_mode_and_current_correct_tag(self):
        remote, assets = published(self.bundle)
        target = self.bundle["attestation"]["distribution_commit"]
        tag = {
            "ref": "refs/tags/" + self.bundle["manifest"]["tag"],
            "object_type": "commit",
            "object_sha": target,
            "peeled_commit": target,
        }
        with self.assertRaisesRegex(ValueError, "published tag"):
            transferred_release_entry(
                self.bundle["manifest"], remote, assets, registry=self.registry
            )
        entry = transferred_release_entry(
            self.bundle["manifest"], remote, assets, registry=self.registry, tag_ref=tag
        )
        self.assertEqual(entry["migration_mode"], MODE)
        append_release(empty_catalog(), entry, registry=self.registry)
        bad = copy.deepcopy(entry)
        bad["migration_mode"] = "strict-v1"
        with self.assertRaises(ValueError):
            append_release(empty_catalog(), bad, registry=self.registry)
        args = (
            empty_catalog(),
            [remote],
            lambda _: assets,
            lambda _: canonical_bytes(self.bundle["manifest"]),
        )
        with self.assertRaisesRegex(ValueError, "current tag lookup"):
            build_catalog(*args, registry=self.registry, repository_id=f.REPOSITORY_ID)
        catalog, _ = build_catalog(
            *args,
            registry=self.registry,
            repository_id=f.REPOSITORY_ID,
            read_tag=lambda _: tag,
        )
        self.assertEqual(catalog["releases"][0]["migration_mode"], MODE)
