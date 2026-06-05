"""Session context persistence abstractions."""

from __future__ import annotations

from typing import Protocol

from .models import SessionContext


class SessionStore(Protocol):
    def load(self, session_id: str) -> SessionContext:
        """Load existing session context."""

    def save(self, session_id: str, context: SessionContext) -> None:
        """Persist session context."""

    def clear(self, session_id: str) -> None:
        """Delete session context."""


class NullSessionStore:
    def load(self, session_id: str) -> SessionContext:
        return SessionContext()

    def save(self, session_id: str, context: SessionContext) -> None:
        return None

    def clear(self, session_id: str) -> None:
        return None


class InMemorySessionStore:
    def __init__(self):
        self._contexts: dict[str, SessionContext] = {}

    def load(self, session_id: str) -> SessionContext:
        return self._contexts.get(session_id, SessionContext())

    def save(self, session_id: str, context: SessionContext) -> None:
        self._contexts[session_id] = context

    def clear(self, session_id: str) -> None:
        self._contexts.pop(session_id, None)
