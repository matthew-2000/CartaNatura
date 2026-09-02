"""Interaction orchestration entrypoint."""

from __future__ import annotations

from typing import Any, Generator

from .analysis_store import AnalysisStore, NullAnalysisStore
from .assistant_runtime import (
    AssistantToolExecutor,
    AssistantRuntime,
)
from .handlers import (
    AnalyzeMunicipalitiesHandler,
    AnalyzeSelectionHandler,
    CompareAnalysesHandler,
    CommandHandler,
    ExplainLastAnalysisHandler,
    ResetSessionHandler,
)
from .llm import LlmProviderConfigurationError, build_optional_llm_provider
from .models import (
    InteractionChannel,
    InteractionIntent,
    InteractionMessage,
    InteractionRequest,
    InteractionResponse,
)
from .resolvers import IntentResolver, RuleBasedIntentResolver
from .session import NullSessionStore, SessionStore
from .tools import build_default_tool_registry


class InteractionOrchestrator:
    def __init__(
        self,
        resolver: IntentResolver,
        handlers: tuple[CommandHandler, ...],
        chat_runtime: AssistantRuntime | None = None,
        session_store: SessionStore | None = None,
        analysis_store: AnalysisStore | None = None,
    ):
        self._resolver = resolver
        self._handlers = {handler.intent: handler for handler in handlers}
        self._chat_runtime = chat_runtime
        self._session_store = session_store or NullSessionStore()
        self._analysis_store = analysis_store or NullAnalysisStore()

    def handle(self, request: InteractionRequest) -> InteractionResponse:
        session_context = self._session_store.load(request.session_id)
        if not self._is_graphical_selection(request):
            response = self._require_chat_runtime().handle(request, session_context)
            return self._persist_response(request, session_context, response)

        resolution = self._resolver.resolve(request, session_context)
        if resolution.command.intent is InteractionIntent.UNKNOWN:
            return InteractionResponse(
                messages=(
                    InteractionMessage(
                        role="assistant",
                        text=resolution.clarification_message or "Richiesta non supportata.",
                    ),
                ),
                commands=(resolution.command,),
                updated_context=session_context,
            )

        return self._handle_resolved_command(request, session_context, resolution)

    def handle_stream(
        self,
        request: InteractionRequest,
    ) -> Generator[dict[str, Any], None, InteractionResponse]:
        session_context = self._session_store.load(request.session_id)

        if not self._is_graphical_selection(request):
            response = yield from self._require_chat_runtime().stream_handle(request, session_context)
            response = self._persist_response(request, session_context, response)
            yield self._serialize_stream_done_event(response)
            return response

        response = self.handle(request)
        yield self._serialize_stream_done_event(response)
        return response

    def _handle_resolved_command(self, request, session_context, resolution) -> InteractionResponse:
        handler = self._handlers.get(resolution.command.intent)
        if handler is None:
            raise ValueError(
                f"No handler registered for intent {resolution.command.intent.value!r}."
            )

        response = handler.handle(request, resolution.command, session_context)
        return self._persist_response(request, session_context, response)

    def _persist_response(
        self,
        request: InteractionRequest,
        session_context,
        response: InteractionResponse,
    ) -> InteractionResponse:
        if response.ui_hints.get("mode") == "reset":
            self._session_store.clear(request.session_id)
            return response

        self._session_store.save(
            request.session_id,
            response.updated_context or session_context,
        )
        return response

    @staticmethod
    def _serialize_stream_done_event(response: InteractionResponse) -> dict[str, Any]:
        return {
            "type": "done",
            "response": {
                "messages": [
                    {
                        "role": message_item.role,
                        "text": message_item.text,
                    }
                    for message_item in response.messages
                ],
                "analysisResult": response.analysis_result,
                "economicResult": response.economic_result,
                "scenarioComparison": response.scenario_comparison,
                "reportContext": response.report_context,
                "mapFilter": response.map_filter,
                "uiHints": response.ui_hints,
            },
        }

    @staticmethod
    def _is_graphical_selection(request: InteractionRequest) -> bool:
        return (
            request.channel is InteractionChannel.WEB_MAP
            and request.input.has_structured_selection()
        )

    def _require_chat_runtime(self) -> AssistantRuntime:
        if self._chat_runtime is None:
            raise LlmProviderConfigurationError(
                "Assistente AI non configurato: serve un provider LLM con supporto ai tool."
            )
        return self._chat_runtime


def build_default_orchestrator(
    session_store: SessionStore | None = None,
    llm_provider=None,
    analysis_store: AnalysisStore | None = None,
) -> InteractionOrchestrator:
    llm_provider = llm_provider if llm_provider is not None else build_optional_llm_provider()
    analysis_store = analysis_store or NullAnalysisStore()
    tool_registry = build_default_tool_registry(analysis_store)
    chat_runtime = None
    if llm_provider is not None and hasattr(llm_provider, "create_response"):
        chat_runtime = AssistantRuntime(
            llm_provider=llm_provider,
            tool_executor=AssistantToolExecutor(
                tool_registry=tool_registry,
                analysis_store=analysis_store,
            ),
        )
    return InteractionOrchestrator(
        resolver=RuleBasedIntentResolver(),
        handlers=(
            AnalyzeSelectionHandler(
                llm_provider=llm_provider,
                tool_registry=tool_registry,
                analysis_store=analysis_store,
            ),
            AnalyzeMunicipalitiesHandler(
                llm_provider=llm_provider,
                tool_registry=tool_registry,
                analysis_store=analysis_store,
            ),
            ExplainLastAnalysisHandler(
                llm_provider=llm_provider,
                analysis_store=analysis_store,
            ),
            CompareAnalysesHandler(
                llm_provider=llm_provider,
                tool_registry=tool_registry,
                analysis_store=analysis_store,
            ),
            ResetSessionHandler(tool_registry=tool_registry),
        ),
        chat_runtime=chat_runtime,
        session_store=session_store or NullSessionStore(),
        analysis_store=analysis_store,
    )
