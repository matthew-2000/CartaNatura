from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.http import HttpResponseNotFound
from django.http import JsonResponse
from django.http import StreamingHttpResponse
from django.shortcuts import redirect, render
from django.middleware.csrf import get_token
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import require_POST

from cartaNatura.domain.economics import PRICE_OPTIONS
from cartaNatura.domain.vegetation import serialize_categories
from cartaNatura.experiments import (
    EXPERIMENT_ACTIVE_TASK_SESSION_KEY,
    STUDY_CONTEXT_SESSION_KEY,
    clear_experiment_log,
    create_study_session,
    export_experiment_log,
    export_study_events_jsonl,
    export_study_session,
    record_experiment_event,
)
from cartaNatura.experiments.study_logging import get_study_log_root, sanitize_identifier
from cartaNatura.interaction import (
    DjangoSessionAnalysisStore,
    InteractionChannel,
    InteractionContext,
    InteractionInput,
    InteractionRequest,
    build_default_orchestrator,
)
from cartaNatura.interaction.analysis_store import (
    build_analysis_label,
)
from cartaNatura.interaction.llm import (
    LlmProviderUnavailableError,
    get_llm_provider_status,
    require_llm_provider_configured,
)
from cartaNatura.interaction.session import DjangoSessionStore
from cartaNatura.interaction.ui_context import build_interaction_context
from cartaNatura.interaction.voice import transcribe_uploaded_audio
from cartaNatura.services.analysis_compare import compare_saved_analyses

logger = logging.getLogger(__name__)
APP_DIR = Path(__file__).resolve().parent


def _build_asset_version() -> str:
    tracked_paths = [
        APP_DIR / "templates" / "cartaNatura" / "index.html",
        APP_DIR / "static" / "css" / "app.css",
    ]
    tracked_paths.extend((APP_DIR / "static" / "js").rglob("*.js"))
    tracked_paths.extend((APP_DIR / "static" / "vendor").rglob("*.js"))
    tracked_paths.extend((APP_DIR / "static" / "vendor").rglob("*.css"))
    return str(int(max(path.stat().st_mtime for path in tracked_paths if path.exists())))


STUDY_TASKS = (
    {"id": "asita_t1_area_analysis", "label": "T1 - Analisi comuni/area"},
    {"id": "asita_t2_forest_co2", "label": "T2 - Categorie forestali e CO2"},
    {"id": "asita_t3_economic_value", "label": "T3 - Valore economico"},
    {"id": "asita_t4_scenario_compare", "label": "T4 - Confronto scenari"},
    {"id": "asita_t5_report_pdf", "label": "T5 - Report e PDF"},
    {"id": "asita_t6_map_verify", "label": "T6 - Verifica in mappa"},
)


def _ensure_session_id(request) -> str:
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key or "web-session"


def _build_request_orchestrator(request):
    return build_default_orchestrator(
        session_store=DjangoSessionStore(request.session),
        analysis_store=DjangoSessionAnalysisStore(request.session),
    )


def _analysis_history_store(request) -> DjangoSessionAnalysisStore:
    return DjangoSessionAnalysisStore(request.session)


def _analysis_history_municipalities(analysis) -> list[str]:
    values = analysis.intersected_municipalities or analysis.requested_municipalities
    return [str(item) for item in values if str(item).strip()]


def _analysis_history_label(analysis) -> str:
    if analysis.label:
        return analysis.label
    return build_analysis_label(
        selection_kind=analysis.selection_kind,
        requested_municipalities=analysis.requested_municipalities,
        intersected_municipalities=analysis.intersected_municipalities,
        created_at=analysis.created_at,
    )


def _compact_summary(summary: dict[str, object]) -> dict[str, object]:
    return {
        "totalCo2": summary.get("totalCo2"),
        "totalHectares": summary.get("totalHectares"),
        "topCategory": summary.get("topCategory"),
        "hasSupportedVegetation": bool(summary.get("hasSupportedVegetation")),
        "items": summary.get("items", []) if isinstance(summary.get("items"), list) else [],
    }


def _serialize_analysis_history_item(analysis) -> dict[str, object]:
    return {
        "id": analysis.analysis_id,
        "createdAt": analysis.created_at,
        "label": _analysis_history_label(analysis),
        "selectionKind": analysis.selection_kind,
        "municipalities": _analysis_history_municipalities(analysis),
        "hasDrawnGeometry": analysis.has_drawn_geometry,
        "summary": _compact_summary(analysis.summary),
        "economicEvaluation": analysis.economic_valuation,
        "metadata": analysis.metadata,
    }


