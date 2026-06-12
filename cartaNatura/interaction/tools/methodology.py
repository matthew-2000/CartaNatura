"""Static methodology tool."""

from __future__ import annotations


def get_methodology() -> dict[str, object]:
    return {
        "dataSource": "Carta della Natura locale",
        "analysisMode": "clip geometrico deterministico",
        "co2Rule": "somma ettari per categoria * coefficiente CO2 per ettaro",
        "notes": [
            "I valori numerici derivano dal backend GIS, non dal modello linguistico.",
            "Le categorie supportate sono definite nel dominio applicativo.",
        ],
    }
