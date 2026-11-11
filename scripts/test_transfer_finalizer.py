import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import transfer_finalizer as f
from publication import canonical_bytes
from reconcile_transfer import identity
from test_reconcile_transfer import NOW, synthetic_approval
from test_transfer_registry import registry_fixture
from transfer_registry import TransferRegistry


def approvals(bundle, registry):
    """Synthetic records only; no real owner authorization."""
    a = bundle["attestation"]
    original = {
        "schema_version": 1,
        "manifest_sha256": identity(bundle["manifest"]),
        "owner": "Synthetic fixture",
        "approved_at": "2026-11-10T00:00:00Z",
        "public_assets": True,
        "voice_redistribution": True,
        "artwork_redistribution": True,
        "publish": False,
    }
    reconciliation = synthetic_approval(a)
    final = {
        "schema_version": 1,
        "purpose": f.PURPOSE,
        "owner": "meramsey",
        "approved_at": "2026-11-10T03:30:00Z",
        "expires_at": "2026-11-11T03:30:00Z",
        "repository": f.REPOSITORY,
        "repository_id": f.REPOSITORY_ID,
        "release_id": a["release_id"],
        "tag": a["tag"],
        "distribution_commit": a["distribution_commit"],
        "original_manifest_sha256": a["original_manifest_sha256"],
        "destination_manifest_sha256": a["destination_manifest_sha256"],
        "attestation_sha256": identity(a),
        "bundle_sha256": identity(bundle),
        "registry_sha256": registry.index_sha256,
        "original_approval_sha256": identity(original),
        "reconciliation_approval_sha256": identity(reconciliation),
        "ci_commits": {"source": "a" * 40, "distribution": "b" * 40},
        "allow_tag_creation": a["tag_ref"] is None,
        "public_assets": True,
        "voice_redistribution": True,
        "artwork_redistribution": True,
        "release_hold_lifted": True,
        "publish": True,
    }
    return original, reconciliation, final


class FakeRemote:
    repository = f.REPOSITORY
    can_finalize = True

    def __init__(self, bundle):
        self.current = copy.deepcopy(bundle["after"])
        self.current["observed_at"] = NOW.isoformat()
        self.calls = 0
        self.reads = 0
        self.mode = None
        self.ci_ok = True
        self.context_ok = True
        self.drift = None

    def verify_execution_context(self, sha, registry):
        if not self.context_ok:
            raise ValueError("dirty execution checkout")

    def verify_ci(self, commits):
        if not self.ci_ok:
            raise ValueError("CI not green")
        return [{"head_sha": commits["distribution"], "run_id": 1}]

    def snapshot(self, *, download):
        self.reads += 1
        value = copy.deepcopy(self.current)
        if self.drift and self.reads == self.drift[0]:
            self.drift[1](value)
        return value

    def finalize_existing(self, release_id, **kwargs):
        self.calls += 1
        pending = json.loads(Path(kwargs["intent_path"]).read_text())
        assert pending["state"] == "finalize-requested"
        if self.mode == "timeout-before":
            raise OSError("response lost before acceptance")
        self.current["release"]["draft"] = False
        target = self.current["release"]["target_commitish"]
        if self.current["tag_ref"] is None:
            self.current["tag_ref"] = {
                "ref": "refs/tags/" + self.current["release"]["tag_name"],
                "object_type": "commit",
                "object_sha": target,
                "peeled_commit": target,
            }
        if self.mode == "timeout-after":
            raise OSError("response lost after acceptance")


class FinalizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.bundle, _ = registry_fixture(self.root)
        self.registry = TransferRegistry(self.root)
        self.records = approvals(self.bundle, self.registry)
        self.remote = FakeRemote(self.bundle)
        self.receipt = self.root / "new-receipt.json"

    def tearDown(self):
        self.temp.cleanup()

    def run_finalizer(self, execute=True):
        return f.finalize_transfer(
            self.bundle["manifest"],
            17,
            self.registry,
            *self.records,
            self.remote,
            self.receipt,
            execute=execute,
            now=NOW,
        )

    def test_default_read_only_and_exact_finalization_preserve_frozen_records(self):
        frozen = copy.deepcopy((self.bundle, self.records))
        self.assertEqual(
            self.run_finalizer(False)["state"], "verified-draft-no-mutation"
        )
        self.assertEqual(self.remote.calls, 0)
        self.assertFalse(self.receipt.exists())
        result = self.run_finalizer()
        self.assertEqual(result["state"], "published-verified")
        self.assertEqual(self.remote.calls, 1)
        self.assertEqual((self.bundle, self.records), frozen)
        self.run_finalizer()  # Successful replay reads; never a second mutation.
        self.assertEqual(self.remote.calls, 1)

    def test_missing_forged_or_unscoped_approvals_fail_before_remote_reads(self):
        changes = [
            ("publish", False),
            ("release_hold_lifted", False),
            ("owner", "ocfproject-org"),
            ("repository", "other/repo"),
            ("release_id", 18),
            ("registry_sha256", "f" * 64),
            ("attestation_sha256", identity(self.bundle["manifest"])),
            ("original_approval_sha256", "f" * 64),
            ("allow_tag_creation", False),
            ("expires_at", "2026-11-10T03:45:00Z"),
            ("expires_at", "2099-01-01T00:00:00Z"),
        ]
        for key, value in changes:
            self.records = approvals(self.bundle, self.registry)
            self.records[2][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.run_finalizer()
        for position in range(3):
            self.records = list(approvals(self.bundle, self.registry))
            self.records[position] = {}
            with self.assertRaises(ValueError):
                self.run_finalizer()
        self.assertEqual(self.remote.reads, 0)
        self.assertEqual(self.remote.calls, 0)

    def test_ci_context_and_readonly_transport_block_writes(self):
        for key in ("ci_ok", "context_ok", "can_finalize"):
            self.remote = FakeRemote(self.bundle)
            setattr(self.remote, key, False)
            with self.assertRaises(ValueError):
                self.run_finalizer()
            self.assertFalse(self.receipt.exists())
            self.assertEqual(self.remote.calls, 0)

    def test_drift_partial_inventory_replaced_assets_and_authors_block_write(self):
        mutations = [
            lambda s: s["assets"].pop(),
            lambda s: s["assets"][0].update(id=900),
            lambda s: s["assets"][0].update(download_sha256="f" * 64),
            lambda s: s["assets"][0].update(api_digest=None),
            lambda s: s["release"].update(author="other"),
            lambda s: s["release"].update(body="changed"),
            lambda s: s.update(repository_id=5),
            lambda s: s.update(observed_at="2026-11-10T01:00:00Z"),
        ]
        for phase in (1, 2):
            for mutation in mutations:
                self.remote = FakeRemote(self.bundle)
                self.remote.drift = (phase, mutation)
                with self.subTest(phase=phase), self.assertRaises(ValueError):
                    self.run_finalizer()
                self.assertEqual(self.remote.calls, 0)
                self.assertFalse(self.receipt.exists())

    def test_uncertain_failure_never_retries_mutation(self):
        self.remote.mode = "timeout-before"
        with self.assertRaisesRegex(ValueError, "uncertain"):
            self.run_finalizer()
        self.assertEqual(
            json.loads(self.receipt.read_text())["state"], "finalize-requested"
        )
        with self.assertRaisesRegex(ValueError, "no automatic retry"):
            self.run_finalizer()
        self.assertEqual(self.remote.calls, 1)

    def test_lost_success_response_is_reconciled_without_second_patch(self):
        self.remote.mode = "timeout-after"
        self.assertEqual(self.run_finalizer()["state"], "published-verified")
        self.run_finalizer()
        self.assertEqual(self.remote.calls, 1)

    def test_terminal_inventory_drift_retains_uncertain_intent(self):
        self.remote.drift = (3, lambda s: s["assets"][0].update(id=999))
        with self.assertRaises(ValueError):
            self.run_finalizer()
        self.assertEqual(
            json.loads(self.receipt.read_text())["state"], "finalize-requested"
        )
        self.assertEqual(self.remote.calls, 1)

    def test_unrelated_receipt_and_unexplained_published_release_not_adopted(self):
        self.receipt.write_bytes(canonical_bytes({"phase": "draft-verified"}))
        with self.assertRaises(ValueError):
            self.run_finalizer()
        self.receipt.unlink()
        self.remote.finalize_existing(17, intent_path=self._synthetic_intent())
        self.remote.calls = 0
        with self.assertRaisesRegex(ValueError, "never adopt"):
            self.run_finalizer()
        self.assertEqual(self.remote.calls, 0)

    def _synthetic_intent(self):
        path = self.root / "fixture-intent.json"
        path.write_text('{"state":"finalize-requested"}')
        return path

    def test_existing_lock_is_not_removed_or_bypassed(self):
        lock = self.receipt.with_suffix(".json.lock")
        lock.write_text("existing owner")
        with self.assertRaises(FileExistsError):
            self.run_finalizer()
        self.assertEqual(lock.read_text(), "existing owner")
        self.assertEqual(self.remote.calls, 0)


class NativeGateTests(unittest.TestCase):
    def test_exact_main_ci_all_required_workflows(self):
        bundle = {"release_id": 17, "distribution_commit": "d" * 40}
        remote = f.TransferGitHub(bundle)
        commits = {"source": "a" * 40, "distribution": "b" * 40}

        def api(endpoint):
            source = (
                endpoint.startswith("repos/" + f.SOURCE + "/")
                or endpoint == "repos/" + f.SOURCE
            )
            repo, rid, sha = (
                (f.SOURCE, f.SOURCE_ID, commits["source"])
                if source
                else (f.REPOSITORY, f.REPOSITORY_ID, commits["distribution"])
            )
            if endpoint == "repos/" + repo:
                return {"id": rid, "full_name": repo, "default_branch": "main"}
            if endpoint.endswith("/commits/main"):
                return {"sha": sha}
            name = endpoint.split("/workflows/")[1].split("/")[0]
            return {
                "total_count": 1,
                "workflow_runs": [
                    {
                        "id": 7,
                        "run_attempt": 1,
                        "updated_at": NOW.isoformat(),
                        "head_sha": sha,
                        "head_branch": "main",
                        "event": "push",
                        "repository": {"id": rid},
                        "path": ".github/workflows/" + name,
                        "status": "completed",
                        "conclusion": "success",
                    }
                ],
            }

        remote._api.api = Mock(side_effect=api)
        self.assertEqual(len(remote.verify_ci(commits)), 5)
        for change in (
            "missing",
            "failure",
            "pr",
            "wrong-sha",
            "wrong-main",
            "older-rerun",
            "active",
            "partial",
        ):

            def bad(endpoint, change=change):
                value = api(endpoint)
                if change == "wrong-main" and endpoint.endswith("/commits/main"):
                    value["sha"] = "f" * 40
                if "workflow_runs" in value:
                    if change == "missing":
                        value["workflow_runs"] = []
                        value["total_count"] = 0
                    elif change == "older-rerun":
                        run = dict(
                            value["workflow_runs"][0],
                            id=6,
                            run_attempt=2,
                            updated_at="2026-11-10T05:00:00Z",
                            conclusion="failure",
                        )
                        value["workflow_runs"].append(run)
                        value["total_count"] = 2
                    elif change == "active":
                        value["workflow_runs"][0]["status"] = "in_progress"
                    elif change == "partial":
                        value["total_count"] = 2
                    elif change == "failure":
                        value["workflow_runs"][0]["conclusion"] = "failure"
                    elif change == "pr":
                        value["workflow_runs"][0]["event"] = "pull_request"
                    elif change == "wrong-sha":
                        value["workflow_runs"][0]["head_sha"] = "f" * 40
                return value

            remote._api.api = Mock(side_effect=bad)
            with self.subTest(change=change), self.assertRaises(ValueError):
                remote.verify_ci(commits)

    def test_native_cache_requires_actual_download_and_unchanged_inventory(self):
        remote = f.TransferGitHub({"release_id": 17, "distribution_commit": "d" * 40})
        metadata = {
            "assets": [
                {
                    "id": 101,
                    "name": "fixture",
                    "size_bytes": 7,
                    "api_digest": "sha256:x",
                    "state": "uploaded",
                }
            ]
        }
        remote._metadata = Mock(side_effect=lambda: copy.deepcopy(metadata))
        remote._api.sha256 = Mock(return_value="x")
        with self.assertRaisesRegex(ValueError, "cache"):
            remote.snapshot(download=False)
        remote.snapshot(download=True)
        remote.snapshot(download=False)
        self.assertEqual(remote._api.sha256.call_count, 1)
        metadata["assets"][0]["id"] = 102
        with self.assertRaisesRegex(ValueError, "cache"):
            remote.snapshot(download=False)

    def test_native_mutation_cannot_bypass_approval_or_durable_intent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            bundle, _ = registry_fixture(root)
            registry = TransferRegistry(root)
            original, reconciliation, final = approvals(bundle, registry)
            remote = f.TransferGitHub(bundle["attestation"], execute=True)
            remote._api.api = Mock()
            remote.verify_execution_context = Mock()
            remote.verify_ci = Mock(return_value=[])
            fresh = copy.deepcopy(bundle["after"])
            fresh["observed_at"] = NOW.isoformat()
            remote.snapshot = Mock(return_value=fresh)
            intent = root / "intent.json"
            kwargs = {
                "registry": registry,
                "original_approval": original,
                "reconciliation_approval": reconciliation,
                "final_approval": final,
                "intent_path": intent,
            }
            with patch.object(f, "datetime") as clock:
                clock.now.return_value = NOW
                with self.assertRaises(ValueError):
                    remote.finalize_existing(17, **kwargs)
                intent.write_bytes(
                    canonical_bytes(
                        {
                            "purpose": f.RECEIPT_PURPOSE,
                            "state": "finalize-requested",
                            "repository_id": f.REPOSITORY_ID,
                            "release_id": 17,
                            "attestation_sha256": identity(bundle["attestation"]),
                            "final_approval_sha256": identity(final),
                            "registry_sha256": registry.index_sha256,
                        }
                    )
                )
                bad = dict(kwargs, final_approval={})
                with self.assertRaises(ValueError):
                    remote.finalize_existing(17, **bad)
                remote._api.api.assert_not_called()
                remote._api.api.side_effect = OSError("lost response")
                with self.assertRaises(OSError):
                    remote.finalize_existing(17, **kwargs)
                with self.assertRaisesRegex(ValueError, "durable intent"):
                    remote.finalize_existing(17, **kwargs)
                # Even restoring a stale pending intent cannot reuse the attempt.
                pending = json.loads(intent.read_text())
                pending["state"] = "finalize-requested"
                intent.write_bytes(canonical_bytes(pending))
                with self.assertRaises(FileExistsError):
                    remote.finalize_existing(17, **kwargs)
                remote._api.api.assert_called_once_with(
                    remote._api.base + "/releases/17",
                    method="PATCH",
                    body={"draft": False, "make_latest": "false"},
                )


if __name__ == "__main__":
    unittest.main()
