"""Request payload validation and parsing."""

from __future__ import annotations

from typing import Any

from cartaNatura.schemas import SelectionArea, SelectionRequest


SUPPORTED_AREA_KINDS = {"municipalities", "drawn"}


def parse_selection_payload(payload: dict[str, Any]) -> SelectionRequest:
    """Validate client payload and return typed request object."""

    raw_areas = payload.get("areas")
    if not isinstance(raw_areas, list) or not raw_areas:
        raise ValueError("Seleziona almeno un'area da analizzare.")

    areas: list[SelectionArea] = []
    seen_kinds: set[str] = set()

    for raw_area in raw_areas:
        if not isinstance(raw_area, dict):
            raise ValueError("Una delle aree selezionate non è valida.")

        kind = raw_area.get("kind")
        geojson = raw_area.get("geojson")

        if kind not in SUPPORTED_AREA_KINDS:
            raise ValueError(f"Tipo di area non supportato: {kind!r}.")

        if kind in seen_kinds:
            raise ValueError(f"Area duplicata: {kind!r}.")

        if not isinstance(geojson, dict) or geojson.get("type") != "FeatureCollection":
            raise ValueError(f"L'area {kind!r} non contiene una geometria valida.")

        features = geojson.get("features")
        if not isinstance(features, list) or not features:
            raise ValueError(f"L'area {kind!r} non contiene geometrie.")

        areas.append(SelectionArea(kind=kind, geojson=geojson))
        seen_kinds.add(kind)

    return SelectionRequest(areas=tuple(areas))
