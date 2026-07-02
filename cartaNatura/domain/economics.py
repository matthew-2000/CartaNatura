"""Economic scenario constants for CO2 valuation."""

from __future__ import annotations

from typing import Any


PRICE_OPTIONS = (
    {"key": "social_cost", "label": "Costo sociale: 138 EUR/t", "value": 138},
    {"key": "shadow_price", "label": "Prezzo ombra: 303 EUR/t", "value": 303},
    {"key": "regulated_market", "label": "Mercato regolamentato: 82 EUR/t", "value": 82},
    {"key": "voluntary_market", "label": "Mercato volontario: 20 EUR/t", "value": 20},
)


def get_price_option(scenario_key: str) -> dict[str, Any]:
    normalized_key = str(scenario_key or "").strip()
    for option in PRICE_OPTIONS:
        if option["key"] == normalized_key:
            return dict(option)
    raise ValueError(f"Scenario economico non supportato: {normalized_key or 'mancante'}.")


def calculate_economic_value(*, total_co2: float, scenario_key: str) -> dict[str, Any]:
    option = get_price_option(scenario_key)
    normalized_total_co2 = float(total_co2)
    price = float(option["value"])
    return {
        "scenarioKey": option["key"],
        "scenarioLabel": option["label"],
        "priceEurPerTon": price,
        "totalCo2": normalized_total_co2,
        "totalValueEur": normalized_total_co2 * price,
    }


def compare_economic_scenarios(*, total_co2: float) -> list[dict[str, Any]]:
    return [
        calculate_economic_value(
            total_co2=total_co2,
            scenario_key=str(option["key"]),
        )
        for option in PRICE_OPTIONS
    ]
