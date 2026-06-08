"""Command handlers that bridge interaction layer and application services."""

from __future__ import annotations

from typing import Protocol

from .analysis_store import AnalysisStore, NullAnalysisStore, new_stored_analysis
from .models import (
    InteractionChannel,
    InteractionCommand,
    InteractionIntent,
    InteractionMessage,
    InteractionRequest,
    InteractionResponse,
    SessionContext,
)
from .providers import LlmProvider
from .response_text import build_analysis_reply, build_comparison_reply, build_explanation_reply
from .tools.contracts import ToolName
from .tools.registry import ToolRegistry


class CommandHandler(Protocol):
    intent: InteractionIntent

    def handle(
        self,
        request: InteractionRequest,
        command: InteractionCommand,
        session_context: SessionContext,
    ) -> InteractionResponse:
        """Execute a resolved interaction command."""


def _require_llm_provider(llm_provider: LlmProvider | None) -> LlmProvider:
    if llm_provider is None:
        raise ValueError("Assistente AI non configurato. Imposta OPENAI_API_KEY.")
    return llm_provider


class AnalyzeSelectionHandler:
    def __init__(
        self,
        llm_provider: LlmProvider | None = None,
        tool_registry: ToolRegistry | None = None,
        analysis_store: AnalysisStore | None = None,
    ):
        self._llm_provider = llm_provider
        self._tool_registry = tool_registry
        self._analysis_store = analysis_store or NullAnalysisStore()

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

        if self._tool_registry is None:
            raise ValueError("Tool registry not configured.")

        analysis_result = self._tool_registry.execute(
            ToolName.ANALYZE_SELECTION,
            selection_payload=selection_payload,
        )
        stored_analysis = self._analysis_store.save(
            new_stored_analysis(
                source=str(analysis_result.get("source") or "selection"),
                summary=analysis_result["summary"],
                intersected_municipalities=analysis_result.get("intersectedMunicipalities", []),
                selection_payload=selection_payload,
                metadata={"channel": request.channel.value},
            )
        )
        analysis_result["analysisId"] = stored_analysis.analysis_id
        summary = analysis_result["summary"]
        messages: tuple[InteractionMessage, ...] = ()
        ui_hints = {
            "channel": request.channel.value,
            "mode": "structured_selection",
        }
        audio_output_text = None

        if request.channel is not InteractionChannel.WEB_MAP:
            assistant_result = build_analysis_reply(
                requested_municipalities=analysis_result.get("intersectedMunicipalities", []),
                summary=summary,
                llm_provider=_require_llm_provider(self._llm_provider),
            )
            messages = (InteractionMessage(role="assistant", text=assistant_result.text),)
            ui_hints["providerMode"] = assistant_result.provider_mode
            audio_output_text = assistant_result.text

        return InteractionResponse(
            messages=messages,
            commands=(command,),
            analysis_result=analysis_result,
            ui_hints=ui_hints,
            audio_output_text=audio_output_text,
            updated_context=SessionContext(
                selection_payload=selection_payload,
                last_analysis={
                    "analysisId": stored_analysis.analysis_id,
                    "summary": summary,
                    "intersectedMunicipalities": analysis_result.get("intersectedMunicipalities", []),
                },
                last_intent=command.intent,
            ),
        )


class AnalyzeMunicipalitiesHandler:
    def __init__(
        self,
        llm_provider: LlmProvider | None = None,
        tool_registry: ToolRegistry | None = None,
        analysis_store: AnalysisStore | None = None,
    ):
        self._llm_provider = llm_provider
        self._tool_registry = tool_registry
        self._analysis_store = analysis_store or NullAnalysisStore()

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

        if self._tool_registry is None:
            raise ValueError("Tool registry not configured.")

        analysis_result = self._tool_registry.execute(
            ToolName.ANALYZE_MUNICIPALITIES,
            municipality_names=requested_municipalities,
        )
        stored_analysis = self._analysis_store.save(
            new_stored_analysis(
                source=str(analysis_result.get("source") or "municipalities"),
                summary=analysis_result["summary"],
                requested_municipalities=requested_municipalities,
                intersected_municipalities=analysis_result.get("intersectedMunicipalities", []),
                selection_payload=analysis_result.get("selectionPayload"),
                metadata={"channel": request.channel.value},
            )
        )
        analysis_result["analysisId"] = stored_analysis.analysis_id
        summary = analysis_result["summary"]
        assistant_result = build_analysis_reply(
            requested_municipalities=requested_municipalities,
            summary=summary,
            llm_provider=_require_llm_provider(self._llm_provider),
        )

        return InteractionResponse(
            messages=(InteractionMessage(role="assistant", text=assistant_result.text),),
            commands=(command,),
            analysis_result=analysis_result,
            ui_hints={
                "channel": request.channel.value,
                "mode": "text_municipality_analysis",
                "providerMode": assistant_result.provider_mode,
            },
            audio_output_text=assistant_result.text,
            updated_context=SessionContext(
                selection_payload=analysis_result.get("selectionPayload"),
                last_analysis={
                    "analysisId": stored_analysis.analysis_id,
                    "summary": summary,
                    "intersectedMunicipalities": analysis_result.get("intersectedMunicipalities", []),
                    "requestedMunicipalities": requested_municipalities,
                },
                last_intent=command.intent,
            ),
        )


