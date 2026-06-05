"""Intent resolution for channel-neutral interaction requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

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

        return IntentResolution(
            command=InteractionCommand(intent=InteractionIntent.UNKNOWN),
            clarification_message=(
                "Input testuale ricevuto, ma interpretazione linguaggio naturale "
                "arrivera nella fase successiva."
            ),
        )
