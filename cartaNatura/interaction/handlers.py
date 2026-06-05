"""Command handlers that bridge interaction layer and application services."""

from __future__ import annotations

import json
from typing import Protocol

from cartaNatura.services.gis_clip import clip_selection
from cartaNatura.services.payloads import parse_selection_payload

from .models import (
    InteractionCommand,
    InteractionIntent,
    InteractionMessage,
    InteractionRequest,
    InteractionResponse,
    SessionContext,
)


class CommandHandler(Protocol):
    intent: InteractionIntent

    def handle(
        self,
        request: InteractionRequest,
        command: InteractionCommand,
        session_context: SessionContext,
    ) -> InteractionResponse:
        """Execute a resolved interaction command."""


class AnalyzeSelectionHandler:
    intent = InteractionIntent.ANALYZE_SELECTION

    def handle(
        self,
        request: InteractionRequest,
        command: InteractionCommand,
        session_context: SessionContext,
    ) -> InteractionResponse:
        del session_context

        selection_payload = command.payload or request.input.geo_selection
        if not selection_payload:
            raise ValueError("Missing structured selection payload.")

        selection = parse_selection_payload(selection_payload)
        result = clip_selection(selection)
        analysis_result = {
            "clipped": json.loads(result.clipped.to_json()),
            "intersectedMunicipalities": result.intersected_municipalities,
        }

        return InteractionResponse(
            messages=(InteractionMessage(role="assistant", text="Analisi completata."),),
            commands=(command,),
            analysis_result=analysis_result,
            ui_hints={
                "channel": request.channel.value,
                "mode": "structured_selection",
            },
            audio_output_text="Analisi completata.",
            updated_context=SessionContext(
                selection_payload=selection_payload,
                last_analysis=analysis_result,
                last_intent=command.intent,
            ),
        )


class ResetSessionHandler:
    intent = InteractionIntent.RESET_SESSION

    def handle(
        self,
        request: InteractionRequest,
        command: InteractionCommand,
        session_context: SessionContext,
    ) -> InteractionResponse:
        del request, session_context

        return InteractionResponse(
            messages=(InteractionMessage(role="assistant", text="Sessione azzerata."),),
            commands=(command,),
            ui_hints={"mode": "reset"},
            audio_output_text="Sessione azzerata.",
            updated_context=SessionContext(last_intent=command.intent),
        )
