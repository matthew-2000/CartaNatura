"""Command handlers that bridge interaction layer and application services."""

from __future__ import annotations

import json
from typing import Protocol

from cartaNatura.services.analysis_summary import summarize_clipped_features
from cartaNatura.services.gis_clip import clip_selection
from cartaNatura.services.municipality_text import build_municipality_selection_payload_dict
from cartaNatura.services.payloads import parse_selection_payload

from .models import (
    InteractionCommand,
    InteractionIntent,
    InteractionMessage,
    InteractionRequest,
    InteractionResponse,
    SessionContext,
)
from .providers import LlmProvider
from .response_text import build_analysis_reply, build_explanation_reply


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
    def __init__(self, llm_provider: LlmProvider | None = None):
        self._llm_provider = llm_provider

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
        summary = summarize_clipped_features(result.clipped)
        analysis_result = {
            "clipped": json.loads(result.clipped.to_json()),
            "intersectedMunicipalities": result.intersected_municipalities,
            "summary": summary,
        }
        assistant_result = build_analysis_reply(
            requested_municipalities=result.intersected_municipalities,
            summary=summary,
            llm_provider=self._llm_provider,
        )

        return InteractionResponse(
            messages=(InteractionMessage(role="assistant", text=assistant_result.text),),
            commands=(command,),
            analysis_result=analysis_result,
            ui_hints={
                "channel": request.channel.value,
                "mode": "structured_selection",
                "llmConfigured": self._llm_provider is not None,
                "providerMode": assistant_result.provider_mode,
                "warning": assistant_result.warning,
            },
            audio_output_text=assistant_result.text,
            updated_context=SessionContext(
                selection_payload=selection_payload,
                last_analysis={
                    "summary": summary,
                    "intersectedMunicipalities": result.intersected_municipalities,
                },
                last_intent=command.intent,
            ),
        )


class AnalyzeMunicipalitiesHandler:
    def __init__(self, llm_provider: LlmProvider | None = None):
        self._llm_provider = llm_provider

    intent = InteractionIntent.ANALYZE_MUNICIPALITIES

    def handle(
        self,
        request: InteractionRequest,
        command: InteractionCommand,
        session_context: SessionContext,
    ) -> InteractionResponse:
        del session_context

        requested_municipalities = [
            str(name)
            for name in command.payload.get("municipality_names", [])
            if str(name).strip()
        ]
        if not requested_municipalities:
            raise ValueError("Nessun comune riconosciuto nel messaggio.")

        selection_payload = build_municipality_selection_payload_dict(requested_municipalities)
        selection = parse_selection_payload(selection_payload)
        result = clip_selection(selection)
        summary = summarize_clipped_features(result.clipped)
        assistant_result = build_analysis_reply(
            requested_municipalities=requested_municipalities,
            summary=summary,
            llm_provider=self._llm_provider,
        )
        analysis_result = {
            "clipped": json.loads(result.clipped.to_json()),
            "intersectedMunicipalities": result.intersected_municipalities,
            "requestedMunicipalities": requested_municipalities,
            "summary": summary,
        }

        return InteractionResponse(
            messages=(InteractionMessage(role="assistant", text=assistant_result.text),),
            commands=(command,),
            analysis_result=analysis_result,
            ui_hints={
                "channel": request.channel.value,
                "mode": "text_municipality_analysis",
                "llmConfigured": self._llm_provider is not None,
                "providerMode": assistant_result.provider_mode,
                "warning": assistant_result.warning,
            },
            audio_output_text=assistant_result.text,
            updated_context=SessionContext(
                selection_payload=selection_payload,
                last_analysis={
                    "summary": summary,
                    "intersectedMunicipalities": result.intersected_municipalities,
                    "requestedMunicipalities": requested_municipalities,
                },
                last_intent=command.intent,
            ),
        )


class ExplainLastAnalysisHandler:
    def __init__(self, llm_provider: LlmProvider | None = None):
        self._llm_provider = llm_provider

    intent = InteractionIntent.EXPLAIN_LAST_ANALYSIS

    def handle(
        self,
        request: InteractionRequest,
        command: InteractionCommand,
        session_context: SessionContext,
    ) -> InteractionResponse:
        del request

        analysis_summary = (session_context.last_analysis or {}).get("summary")
        assistant_result = build_explanation_reply(
            analysis_summary=analysis_summary,
            llm_provider=self._llm_provider,
        )

        return InteractionResponse(
            messages=(InteractionMessage(role="assistant", text=assistant_result.text),),
            commands=(command,),
            ui_hints={
                "mode": "explain_last_analysis",
                "llmConfigured": self._llm_provider is not None,
                "providerMode": assistant_result.provider_mode,
                "warning": assistant_result.warning,
            },
            audio_output_text=assistant_result.text,
            updated_context=SessionContext(
                selection_payload=session_context.selection_payload,
                last_analysis=session_context.last_analysis,
                last_intent=command.intent,
                metadata=session_context.metadata,
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
