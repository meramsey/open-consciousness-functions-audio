"""Finalization-only transferred-draft adapter. No uploads, creation or repair.

The caller supplies authentic private approvals; JSON cannot authenticate an
owner. Default execution is read-only. The committed registry initially trusts
no releases. See TRANSFER_PROTOCOL.md before any production invocation.
"""

import copy
import os
import re
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from github_publisher import GitHub
from publication import (
    REPOSITORY,
    _verify_approval_digest,
    canonical_bytes,
    fields,
    require,
)
from publisher import save_receipt
from reconcile_historical_transfer import MODE, verify_reconciliation_v2
from reconcile_transfer import (
    PUBLISHER,
    REPOSITORY_ID,
    expected_inventory,
    identity,
    legacy_controls,
    load_json,
    positive_id,
    timestamp,
    validate_snapshot,
    verify_reconciliation,
)
from transfer_registry import DEFAULT_ROOT, load_registry

ROOT = Path(__file__).resolve().parents[1]
RELEASE_STATE_ROOT = Path.home() / ".local" / "state" / "ocf-transfer-finalizer"
SOURCE = "ocfproject-org/open-consciousness-functions"
SOURCE_ID = 1367603146
REQUIRED_WORKFLOWS = {
    SOURCE: ("test.yml", "lint.yml", "validate.yml", "generated-index-check.yml"),
    REPOSITORY: ("validate.yml",),
}
PURPOSE = "publish-transferred-draft"
RECEIPT_PURPOSE = "ocf-transferred-draft-finalization"


def durable_exclusive(path, record):
    with path.open("xb") as stream:
        stream.write(canonical_bytes(record))
        stream.flush()
        os.fsync(stream.fileno())
    if hasattr(os, "O_DIRECTORY"):
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


@contextmanager
def release_writer_lock(release_id):
    positive_id(release_id)
    root = RELEASE_STATE_ROOT.absolute()
    require(
        not any(p.is_symlink() for p in (root, *root.parents)),
        "symlink in release state path",
    )
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = root / f"{REPOSITORY_ID}-{release_id}.lock"
    durable_exclusive(lock, {"pid": os.getpid(), "release_id": release_id})
    try:
        yield
    finally:
        lock.unlink()


def commit(value):
    require(
        type(value) is str and re.fullmatch(r"[a-f0-9]{40}", value),
        "expected full commit SHA",
    )


