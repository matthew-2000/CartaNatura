from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from time import perf_counter

from django.conf import settings
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

from cartaNatura.domain.economics import PRICE_OPTIONS
from cartaNatura.domain.vegetation import serialize_categories
from cartaNatura.telemetry import (
    FRONTEND_EVENT_TYPES,
    new_anonymous_session_id,
    new_interaction_id,
    record_raw_event,
)
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


RUNTIME_MODE_SESSION_KEY = "runtime_mode"
ANONYMOUS_SESSION_ID_KEY = "anonymous_session_id"
RUNTIME_MODES = {"full", "gui_only", "conversational_only"}


def _ensure_session_id(request) -> str:
    session_id = request.session.get(ANONYMOUS_SESSION_ID_KEY)
    if not isinstance(session_id, str) or not session_id:
        session_id = new_anonymous_session_id()
        request.session[ANONYMOUS_SESSION_ID_KEY] = session_id
        request.session.modified = True
    return session_id


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


def _interaction_id_from_payload(payload: dict[str, object]) -> str:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    requested = str(metadata.get("interactionId") or "").strip()
    return requested[:160] if requested else new_interaction_id()


def _build_text_interaction_request(
    request, payload: dict[str, object], *, interaction_id: str
) -> InteractionRequest:
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
                "interactionId": interaction_id,
                "transcriptLogged": bool(metadata_payload.get("transcriptLogged")),
            },
        ),
        context=build_interaction_context(context_payload),
    )


