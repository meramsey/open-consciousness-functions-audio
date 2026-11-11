import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import publication
import reconcile_transfer as migration
from test_publication import fixture

NOW = datetime(2026, 11, 10, 4, tzinfo=UTC)


def evidence():
    """Entirely synthetic bytes/IDs/approval; never real owner evidence."""
    manifest = fixture()
    manifest["repository"] = migration.LEGACY_REPOSITORY
    # Independently exercise the unchanged ordinary encoder under its former
    # destination to test legacy control preservation, not just mirror the helper.
    with patch.object(publication, "REPOSITORY", migration.LEGACY_REPOSITORY):
        controls = publication.control_artifacts(manifest)
    assets = [
        {
            "id": 101,
            "name": manifest["assets"][0]["remote_filename"],
            "size_bytes": 7,
            "api_digest": "sha256:" + hashlib.sha256(b"fixture").hexdigest(),
            "download_sha256": hashlib.sha256(b"fixture").hexdigest(),
            "state": "uploaded",
        }
    ]
    for index, (name, data) in enumerate(controls.items(), 102):
        digest = hashlib.sha256(data).hexdigest()
        assets.append(
            {
                "id": index,
                "name": name,
                "size_bytes": len(data),
                "api_digest": "sha256:" + digest,
                "download_sha256": digest,
                "state": "uploaded",
            }
        )
    before = {
        "schema_version": 1,
        "observed_at": "2026-11-10T01:00:00+00:00",
        "repository_id": migration.REPOSITORY_ID,
        "repository": migration.LEGACY_REPOSITORY,
        "release_api_url": f"https://api.github.com/repos/{migration.LEGACY_REPOSITORY}/releases/17",
        "verification": "full-download-sha256",
        "distribution_commit_sha": "d" * 40,
        "tag_ref": None,
        "release": {
            "id": 17,
            "tag_name": manifest["tag"],
            "target_commitish": "d" * 40,
            "draft": True,
            "author": migration.PUBLISHER,
            "body": "OCF publication manifest SHA-256: " + migration.identity(manifest),
            "upload_url": f"https://uploads.github.com/repos/{migration.LEGACY_REPOSITORY}/releases/17/assets{{?name,label}}",
        },
        "assets": assets,
    }
    after = copy.deepcopy(before)
    after["observed_at"] = "2026-11-10T02:00:00+00:00"
    after["repository"] = migration.REPOSITORY
    after["release_api_url"] = before["release_api_url"].replace(
        "meramsey/", "ocfproject-org/"
    )
    after["release"]["upload_url"] = before["release"]["upload_url"].replace(
        "meramsey/", "ocfproject-org/"
    )
    return manifest, before, after


