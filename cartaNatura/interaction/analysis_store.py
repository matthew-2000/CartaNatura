"""Analysis persistence for interaction flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, MutableMapping, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class StoredAnalysis:
    analysis_id: str
    source: str
    created_at: str
    summary: dict[str, Any]
    requested_municipalities: tuple[str, ...] = ()
    intersected_municipalities: tuple[str, ...] = ()
    selection_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "source": self.source,
            "created_at": self.created_at,
            "summary": self.summary,
            "requested_municipalities": list(self.requested_municipalities),
            "intersected_municipalities": list(self.intersected_municipalities),
            "selection_payload": self.selection_payload,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoredAnalysis:
        return cls(
            analysis_id=str(data.get("analysis_id") or ""),
            source=str(data.get("source") or "unknown"),
            created_at=str(data.get("created_at") or ""),
            summary=data.get("summary") or {},
            requested_municipalities=tuple(
                str(item) for item in data.get("requested_municipalities", []) if str(item).strip()
            ),
            intersected_municipalities=tuple(
                str(item) for item in data.get("intersected_municipalities", []) if str(item).strip()
            ),
            selection_payload=data.get("selection_payload"),
            metadata=data.get("metadata") or {},
        )


class AnalysisStore(Protocol):
    def save(self, analysis: StoredAnalysis) -> StoredAnalysis:
        """Persist analysis entry."""

    def get_last(self) -> StoredAnalysis | None:
        """Return most recent analysis."""

    def get(self, analysis_id: str) -> StoredAnalysis | None:
        """Return analysis by id."""

    def list_recent(self, limit: int = 10) -> list[StoredAnalysis]:
        """Return recent analyses ordered from newest to oldest."""

    def clear(self) -> None:
        """Remove all stored analyses."""


def create_analysis_id() -> str:
    return f"analysis_{uuid4().hex[:12]}"


def create_stored_analysis(
    *,
    source: str,
    summary: dict[str, Any],
    requested_municipalities: list[str] | tuple[str, ...] = (),
    intersected_municipalities: list[str] | tuple[str, ...] = (),
    selection_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> StoredAnalysis:
    return StoredAnalysis(
        analysis_id=create_analysis_id(),
        source=source,
        created_at=datetime.now(UTC).isoformat(),
        summary=summary,
        requested_municipalities=tuple(str(item) for item in requested_municipalities if str(item).strip()),
        intersected_municipalities=tuple(
            str(item) for item in intersected_municipalities if str(item).strip()
        ),
        selection_payload=selection_payload,
        metadata=metadata or {},
    )


class NullAnalysisStore:
    def save(self, analysis: StoredAnalysis) -> StoredAnalysis:
        return analysis

    def get_last(self) -> StoredAnalysis | None:
        return None

    def get(self, analysis_id: str) -> StoredAnalysis | None:
        del analysis_id
        return None

    def list_recent(self, limit: int = 10) -> list[StoredAnalysis]:
        del limit
        return []

    def clear(self) -> None:
        return None


class InMemoryAnalysisStore:
    def __init__(self):
        self._items: list[StoredAnalysis] = []

    def save(self, analysis: StoredAnalysis) -> StoredAnalysis:
        self._items = [item for item in self._items if item.analysis_id != analysis.analysis_id]
        self._items.append(analysis)
        return analysis

    def get_last(self) -> StoredAnalysis | None:
        return self._items[-1] if self._items else None

    def get(self, analysis_id: str) -> StoredAnalysis | None:
        for item in reversed(self._items):
            if item.analysis_id == analysis_id:
                return item
        return None

    def list_recent(self, limit: int = 10) -> list[StoredAnalysis]:
        return list(reversed(self._items[-limit:]))

    def clear(self) -> None:
        self._items.clear()


class DjangoSessionAnalysisStore:
    def __init__(self, session: MutableMapping[str, object], key: str = "interaction_analyses"):
        self._session = session
        self._key = key

    def _load_items(self) -> list[StoredAnalysis]:
        raw_items = self._session.get(self._key)
        if not isinstance(raw_items, list):
            return []
        return [
            StoredAnalysis.from_dict(item)
            for item in raw_items
            if isinstance(item, dict)
        ]

    def _save_items(self, items: list[StoredAnalysis]) -> None:
        self._session[self._key] = [item.to_dict() for item in items]
        if hasattr(self._session, "modified"):
            self._session.modified = True

    def save(self, analysis: StoredAnalysis) -> StoredAnalysis:
        items = [item for item in self._load_items() if item.analysis_id != analysis.analysis_id]
        items.append(analysis)
        self._save_items(items)
        return analysis

    def get_last(self) -> StoredAnalysis | None:
        items = self._load_items()
        return items[-1] if items else None

    def get(self, analysis_id: str) -> StoredAnalysis | None:
        for item in reversed(self._load_items()):
            if item.analysis_id == analysis_id:
                return item
        return None

    def list_recent(self, limit: int = 10) -> list[StoredAnalysis]:
        return list(reversed(self._load_items()[-limit:]))

    def clear(self) -> None:
        self._session.pop(self._key, None)
        if hasattr(self._session, "modified"):
            self._session.modified = True
