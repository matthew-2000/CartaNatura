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


def resolve_municipality_names(names: list[str]) -> list[str]:
    """Resolve every supplied name exactly (case/accent insensitive), or fail atomically."""

    catalog: dict[str, list[str]] = {}
    for canonical_name in municipality_names():
        catalog.setdefault(_normalize_phrase(canonical_name), []).append(canonical_name)

    resolved: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    ambiguous: list[tuple[str, list[str]]] = []
    for raw_name in names:
        display_name = str(raw_name or "").strip()
        normalized_name = _normalize_phrase(display_name)
        if not normalized_name:
            invalid.append(display_name or "<vuoto>")
            continue
        matches = catalog.get(normalized_name, [])
        if not matches:
            invalid.append(display_name)
            continue
        if len(matches) > 1:
            ambiguous.append((display_name, matches))
            continue
        canonical_name = matches[0]
        if canonical_name not in seen:
            seen.add(canonical_name)
            resolved.append(canonical_name)

    if invalid or ambiguous:
        parts = []
        if invalid:
            parts.append("non riconosciuti: " + ", ".join(invalid))
        if ambiguous:
            parts.append(
                "ambigui: "
                + "; ".join(
                    f"{raw_name} ({', '.join(matches)})"
                    for raw_name, matches in ambiguous
                )
            )
        raise ValueError(
            "Analisi non avviata: tutti i comuni devono essere risolti correttamente ("
            + "; ".join(parts)
            + ")."
        )
    if not resolved:
        raise ValueError("Nessun comune valido riconosciuto nel messaggio.")
    return resolved


def suggest_municipality_names(text: str, limit: int = 5) -> list[str]:
    normalized_text = _normalize_phrase(text)
    if not normalized_text:
        return []

    tokens = [token for token in normalized_text.split(" ") if len(token) >= 3]
    if not tokens:
        return []

    scored: list[tuple[int, int, str]] = []
    for name in municipality_names():
        normalized_name = _normalize_phrase(name)
        if not normalized_name:
            continue

        score = 0
        matched_tokens = 0
        for token in tokens:
            if normalized_name.startswith(token):
                score += 3
                matched_tokens += 1
            elif f" {token}" in f" {normalized_name}":
                score += 2
                matched_tokens += 1
            elif token in normalized_name:
                score += 1
                matched_tokens += 1

        if matched_tokens:
            scored.append((-score, -matched_tokens, name))

    scored.sort()
    suggestions: list[str] = []
    seen: set[str] = set()
    for _, _, name in scored:
        if name in seen:
            continue
        seen.add(name)
        suggestions.append(name)
        if len(suggestions) >= limit:
            break
    return suggestions


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
    canonical_names = resolve_municipality_names(names)
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
