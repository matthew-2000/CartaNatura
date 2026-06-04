"""App dataclasses for request and response payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import geopandas


@dataclass(frozen=True)
class SelectionArea:
    kind: str
    geojson: dict[str, Any]


@dataclass(frozen=True)
class SelectionRequest:
    areas: tuple[SelectionArea, ...]

    def get_area(self, kind: str) -> SelectionArea | None:
        return next((area for area in self.areas if area.kind == kind), None)


@dataclass(frozen=True)
class ClipResult:
    clipped: geopandas.GeoDataFrame
    intersected_municipalities: list[str]
