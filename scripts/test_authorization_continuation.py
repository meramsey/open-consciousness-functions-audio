"""Synthetic authorization context only; never real owner records or trust pins."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import authorization_continuation as a
import transfer_finalizer as f
from publication import canonical_bytes
from reconcile_historical_transfer import verify_reconciliation_v2
from reconcile_transfer import identity
from test_reconcile_historical_transfer import historical_fixture, registry_fixture_v2
from test_reconcile_transfer import NOW
from test_transfer_finalizer import FakeRemote
from test_transfer_finalizer_v2 import approvals_v2
from transfer_registry import TransferRegistry


def synthetic_context(release_scope):
    messages = []
    for role, sent, author in (
        ("original_release", "2026-11-09T22:00:00Z", "user"),
        ("artwork_rights", "2026-11-09T23:00:00Z", "user"),
        ("migration_hold", "2026-11-10T00:30:00Z", "user"),
        ("latest_instruction", "2026-11-10T02:30:00Z", "user"),
        ("evidence_gap_question", "2026-11-10T02:40:00Z", "user"),
        ("evidence_gap_disclosure", "2026-11-10T02:50:00Z", "aeon"),
    ):
        messages.append(
            {
                "role": role,
                "message_id": "synthetic-" + role,
                "author": author,
                "author_id": "synthetic-" + author,
                "sent_at": sent,
                "text": "Synthetic " + role + " fixture; no actual approval",
            }
        )
    return {
        "schema_version": 1,
        "purpose": a.CONTEXT_PURPOSE,
        "publisher": "meramsey",
        "messages": messages,
        "release_scope": copy.deepcopy(release_scope),
        "migration_completion": {
            "observed_at": "2026-11-10T03:10:00Z",
            "source": {"repository_id": f.SOURCE_ID, "repository": f.SOURCE},
            "distribution": {
                "repository_id": f.REPOSITORY_ID,
                "repository": f.REPOSITORY,
            },
        },
    }


def records(bundle, registry, original, pin):
    bound = a.bindings(bundle["manifest"], bundle["attestation"], original)
    reconciliation = {
        "schema_version": 3,
        "mode": a.MODE,
        "purpose": a.RECONCILIATION_PURPOSE,
        "recorded_by": "Synthetic release operator",
        "recorded_at": "2026-11-10T03:30:00Z",
        "context_sha256": pin,
        "bindings": bound,
        "scope_assessment": copy.deepcopy(a.SCOPE),
        "authorization_basis": a.DERIVATION,
        "operator_evidence_gap_acknowledgement": {
            "uncertainty_sha256": bound["uncertainty_sha256"],
            "historical_tag_state": "unknown",
            "historical_commit_api_resolution": "unobserved",
            "owner_explicit_gap_acceptance": False,
        },
        "reconcile": True,
        "publish": False,
    }
    final = copy.deepcopy(reconciliation)
    del final["reconcile"]
    final.update(
        purpose=a.FINAL_PURPOSE,
        recorded_at="2026-11-10T03:40:00Z",
        expires_at="2026-11-11T03:40:00Z",
        publish=True,
        allow_tag_creation=True,
        ci_commits={"source": "a" * 40, "distribution": "b" * 40},
    )
    final["bindings"].update(
        bundle_sha256=identity(bundle),
        registry_sha256=registry.index_sha256,
        reconciliation_record_sha256=identity(reconciliation),
    )
    return reconciliation, final


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bundle, _ = registry_fixture_v2(self.root)
        self.historical = historical_fixture()[1]
        self.registry = TransferRegistry(self.root)
        self.original = approvals_v2(self.bundle, self.registry)[0]
        self.scope = a.bindings(
            self.bundle["manifest"], self.bundle["attestation"], self.original
        )
        self.context = synthetic_context(self.scope)
        self.pin = identity(
            self.context
        )  # Test-only stand-in for EXTERNAL authentication.
        self.reconciliation, self.final = records(
            self.bundle, self.registry, self.original, self.pin
        )
        self.remote = FakeRemote(self.bundle)
        self.path = self.root / "intent.json"

    def run_finalizer(self, execute=True, **kwargs):
        options = {
            "private_historical": self.historical,
            "private_instruction_context": self.context,
            "expected_context_sha256": self.pin,
        }
        options.update(kwargs)
        return f.finalize_transfer(
            self.bundle["manifest"],
            17,
            self.registry,
            self.original,
            self.reconciliation,
            self.final,
            self.remote,
            self.path,
            execute=execute,
            now=NOW,
            **options,
        )

    def rebind(self):
        self.final["bindings"]["reconciliation_record_sha256"] = identity(
            self.reconciliation
        )

    def test_complete_derived_contract_preserves_frozen_inputs_and_truthful_claims(
        self,
    ):
        frozen = canonical_bytes(
            [self.bundle, self.historical, self.original, self.context]
        )
        result = self.run_finalizer(False)
        self.assertEqual(result["schema_version"], 3)
        self.assertEqual(result["context_sha256"], self.pin)
        self.assertFalse(self.path.exists())
        self.run_finalizer()
        self.run_finalizer()
        self.assertEqual(self.remote.calls, 1)
        self.assertEqual(
            frozen,
            canonical_bytes(
                [self.bundle, self.historical, self.original, self.context]
            ),
        )
        self.assertNotIn("approved_at", self.final)
        self.assertFalse(
            self.final["operator_evidence_gap_acknowledgement"][
                "owner_explicit_gap_acceptance"
            ]
        )

    def test_missing_wrong_or_self_supplied_pin_fails_before_network(self):
        for pin in (None, "f" * 64, self.context, True):
            with (
                self.subTest(pin=type(pin)),
                self.assertRaisesRegex(ValueError, "private"),
            ):
                self.run_finalizer(expected_context_sha256=pin)
        self.assertEqual(self.remote.reads, 0)
        self.assertEqual(self.remote.calls, 0)

    def test_forged_context_cannot_be_trusted_by_rebinding_records(self):
        self.context["messages"][-1]["text"] = "PRIVATE_SENTINEL forged permission"
        self.reconciliation["context_sha256"] = identity(self.context)
        self.final["context_sha256"] = identity(self.context)
        self.rebind()
        with self.assertRaisesRegex(ValueError, "private") as caught:
            self.run_finalizer()
        self.assertNotIn("PRIVATE_SENTINEL", str(caught.exception))

    def test_missing_roles_duplicate_ids_wrong_authors_and_invalid_chronology(self):
        for role in a.ROLES:
            context = synthetic_context(self.scope)
            context["messages"] = [r for r in context["messages"] if r["role"] != role]
            with self.subTest(role=role), self.assertRaises(ValueError):
                a._context(
                    context,
                    identity(context),
                    self.original,
                    NOW,
                    expected_release_scope=self.scope,
                )
        for change in (
            lambda c: c["messages"][2].update(
                message_id=c["messages"][0]["message_id"]
            ),
            lambda c: c["messages"][2].update(author="aeon"),
            lambda c: c["messages"][2].update(author_id="other-owner"),
            lambda c: c["messages"][2].update(sent_at="2026-11-10T03:00:00Z"),
            lambda c: c["migration_completion"]["distribution"].update(
                repository="other/repo"
            ),
        ):
            context = synthetic_context(self.scope)
            change(context)
            with self.assertRaises(ValueError):
                a._context(
                    context,
                    identity(context),
                    self.original,
                    NOW,
                    expected_release_scope=self.scope,
                )

    def test_false_contradictory_or_unresolved_operator_scope_rejected(self):
        for key, value in (
            ("same_original_batch", False),
            ("original_rights_unchanged", False),
            ("hold_scope", "all-publication"),
            ("unresolved_holds", True),
            ("contradictory_instructions", True),
            ("migration_complete", False),
            ("latest_instruction", "engineering-only"),
            ("same_original_batch", 1),
        ):
            with self.subTest(key=key):
                self.reconciliation, self.final = records(
                    self.bundle, self.registry, self.original, self.pin
                )
                self.reconciliation["scope_assessment"][key] = value
                self.rebind()
                with self.assertRaises(ValueError):
                    self.run_finalizer()

    def test_every_reconciliation_binding_is_required_even_if_final_rebound(self):
        for key in self.reconciliation["bindings"]:
            self.reconciliation, self.final = records(
                self.bundle, self.registry, self.original, self.pin
            )
            self.reconciliation["bindings"][key] = "changed"
            self.rebind()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.run_finalizer()

    def test_every_final_binding_is_required(self):
        for key in self.final["bindings"]:
            self.reconciliation, self.final = records(
                self.bundle, self.registry, self.original, self.pin
            )
            self.final["bindings"][key] = "changed"
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.run_finalizer()

    def test_no_fabricated_owner_acknowledgement_or_approval_time(self):
        for key, value in (
            ("owner_explicit_gap_acceptance", True),
            ("historical_tag_state", "absent"),
        ):
            self.reconciliation, self.final = records(
                self.bundle, self.registry, self.original, self.pin
            )
            self.reconciliation["operator_evidence_gap_acknowledgement"][key] = value
            self.rebind()
            with self.assertRaises(ValueError):
                self.run_finalizer()
        self.reconciliation, self.final = records(
            self.bundle, self.registry, self.original, self.pin
        )
        self.final["approved_at"] = self.final["recorded_at"]
        with self.assertRaises(ValueError):
            self.run_finalizer()

    def test_expiry_operator_time_and_impersonation_rejected(self):
        for key, value in (
            ("recorded_at", "2026-11-10T02:00:00Z"),
            ("recorded_by", "meramsey"),
            ("expires_at", "2026-11-10T03:50:00Z"),
            ("expires_at", "2026-11-12T03:40:00Z"),
            ("publish", False),
        ):
            self.reconciliation, self.final = records(
                self.bundle, self.registry, self.original, self.pin
            )
            self.final[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.run_finalizer()

    def test_cross_contract_substitution_does_not_infer_v3_from_public_envelope(self):
        old = approvals_v2(self.bundle, self.registry)
        with self.assertRaises(ValueError):
            verify_reconciliation_v2(
                self.bundle["manifest"],
                self.historical,
                self.bundle["after"],
                self.bundle["attestation"],
                self.reconciliation,
                now=NOW,
            )
        self.reconciliation = old[1]
        with self.assertRaises(ValueError):
            self.run_finalizer()
        self.final = old[2]
        with self.assertRaises(ValueError):
            self.run_finalizer()
        self.run_finalizer(
            False, private_instruction_context=None, expected_context_sha256=None
        )

    def test_unchanged_runtime_guards_and_uncertain_retry(self):
        self.remote.ci_ok = False
        with self.assertRaisesRegex(ValueError, "CI"):
            self.run_finalizer()
        self.remote.ci_ok = True
        self.remote.mode = "timeout-before"
        with self.assertRaises(ValueError):
            self.run_finalizer()
        with self.assertRaisesRegex(ValueError, "no automatic retry"):
            self.run_finalizer()
        self.assertEqual(self.remote.calls, 1)

    def test_native_boundary_rechecks_pin_intent_and_permanent_attempt(self):
        remote = f.TransferGitHub(self.bundle["attestation"], execute=True)
        remote.verify_execution_context = Mock()
        remote.verify_ci = Mock(return_value=[])
        remote._api.api = Mock()
        fresh = copy.deepcopy(self.bundle["after"])
        fresh["observed_at"] = NOW.isoformat()
        remote.snapshot = Mock(return_value=fresh)
        pending = self.run_finalizer(False)
        pending["state"] = "finalize-requested"
        kwargs = {
            "registry": self.registry,
            "original_approval": self.original,
            "reconciliation_approval": self.reconciliation,
            "final_approval": self.final,
            "intent_path": self.path,
            "private_historical": self.historical,
            "private_instruction_context": self.context,
            "expected_context_sha256": self.pin,
        }
        with (
            patch.object(f, "RELEASE_STATE_ROOT", self.root / "native"),
            patch.object(f, "datetime") as clock,
        ):
            clock.now.return_value = NOW
            self.path.write_bytes(canonical_bytes(pending))
            for bad in (None, "f" * 64):
                with self.assertRaises(ValueError):
                    remote.finalize_existing(
                        17, **dict(kwargs, expected_context_sha256=bad)
                    )
            remote._api.api.assert_not_called()
            changed = dict(pending, context_sha256="f" * 64)
            self.path.write_bytes(canonical_bytes(changed))
            with self.assertRaisesRegex(ValueError, "intent binding"):
                remote.finalize_existing(17, **kwargs)
            self.path.write_bytes(canonical_bytes(pending))
            remote.finalize_existing(17, **kwargs)
            self.assertEqual(remote._api.api.call_count, 1)
            marker = json.loads(
                (f.RELEASE_STATE_ROOT / f"{f.REPOSITORY_ID}-17.attempt").read_text()
            )
            self.assertEqual(marker["context_sha256"], self.pin)
            self.path.write_bytes(canonical_bytes(pending))
            with self.assertRaises(FileExistsError):
                remote.finalize_existing(17, **kwargs)
            self.assertEqual(remote._api.api.call_count, 1)

    def test_pin_rechecked_after_remote_work_before_mutation(self):
        def mutate(_):
            self.context["messages"][0]["text"] = "changed during verification"

        self.remote.drift = (2, mutate)
        with self.assertRaises(ValueError):
            self.run_finalizer()
        self.assertEqual(self.remote.calls, 0)

    def test_runtime_freshness_target_and_tag_guards_remain_required(self):
        changes = (
            lambda row: row.update(observed_at="2026-11-10T03:00:00Z"),
            lambda row: row["release"].update(target_commitish="f" * 40),
            lambda row: row.update(tag_ref={"ref": "refs/tags/existing"}),
        )
        for change in changes:
            self.remote = FakeRemote(self.bundle)
            self.remote.drift = (1, change)
            with self.assertRaises(ValueError):
                self.run_finalizer()
            self.assertEqual(self.remote.calls, 0)

    def test_native_context_rechecked_after_ci_before_patch(self):
        remote = f.TransferGitHub(self.bundle["attestation"], execute=True)
        remote.verify_execution_context = Mock()

        def changed(_):
            self.context["messages"][0]["text"] = "changed by concurrent caller"
            return []

        remote.verify_ci = Mock(side_effect=changed)
        remote._api.api = Mock()
        fresh = copy.deepcopy(self.bundle["after"])
        fresh["observed_at"] = NOW.isoformat()
        remote.snapshot = Mock(return_value=fresh)
        pending = self.run_finalizer(False)
        pending["state"] = "finalize-requested"
        self.path.write_bytes(canonical_bytes(pending))
        with (
            patch.object(f, "RELEASE_STATE_ROOT", self.root / "native"),
            patch.object(f, "datetime") as clock,
        ):
            clock.now.return_value = NOW
            with self.assertRaises(ValueError):
                remote.finalize_existing(
                    17,
                    registry=self.registry,
                    original_approval=self.original,
                    reconciliation_approval=self.reconciliation,
                    final_approval=self.final,
                    intent_path=self.path,
                    private_historical=self.historical,
                    private_instruction_context=self.context,
                    expected_context_sha256=self.pin,
                )
        remote._api.api.assert_not_called()

    def test_private_verifiers_suppress_unknown_keys_and_wrong_types(self):
        for context in (None, [], {"PRIVATE_SENTINEL": "private text"}):
            with self.assertRaises(ValueError) as caught:
                a.verify_final_v3(
                    self.bundle,
                    self.registry,
                    self.original,
                    self.reconciliation,
                    self.final,
                    NOW,
                    private_historical=self.historical,
                    private_instruction_context=context,
                    expected_context_sha256=self.pin,
                )
            self.assertNotIn("PRIVATE_SENTINEL", str(caught.exception))
        self.final["PRIVATE_SENTINEL"] = "private text"
        with self.assertRaises(ValueError) as caught:
            self.run_finalizer()
        self.assertNotIn("PRIVATE_SENTINEL", str(caught.exception))

    def test_external_observation_can_follow_instruction_but_not_operator_record(self):
        a._context(
            self.context,
            self.pin,
            self.original,
            NOW,
            expected_release_scope=self.scope,
        )
        self.reconciliation["recorded_at"] = "2026-11-10T03:00:00Z"
        self.rebind()
        with self.assertRaises(ValueError):
            self.run_finalizer()

    def test_original_approval_cannot_change_even_with_new_record_bindings(self):
        self.original["publish"] = not self.original["publish"]
        self.reconciliation, self.final = records(
            self.bundle, self.registry, self.original, self.pin
        )
        with self.assertRaises(ValueError):
            self.run_finalizer()

    def test_final_v3_does_not_allow_legacy_public_bundle_or_new_public_fields(self):
        for version in (1, 2):
            bundle = copy.deepcopy(self.bundle)
            bundle["schema_version"] = version
            with self.assertRaises(ValueError):
                f.verify_final_approval(
                    bundle,
                    self.registry,
                    self.original,
                    self.reconciliation,
                    self.final,
                    NOW,
                    private_historical=self.historical,
                    private_instruction_context=self.context,
                    expected_context_sha256=self.pin,
                )
        from transfer_registry import validate_bundle

        bundle = copy.deepcopy(self.bundle)
        bundle["context_sha256"] = self.pin
        with self.assertRaises(ValueError):
            validate_bundle(bundle)

    def test_trusted_context_is_not_reusable_for_another_self_consistent_release(self):
        for key in self.scope:
            expected = dict(self.scope)
            expected[key] = "different release binding"
            with self.subTest(key=key), self.assertRaises(ValueError):
                a._context(
                    self.context,
                    self.pin,
                    self.original,
                    NOW,
                    expected_release_scope=expected,
                )
        # Rehashing self-authored records/context cannot change the EXTERNAL pin.
        self.context["release_scope"]["release_id"] = 18
        self.reconciliation["context_sha256"] = identity(self.context)
        self.final["context_sha256"] = identity(self.context)
        self.rebind()
        with self.assertRaises(ValueError):
            self.run_finalizer()

    def test_external_pin_replay_against_second_valid_bundle_is_rejected(self):
        from public_transfer_evidence import build_public_bundle
        from reconcile_historical_transfer import build_attestation_v2

        manifest, historical, after = historical_fixture()
        historical["download_receipt"]["release_id"] = 18
        historical["terminal_inventory"]["release"]["id"] = 18
        historical["terminal_inventory"]["release_api_url"] = historical[
            "terminal_inventory"
        ]["release_api_url"].replace("/releases/17", "/releases/18")
        historical["terminal_inventory"]["release"]["upload_url"] = historical[
            "terminal_inventory"
        ]["release"]["upload_url"].replace("/releases/17", "/releases/18")
        after["release"]["id"] = 18
        after["release_api_url"] = after["release_api_url"].replace(
            "/releases/17", "/releases/18"
        )
        after["release"]["upload_url"] = after["release"]["upload_url"].replace(
            "/releases/17", "/releases/18"
        )
        attestation = build_attestation_v2(manifest, historical, after, now=NOW)
        bundle = build_public_bundle(
            {
                "schema_version": 2,
                "mode": a.MODE,
                "manifest": manifest,
                "historical": historical,
                "after": after,
                "attestation": attestation,
            }
        )
        root = self.root / "second"
        root.mkdir()
        index = {
            "schema_version": 1,
            "entries": [
                {
                    "mode": a.MODE,
                    "bundle_schema_version": 3,
                    "evidence_visibility": "public-commitments",
                    "release_id": 18,
                    "attestation_sha256": identity(attestation),
                    "bundle_sha256": identity(bundle),
                }
            ],
        }
        (root / "index.json").write_bytes(canonical_bytes(index))
        (root / (identity(bundle) + ".json")).write_bytes(canonical_bytes(bundle))
        registry = TransferRegistry(root)
        old = approvals_v2(bundle, registry, historical)
        f.verify_final_approval(
            bundle, registry, *old, NOW, private_historical=historical
        )
        reconciliation, final = records(bundle, registry, old[0], self.pin)
        with self.assertRaises(ValueError):
            f.verify_final_approval(
                bundle,
                registry,
                old[0],
                reconciliation,
                final,
                NOW,
                private_historical=historical,
                private_instruction_context=self.context,
                expected_context_sha256=self.pin,
            )

    def test_cli_success_summary_excludes_private_pin_approval_hash_and_paths(self):
        import contextlib
        import io

        values = {
            "manifest": self.bundle["manifest"],
            "original": self.original,
            "reconciliation": self.reconciliation,
            "final": self.final,
            "historical": self.historical,
            "context": self.context,
        }
        args = [
            "manifest",
            "--release-id",
            "17",
            "--original-approval",
            "original",
            "--reconciliation-approval",
            "reconciliation",
            "--final-approval",
            "final",
            "--private-historical",
            "historical",
            "--private-instruction-context",
            "context",
            "--expected-context-sha256",
            self.pin,
            "--receipt",
            str(self.path),
        ]
        result = self.run_finalizer(False)
        stdout = io.StringIO()
        with (
            patch.object(f, "load_registry", return_value=self.registry),
            patch.object(f, "load_json", side_effect=lambda path: values[str(path)]),
            patch.object(f, "verify_final_approval") as verify,
            patch.object(f, "finalize_transfer", return_value=result) as finalize,
            patch.object(f, "TransferGitHub"),
            contextlib.redirect_stdout(stdout),
        ):
            f.main(args)
        verify.assert_called_once()
        self.assertEqual(verify.call_args.kwargs["expected_context_sha256"], self.pin)
        self.assertEqual(finalize.call_args.kwargs["expected_context_sha256"], self.pin)
        out = stdout.getvalue()
        self.assertNotIn(self.pin, out)
        self.assertNotIn(identity(self.final), out)
        self.assertNotIn(str(self.path), out)
        self.assertEqual(
            set(json.loads(out)),
            {"schema_version", "purpose", "repository_id", "release_id", "state"},
        )
