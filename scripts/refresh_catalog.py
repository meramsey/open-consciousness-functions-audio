"""Build a static catalog from owner-published, hash-bound GitHub releases.

This verifies GitHub's stored asset digests, not a fresh download of every audio
file. The publishing workflow performs full download verification before release.
"""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

from catalog import append_release, release_entry, transferred_release_entry
from github_publisher import GitHub
from publication import (
    AUTHORIZED_PUBLISHERS,
    canonical_bytes,
    control_artifacts,
    manifest_digest,
    require,
)

MARKER = re.compile(r"OCF publication manifest SHA-256: ([a-f0-9]{64})\Z")


def build_catalog(
    base,
    releases,
    list_assets,
    read_manifest,
    *,
    registry=None,
    repository_id=None,
    read_tag=None,
):
    # Rebuild from immutable published manifests; never carry stale download URLs.
    result = dict(base, schema_version=2, releases=[])
    ignored = []
    for release in releases:
        if release.get("draft"):
            continue
        match = MARKER.fullmatch(release.get("body") or "")
        if not match:
            ignored.append(release.get("tag_name"))
            continue
        require(
            release.get("author", {}).get("login") in AUTHORIZED_PUBLISHERS,
            "release publisher is not authorized",
        )
        assets = list_assets(release["id"])
        require(
            len({a["name"] for a in assets}) == len(assets),
            "duplicate remote asset names",
        )
        named = {a["name"]: a for a in assets}
        require(
            "publication.json" in named
            and 0 < named["publication.json"]["size"] <= 8 * 1024 * 1024,
            "missing or oversized publication manifest",
        )
        raw = read_manifest(named["publication.json"]["id"])
        require(len(raw) <= 8 * 1024 * 1024, "oversized publication manifest")
        manifest = json.loads(raw)
        from reconcile_transfer import LEGACY_REPOSITORY, REPOSITORY_ID, identity

        if manifest.get("repository") == LEGACY_REPOSITORY:
            require(
                type(repository_id) is int and repository_id == REPOSITORY_ID,
                "current repository stable ID mismatch",
            )
            require(
                hashlib.sha256(raw).hexdigest() == match[1] == identity(manifest),
                "publication manifest differs from owner release marker",
            )
            from transfer_registry import load_registry

            trusted = registry if registry is not None else load_registry()
            bundle = trusted.resolve(manifest, release["id"])
            tag_ref = None
            if bundle["schema_version"] == 2:
                require(callable(read_tag), "v2 catalog needs current tag lookup")
                tag_ref = read_tag(release["tag_name"])
            entry = transferred_release_entry(
                manifest, release, assets, registry=trusted, tag_ref=tag_ref
            )
            if bundle["schema_version"] == 2:
                require(
                    read_tag(release["tag_name"]) == tag_ref,
                    "v2 catalog tag changed during verification",
                )
            result = append_release(result, entry, registry=registry)
            continue
        require(
            hashlib.sha256(raw).hexdigest() == match[1] == manifest_digest(manifest),
            "publication manifest differs from owner release marker",
        )
        expected = {
            a["remote_filename"]: (a["asset_id"], a["size_bytes"], a["sha256"])
            for a in manifest["assets"]
        }
        expected.update(
            {
                name: ("control:" + name, len(data), hashlib.sha256(data).hexdigest())
                for name, data in control_artifacts(manifest).items()
            }
        )
        require(
            set(named) == set(expected), "release asset inventory differs from manifest"
        )
        receipt = {
            "phase": "published-api-digest-verified",
            "manifest_sha256": match[1],
            "release_id": release["id"],
            "verified_assets": [],
        }
        for name, (asset_id, size, checksum) in expected.items():
            remote = named[name]
            require(
                remote["state"] == "uploaded"
                and remote["size"] == size
                and remote.get("digest") == "sha256:" + checksum,
                "GitHub asset digest or size mismatch; full read-back reconciliation required",
            )
            receipt["verified_assets"].append(
                {"asset_id": asset_id, "sha256": checksum, "remote_id": remote["id"]}
            )
        result = append_release(
            result, release_entry(manifest, receipt, release), registry=registry
        )
    from validate_site import validate_catalog

    validate_catalog(result, registry=registry)
    return result, ignored


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path("site/catalog.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    require(
        not args.output.exists() and not args.output.is_symlink(),
        "output already exists",
    )
    remote = GitHub(None)
    pages = remote.api(remote.base + "/releases?per_page=100", paginate=True)

    def read_manifest(asset_id):
        with tempfile.TemporaryFile() as stream:
            outcome = subprocess.run(
                [
                    "gh",
                    "api",
                    remote.base + f"/releases/assets/{int(asset_id)}",
                    "-H",
                    "Accept: application/octet-stream",
                ],
                stdout=stream,
                stderr=subprocess.PIPE,
                check=False,
                timeout=120,
            )
            require(outcome.returncode == 0, "manifest download failed")
            stream.seek(0)
            return stream.read(8 * 1024 * 1024 + 1)

    def read_tag(tag):
        refs = remote.api(
            remote.base + "/git/matching-refs/tags/" + quote(tag, safe="")
        )
        refs = [r for r in refs if r["ref"] == "refs/tags/" + tag]
        require(
            len(refs) == 1 and refs[0]["object"]["type"] == "commit",
            "v2 published tag missing or not lightweight",
        )
        sha = refs[0]["object"]["sha"]
        require(
            remote.api(remote.base + "/commits/" + sha)["sha"] == sha,
            "published commit resolution mismatch",
        )
        return {
            "ref": refs[0]["ref"],
            "object_type": "commit",
            "object_sha": sha,
            "peeled_commit": sha,
        }

    catalog, ignored = build_catalog(
        json.loads(args.base.read_text(encoding="utf-8")),
        [r for page in pages for r in page],
        remote.list_assets,
        read_manifest,
        repository_id=remote.api(remote.base)["id"],
        read_tag=read_tag,
    )
    with args.output.open("xb") as stream:
        stream.write(canonical_bytes(catalog))
    print(
        json.dumps(
            {
                "releases": len(catalog["releases"]),
                "ignored_unmarked_releases": len(ignored),
                "verification": "github-api-digest",
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(str(exc)) from exc
