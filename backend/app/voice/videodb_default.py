"""VideoDB hosted voice (Default / ElevenLabs-style API on your plan quota)."""

from __future__ import annotations

import logging

from videodb.collection import Collection

from app.config import get_settings
from app.voice.types import NarrationAudio
from app.voice.videodb_common import audio_duration_seconds

logger = logging.getLogger(__name__)

PROVIDER_ID = "videodb_default"


def generate(collection: Collection, text: str, *, chapter_title: str = "") -> NarrationAudio:
    settings = get_settings()
    audio = collection.generate_voice(
        text=text,
        voice_name=settings.video_db_default_voice_name,
    )
    duration = float(getattr(audio, "length", 0) or 0)
    if duration <= 0:
        duration = audio_duration_seconds(collection, audio.id, text)
    logger.info(
        "Narration [%s] %s (%.1fs) voice=%s",
        PROVIDER_ID,
        audio.id,
        duration,
        settings.video_db_default_voice_name,
    )
    return NarrationAudio(audio_id=audio.id, duration_sec=duration, provider=PROVIDER_ID)