def _serialize_analysis_history_detail(analysis) -> dict[str, object]:
    payload = _serialize_analysis_history_item(analysis)
    payload.update(
        {
            "source": analysis.source,
            "requestedMunicipalities": list(analysis.requested_municipalities),
            "intersectedMunicipalities": list(analysis.intersected_municipalities),
            "selectionPayload": analysis.selection_payload,
        }
    )
    return payload


def _read_json_body(request) -> dict[str, object]:
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Richiesta non valida: formato JSON errato.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Richiesta non valida: payload non supportato.")
    return payload


def _build_text_interaction_request(request, payload: dict[str, object]) -> InteractionRequest:
    message = str(payload.get("message") or "").strip()
    context_payload = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    metadata_payload = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    interaction_mode = str(metadata_payload.get("interactionMode") or "").strip()
    return InteractionRequest(
        channel=InteractionChannel.VOICE if interaction_mode == "voice" else InteractionChannel.WEB_CHAT,
        session_id=_ensure_session_id(request),
        input=InteractionInput(
            text=message,
            metadata={
                "source": "web_assistant",
                "interactionMode": interaction_mode or "text",
            },
        ),
        context=build_interaction_context(context_payload),
    )


def _serialize_interaction_response(response) -> dict[str, object]:
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


def _llm_status() -> dict[str, object]:
    return get_llm_provider_status()


def _llm_log_details(response) -> dict[str, object]:
    return {
        "providerMode": response.ui_hints.get("providerMode"),
        "providerModel": response.ui_hints.get("providerModel"),
        "needsClarification": response.ui_hints.get("needsClarification"),
    }


def _study_enabled(request) -> bool:
    return request.GET.get("study") == "1"


def _study_context_payload(request) -> dict[str, object] | None:
    context = request.session.get(STUDY_CONTEXT_SESSION_KEY)
    if not isinstance(context, dict):
        return None
    payload = dict(context)
    active_task = request.session.get(EXPERIMENT_ACTIVE_TASK_SESSION_KEY)
    payload["activeTask"] = active_task if isinstance(active_task, dict) else None
    return payload


def _store_study_context(request, context) -> dict[str, object]:
    payload = {
        "participantId": context.participantId,
        "studySessionId": context.studySessionId,
        "condition": context.condition,
        "taskId": context.taskId,
    }
    request.session[STUDY_CONTEXT_SESSION_KEY] = payload
    request.session.modified = True
    return payload


def _assistant_response_text(response) -> str:
    for message_item in response.messages:
        if message_item.role == "assistant":
            return message_item.text
    return response.audio_output_text or ""


def _assistant_intent(response) -> str | None:
    if response.commands:
        return response.commands[0].intent.value
    mode = response.ui_hints.get("mode")
    return str(mode) if mode else None


def _interaction_analysis_id(response) -> str | None:
    for payload in (
        response.analysis_result,
        response.economic_result,
        response.report_context,
    ):
        if isinstance(payload, dict) and payload.get("analysisId"):
            return str(payload["analysisId"])
    return None


def _active_task_condition(request) -> str | None:
    active_task = request.session.get(EXPERIMENT_ACTIVE_TASK_SESSION_KEY)
    context = request.session.get(STUDY_CONTEXT_SESSION_KEY)
    if not isinstance(active_task, dict) or not isinstance(context, dict):
        return None
    condition = str(active_task.get("condition") or context.get("condition") or "")
    return condition if condition in {"webgis", "conversational"} else None


def _condition_violation_response(
    request,
    *,
    blocked_condition: str,
    attempted_action: str,
    channel: str,
    interaction_mode: str,
) -> JsonResponse | None:
    active_condition = _active_task_condition(request)
    if active_condition != blocked_condition:
        return None
    record_experiment_event(
        request.session,
        event_type="protocol_violation",
        channel=channel,
        operation=attempted_action,
        interaction_mode=interaction_mode,
        status="blocked",
        error="condition_action_blocked",
        details={
            "attemptedAction": attempted_action,
            "blockedByCondition": active_condition,
            "eventSource": "backend",
        },
    )
    return JsonResponse(
        {
            "error": "Azione non consentita nella condizione sperimentale attiva.",
            "condition": active_condition,
            "violation": "condition_action_blocked",
        },
        status=403,
    )


