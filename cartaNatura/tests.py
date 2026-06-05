from __future__ import annotations

from unittest.mock import patch

import geopandas
from django.test import Client, SimpleTestCase, override_settings
from shapely.geometry import box

from cartaNatura.interaction import (
    InteractionChannel,
    InteractionContext,
    InteractionInput,
    InteractionIntent,
    InteractionRequest,
    SessionContext,
)
from cartaNatura.interaction.orchestrator import build_default_orchestrator
from cartaNatura.interaction.resolvers import RuleBasedIntentResolver
from cartaNatura.interaction.session import InMemorySessionStore
from cartaNatura.schemas import SelectionArea, SelectionRequest
from cartaNatura.services.gis_clip import clip_selection
from cartaNatura.services.municipality_text import (
    extract_municipality_names,
    suggest_municipality_names,
)
from cartaNatura.services.payloads import parse_selection_payload


class FakeLlmProvider:
    def __init__(self, text: str):
        self._text = text

    def complete(self, prompt: str) -> str:
        del prompt
        return self._text


class PayloadParsingTests(SimpleTestCase):
    def test_parse_selection_payload_accepts_named_areas(self):
        payload = {
            "areas": [
                {
                    "kind": "drawn",
                    "geojson": {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {},
                                "geometry": box(0, 0, 1, 1).__geo_interface__,
                            }
                        ],
                    },
                }
            ]
        }

        selection = parse_selection_payload(payload)

        self.assertEqual(len(selection.areas), 1)
        self.assertEqual(selection.areas[0].kind, "drawn")

    def test_parse_selection_payload_rejects_duplicate_kind(self):
        payload = {
            "areas": [
                {
                    "kind": "drawn",
                    "geojson": {"type": "FeatureCollection", "features": [{"geometry": {}, "properties": {}, "type": "Feature"}]},
                },
                {
                    "kind": "drawn",
                    "geojson": {"type": "FeatureCollection", "features": [{"geometry": {}, "properties": {}, "type": "Feature"}]},
                },
            ]
        }

        with self.assertRaisesMessage(ValueError, "Duplicated area kind"):
            parse_selection_payload(payload)


