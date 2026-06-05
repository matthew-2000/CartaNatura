"""Compose assistant-facing text with optional LLM enhancement."""

from __future__ import annotations

import json
import logging

from .assistant_text import AssistantTextResult
from .llm import LlmProviderUnavailableError
from .providers import LlmProvider

logger = logging.getLogger(__name__)


def build_analysis_reply(
    *,
    requested_municipalities: list[str],
    summary: dict[str, object],
    llm_provider: LlmProvider | None = None,
) -> AssistantTextResult:
    fallback = _build_analysis_reply_fallback(
        requested_municipalities=requested_municipalities,
        summary=summary,
    )

    if llm_provider is None:
        return AssistantTextResult(text=fallback, provider_mode="local")

    prompt = (
        "Sei assistente GIS di Carta della Natura. "
        "Rispondi in italiano, max 4 frasi, tono chiaro e operativo. "
        "Descrivi solo risultato dell'analisi senza inventare dati.\n"
        f"Comuni richiesti: {', '.join(requested_municipalities) or 'non specificati'}\n"
        f"Summary JSON: {json.dumps(summary, ensure_ascii=True)}"
    )

    try:
        return AssistantTextResult(
            text=llm_provider.complete(prompt),
            provider_mode="openai",
        )
    except LlmProviderUnavailableError as exc:
        logger.warning("Assistant analysis reply fallback activated: %s", exc)
        return AssistantTextResult(
            text=fallback,
            provider_mode="fallback",
            warning="LLM non raggiungibile, uso sintesi locale.",
        )


def build_explanation_reply(
    *,
    analysis_summary: dict[str, object] | None,
    llm_provider: LlmProvider | None = None,
) -> AssistantTextResult:
    if not analysis_summary:
        return AssistantTextResult(
            text=(
                "Non ho ancora un'analisi recente da spiegare. "
                "Chiedimi prima di analizzare uno o piu comuni."
            ),
            provider_mode="local",
        )

    fallback = _build_explanation_reply_fallback(analysis_summary)
    if llm_provider is None:
        return AssistantTextResult(text=fallback, provider_mode="local")

    prompt = (
        "Sei assistente GIS di Carta della Natura. "
        "Spiega in italiano, max 4 frasi, ultimo risultato analitico usando solo dati forniti.\n"
        f"Summary JSON: {json.dumps(analysis_summary, ensure_ascii=True)}"
    )

    try:
        return AssistantTextResult(
            text=llm_provider.complete(prompt),
            provider_mode="openai",
        )
    except LlmProviderUnavailableError as exc:
        logger.warning("Assistant explanation reply fallback activated: %s", exc)
        return AssistantTextResult(
            text=fallback,
            provider_mode="fallback",
            warning="LLM non raggiungibile, uso sintesi locale.",
        )


def _build_analysis_reply_fallback(
    *,
    requested_municipalities: list[str],
    summary: dict[str, object],
) -> str:
    municipality_text = ", ".join(requested_municipalities) or "comuni richiesti"
    if not summary.get("hasSupportedVegetation"):
        return (
            f"Analisi completata per {municipality_text}. "
            "Nell'area estratta non risultano categorie forestali supportate dall'analisi corrente."
        )

    top_category = summary.get("topCategory") or {}
    total_hectares = int(float(summary.get("totalHectares") or 0))
    total_co2 = int(float(summary.get("totalCo2") or 0))
    category_count = len(summary.get("items") or [])
    top_label = top_category.get("label") or "-"
    return (
        f"Analisi completata per {municipality_text}. "
        f"Ho trovato {category_count} categorie su circa {total_hectares} ettari, "
        f"con assorbimento stimato di {total_co2} tonnellate di CO2 annue. "
        f"Categoria prevalente: {top_label}."
    )


def _build_explanation_reply_fallback(analysis_summary: dict[str, object]) -> str:
    if not analysis_summary.get("hasSupportedVegetation"):
        return "Ultima analisi senza categorie forestali supportate. Puoi provare un altro comune o una selezione piu ampia."

    top_category = analysis_summary.get("topCategory") or {}
    total_hectares = int(float(analysis_summary.get("totalHectares") or 0))
    total_co2 = int(float(analysis_summary.get("totalCo2") or 0))
    top_label = top_category.get("label") or "-"
    return (
        f"Ultimo risultato: circa {total_hectares} ettari di copertura analizzata, "
        f"{total_co2} tonnellate di CO2 annue stimate e categoria prevalente {top_label}. "
        "Se vuoi posso analizzare altri comuni o confrontare una nuova selezione."
    )