def _clear_operational_state_for_task(request) -> None:
    request.session.pop("interaction_context", None)
    request.session.pop("interaction_analyses", None)
    request.session.modified = True


def _encode_sse(event_type: str, payload: dict[str, object]) -> bytes:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n".encode("utf-8")


def _save_stream_session_if_needed(request) -> None:
    if not getattr(request.session, "modified", False):
        return

    save = getattr(request.session, "save", None)
    if callable(save):
        save()


@ensure_csrf_cookie
def index(request):
    asset_version = _build_asset_version()
    llm_status = _llm_status()
    app_config = {
        "apiUrl": reverse("gis"),
        "interactionUrl": reverse("interact"),
        "interactionStreamUrl": reverse("interact_stream"),
        "analysisHistoryUrl": reverse("analysis_history"),
        "voiceTranscriptionUrl": reverse("voice_transcribe"),
        "experimentLogUrl": reverse("experiment_log"),
        "csrfToken": get_token(request),
        "priceOptions": PRICE_OPTIONS,
        "categories": serialize_categories(),
        "map": {
            "center": [40.8471407, 14.8639451],
            "zoom": 8,
        },
        "assistant": {
            "enabled": settings.AI_ASSISTANT_ENABLED and bool(llm_status["configured"]),
            "title": "Assistente Carta Natura",
            "providerConfigured": bool(llm_status["configured"]),
            "provider": llm_status["provider"],
            "model": llm_status["model"],
            "examples": [
                "Reset sessione",
            ],
        },
        "study": {
            "enabled": _study_enabled(request),
            "sessionUrl": reverse("study_session"),
            "adminUrl": reverse("study_admin"),
            "currentSession": _study_context_payload(request),
            "tasks": STUDY_TASKS,
        },
        "datasets": {
            "municipalitiesUrl": f"{static('data/campania-municipalities-32633.geojson')}?v={asset_version}",
            "boundariesUrl": f"{static('data/campania-boundaries-4326.geojson')}?v={asset_version}",
        },
    }
    return render(
        request,
        "cartaNatura/index.html",
        {
            "app_config_json": json.dumps(app_config),
            "asset_version": asset_version,
        },
    )


@require_POST
def gis(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Richiesta non valida: formato JSON errato."}, status=400)

    violation_response = _condition_violation_response(
        request,
        blocked_condition="conversational",
        attempted_action="spatial_analysis_ui",
        channel=InteractionChannel.WEB_MAP.value,
        interaction_mode="map",
    )
    if violation_response is not None:
        return violation_response

    record_experiment_event(
        request.session,
        event_type="analysis_started",
        channel=InteractionChannel.WEB_MAP.value,
        operation="spatial_analysis",
        interaction_mode="map",
        step_count=len(payload.get("areas", [])) if isinstance(payload.get("areas"), list) else None,
    )

    try:
        response = _build_request_orchestrator(request).handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_MAP,
                session_id=_ensure_session_id(request),
                input=InteractionInput(geo_selection=payload),
            )
        )
    except ValueError as exc:
        record_experiment_event(
            request.session,
            event_type="error",
            channel=InteractionChannel.WEB_MAP.value,
            operation="spatial_analysis",
            interaction_mode="map",
            error=str(exc),
        )
        return JsonResponse({"error": str(exc)}, status=400)

    if response.analysis_result is None:
        record_experiment_event(
            request.session,
            event_type="error",
            channel=InteractionChannel.WEB_MAP.value,
            operation="spatial_analysis",
            interaction_mode="map",
            error="missing_analysis_result",
        )
        return JsonResponse({"error": "Analisi non completata: risultato mancante."}, status=500)

    summary = response.analysis_result.get("summary", {})
    record_experiment_event(
        request.session,
        event_type="analysis_completed",
        channel=InteractionChannel.WEB_MAP.value,
        operation="spatial_analysis",
        interaction_mode="map",
        details={
            "analysisId": response.analysis_result.get("analysisId"),
            "intersectedMunicipalityCount": len(
                response.analysis_result.get("intersectedMunicipalities", [])
            ),
            "categoryCount": len(summary.get("items", [])) if isinstance(summary, dict) else 0,
            "hasSupportedVegetation": bool(
                summary.get("hasSupportedVegetation") if isinstance(summary, dict) else False
            ),
            "totalCo2": summary.get("totalCo2") if isinstance(summary, dict) else None,
        },
    )
    return JsonResponse(response.analysis_result)


