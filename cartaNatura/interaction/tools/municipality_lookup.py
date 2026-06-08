"""Deterministic municipality lookup helpers for assistant runtime."""

from __future__ import annotations

from typing import Any

from cartaNatura.services.municipality_text import (
    extract_municipality_names,
    suggest_municipality_names,
)


def search_municipalities(*, query: str, limit: int = 5) -> dict[str, Any]:
    normalized_query = str(query).strip()
    bounded_limit = max(1, min(int(limit), 10))
    exact_matches = extract_municipality_names(normalized_query)
    suggestions = suggest_municipality_names(normalized_query, limit=bounded_limit)
    merged: list[str] = []

    for name in [*exact_matches, *suggestions]:
        if name not in merged:
            merged.append(name)

    return {
        "query": normalized_query,
        "exactMatches": exact_matches[:bounded_limit],
        "suggestions": suggestions[:bounded_limit],
        "matches": merged[:bounded_limit],
    }
