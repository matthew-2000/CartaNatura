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
EXPERIMENT_ACTIVE_TASK_SESSION_KEY = "experiment_active_task"
logger = logging.getLogger(__name__)

ALLOWED_EVENT_TYPES = {
    "session_started",
    "task_started",
    "task_completed",
    "task_failed",
    "task_interrupted",
    "ui_action",
    "chat_message",
    "chat_response",
    "tool_started",
    "tool_completed",
    "tool_failed",
    "selection_changed",
    "analysis_started",
    "analysis_completed",
    "valuation_completed",
    "report_generated",
    "report_opened",
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
ALLOWED_CONDITIONS = {"webgis", "conversational"}


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
    task_run_id: str | None = None,
    condition: str | None = None,
    status: str | None = None,
    error: str | None = None,
    intent: str | None = None,
    user_text: str | None = None,
    user_transcript: str | None = None,
    assistant_response: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    events = _load_events(session)
    active_task = _load_active_task(session)
    safe_task_id = _safe_string(task_id, max_length=80)
    safe_task_run_id = _safe_string(task_run_id, max_length=80)
    safe_condition = _coerce_optional_choice(condition, ALLOWED_CONDITIONS) or _study_condition(
        session
    )

    if event_type == "task_started":
        if active_task:
            if not safe_task_id or active_task.get("taskId") == safe_task_id:
                existing_start = _find_task_event(
                    events,
                    task_run_id=str(active_task.get("taskRunId") or ""),
                    event_types={"task_started"},
                )
                if existing_start is not None:
                    return existing_start
            record_experiment_event(
                session,
                event_type="task_interrupted",
                channel="system",
                operation="study_task",
                interaction_mode="system",
                task_id=str(active_task.get("taskId") or ""),
                task_run_id=str(active_task.get("taskRunId") or ""),
                condition=str(active_task.get("condition") or safe_condition or ""),
                status="interrupted",
                error="superseded_by_new_task",
            )
            events = _load_events(session)
        safe_task_run_id = safe_task_run_id or f"taskrun_{uuid4().hex[:12]}"
    elif active_task and (
        not safe_task_run_id or active_task.get("taskRunId") == safe_task_run_id
    ):
        safe_task_run_id = safe_task_run_id or _safe_string(
            active_task.get("taskRunId"),
            max_length=80,
        )
        safe_task_id = safe_task_id or _safe_string(active_task.get("taskId"), max_length=80)
        safe_condition = safe_condition or _safe_string(active_task.get("condition"), max_length=40)

    terminal_task_types = {"task_completed", "task_failed", "task_interrupted"}
    if event_type in terminal_task_types and safe_task_run_id:
        existing_terminal = _find_task_event(
            events,
            task_run_id=safe_task_run_id,
            event_types=terminal_task_types,
        )
        if existing_terminal is not None:
            return existing_terminal
        started_event = _find_task_event(
            events,
            task_run_id=safe_task_run_id,
            event_types={"task_started"},
        )
        if started_event is not None:
            duration_ms = _duration_between_timestamps(
                str(started_event.get("timestamp") or ""),
                datetime.now(UTC),
            )

    raw_details = details or {}
    timestamp = datetime.now(UTC).isoformat()
    event = {
        "eventId": f"event_{uuid4().hex[:12]}",
        "eventType": _coerce_choice(event_type, ALLOWED_EVENT_TYPES, "error"),
        "timestamp": timestamp,
        "channel": _coerce_choice(channel, ALLOWED_CHANNELS, "system"),
        "condition": safe_condition,
        "operation": _safe_string(operation, max_length=80),
        "interactionMode": _coerce_optional_choice(
            interaction_mode,
            ALLOWED_INTERACTION_MODES,
        ),
        "durationMs": _coerce_non_negative_int(duration_ms),
        "stepCount": _coerce_non_negative_int(step_count),
        "taskId": safe_task_id,
        "taskRunId": safe_task_run_id,
        "status": _safe_string(status, max_length=40),
        "error": _safe_string(error, max_length=160),
        "details": _sanitize_details(raw_details),
    }
    compact_event = {key: value for key, value in event.items() if value not in (None, {}, "")}
    events.append(compact_event)
    session[EXPERIMENT_LOG_SESSION_KEY] = events[-500:]
    if event_type == "task_started":
        session[EXPERIMENT_ACTIVE_TASK_SESSION_KEY] = {
            "taskId": safe_task_id,
            "taskRunId": safe_task_run_id,
            "condition": safe_condition,
            "startedAt": timestamp,
        }
    elif event_type in terminal_task_types and active_task:
        if active_task.get("taskRunId") == safe_task_run_id:
            session.pop(EXPERIMENT_ACTIVE_TASK_SESSION_KEY, None)
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
        task_id=safe_task_id,
        task_run_id=safe_task_run_id,
        condition=safe_condition,
        event_id=str(compact_event["eventId"]),
        timestamp=timestamp,
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
    session.pop(EXPERIMENT_ACTIVE_TASK_SESSION_KEY, None)
    if hasattr(session, "modified"):
        session.modified = True


def summarize_experiment_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    all_completed_tasks = [
        event for event in events if event.get("eventType") == "task_completed"
    ]
    controlled_completed_tasks = [
        event for event in all_completed_tasks if event.get("taskRunId")
    ]
    completed_tasks = controlled_completed_tasks or all_completed_tasks
    legacy_completed_tasks = [
        event for event in all_completed_tasks if not event.get("taskRunId")
    ]
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
        "legacyTaskCompletionCount": len(legacy_completed_tasks),
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
        "uiActionCount": _count_events(events, "ui_action"),
        "chatMessageCount": _count_events(events, "chat_message"),
        "toolCallCount": _count_events(events, "tool_started"),
        "failedTaskCount": _count_events(events, "task_failed"),
        "interruptedTaskCount": _count_events(events, "task_interrupted"),
        "tasks": _summarize_tasks(events),
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


def _load_active_task(session: MutableMapping[str, object]) -> dict[str, Any] | None:
    active_task = session.get(EXPERIMENT_ACTIVE_TASK_SESSION_KEY)
    return active_task if isinstance(active_task, dict) else None


def _study_condition(session: MutableMapping[str, object]) -> str | None:
    context = session.get("study_context")
    if not isinstance(context, dict):
        return None
    return _safe_string(context.get("condition"), max_length=40)


def _find_task_event(
    events: list[dict[str, Any]],
    *,
    task_run_id: str,
    event_types: set[str],
) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in reversed(events)
            if event.get("taskRunId") == task_run_id
            and event.get("eventType") in event_types
        ),
        None,
    )