@require_http_methods(["GET", "DELETE"])
def analysis_history(request):
    store = _analysis_history_store(request)

    if request.method == "DELETE":
        store.clear()
        return JsonResponse({"items": [], "count": 0})

    items = [
        _serialize_analysis_history_item(item)
        for item in store.list_recent()
    ]
    return JsonResponse({"items": items, "count": len(items)})


@require_POST
def analysis_history_compare(request):
    try:
        payload = _read_json_body(request)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    raw_ids = payload.get("ids")
    if not isinstance(raw_ids, list):
        return JsonResponse({"error": "Lista analisi mancante."}, status=400)

    analysis_ids: list[str] = []
    for raw_id in raw_ids:
        analysis_id = str(raw_id or "").strip()
        if analysis_id and analysis_id not in analysis_ids:
            analysis_ids.append(analysis_id)

    if len(analysis_ids) < 2:
        return JsonResponse({"error": "Servono almeno due analisi da confrontare."}, status=400)

    store = _analysis_history_store(request)
    records = []
    for analysis_id in analysis_ids:
        analysis = store.get(analysis_id)
        if analysis is None:
            return JsonResponse({"error": f"Analisi non trovata: {analysis_id}."}, status=404)
        records.append(analysis)

    try:
        return JsonResponse(compare_saved_analyses(records, price_options=PRICE_OPTIONS))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["GET", "POST", "PATCH", "DELETE"])
def analysis_history_detail(request, analysis_id: str):
    store = _analysis_history_store(request)
    analysis = store.get(analysis_id)
    if analysis is None:
        return JsonResponse({"error": "Analisi non trovata."}, status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_analysis_history_detail(analysis))

    if request.method == "DELETE":
        store.delete(analysis_id)
        return JsonResponse({"deleted": True, "id": analysis_id})

    try:
        payload = _read_json_body(request)
        renamed = store.rename(analysis_id, str(payload.get("label") or ""))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    if renamed is None:
        return JsonResponse({"error": "Analisi non trovata."}, status=404)
    return JsonResponse(_serialize_analysis_history_detail(renamed))


@require_POST
def interact(request):
    if not settings.AI_ASSISTANT_ENABLED:
        return HttpResponseNotFound()

    violation_response = _condition_violation_response(
        request,
        blocked_condition="webgis",
        attempted_action="conversational_request",
        channel=InteractionChannel.WEB_CHAT.value,
        interaction_mode="text",
    )
    if violation_response is not None:
        return violation_response

    try:
        require_llm_provider_configured()
    except LlmProviderUnavailableError as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=503,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Richiesta non valida: formato JSON errato."}, status=400)

    interaction_request = _build_text_interaction_request(request, payload)
    session_id = interaction_request.session_id
    interaction_mode = interaction_request.input.metadata.get("interactionMode", "text")
    record_experiment_event(
        request.session,
        event_type="interaction_started",
        channel=interaction_request.channel.value,
        operation="conversational_request",
        interaction_mode=str(interaction_mode),
        user_text=interaction_request.input.primary_text(),
        user_transcript=interaction_request.input.primary_text() if interaction_mode == "voice" else None,
        details={
            "messageLength": len(interaction_request.input.primary_text()),
            "eventSource": "backend",
            "providerMode": _llm_status()["provider"],
            "providerModel": _llm_status()["model"],
        },
    )
    logger.info(
        "Assistant interaction started session=%s chars=%s selected=%s",
        session_id,
        len(interaction_request.input.primary_text()),
        len(payload.get("context", {}).get("selectedMunicipalities", []))
        if isinstance(payload.get("context"), dict)
        and isinstance(payload.get("context", {}).get("selectedMunicipalities"), list)
        else 0,
    )

    try:
        response = _build_request_orchestrator(request).handle(interaction_request)
    except ValueError as exc:
        record_experiment_event(
            request.session,
            event_type="unknown_request",
            channel=interaction_request.channel.value,
            operation="conversational_request",
            interaction_mode=str(interaction_mode),
            error=str(exc),
        )
        logger.warning(
            "Assistant interaction rejected session=%s error=%s",
            session_id,
            str(exc),
        )
        return JsonResponse({"error": str(exc)}, status=400)
    except LlmProviderUnavailableError as exc:
        record_experiment_event(
            request.session,
            event_type="error",
            channel=interaction_request.channel.value,
            operation="conversational_request",
            interaction_mode=str(interaction_mode),
            error=str(exc),
        )
        logger.warning(
            "Assistant interaction provider failure session=%s error=%s",
            session_id,
            str(exc),
        )
        return JsonResponse({"error": str(exc)}, status=503)

    logger.info(
        "Assistant interaction completed session=%s mode=%s provider=%s has_analysis=%s",
        session_id,
        response.ui_hints.get("mode"),
        response.ui_hints.get("providerMode", "local"),
        bool(response.analysis_result),
    )
    record_experiment_event(
        request.session,
        event_type="interaction_completed",
        channel=interaction_request.channel.value,
        operation=str(response.ui_hints.get("mode") or "conversational_request"),
        interaction_mode=str(interaction_mode),
        intent=_assistant_intent(response),
        user_text=interaction_request.input.primary_text(),
        user_transcript=interaction_request.input.primary_text() if interaction_mode == "voice" else None,
        assistant_response=_assistant_response_text(response),
        details={
            "analysisId": _interaction_analysis_id(response),
            "scenarioKey": (response.economic_result or {}).get("scenarioKey"),
            "priceEurPerTon": (response.economic_result or {}).get("priceEurPerTon"),
            "totalValueEur": (response.economic_result or {}).get("totalValueEur"),
            **_llm_log_details(response),
            "eventSource": "backend",
        },
    )

    return JsonResponse(_serialize_interaction_response(response))


