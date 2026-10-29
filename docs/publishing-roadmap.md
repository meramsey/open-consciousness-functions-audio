# Publishing roadmap

This bootstrap provides a static placeholder, empty catalog, and validation/deployment foundation only. It does not publish audio, create releases, or implement a publisher.

Future work, subject to explicit approval:

1. Finalize strict release-manifest validation and stable function/session/asset identity rules.
2. Consume only eligible, successfully rendered artifacts that separately passed listening, rights/licensing, and explicit public-distribution approval.
3. Produce one MP3 and one lossless FLAC per approved function/session as authorized, supporting multiple voice and language editions and preserving historical versions.
4. Attach individual files, optional packs of individual playable files, M3U8 playlists, approved embedded/downloadable artwork, release notes, audio specifications, machine-readable manifests, and `SHA256SUMS.txt` to GitHub Releases.
5. Respect current GitHub per-asset and release limits; split large packs and checksum each part. Never concatenate an entire library into one large recording.
6. Optionally mirror approved releases to Internet Archive and, if explicitly selected, MEGA. Verify mirror bytes against published SHA-256 values before listing the mirror.
7. Generate the website catalog from release metadata and deploy Pages after release and catalog verification. Provide versioned links and permanent function-ID URLs.

No automation may infer distribution permission from render success. Audio generation eligibility, render success, listening approval, rights approval, and public distribution authorization are independent states. Every release requires explicit approval and verification; do not overwrite an approved release or its historical URLs. Credentials must be scoped, protected, and never written into the repository or logs.