def verify_final_approval(bundle, registry, original, reconciliation, approval, now):
    manifest, attestation = bundle["manifest"], bundle["attestation"]
    legacy_controls(manifest)
    _verify_approval_digest(identity(manifest), original)
    require(
        timestamp(original["approved_at"]) <= now, "original approval is from future"
    )
    v2 = bundle["schema_version"] == 2
    if v2:
        require(bundle.get("mode") == MODE, "unsupported transfer mode")
        require(
            identity(original)
            == attestation["original_rights_approval_canonical_sha256"],
            "original rights differ from historical provenance",
        )
        verify_reconciliation_v2(
            manifest,
            bundle["historical"],
            bundle["after"],
            attestation,
            reconciliation,
            now=now,
        )
    else:
        require(bundle["schema_version"] == 1, "unsupported transfer bundle")
        verify_reconciliation(
            manifest,
            bundle["before"],
            bundle["after"],
            attestation,
            reconciliation,
            now=now,
        )
    extra = ("mode", "uncertainty_acknowledgement_canonical_sha256") if v2 else ()
    fields(
        approval,
        (
            "schema_version",
            "purpose",
            "owner",
            "approved_at",
            "expires_at",
            "repository",
            "repository_id",
            "release_id",
            "tag",
            "distribution_commit",
            "original_manifest_sha256",
            "destination_manifest_sha256",
            "attestation_sha256",
            "bundle_sha256",
            "registry_sha256",
            "original_approval_sha256",
            "reconciliation_approval_sha256",
            "ci_commits",
            "allow_tag_creation",
            "public_assets",
            "voice_redistribution",
            "artwork_redistribution",
            "release_hold_lifted",
            "publish",
            *extra,
        ),
    )
    require(
        type(approval["schema_version"]) is int
        and approval["schema_version"] == (2 if v2 else 1),
        "unsupported final approval schema",
    )
    bindings = {
        "purpose": PURPOSE,
        "owner": PUBLISHER,
        "repository": REPOSITORY,
        "repository_id": REPOSITORY_ID,
        "release_id": attestation["release_id"],
        "tag": attestation["tag"],
        "distribution_commit": attestation["distribution_commit"],
        "original_manifest_sha256": identity(manifest),
        "destination_manifest_sha256": attestation["destination_manifest_sha256"],
        "attestation_sha256": identity(attestation),
        "bundle_sha256": identity(bundle),
        "registry_sha256": registry.index_sha256,
        "original_approval_sha256": identity(original),
        "reconciliation_approval_sha256": identity(reconciliation),
    }
    if v2:
        bindings.update(
            mode=MODE,
            uncertainty_acknowledgement_canonical_sha256=attestation[
                "uncertainty_acknowledgement_canonical_sha256"
            ],
        )
    for key, expected in bindings.items():
        require(
            type(approval[key]) is type(expected) and approval[key] == expected,
            "final approval binding mismatch: " + key,
        )
    for key in (
        "public_assets",
        "voice_redistribution",
        "artwork_redistribution",
        "release_hold_lifted",
        "publish",
    ):
        require(approval[key] is True, "final approval missing: " + key)
    require(
        approval["allow_tag_creation"] is (attestation["tag_ref"] is None),
        "tag creation needs exact approval",
    )
    approved, expires = (
        timestamp(approval["approved_at"]),
        timestamp(approval["expires_at"]),
    )
    require(
        timestamp(reconciliation["approved_at"]) <= approved <= now < expires,
        "final approval is premature or expired",
    )
    require(
        expires - approved <= timedelta(hours=24),
        "final approval lifetime exceeds 24 hours",
    )
    fields(approval["ci_commits"], ("source", "distribution"))
    for sha in approval["ci_commits"].values():
        commit(sha)


def validate_current(snapshot, bundle, now, *, published):
    """Validate current evidence without altering any frozen input."""
    require(
        snapshot["release"]["draft"] is (not published),
        "unexpected current release state",
    )
    controls, _ = legacy_controls(bundle["manifest"])
    normalized = copy.deepcopy(snapshot)
    normalized["release"]["draft"] = True  # Reuse strict invariant validation only.
    observed, release, assets = validate_snapshot(
        normalized,
        REPOSITORY,
        bundle["manifest"],
        expected_inventory(bundle["manifest"], controls),
        now,
    )
    require(now - observed <= timedelta(minutes=5), "current evidence is stale")
    attestation = bundle["attestation"]
    require(release["id"] == attestation["release_id"], "current release ID mismatch")
    require(
        release["target_commitish"] == attestation["distribution_commit"],
        "current target changed",
    )
    require(assets == attestation["assets"], "current asset identity/inventory drift")
    expected_ref = attestation["tag_ref"]
    if published and expected_ref is None:
        expected_ref = {
            "ref": "refs/tags/" + attestation["tag"],
            "object_type": "commit",
            "object_sha": attestation["distribution_commit"],
            "peeled_commit": attestation["distribution_commit"],
        }
    require(snapshot["tag_ref"] == expected_ref, "current tag reference drift")


