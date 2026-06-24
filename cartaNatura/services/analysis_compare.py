"""Deterministic comparison for saved analysis history records."""

from __future__ import annotations

from typing import Any


def compare_saved_analyses(
    records: list[Any] | tuple[Any, ...],
    price_options: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any]:
    analyses = [_normalize_record(record) for record in records]
    if len(analyses) < 2:
        raise ValueError("Servono almeno due analisi da confrontare.")

    return {
        "analyses": analyses,
        "rankings": {
            "totalCo2": _rank(analyses, "totalCo2"),
            "totalHectares": _rank(analyses, "totalHectares"),
            "co2PerHectare": _rank(analyses, "co2PerHectare"),
        },
        "pairwise": _build_pairwise(analyses[:2]) if len(analyses) == 2 else None,
        "categoriesComparison": _build_categories_comparison(analyses),
        "economicComparison": _build_economic_comparison(analyses, price_options or ()),
    }


def _normalize_record(record: Any) -> dict[str, Any]:
    if hasattr(record, "analysis_id"):
        summary = getattr(record, "summary", {}) or {}
        total_co2 = _safe_number(summary.get("totalCo2"))
        total_hectares = _safe_number(summary.get("totalHectares"))
        return {
            "id": getattr(record, "analysis_id", ""),
            "label": getattr(record, "label", "") or getattr(record, "analysis_id", ""),
            "createdAt": getattr(record, "created_at", ""),
            "selectionKind": getattr(record, "selection_kind", "unknown"),
            "municipalities": [
                str(item)
                for item in (
                    getattr(record, "intersected_municipalities", ())
                    or getattr(record, "requested_municipalities", ())
                )
                if str(item).strip()
            ],
            "hasDrawnGeometry": bool(getattr(record, "has_drawn_geometry", False)),
            "totalCo2": total_co2,
            "totalHectares": total_hectares,
            "co2PerHectare": _ratio_or_none(total_co2, total_hectares),
            "topCategory": summary.get("topCategory"),
            "hasSupportedVegetation": bool(summary.get("hasSupportedVegetation")),
            "items": _normalize_items(summary.get("items")),
        }

    summary = record.get("summary", {}) if isinstance(record, dict) else {}
    total_co2 = _safe_number(summary.get("totalCo2"))
    total_hectares = _safe_number(summary.get("totalHectares"))
    return {
        "id": str(record.get("id") or record.get("analysisId") or ""),
        "label": str(record.get("label") or record.get("id") or ""),
        "createdAt": str(record.get("createdAt") or ""),
        "selectionKind": str(record.get("selectionKind") or "unknown"),
        "municipalities": [
            str(item) for item in record.get("municipalities", []) if str(item).strip()
        ],
        "hasDrawnGeometry": bool(record.get("hasDrawnGeometry")),
        "totalCo2": total_co2,
        "totalHectares": total_hectares,
        "co2PerHectare": _ratio_or_none(total_co2, total_hectares),
        "topCategory": summary.get("topCategory"),
        "hasSupportedVegetation": bool(summary.get("hasSupportedVegetation")),
        "items": _normalize_items(summary.get("items")),
    }


def _normalize_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        hectares = _safe_number(item.get("hectares"))
        co2_per_hectare = _safe_number(item.get("co2PerHectare"))
        normalized.append(
            {
                "key": str(item.get("key") or item.get("label") or ""),
                "label": str(item.get("label") or item.get("key") or ""),
                "hectares": hectares,
                "co2PerHectare": co2_per_hectare,
                "totalCo2": (
                    hectares * co2_per_hectare
                    if hectares is not None and co2_per_hectare is not None
                    else None
                ),
            }
        )
    return normalized


