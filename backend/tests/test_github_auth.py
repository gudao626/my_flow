import unittest
from unittest.mock import patch

from app.github_tools import _build_github_headers


class GitHubAuthTests(unittest.TestCase):
    def test_token_is_trimmed_and_used_for_authentication(self):
        # 假凭证即可验证配置行为，不读取真实 Token，也不访问网络。
        # with 结束后环境变量自动恢复，不会污染其他测试。
        with patch.dict("os.environ", {"GITHUB_TOKEN": "  fake-token  "}):
            headers = _build_github_headers()

        self.assertEqual(headers["Authorization"], "Bearer fake-token")
        self.assertEqual(headers["Accept"], "application/vnd.github+json")

    def test_missing_token_allows_anonymous_requests(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": ""}):
            headers = _build_github_headers()

        # 未配置时不发送空认证头，保留匿名查询能力。
        self.assertNotIn("Authorization", headers)
