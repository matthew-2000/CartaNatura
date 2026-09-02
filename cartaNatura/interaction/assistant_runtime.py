"""Provider-neutral assistant runtime for conversational turns."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any, Callable, Generator

from cartaNatura.domain.economics import PRICE_OPTIONS
from cartaNatura.domain.vegetation import serialize_categories

from .analysis_store import AnalysisStore, NullAnalysisStore, create_stored_analysis
from .models import (
    InteractionCommand,
    InteractionIntent,
    InteractionMessage,
    InteractionRequest,
    InteractionResponse,
    SessionContext,
)
from .observability import elapsed_ms, log_provider_call, log_tool_call, start_timer
from .llm import LlmProviderUnavailableError
from .tools import ToolName
from .tools.registry import ToolRegistry
from .ui_actions import ALLOWED_UI_ACTIONS, filter_ui_actions

MODEL_TOOL_SEARCH_MUNICIPALITIES = "search_municipalities"
MODEL_TOOL_ANALYZE_MUNICIPALITIES = "analyze_municipalities"
MODEL_TOOL_ANALYZE_CURRENT_SELECTION = "analyze_current_selection"
MODEL_TOOL_CALCULATE_ECONOMIC_VALUE = "calculate_economic_value"
MODEL_TOOL_COMPARE_ECONOMIC_SCENARIOS = "compare_economic_scenarios"
MODEL_TOOL_GET_LAST_ANALYSIS = "get_last_analysis"
MODEL_TOOL_COMPARE_RECENT_ANALYSES = "compare_recent_analyses"
MODEL_TOOL_LIST_RECENT_ANALYSES = "list_recent_analyses"
MODEL_TOOL_COMPARE_SAVED_ANALYSES = "compare_saved_analyses"
MODEL_TOOL_GET_METHODOLOGY = "get_methodology"
MODEL_TOOL_RESET_ANALYSIS_CONTEXT = "reset_analysis_context"
MODEL_TOOL_PREPARE_REPORT = "prepare_report"
MODEL_TOOL_FILTER_LAST_ANALYSIS = "filter_last_analysis_categories"

MODEL_TOOL_NAMES = (
    MODEL_TOOL_SEARCH_MUNICIPALITIES,
    MODEL_TOOL_ANALYZE_MUNICIPALITIES,
    MODEL_TOOL_ANALYZE_CURRENT_SELECTION,
    MODEL_TOOL_CALCULATE_ECONOMIC_VALUE,
    MODEL_TOOL_COMPARE_ECONOMIC_SCENARIOS,
    MODEL_TOOL_GET_LAST_ANALYSIS,
    MODEL_TOOL_COMPARE_RECENT_ANALYSES,
    MODEL_TOOL_LIST_RECENT_ANALYSES,
    MODEL_TOOL_COMPARE_SAVED_ANALYSES,
    MODEL_TOOL_GET_METHODOLOGY,
    MODEL_TOOL_RESET_ANALYSIS_CONTEXT,
    MODEL_TOOL_PREPARE_REPORT,
    MODEL_TOOL_FILTER_LAST_ANALYSIS,
)


@dataclass(frozen=True)
class ToolExecutionOutcome:
    payload: dict[str, Any]
    analysis_result: dict[str, Any] | None = None
    economic_result: dict[str, Any] | None = None
    scenario_comparison: dict[str, Any] | None = None
    report_context: dict[str, Any] | None = None
    map_filter: dict[str, Any] | None = None
    last_analysis_details: dict[str, Any] | None = None
    history_result: dict[str, Any] | None = None
    search_result: dict[str, Any] | None = None
    tool_error: str | None = None
    last_analysis: dict[str, Any] | None = None
    selection_payload: dict[str, Any] | None = None
    intent: InteractionIntent | None = None
    clears_context: bool = False


@dataclass(frozen=True)
class RuntimeLoopResult:
    response_body: dict[str, Any]
    latest_analysis_result: dict[str, Any] | None = None
    latest_economic_result: dict[str, Any] | None = None
    latest_scenario_comparison: dict[str, Any] | None = None
    latest_report_context: dict[str, Any] | None = None
    latest_map_filter: dict[str, Any] | None = None
    latest_last_analysis_details: dict[str, Any] | None = None
    latest_history_result: dict[str, Any] | None = None
    latest_search_result: dict[str, Any] | None = None
    latest_tool_error: str | None = None
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
            payload = self._tool_registry.execute(
                ToolName.SEARCH_MUNICIPALITIES,
                query=str(arguments.get("query") or ""),
                limit=int(arguments.get("limit") or 5),
            )
            return ToolExecutionOutcome(
                payload=payload,
                search_result=payload,
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
                or request.input.geo_selection
            )
            if not selection_payload:
                raise ValueError(
                    "Non c'è una selezione corrente sulla mappa. Seleziona uno o più comuni "
                    "oppure disegna un'area, poi riprova."
                )

            result = self._tool_registry.execute(
                ToolName.ANALYZE_SELECTION,
                selection_payload=selection_payload,
            )
            return self._persist_analysis(
                request=request,
                result=result,
                intent=InteractionIntent.ANALYZE_SELECTION,
            )

        if tool_name == MODEL_TOOL_CALCULATE_ECONOMIC_VALUE:
            payload = self._tool_registry.execute(
                ToolName.CALCULATE_ECONOMIC_VALUE,
                scenario_key=str(arguments.get("scenario_key") or ""),
            )
            last_analysis = dict(session_context.last_analysis or {})
            last_analysis.update(
                {
                    "analysisId": payload.get("analysisId"),
                    "economicResult": payload,
                }
            )
            return ToolExecutionOutcome(
                payload=payload,
                economic_result=payload,
                last_analysis=last_analysis,
                intent=InteractionIntent.COMPARE_ECONOMIC_SCENARIOS,
            )

        if tool_name == MODEL_TOOL_COMPARE_ECONOMIC_SCENARIOS:
            payload = self._tool_registry.execute(ToolName.COMPARE_ECONOMIC_SCENARIOS)
            return ToolExecutionOutcome(
                payload=payload,
                scenario_comparison=payload,
                intent=InteractionIntent.COMPARE_ECONOMIC_SCENARIOS,
            )

        if tool_name == MODEL_TOOL_GET_LAST_ANALYSIS:
            payload = self._tool_registry.execute(ToolName.GET_LAST_ANALYSIS)
            return ToolExecutionOutcome(
                payload=payload,
                last_analysis_details=payload,
                intent=InteractionIntent.EXPLAIN_LAST_ANALYSIS,
            )

        if tool_name == MODEL_TOOL_COMPARE_RECENT_ANALYSES:
            payload = self._tool_registry.execute(
                ToolName.COMPARE_RECENT_ANALYSES,
                limit=int(arguments.get("recent_count") or 2),
            )
            return ToolExecutionOutcome(
                payload=payload,
                analysis_result=payload,
                intent=InteractionIntent.COMPARE_ANALYSES,
            )

        if tool_name == MODEL_TOOL_LIST_RECENT_ANALYSES:
            payload = self._tool_registry.execute(
                ToolName.LIST_RECENT_ANALYSES,
                limit=int(arguments.get("limit") or 10),
            )
            return ToolExecutionOutcome(
                payload=payload,
                history_result=payload,
                intent=InteractionIntent.EXPLAIN_LAST_ANALYSIS,
            )

        if tool_name == MODEL_TOOL_FILTER_LAST_ANALYSIS:
            payload = self._tool_registry.execute(
                ToolName.FILTER_ANALYSIS_CATEGORIES,
                category_names=[
                    str(item)
                    for item in arguments.get("category_names", [])
                    if str(item).strip()
                ],
                displayed_analysis_id=request.context.displayed_analysis_id,
                show_all=bool(arguments.get("show_all")),
            )
            return ToolExecutionOutcome(
                payload=payload,
                map_filter=payload,
                intent=InteractionIntent.EXTRACT_FOREST_INFORMATION,
            )

        if tool_name == MODEL_TOOL_COMPARE_SAVED_ANALYSES:
            selectors = [
                str(item)
                for item in arguments.get("selectors", [])
                if str(item).strip()
            ]
            payload = self._tool_registry.execute(
                ToolName.COMPARE_SAVED_ANALYSES,
                selectors=selectors,
            )
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

        if tool_name == MODEL_TOOL_PREPARE_REPORT:
            payload = self._tool_registry.execute(ToolName.PREPARE_REPORT)
            return ToolExecutionOutcome(
                payload=payload,
                report_context=payload,
                intent=InteractionIntent.GENERATE_REPORT,
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
            create_stored_analysis(
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


class AssistantRuntime:
    def __init__(
        self,
        *,
        llm_provider: Any,
        tool_executor: AssistantToolExecutor,
    ):
        self._llm_provider = llm_provider
        self._tool_executor = tool_executor

    @property
    def provider_name(self) -> str:
        return str(getattr(self._llm_provider, "provider_name", "openai"))

    @property
    def provider_model(self) -> str | None:
        model = getattr(self._llm_provider, "model", None)
        return str(model) if model else None

    @property
    def runtime_name(self) -> str:
        return str(getattr(self._llm_provider, "runtime_name", "responses_api"))

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
            "stage": "started",
            "message": "Richiesta ricevuta.",
        }
        current_turn_input = self._build_model_input(
            request=request,
            session_context=session_context,
        )
        provider_tool_exchanges: list[dict[str, Any]] = []
        response_body = yield from self._stream_response_body_events(
            request=request,
            payload=self._build_model_request_payload(
                request=request,
                session_context=session_context,
                response_input=current_turn_input,
                previous_response_id=self._previous_response_id(session_context),
                provider_metadata=self._build_provider_metadata(
                    current_turn_input=current_turn_input,
                    tool_exchanges=provider_tool_exchanges,
                    response_phase="tool_planning",
                ),
            ),
            phase="planning",
        )
        latest_analysis_result = None
        latest_economic_result = None
        latest_scenario_comparison = None
        latest_report_context = None
        latest_map_filter = None
        latest_last_analysis_details = None
        latest_history_result = None
        latest_search_result = None
        latest_tool_error = None
        latest_analysis = None
        latest_selection_payload = None
        derived_intent = InteractionIntent.UNKNOWN
        clears_context = False
        tool_rounds = 0
        tool_request, tool_context = request, session_context

        while True:
            tool_calls = self._extract_tool_calls(response_body)
            if not tool_calls:
                break
            tool_rounds += 1
            if tool_rounds > 6:
                raise LlmProviderUnavailableError(
                    "L'assistente non è riuscito a completare l'operazione. Riformula la richiesta in modo più specifico."
                )

            tool_outputs = []
            for tool_call in tool_calls:
                yield {
                    "type": "tool_start",
                    "toolName": tool_call["name"],
                    "toolCallId": tool_call["call_id"],
                }
                outcome = self._execute_tool_call(
                    tool_call=tool_call,
                    request=tool_request,
                    session_context=tool_context,
                )
                tool_request, tool_context = self._advance_tool_context(tool_request, tool_context, outcome)
                if outcome.clears_context:
                    latest_analysis_result = latest_analysis = latest_selection_payload = None
                    latest_economic_result = latest_scenario_comparison = latest_report_context = None
                    latest_map_filter = latest_last_analysis_details = latest_history_result = latest_search_result = None
                if outcome.analysis_result is not None and outcome.analysis_result.get("clipped") is not None:
                    # A new area invalidates values and filters from an earlier
                    # area in this same turn, just as it does in the WebGIS UI.
                    latest_economic_result = latest_scenario_comparison = latest_report_context = None
                    latest_map_filter = latest_last_analysis_details = None
                if outcome.analysis_result is not None:
                    latest_analysis_result = outcome.analysis_result
                    yield {
                        "type": "analysis_result",
                        "analysisResult": outcome.analysis_result,
                    }
                if outcome.economic_result is not None:
                    latest_economic_result = outcome.economic_result
                if outcome.scenario_comparison is not None:
                    latest_scenario_comparison = outcome.scenario_comparison
                if outcome.report_context is not None:
                    latest_report_context = outcome.report_context
                if outcome.map_filter is not None:
                    latest_map_filter = outcome.map_filter
                if outcome.last_analysis_details is not None:
                    latest_last_analysis_details = outcome.last_analysis_details
                if outcome.history_result is not None:
                    latest_history_result = outcome.history_result
                if outcome.search_result is not None:
                    latest_search_result = outcome.search_result
                latest_tool_error = outcome.tool_error
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
                    "toolCallId": tool_call["call_id"],
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

            provider_tool_exchanges.append(
                {
                    "tool_calls": tool_calls,
                    "tool_outputs": tool_outputs,
                }
            )
            # The model decides whether to call another tool or answer. A GIS
            # result is not necessarily the end of a compound request.
            response_phase = "tool_planning"
            yield {
                "type": "status",
                "stage": "synthesizing_response",
                "phase": response_phase,
                "message": self._tool_completion_message(response_phase),
            }
            response_body = yield from self._stream_response_body_events(
                request=request,
                payload=self._build_model_request_payload(
                    request=request,
                    session_context=session_context,
                    response_input=tool_outputs,
                    previous_response_id=str(response_body.get("id") or ""),
                    provider_metadata=self._build_provider_metadata(
                        current_turn_input=current_turn_input,
                        tool_exchanges=provider_tool_exchanges,
                        response_phase=response_phase,
                    ),
                ),
                phase=response_phase,
            )

        if self._parse_final_payload(response_body).get("_unstructured"):
            response_body = yield from self._stream_response_body_events(
                request=request,
                payload=self._build_model_request_payload(
                    request=request,
                    session_context=session_context,
                    response_input=self._formatting_request(),
                    previous_response_id=str(response_body.get("id") or ""),
                    provider_metadata=self._build_provider_metadata(
                        current_turn_input=current_turn_input,
                        tool_exchanges=provider_tool_exchanges,
                        response_phase="final",
                    ),
                ),
                phase="final",
            )

        response = self._build_interaction_response(
            request=request,
            session_context=session_context,
            loop_result=RuntimeLoopResult(
                response_body=response_body,
                latest_analysis_result=latest_analysis_result,
                latest_economic_result=latest_economic_result,
                latest_scenario_comparison=latest_scenario_comparison,
                latest_report_context=latest_report_context,
                latest_map_filter=latest_map_filter,
                latest_last_analysis_details=latest_last_analysis_details,
                latest_history_result=latest_history_result,
                latest_search_result=latest_search_result,
                latest_tool_error=latest_tool_error,
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
                "providerMode": self.provider_name,
                "providerModel": self.provider_model,
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
                assistant_text="Nessun input interpretabile ricevuto.",
            ),
        )

    def _run_response_loop(
        self,
        *,
        request: InteractionRequest,
        session_context: SessionContext,
        event_callback: Callable[[dict[str, Any]], None] | None,
    ) -> RuntimeLoopResult:
        current_turn_input = self._build_model_input(
            request=request,
            session_context=session_context,
        )
        provider_tool_exchanges: list[dict[str, Any]] = []
        response_body = self._request_response_body(
            request=request,
            session_context=session_context,
            response_input=current_turn_input,
            previous_response_id=self._previous_response_id(session_context),
            event_callback=event_callback,
            provider_metadata=self._build_provider_metadata(
                current_turn_input=current_turn_input,
                tool_exchanges=provider_tool_exchanges,
                response_phase="tool_planning",
            ),
        )

        latest_analysis_result = None
        latest_economic_result = None
        latest_scenario_comparison = None
        latest_report_context = None
        latest_map_filter = None
        latest_last_analysis_details = None
        latest_history_result = None
        latest_search_result = None
        latest_tool_error = None
        latest_analysis = None
        latest_selection_payload = None
        derived_intent = InteractionIntent.UNKNOWN
        clears_context = False
        tool_rounds = 0
        tool_request, tool_context = request, session_context

        while True:
            tool_calls = self._extract_tool_calls(response_body)
            if not tool_calls:
                break
            tool_rounds += 1
            if tool_rounds > 6:
                raise LlmProviderUnavailableError(
                    "L'assistente non è riuscito a completare l'operazione. Riformula la richiesta in modo più specifico."
                )

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
                    request=tool_request,
                    session_context=tool_context,
                )
                tool_request, tool_context = self._advance_tool_context(tool_request, tool_context, outcome)
                if outcome.clears_context:
                    latest_analysis_result = latest_analysis = latest_selection_payload = None
                    latest_economic_result = latest_scenario_comparison = latest_report_context = None
                    latest_map_filter = latest_last_analysis_details = latest_history_result = latest_search_result = None
                if outcome.analysis_result is not None and outcome.analysis_result.get("clipped") is not None:
                    # A new area invalidates values and filters from an earlier
                    # area in this same turn, just as it does in the WebGIS UI.
                    latest_economic_result = latest_scenario_comparison = latest_report_context = None
                    latest_map_filter = latest_last_analysis_details = None
                if outcome.analysis_result is not None:
                    latest_analysis_result = outcome.analysis_result
                    self._emit_event(
                        event_callback,
                        {
                            "type": "analysis_result",
                            "analysisResult": outcome.analysis_result,
                        },
                    )
                if outcome.economic_result is not None:
                    latest_economic_result = outcome.economic_result
                if outcome.scenario_comparison is not None:
                    latest_scenario_comparison = outcome.scenario_comparison
                if outcome.report_context is not None:
                    latest_report_context = outcome.report_context
                if outcome.map_filter is not None:
                    latest_map_filter = outcome.map_filter
                if outcome.last_analysis_details is not None:
                    latest_last_analysis_details = outcome.last_analysis_details
                if outcome.history_result is not None:
                    latest_history_result = outcome.history_result
                if outcome.search_result is not None:
                    latest_search_result = outcome.search_result
                latest_tool_error = outcome.tool_error
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

            provider_tool_exchanges.append(
                {
                    "tool_calls": tool_calls,
                    "tool_outputs": tool_outputs,
                }
            )
            # The model decides whether to call another tool or answer. A GIS
            # result is not necessarily the end of a compound request.
            response_phase = "tool_planning"
            response_body = self._request_response_body(
                request=request,
                session_context=session_context,
                response_input=tool_outputs,
                previous_response_id=str(response_body.get("id") or ""),
                event_callback=event_callback,
                provider_metadata=self._build_provider_metadata(
                    current_turn_input=current_turn_input,
                    tool_exchanges=provider_tool_exchanges,
                    response_phase=response_phase,
                ),
            )

        if self._parse_final_payload(response_body).get("_unstructured"):
            response_body = self._request_response_body(
                request=request,
                session_context=session_context,
                response_input=self._formatting_request(),
                previous_response_id=str(response_body.get("id") or ""),
                event_callback=event_callback,
                provider_metadata=self._build_provider_metadata(
                    current_turn_input=current_turn_input,
                    tool_exchanges=provider_tool_exchanges,
                    response_phase="final",
                ),
            )

        return RuntimeLoopResult(
            response_body=response_body,
            latest_analysis_result=latest_analysis_result,
            latest_economic_result=latest_economic_result,
            latest_scenario_comparison=latest_scenario_comparison,
            latest_report_context=latest_report_context,
            latest_map_filter=latest_map_filter,
            latest_last_analysis_details=latest_last_analysis_details,
            latest_history_result=latest_history_result,
            latest_search_result=latest_search_result,
            latest_tool_error=latest_tool_error,
            latest_analysis=latest_analysis,
            latest_selection_payload=latest_selection_payload,
            derived_intent=derived_intent,
            clears_context=clears_context,
        )

    @staticmethod
    def _advance_tool_context(
        request: InteractionRequest,
        context: SessionContext,
        outcome: ToolExecutionOutcome,
    ) -> tuple[InteractionRequest, SessionContext]:
        if outcome.clears_context:
            return replace(request, context=type(request.context)()), SessionContext()
        if outcome.last_analysis is not None:
            context = replace(
                context,
                last_analysis=outcome.last_analysis,
                selection_payload=outcome.selection_payload or context.selection_payload,
            )
        if outcome.analysis_result is not None and outcome.analysis_result.get("clipped") is not None:
            request = replace(request, context=replace(
                request.context,
                displayed_analysis_id=outcome.analysis_result.get("analysisId"),
                selected_municipalities=(),
                current_selection_payload=None,
            ))
        return request, context

    def _request_response_body(
        self,
        *,
        request: InteractionRequest,
        session_context: SessionContext,
        response_input: list[dict[str, Any]],
        previous_response_id: str | None,
        event_callback: Callable[[dict[str, Any]], None] | None,
        provider_metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = self._build_model_request_payload(
            request=request,
            session_context=session_context,
            response_input=response_input,
            previous_response_id=previous_response_id,
            provider_metadata=provider_metadata,
        )
        if event_callback is None:
            started_at = start_timer()
            try:
                response_body = self._llm_provider.create_response(**payload)
            except Exception as exc:
                log_provider_call(
                    provider=self.provider_name,
                    model=self.provider_model,
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
                provider=self.provider_name,
                model=self.provider_model,
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
        except ValueError as exc:
            log_tool_call(
                session_id=request.session_id,
                tool_name=tool_call["name"],
                duration_ms=elapsed_ms(started_at),
                status="error",
                error=str(exc),
            )
            return ToolExecutionOutcome(
                payload={"ok": False, "error": str(exc)},
                tool_error=str(exc),
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
                            "stage": "model_created",
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
            provider=self.provider_name,
            model=self.provider_model,
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
        phase: str = "planning",
        emit_message_deltas: bool = True,
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
                        "stage": "model_created",
                        "phase": phase,
                        "message": self._stream_model_created_message(phase),
                        "responseId": getattr(response, "id", None),
                    }
                elif event_type == "response.output_item.added":
                    item = getattr(event, "item", None)
                    if getattr(item, "type", None) == "function_call":
                        yield {
                            "type": "tool_pending",
                            "toolName": getattr(item, "name", ""),
                        }
                elif event_type == "response.output_text.delta" and emit_message_deltas:
                    delta = extractor.push(str(getattr(event, "delta", "")))
                    if delta:
                        yield {
                            "type": "message_delta",
                            "delta": delta,
                        }

            final_response = stream.get_final_response()
            final_payload = final_response.model_dump(mode="python")

        log_provider_call(
            provider=self.provider_name,
            model=self.provider_model,
            session_id=request.session_id,
            response_body=final_payload,
            previous_response_id=payload.get("previous_response_id"),
            streaming=True,
            duration_ms=elapsed_ms(started_at),
            status="ok",
        )
        return final_payload

    @staticmethod
    def _stream_model_created_message(phase: str) -> str:
        if phase in {"synthesis", "final"}:
            return "L'assistente sta scrivendo la risposta finale."
        return "L'assistente sta interpretando la richiesta."

    @staticmethod
    def _tool_completion_message(phase: str) -> str:
        if phase == "tool_planning":
            return "Strumenti completati. Continuo l'elaborazione."
        return "Strumenti completati. Preparo la risposta finale."

    @staticmethod
    def _build_provider_metadata(
        *,
        current_turn_input: list[dict[str, Any]],
        tool_exchanges: list[dict[str, Any]],
        response_phase: str,
    ) -> dict[str, Any]:
        return {
            "ollama_current_turn_input": current_turn_input,
            "ollama_tool_exchanges": tool_exchanges,
            "ollama_response_phase": response_phase,
        }

    def _build_model_input(
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

    def _build_model_request_payload(
        self,
        *,
        request: InteractionRequest,
        session_context: SessionContext,
        response_input: list[dict[str, Any]],
        previous_response_id: str | None,
        provider_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        formatting_final_answer = (provider_metadata or {}).get("ollama_response_phase") == "final"
        return {
            "instructions": self._build_instructions(),
            "input": response_input,
            "tools": [] if formatting_final_answer else self._build_model_tools(),
            "tool_choice": "none" if formatting_final_answer else "auto",
            "parallel_tool_calls": False,
            "previous_response_id": previous_response_id,
            "conversation_messages": self._conversation_messages(session_context),
            "provider_metadata": provider_metadata or {},
            "text": {
                "format": self._build_final_response_format(),
                "verbosity": "low",
            },
        }

    @staticmethod
    def _formatting_request() -> list[dict[str, Any]]:
        return [{
            "role": "user",
            "content": [{
                "type": "input_text",
                "text": "Le operazioni sono concluse. Restituisci la risposta finale nel formato JSON richiesto, usando i risultati già ottenuti e senza nuovi calcoli.",
            }],
        }]

    def _build_interaction_response(
        self,
        *,
        request: InteractionRequest,
        session_context: SessionContext,
        loop_result: RuntimeLoopResult,
    ) -> InteractionResponse:
        final_payload = self._parse_final_payload(loop_result.response_body)
        if final_payload.get("_unstructured"):
            raise LlmProviderUnavailableError("Il modello LLM non ha rispettato il formato della risposta finale.")
        message_text = (
            str(final_payload.get("assistant_text") or "").strip()
            or str(final_payload.get("clarification_question") or "").strip()
        )
        if not message_text:
            raise LlmProviderUnavailableError("Il modello LLM ha restituito una risposta testuale vuota.")
        ui_actions = filter_ui_actions(final_payload.get("ui_actions"))
        follow_up_suggestions = final_payload.get("follow_up_suggestions", [])
        final_intent = self._resolve_final_intent(
            raw_intent=final_payload.get("intent"),
            fallback=loop_result.derived_intent,
        )
        needs_clarification = bool(final_payload.get("needs_clarification"))
        # Only an executed tool can reset application state. Merely talking
        # about reset must never erase a session or its saved analyses.
        reset_completed = loop_result.clears_context and loop_result.latest_analysis is None
        updated_context = self._build_updated_context(
            request=request,
            session_context=session_context,
            final_intent=final_intent,
            response_id=str(loop_result.response_body.get("id") or ""),
            latest_analysis=loop_result.latest_analysis,
            latest_selection_payload=loop_result.latest_selection_payload,
            clears_context=loop_result.clears_context,
            assistant_text=message_text,
        )

        return InteractionResponse(
            messages=(InteractionMessage(role="assistant", text=message_text),),
            commands=(InteractionCommand(intent=final_intent),),
            analysis_result=loop_result.latest_analysis_result,
            economic_result=loop_result.latest_economic_result,
            scenario_comparison=loop_result.latest_scenario_comparison,
            report_context=loop_result.latest_report_context,
            map_filter=loop_result.latest_map_filter,
            ui_hints={
                "mode": (
                    "reset"
                    if reset_completed
                    else ("assistant_runtime" if final_intent is InteractionIntent.RESET_SESSION else final_intent.value)
                ),
                "providerMode": self.provider_name,
                "providerModel": self.provider_model,
                "runtime": self.runtime_name,
                "needsClarification": needs_clarification,
                "followUpSuggestions": follow_up_suggestions,
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
        if tool_name in {MODEL_TOOL_ANALYZE_MUNICIPALITIES, MODEL_TOOL_ANALYZE_CURRENT_SELECTION}:
            # Keep geometry out of the model context, but expose every computed
            # metric and the id needed for subsequent tool calls.
            return {
                "analysisId": payload.get("analysisId"),
                "source": payload.get("source"),
                "requestedMunicipalities": payload.get("requestedMunicipalities", []),
                "intersectedMunicipalities": payload.get("intersectedMunicipalities", []),
                "summary": payload.get("summary", {}),
                **({"ok": False, "error": payload["error"]} if "error" in payload else {}),
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
            "economicResult": response.economic_result,
            "scenarioComparison": response.scenario_comparison,
            "reportContext": response.report_context,
            "mapFilter": response.map_filter,
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
        assistant_text: str,
    ) -> SessionContext:
        if clears_context:
            session_context = SessionContext()

        metadata = dict(session_context.metadata)
        # Cross-turn continuity is carried explicitly in conversation_messages and
        # domain context. Provider response ids are intentionally turn-local: an
        # old or incomplete function-call chain can otherwise contaminate a later
        # request or make it impossible to reset the session reliably.
        metadata.pop("provider_previous_response_id", None)
        metadata.pop("openai_previous_response_id", None)

        metadata["conversation_messages"] = self._updated_conversation_messages(
            session_context=session_context,
            request=request,
            assistant_text=assistant_text,
        )

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
        del session_context
        return None

    @staticmethod
    def _conversation_messages(session_context: SessionContext) -> list[dict[str, str]]:
        messages = session_context.metadata.get("conversation_messages")
        if not isinstance(messages, list):
            return []
        normalized: list[dict[str, str]] = []
        for item in messages[-16:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "")
            content = str(item.get("content") or "").strip()
            if role in {"user", "assistant", "tool"} and content:
                normalized.append({"role": role, "content": content})
        return normalized

    @classmethod
    def _updated_conversation_messages(
        cls,
        *,
        session_context: SessionContext,
        request: InteractionRequest,
        assistant_text: str,
    ) -> list[dict[str, str]]:
        messages = cls._conversation_messages(session_context)
        user_text = request.input.primary_text()
        if user_text:
            messages.append({"role": "user", "content": user_text})
        if assistant_text:
            messages.append({"role": "assistant", "content": assistant_text})
        return messages[-16:]

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
            raise LlmProviderUnavailableError("Il modello LLM ha restituito una risposta strutturata vuota.")

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return {"_unstructured": True}
        if not isinstance(payload, dict):
            raise LlmProviderUnavailableError("Il modello LLM ha restituito un payload strutturato non valido.")
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
            "Rispondi sempre in italiano, in testo semplice senza Markdown. "
            "Non mostrare JSON, nomi tecnici di tool, identificativi interni o dettagli di implementazione. "
            "Non inventare mai dati GIS: per ogni fatto numerico o analitico devi usare i tool. "
            "I valori geografici ed economici finali devono arrivare solo dai tool backend. "
            "Interpreta l'intera richiesta e pianifica tutti i passaggi necessari, anche quando richiede più operazioni. "
            "Dopo ogni risultato di tool, continua con i tool ancora necessari prima della risposta finale. "
            "Per analizzare separatamente più comuni, chiama analyze_municipalities una volta per ciascun comune; "
            "una chiamata con più nomi produce invece un'unica analisi congiunta. "
            "Per analizzare e poi confrontare, crea prima tutte le analisi richieste e poi confronta i loro id "
            "con compare_saved_analyses. Non usare analisi pregresse al posto di quelle appena richieste. "
            "Se un tool restituisce un errore, valutalo e correggi la chiamata oppure chiedi il chiarimento necessario. "
            "Scrivi tu la risposta finale, rispondendo a tutte le domande e usando i risultati dei tool. "
            "Quando citi numeri, formatta in italiano e arrotonda a massimo 2 decimali. "
            "Non mostrare precisione grezza lunga da float. "
            "Se il messaggio corrente nomina uno o più comuni e chiede situazione, dati, boschi, CO2 o analisi, "
            "risolvi quei comuni e usa analyze_municipalities; non rispondere con l'ultima analisi salvo richiesta esplicita. "
            "Se utente cita comuni in modo parziale o ambiguo, usa prima search_municipalities. "
            "Se il tool di ricerca restituisce più candidati, chiedi quale intende senza avviare analisi. "
            "Usa analyze_current_selection solo quando il messaggio indica la selezione corrente e hasCurrentSelection è vero. "
            "Non trattare mai l'area dell'ultima analisi come selezione corrente. "
            "Se utente dice 'questi comuni', 'quelli selezionati' o equivalente e selectedMunicipalities è valorizzato, "
            "usa quei nomi senza richiederli di nuovo. "
            "Se utente chiede spiegazioni, dettagli o approfondimenti senza nominare nuovi comuni usa get_last_analysis. "
            "Se chiede di mostrare solo una o più categorie sulla mappa usa filter_last_analysis_categories. "
            "Questo filtro modifica solo la visualizzazione: non dichiarare che ricalcola l'analisi. "
            "Se chiede valore economico con uno scenario usa calculate_economic_value. "
            "Se chiede confronto prezzi o scenari usa compare_economic_scenarios. "
            "Se chiede report o PDF usa prepare_report. Il tool apre il report esistente: non dichiarare mai PDF generato. "
            "Se chiede elenco storico o analisi recenti usa list_recent_analyses. "
            "Se chiede 'confrontalo con il precedente' o un confronto di risultati recenti usa compare_recent_analyses: "
            "ultime due per default, ultime tre se richiesto. "
            "Per confrontare analisi già salvate identificate da id, label o comune usa compare_saved_analyses; se ambiguo lista le analisi e chiedi chiarimento. "
            "Quando non servono altri tool, rispondi solo con JSON valido con i campi: intent, assistant_text, "
            "needs_clarification, clarification_question, ui_actions, citations_internal, follow_up_suggestions. "
            "Classifica intenti finali in operazioni di dominio: analisi area/comuni, informazioni forestali, stima CO2, "
            "scenari economici, report, spiegazione risultati, guida workflow. "
            "Non inventare controlli, parametri, pulsanti o workflow non presenti nei tool. "
            "Per richieste metodologiche usa get_methodology prima di spiegare. "
            "Se manca contesto sufficiente, non improvvisare: chiedi chiarimento. "
            "Azioni UI consentite: show_last_analysis, open_report_panel, show_legend, focus_map_results. "
            "Non emettere altre ui_actions. Usa open_report_panel dopo prepare_report e per mostrare valutazioni e scenari. "
            "Chiedi chiarimenti solo quando manca una scelta indispensabile; non chiedere dati già presenti nel contesto. "
            "Mantieni risposte concise ma complete: copri tutti i risultati richiesti, senza un limite fisso di frasi. "
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
                "hasCurrentSelection": bool(request.context.current_selection_payload),
                "selectionSource": request.context.metadata.get("selectionSource"),
                "mapExtent": request.context.current_map_extent,
                "hasDisplayedAnalysis": bool(request.context.displayed_analysis_id),
                "displayedAnalysisMatchesLast": bool(
                    request.context.displayed_analysis_id
                    and session_context.last_analysis
                    and request.context.displayed_analysis_id
                    == session_context.last_analysis.get("analysisId")
                ),
            },
            "analysis_context": {
                "lastAnalysis": session_context.last_analysis,
            },
            "conversation_context": {
                "lastIntent": session_context.last_intent.value if session_context.last_intent else None,
                "recentMessages": AssistantRuntime._conversation_messages(session_context)[-8:],
            },
            "grounding": {
                "availableTools": list(MODEL_TOOL_NAMES),
                "priceOptions": [dict(option) for option in PRICE_OPTIONS],
                "vegetationCategories": [
                    {"key": item["key"], "label": item["label"]}
                    for item in serialize_categories()
                ],
                "rules": [
                    "Numeri GIS solo da tool backend.",
                    "Comuni nominati nel messaggio corrente hanno priorita su lastAnalysis e selectedMunicipalities.",
                    "Selezione corrente disponibile solo se hasCurrentSelection e true.",
                    "Ultima analisi, analisi visualizzata e storico salvato sono contesti distinti.",
                    "Confronti recenti basati sulle ultime due analisi in sessione, o ultime N se esplicitato.",
                    "Confronti salvati possono risolvere id, label o comuni presenti nello storico.",
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
                "description": (
                    "Use this when the current user message asks for analysis, situazione, quadro forestale, "
                    "boschi, CO2 or dati for one or more resolved municipalities. This has priority over "
                    "lastAnalysis when municipality_names come from the current message."
                ),
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
                "description": (
                    "Use this only when the current user message explicitly asks for selezione corrente, "
                    "area corrente or mappa corrente already present in UI context."
                ),
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
                "name": MODEL_TOOL_FILTER_LAST_ANALYSIS,
                "description": (
                    "Filtra la visualizzazione dell'analisi attualmente mostrata sulla mappa per categorie "
                    "vegetazionali. Usalo per richieste come 'mostrami solo i castagneti'. Non ricalcola "
                    "risultati GIS o economici. Usa show_all=true per ripristinare tutte le categorie."
                ),
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category_names": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "show_all": {"type": "boolean"},
                    },
                    "required": ["category_names", "show_all"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": MODEL_TOOL_CALCULATE_ECONOMIC_VALUE,
                "description": "Calcola valore economico deterministico dell'ultima analisi con uno scenario configurato.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "scenario_key": {
                            "type": "string",
                            "enum": [str(option["key"]) for option in PRICE_OPTIONS],
                        },
                    },
                    "required": ["scenario_key"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": MODEL_TOOL_COMPARE_ECONOMIC_SCENARIOS,
                "description": "Confronta tutti gli scenari economici configurati per l'ultima analisi.",
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
                "description": (
                    "Use this when utente chiede spiegazione o richiamo di ultima analisi. Do not use this "
                    "when the current user message names a new municipality to analyze."
                ),
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
                "description": "Use this when utente chiede confronto tra analisi recenti: default ultime due, oppure ultime N se richiesto.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "recent_count": {"type": "integer"},
                    },
                    "required": ["recent_count"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": MODEL_TOOL_LIST_RECENT_ANALYSES,
                "description": "Use this when utente chiede storico, elenco o analisi recenti salvate nella sessione.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer"},
                    },
                    "required": ["limit"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": MODEL_TOOL_COMPARE_SAVED_ANALYSES,
                "description": "Use this when utente chiede confronto tra analisi salvate citando id, label o comune.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selectors": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["selectors"],
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
            {
                "type": "function",
                "name": MODEL_TOOL_PREPARE_REPORT,
                "description": "Apre il report UI esistente per l'ultima analisi senza dichiarare che il PDF sia già generato.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        ]
