from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, constr

from .chat_graph import chat_graph
from .llm import ModelConfigError, ModelResponseError
from .sessions import MAX_HISTORY_MESSAGES, create_session, sessions

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
    return ChatResponse(reply=reply)


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
