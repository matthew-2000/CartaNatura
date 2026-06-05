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
    InteractionInput,
    InteractionRequest,
    build_default_orchestrator,
)


PRICE_OPTIONS = (
    {"label": "Costo sociale - 138 EUR", "value": 138},
    {"label": "Prezzo ombra - 303 EUR", "value": 303},
    {"label": "Prezzo nel mercato regolamentato - 82 EUR", "value": 82},
    {"label": "Prezzo nel mercato volontario - 20 EUR", "value": 20},
)


interaction_orchestrator = build_default_orchestrator()


@ensure_csrf_cookie
def index(request):
    app_config = {
        "apiUrl": reverse("gis"),
        "priceOptions": PRICE_OPTIONS,
        "categories": serialize_categories(),
        "map": {
            "center": [40.8471407, 14.8639451],
            "zoom": 8,
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
        response = interaction_orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_MAP,
                session_id=request.headers.get("X-Session-Id") or "web-map",
                input=InteractionInput(geo_selection=payload),
            )
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    if response.analysis_result is None:
        return JsonResponse({"error": "Missing analysis result."}, status=500)

    return JsonResponse(response.analysis_result)
