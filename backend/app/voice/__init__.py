"""
Pluggable voice generation for chapter narration.

Set CONTINUUM_VOICE_PROVIDER in continuum/.env — see README "Voice generation".
"""

from __future__ import annotations

import logging
from typing import Callable

from videodb.collection import Collection

from app.config import VALID_VOICE_PROVIDERS, get_settings
from app.voice import openai_tts, videodb_default, videodb_sandbox
from app.voice.types import NarrationAudio

logger = logging.getLogger(__name__)

_PROVIDER_FN: dict[str, Callable[..., NarrationAudio]] = {
    videodb_default.PROVIDER_ID: videodb_default.generate,
    videodb_sandbox.PROVIDER_ID: videodb_sandbox.generate,
    openai_tts.PROVIDER_ID: openai_tts.generate,
}

_PROVIDER_LABELS: dict[str, str] = {
    videodb_default.PROVIDER_ID: "VideoDB hosted (Default voice)",
    videodb_sandbox.PROVIDER_ID: "VideoDB Sandbox (OmniVoice)",
    openai_tts.PROVIDER_ID: "OpenAI TTS (uploaded to VideoDB)",
}


def provider_label(provider_id: str) -> str:
    return _PROVIDER_LABELS.get(provider_id, provider_id)


def active_provider_id() -> str:
    return get_settings().resolved_voice_provider


def generate_chapter_narration(
    collection: Collection,
    text: str,
    *,
    chapter_title: str = "",
) -> NarrationAudio:
    """Generate narration audio using the configured provider."""
    provider = active_provider_id()
    if provider not in _PROVIDER_FN:
        raise ValueError(
            f"Unknown CONTINUUM_VOICE_PROVIDER={provider!r}. "
            f"Choose one of: {', '.join(sorted(VALID_VOICE_PROVIDERS))}"
        )
    logger.info("Voice provider: %s (%s)", provider, provider_label(provider))
    return _PROVIDER_FN[provider](collection, text, chapter_title=chapter_title)
