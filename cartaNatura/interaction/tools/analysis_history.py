"""Tools over stored analysis history."""

from __future__ import annotations

from typing import Any

from cartaNatura.domain.economics import PRICE_OPTIONS
from cartaNatura.interaction.analysis_store import AnalysisStore, StoredAnalysis
from cartaNatura.services.analysis_compare import compare_saved_analyses


def _municipalities(analysis: StoredAnalysis) -> list[str]:
    values = analysis.intersected_municipalities or analysis.requested_municipalities
    return [str(item) for item in values if str(item).strip()]


def _compact_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "totalCo2": summary.get("totalCo2"),
        "totalHectares": summary.get("totalHectares"),
        "topCategory": summary.get("topCategory"),
        "hasSupportedVegetation": bool(summary.get("hasSupportedVegetation")),
        "items": summary.get("items", []) if isinstance(summary.get("items"), list) else [],
    }


def _history_label(analysis: StoredAnalysis) -> str:
    return analysis.label or analysis.analysis_id


def _serialize_analysis(analysis: StoredAnalysis) -> dict[str, Any]:
    return {
        "id": analysis.analysis_id,
        "analysisId": analysis.analysis_id,
        "source": analysis.source,
        "label": _history_label(analysis),
        "createdAt": analysis.created_at,
        "selectionKind": analysis.selection_kind,
        "municipalities": _municipalities(analysis),
        "hasDrawnGeometry": analysis.has_drawn_geometry,
        "requestedMunicipalities": list(analysis.requested_municipalities),
        "intersectedMunicipalities": list(analysis.intersected_municipalities),
        "summary": _compact_summary(analysis.summary),
        "economicEvaluation": analysis.economic_valuation,
        "metadata": analysis.metadata,
    }


def _serialize_compact_analysis(analysis: StoredAnalysis) -> dict[str, Any]:
    summary = _compact_summary(analysis.summary)
    return {
        "id": analysis.analysis_id,
        "analysisId": analysis.analysis_id,
        "label": _history_label(analysis),
        "createdAt": analysis.created_at,
        "selectionKind": analysis.selection_kind,
        "municipalities": _municipalities(analysis),
        "totalCo2": summary.get("totalCo2"),
        "totalHectares": summary.get("totalHectares"),
        "topCategory": summary.get("topCategory"),
        "hasSupportedVegetation": summary.get("hasSupportedVegetation"),
        "economicEvaluation": analysis.economic_valuation,
    }


def get_last_analysis(*, analysis_store: AnalysisStore) -> dict[str, Any]:
    analysis = analysis_store.get_last()
    if analysis is None:
        raise ValueError("Non ho ancora un'analisi recente disponibile.")
    return _serialize_analysis(analysis)


def compare_analyses(
    *,
    analysis_store: AnalysisStore,
    left_analysis_id: str,
    right_analysis_id: str,
) -> dict[str, Any]:
    left = analysis_store.get(left_analysis_id)
    right = analysis_store.get(right_analysis_id)
    if left is None or right is None:
        raise ValueError("Una delle analisi richieste non esiste.")

    return compare_saved_analyses([left, right], price_options=PRICE_OPTIONS)


def compare_recent_analyses(*, analysis_store: AnalysisStore, limit: int = 2) -> dict[str, Any]:
    try:
        normalized_limit = max(2, min(10, int(limit)))
    except (TypeError, ValueError):
        normalized_limit = 2
    recent = analysis_store.list_recent(limit=normalized_limit)
    if len(recent) < 2:
        raise ValueError("Servono almeno due analisi recenti per eseguire un confronto.")

    return compare_saved_analyses(recent, price_options=PRICE_OPTIONS)


def _normalize_selector(selector: str) -> str:
    return " ".join(str(selector or "").casefold().split())


def _matches_selector(analysis: StoredAnalysis, selector: str) -> bool:
    normalized = _normalize_selector(selector)
    if not normalized:
        return False
    if _normalize_selector(analysis.analysis_id) == normalized:
        return True
    if _normalize_selector(_history_label(analysis)) == normalized:
        return True
    return any(_normalize_selector(municipality) == normalized for municipality in _municipalities(analysis))


def _resolve_saved_analyses(
    *,
    analysis_store: AnalysisStore,
    selectors: list[str],
) -> list[StoredAnalysis]:
    selected: list[StoredAnalysis] = []
    all_recent = analysis_store.list_recent(limit=50)
    for selector in selectors:
        raw_selector = str(selector or "").strip()
        if not raw_selector:
            continue
        direct_match = analysis_store.get(raw_selector)
        matches = [direct_match] if direct_match is not None else [
            item for item in all_recent if _matches_selector(item, raw_selector)
        ]
        matches = [item for item in matches if item is not None]
        if not matches:
            raise ValueError(f"Analisi non trovata: {raw_selector}.")
        if len(matches) > 1:
            labels = ", ".join(_history_label(item) for item in matches[:5])
            raise ValueError(f"Riferimento ambiguo per '{raw_selector}': {labels}.")
        match = matches[0]
        if match.analysis_id not in {item.analysis_id for item in selected}:
            selected.append(match)
    return selected


def compare_saved_history_analyses(
    *,
    analysis_store: AnalysisStore,
    selectors: list[str],
) -> dict[str, Any]:
    records = _resolve_saved_analyses(analysis_store=analysis_store, selectors=selectors)
    if len(records) < 2:
        raise ValueError("Servono almeno due analisi salvate da confrontare.")
    return compare_saved_analyses(records, price_options=PRICE_OPTIONS)


def reset_analysis_context(*, analysis_store: AnalysisStore) -> dict[str, Any]:
    analysis_store.clear()
    return {"cleared": True}


def get_recent_analyses(*, analysis_store: AnalysisStore, limit: int = 10) -> dict[str, Any]:
    try:
        normalized_limit = max(1, min(50, int(limit)))
    except (TypeError, ValueError):
        normalized_limit = 10
    items = analysis_store.list_recent(limit=normalized_limit)
    return {
        "items": [_serialize_compact_analysis(item) for item in items],
        "count": len(items),
    }
