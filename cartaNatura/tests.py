from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import geopandas
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from shapely.geometry import box

from cartaNatura.domain.economics import (
    PRICE_OPTIONS,
    calculate_economic_value,
    compare_economic_scenarios,
)
from cartaNatura.interaction import (
    InMemoryAnalysisStore,
    InteractionChannel,
    InteractionContext,
    InteractionInput,
    InteractionIntent,
    InteractionRequest,
    SessionContext,
)
from cartaNatura.interaction.analysis_store import StoredAnalysis, create_stored_analysis
from cartaNatura.interaction.observability import summarize_openai_usage
from cartaNatura.interaction.llm import (
    LlmProviderConfigurationError,
    OllamaChatLlmProvider,
    build_optional_llm_provider,
    get_llm_provider_status,
    _build_ollama_messages,
)
from cartaNatura.interaction.orchestrator import build_default_orchestrator
from cartaNatura.interaction.resolvers import RuleBasedIntentResolver
from cartaNatura.interaction.session import InMemorySessionStore
from cartaNatura.interaction.tools import build_default_tool_registry
from cartaNatura.interaction.tools.analysis_history import (
    compare_analyses,
    compare_recent_analyses,
    compare_saved_history_analyses,
    get_last_analysis,
    get_recent_analyses,
)
from cartaNatura.interaction.tools.gis_analysis import analyze_selection
from cartaNatura.interaction.tools.map_filtering import filter_analysis_categories
from cartaNatura.interaction.ui_context import build_interaction_context
from cartaNatura.interaction.tools.contracts import ToolName
from cartaNatura.interaction.voice import transcribe_uploaded_audio
from cartaNatura.schemas import SelectionArea, SelectionRequest
from cartaNatura.services.gis_clip import clip_selection
from cartaNatura.services.municipality_text import (
    extract_municipality_names,
    suggest_municipality_names,
)
from cartaNatura.services.analysis_compare import compare_saved_analyses
from cartaNatura.services.payloads import parse_selection_payload
from cartaNatura.experiments import (
    STUDY_CONTEXT_SESSION_KEY,
    create_study_session,
    export_experiment_log,
    export_study_events_jsonl,
    export_study_session,
    record_experiment_event,
    record_study_event,
)


class FakeLlmProvider:
    def __init__(self, text: str):
        self._text = text

    def complete(self, prompt: str) -> str:
        del prompt
        return self._text


class FakeResponsesProvider:
    def __init__(self, responses: list[dict[str, object]]):
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def create_response(self, **payload):
        self.calls.append(payload)
        if not self._responses:
            raise AssertionError("No scripted Responses payload left.")
        return self._responses.pop(0)

    def complete(self, prompt: str) -> str:
        del prompt
        raise AssertionError("complete() should not be used in runtime tests.")


class FakeHybridProvider:
    def __init__(self, text: str, responses: list[dict[str, object]] | None = None):
        self._text = text
        self._responses = list(responses or [])
        self.complete_calls: list[str] = []
        self.response_calls: list[dict[str, object]] = []

    def complete(self, prompt: str) -> str:
        self.complete_calls.append(prompt)
        return self._text

    def create_response(self, **payload):
        self.response_calls.append(payload)
        if not self._responses:
            raise AssertionError("No scripted Responses payload left.")
        return self._responses.pop(0)


class FakeStreamEvent:
    def __init__(self, event_type: str, **payload):
        self.type = event_type
        for key, value in payload.items():
            setattr(self, key, value)


class FakeStreamItem:
    def __init__(self, item_type: str, **payload):
        self.type = item_type
        for key, value in payload.items():
            setattr(self, key, value)


class FakeStreamResponseRef:
    def __init__(self, response_id: str):
        self.id = response_id


class FakeFinalResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload = payload

    def model_dump(self, mode: str = "python"):
        del mode
        return self._payload


class FakeResponseStreamManager:
    def __init__(self, events: list[FakeStreamEvent], final_payload: dict[str, object]):
        self._events = list(events)
        self._final_response = FakeFinalResponse(final_payload)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_response(self):
        return self._final_response


class FakeStreamingProvider:
    def __init__(self, streams: list[dict[str, object]]):
        self._streams = list(streams)
        self.stream_calls: list[dict[str, object]] = []

    def create_response(self, **payload):
        del payload
        raise AssertionError("create_response() should not be used in streaming runtime tests.")

    def stream_response(self, **payload):
        self.stream_calls.append(payload)
        if not self._streams:
            raise AssertionError("No scripted stream payload left.")
        scripted = self._streams.pop(0)
        return FakeResponseStreamManager(
            scripted["events"],
            scripted["final_payload"],
        )

    def complete(self, prompt: str) -> str:
        del prompt
        raise AssertionError("complete() should not be used in streaming runtime tests.")


class FakeOllamaStyleProvider(FakeResponsesProvider):
    provider_name = "ollama"
    runtime_name = "ollama_chat"
    model = "llama3.1"


