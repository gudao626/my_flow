from time import perf_counter
from typing import Annotated, Literal
import sqlite3
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, constr
from starlette.concurrency import run_in_threadpool

from .chat_graph import chat_graph
from .llm import ModelConfigError, ModelResponseError
from .sessions import MAX_HISTORY_MESSAGES, create_session, sessions
from .execution import ExecutionPage, ExecutionSummary, build_execution_summary
from .execution_store import execution_store

class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


app = FastAPI(title="My Git Flow API")


class ModelInfo(BaseModel):
    id: str
    name: str
    model: str
    display_name: str
    description: str
    supports_thinking: bool = False


class ModelList(BaseModel):
    models: list[ModelInfo]


class ChatRequest(BaseModel):
    message: constr(strip_whitespace=True, min_length=1, max_length=8000)
    session_id: UUID | None = None


class ChatResponse(BaseModel):
    reply: str
    execution: ExecutionSummary


class SessionResponse(BaseModel):
    session_id: UUID


@app.post("/api/sessions", response_model=SessionResponse, status_code=201)
async def new_session() -> SessionResponse:
    session_id = create_session()
    if session_id is None:
        raise HTTPException(status_code=503, detail="Local session limit reached.")
    return SessionResponse(session_id=session_id)


@app.post("/api/chat", response_model=ChatResponse, response_class=UTF8JSONResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    # 每次请求都有独立 ID；耗时包括模型、工具及会话锁等待，不是 token 计费数据。
    trace_id = uuid4()
    started = perf_counter()
    try:
        if request.session_id is None:
            result = await chat_graph.ainvoke({"message": request.message, "history": []})
            reply = result["reply"]
        else:
            session = sessions.get(request.session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Chat session not found.")
            async with session.lock:
                result = await chat_graph.ainvoke({"message": request.message, "history": session.history.copy()})
                reply = result["reply"]
                session.history.extend([
                    {"role": "user", "content": request.message},
                    {"role": "assistant", "content": reply},
                ])
                del session.history[:-MAX_HISTORY_MESSAGES]
    except ModelConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="The model provider timed out.") from None
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise HTTPException(status_code=502, detail=f"The model provider returned HTTP {status}.") from None
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Model provider connection failed ({type(exc).__name__}).") from None
    except httpx.InvalidURL:
        raise HTTPException(status_code=502, detail="The model provider URL is invalid.") from None
    except ModelResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    response = ChatResponse(
        reply=reply,
        execution=build_execution_summary(result, trace_id, round((perf_counter() - started) * 1000, 3)),
    )
    try:
        # SQLite 是同步接口，放到线程池，避免磁盘操作阻塞异步事件循环。
        await run_in_threadpool(execution_store.save, response.execution)
    except (sqlite3.Error, OSError):
        raise HTTPException(status_code=503, detail="Execution storage unavailable.") from None
    return response


@app.get("/api/executions", response_model=ExecutionPage)
def list_executions(
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    finish_reason: Literal["completed", "tool_budget_exhausted"] | None = None,
) -> ExecutionPage:
    # HTTP 层先校验参数；同步路由在线程池中访问数据库。
    try:
        return execution_store.list_page(limit, offset, finish_reason)
    except (sqlite3.Error, OSError):
        raise HTTPException(status_code=503, detail="Execution storage unavailable.") from None


@app.get("/api/executions/{trace_id}", response_model=ExecutionSummary)
def get_execution(trace_id: UUID) -> ExecutionSummary:
    # 普通 def 路由由 FastAPI 在线程池执行，适合这里的同步数据库读取。
    try:
        summary = execution_store.get(trace_id)
    except (sqlite3.Error, OSError):
        raise HTTPException(status_code=503, detail="Execution storage unavailable.") from None
    if summary is None:
        raise HTTPException(status_code=404, detail="Execution not found.")
    return summary


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/api/models", response_model=ModelList)
def list_models() -> ModelList:
    return ModelList(
        models=[
            ModelInfo(
                id="demo",
                name="demo",
                model="demo",
                display_name="本地演示模型",
                description="用于验证模型列表接口，尚未接入推理。",
            ),
            ModelInfo(
                id="demo1",
                name="demo1",
                model="demo1",
                display_name="本地演示模型1",
                description="用于验证模型列表接口，尚未接入推理。1",
            )
        ]
    )
