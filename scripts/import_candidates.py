"""Copy explicit source-export candidates into a fresh, unapproved publication bundle."""

import argparse
import hashlib
import json
import math
import re
import shutil
import tempfile
from pathlib import Path

from publication import (
    REPOSITORY,
    canonical_bytes,
    digest,
    fields,
    filename,
    require,
    validate_manifest,
    verify_files,
)


def import_candidates(paths, destination, *, tag, edition):
    destination = Path(destination).absolute()
    require(not destination.exists(), "destination already exists")
    require(
        not any(p.is_symlink() for p in (destination, *destination.parents)),
        "symlink destination",
    )
    require(paths, "no export candidates")
    manifest = {
        "schema_version": 1,
        "repository": REPOSITORY,
        "tag": tag,
        "edition": edition,
        "source_commit": None,
        "source_version": None,
        "assets": [],
    }
    sources = []
    for supplied in paths:
        path = Path(supplied).absolute()
        require(
            not any(p.is_symlink() for p in (path, *path.parents)), "symlink candidate"
        )
        document = json.loads(path.read_text(encoding="utf-8"))
        fields(
            document,
            (
                "schema_version",
                "session",
                "source_commit",
                "source_version",
                "source_manifest_sha256",
                "master_sha256",
                "technical_receipt_sha256",
                "audio",
                "artifacts",
                "publication_approved",
            ),
            ("render_source", "export_commit"),
        )
        require(
            type(document["schema_version"]) is int and document["schema_version"] == 1,
            "unsupported export candidate schema",
        )
        require(
            document["publication_approved"] is False,
            "candidate must not assert publication approval",
        )
        require(
            document["session"].get("edition") == edition, "candidate edition mismatch"
        )
        for key in ("source_commit", "source_version"):
            if manifest[key] is None:
                manifest[key] = document[key]
            require(
                manifest[key] == document[key],
                "mixed source revisions require separate releases",
            )
        provenance = {
            k: document[k]
            for k in (
                "source_manifest_sha256",
                "master_sha256",
                "technical_receipt_sha256",
                "render_source",
                "export_commit",
            )
            if k in document
        }
        require(
            type(document["artifacts"]) is list and document["artifacts"],
            "no candidate artifacts",
        )
        candidate_assets = []
        for item in document["artifacts"]:
            fields(item, ("file", "bytes", "sha256"))
            filename(item["file"])
            fmt = Path(item["file"]).suffix.lower().lstrip(".")
            require(
                fmt
                in {"flac", "mp3", "png", "jpg", "txt", "srt", "vtt", "lrc", "json"},
                "unexpected export artifact",
            )
            # GitHub normalizes punctuation. Make the exact remote name explicit,
            # with a stable filename digest to disambiguate Unicode normalization.
            stem = (
                re.sub(r"[^A-Za-z0-9._-]+", "-", Path(item["file"]).stem).strip("-.")[
                    :170
                ]
                or "OCF"
            )
            suffix = hashlib.sha256(item["file"].encode("utf-8")).hexdigest()[:12]
            asset = {
                "asset_id": "asset-"
                + hashlib.sha256(item["file"].encode("utf-8")).hexdigest(),
                "filename": item["file"],
                "remote_filename": f"{stem}-{suffix}.{fmt}",
                "format": fmt,
                "size_bytes": item["bytes"],
                "sha256": item["sha256"],
                "provenance": provenance,
            }
            if fmt in {"flac", "mp3"}:
                audio = document["audio"][fmt]
                asset["session"] = {
                    **document["session"],
                    **{
                        k: audio[k]
                        for k in (
                            "duration_seconds",
                            "sample_rate_hz",
                            "channels",
                            "encoding",
                            "bit_depth",
                        )
                        if k in audio
                    },
                }
            candidate_assets.append(asset)
            sources.append((path.parent / item["file"], asset))
        formats = [a["format"] for a in candidate_assets]
        require(
            formats.count("flac") == formats.count("mp3") == formats.count("json") == 1,
            "candidate needs one FLAC, MP3 and technical receipt",
        )
        require(
            formats.count("png") + formats.count("jpg") == 1,
            "candidate needs one cover",
        )
        verify_files({**manifest, "assets": candidate_assets}, path.parent)
        technical_asset = next(a for a in candidate_assets if a["format"] == "json")
        require(
            technical_asset["sha256"] == document["technical_receipt_sha256"],
            "technical receipt hash mismatch",
        )
        technical = json.loads(
            (path.parent / technical_asset["filename"]).read_text(encoding="utf-8")
        )
        fields(
            technical,
            (
                "schema_version",
                "source_kind",
                "source_commit",
                "source_version",
                "frames",
                "peak",
                "clipped_sample_count",
                "audio",
            ),
        )
        require(
            type(technical["schema_version"]) is int
            and technical["schema_version"] == 1
            and technical["source_kind"] == "verified-retained-flac",
            "unsupported technical receipt",
        )
        require(
            type(technical["frames"]) is int
            and technical["frames"] > 0
            and type(technical["peak"]) in (int, float)
            and math.isfinite(technical["peak"])
            and 0 <= technical["peak"] < 1
            and type(technical["clipped_sample_count"]) is int,
            "invalid technical measurements",
        )
        fields(technical["audio"], ("flac", "mp3"))
        for fmt, measured in technical["audio"].items():
            fields(
                measured,
                (
                    "decoded_pcm_sha256",
                    "packet_sha256",
                    "operation",
                    "sample_rate_hz",
                    "channels",
                    "duration_seconds",
                    "encoding",
                ),
                ("bit_depth",),
            )
            digest(measured["decoded_pcm_sha256"])
            digest(measured["packet_sha256"])
            require(
                measured["operation"] in {"stream-copy", "encode-from-lossless"},
                "invalid audio operation",
            )
            if fmt == "flac":
                require(
                    measured["operation"] == "stream-copy"
                    and measured.get("bit_depth") in {16, 24, 32},
                    "invalid retained FLAC operation or resolution",
                )
        require(
            technical.get("audio") == document["audio"]
            and technical.get("source_commit") == document["source_commit"]
            and technical.get("source_version") == document["source_version"]
            and technical.get("clipped_sample_count") == 0,
            "technical receipt disagrees with candidate",
        )
        manifest["assets"].extend(candidate_assets)
    manifest["assets"].sort(
        key=lambda a: (not a["filename"].startswith("00 - "), a["filename"])
    )
    validate_manifest(manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".ocf-import-stage-", dir=destination.parent))
    # Failed staging is retained. Only hash-verified copies become a candidate.
    for source, asset in sources:
        require(
            not source.is_symlink() and source.is_file(), "source changed during import"
        )
        shutil.copyfile(source, stage / asset["filename"])
    verify_files(manifest, stage)
    (stage / "publication.json").write_bytes(canonical_bytes(manifest))
    require(not destination.exists(), "destination appeared during import")
    stage.rename(destination)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--edition", required=True)
    args = parser.parse_args(argv)
    manifest = import_candidates(
        args.candidates, args.output, tag=args.tag, edition=args.edition
    )
    print(
        json.dumps({"assets": len(manifest["assets"]), "publication_approved": False})
    )


if __name__ == "__main__":
    main()
