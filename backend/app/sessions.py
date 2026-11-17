from asyncio import Lock
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from .llm import ChatMessage

MAX_SESSIONS = 100
MAX_HISTORY_MESSAGES = 10


@dataclass
class ChatSession:
    history: list[ChatMessage] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)


sessions: dict[UUID, ChatSession] = {}


def create_session() -> UUID | None:
    if len(sessions) >= MAX_SESSIONS:
        return None
    session_id = uuid4()
    sessions[session_id] = ChatSession()
    return session_id
