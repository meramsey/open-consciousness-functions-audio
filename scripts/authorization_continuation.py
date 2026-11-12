"""Private v3 continuation records; consistency checks never authenticate messages.

A trusted operator must independently authenticate the COMPLETE context, role
classification, scope and migration observation before supplying its canonical
pin through a separate trusted channel. Neither JSON nor a public registry can
establish that trust. No record is generated or approved by this module.
"""

import re
from datetime import UTC, datetime, timedelta

from public_transfer_evidence import verify_private_evidence
from publication import (
    REPOSITORY,
    _verify_approval_digest,
    digest,
    fields,
    require,
    text,
)
from reconcile_historical_transfer import MODE, build_attestation_v2
from reconcile_transfer import PUBLISHER, REPOSITORY_ID, identity, timestamp

CONTEXT_PURPOSE = "ocf-authenticated-instruction-context"
RECONCILIATION_PURPOSE = "record-ocf-authorization-continuation-reconciliation"
FINAL_PURPOSE = "record-ocf-authorization-continuation-finalization"
DERIVATION = "original-release-authority-after-migration-only-hold"
SCOPE = {
    "original_rights_unchanged": True,
    "same_original_batch": True,
    "hold_scope": "migration-only",
    "migration_complete": True,
    "latest_instruction": "resume-original-release",
    "unresolved_holds": False,
    "contradictory_instructions": False,
}
ROLES = ("original_release", "artwork_rights", "migration_hold", "latest_instruction")


def _context(context, expected_pin, original, now, *, expected_release_scope):
    # Never derive the expected pin from the supplied context or registry.
    digest(expected_pin)
    require(identity(context) == expected_pin, "external context pin mismatch")
    fields(
        context,
        (
            "schema_version",
            "purpose",
            "publisher",
            "messages",
            "migration_completion",
            "release_scope",
        ),
    )
    require(
        type(context["schema_version"]) is int and context["schema_version"] == 1,
        "unsupported instruction context",
    )
    require(
        context["purpose"] == CONTEXT_PURPOSE and context["publisher"] == PUBLISHER,
        "unexpected instruction context",
    )
    require(
        identity(context["release_scope"]) == identity(expected_release_scope),
        "authenticated release scope mismatch",
    )
    rows = context["messages"]
    require(
        type(rows) is list and 4 <= len(rows) <= 6, "incomplete instruction context"
    )
    roles, ids, owner_ids = {}, set(), set()
    for row in rows:
        fields(row, ("role", "message_id", "author", "author_id", "sent_at", "text"))
        for key in ("role", "message_id", "author_id"):
            text(row[key])
        # Message bodies are authenticated verbatim, not identifier strings.
        # Preserve ordinary whitespace; normalizing it would invalidate the pin.
        body = row["text"]
        require(
            type(body) is str
            and bool(body.strip())
            and not any(
                (ord(c) < 32 and c not in "\t\r\n") or ord(c) == 127 for c in body
            ),
            "invalid instruction body",
        )
        role = row["role"]
        require(
            role in (*ROLES, "evidence_gap_question", "evidence_gap_disclosure")
            and role not in roles,
            "duplicate or unsupported instruction role",
        )
        require(row["message_id"] not in ids, "duplicate instruction message")
        ids.add(row["message_id"])
        require(
            row["author"] == ("aeon" if role == "evidence_gap_disclosure" else "user"),
            "instruction author/role mismatch",
        )
        if role != "evidence_gap_disclosure":
            owner_ids.add(row["author_id"])
        roles[role] = timestamp(row["sent_at"])
        require(roles[role] <= now, "future instruction")
    require(
        set(ROLES) <= roles.keys() and len(owner_ids) == 1,
        "missing owner instruction roles",
    )
    require(
        max(roles["original_release"], roles["artwork_rights"])
        <= timestamp(original["approved_at"])
        <= roles["migration_hold"]
        < roles["latest_instruction"],
        "instruction chronology mismatch",
    )
    if "evidence_gap_question" in roles:
        require(
            "evidence_gap_disclosure" in roles
            and roles["evidence_gap_question"] < roles["evidence_gap_disclosure"],
            "gap question/disclosure chronology mismatch",
        )
    observation = context["migration_completion"]
    fields(observation, ("observed_at", "source", "distribution"))
    for key, repo_id, repository in (
        ("source", 1367603146, "ocfproject-org/open-consciousness-functions"),
        ("distribution", REPOSITORY_ID, REPOSITORY),
    ):
        fields(observation[key], ("repository_id", "repository"))
        require(
            type(observation[key]["repository_id"]) is int
            and observation[key]["repository_id"] == repo_id
            and observation[key]["repository"] == repository,
            "migration observation destination mismatch",
        )
    observed = timestamp(observation["observed_at"])
    require(
        roles["migration_hold"] < observed <= now,
        "migration observation chronology mismatch",
    )
    # Observation time is NOT transfer time and may follow the latest instruction.
    return max(*roles.values(), observed)


def bindings(manifest, attestation, original):
    return {
        "repository": REPOSITORY,
        "repository_id": REPOSITORY_ID,
        "release_id": attestation["release_id"],
        "tag": attestation["tag"],
        "distribution_commit": attestation["distribution_commit"],
        "original_manifest_sha256": identity(manifest),
        "destination_manifest_sha256": attestation["destination_manifest_sha256"],
        "original_approval_sha256": identity(original),
        "inventory_sha256": identity(attestation["assets"]),
        "attestation_sha256": identity(attestation),
        "uncertainty_sha256": attestation[
            "uncertainty_acknowledgement_canonical_sha256"
        ],
    }


