"""Core GIS analysis service."""

from __future__ import annotations

import pandas as pd
import geopandas

from cartaNatura.domain.municipalities import filter_municipalities_with_nature
from cartaNatura.schemas import ClipResult, SelectionArea, SelectionRequest
from cartaNatura.services.datasets import load_campania_boundaries, load_nature_shapes


SOURCE_EPSG_BY_KIND = {
    "municipalities": 32633,
    "drawn": 4326,
}


def _area_to_geodataframe(area: SelectionArea) -> geopandas.GeoDataFrame:
    frame = geopandas.GeoDataFrame.from_features(area.geojson["features"])
    if frame.empty:
        raise ValueError(f"Area {area.kind!r} contains no geometries.")

    source_epsg = SOURCE_EPSG_BY_KIND[area.kind]
    frame = frame.set_crs(epsg=source_epsg, allow_override=True)
    return frame.to_crs(epsg=4326)


def clip_selection(selection: SelectionRequest) -> ClipResult:
    """Run GIS clip analysis on selected municipalities and/or drawn polygons."""

    analysis_frames: list[geopandas.GeoDataFrame] = []
    intersected_names: list[str] = []

    municipalities_area = selection.get_area("municipalities")
    if municipalities_area is not None:
        municipalities_frame = _area_to_geodataframe(municipalities_area)
        analysis_frames.append(municipalities_frame)
        if "COMUNE" in municipalities_frame:
            intersected_names.extend(
                municipalities_frame["COMUNE"].dropna().astype(str).tolist()
            )

    drawn_area = selection.get_area("drawn")
    if drawn_area is not None:
        drawn_frame = _area_to_geodataframe(drawn_area)
        analysis_frames.append(drawn_frame)

        drawn_intersections = geopandas.clip(
            load_campania_boundaries().copy(),
            drawn_frame,
            keep_geom_type=False,
        )
        if "COMUNE" in drawn_intersections:
            intersected_names.extend(
                drawn_intersections["COMUNE"].dropna().astype(str).tolist()
            )

    if not analysis_frames:
        raise ValueError("At least one analysis area required.")

    analysis_mask = geopandas.GeoDataFrame(
        pd.concat(analysis_frames, ignore_index=True),
        crs=analysis_frames[0].crs,
    )

    clipped = geopandas.clip(
        load_nature_shapes().copy(),
        analysis_mask,
        keep_geom_type=False,
    )

    return ClipResult(
        clipped=clipped,
        intersected_municipalities=filter_municipalities_with_nature(intersected_names),
    )
