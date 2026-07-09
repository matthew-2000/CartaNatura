"""Configurable LLM provider implementations for textual interaction."""

from __future__ import annotations

import json
import logging
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterator
from uuid import uuid4

from django.conf import settings
from openai import OpenAI
from openai import OpenAIError

from .providers import LlmProvider

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5-mini"
SUPPORTED_LLM_PROVIDERS = {"openai", "ollama"}


class LlmProviderUnavailableError(RuntimeError):
    """Raised when an external LLM provider cannot be used."""


class LlmProviderConfigurationError(LlmProviderUnavailableError):
    """Raised when the selected LLM provider is not configured correctly."""


@dataclass(frozen=True)
class LlmProviderConfig:
    provider: str
    model: str
    base_url: str
    api_key: str = ""
    timeout_seconds: float = 60.0

    @property
    def is_configured(self) -> bool:
        if self.provider == "openai":
            return bool(self.api_key and self.model and self.base_url)
        if self.provider == "ollama":
            return bool(self.model and self.base_url)
        return False


@dataclass(frozen=True)
class OpenAiResponsesLlmProvider:
    api_key: str
    model: str = DEFAULT_OPENAI_MODEL
    base_url: str = DEFAULT_OPENAI_BASE_URL

    provider_name = "openai"
    runtime_name = "responses_api"

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

        raise LlmProviderUnavailableError("Provider OpenAI: risposta testuale vuota.")

    def create_response(self, **payload: Any) -> dict[str, Any]:
        try:
            response = self._client.responses.create(
                model=self.model,
                **_without_provider_only_payload(payload),
            )
        except OpenAIError as exc:
            logger.warning("OpenAI provider request failed: %s", exc)
            raise LlmProviderUnavailableError("Provider OpenAI non raggiungibile.") from exc

        return response.model_dump(mode="python")

    def stream_response(self, **payload: Any):
        try:
            stream_manager = self._client.responses.stream(
                model=self.model,
                **_without_provider_only_payload(payload),
            )
        except OpenAIError as exc:
            logger.warning("OpenAI provider stream setup failed: %s", exc)
            raise LlmProviderUnavailableError("Provider OpenAI non raggiungibile.") from exc
        return _OpenAiStreamManager(stream_manager)


class _OpenAiStreamManager:
    def __init__(self, stream_manager):
        self._stream_manager = stream_manager

    def __enter__(self):
        try:
            return self._stream_manager.__enter__()
        except OpenAIError as exc:
            logger.warning("OpenAI provider stream failed: %s", exc)
            raise LlmProviderUnavailableError("Provider OpenAI non raggiungibile.") from exc

    def __exit__(self, exc_type, exc, tb):
        return self._stream_manager.__exit__(exc_type, exc, tb)


@dataclass(frozen=True)
class OllamaChatLlmProvider:
    model: str
    base_url: str
    timeout_seconds: float = 60.0

    provider_name = "ollama"
    runtime_name = "ollama_chat"

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        object.__setattr__(self, "_opener", urllib.request.build_opener())

    def complete(self, prompt: str) -> str:
        response = self.create_response(
            instructions="Rispondi in italiano in modo breve e operativo.",
            input=[
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
            tools=[],
        )
        output_text = response.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        raise LlmProviderUnavailableError("Provider Ollama: risposta testuale vuota.")

    def create_response(self, **payload: Any) -> dict[str, Any]:
        body = self._build_chat_payload(payload, stream=False)
        response = self._post_json("/api/chat", body)
        return self._normalize_chat_response(response)

    def stream_response(self, **payload: Any):
        body = self._build_chat_payload(payload, stream=True)
        return _OllamaStreamManager(
            opener=self._opener,
            url=f"{self.base_url}/api/chat",
            payload=body,
            timeout_seconds=self.timeout_seconds,
        )

    def _build_chat_payload(self, payload: dict[str, Any], *, stream: bool) -> dict[str, Any]:
        messages = _build_ollama_messages(payload)
        tools = [_to_ollama_tool(tool) for tool in payload.get("tools", [])]
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": 0},
        }
        if tools:
            body["tools"] = tools

        schema = _extract_json_schema(payload)
        if schema:
            body["format"] = schema
        return body

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LlmProviderUnavailableError(
                f"Provider Ollama ha risposto con HTTP {exc.code}: {detail[:200]}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            raise LlmProviderUnavailableError(
                f"Provider Ollama non raggiungibile all'URL configurato ({self.base_url})."
            ) from exc

        try:
            decoded = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise LlmProviderUnavailableError("Provider Ollama: risposta JSON non valida.") from exc
        if not isinstance(decoded, dict):
            raise LlmProviderUnavailableError("Provider Ollama: risposta non supportata.")
        if decoded.get("error"):
            raise LlmProviderUnavailableError(f"Provider Ollama: {decoded['error']}")
        return decoded

    @staticmethod
    def _normalize_chat_response(response: dict[str, Any]) -> dict[str, Any]:
        message = response.get("message") if isinstance(response.get("message"), dict) else {}
        return _normalize_ollama_message(
            message=message,
            response_id=f"ollama-{uuid4().hex[:12]}",
            usage=_ollama_usage(response),
        )


