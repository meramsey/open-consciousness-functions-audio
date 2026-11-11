"""Optional deterministic ZIP parts of individual verified recordings (no re-encoding)."""

import hashlib
import re
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote

from publication import (
    canonical_bytes,
    filename,
    manifest_digest,
    require,
    validate_manifest,
    verify_files,
)


def _info(name):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def build_collections(manifest, root, destination, *, max_part_bytes=2_000_000_000):
    """Write a fresh collection directory; preserve failed staging for diagnosis.

    Parts are grouped by language, voice ID and format, with separate tracks.
    Input approval is not inferred; outputs still require exact-asset approval.
    """
    verify_files(manifest, root)
    require(
        type(max_part_bytes) is int and 4096 <= max_part_bytes < 2**31,
        "invalid ZIP part limit",
    )
    root, destination = Path(root), Path(destination).absolute()
    require(
        not destination.exists() and not destination.is_symlink(),
        "collection destination already exists",
    )
    require(
        not any(p.is_symlink() for p in destination.parents),
        "symlink in collection destination",
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    groups = {}
    for asset in manifest["assets"]:
        if asset["format"] in {"mp3", "flac"}:
            session = asset["session"]
            groups.setdefault(
                (session["locale"], session["voice_id"], asset["format"]), []
            ).append(asset)
    require(groups, "no recordings to collect")
    stage = Path(
        tempfile.mkdtemp(prefix=".ocf-collection-stage-", dir=destination.parent)
    )
    records = []
    try:
        for (locale, voice, fmt), assets in sorted(groups.items()):
            parts, current, budget = [], [], 4096
            for asset in sorted(
                assets,
                key=lambda a: (
                    a["session"]["kind"] != "preparation-learning",
                    a["filename"],
                ),
            ):
                # Conservative room for ZIP headers, playlist and entry manifest.
                cost = (
                    asset["size_bytes"]
                    + 2048
                    + 4 * len(asset["filename"].encode("utf-8"))
                )
                require(
                    cost + 4096 < max_part_bytes,
                    "one recording exceeds collection part limit",
                )
                if current and budget + cost >= max_part_bytes:
                    parts.append(current)
                    current, budget = [], 4096
                current.append(asset)
                budget += cost
            if current:
                parts.append(current)
            for number, members in enumerate(parts, 1):
                name = f"OCF-Collection - {locale} - {voice} - v{manifest['edition']} - {fmt} - part{number:03d}.zip"
                filename(name)
                path = stage / name
                playlist = "#EXTM3U\n" + "".join(
                    quote(a["filename"], safe="") + "\n" for a in members
                )
                member_manifest = {
                    "schema_version": 1,
                    "source_publication_sha256": manifest_digest(manifest),
                    "members": [
                        {
                            k: a[k]
                            for k in ("asset_id", "filename", "size_bytes", "sha256")
                        }
                        for a in members
                    ],
                }
                with zipfile.ZipFile(
                    path, "x", compression=zipfile.ZIP_STORED
                ) as archive:
                    for asset in members:
                        source = root / asset["filename"]
                        require(not source.is_symlink(), "source became a symlink")
                        digest = hashlib.sha256()
                        size = 0
                        with (
                            source.open("rb") as inp,
                            archive.open(_info(asset["filename"]), "w") as out,
                        ):
                            while chunk := inp.read(1024 * 1024):
                                digest.update(chunk)
                                size += len(chunk)
                                out.write(chunk)
                        require(
                            size == asset["size_bytes"]
                            and digest.hexdigest() == asset["sha256"],
                            "source changed while building collection",
                        )
                    archive.writestr(_info("playlist.m3u8"), playlist.encode("utf-8"))
                    archive.writestr(
                        _info("members.json"), canonical_bytes(member_manifest)
                    )
                require(path.stat().st_size < max_part_bytes, "ZIP exceeded part limit")
                with zipfile.ZipFile(path) as archive:
                    for asset in members:
                        with archive.open(asset["filename"]) as stream:
                            require(
                                hashlib.file_digest(stream, "sha256").hexdigest()
                                == asset["sha256"],
                                "ZIP member read-back mismatch",
                            )
                with path.open("rb") as stream:
                    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
                records.append(
                    {
                        "asset_id": "collection-" + checksum[:32],
                        "filename": name,
                        "remote_filename": re.sub(
                            r"[^A-Za-z0-9._-]+", "-", name[:-4]
                        ).strip(".-")[:170]
                        + "-"
                        + checksum[:12]
                        + ".zip",
                        "format": "zip",
                        "size_bytes": path.stat().st_size,
                        "sha256": checksum,
                        "provenance": {
                            "source_manifest_sha256": manifest_digest(manifest),
                            "technical_receipt_sha256": hashlib.sha256(
                                canonical_bytes(member_manifest)
                            ).hexdigest(),
                        },
                    }
                )
        validate_manifest({**manifest, "assets": records})
        (stage / "collection-receipt.json").write_bytes(
            canonical_bytes(
                {"schema_version": 1, "assets": records, "publication_approved": False}
            )
        )
        require(
            not destination.exists(), "collection destination appeared during build"
        )
        stage.rename(destination)
        return records
    except Exception as exc:
        (stage / "failure.json").write_bytes(
            canonical_bytes({"error": type(exc).__name__, "message": str(exc)})
        )
        raise
