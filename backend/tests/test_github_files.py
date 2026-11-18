import unittest

from app.github_files import MAX_PATCH_CHARS, _summarize_files
from app.github_tools import _parse_pr_url


class GitHubFilesTests(unittest.TestCase):
    def test_long_patch_is_bounded_and_marked(self):
        result = _summarize_files([
            {"filename": "app.py", "patch": "x" * (MAX_PATCH_CHARS + 1)}
        ], False)
        item = result["items"][0]
        self.assertEqual(len(item["patch"]), MAX_PATCH_CHARS)
        self.assertEqual(item["patch_status"], "truncated")

    def test_missing_patch_is_not_empty_diff(self):
        result = _summarize_files([{"filename": "image.png"}], False)
        self.assertIsNone(result["items"][0]["patch"])
        self.assertEqual(result["items"][0]["patch_status"], "unavailable")

    def test_next_page_means_incomplete_file_list(self):
        result = _summarize_files([{"filename": "app.py", "patch": "+hello"}], True)
        self.assertEqual(result["status"], "incomplete")

    def test_shared_parser_rejects_other_hosts(self):
        with self.assertRaises(ValueError):
            _parse_pr_url("https://example.com/owner/repo/pull/1")

    def test_shared_parser_extracts_repository_and_number(self):
        self.assertEqual(
            _parse_pr_url("https://github.com/gudao626/my_flow/pull/1"),
            ("gudao626", "my_flow", "1"),
        )
