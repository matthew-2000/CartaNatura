"""Analysis persistence for interaction flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, MutableMapping, Protocol
from uuid import uuid4

from django.conf import settings


@dataclass(frozen=True)
class StoredAnalysis:
    analysis_id: str
    source: str
    created_at: str
    summary: dict[str, Any]
    label: str = ""
    selection_kind: str = "unknown"
    has_drawn_geometry: bool = False
    requested_municipalities: tuple[str, ...] = ()
    intersected_municipalities: tuple[str, ...] = ()
    selection_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "source": self.source,
            "created_at": self.created_at,
            "label": self.label,
            "selection_kind": self.selection_kind,
            "has_drawn_geometry": self.has_drawn_geometry,
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
            label=str(data.get("label") or ""),
            selection_kind=str(data.get("selection_kind") or "unknown"),
            has_drawn_geometry=bool(data.get("has_drawn_geometry")),
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


def analysis_history_limit() -> int:
    configured = getattr(settings, "ANALYSIS_HISTORY_LIMIT", 10)
    try:
        return max(1, int(configured))
    except (TypeError, ValueError):
        return 10


def create_analysis_id() -> str:
    return f"analysis_{uuid4().hex[:12]}"


def derive_selection_kind(selection_payload: dict[str, Any] | None) -> str:
    if not isinstance(selection_payload, dict):
        return "unknown"

    raw_areas = selection_payload.get("areas")
    if not isinstance(raw_areas, list):
        return "unknown"

    kinds = {
        str(area.get("kind"))
        for area in raw_areas
        if isinstance(area, dict) and str(area.get("kind") or "").strip()
    }
    if kinds == {"municipalities"}:
        return "municipalities"
    if kinds == {"drawn"}:
        return "drawn"
    if "municipalities" in kinds and "drawn" in kinds:
        return "mixed"
    return "unknown"


def has_drawn_geometry(selection_payload: dict[str, Any] | None) -> bool:
    if not isinstance(selection_payload, dict):
        return False
    raw_areas = selection_payload.get("areas")
    if not isinstance(raw_areas, list):
        return False
    return any(isinstance(area, dict) and area.get("kind") == "drawn" for area in raw_areas)


def build_analysis_label(
    *,
    selection_kind: str,
    requested_municipalities: list[str] | tuple[str, ...] = (),
    intersected_municipalities: list[str] | tuple[str, ...] = (),
    created_at: str,
) -> str:
    municipalities = [
        str(item)
        for item in (requested_municipalities or intersected_municipalities)
        if str(item).strip()
    ]
    if municipalities:
        names = ", ".join(municipalities[:2])
        suffix = f" +{len(municipalities) - 2}" if len(municipalities) > 2 else ""
        return f"Analisi {names}{suffix}"

    if selection_kind == "drawn":
        return "Analisi area disegnata"
    if selection_kind == "mixed":
        return "Analisi mista"
    if selection_kind == "municipalities":
        return "Analisi comuni"
    return f"Analisi {created_at[:10]}" if created_at else "Analisi"


def create_stored_analysis(
    *,
    source: str,
    summary: dict[str, Any],
    requested_municipalities: list[str] | tuple[str, ...] = (),
    intersected_municipalities: list[str] | tuple[str, ...] = (),
    selection_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> StoredAnalysis:
    created_at = datetime.now(UTC).isoformat()
    selection_kind = derive_selection_kind(selection_payload)
    safe_metadata = {
        key: value
        for key, value in (metadata or {}).items()
        if key in {"channel", "source", "operation"}
    }
    return StoredAnalysis(
        analysis_id=create_analysis_id(),
        source=source,
        created_at=created_at,
        label=build_analysis_label(
            selection_kind=selection_kind,
            requested_municipalities=requested_municipalities,
            intersected_municipalities=intersected_municipalities,
            created_at=created_at,
        ),
        selection_kind=selection_kind,
        has_drawn_geometry=has_drawn_geometry(selection_payload),
        summary=summary,
        requested_municipalities=tuple(str(item) for item in requested_municipalities if str(item).strip()),
        intersected_municipalities=tuple(
            str(item) for item in intersected_municipalities if str(item).strip()
        ),
        selection_payload=selection_payload,
        metadata=safe_metadata,
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
    def __init__(self, max_items: int | None = None):
        self._items: list[StoredAnalysis] = []
        self._max_items = max_items

    def save(self, analysis: StoredAnalysis) -> StoredAnalysis:
        self._items = [item for item in self._items if item.analysis_id != analysis.analysis_id]
        self._items.append(analysis)
        if self._max_items is not None:
            self._items = self._items[-max(1, self._max_items):]
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
    def __init__(
        self,
        session: MutableMapping[str, object],
        key: str = "interaction_analyses",
        max_items: int | None = None,
    ):
        self._session = session
        self._key = key
        self._max_items = max_items

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
        items = items[-(self._max_items or analysis_history_limit()):]
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

    def rename(self, analysis_id: str, label: str) -> StoredAnalysis | None:
        clean_label = str(label or "").strip()[:120]
        if not clean_label:
            raise ValueError("Etichetta analisi mancante.")

        items = self._load_items()
        renamed: StoredAnalysis | None = None
        next_items: list[StoredAnalysis] = []
        for item in items:
            if item.analysis_id == analysis_id:
                renamed = StoredAnalysis(
                    analysis_id=item.analysis_id,
                    source=item.source,
                    created_at=item.created_at,
                    label=clean_label,
                    selection_kind=item.selection_kind,
                    has_drawn_geometry=item.has_drawn_geometry,
                    summary=item.summary,
                    requested_municipalities=item.requested_municipalities,
                    intersected_municipalities=item.intersected_municipalities,
                    selection_payload=item.selection_payload,
                    metadata=item.metadata,
                )
                next_items.append(renamed)
            else:
                next_items.append(item)
        if renamed is not None:
            self._save_items(next_items)
        return renamed

    def delete(self, analysis_id: str) -> bool:
        items = self._load_items()
        next_items = [item for item in items if item.analysis_id != analysis_id]
        if len(next_items) == len(items):
            return False
        self._save_items(next_items)
        return True
