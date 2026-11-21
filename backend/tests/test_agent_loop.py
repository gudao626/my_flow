import json
import unittest
from unittest.mock import patch

from app.chat_graph import (
    MAX_TOOL_CALLS, MAX_TOOL_ROUNDS, answer_with_evidence,
    call_model, chat_graph, route_after_tools, route_reply, run_tool,
)
from app.llm import ModelResponseError


def finish_immediate(coroutine):
    # 本文件的异步外部调用全部用立即返回的假函数替换，不需要网络或密钥。
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    raise AssertionError("Unexpected suspension in mocked node.")


def tool_call(number, name="get_utc_time", arguments="{}"):
    return {"id": f"call-{number}", "type": "function", "function": {
        "name": name, "arguments": arguments,
    }}


class AgentLoopTests(unittest.TestCase):
    def test_followup_model_receives_previous_tool_evidence(self):
        responses = iter([
            {"tool_calls": [tool_call(1)]},
            {"tool_calls": [tool_call(2)]},
            {"content": "Finished using two rounds of evidence."},
        ])
        seen = []

        async def model(messages, **kwargs):
            seen.append(list(messages))
            return next(responses)

        state = {"message": "Query and then verify", "history": []}
        with patch("app.chat_graph.request_completion", new=model):
            for _ in range(2):
                state.update(finish_immediate(call_model(state)))
                self.assertEqual(route_reply(state), "run_tool")
                state.update(finish_immediate(run_tool(state)))
                self.assertEqual(route_after_tools(state), "call_model")
            state.update(finish_immediate(call_model(state)))

        self.assertEqual(route_reply(state), "end")
        self.assertEqual(state["tool_calls"], [])
        self.assertEqual(state["tool_calls_used"], 2)
        self.assertEqual(sum(m["role"] == "tool" for m in seen[-1]), 2)

    def test_excess_calls_get_results_but_are_not_executed(self):
        executed = []

        async def execute(call):
            executed.append(call["id"])
            return "evidence"

        calls = [tool_call(i, arguments=json.dumps({"i": i})) for i in range(MAX_TOOL_CALLS + 2)]
        with patch("app.chat_graph._execute_call", new=execute):
            result = finish_immediate(run_tool({"messages": [], "tool_calls": calls}))
        self.assertEqual(len(executed), MAX_TOOL_CALLS)
        tool_results = [m for m in result["messages"] if m["role"] == "tool"]
        self.assertEqual(len(tool_results), len(calls))
        self.assertIn("budget exhausted", tool_results[-1]["content"])
        self.assertEqual(route_after_tools(result), "answer_with_evidence")

    def test_round_budget_forces_final_answer(self):
        self.assertEqual(route_after_tools({"tool_rounds": MAX_TOOL_ROUNDS}), "answer_with_evidence")

    def test_budget_accumulates_across_rounds(self):
        result = finish_immediate(run_tool({
            "messages": [], "tool_calls": [tool_call(1)],
            "tool_calls_used": MAX_TOOL_CALLS - 1, "tool_rounds": 1,
        }))
        self.assertEqual(result["tool_calls_used"], MAX_TOOL_CALLS)
        self.assertEqual(result["tool_rounds"], 2)
        self.assertEqual(route_after_tools(result), "answer_with_evidence")

    def test_invalid_tool_arguments_become_recoverable_tool_result(self):
        result = finish_immediate(run_tool({
            "messages": [], "tool_calls": [tool_call(1, arguments="not-json")],
        }))
        self.assertIn("Invalid tool arguments", result["messages"][-1]["content"])
        self.assertEqual(result["tool_calls_used"], 1)

    def test_final_answer_disables_tools(self):
        async def model(messages, **kwargs):
            self.assertEqual(kwargs["tool_choice"], "none")
            self.assertIn("budget is exhausted", messages[-1]["content"])
            return {"content": "Evidence is incomplete."}

        with patch("app.chat_graph.request_completion", new=model):
            result = finish_immediate(answer_with_evidence({"messages": []}))
        self.assertEqual(result["reply"], "Evidence is incomplete.")

    def test_final_answer_rejects_provider_ignoring_tool_choice(self):
        async def model(messages, **kwargs):
            return {"tool_calls": [tool_call(1)], "content": "Unexpected tool request"}

        with patch("app.chat_graph.request_completion", new=model):
            with self.assertRaises(ModelResponseError):
                finish_immediate(answer_with_evidence({"messages": []}))

    def test_compiled_graph_has_followup_and_budget_exit_edges(self):
        edges = {(edge.source, edge.target) for edge in chat_graph.get_graph().edges}
        self.assertIn(("run_tool", "call_model"), edges)
        self.assertIn(("run_tool", "answer_with_evidence"), edges)
