"""Session-scoped experimental event logging.

The log stores operational metadata only. It avoids free-text prompts,
transcripts, names, IP addresses and browser identifiers.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, MutableMapping
from uuid import uuid4

EXPERIMENT_LOG_SESSION_KEY = "experiment_events"
logger = logging.getLogger(__name__)

ALLOWED_EVENT_TYPES = {
    "session_started",
    "task_started",
    "task_completed",
    "selection_changed",
    "analysis_started",
    "analysis_completed",
    "valuation_completed",
    "report_generated",
    "interaction_started",
    "interaction_completed",
    "voice_started",
    "voice_transcribed",
    "reset_completed",
    "error",
    "unknown_request",
}

ALLOWED_CHANNELS = {"web_map", "web_chat", "voice", "system"}
ALLOWED_INTERACTION_MODES = {"map", "text", "voice", "system"}


def record_experiment_event(
    session: MutableMapping[str, object],
    *,
    event_type: str,
    channel: str = "system",
    operation: str | None = None,
    interaction_mode: str | None = None,
    duration_ms: int | None = None,
    step_count: int | None = None,
    task_id: str | None = None,
    status: str | None = None,
    error: str | None = None,
    intent: str | None = None,
    user_text: str | None = None,
    user_transcript: str | None = None,
    assistant_response: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_details = details or {}
    event = {
        "eventId": f"event_{uuid4().hex[:12]}",
        "eventType": _coerce_choice(event_type, ALLOWED_EVENT_TYPES, "error"),
        "timestamp": datetime.now(UTC).isoformat(),
        "channel": _coerce_choice(channel, ALLOWED_CHANNELS, "system"),
        "operation": _safe_string(operation, max_length=80),
        "interactionMode": _coerce_optional_choice(
            interaction_mode,
            ALLOWED_INTERACTION_MODES,
        ),
        "durationMs": _coerce_non_negative_int(duration_ms),
        "stepCount": _coerce_non_negative_int(step_count),
        "taskId": _safe_string(task_id, max_length=80),
        "status": _safe_string(status, max_length=40),
        "error": _safe_string(error, max_length=160),
        "details": _sanitize_details(raw_details),
    }
    compact_event = {key: value for key, value in event.items() if value not in (None, {}, "")}
    events = _load_events(session)
    events.append(compact_event)
    session[EXPERIMENT_LOG_SESSION_KEY] = events[-500:]
    if hasattr(session, "modified"):
        session.modified = True
    _record_persistent_study_event(
        session,
        event_type=event_type,
        channel=channel,
        operation=operation,
        interaction_mode=interaction_mode,
        duration_ms=duration_ms,
        step_count=step_count,
        status=status,
        error=error,
        intent=intent,
        user_text=user_text,
        user_transcript=user_transcript,
        assistant_response=assistant_response,
        details=raw_details,
    )
    return compact_event


def export_experiment_log(session: MutableMapping[str, object]) -> dict[str, Any]:
    events = _load_events(session)
    return {
        "schema": "carta-natura-experiment-log",
        "eventCount": len(events),
        "summary": summarize_experiment_events(events),
        "events": events,
    }


def clear_experiment_log(session: MutableMapping[str, object]) -> None:
    session.pop(EXPERIMENT_LOG_SESSION_KEY, None)
    if hasattr(session, "modified"):
        session.modified = True


def summarize_experiment_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    completed_tasks = [event for event in events if event.get("eventType") == "task_completed"]
    duration_values = [
        int(event["durationMs"])
        for event in completed_tasks
        if isinstance(event.get("durationMs"), int)
    ]
    completed_operations = [
        event.get("operation")
        for event in events
        if event.get("eventType")
        in {"analysis_completed", "valuation_completed", "report_generated", "interaction_completed"}
        and event.get("operation")
    ]
    return {
        "taskCompletionCount": len(completed_tasks),
        "taskCompletionDurationMs": duration_values,
        "interactionCount": _count_events(events, "interaction_started"),
        "operationalStepCount": sum(
            int(event.get("stepCount") or 0)
            for event in events
            if isinstance(event.get("stepCount") or 0, int)
        ),
        "errorCount": _count_events(events, "error"),
        "unknownRequestCount": _count_events(events, "unknown_request"),
        "textInteractionCount": _count_interaction_mode(events, "text"),
        "voiceInteractionCount": _count_interaction_mode(events, "voice"),
        "completedOperations": completed_operations,
        "reportGeneratedCount": _count_events(events, "report_generated"),
    }


def _load_events(session: MutableMapping[str, object]) -> list[dict[str, Any]]:
    raw_events = session.get(EXPERIMENT_LOG_SESSION_KEY)
    if not isinstance(raw_events, list):
        return []
    return [event for event in raw_events if isinstance(event, dict)]


def _count_events(events: list[dict[str, Any]], event_type: str) -> int:
    return sum(1 for event in events if event.get("eventType") == event_type)


def _count_interaction_mode(events: list[dict[str, Any]], interaction_mode: str) -> int:
    return sum(1 for event in events if event.get("interactionMode") == interaction_mode)


def _record_persistent_study_event(
    session: MutableMapping[str, object],
    *,
    event_type: str,
    channel: str,
    operation: str | None,
    interaction_mode: str | None,
    duration_ms: int | None,
    step_count: int | None,
    status: str | None,
    error: str | None,
    intent: str | None,
    user_text: str | None,
    user_transcript: str | None,
    assistant_response: str | None,
    details: dict[str, Any],
) -> None:
    try:
        from .study_logging import STUDY_CONTEXT_SESSION_KEY, record_study_event

        context = session.get(STUDY_CONTEXT_SESSION_KEY)
        if not isinstance(context, dict):
            return
        record_study_event(
            context,
            event_type=event_type,
            channel=channel,
            operation=operation,
            interaction_mode=interaction_mode,
            duration_ms=duration_ms,
            step_count=step_count,
            status=status,
            error=error,
            intent=intent,
            user_text=user_text,
            user_transcript=user_transcript,
            assistant_response=assistant_response,
            details=details,
        )
    except Exception:
        logger.exception("Persistent study event not recorded.")


def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "analysisId",
        "selectedMunicipalityCount",
        "drawnFeatureCount",
        "intersectedMunicipalityCount",
        "categoryCount",
        "hasSupportedVegetation",
        "priceEurPerTon",
        "totalCo2",
        "reportFormat",
        "messageLength",
        "transcriptLength",
        "providerMode",
        "needsClarification",
    }
    return {
        key: _safe_detail_value(value)
        for key, value in details.items()
        if key in allowed_keys and _safe_detail_value(value) is not None
    }


def _safe_detail_value(value: Any) -> int | float | bool | str | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        return _safe_string(value, max_length=80)
    return None


def _safe_string(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized[:max_length]


def _coerce_choice(value: str, allowed_values: set[str], fallback: str) -> str:
    normalized = str(value or "").strip()
    return normalized if normalized in allowed_values else fallback


def _coerce_optional_choice(value: str | None, allowed_values: set[str]) -> str | None:
    normalized = str(value or "").strip()
    return normalized if normalized in allowed_values else None


def _coerce_non_negative_int(value: int | None) -> int | None:
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None
