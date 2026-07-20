"""UI context normalization for interaction requests."""

from __future__ import annotations

from typing import Any

from .models import InteractionContext


def build_interaction_context(context_payload: dict[str, Any] | None) -> InteractionContext:
    payload = context_payload if isinstance(context_payload, dict) else {}
    raw_selected = payload.get("selectedMunicipalities", [])
    selected = tuple(
        str(name)
        for name in raw_selected
        if str(name).strip()
    ) if isinstance(raw_selected, list) else ()
    raw_extent = payload.get("mapExtent")
    map_extent = raw_extent if isinstance(raw_extent, dict) else None
    raw_selection_payload = payload.get("selectionPayload")
    selection_payload = (
        raw_selection_payload
        if (
            isinstance(raw_selection_payload, dict)
            and isinstance(raw_selection_payload.get("areas"), list)
            and len(raw_selection_payload.get("areas", [])) > 0
        )
        else None
    )
    metadata = {
        "selectionSource": str(payload.get("selectionSource") or "").strip() or None,
    }
    displayed_analysis_id = str(payload.get("displayedAnalysisId") or "").strip() or None

    return InteractionContext(
        selected_municipalities=selected,
        current_map_extent=map_extent,
        current_selection_payload=selection_payload,
        displayed_analysis_id=displayed_analysis_id,
        metadata={key: value for key, value in metadata.items() if value is not None},
    )
