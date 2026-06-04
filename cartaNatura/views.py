from __future__ import annotations

import json

from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from cartaNatura.domain.vegetation import serialize_categories
from cartaNatura.services.gis_clip import clip_selection
from cartaNatura.services.payloads import parse_selection_payload


PRICE_OPTIONS = (
    {"label": "Costo sociale - 138 EUR", "value": 138},
    {"label": "Prezzo ombra - 303 EUR", "value": 303},
    {"label": "Prezzo nel mercato regolamentato - 82 EUR", "value": 82},
    {"label": "Prezzo nel mercato volontario - 20 EUR", "value": 20},
)


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
        "assets": {
            "loadingUrl": static("assets/small-load.gif"),
            "reportLogoUrl": "https://www.unidformazione.com/wp-content/uploads/2018/06/unisa-universita-di-salerno.jpg",
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
        selection = parse_selection_payload(payload)
        result = clip_selection(selection)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(
        {
            "clipped": json.loads(result.clipped.to_json()),
            "intersectedMunicipalities": result.intersected_municipalities,
        }
    )
