"""Provider interfaces for future AI and voice integrations."""

from __future__ import annotations

from typing import Any, Protocol


class LlmProvider(Protocol):
    provider_name: str
    model: str

    def complete(self, prompt: str) -> str:
        """Generate text from a prompt."""

    def create_response(self, **payload: Any) -> dict[str, Any]:
        """Generate a normalized assistant response."""

    def stream_response(self, **payload: Any):
        """Stream a normalized assistant response."""


class SpeechToTextProvider(Protocol):
    def transcribe(self, audio_reference: str) -> str:
        """Transcribe audio into text."""


class TextToSpeechProvider(Protocol):
    def synthesize(self, text: str) -> bytes:
        """Generate audio from text."""
