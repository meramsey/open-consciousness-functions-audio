"""Validate the public static site and its versioned audio catalog."""

import argparse
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")
REQUIRED = (
    "index.html",
    "catalog.json",
    ".nojekyll",
    "assets/css/main.css",
    "assets/css/website.css",
    "assets/favicon.svg",
    "assets/js/app.js",
    "assets/js/docs.js",
    "source.json",
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
        self.text = []
        self.function_ids = set()
        self.domain_groups = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if attrs.get("data-function-id"):
            self.function_ids.add(attrs["data-function-id"])
        if attrs.get("data-domain-group"):
            self.domain_groups.add(attrs["data-domain-group"])
        for key in ("href", "src"):
            if attrs.get(key):
                self.refs.append((key, attrs[key]))

    def handle_data(self, data):
        if data.strip():
            self.text.append(data.strip())


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


def _resolve_local_reference(site_root: Path, page: Path, reference: str):
    url = urlparse(reference)
    if url.scheme or url.netloc:
        require(url.scheme in {"https", "mailto"}, f"unsafe external URL: {reference}")
        if url.scheme == "https":
            require(bool(url.netloc), f"invalid external URL: {reference}")
        return None
    relative = unquote(url.path).replace("\\", "/")
    target = page if not relative else (page.parent / relative)
    if target.is_dir() or url.path.endswith("/"):
        target = target / "index.html"
    target = target.resolve()
    require(
        target.is_relative_to(site_root.resolve()),
        f"website URL escapes site root: {reference}",
    )
    require(
        target.is_file(),
        f"missing local website target: {reference} from {page.relative_to(site_root)}",
    )
    return target


def _validate_documentation_site(site_root: Path):
    pin_path = site_root / "source.json"
    index_path = site_root / "documentation-index.json"
    require(
        pin_path.is_file() and index_path.is_file(),
        "documentation source pin or index is missing",
    )
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    require(
        pin.get("schema_version") == 1
        and pin.get("source_repository")
        == "https://github.com/ocfproject-org/open-consciousness-functions"
        and re.fullmatch(r"[a-f0-9]{40}", pin.get("source_commit", ""))
        and pin.get("locale") == "en-US"
        and isinstance(pin.get("source_version"), str)
        and pin["source_version"].strip()
        and pin.get("exporter") == "ocf.public-site-guides/1"
        and set(pin)
        == {
            "schema_version",
            "source_repository",
            "source_commit",
            "source_version",
            "locale",
            "exporter",
        },
        "invalid pinned OCF source descriptor",
    )
    require(index.get("schema_version") == 1, "unsupported documentation index schema")
    require(
        index.get("source_commit") == pin["source_commit"],
        "documentation index source commit differs from pin",
    )
    receipt_path = site_root / "site-build-receipt.json"
    require(receipt_path.is_file(), "documentation build receipt is missing")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    require(
        receipt.get("schema_version") == 1
        and receipt.get("builder") == "ocf.audio-library-pages/1",
        "unsupported website build receipt",
    )
    require(
        receipt.get("source_commit") == pin["source_commit"]
        and receipt.get("source_repository") == pin["source_repository"]
        and receipt.get("source_version") == pin["source_version"]
        and receipt.get("locale") == pin["locale"],
        "website receipt source identity differs from pin",
    )
    require(
        receipt.get("catalog_sha256")
        == hashlib.sha256((site_root / "catalog.json").read_bytes()).hexdigest(),
        "website receipt catalog hash mismatch",
    )
    require(
        receipt.get("publication_or_listening_approval_inferred") is False,
        "website receipt must not infer publication or listening approval",
    )
    functions = index.get("functions")
    require(
        type(functions) is list and len(functions) == 58,
        "documentation index must contain 58 functions",
    )
    identities = [row.get("function_id") for row in functions if isinstance(row, dict)]
    require(
        len(identities) == 58 and len(set(identities)) == 58,
        "documentation index has duplicate or missing function IDs",
    )
    require(
        all(
            re.fullmatch(r"OCF-[A-Z]{3}-[0-9]{3}", identity or "")
            for identity in identities
        ),
        "documentation index contains an invalid function ID",
    )
    expected = {
        "start/index.html",
        "historical-names/index.html",
        "listening/index.html",
        "listening/android/index.html",
        "listening/ios/index.html",
        "listening/windows/index.html",
        "listening/macos/index.html",
        "listening/linux/index.html",
        "functions/index.html",
        "quick-reference/index.html",
        "relationships/index.html",
        "downloads/index.html",
        "preparation-learning/index.html",
        "about/index.html",
    }
    expected.update(f"functions/{identity}/index.html" for identity in identities)
    for relative in expected:
        require(
            (site_root / relative).is_file(),
            f"documentation page is missing: {relative}",
        )

    parsed_pages = {}
    pages = sorted(site_root.rglob("*.html"))
    for page in pages:
        parser = SiteLinks()
        parser.feed(page.read_text(encoding="utf-8"))
        parsed_pages[page.resolve()] = parser
        require(
            bool(parser.ids),
            f"HTML page has no anchor IDs: {page.relative_to(site_root)}",
        )
        for _kind, reference in parser.refs:
            url = urlparse(reference)
            target = _resolve_local_reference(site_root, page, reference)
            if url.fragment and target and target.suffix.lower() == ".html":
                target_parser = parsed_pages.get(target)
                if target_parser is None:
                    target_parser = SiteLinks()
                    target_parser.feed(target.read_text(encoding="utf-8"))
                    parsed_pages[target] = target_parser
                require(
                    unquote(url.fragment) in target_parser.ids,
                    f"broken website fragment {reference} from {page.relative_to(site_root)}",
                )
    for row in functions:
        identity = row["function_id"]
        require(
            row.get("href") == f"functions/{identity}/",
            f"function guide URL is not stable: {identity}",
        )
        page = site_root / row["href"] / "index.html"
        parser = parsed_pages.get(page.resolve())
        require(parser is not None, f"function guide is not valid HTML: {identity}")
        require(
            identity in parser.function_ids,
            f"function guide identity mismatch: {identity}",
        )
    primary_domains = {row.get("primary_category") for row in functions}
    directory = parsed_pages[(site_root / "functions" / "index.html").resolve()]
    require(
        None not in primary_domains and directory.domain_groups == primary_domains,
        "function directory does not group every primary canonical domain",
    )
    inventory = {
        path.relative_to(site_root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(site_root.rglob("*"))
        if path.is_file() and path.name != "site-build-receipt.json"
    }
    inventory_digest = hashlib.sha256(
        json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    require(
        receipt.get("site_inventory_sha256") == inventory_digest,
        "website build receipt inventory hash mismatch",
    )
    require(
        receipt.get("file_count") == len(inventory),
        "website build receipt file count mismatch",
    )


def validate_site(site_root: Path | None = None):
    site_root = Path(site_root or SITE)
    for relative in REQUIRED:
        require(
            (site_root / relative).is_file(), f"required site file missing: {relative}"
        )
    try:
        catalog = json.loads((site_root / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"catalog.json is invalid: {exc}") from exc
    validate_catalog(catalog)
    if (site_root / "documentation-index.json").exists():
        _validate_documentation_site(site_root)
    else:
        parser = SiteLinks()
        parser.feed((site_root / "index.html").read_text(encoding="utf-8"))
        for key, ref in parser.refs:
            url = urlparse(ref)
            if url.scheme or url.netloc or ref.startswith("mailto:"):
                continue
            path = url.path
            if path:
                require((site_root / path).is_file(), f"missing local {key}: {ref}")
            if ref.startswith("#"):
                require(ref[1:] in parser.ids, f"broken internal navigation: {ref}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site_root", nargs="?", type=Path, default=SITE)
    args = parser.parse_args()
    try:
        validate_site(args.site_root)
    except (ValueError, OSError) as exc:
        print(f"Site validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("Site validation passed.")
