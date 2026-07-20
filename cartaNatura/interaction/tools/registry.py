"""Tool registry for interaction runtime."""

from __future__ import annotations

from typing import Any, Callable

from cartaNatura.interaction.analysis_store import AnalysisStore

from .analysis_history import (
    compare_analyses,
    compare_recent_analyses,
    compare_saved_history_analyses,
    get_last_analysis,
    get_recent_analyses,
    reset_analysis_context,
)
from .contracts import ToolName
from .economic_valuation import (
    calculate_analysis_economic_value,
    compare_analysis_economic_scenarios,
    prepare_analysis_report,
)
from .gis_analysis import analyze_municipalities, analyze_selection
from .methodology import get_methodology
from .municipality_lookup import search_municipalities
from .map_filtering import filter_analysis_categories


ToolHandler = Callable[..., dict[str, Any]]


class ToolRegistry:
    def __init__(self):
        self._handlers: dict[ToolName, ToolHandler] = {}

    def register(self, tool_name: ToolName, handler: ToolHandler) -> None:
        self._handlers[tool_name] = handler

    def execute(self, tool_name: ToolName, **kwargs: Any) -> dict[str, Any]:
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise ValueError(f"No tool registered for {tool_name.value!r}.")
        return handler(**kwargs)


def build_default_tool_registry(analysis_store: AnalysisStore) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolName.ANALYZE_MUNICIPALITIES, analyze_municipalities)
    registry.register(ToolName.ANALYZE_SELECTION, analyze_selection)
    registry.register(
        ToolName.CALCULATE_ECONOMIC_VALUE,
        lambda **kwargs: calculate_analysis_economic_value(
            analysis_store=analysis_store,
            **kwargs,
        ),
    )
    registry.register(
        ToolName.COMPARE_ECONOMIC_SCENARIOS,
        lambda **kwargs: compare_analysis_economic_scenarios(
            analysis_store=analysis_store,
            **kwargs,
        ),
    )
    registry.register(
        ToolName.COMPARE_ANALYSES,
        lambda **kwargs: compare_analyses(analysis_store=analysis_store, **kwargs),
    )
    registry.register(
        ToolName.COMPARE_RECENT_ANALYSES,
        lambda **kwargs: compare_recent_analyses(analysis_store=analysis_store, **kwargs),
    )
    registry.register(
        ToolName.COMPARE_SAVED_ANALYSES,
        lambda **kwargs: compare_saved_history_analyses(analysis_store=analysis_store, **kwargs),
    )
    registry.register(
        ToolName.GET_LAST_ANALYSIS,
        lambda **kwargs: get_last_analysis(analysis_store=analysis_store, **kwargs),
    )
    registry.register(
        ToolName.LIST_RECENT_ANALYSES,
        lambda **kwargs: get_recent_analyses(analysis_store=analysis_store, **kwargs),
    )
    registry.register(
        ToolName.RESET_ANALYSIS_CONTEXT,
        lambda **kwargs: reset_analysis_context(analysis_store=analysis_store, **kwargs),
    )
    registry.register(
        ToolName.PREPARE_REPORT,
        lambda **kwargs: prepare_analysis_report(
            analysis_store=analysis_store,
            **kwargs,
        ),
    )
    registry.register(ToolName.GET_METHODOLOGY, get_methodology)
    registry.register(ToolName.SEARCH_MUNICIPALITIES, search_municipalities)
    registry.register(
        ToolName.FILTER_ANALYSIS_CATEGORIES,
        lambda **kwargs: filter_analysis_categories(analysis_store=analysis_store, **kwargs),
    )
    return registry
