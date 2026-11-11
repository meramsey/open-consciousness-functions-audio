"""Assemble a local release review packet without approval or remote operations."""

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from collections_export import build_collections
from import_candidates import import_candidates
from publication import (
    asset_url,
    canonical_bytes,
    control_artifacts,
    manifest_digest,
    require,
    verify_files,
)


def prepare_review(paths, destination, *, tag, edition, collections=False):
    destination = Path(destination).absolute()
    require(not destination.exists(), "review destination already exists")
    require(
        not any(p.is_symlink() for p in (destination, *destination.parents)),
        "symlink review destination",
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".ocf-review-stage-", dir=destination.parent))
    # Failed assembly is retained. Original candidates are only read.
    assets = stage / "assets"
    manifest = import_candidates(paths, assets, tag=tag, edition=edition)
    if collections:
        collection_root = stage / "collections"
        records = build_collections(manifest, assets, collection_root)
        for record in records:
            shutil.copyfile(
                collection_root / record["filename"], assets / record["filename"]
            )
        manifest["assets"].extend(records)
    verify_files(manifest, assets)
    for name, data in control_artifacts(manifest).items():
        (assets / name).write_bytes(data)
    local_checksums = "".join(
        f"{a['sha256']}  {a['filename']}\n" for a in manifest["assets"]
    )
    for name in ("publication.json", "release-notes.md"):
        checksum = hashlib.sha256((assets / name).read_bytes()).hexdigest()
        local_checksums += f"{checksum}  {name}\n"
    (assets / "LOCAL-SHA256SUMS.txt").write_text(local_checksums, encoding="utf-8")
    report = {
        "schema_version": 1,
        "state": "local-review-only",
        "manifest_sha256": manifest_digest(manifest),
        "publication_approved": False,
        "required_owner_decisions": [
            "exact-assets-and-listening",
            "voice-redistribution",
            "artwork-and-content-rights",
            "final-publication",
        ],
        "assets": [
            {
                "asset_id": a["asset_id"],
                "file": "assets/" + a["filename"],
                "bytes": a["size_bytes"],
                "sha256": a["sha256"],
                "proposed_url": asset_url(manifest, a),
                **({"session": a["session"]} if "session" in a else {}),
            }
            for a in manifest["assets"]
        ],
    }
    (stage / "review.json").write_bytes(canonical_bytes(report))
    require(not destination.exists(), "review destination appeared during assembly")
    stage.rename(destination)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--edition", required=True)
    parser.add_argument("--collections", action="store_true")
    args = parser.parse_args(argv)
    report = prepare_review(
        args.candidates,
        args.output,
        tag=args.tag,
        edition=args.edition,
        collections=args.collections,
    )
    print(json.dumps({k: v for k, v in report.items() if k != "assets"}))


if __name__ == "__main__":
    main()
