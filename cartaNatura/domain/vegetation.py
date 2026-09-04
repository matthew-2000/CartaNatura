"""Vegetation categories and shared mapping rules."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class VegetationCategory:
    key: str
    label: str
    color: str
    co2_per_hectare: float
    codes: tuple[str, ...]


VEGETATION_CATEGORIES: tuple[VegetationCategory, ...] = (
    VegetationCategory(
        key="abete_bianco",
        label="Boschi di abete bianco",
        color="black",
        co2_per_hectare=0.0,
        codes=("42.15",),
    ),
    VegetationCategory(
        key="igrofili",
        label="Boschi igrofili",
        color="maroon",
        co2_per_hectare=3.3,
        codes=("44.12", "44.14", "44.513", "44.61", "44.71", "44.9", "44.D2cn"),
    ),
    VegetationCategory(
        key="querceti_roverella",
        label="Querceti di roverella",
        color="olive",
        co2_per_hectare=3.3,
        codes=("41.732",),
    ),
    VegetationCategory(
        key="ostrieti_carpineti",
        label="Ostrieti e carpineti",
        color="navy",
        co2_per_hectare=4.4,
        codes=("41.8",),
    ),
    VegetationCategory(
        key="leccete",
        label="Leccete",
        color="teal",
        co2_per_hectare=5.51,
        codes=("45.31", "45.32"),
    ),
    VegetationCategory(
        key="caducifogli",
        label="Altri boschi caducifogli",
        color="aqua",
        co2_per_hectare=5.87,
        codes=("41.4", "41.B", "41.C1"),
    ),
    VegetationCategory(
        key="cerrete_farnetto",
        label="Cerrete e boschi di farnetto",
        color="purple",
        co2_per_hectare=5.87,
        codes=("41.7511", "41.7512"),
    ),
    VegetationCategory(
        key="pinete_mediterranee",
        label="Pinete di pini mediterranei",
        color="lime",
        co2_per_hectare=5.87,
        codes=("42.83", "42.84"),
    ),
    VegetationCategory(
        key="castagneti",
        label="Castagneti",
        color="blue",
        co2_per_hectare=6.24,
        codes=("41.9",),
    ),
    VegetationCategory(
        key="sugherete",
        label="Sugherete",
        color="gray",
        co2_per_hectare=8.07,
        codes=("45.21",),
    ),
    VegetationCategory(
        key="faggete",
        label="Faggete",
        color="orange",
        co2_per_hectare=9.54,
        codes=("41.18",),
    ),
    VegetationCategory(
        key="conifere_miste",
        label="Altri boschi di conifere, pure o miste",
        color="gold",
        co2_per_hectare=12.48,
        codes=("41.Lcn", "42.A1"),
    ),
)


VEGETATION_BY_CODE = {
    code: category
    for category in VEGETATION_CATEGORIES
    for code in category.codes
}

# Dataset codes that are intentionally excluded from the analytical model.
# Keeping the set explicit makes an upstream dataset change fail closed instead
# of silently dropping area and CO2 from summaries.
EXCLUDED_VEGETATION_CODES: frozenset[str] = frozenset()


def resolve_vegetation_category(code: object) -> VegetationCategory | None:
    """Resolve an exact dataset code or reject an unclassified value."""

    canonical_code = "" if code is None else str(code).strip()
    if canonical_code in EXCLUDED_VEGETATION_CODES:
        return None
    category = VEGETATION_BY_CODE.get(canonical_code)
    if category is None:
        raise ValueError(f"Codice vegetazionale non classificato: {canonical_code or '<vuoto>'}.")
    return category


def unclassified_vegetation_codes(codes: Iterable[object]) -> set[str]:
    """Return dataset values lacking either a category or an explicit exclusion."""

    classified = set(VEGETATION_BY_CODE) | set(EXCLUDED_VEGETATION_CODES)
    normalized = {"" if code is None else str(code).strip() for code in codes}
    return normalized - classified


def serialize_categories() -> list[dict[str, object]]:
    """Expose category config to frontend."""

    return [
        {
            "key": category.key,
            "label": category.label,
            "color": category.color,
            "co2PerHectare": category.co2_per_hectare,
            "codes": list(category.codes),
        }
        for category in VEGETATION_CATEGORIES
    ]
