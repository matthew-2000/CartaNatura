"""Backend summary helpers shared by interaction flows."""

from __future__ import annotations

from typing import Any

import geopandas

from cartaNatura.domain.vegetation import VEGETATION_BY_CODE, VEGETATION_CATEGORIES


def summarize_clipped_features(clipped: geopandas.GeoDataFrame) -> dict[str, Any]:
    totals_by_key = {category.key: 0.0 for category in VEGETATION_CATEGORIES}
    total_co2 = 0.0
    total_hectares = 0.0

    for _, row in clipped.iterrows():
        code = row.get("CODICE")
        hectares = float(row.get("ettari") or 0)
        category = VEGETATION_BY_CODE.get(str(code))

        if category is None:
            continue

        totals_by_key[category.key] += hectares
        total_co2 += category.co2_per_hectare * hectares
        total_hectares += hectares

    items = [
        {
            "key": category.key,
            "label": category.label,
            "color": category.color,
            "hectares": totals_by_key[category.key],
            "co2PerHectare": category.co2_per_hectare,
        }
        for category in VEGETATION_CATEGORIES
        if totals_by_key[category.key] > 0
    ]

    top_category = max(items, key=lambda item: item["hectares"], default=None)

    return {
        "items": items,
        "totalCo2": total_co2,
        "totalHectares": total_hectares,
        "hasSupportedVegetation": bool(items),
        "topCategory": top_category,
    }
