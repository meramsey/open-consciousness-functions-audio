"""Build the documentation-first static website from pinned OCF docs and releases."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import tempfile
import time
import unicodedata
import urllib.request
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit

from catalog import validate_catalog

SOURCE_REPOSITORY = "https://github.com/ocfproject-org/open-consciousness-functions"
SITE_REPOSITORY = "https://github.com/ocfproject-org/open-consciousness-functions-audio"
PUBLIC_ORIGIN = "https://ocfproject.org/"
EXPORTER = "ocf.public-site-guides/1"
HISTORICAL_LOOKUP_SOURCE = "docs/releases/OCF_HISTORICAL_LOOKUP_CURRENT.md"
PREPARATION_FIRST_GUIDANCE = (
    "Complete Preparation Learning before using any OCF function. Only people who "
    "have already learned the official Human Plus preparation track may skip it."
)
STALE_CUE_DISTINCTION_NOTE = (
    "Function guides distinguish exact display cues from exact spoken cues. Spelling,\n"
    "hyphens, and spoken wording can differ. A cue identifies a command; it does not\n"
    "by itself supply an activation procedure. Where reviewed instructions are absent,\n"
    "the guide says so rather than guessing breathing, repetition, or timing steps."
)
HISTORICAL_LOOKUP_KIND_LABELS = {
    "former-title": "Former title",
    "former-primary": "Former primary cue",
    "former-teaching": "Former teaching phrase",
    "legacy-phrase": "Legacy phrase",
}


def _public_historical_name(function_id, name):
    return not (
        function_id == "OCF-PRF-002"
        and name.get("kind") == "former-primary"
        and name.get("text") == "PLUS-STRONG"
    )
PUBLIC_DISCOVERY_STATUSES = {"canonical", "reviewed"}


def _historical_lookup_form(text):
    """Exact same-function comparison with only Unicode, case and whitespace normalization."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


FORBIDDEN_PUBLIC_KEYS = {
    "narration",
    "narration_text",
    "entries",
    "source_path",
    "evidence",
    "bindings",
    "editorial_decisions",
    "historical_lookup",
    "sources",
}
MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024
TRANSIENT_HTTP_STATUS = {429, 500, 502, 503, 504}
TRANSCRIPT_FETCH_ATTEMPTS = 3


def digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def validate_guide_export(document, source_pin):
    """Check the cross-repository export contract and its deterministic receipt."""
    _require(isinstance(document, dict), "guide export must be an object")
    _require(document.get("schema_version") == 1, "unsupported guide export schema")
    _require(document.get("exporter") == EXPORTER, "unsupported guide exporter")
    _require(
        document.get("source_repository") == SOURCE_REPOSITORY,
        "wrong OCF source repository",
    )
    _require(
        document.get("locale") == "en-US", "website export locale is not supported"
    )
    _require(
        source_pin.get("schema_version") == 1
        and source_pin.get("source_repository") == SOURCE_REPOSITORY
        and source_pin.get("locale") == "en-US"
        and source_pin.get("exporter") == EXPORTER
        and isinstance(source_pin.get("source_version"), str)
        and source_pin["source_version"].strip(),
        "source pin has an invalid repository, locale, exporter, or version",
    )
    _require(
        re.fullmatch(r"[a-f0-9]{40}", str(source_pin.get("source_commit", "")))
        is not None,
        "source pin must contain an exact commit",
    )
    _require(
        document.get("source_commit") == source_pin["source_commit"],
        "guide export source commit differs from the pinned OCF commit",
    )
    functions = document.get("functions")
    _require(
        isinstance(functions, list) and len(functions) == 58,
        "guide export must contain 58 functions",
    )
    identities = [row.get("function_id") for row in functions if isinstance(row, dict)]
    _require(
        len(identities) == 58 and len(set(identities)) == 58,
        "guide export has duplicate/missing function IDs",
    )
    _require(
        all(
            re.fullmatch(r"OCF-[A-Z]{3}-[0-9]{3}", identity or "")
            for identity in identities
        ),
        "guide export has an invalid function ID",
    )
    receipt = document.get("build_receipt")
    _require(isinstance(receipt, dict), "guide export build receipt is missing")
    _require(
        receipt.get("function_count") == 58,
        "guide export function count receipt mismatch",
    )
    _require(
        receipt.get("narration_text_included") is False,
        "canonical narration text is forbidden in public guide export",
    )
    _require(
        receipt.get("source_evidence_paths_included") is False,
        "source evidence paths are forbidden in public guide export",
    )
    _require(
        receipt.get("draft_procedures_included") is False,
        "draft procedure text is forbidden in public guide export",
    )
    _require(
        receipt.get("relationship_proposals_included") is False,
        "draft relationship proposals are forbidden in public guide export",
    )
    _require(
        receipt.get("functions_sha256") == digest(functions),
        "guide export functions hash mismatch",
    )
    content = {key: value for key, value in document.items() if key != "build_receipt"}
    _require(
        receipt.get("export_content_sha256") == digest(content),
        "guide export content hash mismatch",
    )
    guide = document.get("listening_guide", {})
    _require(isinstance(guide.get("markdown"), str), "listening guide is missing")
    _require(
        hashlib.sha256(guide["markdown"].encode("utf-8")).hexdigest()
        == guide.get("source_sha256"),
        "listening guide source hash mismatch",
    )
    for row in functions:
        _require(
            row.get("documentation_status") == "canonical-function-resource",
            f"{row['function_id']}: unexpected documentation status",
        )
        _require(
            re.fullmatch(r"[a-f0-9]{64}", row.get("canonical_resource_sha256", ""))
            is not None,
            f"{row['function_id']}: invalid canonical-resource fingerprint",
        )
        for command in row.get("commands", []):
            _require(
                command.get("command_status") == "active",
                f"{row['function_id']}: active command has invalid status",
            )
            _require(
                command.get("role") not in {"legacy-alias", "access-close"},
                f"{row['function_id']}: inactive command exported",
            )
            _require(
                command.get("procedure_status")
                in {"documented", "not-specified", "review-pending"},
                f"{row['function_id']}: invalid procedure status",
            )
            if command.get("procedure_status") != "documented":
                _require(
                    not command.get("procedure_steps"),
                    f"{row['function_id']}: unapproved procedure steps exported",
                )
        for command in row.get("historical_commands", []):
            _require(
                command.get("command_status") == "historical-inactive",
                f"{row['function_id']}: historical cue is not marked inactive",
            )
        for relation in row.get("related_functions", []):
            _require(
                relation.get("dependency") == "optional"
                and relation.get("direction") == "outgoing",
                f"{row['function_id']}: relationship is not an optional outgoing link",
            )
    _require(
        not (FORBIDDEN_PUBLIC_KEYS & set(_walk_keys(functions))),
        "guide export contains a private/source-authority field",
    )
    return document


def safe_https(value):
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.netloc)
            and not parsed.username
            and not parsed.password
        )
    except (TypeError, ValueError):
        return False


