"""Optional LLM provider implementations for textual interaction."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai import OpenAI
from openai import OpenAIError

from .providers import LlmProvider

logger = logging.getLogger(__name__)


class LlmProviderUnavailableError(RuntimeError):
    """Raised when an external LLM provider cannot be used."""


@dataclass(frozen=True)
class OpenAiResponsesLlmProvider:
    api_key: str
    model: str = "gpt-5-mini"
    base_url: str = "https://api.openai.com/v1"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_client",
            OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            ),
        )

    def complete(self, prompt: str) -> str:
        body = self.create_response(input=prompt)
        output_text = body.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        for item in body.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()

        raise LlmProviderUnavailableError("OpenAI provider returned empty text output.")

    def create_response(self, **payload: Any) -> dict[str, Any]:
        try:
            response = self._client.responses.create(
                model=self.model,
                **payload,
            )
        except OpenAIError as exc:
            logger.warning("OpenAI provider request failed: %s", exc)
            raise LlmProviderUnavailableError("OpenAI provider not reachable.") from exc

        return response.model_dump(mode="python")

    def stream_response(self, **payload: Any):
        return self._client.responses.stream(
            model=self.model,
            **payload,
        )


def build_optional_llm_provider() -> LlmProvider | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip() or "gpt-5-mini"
    base_url = (
        os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        or "https://api.openai.com/v1"
    )
    return _cached_openai_provider(api_key, model, base_url)


@lru_cache(maxsize=4)
def _cached_openai_provider(
    api_key: str,
    model: str,
    base_url: str,
) -> OpenAiResponsesLlmProvider:
    return OpenAiResponsesLlmProvider(
        api_key=api_key,
        model=model,
        base_url=base_url,
    )
