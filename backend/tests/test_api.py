import unittest
from app.github_tools import _assess_ci
from app.main import app, health


class ApiTests(unittest.TestCase):
    def test_health(self):
        self.assertIn("get", app.openapi()["paths"]["/health"])
        self.assertEqual(health(), {"status": "healthy"})

    def test_partial_success_is_insufficient(self):
        checks = {
            "status": "incomplete",
            "items": [{"status": "completed", "conclusion": "success"}],
        }
        self.assertEqual(_assess_ci(checks), "insufficient_evidence")

    def test_running_check_is_pending(self):
        # 检查还在运行，没有结论是正常状态。
        checks = {
            "status": "available",
            "items": [{"status": "in_progress", "conclusion": None}],
        }
        self.assertEqual(_assess_ci(checks), "pending")
