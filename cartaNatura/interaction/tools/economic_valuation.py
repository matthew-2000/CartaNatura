"""Deterministic economic valuation tools over saved GIS analyses."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from cartaNatura.domain.economics import (
    calculate_economic_value as calculate_value,
)
from cartaNatura.domain.economics import compare_economic_scenarios as compare_scenarios
from cartaNatura.interaction.analysis_store import AnalysisStore, StoredAnalysis


def _resolve_analysis(
    *,
    analysis_store: AnalysisStore,
    analysis_id: str | None = None,
) -> StoredAnalysis:
    normalized_id = str(analysis_id or "").strip()
    analysis = analysis_store.get(normalized_id) if normalized_id else analysis_store.get_last()
    if analysis is None:
        raise ValueError("Non esiste un'analisi disponibile per la valutazione economica.")
    return analysis


def _area_reference(analysis: StoredAnalysis) -> dict[str, Any]:
    municipalities = analysis.intersected_municipalities or analysis.requested_municipalities
    return {
        "selectionKind": analysis.selection_kind,
        "label": analysis.label,
        "municipalities": list(municipalities),
        "hasDrawnGeometry": analysis.has_drawn_geometry,
    }


def calculate_analysis_economic_value(
    *,
    analysis_store: AnalysisStore,
    scenario_key: str,
    analysis_id: str | None = None,
) -> dict[str, Any]:
    analysis = _resolve_analysis(analysis_store=analysis_store, analysis_id=analysis_id)
    result = calculate_value(
        total_co2=float(analysis.summary.get("totalCo2") or 0),
        scenario_key=scenario_key,
    )
    result.update(
        {
            "analysisId": analysis.analysis_id,
            "areaReference": _area_reference(analysis),
        }
    )
    analysis_store.save(replace(analysis, economic_valuation=result))
    return result


def compare_analysis_economic_scenarios(
    *,
    analysis_store: AnalysisStore,
    analysis_id: str | None = None,
) -> dict[str, Any]:
    analysis = _resolve_analysis(analysis_store=analysis_store, analysis_id=analysis_id)
    return {
        "analysisId": analysis.analysis_id,
        "areaReference": _area_reference(analysis),
        "totalCo2": float(analysis.summary.get("totalCo2") or 0),
        "scenarios": compare_scenarios(
            total_co2=float(analysis.summary.get("totalCo2") or 0),
        ),
    }


def prepare_analysis_report(
    *,
    analysis_store: AnalysisStore,
    analysis_id: str | None = None,
) -> dict[str, Any]:
    analysis = _resolve_analysis(analysis_store=analysis_store, analysis_id=analysis_id)
    return {
        "analysisId": analysis.analysis_id,
        "areaReference": _area_reference(analysis),
        "totalCo2": float(analysis.summary.get("totalCo2") or 0),
        "economicResult": analysis.economic_valuation,
        "action": "open_existing_report",
    }
