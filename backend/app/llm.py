import os
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


class ModelConfigError(Exception):
    """The server is missing model configuration."""


class ModelResponseError(Exception):
    """The provider returned no usable reply."""


class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


async def request_completion(
    messages: list[dict], tools: list[dict] | None = None, *, tool_choice: Literal["none"] | None = None
) -> dict:
    # 接收图节点组装好的消息。第一轮可附带工具说明，第二轮提供工具结果。
    base_url = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    if not all((base_url, api_key, model)):
        raise ModelConfigError("Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL in backend/.env, then restart the server.")

    payload = {"model": model, "messages": messages}
    if tools:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    if urlsplit(base_url).hostname == "api.deepseek.com":
        # 这一步在 DeepSeek 官方接口上使用非思考模式来练习工具调用。
        payload["thinking"] = {"type": "disabled"}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        response.raise_for_status()

    try:
        # 保留模型消息对象，让图能读取 content 或 tool_calls。
        result = response.json()["choices"][0]["message"]
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise ModelResponseError("The model provider returned an unexpected response.") from exc
    if not isinstance(result, dict):
        raise ModelResponseError("The model provider returned an invalid message.")
    return result


def read_reply(message: dict) -> str:
    # 只有需要最终文本回复时才检查 content。工具请求本身可以没有正文。
    reply = message.get("content")
    if not isinstance(reply, str) or not reply.strip():
        raise ModelResponseError("The model provider returned an empty reply.")
    return reply
