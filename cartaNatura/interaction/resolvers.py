"""Intent resolution for channel-neutral interaction requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from cartaNatura.services.municipality_text import (
    extract_municipality_names,
    suggest_municipality_names,
)

from .models import InteractionCommand, InteractionIntent, InteractionRequest, SessionContext


@dataclass(frozen=True)
class IntentResolution:
    command: InteractionCommand
    clarification_message: str | None = None


class IntentResolver(Protocol):
    def resolve(
        self,
        request: InteractionRequest,
        session_context: SessionContext,
    ) -> IntentResolution:
        """Resolve incoming request into an application command."""


class RuleBasedIntentResolver:
    def resolve(
        self,
        request: InteractionRequest,
        session_context: SessionContext,
    ) -> IntentResolution:
        del session_context

        if request.input.has_structured_selection():
            return IntentResolution(
                command=InteractionCommand(
                    intent=InteractionIntent.ANALYZE_SELECTION,
                    payload=request.input.geo_selection or {},
                )
            )

        text = request.input.primary_text().lower()
        if not text:
            return IntentResolution(
                command=InteractionCommand(intent=InteractionIntent.UNKNOWN),
                clarification_message="Nessun input interpretabile ricevuto.",
            )

        if any(keyword in text for keyword in ("reset", "azzera", "pulisci")):
            return IntentResolution(
                command=InteractionCommand(intent=InteractionIntent.RESET_SESSION)
            )

        if any(keyword in text for keyword in ("spiega", "riepiloga", "riassumi", "ultimo risultato")):
            return IntentResolution(
                command=InteractionCommand(intent=InteractionIntent.EXPLAIN_LAST_ANALYSIS)
            )

        municipality_names = extract_municipality_names(text)
        if municipality_names:
            return IntentResolution(
                command=InteractionCommand(
                    intent=InteractionIntent.ANALYZE_MUNICIPALITIES,
                    payload={
                        "municipality_names": municipality_names,
                        "source_text": request.input.primary_text(),
                    },
                )
            )

        suggested_names = suggest_municipality_names(text)
        if suggested_names:
            if len(suggested_names) == 1:
                return IntentResolution(
                    command=InteractionCommand(
                        intent=InteractionIntent.ANALYZE_MUNICIPALITIES,
                        payload={
                            "municipality_names": suggested_names,
                            "source_text": request.input.primary_text(),
                            "matchMode": "suggested_single",
                        },
                    )
                )

            return IntentResolution(
                command=InteractionCommand(intent=InteractionIntent.UNKNOWN),
                clarification_message=(
                    "Ho trovato piu comuni compatibili. Intendi uno di questi: "
                    f"{', '.join(suggested_names)}?"
                ),
            )

        return IntentResolution(
            command=InteractionCommand(intent=InteractionIntent.UNKNOWN),
            clarification_message=(
                "Posso gia analizzare comuni nominati nel messaggio, per esempio: "
                "'analizza Avellino e Benevento'."
            ),
        )
