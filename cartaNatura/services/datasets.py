"""Lazy cached GIS dataset loaders."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import geopandas


APP_DIR = Path(__file__).resolve().parents[1]
NATURE_SHAPEFILE_PATH = APP_DIR / "shapeCN" / "CNPulita.shp"
CAMPANIA_BOUNDARIES_PATH = APP_DIR / "static" / "util" / "moddedCampania.geojson"


@lru_cache(maxsize=1)
def load_nature_shapes() -> geopandas.GeoDataFrame:
    """Load and normalize Carta della Natura shapes."""

    return geopandas.read_file(NATURE_SHAPEFILE_PATH).to_crs(epsg=4326)


@lru_cache(maxsize=1)
def load_campania_boundaries() -> geopandas.GeoDataFrame:
    """Load municipal boundaries used for polygon intersection lookup."""

    return geopandas.read_file(CAMPANIA_BOUNDARIES_PATH).to_crs(epsg=4326)
