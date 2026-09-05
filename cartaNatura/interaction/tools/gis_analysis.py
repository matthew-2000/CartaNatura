"""Deterministic GIS tools exposed to interaction layer."""

from __future__ import annotations

import json
from typing import Any

from cartaNatura.services.analysis_summary import summarize_clipped_features
from cartaNatura.services.gis_clip import clip_selection
from cartaNatura.services.municipality_text import build_municipality_selection_payload_dict
from cartaNatura.services.municipality_text import resolve_municipality_names
from cartaNatura.services.payloads import parse_selection_payload

from .contracts import require_summary


def _build_analysis_result(
    *,
    source: str,
    selection_payload: dict[str, Any],
    requested_municipalities: list[str] | None = None,
) -> dict[str, Any]:
    selection = parse_selection_payload(selection_payload)
    result = clip_selection(selection)
    summary = require_summary(summarize_clipped_features(result.clipped))

    payload = {
        "source": source,
        "selectionPayload": selection_payload,
        "clipped": json.loads(result.clipped.to_json()),
        "intersectedMunicipalities": result.intersected_municipalities,
        "summary": summary,
    }
    if requested_municipalities is not None:
        payload["requestedMunicipalities"] = requested_municipalities
    return payload


def analyze_municipalities(*, municipality_names: list[str]) -> dict[str, Any]:
    requested_municipalities = resolve_municipality_names(municipality_names)

    selection_payload = build_municipality_selection_payload_dict(requested_municipalities)
    return _build_analysis_result(
        source="municipalities",
        selection_payload=selection_payload,
        requested_municipalities=requested_municipalities,
    )


def analyze_selection(*, selection_payload: dict[str, Any]) -> dict[str, Any]:
    if not selection_payload:
        raise ValueError("Nessuna selezione valida da analizzare.")

    return _build_analysis_result(
        source="selection",
        selection_payload=selection_payload,
    )