def _rank(analyses: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    ranked = sorted(
        analyses,
        key=lambda item: (
            item.get(field) is None,
            -float(item.get(field) or 0),
            str(item.get("label") or ""),
        ),
    )
    return [
        {
            "rank": index + 1,
            "id": item["id"],
            "label": item["label"],
            "value": item.get(field),
        }
        for index, item in enumerate(ranked)
    ]


def _build_pairwise(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    left, right = analyses
    co2_winner = _winner(left, right, "totalCo2")
    intensity_winner = _winner(left, right, "co2PerHectare")
    return {
        "left": {"id": left["id"], "label": left["label"]},
        "right": {"id": right["id"], "label": right["label"]},
        "totalCo2": _difference(left.get("totalCo2"), right.get("totalCo2")),
        "totalHectares": _difference(left.get("totalHectares"), right.get("totalHectares")),
        "co2PerHectare": _difference(left.get("co2PerHectare"), right.get("co2PerHectare")),
        "higherTotalCo2": co2_winner,
        "higherCo2PerHectare": intensity_winner,
    }


def _difference(left: Any, right: Any) -> dict[str, float | None]:
    left_value = _safe_number(left)
    right_value = _safe_number(right)
    if left_value is None or right_value is None:
        return {"absolute": None, "percent": None}

    absolute = abs(right_value - left_value)
    percent = None if left_value == 0 else (absolute / abs(left_value)) * 100
    return {"absolute": absolute, "percent": percent}


def _winner(left: dict[str, Any], right: dict[str, Any], field: str) -> dict[str, Any] | None:
    left_value = _safe_number(left.get(field))
    right_value = _safe_number(right.get(field))
    if left_value is None and right_value is None:
        return None
    if right_value is None or (left_value is not None and left_value >= right_value):
        return {"id": left["id"], "label": left["label"], "value": left_value}
    return {"id": right["id"], "label": right["label"], "value": right_value}


def _build_categories_comparison(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    category_sets = {
        analysis["id"]: {item["key"] for item in analysis["items"] if item.get("key")}
        for analysis in analyses
    }
    all_categories = sorted(set().union(*category_sets.values())) if category_sets else []
    common_categories = sorted(set.intersection(*category_sets.values())) if category_sets else []
    partial_categories = [
        key for key in all_categories if key not in set(common_categories)
    ]

    category_breakdown = []
    for key in all_categories:
        rows = []
        label = key
        for analysis in analyses:
            item = next((entry for entry in analysis["items"] if entry["key"] == key), None)
            if item is not None:
                label = item.get("label") or label
            rows.append(
                {
                    "id": analysis["id"],
                    "label": analysis["label"],
                    "hectares": item.get("hectares") if item else 0,
                    "totalCo2": item.get("totalCo2") if item else 0,
                    "co2PerHectare": item.get("co2PerHectare") if item else None,
                    "present": item is not None,
                }
            )
        category_breakdown.append({"key": key, "label": label, "analyses": rows})

    return {
        "categoriesByAnalysis": [
            {
                "id": analysis["id"],
                "label": analysis["label"],
                "categories": analysis["items"],
            }
            for analysis in analyses
        ],
        "commonCategories": common_categories,
        "partialCategories": partial_categories,
        "topCategoriesByAnalysis": [
            {
                "id": analysis["id"],
                "label": analysis["label"],
                "topCategory": analysis.get("topCategory"),
            }
            for analysis in analyses
        ],
        "categoryBreakdown": category_breakdown,
    }


def _build_economic_comparison(
    analyses: list[dict[str, Any]],
    price_options: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    scenarios = []
    for option in price_options:
        price = _safe_number(option.get("value"))
        label = str(option.get("label") or "")
        values = [
            {
                "id": analysis["id"],
                "label": analysis["label"],
                "totalCo2": analysis["totalCo2"],
                "value": (
                    analysis["totalCo2"] * price
                    if analysis["totalCo2"] is not None and price is not None
                    else None
                ),
            }
            for analysis in analyses
        ]
        ranked = sorted(
            values,
            key=lambda item: (
                item["value"] is None,
                -float(item["value"] or 0),
                item["label"],
            ),
        )
        scenarios.append(
            {
                "label": label,
                "priceEurPerTon": price,
                "values": values,
                "ranking": [
                    {
                        "rank": index + 1,
                        "id": item["id"],
                        "label": item["label"],
                        "value": item["value"],
                    }
                    for index, item in enumerate(ranked)
                ],
            }
        )
    return scenarios


def _safe_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ratio_or_none(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator
