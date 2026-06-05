"""Optional LLM provider implementations for textual interaction."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from .providers import LlmProvider


class LlmProviderUnavailableError(RuntimeError):
    """Raised when an external LLM provider cannot be used."""


@dataclass(frozen=True)
class OpenAiResponsesLlmProvider:
    api_key: str
    model: str = "gpt-5-mini"
    base_url: str = "https://api.openai.com/v1"

    def complete(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "input": prompt,
        }
        req = request.Request(
            f"{self.base_url.rstrip('/')}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=20) as response:
                body: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            raise LlmProviderUnavailableError("OpenAI provider not reachable.") from exc

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


def build_optional_llm_provider() -> LlmProvider | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    return OpenAiResponsesLlmProvider(
        api_key=api_key,
        model=os.getenv("OPENAI_MODEL", "gpt-5-mini").strip() or "gpt-5-mini",
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        or "https://api.openai.com/v1",
    )