class _Event:
    def __init__(self, event_type: str, **payload: Any):
        self.type = event_type
        for key, value in payload.items():
            setattr(self, key, value)


class _ResponseRef:
    def __init__(self, response_id: str):
        self.id = response_id


class _OutputItem:
    def __init__(self, item_type: str, **payload: Any):
        self.type = item_type
        for key, value in payload.items():
            setattr(self, key, value)


class _FinalResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        del mode
        return self._payload


class _OllamaStreamManager:
    def __init__(
        self,
        *,
        opener,
        url: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ):
        self._opener = opener
        self._url = url
        self._payload = payload
        self._timeout_seconds = timeout_seconds
        self._response = None
        self._response_id = f"ollama-{uuid4().hex[:12]}"
        self._content_parts: list[str] = []
        self._tool_calls: list[dict[str, Any]] = []
        self._usage: dict[str, int | None] = {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        }

    def __enter__(self):
        request = urllib.request.Request(
            self._url,
            data=json.dumps(self._payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            self._response = self._opener.open(request, timeout=self._timeout_seconds)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LlmProviderUnavailableError(
                f"Provider Ollama ha risposto con HTTP {exc.code}: {detail[:200]}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            raise LlmProviderUnavailableError(
                "Provider Ollama non raggiungibile durante lo streaming."
            ) from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        if self._response is not None:
            self._response.close()
        return False

    def __iter__(self) -> Iterator[_Event]:
        yield _Event("response.created", response=_ResponseRef(self._response_id))
        if self._response is None:
            return
        for raw_line in self._response:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LlmProviderUnavailableError(
                    "Provider Ollama: evento streaming JSON non valido."
                ) from exc
            if chunk.get("error"):
                raise LlmProviderUnavailableError(f"Provider Ollama: {chunk['error']}")

            self._usage = _ollama_usage(chunk)
            message = chunk.get("message") if isinstance(chunk.get("message"), dict) else {}
            content = message.get("content")
            if isinstance(content, str) and content:
                self._content_parts.append(content)
                yield _Event("response.output_text.delta", delta=content)

            for tool_call in _extract_ollama_tool_calls(message):
                if tool_call not in self._tool_calls:
                    self._tool_calls.append(tool_call)
                    yield _Event(
                        "response.output_item.added",
                        item=_OutputItem("function_call", name=tool_call["name"]),
                    )

    def get_final_response(self) -> _FinalResponse:
        if self._tool_calls:
            payload = {
                "id": self._response_id,
                "output": [
                    {
                        "type": "function_call",
                        "call_id": tool_call["call_id"],
                        "name": tool_call["name"],
                        "arguments": tool_call["arguments"],
                    }
                    for tool_call in self._tool_calls
                ],
                "usage": self._usage,
            }
        else:
            payload = {
                "id": self._response_id,
                "output_text": "".join(self._content_parts),
                "output": [],
                "usage": self._usage,
            }
        return _FinalResponse(payload)


def build_optional_llm_provider() -> LlmProvider | None:
    config = load_llm_provider_config()
    if not config.is_configured:
        if config.provider == "openai" and not config.api_key:
            return None
        raise _configuration_error(config)

    if config.provider == "openai":
        return _cached_openai_provider(config.api_key, config.model, config.base_url)
    if config.provider == "ollama":
        return _cached_ollama_provider(config.model, config.base_url, config.timeout_seconds)
    raise _configuration_error(config)


def load_llm_provider_config() -> LlmProviderConfig:
    provider = _env_or_setting("LLM_PROVIDER", "openai").strip().lower()
    provider = _env_or_setting("AI_LLM_PROVIDER", provider).strip().lower()
    generic_model = _env_or_setting("LLM_MODEL", "").strip()
    generic_base_url = _env_or_setting("LLM_BASE_URL", "").strip()
    timeout_seconds = _coerce_float(_env_or_setting("LLM_TIMEOUT_SECONDS", "60"), default=60.0)

    if provider == "openai":
        return LlmProviderConfig(
            provider=provider,
            model=generic_model
            or _env_or_setting("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip()
            or DEFAULT_OPENAI_MODEL,
            base_url=generic_base_url
            or _env_or_setting("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip()
            or DEFAULT_OPENAI_BASE_URL,
            api_key=_env_or_setting("OPENAI_API_KEY", "").strip(),
            timeout_seconds=timeout_seconds,
        )

    if provider == "ollama":
        return LlmProviderConfig(
            provider=provider,
            model=generic_model or _env_or_setting("OLLAMA_MODEL", "").strip(),
            base_url=generic_base_url or _env_or_setting("OLLAMA_BASE_URL", "").strip(),
            timeout_seconds=timeout_seconds,
        )

    return LlmProviderConfig(provider=provider, model=generic_model, base_url=generic_base_url)


def get_llm_provider_status() -> dict[str, Any]:
    config = load_llm_provider_config()
    error = None
    if not config.is_configured:
        error = str(_configuration_error(config))
    return {
        "provider": config.provider,
        "model": config.model,
        "base_url": config.base_url,
        "configured": config.is_configured,
        "error": error,
    }


def require_llm_provider_configured() -> LlmProviderConfig:
    config = load_llm_provider_config()
    if not config.is_configured:
        raise _configuration_error(config)
    return config


def _configuration_error(config: LlmProviderConfig) -> LlmProviderConfigurationError:
    if config.provider not in SUPPORTED_LLM_PROVIDERS:
        return LlmProviderConfigurationError(
            f"Provider LLM non supportato: {config.provider!r}. Usa 'openai' oppure 'ollama'."
        )
    if config.provider == "openai" and not config.api_key:
        return LlmProviderConfigurationError(
            "Assistente AI non configurato. Imposta OPENAI_API_KEY oppure seleziona LLM_PROVIDER=ollama."
        )
    if config.provider == "ollama":
        missing = []
        if not config.base_url:
            missing.append("OLLAMA_BASE_URL o LLM_BASE_URL")
        if not config.model:
            missing.append("OLLAMA_MODEL o LLM_MODEL")
        return LlmProviderConfigurationError(
            "Provider Ollama non configurato. Imposta " + " e ".join(missing) + "."
        )
    return LlmProviderConfigurationError("Configurazione LLM non valida.")


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


@lru_cache(maxsize=4)
def _cached_ollama_provider(
    model: str,
    base_url: str,
    timeout_seconds: float,
) -> OllamaChatLlmProvider:
    return OllamaChatLlmProvider(
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def _env_or_setting(name: str, default: str) -> str:
    if name in os.environ:
        return os.environ[name]
    if hasattr(settings, name):
        return str(getattr(settings, name))
    return default


def _coerce_float(value: str, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _without_provider_only_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"conversation_messages", "provider_metadata"}
    }


def _build_ollama_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    instructions = payload.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions.strip()})

    for history_item in payload.get("conversation_messages", []) or []:
        if isinstance(history_item, dict):
            role = str(history_item.get("role") or "").strip()
            content = str(history_item.get("content") or "").strip()
            if role in {"user", "assistant", "tool"} and content:
                messages.append({"role": role, "content": content})

    for input_item in payload.get("input", []) or []:
        if not isinstance(input_item, dict):
            continue
        if input_item.get("type") == "function_call_output":
            messages.append(
                {
                    "role": "tool",
                    "content": str(input_item.get("output") or ""),
                    "tool_call_id": str(input_item.get("call_id") or ""),
                }
            )
            continue

        role = str(input_item.get("role") or "user")
        content = _input_content_to_text(input_item.get("content"))
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    return messages


def _input_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n".join(parts)


def _to_ollama_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.get("name"),
            "description": tool.get("description", ""),
            "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
        },
    }


