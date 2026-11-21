import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.chat_graph import MAX_TOOL_CALLS, answer_with_evidence, call_model, run_tool
from app.execution import build_execution_summary, classify_tool_result
from app.main import ChatRequest, app, chat


def finish_immediate(coroutine):
    # 测试中的异步外部依赖均立即返回，避免访问模型、GitHub 和本机事件循环。
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    raise AssertionError("Unexpected suspension in mocked node.")


def tool_call(number):
    return {"id": f"call-{number}", "type": "function", "function": {
        "name": "get_utc_time", "arguments": "{}",
    }}


class ExecutionTests(unittest.TestCase):
    def test_structured_errors_and_stale_are_distinguished(self):
        self.assertEqual(classify_tool_result('{"error":"denied","http_status":403}'), "error")
        self.assertEqual(classify_tool_result('{"status":"unavailable"}'), "error")
        self.assertEqual(classify_tool_result('{"status":"stale"}'), "stale")
        # CI 失败不是工具执行失败，工具依然可能正确完成查询。
        self.assertEqual(classify_tool_result('{"ci_assessment":"failed"}'), "completed")

    def test_cache_and_budget_skip_do_not_count_as_actual_executions(self):
        result = finish_immediate(run_tool({
            "messages": [], "tool_calls": [tool_call(i) for i in range(MAX_TOOL_CALLS + 1)],
        }))
        result["finish_reason"] = "tool_budget_exhausted"
        summary = build_execution_summary(result, uuid4(), 10)
        self.assertEqual(summary.tool_calls_used, MAX_TOOL_CALLS)
        self.assertEqual(summary.tools_executed, 1)
        self.assertTrue(summary.tools[1].cached)
        self.assertEqual(summary.tools[-1].status, "budget_exhausted")

    def test_tool_trace_does_not_expose_arguments_or_result_content(self):
        call = tool_call(1)
        call["function"] = {
            "name": "get_github_pr", "arguments": json.dumps({"pr_url": "private-marker"}),
        }

        async def execute(call):
            return '{"title":"secret-result-marker"}'

        with patch("app.chat_graph._execute_call", new=execute):
            result = finish_immediate(run_tool({"messages": [], "tool_calls": [call]}))
        trace = json.dumps(result["tool_events"])
        self.assertNotIn("private-marker", trace)
        self.assertNotIn("secret-result-marker", trace)
        self.assertEqual(result["tool_events"][0]["tool_name"], "get_github_pr")

    def test_model_calls_accumulate_and_final_node_records_stop_reason(self):
        async def model(messages, **kwargs):
            return {"content": "Answer"}

        with patch("app.chat_graph.request_completion", new=model):
            direct = finish_immediate(call_model({"message": "Hi", "history": []}))
            final = finish_immediate(answer_with_evidence({"messages": [], "model_calls": 3}))
        self.assertEqual(direct["model_calls"], 1)
        self.assertEqual(direct["finish_reason"], "completed")
        self.assertEqual(final["model_calls"], 4)
        self.assertEqual(final["finish_reason"], "tool_budget_exhausted")

    def test_chat_endpoint_returns_execution_for_direct_answer(self):
        async def invoke(state):
            return {"reply": "Hello", "model_calls": 1, "finish_reason": "completed"}

        saved = []

        async def save_in_threadpool(function, summary):
            # 单测隔离磁盘和线程池；真实 SQLite 持久化由仓库测试覆盖。
            saved.append(summary)

        with patch("app.main.chat_graph.ainvoke", new=invoke), patch(
            "app.main.run_in_threadpool", new=save_in_threadpool
        ):
            first = finish_immediate(chat(ChatRequest(message="Hi")))
            second = finish_immediate(chat(ChatRequest(message="Hi")))
        self.assertEqual(first.reply, "Hello")
        self.assertEqual(first.execution.model_calls, 1)
        self.assertEqual(first.execution.tools, [])
        self.assertEqual(first.execution.tools_executed, 0)
        self.assertNotEqual(first.execution.trace_id, second.execution.trace_id)
        self.assertEqual(saved, [first.execution, second.execution])

    def test_openapi_exposes_execution_schema(self):
        schema = app.openapi()["components"]["schemas"]
        self.assertIn("execution", schema["ChatResponse"]["properties"])
