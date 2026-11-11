"""Strict, offline publication boundary. No uploads or inferred permissions."""

import hashlib
import json
import math
import re
from pathlib import Path
from urllib.parse import quote

REPOSITORY = "meramsey/open-consciousness-functions-audio"
HEX = re.compile(r"[a-f0-9]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}\Z")
FORMATS = {
    "mp3",
    "flac",
    "png",
    "jpg",
    "pdf",
    "html",
    "md",
    "txt",
    "vtt",
    "srt",
    "zip",
    "m3u8",
}


def require(value, message):
    if not value:
        raise ValueError(message)


def fields(value, required, optional=()):
    require(type(value) is dict, "expected object")
    require(
        set(required) <= value.keys(),
        "missing required fields: " + ", ".join(sorted(set(required) - value.keys())),
    )
    require(
        value.keys() <= set(required) | set(optional),
        "unknown fields: "
        + ", ".join(sorted(value.keys() - set(required) - set(optional))),
    )


def text(value):
    require(
        type(value) is str and value.strip() == value and bool(value),
        "expected nonempty text",
    )
    require(
        not any(ord(c) < 32 or ord(c) == 127 for c in value),
        "control character in text",
    )


def identifier(value):
    text(value)
    require(IDENTIFIER.fullmatch(value), "invalid identifier")


def digest(value):
    require(type(value) is str and HEX.fullmatch(value), "invalid SHA-256")


def filename(value):
    text(value)
    require(
        len(value.encode("utf-8")) <= 200 and not any(c in value for c in '/\\:*?"<>|'),
        "unsafe filename",
    )
    require(
        not value.startswith((".", "-")) and not value.endswith((".", " ")),
        "unsafe filename",
    )
    require(
        value.split(".")[0].upper()
        not in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *[f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)],
        },
        "reserved filename",
    )


def canonical_bytes(value):
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def manifest_digest(manifest):
    validate_manifest(manifest)
    return hashlib.sha256(canonical_bytes(manifest)).hexdigest()


def validate_manifest(manifest):
    fields(
        manifest,
        (
            "schema_version",
            "repository",
            "tag",
            "edition",
            "source_commit",
            "source_version",
            "assets",
        ),
    )
    require(
        type(manifest["schema_version"]) is int and manifest["schema_version"] == 1,
        "unsupported publication schema",
    )
    require(manifest["repository"] == REPOSITORY, "unexpected distribution repository")
    for key in ("tag", "edition", "source_version"):
        identifier(manifest[key])
    require(
        type(manifest["source_commit"]) is str
        and re.fullmatch(r"[a-f0-9]{40}", manifest["source_commit"]),
        "source_commit must be a full Git SHA",
    )
    assets = manifest["assets"]
    require(
        type(assets) is list and 0 < len(assets) <= 997,
        "expected 1..997 assets (three slots reserved for manifest, checksums and notes)",
    )
    remote_names = {"publication.json", "sha256sums.txt", "release-notes.md"}
    ids, names = set(), {"publication.json", "sha256sums.txt", "release-notes.md"}
    for asset in assets:
        fields(
            asset,
            (
                "asset_id",
                "filename",
                "remote_filename",
                "format",
                "size_bytes",
                "sha256",
                "provenance",
            ),
            ("session",),
        )
        identifier(asset["asset_id"])
        filename(asset["filename"])
        filename(asset["remote_filename"])
        require(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", asset["remote_filename"]),
            "remote filename must be GitHub-compatible ASCII",
        )
        require(
            asset["remote_filename"].casefold() not in remote_names,
            "duplicate remote filename",
        )
        remote_names.add(asset["remote_filename"].casefold())
        require(
            asset["asset_id"] not in ids and asset["filename"].casefold() not in names,
            "duplicate asset ID or filename",
        )
        ids.add(asset["asset_id"])
        names.add(asset["filename"].casefold())
        require(
            type(asset["format"]) is str
            and asset["format"] in FORMATS
            and asset["filename"].lower().endswith("." + asset["format"])
            and asset["remote_filename"].lower().endswith("." + asset["format"]),
            "format/extension mismatch",
        )
        require(
            type(asset["size_bytes"]) is int and 0 < asset["size_bytes"] < 2**31,
            "asset must be nonempty and under 2 GiB",
        )
        digest(asset["sha256"])
        provenance = asset["provenance"]
        fields(
            provenance,
            ("source_manifest_sha256", "technical_receipt_sha256"),
            ("master_sha256",),
        )
        for value in provenance.values():
            digest(value)
        if asset["format"] in {"mp3", "flac"}:
            require("session" in asset, "audio needs session metadata")
            require(
                "master_sha256" in provenance, "audio needs verified master provenance"
            )
        if "session" not in asset:
            continue
        require(
            asset["format"] in {"mp3", "flac"},
            "session metadata belongs only to audio assets",
        )
        session = asset["session"]
        fields(
            session,
            (
                "kind",
                "function_id",
                "title",
                "locale",
                "voice_id",
                "voice_name",
                "edition",
                "duration_seconds",
                "sample_rate_hz",
                "channels",
                "encoding",
            ),
            ("bit_depth",),
        )
        require(
            session["kind"] in {"function", "preparation-learning"},
            "unknown session kind",
        )
        if session["kind"] == "function":
            require(
                type(session["function_id"]) is str
                and re.fullmatch(r"OCF-[A-Z]{3}-[A-Z0-9]{3,4}", session["function_id"]),
                "invalid function ID",
            )
        else:
            require(
                session["function_id"] is None, "Preparation Learning is not a function"
            )
        for key in ("title", "voice_name", "encoding"):
            text(session[key])
        for key in ("locale", "voice_id", "edition"):
            identifier(session[key])
        duration = session["duration_seconds"]
        require(
            type(duration) in (int, float) and math.isfinite(duration) and duration > 0,
            "invalid duration",
        )
        require(
            type(session["sample_rate_hz"]) is int and session["sample_rate_hz"] > 0,
            "invalid sample rate",
        )
        require(
            type(session["channels"]) is int and session["channels"] in (1, 2),
            "invalid channels",
        )
        if "bit_depth" in session:
            require(
                type(session["bit_depth"]) is int
                and session["bit_depth"] in (16, 24, 32),
                "invalid bit depth",
            )


def verify_files(manifest, root):
    """Read only explicitly named regular files; reject symlinks, including parents."""
    validate_manifest(manifest)
    root = Path(root).absolute()
    require(
        not any(p.is_symlink() for p in (root, *root.parents)), "symlink in asset root"
    )
    for asset in manifest["assets"]:
        path = root / asset["filename"]
        require(
            not path.is_symlink() and path.is_file(),
            "missing or symlink asset: " + asset["filename"],
        )
        require(
            path.stat().st_size == asset["size_bytes"],
            "asset size mismatch: " + asset["filename"],
        )
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        require(
            actual == asset["sha256"], "asset checksum mismatch: " + asset["filename"]
        )


def verify_approval(manifest, approval, *, publication=False):
    """An explicit owner record, not proof of identity or an automatic legal verdict."""
    fields(
        approval,
        (
            "schema_version",
            "manifest_sha256",
            "owner",
            "approved_at",
            "public_assets",
            "voice_redistribution",
            "artwork_redistribution",
            "publish",
        ),
    )
    require(
        type(approval["schema_version"]) is int and approval["schema_version"] == 1,
        "unsupported approval schema",
    )
    require(
        approval["manifest_sha256"] == manifest_digest(manifest),
        "approval does not bind this exact manifest",
    )
    text(approval["owner"])
    from datetime import datetime

    text(approval["approved_at"])
    timestamp = datetime.fromisoformat(approval["approved_at"])
    require(timestamp.tzinfo is not None, "approval needs timezone")
    for key in ("public_assets", "voice_redistribution", "artwork_redistribution"):
        require(approval[key] is True, "owner approval missing: " + key)
    require(type(approval["publish"]) is bool, "publish must be boolean")
    if publication:
        require(approval["publish"] is True, "final publication approval missing")


def asset_url(manifest, asset):
    return f"https://github.com/{REPOSITORY}/releases/download/{quote(manifest['tag'], safe='')}/{quote(asset.get('remote_filename', asset['filename']), safe='')}"


def checksums(manifest):
    validate_manifest(manifest)
    return "".join(
        f"{a['sha256']}  {a['remote_filename']}\n"
        for a in sorted(manifest["assets"], key=lambda item: item["filename"])
    )


def control_artifacts(manifest):
    """Deterministic public metadata, with no local paths or approval identities."""
    validate_manifest(manifest)
    notes = [
        "# OCF audio edition " + manifest["edition"],
        "",
        "Source commit: " + manifest["source_commit"],
        "",
        "## Downloads",
        "",
    ]
    for asset in sorted(manifest["assets"], key=lambda item: item["filename"]):
        notes.append(
            "- "
            + asset["filename"]
            + " → "
            + asset["remote_filename"]
            + " ("
            + str(asset["size_bytes"])
            + " bytes)"
        )
    files = {
        "publication.json": canonical_bytes(manifest),
        "release-notes.md": ("\n".join(notes) + "\n").encode("utf-8"),
    }
    hashes = {a["remote_filename"]: a["sha256"] for a in manifest["assets"]}
    hashes.update(
        {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    )
    files["SHA256SUMS.txt"] = "".join(
        f"{hashes[name]}  {name}\n" for name in sorted(hashes)
    ).encode("utf-8")
    return files