@require_POST
def interact_stream(request):
    if not settings.AI_ASSISTANT_ENABLED:
        return HttpResponseNotFound()

    violation_response = _condition_violation_response(
        request,
        blocked_condition="webgis",
        attempted_action="conversational_request",
        channel=InteractionChannel.WEB_CHAT.value,
        interaction_mode="text",
    )
    if violation_response is not None:
        return violation_response

    try:
        require_llm_provider_configured()
    except LlmProviderUnavailableError as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=503,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Richiesta non valida: formato JSON errato."}, status=400)

    interaction_request = _build_text_interaction_request(request, payload)
    session_id = interaction_request.session_id
    interaction_mode = interaction_request.input.metadata.get("interactionMode", "text")
    record_experiment_event(
        request.session,
        event_type="interaction_started",
        channel=interaction_request.channel.value,
        operation="conversational_request",
        interaction_mode=str(interaction_mode),
        user_text=interaction_request.input.primary_text(),
        user_transcript=interaction_request.input.primary_text() if interaction_mode == "voice" else None,
        details={
            "messageLength": len(interaction_request.input.primary_text()),
            "eventSource": "backend",
            "providerMode": _llm_status()["provider"],
            "providerModel": _llm_status()["model"],
        },
    )
    logger.info(
        "Assistant stream started session=%s chars=%s",
        session_id,
        len(interaction_request.input.primary_text()),
    )

    orchestrator = _build_request_orchestrator(request)

    def event_stream():
        final_response = None
        try:
            stream = orchestrator.handle_stream(interaction_request)
            while True:
                try:
                    event = next(stream)
                except StopIteration as stop:
                    final_response = stop.value
                    break
                event_type = str(event.get("type") or "message")
                if event_type == "done":
                    # Persist analysis history and conversation context before the
                    # browser can issue a follow-up based on this completed turn.
                    _save_stream_session_if_needed(request)
                yield _encode_sse(event_type, event)
        except ValueError as exc:
            record_experiment_event(
                request.session,
                event_type="unknown_request",
                channel=interaction_request.channel.value,
                operation="conversational_request",
                interaction_mode=str(interaction_mode),
                error=str(exc),
            )
            logger.warning(
                "Assistant stream rejected session=%s error=%s",
                session_id,
                str(exc),
            )
            yield _encode_sse("error", {"type": "error", "message": str(exc)})
        except LlmProviderUnavailableError as exc:
            record_experiment_event(
                request.session,
                event_type="error",
                channel=interaction_request.channel.value,
                operation="conversational_request",
                interaction_mode=str(interaction_mode),
                error=str(exc),
            )
            logger.warning(
                "Assistant stream provider failure session=%s error=%s",
                session_id,
                str(exc),
            )
            yield _encode_sse("error", {"type": "error", "message": str(exc)})
        except Exception as exc:
            record_experiment_event(
                request.session,
                event_type="error",
                channel=interaction_request.channel.value,
                operation="conversational_request",
                interaction_mode=str(interaction_mode),
                error=str(exc),
                details={"eventSource": "backend"},
            )
            logger.exception("Assistant stream failed session=%s", session_id)
            yield _encode_sse("error", {"type": "error", "message": str(exc)})
        finally:
            if final_response is not None:
                record_experiment_event(
                    request.session,
                    event_type="interaction_completed",
                    channel=interaction_request.channel.value,
                    operation=str(final_response.ui_hints.get("mode") or "conversational_request"),
                    interaction_mode=str(interaction_mode),
                    intent=_assistant_intent(final_response),
                    user_text=interaction_request.input.primary_text(),
                    user_transcript=(
                        interaction_request.input.primary_text() if interaction_mode == "voice" else None
                    ),
                    assistant_response=_assistant_response_text(final_response),
                    details={
                        "analysisId": _interaction_analysis_id(final_response),
                        "scenarioKey": (final_response.economic_result or {}).get("scenarioKey"),
                        "priceEurPerTon": (final_response.economic_result or {}).get(
                            "priceEurPerTon"
                        ),
                        "totalValueEur": (final_response.economic_result or {}).get(
                            "totalValueEur"
                        ),
                        **_llm_log_details(final_response),
                        "eventSource": "backend",
                    },
                )
                logger.info(
                    "Assistant stream completed session=%s mode=%s provider=%s has_analysis=%s",
                    session_id,
                    final_response.ui_hints.get("mode"),
                    final_response.ui_hints.get("providerMode", "local"),
                    bool(final_response.analysis_result),
                )
            _save_stream_session_if_needed(request)

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@require_POST
def voice_transcribe(request):
    if not settings.AI_ASSISTANT_ENABLED:
        return HttpResponseNotFound()

    violation_response = _condition_violation_response(
        request,
        blocked_condition="webgis",
        attempted_action="voice_input",
        channel=InteractionChannel.VOICE.value,
        interaction_mode="voice",
    )
    if violation_response is not None:
        return violation_response

    if not os.getenv("OPENAI_API_KEY", "").strip():
        return JsonResponse(
            {"error": "Trascrizione vocale non configurata. Imposta OPENAI_API_KEY."},
            status=503,
        )

    audio_file = request.FILES.get("audio")
    if audio_file is None:
        return JsonResponse({"error": "Audio mancante nella richiesta."}, status=400)

    duration_ms = None
    try:
        raw_duration = request.POST.get("durationMs")
        duration_ms = int(raw_duration) if raw_duration else None
    except (TypeError, ValueError):
        duration_ms = None

    try:
        transcript = transcribe_uploaded_audio(audio_file)
    except ValueError as exc:
        record_experiment_event(
            request.session,
            event_type="error",
            channel=InteractionChannel.VOICE.value,
            operation="voice_transcription",
            interaction_mode="voice",
            duration_ms=duration_ms,
            error=str(exc),
        )
        return JsonResponse({"error": str(exc)}, status=400)
    except LlmProviderUnavailableError as exc:
        record_experiment_event(
            request.session,
            event_type="error",
            channel=InteractionChannel.VOICE.value,
            operation="voice_transcription",
            interaction_mode="voice",
            duration_ms=duration_ms,
            error=str(exc),
        )
        return JsonResponse({"error": str(exc)}, status=503)

    record_experiment_event(
        request.session,
        event_type="voice_transcribed",
        channel=InteractionChannel.VOICE.value,
        operation="voice_transcription",
        interaction_mode="voice",
        duration_ms=duration_ms,
        user_transcript=transcript,
        details={"transcriptLength": len(transcript)},
    )
    return JsonResponse({"transcript": transcript})


