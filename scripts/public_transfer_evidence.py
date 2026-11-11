"""Public transfer commitments, never private archive evidence or authorization.

Public validation checks consistency only. Reviewed registry pins supply trust;
finalization must separately verify authenticated private evidence and approvals.
"""

import copy
from datetime import UTC, datetime
from functools import wraps

from publication import REPOSITORY, canonical_bytes, digest, fields, require
from reconcile_historical_transfer import (
    MODE,
    PURPOSE,
    UNCERTAINTY,
    build_attestation_v2,
)
from reconcile_transfer import (
    LEGACY_REPOSITORY,
    PUBLISHER,
    REPOSITORY_ID,
    expected_inventory,
    identity,
    legacy_controls,
    validate_snapshot,
)

VISIBILITY = "public-commitments"


def _sanitized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            # Schema errors can contain unknown keys supplied by private records.
            raise ValueError(
                "invalid public transfer evidence or private binding"
            ) from None

    return wrapped


def _commitments(historical):
    roles = {"manifest": historical["manifest_raw_file_sha256"]}
    roles.update(
        {
            role: historical[key]["raw_file_sha256"]
            for role, key in (
                ("original_rights", "rights_approval"),
                ("download_receipt", "download_receipt"),
                ("terminal_inventory", "terminal_inventory"),
                ("frozen_code", "frozen_code"),
                ("frozen_config", "frozen_config"),
                ("prelaunch_tag_observation", "prelaunch_tag_observation"),
            )
        }
    )
    inventory = {
        "schema_version": 1,
        "records": [
            {"role": role, "raw_file_sha256": roles[role]} for role in sorted(roles)
        ],
    }
    return {
        "schema_version": 1,
        "historical_canonical_sha256": identity(historical),
        "original_rights_approval_canonical_sha256": historical["rights_approval"][
            "canonical_sha256"
        ],
        "archive_provenance_canonical_sha256": identity(
            historical["trusted_provenance"]
        ),
        "raw_archive_inventory_canonical_sha256": identity(inventory),
    }


@_sanitized
def validate_public_bundle(bundle):
    fields(
        bundle,
        (
            "schema_version",
            "mode",
            "evidence_visibility",
            "manifest",
            "after",
            "attestation",
            "historical_commitments",
        ),
    )
    require(
        type(bundle["schema_version"]) is int and bundle["schema_version"] == 3,
        "public bundle schema mismatch",
    )
    require(
        bundle["mode"] == MODE and bundle["evidence_visibility"] == VISIBILITY,
        "public evidence mode mismatch",
    )
    manifest, after = bundle["manifest"], bundle["after"]
    controls, destination = legacy_controls(manifest)
    expected_assets = expected_inventory(manifest, controls)
    _, current, assets = validate_snapshot(
        after, REPOSITORY, manifest, expected_assets, datetime.now(UTC)
    )
    require(after["tag_ref"] is None, "v2 snapshot tag must be absent")
    commitments = bundle["historical_commitments"]
    fields(
        commitments,
        (
            "schema_version",
            "historical_canonical_sha256",
            "original_rights_approval_canonical_sha256",
            "archive_provenance_canonical_sha256",
            "raw_archive_inventory_canonical_sha256",
        ),
    )
    require(
        type(commitments["schema_version"]) is int
        and commitments["schema_version"] == 1,
        "commitment schema mismatch",
    )
    for key, value in commitments.items():
        if key != "schema_version":
            digest(value)
    # Reconstruct only publicly derivable facts; opaque commitments are not proof
    # of history. No synthetic historical snapshot or approval is constructed.
    expected = {
        "schema_version": 2,
        "mode": MODE,
        "purpose": PURPOSE,
        "repository_id": REPOSITORY_ID,
        "original_owner": "meramsey",
        "original_repository": LEGACY_REPOSITORY,
        "destination_owner": "ocfproject-org",
        "destination_repository": REPOSITORY,
        "expected_publisher": PUBLISHER,
        "release_id": current["id"],
        "tag": manifest["tag"],
        "distribution_commit": current["target_commitish"],
        "tag_ref": None,
        "original_manifest_sha256": identity(manifest),
        "destination_manifest_sha256": identity(destination),
        "original_rights_approval_canonical_sha256": commitments[
            "original_rights_approval_canonical_sha256"
        ],
        "historical_canonical_sha256": commitments["historical_canonical_sha256"],
        "after_snapshot_canonical_sha256": identity(after),
        "uncertainty_acknowledgement": dict(UNCERTAINTY),
        "uncertainty_acknowledgement_canonical_sha256": identity(UNCERTAINTY),
        "assets": assets,
    }
    require(
        canonical_bytes(bundle["attestation"]) == canonical_bytes(expected),
        "public attestation mismatch",
    )
    return copy.deepcopy(expected)


@_sanitized
def build_public_bundle(private_bundle):
    fields(
        private_bundle,
        ("schema_version", "mode", "manifest", "historical", "after", "attestation"),
    )
    require(
        type(private_bundle["schema_version"]) is int
        and private_bundle["schema_version"] == 2
        and private_bundle["mode"] == MODE,
        "private evidence mode mismatch",
    )
    expected = build_attestation_v2(
        private_bundle["manifest"],
        private_bundle["historical"],
        private_bundle["after"],
    )
    require(
        canonical_bytes(private_bundle["attestation"]) == canonical_bytes(expected),
        "private attestation mismatch",
    )
    result = {
        "schema_version": 3,
        "mode": MODE,
        "evidence_visibility": VISIBILITY,
        "manifest": copy.deepcopy(private_bundle["manifest"]),
        "after": copy.deepcopy(private_bundle["after"]),
        "attestation": copy.deepcopy(private_bundle["attestation"]),
        "historical_commitments": _commitments(private_bundle["historical"]),
    }
    validate_public_bundle(result)
    return result


@_sanitized
def verify_private_evidence(public_bundle, historical):
    attestation = validate_public_bundle(public_bundle)
    expected = build_attestation_v2(
        public_bundle["manifest"], historical, public_bundle["after"]
    )
    require(
        canonical_bytes(expected) == canonical_bytes(attestation),
        "private attestation mismatch",
    )
    require(
        canonical_bytes(_commitments(historical))
        == canonical_bytes(public_bundle["historical_commitments"]),
        "private commitment mismatch",
    )
    return copy.deepcopy(attestation)
