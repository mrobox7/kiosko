"""Chats held in memory, one lock each. A restart forgets them: this is a prototype store."""

import secrets
import threading
from dataclasses import dataclass, field

from app.session.session import Session


@dataclass
class Chat:
    """A live chat. `lock` is held while a reply is being written: `Session` handles one
    message at a time."""

    session: Session
    lock: threading.Lock = field(default_factory=threading.Lock)


class SessionStore:
    """Maps a session id, the only credential a client holds, to its chat."""

    def __init__(self) -> None:
        self._chats: dict[str, Chat] = {}

    def add(self, session: Session) -> str:
        """Hold a new chat and return its id."""
        session_id = secrets.token_urlsafe(16)
        self._chats[session_id] = Chat(session)
        return session_id

    def get(self, session_id: str) -> Chat:
        """The chat, or KeyError."""
        return self._chats[session_id]

    def remove(self, session_id: str) -> None:
        """Forget a chat; unknown ids are ignored."""
        self._chats.pop(session_id, None)
