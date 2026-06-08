"""Contracts for deterministic tool execution."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ToolName(StrEnum):
    ANALYZE_MUNICIPALITIES = "analyze_municipalities"
    ANALYZE_SELECTION = "analyze_selection"
    COMPARE_ANALYSES = "compare_analyses"
    GET_LAST_ANALYSIS = "get_last_analysis"
    RESET_ANALYSIS_CONTEXT = "reset_analysis_context"
    GET_METHODOLOGY = "get_methodology"


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
