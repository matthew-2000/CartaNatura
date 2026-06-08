"""Tools over stored analysis history."""

from __future__ import annotations

from typing import Any

from cartaNatura.interaction.analysis_store import AnalysisStore, StoredAnalysis


def _serialize_analysis(analysis: StoredAnalysis) -> dict[str, Any]:
    return {
        "analysisId": analysis.analysis_id,
        "source": analysis.source,
        "createdAt": analysis.created_at,
        "requestedMunicipalities": list(analysis.requested_municipalities),
        "intersectedMunicipalities": list(analysis.intersected_municipalities),
        "summary": analysis.summary,
        "metadata": analysis.metadata,
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

    left_summary = left.summary
    right_summary = right.summary
    return {
        "left": _serialize_analysis(left),
        "right": _serialize_analysis(right),
        "delta": {
            "totalCo2": float(right_summary.get("totalCo2", 0)) - float(left_summary.get("totalCo2", 0)),
            "totalHectares": float(right_summary.get("totalHectares", 0))
            - float(left_summary.get("totalHectares", 0)),
        },
    }


def reset_analysis_context(*, analysis_store: AnalysisStore) -> dict[str, Any]:
    analysis_store.clear()
    return {"cleared": True}


def get_recent_analyses(*, analysis_store: AnalysisStore, limit: int = 2) -> dict[str, Any]:
    return {
        "items": [
            _serialize_analysis(item)
            for item in analysis_store.list_recent(limit=limit)
        ]
    }