def finalize_transfer(
    manifest,
    release_id,
    registry,
    original_approval,
    reconciliation_approval,
    final_approval,
    remote,
    receipt_path,
    *,
    execute=False,
    now=None,
):
    """Only a verified existing draft may transition to published; never repair it.

    Pending/uncertain mutation receipts cannot cause a second PATCH. A replay may
    only verify an already-published exact release, otherwise it stops for the
    supervisor. A new receipt/approval cannot silently adopt a published release.
    """

    def clock():
        return now if now is not None else datetime.now(UTC)

    bundle = registry.resolve(manifest, release_id)
    verify_final_approval(
        bundle,
        registry,
        original_approval,
        reconciliation_approval,
        final_approval,
        clock(),
    )
    require(remote.repository == REPOSITORY, "transport destination mismatch")
    require(
        not execute or remote.can_finalize,
        "read-only transfer transport cannot finalize",
    )
    remote.verify_execution_context(
        final_approval["ci_commits"]["distribution"], registry
    )
    ci = remote.verify_ci(final_approval["ci_commits"])
    path = Path(receipt_path).absolute()
    require(
        not any(p.is_symlink() for p in (path, *path.parents)),
        "symlink in receipt path",
    )
    binding = {
        "schema_version": 1,
        "purpose": RECEIPT_PURPOSE,
        "release_id": release_id,
        "repository_id": REPOSITORY_ID,
        "attestation_sha256": identity(bundle["attestation"]),
        "final_approval_sha256": identity(final_approval),
        "registry_sha256": registry.index_sha256,
    }
    if bundle["schema_version"] == 2:
        binding.update(
            schema_version=2,
            mode=MODE,
            uncertainty_acknowledgement_canonical_sha256=bundle["attestation"][
                "uncertainty_acknowledgement_canonical_sha256"
            ],
        )
    lock = path.with_suffix(path.suffix + ".lock")
    # Same receipt is the serialization boundary; supervisor must also enforce
    # one owner per release across hosts. Never delete an unexplained stale lock.
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()) + "\n")
    try:
        prior = None
        if path.exists():
            prior = load_json(path)
            fields(prior, (*binding, "state", "ci", "tag_ref"))
            require(
                all(prior[k] == v for k, v in binding.items()),
                "receipt belongs to another operation",
            )
            require(
                prior["state"]
                in ("finalize-requested", "mutation-attempted", "published-verified"),
                "unknown receipt state",
            )
        current = remote.snapshot(download=True)
        is_published = current["release"]["draft"] is False
        validate_current(current, bundle, clock(), published=is_published)
        if prior:
            require(
                is_published,
                "previous finalization outcome unresolved; no automatic retry",
            )
            receipt = dict(
                binding, state="published-verified", ci=ci, tag_ref=current["tag_ref"]
            )
            if execute:
                save_receipt(path, receipt)
            return receipt
        require(
            not is_published,
            "published release has no matching prior intent; never adopt it",
        )
        if not execute:
            return dict(
                binding,
                state="verified-draft-no-mutation",
                ci=ci,
                tag_ref=current["tag_ref"],
            )
        # Recheck CI/main, identities, and the unchanged current inventory at the
        # last boundary. Cached byte hashes may be reused only for identical API
        # metadata from this same call's full download verification.
        ci = remote.verify_ci(final_approval["ci_commits"])
        fresh = remote.snapshot(download=False)
        validate_current(fresh, bundle, clock(), published=False)
        remote.verify_execution_context(
            final_approval["ci_commits"]["distribution"], registry
        )
        verify_final_approval(
            bundle,
            registry,
            original_approval,
            reconciliation_approval,
            final_approval,
            clock(),
        )
        pending = dict(
            binding, state="finalize-requested", ci=ci, tag_ref=fresh["tag_ref"]
        )
        save_receipt(path, pending)  # Durable before the only permitted mutation.
        try:
            remote.finalize_existing(
                release_id,
                registry=registry,
                original_approval=original_approval,
                reconciliation_approval=reconciliation_approval,
                final_approval=final_approval,
                intent_path=path,
            )
        except (ValueError, OSError, subprocess.TimeoutExpired):
            # Read-only reconciliation even when the response was lost. Leave
            # intent durable if readback is missing, fails, or still says draft.
            terminal = remote.snapshot(download=False)
            require(
                terminal["release"]["draft"] is False,
                "finalization outcome uncertain; reconcile intent before retry",
            )
        else:
            terminal = remote.snapshot(download=False)
        validate_current(terminal, bundle, clock(), published=True)
        receipt = dict(
            binding, state="published-verified", ci=ci, tag_ref=terminal["tag_ref"]
        )
        save_receipt(path, receipt)
        return receipt
    finally:
        lock.unlink()


