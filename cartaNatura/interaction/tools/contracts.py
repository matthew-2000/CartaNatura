"""Contracts for deterministic tool execution."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ToolName(StrEnum):
    ANALYZE_MUNICIPALITIES = "analyze_municipalities"
    ANALYZE_SELECTION = "analyze_selection"
    CALCULATE_ECONOMIC_VALUE = "calculate_economic_value"
    COMPARE_ECONOMIC_SCENARIOS = "compare_economic_scenarios"
    COMPARE_ANALYSES = "compare_analyses"
    COMPARE_RECENT_ANALYSES = "compare_recent_analyses"
    COMPARE_SAVED_ANALYSES = "compare_saved_analyses"
    GET_LAST_ANALYSIS = "get_last_analysis"
    LIST_RECENT_ANALYSES = "list_recent_analyses"
    RESET_ANALYSIS_CONTEXT = "reset_analysis_context"
    PREPARE_REPORT = "prepare_report"
    GET_METHODOLOGY = "get_methodology"
    SEARCH_MUNICIPALITIES = "search_municipalities"


def require_summary(summary: dict[str, Any]) -> dict[str, Any]:
    required_keys = {
        "items",
        "totalCo2",
        "totalHectares",
        "hasSupportedVegetation",
        "topCategory",
    }
    missing = sorted(required_keys.difference(summary.keys()))
    if missing:
        raise ValueError(f"Tool summary missing keys: {', '.join(missing)}.")
    return summary
