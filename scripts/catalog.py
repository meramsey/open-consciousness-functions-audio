"""Project verified public releases into the existing catalog; never infer approval."""

import copy
from datetime import datetime
from urllib.parse import quote

from publication import (
    REPOSITORY,
    asset_url,
    control_artifacts,
    manifest_digest,
    require,
)
from validate_site import validate_catalog


def release_entry(manifest, receipt, remote_release):
    identity = manifest_digest(manifest)
    require(
        receipt.get("manifest_sha256") == identity
        and receipt.get("phase")
        in {"published-verified", "published-api-digest-verified"},
        "catalog requires a published verification receipt",
    )
    require(
        remote_release.get("id") == receipt.get("release_id")
        and remote_release.get("draft") is False,
        "remote publication does not match receipt",
    )
    require(
        remote_release.get("tag_name") == manifest["tag"]
        and remote_release.get("body")
        == "OCF publication manifest SHA-256: " + identity,
        "remote publication identity mismatch",
    )
    expected = {(a["asset_id"], a["sha256"]) for a in manifest["assets"]}
    import hashlib

    expected.update(
        ("control:" + name, hashlib.sha256(data).hexdigest())
        for name, data in control_artifacts(manifest).items()
    )
    actual = [(a["asset_id"], a["sha256"]) for a in receipt.get("verified_assets", [])]
    require(
        len(actual) == len(expected) and set(actual) == expected,
        "catalog receipt asset set mismatch",
    )
    published = datetime.fromisoformat(remote_release["published_at"])
    require(published.tzinfo is not None, "publication timestamp needs timezone")
    return _project_entry(manifest, identity, published)


def _project_entry(manifest, identity, published):
    """Project only after an ordinary or transferred evidence gate succeeded."""
    url = (
        "https://github.com/"
        + REPOSITORY
        + "/releases/tag/"
        + quote(manifest["tag"], safe="")
    )
    release = {
        "version": manifest["edition"],
        "channel": "stable",
        "date": published.date().isoformat(),
        "source_ocf_commit": manifest["source_commit"],
        "source_ocf_version": manifest["source_version"],
        "release_url": url,
        "release_notes_url": url,
        "functions": [],
        "preparations": [],
        "publication_manifest_sha256": identity,
        "tag": manifest["tag"],
        "asset_order": [a["asset_id"] for a in manifest["assets"]],
        "collections": [],
        "companions": [],
    }
    groups = {}
    sessions = {}
    for asset in manifest["assets"]:
        public_asset = {
            k: asset[k]
            for k in ("asset_id", "filename", "format", "size_bytes", "sha256")
        }
        public_asset["display_filename"] = asset["filename"]
        public_asset["filename"] = asset["remote_filename"]
        public_asset["download_url"] = asset_url(manifest, asset)
        public_asset["provenance"] = dict(
            asset["provenance"], source_ocf_commit=manifest["source_commit"]
        )
        if asset["format"] == "zip":
            release["collections"].append(public_asset)
        if asset["format"] not in {"mp3", "flac"}:
            if asset["format"] != "zip":
                release["companions"].append(public_asset)
            continue
        session = asset["session"]
        identity_key = (
            session["function_id"]
            if session["kind"] == "function"
            else "preparation-learning"
        )
        if identity_key not in groups:
            group = {
                "title": session["title"],
                "languages": [],
                "voices": [],
                "sessions": [],
            }
            if session["kind"] == "function":
                group["function_id"] = identity_key
                release["functions"].append(group)
            else:
                group["session_kind"] = "preparation-learning"
                release["preparations"].append(group)
            groups[identity_key] = group
        group = groups[identity_key]
        for field, value in (
            ("languages", session["locale"]),
            ("voices", session["voice_id"]),
        ):
            if value not in group[field]:
                group[field].append(value)
        key = (identity_key, session["locale"], session["voice_id"], session["edition"])
        if key not in sessions:
            sessions[key] = {
                k: session[k]
                for k in ("title", "locale", "voice_id", "voice_name", "edition")
            }
            sessions[key]["assets"] = []
            group["sessions"].append(sessions[key])
        target = sessions[key]
        require(
            all(target[k] == session[k] for k in ("title", "voice_name")),
            "conflicting session identity",
        )
        require(
            asset["format"] not in {a["format"] for a in target["assets"]},
            "duplicate session format",
        )
        for field in (
            "duration_seconds",
            "sample_rate_hz",
            "channels",
            "encoding",
            "bit_depth",
        ):
            if field in session:
                public_asset[field] = session[field]
        target["assets"].append(public_asset)
    return release


