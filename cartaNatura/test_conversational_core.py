from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import geopandas
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings
from shapely.geometry import box

from cartaNatura.interaction.analysis_store import InMemoryAnalysisStore, create_stored_analysis
from cartaNatura.interaction.llm import (
    LlmProviderUnavailableError,
    OpenAiResponsesLlmProvider,
)
from cartaNatura.interaction.models import (
    InteractionChannel,
    InteractionContext,
    InteractionInput,
    InteractionRequest,
    SessionContext,
)
from cartaNatura.interaction.orchestrator import build_default_orchestrator
from cartaNatura.interaction.resolvers import RuleBasedIntentResolver
from cartaNatura.interaction.session import InMemorySessionStore
from cartaNatura.services.municipality_text import resolve_municipality_names
from cartaNatura.telemetry import load_raw_events
from cartaNatura.tests import (
    FakeResponsesProvider,
    FakeStreamingProvider,
    model_answer,
    model_streams,
)


def tool_call(name: str, arguments: dict | None = None, *, call_id: str) -> dict:
    return {
        "id": f"response_{call_id}",
        "output": [{
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": json.dumps(arguments or {}),
        }],
    }


def fake_analysis(*, municipality_names: list[str]) -> dict:
    return {
        "source": "municipalities",
        "selectionPayload": {"areas": [{"kind": "municipalities", "geojson": {}}]},
        "clipped": {"type": "FeatureCollection", "features": []},
        "requestedMunicipalities": list(municipality_names),
        "intersectedMunicipalities": list(municipality_names),
        "summary": {
            "items": [{
                "key": "faggete",
                "label": "Faggete",
                "hectares": 2.0,
                "co2PerHectare": 5.0,
            }],
            "totalCo2": 10.0,
            "totalHectares": 2.0,
            "hasSupportedVegetation": True,
            "topCategory": {"key": "faggete", "label": "Faggete", "hectares": 2.0},
        },
    }


class FailingAfterResponsesProvider(FakeResponsesProvider):
    provider_name = "openai"
    runtime_name = "responses_api"
    model = "gpt-test"

    def create_response(self, **payload):
        if self._responses:
            return super().create_response(**payload)
        raise LlmProviderUnavailableError("OpenAI unavailable")