def _duration_between_timestamps(started_at: str, completed_at: datetime) -> int | None:
    try:
        parsed_start = datetime.fromisoformat(started_at)
    except (TypeError, ValueError):
        return None
    return max(0, round((completed_at - parsed_start).total_seconds() * 1000))


def _summarize_tasks(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for event in events:
        task_run_id = event.get("taskRunId")
        if not task_run_id:
            continue
        task = tasks.setdefault(
            str(task_run_id),
            {
                "taskRunId": task_run_id,
                "taskId": event.get("taskId"),
                "condition": event.get("condition"),
                "startedAt": None,
                "completedAt": None,
                "status": "active",
                "durationMs": None,
                "eventCount": 0,
                "analysisIds": [],
            },
        )
        task["eventCount"] += 1
        analysis_id = (event.get("details") or {}).get("analysisId")
        if analysis_id and analysis_id not in task["analysisIds"]:
            task["analysisIds"].append(analysis_id)
        if event.get("eventType") == "task_started":
            task["startedAt"] = event.get("timestamp")
        elif event.get("eventType") in {"task_completed", "task_failed", "task_interrupted"}:
            task["completedAt"] = event.get("timestamp")
            task["status"] = str(event.get("eventType")).removeprefix("task_")
            task["durationMs"] = event.get("durationMs")
    return list(tasks.values())


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
    task_id: str | None,
    task_run_id: str | None,
    condition: str | None,
    event_id: str,
    timestamp: str,
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
            task_id=task_id,
            task_run_id=task_run_id,
            condition=condition,
            event_id=event_id,
            timestamp=timestamp,
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
        "scenarioKey",
        "totalCo2",
        "totalValueEur",
        "reportFormat",
        "messageLength",
        "transcriptLength",
        "providerMode",
        "needsClarification",
        "toolName",
        "toolCallId",
        "controlId",
        "controlLabel",
        "eventSource",
        "taskOutcome",
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
