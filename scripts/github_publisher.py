"""GitHub CLI transport for approved OCF releases. Defaults to offline preflight."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse

from publication import (
    REPOSITORY,
    canonical_bytes,
    manifest_digest,
    require,
    verify_approval,
    verify_files,
)
from publisher import publish


class GitHub:
    repository = REPOSITORY

    def __init__(self, target_commit):
        require(
            target_commit is None or re.fullmatch(r"[a-f0-9]{40}", target_commit),
            "distribution target must be a full commit SHA",
        )
        self.target_commit = target_commit
        self.base = "repos/" + REPOSITORY

    def api(self, endpoint, *, method="GET", body=None, paginate=False):
        command = [
            "gh",
            "api",
            endpoint,
            "--method",
            method,
            "-H",
            "Accept: application/vnd.github+json",
        ]
        if paginate:
            command += ["--paginate"]
        if body is not None:
            command += ["--input", "-"]
        result = subprocess.run(
            command,
            input=None if body is None else json.dumps(body),
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        require(
            result.returncode == 0,
            "GitHub API request failed: " + result.stderr.strip(),
        )
        if paginate:
            pages = []
            remaining = result.stdout.lstrip()
            decoder = json.JSONDecoder()
            while remaining:
                page, end = decoder.raw_decode(remaining)
                require(
                    type(page) is list, "paginated API response must contain arrays"
                )
                pages.append(page)
                remaining = remaining[end:].lstrip()
            return pages
        return json.loads(result.stdout)

    def find_release(self, tag):
        pages = self.api(self.base + "/releases?per_page=100", paginate=True)
        matches = [
            release for page in pages for release in page if release["tag_name"] == tag
        ]
        require(len(matches) <= 1, "duplicate remote release tags")
        release = matches[0] if matches else None
        if release and self.target_commit is not None:
            require(
                release.get("target_commitish") == self.target_commit,
                "existing release targets another distribution commit",
            )
            self.verify_tag_target(tag)
        return release

    def verify_tag_target(self, tag):
        """Never adopt or move a tag that names another distribution revision."""
        refs = self.api(self.base + "/git/matching-refs/tags/" + quote(tag, safe=""))
        if any(ref["ref"] == "refs/tags/" + tag for ref in refs):
            resolved = self.api(self.base + "/commits/" + quote(tag, safe=""))
            require(
                resolved["sha"] == self.target_commit,
                "existing tag points to another commit",
            )

    def create_draft(self, tag, marker):
        require(
            self.target_commit is not None,
            "read-only transport cannot create a release",
        )
        commit = self.api(self.base + "/commits/" + self.target_commit)
        require(commit["sha"] == self.target_commit, "distribution commit not found")
        # Existing tags must resolve to the intended commit; do not move tags.
        self.verify_tag_target(tag)
        return self.api(
            self.base + "/releases",
            method="POST",
            body={
                "tag_name": tag,
                "target_commitish": self.target_commit,
                "name": tag,
                "body": marker,
                "draft": True,
                "prerelease": False,
            },
        )

    def list_assets(self, release_id):
        pages = self.api(
            self.base + f"/releases/{int(release_id)}/assets?per_page=100",
            paginate=True,
        )
        return [asset for page in pages for asset in page]

    def upload(self, release_id, path):
        require(self.target_commit is not None, "read-only transport cannot upload")
        release = self.api(self.base + f"/releases/{int(release_id)}")
        require(
            release["id"] == release_id
            and release["draft"] is True
            and release.get("target_commitish") == self.target_commit,
            "upload target is not the expected draft",
        )
        upload_url = release["upload_url"].split("{", 1)[0]
        parsed = urlparse(upload_url)
        require(
            parsed.scheme == "https"
            and parsed.netloc == "uploads.github.com"
            and parsed.path == f"/{self.base}/releases/{int(release_id)}/assets"
            and not parsed.query
            and not parsed.fragment,
            "unexpected GitHub upload URL",
        )
        endpoint = upload_url + "?name=" + quote(path.name, safe="")
        # gh reads the verified temporary file directly; no shell, token extraction,
        # clobber, deletion, or automatic retry of an uncertain mutation.
        result = subprocess.run(
            [
                "gh",
                "api",
                endpoint,
                "--method",
                "POST",
                "-H",
                "Content-Type: application/octet-stream",
                "--input",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=3600,
        )
        require(
            result.returncode == 0,
            "asset upload failed; reconcile before retry: " + result.stderr.strip(),
        )
        uploaded = json.loads(result.stdout)
        require(
            uploaded["name"] == path.name,
            "GitHub renamed the asset; reconcile before retry",
        )

    def sha256(self, asset_id):
        with tempfile.TemporaryFile() as stream:
            result = subprocess.run(
                [
                    "gh",
                    "api",
                    self.base + f"/releases/assets/{int(asset_id)}",
                    "-H",
                    "Accept: application/octet-stream",
                ],
                stdout=stream,
                stderr=subprocess.PIPE,
                check=False,
                timeout=3600,
            )
            require(result.returncode == 0, "asset read-back failed")
            stream.seek(0)
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def finalize(self, release_id):
        result = self.api(
            self.base + f"/releases/{int(release_id)}",
            method="PATCH",
            body={"draft": False, "make_latest": "false"},
        )
        require(result["draft"] is False, "GitHub did not confirm publication")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("assets", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--distribution-commit")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument(
        "--catalog", type=Path, help="existing public catalog, read only"
    )
    parser.add_argument(
        "--catalog-output",
        type=Path,
        help="new proposed catalog; never overwrite history",
    )
    parser.add_argument(
        "--execute", action="store_true", help="create/resume an approved draft"
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="publish after exact final owner approval",
    )
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    verify_files(manifest, args.assets)
    require(not args.finalize or args.execute, "--finalize requires --execute")
    require(
        bool(args.catalog) == bool(args.catalog_output),
        "catalog input and output must be supplied together",
    )
    require(
        not args.catalog or args.execute,
        "catalog projection requires remote verification",
    )
    if args.catalog_output:
        require(
            not args.catalog_output.exists() and not args.catalog_output.is_symlink(),
            "catalog output already exists",
        )
    if not args.execute:
        print(
            json.dumps(
                {
                    "state": "offline-preflight",
                    "manifest_sha256": manifest_digest(manifest),
                    "asset_count": len(manifest["assets"]),
                    "publication_approved": False,
                }
            )
        )
        return
    require(
        args.approval and args.distribution_commit and args.receipt,
        "execution requires --approval, --distribution-commit and --receipt",
    )
    approval = json.loads(args.approval.read_text(encoding="utf-8"))
    verify_approval(manifest, approval, publication=args.finalize)
    # One canonical receipt per tag; workflow concurrency must also serialize tags.
    lock = args.receipt.with_suffix(args.receipt.suffix + ".lock")
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps({"pid": os.getpid(), "tag": manifest["tag"]}))
    try:
        remote = GitHub(args.distribution_commit)
        result = publish(
            manifest,
            args.assets,
            approval,
            remote,
            args.receipt,
            finalize=args.finalize,
        )
        if args.catalog:
            from catalog import append_release, release_entry

            previous = json.loads(args.catalog.read_text(encoding="utf-8"))
            entry = release_entry(
                manifest, result, remote.find_release(manifest["tag"])
            )
            proposed = append_release(previous, entry)
            with args.catalog_output.open("xb") as stream:
                stream.write(canonical_bytes(proposed))
        print(json.dumps(result))
    finally:
        lock.unlink()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(str(exc)) from exc
