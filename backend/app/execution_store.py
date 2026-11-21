"""SQLite 执行摘要仓库：每次操作独立连接，避免跨线程共享连接。"""

import sqlite3
from pathlib import Path
from uuid import UUID

from .execution import ExecutionSummary


class ExecutionStore:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS executions ("
            "trace_id TEXT PRIMARY KEY, summary_json TEXT NOT NULL, "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        return connection

    def save(self, summary: ExecutionSummary) -> None:
        connection = self._connect()
        try:
            # 参数绑定，不拼接 SQL；事务成功后提交，失败时自动回滚。
            with connection:
                connection.execute(
                    "INSERT INTO executions (trace_id, summary_json) VALUES (?, ?)",
                    (str(summary.trace_id), summary.model_dump_json()),
                )
        finally:
            connection.close()

    def get(self, trace_id: UUID) -> ExecutionSummary | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT summary_json FROM executions WHERE trace_id = ?", (str(trace_id),)
            ).fetchone()
            # 从数据库读出后再次校验，避免把损坏的数据直接返回接口。
            return ExecutionSummary.model_validate_json(row[0]) if row else None
        finally:
            connection.close()


# 路径与启动目录无关；不保存聊天正文、Token 或仓库差异。
execution_store = ExecutionStore(Path(__file__).resolve().parents[1] / "data" / "executions.sqlite3")
