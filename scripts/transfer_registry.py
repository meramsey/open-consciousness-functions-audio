"""Reviewed local transfer evidence registry; never discover trust in release assets."""

import copy
from pathlib import Path

from publication import canonical_bytes, digest, require
from publication import fields as _fields
from reconcile_transfer import build_attestation, identity, load_json, positive_id


def fields(*args, **kwargs):
    try:
        return _fields(*args, **kwargs)
    except (ValueError, TypeError):
        raise ValueError("invalid transfer registry schema") from None


def _load_json(path):
    try:
        return load_json(path)
    except (ValueError, TypeError, OSError) as exc:
        if str(exc) == "symlink in input path":
            raise ValueError("symlink in registry path") from None
        raise ValueError("invalid transfer registry JSON") from None


DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "migration-attestations"


def _validate_bundle(bundle):
    require(type(bundle) is dict, "expected transfer bundle object")
    version = bundle.get("schema_version")
    require(type(version) is int, "unsupported transfer bundle schema")
    if version == 1:
        fields(bundle, ("schema_version", "manifest", "before", "after", "attestation"))
        expected = build_attestation(
            bundle["manifest"], bundle["before"], bundle["after"]
        )
    elif version == 3:
        from public_transfer_evidence import validate_public_bundle

        return validate_public_bundle(bundle)
    else:
        raise ValueError("unsupported transfer bundle schema")
    require(
        canonical_bytes(bundle["attestation"]) == canonical_bytes(expected),
        "registry attestation differs from transfer evidence",
    )
    return expected


def validate_bundle(bundle):
    try:
        return _validate_bundle(bundle)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("invalid transfer registry bundle") from None


class TransferRegistry:
    """Trust anchor is this reviewed checkout's index, not supplied public metadata."""

    def __init__(self, path=DEFAULT_ROOT):
        self.root = Path(path)
        index = _load_json(self.root / "index.json")
        self.root = self.root.resolve()
        fields(index, ("schema_version", "entries"))
        require(
            type(index["schema_version"]) is int and index["schema_version"] == 1,
            "unsupported transfer registry schema",
        )
        require(type(index["entries"]) is list, "registry entries must be an array")
        self.index_sha256 = identity(index)
        self._bundles = {}
        for entry in index["entries"]:
            fields(
                entry,
                ("release_id", "attestation_sha256", "bundle_sha256"),
                ("mode", "bundle_schema_version", "evidence_visibility"),
            )
            if "mode" in entry:
                from public_transfer_evidence import VISIBILITY
                from reconcile_historical_transfer import MODE

                require(
                    entry["mode"] == MODE
                    and type(entry.get("bundle_schema_version")) is int
                    and entry["bundle_schema_version"] == 3
                    and entry.get("evidence_visibility") == VISIBILITY,
                    "unexpected registry entry mode or visibility",
                )
            else:
                require(
                    "bundle_schema_version" not in entry
                    and "evidence_visibility" not in entry,
                    "unexpected v1 registry entry fields",
                )
            positive_id(entry["release_id"])
            digest(entry["attestation_sha256"])
            digest(entry["bundle_sha256"])
            require(
                entry["release_id"] not in self._bundles, "duplicate registry release"
            )
            bundle = _load_json(self.root / (entry["bundle_sha256"] + ".json"))
            require(
                identity(bundle) == entry["bundle_sha256"],
                "registry bundle digest mismatch",
            )
            require(
                (
                    bundle.get("schema_version") == 3
                    and entry.get("mode") == bundle.get("mode")
                )
                or (bundle.get("schema_version") == 1 and "mode" not in entry),
                "registry entry/bundle mode mismatch",
            )
            attestation = validate_bundle(bundle)
            require(
                identity(attestation) == entry["attestation_sha256"],
                "registry attestation digest mismatch",
            )
            require(
                attestation["release_id"] == entry["release_id"],
                "registry release ID mismatch",
            )
            self._bundles[entry["release_id"]] = bundle

    def for_release(self, release_id):
        positive_id(release_id)
        require(
            release_id in self._bundles, "transfer release is not in reviewed registry"
        )
        return copy.deepcopy(self._bundles[release_id])

    def resolve(self, manifest, release_id):
        bundle = self.for_release(release_id)
        require(
            canonical_bytes(manifest) == canonical_bytes(bundle["manifest"]),
            "manifest differs from reviewed transfer bundle",
        )
        return bundle


def load_registry(path=DEFAULT_ROOT):
    return TransferRegistry(path)
