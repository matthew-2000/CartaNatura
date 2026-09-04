"""Lazy cached GIS dataset loaders."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import geopandas
from shapely import make_valid

from cartaNatura.domain.vegetation import unclassified_vegetation_codes


APP_DIR = Path(__file__).resolve().parents[1]
NATURE_SHAPEFILE_PATH = APP_DIR / "shapeCN" / "CNPulita.shp"
CAMPANIA_BOUNDARIES_PATH = APP_DIR / "static" / "util" / "moddedCampania.geojson"
MUNICIPALITY_SHAPES_PATH = APP_DIR / "static" / "data" / "campania-municipalities-32633.geojson"
NATURE_REQUIRED_COLUMNS = frozenset({"CODICE", "ettari"})
NATURE_SOURCE_EPSG = 32633
MUNICIPALITY_SOURCE_EPSG = 32633
MAX_GEOMETRY_REPAIR_RELATIVE_AREA_CHANGE = 1e-9


def prepare_nature_shapes(frame: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame:
    """Validate and reproducibly repair the scientific source layer."""

    missing_columns = NATURE_REQUIRED_COLUMNS - set(frame.columns)
    if missing_columns:
        raise ValueError(
            "Dataset Carta Natura privo dei campi richiesti: "
            + ", ".join(sorted(missing_columns))
            + "."
        )
    if frame.crs is None:
        raise ValueError("Dataset Carta Natura privo di CRS.")
    if frame.crs.to_epsg() != NATURE_SOURCE_EPSG:
        raise ValueError(
            f"CRS Carta Natura inatteso: atteso EPSG:{NATURE_SOURCE_EPSG}, ricevuto {frame.crs}."
        )
    if frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise ValueError("Dataset Carta Natura contenente geometrie nulle o vuote.")

    unknown_codes = unclassified_vegetation_codes(frame["CODICE"])
    if unknown_codes:
        raise ValueError(
            "Dataset Carta Natura contenente codici vegetazionali non classificati: "
            + ", ".join(sorted(unknown_codes))
            + "."
        )

    prepared = frame.copy()
    invalid_mask = ~prepared.geometry.is_valid
    if invalid_mask.any():
        original = prepared.loc[invalid_mask, prepared.geometry.name]
        repaired = geopandas.GeoSeries(
            [make_valid(geometry) for geometry in original],
            index=original.index,
            crs=prepared.crs,
        )
        if repaired.is_empty.any() or (~repaired.is_valid).any():
            raise ValueError("Riparazione delle geometrie Carta Natura non riuscita.")
        if not repaired.geom_type.isin({"Polygon", "MultiPolygon"}).all():
            raise ValueError(
                "Riparazione Carta Natura produrrebbe geometrie non areali; "
                "è richiesta una decisione esplicita di preprocessing."
            )

        original_area = original.area
        repaired_area = repaired.area
        area_scale = original_area.abs().combine(repaired_area.abs(), max).clip(lower=1.0)
        relative_change = (repaired_area - original_area).abs() / area_scale
        if (relative_change > MAX_GEOMETRY_REPAIR_RELATIVE_AREA_CHANGE).any():
            raise ValueError(
                "Riparazione Carta Natura modificherebbe materialmente la superficie; "
                "è richiesta una decisione esplicita di preprocessing."
            )
        prepared.loc[invalid_mask, prepared.geometry.name] = repaired

    if (~prepared.geometry.is_valid).any():
        raise ValueError("Dataset Carta Natura ancora contenente geometrie non valide.")
    return prepared


@lru_cache(maxsize=1)
def load_nature_shapes() -> geopandas.GeoDataFrame:
    """Load, validate and normalize Carta della Natura shapes."""

    return prepare_nature_shapes(geopandas.read_file(NATURE_SHAPEFILE_PATH)).to_crs(epsg=4326)


@lru_cache(maxsize=1)
def load_campania_boundaries() -> geopandas.GeoDataFrame:
    """Load municipal boundaries used for polygon intersection lookup."""

    return geopandas.read_file(CAMPANIA_BOUNDARIES_PATH).to_crs(epsg=4326)


@lru_cache(maxsize=1)
def load_municipality_shapes() -> geopandas.GeoDataFrame:
    """Load municipality geometries used for text-driven selections."""

    frame = geopandas.read_file(MUNICIPALITY_SHAPES_PATH)
    if frame.crs is None or frame.crs.to_epsg() != MUNICIPALITY_SOURCE_EPSG:
        raise ValueError(
            "CRS del dataset comunale inatteso: "
            f"atteso EPSG:{MUNICIPALITY_SOURCE_EPSG}, ricevuto {frame.crs or 'assente'}."
        )
    return frame