class LlmProviderConfigurationTests(SimpleTestCase):
    def test_selects_openai_provider_from_configuration(self):
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "openai",
                "LLM_MODEL": "",
                "LLM_BASE_URL": "",
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "gpt-test",
                "OPENAI_BASE_URL": "https://example.test/v1",
            },
        ):
            provider = build_optional_llm_provider()
            status = get_llm_provider_status()

        self.assertEqual(provider.provider_name, "openai")
        self.assertEqual(provider.model, "gpt-test")
        self.assertTrue(status["configured"])
        self.assertEqual(status["provider"], "openai")

    def test_selects_ollama_provider_from_configuration(self):
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "ollama",
                "LLM_MODEL": "",
                "LLM_BASE_URL": "",
                "OLLAMA_MODEL": "llama3.1",
                "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
                "OLLAMA_THINK": "false",
                "OPENAI_API_KEY": "test-key",
            },
        ):
            provider = build_optional_llm_provider()
            status = get_llm_provider_status()

        self.assertEqual(provider.provider_name, "ollama")
        self.assertEqual(provider.model, "llama3.1")
        self.assertFalse(provider.think)
        self.assertTrue(status["configured"])
        self.assertEqual(status["provider"], "ollama")
        self.assertFalse(status["think"])

    def test_selected_ollama_provider_does_not_fallback_to_openai(self):
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "ollama",
                "LLM_MODEL": "",
                "LLM_BASE_URL": "",
                "OLLAMA_MODEL": "",
                "OLLAMA_BASE_URL": "",
                "OPENAI_API_KEY": "test-key",
            },
        ):
            status = get_llm_provider_status()
            with self.assertRaises(LlmProviderConfigurationError):
                build_optional_llm_provider()

        self.assertFalse(status["configured"])
        self.assertIn("Ollama", status["error"])

    def test_ollama_normalizes_tool_calls_to_runtime_contract(self):
        body = OllamaChatLlmProvider._normalize_chat_response(
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "tool_1",
                            "function": {
                                "name": "get_methodology",
                                "arguments": {},
                            },
                        }
                    ]
                },
                "prompt_eval_count": 3,
                "eval_count": 2,
            }
        )

        self.assertEqual(body["output"][0]["type"], "function_call")
        self.assertEqual(body["output"][0]["name"], "get_methodology")
        self.assertEqual(body["usage"]["total_tokens"], 5)

    def test_ollama_payload_can_disable_thinking(self):
        provider = OllamaChatLlmProvider(
            model="qwen3.5:9b",
            base_url="http://127.0.0.1:11434",
            think=False,
        )

        payload = provider._build_chat_payload(
            {
                "instructions": "Rispondi in italiano.",
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": "ciao"}],
                    }
                ],
                "tools": [],
            },
            stream=False,
        )

        self.assertEqual(payload["model"], "qwen3.5:9b")
        self.assertFalse(payload["think"])

    def test_ollama_does_not_force_json_format_while_planning_tool_calls(self):
        provider = OllamaChatLlmProvider(
            model="qwen3.5:4b",
            base_url="http://127.0.0.1:11434",
        )
        payload = {
            "instructions": "Usa i tool quando servono.",
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "analizza Avellino"}],
                }
            ],
            "tools": [
                {
                    "name": "search_municipalities",
                    "description": "Cerca comuni.",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            "text": {
                "format": {
                    "schema": {
                        "type": "object",
                        "properties": {"assistant_text": {"type": "string"}},
                    }
                }
            },
            "provider_metadata": {"ollama_response_phase": "tool_planning"},
        }

        planning_body = provider._build_chat_payload(payload, stream=False)
        final_body = provider._build_chat_payload(
            {
                **payload,
                "provider_metadata": {"ollama_response_phase": "final"},
            },
            stream=False,
        )

        self.assertNotIn("format", planning_body)
        self.assertIn("format", final_body)

    def test_ollama_rebuilds_current_tool_turn_for_stateless_chat_api(self):
        messages = _build_ollama_messages(
            {
                "instructions": "Sistema.",
                "input": [
                    {
                        "type": "function_call_output",
                        "call_id": "call_search",
                        "output": '{"matches":["Avellino"]}',
                    }
                ],
                "provider_metadata": {
                    "ollama_current_turn_input": [
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": "analizza Avellino"}],
                        }
                    ],
                    "ollama_tool_exchanges": [
                        {
                            "tool_calls": [
                                {
                                    "call_id": "call_search",
                                    "name": "search_municipalities",
                                    "arguments": {"query": "Avellino", "limit": 5},
                                }
                            ],
                            "tool_outputs": [
                                {
                                    "type": "function_call_output",
                                    "call_id": "call_search",
                                    "output": '{"matches":["Avellino"]}',
                                }
                            ],
                        }
                    ],
                },
            }
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[1]["content"], "analizza Avellino")
        self.assertEqual(messages[2]["role"], "assistant")
        self.assertEqual(
            messages[2]["tool_calls"][0]["function"]["name"],
            "search_municipalities",
        )
        self.assertEqual(messages[3]["role"], "tool")
        self.assertEqual(messages[3]["tool_call_id"], "call_search")


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

        with self.assertRaisesMessage(ValueError, "Area duplicata"):
            parse_selection_payload(payload)

    def test_parse_selection_payload_rejects_empty_feature_collection(self):
        payload = {
            "areas": [
                {
                    "kind": "drawn",
                    "geojson": {"type": "FeatureCollection", "features": []},
                }
            ]
        }

        with self.assertRaisesMessage(ValueError, "non contiene geometrie"):
            parse_selection_payload(payload)

    def test_parse_selection_payload_rejects_wrong_declared_crs(self):
        payload = {
            "areas": [
                {
                    "kind": "drawn",
                    "geojson": {
                        "type": "FeatureCollection",
                        "crs": {"type": "name", "properties": {"name": "EPSG:3857"}},
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

        with self.assertRaisesMessage(ValueError, "CRS non supportato"):
            parse_selection_payload(payload)

    def test_parse_selection_payload_accepts_urn_epsg_crs(self):
        payload = {
            "areas": [
                {
                    "kind": "drawn",
                    "geojson": {
                        "type": "FeatureCollection",
                        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
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

        self.assertEqual(selection.areas[0].kind, "drawn")


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

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    def test_clip_selection_allows_area_without_nature_results(
        self,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_nature_shapes.return_value = self._nature_shapes()
        load_campania_boundaries.return_value = self._campania_boundaries()
        selection = SelectionRequest(
            areas=(
                SelectionArea(
                    kind="drawn",
                    geojson={
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {},
                                "geometry": box(10, 10, 11, 11).__geo_interface__,
                            }
                        ],
                    },
                ),
            )
        )

        result = clip_selection(selection)

        self.assertTrue(result.clipped.empty)
        self.assertEqual(result.intersected_municipalities, [])


class AnalysisCompareServiceTests(SimpleTestCase):
    @staticmethod
    def _record(
        analysis_id: str,
        label: str,
        *,
        total_co2: float | None,
        total_hectares: float | None,
        items: list[dict[str, object]],
        top_category: dict[str, object] | None = None,
    ) -> StoredAnalysis:
        return StoredAnalysis(
            analysis_id=analysis_id,
            source="selection",
            created_at=f"2026-06-24T10:0{analysis_id[-1]}:00+00:00",
            label=label,
            selection_kind="drawn",
            has_drawn_geometry=True,
            summary={
                "totalCo2": total_co2,
                "totalHectares": total_hectares,
                "topCategory": top_category,
                "hasSupportedVegetation": bool(items),
                "items": items,
            },
            intersected_municipalities=(label,),
            metadata={"channel": "web_map"},
        )

    def test_compare_saved_analyses_handles_two_records_pairwise_and_rankings(self):
        first = self._record(
            "analysis_1",
            "A",
            total_co2=100,
            total_hectares=50,
            top_category={"key": "faggete", "label": "Faggete"},
            items=[
                {"key": "faggete", "label": "Faggete", "hectares": 50, "co2PerHectare": 2}
            ],
        )
        second = self._record(
            "analysis_2",
            "B",
            total_co2=150,
            total_hectares=30,
            top_category={"key": "castagneti", "label": "Castagneti"},
            items=[
                {"key": "castagneti", "label": "Castagneti", "hectares": 30, "co2PerHectare": 5}
            ],
        )

        comparison = compare_saved_analyses([first, second], price_options=({"label": "Scenario", "value": 20},))

        self.assertEqual(comparison["analyses"][0]["co2PerHectare"], 2)
        self.assertEqual(comparison["analyses"][1]["co2PerHectare"], 5)
        self.assertEqual(comparison["rankings"]["totalCo2"][0]["id"], "analysis_2")
        self.assertEqual(comparison["rankings"]["totalHectares"][0]["id"], "analysis_1")
        self.assertEqual(comparison["rankings"]["co2PerHectare"][0]["id"], "analysis_2")
        self.assertEqual(comparison["pairwise"]["totalCo2"]["absolute"], 50)
        self.assertEqual(comparison["pairwise"]["totalCo2"]["percent"], 50)
        self.assertEqual(comparison["pairwise"]["higherTotalCo2"]["id"], "analysis_2")
        self.assertEqual(comparison["pairwise"]["higherCo2PerHectare"]["id"], "analysis_2")
        self.assertEqual(comparison["economicComparison"][0]["values"][1]["value"], 3000)
        self.assertEqual(comparison["economicComparison"][0]["ranking"][0]["id"], "analysis_2")

    def test_compare_saved_analyses_handles_multiple_records_and_category_overlap(self):
        records = [
            self._record(
                "analysis_1",
                "A",
                total_co2=100,
                total_hectares=50,
                items=[
                    {"key": "faggete", "label": "Faggete", "hectares": 20, "co2PerHectare": 2},
                    {"key": "leccete", "label": "Leccete", "hectares": 30, "co2PerHectare": 2},
                ],
            ),
            self._record(
                "analysis_2",
                "B",
                total_co2=60,
                total_hectares=20,
                items=[
                    {"key": "faggete", "label": "Faggete", "hectares": 20, "co2PerHectare": 3},
                ],
            ),
            self._record(
                "analysis_3",
                "C",
                total_co2=0,
                total_hectares=0,
                items=[],
            ),
        ]

        comparison = compare_saved_analyses(records)

        self.assertIsNone(comparison["pairwise"])
        self.assertEqual(comparison["rankings"]["totalCo2"][0]["id"], "analysis_1")
        self.assertEqual(comparison["rankings"]["co2PerHectare"][0]["id"], "analysis_2")
        self.assertIsNone(comparison["analyses"][2]["co2PerHectare"])
        self.assertEqual(comparison["categoriesComparison"]["commonCategories"], [])
        self.assertIn("faggete", comparison["categoriesComparison"]["partialCategories"])
        self.assertIn("leccete", comparison["categoriesComparison"]["partialCategories"])

    def test_compare_saved_analyses_rejects_less_than_two_records(self):
        with self.assertRaisesMessage(ValueError, "almeno due analisi"):
            compare_saved_analyses([])


@override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
class ViewSmokeTests(SimpleTestCase):
    @staticmethod
    def _history_analysis_payload():
        return {
            "areas": [
                {
                    "kind": "drawn",
                    "geojson": GisClipServiceTests._drawn_geojson(),
                }
            ]
        }

    @staticmethod
    def _post_history_analysis(client: Client):
        return client.post(
            "/progettoGIS/cartaNatura/gis",
            data=json.dumps(ViewSmokeTests._history_analysis_payload()),
            content_type="application/json",
        )

    @staticmethod
    def _saved_history_record(analysis_id: str, label: str, total_co2: float, total_hectares: float):
        return StoredAnalysis(
            analysis_id=analysis_id,
            source="selection",
            created_at="2026-06-24T10:00:00+00:00",
            label=label,
            selection_kind="drawn",
            has_drawn_geometry=True,
            summary={
                "items": [
                    {
                        "key": "faggete",
                        "label": "Faggete",
                        "hectares": total_hectares,
                        "co2PerHectare": total_co2 / total_hectares if total_hectares else 0,
                    }
                ]
                if total_hectares
                else [],
                "totalCo2": total_co2,
                "totalHectares": total_hectares,
                "hasSupportedVegetation": total_hectares > 0,
                "topCategory": {"key": "faggete", "label": "Faggete"} if total_hectares else None,
            },
            intersected_municipalities=(label,),
            metadata={"channel": "web_map"},
        )

    @staticmethod
    def _seed_history(client: Client, records: list[StoredAnalysis]):
        session = client.session
        session["interaction_analyses"] = [record.to_dict() for record in records]
        session.save()
        client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    def test_index_renders(self):
        response = Client().get("/progettoGIS/cartaNatura/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"apiUrl": "/progettoGIS/cartaNatura/gis"')
        self.assertContains(
            response,
            '"analysisHistoryUrl": "/progettoGIS/cartaNatura/analysis/history"',
        )
        self.assertContains(
            response,
            '"voiceTranscriptionUrl": "/progettoGIS/cartaNatura/voice/transcribe"',
        )

    def test_gis_rejects_invalid_payload(self):
        response = Client().post(
            "/progettoGIS/cartaNatura/gis",
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    def test_gis_completed_analysis_creates_history_record(
        self,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = GisClipServiceTests._campania_boundaries()
        client = Client()

        analysis_response = self._post_history_analysis(client)
        history_response = client.get("/progettoGIS/cartaNatura/analysis/history")

        self.assertEqual(analysis_response.status_code, 200)
        self.assertEqual(history_response.status_code, 200)
        items = history_response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], analysis_response.json()["analysisId"])
        self.assertEqual(items[0]["selectionKind"], "drawn")
        self.assertTrue(items[0]["hasDrawnGeometry"])
        self.assertEqual(items[0]["summary"]["totalCo2"], analysis_response.json()["summary"]["totalCo2"])

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    def test_analysis_history_detail_rename_and_delete_work(
        self,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = GisClipServiceTests._campania_boundaries()
        client = Client()
        analysis_id = self._post_history_analysis(client).json()["analysisId"]

        detail_response = client.get(f"/progettoGIS/cartaNatura/analysis/history/{analysis_id}")
        rename_response = client.patch(
            f"/progettoGIS/cartaNatura/analysis/history/{analysis_id}",
            data='{"label":"Area pilota"}',
            content_type="application/json",
        )
        delete_response = client.delete(f"/progettoGIS/cartaNatura/analysis/history/{analysis_id}")
        missing_response = client.get(f"/progettoGIS/cartaNatura/analysis/history/{analysis_id}")

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["id"], analysis_id)
        self.assertEqual(detail_response.json()["selectionPayload"]["areas"][0]["kind"], "drawn")
        self.assertEqual(rename_response.status_code, 200)
        self.assertEqual(rename_response.json()["label"], "Area pilota")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["deleted"], True)
        self.assertEqual(missing_response.status_code, 404)

    @override_settings(ANALYSIS_HISTORY_LIMIT=2)
    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    def test_analysis_history_limit_is_respected(
        self,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = GisClipServiceTests._campania_boundaries()
        client = Client()

        first_id = self._post_history_analysis(client).json()["analysisId"]
        second_id = self._post_history_analysis(client).json()["analysisId"]
        third_id = self._post_history_analysis(client).json()["analysisId"]
        history_response = client.get("/progettoGIS/cartaNatura/analysis/history")

        self.assertEqual(history_response.status_code, 200)
        ids = [item["id"] for item in history_response.json()["items"]]
        self.assertEqual(ids, [third_id, second_id])
        self.assertNotIn(first_id, ids)

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    def test_analysis_history_does_not_store_user_text_or_personal_data(
        self,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = GisClipServiceTests._campania_boundaries()
        client = Client()
        client.post(
            "/progettoGIS/cartaNatura/experiment/log",
            data=json.dumps(
                {
                    "eventType": "interaction_completed",
                    "channel": "web_chat",
                    "operation": "conversational_request",
                    "interactionMode": "text",
                    "userText": "testo libero da non salvare",
                    "userTranscript": "transcript da non salvare",
                    "assistantResponse": "risposta da non salvare",
                    "details": {
                        "ip": "127.0.0.1",
                        "userAgent": "Browser",
                    },
                }
            ),
            content_type="application/json",
        )
        analysis_id = self._post_history_analysis(client).json()["analysisId"]

        detail_response = client.get(f"/progettoGIS/cartaNatura/analysis/history/{analysis_id}")
        serialized = json.dumps(detail_response.json())

        self.assertEqual(detail_response.status_code, 200)
        self.assertNotIn("testo libero da non salvare", serialized)
        self.assertNotIn("transcript da non salvare", serialized)
        self.assertNotIn("risposta da non salvare", serialized)
        self.assertNotIn("127.0.0.1", serialized)
        self.assertNotIn("Browser", serialized)

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    def test_analysis_history_clear_all_works(
        self,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = GisClipServiceTests._campania_boundaries()
        client = Client()
        self._post_history_analysis(client)

        clear_response = client.delete("/progettoGIS/cartaNatura/analysis/history")
        list_response = client.get("/progettoGIS/cartaNatura/analysis/history")

        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(clear_response.json()["count"], 0)
        self.assertEqual(list_response.json()["items"], [])

    def test_analysis_history_compare_endpoint_returns_deterministic_comparison(self):
        client = Client()
        self._seed_history(
            client,
            [
                self._saved_history_record("analysis_a", "A", 100, 50),
                self._saved_history_record("analysis_b", "B", 150, 30),
            ],
        )

        response = client.post(
            "/progettoGIS/cartaNatura/analysis/history/compare",
            data='{"ids":["analysis_a","analysis_b"]}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["id"] for item in payload["analyses"]], ["analysis_a", "analysis_b"])
        self.assertEqual(payload["rankings"]["totalCo2"][0]["id"], "analysis_b")
        self.assertEqual(payload["rankings"]["totalHectares"][0]["id"], "analysis_a")
        self.assertEqual(payload["rankings"]["co2PerHectare"][0]["id"], "analysis_b")
        self.assertEqual(payload["pairwise"]["totalCo2"]["absolute"], 50)
        self.assertEqual(payload["economicComparison"][0]["priceEurPerTon"], 138)
        self.assertEqual(payload["economicComparison"][0]["ranking"][0]["id"], "analysis_b")

    def test_analysis_history_compare_endpoint_rejects_less_than_two_ids(self):
        client = Client()
        self._seed_history(client, [self._saved_history_record("analysis_a", "A", 100, 50)])

        response = client.post(
            "/progettoGIS/cartaNatura/analysis/history/compare",
            data='{"ids":["analysis_a"]}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("almeno due analisi", response.json()["error"])

    def test_analysis_history_compare_endpoint_returns_404_for_missing_id(self):
        client = Client()
        self._seed_history(client, [self._saved_history_record("analysis_a", "A", 100, 50)])

        response = client.post(
            "/progettoGIS/cartaNatura/analysis/history/compare",
            data='{"ids":["analysis_a","missing"]}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("missing", response.json()["error"])

    def test_analysis_history_compare_endpoint_deduplicates_ids_then_rejects_if_needed(self):
        client = Client()
        self._seed_history(client, [self._saved_history_record("analysis_a", "A", 100, 50)])

        response = client.post(
            "/progettoGIS/cartaNatura/analysis/history/compare",
            data='{"ids":["analysis_a","analysis_a"]}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("almeno due analisi", response.json()["error"])

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
        with patch.dict("os.environ", {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"}):
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
        with patch.dict("os.environ", {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": ""}):
            response = Client().post(
                "/progettoGIS/cartaNatura/interact",
                data='{"message": "Analizza Avellino"}',
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 503)

    def test_experiment_log_endpoint_records_and_exports_events(self):
        client = Client()
        post_response = client.post(
            "/progettoGIS/cartaNatura/experiment/log",
            data=(
                '{"eventType":"task_completed","channel":"web_map",'
                '"operation":"spatial_analysis","interactionMode":"map",'
                '"durationMs":321,"stepCount":2}'
            ),
            content_type="application/json",
        )
        get_response = client.get("/progettoGIS/cartaNatura/experiment/log")

        self.assertEqual(post_response.status_code, 200)
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["eventCount"], 1)
        self.assertEqual(get_response.json()["summary"]["taskCompletionDurationMs"], [321])

    def test_index_exposes_study_config_only_with_query_flag(self):
        client = Client()

        normal_response = client.get("/progettoGIS/cartaNatura/")
        study_response = client.get("/progettoGIS/cartaNatura/?study=1")

        self.assertContains(normal_response, '"study": {"enabled": false')
        self.assertContains(study_response, '"study": {"enabled": true')
        self.assertContains(study_response, '"sessionUrl": "/progettoGIS/cartaNatura/experiment/study/session"')

    def test_index_exposes_asita_pilot_task_ids(self):
        response = Client().get("/progettoGIS/cartaNatura/?study=1")

        for task_id in (
            "asita_t1_area_analysis",
            "asita_t2_forest_co2",
            "asita_t3_economic_value",
            "asita_t4_scenario_compare",
            "asita_t5_report_pdf",
            "asita_t6_map_verify",
        ):
            self.assertContains(response, f'"id": "{task_id}"')

    def test_study_session_endpoint_persists_following_experiment_events(self):
        with TemporaryDirectory() as temp_dir, override_settings(STUDY_LOG_ROOT=Path(temp_dir)):
            client = Client()
            start_response = client.post(
                "/progettoGIS/cartaNatura/experiment/study/session",
                data=(
                    '{"participantId":"participant_010","condition":"conversational",'
                    '"taskId":"municipalities_report"}'
                ),
                content_type="application/json",
            )
            event_response = client.post(
                "/progettoGIS/cartaNatura/experiment/log",
                data=(
                    '{"eventType":"task_completed","channel":"web_chat",'
                    '"operation":"conversational_request","interactionMode":"text",'
                    '"intent":"analyze_municipalities",'
                    '"userText":"analizza Avellino",'
                    '"assistantResponse":"Ho analizzato Avellino."}'
                ),
                content_type="application/json",
            )
            export_response = client.get("/progettoGIS/cartaNatura/experiment/study/session")
            jsonl_response = client.get(
                "/progettoGIS/cartaNatura/experiment/study/session?format=jsonl"
            )

        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(start_response.json()["session"]["participantId"], "participant_010")
        self.assertEqual(event_response.status_code, 200)
        self.assertEqual(export_response.status_code, 200)
        exported_events = export_response.json()["export"]["events"]
        self.assertEqual(export_response.json()["export"]["condition"], "conversational")
        self.assertEqual(export_response.json()["export"]["eventCount"], 2)
        self.assertEqual(exported_events[1]["userText"], "analizza Avellino")
        self.assertEqual(exported_events[1]["assistantResponse"], "Ho analizzato Avellino.")
        self.assertContains(jsonl_response, '"userText": "analizza Avellino"')

    def test_experiment_endpoint_correlates_task_run_and_restores_active_task(self):
        with TemporaryDirectory() as temp_dir, override_settings(STUDY_LOG_ROOT=Path(temp_dir)):
            client = Client()
            client.post(
                "/progettoGIS/cartaNatura/experiment/study/session",
                data='{"participantId":"participant_011","condition":"webgis"}',
                content_type="application/json",
            )
            started_response = client.post(
                "/progettoGIS/cartaNatura/experiment/log",
                data='{"eventType":"task_started","taskId":"task_area","condition":"webgis"}',
                content_type="application/json",
            )
            task_run_id = started_response.json()["event"]["taskRunId"]
            page_response = client.get("/progettoGIS/cartaNatura/?study=1")
            action_response = client.post(
                "/progettoGIS/cartaNatura/experiment/log",
                data=(
                    '{"eventType":"ui_action","channel":"web_map","interactionMode":"map",'
                    '"operation":"eseguiClipBut","details":{"controlId":"eseguiClipBut"}}'
                ),
                content_type="application/json",
            )
            completed_response = client.post(
                "/progettoGIS/cartaNatura/experiment/log",
                data=json.dumps(
                    {
                        "eventType": "task_completed",
                        "taskId": "task_area",
                        "taskRunId": task_run_id,
                        "durationMs": 999999,
                    }
                ),
                content_type="application/json",
            )
            exported = client.get(
                "/progettoGIS/cartaNatura/experiment/study/session"
            ).json()["export"]

        self.assertContains(page_response, f'"taskRunId": "{task_run_id}"')
        self.assertEqual(action_response.json()["event"]["taskRunId"], task_run_id)
        self.assertEqual(action_response.json()["event"]["condition"], "webgis")
        self.assertNotEqual(completed_response.json()["event"]["durationMs"], 999999)
        self.assertEqual(exported["summary"]["tasks"][0]["status"], "completed")

    def test_webgis_task_blocks_chat_and_preserves_previous_operational_state(self):
        with TemporaryDirectory() as temp_dir, override_settings(STUDY_LOG_ROOT=Path(temp_dir)):
            client = Client()
            client.post(
                "/progettoGIS/cartaNatura/experiment/study/session",
                data='{"participantId":"participant_webgis","condition":"webgis"}',
                content_type="application/json",
            )
            session = client.session
            session["interaction_context"] = {"last_intent": "generate_report"}
            session["interaction_analyses"] = [{"analysis_id": "analysis_previous"}]
            session.save()
            client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
            started = client.post(
                "/progettoGIS/cartaNatura/experiment/log",
                data='{"eventType":"task_started","taskId":"area_co2","condition":"webgis"}',
                content_type="application/json",
            ).json()["event"]

            with patch.dict("os.environ", {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"}):
                blocked = client.post(
                    "/progettoGIS/cartaNatura/interact",
                    data='{"message":"analizza Avellino"}',
                    content_type="application/json",
                )
            exported = client.get(
                "/progettoGIS/cartaNatura/experiment/study/session"
            ).json()["export"]

        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(client.session["interaction_context"]["last_intent"], "generate_report")
        self.assertEqual(
            client.session["interaction_analyses"][0]["analysis_id"],
            "analysis_previous",
        )
        violation = exported["events"][-1]
        self.assertEqual(violation["eventType"], "protocol_violation")
        self.assertEqual(violation["condition"], "webgis")
        self.assertEqual(violation["taskRunId"], started["taskRunId"])
        self.assertEqual(exported["summary"]["protocolViolationCount"], 1)

    def test_conversational_task_blocks_traditional_gis_endpoint_only(self):
        with TemporaryDirectory() as temp_dir, override_settings(STUDY_LOG_ROOT=Path(temp_dir)):
            client = Client()
            client.post(
                "/progettoGIS/cartaNatura/experiment/study/session",
                data='{"participantId":"participant_chat","condition":"conversational"}',
                content_type="application/json",
            )
            started = client.post(
                "/progettoGIS/cartaNatura/experiment/log",
                data=(
                    '{"eventType":"task_started","taskId":"area_co2",'
                    '"condition":"conversational"}'
                ),
                content_type="application/json",
            ).json()["event"]
            blocked = client.post(
                "/progettoGIS/cartaNatura/gis",
                data='{"areas":[]}',
                content_type="application/json",
            )
            with patch.dict("os.environ", {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": ""}):
                allowed_channel = client.post(
                    "/progettoGIS/cartaNatura/interact",
                    data='{"message":"analizza Avellino"}',
                    content_type="application/json",
                )
            exported = client.get(
                "/progettoGIS/cartaNatura/experiment/study/session"
            ).json()["export"]

        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(allowed_channel.status_code, 503)
        violation = next(
            event
            for event in exported["events"]
            if event.get("eventType") == "protocol_violation"
        )
        self.assertEqual(violation["condition"], "conversational")
        self.assertEqual(violation["taskRunId"], started["taskRunId"])
        self.assertEqual(violation["details"]["attemptedAction"], "spatial_analysis_ui")

    @patch("cartaNatura.views.transcribe_uploaded_audio")
    def test_voice_transcribe_returns_transcript(self, transcribe_uploaded_audio):
        transcribe_uploaded_audio.return_value = "analizza Avellino"

        with patch.dict("os.environ", {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"}):
            response = Client().post(
                "/progettoGIS/cartaNatura/voice/transcribe",
                data={
                    "audio": SimpleUploadedFile(
                        "voice.webm",
                        b"fake-audio",
                        content_type="audio/webm",
                    ),
                    "durationMs": "1200",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transcript"], "analizza Avellino")
        transcribe_uploaded_audio.assert_called_once()

    @patch("cartaNatura.interaction.orchestrator.build_optional_llm_provider")
    def test_interact_stream_returns_sse_events(self, build_optional_llm_provider):
        build_optional_llm_provider.return_value = FakeStreamingProvider(
            [
                {
                    "events": [
                        FakeStreamEvent(
                            "response.created",
                            response=FakeStreamResponseRef("resp_stream_1"),
                        ),
                        FakeStreamEvent(
                            "response.output_text.delta",
                            delta=(
                                '{"intent":"unknown","assistant_text":"Streaming ok.",'
                                '"needs_clarification":false,"clarification_question":"",'
                                '"ui_actions":[],"citations_internal":[],"follow_up_suggestions":[]}'
                            ),
                        ),
                    ],
                    "final_payload": {
                        "id": "resp_stream_1",
                        "output_text": (
                            '{"intent":"unknown","assistant_text":"Streaming ok.",'
                            '"needs_clarification":false,"clarification_question":"",'
                            '"ui_actions":[],"citations_internal":[],"follow_up_suggestions":[]}'
                        ),
                        "output": [],
                    },
                }
            ]
        )

        with patch.dict("os.environ", {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"}):
            response = Client().post(
                "/progettoGIS/cartaNatura/interact/stream",
                data='{"message": "ciao"}',
                content_type="application/json",
            )

        body = b"".join(response.streaming_content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertIn(b"event: message_delta", body)
        self.assertIn(b"event: done", body)
        self.assertIn(b"Streaming ok.", body)

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    @patch("cartaNatura.interaction.orchestrator.build_optional_llm_provider")
    @override_settings(SESSION_ENGINE="django.contrib.sessions.backends.cache")
    def test_interact_stream_persists_analysis_before_done_event(
        self,
        build_optional_llm_provider,
        load_municipality_shapes,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        build_optional_llm_provider.return_value = FakeStreamingProvider([])
        load_municipality_shapes.return_value = GisClipServiceTests._municipality_shapes_catalog()
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = geopandas.GeoDataFrame(
            {"COMUNE": ["Avellino", "Benevento"]},
            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
            crs="EPSG:4326",
        )
        client = Client()

        with patch.dict("os.environ", {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"}):
            response = client.post(
                "/progettoGIS/cartaNatura/interact/stream",
                data='{"message": "analizza Avellino"}',
                content_type="application/json",
            )
            body = b"".join(response.streaming_content)

        self.assertIn(b"event: done", body)
        self.assertIn(
            "interaction_analyses",
            client.session,
            msg=body.decode("utf-8", errors="replace"),
        )
        self.assertEqual(
            client.session["interaction_analyses"][-1]["requested_municipalities"],
            ["Avellino"],
        )
        self.assertEqual(
            client.session["interaction_context"]["last_analysis"]["requestedMunicipalities"],
            ["Avellino"],
        )


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
                "displayedAnalysisId": "analysis_visible",
            }
        )

        self.assertIsNone(context.current_selection_payload)
        self.assertEqual(context.displayed_analysis_id, "analysis_visible")


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

    def test_resolver_prioritizes_explicit_analysis_over_requested_explanation(self):
        resolution = RuleBasedIntentResolver().resolve(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="compound-analysis",
                input=InteractionInput(
                    text="Analizza Bagnoli Irpino e spiegami in breve il risultato"
                ),
            ),
            SessionContext(last_analysis={"analysisId": "analysis_previous"}),
        )

        self.assertEqual(
            resolution.command.intent,
            InteractionIntent.ANALYZE_MUNICIPALITIES,
        )
        self.assertEqual(
            resolution.command.payload["municipality_names"],
            ["Bagnoli Irpino"],
        )

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
            create_stored_analysis(
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

    def test_streaming_reset_clears_context_without_calling_provider(self):
        session_store = InMemorySessionStore()
        analysis_store = InMemoryAnalysisStore()
        session_store.save(
            "stream-reset",
            SessionContext(last_analysis={"analysisId": "analysis_old"}),
        )
        analysis_store.save(
            create_stored_analysis(
                source="selection",
                summary={
                    "items": [],
                    "totalCo2": 1,
                    "totalHectares": 1,
                    "hasSupportedVegetation": True,
                    "topCategory": None,
                },
            )
        )
        provider = FakeResponsesProvider([])
        orchestrator = build_default_orchestrator(
            session_store=session_store,
            llm_provider=provider,
            analysis_store=analysis_store,
        )

        events = list(
            orchestrator.handle_stream(
                InteractionRequest(
                    channel=InteractionChannel.WEB_CHAT,
                    session_id="stream-reset",
                    input=InteractionInput(text="azzera tutto"),
                )
            )
        )

        self.assertEqual([event["type"] for event in events], ["done"])
        self.assertEqual(events[0]["response"]["uiHints"]["mode"], "reset")
        self.assertEqual(provider.calls, [])
        self.assertEqual(session_store.load("stream-reset"), SessionContext())
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
        self.assertIn("analyses", response.analysis_result)
        self.assertIn("pairwise", response.analysis_result)
        self.assertEqual(
            [item["municipalities"] for item in response.analysis_result["analyses"]],
            [["Avellino"], ["Benevento"]],
        )
        self.assertIn("totalCo2", response.analysis_result["rankings"])

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_orchestrator_uses_rule_based_fast_path_for_simple_text_requests(
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
        provider = FakeHybridProvider("Sintesi LLM mockata.")
        orchestrator = build_default_orchestrator(
            session_store=InMemorySessionStore(),
            llm_provider=provider,
            analysis_store=InMemoryAnalysisStore(),
        )

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="session-fast-path",
                input=InteractionInput(text="analizza Avellino e Benevento"),
            )
        )

        self.assertEqual(response.commands[0].intent, InteractionIntent.ANALYZE_MUNICIPALITIES)
        self.assertIn("10 ha forestali e 95,4 t CO2/anno", response.messages[0].text)
        self.assertEqual(provider.response_calls, [])
        self.assertEqual(provider.complete_calls, [])

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
        with patch.dict("os.environ", {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": ""}):
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


class OpenAiAssistantRuntimeTests(SimpleTestCase):
    def test_runtime_falls_back_to_plain_text_when_final_json_is_invalid(self):
        provider = FakeResponsesProvider(
            [
                {
                    "id": "resp_plain_text",
                    "output_text": "Ho bisogno di un comune piu specifico.",
                    "output": [],
                }
            ]
        )
        orchestrator = build_default_orchestrator(
            session_store=InMemorySessionStore(),
            llm_provider=provider,
            analysis_store=InMemoryAnalysisStore(),
        )

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="plain-text-final-session",
                input=InteractionInput(text="analizza san"),
            )
        )

        self.assertEqual(response.messages[0].text, "Ho bisogno di un comune piu specifico.")
        self.assertTrue(response.ui_hints["needsClarification"])

    def test_runtime_extracts_assistant_text_from_malformed_final_json(self):
        provider = FakeResponsesProvider(
            [
                {
                    "id": "resp_malformed_text",
                    "output_text": (
                        '{"intent":"analyze_municipalities","assistant_text":"Specifica '
                        'quale comune San vuoi analizzare'
                    ),
                    "output": [],
                }
            ]
        )
        orchestrator = build_default_orchestrator(
            session_store=InMemorySessionStore(),
            llm_provider=provider,
            analysis_store=InMemoryAnalysisStore(),
        )

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="malformed-final-session",
                input=InteractionInput(text="analizza san"),
            )
        )

        self.assertEqual(
            response.messages[0].text,
            "Specifica quale comune San vuoi analizzare",
        )
        self.assertTrue(response.ui_hints["needsClarification"])

    def test_runtime_uses_provider_identity_and_history_with_ollama(self):
        provider = FakeOllamaStyleProvider(
            [
                {
                    "id": "ollama_turn_1",
                    "output_text": (
                        '{"intent":"guide_workflow","assistant_text":"Prima risposta.",'
                        '"needs_clarification":false,"clarification_question":"","ui_actions":[],'
                        '"citations_internal":[],"follow_up_suggestions":[]}'
                    ),
                    "output": [],
                },
                {
                    "id": "ollama_turn_2",
                    "output_text": (
                        '{"intent":"guide_workflow","assistant_text":"Seconda risposta.",'
                        '"needs_clarification":false,"clarification_question":"","ui_actions":[],'
                        '"citations_internal":[],"follow_up_suggestions":[]}'
                    ),
                    "output": [],
                },
            ]
        )
        session_store = InMemorySessionStore()
        orchestrator = build_default_orchestrator(
            session_store=session_store,
            llm_provider=provider,
            analysis_store=InMemoryAnalysisStore(),
        )

        first = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="ollama-history-session",
                input=InteractionInput(text="ciao"),
            )
        )
        second = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="ollama-history-session",
                input=InteractionInput(text="continua"),
            )
        )

        self.assertEqual(first.ui_hints["providerMode"], "ollama")
        self.assertEqual(first.ui_hints["providerModel"], "llama3.1")
        self.assertEqual(first.ui_hints["runtime"], "ollama_chat")
        self.assertEqual(second.messages[0].text, "Seconda risposta.")
        self.assertEqual(
            provider.calls[1]["conversation_messages"],
            [
                {"role": "user", "content": "ciao"},
                {"role": "assistant", "content": "Prima risposta."},
            ],
        )

    def test_runtime_uses_authoritative_economic_tools_and_report_text(self):
        store = InMemoryAnalysisStore()
        saved = store.save(
            create_stored_analysis(
                source="municipalities",
                summary={
                    "items": [],
                    "totalCo2": 10,
                    "totalHectares": 2,
                    "hasSupportedVegetation": True,
                    "topCategory": None,
                },
                requested_municipalities=["Avellino"],
                intersected_municipalities=["Avellino"],
            )
        )
        provider = FakeResponsesProvider(
            [
                {
                    "id": "resp_economic_tool",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_economic",
                            "name": "calculate_economic_value",
                            "arguments": '{"scenario_key":"social_cost"}',
                        }
                    ],
                },
                {
                    "id": "resp_report_tool",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_report",
                            "name": "prepare_report",
                            "arguments": "{}",
                        }
                    ],
                },
            ]
        )
        orchestrator = build_default_orchestrator(
            session_store=InMemorySessionStore(),
            llm_provider=provider,
            analysis_store=store,
        )

        economic_response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="economic-runtime-session",
                input=InteractionInput(text="calcola con il costo sociale"),
            )
        )
        report_response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="economic-runtime-session",
                input=InteractionInput(text="genera il report"),
            )
        )

        self.assertEqual(economic_response.economic_result["analysisId"], saved.analysis_id)
        self.assertEqual(economic_response.economic_result["totalValueEur"], 1380)
        self.assertIn("1.380 €", economic_response.messages[0].text)
        self.assertNotIn(saved.analysis_id, economic_response.messages[0].text)
        self.assertNotIn("costi e ricavi", economic_response.messages[0].text)
        self.assertEqual(
            economic_response.ui_hints["followUpSuggestions"],
            ["Confronta gli scenari economici", "Apri il report"],
        )
        self.assertIn("open_report_panel", economic_response.ui_hints["uiActions"])
        self.assertEqual(
            store.get(saved.analysis_id).economic_valuation["totalValueEur"],
            1380,
        )
        self.assertEqual(report_response.report_context["analysisId"], saved.analysis_id)
        self.assertIn("Apro il report dell'ultima analisi", report_response.messages[0].text)
        self.assertIn("Esporta PDF", report_response.messages[0].text)
        self.assertNotIn("gia generato", report_response.messages[0].text)
        self.assertIn("open_report_panel", report_response.ui_hints["uiActions"])

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_runtime_streams_events_and_persists_follow_up_context(
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
        provider = FakeStreamingProvider(
            [
                {
                    "events": [
                        FakeStreamEvent(
                            "response.created",
                            response=FakeStreamResponseRef("resp_stream_tool_1"),
                        ),
                        FakeStreamEvent(
                            "response.output_item.added",
                            item=FakeStreamItem(
                                "function_call",
                                name="analyze_municipalities",
                            ),
                        ),
                    ],
                    "final_payload": {
                        "id": "resp_stream_tool_1",
                        "output": [
                            {
                                "type": "function_call",
                                "call_id": "call_stream_1",
                                "name": "analyze_municipalities",
                                "arguments": '{"municipality_names":["Avellino","Benevento"]}',
                            }
                        ],
                    },
                },
                {
                    "events": [
                        FakeStreamEvent(
                            "response.created",
                            response=FakeStreamResponseRef("resp_stream_final_1"),
                        ),
                        FakeStreamEvent(
                            "response.output_text.delta",
                            delta=(
                                '{"intent":"analyze_municipalities","assistant_text":"Avellino e '
                                'Benevento dominano.","needs_clarification":false,'
                                '"clarification_question":"","ui_actions":["show_last_analysis"],'
                                '"citations_internal":["analysis_latest"],'
                                '"follow_up_suggestions":["Perche dominano?"]}'
                            ),
                        ),
                    ],
                    "final_payload": {
                        "id": "resp_stream_final_1",
                        "output_text": (
                            '{"intent":"analyze_municipalities","assistant_text":"Avellino e '
                            'Benevento dominano.","needs_clarification":false,'
                            '"clarification_question":"","ui_actions":["show_last_analysis"],'
                            '"citations_internal":["analysis_latest"],'
                            '"follow_up_suggestions":["Perche dominano?"]}'
                        ),
                        "output": [],
                    },
                },
            ]
        )
        session_store = InMemorySessionStore()
        analysis_store = InMemoryAnalysisStore()
        orchestrator = build_default_orchestrator(
            session_store=session_store,
            llm_provider=provider,
            analysis_store=analysis_store,
        )

        events = list(
            orchestrator.handle_stream(
                InteractionRequest(
                    channel=InteractionChannel.WEB_CHAT,
                    session_id="runtime-stream-session-1",
                    input=InteractionInput(text="analizza Avellino e Benevento"),
                )
            )
        )

        event_types = [event["type"] for event in events]
        self.assertIn("tool_running", event_types)
        self.assertIn("tool_result", event_types)
        self.assertNotIn("message_delta", event_types)
        self.assertEqual(event_types[-1], "done")
        self.assertIn(
            "10 ha forestali e 95,4 t CO2/anno",
            events[-1]["response"]["messages"][0]["text"],
        )
        self.assertEqual(
            events[-1]["response"]["analysisResult"]["requestedMunicipalities"],
            ["Avellino", "Benevento"],
        )
        self.assertEqual(
            session_store.load("runtime-stream-session-1").metadata["conversation_messages"][0],
            {"role": "user", "content": "analizza Avellino e Benevento"},
        )
        self.assertEqual(len(provider.stream_calls), 0)
        self.assertIsNotNone(analysis_store.get_last())

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_runtime_runs_responses_tool_loop_for_municipality_analysis(
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
        provider = FakeResponsesProvider(
            [
                {
                    "id": "resp_tool_1",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_1",
                            "name": "search_municipalities",
                            "arguments": '{"query":"Avell","limit":5}',
                        }
                    ],
                },
                {
                    "id": "resp_tool_2",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_2",
                            "name": "analyze_municipalities",
                            "arguments": '{"municipality_names":["Avellino"]}',
                        }
                    ],
                },
                {
                    "id": "resp_final_1",
                    "output_text": (
                        '{"intent":"analyze_municipalities","assistant_text":"Analisi pronta.",'
                        '"needs_clarification":false,"clarification_question":"","ui_actions":["show_last_analysis","delete_everything"],'
                        '"citations_internal":["analysis_latest"],"follow_up_suggestions":["Confronta ultime due analisi"]}'
                    ),
                    "output": [],
                },
            ]
        )
        session_store = InMemorySessionStore()
        analysis_store = InMemoryAnalysisStore()
        orchestrator = build_default_orchestrator(
            session_store=session_store,
            llm_provider=provider,
            analysis_store=analysis_store,
        )

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="runtime-session-1",
                input=InteractionInput(text="analizza Avell"),
            )
        )

        self.assertEqual(response.commands[0].intent, InteractionIntent.ANALYZE_MUNICIPALITIES)
        self.assertIn("95,4 t CO2/anno", response.messages[0].text)
        self.assertEqual(
            response.analysis_result["requestedMunicipalities"],
            ["Avellino"],
        )
        self.assertEqual(response.ui_hints["runtime"], "responses_api")
        self.assertNotIn(
            "provider_previous_response_id",
            session_store.load("runtime-session-1").metadata,
        )
        self.assertEqual(provider.calls[1]["previous_response_id"], "resp_tool_1")
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(
            response.ui_hints["uiActions"],
            ["show_last_analysis", "focus_map_results"],
        )
        grounded_prompt = provider.calls[0]["input"][0]["content"][0]["text"]
        self.assertIn('"vegetationCategories"', grounded_prompt)
        self.assertIn('"Castagneti"', grounded_prompt)
        self.assertNotIn('"codes"', grounded_prompt)
        self.assertIn('"availableTools"', grounded_prompt)

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_runtime_carries_grounded_conversation_context_on_follow_up(
        self,
        load_municipality_shapes,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_municipality_shapes.return_value = GisClipServiceTests._municipality_shapes_catalog()
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = geopandas.GeoDataFrame(
            {"COMUNE": ["Avellino"]},
            geometry=[box(0, 0, 1, 1)],
            crs="EPSG:4326",
        )
        provider = FakeResponsesProvider(
            [
                {
                    "id": "resp_tool_1",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_1",
                            "name": "search_municipalities",
                            "arguments": '{"query":"Avell","limit":5}',
                        }
                    ],
                },
                {
                    "id": "resp_tool_2",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_2",
                            "name": "analyze_municipalities",
                            "arguments": '{"municipality_names":["Avellino"]}',
                        }
                    ],
                },
                {
                    "id": "resp_tool_3",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_3",
                            "name": "get_last_analysis",
                            "arguments": "{}",
                        }
                    ],
                },
            ]
        )
        session_store = InMemorySessionStore()
        analysis_store = InMemoryAnalysisStore()
        orchestrator = build_default_orchestrator(
            session_store=session_store,
            llm_provider=provider,
            analysis_store=analysis_store,
        )

        orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="runtime-session-2",
                input=InteractionInput(text="analizza Avell"),
            )
        )
        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="runtime-session-2",
                input=InteractionInput(text="perche dominano?"),
            )
        )

        self.assertEqual(response.commands[0].intent, InteractionIntent.EXPLAIN_LAST_ANALYSIS)
        self.assertIn("Nell'ultima analisi", response.messages[0].text)
        self.assertEqual(provider.calls[2]["previous_response_id"], None)
        follow_up_prompt = provider.calls[2]["input"][0]["content"][0]["text"]
        self.assertIn('"recentMessages"', follow_up_prompt)
        self.assertIn("analizza Avell", follow_up_prompt)

    def test_runtime_exposes_recent_analysis_history_tool(self):
        provider = FakeResponsesProvider(
            [
                {
                    "id": "resp_tool_history",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_history",
                            "name": "list_recent_analyses",
                            "arguments": '{"limit":10}',
                        }
                    ],
                },
            ]
        )
        analysis_store = InMemoryAnalysisStore()
        saved = analysis_store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 7, "totalHectares": 3, "hasSupportedVegetation": True, "topCategory": None},
                requested_municipalities=["Avellino"],
                intersected_municipalities=["Avellino"],
            )
        )
        orchestrator = build_default_orchestrator(
            session_store=InMemorySessionStore(),
            llm_provider=provider,
            analysis_store=analysis_store,
        )

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="runtime-history-session",
                input=InteractionInput(text="mostrami le analisi recenti"),
            )
        )

        self.assertEqual(response.commands[0].intent, InteractionIntent.EXPLAIN_LAST_ANALYSIS)
        self.assertIn("Analisi Avellino", response.messages[0].text)
        self.assertNotIn(saved.analysis_id, response.messages[0].text)
        self.assertEqual(len(provider.calls), 1)

    def test_runtime_exposes_saved_analysis_compare_tool(self):
        provider = FakeResponsesProvider(
            [
                {
                    "id": "resp_tool_compare",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_compare",
                            "name": "compare_saved_analyses",
                            "arguments": '{"selectors":["Castellabate","Roccadaspide"]}',
                        }
                    ],
                },
            ]
        )
        analysis_store = InMemoryAnalysisStore()
        analysis_store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 7, "totalHectares": 3.5, "hasSupportedVegetation": True, "topCategory": None},
                requested_municipalities=["Castellabate"],
                intersected_municipalities=["Castellabate"],
            )
        )
        analysis_store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 11, "totalHectares": 2, "hasSupportedVegetation": True, "topCategory": None},
                requested_municipalities=["Roccadaspide"],
                intersected_municipalities=["Roccadaspide"],
            )
        )
        orchestrator = build_default_orchestrator(
            session_store=InMemorySessionStore(),
            llm_provider=provider,
            analysis_store=analysis_store,
        )

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="runtime-compare-session",
                input=InteractionInput(text="usa lo storico salvato"),
            )
        )

        self.assertEqual(response.commands[0].intent, InteractionIntent.COMPARE_ANALYSES)
        self.assertEqual(len(response.analysis_result["analyses"]), 2)
        self.assertIn("Analisi Roccadaspide", response.messages[0].text)
        self.assertNotIn("JSON", response.messages[0].text)
        self.assertEqual(len(provider.calls), 1)

    def test_runtime_filters_visible_analysis_without_recalculating_it(self):
        analysis_store = InMemoryAnalysisStore()
        saved = analysis_store.save(
            create_stored_analysis(
                source="municipalities",
                summary={
                    "items": [
                        {
                            "key": "castagneti",
                            "label": "Castagneti",
                            "hectares": 12,
                            "co2PerHectare": 6.2,
                        },
                        {
                            "key": "faggete",
                            "label": "Faggete",
                            "hectares": 20,
                            "co2PerHectare": 9.54,
                        },
                    ],
                    "totalCo2": 265.2,
                    "totalHectares": 32,
                    "hasSupportedVegetation": True,
                    "topCategory": {"key": "faggete", "label": "Faggete"},
                },
                requested_municipalities=["Montella"],
                intersected_municipalities=["Montella"],
            )
        )
        provider = FakeResponsesProvider(
            [
                {
                    "id": "resp_filter_tool",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_filter",
                            "name": "filter_last_analysis_categories",
                            "arguments": '{"category_names":["castagneti"],"show_all":false}',
                        }
                    ],
                }
            ]
        )
        orchestrator = build_default_orchestrator(
            session_store=InMemorySessionStore(),
            llm_provider=provider,
            analysis_store=analysis_store,
        )

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="runtime-filter-session",
                input=InteractionInput(text="mostrami solo i castagneti"),
                context=InteractionContext(displayed_analysis_id=saved.analysis_id),
            )
        )

        self.assertEqual(response.analysis_result, None)
        self.assertEqual(response.map_filter["categories"][0]["key"], "castagneti")
        self.assertIn("mostro solo: Castagneti", response.messages[0].text)
        self.assertNotIn(saved.analysis_id, response.messages[0].text)
        self.assertEqual(response.ui_hints["uiActions"], ["focus_map_results"])

    def test_streaming_runtime_preplans_clear_comparison_without_provider_guesswork(self):
        analysis_store = InMemoryAnalysisStore()
        analysis_store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 10, "totalHectares": 5, "hasSupportedVegetation": True, "topCategory": None},
                requested_municipalities=["Montella"],
                intersected_municipalities=["Montella"],
            )
        )
        analysis_store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 8, "totalHectares": 4, "hasSupportedVegetation": True, "topCategory": None},
                requested_municipalities=["Bagnoli Irpino"],
                intersected_municipalities=["Bagnoli Irpino"],
            )
        )
        provider = FakeStreamingProvider([])
        orchestrator = build_default_orchestrator(
            session_store=InMemorySessionStore(),
            llm_provider=provider,
            analysis_store=analysis_store,
        )

        events = list(
            orchestrator.handle_stream(
                InteractionRequest(
                    channel=InteractionChannel.WEB_CHAT,
                    session_id="empty-compare-session",
                    input=InteractionInput(text="confrontalo con il precedente"),
                )
            )
        )
        response_payload = events[-1]["response"]

        self.assertEqual(len(response_payload["analysisResult"]["analyses"]), 2)
        self.assertIn("Analisi Montella", response_payload["messages"][0]["text"])
        self.assertNotIn("risposta strutturata vuota", response_payload["messages"][0]["text"])
        self.assertEqual(len(provider.stream_calls), 0)

    def test_runtime_does_not_treat_previous_analysis_selection_as_current(self):
        provider = FakeResponsesProvider(
            [
                {
                    "id": "resp_stale_selection",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_stale_selection",
                            "name": "analyze_current_selection",
                            "arguments": "{}",
                        }
                    ],
                }
            ]
        )
        session_store = InMemorySessionStore()
        session_store.save(
            "stale-selection-session",
            SessionContext(
                selection_payload={"areas": [{"kind": "drawn"}]},
                last_analysis={"analysisId": "analysis_old"},
            ),
        )
        orchestrator = build_default_orchestrator(
            session_store=session_store,
            llm_provider=provider,
            analysis_store=InMemoryAnalysisStore(),
        )

        response = orchestrator.handle(
            InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="stale-selection-session",
                input=InteractionInput(text="analizza la selezione corrente"),
            )
        )

        self.assertTrue(response.ui_hints["needsClarification"])
        self.assertIn("Non c'è una selezione corrente", response.messages[0].text)
        self.assertIsNone(response.analysis_result)