def synthetic_approval(attestation):
    return {
        "schema_version": 1,
        "purpose": migration.APPROVAL_PURPOSE,
        "owner": migration.PUBLISHER,
        "approved_at": "2026-11-10T03:00:00+00:00",
        "attestation_sha256": migration.identity(attestation),
        "reconcile": True,
        "publish": False,
    }


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.before, self.after = evidence()

    def propose(self):
        return migration.build_attestation(
            self.manifest, self.before, self.after, now=NOW
        )

    def test_exact_binding_preserves_inputs_and_all_frozen_controls(self):
        original = copy.deepcopy((self.manifest, self.before, self.after))
        attestation = self.propose()
        result = migration.verify_reconciliation(
            self.manifest,
            self.before,
            self.after,
            attestation,
            synthetic_approval(attestation),
            now=NOW,
        )
        self.assertEqual((self.manifest, self.before, self.after), original)
        self.assertEqual(result["state"], "reconciled-publication-held")
        self.assertIs(result["publication_allowed"], False)
        self.assertNotIn("phase", result)  # Not a publisher/catalog receipt.
        self.assertEqual(len(attestation["assets"]), 4)
        self.assertEqual(
            attestation["original_manifest_sha256"], migration.identity(self.manifest)
        )
        destination = dict(self.manifest, repository=migration.REPOSITORY)
        self.assertEqual(
            attestation["destination_manifest_sha256"],
            publication.manifest_digest(destination),
        )
        self.assertNotEqual(
            attestation["original_manifest_sha256"],
            attestation["destination_manifest_sha256"],
        )
        with self.assertRaisesRegex(ValueError, "unexpected distribution repository"):
            publication.validate_manifest(self.manifest)
        with self.assertRaisesRegex(ValueError, "unexpected distribution repository"):
            publication.control_artifacts(self.manifest)

    def test_arbitrary_destinations_and_repository_replacements_rejected(self):
        for key, value in (
            ("repository", "other/open-consciousness-functions-audio"),
            ("repository", migration.LEGACY_REPOSITORY),
            ("repository_id", migration.REPOSITORY_ID + 1),
            ("repository_id", str(migration.REPOSITORY_ID)),
        ):
            with self.subTest(key=key, value=value):
                _, self.before, self.after = evidence()
                self.after[key] = value
                with self.assertRaises(ValueError):
                    self.propose()

    def test_changed_release_or_wrong_upload_url_rejected(self):
        changes = (
            ("id", 18),
            ("id", True),
            ("tag_name", "other"),
            ("target_commitish", "e" * 40),
            ("target_commitish", "main"),
            ("draft", False),
            ("draft", 1),
            ("author", "ocfproject-org"),
            ("author", "other"),
            ("body", "changed"),
            ("upload_url", self.before["release"]["upload_url"]),
            ("upload_url", self.after["release"]["upload_url"] + "?x=1"),
        )
        for key, value in changes:
            with self.subTest(key=key, value=value):
                _, self.before, self.after = evidence()
                self.after["release"][key] = value
                with self.assertRaises(ValueError):
                    self.propose()

    def test_partial_duplicate_replaced_and_modified_assets_rejected(self):
        mutations = (
            lambda a: a.pop(),
            lambda a: a.append(copy.deepcopy(a[0])),
            lambda a: a[1].update(id=a[0]["id"]),
            lambda a: a[1].update(name=a[0]["name"]),
            lambda a: a[0].update(id=999),
            lambda a: a[0].update(id=True),
            lambda a: a[0].update(name="different.flac"),
            lambda a: a[0].update(size_bytes=8),
            lambda a: a[0].update(state="new"),
            lambda a: a[0].update(api_digest=None),
            lambda a: a[0].update(download_sha256="f" * 64),
        )
        for mutate in mutations:
            _, self.before, self.after = evidence()
            mutate(self.after["assets"])
            with self.assertRaises(ValueError):
                self.propose()

    def test_rewritten_control_asset_is_rejected(self):
        controls = publication.control_artifacts(
            dict(self.manifest, repository=migration.REPOSITORY)
        )
        for asset in self.after["assets"]:
            if asset["name"] == "publication.json":
                data = controls[asset["name"]]
                asset.update(
                    size_bytes=len(data),
                    api_digest="sha256:" + hashlib.sha256(data).hexdigest(),
                    download_sha256=hashlib.sha256(data).hexdigest(),
                )
        with self.assertRaises(ValueError):
            self.propose()

    def test_distribution_commit_and_tag_identity_must_survive(self):
        self.after["distribution_commit_sha"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "commit lookup"):
            self.propose()
        self.manifest, self.before, self.after = evidence()
        ref = {
            "ref": "refs/tags/" + self.manifest["tag"],
            "object_type": "tag",
            "object_sha": "e" * 40,
            "peeled_commit": "d" * 40,
        }
        self.before["tag_ref"] = dict(ref)
        self.after["tag_ref"] = dict(ref)
        self.assertEqual(self.propose()["tag_ref"], ref)
        self.after["tag_ref"]["object_sha"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "tag reference changed"):
            self.propose()
        self.after["tag_ref"] = dict(ref, peeled_commit="f" * 40)
        with self.assertRaisesRegex(ValueError, "tag points to another"):
            self.propose()

    def test_api_only_and_ambiguous_evidence_are_rejected(self):
        for key, value in (
            ("verification", "github-api-digest"),
            ("observed_at", self.before["observed_at"]),
            ("observed_at", "2026-11-10T02:00:00"),
            ("observed_at", "2099-01-01T00:00:00Z"),
            ("release_api_url", "https://example.org/release"),
            ("approved", True),
        ):
            with self.subTest(key=key):
                _, self.before, self.after = evidence()
                self.after[key] = value
                with self.assertRaises(ValueError):
                    self.propose()

    def test_proposal_cannot_authorize_itself_or_reuse_old_approval(self):
        attestation = self.propose()
        for approval in (
            attestation,
            {},
            dict(
                synthetic_approval(attestation),
                attestation_sha256=migration.identity(self.manifest),
            ),
        ):
            with self.assertRaises(ValueError):
                migration.verify_reconciliation(
                    self.manifest,
                    self.before,
                    self.after,
                    attestation,
                    approval,
                    now=NOW,
                )
        attestation["approved"] = True
        with self.assertRaisesRegex(ValueError, "exact transfer evidence"):
            migration.verify_reconciliation(
                self.manifest,
                self.before,
                self.after,
                attestation,
                synthetic_approval(attestation),
                now=NOW,
            )

    def test_new_approval_is_exact_and_never_a_publication_gate(self):
        attestation = self.propose()
        for key, value in (
            ("owner", "ocfproject-org"),
            ("owner", "other"),
            ("purpose", "publish"),
            ("schema_version", True),
            ("reconcile", 1),
            ("reconcile", False),
            ("publish", True),
            ("publish", 0),
            ("approved_at", self.before["observed_at"]),
            ("approved_at", "2099-01-01T00:00:00Z"),
        ):
            with self.subTest(key=key, value=value):
                approval = dict(synthetic_approval(attestation), **{key: value})
                with self.assertRaises(ValueError):
                    migration.verify_reconciliation(
                        self.manifest,
                        self.before,
                        self.after,
                        attestation,
                        approval,
                        now=NOW,
                    )

    def test_snapshot_replay_requires_new_approval_even_for_same_assets(self):
        attestation = self.propose()
        approval = synthetic_approval(attestation)
        self.after["observed_at"] = "2026-11-10T02:30:00+00:00"
        current = self.propose()
        with self.assertRaisesRegex(ValueError, "exact transfer attestation"):
            migration.verify_reconciliation(
                self.manifest, self.before, self.after, current, approval, now=NOW
            )

    def test_cli_requires_separate_approval_and_exclusive_new_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            args = []
            for name, value in zip(
                ("manifest", "before", "after"),
                (self.manifest, self.before, self.after),
            ):
                path = root / (name + ".json")
                path.write_bytes(publication.canonical_bytes(value))
                args.append(str(path))
            proposal_path, approval_path, report_path = [
                root / (name + ".json") for name in ("proposal", "approval", "report")
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                migration.main(["propose", *args, "--output", str(proposal_path)])
            proposal = json.loads(proposal_path.read_text())
            self.assertNotIn("approved", proposal)
            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                migration.main(
                    ["verify", *args, str(proposal_path), "--output", str(report_path)]
                )
            approval_path.write_bytes(
                publication.canonical_bytes(synthetic_approval(proposal))
            )
            verify = [
                "verify",
                *args,
                str(proposal_path),
                "--approval",
                str(approval_path),
                "--output",
                str(report_path),
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                migration.main(verify)
            saved = report_path.read_bytes()
            with self.assertRaises(FileExistsError):
                migration.main(verify)
            self.assertEqual(saved, report_path.read_bytes())
            self.assertIs(json.loads(saved)["publication_allowed"], False)

    def test_json_parser_rejects_duplicate_keys_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "ambiguous.json"
            for raw in ('{"id": 1, "id": 2}', '{"n": NaN}', '{"n": Infinity}'):
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    migration.load_json(path)


if __name__ == "__main__":
    unittest.main()
