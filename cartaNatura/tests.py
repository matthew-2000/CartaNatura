from __future__ import annotations

from unittest.mock import patch

import geopandas
from django.test import Client, SimpleTestCase, override_settings
from shapely.geometry import box

from cartaNatura.interaction import (
    InMemoryAnalysisStore,
    InteractionChannel,
    InteractionContext,
    InteractionInput,
    InteractionIntent,
    InteractionRequest,
    SessionContext,
)
from cartaNatura.interaction.analysis_store import StoredAnalysis, new_stored_analysis
from cartaNatura.interaction.orchestrator import build_default_orchestrator
from cartaNatura.interaction.resolvers import RuleBasedIntentResolver
from cartaNatura.interaction.session import InMemorySessionStore
from cartaNatura.interaction.tools import build_default_tool_registry
from cartaNatura.interaction.tools.analysis_history import (
    compare_analyses,
    get_last_analysis,
    get_recent_analyses,
)
from cartaNatura.interaction.ui_context import build_interaction_context
from cartaNatura.interaction.tools.contracts import ToolName
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
    @patch("cartaNatura.interaction.orchestrator.build_optional_llm_provider")
    def test_interact_analyzes_named_municipalities(
        self,
        build_optional_llm_provider,
        load_municipality_shapes,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        build_optional_llm_provider.return_value = FakeLlmProvider("Sintesi LLM mockata.")
        load_municipality_shapes.return_value = GisClipServiceTests._municipality_shapes_catalog()
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = geopandas.GeoDataFrame(
            {"COMUNE": ["Avellino", "Benevento"]},
            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
            crs="EPSG:4326",
        )
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
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
        self.assertEqual(response.json()["uiHints"]["providerMode"], "openai")

    @override_settings(AI_ASSISTANT_ENABLED=False)
    def test_interact_returns_404_when_assistant_disabled(self):
        response = Client().post(
            "/progettoGIS/cartaNatura/interact",
            data='{"message": "Analizza Avellino"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_interact_returns_503_without_openai_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            response = Client().post(
                "/progettoGIS/cartaNatura/interact",
                data='{"message": "Analizza Avellino"}',
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 503)


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

    def test_build_interaction_context_ignores_empty_selection_payload(self):
        context = build_interaction_context(
            {
                "selectedMunicipalities": [],
                "mapExtent": {"south": 0, "west": 0, "north": 1, "east": 1},
                "selectionPayload": {"areas": []},
            }
        )

        self.assertIsNone(context.current_selection_payload)


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

    def test_resolver_routes_current_selection_analysis_from_context(self):
        request = InteractionRequest(
            channel=InteractionChannel.WEB_CHAT,
            session_id="session-ctx",
            input=InteractionInput(text="analizza selezione corrente"),
            context=InteractionContext(
                current_selection_payload={
                    "areas": [
                        {
                            "kind": "drawn",
                            "geojson": GisClipServiceTests._drawn_geojson(),
                        }
                    ]
                }
            ),
        )

        resolution = RuleBasedIntentResolver().resolve(request, SessionContext())

        self.assertEqual(resolution.command.intent, InteractionIntent.ANALYZE_SELECTION)
        self.assertEqual(resolution.command.payload["areas"][0]["kind"], "drawn")


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
        analysis_store = InMemoryAnalysisStore()
        orchestrator = build_default_orchestrator(
            session_store=session_store,
            analysis_store=analysis_store,
        )

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
        self.assertIsNotNone(analysis_store.get_last())

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
        analysis_store = InMemoryAnalysisStore()
        orchestrator = build_default_orchestrator(
            session_store=session_store,
            llm_provider=FakeLlmProvider("Sintesi LLM mockata."),
            analysis_store=analysis_store,
        )

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
        self.assertEqual(analysis_store.get_last().requested_municipalities, ("Avellino", "Benevento"))

    def test_orchestrator_clears_session_on_reset(self):
        session_store = InMemorySessionStore()
        analysis_store = InMemoryAnalysisStore()
        session_store.save(
            "session-reset",
            SessionContext(
                selection_payload={"areas": [{"kind": "drawn"}]},
                last_analysis={"status": "done"},
                last_intent=InteractionIntent.ANALYZE_SELECTION,
            ),
        )
        analysis_store.save(
            new_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 0, "totalHectares": 0, "hasSupportedVegetation": False, "topCategory": None},
            )
        )
        orchestrator = build_default_orchestrator(
            session_store=session_store,
            analysis_store=analysis_store,
        )

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="session-reset",
                input=InteractionInput(text="reset"),
            )
        )

        self.assertEqual(response.commands[0].intent, InteractionIntent.RESET_SESSION)
        self.assertEqual(session_store.load("session-reset"), SessionContext())
        self.assertIsNone(analysis_store.get_last())

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
        analysis_store = InMemoryAnalysisStore()
        orchestrator = build_default_orchestrator(
            session_store=session_store,
            llm_provider=FakeLlmProvider("Sintesi LLM mockata."),
            analysis_store=analysis_store,
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
        self.assertIsNotNone(analysis_store.get_last())

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    def test_orchestrator_runs_current_selection_analysis_from_context(
        self,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = GisClipServiceTests._campania_boundaries()
        analysis_store = InMemoryAnalysisStore()
        orchestrator = build_default_orchestrator(
            session_store=InMemorySessionStore(),
            llm_provider=FakeLlmProvider("Sintesi LLM mockata."),
            analysis_store=analysis_store,
        )

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="session-current-selection",
                input=InteractionInput(text="analizza selezione corrente"),
                context=InteractionContext(
                    current_selection_payload={
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

        self.assertEqual(response.commands[0].intent, InteractionIntent.ANALYZE_SELECTION)
        self.assertIsNotNone(response.analysis_result["analysisId"])
        self.assertEqual(analysis_store.get_last().source, "selection")

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_orchestrator_compares_recent_analyses(
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
        analysis_store = InMemoryAnalysisStore()
        orchestrator = build_default_orchestrator(
            session_store=InMemorySessionStore(),
            llm_provider=FakeLlmProvider("Confronto LLM mockato."),
            analysis_store=analysis_store,
        )

        orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="session-a",
                input=InteractionInput(text="analizza Avellino"),
            )
        )
        orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="session-b",
                input=InteractionInput(text="analizza Benevento"),
            )
        )

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="session-compare",
                input=InteractionInput(text="confronta ultime due analisi"),
            )
        )

        self.assertEqual(response.commands[0].intent, InteractionIntent.COMPARE_ANALYSES)
        self.assertEqual(response.messages[0].text, "Confronto LLM mockato.")
        self.assertIn("delta", response.analysis_result)

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_orchestrator_rejects_text_analysis_without_llm_provider(
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
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            orchestrator = build_default_orchestrator(
                session_store=InMemorySessionStore(),
                llm_provider=None,
            )
            with self.assertRaisesMessage(ValueError, "Assistente AI non configurato"):
                orchestrator.handle(
                    InteractionRequest(
                        channel=InteractionChannel.WEB_CHAT,
                        session_id="session-no-llm",
                        input=InteractionInput(text="analizza Avellino e Benevento"),
                    )
                )


class AnalysisStoreAndToolsTests(SimpleTestCase):
    def test_inmemory_analysis_store_returns_last_saved_item(self):
        store = InMemoryAnalysisStore()
        first = store.save(
            new_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 1, "totalHectares": 2, "hasSupportedVegetation": True, "topCategory": None},
            )
        )
        second = store.save(
            new_stored_analysis(
                source="selection",
                summary={"items": [], "totalCo2": 3, "totalHectares": 4, "hasSupportedVegetation": True, "topCategory": None},
            )
        )

        self.assertEqual(store.get(first.analysis_id), first)
        self.assertEqual(store.get_last(), second)

    def test_tool_registry_returns_last_analysis(self):
        store = InMemoryAnalysisStore()
        saved = store.save(
            new_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 3, "totalHectares": 4, "hasSupportedVegetation": True, "topCategory": None},
                requested_municipalities=["Avellino"],
                intersected_municipalities=["Avellino"],
            )
        )
        registry = build_default_tool_registry(store)

        payload = registry.execute(ToolName.GET_LAST_ANALYSIS)

        self.assertEqual(payload["analysisId"], saved.analysis_id)
        self.assertEqual(payload["requestedMunicipalities"], ["Avellino"])

    def test_get_recent_analyses_returns_newest_first(self):
        store = InMemoryAnalysisStore()
        first = store.save(
            new_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 1, "totalHectares": 2, "hasSupportedVegetation": True, "topCategory": None},
            )
        )
        second = store.save(
            new_stored_analysis(
                source="selection",
                summary={"items": [], "totalCo2": 3, "totalHectares": 4, "hasSupportedVegetation": True, "topCategory": None},
            )
        )

        payload = get_recent_analyses(analysis_store=store, limit=2)

        self.assertEqual(payload["items"][0]["analysisId"], second.analysis_id)
        self.assertEqual(payload["items"][1]["analysisId"], first.analysis_id)

    def test_compare_analyses_returns_numeric_delta(self):
        store = InMemoryAnalysisStore()
        left = store.save(
            new_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 10, "totalHectares": 20, "hasSupportedVegetation": True, "topCategory": None},
            )
        )
        right = store.save(
            new_stored_analysis(
                source="selection",
                summary={"items": [], "totalCo2": 15, "totalHectares": 24, "hasSupportedVegetation": True, "topCategory": None},
            )
        )

        comparison = compare_analyses(
            analysis_store=store,
            left_analysis_id=left.analysis_id,
            right_analysis_id=right.analysis_id,
        )

        self.assertEqual(comparison["delta"]["totalCo2"], 5)
        self.assertEqual(comparison["delta"]["totalHectares"], 4)