class ConversationalTrustBoundaryTests(SimpleTestCase):
    def _orchestrator(self, responses, *, store=None, sessions=None):
        return build_default_orchestrator(
            llm_provider=FakeResponsesProvider(responses),
            analysis_store=store or InMemoryAnalysisStore(),
            session_store=sessions or InMemorySessionStore(),
        )

    def test_text_with_structured_map_payload_still_requires_llm_mediation(self):
        provider = FakeResponsesProvider([model_answer("Richiesta interpretata dal modello.")])
        orchestrator = build_default_orchestrator(
            llm_provider=provider,
            analysis_store=InMemoryAnalysisStore(),
            session_store=InMemorySessionStore(),
        )
        request = InteractionRequest(
            channel=InteractionChannel.WEB_MAP,
            session_id="mandatory-llm",
            input=InteractionInput(
                text="spiegami questa selezione",
                geo_selection={"areas": [{"kind": "drawn", "geojson": {}}]},
            ),
        )

        with patch.object(
            RuleBasedIntentResolver,
            "resolve",
            side_effect=AssertionError("text must never reach the legacy resolver"),
        ):
            response = orchestrator.handle(request)

        self.assertEqual(response.messages[0].text, "Richiesta interpretata dal modello.")
        self.assertEqual(len(provider.calls), 1)

    @patch("cartaNatura.interaction.tools.registry.analyze_municipalities", side_effect=fake_analysis)
    def test_provider_failure_after_successful_tool_rolls_back_domain_and_session(self, _analysis):
        store = InMemoryAnalysisStore()
        sessions = InMemorySessionStore()
        original = store.save(create_stored_analysis(source="selection", summary={"items": []}))
        sessions.save("rollback", SessionContext(last_analysis={"analysisId": original.analysis_id}))
        provider = FailingAfterResponsesProvider([
            tool_call("analyze_municipalities", {"municipality_names": ["Avellino"]}, call_id="call_analysis"),
        ])
        orchestrator = build_default_orchestrator(
            llm_provider=provider,
            analysis_store=store,
            session_store=sessions,
        )

        with self.assertRaises(LlmProviderUnavailableError):
            orchestrator.handle(InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="rollback",
                input=InteractionInput(text="Analizza Avellino"),
            ))

        self.assertEqual([item.analysis_id for item in store.list_recent()], [original.analysis_id])
        self.assertEqual(sessions.load("rollback").last_analysis["analysisId"], original.analysis_id)

    def test_malformed_tool_arguments_never_execute_domain_operation(self):
        store = InMemoryAnalysisStore()
        provider = FakeResponsesProvider([{
            "id": "malformed-tool",
            "output": [{
                "type": "function_call",
                "call_id": "bad-call",
                "name": "analyze_municipalities",
                "arguments": "{not-json",
            }],
        }])
        orchestrator = build_default_orchestrator(
            llm_provider=provider,
            analysis_store=store,
            session_store=InMemorySessionStore(),
        )

        with self.assertRaises(LlmProviderUnavailableError):
            orchestrator.handle(InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="malformed",
                input=InteractionInput(text="Analizza Avellino"),
            ))
        self.assertEqual(store.list_recent(), [])

    def test_structurally_malformed_provider_response_is_explicit_failure(self):
        orchestrator = self._orchestrator([[]])

        with self.assertRaisesMessage(LlmProviderUnavailableError, "strutturalmente non valida"):
            orchestrator.handle(InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="malformed-response",
                input=InteractionInput(text="Analizza Avellino"),
            ))

    def test_structurally_malformed_stream_response_is_explicit_failure(self):
        provider = FakeStreamingProvider([{"events": [], "final_payload": []}])
        orchestrator = build_default_orchestrator(
            llm_provider=provider,
            analysis_store=InMemoryAnalysisStore(),
            session_store=InMemorySessionStore(),
        )

        with self.assertRaisesMessage(LlmProviderUnavailableError, "strutturalmente non valida"):
            list(orchestrator.handle_stream(InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="malformed-stream",
                input=InteractionInput(text="Analizza Avellino"),
            )))

    def test_quantitative_contradiction_is_rejected_and_economic_mutation_rolls_back(self):
        store = InMemoryAnalysisStore()
        saved = store.save(create_stored_analysis(
            source="municipalities",
            summary={
                "items": [], "totalCo2": 10, "totalHectares": 2,
                "hasSupportedVegetation": True, "topCategory": None,
            },
            requested_municipalities=["Avellino"],
        ))
        orchestrator = self._orchestrator([
            tool_call("calculate_economic_value", {
                "scenario_key": "social_cost", "analysis_id": saved.analysis_id,
            }, call_id="economic"),
            model_answer("Il valore autorevole è 999 euro.", "compare_economic_scenarios"),
        ], store=store)

        with self.assertRaisesMessage(LlmProviderUnavailableError, "non verificabili"):
            orchestrator.handle(InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="grounding",
                input=InteractionInput(text="Calcola il costo sociale"),
                context=InteractionContext(displayed_analysis_id=saved.analysis_id),
            ))
        self.assertIsNone(store.get(saved.analysis_id).economic_valuation)

    def test_report_tool_cannot_claim_pdf_generation_or_download(self):
        store = InMemoryAnalysisStore()
        saved = store.save(create_stored_analysis(
            source="selection",
            summary={"items": [], "totalCo2": 0, "totalHectares": 0,
                     "hasSupportedVegetation": False, "topCategory": None},
        ))
        orchestrator = self._orchestrator([
            tool_call("prepare_report", {"analysis_id": saved.analysis_id}, call_id="report"),
            model_answer("Il PDF è stato generato e scaricato.", "generate_report"),
        ], store=store)

        with self.assertRaisesMessage(LlmProviderUnavailableError, "stato PDF non avvenuto"):
            orchestrator.handle(InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="report-claim",
                input=InteractionInput(text="Prepara il report"),
            ))

    @patch("cartaNatura.interaction.tools.registry.analyze_municipalities", side_effect=fake_analysis)
    def test_stream_failure_does_not_publish_analysis_or_commit_history(self, _analysis):
        store = InMemoryAnalysisStore()
        provider = FakeStreamingProvider(model_streams([
            tool_call("analyze_municipalities", {"municipality_names": ["Avellino"]}, call_id="stream-analysis"),
            {"id": "stream-empty", "output": []},
        ]))
        orchestrator = build_default_orchestrator(
            llm_provider=provider,
            analysis_store=store,
            session_store=InMemorySessionStore(),
        )
        events = []

        with self.assertRaises(LlmProviderUnavailableError):
            for event in orchestrator.handle_stream(InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="stream-rollback",
                input=InteractionInput(text="Analizza Avellino"),
            )):
                events.append(event)

        self.assertNotIn("analysis_result", [event["type"] for event in events])
        self.assertEqual(store.list_recent(), [])

    @patch("cartaNatura.interaction.tools.registry.analyze_municipalities", side_effect=fake_analysis)
    def test_required_multi_tool_chains_keep_analysis_references_distinct(self, _analysis):
        store = InMemoryAnalysisStore()
        sessions = InMemorySessionStore()

        montella = self._orchestrator([
            tool_call("analyze_municipalities", {"municipality_names": ["Montella"]}, call_id="montella"),
            tool_call("calculate_economic_value", {"scenario_key": "social_cost", "analysis_id": None}, call_id="montella-economy"),
            model_answer("Analisi e valore economico pronti.", "compare_economic_scenarios"),
        ], store=store, sessions=sessions).handle(InteractionRequest(
            channel=InteractionChannel.WEB_CHAT,
            session_id="multi-context",
            input=InteractionInput(text="Analizza Montella e calcola il valore economico"),
        ))
        montella_id = montella.analysis_result["analysisId"]
        self.assertEqual(montella.economic_result["analysisId"], montella_id)

        salerno = self._orchestrator([
            tool_call("analyze_municipalities", {"municipality_names": ["Salerno"]}, call_id="salerno"),
            tool_call("filter_last_analysis_categories", {
                "category_names": ["faggete"], "show_all": False,
            }, call_id="salerno-filter"),
            model_answer("Analisi di Salerno filtrata.", "extract_forest_information"),
        ], store=store, sessions=sessions).handle(InteractionRequest(
            channel=InteractionChannel.WEB_CHAT,
            session_id="multi-context",
            input=InteractionInput(text="Analizza Salerno e mostra le faggete"),
            context=InteractionContext(displayed_analysis_id=montella_id),
        ))
        salerno_id = salerno.analysis_result["analysisId"]
        self.assertNotEqual(salerno_id, montella_id)
        self.assertEqual(salerno.map_filter["analysisId"], salerno_id)
        self.assertEqual(sessions.load("multi-context").last_analysis["analysisId"], salerno_id)

        comparison = self._orchestrator([
            tool_call("compare_recent_analyses", {"recent_count": 2}, call_id="recent-comparison"),
            model_answer("Confronto tra questa analisi e la precedente pronto.", "compare_analyses"),
        ], store=store, sessions=sessions).handle(InteractionRequest(
            channel=InteractionChannel.WEB_CHAT,
            session_id="multi-context",
            input=InteractionInput(text="Confronta questa analisi con la precedente"),
            context=InteractionContext(displayed_analysis_id=salerno_id),
        ))
        self.assertEqual(
            {item["id"] for item in comparison.analysis_result["analyses"]},
            {montella_id, salerno_id},
        )
        self.assertEqual(len(store.list_recent()), 2)

        scenarios = self._orchestrator([
            tool_call("compare_economic_scenarios", {"analysis_id": salerno_id}, call_id="all-scenarios"),
            model_answer("Confronto di tutti gli scenari pronto.", "compare_economic_scenarios"),
        ], store=store, sessions=sessions).handle(InteractionRequest(
            channel=InteractionChannel.WEB_CHAT,
            session_id="multi-context",
            input=InteractionInput(text="Confronta tutti gli scenari economici"),
            context=InteractionContext(displayed_analysis_id=salerno_id),
        ))
        self.assertEqual(scenarios.scenario_comparison["analysisId"], salerno_id)
        self.assertEqual(len(scenarios.scenario_comparison["scenarios"]), 4)

        joint_store = InMemoryAnalysisStore()
        joint = self._orchestrator([
            tool_call("analyze_municipalities", {
                "municipality_names": ["Avellino", "Salerno"],
            }, call_id="joint"),
            tool_call("calculate_economic_value", {
                "scenario_key": "regulated_market", "analysis_id": None,
            }, call_id="joint-economy"),
            tool_call("prepare_report", {"analysis_id": None}, call_id="joint-report"),
            model_answer("Analisi congiunta, economia e report preparati.", "generate_report"),
        ], store=joint_store).handle(InteractionRequest(
            channel=InteractionChannel.WEB_CHAT,
            session_id="joint-chain",
            input=InteractionInput(text="Analizza Avellino e Salerno insieme, valuta e prepara il report"),
        ))
        joint_id = joint.analysis_result["analysisId"]
        self.assertEqual(joint.analysis_result["requestedMunicipalities"], ["Avellino", "Salerno"])
        self.assertEqual(joint.economic_result["analysisId"], joint_id)
        self.assertEqual(joint.report_context["analysisId"], joint_id)
        self.assertEqual(joint.report_context["action"], "open_existing_report")

    def test_explicit_displayed_analysis_target_does_not_replace_last_analysis(self):
        store = InMemoryAnalysisStore()
        displayed = store.save(create_stored_analysis(
            source="municipalities",
            summary={"items": [], "totalCo2": 10, "totalHectares": 2,
                     "hasSupportedVegetation": True, "topCategory": None},
            requested_municipalities=["Avellino"],
        ))
        latest = store.save(create_stored_analysis(
            source="municipalities",
            summary={"items": [], "totalCo2": 20, "totalHectares": 4,
                     "hasSupportedVegetation": True, "topCategory": None},
            requested_municipalities=["Salerno"],
        ))
        sessions = InMemorySessionStore()
        sessions.save("displayed-target", SessionContext(last_analysis={"analysisId": latest.analysis_id}))
        response = self._orchestrator([
            tool_call("calculate_economic_value", {
                "scenario_key": "social_cost", "analysis_id": displayed.analysis_id,
            }, call_id="displayed-economy"),
            model_answer("Valutazione dell'analisi visualizzata pronta.", "compare_economic_scenarios"),
        ], store=store, sessions=sessions).handle(InteractionRequest(
            channel=InteractionChannel.WEB_CHAT,
            session_id="displayed-target",
            input=InteractionInput(text="Calcola il valore di questa analisi"),
            context=InteractionContext(displayed_analysis_id=displayed.analysis_id),
        ))
        self.assertEqual(response.economic_result["analysisId"], displayed.analysis_id)
        self.assertEqual(sessions.load("displayed-target").last_analysis["analysisId"], latest.analysis_id)
        self.assertIsNotNone(store.get(displayed.analysis_id).economic_valuation)
        self.assertIsNone(store.get(latest.analysis_id).economic_valuation)

    @patch("cartaNatura.interaction.tools.registry.analyze_municipalities", side_effect=fake_analysis)
    def test_tool_failure_completion_and_true_recovery_are_correlated_by_call_id(self, _analysis):
        with TemporaryDirectory() as temp_dir, override_settings(RAW_EVENT_LOG_ROOT=Path(temp_dir)):
            orchestrator = self._orchestrator([
                tool_call("compare_recent_analyses", {"recent_count": 2}, call_id="compare-failed"),
                tool_call("analyze_municipalities", {"municipality_names": ["Avellino"]}, call_id="analysis-a"),
                tool_call("analyze_municipalities", {"municipality_names": ["Salerno"]}, call_id="analysis-b"),
                tool_call("compare_recent_analyses", {"recent_count": 2}, call_id="compare-retry"),
                model_answer("Errore recuperato e confronto completato.", "compare_analyses"),
            ])
            orchestrator.handle(InteractionRequest(
                channel=InteractionChannel.WEB_CHAT,
                session_id="tool-lifecycle",
                input=InteractionInput(
                    text="Analizza Avellino e Salerno separatamente e confronta",
                    metadata={
                        "interactionId": "interaction-lifecycle",
                        "interactionMode": "text",
                    },
                ),
            ))
            events = load_raw_events("tool-lifecycle")

        comparison_events = [
            event for event in events
            if event.get("tool", {}).get("name") == "compare_recent_analyses"
        ]
        by_type = {event["eventType"]: event for event in comparison_events}
        self.assertEqual(
            [event["eventType"] for event in comparison_events],
            ["tool_started", "tool_failed", "tool_started", "tool_completed", "tool_recovered"],
        )
        self.assertEqual(by_type["tool_failed"]["tool"]["callId"], "compare-failed")
        self.assertEqual(by_type["tool_completed"]["tool"]["callId"], "compare-retry")
        self.assertEqual(by_type["tool_recovered"]["tool"]["callId"], "compare-failed")
        self.assertEqual(
            by_type["tool_recovered"]["data"]["toolResult"]["recoveryCallId"],
            "compare-retry",
        )
        self.assertNotEqual(
            by_type["tool_failed"]["eventId"],
            by_type["tool_completed"]["eventId"],
        )