@require_http_methods(["GET", "POST", "DELETE"])
def experiment_log(request):
    if request.method == "GET":
        return JsonResponse(export_experiment_log(request.session))

    if request.method == "DELETE":
        clear_experiment_log(request.session)
        return JsonResponse(export_experiment_log(request.session))

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Richiesta non valida: formato JSON errato."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "Richiesta non valida: payload non supportato."}, status=400)

    event = record_experiment_event(
        request.session,
        event_type=str(payload.get("eventType") or ""),
        channel=str(payload.get("channel") or "system"),
        operation=str(payload.get("operation") or ""),
        interaction_mode=str(payload.get("interactionMode") or ""),
        duration_ms=payload.get("durationMs") if isinstance(payload.get("durationMs"), int) else None,
        step_count=payload.get("stepCount") if isinstance(payload.get("stepCount"), int) else None,
        task_id=str(payload.get("taskId") or ""),
        task_run_id=str(payload.get("taskRunId") or ""),
        condition=str(payload.get("condition") or ""),
        status=str(payload.get("status") or ""),
        error=str(payload.get("error") or ""),
        intent=str(payload.get("intent") or ""),
        user_text=str(payload.get("userText") or ""),
        user_transcript=str(payload.get("userTranscript") or ""),
        assistant_response=str(payload.get("assistantResponse") or ""),
        details=payload.get("details") if isinstance(payload.get("details"), dict) else {},
    )
    return JsonResponse({"event": event, "summary": export_experiment_log(request.session)["summary"]})


