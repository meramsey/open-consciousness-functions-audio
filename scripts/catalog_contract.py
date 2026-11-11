"""Strict production catalog projection (schema 2); schema 1 remains legacy-readable."""

from datetime import date
from urllib.parse import quote

from publication import (
    REPOSITORY,
    asset_url,
    digest,
    fields,
    manifest_digest,
    require,
    validate_manifest,
)


def validate_release(release):
    fields(
        release,
        (
            "version",
            "channel",
            "date",
            "source_ocf_commit",
            "source_ocf_version",
            "release_url",
            "release_notes_url",
            "functions",
            "preparations",
            "publication_manifest_sha256",
            "tag",
            "asset_order",
            "collections",
            "companions",
        ),
    )
    require(release["channel"] == "stable", "unsupported production channel")
    require(type(release["date"]) is str, "invalid release date")
    date.fromisoformat(release["date"])
    digest(release["publication_manifest_sha256"])
    require(
        all(
            type(release[k]) is list
            for k in ("functions", "preparations", "collections", "companions")
        ),
        "catalog groups must be arrays",
    )
    manifest = {
        "schema_version": 1,
        "repository": REPOSITORY,
        "tag": release["tag"],
        "edition": release["version"],
        "source_commit": release["source_ocf_commit"],
        "source_version": release["source_ocf_version"],
        "assets": [],
    }
    identities = set()

    def add_asset(asset, session=None, companion=False):
        common = (
            "asset_id",
            "filename",
            "display_filename",
            "format",
            "size_bytes",
            "sha256",
            "download_url",
            "provenance",
        )
        audio = (
            ("duration_seconds", "sample_rate_hz", "channels", "encoding")
            if session
            else ()
        )
        fields(asset, (*common, *audio), ("bit_depth",) if session else ())
        require(
            asset["download_url"] == asset_url(manifest, asset),
            "asset URL does not match release identity",
        )
        require(type(asset["provenance"]) is dict, "invalid provenance")
        provenance = dict(asset["provenance"])
        require(
            provenance.pop("source_ocf_commit", None) == release["source_ocf_commit"],
            "asset source commit mismatch",
        )
        entry = {k: asset[k] for k in common if k not in {"download_url", "provenance"}}
        entry.pop("display_filename")
        entry["filename"] = asset["display_filename"]
        entry["remote_filename"] = asset["filename"]
        entry["provenance"] = provenance
        if session:
            entry["session"] = dict(session)
            for key in (*audio, "bit_depth"):
                if key in asset:
                    entry["session"][key] = asset[key]
        else:
            require(
                asset["format"] not in {"mp3", "flac", "zip"}
                if companion
                else asset["format"] == "zip",
                "invalid collection/companion format",
            )
        manifest["assets"].append(entry)

    for preparation, group in [(False, f) for f in release["functions"]] + [
        (True, f) for f in release["preparations"]
    ]:
        fields(
            group,
            (
                "title",
                "languages",
                "voices",
                "sessions",
                "session_kind" if preparation else "function_id",
            ),
        )
        if preparation:
            require(
                group["session_kind"] == "preparation-learning",
                "invalid preparation identity",
            )
        identity = "preparation-learning" if preparation else group["function_id"]
        require(
            type(identity) is str and identity not in identities,
            "duplicate catalog identity",
        )
        identities.add(identity)
        require(
            all(type(group[k]) is list for k in ("languages", "voices", "sessions")),
            "invalid catalog group arrays",
        )
        require(
            type(group["title"]) is str and bool(group["title"].strip()),
            "invalid group title",
        )
        require(
            all(type(v) is str for k in ("languages", "voices") for v in group[k]),
            "invalid selector values",
        )
        languages, voices, session_ids = set(), set(), set()
        require(
            group["sessions"] and group["title"] == group["sessions"][0]["title"],
            "group title differs from session",
        )
        for session in group["sessions"]:
            fields(
                session,
                ("title", "locale", "voice_id", "voice_name", "edition", "assets"),
            )
            require(
                type(session["assets"]) is list and session["assets"],
                "session requires assets",
            )
            require(
                all(type(session[k]) is str for k in ("locale", "voice_id", "edition")),
                "invalid session identity",
            )
            key = (session["locale"], session["voice_id"], session["edition"])
            require(key not in session_ids, "duplicate session edition")
            session_ids.add(key)
            languages.add(session["locale"])
            voices.add(session["voice_id"])
            formats = []
            for asset in session["assets"]:
                formats.append(asset["format"])
                public_session = {k: v for k, v in session.items() if k != "assets"}
                public_session.update(
                    kind="preparation-learning" if preparation else "function",
                    function_id=None if preparation else identity,
                )
                add_asset(asset, public_session)
            require(
                len(formats) == len(set(formats)) and set(formats) <= {"mp3", "flac"},
                "duplicate or invalid session format",
            )
        require(
            group["sessions"]
            and sorted(languages) == sorted(group["languages"])
            and sorted(voices) == sorted(group["voices"]),
            "catalog selectors disagree with sessions",
        )
    for asset in release["collections"]:
        add_asset(asset)
    for asset in release["companions"]:
        add_asset(asset, companion=True)
    validate_manifest(manifest)
    order = release["asset_order"]
    require(
        type(order) is list and all(type(x) is str for x in order),
        "invalid asset order",
    )
    require(
        len(order) == len(set(order)) == len(manifest["assets"])
        and set(order) == {a["asset_id"] for a in manifest["assets"]},
        "asset order mismatch",
    )
    positions = {asset_id: index for index, asset_id in enumerate(order)}
    manifest["assets"].sort(key=lambda a: positions[a["asset_id"]])
    require(
        manifest_digest(manifest) == release["publication_manifest_sha256"],
        "catalog projection differs from approved manifest",
    )
    url = (
        "https://github.com/"
        + REPOSITORY
        + "/releases/tag/"
        + quote(release["tag"], safe="")
    )
    require(
        release["release_url"] == url and release["release_notes_url"] == url,
        "release URL mismatch",
    )
