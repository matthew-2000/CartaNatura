from __future__ import annotations

import json

from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from cartaNatura.domain.vegetation import serialize_categories
from cartaNatura.interaction import (
    InteractionChannel,
    InteractionContext,
    InteractionInput,
    InteractionRequest,
    build_default_orchestrator,
)
from cartaNatura.interaction.session import DjangoSessionStore


PRICE_OPTIONS = (
    {"label": "Costo sociale - 138 EUR", "value": 138},
    {"label": "Prezzo ombra - 303 EUR", "value": 303},
    {"label": "Prezzo nel mercato regolamentato - 82 EUR", "value": 82},
    {"label": "Prezzo nel mercato volontario - 20 EUR", "value": 20},
)


def _ensure_session_id(request) -> str:
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key or "web-session"


def _build_request_orchestrator(request):
    return build_default_orchestrator(
        session_store=DjangoSessionStore(request.session),
    )


@ensure_csrf_cookie
def index(request):
    app_config = {
        "apiUrl": reverse("gis"),
        "interactionUrl": reverse("interact"),
        "priceOptions": PRICE_OPTIONS,
        "categories": serialize_categories(),
        "map": {
            "center": [40.8471407, 14.8639451],
            "zoom": 8,
        },
        "assistant": {
            "title": "Assistente Carta Natura",
        },
        "datasets": {
            "municipalitiesUrl": static("data/campania-municipalities-32633.geojson"),
            "boundariesUrl": static("data/campania-boundaries-4326.geojson"),
        },
    }
    return render(
        request,
        "cartaNatura/index.html",
        {"app_config_json": json.dumps(app_config)},
    )


@require_POST
def gis(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    try:
        response = _build_request_orchestrator(request).handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_MAP,
                session_id=_ensure_session_id(request),
                input=InteractionInput(geo_selection=payload),
            )
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    if response.analysis_result is None:
        return JsonResponse({"error": "Missing analysis result."}, status=500)

    return JsonResponse(response.analysis_result)


@require_POST
def interact(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    message = str(payload.get("message") or "").strip()
    context_payload = payload.get("context") if isinstance(payload.get("context"), dict) else {}

    try:
        response = _build_request_orchestrator(request).handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id=_ensure_session_id(request),
                input=InteractionInput(text=message, metadata={"source": "web_assistant"}),
                context=InteractionContext(
                    selected_municipalities=tuple(
                        str(name)
                        for name in context_payload.get("selectedMunicipalities", [])
                        if str(name).strip()
                    ),
                    current_map_extent=context_payload.get("mapExtent"),
                ),
            )
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(
        {
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
    )