class ExplainLastAnalysisHandler:
    def __init__(
        self,
        llm_provider: LlmProvider | None = None,
        analysis_store: AnalysisStore | None = None,
    ):
        self._llm_provider = llm_provider
        self._analysis_store = analysis_store or NullAnalysisStore()

    intent = InteractionIntent.EXPLAIN_LAST_ANALYSIS

    def handle(
        self,
        request: InteractionRequest,
        command: InteractionCommand,
        session_context: SessionContext,
    ) -> InteractionResponse:
        del request

        last_analysis = self._analysis_store.get_last()
        analysis_summary = (
            last_analysis.summary
            if last_analysis is not None
            else (session_context.last_analysis or {}).get("summary")
        )
        assistant_result = build_explanation_reply(
            analysis_summary=analysis_summary,
            llm_provider=_require_llm_provider(self._llm_provider),
        )

        return InteractionResponse(
            messages=(InteractionMessage(role="assistant", text=assistant_result.text),),
            commands=(command,),
            ui_hints={
                "mode": "explain_last_analysis",
                "providerMode": assistant_result.provider_mode,
            },
            audio_output_text=assistant_result.text,
            updated_context=SessionContext(
                selection_payload=session_context.selection_payload,
                last_analysis=session_context.last_analysis,
                last_intent=command.intent,
                metadata=session_context.metadata,
            ),
        )


class CompareAnalysesHandler:
    def __init__(
        self,
        llm_provider: LlmProvider | None = None,
        tool_registry: ToolRegistry | None = None,
        analysis_store: AnalysisStore | None = None,
    ):
        self._llm_provider = llm_provider
        self._tool_registry = tool_registry
        self._analysis_store = analysis_store or NullAnalysisStore()

    intent = InteractionIntent.COMPARE_ANALYSES

    def handle(
        self,
        request: InteractionRequest,
        command: InteractionCommand,
        session_context: SessionContext,
    ) -> InteractionResponse:
        del request, command
        if self._tool_registry is None:
            raise ValueError("Tool registry not configured.")

        recent = self._analysis_store.list_recent(limit=2)
        if len(recent) < 2:
            raise ValueError("Servono almeno due analisi recenti per eseguire un confronto.")

        comparison = self._tool_registry.execute(
            ToolName.COMPARE_ANALYSES,
            left_analysis_id=recent[1].analysis_id,
            right_analysis_id=recent[0].analysis_id,
        )
        assistant_result = build_comparison_reply(
            comparison_summary=comparison,
            llm_provider=_require_llm_provider(self._llm_provider),
        )

        return InteractionResponse(
            messages=(InteractionMessage(role="assistant", text=assistant_result.text),),
            commands=(InteractionCommand(intent=self.intent),),
            analysis_result=comparison,
            ui_hints={
                "mode": "compare_analyses",
                "providerMode": assistant_result.provider_mode,
            },
            audio_output_text=assistant_result.text,
            updated_context=SessionContext(
                selection_payload=session_context.selection_payload,
                last_analysis=session_context.last_analysis,
                last_intent=self.intent,
                metadata=session_context.metadata,
            ),
        )


class ResetSessionHandler:
    def __init__(self, tool_registry: ToolRegistry | None = None):
        self._tool_registry = tool_registry

    intent = InteractionIntent.RESET_SESSION

    def handle(
        self,
        request: InteractionRequest,
        command: InteractionCommand,
        session_context: SessionContext,
    ) -> InteractionResponse:
        del request, session_context
        if self._tool_registry is not None:
            self._tool_registry.execute(ToolName.RESET_ANALYSIS_CONTEXT)

        return InteractionResponse(
            messages=(InteractionMessage(role="assistant", text="Sessione azzerata."),),
            commands=(command,),
            ui_hints={"mode": "reset"},
            audio_output_text="Sessione azzerata.",
            updated_context=SessionContext(last_intent=command.intent),
        )
