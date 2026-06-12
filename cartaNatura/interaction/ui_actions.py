"""Validated UI action contract for assistant responses."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class UiAction(StrEnum):
    SHOW_LAST_ANALYSIS = "show_last_analysis"
    OPEN_REPORT_PANEL = "open_report_panel"
    SHOW_LEGEND = "show_legend"
    FOCUS_MAP_RESULTS = "focus_map_results"


ALLOWED_UI_ACTIONS = tuple(action.value for action in UiAction)


def filter_ui_actions(raw_actions: Any) -> list[str]:
    if not isinstance(raw_actions, list):
        return []

    allowed = set(ALLOWED_UI_ACTIONS)
    return [
        action
        for action in (str(item).strip() for item in raw_actions)
        if action in allowed
    ]
