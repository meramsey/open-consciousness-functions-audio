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

    def test_pagination_supports_existing_cli_without_slurp(self):
        transport = gh.GitHub(None)
        outcome = SimpleNamespace(returncode=0, stderr="", stdout='[]\n[{"id":2}]\n')
        with patch.object(gh.subprocess, "run", return_value=outcome) as run:
            self.assertEqual(
                transport.api("repos/example/releases", paginate=True),
                [[], [{"id": 2}]],
            )
            self.assertNotIn("--slurp", run.call_args.args[0])

    def test_read_only_transport_cannot_create_release(self):
        transport = gh.GitHub(None)
        with (
            patch.object(transport, "api") as api,
            self.assertRaisesRegex(ValueError, "read-only"),
        ):
            transport.create_draft("v1", "marker")
        api.assert_not_called()

    def test_paginated_draft_lookup(self):
        transport = gh.GitHub("a" * 40)
        release = {
            "id": 2,
            "tag_name": "wanted",
            "draft": True,
            "target_commitish": "a" * 40,
        }
        with patch.object(
            transport, "api", side_effect=[[[{"tag_name": "other"}], [release]], []]
        ) as request:
            self.assertEqual(transport.find_release("wanted"), release)
            self.assertTrue(request.call_args_list[0].kwargs["paginate"])

    def test_existing_draft_with_another_target_is_never_adopted(self):
        transport = gh.GitHub("a" * 40)
        release = {"id": 2, "tag_name": "wanted", "target_commitish": "b" * 40}
        with patch.object(transport, "api", return_value=[[release]]) as request:
            with self.assertRaisesRegex(ValueError, "another distribution commit"):
                transport.find_release("wanted")
            self.assertEqual(request.call_count, 1)

    def test_existing_draft_tag_cannot_name_another_commit(self):
        transport = gh.GitHub("a" * 40)
        release = {"id": 2, "tag_name": "wanted", "target_commitish": "a" * 40}
        with (
            patch.object(
                transport,
                "api",
                side_effect=[
                    [[release]],
                    [{"ref": "refs/tags/wanted"}],
                    {"sha": "b" * 40},
                ],
            ),
            self.assertRaisesRegex(ValueError, "tag points to another"),
        ):
            transport.find_release("wanted")

    def test_existing_matching_draft_and_tag_are_reused(self):
        transport = gh.GitHub("a" * 40)
        release = {"id": 2, "tag_name": "wanted", "target_commitish": "a" * 40}
        with patch.object(
            transport,
            "api",
            side_effect=[[[release]], [{"ref": "refs/tags/wanted"}], {"sha": "a" * 40}],
        ):
            self.assertEqual(transport.find_release("wanted"), release)

    def test_read_only_transport_never_uploads(self):
        transport = gh.GitHub(None)
        with patch.object(transport, "api") as request:
            with self.assertRaisesRegex(ValueError, "read-only"):
                transport.upload(1, Path("example.flac"))
            request.assert_not_called()

    def test_upload_rechecks_distribution_target_before_write(self):
        transport = gh.GitHub("a" * 40)
        release = {"id": 1, "draft": True, "target_commitish": "b" * 40}
        with (
            patch.object(transport, "api", return_value=release),
            patch.object(gh.subprocess, "run") as upload,
        ):
            with self.assertRaisesRegex(ValueError, "expected draft"):
                transport.upload(1, Path("example.flac"))
            upload.assert_not_called()

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
            "target_commitish": "a" * 40,
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