def _extract_json_schema(payload: dict[str, Any]) -> dict[str, Any] | None:
    text_config = payload.get("text") if isinstance(payload.get("text"), dict) else {}
    format_config = text_config.get("format") if isinstance(text_config.get("format"), dict) else {}
    schema = format_config.get("schema")
    return schema if isinstance(schema, dict) else None


def _normalize_ollama_message(
    *,
    message: dict[str, Any],
    response_id: str,
    usage: dict[str, int | None],
) -> dict[str, Any]:
    tool_calls = _extract_ollama_tool_calls(message)
    if tool_calls:
        return {
            "id": response_id,
            "output": [
                {
                    "type": "function_call",
                    "call_id": tool_call["call_id"],
                    "name": tool_call["name"],
                    "arguments": tool_call["arguments"],
                }
                for tool_call in tool_calls
            ],
            "usage": usage,
        }

    content = message.get("content")
    return {
        "id": response_id,
        "output_text": content if isinstance(content, str) else "",
        "output": [],
        "usage": usage,
    }


def _extract_ollama_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    raw_calls = message.get("tool_calls")
    if not isinstance(raw_calls, list):
        return []

    calls: list[dict[str, Any]] = []
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict):
            continue
        function = raw_call.get("function") if isinstance(raw_call.get("function"), dict) else {}
        name = str(function.get("name") or raw_call.get("name") or "").strip()
        if not name:
            continue
        arguments = function.get("arguments", raw_call.get("arguments", {}))
        calls.append(
            {
                "call_id": str(raw_call.get("id") or f"call_{uuid4().hex[:12]}"),
                "name": name,
                "arguments": arguments if isinstance(arguments, dict) else str(arguments or "{}"),
            }
        )
    return calls


def _ollama_usage(response: dict[str, Any]) -> dict[str, int | None]:
    input_tokens = _coerce_int(response.get("prompt_eval_count"))
    output_tokens = _coerce_int(response.get("eval_count"))
    total_tokens = None
    if input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
