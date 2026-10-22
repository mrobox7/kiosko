"""Chats held in memory, one lock each. A restart forgets them: this is a prototype store."""

import secrets
import threading
import time
from dataclasses import dataclass, field

from app.session.session import Session


@dataclass
class Chat:
    """A live chat. `lock` is held while a reply is being written: `Session` handles one
    message at a time. `last_active` is the last time the customer did something."""

    session: Session
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_active: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        """The customer just did something: restart the idle clock."""
        self.last_active = time.monotonic()


class SessionStore:
    """Maps a session id, the only credential a client holds, to its chat."""

    def __init__(self) -> None:
        self._chats: dict[str, Chat] = {}
        self._mutating = threading.Lock()  # requests and the idle sweep run on different threads

    def add(self, session: Session) -> str:
        """Hold a new chat and return its id."""
        session_id = secrets.token_urlsafe(16)
        with self._mutating:
            self._chats[session_id] = Chat(session)
        return session_id

    def get(self, session_id: str) -> Chat:
        """The chat, or KeyError."""
        return self._chats[session_id]

    def remove(self, session_id: str) -> None:
        """Forget a chat; unknown ids are ignored."""
        with self._mutating:
            self._chats.pop(session_id, None)

    def sweep(self, idle_s: float, now: float) -> list[str]:
        """End the chats nobody has touched for `idle_s` seconds: cancel their draft orders and
        forget them. A chat that is writing a reply is left for the next sweep. Returns the ids
        that were ended."""
        with self._mutating:
            idle = [i for i, c in self._chats.items() if now - c.last_active >= idle_s]
        ended: list[str] = []
        for session_id in idle:
            chat = self._chats.get(session_id)
            if chat is None or not chat.lock.acquire(blocking=False):
                continue
            try:
                chat.session.abandon()
            finally:
                chat.lock.release()
            self.remove(session_id)
            ended.append(session_id)
        return ended
