"""Voice transcription helpers powered by OpenAI audio models."""

from __future__ import annotations

import logging
import os

from django.core.files.uploadedfile import UploadedFile
from django.conf import settings
from openai import OpenAI, OpenAIError

from .llm import LlmProviderUnavailableError

logger = logging.getLogger(__name__)

MAX_AUDIO_UPLOAD_BYTES = 12 * 1024 * 1024

_AUDIO_SUFFIX_BY_CONTENT_TYPE = {
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "audio/x-m4a": ".m4a",
}


def transcribe_uploaded_audio(audio_file: UploadedFile) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise LlmProviderUnavailableError("OpenAI API key missing.")

    if audio_file.size and audio_file.size > MAX_AUDIO_UPLOAD_BYTES:
        raise ValueError("Audio troppo grande. Registra un messaggio più breve.")

    suffix = _suffix_for_audio(audio_file)
    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        or "https://api.openai.com/v1",
        timeout=_voice_timeout_seconds(),
        max_retries=0,
    )

    try:
        transcription = client.audio.transcriptions.create(
            model=os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-transcribe").strip()
            or "gpt-4o-transcribe",
            file=(
                _audio_upload_filename(audio_file, suffix=suffix),
                _read_uploaded_audio(audio_file),
                str(getattr(audio_file, "content_type", "") or "audio/webm"),
            ),
            response_format="text",
            language="it",
        )
    except OpenAIError as exc:
        logger.warning("OpenAI transcription failed: %s", exc)
        raise LlmProviderUnavailableError("Trascrizione vocale non disponibile.") from exc

    text = _extract_transcription_text(transcription)
    if not text:
        raise ValueError("Audio ricevuto, ma nessun testo riconosciuto.")
    return text


def _suffix_for_audio(audio_file: UploadedFile) -> str:
    content_type = str(getattr(audio_file, "content_type", "") or "").split(";", 1)[0]
    return _AUDIO_SUFFIX_BY_CONTENT_TYPE.get(content_type, ".webm")


def _audio_upload_filename(audio_file: UploadedFile, *, suffix: str) -> str:
    raw_name = str(getattr(audio_file, "name", "") or "").strip()
    if raw_name and "." in raw_name.rsplit("/", 1)[-1]:
        return raw_name.rsplit("/", 1)[-1]
    return f"voice-message{suffix}"


def _read_uploaded_audio(audio_file: UploadedFile) -> bytes:
    audio_file.seek(0)
    return b"".join(audio_file.chunks())


def _extract_transcription_text(transcription) -> str:
    if isinstance(transcription, str):
        return transcription.strip()

    text = getattr(transcription, "text", "")
    if isinstance(text, str):
        return text.strip()

    if isinstance(transcription, dict):
        raw_text = transcription.get("text")
        if isinstance(raw_text, str):
            return raw_text.strip()

    return ""


def _voice_timeout_seconds() -> float:
    raw_value = os.getenv(
        "LLM_TIMEOUT_SECONDS",
        str(getattr(settings, "LLM_TIMEOUT_SECONDS", "60")),
    )
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return 60.0
    return value if value > 0 else 60.0
