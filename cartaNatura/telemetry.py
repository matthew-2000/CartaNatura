"""Append-only, privacy-minimized runtime telemetry.

The JSONL event stream is the only authoritative telemetry store.  This module
deliberately computes no study metrics and contains no participant/task model.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from django.conf import settings

SCHEMA_VERSION = 1
ALLOWED_EVENT_TYPES = {
    "interaction_started",
    "interaction_completed",
    "interaction_failed",
    "voice_transcribed",
    "tool_started",
    "tool_completed",
    "tool_failed",
    "tool_recovered",
    "gui_action",
    "analysis_completed",
    "economic_evaluation",
    "comparison_completed",
    "report_prepared",
    "pdf_generated",
    "error",
}
ALLOWED_INTERACTION_MODES = {"gui", "text", "voice"}
FRONTEND_EVENT_TYPES = {
    "gui_action",
    "economic_evaluation",
    "report_prepared",
    "pdf_generated",
    "error",
}

_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]+")
_DATA_KEYS = {
    "action",
    "analysisIds",
    "categoryCount",
    "controlId",
    "controlLabel",
    "drawnFeatureCount",
    "hasSupportedVegetation",
    "intersectedMunicipalities",
    "intersectedMunicipalityCount",
    "municipalities",
    "needsClarification",
    "priceEurPerTon",
    "providerMode",
    "providerModel",
    "reportFormat",
    "scenarioKey",
    "selectedMunicipalityCount",
    "selectionKind",
    "summary",
    "totalCo2",
    "totalHectares",
    "totalValueEur",
    "toolArguments",
    "toolResult",
}


def new_interaction_id() -> str:
    return f"interaction_{uuid4().hex}"


def new_anonymous_session_id() -> str:
    return f"session_{uuid4().hex}"


def record_raw_event(
    anonymous_session_id: str,
    *,
    event_type: str,
    interaction_mode: str,
    interaction_id: str | None = None,
    operation: str | None = None,
    duration_ms: int | float | None = None,
    analysis_id: str | None = None,
    user_text: str | None = None,
    transcript: str | None = None,
    assistant_response: str | None = None,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    data: Mapping[str, Any] | None = None,
    log_root: Path | None = None,
) -> dict[str, Any]:
    """Validate and append one self-contained event using an OS file lock."""
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"Unsupported telemetry event type: {event_type}")
    if interaction_mode not in ALLOWED_INTERACTION_MODES:
        raise ValueError(f"Unsupported interaction mode: {interaction_mode}")

    session_id = _safe_identifier(anonymous_session_id, "session")
    event: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "eventId": f"event_{uuid4().hex}",
        "timestamp": datetime.now(UTC).isoformat(),
        "anonymousSessionId": session_id,
        "interactionMode": interaction_mode,
        "eventType": event_type,
    }
    _put(
        event,
        "interactionId",
        _safe_identifier(interaction_id, "interaction") if interaction_id else None,
    )
    _put(event, "operation", _safe_text(operation, 100))
    _put(event, "durationMs", _duration(duration_ms))
    _put(event, "analysisId", _safe_identifier(analysis_id, "analysis") if analysis_id else None)
    _put(event, "userText", _safe_text(user_text, 5000))
    _put(event, "transcript", _safe_text(transcript, 5000))
    _put(event, "assistantResponse", _safe_text(assistant_response, 8000))
    if tool_name:
        event["tool"] = {
            "name": _safe_text(tool_name, 100),
            **({"callId": _safe_identifier(tool_call_id, "toolcall")} if tool_call_id else {}),
        }
    if error_type or error_message:
        event["error"] = {
            "type": _safe_text(error_type or "application_error", 100),
            "message": _safe_text(error_message, 1000),
        }
    safe_data = _sanitize_data(data or {})
    if safe_data:
        event["data"] = safe_data

    path = raw_log_path(session_id, log_root=log_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        remaining = memoryview(line)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("Incomplete telemetry write")
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    return event


def raw_log_path(anonymous_session_id: str, *, log_root: Path | None = None) -> Path:
    root = Path(
        log_root
        or getattr(settings, "RAW_EVENT_LOG_ROOT", settings.BASE_DIR / "var" / "raw-events")
    )
    return root / f"{_safe_identifier(anonymous_session_id, 'session')}.jsonl"


def load_raw_events(anonymous_session_id: str, *, log_root: Path | None = None) -> list[dict[str, Any]]:
    path = raw_log_path(anonymous_session_id, log_root=log_root)
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def _sanitize_data(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: safe
        for key, value in data.items()
        if key in _DATA_KEYS and (safe := _safe_value(value, depth=0)) is not None
    }


def _safe_value(value: Any, *, depth: int) -> Any:
    if depth > 4:
        return None
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return _safe_text(value, 500)
    if isinstance(value, list):
        return [_safe_value(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, Mapping):
        return {
            str(key)[:100]: safe
            for key, item in list(value.items())[:100]
            if (safe := _safe_value(item, depth=depth + 1)) is not None
        }
    return None


def _safe_identifier(value: Any, prefix: str) -> str:
    normalized = _SAFE_ID.sub("_", str(value or "").strip())[:160].strip("_")
    return normalized or f"{prefix}_{uuid4().hex}"


def _safe_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_length] if text else None


def _duration(value: int | float | None) -> int | None:
    if value is None:
        return None
    try:
        return max(0, round(float(value)))
    except (TypeError, ValueError):
        return None


def _put(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        target[key] = value
