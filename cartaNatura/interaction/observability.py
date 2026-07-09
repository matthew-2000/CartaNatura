"""Small observability helpers for assistant runtime."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("cartaNatura.interaction.observability")


def start_timer() -> float:
    return time.perf_counter()


def elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def summarize_provider_usage(response_body: dict[str, Any]) -> dict[str, int | None]:
    usage = response_body.get("usage")
    if not isinstance(usage, dict):
        return {"input_tokens": None, "output_tokens": None, "total_tokens": None}

    input_tokens = _coerce_int(usage.get("input_tokens") or usage.get("prompt_tokens"))
    output_tokens = _coerce_int(usage.get("output_tokens") or usage.get("completion_tokens"))
    total_tokens = _coerce_int(usage.get("total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def summarize_openai_usage(response_body: dict[str, Any]) -> dict[str, int | None]:
    """Backward-compatible alias for existing tests and callers."""
    return summarize_provider_usage(response_body)


def log_provider_call(
    *,
    provider: str,
    model: str | None,
    session_id: str,
    response_body: dict[str, Any] | None,
    previous_response_id: str | None,
    streaming: bool,
    duration_ms: int,
    status: str,
    error: str | None = None,
) -> None:
    usage = summarize_provider_usage(response_body or {})
    log = logger.warning if status != "ok" else logger.info
    log(
        "assistant.provider.%s provider=%s model=%s session=%s response_id=%s previous_response_id=%s "
        "streaming=%s duration_ms=%s input_tokens=%s output_tokens=%s total_tokens=%s error=%s",
        status,
        provider,
        model,
        session_id,
        (response_body or {}).get("id"),
        previous_response_id,
        streaming,
        duration_ms,
        usage["input_tokens"],
        usage["output_tokens"],
        usage["total_tokens"],
        error,
    )


def log_tool_call(
    *,
    session_id: str,
    tool_name: str,
    duration_ms: int,
    status: str,
    has_analysis: bool = False,
    error: str | None = None,
) -> None:
    log = logger.warning if status != "ok" else logger.info
    log(
        "assistant.tool.%s session=%s tool=%s duration_ms=%s has_analysis=%s error=%s",
        status,
        session_id,
        tool_name,
        duration_ms,
        has_analysis,
        error,
    )


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
