"""Session context persistence abstractions."""

from __future__ import annotations

from typing import MutableMapping
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


class DjangoSessionStore:
    def __init__(self, session: MutableMapping[str, object], key: str = "interaction_context"):
        self._session = session
        self._key = key

    def load(self, session_id: str) -> SessionContext:
        del session_id
        return SessionContext.from_dict(self._session.get(self._key))

    def save(self, session_id: str, context: SessionContext) -> None:
        del session_id
        self._session[self._key] = context.to_dict()
        if hasattr(self._session, "modified"):
            self._session.modified = True

    def clear(self, session_id: str) -> None:
        del session_id
        self._session.pop(self._key, None)
        if hasattr(self._session, "modified"):
            self._session.modified = True