@require_http_methods(["GET", "POST", "DELETE"])
def study_session(request):
    if request.method == "GET":
        context = _study_context_payload(request)
        if context is None:
            return JsonResponse({"active": False, "export": None})
        if request.GET.get("format") == "jsonl":
            body = export_study_events_jsonl(context)
            response = HttpResponse(body, content_type="application/jsonl; charset=utf-8")
            response["Content-Disposition"] = (
                f'attachment; filename="{context["participantId"]}_{context["studySessionId"]}.jsonl"'
            )
            return response
        return JsonResponse({"active": True, "export": export_study_session(context)})

    if request.method == "DELETE":
        context = _study_context_payload(request)
        if context is not None:
            active_task = request.session.get(EXPERIMENT_ACTIVE_TASK_SESSION_KEY)
            if isinstance(active_task, dict):
                record_experiment_event(
                    request.session,
                    event_type="task_interrupted",
                    channel="system",
                    operation="study_task",
                    interaction_mode="system",
                    task_id=str(active_task.get("taskId") or ""),
                    task_run_id=str(active_task.get("taskRunId") or ""),
                    condition=str(context.get("condition") or ""),
                    status="interrupted",
                    error="study_session_reset",
                )
            record_experiment_event(
                request.session,
                event_type="reset_completed",
                channel="system",
                operation="study_session_reset",
                interaction_mode="system",
                status="completed",
            )
        request.session.pop(STUDY_CONTEXT_SESSION_KEY, None)
        _clear_operational_state_for_task(request)
        request.session.modified = True
        return JsonResponse({"active": False})

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Richiesta non valida: formato JSON errato."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "Richiesta non valida: payload non supportato."}, status=400)

    participant_id = str(payload.get("participantId") or "").strip()
    condition = str(payload.get("condition") or "").strip()
    task_id = str(payload.get("taskId") or "").strip()
    if not participant_id:
        return JsonResponse({"error": "Codice anonimo mancante."}, status=400)

    previous_context = _study_context_payload(request)
    active_task = request.session.get(EXPERIMENT_ACTIVE_TASK_SESSION_KEY)
    if previous_context is not None and isinstance(active_task, dict):
        record_experiment_event(
            request.session,
            event_type="task_interrupted",
            channel="system",
            operation="study_task",
            interaction_mode="system",
            task_id=str(active_task.get("taskId") or ""),
            task_run_id=str(active_task.get("taskRunId") or ""),
            condition=str(previous_context.get("condition") or ""),
            status="interrupted",
            error="study_session_replaced",
        )
    clear_experiment_log(request.session)
    _clear_operational_state_for_task(request)
    context = create_study_session(
        participant_id=participant_id,
        condition=condition,
        task_id=task_id or None,
    )
    context_payload = _store_study_context(request, context)
    event = record_experiment_event(
        request.session,
        event_type="session_started",
        channel="system",
        operation="study_session_started",
        interaction_mode="system",
        status="active",
        details={"taskId": context.taskId or ""},
    )
    return JsonResponse({"active": True, "session": context_payload, "event": event})


def _read_study_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_study_jsonl(path: Path, *, with_pretty: bool = False) -> list[dict[str, object]]:
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            if with_pretty:
                event["prettyJson"] = json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True)
            events.append(event)
    return events


def _resolve_study_session_path(participant_id: str, study_session_id: str) -> Path | None:
    if sanitize_identifier(participant_id, prefix="participant") != participant_id:
        return None
    if sanitize_identifier(study_session_id, prefix="session") != study_session_id:
        return None
    root = get_study_log_root().resolve()
    session_path = (root / participant_id / study_session_id).resolve()
    if root not in session_path.parents or not session_path.is_dir():
        return None
    return session_path