class MunicipalityResolutionRegressionTests(SimpleTestCase):
    @staticmethod
    def _catalog(*names: str):
        return geopandas.GeoDataFrame(
            {"COMUNE": list(names)},
            geometry=[box(index, 0, index + 1, 1) for index in range(len(names))],
            crs="EPSG:32633",
        )

    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_case_accents_and_duplicates_resolve_to_stable_canonical_names(self, load_shapes):
        load_shapes.return_value = self._catalog("Avellino", "Città della Pieve")
        self.assertEqual(
            resolve_municipality_names(["avellino", "AVELLINO", "citta della pieve"]),
            ["Avellino", "Città della Pieve"],
        )

    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_one_invalid_name_rejects_the_complete_municipality_set(self, load_shapes):
        load_shapes.return_value = self._catalog("Avellino", "Salerno")
        with self.assertRaisesMessage(ValueError, "Comunefalso"):
            resolve_municipality_names(["Avellino", "Comunefalso"])

    @patch("cartaNatura.services.municipality_text.load_municipality_shapes")
    def test_normalized_name_collision_is_reported_as_ambiguous(self, load_shapes):
        load_shapes.return_value = self._catalog("Sant'Agata", "Sant Agata")
        with self.assertRaisesMessage(ValueError, "ambigui"):
            resolve_municipality_names(["sant agata"])


