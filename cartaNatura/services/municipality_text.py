"""Text-driven municipality matching and selection building."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from cartaNatura.services.datasets import load_municipality_shapes


def _normalize_phrase(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    collapsed = re.sub(r"[^a-z0-9]+", " ", without_marks.lower())
    return re.sub(r"\s+", " ", collapsed).strip()


def municipality_names() -> list[str]:
    frame = load_municipality_shapes()
    return sorted(frame["COMUNE"].dropna().astype(str).unique().tolist())


def extract_municipality_names(text: str) -> list[str]:
    normalized_text = f" {_normalize_phrase(text)} "
    matches: list[tuple[int, str]] = []

    for name in municipality_names():
        normalized_name = _normalize_phrase(name)
        if not normalized_name:
            continue

        position = normalized_text.find(f" {normalized_name} ")
        if position == -1:
            continue

        matches.append((position, name))

    matches.sort(key=lambda item: (item[0], item[1]))
    deduped: list[str] = []
    seen: set[str] = set()
    for _, name in matches:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped


def build_municipality_selection_payload(names: list[str]) -> dict[str, Any]:
    frame = load_municipality_shapes().copy()
    canonical_names = [str(name) for name in names if name]
    filtered = frame[frame["COMUNE"].isin(canonical_names)]
    if filtered.empty:
        raise ValueError("Nessun comune valido riconosciuto nel messaggio.")

    return {
        "areas": [
            {
                "kind": "municipalities",
                "geojson": filtered.to_json(drop_id=True),
            }
        ]
    }


def build_municipality_selection_payload_dict(names: list[str]) -> dict[str, Any]:
    payload = build_municipality_selection_payload(names)
    area = payload["areas"][0]
    if isinstance(area["geojson"], str):
        import json

        area["geojson"] = json.loads(area["geojson"])
    return payload
