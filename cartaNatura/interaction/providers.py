"""Provider interfaces for future AI and voice integrations."""

from __future__ import annotations

from typing import Protocol


class LlmProvider(Protocol):
    def complete(self, prompt: str) -> str:
        """Generate text from a prompt."""


class SpeechToTextProvider(Protocol):
    def transcribe(self, audio_reference: str) -> str:
        """Transcribe audio into text."""


class TextToSpeechProvider(Protocol):
    def synthesize(self, text: str) -> bytes:
        """Generate audio from text."""