def append_release(catalog, release, *, registry=None):
    validate_catalog(catalog, registry=registry)
    result = copy.deepcopy(catalog)
    require(
        catalog["schema_version"] in (2, 3) or not catalog["releases"],
        "legacy nonempty catalog requires explicit migration",
    )
    result["schema_version"] = (
        3 if catalog["schema_version"] == 3 or "manifest_repository" in release else 2
    )
    existing = [
        r
        for r in result["releases"]
        if r.get("tag") == release["tag"] or r["version"] == release["version"]
    ]
    if existing:
        require(
            len(existing) == 1 and existing[0] == release,
            "immutable catalog release conflict",
        )
        return result
    old_ids = {
        a["asset_id"]
        for r in result["releases"]
        for f in r["functions"] + r.get("preparations", [])
        for s in f["sessions"]
        for a in s["assets"]
    }
    new_ids = {
        a["asset_id"]
        for f in release["functions"] + release.get("preparations", [])
        for s in f["sessions"]
        for a in s["assets"]
    }
    require(not old_ids & new_ids, "asset IDs already belong to a historical release")
    result["releases"].append(release)
    result["releases"].sort(key=lambda r: (r["date"], r["version"]), reverse=True)
    validate_catalog(result, registry=registry)
    return result


def transferred_release_entry(
    manifest, remote_release, remote_assets, *, registry=None
):
    """Project a published legacy manifest only through a pinned transfer bundle."""
    from reconcile_transfer import LEGACY_REPOSITORY, PUBLISHER, REPOSITORY_ID, identity
    from transfer_registry import load_registry

    registry = registry if registry is not None else load_registry()
    bundle = registry.resolve(manifest, remote_release["id"])
    attestation = bundle["attestation"]
    original = bundle["after"]["release"]
    require(
        remote_release.get("draft") is False, "transferred release is not published"
    )
    require(
        remote_release.get("author", {}).get("login") == PUBLISHER,
        "transferred release publisher is not authorized",
    )
    for key in ("id", "tag_name", "target_commitish", "body", "upload_url"):
        require(
            remote_release.get(key) == original[key],
            "transferred release identity mismatch: " + key,
        )
    expected = {a["name"]: a for a in attestation["assets"]}
    require(
        type(remote_assets) is list and len(remote_assets) == len(expected),
        "transferred asset inventory mismatch",
    )
    seen = set()
    for asset in remote_assets:
        name = asset.get("name")
        require(
            type(name) is str and name in expected and name not in seen,
            "unexpected or duplicate transferred asset",
        )
        seen.add(name)
        pinned = expected[name]
        require(
            type(asset.get("id")) is int
            and asset["id"] == pinned["remote_id"]
            and type(asset.get("size")) is int
            and asset["size"] == pinned["size_bytes"]
            and asset.get("state") == "uploaded"
            and asset.get("digest") == "sha256:" + pinned["sha256"],
            "transferred asset ID, state, size or digest mismatch",
        )
    published = datetime.fromisoformat(remote_release["published_at"])
    require(published.tzinfo is not None, "publication timestamp needs timezone")
    release = _project_entry(manifest, identity(manifest), published)
    release.update(
        manifest_repository=LEGACY_REPOSITORY,
        download_repository=REPOSITORY,
        repository_id=REPOSITORY_ID,
        release_id=remote_release["id"],
        migration_attestation_sha256=identity(attestation),
    )
    return release
