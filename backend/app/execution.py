"""对外返回执行元数据，不暴露提示词、工具参数或仓库代码。"""

import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ToolStatus = Literal["completed", "error", "stale", "budget_exhausted"]


class ToolExecution(BaseModel):
    round: int = Field(ge=1)
    tool_name: str
    status: ToolStatus
    cached: bool = False
    duration_ms: float = Field(ge=0)


class ExecutionSummary(BaseModel):
    trace_id: UUID
    duration_ms: float = Field(ge=0)
    model_calls: int = Field(ge=0)
    tool_rounds: int = Field(ge=0)
    tool_calls_used: int = Field(ge=0)
    tools_executed: int = Field(
        ge=0, description="进入工具执行器的尝试数，含参数校验失败；不含缓存命中和预算跳过，也不等于 HTTP 请求数。"
    )
    finish_reason: Literal["completed", "tool_budget_exhausted"]
    tools: list[ToolExecution] = Field(default_factory=list)


def classify_tool_result(content: str) -> ToolStatus:
    # HTTP 请求可能成功，但工具返回了结构化错误；不能仅凭没抛异常判断成功。
    # completed 只表示工具完成，不代表 CI 成功或代码允许合并。
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return "completed"  # 时间工具等可以返回普通文本。
    if isinstance(data, dict):
        if "error" in data or data.get("status") == "unavailable":
            return "error"
        if data.get("status") == "stale":
            return "stale"
    return "completed"


def build_execution_summary(result: dict, trace_id: UUID, duration_ms: float) -> ExecutionSummary:
    events = [ToolExecution.model_validate(event) for event in result.get("tool_events", [])]
    return ExecutionSummary(
        trace_id=trace_id,
        duration_ms=duration_ms,
        model_calls=result.get("model_calls", 0),
        tool_rounds=result.get("tool_rounds", 0),
        tool_calls_used=result.get("tool_calls_used", 0),
        # 统计执行器尝试（含参数校验失败），排除缓存命中和预算跳过。
        tools_executed=sum(not event.cached and event.status != "budget_exhausted" for event in events),
        finish_reason=result["finish_reason"],
        tools=events,
    )
