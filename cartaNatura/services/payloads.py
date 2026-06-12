"""Request payload validation and parsing."""

from __future__ import annotations

from typing import Any

from shapely.geometry import shape
from shapely.errors import ShapelyError

from cartaNatura.schemas import SelectionArea, SelectionRequest


SUPPORTED_AREA_KINDS = {"municipalities", "drawn"}
EXPECTED_CRS_BY_KIND = {
    "municipalities": "EPSG:32633",
    "drawn": "EPSG:4326",
}


def parse_selection_payload(payload: dict[str, Any]) -> SelectionRequest:
    """Validate client payload and return typed request object."""

    raw_areas = payload.get("areas")
    if not isinstance(raw_areas, list) or not raw_areas:
        raise ValueError("Seleziona almeno un'area da analizzare.")

    areas: list[SelectionArea] = []
    seen_kinds: set[str] = set()
    _validate_unique_area_kinds(raw_areas)

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

        _validate_declared_crs(kind=kind, geojson=geojson)
        _validate_feature_geometries(kind=kind, features=features)

        areas.append(SelectionArea(kind=kind, geojson=geojson))
        seen_kinds.add(kind)

    return SelectionRequest(areas=tuple(areas))


def _validate_declared_crs(*, kind: str, geojson: dict[str, Any]) -> None:
    raw_crs = geojson.get("crs")
    if raw_crs is None:
        return

    declared = ""
    if isinstance(raw_crs, dict):
        properties = raw_crs.get("properties")
        if isinstance(properties, dict):
            declared = _normalize_crs_name(str(properties.get("name") or ""))

    expected = EXPECTED_CRS_BY_KIND[kind]
    if declared != expected:
        raise ValueError(
            f"CRS non supportato per l'area {kind!r}: atteso {expected}, ricevuto {declared or 'sconosciuto'}."
        )


def _validate_unique_area_kinds(raw_areas: list[Any]) -> None:
    seen_kinds: set[str] = set()
    for raw_area in raw_areas:
        if not isinstance(raw_area, dict):
            continue
        kind = raw_area.get("kind")
        if kind in seen_kinds:
            raise ValueError(f"Area duplicata: {kind!r}.")
        if kind in SUPPORTED_AREA_KINDS:
            seen_kinds.add(kind)


def _normalize_crs_name(value: str) -> str:
    normalized = value.strip().upper()
    if normalized.startswith("URN:OGC:DEF:CRS:EPSG::"):
        return f"EPSG:{normalized.rsplit(':', 1)[-1]}"
    return normalized


def _validate_feature_geometries(*, kind: str, features: list[Any]) -> None:
    for feature in features:
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(geometry, dict):
            raise ValueError(f"L'area {kind!r} contiene una geometria non valida.")

        try:
            parsed_geometry = shape(geometry)
        except (AttributeError, ShapelyError, TypeError, ValueError) as exc:
            raise ValueError(f"L'area {kind!r} contiene una geometria non valida.") from exc

        if parsed_geometry.is_empty or not parsed_geometry.is_valid:
            raise ValueError(f"L'area {kind!r} contiene una geometria non valida.")