def _serialize_interaction_response(response, *, interaction_id: str) -> dict[str, object]:
    return {
        "interactionId": interaction_id,
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


def _runtime_mode(request) -> str:
    requested = str(request.GET.get("mode") or "").strip().lower().replace("-", "_")
    if requested in RUNTIME_MODES:
        request.session[RUNTIME_MODE_SESSION_KEY] = requested
        request.session.modified = True
    stored = str(request.session.get(RUNTIME_MODE_SESSION_KEY) or "full")
    return stored if stored in RUNTIME_MODES else "full"


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


def _mode_violation_response(
    request,
    *,
    blocked_mode: str,
    attempted_action: str,
    interaction_mode: str,
    interaction_id: str | None = None,
) -> JsonResponse | None:
    active_mode = _runtime_mode(request)
    if active_mode != blocked_mode:
        return None
    record_raw_event(
        _ensure_session_id(request),
        event_type="error",
        interaction_id=interaction_id,
        operation=attempted_action,
        interaction_mode=interaction_mode,
        error_type="runtime_mode_blocked",
        error_message=f"Action blocked by runtime mode {active_mode}",
        data={"action": attempted_action},
    )
    return JsonResponse(
        {
            "error": "Azione non disponibile nella modalità operativa attiva.",
            "runtimeMode": active_mode,
            "violation": "runtime_mode_blocked",
        },
        status=403,
    )


def _encode_sse(event_type: str, payload: dict[str, object]) -> bytes:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n".encode("utf-8")


def _save_stream_session_if_needed(request) -> None:
    if not getattr(request.session, "modified", False):
        return

    save = getattr(request.session, "save", None)
    if callable(save):
        save()


def _provider_failure_response(
    *, session_id: str, interaction_id: str, interaction_mode: str, started_at: float
) -> JsonResponse | None:
    try:
        require_llm_provider_configured()
    except LlmProviderUnavailableError as exc:
        record_raw_event(
            session_id,
            event_type="interaction_failed",
            interaction_mode=interaction_mode,
            interaction_id=interaction_id,
            operation="conversational_request",
            duration_ms=(perf_counter() - started_at) * 1000,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return JsonResponse({"error": str(exc)}, status=503)
    return None


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
        "telemetryUrl": reverse("telemetry_event"),
        "runtimeMode": _runtime_mode(request),
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
    started_at = perf_counter()
    session_id = _ensure_session_id(request)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Richiesta non valida: formato JSON errato."}, status=400)
    interaction_id = new_interaction_id()

    violation_response = _mode_violation_response(
        request,
        blocked_mode="conversational_only",
        attempted_action="spatial_analysis_ui",
        interaction_mode="gui",
    )
    if violation_response is not None:
        return violation_response

    record_raw_event(
        session_id,
        event_type="interaction_started",
        interaction_id=interaction_id,
        operation="spatial_analysis",
        interaction_mode="gui",
        data={
            "selectedMunicipalityCount": sum(
                1 for area in payload.get("areas", [])
                if isinstance(area, dict) and area.get("kind") == "municipality"
            ),
            "drawnFeatureCount": sum(
                1 for area in payload.get("areas", [])
                if isinstance(area, dict) and area.get("kind") == "drawn"
            ),
        },
    )

    try:
        response = _build_request_orchestrator(request).handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_MAP,
                session_id=session_id,
                input=InteractionInput(geo_selection=payload),
            )
        )
    except ValueError as exc:
        record_raw_event(
            session_id,
            event_type="interaction_failed",
            interaction_id=interaction_id,
            operation="spatial_analysis",
            interaction_mode="gui",
            duration_ms=(perf_counter() - started_at) * 1000,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return JsonResponse({"error": str(exc)}, status=400)

    if response.analysis_result is None:
        record_raw_event(
            session_id,
            event_type="interaction_failed",
            interaction_id=interaction_id,
            operation="spatial_analysis",
            interaction_mode="gui",
            duration_ms=(perf_counter() - started_at) * 1000,
            error_type="missing_analysis_result",
            error_message="Analysis result missing",
        )
        return JsonResponse({"error": "Analisi non completata: risultato mancante."}, status=500)

    summary = response.analysis_result.get("summary", {})
    record_raw_event(
        session_id,
        event_type="analysis_completed",
        interaction_id=interaction_id,
        operation="spatial_analysis",
        interaction_mode="gui",
        analysis_id=response.analysis_result.get("analysisId"),
        duration_ms=(perf_counter() - started_at) * 1000,
        data={
            "summary": summary,
            "intersectedMunicipalities": response.analysis_result.get("intersectedMunicipalities", []),
        },
    )
    record_raw_event(
        session_id,
        event_type="interaction_completed",
        interaction_id=interaction_id,
        operation="spatial_analysis",
        interaction_mode="gui",
        duration_ms=(perf_counter() - started_at) * 1000,
        analysis_id=response.analysis_result.get("analysisId"),
    )
    payload_out = dict(response.analysis_result)
    payload_out["interactionId"] = interaction_id
    return JsonResponse(payload_out)


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
    started_at = perf_counter()
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
        comparison = compare_saved_analyses(records, price_options=PRICE_OPTIONS)
        record_raw_event(
            _ensure_session_id(request),
            event_type="comparison_completed",
            interaction_mode="gui",
            operation="analysis_history_compare",
            duration_ms=(perf_counter() - started_at) * 1000,
            data={"analysisIds": analysis_ids},
        )
        return JsonResponse(comparison)
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
    started_at = perf_counter()
    if not settings.AI_ASSISTANT_ENABLED:
        return HttpResponseNotFound()

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Richiesta non valida: formato JSON errato."}, status=400)
    interaction_id = _interaction_id_from_payload(payload)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    requested_mode = "voice" if metadata.get("interactionMode") == "voice" else "text"

    violation_response = _mode_violation_response(
        request,
        blocked_mode="gui_only",
        attempted_action="conversational_request",
        interaction_mode=requested_mode,
        interaction_id=interaction_id,
    )
    if violation_response is not None:
        return violation_response

    interaction_request = _build_text_interaction_request(request, payload, interaction_id=interaction_id)
    session_id = interaction_request.session_id
    interaction_mode = interaction_request.input.metadata.get("interactionMode", "text")
    record_raw_event(
        session_id,
        event_type="interaction_started",
        interaction_id=interaction_id,
        operation="conversational_request",
        interaction_mode=str(interaction_mode),
        user_text=interaction_request.input.primary_text() if interaction_mode != "voice" else None,
        transcript=(
            interaction_request.input.primary_text()
            if interaction_mode == "voice" and not interaction_request.input.metadata.get("transcriptLogged")
            else None
        ),
        data={
            "providerMode": _llm_status()["provider"],
            "providerModel": _llm_status()["model"],
        },
    )
    provider_failure = _provider_failure_response(
        session_id=session_id,
        interaction_id=interaction_id,
        interaction_mode=str(interaction_mode),
        started_at=started_at,
    )
    if provider_failure is not None:
        return provider_failure
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
        record_raw_event(
            session_id,
            event_type="interaction_failed",
            interaction_id=interaction_id,
            operation="conversational_request",
            interaction_mode=str(interaction_mode),
            duration_ms=(perf_counter() - started_at) * 1000,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        logger.warning(
            "Assistant interaction rejected session=%s error=%s",
            session_id,
            str(exc),
        )
        return JsonResponse({"error": str(exc)}, status=400)
    except LlmProviderUnavailableError as exc:
        record_raw_event(
            session_id,
            event_type="interaction_failed",
            interaction_id=interaction_id,
            operation="conversational_request",
            interaction_mode=str(interaction_mode),
            duration_ms=(perf_counter() - started_at) * 1000,
            error_type=type(exc).__name__,
            error_message=str(exc),
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
    record_raw_event(
        session_id,
        event_type="interaction_completed",
        interaction_id=interaction_id,
        operation=str(response.ui_hints.get("mode") or "conversational_request"),
        interaction_mode=str(interaction_mode),
        duration_ms=(perf_counter() - started_at) * 1000,
        assistant_response=_assistant_response_text(response),
        analysis_id=_interaction_analysis_id(response),
        data={
            "scenarioKey": (response.economic_result or {}).get("scenarioKey"),
            "priceEurPerTon": (response.economic_result or {}).get("priceEurPerTon"),
            "totalValueEur": (response.economic_result or {}).get("totalValueEur"),
            **_llm_log_details(response),
        },
    )
    return JsonResponse(_serialize_interaction_response(response, interaction_id=interaction_id))


@require_POST
def interact_stream(request):
    started_at = perf_counter()
    if not settings.AI_ASSISTANT_ENABLED:
        return HttpResponseNotFound()

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Richiesta non valida: formato JSON errato."}, status=400)
    interaction_id = _interaction_id_from_payload(payload)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    requested_mode = "voice" if metadata.get("interactionMode") == "voice" else "text"

    violation_response = _mode_violation_response(
        request,
        blocked_mode="gui_only",
        attempted_action="conversational_request",
        interaction_mode=requested_mode,
        interaction_id=interaction_id,
    )
    if violation_response is not None:
        return violation_response

    interaction_request = _build_text_interaction_request(request, payload, interaction_id=interaction_id)
    session_id = interaction_request.session_id
    interaction_mode = interaction_request.input.metadata.get("interactionMode", "text")
    record_raw_event(
        session_id,
        event_type="interaction_started",
        interaction_id=interaction_id,
        operation="conversational_request",
        interaction_mode=str(interaction_mode),
        user_text=interaction_request.input.primary_text() if interaction_mode != "voice" else None,
        transcript=(
            interaction_request.input.primary_text()
            if interaction_mode == "voice" and not interaction_request.input.metadata.get("transcriptLogged")
            else None
        ),
        data={
            "providerMode": _llm_status()["provider"],
            "providerModel": _llm_status()["model"],
        },
    )
    provider_failure = _provider_failure_response(
        session_id=session_id,
        interaction_id=interaction_id,
        interaction_mode=str(interaction_mode),
        started_at=started_at,
    )
    if provider_failure is not None:
        return provider_failure
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
            record_raw_event(
                session_id,
                event_type="interaction_failed",
                interaction_id=interaction_id,
                operation="conversational_request",
                interaction_mode=str(interaction_mode),
                duration_ms=(perf_counter() - started_at) * 1000,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            logger.warning(
                "Assistant stream rejected session=%s error=%s",
                session_id,
                str(exc),
            )
            yield _encode_sse("error", {"type": "error", "message": str(exc)})
        except LlmProviderUnavailableError as exc:
            record_raw_event(
                session_id,
                event_type="interaction_failed",
                interaction_id=interaction_id,
                operation="conversational_request",
                interaction_mode=str(interaction_mode),
                duration_ms=(perf_counter() - started_at) * 1000,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            logger.warning(
                "Assistant stream provider failure session=%s error=%s",
                session_id,
                str(exc),
            )
            yield _encode_sse("error", {"type": "error", "message": str(exc)})
        except Exception as exc:
            record_raw_event(
                session_id,
                event_type="interaction_failed",
                interaction_id=interaction_id,
                operation="conversational_request",
                interaction_mode=str(interaction_mode),
                duration_ms=(perf_counter() - started_at) * 1000,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            logger.exception("Assistant stream failed session=%s", session_id)
            yield _encode_sse("error", {"type": "error", "message": str(exc)})
        finally:
            if final_response is not None:
                record_raw_event(
                    session_id,
                    event_type="interaction_completed",
                    interaction_id=interaction_id,
                    operation=str(final_response.ui_hints.get("mode") or "conversational_request"),
                    interaction_mode=str(interaction_mode),
                    duration_ms=(perf_counter() - started_at) * 1000,
                    assistant_response=_assistant_response_text(final_response),
                    analysis_id=_interaction_analysis_id(final_response),
                    data={
                        "scenarioKey": (final_response.economic_result or {}).get("scenarioKey"),
                        "priceEurPerTon": (final_response.economic_result or {}).get(
                            "priceEurPerTon"
                        ),
                        "totalValueEur": (final_response.economic_result or {}).get(
                            "totalValueEur"
                        ),
                        **_llm_log_details(final_response),
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
    response["X-Interaction-Id"] = interaction_id
    return response


@require_POST
def voice_transcribe(request):
    if not settings.AI_ASSISTANT_ENABLED:
        return HttpResponseNotFound()

    violation_response = _mode_violation_response(
        request,
        blocked_mode="gui_only",
        attempted_action="voice_input",
        interaction_mode="voice",
    )
    if violation_response is not None:
        return violation_response

    interaction_id = str(request.POST.get("interactionId") or "").strip() or new_interaction_id()
    if not os.getenv("OPENAI_API_KEY", "").strip():
        record_raw_event(
            _ensure_session_id(request),
            event_type="error",
            interaction_id=interaction_id,
            operation="voice_transcription",
            interaction_mode="voice",
            error_type="voice_not_configured",
            error_message="OPENAI_API_KEY is not configured",
        )
        return JsonResponse(
            {"error": "Trascrizione vocale non configurata. Imposta OPENAI_API_KEY."},
            status=503,
        )

    audio_file = request.FILES.get("audio")
    if audio_file is None:
        record_raw_event(
            _ensure_session_id(request),
            event_type="error",
            interaction_id=interaction_id,
            operation="voice_transcription",
            interaction_mode="voice",
            error_type="missing_audio",
            error_message="Audio file missing",
        )
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
        record_raw_event(
            _ensure_session_id(request),
            event_type="error",
            interaction_id=interaction_id,
            operation="voice_transcription",
            interaction_mode="voice",
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return JsonResponse({"error": str(exc)}, status=400)
    except LlmProviderUnavailableError as exc:
        record_raw_event(
            _ensure_session_id(request),
            event_type="error",
            interaction_id=interaction_id,
            operation="voice_transcription",
            interaction_mode="voice",
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return JsonResponse({"error": str(exc)}, status=503)

    record_raw_event(
        _ensure_session_id(request),
        event_type="voice_transcribed",
        interaction_id=interaction_id,
        operation="voice_transcription",
        interaction_mode="voice",
        duration_ms=duration_ms,
        transcript=transcript,
    )
    return JsonResponse({"transcript": transcript, "interactionId": interaction_id})


@require_POST
def telemetry_event(request):
    """Accept only frontend-authoritative, non-conversational raw events."""
    try:
        payload = _read_json_body(request)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    event_type = str(payload.get("eventType") or "")
    if event_type not in FRONTEND_EVENT_TYPES:
        return JsonResponse({"error": "Tipo evento frontend non consentito."}, status=400)
    if any(
        payload.get(key)
        for key in ("userText", "transcript", "userTranscript", "assistantResponse")
    ):
        return JsonResponse(
            {"error": "Il testo conversazionale è registrato esclusivamente dal backend."},
            status=400,
        )

    try:
        event = record_raw_event(
            _ensure_session_id(request),
            event_type=event_type,
            interaction_mode=str(payload.get("interactionMode") or "gui"),
            interaction_id=str(payload.get("interactionId") or "") or None,
            operation=str(payload.get("operation") or "") or None,
            duration_ms=payload.get("durationMs"),
            analysis_id=str(payload.get("analysisId") or "") or None,
            error_type=str(payload.get("errorType") or "") or None,
            error_message=str(payload.get("errorMessage") or "") or None,
            data=payload.get("data") if isinstance(payload.get("data"), dict) else {},
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"eventId": event["eventId"]}, status=201)
