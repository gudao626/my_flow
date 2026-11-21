import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.execution import ExecutionSummary
from app.execution_store import ExecutionStore
from app.main import list_executions


class ExecutionPageTests(unittest.TestCase):
    def test_paging_filtering_and_empty_pages(self):
        # 测试使用临时数据库，不影响你的开发历史。
        with tempfile.TemporaryDirectory() as directory:
            store = ExecutionStore(Path(directory) / "test.sqlite3")
            summaries = []
            for reason in ["completed", "tool_budget_exhausted", "completed"]:
                summary = ExecutionSummary(
                    trace_id=uuid4(), duration_ms=1, model_calls=1, tool_rounds=0,
                    tool_calls_used=0, tools_executed=0, finish_reason=reason,
                )
                store.save(summary)
                summaries.append(summary)
            first = store.list_page(2, 0)
            second = store.list_page(2, 2)
            self.assertEqual(first.total, 3)
            self.assertEqual([item.trace_id for item in first.items], [summaries[2].trace_id, summaries[1].trace_id])
            self.assertEqual(second.items, [summaries[0]])
            self.assertEqual(store.list_page(2, 99).items, [])
            with patch("app.main.execution_store", store):
                filtered = list_executions(20, 0, "tool_budget_exhausted")
            self.assertEqual(filtered.total, 1)
            self.assertEqual(filtered.items, [summaries[1]])

    def test_invalid_repository_parameters_are_rejected(self):
        store = ExecutionStore(Path("unused.sqlite3"))
        for limit, offset, reason in [(0, 0, None), (51, 0, None), (1, -1, None), (1, 0, "invalid")]:
            with self.assertRaises(ValueError):
                store.list_page(limit, offset, reason)

    def test_new_database_has_empty_history(self):
        with tempfile.TemporaryDirectory() as directory:
            page = ExecutionStore(Path(directory) / "test.sqlite3").list_page(20, 0)
            self.assertEqual(page.total, 0)
            self.assertEqual(page.items, [])