class OpenAiRuntimeFreezeTests(SimpleTestCase):
    @patch("cartaNatura.interaction.llm.OpenAI")
    def test_configured_timeout_and_zero_retries_are_applied_to_openai_client(self, openai):
        OpenAiResponsesLlmProvider(
            api_key="test-key",
            model="gpt-test",
            base_url="https://example.test/v1",
            timeout_seconds=7.5,
        )
        openai.assert_called_once_with(
            api_key="test-key",
            base_url="https://example.test/v1",
            timeout=7.5,
            max_retries=0,
        )

    @patch("cartaNatura.views._build_request_orchestrator")
    @patch("cartaNatura.views.require_llm_provider_configured")
    def test_asita_endpoint_rejects_ollama_before_orchestration(self, require_provider, build):
        require_provider.return_value = SimpleNamespace(provider="ollama")
        response = Client().post(
            "/progettoGIS/cartaNatura/interact",
            data=json.dumps({"message": "Analizza Avellino"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 503)
        build.assert_not_called()


@override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
class VoiceBoundaryRegressionTests(SimpleTestCase):
    def setUp(self):
        self._temporary = TemporaryDirectory()
        self._settings = override_settings(RAW_EVENT_LOG_ROOT=Path(self._temporary.name))
        self._settings.enable()

    def tearDown(self):
        self._settings.disable()
        self._temporary.cleanup()

    @patch("cartaNatura.views.transcribe_uploaded_audio", return_value="   ")
    def test_empty_stt_transcript_is_rejected_and_not_logged_as_transcribed(self, _transcribe):
        client = Client()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            response = client.post(
                "/progettoGIS/cartaNatura/voice/transcribe",
                data={
                    "audio": SimpleUploadedFile("voice.webm", b"raw-audio", content_type="audio/webm"),
                    "interactionId": "voice-empty",
                },
            )
        events = load_raw_events(client.session["anonymous_session_id"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual([event["eventType"] for event in events], ["error"])
        self.assertEqual(events[0]["operation"], "voice_transcription")
        self.assertNotIn("raw-audio", json.dumps(events))