class AnalysisStoreAndToolsTests(SimpleTestCase):
    def test_economic_domain_uses_configured_scenarios(self):
        result = calculate_economic_value(total_co2=10, scenario_key="social_cost")
        comparison = compare_economic_scenarios(total_co2=10)

        self.assertEqual(result["priceEurPerTon"], 138)
        self.assertEqual(result["totalValueEur"], 1380)
        self.assertEqual(len(comparison), len(PRICE_OPTIONS))
        self.assertEqual(
            [item["priceEurPerTon"] for item in comparison],
            [float(option["value"]) for option in PRICE_OPTIONS],
        )

    def test_economic_tools_calculate_compare_and_persist_analysis_link(self):
        store = InMemoryAnalysisStore()
        saved = store.save(
            create_stored_analysis(
                source="municipalities",
                summary={
                    "items": [],
                    "totalCo2": 12.5,
                    "totalHectares": 3,
                    "hasSupportedVegetation": True,
                    "topCategory": None,
                },
                requested_municipalities=["Avellino"],
                intersected_municipalities=["Avellino"],
            )
        )
        registry = build_default_tool_registry(store)

        valuation = registry.execute(
            ToolName.CALCULATE_ECONOMIC_VALUE,
            scenario_key="regulated_market",
        )
        comparison = registry.execute(ToolName.COMPARE_ECONOMIC_SCENARIOS)
        report = registry.execute(ToolName.PREPARE_REPORT)

        self.assertEqual(valuation["analysisId"], saved.analysis_id)
        self.assertEqual(valuation["priceEurPerTon"], 82)
        self.assertEqual(valuation["totalValueEur"], 1025)
        self.assertEqual(comparison["analysisId"], saved.analysis_id)
        self.assertEqual(len(comparison["scenarios"]), 4)
        self.assertEqual(report["economicResult"], valuation)
        self.assertEqual(
            store.get(saved.analysis_id).economic_valuation,
            valuation,
        )

    def test_economic_tool_rejects_unknown_scenario(self):
        store = InMemoryAnalysisStore()
        store.save(
            create_stored_analysis(
                source="selection",
                summary={
                    "items": [],
                    "totalCo2": 1,
                    "totalHectares": 1,
                    "hasSupportedVegetation": True,
                    "topCategory": None,
                },
            )
        )
        registry = build_default_tool_registry(store)

        with self.assertRaisesMessage(ValueError, "Scenario economico non supportato"):
            registry.execute(
                ToolName.CALCULATE_ECONOMIC_VALUE,
                scenario_key="invented",
            )

    def test_inmemory_analysis_store_returns_last_saved_item(self):
        store = InMemoryAnalysisStore()
        first = store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 1, "totalHectares": 2, "hasSupportedVegetation": True, "topCategory": None},
            )
        )
        second = store.save(
            create_stored_analysis(
                source="selection",
                summary={"items": [], "totalCo2": 3, "totalHectares": 4, "hasSupportedVegetation": True, "topCategory": None},
            )
        )

        self.assertEqual(store.get(first.analysis_id), first)
        self.assertEqual(store.get_last(), second)

    def test_tool_registry_returns_last_analysis(self):
        store = InMemoryAnalysisStore()
        saved = store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 3, "totalHectares": 4, "hasSupportedVegetation": True, "topCategory": None},
                requested_municipalities=["Avellino"],
                intersected_municipalities=["Avellino"],
            )
        )
        registry = build_default_tool_registry(store)

        payload = registry.execute(ToolName.GET_LAST_ANALYSIS)

        self.assertEqual(payload["analysisId"], saved.analysis_id)
        self.assertEqual(payload["id"], saved.analysis_id)
        self.assertEqual(payload["selectionKind"], "unknown")
        self.assertEqual(payload["requestedMunicipalities"], ["Avellino"])
        self.assertEqual(payload["municipalities"], ["Avellino"])

    def test_map_filter_reports_missing_category_with_human_label(self):
        store = InMemoryAnalysisStore()
        saved = store.save(
            create_stored_analysis(
                source="municipalities",
                summary={
                    "items": [
                        {
                            "key": "castagneti",
                            "label": "Castagneti",
                            "hectares": 12,
                            "co2PerHectare": 6.2,
                        }
                    ],
                    "totalCo2": 74.4,
                    "totalHectares": 12,
                    "hasSupportedVegetation": True,
                    "topCategory": {"key": "castagneti", "label": "Castagneti"},
                },
                requested_municipalities=["Montella"],
                intersected_municipalities=["Montella"],
            )
        )

        with self.assertRaisesMessage(
            ValueError,
            "La categoria 'Boschi di abete bianco' non è presente nell'analisi corrente",
        ):
            filter_analysis_categories(
                analysis_store=store,
                displayed_analysis_id=saved.analysis_id,
                category_names=["abete_bianco"],
            )

    def test_map_filter_uses_visible_analysis_even_when_it_is_not_latest(self):
        store = InMemoryAnalysisStore()
        visible = store.save(
            create_stored_analysis(
                source="municipalities",
                summary={
                    "items": [{"key": "castagneti", "label": "Castagneti", "hectares": 4, "co2PerHectare": 6.2}],
                    "totalCo2": 24.8,
                    "totalHectares": 4,
                    "hasSupportedVegetation": True,
                    "topCategory": {"key": "castagneti", "label": "Castagneti"},
                },
                requested_municipalities=["Bagnoli Irpino"],
            )
        )
        store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 0, "totalHectares": 0, "hasSupportedVegetation": False, "topCategory": None},
                requested_municipalities=["Montella"],
            )
        )

        result = filter_analysis_categories(
            analysis_store=store,
            displayed_analysis_id=visible.analysis_id,
            category_names=["castagneti"],
        )

        self.assertEqual(result["analysisId"], visible.analysis_id)
        self.assertEqual(result["categories"], [{"key": "castagneti", "label": "Castagneti"}])

    def test_get_recent_analyses_returns_newest_first(self):
        store = InMemoryAnalysisStore()
        first = store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 1, "totalHectares": 2, "hasSupportedVegetation": True, "topCategory": None},
            )
        )
        second = store.save(
            create_stored_analysis(
                source="selection",
                summary={"items": [], "totalCo2": 3, "totalHectares": 4, "hasSupportedVegetation": True, "topCategory": None},
            )
        )

        payload = get_recent_analyses(analysis_store=store, limit=2)

        self.assertEqual(payload["items"][0]["analysisId"], second.analysis_id)
        self.assertEqual(payload["items"][1]["analysisId"], first.analysis_id)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["items"][0]["totalCo2"], 3)

    def test_compare_analyses_returns_deterministic_comparison_payload(self):
        store = InMemoryAnalysisStore()
        left = store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 10, "totalHectares": 20, "hasSupportedVegetation": True, "topCategory": None},
            )
        )
        right = store.save(
            create_stored_analysis(
                source="selection",
                summary={"items": [], "totalCo2": 15, "totalHectares": 24, "hasSupportedVegetation": True, "topCategory": None},
            )
        )

        comparison = compare_analyses(
            analysis_store=store,
            left_analysis_id=left.analysis_id,
            right_analysis_id=right.analysis_id,
        )

        self.assertEqual([item["id"] for item in comparison["analyses"]], [left.analysis_id, right.analysis_id])
        self.assertEqual(comparison["pairwise"]["totalCo2"]["absolute"], 5)
        self.assertEqual(comparison["pairwise"]["totalHectares"]["absolute"], 4)
        self.assertTrue(comparison["economicComparison"])

    def test_compare_recent_analyses_uses_latest_two_items(self):
        store = InMemoryAnalysisStore()
        older = store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 10, "totalHectares": 20, "hasSupportedVegetation": True, "topCategory": None},
            )
        )
        latest = store.save(
            create_stored_analysis(
                source="selection",
                summary={"items": [], "totalCo2": 15, "totalHectares": 24, "hasSupportedVegetation": True, "topCategory": None},
            )
        )
        registry = build_default_tool_registry(store)

        comparison = registry.execute(ToolName.COMPARE_RECENT_ANALYSES)

        self.assertEqual([item["id"] for item in comparison["analyses"]], [latest.analysis_id, older.analysis_id])
        self.assertEqual(comparison["pairwise"]["totalCo2"]["absolute"], 5)
        self.assertEqual(comparison["rankings"]["totalCo2"][0]["id"], latest.analysis_id)

    def test_compare_recent_analyses_supports_more_than_two_items(self):
        store = InMemoryAnalysisStore()
        store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 1, "totalHectares": 10, "hasSupportedVegetation": True, "topCategory": None},
            )
        )
        store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 3, "totalHectares": 20, "hasSupportedVegetation": True, "topCategory": None},
            )
        )
        latest = store.save(
            create_stored_analysis(
                source="selection",
                summary={"items": [], "totalCo2": 2, "totalHectares": 5, "hasSupportedVegetation": True, "topCategory": None},
            )
        )

        comparison = compare_recent_analyses(analysis_store=store, limit=3)

        self.assertEqual(len(comparison["analyses"]), 3)
        self.assertIsNone(comparison["pairwise"])
        self.assertEqual(comparison["analyses"][0]["id"], latest.analysis_id)
        self.assertEqual(comparison["rankings"]["totalHectares"][0]["value"], 20)

    def test_compare_recent_analyses_requires_two_records(self):
        store = InMemoryAnalysisStore()
        store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 1, "totalHectares": 10, "hasSupportedVegetation": True, "topCategory": None},
            )
        )

        with self.assertRaisesMessage(ValueError, "Servono almeno due analisi recenti"):
            compare_recent_analyses(analysis_store=store)

    def test_compare_saved_history_analyses_resolves_labels_and_municipalities(self):
        store = InMemoryAnalysisStore()
        first = store.save(
            create_stored_analysis(
                source="municipalities",
                summary={"items": [], "totalCo2": 10, "totalHectares": 5, "hasSupportedVegetation": True, "topCategory": None},
                requested_municipalities=["Castellabate"],
                intersected_municipalities=["Castellabate"],
            )
        )
        second = store.save(
            StoredAnalysis(
                analysis_id="analysis_roccadaspide",
                source="municipalities",
                created_at="2026-06-24T10:00:00+00:00",
                label="Analisi Roccadaspide",
                selection_kind="municipalities",
                summary={"items": [], "totalCo2": 20, "totalHectares": 10, "hasSupportedVegetation": True, "topCategory": None},
                requested_municipalities=("Roccadaspide",),
                intersected_municipalities=("Roccadaspide",),
            )
        )

        comparison = compare_saved_history_analyses(
            analysis_store=store,
            selectors=["Castellabate", "Analisi Roccadaspide"],
        )

        self.assertEqual([item["id"] for item in comparison["analyses"]], [first.analysis_id, second.analysis_id])
        self.assertEqual(comparison["rankings"]["totalCo2"][0]["id"], second.analysis_id)

    def test_compare_saved_history_analyses_rejects_ambiguous_selector(self):
        store = InMemoryAnalysisStore()
        for label in ("Analisi A", "Analisi B"):
            store.save(
                StoredAnalysis(
                    analysis_id=f"analysis_{label[-1].casefold()}",
                    source="municipalities",
                    created_at="2026-06-24T10:00:00+00:00",
                    label=label,
                    selection_kind="municipalities",
                    summary={"items": [], "totalCo2": 10, "totalHectares": 5, "hasSupportedVegetation": True, "topCategory": None},
                    requested_municipalities=("Avellino",),
                    intersected_municipalities=("Avellino",),
                )
            )

        with self.assertRaisesMessage(ValueError, "Riferimento ambiguo"):
            compare_saved_history_analyses(analysis_store=store, selectors=["Avellino", "Analisi A"])

    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_search_municipalities_returns_exact_and_suggested_matches(self, load_municipality_shapes):
        load_municipality_shapes.return_value = GisClipServiceTests._municipality_shapes_catalog()
        registry = build_default_tool_registry(InMemoryAnalysisStore())

        payload = registry.execute(ToolName.SEARCH_MUNICIPALITIES, query="Avell", limit=5)

        self.assertEqual(payload["suggestions"], ["Avellino"])
        self.assertIn("Avellino", payload["matches"])

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    def test_analyze_selection_returns_empty_supported_summary_for_area_without_nature(
        self,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = GisClipServiceTests._campania_boundaries()

        payload = analyze_selection(
            selection_payload={
                "areas": [
                    {
                        "kind": "drawn",
                        "geojson": {
                            "type": "FeatureCollection",
                            "features": [
                                {
                                    "type": "Feature",
                                    "properties": {},
                                    "geometry": box(10, 10, 11, 11).__geo_interface__,
                                }
                            ],
                        },
                    }
                ]
            }
        )

        self.assertFalse(payload["summary"]["hasSupportedVegetation"])
        self.assertEqual(payload["summary"]["items"], [])
        self.assertEqual(payload["intersectedMunicipalities"], [])

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    def test_analyze_selection_handles_mixed_municipality_and_drawn_payload(
        self,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_nature_shapes.return_value = GisClipServiceTests._nature_shapes()
        load_campania_boundaries.return_value = GisClipServiceTests._campania_boundaries()

        payload = analyze_selection(
            selection_payload={
                "areas": [
                    {
                        "kind": "municipalities",
                        "geojson": GisClipServiceTests._municipality_geojson("Comune Uno"),
                    },
                    {
                        "kind": "drawn",
                        "geojson": GisClipServiceTests._drawn_geojson(),
                    },
                ]
            }
        )

        self.assertTrue(payload["summary"]["hasSupportedVegetation"])
        self.assertEqual(payload["intersectedMunicipalities"], ["Comune Uno"])


class ObservabilityTests(SimpleTestCase):
    def test_summarize_openai_usage_accepts_responses_usage_shape(self):
        usage = summarize_openai_usage(
            {
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 8,
                    "total_tokens": 20,
                }
            }
        )

        self.assertEqual(
            usage,
            {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
        )

    def test_summarize_openai_usage_falls_back_to_classic_token_names(self):
        usage = summarize_openai_usage(
            {
                "usage": {
                    "prompt_tokens": "7",
                    "completion_tokens": "3",
                }
            }
        )

        self.assertEqual(
            usage,
            {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
        )


class ExperimentLoggingTests(SimpleTestCase):
    def test_record_experiment_event_sanitizes_details(self):
        session = {}

        event = record_experiment_event(
            session,
            event_type="task_completed",
            channel="voice",
            operation="conversational_request",
            interaction_mode="voice",
            duration_ms=1200,
            step_count=3,
            details={
                "messageText": "non salvare",
                "transcriptText": "non salvare",
                "messageLength": 42,
                "totalCo2": 12.5,
            },
        )

        self.assertEqual(event["eventType"], "task_completed")
        self.assertEqual(event["details"], {"messageLength": 42, "totalCo2": 12.5})
        self.assertNotIn("messageText", event["details"])
        self.assertNotIn("transcriptText", event["details"])

    def test_export_experiment_log_returns_summary_metrics(self):
        session = {}
        record_experiment_event(
            session,
            event_type="interaction_started",
            channel="web_chat",
            operation="conversational_request",
            interaction_mode="text",
        )
        record_experiment_event(
            session,
            event_type="task_completed",
            channel="web_chat",
            operation="analyze_municipalities",
            interaction_mode="text",
            duration_ms=900,
            step_count=2,
        )
        record_experiment_event(
            session,
            event_type="report_generated",
            channel="web_map",
            operation="report_generation",
            interaction_mode="map",
        )

        payload = export_experiment_log(session)

        self.assertEqual(payload["eventCount"], 3)
        self.assertEqual(payload["summary"]["taskCompletionCount"], 1)
        self.assertEqual(payload["summary"]["textInteractionCount"], 2)
        self.assertEqual(payload["summary"]["reportGeneratedCount"], 1)

    def test_task_runs_are_isolated_and_duration_is_server_derived(self):
        with TemporaryDirectory() as temp_dir, override_settings(STUDY_LOG_ROOT=Path(temp_dir)):
            context = create_study_session(
                participant_id="participant_lifecycle",
                condition="webgis",
                task_id="task_initial",
                log_root=Path(temp_dir),
            )
            session = {
                STUDY_CONTEXT_SESSION_KEY: {
                    "participantId": context.participantId,
                    "studySessionId": context.studySessionId,
                    "condition": context.condition,
                    "taskId": context.taskId,
                }
            }

            first_start = record_experiment_event(
                session,
                event_type="task_started",
                task_id="task_area",
                condition="webgis",
            )
            record_experiment_event(
                session,
                event_type="ui_action",
                channel="web_map",
                interaction_mode="map",
                details={"controlId": "eseguiClipBut"},
            )
            first_complete = record_experiment_event(
                session,
                event_type="task_completed",
                task_run_id=first_start["taskRunId"],
                duration_ms=999999,
                details={"analysisId": "analysis_ui"},
            )
            duplicate_complete = record_experiment_event(
                session,
                event_type="task_completed",
                task_run_id=first_start["taskRunId"],
            )

            second_start = record_experiment_event(
                session,
                event_type="task_started",
                task_id="task_economic",
                condition="webgis",
            )
            record_experiment_event(
                session,
                event_type="valuation_completed",
                channel="web_map",
                interaction_mode="map",
                details={
                    "analysisId": "analysis_economic",
                    "scenarioKey": "social_cost",
                    "priceEurPerTon": 138,
                    "totalValueEur": 1380,
                },
            )
            record_experiment_event(
                session,
                event_type="task_completed",
                task_run_id=second_start["taskRunId"],
            )
            exported = export_experiment_log(session)
            persisted = export_study_session(context, log_root=Path(temp_dir))

        self.assertNotEqual(first_start["taskRunId"], second_start["taskRunId"])
        self.assertNotEqual(first_complete["durationMs"], 999999)
        self.assertEqual(first_complete["eventId"], duplicate_complete["eventId"])
        self.assertEqual(exported["summary"]["taskCompletionCount"], 2)
        self.assertEqual(len(exported["summary"]["tasks"]), 2)
        self.assertEqual(
            {task["taskId"] for task in exported["summary"]["tasks"]},
            {"task_area", "task_economic"},
        )
        self.assertEqual(
            exported["summary"]["tasks"][1]["analysisIds"],
            ["analysis_economic"],
        )
        self.assertEqual(persisted["events"][0]["eventId"], first_start["eventId"])
        self.assertEqual(persisted["events"][0]["taskId"], "task_area")
        self.assertEqual(persisted["events"][0]["taskRunId"], first_start["taskRunId"])

    def test_new_task_interrupts_active_task_and_conversation_events_stay_separate(self):
        session = {}
        first_start = record_experiment_event(
            session,
            event_type="task_started",
            task_id="task_one",
            condition="conversational",
        )
        second_start = record_experiment_event(
            session,
            event_type="task_started",
            task_id="task_two",
            condition="conversational",
        )
        record_experiment_event(
            session,
            event_type="chat_message",
            channel="web_chat",
            interaction_mode="text",
        )
        record_experiment_event(
            session,
            event_type="tool_started",
            channel="web_chat",
            operation="calculate_economic_value",
            interaction_mode="text",
            details={"toolCallId": "call_1", "toolName": "calculate_economic_value"},
        )
        record_experiment_event(
            session,
            event_type="tool_completed",
            channel="web_chat",
            operation="calculate_economic_value",
            interaction_mode="text",
            details={
                "analysisId": "analysis_chat",
                "toolCallId": "call_1",
                "toolName": "calculate_economic_value",
            },
        )
        record_experiment_event(
            session,
            event_type="task_failed",
            task_run_id=second_start["taskRunId"],
            error="timeout",
        )
        exported = export_experiment_log(session)

        first_task = exported["summary"]["tasks"][0]
        second_task = exported["summary"]["tasks"][1]
        self.assertEqual(first_task["taskRunId"], first_start["taskRunId"])
        self.assertEqual(first_task["status"], "interrupted")
        self.assertEqual(second_task["status"], "failed")
        self.assertEqual(exported["summary"]["chatMessageCount"], 1)
        self.assertEqual(exported["summary"]["toolCallCount"], 1)
        self.assertEqual(exported["summary"]["failedTaskCount"], 1)
        self.assertEqual(exported["summary"]["interruptedTaskCount"], 1)

    def test_controlled_task_count_does_not_mix_legacy_completions(self):
        session = {}
        record_experiment_event(session, event_type="task_completed", duration_ms=12)
        started = record_experiment_event(
            session,
            event_type="task_started",
            task_id="controlled_task",
            condition="webgis",
        )
        record_experiment_event(
            session,
            event_type="task_completed",
            task_run_id=started["taskRunId"],
        )

        summary = export_experiment_log(session)["summary"]

        self.assertEqual(summary["taskCompletionCount"], 1)
        self.assertEqual(summary["legacyTaskCompletionCount"], 1)


class StudyLoggingTests(SimpleTestCase):
    def test_create_study_session_writes_summary_in_expected_directory(self):
        with TemporaryDirectory() as temp_dir:
            context = create_study_session(
                participant_id="participant_001",
                condition="webgis",
                task_id="task_area_co2",
                now=datetime(2026, 6, 13, 10, 15, tzinfo=UTC),
                log_root=Path(temp_dir),
            )

            session_dir = Path(temp_dir) / "participant_001" / "session_20260613_101500_webgis"
            summary = json.loads((session_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertTrue(session_dir.exists())

            self.assertEqual(context.participantId, "participant_001")
            self.assertEqual(context.condition, "webgis")
            self.assertEqual(summary["participantId"], "participant_001")
            self.assertEqual(summary["condition"], "webgis")
            self.assertEqual(summary["eventCount"], 0)

    def test_record_study_event_persists_jsonl_and_summary_with_conversation_text(self):
        with TemporaryDirectory() as temp_dir:
            context = create_study_session(
                participant_id="participant_002",
                condition="conversational",
                task_id="task_report",
                now=datetime(2026, 6, 13, 10, 42, tzinfo=UTC),
                log_root=Path(temp_dir),
            )

            event = record_study_event(
                context,
                event_type="interaction_completed",
                channel="voice",
                operation="analyze_municipalities",
                interaction_mode="voice",
                duration_ms=1200,
                step_count=2,
                status="completed",
                intent="analyze_municipalities",
                user_text="analizza Avellino",
                user_transcript="analizza Avellino",
                assistant_response="Ho analizzato Avellino.",
                details={
                    "toolCalls": ["analyze_municipalities"],
                    "email": "person@example.com",
                    "ip": "127.0.0.1",
                    "userAgent": "Browser",
                },
                log_root=Path(temp_dir),
            )
            exported = export_study_session(context, log_root=Path(temp_dir))
            jsonl = export_study_events_jsonl(context, log_root=Path(temp_dir))
            summary_path = (
                Path(temp_dir)
                / "participant_002"
                / "session_20260613_104200_conversational"
                / "summary.json"
            )
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(event["participantId"], "participant_002")
        self.assertEqual(event["condition"], "conversational")
        self.assertEqual(event["taskId"], "task_report")
        self.assertEqual(event["userText"], "analizza Avellino")
        self.assertEqual(event["userTranscript"], "analizza Avellino")
        self.assertEqual(event["assistantResponse"], "Ho analizzato Avellino.")
        self.assertEqual(event["details"], {"toolCalls": ["analyze_municipalities"]})
        self.assertEqual(exported["eventCount"], 1)
        self.assertIn('"userText": "analizza Avellino"', jsonl)
        self.assertEqual(summary["eventCount"], 1)
        self.assertEqual(summary["voiceInteractionCount"], 1)

    def test_study_logging_sanitizes_ids_and_invalid_values(self):
        with TemporaryDirectory() as temp_dir:
            context = create_study_session(
                participant_id="../participant 003@example.com",
                condition="invalid-condition",
                task_id="../task/one",
                now=datetime(2026, 6, 13, 11, 0, tzinfo=UTC),
                log_root=Path(temp_dir),
            )
            event = record_study_event(
                context,
                event_type="not_allowed",
                channel="browser",
                interaction_mode="browser",
                duration_ms=-5,
                step_count="bad",
                log_root=Path(temp_dir),
            )

        self.assertEqual(context.participantId, "participant_003_example_com")
        self.assertEqual(context.condition, "webgis")
        self.assertEqual(context.taskId, "task_one")
        self.assertEqual(event["eventType"], "error")
        self.assertEqual(event["channel"], "system")
        self.assertNotIn("durationMs", event)
        self.assertNotIn("stepCount", event)


@override_settings(
    STUDY_ADMIN_PASSWORD="test-study-admin-password",
    SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
)
class StudyAdminTests(SimpleTestCase):
    @staticmethod
    def _login(client: Client, password: str = "test-study-admin-password"):
        return client.post(
            "/progettoGIS/cartaNatura/study-admin/login/",
            {"password": password},
        )

    def test_admin_lists_session_events_and_downloads_clean_exports(self):
        with TemporaryDirectory() as temp_dir, override_settings(STUDY_LOG_ROOT=Path(temp_dir)):
            context = create_study_session(
                participant_id="participant_admin_001",
                condition="conversational",
                task_id="asita_t1_area_analysis",
                now=datetime(2026, 9, 1, 10, 30, tzinfo=UTC),
                log_root=Path(temp_dir),
            )
            record_study_event(
                context,
                event_type="task_completed",
                status="completed",
                task_run_id="taskrun_admin_001",
                duration_ms=1200,
                log_root=Path(temp_dir),
            )
            client = Client()
            self._login(client)

            page = client.get("/progettoGIS/cartaNatura/study-admin/")
            json_export = client.get(
                f"/progettoGIS/cartaNatura/study-admin/{context.participantId}/"
                f"{context.studySessionId}/download/json/"
            )
            jsonl_export = client.get(
                f"/progettoGIS/cartaNatura/study-admin/{context.participantId}/"
                f"{context.studySessionId}/download/jsonl/"
            )

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Esperimenti salvati")
        self.assertContains(page, context.participantId)
        self.assertContains(page, "task_completed")
        self.assertEqual(json_export.status_code, 200)
        self.assertEqual(jsonl_export.status_code, 200)
        for protected_response in (page, json_export, jsonl_export):
            self.assertIn("no-store", protected_response["Cache-Control"])
        exported_payload = json.loads(json_export.content)
        self.assertEqual(exported_payload["events"][0]["eventType"], "task_completed")
        self.assertNotIn("prettyJson", exported_payload["events"][0])
        self.assertIn('attachment; filename="participant_admin_001_', json_export["Content-Disposition"])
        self.assertIn('"eventType": "task_completed"', jsonl_export.content.decode("utf-8"))

    def test_admin_deletes_closed_session(self):
        with TemporaryDirectory() as temp_dir, override_settings(STUDY_LOG_ROOT=Path(temp_dir)):
            context = create_study_session(
                participant_id="participant_delete_001",
                condition="webgis",
                now=datetime(2026, 9, 1, 11, 0, tzinfo=UTC),
                log_root=Path(temp_dir),
            )
            session_path = Path(temp_dir) / context.participantId / context.studySessionId
            client = Client()
            self._login(client)
            response = client.post(
                f"/progettoGIS/cartaNatura/study-admin/{context.participantId}/"
                f"{context.studySessionId}/delete/"
            )

            self.assertEqual(response.status_code, 302)
            self.assertFalse(session_path.exists())

    def test_admin_does_not_delete_active_session(self):
        with TemporaryDirectory() as temp_dir, override_settings(
            STUDY_LOG_ROOT=Path(temp_dir),
            SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
        ):
            client = Client()
            started = client.post(
                "/progettoGIS/cartaNatura/experiment/study/session",
                data=json.dumps(
                    {
                        "participantId": "participant_active_001",
                        "condition": "webgis",
                        "taskId": "asita_t1_area_analysis",
                    }
                ),
                content_type="application/json",
            ).json()["session"]
            self._login(client)
            session_path = Path(temp_dir) / started["participantId"] / started["studySessionId"]
            response = client.post(
                f"/progettoGIS/cartaNatura/study-admin/{started['participantId']}/"
                f"{started['studySessionId']}/delete/"
            )

            self.assertEqual(response.status_code, 302)
            self.assertIn("error=active", response.url)
            self.assertTrue(session_path.exists())

    def test_anonymous_archive_exports_and_delete_are_blocked_for_both_route_aliases(self):
        with TemporaryDirectory() as temp_dir, override_settings(STUDY_LOG_ROOT=Path(temp_dir)):
            context = create_study_session(
                participant_id="participant_private_001",
                condition="webgis",
                now=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
                log_root=Path(temp_dir),
            )
            session_path = Path(temp_dir) / context.participantId / context.studySessionId
            client = Client()

            for prefix in ("", "/progettoGIS/cartaNatura"):
                page = client.get(f"{prefix}/study-admin/")
                download = client.get(
                    f"{prefix}/study-admin/{context.participantId}/"
                    f"{context.studySessionId}/download/json/"
                )
                delete = client.post(
                    f"{prefix}/study-admin/{context.participantId}/"
                    f"{context.studySessionId}/delete/"
                )

                self.assertEqual(page.status_code, 302)
                self.assertIn("/study-admin/login/", page.url)
                self.assertNotIn(context.participantId, page.content.decode("utf-8"))
                self.assertEqual(download.status_code, 302)
                self.assertIn("/study-admin/login/", download.url)
                self.assertEqual(delete.status_code, 302)
                self.assertIn("/study-admin/login/", delete.url)
                self.assertTrue(session_path.exists())

    def test_login_rejects_wrong_password_and_allows_correct_password(self):
        client = Client()

        wrong = self._login(client, "wrong-password")
        still_blocked = client.get("/progettoGIS/cartaNatura/study-admin/")
        correct = self._login(client)
        allowed = client.get("/progettoGIS/cartaNatura/study-admin/")

        self.assertEqual(wrong.status_code, 401)
        self.assertContains(wrong, "Password non corretta", status_code=401)
        self.assertEqual(still_blocked.status_code, 302)
        self.assertEqual(correct.status_code, 302)
        self.assertEqual(allowed.status_code, 200)
        self.assertContains(allowed, "Esperimenti salvati")

    def test_login_rejects_external_next_redirect(self):
        response = Client().post(
            "/progettoGIS/cartaNatura/study-admin/login/",
            {"password": "test-study-admin-password", "next": "https://attacker.example/"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/progettoGIS/cartaNatura/study-admin/")
        self.assertNotIn("attacker.example", response.url)

    @override_settings(STUDY_ADMIN_PASSWORD="")
    def test_unconfigured_password_fails_closed(self):
        client = Client()

        archive = client.get("/progettoGIS/cartaNatura/study-admin/")
        login = client.get("/progettoGIS/cartaNatura/study-admin/login/")

        self.assertEqual(archive.status_code, 302)
        self.assertEqual(login.status_code, 503)
        self.assertContains(login, "Password amministrativa non configurata", status_code=503)

    def test_password_rotation_invalidates_existing_admin_session(self):
        client = Client()
        self._login(client)

        before_rotation = client.get("/progettoGIS/cartaNatura/study-admin/")
        with override_settings(STUDY_ADMIN_PASSWORD="rotated-study-password"):
            after_rotation = client.get("/progettoGIS/cartaNatura/study-admin/")

        self.assertEqual(before_rotation.status_code, 200)
        self.assertEqual(after_rotation.status_code, 302)
        self.assertIn("/study-admin/login/", after_rotation.url)

    def test_logout_preserves_active_study_context(self):
        with TemporaryDirectory() as temp_dir, override_settings(STUDY_LOG_ROOT=Path(temp_dir)):
            client = Client()
            started = client.post(
                "/progettoGIS/cartaNatura/experiment/study/session",
                data='{"participantId":"participant_logout","condition":"webgis"}',
                content_type="application/json",
            ).json()["session"]
            self._login(client)

            logout = client.post("/progettoGIS/cartaNatura/study-admin/logout/")
            archive = client.get("/progettoGIS/cartaNatura/study-admin/")

            self.assertEqual(logout.status_code, 302)
            self.assertEqual(archive.status_code, 302)
            self.assertEqual(client.session[STUDY_CONTEXT_SESSION_KEY]["studySessionId"], started["studySessionId"])

    def test_admin_mutations_keep_csrf_protection(self):
        client = Client(enforce_csrf_checks=True)
        login_page = client.get("/progettoGIS/cartaNatura/study-admin/login/")
        csrf_token = login_page.cookies["csrftoken"].value

        rejected_login = client.post(
            "/progettoGIS/cartaNatura/study-admin/login/",
            {"password": "test-study-admin-password"},
        )
        accepted_login = client.post(
            "/progettoGIS/cartaNatura/study-admin/login/",
            {"password": "test-study-admin-password", "csrfmiddlewaretoken": csrf_token},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        rejected_logout = client.post("/progettoGIS/cartaNatura/study-admin/logout/")
        rejected_delete = client.post("/study-admin/participant_001/session_001/delete/")

        self.assertEqual(rejected_login.status_code, 403)
        self.assertEqual(accepted_login.status_code, 302)
        self.assertEqual(rejected_logout.status_code, 403)
        self.assertEqual(rejected_delete.status_code, 403)


@override_settings(
    STUDY_ADMIN_PASSWORD="test-study-admin-password",
    SESSION_ENGINE="django.contrib.sessions.backends.db",
)
class StudyAdminDatabaseSessionTests(TestCase):
    def test_login_rotates_session_and_logout_preserves_study_context(self):
        with TemporaryDirectory() as temp_dir, override_settings(STUDY_LOG_ROOT=Path(temp_dir)):
            client = Client()
            started = client.post(
                "/experiment/study/session",
                data='{"participantId":"participant_db_auth","condition":"webgis"}',
                content_type="application/json",
            ).json()["session"]
            previous_session_key = client.session.session_key

            login = StudyAdminTests._login(client)
            self.assertEqual(login.status_code, 302)
            self.assertNotEqual(client.session.session_key, previous_session_key)
            self.assertEqual(client.get("/study-admin/").status_code, 200)
            self.assertNotIn("test-study-admin-password", json.dumps(dict(client.session)))

            client.post("/study-admin/logout/")
            self.assertEqual(client.get("/study-admin/").status_code, 302)
            self.assertEqual(
                client.session[STUDY_CONTEXT_SESSION_KEY]["studySessionId"],
                started["studySessionId"],
            )


class VoiceTranscriptionTests(SimpleTestCase):
    @patch("cartaNatura.interaction.voice.OpenAI")
    def test_transcribe_uploaded_audio_uses_tuple_file_upload(self, openai_client_class):
        create = MagicMock(return_value="analizza Avellino")
        openai_client_class.return_value.audio.transcriptions.create = create
        audio = SimpleUploadedFile(
            "voice.webm",
            b"fake-audio",
            content_type="audio/webm",
        )

        with patch.dict("os.environ", {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"}):
            transcript = transcribe_uploaded_audio(audio)

        self.assertEqual(transcript, "analizza Avellino")
        file_argument = create.call_args.kwargs["file"]
        self.assertIsInstance(file_argument, tuple)
        self.assertEqual(file_argument[0], "voice.webm")
        self.assertEqual(file_argument[1], b"fake-audio")
        self.assertEqual(file_argument[2], "audio/webm")
