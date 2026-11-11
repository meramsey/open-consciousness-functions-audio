"""Explicit historical-receipt reconciliation; never synthesize a v1 snapshot.

Normalized projections cannot authenticate archived files or approval messages.
The trusted supervisor verifies raw-file hashes and provenance outside this tool.
Canonical hashes identify new records; raw hashes identify immutable source bytes.
No network, publication, approval generation, or mutation of existing evidence.
"""

from datetime import UTC, datetime

from publication import REPOSITORY, canonical_bytes, digest, fields, require, text
from reconcile_transfer import (
    LEGACY_REPOSITORY,
    PUBLISHER,
    REPOSITORY_ID,
    expected_inventory,
    identity,
    legacy_controls,
    positive_id,
    timestamp,
    validate_snapshot,
)

MODE = "historical-receipt-v2"
PURPOSE = "ocf-historical-receipt-transfer-evidence"
APPROVAL_PURPOSE = "approve-ocf-historical-transfer-reconciliation"
UNCERTAINTY = {
    "schema_version": 2,
    "mode": MODE,
    "historical_tag_state": "unknown",
    "historical_commit_api_resolution": "unobserved",
    "historical_tag_continuity": "unverified",
    "current_tag_requirement": "observed-absent",
    "authorized_tag_transition": "absent-to-approved-distribution-commit",
}


def _assets(rows, expected, *, receipt):
    require(
        type(rows) is list and len(rows) == len(expected),
        "incomplete historical inventory",
    )
    names, ids, result = set(), set(), []
    for row in rows:
        fields(
            row,
            ("remote_id", "name", "asset_id", "size_bytes", "sha256"),
            ("download_sha256",) if receipt else ("state", "api_digest"),
        )
        # Optional field declarations above are checked as required here too.
        required = ("download_sha256",) if receipt else ("state", "api_digest")
        require(all(k in row for k in required), "missing historical asset evidence")
        positive_id(row["remote_id"])
        require(
            type(row["name"]) is str and row["name"] in expected,
            "unexpected historical asset name",
        )
        require(
            row["name"] not in names and row["remote_id"] not in ids,
            "duplicate historical asset name or ID",
        )
        names.add(row["name"])
        ids.add(row["remote_id"])
        target = expected[row["name"]]
        require(
            type(row["size_bytes"]) is int
            and all(row[k] == target[k] for k in ("asset_id", "size_bytes", "sha256")),
            "historical asset differs from frozen manifest or controls",
        )
        if receipt:
            require(
                row["download_sha256"] == target["sha256"],
                "historical downloaded-byte hash mismatch",
            )
        else:
            require(
                row["state"] == "uploaded"
                and row["api_digest"] == "sha256:" + target["sha256"],
                "historical terminal asset incomplete or digest mismatch",
            )
        result.append(dict(target, remote_id=row["remote_id"], name=row["name"]))
    return sorted(result, key=lambda row: row["name"])


def _archive(record, keys):
    fields(record, ("raw_file_sha256", *keys))
    digest(record["raw_file_sha256"])


