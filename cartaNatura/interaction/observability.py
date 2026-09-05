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
    interaction_id: str | None = None,
    interaction_mode: str | None = None,
    tool_call_id: str | None = None,
    arguments: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    domain_results: dict[str, Any] | None = None,
) -> None:
    log = logger.warning if status == "error" else logger.info
    log(
        "assistant.tool.%s session=%s tool=%s duration_ms=%s has_analysis=%s error=%s",
        status,
        session_id,
        tool_name,
        duration_ms,
        has_analysis,
        error,
    )
    if not interaction_id:
        return
    try:
        from cartaNatura.telemetry import record_raw_event

        mode = interaction_mode if interaction_mode in {"text", "voice"} else "text"
        event_type = {
            "started": "tool_started",
            "ok": "tool_completed",
            "recovered": "tool_recovered",
        }.get(status, "tool_failed")
        record_raw_event(
            session_id,
            event_type=event_type,
            interaction_mode=mode,
            interaction_id=interaction_id,
            operation=tool_name,
            duration_ms=duration_ms if status != "started" else None,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            error_type="tool_error" if error else None,
            error_message=error,
            data={"toolArguments": arguments, "toolResult": result},
        )
        if status == "ok" and domain_results:
            analysis = domain_results.get("analysis")
            if isinstance(analysis, dict) and isinstance(analysis.get("summary"), dict):
                record_raw_event(
                    session_id,
                    event_type="analysis_completed",
                    interaction_mode=mode,
                    interaction_id=interaction_id,
                    operation=tool_name,
                    analysis_id=analysis.get("analysisId"),
                    data={
                        "summary": analysis["summary"],
                        "intersectedMunicipalities": analysis.get(
                            "intersectedMunicipalities", []
                        ),
                    },
                )
            economic = domain_results.get("economic")
            if isinstance(economic, dict):
                record_raw_event(
                    session_id,
                    event_type="economic_evaluation",
                    interaction_mode=mode,
                    interaction_id=interaction_id,
                    operation=tool_name,
                    analysis_id=economic.get("analysisId"),
                    data=economic,
                )
            comparison = domain_results.get("comparison")
            if isinstance(comparison, dict):
                analysis_ids = comparison.get("analysisIds")
                if not isinstance(analysis_ids, list):
                    analyses = comparison.get("analyses")
                    analysis_ids = [
                        item.get("id")
                        for item in analyses
                        if isinstance(item, dict) and item.get("id")
                    ] if isinstance(analyses, list) else []
                record_raw_event(
                    session_id,
                    event_type="comparison_completed",
                    interaction_mode=mode,
                    interaction_id=interaction_id,
                    operation=tool_name,
                    data={"analysisIds": analysis_ids},
                )
            report = domain_results.get("report")
            if isinstance(report, dict):
                record_raw_event(
                    session_id,
                    event_type="report_prepared",
                    interaction_mode=mode,
                    interaction_id=interaction_id,
                    operation=tool_name,
                    analysis_id=report.get("analysisId"),
                    data={"reportFormat": report.get("format", "application")},
                )
    except Exception:
        logger.exception("assistant.tool.telemetry_failed session=%s tool=%s", session_id, tool_name)


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