def _record(record, purpose, expected_bindings, context_pin, earliest, now, extra=()):
    fields(
        record,
        (
            "schema_version",
            "mode",
            "purpose",
            "recorded_by",
            "recorded_at",
            "context_sha256",
            "bindings",
            "scope_assessment",
            "operator_evidence_gap_acknowledgement",
            "authorization_basis",
            *extra,
        ),
    )
    require(
        type(record["schema_version"]) is int
        and record["schema_version"] == 3
        and record["mode"] == MODE
        and record["purpose"] == purpose,
        "unexpected continuation contract",
    )
    text(record["recorded_by"])
    require(
        record["recorded_by"] not in (PUBLISHER, "ocfproject-org"),
        "operator record cannot impersonate publisher",
    )
    require(record["context_sha256"] == context_pin, "record context mismatch")
    require(
        identity(record["bindings"]) == identity(expected_bindings),
        "continuation binding mismatch",
    )
    require(
        identity(record["scope_assessment"]) == identity(SCOPE),
        "unsupported or unresolved scope",
    )
    require(
        record["authorization_basis"] == DERIVATION, "unsupported authorization basis"
    )
    require(
        record["operator_evidence_gap_acknowledgement"]
        == {
            "uncertainty_sha256": expected_bindings["uncertainty_sha256"],
            "historical_tag_state": "unknown",
            "historical_commit_api_resolution": "unobserved",
            "owner_explicit_gap_acceptance": False,
        },
        "operator evidence-gap acknowledgement mismatch",
    )
    # Canonical equality also disallows numeric false/true substitutions.
    require(
        identity(record["operator_evidence_gap_acknowledgement"])
        == identity(
            {
                "uncertainty_sha256": expected_bindings["uncertainty_sha256"],
                "historical_tag_state": "unknown",
                "historical_commit_api_resolution": "unobserved",
                "owner_explicit_gap_acceptance": False,
            }
        ),
        "invalid operator acknowledgement types",
    )
    recorded = timestamp(record["recorded_at"])
    require(earliest <= recorded <= now, "operator record chronology mismatch")
    return recorded


def verify_reconciliation_v3(
    manifest,
    historical,
    after,
    attestation,
    original,
    record,
    *,
    private_instruction_context=None,
    expected_context_sha256=None,
    now=None,
):
    """Validate an externally authenticated operator derivation, not owner consent."""
    try:
        now = now if now is not None else datetime.now(UTC)
        expected = build_attestation_v2(manifest, historical, after, now=now)
        require(identity(attestation) == identity(expected), "attestation mismatch")
        _verify_approval_digest(identity(manifest), original)
        require(
            identity(original) == expected["original_rights_approval_canonical_sha256"],
            "original rights changed",
        )
        latest = _context(
            private_instruction_context,
            expected_context_sha256,
            original,
            now,
            expected_release_scope=bindings(manifest, expected, original),
        )
        earliest = max(
            latest,
            timestamp(after["observed_at"]),
            timestamp(historical["trusted_provenance"]["verified_at"]),
        )
        _record(
            record,
            RECONCILIATION_PURPOSE,
            bindings(manifest, expected, original),
            expected_context_sha256,
            earliest,
            now,
            ("reconcile", "publish"),
        )
        require(
            record["reconcile"] is True and record["publish"] is False,
            "reconciliation cannot publish",
        )
        return {
            "schema_version": 3,
            "mode": MODE,
            "state": "reconciled-publication-held",
            "publication_allowed": False,
            "context_sha256": expected_context_sha256,
            "record_sha256": identity(record),
        }
    except (ValueError, KeyError, TypeError, AttributeError, OSError):
        raise ValueError(
            "private authorization continuation validation failed"
        ) from None


def _verify_final_v3(
    bundle,
    registry,
    original,
    reconciliation,
    record,
    now,
    *,
    private_historical=None,
    private_instruction_context=None,
    expected_context_sha256=None,
):
    require(
        type(bundle["schema_version"]) is int
        and bundle["schema_version"] == 3
        and bundle["mode"] == MODE,
        "v3 requires public historical-receipt envelope",
    )
    verify_private_evidence(bundle, private_historical)
    verify_reconciliation_v3(
        bundle["manifest"],
        private_historical,
        bundle["after"],
        bundle["attestation"],
        original,
        reconciliation,
        private_instruction_context=private_instruction_context,
        expected_context_sha256=expected_context_sha256,
        now=now,
    )
    expected = bindings(bundle["manifest"], bundle["attestation"], original)
    expected.update(
        bundle_sha256=identity(bundle),
        registry_sha256=registry.index_sha256,
        reconciliation_record_sha256=identity(reconciliation),
    )
    recorded = _record(
        record,
        FINAL_PURPOSE,
        expected,
        expected_context_sha256,
        timestamp(reconciliation["recorded_at"]),
        now,
        ("expires_at", "ci_commits", "allow_tag_creation", "publish"),
    )
    require(
        record["publish"] is True
        and record["allow_tag_creation"] is True
        and bundle["attestation"]["tag_ref"] is None,
        "unexpected finalization scope",
    )
    expires = timestamp(record["expires_at"])
    require(
        now < expires and expires - recorded <= timedelta(hours=24),
        "expired continuation",
    )
    fields(record["ci_commits"], ("source", "distribution"))
    for sha in record["ci_commits"].values():
        require(
            type(sha) is str and re.fullmatch(r"[a-f0-9]{40}", sha), "invalid CI commit"
        )


def verify_final_v3(*args, **kwargs):
    """Private fail-closed boundary; never echo message text, fields or paths."""
    try:
        return _verify_final_v3(*args, **kwargs)
    except (ValueError, KeyError, TypeError, AttributeError, OSError):
        raise ValueError(
            "private authorization continuation validation failed"
        ) from None