class TransferGitHub:
    """Restricted native transport; no create/upload/delete or marker edits."""

    repository = REPOSITORY

    def __init__(self, attestation, *, execute=False):
        positive_id(attestation["release_id"])
        commit(attestation["distribution_commit"])
        self.attestation = copy.deepcopy(attestation)
        self._execute = execute
        self._api = GitHub(None)
        self._verified = None

    @property
    def can_finalize(self):
        return self._execute is True

    def verify_execution_context(self, expected_commit, registry):
        require(
            registry.root == DEFAULT_ROOT.resolve(),
            "execution requires the committed default registry",
        )
        require(
            load_registry().index_sha256 == registry.index_sha256,
            "registry changed since approval/loading",
        )
        for args, expected in (
            (["rev-parse", "HEAD"], expected_commit),
            (["status", "--porcelain=v1"], ""),
        ):
            result = subprocess.run(
                ["git", "-C", str(ROOT), *args],
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            require(
                result.returncode == 0 and result.stdout.strip() == expected,
                "execution requires clean exact approved code commit",
            )

    def verify_ci(self, commits):
        evidence = []
        for repository, key, repo_id in (
            (SOURCE, "source", SOURCE_ID),
            (REPOSITORY, "distribution", REPOSITORY_ID),
        ):
            sha = commits[key]
            commit(sha)
            base = "repos/" + repository
            repo = self._api.api(base)
            require(
                repo["id"] == repo_id
                and repo["full_name"] == repository
                and repo["default_branch"] == "main",
                "CI repository identity mismatch",
            )
            main = self._api.api(base + "/commits/main")
            require(main["sha"] == sha, "approved CI commit is not current main")
            for workflow in REQUIRED_WORKFLOWS[repository]:
                runs, total = [], None
                endpoint = (
                    base
                    + "/actions/workflows/"
                    + workflow
                    + "/runs?branch=main&event=push&head_sha="
                    + sha
                    + "&per_page=100"
                )
                for page in range(1, 11):
                    response = self._api.api(endpoint + "&page=" + str(page))
                    count = response["total_count"]
                    require(
                        type(count) is int and 0 <= count <= 1000,
                        "CI run inventory exceeds bounded verification",
                    )
                    require(
                        total is None or total == count,
                        "CI run inventory changed during pagination",
                    )
                    total = count
                    batch = response["workflow_runs"]
                    require(
                        type(batch) is list and len(batch) <= 100, "invalid CI run page"
                    )
                    runs.extend(batch)
                    require(
                        len({r["id"] for r in runs}) == len(runs),
                        "duplicate CI run inventory",
                    )
                    if len(runs) >= total:
                        break
                    require(bool(batch), "partial CI run inventory")
                require(len(runs) == total, "partial CI run inventory")
                require(runs, "required main workflow run missing: " + workflow)
                require(
                    all(r["status"] == "completed" for r in runs),
                    "required exact-main CI still has an active attempt: " + workflow,
                )
                # A rerun of an older-created run may be the latest activity.
                run = max(
                    runs,
                    key=lambda r: (
                        timestamp(r["updated_at"]),
                        r["id"],
                        r["run_attempt"],
                    ),
                )
                require(
                    run["head_sha"] == sha
                    and run["head_branch"] == "main"
                    and run["event"] == "push"
                    and run["repository"]["id"] == repo_id
                    and run["path"] == ".github/workflows/" + workflow
                    and run["status"] == "completed"
                    and run["conclusion"] == "success",
                    "required exact-main CI is not successful: " + workflow,
                )
                evidence.append(
                    {
                        "repository": repository,
                        "workflow": workflow,
                        "run_id": run["id"],
                        "attempt": run["run_attempt"],
                        "head_sha": sha,
                    }
                )
        return evidence

    def _metadata(self):
        base = self._api.base
        repo = self._api.api(base)
        release = self._api.api(base + f"/releases/{self.attestation['release_id']}")
        target = release["target_commitish"]
        commit(target)
        tag = quote(self.attestation["tag"], safe="")
        refs = self._api.api(base + "/git/matching-refs/tags/" + tag)
        refs = [r for r in refs if r["ref"] == "refs/tags/" + self.attestation["tag"]]
        require(len(refs) <= 1, "ambiguous tag reference")
        tag_ref = None
        if refs:
            obj = refs[0]["object"]
            initial = dict(obj)
            seen = set()
            while obj["type"] == "tag":
                commit(obj["sha"])
                require(
                    obj["sha"] not in seen and len(seen) < 8, "tag cycle/depth exceeded"
                )
                seen.add(obj["sha"])
                obj = self._api.api(base + "/git/tags/" + obj["sha"])["object"]
            require(obj["type"] == "commit", "tag does not resolve to commit")
            tag_ref = {
                "ref": refs[0]["ref"],
                "object_type": initial["type"],
                "object_sha": initial["sha"],
                "peeled_commit": obj["sha"],
            }
        assets = self._api.list_assets(self.attestation["release_id"])
        return {
            "schema_version": 1,
            "repository": repo["full_name"],
            "repository_id": repo["id"],
            "release_api_url": f"https://api.github.com/{base}/releases/{self.attestation['release_id']}",
            "verification": "full-download-sha256",
            "distribution_commit_sha": self._api.api(base + "/commits/" + target)[
                "sha"
            ],
            "tag_ref": tag_ref,
            "release": {
                k: release[k]
                for k in (
                    "id",
                    "tag_name",
                    "target_commitish",
                    "draft",
                    "body",
                    "upload_url",
                )
            }
            | {"author": release["author"]["login"]},
            "assets": sorted(
                [
                    {
                        "id": a["id"],
                        "name": a["name"],
                        "size_bytes": a["size"],
                        "state": a["state"],
                        "api_digest": a.get("digest"),
                    }
                    for a in assets
                ],
                key=lambda a: a["id"],
            ),
        }

    def snapshot(self, *, download):
        before = self._metadata()
        # No inferred download proof: reuse only hashes actually read in this
        # transport instance, with byte-identifying metadata unchanged.
        if download:
            hashes = {a["id"]: self._api.sha256(a["id"]) for a in before["assets"]}
        else:
            require(
                self._verified is not None and before["assets"] == self._verified[0],
                "inventory drift invalidates downloaded-byte cache",
            )
            hashes = self._verified[1]
        after = self._metadata()
        require(before == after, "remote state changed during snapshot")
        self._verified = (copy.deepcopy(after["assets"]), hashes)
        after["observed_at"] = datetime.now(UTC).isoformat()
        for asset in after["assets"]:
            asset["download_sha256"] = hashes[asset["id"]]
        return after

    def finalize_existing(self, release_id, **kwargs):
        with release_writer_lock(release_id):
            return self._finalize_existing_locked(release_id, **kwargs)

    def _finalize_existing_locked(
        self,
        release_id,
        *,
        registry,
        original_approval,
        reconciliation_approval,
        final_approval,
        intent_path,
    ):
        require(self._execute, "read-only transfer transport cannot finalize")
        require(
            release_id == self.attestation["release_id"],
            "unexpected finalization target",
        )
        bundle = registry.for_release(release_id)
        require(
            bundle["attestation"] == self.attestation, "transport attestation mismatch"
        )
        now = datetime.now(UTC)
        verify_final_approval(
            bundle,
            registry,
            original_approval,
            reconciliation_approval,
            final_approval,
            now,
        )
        self.verify_execution_context(
            final_approval["ci_commits"]["distribution"], registry
        )
        self.verify_ci(final_approval["ci_commits"])
        intent = load_json(intent_path)
        require(
            intent.get("purpose") == RECEIPT_PURPOSE
            and intent.get("state") == "finalize-requested"
            and intent.get("repository_id") == REPOSITORY_ID
            and intent.get("release_id") == release_id
            and intent.get("attestation_sha256") == identity(self.attestation)
            and intent.get("final_approval_sha256") == identity(final_approval)
            and intent.get("registry_sha256") == registry.index_sha256,
            "finalization needs the matching durable intent",
        )
        if bundle["schema_version"] == 2:
            require(
                intent.get("schema_version") == 2
                and intent.get("mode") == MODE
                and intent.get("uncertainty_acknowledgement_canonical_sha256")
                == self.attestation["uncertainty_acknowledgement_canonical_sha256"],
                "intent mode or uncertainty acknowledgement mismatch",
            )
        else:
            require(
                "mode" not in intent
                and "uncertainty_acknowledgement_canonical_sha256" not in intent,
                "v1 intent cannot contain v2 mode",
            )
        validate_current(
            self.snapshot(download=False), bundle, datetime.now(UTC), published=False
        )
        verify_final_approval(
            bundle,
            registry,
            original_approval,
            reconciliation_approval,
            final_approval,
            datetime.now(UTC),
        )
        # Durable one-attempt guard also protects direct native calls and
        # concurrent callers. Never remove/reuse this marker after any outcome.
        intent_path = Path(intent_path).absolute()
        attempt = intent_path.with_suffix(intent_path.suffix + ".attempt")
        # Permanent release-wide attempt marker prevents switching receipt paths
        # after a lost response. It is never automatically removed or reset.
        release_attempt = RELEASE_STATE_ROOT / f"{REPOSITORY_ID}-{release_id}.attempt"
        attempt_record = {
            "purpose": "ocf-transfer-mutation-attempt",
            "intent_sha256": identity(intent),
            "mode": bundle.get("mode", "strict-v1"),
            "attestation_sha256": identity(self.attestation),
        }
        if bundle["schema_version"] == 2:
            attempt_record["uncertainty_acknowledgement_canonical_sha256"] = (
                self.attestation["uncertainty_acknowledgement_canonical_sha256"]
            )
        durable_exclusive(release_attempt, attempt_record)
        durable_exclusive(attempt, attempt_record)
        save_receipt(intent_path, dict(intent, state="mutation-attempted"))
        # This adapter has exactly one mutation shape and rechecks every gate at
        # the transport boundary too. No standalone unapproved PATCH route.
        self._api.api(
            self._api.base + f"/releases/{release_id}",
            method="PATCH",
            body={"draft": False, "make_latest": "false"},
        )


def main(argv=None):
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--release-id", required=True, type=int)
    parser.add_argument("--original-approval", required=True, type=Path)
    parser.add_argument("--reconciliation-approval", required=True, type=Path)
    parser.add_argument("--final-approval", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="finalize only after all exact approval/CI gates",
    )
    args = parser.parse_args(argv)
    registry = load_registry()
    manifest = load_json(args.manifest)
    bundle = registry.resolve(manifest, args.release_id)
    approvals = [
        load_json(p)
        for p in (
            args.original_approval,
            args.reconciliation_approval,
            args.final_approval,
        )
    ]
    # Verify locally before constructing any transport or doing network reads.
    verify_final_approval(bundle, registry, *approvals, datetime.now(UTC))
    result = finalize_transfer(
        manifest,
        args.release_id,
        registry,
        *approvals,
        TransferGitHub(bundle["attestation"], execute=args.execute),
        args.receipt,
        execute=args.execute,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, TypeError, KeyError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(str(exc)) from exc
