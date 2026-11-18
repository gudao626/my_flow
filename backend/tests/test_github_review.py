import json
import unittest
from unittest.mock import patch

import httpx

from app.chat_graph import TOOLS, _execute_call
from app.github_review import _collect_review_context
from app.llm import ModelResponseError

HEAD = "a" * 40
BASE = "b" * 40
NEW_SHA = "c" * 40


def finish_immediate(coroutine):
    """假客户端的 async 方法立即返回，无需网络或事件循环即可执行本单元测试。"""
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    raise AssertionError("Test coroutine unexpectedly suspended.")


class FakeGitHub:
    def __init__(self, after_head=HEAD, after_base=BASE, checks_status=200):
        self.after_head = after_head
        self.after_base = after_base
        self.checks_status = checks_status
        self.paths = []
        self.pr_reads = 0

    async def get(self, path, **kwargs):
        self.paths.append(path)
        request = httpx.Request("GET", f"https://api.github.com{path}")
        if path.endswith("/pulls/1"):
            self.pr_reads += 1
            data = {
                "title": "Example PR", "state": "open", "merged": False,
                "head": {"sha": HEAD if self.pr_reads == 1 else self.after_head},
                "base": {"sha": BASE if self.pr_reads == 1 else self.after_base},
            }
        elif path.endswith("/files"):
            data = [{"filename": "app.py", "patch": "+print('hello')"}]
        elif path.endswith("/check-runs"):
            data = {"total_count": 1, "check_runs": [{
                "name": "tests", "head_sha": HEAD, "status": "completed", "conclusion": "success",
            }]}
            return httpx.Response(self.checks_status, json=data, request=request)
        else:
            raise AssertionError(f"Unexpected path: {path}")
        return httpx.Response(200, json=data, request=request)


class ReviewContextTests(unittest.TestCase):
    def collect(self, client):
        return finish_immediate(_collect_review_context(client, "/repos/gudao626/my_flow", "1"))

    def test_stable_pr_returns_code_and_ci_for_observed_version(self):
        client = FakeGitHub()
        result = self.collect(client)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["head_sha"], HEAD)
        self.assertEqual(result["ci_assessment"], "observed_success")
        self.assertEqual(result["files"]["items"][0]["filename"], "app.py")
        self.assertIn(f"/repos/gudao626/my_flow/commits/{HEAD}/check-runs", client.paths)

    def test_new_commit_discards_review_evidence(self):
        result = self.collect(FakeGitHub(after_head=NEW_SHA))
        self.assertEqual(result["status"], "stale")
        self.assertNotIn("files", result)
        self.assertNotIn("ci_assessment", result)

    def test_target_branch_update_also_discards_evidence(self):
        result = self.collect(FakeGitHub(after_base=NEW_SHA))
        self.assertEqual(result["status"], "stale")
        self.assertNotIn("check_runs", result)

    def test_ci_failure_to_load_preserves_files_without_success_verdict(self):
        result = self.collect(FakeGitHub(checks_status=403))
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["check_runs"]["status"], "unavailable")
        self.assertEqual(result["ci_assessment"], "insufficient_evidence")
        self.assertTrue(result["files"]["items"])

    def test_tool_is_registered_and_dispatched(self):
        name = "get_github_pr_review_context"
        self.assertIn(name, [tool["function"]["name"] for tool in TOOLS])

        async def fake_tool(pr_url):
            return {"status": "stale", "source_url": pr_url}

        call = {"id": "call-1", "type": "function", "function": {
            "name": name, "arguments": json.dumps({"pr_url": "https://github.com/gudao626/my_flow/pull/1"}),
        }}
        with patch("app.chat_graph.get_github_pr_review_context", new=fake_tool):
            result = json.loads(finish_immediate(_execute_call(call)))
        self.assertEqual(result["status"], "stale")

    def test_tool_rejects_unexpected_arguments(self):
        call = {"id": "call-1", "type": "function", "function": {
            "name": "get_github_pr_review_context",
            "arguments": json.dumps({"pr_url": "https://github.com/gudao626/my_flow/pull/1", "token": "fake"}),
        }}
        with self.assertRaises(ModelResponseError):
            finish_immediate(_execute_call(call))
