"""Deterministic category filters for the analysis currently shown on the map."""

from __future__ import annotations

import unicodedata
from typing import Any

from cartaNatura.domain.vegetation import VEGETATION_CATEGORIES
from cartaNatura.interaction.analysis_store import AnalysisStore


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).split())


def filter_analysis_categories(
    *,
    analysis_store: AnalysisStore,
    category_names: list[str],
    displayed_analysis_id: str | None = None,
    show_all: bool = False,
) -> dict[str, Any]:
    visible_id = str(displayed_analysis_id or "").strip()
    if not visible_id:
        raise ValueError("Non c'è un'analisi visibile sulla mappa da filtrare.")
    analysis = analysis_store.get(visible_id)
    if analysis is None:
        raise ValueError(
            "L'analisi visibile sulla mappa non è più disponibile nello storico. "
            "Esegui o riapri un'analisi e riprova."
        )

    items = analysis.summary.get("items")
    available = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    if not available:
        raise ValueError("L'analisi corrente non contiene categorie forestali filtrabili.")

    if show_all:
        resolved = available
    else:
        requested = [str(item).strip() for item in category_names if str(item).strip()]
        if not requested:
            raise ValueError("Indica almeno una categoria da mostrare sulla mappa.")

        resolved = []
        for selector in requested:
            normalized = _normalize(selector)
            matches = [
                item
                for item in available
                if normalized in {_normalize(item.get("key")), _normalize(item.get("label"))}
                or normalized in _normalize(item.get("label"))
            ]
            if not matches:
                selector_label = next(
                    (
                        category.label
                        for category in VEGETATION_CATEGORIES
                        if _normalize(category.key) == normalized
                    ),
                    selector,
                )
                labels = ", ".join(str(item.get("label") or item.get("key")) for item in available)
                raise ValueError(
                    f"La categoria '{selector_label}' non è presente nell'analisi corrente. "
                    f"Categorie disponibili: {labels}."
                )
            if len(matches) > 1:
                labels = ", ".join(str(item.get("label") or item.get("key")) for item in matches)
                raise ValueError(f"La categoria '{selector}' è ambigua: {labels}.")
            if matches[0] not in resolved:
                resolved.append(matches[0])

    return {
        "analysisId": analysis.analysis_id,
        "showAll": bool(show_all),
        "categories": [
            {"key": str(item.get("key") or ""), "label": str(item.get("label") or "")}
            for item in resolved
        ],
        "availableCategories": [
            {"key": str(item.get("key") or ""), "label": str(item.get("label") or "")}
            for item in available
        ],
    }
