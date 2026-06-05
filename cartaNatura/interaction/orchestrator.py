"""Interaction orchestration entrypoint."""

from __future__ import annotations

from .handlers import (
    AnalyzeMunicipalitiesHandler,
    AnalyzeSelectionHandler,
    CommandHandler,
    ExplainLastAnalysisHandler,
    ResetSessionHandler,
)
from .llm import build_optional_llm_provider
from .models import (
    InteractionIntent,
    InteractionMessage,
    InteractionRequest,
    InteractionResponse,
)
from .resolvers import IntentResolver, RuleBasedIntentResolver
from .session import NullSessionStore, SessionStore


class InteractionOrchestrator:
    def __init__(
        self,
        resolver: IntentResolver,
        handlers: tuple[CommandHandler, ...],
        session_store: SessionStore | None = None,
    ):
        self._resolver = resolver
        self._handlers = {handler.intent: handler for handler in handlers}
        self._session_store = session_store or NullSessionStore()

    def handle(self, request: InteractionRequest) -> InteractionResponse:
        session_context = self._session_store.load(request.session_id)
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

        handler = self._handlers.get(resolution.command.intent)
        if handler is None:
            raise ValueError(
                f"No handler registered for intent {resolution.command.intent.value!r}."
            )

        response = handler.handle(request, resolution.command, session_context)

        if resolution.command.intent is InteractionIntent.RESET_SESSION:
            self._session_store.clear(request.session_id)
            return response

        self._session_store.save(
            request.session_id,
            response.updated_context or session_context,
        )
        return response


def build_default_orchestrator(
    session_store: SessionStore | None = None,
    llm_provider=None,
) -> InteractionOrchestrator:
    llm_provider = llm_provider if llm_provider is not None else build_optional_llm_provider()
    return InteractionOrchestrator(
        resolver=RuleBasedIntentResolver(),
        handlers=(
            AnalyzeSelectionHandler(llm_provider=llm_provider),
            AnalyzeMunicipalitiesHandler(llm_provider=llm_provider),
            ExplainLastAnalysisHandler(llm_provider=llm_provider),
            ResetSessionHandler(),
        ),
        session_store=session_store or NullSessionStore(),
    )
