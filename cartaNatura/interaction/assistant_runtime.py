"""OpenAI Responses-based assistant runtime for conversational turns."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Generator

from cartaNatura.domain.vegetation import serialize_categories

from .analysis_store import AnalysisStore, NullAnalysisStore, new_stored_analysis
from .models import (
    InteractionCommand,
    InteractionIntent,
    InteractionMessage,
    InteractionRequest,
    InteractionResponse,
    SessionContext,
)
from .observability import elapsed_ms, log_provider_call, log_tool_call, start_timer
from .tools import ToolName
from .tools.methodology import get_methodology
from .tools.registry import ToolRegistry
from .ui_actions import ALLOWED_UI_ACTIONS, filter_ui_actions

MODEL_TOOL_SEARCH_MUNICIPALITIES = "search_municipalities"
MODEL_TOOL_ANALYZE_MUNICIPALITIES = "analyze_municipalities"
MODEL_TOOL_ANALYZE_CURRENT_SELECTION = "analyze_current_selection"
MODEL_TOOL_GET_LAST_ANALYSIS = "get_last_analysis"
MODEL_TOOL_COMPARE_RECENT_ANALYSES = "compare_recent_analyses"
MODEL_TOOL_GET_METHODOLOGY = "get_methodology"
MODEL_TOOL_RESET_ANALYSIS_CONTEXT = "reset_analysis_context"

MODEL_TOOL_NAMES = (
    MODEL_TOOL_SEARCH_MUNICIPALITIES,
    MODEL_TOOL_ANALYZE_MUNICIPALITIES,
    MODEL_TOOL_ANALYZE_CURRENT_SELECTION,
    MODEL_TOOL_GET_LAST_ANALYSIS,
    MODEL_TOOL_COMPARE_RECENT_ANALYSES,
    MODEL_TOOL_GET_METHODOLOGY,
    MODEL_TOOL_RESET_ANALYSIS_CONTEXT,
)
RULE_BASED_CHAT_INTENTS = {
    InteractionIntent.ANALYZE_SELECTION,
    InteractionIntent.ANALYZE_MUNICIPALITIES,
    InteractionIntent.COMPARE_ANALYSES,
    InteractionIntent.EXPLAIN_LAST_ANALYSIS,
    InteractionIntent.RESET_SESSION,
}


@dataclass(frozen=True)
class ToolExecutionOutcome:
    payload: dict[str, Any]
    analysis_result: dict[str, Any] | None = None
    last_analysis: dict[str, Any] | None = None
    selection_payload: dict[str, Any] | None = None
    intent: InteractionIntent | None = None
    clears_context: bool = False


@dataclass(frozen=True)
class RuntimeLoopResult:
    response_body: dict[str, Any]
    latest_analysis_result: dict[str, Any] | None = None
    latest_analysis: dict[str, Any] | None = None
    latest_selection_payload: dict[str, Any] | None = None
    derived_intent: InteractionIntent = InteractionIntent.UNKNOWN
    clears_context: bool = False


class AssistantTextDeltaExtractor:
    _FIELD_PATTERN = re.compile(r'"assistant_text"\s*:\s*"')

    def __init__(self):
        self._buffer = ""
        self._last_emitted = ""

    def push(self, delta: str) -> str:
        self._buffer += delta
        current = self._extract_partial_value()
        if current is None:
            return ""

        if current.startswith(self._last_emitted):
            new_delta = current[len(self._last_emitted):]
        else:
            new_delta = current
        self._last_emitted = current
        return new_delta

    def _extract_partial_value(self) -> str | None:
        match = self._FIELD_PATTERN.search(self._buffer)
        if match is None:
            return None

        start = match.end()
        end = self._find_string_end(start)
        raw_value = self._buffer[start:end]
        while raw_value:
            try:
                return json.loads(f'"{raw_value}"')
            except json.JSONDecodeError:
                raw_value = raw_value[:-1]

        return ""

    def _find_string_end(self, start: int) -> int:
        index = start
        escaped = False
        while index < len(self._buffer):
            char = self._buffer[index]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                return index
            index += 1
        return len(self._buffer)


class AssistantToolExecutor:
    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        analysis_store: AnalysisStore | None = None,
    ):
        self._tool_registry = tool_registry
        self._analysis_store = analysis_store or NullAnalysisStore()

    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        request: InteractionRequest,
        session_context: SessionContext,
    ) -> ToolExecutionOutcome:
        if tool_name == MODEL_TOOL_SEARCH_MUNICIPALITIES:
            return ToolExecutionOutcome(
                payload=self._tool_registry.execute(
                    ToolName.SEARCH_MUNICIPALITIES,
                    query=str(arguments.get("query") or ""),
                    limit=int(arguments.get("limit") or 5),
                )
            )

        if tool_name == MODEL_TOOL_ANALYZE_MUNICIPALITIES:
            requested_municipalities = [
                str(name)
                for name in arguments.get("municipality_names", [])
                if str(name).strip()
            ]
            result = self._tool_registry.execute(
                ToolName.ANALYZE_MUNICIPALITIES,
                municipality_names=requested_municipalities,
            )
            return self._persist_analysis(
                request=request,
                result=result,
                intent=InteractionIntent.ANALYZE_MUNICIPALITIES,
                requested_municipalities=requested_municipalities,
            )

        if tool_name == MODEL_TOOL_ANALYZE_CURRENT_SELECTION:
            selection_payload = (
                request.context.current_selection_payload
                or session_context.selection_payload
            )
            if not selection_payload:
                raise ValueError("Non esiste una selezione corrente da analizzare.")

            result = self._tool_registry.execute(
                ToolName.ANALYZE_SELECTION,
                selection_payload=selection_payload,
            )
            return self._persist_analysis(
                request=request,
                result=result,
                intent=InteractionIntent.ANALYZE_SELECTION,
            )

        if tool_name == MODEL_TOOL_GET_LAST_ANALYSIS:
            return ToolExecutionOutcome(
                payload=self._tool_registry.execute(ToolName.GET_LAST_ANALYSIS),
                intent=InteractionIntent.EXPLAIN_LAST_ANALYSIS,
            )

        if tool_name == MODEL_TOOL_COMPARE_RECENT_ANALYSES:
            payload = self._tool_registry.execute(ToolName.COMPARE_RECENT_ANALYSES)
            return ToolExecutionOutcome(
                payload=payload,
                analysis_result=payload,
                intent=InteractionIntent.COMPARE_ANALYSES,
            )

        if tool_name == MODEL_TOOL_GET_METHODOLOGY:
            return ToolExecutionOutcome(
                payload=self._tool_registry.execute(ToolName.GET_METHODOLOGY)
            )

        if tool_name == MODEL_TOOL_RESET_ANALYSIS_CONTEXT:
            return ToolExecutionOutcome(
                payload=self._tool_registry.execute(ToolName.RESET_ANALYSIS_CONTEXT),
                intent=InteractionIntent.RESET_SESSION,
                clears_context=True,
            )

        raise ValueError(f"Tool modello non supportato: {tool_name}.")

    def _persist_analysis(
        self,
        *,
        request: InteractionRequest,
        result: dict[str, Any],
        intent: InteractionIntent,
        requested_municipalities: list[str] | None = None,
    ) -> ToolExecutionOutcome:
        requested = requested_municipalities or result.get("requestedMunicipalities", []) or []
        stored = self._analysis_store.save(
            new_stored_analysis(
                source=str(result.get("source") or "analysis"),
                summary=result["summary"],
                requested_municipalities=requested,
                intersected_municipalities=result.get("intersectedMunicipalities", []),
                selection_payload=result.get("selectionPayload"),
                metadata={"channel": request.channel.value},
            )
        )
        analysis_result = dict(result)
        analysis_result["analysisId"] = stored.analysis_id
        last_analysis = {
            "analysisId": stored.analysis_id,
            "summary": analysis_result["summary"],
            "intersectedMunicipalities": analysis_result.get("intersectedMunicipalities", []),
        }
        if requested:
            last_analysis["requestedMunicipalities"] = requested

        return ToolExecutionOutcome(
            payload=analysis_result,
            analysis_result=analysis_result,
            last_analysis=last_analysis,
            selection_payload=analysis_result.get("selectionPayload"),
            intent=intent,
        )


class OpenAiAssistantRuntime:
    def __init__(
        self,
        *,
        llm_provider: Any,
        tool_executor: AssistantToolExecutor,
    ):
        self._llm_provider = llm_provider
        self._tool_executor = tool_executor

    def handle(
        self,
        request: InteractionRequest,
        session_context: SessionContext,
    ) -> InteractionResponse:
        if not request.input.primary_text():
            return self._build_empty_response(request, session_context)

        loop_result = self._run_response_loop(
            request=request,
            session_context=session_context,
            event_callback=None,
        )
        return self._build_interaction_response(
            request=request,
            session_context=session_context,
            loop_result=loop_result,
        )

    def stream_handle(
        self,
        request: InteractionRequest,
        session_context: SessionContext,
    ) -> Generator[dict[str, Any], None, InteractionResponse]:
        if not request.input.primary_text():
            response = self._build_empty_response(request, session_context)
            yield {
                "type": "done",
                "response": self._serialize_response(response),
            }
            return response

        yield {
            "type": "status",
            "phase": "started",
            "message": "Richiesta ricevuta.",
        }
        response_body = yield from self._stream_response_body_events(
            request=request,
            payload=self._build_openai_request_payload(
                request=request,
                session_context=session_context,
                response_input=self._build_openai_input(
                    request=request,
                    session_context=session_context,
                ),
                previous_response_id=self._previous_response_id(session_context),
            )
        )
        latest_analysis_result = None
        latest_analysis = None
        latest_selection_payload = None
        derived_intent = InteractionIntent.UNKNOWN
        clears_context = False

        while True:
            tool_calls = self._extract_tool_calls(response_body)
            if not tool_calls:
                break

            tool_outputs = []
            for tool_call in tool_calls:
                yield {
                    "type": "tool_start",
                    "toolName": tool_call["name"],
                }
                outcome = self._execute_tool_call(
                    tool_call=tool_call,
                    request=request,
                    session_context=session_context,
                )
                if outcome.analysis_result is not None:
                    latest_analysis_result = outcome.analysis_result
                    yield {
                        "type": "analysis_result",
                        "analysisResult": outcome.analysis_result,
                    }
                if outcome.last_analysis is not None:
                    latest_analysis = outcome.last_analysis
                if outcome.selection_payload is not None:
                    latest_selection_payload = outcome.selection_payload
                if outcome.intent is not None:
                    derived_intent = outcome.intent
                clears_context = clears_context or outcome.clears_context
                yield {
                    "type": "tool_result",
                    "toolName": tool_call["name"],
                }
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call["call_id"],
                        "output": json.dumps(
                            self._build_model_tool_output(
                                tool_name=tool_call["name"],
                                payload=outcome.payload,
                            ),
                            ensure_ascii=True,
                        ),
                    }
                )

            response_body = yield from self._stream_response_body_events(
                request=request,
                payload=self._build_openai_request_payload(
                    request=request,
                    session_context=session_context,
                    response_input=tool_outputs,
                    previous_response_id=str(response_body.get("id") or ""),
                )
            )

        response = self._build_interaction_response(
            request=request,
            session_context=session_context,
            loop_result=RuntimeLoopResult(
                response_body=response_body,
                latest_analysis_result=latest_analysis_result,
                latest_analysis=latest_analysis,
                latest_selection_payload=latest_selection_payload,
                derived_intent=derived_intent,
                clears_context=clears_context,
            ),
        )
        return response

    def _build_empty_response(
        self,
        request: InteractionRequest,
        session_context: SessionContext,
    ) -> InteractionResponse:
        return InteractionResponse(
            messages=(
                InteractionMessage(
                    role="assistant",
                    text="Nessun input interpretabile ricevuto.",
                ),
            ),
            commands=(InteractionCommand(intent=InteractionIntent.UNKNOWN),),
            ui_hints={
                "mode": "assistant_runtime",
                "providerMode": "openai",
            },
            audio_output_text="Nessun input interpretabile ricevuto.",
            updated_context=self._build_updated_context(
                request=request,
                session_context=session_context,
                final_intent=InteractionIntent.UNKNOWN,
                response_id=None,
                latest_analysis=None,
                latest_selection_payload=None,
                clears_context=False,
            ),
        )

    def _run_response_loop(
        self,
        *,
        request: InteractionRequest,
        session_context: SessionContext,
        event_callback: Callable[[dict[str, Any]], None] | None,
    ) -> RuntimeLoopResult:
        response_body = self._request_response_body(
            request=request,
            session_context=session_context,
            response_input=self._build_openai_input(
                request=request,
                session_context=session_context,
            ),
            previous_response_id=self._previous_response_id(session_context),
            event_callback=event_callback,
        )

        latest_analysis_result = None
        latest_analysis = None
        latest_selection_payload = None
        derived_intent = InteractionIntent.UNKNOWN
        clears_context = False

        while True:
            tool_calls = self._extract_tool_calls(response_body)
            if not tool_calls:
                break

            tool_outputs = []
            for tool_call in tool_calls:
                self._emit_event(
                    event_callback,
                    {
                        "type": "tool_start",
                        "toolName": tool_call["name"],
                    },
                )
                outcome = self._execute_tool_call(
                    tool_call=tool_call,
                    request=request,
                    session_context=session_context,
                )
                if outcome.analysis_result is not None:
                    latest_analysis_result = outcome.analysis_result
                    self._emit_event(
                        event_callback,
                        {
                            "type": "analysis_result",
                            "analysisResult": outcome.analysis_result,
                        },
                    )
                if outcome.last_analysis is not None:
                    latest_analysis = outcome.last_analysis
                if outcome.selection_payload is not None:
                    latest_selection_payload = outcome.selection_payload
                if outcome.intent is not None:
                    derived_intent = outcome.intent
                clears_context = clears_context or outcome.clears_context
                self._emit_event(
                    event_callback,
                    {
                        "type": "tool_result",
                        "toolName": tool_call["name"],
                    },
                )
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call["call_id"],
                        "output": json.dumps(
                            self._build_model_tool_output(
                                tool_name=tool_call["name"],
                                payload=outcome.payload,
                            ),
                            ensure_ascii=True,
                        ),
                    }
                )

            response_body = self._request_response_body(
                request=request,
                session_context=session_context,
                response_input=tool_outputs,
                previous_response_id=str(response_body.get("id") or ""),
                event_callback=event_callback,
            )

        return RuntimeLoopResult(
            response_body=response_body,
            latest_analysis_result=latest_analysis_result,
            latest_analysis=latest_analysis,
            latest_selection_payload=latest_selection_payload,
            derived_intent=derived_intent,
            clears_context=clears_context,
        )

    def _request_response_body(
        self,
        *,
        request: InteractionRequest,
        session_context: SessionContext,
        response_input: list[dict[str, Any]],
        previous_response_id: str | None,
        event_callback: Callable[[dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        payload = self._build_openai_request_payload(
            request=request,
            session_context=session_context,
            response_input=response_input,
            previous_response_id=previous_response_id,
        )
        if event_callback is None:
            started_at = start_timer()
            try:
                response_body = self._llm_provider.create_response(**payload)
            except Exception as exc:
                log_provider_call(
                    session_id=request.session_id,
                    response_body=None,
                    previous_response_id=previous_response_id,
                    streaming=False,
                    duration_ms=elapsed_ms(started_at),
                    status="error",
                    error=str(exc),
                )
                raise
            log_provider_call(
                session_id=request.session_id,
                response_body=response_body,
                previous_response_id=previous_response_id,
                streaming=False,
                duration_ms=elapsed_ms(started_at),
                status="ok",
            )
            return response_body
        return self._stream_response_body(
            request=request,
            payload=payload,
            event_callback=event_callback,
        )

    def _execute_tool_call(
        self,
        *,
        tool_call: dict[str, Any],
        request: InteractionRequest,
        session_context: SessionContext,
    ) -> ToolExecutionOutcome:
        started_at = start_timer()
        try:
            outcome = self._tool_executor.execute(
                tool_name=tool_call["name"],
                arguments=tool_call["arguments"],
                request=request,
                session_context=session_context,
            )
        except Exception as exc:
            log_tool_call(
                session_id=request.session_id,
                tool_name=tool_call["name"],
                duration_ms=elapsed_ms(started_at),
                status="error",
                error=str(exc),
            )
            raise

        log_tool_call(
            session_id=request.session_id,
            tool_name=tool_call["name"],
            duration_ms=elapsed_ms(started_at),
            status="ok",
            has_analysis=outcome.analysis_result is not None,
        )
        return outcome

    def _stream_response_body(
        self,
        *,
        request: InteractionRequest,
        payload: dict[str, Any],
        event_callback: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        extractor = AssistantTextDeltaExtractor()
        started_at = start_timer()
        final_payload: dict[str, Any] | None = None
        with self._llm_provider.stream_response(**payload) as stream:
            for event in stream:
                event_type = str(getattr(event, "type", ""))
                if event_type == "response.created":
                    response = getattr(event, "response", None)
                    self._emit_event(
                        event_callback,
                        {
                            "type": "status",
                            "phase": "model_created",
                            "responseId": getattr(response, "id", None),
                        },
                    )
                elif event_type == "response.output_item.added":
                    item = getattr(event, "item", None)
                    if getattr(item, "type", None) == "function_call":
                        self._emit_event(
                            event_callback,
                            {
                                "type": "tool_pending",
                                "toolName": getattr(item, "name", ""),
                            },
                        )
                elif event_type == "response.output_text.delta":
                    delta = extractor.push(str(getattr(event, "delta", "")))
                    if delta:
                        self._emit_event(
                            event_callback,
                            {
                                "type": "message_delta",
                                "delta": delta,
                            },
                        )

            final_response = stream.get_final_response()
            final_payload = final_response.model_dump(mode="python")

        log_provider_call(
            session_id=request.session_id,
            response_body=final_payload,
            previous_response_id=payload.get("previous_response_id"),
            streaming=True,
            duration_ms=elapsed_ms(started_at),
            status="ok",
        )
        return final_payload

    def _stream_response_body_events(
        self,
        *,
        request: InteractionRequest,
        payload: dict[str, Any],
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        extractor = AssistantTextDeltaExtractor()
        started_at = start_timer()
        final_payload: dict[str, Any] | None = None
        with self._llm_provider.stream_response(**payload) as stream:
            for event in stream:
                event_type = str(getattr(event, "type", ""))
                if event_type == "response.created":
                    response = getattr(event, "response", None)
                    yield {
                        "type": "status",
                        "phase": "model_created",
                        "responseId": getattr(response, "id", None),
                    }
                elif event_type == "response.output_item.added":
                    item = getattr(event, "item", None)
                    if getattr(item, "type", None) == "function_call":
                        yield {
                            "type": "tool_pending",
                            "toolName": getattr(item, "name", ""),
                        }
                elif event_type == "response.output_text.delta":
                    delta = extractor.push(str(getattr(event, "delta", "")))
                    if delta:
                        yield {
                            "type": "message_delta",
                            "delta": delta,
                        }

            final_response = stream.get_final_response()
            final_payload = final_response.model_dump(mode="python")

        log_provider_call(
            session_id=request.session_id,
            response_body=final_payload,
            previous_response_id=payload.get("previous_response_id"),
            streaming=True,
            duration_ms=elapsed_ms(started_at),
            status="ok",
        )
        return final_payload

    def _build_openai_input(
        self,
        *,
        request: InteractionRequest,
        session_context: SessionContext,
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": self._build_user_prompt(
                            request=request,
                            session_context=session_context,
                        ),
                    }
                ],
            }
        ]

    def _build_openai_request_payload(
        self,
        *,
        request: InteractionRequest,
        session_context: SessionContext,
        response_input: list[dict[str, Any]],
        previous_response_id: str | None,
    ) -> dict[str, Any]:
        del request, session_context
        return {
            "instructions": self._build_instructions(),
            "input": response_input,
            "tools": self._build_model_tools(),
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "previous_response_id": previous_response_id,
            "text": {
                "format": self._build_final_response_format(),
                "verbosity": "low",
            },
        }

    def _build_interaction_response(
        self,
        *,
        request: InteractionRequest,
        session_context: SessionContext,
        loop_result: RuntimeLoopResult,
    ) -> InteractionResponse:
        final_payload = self._parse_final_payload(loop_result.response_body)
        ui_actions = filter_ui_actions(final_payload.get("ui_actions"))
        final_intent = self._resolve_final_intent(
            raw_intent=final_payload.get("intent"),
            fallback=loop_result.derived_intent,
        )
        message_text = (
            str(final_payload.get("assistant_text") or "").strip()
            or str(final_payload.get("clarification_question") or "").strip()
            or "Richiesta completata."
        )
        updated_context = self._build_updated_context(
            request=request,
            session_context=session_context,
            final_intent=final_intent,
            response_id=str(loop_result.response_body.get("id") or ""),
            latest_analysis=loop_result.latest_analysis,
            latest_selection_payload=loop_result.latest_selection_payload,
            clears_context=loop_result.clears_context,
        )

        return InteractionResponse(
            messages=(InteractionMessage(role="assistant", text=message_text),),
            commands=(InteractionCommand(intent=final_intent),),
            analysis_result=loop_result.latest_analysis_result,
            ui_hints={
                "mode": final_intent.value,
                "providerMode": "openai",
                "runtime": "responses_api",
                "needsClarification": bool(final_payload.get("needs_clarification")),
                "followUpSuggestions": final_payload.get("follow_up_suggestions", []),
                "citationsInternal": final_payload.get("citations_internal", []),
                "uiActions": ui_actions,
            },
            audio_output_text=message_text,
            updated_context=updated_context,
        )

    @staticmethod
    def _build_model_tool_output(
        *,
        tool_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_name in {
            MODEL_TOOL_ANALYZE_MUNICIPALITIES,
            MODEL_TOOL_ANALYZE_CURRENT_SELECTION,
        }:
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            summary_items = summary.get("items") if isinstance(summary.get("items"), list) else []
            return {
                "analysisId": payload.get("analysisId"),
                "source": payload.get("source"),
                "requestedMunicipalities": payload.get("requestedMunicipalities", []),
                "intersectedMunicipalities": payload.get("intersectedMunicipalities", []),
                "summary": {
                    "totalCo2": summary.get("totalCo2"),
                    "hasSupportedVegetation": summary.get("hasSupportedVegetation"),
                    "items": summary_items[:8],
                },
            }

        if tool_name == MODEL_TOOL_COMPARE_RECENT_ANALYSES:
            return {
                "current": payload.get("current"),
                "previous": payload.get("previous"),
                "delta": payload.get("delta"),
            }

        return payload

    @staticmethod
    def _serialize_response(response: InteractionResponse) -> dict[str, Any]:
        return {
            "messages": [
                {
                    "role": message_item.role,
                    "text": message_item.text,
                }
                for message_item in response.messages
            ],
            "analysisResult": response.analysis_result,
            "uiHints": response.ui_hints,
        }

    @staticmethod
    def _emit_event(
        event_callback: Callable[[dict[str, Any]], None] | None,
        event: dict[str, Any],
    ) -> None:
        if event_callback is not None:
            event_callback(event)

    def _build_updated_context(
        self,
        *,
        request: InteractionRequest,
        session_context: SessionContext,
        final_intent: InteractionIntent,
        response_id: str | None,
        latest_analysis: dict[str, Any] | None,
        latest_selection_payload: dict[str, Any] | None,
        clears_context: bool,
    ) -> SessionContext:
        if clears_context or final_intent is InteractionIntent.RESET_SESSION:
            return SessionContext(last_intent=InteractionIntent.RESET_SESSION)

        metadata = dict(session_context.metadata)
        if response_id:
            metadata["openai_previous_response_id"] = response_id
        elif "openai_previous_response_id" in metadata:
            metadata.pop("openai_previous_response_id")

        return SessionContext(
            selection_payload=(
                latest_selection_payload
                or request.context.current_selection_payload
                or session_context.selection_payload
            ),
            last_analysis=latest_analysis or session_context.last_analysis,
            last_intent=final_intent,
            metadata=metadata,
        )

    @staticmethod
    def _previous_response_id(session_context: SessionContext) -> str | None:
        previous_response_id = session_context.metadata.get("openai_previous_response_id")
        if isinstance(previous_response_id, str) and previous_response_id.strip():
            return previous_response_id
        return None

    @staticmethod
    def _extract_tool_calls(response_body: dict[str, Any]) -> list[dict[str, Any]]:
        tool_calls: list[dict[str, Any]] = []
        for item in response_body.get("output", []):
            if item.get("type") != "function_call":
                continue

            raw_arguments = item.get("arguments")
            parsed_arguments = raw_arguments if isinstance(raw_arguments, dict) else {}
            if isinstance(raw_arguments, str) and raw_arguments.strip():
                parsed_arguments = json.loads(raw_arguments)

            tool_calls.append(
                {
                    "call_id": str(item.get("call_id") or item.get("id") or ""),
                    "name": str(item.get("name") or ""),
                    "arguments": parsed_arguments if isinstance(parsed_arguments, dict) else {},
                }
            )
        return tool_calls

    @staticmethod
    def _parse_final_payload(response_body: dict[str, Any]) -> dict[str, Any]:
        raw_text = response_body.get("output_text")
        if not isinstance(raw_text, str) or not raw_text.strip():
            for item in response_body.get("output", []):
                if item.get("type") != "message":
                    continue
                for content in item.get("content", []):
                    text = content.get("text")
                    if isinstance(text, str) and text.strip():
                        raw_text = text
                        break
                if isinstance(raw_text, str) and raw_text.strip():
                    break

        if not isinstance(raw_text, str) or not raw_text.strip():
            raise ValueError("OpenAI provider returned empty structured response.")

        payload = json.loads(raw_text)
        if not isinstance(payload, dict):
            raise ValueError("OpenAI provider returned invalid structured payload.")
        return payload

    @staticmethod
    def _resolve_final_intent(
        *,
        raw_intent: Any,
        fallback: InteractionIntent,
    ) -> InteractionIntent:
        if isinstance(raw_intent, str):
            try:
                return InteractionIntent(raw_intent)
            except ValueError:
                return fallback
        return fallback

    @staticmethod
    def _build_instructions() -> str:
        return (
            "Sei assistente WebGIS di Carta della Natura. "
            "Rispondi sempre in italiano. "
            "Non inventare mai dati GIS: per ogni fatto numerico o analitico devi usare i tool. "
            "Categorie vegetazionali e regole CO2 presenti nel grounding sono fonte descrittiva, non numerica: "
            "valori finali devono arrivare solo dai tool. "
            "Quando citi numeri, formatta in italiano e arrotonda a massimo 2 decimali. "
            "Non mostrare precisione grezza lunga da float. "
            "Se utente cita comuni in modo parziale o ambiguo, usa prima search_municipalities. "
            "Se utente chiede analisi su selezione corrente, usa analyze_current_selection solo se selezione disponibile. "
            "Se utente chiede spiegazioni o confronto di risultati recenti, usa get_last_analysis o compare_recent_analyses. "
            "Per richieste metodologiche usa get_methodology prima di spiegare. "
            "Se manca contesto sufficiente, non improvvisare: chiedi chiarimento. "
            "Azioni UI consentite: show_last_analysis, open_report_panel, show_legend, focus_map_results. "
            "Non emettere altre ui_actions. "
            "Mantieni risposte brevi: massimo 4 frasi operative. "
            "Dopo aver usato i tool, restituisci solo JSON conforme allo schema finale."
        )

    @staticmethod
    def _build_user_prompt(
        *,
        request: InteractionRequest,
        session_context: SessionContext,
    ) -> str:
        payload = {
            "user_message": request.input.primary_text(),
            "ui_context": {
                "selectedMunicipalities": list(request.context.selected_municipalities),
                "hasCurrentSelection": bool(request.context.current_selection_payload or session_context.selection_payload),
                "selectionSource": request.context.metadata.get("selectionSource"),
                "mapExtent": request.context.current_map_extent,
            },
            "analysis_context": {
                "lastAnalysis": session_context.last_analysis,
            },
            "conversation_context": {
                "lastIntent": session_context.last_intent.value if session_context.last_intent else None,
            },
            "grounding": {
                "availableTools": list(MODEL_TOOL_NAMES),
                "vegetationCategories": [
                    {
                        "key": item["key"],
                        "label": item["label"],
                        "co2PerHectare": item["co2PerHectare"],
                    }
                    for item in serialize_categories()
                ],
                "methodology": get_methodology(),
                "rules": [
                    "Numeri GIS solo da tool backend.",
                    "Selezione corrente disponibile solo se hasCurrentSelection e true.",
                    "Confronti recenti basati sulle ultime due analisi in sessione.",
                ],
            },
        }
        return json.dumps(payload, ensure_ascii=True)

    @staticmethod
    def _build_final_response_format() -> dict[str, Any]:
        return {
            "type": "json_schema",
            "name": "assistant_turn_output",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": [intent.value for intent in InteractionIntent],
                    },
                    "assistant_text": {"type": "string"},
                    "needs_clarification": {"type": "boolean"},
                    "clarification_question": {"type": "string"},
                    "ui_actions": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": list(ALLOWED_UI_ACTIONS),
                        },
                    },
                    "citations_internal": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "follow_up_suggestions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "intent",
                    "assistant_text",
                    "needs_clarification",
                    "clarification_question",
                    "ui_actions",
                    "citations_internal",
                    "follow_up_suggestions",
                ],
                "additionalProperties": False,
            },
        }

    @staticmethod
    def _build_model_tools() -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": MODEL_TOOL_SEARCH_MUNICIPALITIES,
                "description": "Use this when utente cita comuni in modo parziale, ambiguo o con dubbi di spelling.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query", "limit"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": MODEL_TOOL_ANALYZE_MUNICIPALITIES,
                "description": "Use this when utente chiede analisi di uno o più comuni già risolti in modo affidabile.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "municipality_names": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["municipality_names"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": MODEL_TOOL_ANALYZE_CURRENT_SELECTION,
                "description": "Use this when utente vuole analizzare la selezione mappa corrente già presente nel contesto UI.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": MODEL_TOOL_GET_LAST_ANALYSIS,
                "description": "Use this when utente chiede spiegazione o richiamo di ultima analisi.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": MODEL_TOOL_COMPARE_RECENT_ANALYSES,
                "description": "Use this when utente chiede confronto tra ultime due analisi recenti.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": MODEL_TOOL_GET_METHODOLOGY,
                "description": "Use this when utente chiede come vengono calcolati risultati o quale metodologia è stata usata.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": MODEL_TOOL_RESET_ANALYSIS_CONTEXT,
                "description": "Use this when utente chiede reset esplicito di sessione o contesto analitico.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        ]
