"""Validate the public static site and its versioned audio catalog."""

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")
REQUIRED = (
    "index.html",
    "catalog.json",
    ".nojekyll",
    "assets/css/main.css",
    "assets/js/app.js",
)
TOP_LEVEL = (
    "schema_version",
    "catalog_id",
    "project_name",
    "source_repository",
    "distribution_repository",
    "releases",
)


class SiteLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        for key in ("href", "src"):
            if attrs.get(key):
                self.refs.append((key, attrs[key]))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_catalog(catalog, *, registry=None):
    require(isinstance(catalog, dict), "catalog must be a JSON object")
    require(
        all(key in catalog for key in TOP_LEVEL),
        "catalog is missing required top-level fields",
    )
    require(
        type(catalog["schema_version"]) is int
        and catalog["schema_version"] in (1, 2, 3),
        "unsupported schema_version (supported: 1, 2, 3)",
    )
    for key in TOP_LEVEL[1:5]:
        require(
            isinstance(catalog[key], str) and catalog[key].strip(),
            f"{key} must be a non-empty string",
        )
    for key in ("source_repository", "distribution_repository"):
        parsed = urlparse(catalog[key])
        require(
            parsed.scheme == "https" and bool(parsed.netloc),
            f"{key} must be an absolute HTTPS URL",
        )
    require(
        "published_at" not in catalog or isinstance(catalog["published_at"], str),
        "published_at must be a string when present",
    )
    require(isinstance(catalog["releases"], list), "releases must be an array")
    if catalog["schema_version"] in (2, 3):
        from publication import fields

        fields(catalog, TOP_LEVEL, ("published_at",))
    asset_ids = set()
    editions, tags = set(), set()
    for release in catalog["releases"]:
        if catalog["schema_version"] in (2, 3):
            from catalog_contract import validate_release

            if catalog["schema_version"] == 3 and "manifest_repository" in release:
                from catalog_contract import validate_transferred_release

                validate_transferred_release(release, registry=registry)
            else:
                validate_release(release)
            require(
                release["version"] not in editions and release["tag"] not in tags,
                "duplicate release edition or tag",
            )
            editions.add(release["version"])
            tags.add(release["tag"])
        require(isinstance(release, dict), "release entries must be objects")
        for field in (
            "version",
            "channel",
            "date",
            "source_ocf_commit",
            "source_ocf_version",
            "release_url",
            "release_notes_url",
            "functions",
        ):
            require(field in release, f"release is missing required field: {field}")
        for field in (
            "version",
            "channel",
            "date",
            "source_ocf_commit",
            "source_ocf_version",
        ):
            require(
                isinstance(release[field], str) and release[field],
                f"release {field} must be a non-empty string",
            )
        for field in ("release_url", "release_notes_url"):
            parsed = (
                urlparse(release[field]) if isinstance(release[field], str) else None
            )
            require(
                parsed and parsed.scheme == "https" and parsed.netloc,
                f"{field} must be an absolute HTTPS URL",
            )
        require(
            isinstance(release["functions"], list), "release functions must be an array"
        )
        for function in release["functions"]:
            require(isinstance(function, dict), "function entries must be objects")
            for field in ("function_id", "title", "languages", "voices", "sessions"):
                require(
                    field in function, f"function is missing required field: {field}"
                )
            for field in ("function_id", "title"):
                require(
                    isinstance(function[field], str) and function[field],
                    f"function {field} must be a non-empty string",
                )
            require(
                all(
                    isinstance(function[field], list)
                    for field in ("languages", "voices", "sessions")
                ),
                "languages, voices, and sessions must be arrays",
            )
            for session in function["sessions"]:
                require(
                    isinstance(session, dict)
                    and isinstance(session.get("assets"), list),
                    "session entries must contain an assets array",
                )
                for asset in session["assets"]:
                    require(isinstance(asset, dict), "asset entries must be objects")
                    for field in (
                        "asset_id",
                        "filename",
                        "format",
                        "download_url",
                        "sha256",
                    ):
                        require(
                            field in asset, f"asset is missing required field: {field}"
                        )
                    require(
                        isinstance(asset["asset_id"], str) and asset["asset_id"],
                        "asset_id must be a non-empty string",
                    )
                    for field in ("filename", "format"):
                        require(
                            isinstance(asset[field], str) and asset[field],
                            f"asset {field} must be a non-empty string",
                        )
                    require(
                        asset["asset_id"] not in asset_ids,
                        f"duplicate asset identifier: {asset['asset_id']}",
                    )
                    asset_ids.add(asset["asset_id"])
                    parsed = (
                        urlparse(asset["download_url"])
                        if isinstance(asset["download_url"], str)
                        else None
                    )
                    require(
                        parsed and parsed.scheme == "https" and parsed.netloc,
                        "download_url must be an absolute HTTPS URL",
                    )
                    require(
                        isinstance(asset["sha256"], str)
                        and SHA256.fullmatch(asset["sha256"]),
                        f"invalid SHA-256 for asset {asset['asset_id']}",
                    )
                    for field in (
                        "size_bytes",
                        "duration_seconds",
                        "sample_rate_hz",
                        "bit_depth",
                        "channels",
                    ):
                        if field in asset:
                            require(
                                type(asset[field]) in (int, float)
                                and asset[field] >= 0,
                                f"asset {field} must be a non-negative number",
                            )
                    require(
                        isinstance(asset.get("mirrors", []), list),
                        "asset mirrors must be an array",
                    )
                    for mirror in asset.get("mirrors", []):
                        parsed = urlparse(mirror) if isinstance(mirror, str) else None
                        require(
                            parsed and parsed.scheme == "https" and parsed.netloc,
                            "mirror URLs must be absolute HTTPS URLs",
                        )
                    require(
                        isinstance(asset.get("companion_files", []), list),
                        "companion_files must be an array",
                    )

    if catalog["schema_version"] in (2, 3):
        extras = [
            asset
            for release in catalog["releases"]
            for group in release["preparations"]
            for session in group["sessions"]
            for asset in session["assets"]
        ]
        extras += [
            asset
            for release in catalog["releases"]
            for asset in release["collections"] + release["companions"]
        ]
        for asset in extras:
            require(asset["asset_id"] not in asset_ids, "duplicate asset identifier")
            asset_ids.add(asset["asset_id"])


def validate_site():
    for relative in REQUIRED:
        require((SITE / relative).is_file(), f"required site file missing: {relative}")
    try:
        catalog = json.loads((SITE / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"catalog.json is invalid: {exc}") from exc
    validate_catalog(catalog)
    parser = SiteLinks()
    parser.feed((SITE / "index.html").read_text(encoding="utf-8"))
    for key, ref in parser.refs:
        url = urlparse(ref)
        if url.scheme or url.netloc or ref.startswith("mailto:"):
            continue
        path = url.path
        if path:
            require((SITE / path).is_file(), f"missing local {key}: {ref}")
        if ref.startswith("#"):
            require(ref[1:] in parser.ids, f"broken internal navigation: {ref}")


if __name__ == "__main__":
    try:
        validate_site()
    except (ValueError, OSError) as exc:
        print(f"Site validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("Site validation passed.")
