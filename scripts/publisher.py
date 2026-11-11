"""Resumable release publication; all remote mutation requires exact owner approval.

The transport is injected so the state machine can be tested without GitHub.
An interrupted upload is reconciled from remote bytes, never blindly repeated.
"""

import hashlib
import json
from pathlib import Path

from publication import (
    canonical_bytes,
    control_artifacts,
    manifest_digest,
    require,
    verify_approval,
    verify_files,
)


def save_receipt(path, receipt):
    path = Path(path)
    require(not path.is_symlink(), "receipt cannot be a symlink")
    import os
    import tempfile

    # Unique siblings permit recovery after a crash before atomic replacement.
    # Interrupted receipts remain as diagnostics and are never trusted on resume.
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=path.name + ".", suffix=".tmp", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(canonical_bytes(receipt))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    if hasattr(os, "O_DIRECTORY"):
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _publish(
    manifest, root, approval, remote, receipt_path, controls_root, *, finalize=False
):
    """Stage or finalize one immutable release using a supplied transport.

    Callers must enforce a single writer (workflow concurrency or local lock).
    Existing released tags are verified and returned without modification.
    The transport must paginate assets and stream downloads for verification.
    """
    require(
        remote.repository == manifest["repository"], "transport repository mismatch"
    )
    verify_files(manifest, root)
    verify_approval(manifest, approval, publication=finalize)
    identity = manifest_digest(manifest)
    tag = manifest["tag"]
    marker = "OCF publication manifest SHA-256: " + identity
    receipt_path = Path(receipt_path)
    prior = {}
    if receipt_path.exists():
        prior = json.loads(receipt_path.read_text(encoding="utf-8"))
        require(
            prior.get("manifest_sha256") == identity,
            "receipt belongs to another manifest",
        )
    receipt = {
        "schema_version": 1,
        "manifest_sha256": identity,
        "tag": tag,
        "phase": "reconciling",
        "verified_assets": [],
    }
    release = remote.find_release(tag)
    if prior.get("release_id") is not None:
        require(
            release and release["id"] == prior["release_id"],
            "previous release missing or replaced; never recreate it",
        )
        receipt["release_id"] = prior["release_id"]
    if prior.get("phase") == "published-verified" or prior.get("published_release_id"):
        require(
            release and release["draft"] is False,
            "previously published release changed state",
        )
        receipt["published_release_id"] = release["id"]
    save_receipt(receipt_path, receipt)
    if release is None:
        release = remote.create_draft(tag, marker)
    require(
        release["tag_name"] == tag and release.get("body") == marker,
        "remote release identity mismatch",
    )
    release_id = release["id"]
    receipt["release_id"] = release_id
    save_receipt(receipt_path, receipt)
    expected = {asset["remote_filename"]: asset for asset in manifest["assets"]}
    controls = control_artifacts(manifest)
    for name, data in controls.items():
        (controls_root / name).write_bytes(data)
        expected[name] = {
            "asset_id": "control:" + name,
            "filename": name,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    observed = remote.list_assets(release_id)
    require(
        len({a["name"] for a in observed}) == len(observed),
        "duplicate remote asset names",
    )
    require(
        {a["name"] for a in observed} <= expected.keys(),
        "unexpected remote assets; manual reconciliation required",
    )
    by_name = {asset["name"]: asset for asset in observed}
    for name, asset in expected.items():
        if name not in by_name:
            require(
                release["draft"] is True,
                "published release is missing an asset; never modify it",
            )
            # Recheck local bytes immediately before upload after potentially slow downloads.
            if name in controls:
                path = controls_root / name
            else:
                verify_files({**manifest, "assets": [asset]}, root)
                # Copy and verify before any public write: never upload a mutable
                # source pathname that was hashed earlier.
                import shutil

                path = controls_root / name
                shutil.copyfile(Path(root) / asset["filename"], path)
                require(
                    path.stat().st_size == asset["size_bytes"],
                    "staged asset size mismatch",
                )
                with path.open("rb") as stream:
                    require(
                        hashlib.file_digest(stream, "sha256").hexdigest()
                        == asset["sha256"],
                        "staged asset checksum mismatch",
                    )
            current = remote.find_release(tag)
            require(
                current
                and current["id"] == release_id
                and current.get("body") == marker
                and current["draft"] is True,
                "release is no longer the expected draft",
            )
            remote.upload(release_id, path)
            if name not in controls:
                path.unlink()
            matches = [a for a in remote.list_assets(release_id) if a["name"] == name]
            require(
                len(matches) == 1,
                "uploaded asset was renamed or not visible; reconcile before retry",
            )
            by_name[name] = matches[0]
        actual = by_name[name]
        require(
            actual.get("state") == "uploaded"
            and actual.get("size") == asset["size_bytes"],
            "remote asset incomplete or wrong size",
        )
        require(
            remote.sha256(actual["id"]) == asset["sha256"],
            "remote download checksum mismatch",
        )
        receipt["verified_assets"].append(
            {
                "asset_id": asset["asset_id"],
                "remote_id": actual["id"],
                "sha256": asset["sha256"],
            }
        )
        receipt["phase"] = "verifying"
        save_receipt(receipt_path, receipt)
    # Re-read immediately before final mutation to catch concurrent changes.
    fresh = remote.find_release(tag)
    require(
        fresh
        and fresh["id"] == release_id
        and fresh.get("tag_name") == tag
        and fresh.get("body") == marker,
        "release changed during verification",
    )
    assets = remote.list_assets(release_id)
    require(
        {(a["name"], a["id"], a["size"], a["state"]) for a in assets}
        == {(a["name"], a["id"], a["size"], a["state"]) for a in by_name.values()},
        "remote inventory changed during verification",
    )
    if finalize and fresh["draft"] is True:
        remote.finalize(release_id)
        fresh = remote.find_release(tag)
        require(
            fresh
            and fresh["id"] == release_id
            and fresh["draft"] is False
            and fresh.get("tag_name") == tag
            and fresh.get("body") == marker,
            "publication was not confirmed",
        )
    terminal_assets = remote.list_assets(release_id)
    require(
        {(a["name"], a["id"], a["size"], a["state"]) for a in terminal_assets}
        == {(a["name"], a["id"], a["size"], a["state"]) for a in by_name.values()},
        "remote inventory changed before terminal verification",
    )
    if not fresh["draft"]:
        receipt["published_release_id"] = release_id
    receipt["phase"] = "draft-verified" if fresh["draft"] else "published-verified"
    save_receipt(receipt_path, receipt)
    return receipt


def publish(manifest, root, approval, remote, receipt_path, *, finalize=False):
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ocf-publication-controls-") as directory:
        return _publish(
            manifest,
            root,
            approval,
            remote,
            receipt_path,
            Path(directory),
            finalize=finalize,
        )