def _study_admin_records() -> list[dict[str, object]]:
    root = get_study_log_root()
    if not root.exists():
        return []
    records: list[dict[str, object]] = []
    for participant_path in root.iterdir():
        if not participant_path.is_dir() or participant_path.name.startswith("."):
            continue
        for session_path in participant_path.iterdir():
            if not session_path.is_dir() or session_path.name.startswith("."):
                continue
            summary = _read_study_json(session_path / "summary.json")
            events = _read_study_jsonl(session_path / "events.jsonl", with_pretty=True)
            last_event = events[-1] if events else {}
            closed = (
                last_event.get("eventType") == "reset_completed"
                and last_event.get("operation") == "study_session_reset"
            )
            records.append(
                {
                    "participantId": participant_path.name,
                    "studySessionId": session_path.name,
                    "condition": summary.get("condition") or "—",
                    "eventCount": summary.get("eventCount") or len(events),
                    "taskCompletionCount": summary.get("taskCompletionCount") or 0,
                    "failedTaskCount": summary.get("failedTaskCount") or 0,
                    "errorCount": summary.get("errorCount") or 0,
                    "unknownRequestCount": summary.get("unknownRequestCount") or 0,
                    "startedAt": summary.get("startedAt"),
                    "completedAt": summary.get("completedAt"),
                    "statusLabel": "Chiusa" if closed else "Salvata",
                    "summary": summary,
                    "events": events,
                }
            )
    return sorted(
        records,
        key=lambda item: str(item.get("startedAt") or item.get("studySessionId") or ""),
        reverse=True,
    )


@ensure_csrf_cookie
@require_http_methods(["GET"])
def study_admin(request):
    records = _study_admin_records()
    requested_participant = str(request.GET.get("participant") or "")
    requested_session = str(request.GET.get("session") or "")
    selected = next(
        (
            record
            for record in records
            if record["participantId"] == requested_participant
            and record["studySessionId"] == requested_session
        ),
        records[0] if records else None,
    )
    active_context = _study_context_payload(request)
    active_key = None
    if active_context:
        active_key = (
            active_context.get("participantId"),
            active_context.get("studySessionId"),
        )
    if selected:
        selected["isActive"] = active_key == (
            selected["participantId"],
            selected["studySessionId"],
        )
    return render(
        request,
        "cartaNatura/study_admin.html",
        {
            "records": records,
            "selected": selected,
            "participant_count": len({record["participantId"] for record in records}),
            "event_count": sum(int(record["eventCount"] or 0) for record in records),
            "deleted": request.GET.get("deleted") == "1",
            "delete_blocked": request.GET.get("error") == "active",
        },
    )


@require_http_methods(["GET"])
def study_admin_download(request, participant_id: str, study_session_id: str, export_format: str):
    session_path = _resolve_study_session_path(participant_id, study_session_id)
    if session_path is None or export_format not in {"json", "jsonl"}:
        return HttpResponseNotFound("Sessione non trovata.")
    events_path = session_path / "events.jsonl"
    if export_format == "jsonl":
        body = events_path.read_text(encoding="utf-8") if events_path.exists() else ""
        content_type = "application/jsonl; charset=utf-8"
    else:
        body = json.dumps(
            {
                "schema": "carta-natura-study-log",
                "participantId": participant_id,
                "studySessionId": study_session_id,
                "summary": _read_study_json(session_path / "summary.json"),
                "events": _read_study_jsonl(events_path),
            },
            ensure_ascii=False,
            indent=2,
        )
        content_type = "application/json; charset=utf-8"
    response = HttpResponse(body, content_type=content_type)
    response["Content-Disposition"] = (
        f'attachment; filename="{participant_id}_{study_session_id}.{export_format}"'
    )
    return response


@require_POST
def study_admin_delete(request, participant_id: str, study_session_id: str):
    session_path = _resolve_study_session_path(participant_id, study_session_id)
    if session_path is None:
        return HttpResponseNotFound("Sessione non trovata.")
    active_context = _study_context_payload(request)
    if active_context and (
        active_context.get("participantId") == participant_id
        and active_context.get("studySessionId") == study_session_id
    ):
        return redirect(f'{reverse("study_admin")}?error=active')
    participant_path = session_path.parent
    shutil.rmtree(session_path)
    try:
        participant_path.rmdir()
    except OSError:
        pass
    return redirect(f'{reverse("study_admin")}?deleted=1')
