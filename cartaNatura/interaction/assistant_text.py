"""Structured assistant text generation results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssistantTextResult:
    text: str
    provider_mode: str
    warning: str | None = None
