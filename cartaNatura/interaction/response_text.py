"""Compose assistant-facing text with mandatory LLM generation."""

from __future__ import annotations

import json
from .assistant_text import AssistantTextResult
from .providers import LlmProvider


def _provider_mode(llm_provider: LlmProvider) -> str:
    return str(getattr(llm_provider, "provider_name", "openai"))


def build_analysis_reply(
    *,
    requested_municipalities: list[str],
    summary: dict[str, object],
    llm_provider: LlmProvider,
) -> AssistantTextResult:
    prompt = (
        "Sei assistente GIS di Carta della Natura. "
        "Rispondi in italiano, max 4 frasi, tono chiaro e operativo. "
        "Formatta i numeri in stile italiano e arrotonda a massimo 2 decimali. "
        "Descrivi solo il risultato dell'analisi senza inventare dati.\n"
        f"Comuni richiesti: {', '.join(requested_municipalities) or 'non specificati'}\n"
        f"Summary JSON: {json.dumps(summary, ensure_ascii=True)}"
    )

    return AssistantTextResult(
        text=llm_provider.complete(prompt),
        provider_mode=_provider_mode(llm_provider),
    )


def build_explanation_reply(
    *,
    analysis_summary: dict[str, object] | None,
    llm_provider: LlmProvider,
) -> AssistantTextResult:
    if not analysis_summary:
        raise ValueError(
            "Non ho ancora un'analisi recente da spiegare. "
            "Avvia prima un'analisi su uno o più comuni."
        )

    prompt = (
        "Sei assistente GIS di Carta della Natura. "
        "Spiega in italiano, max 4 frasi, l'ultimo report usando solo i dati forniti. "
        "Formatta i numeri in stile italiano e arrotonda a massimo 2 decimali.\n"
        f"Summary JSON: {json.dumps(analysis_summary, ensure_ascii=True)}"
    )

    return AssistantTextResult(
        text=llm_provider.complete(prompt),
        provider_mode=_provider_mode(llm_provider),
    )


def build_comparison_reply(
    *,
    comparison_summary: dict[str, object],
    llm_provider: LlmProvider,
) -> AssistantTextResult:
    prompt = (
        "Sei assistente GIS di Carta della Natura. "
        "Confronta in italiano, max 4 frasi, due analisi usando solo dati forniti. "
        "Evidenzia differenze di superficie, CO2 e categoria dominante senza inventare dati. "
        "Formatta i numeri in stile italiano e arrotonda a massimo 2 decimali.\n"
        f"Comparison JSON: {json.dumps(comparison_summary, ensure_ascii=True)}"
    )

    return AssistantTextResult(
        text=llm_provider.complete(prompt),
        provider_mode=_provider_mode(llm_provider),
    )
