from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.http import HttpResponseNotFound
from django.http import JsonResponse
from django.http import StreamingHttpResponse
from django.shortcuts import render
from django.middleware.csrf import get_token
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import require_POST

from cartaNatura.domain.vegetation import serialize_categories
from cartaNatura.experiments import (
    STUDY_CONTEXT_SESSION_KEY,
    clear_experiment_log,
    create_study_session,
    export_experiment_log,
    export_study_events_jsonl,
    export_study_session,
    record_experiment_event,
)
from cartaNatura.interaction import (
    DjangoSessionAnalysisStore,
    InteractionChannel,
    InteractionContext,
    InteractionInput,
    InteractionRequest,
    build_default_orchestrator,
)
from cartaNatura.interaction.llm import LlmProviderUnavailableError
from cartaNatura.interaction.session import DjangoSessionStore
from cartaNatura.interaction.ui_context import build_interaction_context
from cartaNatura.interaction.voice import transcribe_uploaded_audio

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


PRICE_OPTIONS = (
    {"label": "Costo sociale: 138 EUR/t", "value": 138},
    {"label": "Prezzo ombra: 303 EUR/t", "value": 303},
    {"label": "Mercato regolamentato: 82 EUR/t", "value": 82},
    {"label": "Mercato volontario: 20 EUR/t", "value": 20},
)

STUDY_TASKS = (
    {"id": "area_co2", "label": "CO2 area selezionata"},
    {"id": "municipalities_report", "label": "Report comuni"},
    {"id": "economic_valuation", "label": "Valutazione economica"},
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
        "uiHints": response.ui_hints,
    }


def _study_enabled(request) -> bool:
    return request.GET.get("study") == "1"


def _study_context_payload(request) -> dict[str, object] | None:
    context = request.session.get(STUDY_CONTEXT_SESSION_KEY)
    return context if isinstance(context, dict) else None


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
    app_config = {
        "apiUrl": reverse("gis"),
        "interactionUrl": reverse("interact"),
        "interactionStreamUrl": reverse("interact_stream"),
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
            "enabled": settings.AI_ASSISTANT_ENABLED and bool(os.getenv("OPENAI_API_KEY", "").strip()),
            "title": "Assistente Carta Natura",
            "providerConfigured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
            "examples": [
                "Reset sessione",
            ],
        },
        "study": {
            "enabled": _study_enabled(request),
            "sessionUrl": reverse("study_session"),
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


@require_POST
def interact(request):
    if not settings.AI_ASSISTANT_ENABLED:
        return HttpResponseNotFound()

    if not os.getenv("OPENAI_API_KEY", "").strip():
        return JsonResponse(
            {"error": "Assistente AI non configurato. Imposta OPENAI_API_KEY."},
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
        details={"messageLength": len(interaction_request.input.primary_text())},
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
            "analysisId": (response.analysis_result or {}).get("analysisId"),
            "providerMode": response.ui_hints.get("providerMode"),
            "needsClarification": response.ui_hints.get("needsClarification"),
        },
    )

    return JsonResponse(_serialize_interaction_response(response))


@require_POST
def interact_stream(request):
    if not settings.AI_ASSISTANT_ENABLED:
        return HttpResponseNotFound()

    if not os.getenv("OPENAI_API_KEY", "").strip():
        return JsonResponse(
            {"error": "Assistente AI non configurato. Imposta OPENAI_API_KEY."},
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
        details={"messageLength": len(interaction_request.input.primary_text())},
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
            logger.exception("Assistant stream failed session=%s", session_id)
            yield _encode_sse("error", {"type": "error", "message": str(exc)})
        finally:
            _save_stream_session_if_needed(request)
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
                        "analysisId": (final_response.analysis_result or {}).get("analysisId"),
                        "providerMode": final_response.ui_hints.get("providerMode"),
                        "needsClarification": final_response.ui_hints.get("needsClarification"),
                    },
                )
                logger.info(
                    "Assistant stream completed session=%s mode=%s provider=%s has_analysis=%s",
                    session_id,
                    final_response.ui_hints.get("mode"),
                    final_response.ui_hints.get("providerMode", "local"),
                    bool(final_response.analysis_result),
                )

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@require_POST
def voice_transcribe(request):
    if not settings.AI_ASSISTANT_ENABLED:
        return HttpResponseNotFound()

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
            record_experiment_event(
                request.session,
                event_type="reset_completed",
                channel="system",
                operation="study_session_reset",
                interaction_mode="system",
                status="completed",
            )
        request.session.pop(STUDY_CONTEXT_SESSION_KEY, None)
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
