"""Channel-neutral interaction models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class InteractionChannel(StrEnum):
    WEB_MAP = "web_map"
    WEB_CHAT = "web_chat"
    VOICE = "voice"
    CLI = "cli"
    AGENT = "agent"


class InteractionIntent(StrEnum):
    ANALYZE_SELECTION = "analyze_selection"
    ANALYZE_MUNICIPALITIES = "analyze_municipalities"
    EXTRACT_FOREST_INFORMATION = "extract_forest_information"
    ESTIMATE_CO2_SEQUESTRATION = "estimate_co2_sequestration"
    COMPARE_ECONOMIC_SCENARIOS = "compare_economic_scenarios"
    COMPARE_ANALYSES = "compare_analyses"
    EXPLAIN_LAST_ANALYSIS = "explain_last_analysis"
    GENERATE_REPORT = "generate_report"
    GUIDE_WORKFLOW = "guide_workflow"
    RESET_SESSION = "reset_session"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class InteractionInput:
    text: str | None = None
    transcript: str | None = None
    geo_selection: dict[str, Any] | None = None
    audio_reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def primary_text(self) -> str:
        return (self.transcript or self.text or "").strip()

    def has_structured_selection(self) -> bool:
        return isinstance(self.geo_selection, dict)


@dataclass(frozen=True)
class InteractionContext:
    selected_municipalities: tuple[str, ...] = ()
    current_map_extent: dict[str, Any] | None = None
    current_selection_payload: dict[str, Any] | None = None
    previous_result: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InteractionRequest:
    channel: InteractionChannel
    session_id: str
    input: InteractionInput
    context: InteractionContext = field(default_factory=InteractionContext)
    user_id: str | None = None


@dataclass(frozen=True)
class InteractionCommand:
    intent: InteractionIntent
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InteractionMessage:
    role: str
    text: str


@dataclass(frozen=True)
class SessionContext:
    selection_payload: dict[str, Any] | None = None
    last_analysis: dict[str, Any] | None = None
    last_intent: InteractionIntent | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selection_payload": self.selection_payload,
            "last_analysis": self.last_analysis,
            "last_intent": self.last_intent.value if self.last_intent else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SessionContext:
        if not data:
            return cls()

        raw_intent = data.get("last_intent")
        last_intent = InteractionIntent(raw_intent) if raw_intent else None
        return cls(
            selection_payload=data.get("selection_payload"),
            last_analysis=data.get("last_analysis"),
            last_intent=last_intent,
            metadata=data.get("metadata") or {},
        )


@dataclass(frozen=True)
class InteractionResponse:
    messages: tuple[InteractionMessage, ...] = ()
    commands: tuple[InteractionCommand, ...] = ()
    analysis_result: dict[str, Any] | None = None
    economic_result: dict[str, Any] | None = None
    scenario_comparison: dict[str, Any] | None = None
    report_context: dict[str, Any] | None = None
    ui_hints: dict[str, Any] = field(default_factory=dict)
    audio_output_text: str | None = None
    updated_context: SessionContext | None = None