def build_attestation_v2(manifest, historical, after, *, now=None):
    now = now if now is not None else datetime.now(UTC)
    controls, destination = legacy_controls(manifest)
    expected = expected_inventory(manifest, controls)
    fields(
        historical,
        (
            "schema_version",
            "mode",
            "repository_id",
            "repository",
            "historical_tag_state",
            "historical_commit_api_resolution",
            "manifest_raw_file_sha256",
            "rights_approval",
            "download_receipt",
            "terminal_inventory",
            "frozen_code",
            "frozen_config",
            "prelaunch_tag_observation",
            "trusted_provenance",
        ),
    )
    require(
        type(historical["schema_version"]) is int and historical["schema_version"] == 2,
        "unsupported historical evidence schema",
    )
    require(historical["mode"] == MODE, "unexpected historical evidence mode")
    require(
        type(historical["repository_id"]) is int
        and historical["repository_id"] == REPOSITORY_ID
        and historical["repository"] == LEGACY_REPOSITORY,
        "historical repository identity mismatch",
    )
    require(
        historical["historical_tag_state"] == "unknown"
        and historical["historical_commit_api_resolution"] == "unobserved",
        "historical gaps must remain explicitly unknown and unobserved",
    )
    require(
        historical["manifest_raw_file_sha256"]
        == expected["publication.json"]["sha256"],
        "original manifest raw-file hash mismatch",
    )
    for key in ("frozen_code", "frozen_config"):
        _archive(historical[key], ("source_id",))
        text(historical[key]["source_id"])
    rights = historical["rights_approval"]
    _archive(
        rights,
        (
            "canonical_sha256",
            "manifest_canonical_sha256",
            "owner",
            "public_assets",
            "voice_redistribution",
            "artwork_redistribution",
            "publish",
            "approved_at",
        ),
    )
    digest(rights["canonical_sha256"])
    require(
        rights["manifest_canonical_sha256"] == identity(manifest),
        "historical rights manifest mismatch",
    )
    text(rights["owner"])  # Preserve the immutable original human-readable label.
    require(
        all(
            rights[k] is True
            for k in ("public_assets", "voice_redistribution", "artwork_redistribution")
        ),
        "historical rights approval missing",
    )
    require(type(rights["publish"]) is bool, "historical publish must be Boolean")
    original_rights = {
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
    original_rights.update(schema_version=1, manifest_sha256=identity(manifest))
    require(
        rights["canonical_sha256"] == identity(original_rights),
        "historical rights canonical projection mismatch",
    )
    receipt = historical["download_receipt"]
    _archive(
        receipt,
        (
            "verification_recorded_at",
            "observation_basis",
            "release_id",
            "manifest_canonical_sha256",
            "verification",
            "assets",
        ),
    )
    positive_id(receipt["release_id"])
    require(
        receipt["manifest_canonical_sha256"] == identity(manifest),
        "historical receipt manifest mismatch",
    )
    require(
        receipt["verification"] == "full-download-sha256",
        "historical full-download receipt required",
    )
    receipt_assets = _assets(receipt["assets"], expected, receipt=True)
    terminal = historical["terminal_inventory"]
    _archive(terminal, ("observed_at", "release_api_url", "release", "assets"))
    old = terminal["release"]
    fields(
        old,
        ("id", "tag_name", "target_commitish", "draft", "author", "body", "upload_url"),
    )
    positive_id(old["id"])
    require(old["id"] == receipt["release_id"], "historical receipt release mismatch")
    require(
        old["draft"] is True and old["author"] == PUBLISHER,
        "historical draft/publisher mismatch",
    )
    require(
        old["tag_name"] == manifest["tag"]
        and old["body"] == "OCF publication manifest SHA-256: " + identity(manifest),
        "historical release marker or tag mismatch",
    )
    require(
        terminal["release_api_url"]
        == f"https://api.github.com/repos/{LEGACY_REPOSITORY}/releases/{old['id']}",
        "historical endpoint mismatch",
    )
    upload = f"https://uploads.github.com/repos/{LEGACY_REPOSITORY}/releases/{old['id']}/assets"
    require(
        old["upload_url"] in (upload, upload + "{?name,label}"),
        "historical upload URL mismatch",
    )
    terminal_assets = _assets(terminal["assets"], expected, receipt=False)
    require(
        receipt_assets == terminal_assets, "historical receipt/terminal join mismatch"
    )
    after_time, current, current_assets = validate_snapshot(
        after, REPOSITORY, manifest, expected, now
    )
    require(
        after["tag_ref"] is None,
        "v2 requires an explicitly observed absent current tag",
    )
    for key in ("id", "tag_name", "target_commitish", "draft", "author", "body"):
        require(
            old[key] == current[key],
            "historical/current release identity mismatch: " + key,
        )
    require(
        current_assets == receipt_assets, "historical/current asset identity mismatch"
    )
    prelaunch = historical["prelaunch_tag_observation"]
    _archive(prelaunch, ("source_id", "observation_time", "state", "ref"))
    text(prelaunch["source_id"])
    require(
        prelaunch["state"] == "absent"
        and prelaunch["ref"] == "refs/tags/" + manifest["tag"],
        "prelaunch observation must separately record the expected absent tag",
    )
    require(
        timestamp(rights["approved_at"])
        <= timestamp(receipt["verification_recorded_at"]),
        "historical receipt verification record precedes rights approval",
    )
    observation_time = prelaunch["observation_time"]
    require(
        type(observation_time) is dict, "expected explicit prelaunch observation time"
    )
    if observation_time.get("state") == "unknown":
        fields(observation_time, ("state",))
    else:
        fields(observation_time, ("state", "observed_at"))
        require(observation_time["state"] == "recorded", "unknown prelaunch time state")
        require(
            timestamp(observation_time["observed_at"])
            < timestamp(terminal["observed_at"]),
            "recorded prelaunch observation is not earlier than terminal evidence",
        )
    require(
        receipt["observation_basis"]
        in ("receipt-recorded-verification", "terminal-recorded-receipt-verification"),
        "unsupported receipt observation provenance",
    )
    if receipt["observation_basis"] == "terminal-recorded-receipt-verification":
        require(
            timestamp(receipt["verification_recorded_at"])
            == timestamp(terminal["observed_at"]),
            "terminal receipt observation timestamp differs from terminal record",
        )
    require(
        timestamp(receipt["verification_recorded_at"])
        <= timestamp(terminal["observed_at"])
        < after_time,
        "historical/current evidence timestamps are not ordered",
    )
    provenance = historical["trusted_provenance"]
    fields(
        provenance,
        (
            "verification",
            "archive_source_id",
            "owner_message_ids",
            "verified_by",
            "authenticated_owner",
            "verified_at",
        ),
    )
    require(
        provenance["verification"] == "authenticated-archive-and-owner-messages",
        "external authenticated historical provenance required",
    )
    text(provenance["archive_source_id"])
    text(provenance["verified_by"])
    require(
        provenance["authenticated_owner"] == PUBLISHER,
        "unexpected authenticated historical owner",
    )
    messages = provenance["owner_message_ids"]
    require(
        type(messages) is list and bool(messages), "owner message provenance required"
    )
    for message in messages:
        text(message)
    require(len(messages) == len(set(messages)), "duplicate owner message provenance")
    require(
        timestamp(terminal["observed_at"])
        <= timestamp(provenance["verified_at"])
        <= now,
        "historical provenance verification timestamp mismatch",
    )
    return {
        "schema_version": 2,
        "mode": MODE,
        "purpose": PURPOSE,
        "repository_id": REPOSITORY_ID,
        "original_owner": "meramsey",
        "original_repository": LEGACY_REPOSITORY,
        "destination_owner": "ocfproject-org",
        "destination_repository": REPOSITORY,
        "expected_publisher": PUBLISHER,
        "release_id": old["id"],
        "tag": manifest["tag"],
        "distribution_commit": current["target_commitish"],
        "tag_ref": None,
        # Compatibility names below always denote canonical manifest identity.
        "original_manifest_sha256": identity(manifest),
        "destination_manifest_sha256": identity(destination),
        "original_rights_approval_canonical_sha256": rights["canonical_sha256"],
        "historical_canonical_sha256": identity(historical),
        "after_snapshot_canonical_sha256": identity(after),
        "uncertainty_acknowledgement": dict(UNCERTAINTY),
        "uncertainty_acknowledgement_canonical_sha256": identity(UNCERTAINTY),
        "assets": receipt_assets,
    }


def verify_reconciliation_v2(
    manifest, historical, after, attestation, approval, *, now=None
):
    now = now if now is not None else datetime.now(UTC)
    expected = build_attestation_v2(manifest, historical, after, now=now)
    require(
        canonical_bytes(attestation) == canonical_bytes(expected),
        "v2 attestation does not bind exact evidence",
    )
    fields(
        approval,
        (
            "schema_version",
            "mode",
            "purpose",
            "owner",
            "approved_at",
            "attestation_canonical_sha256",
            "uncertainty_acknowledgement_canonical_sha256",
            "accept_unverified_historical_tag_continuity",
            "authorize_current_absent_tag_creation",
            "reconcile",
            "publish",
        ),
    )
    require(
        type(approval["schema_version"]) is int
        and approval["schema_version"] == 2
        and approval["mode"] == MODE
        and approval["purpose"] == APPROVAL_PURPOSE,
        "unexpected v2 reconciliation approval mode/schema/purpose",
    )
    require(approval["owner"] == PUBLISHER, "unexpected v2 approval operator")
    require(
        approval["attestation_canonical_sha256"] == identity(expected),
        "v2 approval attestation mismatch",
    )
    require(
        approval["uncertainty_acknowledgement_canonical_sha256"]
        == identity(UNCERTAINTY),
        "v2 uncertainty acknowledgement mismatch",
    )
    require(
        all(
            approval[k] is True
            for k in (
                "accept_unverified_historical_tag_continuity",
                "authorize_current_absent_tag_creation",
                "reconcile",
            )
        ),
        "explicit v2 uncertainty/target acceptance missing",
    )
    require(
        approval["publish"] is False, "v2 reconciliation cannot authorize publication"
    )
    require(
        max(
            timestamp(after["observed_at"]),
            timestamp(historical["trusted_provenance"]["verified_at"]),
        )
        <= timestamp(approval["approved_at"])
        <= now,
        "v2 approval timestamp mismatch",
    )
    return {
        "schema_version": 2,
        "mode": MODE,
        "purpose": "ocf-transfer-reconciliation-result",
        "state": "reconciled-publication-held",
        "repository_id": REPOSITORY_ID,
        "repository": REPOSITORY,
        "release_id": expected["release_id"],
        "attestation_canonical_sha256": identity(expected),
        "approval_canonical_sha256": identity(approval),
        "uncertainty_acknowledgement_canonical_sha256": identity(UNCERTAINTY),
        "publication_allowed": False,
    }