class GisClipServiceTests(SimpleTestCase):
    @staticmethod
    def _municipality_geojson(name: str):
        municipality_frame = geopandas.GeoDataFrame(
            {"COMUNE": [name]},
            geometry=[box(0, 0, 1, 1)],
            crs="EPSG:4326",
        ).to_crs(epsg=32633)

        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"COMUNE": name},
                    "geometry": municipality_frame.geometry.iloc[0].__geo_interface__,
                }
            ],
        }

    @staticmethod
    def _drawn_geojson():
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": box(0, 0, 2, 1).__geo_interface__,
                }
            ],
        }

    @staticmethod
    def _nature_shapes():
        return geopandas.GeoDataFrame(
            {
                "CODICE": ["41.18"],
                "ettari": [10],
            },
            geometry=[box(0, 0, 2, 2)],
            crs="EPSG:4326",
        )

    @staticmethod
    def _campania_boundaries():
        return geopandas.GeoDataFrame(
            {"COMUNE": ["Comune Uno", "Acerra"]},
            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
            crs="EPSG:4326",
        )

    @staticmethod
    def _municipality_shapes_catalog():
        return geopandas.GeoDataFrame(
            {"COMUNE": ["Avellino", "Benevento"]},
            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
            crs="EPSG:4326",
        ).to_crs(epsg=32633)

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    def test_clip_selection_filters_municipalities_without_nature(
        self,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_nature_shapes.return_value = self._nature_shapes()
        load_campania_boundaries.return_value = self._campania_boundaries()

        selection = SelectionRequest(
            areas=(
                SelectionArea(
                    kind="municipalities",
                    geojson=self._municipality_geojson("Comune Uno"),
                ),
                SelectionArea(kind="drawn", geojson=self._drawn_geojson()),
            )
        )

        result = clip_selection(selection)

        self.assertEqual(result.intersected_municipalities, ["Comune Uno"])
        self.assertFalse(result.clipped.empty)


@override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
class ViewSmokeTests(SimpleTestCase):
    def test_index_renders(self):
        response = Client().get("/progettoGIS/cartaNatura/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"apiUrl": "/progettoGIS/cartaNatura/gis"')

    def test_gis_rejects_invalid_payload(self):
        response = Client().post(
            "/progettoGIS/cartaNatura/gis",
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_interact_analyzes_named_municipalities(
        self,
        load_municipality_shapes,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_municipality_shapes.return_value = GisClipServiceTests._municipality_shapes_catalog()
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = geopandas.GeoDataFrame(
            {"COMUNE": ["Avellino", "Benevento"]},
            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
            crs="EPSG:4326",
        )

        response = Client().post(
            "/progettoGIS/cartaNatura/interact",
            data='{"message": "Analizza Avellino e Benevento"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["analysisResult"]["requestedMunicipalities"],
            ["Avellino", "Benevento"],
        )

    @override_settings(AI_ASSISTANT_ENABLED=False)
    def test_interact_returns_404_when_assistant_disabled(self):
        response = Client().post(
            "/progettoGIS/cartaNatura/interact",
            data='{"message": "Analizza Avellino"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)


class InteractionSessionContextTests(SimpleTestCase):
    def test_session_context_round_trip_is_serializable(self):
        context = SessionContext(
            selection_payload={"areas": [{"kind": "drawn"}]},
            last_analysis={"intersectedMunicipalities": ["Avellino"]},
            last_intent=InteractionIntent.ANALYZE_SELECTION,
            metadata={"channel": "web_map"},
        )

        restored = SessionContext.from_dict(context.to_dict())

        self.assertEqual(restored, context)


class RuleBasedIntentResolverTests(SimpleTestCase):
    def test_resolver_routes_structured_selection_to_analysis(self):
        request = InteractionRequest(
            channel=InteractionChannel.WEB_MAP,
            session_id="session-1",
            input=InteractionInput(
                geo_selection={
                    "areas": [
                        {
                            "kind": "drawn",
                            "geojson": GisClipServiceTests._drawn_geojson(),
                        }
                    ]
                }
            ),
            context=InteractionContext(),
        )

        resolution = RuleBasedIntentResolver().resolve(request, SessionContext())

        self.assertEqual(resolution.command.intent, InteractionIntent.ANALYZE_SELECTION)
        self.assertIsNone(resolution.clarification_message)

    def test_resolver_detects_reset_requests(self):
        request = InteractionRequest(
            channel=InteractionChannel.WEB_CHAT,
            session_id="session-1",
            input=InteractionInput(text="pulisci sessione"),
        )

        resolution = RuleBasedIntentResolver().resolve(request, SessionContext())

        self.assertEqual(resolution.command.intent, InteractionIntent.RESET_SESSION)

    @patch("cartaNatura.interaction.resolvers.extract_municipality_names")
    def test_resolver_detects_municipality_analysis_requests(self, extract_names):
        extract_names.return_value = ["Avellino", "Benevento"]
        request = InteractionRequest(
            channel=InteractionChannel.WEB_CHAT,
            session_id="session-1",
            input=InteractionInput(text="analizza Avellino e Benevento"),
        )

        resolution = RuleBasedIntentResolver().resolve(request, SessionContext())

        self.assertEqual(resolution.command.intent, InteractionIntent.ANALYZE_MUNICIPALITIES)
        self.assertEqual(
            resolution.command.payload["municipality_names"],
            ["Avellino", "Benevento"],
        )

    @patch("cartaNatura.interaction.resolvers.extract_municipality_names")
    @patch("cartaNatura.interaction.resolvers.suggest_municipality_names")
    def test_resolver_uses_single_suggestion_as_analysis_target(
        self,
        suggest_names,
        extract_names,
    ):
        extract_names.return_value = []
        suggest_names.return_value = ["Avellino"]
        request = InteractionRequest(
            channel=InteractionChannel.WEB_CHAT,
            session_id="session-1",
            input=InteractionInput(text="analizza Avell"),
        )

        resolution = RuleBasedIntentResolver().resolve(request, SessionContext())

        self.assertEqual(resolution.command.intent, InteractionIntent.ANALYZE_MUNICIPALITIES)
        self.assertEqual(resolution.command.payload["municipality_names"], ["Avellino"])

    @patch("cartaNatura.interaction.resolvers.extract_municipality_names")
    @patch("cartaNatura.interaction.resolvers.suggest_municipality_names")
    def test_resolver_returns_clarification_for_ambiguous_suggestions(
        self,
        suggest_names,
        extract_names,
    ):
        extract_names.return_value = []
        suggest_names.return_value = ["San Giorgio a Cremano", "San Gennaro Vesuviano"]
        request = InteractionRequest(
            channel=InteractionChannel.WEB_CHAT,
            session_id="session-1",
            input=InteractionInput(text="analizza san"),
        )

        resolution = RuleBasedIntentResolver().resolve(request, SessionContext())

        self.assertEqual(resolution.command.intent, InteractionIntent.UNKNOWN)
        self.assertIn("San Giorgio a Cremano", resolution.clarification_message)


class MunicipalityTextTests(SimpleTestCase):
    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_extract_municipality_names_preserves_text_order(self, load_municipality_shapes):
        load_municipality_shapes.return_value = GisClipServiceTests._municipality_shapes_catalog()

        names = extract_municipality_names("Analizza Benevento e Avellino")

        self.assertEqual(names, ["Benevento", "Avellino"])

    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_suggest_municipality_names_handles_partial_matches(self, load_municipality_shapes):
        load_municipality_shapes.return_value = GisClipServiceTests._municipality_shapes_catalog()

        names = suggest_municipality_names("Analizza Avell")

        self.assertEqual(names, ["Avellino"])


class InteractionOrchestratorTests(SimpleTestCase):
    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    def test_orchestrator_runs_structured_selection_analysis(
        self,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = GisClipServiceTests._campania_boundaries()
        session_store = InMemorySessionStore()
        orchestrator = build_default_orchestrator(session_store=session_store)

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_MAP,
                session_id="session-42",
                input=InteractionInput(
                    geo_selection={
                        "areas": [
                            {
                                "kind": "drawn",
                                "geojson": GisClipServiceTests._drawn_geojson(),
                            }
                        ]
                    }
                ),
            )
        )

        self.assertIsNotNone(response.analysis_result)
        self.assertEqual(
            session_store.load("session-42").last_intent,
            InteractionIntent.ANALYZE_SELECTION,
        )

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_orchestrator_runs_text_municipality_analysis(
        self,
        load_municipality_shapes,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_municipality_shapes.return_value = GisClipServiceTests._municipality_shapes_catalog()
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = geopandas.GeoDataFrame(
            {"COMUNE": ["Avellino", "Benevento"]},
            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
            crs="EPSG:4326",
        )
        session_store = InMemorySessionStore()
        orchestrator = build_default_orchestrator(session_store=session_store)

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="session-text",
                input=InteractionInput(text="analizza Avellino e Benevento"),
            )
        )

        self.assertEqual(response.commands[0].intent, InteractionIntent.ANALYZE_MUNICIPALITIES)
        self.assertEqual(
            response.analysis_result["requestedMunicipalities"],
            ["Avellino", "Benevento"],
        )

    def test_orchestrator_clears_session_on_reset(self):
        session_store = InMemorySessionStore()
        session_store.save(
            "session-reset",
            SessionContext(
                selection_payload={"areas": [{"kind": "drawn"}]},
                last_analysis={"status": "done"},
                last_intent=InteractionIntent.ANALYZE_SELECTION,
            ),
        )
        orchestrator = build_default_orchestrator(session_store=session_store)

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="session-reset",
                input=InteractionInput(text="reset"),
            )
        )

        self.assertEqual(response.commands[0].intent, InteractionIntent.RESET_SESSION)
        self.assertEqual(session_store.load("session-reset"), SessionContext())

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_orchestrator_uses_llm_provider_when_available(
        self,
        load_municipality_shapes,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_municipality_shapes.return_value = GisClipServiceTests._municipality_shapes_catalog()
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = geopandas.GeoDataFrame(
            {"COMUNE": ["Avellino", "Benevento"]},
            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
            crs="EPSG:4326",
        )
        session_store = InMemorySessionStore()
        orchestrator = build_default_orchestrator(
            session_store=session_store,
            llm_provider=FakeLlmProvider("Sintesi LLM mockata."),
        )

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="session-llm",
                input=InteractionInput(text="analizza Avellino e Benevento"),
            )
        )

        self.assertEqual(response.messages[0].text, "Sintesi LLM mockata.")
        self.assertEqual(response.ui_hints["providerMode"], "openai")
