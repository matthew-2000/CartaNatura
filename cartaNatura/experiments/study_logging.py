"""Persistent study logging for controlled experimental sessions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from django.conf import settings

from cartaNatura.experiments.logging import (
    ALLOWED_CHANNELS,
    ALLOWED_EVENT_TYPES,
    ALLOWED_INTERACTION_MODES,
    summarize_experiment_events,
)

ALLOWED_CONDITIONS = {"webgis", "conversational"}
STUDY_CONTEXT_SESSION_KEY = "study_context"
STUDY_LOG_DIRNAME = "study-logs"
_SAFE_ID_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")
_BLOCKED_DETAIL_KEYS = {
    "email",
    "firstName",
    "ip",
    "ipAddress",
    "lastName",
    "name",
    "userAgent",
}


@dataclass(frozen=True)
class StudySessionContext:
    participantId: str
    studySessionId: str
    condition: str
    taskId: str | None


def create_study_session(
    *,
    participant_id: str,
    condition: str,
    task_id: str | None = None,
    now: datetime | None = None,
    log_root: Path | None = None,
) -> StudySessionContext:
    safe_participant_id = sanitize_identifier(participant_id, prefix="participant")
    safe_condition = _coerce_choice(condition, ALLOWED_CONDITIONS, "webgis")
    safe_task_id = sanitize_identifier(task_id, prefix="task") if task_id else None
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%d_%H%M%S")
    study_session_id = f"session_{timestamp}_{safe_condition}"
    context = StudySessionContext(
        participantId=safe_participant_id,
        studySessionId=study_session_id,
        condition=safe_condition,
        taskId=safe_task_id,
    )
    session_dir = get_study_session_dir(context, log_root=log_root)
    session_dir.mkdir(parents=True, exist_ok=True)
    _write_summary(context, [], log_root=log_root)
    return context


def record_study_event(
    context: StudySessionContext | dict[str, Any],
    *,
    event_type: str,
    channel: str = "system",
    operation: str | None = None,
    interaction_mode: str | None = None,
    duration_ms: int | None = None,
    step_count: int | None = None,
    status: str | None = None,
    error: str | None = None,
    intent: str | None = None,
    user_text: str | None = None,
    user_transcript: str | None = None,
    assistant_response: str | None = None,
    task_id: str | None = None,
    task_run_id: str | None = None,
    condition: str | None = None,
    event_id: str | None = None,
    timestamp: str | None = None,
    details: dict[str, Any] | None = None,
    log_root: Path | None = None,
) -> dict[str, Any]:
    study_context = coerce_study_context(context)
    event_condition = _coerce_choice(
        str(condition or study_context.condition),
        ALLOWED_CONDITIONS,
        study_context.condition,
    )
    event = {
        "eventId": event_id or f"event_{uuid4().hex[:12]}",
        "timestamp": timestamp or datetime.now(UTC).isoformat(),
        "participantId": study_context.participantId,
        "studySessionId": study_context.studySessionId,
        "condition": event_condition,
        "taskId": sanitize_identifier(task_id, prefix="task") if task_id else study_context.taskId,
        "taskRunId": sanitize_identifier(task_run_id, prefix="taskrun") if task_run_id else None,
        "eventType": _coerce_choice(event_type, ALLOWED_EVENT_TYPES, "error"),
        "channel": _coerce_choice(channel, ALLOWED_CHANNELS, "system"),
        "interactionMode": _coerce_optional_choice(
            interaction_mode,
            ALLOWED_INTERACTION_MODES,
        ),
        "operation": _safe_string(operation, max_length=120),
        "durationMs": _coerce_non_negative_int(duration_ms),
        "stepCount": _coerce_non_negative_int(step_count),
        "status": _safe_string(status, max_length=60),
        "error": _safe_string(error, max_length=500),
        "intent": _safe_string(intent, max_length=120),
        "userText": _safe_string(user_text, max_length=5000),
        "userTranscript": _safe_string(user_transcript, max_length=5000),
        "assistantResponse": _safe_string(assistant_response, max_length=8000),
        "details": sanitize_study_details(details or {}),
    }
    compact_event = {key: value for key, value in event.items() if value not in (None, {}, "")}
    session_dir = get_study_session_dir(study_context, log_root=log_root)
    session_dir.mkdir(parents=True, exist_ok=True)
    events_path = session_dir / "events.jsonl"
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(compact_event, ensure_ascii=False, sort_keys=True))
        handle.write("\n")
    _write_summary(study_context, load_study_events(study_context, log_root=log_root), log_root=log_root)
    return compact_event


def export_study_session(
    context: StudySessionContext | dict[str, Any],
    *,
    log_root: Path | None = None,
) -> dict[str, Any]:
    study_context = coerce_study_context(context)
    events = load_study_events(study_context, log_root=log_root)
    return {
        "schema": "carta-natura-study-log",
        "participantId": study_context.participantId,
        "studySessionId": study_context.studySessionId,
        "condition": study_context.condition,
        "taskId": study_context.taskId,
        "eventCount": len(events),
        "summary": build_study_summary(study_context, events),
        "events": events,
    }


def export_study_events_jsonl(
    context: StudySessionContext | dict[str, Any],
    *,
    log_root: Path | None = None,
) -> str:
    study_context = coerce_study_context(context)
    events_path = get_study_session_dir(study_context, log_root=log_root) / "events.jsonl"
    if not events_path.exists():
        return ""
    return events_path.read_text(encoding="utf-8")


def load_study_events(
    context: StudySessionContext | dict[str, Any],
    *,
    log_root: Path | None = None,
) -> list[dict[str, Any]]:
    study_context = coerce_study_context(context)
    events_path = get_study_session_dir(study_context, log_root=log_root) / "events.jsonl"
    if not events_path.exists():
        return []
    events: list[dict[str, Any]] = []
    with events_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
    return events


def build_study_summary(
    context: StudySessionContext | dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    study_context = coerce_study_context(context)
    summary = summarize_experiment_events(events)
    summary.update(
        {
            "participantId": study_context.participantId,
            "studySessionId": study_context.studySessionId,
            "condition": study_context.condition,
            "taskId": study_context.taskId,
            "eventCount": len(events),
            "startedAt": events[0].get("timestamp") if events else None,
            "completedAt": events[-1].get("timestamp") if events else None,
        }
    )
    return summary


def coerce_study_context(context: StudySessionContext | dict[str, Any]) -> StudySessionContext:
    if isinstance(context, StudySessionContext):
        return context
    return StudySessionContext(
        participantId=sanitize_identifier(context.get("participantId"), prefix="participant"),
        studySessionId=sanitize_identifier(context.get("studySessionId"), prefix="session"),
        condition=_coerce_choice(str(context.get("condition") or ""), ALLOWED_CONDITIONS, "webgis"),
        taskId=sanitize_identifier(context.get("taskId"), prefix="task")
        if context.get("taskId")
        else None,
    )


def sanitize_identifier(value: Any, *, prefix: str) -> str:
    normalized = _SAFE_ID_PATTERN.sub("_", str(value or "").strip())[:80].strip("_-")
    if not normalized:
        return f"{prefix}_{uuid4().hex[:8]}"
    return normalized


def sanitize_study_details(details: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        safe_key = _safe_string(key, max_length=80)
        if not safe_key or safe_key in _BLOCKED_DETAIL_KEYS:
            continue
        safe_value = _safe_detail_value(value)
        if safe_value is not None:
            sanitized[safe_key] = safe_value
    return sanitized


def get_study_log_root(log_root: Path | None = None) -> Path:
    if log_root is not None:
        return Path(log_root)
    configured_root = getattr(settings, "STUDY_LOG_ROOT", None)
    if configured_root:
        return Path(configured_root)
    return Path(settings.BASE_DIR) / "var" / STUDY_LOG_DIRNAME


def get_study_session_dir(
    context: StudySessionContext | dict[str, Any],
    *,
    log_root: Path | None = None,
) -> Path:
    study_context = coerce_study_context(context)
    return get_study_log_root(log_root) / study_context.participantId / study_context.studySessionId


def _write_summary(
    context: StudySessionContext,
    events: list[dict[str, Any]],
    *,
    log_root: Path | None = None,
) -> None:
    summary_path = get_study_session_dir(context, log_root=log_root) / "summary.json"
    summary_path.write_text(
        json.dumps(build_study_summary(context, events), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _safe_detail_value(value: Any) -> int | float | bool | str | list[Any] | dict[str, Any] | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        return _safe_string(value, max_length=500)
    if isinstance(value, list):
        safe_items = [_safe_detail_value(item) for item in value[:50]]
        return [item for item in safe_items if item is not None]
    if isinstance(value, dict):
        return sanitize_study_details(value)
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
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
