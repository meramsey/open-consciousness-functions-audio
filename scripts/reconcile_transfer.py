"""Offline, fail-closed evidence validation for the OCF organization transfer.

No network, asset copying, approval generation, publication or receipt adoption.
Inputs are evidence, not proof of authenticity: approval must come separately
from the trusted operator authorization channel. See docs/TRANSFER_PROTOCOL.md.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from publication import (
    REPOSITORY,
    _control_artifacts,
    canonical_bytes,
    fields,
    require,
    validate_manifest,
)

LEGACY_REPOSITORY = "meramsey/open-consciousness-functions-audio"
REPOSITORY_ID = 1437852834
PUBLISHER = "meramsey"
PURPOSE = "ocf-repository-transfer-evidence"
APPROVAL_PURPOSE = "approve-ocf-transfer-reconciliation"
MAX_JSON_BYTES = 8 * 1024 * 1024


def identity(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def timestamp(value):
    require(type(value) is str, "timestamp must be text")
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, "timestamp needs timezone")
    return result


def positive_id(value):
    require(type(value) is int and value > 0, "expected positive integer ID")


def legacy_controls(manifest):
    require(type(manifest) is dict, "expected legacy manifest object")
    require(
        manifest.get("repository") == LEGACY_REPOSITORY,
        "unexpected original repository",
    )
    # Validate every field against the unchanged schema, with only the fixed
    # destination substituted. Neither input nor frozen control bytes are edited.
    destination_manifest = dict(manifest, repository=REPOSITORY)
    validate_manifest(destination_manifest)
    return _control_artifacts(manifest), destination_manifest


def expected_inventory(manifest, controls):
    result = {
        asset["remote_filename"]: {
            "asset_id": asset["asset_id"],
            "size_bytes": asset["size_bytes"],
            "sha256": asset["sha256"],
        }
        for asset in manifest["assets"]
    }
    for name, data in controls.items():
        result[name] = {
            "asset_id": "control:" + name,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return result


def validate_snapshot(snapshot, repository, manifest, expected, now):
    fields(
        snapshot,
        (
            "schema_version",
            "observed_at",
            "repository_id",
            "repository",
            "release_api_url",
            "release",
            "assets",
            "verification",
            "distribution_commit_sha",
            "tag_ref",
        ),
    )
    require(
        type(snapshot["schema_version"]) is int and snapshot["schema_version"] == 1,
        "unsupported snapshot schema",
    )
    require(
        type(snapshot["repository_id"]) is int
        and snapshot["repository_id"] == REPOSITORY_ID,
        "repository stable ID mismatch",
    )
    require(snapshot["repository"] == repository, "snapshot destination mismatch")
    observed = timestamp(snapshot["observed_at"])
    require(observed <= now, "snapshot is from the future")
    require(
        snapshot["verification"] == "full-download-sha256",
        "full downloaded-byte evidence required; API digests alone are insufficient",
    )
    release = snapshot["release"]
    fields(
        release,
        ("id", "tag_name", "target_commitish", "draft", "author", "body", "upload_url"),
    )
    positive_id(release["id"])
    require(
        snapshot["release_api_url"]
        == f"https://api.github.com/repos/{repository}/releases/{release['id']}",
        "release evidence endpoint mismatch",
    )
    require(release["draft"] is True, "release is not an unpublished draft")
    require(release["author"] == PUBLISHER, "unexpected human publisher")
    require(release["tag_name"] == manifest["tag"], "release tag mismatch")
    require(
        type(release["target_commitish"]) is str
        and len(release["target_commitish"]) == 40
        and all(c in "0123456789abcdef" for c in release["target_commitish"]),
        "distribution target must be a full commit SHA",
    )
    require(
        snapshot["distribution_commit_sha"] == release["target_commitish"],
        "distribution commit lookup mismatch",
    )
    tag_ref = snapshot["tag_ref"]
    if tag_ref is not None:
        fields(tag_ref, ("ref", "object_type", "object_sha", "peeled_commit"))
        require(
            tag_ref["ref"] == "refs/tags/" + manifest["tag"], "tag reference mismatch"
        )
        require(
            tag_ref["object_type"] in ("tag", "commit"), "unexpected tag object type"
        )
        require(
            type(tag_ref["object_sha"]) is str
            and len(tag_ref["object_sha"]) == 40
            and all(c in "0123456789abcdef" for c in tag_ref["object_sha"]),
            "tag object must have a full SHA",
        )
        require(
            tag_ref["peeled_commit"] == release["target_commitish"],
            "tag points to another distribution commit",
        )
        if tag_ref["object_type"] == "commit":
            require(
                tag_ref["object_sha"] == tag_ref["peeled_commit"],
                "lightweight tag object mismatch",
            )
    require(
        release["body"] == "OCF publication manifest SHA-256: " + identity(manifest),
        "frozen release marker mismatch",
    )
    upload = (
        f"https://uploads.github.com/repos/{repository}/releases/{release['id']}/assets"
    )
    require(
        release["upload_url"] in (upload, upload + "{?name,label}"),
        "unexpected GitHub upload URL",
    )
    assets = snapshot["assets"]
    require(
        type(assets) is list and len(assets) == len(expected),
        "incomplete or extra asset inventory",
    )
    names, remote_ids = set(), set()
    inventory = []
    for asset in assets:
        fields(
            asset,
            ("id", "name", "size_bytes", "api_digest", "download_sha256", "state"),
        )
        positive_id(asset["id"])
        require(
            type(asset["name"]) is str and asset["name"] in expected,
            "unexpected remote asset name",
        )
        require(
            asset["id"] not in remote_ids and asset["name"] not in names,
            "duplicate remote asset ID or name",
        )
        names.add(asset["name"])
        remote_ids.add(asset["id"])
        target = expected[asset["name"]]
        require(
            type(asset["size_bytes"]) is int
            and asset["size_bytes"] == target["size_bytes"],
            "asset size mismatch",
        )
        require(asset["state"] == "uploaded", "asset is not uploaded")
        require(
            asset["api_digest"] == "sha256:" + target["sha256"],
            "API asset digest mismatch or missing",
        )
        require(
            asset["download_sha256"] == target["sha256"],
            "downloaded asset checksum mismatch",
        )
        inventory.append(dict(target, remote_id=asset["id"], name=asset["name"]))
    return observed, release, sorted(inventory, key=lambda a: a["name"])


def build_attestation(manifest, before, after, *, now=None):
    """Build an unapproved proposal only from complete, mutually consistent evidence."""
    now = now if now is not None else datetime.now(UTC)
    controls, destination_manifest = legacy_controls(manifest)
    expected = expected_inventory(manifest, controls)
    before_time, old_release, old_assets = validate_snapshot(
        before, LEGACY_REPOSITORY, manifest, expected, now
    )
    after_time, new_release, new_assets = validate_snapshot(
        after, REPOSITORY, manifest, expected, now
    )
    require(before_time < after_time, "transfer evidence timestamps are not ordered")
    for key in ("id", "tag_name", "target_commitish", "draft", "author", "body"):
        require(
            old_release[key] == new_release[key], "release identity changed: " + key
        )
    require(old_assets == new_assets, "remote asset identities changed during transfer")
    require(
        before["tag_ref"] == after["tag_ref"], "tag reference changed during transfer"
    )
    return {
        "schema_version": 1,
        "purpose": PURPOSE,
        "repository_id": REPOSITORY_ID,
        "original_owner": "meramsey",
        "original_repository": LEGACY_REPOSITORY,
        "destination_owner": "ocfproject-org",
        "destination_repository": REPOSITORY,
        "expected_publisher": PUBLISHER,
        "release_id": old_release["id"],
        "tag": manifest["tag"],
        "distribution_commit": old_release["target_commitish"],
        "tag_ref": before["tag_ref"],
        "original_manifest_sha256": identity(manifest),
        # This virtual manifest is NOT uploaded or substituted for the original.
        "destination_manifest_sha256": identity(destination_manifest),
        "before_snapshot_sha256": identity(before),
        "after_snapshot_sha256": identity(after),
        "assets": old_assets,
    }


def verify_reconciliation(manifest, before, after, attestation, approval, *, now=None):
    """Validate supplied trusted approval; never infer authenticity from JSON alone."""
    now = now if now is not None else datetime.now(UTC)
    expected = build_attestation(manifest, before, after, now=now)
    require(
        canonical_bytes(attestation) == canonical_bytes(expected),
        "attestation does not bind this exact transfer evidence",
    )
    fields(
        approval,
        (
            "schema_version",
            "purpose",
            "owner",
            "approved_at",
            "attestation_sha256",
            "reconcile",
            "publish",
        ),
    )
    require(
        type(approval["schema_version"]) is int and approval["schema_version"] == 1,
        "unsupported reconciliation approval schema",
    )
    require(approval["purpose"] == APPROVAL_PURPOSE, "wrong approval purpose")
    require(approval["owner"] == PUBLISHER, "unexpected approval operator")
    require(
        approval["attestation_sha256"] == identity(expected),
        "approval does not bind this exact transfer attestation",
    )
    approved = timestamp(approval["approved_at"])
    require(
        timestamp(after["observed_at"]) <= approved <= now,
        "approval must follow transfer evidence and not be in the future",
    )
    require(approval["reconcile"] is True, "explicit reconciliation approval missing")
    require(approval["publish"] is False, "reconciliation cannot authorize publication")
    return {
        "schema_version": 1,
        "purpose": "ocf-transfer-reconciliation-result",
        "state": "reconciled-publication-held",
        "repository_id": REPOSITORY_ID,
        "repository": REPOSITORY,
        "release_id": expected["release_id"],
        "attestation_sha256": identity(expected),
        "approval_sha256": identity(approval),
        "original_manifest_sha256": identity(manifest),
        "publication_allowed": False,
    }


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON object key: " + key)
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite JSON number: " + value)


def load_json(path):
    path = Path(path).absolute()
    require(
        not any(p.is_symlink() for p in (path, *path.parents)), "symlink in input path"
    )
    require(path.is_file(), "input must be a regular JSON file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    require(len(raw) <= MAX_JSON_BYTES, "JSON input exceeds 8 MiB")
    return json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("propose", "verify"):
        sub = commands.add_parser(command)
        sub.add_argument("manifest", type=Path)
        sub.add_argument("before", type=Path)
        sub.add_argument("after", type=Path)
        if command == "verify":
            sub.add_argument("attestation", type=Path)
            sub.add_argument("--approval", type=Path, required=True)
        sub.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    inputs = [load_json(path) for path in (args.manifest, args.before, args.after)]
    if args.command == "propose":
        result = build_attestation(*inputs)
    else:
        result = verify_reconciliation(
            *inputs, load_json(args.attestation), load_json(args.approval)
        )
    output = args.output.absolute()
    require(
        not any(p.is_symlink() for p in (output, *output.parents)),
        "symlink in output path",
    )
    with output.open("xb") as stream:
        stream.write(canonical_bytes(result))
    print(
        "Unapproved attestation proposal written."
        if args.command == "propose"
        else "Reconciliation record written; publication remains held."
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, TypeError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc
