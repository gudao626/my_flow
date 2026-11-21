import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.execution import ExecutionSummary
from app.execution_store import ExecutionStore
from app.main import get_execution


class ExecutionStoreTests(unittest.TestCase):
    def test_record_survives_new_store_instance(self):
        # 临时目录隔离测试，不向开发数据库写入假记录。
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "executions.sqlite3"
            summary = ExecutionSummary(
                trace_id=uuid4(), duration_ms=12, model_calls=1,
                tool_rounds=0, tool_calls_used=0, tools_executed=0,
                finish_reason="completed",
            )
            ExecutionStore(path).save(summary)
            self.assertEqual(ExecutionStore(path).get(summary.trace_id), summary)
            self.assertIsNone(ExecutionStore(path).get(uuid4()))

    def test_query_endpoint_returns_404_for_unknown_id(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ExecutionStore(Path(directory) / "test.sqlite3")
            with patch("app.main.execution_store", store):
                with self.assertRaises(HTTPException) as error:
                    get_execution(uuid4())
            self.assertEqual(error.exception.status_code, 404)
