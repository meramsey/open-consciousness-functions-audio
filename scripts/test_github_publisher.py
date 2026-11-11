import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import github_publisher as gh
from test_publication import fixture


class GitHubTests(unittest.TestCase):
    def test_offline_default_never_constructs_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest = fixture()
            (root / manifest["assets"][0]["filename"]).write_bytes(b"fixture")
            source = root / "manifest.json"
            source.write_text(json.dumps(manifest), encoding="utf-8")
            with (
                patch.object(gh, "GitHub") as transport,
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                gh.main([str(source), str(root)])
            transport.assert_not_called()
            self.assertEqual(
                json.loads(output.getvalue())["state"], "offline-preflight"
            )

    def test_failed_lookup_is_not_missing_release(self):
        transport = gh.GitHub("a" * 40)
        with (
            patch.object(
                gh.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=1, stderr="network failure"),
            ),
            self.assertRaisesRegex(ValueError, "network failure"),
        ):
            transport.find_release("audio-v1")

    def test_paginated_draft_lookup(self):
        transport = gh.GitHub("a" * 40)
        release = {"id": 2, "tag_name": "wanted", "draft": True}
        with patch.object(
            transport, "api", return_value=[[{"tag_name": "other"}], [release]]
        ) as request:
            self.assertEqual(transport.find_release("wanted"), release)
            self.assertTrue(request.call_args.kwargs["paginate"])

    def test_tag_mismatch_never_creates_release(self):
        transport = gh.GitHub("a" * 40)
        with patch.object(
            transport,
            "api",
            side_effect=[
                {"sha": "a" * 40},
                [{"ref": "refs/tags/v1"}],
                {"sha": "b" * 40},
            ],
        ) as request:
            with self.assertRaisesRegex(ValueError, "another commit"):
                transport.create_draft("v1", "marker")
            self.assertEqual(request.call_count, 3)
            self.assertFalse(
                any(c.kwargs.get("method") == "POST" for c in request.call_args_list)
            )

    def test_upload_uses_staged_file_and_encoded_name_without_clobber(self):
        transport = gh.GitHub("a" * 40)
        path = Path("/example/Readable title.flac")
        transport.api = lambda endpoint: {
            "id": 1,
            "draft": True,
            "upload_url": "https://uploads.github.com/repos/meramsey/open-consciousness-functions-audio/releases/1/assets{?name,label}",
        }
        with patch.object(
            gh.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=0, stderr="", stdout=json.dumps({"name": path.name})
            ),
        ) as run:
            transport.upload(1, path)
            command = run.call_args.args[0]
            self.assertIn("Readable%20title.flac", command[2])
            self.assertEqual(command[-1], str(path))
            self.assertNotIn("--clobber", command)


if __name__ == "__main__":
    unittest.main()