def _request_public_asset(asset):
    url = asset.get("download_url")
    _require(safe_https(url), "companion asset URL must be HTTPS")
    before = urlsplit(url)
    _require(
        before.hostname == "github.com"
        and before.path.startswith(
            "/ocfproject-org/open-consciousness-functions-audio/releases/download/"
        ),
        "companion asset is outside the official published release URL space",
    )
    request = urllib.request.Request(
        url, headers={"User-Agent": "OCF-public-site-build/1"}
    )
    for attempt in range(TRANSCRIPT_FETCH_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                final = urlsplit(response.geturl())
                _require(
                    final.scheme == "https"
                    and final.hostname
                    in {"github.com", "release-assets.githubusercontent.com"},
                    "companion download redirected outside GitHub release hosting",
                )
                return response.read(MAX_TRANSCRIPT_BYTES + 1)
        except HTTPError as exc:
            if (
                exc.code not in TRANSIENT_HTTP_STATUS
                or attempt + 1 == TRANSCRIPT_FETCH_ATTEMPTS
            ):
                exc.close()
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                server_delay = float(retry_after) if retry_after else 0.0
            except ValueError:
                server_delay = 0.0
            exc.close()
            time.sleep(min(5.0, max(0.25 * (2**attempt), server_delay)))
    raise AssertionError("bounded transcript retry loop exited unexpectedly")


def fetch_transcript(asset, *, fetcher=None):
    fmt = asset.get("format")
    _require(
        fmt in {"txt", "vtt"},
        "only published TXT/VTT transcript companions may be mirrored",
    )
    _require(
        re.fullmatch(r"asset-[a-f0-9]{64}", asset.get("asset_id", "")) is not None,
        "invalid published transcript asset ID",
    )
    expected_size = asset.get("size_bytes")
    _require(
        type(expected_size) is int and 0 < expected_size <= MAX_TRANSCRIPT_BYTES,
        "published transcript size is invalid or exceeds limit",
    )
    body = (fetcher or _request_public_asset)(asset)
    _require(
        isinstance(body, bytes) and len(body) == expected_size,
        "published transcript size verification failed",
    )
    _require(
        hashlib.sha256(body).hexdigest() == asset.get("sha256"),
        "published transcript SHA-256 verification failed",
    )
    try:
        body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("published transcript is not valid UTF-8") from exc
    return body


def _copy_static_site(site_root: Path, output: Path):
    _require(site_root.is_dir(), "source site directory is missing")
    _require(
        not output.exists(), "site build target already exists; refusing to overwrite"
    )
    output.mkdir(parents=True)
    for path in sorted(site_root.rglob("*")):
        relative = path.relative_to(site_root)
        if path.is_symlink():
            raise ValueError(f"source site contains a symlink: {relative}")
        target = output / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def _html(value):
    return html.escape(str(value), quote=True)


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-") or "section"


def _inline(markdown):
    # Escape source text first; only construct links with safe schemes/relative paths.
    text = _html(markdown)
    token_links = []
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    def link(match):
        label, target = match.group(1), match.group(2)
        parsed = urlsplit(target)
        safe = (
            (
                parsed.scheme == "https"
                and parsed.netloc
                and not parsed.username
                and not parsed.password
            )
            or (
                not parsed.scheme
                and not parsed.netloc
                and not target.startswith("/")
                and not target.startswith("\\")
                and "\\" not in target
            )
            or target.startswith("#")
        )
        if not safe:
            return label
        token = f"\x00LINK{len(token_links)}\x00"
        token_links.append(f'<a href="{_html(target)}">{label}</a>')
        return token

    # Markdown delimiters are not HTML; source tags remain escaped.
    text = link_pattern.sub(link, text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    for index, rendered in enumerate(token_links):
        text = text.replace(f"\x00LINK{index}\x00", rendered)
    return text


def render_markdown(markdown):
    blocks = re.split(r"\n\s*\n", markdown.strip())
    output = []
    for block in blocks:
        lines = block.splitlines()
        heading = (
            re.fullmatch(r"(#{1,4})\s+(.+)", lines[0]) if len(lines) == 1 else None
        )
        if heading:
            level = len(heading.group(1))
            text = heading.group(2)
            output.append(
                f'<h{level} id="{_html(_slug(text))}">{_inline(text)}</h{level}>'
            )
        elif (unordered_items := _unordered_list_items(lines)) is not None:
            output.append(
                "<ul>"
                + "".join(f"<li>{_inline(item)}</li>" for item in unordered_items)
                + "</ul>"
            )
        elif (ordered_items := _ordered_list_items(lines)) is not None:
            output.append(
                "<ol>"
                + "".join(f"<li>{_inline(item)}</li>" for item in ordered_items)
                + "</ol>"
            )
        else:
            output.append(
                "<p>" + _inline(" ".join(line.strip() for line in lines)) + "</p>"
            )
    return "\n".join(output)


def _ordered_list_items(lines):
    items = []
    for line in lines:
        match = re.match(r"^\d+\. (.+)$", line)
        if match:
            items.append(match.group(1))
        elif (
            items
            and re.match(r"^\s{2,}\S", line)
            and not re.match(r"^\s*[-+*]\s", line)
        ):
            items[-1] += " " + line.strip()
        else:
            return None
    return items or None


def _unordered_list_items(lines):
    items = []
    for line in lines:
        match = re.match(r"^- (.+)$", line)
        if match:
            items.append(match.group(1))
        elif (
            items
            and re.match(r"^\s{2,}\S", line)
            and not re.match(r"^\s*[-+*]\s", line)
        ):
            items[-1] += " " + line.strip()
        else:
            return None
    return items or None


def _read_markdown(content_dir: Path, relative: str):
    path = content_dir / relative
    resolved = path.resolve()
    _require(
        resolved.is_relative_to(content_dir.resolve())
        and path.is_file()
        and not path.is_symlink(),
        f"website content file unavailable: {relative}",
    )
    return path.read_text(encoding="utf-8")


def _markdown_section_body(markdown, heading):
    pattern = re.compile(
        rf"(?ms)^## {re.escape(heading)}\n\n(.*?)(?=^## |\Z)"
    )
    matches = list(pattern.finditer(markdown))
    _require(len(matches) == 1, f"expected one Markdown section: {heading}")
    return matches[0].group(1).strip()


def _replace_markdown_section(markdown, heading, body):
    pattern = re.compile(
        rf"(?ms)^## {re.escape(heading)}\n\n.*?(?=^## |\Z)"
    )
    _require(len(pattern.findall(markdown)) == 1, f"expected one Markdown section: {heading}")
    replacement = f"## {heading}\n\n{body.strip()}\n\n" if body.strip() else ""
    return pattern.sub(lambda _: replacement, markdown, count=1)


def _replace_markdown_once(markdown, old, new, label):
    _require(markdown.count(old) == 1, f"expected one source passage to reorganize: {label}")
    return markdown.replace(old, new, 1)


def _replace_markdown_wrapped_once(markdown, old, new, label):
    pattern = r"\s+".join(re.escape(word) for word in old.split())
    matches = list(re.finditer(pattern, markdown))
    _require(len(matches) == 1, f"expected one source passage to reorganize: {label}")
    match = matches[0]
    return markdown[:match.start()] + new + markdown[match.end():]


def _function_audio_availability(functions, catalog, sessions_by_function):
    releases = catalog["releases"]
    scope = "; ".join(
        f'{release["tag"]} (edition {release["version"]})' for release in releases
    ) or "no published release in the verified catalog"
    available = sum(bool(sessions_by_function.get(function["function_id"])) for function in functions)
    preparation_count = sum(
        len(group["sessions"])
        for release in releases
        for group in release.get("preparations", [])
    )
    return (
        f"{available} of {len(functions)} canonical function guides have at least one published recording "
        f"in the verified catalog snapshot ({scope}). The {preparation_count} Preparation Learning "
        "session is listed separately from function records. Check an individual guide for the "
        "exact published locale, voice, and edition; this snapshot does not promise future availability."
    )


def _listening_guide_for_publication(markdown, catalog, functions, sessions_by_function):
    markdown = markdown.replace(STALE_CUE_DISTINCTION_NOTE, "")
    markdown = _replace_markdown_once(markdown, "# Welcome to OCF", "# Listening Guide", "page title")
    markdown = _replace_markdown_section(
        markdown,
        "What OCF is",
        "For the project overview and optional first-practice suggestions, see "
        "[About OCF](../about/) and [Start Here](../start/).",
    )
    markdown = _replace_markdown_once(markdown, "## What OCF is", "## Project overview", "overview section label")

    before = _markdown_section_body(markdown, "Before listening")
    comfortable = " ".join(_markdown_section_body(markdown, "A comfortable environment").split())
    repeated_safe_place = "Choose a place where you can safely give the recording your attention. "
    _require(comfortable.startswith(repeated_safe_place), "comfortable-environment opening changed")
    comfortable = comfortable[len(repeated_safe_place):]
    repeated_vigilance = " Do not listen while driving, operating equipment, or doing anything that requires vigilance."
    _require(comfortable.count(repeated_vigilance.strip()) == 1, "comfortable-environment safety reminder changed")
    comfortable = comfortable.replace(repeated_vigilance.strip(), "", 1).strip()
    markdown = _replace_markdown_section(markdown, "Before listening", f"{before}\n\n{comfortable}")
    markdown = _replace_markdown_section(markdown, "A comfortable environment", "")

    markdown = _replace_markdown_wrapped_once(
        markdown,
        "Preserve separate left/right stereo playback for intended binaural/channel-separated audio; "
        "mono mixing does not provide equivalent delivery. Separately, check whether",
        "Check whether",
        "redundant player stereo reminder",
    )

    accessibility = _markdown_section_body(markdown, "Accessibility")
    repeated_stereo = (
        "If you cannot use separate left/right stereo headphones or earbuds, use the written guide or an "
        "edition-matched transcript if available, or skip the audio. These text options provide access to "
        "wording; they are not equivalent delivery of the binaural audio or a promise of equivalent effects."
    )
    accessibility = " ".join(accessibility.split())
    _require(repeated_stereo in accessibility, "accessibility stereo alternatives changed")
    accessibility = accessibility.replace(
        repeated_stereo,
        "For the required stereo setup and available text alternatives, see "
        "[Headphones and stereo](#headphones-and-stereo). The text alternatives provide access to wording; "
        "they are not equivalent delivery of the binaural audio or a promise of equivalent effects.",
        1,
    )
    markdown = _replace_markdown_section(markdown, "Accessibility", accessibility)

    availability_answer = _function_audio_availability(functions, catalog, sessions_by_function)
    markdown = _replace_markdown_wrapped_once(
        markdown,
        "No. Function documentation and published audio availability are separate. Check the edition list "
        "on the function page; a catalog entry does not promise a recording.",
        availability_answer,
        "inventory-derived recording availability",
    )
    markdown = _replace_markdown_wrapped_once(
        markdown,
        "Yes. Stereo headphones or stereo earbuds with separate left/right playback are required for the intended "
        "binaural/channel-separated audio. Speakers, mono mixing, or a single earpiece are not equivalent delivery "
        "of that audio. If you cannot use this setup, use the written guide or an edition-matched transcript if "
        "available, or skip the audio; no equivalent effects are promised. Keep any accessibility settings you rely on.",
        "See [Headphones and stereo](#headphones-and-stereo) for the required setup, limitations, and available text alternatives.",
        "stereo FAQ cross-link",
    )
    markdown = _replace_markdown_wrapped_once(
        markdown,
        "Use the function's documented activation steps. A cue identifies a command but does not supply missing "
        "timing, repetition, breathing, or release instructions.",
        "See [Commands and cues](#commands-and-cues) above; do not infer missing activation details from a cue.",
        "cue FAQ cross-link",
    )
    markdown = _replace_markdown_wrapped_once(
        markdown,
        "No particular sensation is required. Read the documented purpose and choose whether the practice is useful "
        "or comfortable for you.",
        "No particular sensation is required. See [Imagery is not required](#imagery-is-not-required) above.",
        "imagery FAQ cross-link",
    )
    markdown = _replace_markdown_wrapped_once(
        markdown,
        "Use the transcript attached to the exact voice, locale, and edition you selected. Do not substitute current "
        "function-guide wording for a published edition's transcript.",
        "Use the exact voice-, locale-, and edition-matched transcript described in [Transcripts](#transcripts) above. "
        "Do not substitute current function-guide wording for a published edition's transcript.",
        "transcript FAQ cross-link",
    )
    return markdown


def _catalog_sessions(catalog):
    sessions_by_function = {
        function["function_id"]: []
        for release in catalog["releases"]
        for function in release["functions"]
    }
    preparation_sessions = []
    for release in catalog["releases"]:
        release_sessions = []
        groups = [(False, group) for group in release["functions"]]
        groups += [(True, group) for group in release.get("preparations", [])]
        for is_preparation, group in groups:
            for session in group["sessions"]:
                session_assets = list(session["assets"])
                if not session_assets:
                    continue
                masters = {
                    asset.get("provenance", {}).get("master_sha256")
                    for asset in session_assets
                }
                if None in masters or len(masters) != 1:
                    raise ValueError(
                        f"session audio assets lack one explicit shared master fingerprint: {release['tag']} / {session['title']}"
                    )
                rows = {
                    "release": release,
                    "group": group,
                    "session": session,
                    "audio_assets": session_assets,
                    "companions": {},
                    "is_preparation": is_preparation,
                    "master_sha256": next(iter(masters)),
                }
                release_sessions.append(rows)
                if is_preparation:
                    preparation_sessions.append(rows)
                else:
                    sessions_by_function.setdefault(group["function_id"], []).append(
                        rows
                    )
        by_master = {}
        for session_rows in release_sessions:
            master = session_rows["master_sha256"]
            if master in by_master:
                raise ValueError(
                    f"published master fingerprint is shared by multiple sessions: {release['tag']} / {master}"
                )
            by_master[master] = session_rows
        for companion in release.get("companions", []):
            master = companion.get("provenance", {}).get("master_sha256")
            session_rows = by_master.get(master)
            if session_rows is None:
                raise ValueError(
                    f"published companion lacks a unique manifest-bound session fingerprint: {release['tag']} / {companion['asset_id']}"
                )
            fmt = companion["format"]
            if fmt in session_rows["companions"]:
                raise ValueError(
                    f"duplicate published companion format for a session: {release['tag']} / {fmt}"
                )
            session_rows["companions"][fmt] = companion
    return sessions_by_function, preparation_sessions


def _verified_sidecars(releases, output, fetcher):
    local = {}
    counts = {"txt": 0, "vtt": 0}
    for session_rows in releases:
        for fmt in ("txt", "vtt"):
            asset = session_rows["companions"].get(fmt)
            if not asset:
                continue
            body = fetch_transcript(asset, fetcher=fetcher)
            relative = f"transcripts/{asset['asset_id']}.{fmt}"
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            local[asset["asset_id"]] = {
                "path": relative,
                "format": fmt,
                "sha256": asset["sha256"],
            }
            counts[fmt] += 1
    return local, counts


def build_public_site(
    *,
    site_root: Path,
    output: Path,
    guide_export: dict,
    catalog: dict,
    source_pin: dict,
    content_dir: Path,
    historical_reference: Path,
    transcript_fetcher=None,
):
    """Build all local pages from one pinned OCF export and verified release catalog."""
    validate_guide_export(guide_export, source_pin)
    validate_catalog(catalog)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    _require(
        not output.exists() and not output.is_symlink(),
        "site build output already exists",
    )
    functions = guide_export["functions"]
    historical_reference = Path(historical_reference)
    _require(
        historical_reference.name == "OCF_HISTORICAL_LOOKUP_CURRENT.md"
        and historical_reference.is_file()
        and not historical_reference.is_symlink(),
        "pinned OCF historical lookup reference is unavailable",
    )
    historical_reference = historical_reference.resolve()
    source_root = historical_reference.parents[2]
    _require(
        historical_reference.relative_to(source_root).as_posix()
        == HISTORICAL_LOOKUP_SOURCE,
        "historical lookup reference must be inside the pinned OCF checkout",
    )
    historical_reference_bytes = historical_reference.read_bytes()
    historical_reference_markdown = historical_reference_bytes.decode("utf-8")
    historical_rows = _historical_lookup_rows(
        historical_reference_markdown, functions, source_root
    )
    sessions_by_function, preparation_sessions = _catalog_sessions(catalog)
    all_session_rows = [
        row for rows in sessions_by_function.values() for row in rows
    ] + preparation_sessions
    _validate_suggested_download_filenames(all_session_rows)
    with tempfile.TemporaryDirectory(
        prefix="ocf-site-build-", dir=output.parent
    ) as staging_name:
        staging = Path(staging_name) / "site"
        _copy_static_site(site_root, staging)
        transcript_paths, transcript_counts = _verified_sidecars(
            all_session_rows, staging, transcript_fetcher
        )
        # Preserve the verified release projection byte-for-value; only JSON formatting changes.
        _write(
            staging / "catalog.json",
            json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

        source_commit = guide_export["source_commit"]
        source_docs_url = f"{SOURCE_REPOSITORY}/tree/{source_commit}/docs"
        root_body = _home_page(functions, catalog, source_commit)
        _write(
            staging / "index.html",
            _shell(
                "Open Consciousness Functions — Guided Audio and Practice Guides",
                root_body,
                "",
                source_commit,
                root=True,
            ),
        )

        docs_dir = staging / "functions"
        _write(
            docs_dir / "index.html",
            _shell(
                "Browse & Listen — OCF Functions",
                _functions_index(functions, sessions_by_function, preparation_sessions),
                "functions",
                source_commit,
                include_catalog=True,
            ),
        )
        for function in functions:
            fid = function["function_id"]
            sessions = sessions_by_function.get(fid, [])
            body = _function_page(function, sessions, transcript_paths, source_commit)
            _write(
                docs_dir / fid / "index.html",
                _shell(
                    f"{function['title']['text']} — OCF",
                    body,
                    f"functions/{fid}",
                    source_commit,
                    toc=True,
                    toc_items=_function_toc_items(),
                    description=_public_description(function),
                ),
            )

        _write(
            staging / "start" / "index.html",
            _shell(
                "Start Here — OCF",
                render_markdown(_read_markdown(content_dir, "start-here.md")),
                "start",
                source_commit,
            ),
        )
        historical_body = _historical_names_page(
            historical_rows,
            functions,
            source_commit,
            historical_reference_sha256=hashlib.sha256(
                historical_reference_bytes
            ).hexdigest(),
        )
        _write(
            staging / "historical-names" / "index.html",
            _shell(
                "Historical Name Lookup — OCF",
                historical_body,
                "historical-names",
                source_commit,
            ),
        )
        listening_source = guide_export["listening_guide"]["markdown"]
        listening_markdown = _listening_guide_for_publication(
            listening_source,
            catalog,
            functions,
            sessions_by_function,
        )
        listening_html = render_markdown(listening_markdown)
        # Retain incoming links when consolidating/renaming public guide sections.
        for old_id, current_id in (
            ("welcome-to-ocf", "listening-guide"),
            ("what-ocf-is", "project-overview"),
            ("a-comfortable-environment", "before-listening"),
        ):
            heading = f'<h2 id="{current_id}">' if current_id != "listening-guide" else f'<h1 id="{current_id}">'
            _require(listening_html.count(heading) == 1, f"legacy listening destination missing: {current_id}")
            listening_html = listening_html.replace(heading, f'<span id="{old_id}"></span>' + heading, 1)

        preparation_paragraph = f"<p>{_html(PREPARATION_FIRST_GUIDANCE)}</p>"
        _require(
            listening_html.count(preparation_paragraph) == 1,
            "Listening Guide must have one preparation-first paragraph",
        )
        listening_html = listening_html.replace(
            preparation_paragraph,
            preparation_paragraph + _preparation_first_link(),
            1,
        )
        listening_html += _recommended_settings(source_commit)
        listening_html += _device_links()
        listening_toc_source = (
            listening_markdown
            + "\n\n## Recommended audio settings\n\n## Device-specific setup"
        )
        _write(
            staging / "listening" / "index.html",
            _shell(
                "Listening Guide — OCF",
                listening_html,
                "listening",
                source_commit,
                toc=True,
                toc_items=_markdown_toc(listening_toc_source),
            ),
        )
        for platform in ("android", "ios", "windows", "macos", "linux"):
            markdown = _read_markdown(content_dir, f"listening/{platform}.md")
            content = render_markdown(markdown)
            _write(
                staging / "listening" / platform / "index.html",
                _shell(
                    f"{platform.title()} Audio Guide — OCF",
                    content,
                    f"listening/{platform}",
                    source_commit,
                    toc=True,
                    toc_items=_markdown_toc(markdown),
                ),
            )

        quick_body = _quick_reference(functions, sessions_by_function)
        _write(
            staging / "quick-reference" / "index.html",
            _shell(
                "Cue Quick Reference — OCF",
                quick_body,
                "quick-reference",
                source_commit,
                docs_js=True,
            ),
        )
        _write(
            staging / "relationships" / "index.html",
            _shell(
                "Approved Related Functions — OCF",
                _relationships_page(functions),
                "relationships",
                source_commit,
            ),
        )
        _write(
            staging / "downloads" / "index.html",
            _shell(
                "Downloads — OCF Audio Library",
                _downloads_page(catalog, preparation_sessions),
                "downloads",
                source_commit,
            ),
        )
        prep_body = _preparation_page(preparation_sessions, transcript_paths)
        _write(
            staging / "preparation-learning" / "index.html",
            _shell(
                "Preparation Learning — OCF",
                prep_body,
                "preparation-learning",
                source_commit,
            ),
        )
        about = _about_page(guide_export, catalog, source_docs_url, transcript_counts)
        _write(
            staging / "about" / "index.html",
            _shell("About OCF", about, "about", source_commit),
        )

        doc_index = {
            "schema_version": 1,
            "source_commit": source_commit,
            "functions": [
                {
                    "function_id": row["function_id"],
                    "title": row["title"]["text"],
                    "description": _public_description(row),
                    "primary_category": row["primary_category"],
                    "primary_category_label": next(
                        category["label"].title()
                        for category in row["categories"]
                        if category["id"] == row["primary_category"]
                    ),
                    "categories": [category["id"] for category in row["categories"]],
                    "cues": [
                        command["spoken_cue"]
                        for command in row["commands"]
                        if command.get("spoken_cue")
                    ],
                    "search_terms": [
                        item["text"]
                        for item in row["tags"] + row["common_uses"]
                        if item.get("status") in PUBLIC_DISCOVERY_STATUSES
                    ],
                    "audio_available": bool(
                        sessions_by_function.get(row["function_id"])
                    ),
                    "href": f"functions/{row['function_id']}/",
                }
                for row in functions
            ],
        }
        _write(
            staging / "documentation-index.json",
            json.dumps(doc_index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        # Browser catalog contains presentation fields only; full provenance remains in catalog.json.
        browse_catalog = {"schema_version": catalog["schema_version"], "releases": []}
        for release in catalog["releases"]:
            public_release = {key: release[key] for key in ("date", "version", "release_url") if key in release}
            for group_key in ("functions", "preparations"):
                public_release[group_key] = []
                for group in release.get(group_key, []):
                    public_group = {key: group[key] for key in ("function_id", "title", "description") if key in group}
                    public_group["sessions"] = []
                    for session in group.get("sessions", []):
                        public_session = {key: value for key, value in session.items() if key != "assets"}
                        public_session["assets"] = [{key: value for key, value in asset.items() if key != "provenance"} for asset in session["assets"]]
                        public_group["sessions"].append(public_session)
                    public_release[group_key].append(public_group)
            for key in ("collections", "companions"):
                public_release[key] = [{field: asset[field] for field in ("filename", "download_url", "sha256") if field in asset} for asset in release.get(key, [])]
            browse_catalog["releases"].append(public_release)
        _write(staging / "browse-catalog.json", json.dumps(browse_catalog, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
        urls = [PUBLIC_ORIGIN + (path.parent.relative_to(staging).as_posix() + "/" if path.parent != staging else "") for path in sorted(staging.rglob("index.html"))]
        _write(staging / "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{_html(url)}</loc></url>" for url in urls) + "</urlset>\n")
        _write(staging / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {PUBLIC_ORIGIN}sitemap.xml\n")
        not_found = _shell("Page not found — OCF", '<h1>Page not found</h1><p>This address may have changed. <a href="functions/">Browse or search the function library</a>, or <a href="start/">Start Here</a>.</p>', "", source_commit, root=True)
        not_found = re.sub(r'href="(?!https:|#)([^"]+)"', lambda match: f'href="{PUBLIC_ORIGIN}{match.group(1)}"', not_found)
        not_found = not_found.replace('src="assets/', f'src="{PUBLIC_ORIGIN}assets/').replace('<meta name="theme-color"', '<meta name="robots" content="noindex"><meta name="theme-color"')
        not_found = re.sub(r'<link rel="canonical"[^>]+>|<meta property="og:url"[^>]+>', '', not_found)
        _write(staging / "404.html", not_found)
        _write_site_receipt(
            staging,
            guide_export=guide_export,
            source_pin=source_pin,
            catalog=catalog,
            summary={
                "function_count": len(functions),
                "category_count": len(
                    {
                        item["id"]
                        for function in functions
                        for item in function["categories"]
                    }
                ),
                "approved_relationship_count": guide_export["build_receipt"][
                    "approved_relationship_count"
                ],
                "published_session_count": len(all_session_rows),
                "function_session_count": sum(
                    len(rows) for rows in sessions_by_function.values()
                ),
                "preparation_session_count": len(preparation_sessions),
                "historical_mapping_count": len(historical_rows),
                "historical_name_count": sum(
                    len(row["names"]) for row in historical_rows
                ),
                "historical_name_kind_counts": {
                    kind: sum(
                        name["kind"] == kind
                        for row in historical_rows
                        for name in row["names"]
                    )
                    for kind in HISTORICAL_LOOKUP_KIND_LABELS
                },
                "historical_reference_sha256": hashlib.sha256(
                    historical_reference_bytes
                ).hexdigest(),
                "transcript_counts": transcript_counts,
                "audio_asset_count": sum(
                    len(row["audio_assets"]) for row in all_session_rows
                ),
            },
        )
        from validate_site import validate_site

        validate_site(staging)
        staged_catalog = json.loads(
            (staging / "catalog.json").read_text(encoding="utf-8")
        )
        _require(
            staged_catalog == catalog,
            "staged catalog differs from the verified release catalog",
        )
        staged_index = json.loads(
            (staging / "documentation-index.json").read_text(encoding="utf-8")
        )
        _require(
            staged_index["source_commit"] == source_commit,
            "staged documentation index source mismatch",
        )
        shutil.copytree(staging, output)
        return json.loads(
            (output / "site-build-receipt.json").read_text(encoding="utf-8")
        )


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _site_inventory(root: Path) -> dict[str, str]:
    inventory = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(
                f"generated site contains a symlink: {path.relative_to(root)}"
            )
        if path.is_file() and path.name != "site-build-receipt.json":
            inventory[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return inventory


def _write_site_receipt(
    root: Path, *, guide_export: dict, source_pin: dict, catalog: dict, summary: dict
) -> dict:
    inventory = _site_inventory(root)
    release_rows = [
        {
            "tag": release.get("tag"),
            "publication_manifest_sha256": release.get("publication_manifest_sha256"),
            "source_ocf_commit": release.get("source_ocf_commit"),
        }
        for release in catalog.get("releases", [])
    ]
    receipt = {
        "schema_version": 1,
        "builder": "ocf.audio-library-pages/1",
        "source_repository": source_pin["source_repository"],
        "source_commit": source_pin["source_commit"],
        "source_version": source_pin["source_version"],
        "locale": source_pin["locale"],
        "guide_exporter": guide_export["exporter"],
        "guide_export_sha256": guide_export["build_receipt"]["export_content_sha256"],
        "catalog_schema_version": catalog["schema_version"],
        "catalog_sha256": hashlib.sha256(
            (root / "catalog.json").read_bytes()
        ).hexdigest(),
        "published_releases": release_rows,
        "file_count": len(inventory),
        "site_inventory_sha256": digest(inventory),
        "publication_or_listening_approval_inferred": False,
        **summary,
    }
    _write(
        root / "site-build-receipt.json",
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return receipt


def _shell(
    title,
    body,
    current,
    source_commit,
    *,
    root=False,
    docs_js=False,
    include_catalog=False,
    toc=False,
    toc_items=None,
    description=None,
):
    canonical = PUBLIC_ORIGIN + (current.strip("/") + "/" if current else "")
    description = description or f"{title.removesuffix(' — OCF')}: OCF guides and verified published recordings."
    depth = 0 if root else current.count("/") + 1
    base = "../" * depth
    primary_nav = [
        ("Start Here", "start/", "start"),
        ("Browse &amp; Listen", "functions/", "functions"),
        ("Quick Reference", "quick-reference/", "quick-reference"),
        ("Listening Guide", "listening/", "listening"),
    ]
    more_nav = [
        ("Historical names", "historical-names/", "historical-names"),
        ("Related functions", "relationships/", "relationships"),
        ("Listen", "functions/#library", ""),
        ("Downloads", "downloads/", "downloads"),
        ("About", "about/", "about"),
    ]
    current_path = current.strip("/")

    def nav_link(label, href, route):
        route = route.strip("/")
        current_attr = ""
        if route and current_path == route:
            current_attr = ' aria-current="page"'
        elif route and current_path.startswith(route + "/"):
            current_attr = ' aria-current="location"'
        return f'<a href="{base}{href}"{current_attr}>{label}</a>'

    primary_links = "".join(
        nav_link(label, href, route) for label, href, route in primary_nav
    )
    more_links = "".join(
        nav_link(label, href, route) for label, href, route in more_nav
    )
    more_current = current_path in {route for _, _, route in more_nav if route}
    more_current_attr = ' aria-current="location"' if more_current else ""
    more_menu = (
        f'<details class="more-menu"><summary{more_current_attr}>More</summary>'
        f'<div class="more-links" role="group" aria-label="More pages">{more_links}</div>'
        "</details>"
    )
    logo_href = base + "index.html"
    logo_current_attr = ' aria-current="page"' if not current_path else ""
    toc_nav = _render_toc(toc_items or []) if toc else ""
    toc_mobile = (
        f'<details class="mobile-toc"><summary>On this page</summary>{toc_nav}</details>'
        if toc_nav
        else ""
    )
    toc_desktop = (
        f'<aside class="desktop-toc" aria-label="On this page">{toc_nav}</aside>'
        if toc_nav
        else ""
    )
    catalog_script = (
        f'<script src="{base}assets/js/app.js" defer></script>'
        if include_catalog
        else ""
    )
    docs_script = f'<script src="{base}assets/js/docs.js" defer></script>'
    content_class = "docs-content home-content" if root else "docs-content"
    return f'''<!doctype html>
<html lang="en-US"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#101a22"><meta name="description" content="{_html(description)}">
<link rel="canonical" href="{_html(canonical)}"><meta property="og:type" content="website"><meta property="og:title" content="{_html(title)}"><meta property="og:description" content="{_html(description)}"><meta property="og:url" content="{_html(canonical)}"><meta name="twitter:card" content="summary">
<title>{_html(title)}</title><link rel="icon" href="{base}assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="{base}assets/css/main.css"><link rel="stylesheet" href="{base}assets/css/website.css">
{catalog_script}{docs_script}<noscript><style>.theme-toggle,.library-tools,.selection-tools,.reference-tools,.transcript-search{{display:none!important}}</style></noscript></head><body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header docs-header"><a class="brand" href="{logo_href}"{logo_current_attr}><span class="brand-mark" aria-hidden="true">OCF</span><span class="brand-name">Open Consciousness Functions<small>Audio and Guides</small></span></a>
<nav class="desktop-nav" aria-label="Main navigation">{primary_links}{more_menu}</nav><details class="mobile-nav"><summary>Menu</summary><nav aria-label="Main navigation">{primary_links}{more_menu}</nav></details>
<button class="theme-toggle" type="button" data-theme-toggle aria-label="Color theme: System">Theme: System</button></header>
<main id="main" class="docs-main">{toc_mobile}<div class="docs-layout{" with-toc" if toc_nav else ""}">{toc_desktop}<article class="{content_class}">{body}</article></div></main>
<footer class="site-footer"><a class="footer-brand" href="{logo_href}">OCF<span> / AUDIO &amp; GUIDES</span></a><div class="footer-links"><a href="{SITE_REPOSITORY}">Audio site source</a><a href="{SOURCE_REPOSITORY}/tree/{source_commit}">Canonical OCF source at {source_commit[:12]}</a><a href="https://github.com/ocfproject-org/open-consciousness-functions-audio/releases">Published releases</a></div><p>Independent documentation and listening library. Audio files remain with their verified published releases.</p></footer>
</body></html>'''


def _function_toc_items():
    return [
        (2, identity, label)
        for identity, label in (
            ("overview", "Purpose"),
            ("cues", "Cues and documented instructions"),
            ("behavior", "Lifecycle and behavior"),
            ("safety", "Precautions"),
            ("listening", "Listen and download"),
            ("related", "Explore related practices"),
        )
    ]


def _markdown_toc(markdown):
    items = []
    for line in markdown.splitlines():
        match = re.fullmatch(r"(#{2,3})\s+(.+)", line.strip())
        if match:
            title = match.group(2)
            items.append((len(match.group(1)), _slug(title), _inline(title)))
    return items


def _render_toc(items):
    if not items:
        return ""
    rows = "".join(
        f'<li class="toc-level-{level}"><a href="#{_html(identity)}">{label}</a></li>'
        for level, identity, label in items
    )
    return (
        '<nav aria-label="On this page"><p class="eyebrow">On this page</p><ul>'
        + rows
        + "</ul></nav>"
    )


def _home_page(functions, catalog, source_commit):
    categories = _unique_categories(functions)
    category_links = "".join(
        f'<a class="category-link" href="functions/?category={_html(item["id"])}">{_html(item["label"].title())}</a>'
        for item in categories
    )
    starting = {row["function_id"]: row for row in functions}
    starting_links = "".join(
        f'<li><a href="functions/{fid}/">{_html(starting[fid]["title"]["text"])}</a></li>'
        for fid in ("OCF-FND-004", "OCF-FND-002", "OCF-COG-007")
        if fid in starting
    )
    session_count = sum(
        len(group["sessions"])
        for release in catalog["releases"]
        for group in release["functions"] + release.get("preparations", [])
    )
    return f'''<section class="hero docs-hero"><div class="hero-copy"><p class="eyebrow">Guided practices and function guides</p><h1 id="home-title">Read the guide.<br><em>Choose how to listen.</em></h1><p class="hero-lede">Read a function’s instructions, browse current spoken cues, or listen to and download an available recording.</p><div class="hero-actions"><a class="button button-light" href="start/">Start Here <span aria-hidden="true">→</span></a><a class="button button-outline-light" href="functions/">Browse &amp; Listen</a></div></div><div class="hero-index" aria-hidden="true">{len(functions)} FUNCTION GUIDES · {session_count} PUBLISHED SESSIONS</div></section>
<section class="home-paths" aria-labelledby="paths-title"><p class="eyebrow">First steps</p><h2 id="paths-title">Preparation first; then explore by choice.</h2><p class="preparation-note">{_html(PREPARATION_FIRST_GUIDANCE)}</p><p>After Preparation Learning, these practices are optional starting choices—not additional prerequisites:</p><ul class="starting-practices">{starting_links}</ul><div class="path-grid"><a class="path-card" href="start/"><h3>Start Here</h3><p>Preparation instructions, the exception, and choosing a first practice.</p></a><a class="path-card" href="functions/"><h3>Browse &amp; Listen</h3><p>Search practices, compare categories, and open available recordings.</p></a></div><p class="home-utilities">Also available: <a href="quick-reference/">Quick Reference for current spoken cues</a> · <a href="listening/">Detailed Listening Guide</a></p></section>
<section class="home-library-preview" id="library" aria-labelledby="home-library-title"><span id="releases"></span><p class="eyebrow">Explore all {len(functions)} guides</p><h2 id="home-library-title">Browse by category</h2><nav class="category-links" aria-label="Browse categories">{category_links}</nav><p><a class="text-link" href="functions/">Open Browse &amp; Listen</a> · <a href="quick-reference/">Quick Reference</a> · <a href="downloads/">Individual downloads</a></p></section>
<section class="home-about"><p class="eyebrow">Open-source and independent</p><p>OCF offers written function guides and a library of individually downloadable recordings. Audio availability is release-specific; the guide remains available independently.</p><a class="text-link" href="about/">About OCF</a></section>'''


def _functions_index(functions, sessions_by_function, preparation_sessions):
    category_options = _unique_categories(functions)
    options = "".join(
        f'<option value="{_html(category["id"])}">{_html(category["label"].title())}</option>'
        for category in category_options
    ) + '<option value="preparation-learning">Preparation Learning</option>'
    languages = sorted(
        {
            session["session"].get("locale", "")
            for sessions in sessions_by_function.values()
            for session in sessions
            if session["session"].get("locale")
        }
    )
    voices = sorted(
        {
            session["session"].get("voice_name", "")
            for sessions in sessions_by_function.values()
            for session in sessions
            if session["session"].get("voice_name")
        }
    )
    language_options = "".join(
        f'<option value="{_html(value)}">{_html(value)}</option>' for value in languages
    )
    voice_options = "".join(
        f'<option value="{_html(value)}">{_html(value)}</option>' for value in voices
    )
    session_count = sum(len(rows) for rows in sessions_by_function.values()) + len(preparation_sessions)
    availability = {bool(sessions_by_function.get(function["function_id"])) for function in functions}
    audio_filter = (
        '<label for="audio-filter">Audio availability</label><select id="audio-filter"><option value="">All documentation</option><option value="yes">Published audio available</option><option value="no">Documentation only</option></select>'
        if len(availability) > 1
        else ""
    )
    language_filter = (
        f'<label for="language-filter">Language</label><select id="language-filter"><option value="">All languages</option>{language_options}</select>'
        if len(languages) > 1
        else ""
    )
    voice_filter = (
        f'<label for="voice-filter">Voice</label><select id="voice-filter"><option value="">All voices</option>{voice_options}</select>'
        if len(voices) > 1
        else ""
    )
    cards_by_domain = {}
    for function in functions:
        categories = {item["id"] for item in function["categories"]}
        search = [
            function["function_id"],
            function["slug"],
            function["title"]["text"],
            _public_description(function),
        ]
        search.extend(
            command["spoken_cue"]
            for command in function["commands"]
            if command.get("spoken_cue")
        )
        search.extend(
            item["text"]
            for item in function["tags"] + function["common_uses"]
            if item.get("status") in PUBLIC_DISCOVERY_STATUSES
        )
        sessions = sessions_by_function.get(function["function_id"], [])
        function_languages = sorted(
            {row["session"].get("locale", "") for row in sessions}
        )
        function_voices = sorted(
            {row["session"].get("voice_name", "") for row in sessions}
        )
        editions = []
        for row in sessions:
            session = row["session"]
            actions = [
                f'<a class="browse-action" href="{_html(function["function_id"])}/#{_session_anchor(row)}" aria-label="Listen to {_html(session.get("title") or function["title"]["text"])}, edition {_html(session["edition"])}">Listen</a>'
            ]
            actions.extend(
                f'<a class="browse-action" href="{_html(asset["download_url"])}" aria-label="Download {str(asset["format"]).upper()} for {_html(session.get("title") or function["title"]["text"])}, edition {_html(session["edition"])}">{str(asset["format"]).upper()}</a>'
                for asset in row["audio_assets"]
            )
            editions.append(
                f'<div class="browse-edition" role="group" aria-label="Edition {_html(session["edition"])}"><span>Edition {_html(session["edition"])}</span>{"".join(actions)}</div>'
            )
        sessions_text = " ".join(
            f'{row["session"].get("locale", "")} {row["session"].get("voice_name", "")}'
            for row in sessions
        )
        cards_by_domain.setdefault(function["primary_category"], []).append(
            f'''<article class="function-card" data-function-card data-category="{_html(" ".join(sorted(categories)))}" data-audio="{"yes" if sessions else "no"}" data-language="{_html("|".join(function_languages))}" data-voice="{_html("|".join(function_voices))}" data-search="{_html(" ".join(search + [sessions_text]).casefold())}"><p class="eyebrow">{_html(function["primary_category"].title())} · {function["function_id"]}</p><h2><a href="{_html(function["function_id"])}/">{_html(function["title"]["text"])}</a></h2><p>{_html(_public_description(function))}</p><p class="function-status">{"Published recording available" if sessions else "Function guide · no recording in the current release"}</p><div class="browse-editions">{"".join(editions) if editions else ""}</div><a class="text-link" href="{_html(function["function_id"])}/">Read instructions <span aria-hidden="true">→</span></a></article>'''
        )
    groups = "".join(
        f'<section class="domain-group" data-domain-group="{_html(category["id"])}"><h2>{_html(category["label"].title())}</h2><div class="function-grid" data-function-grid>{"".join(cards_by_domain.get(category["id"], []))}</div></section>'
        for category in category_options
        if cards_by_domain.get(category["id"])
    )
    return f'''<header class="page-intro"><p class="eyebrow">Find a guide, then choose how to listen</p><h1>Browse &amp; Listen</h1><p>Search all {len(functions)} function guides by title, current spoken cue, category, or purpose. Each recording retains its original release files.</p><p class="preparation-note">{_html(PREPARATION_FIRST_GUIDANCE)} <a href="../preparation-learning/">Open Preparation Learning</a></p></header><section class="library-section browse-library" id="library" aria-labelledby="library-title"><div class="section-heading"><div><p class="eyebrow">Published editions and all function guides</p><h2 id="library-title">Find a practice</h2></div><span class="count" id="release-count">{session_count} recordings</span></div><p>Function guides remain available independently of audio.</p><div class="library-tools"><label class="sr-only" for="search">Search title, ID, description, current spoken cue, category, or use</label><input id="search" type="search" placeholder="Search functions, cues, categories, or uses" aria-describedby="results-count"><label for="category-filter">Category <select id="category-filter"><option value="">All categories</option>{options}</select></label>{audio_filter}{language_filter}{voice_filter}<button id="clear-library-filters" type="button" hidden>Clear filters</button></div><section class="release-banner browse-banner" aria-labelledby="release-title"><div class="release-symbol" aria-hidden="true">↗</div><div><p class="eyebrow">Published audio</p><h2 id="release-title">{session_count} session editions are listed</h2><p id="release-description">Search by practice and category. Open a function guide to read, listen, or download its original edition.</p></div><a class="text-link" href="https://github.com/ocfproject-org/open-consciousness-functions-audio/releases">All releases <span aria-hidden="true">↗</span></a></section><p id="empty-state" class="empty-state" role="status" hidden>No published recordings are listed in the verified catalog; function guides remain available.</p><p id="results-count" role="status" aria-live="polite">Published editions and direct download links are listed below.</p><p id="catalog-no-results" class="filter-empty" hidden>No functions match these filters.</p><div class="selection-tools"><span id="selection-count" role="status" aria-live="polite" tabindex="-1">0 files selected</span><button id="download-selection" disabled>Save download list</button><button id="playlist-selection" disabled>Save MP3 playlist</button><details id="selected-files-review" hidden><summary id="selected-files-summary">Review selected files (0)</summary><ul id="selected-files-list"></ul><button id="clear-selection" type="button">Clear selected files</button></details><p>Downloads open the original release assets. Detailed filenames, versions, and checksums are on each function guide.</p></div><div id="catalog-results">{groups}</div><div id="release-extras"></div></section><noscript><p>Search and player controls need JavaScript. Function guides and individual download links remain available above.</p></noscript>'''


def _unique_categories(functions):
    values = {}
    for function in functions:
        for category in function["categories"]:
            values[category["id"]] = category["label"]
    return [{"id": key, "label": values[key]} for key in sorted(values)]


def _public_description(function):
    text = function["description"]["text"]
    display_cues = [
        re.escape(command["display_cue"]["text"])
        for command in function["commands"]
        if command.get("display_cue", {}).get("text")
    ]
    if display_cues:
        text = re.sub(
            rf";\s*activation cue\s+(?:{'|'.join(display_cues)})[.!?]?\s*$",
            "",
            text,
            flags=re.IGNORECASE,
        )
    return text


def _historical_lookup_rows(markdown, functions, source_root):
    import yaml

    lines = markdown.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if line.strip() == "## Migrated vocabulary"
    ]
    _require(len(starts) == 1, "historical lookup reference needs one Migrated vocabulary section")
    start = starts[0] + 1
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    functions_by_id = {function["function_id"]: function for function in functions}
    rows = []
    seen = set()
    pattern = re.compile(
        r"- (OCF-[A-Z]{3}-[0-9]{3}) → (.+?) / `([^`]+)`; historical matches: (.+)\."
    )
    for line_number, line in enumerate(lines[start:end], start=start + 1):
        if not line.strip():
            continue
        match = pattern.fullmatch(line)
        _require(
            match is not None,
            f"historical lookup row {line_number} does not match the pinned reference format",
        )
        function_id, source_title, current_display_cue, raw_names = match.groups()
        _require(function_id not in seen, f"duplicate historical lookup function: {function_id}")
        function = functions_by_id.get(function_id)
        _require(function is not None, f"historical lookup references unknown function: {function_id}")
        _require(
            source_title == function["title"]["text"],
            f"historical lookup title does not match pinned function title: {function_id}",
        )
        _require(
            current_display_cue
            in {command["display_cue"]["text"] for command in function["commands"]},
            f"historical lookup current cue does not match pinned function commands: {function_id}",
        )
        locale_path = source_root / function["canonical_resource"]
        locale_resource = locale_path.resolve()
        _require(
            locale_resource.is_relative_to(source_root.resolve())
            and locale_path.is_file()
            and not locale_path.is_symlink(),
            f"historical lookup locale resource is unavailable: {function_id}",
        )
        locale_bytes = locale_resource.read_bytes()
        _require(
            hashlib.sha256(locale_bytes).hexdigest()
            == function["canonical_resource_sha256"],
            f"historical lookup locale resource hash mismatch: {function_id}",
        )
        record = yaml.safe_load(locale_bytes)
        _require(
            record.get("function_id") == function_id,
            f"historical lookup locale identity mismatch: {function_id}",
        )
        typed_names = record.get("record_metadata", {}).get("historical_lookup", [])
        source_names = [name.strip() for name in raw_names.split("; ")]
        _require(
            [name.get("text") for name in typed_names] == source_names,
            f"historical lookup names differ from pinned canonical records: {function_id}",
        )
        current_terms = {_historical_lookup_form(function["title"]["text"])}
        for command in function["commands"]:
            for cue in (
                command.get("display_cue", {}).get("text"),
                command.get("spoken_cue"),
            ):
                if isinstance(cue, str) and cue.strip():
                    current_terms.add(_historical_lookup_form(cue))
        names = []
        for name in typed_names:
            kind = name.get("kind")
            _require(
                kind in HISTORICAL_LOOKUP_KIND_LABELS,
                f"historical lookup classification is unknown: {function_id} / {kind}",
            )
            if not _public_historical_name(function_id, name):
                continue
            also_current = _historical_lookup_form(name["text"]) in current_terms
            label = HISTORICAL_LOOKUP_KIND_LABELS[kind]
            if also_current:
                label += " · Also current"
            names.append(
                {
                    "text": name["text"],
                    "kind": kind,
                    "label": label,
                    "also_current": also_current,
                }
            )
        seen.add(function_id)
        rows.append({"function_id": function_id, "title": source_title, "names": names})
    _require(rows, "historical lookup reference contains no mapped names")
    return rows


def _spoken_cue_references(text, commands):
    mappings = sorted(
        (
            (command["display_cue"]["text"], command["spoken_cue"])
            for command in commands
            if command.get("display_cue", {}).get("text")
            and command.get("spoken_cue")
        ),
        key=lambda mapping: len(mapping[0]),
        reverse=True,
    )
    for display, spoken in mappings:
        text = re.sub(
            rf"(?<![\w]){re.escape(display)}(?![\w])",
            lambda _: spoken,
            text,
            flags=re.IGNORECASE,
        )
    return text


def _function_page(function, sessions, transcript_paths, source_commit):
    categories = " · ".join(
        _html(category["label"]) for category in function["categories"]
    )
    terms = _discovery_section(
        "Tags and discovery terms", function["tags"]
    ) + _discovery_section("Common-use examples", function["common_uses"])
    command_sections = []
    for command in function["commands"]:
        spoken_cue = command.get("spoken_cue", "").strip()
        if not spoken_cue:
            raise ValueError(
                f"{function['function_id']}/{command['command_id']} has no spoken cue"
            )
        spoken = _html(spoken_cue)
        spoken_html = f'<p class="spoken-cue"><strong>{spoken}</strong></p>'
        visible_steps = []
        for step in command["procedure_steps"]:
            current = (step["operation"], step["instruction"])
            if not visible_steps or visible_steps[-1] != current:
                visible_steps.append(current)
        steps = "".join(
            f"<li>{_html(instruction)}</li>" for _, instruction in visible_steps
        )
        if command["procedure_status"] == "documented":
            procedure_html = f"<ol>{steps}</ol>"
        elif command["procedure_status"] == "review-pending":
            procedure_html = '<p class="not-specified">No activation steps are published for this command.</p>'
        else:
            procedure_html = '<p class="not-specified">No activation steps are specified. Do not infer a procedure from the cue name.</p>'
        usage_html = (
            "<p>"
            + _html(
                _spoken_cue_references(
                    command["usage"]["text"], function["commands"]
                )
            )
            + "</p>"
            if command.get("usage")
            and command["usage"]["text"]
            != "Use only when you choose to activate the documented function."
            else ""
        )
        explanation_html = (
            "<p>" + _html(command["explanation"]["text"]) + "</p>"
            if command.get("explanation")
            and command["explanation"]["text"]
            != "This is the primary command for the function."
            else ""
        )
        scope_html = (
            '<p class="scope-note">Effect scope: '
            + _html(command["effect_scope"])
            + "</p>"
            if command.get("effect_scope")
            else ""
        )
        command_sections.append(
            f'''<section class="command-block"><h3>{"Primary activation" if command["designation"] == "primary" else "Secondary command"}</h3>{spoken_html}{usage_html}{explanation_html}<h4>Documented activation steps</h4>{procedure_html}{scope_html}</section>'''
        )
    scope_rows = []
    for scope in function["lifecycle"]["scopes"]:
        description = (
            ": " + _html(scope["description"]) if scope.get("description") else ""
        )
        scope_rows.append(
            f"<li><strong>{_html(scope['label'])}</strong> — "
            f"{_html(scope['persistence'])}{description}</li>"
        )
    scopes_html = (
        "<ul>" + "".join(scope_rows) + "</ul>"
        if scope_rows
        else ""
    )
    lifecycle = function["lifecycle"]
    trigger_text = "; ".join(lifecycle["trigger_conditions"])
    trigger_html = (
        "<p>Declared trigger conditions: " + _html(trigger_text) + "</p>"
        if trigger_text
        else ""
    )
    release_command = lifecycle["release_command"]
    release_html = (
        "<p>Declared release command: <strong>"
        + _html(release_command)
        + "</strong></p>"
        if release_command
        else ""
    )
    lifecycle_html = f"""<section class="guide-section"><h2 id="behavior">Lifecycle and behavior</h2><p>Activation: {_html(lifecycle["activation"] or "not specified")}. Intended persistence: {_html(lifecycle["persistence"] or "not specified")}.</p>{scopes_html}{trigger_html}{release_html}</section>"""
    safety_html = "".join(
        f"<li>{_html(note)}</li>" for note in function["safety_notes"]
    )
    general_safety = (
        "<p>For general comfort and safety guidance, see the "
        '<a href="../../listening/">Listening Guide</a>.</p>'
    )
    specific_safety = (
        "<p>Function-specific notes:</p><ul>" + safety_html + "</ul>"
        if safety_html
        else "<p>No additional function-specific precautions are recorded.</p>"
    )
    safety = (
        '<section class="guide-section"><h2 id="safety">Precautions</h2>'
        + specific_safety
        + general_safety
        + "</section>"
    )
    session_html = "".join(
        _session_card(row, transcript_paths, site_root_prefix="../../")
        for row in sessions
    )
    audio_actions = _function_audio_actions(sessions)
    if not session_html:
        session_html = '<p class="no-audio">Documentation is available; this function has no audio edition in the verified published catalog.</p>'
    related = []
    for relation in function["related_functions"]:
        related.append(
            f'<li><a href="../{_html(relation["function_id"])}/">{_html(relation["title"])}</a> <span class="stable-id">{_html(relation["function_id"])}</span><p>{_html(relation["description"])}</p></li>'
        )
    related_html = (
        "".join(related)
        or "<li>No related practice is listed for this function. You can still choose it independently.</li>"
    )
    breadcrumb = f'<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="../../">Home</a> / <a href="../">Browse &amp; Listen</a> / <span aria-current="page">{_html(function["title"]["text"])}</span></nav>'
    source_details = (
        f'<details class="source-details"><summary>Sources and versions</summary><p>Canonical function source: <a href="{SOURCE_REPOSITORY}/tree/{source_commit}/{_html(function["canonical_resource"])}">locale resource at pinned commit {_html(source_commit[:12])}</a>.</p></details>'
    )
    return (
        breadcrumb
        + f'''<header class="page-intro function-intro" data-function-id="{_html(function["function_id"])}"><p class="eyebrow">{_html(function["function_id"])} · {_html(categories)}</p><h1>{_html(function["title"]["text"])}</h1><p id="overview" class="lead">{_html(_public_description(function))}</p>{audio_actions}</header>{terms}<section class="guide-section"><h2 id="cues">Cues and documented instructions</h2>{"".join(command_sections)}</section>{lifecycle_html}{safety}<section class="guide-section"><h2 id="listening">Listen and download</h2><p>Choose an edition. The written instructions are available whether or not you use audio. Release downloads open the original files; some browsers may use the server filename, so rename it locally if needed. This page does not buffer audio.</p>{session_html}</section><section class="guide-section"><h2 id="related">Explore related practices</h2><p>These source-approved links are optional, one-way relationships. They are not prerequisites or claims about combining practices.</p><ul class="relationship-list">{related_html}</ul></section>{source_details}'''
    )


def _session_anchor(row):
    session = row["session"]
    asset_id = session.get("asset_id") or row["audio_assets"][0]["asset_id"]
    return f"session-{_html(asset_id)}"


def _function_audio_actions(sessions):
    groups = []
    for row in sessions:
        session = row["session"]
        title = session.get("title") or row["group"].get("title") or "Session"
        locale = session.get("locale") or "locale not specified"
        edition = session.get("edition") or row["release"].get("version") or "edition not specified"
        label = _html(f"{title}, {locale}, edition {edition}")
        actions = [
            f'<a class="function-audio-action" href="#{_session_anchor(row)}" aria-label="Listen to {label}">Listen</a>'
        ]
        for asset in row["audio_assets"]:
            fmt = str(asset["format"]).upper()
            actions.append(
                f'<a class="function-audio-action" href="{_html(asset["download_url"])}" aria-label="Download {fmt} for {label}">Download {fmt}</a>'
            )
        groups.append(
            f'<div class="function-audio-action-group" role="group" aria-label="{label}">'
            f'<span>Edition {_html(edition)}</span>{"".join(actions)}</div>'
        )
    if not groups:
        return ""
    return f'<nav class="function-audio-actions" aria-label="Listen and download">{"".join(groups)}</nav>'


def _discovery_section(title, values):
    values = [
        value
        for value in values
        if value.get("status") in PUBLIC_DISCOVERY_STATUSES
    ]
    if not values:
        return ""
    rows = "".join(f"<li>{_html(value['text'])}</li>" for value in values)
    return f'<details class="discovery-details"><summary>{_html(title)}</summary><ul>{rows}</ul></details>'


def _session_card(row, transcript_paths, *, site_root_prefix="../../"):
    release, session, companions = row["release"], row["session"], row["companions"]
    title = session.get("title") or row["group"].get("title")
    images = companions.get("png")
    artwork = (
        f'<img class="session-art" src="{_html(images["download_url"])}" alt="Artwork for {_html(title)}" loading="lazy">'
        if images
        else ""
    )
    audio = []
    playable = next(
        (asset for asset in row["audio_assets"] if asset["format"] == "mp3"), None
    )
    playable = playable or next(
        (asset for asset in row["audio_assets"] if asset["format"] == "flac"), None
    )
    if playable:
        media_type = "audio/mpeg" if playable["format"] == "mp3" else "audio/flac"
        vtt = companions.get("vtt")
        local_vtt = transcript_paths.get(vtt["asset_id"]) if vtt else None
        track = (
            f'<track kind="subtitles" srclang="{_html(session["locale"])}" label="Timed transcript" src="{_html(site_root_prefix + local_vtt["path"])}">'
            if local_vtt
            else ""
        )
        audio.append(
            f'<audio controls preload="none" aria-label="Listen to {_html(title)}, {_html(session["locale"])}, edition {_html(session["edition"])}" data-session-title="{_html(title)}" data-session-edition="{_html(session["edition"])}" data-session-locale="{_html(session["locale"])}"><source src="{_html(playable["download_url"])}" type="{media_type}">{track}Your browser may not support this audio format. Use an individual download link.</audio><p class="playback-status" data-playback-status role="status" aria-live="polite" hidden></p>'
        )
    for asset in row["audio_assets"]:
        fmt = asset["format"].upper()
        suggested_filename = _suggested_download_filename(
            row["group"], session, release, asset
        )
        size = (
            f"{asset.get('size_bytes', 0) / 1048576:.1f} MiB"
            if asset.get("size_bytes")
            else "size not reported"
        )
        duration = (
            f"{int(asset['duration_seconds'] // 60)}m {int(asset['duration_seconds'] % 60)}s"
            if asset.get("duration_seconds")
            else "duration not reported"
        )
        specification_text = _asset_specification(asset, size=size, duration=duration)
        audio.append(
            f'''<div class="asset-download" data-download-format="{_html(asset["format"])}"><div class="download-actions"><a class="download-link" href="{_html(asset["download_url"])}" download="{_html(suggested_filename)}">Download {fmt}</a></div><p class="download-specification">{_html(specification_text)}</p><details class="file-details"><summary>File details</summary><p>Release filename: <code>{_html(asset["filename"])}</code></p><p>Suggested local filename: <code>{_html(suggested_filename)}</code></p><button type="button" class="copy-filename" data-copy="{_html(suggested_filename)}" aria-label="Copy suggested filename for {fmt}">Copy suggested filename</button><p>SHA-256: <code>{_html(asset["sha256"])}</code></p></details></div>'''
        )
    transcript_controls = []
    for fmt, label in (("txt", "Read transcript"), ("vtt", "Download timed subtitles")):
        asset = companions.get(fmt)
        if not asset:
            continue
        local = transcript_paths.get(asset["asset_id"])
        if fmt == "txt" and local:
            transcript_controls.append(
                f'<details class="transcript" data-transcript><summary>{label} — edition {_html(session["edition"])} ({_html(session["locale"])})</summary><p class="transcript-status" data-transcript-status role="status" aria-live="polite" hidden></p><label class="transcript-search"><span>Search this transcript</span><input type="search" data-transcript-search disabled></label><pre class="transcript-body" data-transcript-src="{_html(site_root_prefix + local["path"])}" aria-live="off">Open the download link below to read this edition-matched transcript. With JavaScript enabled, it also loads here when expanded.</pre><button type="button" data-transcript-retry hidden>Retry loading transcript</button><p><a href="{_html(site_root_prefix + local["path"])}" download aria-label="Download transcript text for {_html(title)}, edition {_html(session["edition"])}, {_html(session["locale"])}">Download transcript text</a> · <a href="{_html(asset["download_url"])}" aria-label="Original release asset, TXT for {_html(title)}, edition {_html(session["edition"])}, {_html(session["locale"])}">Original release asset</a></p><details class="file-details"><summary>Transcript file details</summary><p>SHA-256: <code>{_html(asset["sha256"])}</code></p></details></details>'
            )
        elif local:
            transcript_controls.append(
                f'<p><a href="{_html(site_root_prefix + local["path"])}" download aria-label="Download timed subtitles for {_html(title)}, edition {_html(session["edition"])}, {_html(session["locale"])}">{label}</a> · <a href="{_html(asset["download_url"])}" aria-label="Original release asset, VTT for {_html(title)}, edition {_html(session["edition"])}, {_html(session["locale"])}">Original release asset</a></p>'
            )
    companion_links = []
    for fmt, asset in sorted(companions.items()):
        if fmt in {"txt", "vtt"}:
            continue
        companion_links.append(
            f'<li><a href="{_html(asset["download_url"])}">{_html("Artwork" if fmt == "png" else fmt.upper() + " companion")}</a> <span>SHA-256 {_html(asset["sha256"])}</span></li>'
        )
    companion_html = (
        "<details><summary>Other companion files</summary><ul>"
        + "".join(companion_links)
        + "</ul></details>"
        if companion_links
        else ""
    )
    audio_html = "".join(audio)
    transcript_html = "".join(transcript_controls)
    source_info = f'<details class="recording-details"><summary>Recording source and version</summary><p>Published release <a href="{_html(release["release_url"])}">{_html(release["tag"])}</a></p><p>Source OCF commit: <code>{_html(release["source_ocf_commit"])}</code></p></details>'
    return f'''<article class="edition-card" id="{_session_anchor(row)}"><div class="edition-heading">{artwork}<div><h3>{_html(title)}</h3><p>{_html(session["locale"])} · {_html(session["voice_name"])} · edition {_html(session["edition"])}</p>{source_info}</div></div>{audio_html}{transcript_html}{companion_html}</article>'''


def _asset_specification(asset, *, size=None, duration=None):
    fmt = str(asset.get("format", "")).upper()
    specifications = [fmt, asset.get("encoding")]
    if asset.get("sample_rate_hz"):
        specifications.append(f"{asset['sample_rate_hz']:,} Hz")
    if asset.get("channels"):
        specifications.append(
            f"{asset['channels']} channel{'s' if asset['channels'] != 1 else ''}"
        )
    if size is None:
        size = (
            f"{asset['size_bytes'] / 1048576:.1f} MiB"
            if asset.get("size_bytes")
            else None
        )
    if duration is None:
        duration = (
            f"{int(asset['duration_seconds'] // 60)}m {int(asset['duration_seconds'] % 60)}s"
            if asset.get("duration_seconds")
            else None
        )
    specifications.extend((size, duration))
    return " · ".join(value for value in specifications if value)


def _suggested_download_filename(group, session, release, asset):
    extension = str(asset.get("format", "")).casefold()
    if not re.fullmatch(r"[a-z0-9]{1,8}", extension):
        raise ValueError(f"unsupported suggested-download extension: {extension!r}")
    identity = group.get("function_id") or "Preparation"
    values = (
        identity,
        session.get("title") or group.get("title") or "Session",
        session["locale"],
        session["voice_name"],
        f"v{session['edition']}",
        release["tag"],
    )
    parts = [
        re.sub(r"\s+", " ", re.sub(r'[\x00-\x1f<>:"/\\|?*]+', "-", str(value)))
        .strip(" .-")
        for value in values
    ]
    return " - ".join(part for part in parts if part) + f".{extension}"


def _validate_suggested_download_filenames(session_rows):
    seen = {}
    for row in session_rows:
        for asset in row["audio_assets"]:
            filename = _suggested_download_filename(
                row["group"], row["session"], row["release"], asset
            )
            key = filename.casefold()
            if key in seen:
                previous = seen[key]
                raise ValueError(
                    "published audio assets share a suggested local filename: "
                    f"{previous['function_id']} and {row['group'].get('function_id', 'preparation')} / {filename}"
                )
            seen[key] = {"function_id": row["group"].get("function_id", "preparation")}


def _quick_reference(functions, sessions_by_function):
    rows = []
    for function in functions:
        cue_rows = []
        searchable = [
            function["function_id"],
            function["title"]["text"],
            _public_description(function),
        ]
        searchable.extend(
            term["text"]
            for term in function["tags"] + function["common_uses"]
            if term.get("status") in PUBLIC_DISCOVERY_STATUSES
        )
        for command in function["commands"]:
            spoken = command.get("spoken_cue")
            if not spoken:
                raise ValueError(
                    f"{function['function_id']}/{command['command_id']} has no spoken cue"
                )
            searchable.append(spoken)
            cue_rows.append(
                f'<li><span class="cue-role">{_html("Primary" if command["designation"] == "primary" else "Secondary")}</span> <strong>{_html(spoken)}</strong></li>'
            )
        category = function["primary_category"]
        rows.append(
            f'<tr role="row" data-reference-row data-search="{_html(" ".join(searchable).casefold())}" data-category="{_html(" ".join(category["id"] for category in function["categories"]))}"><th role="rowheader" scope="row"><a href="../functions/{_html(function["function_id"])}/">{_html(function["title"]["text"])}</a><span class="stable-id">{_html(function["function_id"])}</span><span class="category-chip">{_html(category.title())}</span></th><td role="cell" data-label="Current spoken cues"><ul>{"".join(cue_rows)}</ul></td><td role="cell" data-label="Description">{_html(_public_description(function))}</td><td role="cell" data-label="Published audio availability">{"Published audio available" if sessions_by_function.get(function["function_id"]) else "Audio unavailable"}</td></tr>'
        )
    options = "".join(
        f'<option value="{_html(item["id"])}">{_html(item["label"].title())}</option>'
        for item in _unique_categories(functions)
    )
    return f"""<header class="page-intro"><p class="eyebrow">Approved spoken cues</p><h1>Quick Reference</h1><p>Find a spoken cue; use the function's documented steps rather than inferring a procedure from its name.</p></header><div class="reference-tools"><label for="reference-search">Search title, ID, spoken cue or description</label><input id="reference-search" type="search" data-reference-search><label for="reference-category">Category</label><select id="reference-category" data-reference-category><option value="">All categories</option>{options}</select><output data-reference-count aria-live="polite">58 functions</output><button type="button" data-reference-clear hidden>Clear filters</button><p class="filter-empty" data-reference-no-results role="status" hidden>No functions match these filters.</p></div><div class="table-scroll"><table role="table" class="reference-table quick-reference-table" aria-label="Current cues, function descriptions, and audio availability"><thead role="rowgroup"><tr role="row"><th role="columnheader" scope="col">Function</th><th role="columnheader" scope="col">Current spoken cues</th><th role="columnheader" scope="col">Description</th><th role="columnheader" scope="col">Audio availability</th></tr></thead><tbody role="rowgroup">{"".join(rows)}</tbody></table></div>"""


def _historical_names_page(
    rows, functions, source_commit, *, historical_reference_sha256
):
    entries = "".join(
        f'''<article class="historical-name-entry" data-historical-name-entry data-function-id="{_html(row["function_id"])}"><h2><a href="../functions/{_html(row["function_id"])}/">{_html(row["title"])}</a> <span class="stable-id">{_html(row["function_id"])}</span></h2><ul>{"".join(f'<li data-historical-kind="{_html(name["kind"])}" data-also-current="{str(name["also_current"]).lower()}"><span class="historical-name-kind">{_html(name["label"])}</span> <span class="historical-name-text">{_html(name["text"])}</span></li>' for name in row["names"])}</ul></article>'''
        for row in rows
    )
    source_url = (
        f"{SOURCE_REPOSITORY}/blob/{source_commit}/"
        "docs/releases/OCF_HISTORICAL_LOOKUP_CURRENT.md"
    )
    mapped_ids = {row["function_id"] for row in rows}
    unmapped = [
        function
        for function in functions
        if function["function_id"] not in mapped_ids
    ]
    unmapped_items = "".join(
        f'<li><a href="../functions/{_html(function["function_id"])}/">{_html(function["title"]["text"])}</a> <span class="stable-id">{_html(function["function_id"])}</span></li>'
        for function in unmapped
    )
    return (
        '<header class="page-intro"><p class="eyebrow">Historical lookup only</p>'
        '<h1>Historical names</h1><p>These are only the historical matches listed in '
        'the pinned OCF reference. Each type label comes from the canonical '
        'historical_lookup.kind field; types are not inferred from the spelling. '
        '“Also current” marks an exact case/whitespace-normalized match to this '
        'same function’s current title, active display cue, or active spoken cue; '
        'the source historical classification remains unchanged. '
        'They are for lookup; a match never selects an activation target. Use the '
        'current function guide for current instructions.</p>'
        f'<p>The pinned reference contains mappings for {len(rows)} functions and '
        f'{sum(len(row["names"]) for row in rows)} historical strings. It has no '
        f'mapping for these {len(unmapped)} functions:</p><ul>{unmapped_items}</ul>'
        '<p>Absence from this reference does not establish that no historical '
        'counterpart exists.</p>'
        f'<p class="source-link">Source: <a href="{_html(source_url)}">OCF historical lookup at pinned commit {source_commit[:12]}</a> · SHA-256 <code>{historical_reference_sha256}</code></p></header>'
        f'<div class="historical-name-grid">{entries}</div>'
    )


def _relationships_page(functions):
    links_by_category = {}
    for function in functions:
        for relation in function["related_functions"]:
            links_by_category.setdefault(function["primary_category"], []).append(
                f'<article class="relationship-card"><p class="eyebrow">From {_html(function["function_id"])}</p><h3><a href="../functions/{_html(function["function_id"])}/">{_html(function["title"]["text"])}</a> <span aria-hidden="true">→</span> <a href="../functions/{_html(relation["function_id"])}/">{_html(relation["title"])}</a></h3><p>{_html(relation["description"])}</p></article>'
            )
    groups = "".join(
        f'<section class="relationship-group"><h2>{_html(category.title())}</h2><div class="relationship-grid">{"".join(cards)}</div></section>'
        for category, cards in links_by_category.items()
    )
    relation_count = sum(len(cards) for cards in links_by_category.values())
    return f'<header class="page-intro"><p class="eyebrow">Source-approved relationships</p><h1>Explore related practices</h1><p>These {relation_count} links are optional and one-way. They are not prerequisites, sequences, or claims of combined effects.</p></header>{groups}'


def _downloads_page(catalog, preparation_sessions):
    cards = []
    for release in catalog["releases"]:
        groups = [(False, group) for group in release["functions"]]
        groups += [(True, group) for group in release.get("preparations", [])]
        for is_preparation, group in groups:
            for session in group["sessions"]:
                title = session.get("title") or group.get("title") or "Session"
                function_id = group.get("function_id") or "preparation-learning"
                locale = session.get("locale") or "Language not specified"
                voice = session.get("voice_name") or session.get("voice_id") or "Voice not specified"
                edition = session.get("edition") or release.get("version") or "Edition not specified"
                href = (
                    "../preparation-learning/"
                    if is_preparation
                    else f"../functions/{_html(group['function_id'])}/"
                )
                session_id = session.get("asset_id") or next(
                    (asset.get("asset_id") for asset in session.get("assets", [])),
                    group.get("function_id", "preparation"),
                )
                heading_id = f"download-session-{_html(session_id)}"
                actions = []
                file_details = []
                for asset in session.get("assets", []):
                    fmt = str(asset.get("format", "file")).upper()
                    specification = dict(asset)
                    encoding = str(asset.get("encoding", ""))
                    if encoding.casefold().startswith(fmt.casefold()):
                        encoding = encoding[len(fmt):].lstrip(" :-–—")
                    specification["encoding"] = encoding
                    accessible_name = _html(
                        f"Download {fmt} for {title}, {locale}, {voice}, edition {edition}"
                    )
                    actions.append(
                        f'<div class="download-format"><a class="download-action" href="{_html(asset["download_url"])}" download aria-label="{accessible_name}">Download {_html(fmt)}</a><p class="download-file-specification">{_html(_asset_specification(specification))}</p></div>'
                    )
                    file_details.append(
                        f'<li><strong>{_html(fmt)}</strong> · <code>{_html(asset.get("filename", "Filename not supplied"))}</code><br>SHA-256 <code>{_html(asset.get("sha256", "Not supplied"))}</code></li>'
                    )
                cards.append(
                    f'<article class="download-card" aria-labelledby="{heading_id}" data-download-card data-function-id="{_html(function_id)}" data-edition="{_html(edition)}"><header><h2 id="{heading_id}"><a href="{href}">{_html(title)}</a></h2><dl class="download-session-meta"><div><dt>Language</dt><dd>{_html(locale)}</dd></div><div><dt>Voice</dt><dd>{_html(voice)}</dd></div><div><dt>Edition</dt><dd>{_html(edition)}</dd></div></dl></header><div class="download-card-actions" role="group" aria-label="Individual file downloads for {_html(title)}">{"".join(actions)}</div><details class="download-file-details"><summary>Release and file details</summary><p>Release <a href="{_html(release["release_url"])}">{_html(release.get("tag", "Published release"))}</a></p><ul>{"".join(file_details)}</ul></details></article>'
                )
    return f'<header class="page-intro"><p class="eyebrow">Individual published files</p><h1>Downloads</h1><p>Choose an individual MP3 or FLAC for each session. Links use the verified release catalog URLs; files are not repackaged or transcoded. Release versions and file checksums remain available in each card’s details.</p></header><section class="download-directory" aria-label="Individual session downloads">{"".join(cards)}</section>'


def _preparation_page(rows, transcript_paths):
    sessions = "".join(
        _session_card(row, transcript_paths, site_root_prefix="../") for row in rows
    )
    if not sessions:
        sessions = '<p class="no-audio">Preparation Learning documentation is separate from function guides. No published edition is present in the verified catalog.</p>'
    return f'<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="../">Home</a> / Preparation Learning</nav><header class="page-intro"><p class="eyebrow">Separate introductory session</p><h1>Preparation Learning</h1><p>{_html(PREPARATION_FIRST_GUIDANCE)}</p><p>This published session is separate from the 58 canonical function records. Its transcript, when available, is tied to the exact selected audio edition. Follow only the instructions in that published session.</p></header><section class="guide-section"><h2>Listen to an available edition</h2>{sessions}</section><p><a href="../functions/">Browse the 58 function guides</a></p>'


def _preparation_first_link():
    return '<p class="preparation-first-link"><a href="../preparation-learning/">Open Preparation Learning</a></p>'


def _downloads_from_catalog(catalog):
    return sum(
        len(session["assets"])
        for release in catalog["releases"]
        for group in release["functions"] + release.get("preparations", [])
        for session in group["sessions"]
    )


def _about_page(guide_export, catalog, source_docs_url, transcript_counts):
    releases = []
    for release in catalog["releases"]:
        releases.append(
            f'<li><a href="{_html(release["release_url"])}">{_html(release["tag"])}</a> — edition {_html(release["version"])}; source OCF commit <code>{_html(release["source_ocf_commit"])}</code>.</li>'
        )
    session_count = sum(
        1
        for release in catalog["releases"]
        for group in release["functions"] + release.get("preparations", [])
        for session in group["sessions"]
    )
    return f'''<header class="page-intro"><p class="eyebrow">Independent and open-source</p><h1>About OCF</h1><p>Open Consciousness Functions is an independent, open-source library of function guides and published recordings for self-directed practice.</p><p>Read the guide, explore current cues, and choose whether to listen or download an available edition. The verified catalog currently lists {session_count} session editions, including the separate Preparation Learning session.</p><p>OCF is not affiliated with The Monroe Institute or Hemi-Sync. The material is not healthcare or emergency advice.</p><p><a href="../start/">Start Here</a> · <a href="../functions/">Browse &amp; Listen</a> · <a href="{SITE_REPOSITORY}/issues">Report a website or catalog issue</a></p></header><details class="technical-transparency"><summary>Sources, versions and publishing details</summary><section class="guide-section"><h2>Documentation and audio sources</h2><ul><li>Function titles, instructions, cues, lifecycle and approved relationships come from the canonical OCF en-US locale resources at source commit <code>{_html(guide_export["source_commit"])}</code>.</li><li>The export contains {len(guide_export["functions"])} function records and {guide_export["build_receipt"]["approved_relationship_count"]} approved optional directional relationships; it excludes narration text and source-evidence paths.</li><li>Audio editions, original release URLs and SHA-256 digests come from verified published release manifests. The site does not modify or republish the release files.</li><li>Edition-matched transcripts copied for same-origin reading are checked against the published manifest's size and digest before the Pages artifact is built.</li></ul><p><a href="{SOURCE_REPOSITORY}/tree/{_html(guide_export["source_commit"])}">Pinned source tree</a> · <a href="{_html(source_docs_url)}">Source documentation</a></p><h2>Published release versions</h2><ul>{"".join(releases) if releases else "<li>No published release is present in the verified catalog.</li>"}</ul></section></details><section class="guide-section"><h2>What this library does not claim</h2><p>Documentation, audio availability, successful playback and checksum validation do not establish efficacy, listening approval, rights clearance, or publication authorization beyond the verified release manifest.</p></section>'''


def _recommended_settings(source_commit):
    return """<section class="guide-section" id="recommended-audio-settings"><h2>Optional audio processing</h2><p>For the required stereo setup and its alternatives, see <a href="#headphones-and-stereo">Headphones and stereo</a>.</p><p>Preserve separate left/right playback and keep balance centered unless you use an accessibility adjustment.</p><h3>Processing preferences</h3><ul><li>Turn off optional spatial audio, head tracking, surround virtualization, EQ, audio enhancements, and crossfade when you want the unmodified stereo mix and those controls are available.</li><li>Disable unwanted repeat and shuffle, and disable automatic loudness normalization if the player offers that control. Use normal playback speed (1.0x).</li><li>Start at a comfortable low volume. Do not increase volume to chase a perceived effect.</li></ul><p>Optional processing choices are separate from the required stereo delivery. The website cannot detect or turn off operating-system, headphone, driver, or player processing. Accessibility needs and comfortable listening take priority.</p></section>"""


def _device_links():
    labels = [
        ("Android", "android"),
        ("iPhone and iPad", "ios"),
        ("Windows 11", "windows"),
        ("macOS", "macos"),
        ("Linux", "linux"),
    ]
    return (
        '<section class="guide-section" id="device-specific-setup"><h2>Device-specific setup</h2><p>Vendor and distribution menus vary. Review the guide for your device:</p><ul>'
        + "".join(
            f'<li><a href="{_html(slug)}/">{_html(name)}</a></li>'
            for name, slug in labels
        )
        + "</ul></section>"
    )


def _about_page_canonical(guide_export, catalog, source_docs_url, transcript_counts):
    return _about_page(guide_export, catalog, source_docs_url, transcript_counts)


def _validate_build(args):
    source_pin = json.loads(args.source_pin.read_text(encoding="utf-8"))
    guide_export = json.loads(args.guide_export.read_text(encoding="utf-8"))
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    return build_public_site(
        site_root=args.site_root,
        output=args.output,
        guide_export=guide_export,
        catalog=catalog,
        source_pin=source_pin,
        content_dir=args.content_dir,
        historical_reference=args.historical_reference,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", type=Path, default=Path("site"))
    parser.add_argument("--content-dir", type=Path, default=Path("docs/website"))
    parser.add_argument("--source-pin", type=Path, default=Path("site/source.json"))
    parser.add_argument("--guide-export", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--historical-reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = _validate_build(args)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
