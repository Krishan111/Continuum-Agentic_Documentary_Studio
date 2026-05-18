"""OpenAI TTS → upload MP3 to VideoDB (no VideoDB voice quota required)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from openai import OpenAI
from videodb.collection import Collection
from videodb.exceptions import VideodbError

from app.config import get_settings
from app.voice.types import NarrationAudio
from app.voice.videodb_common import audio_duration_seconds

logger = logging.getLogger(__name__)

PROVIDER_ID = "openai_tts"


def generate(collection: Collection, text: str, *, chapter_title: str = "") -> NarrationAudio:
    settings = get_settings()
    if not settings.has_openai:
        raise VideodbError(
            "openai_tts provider requires OPENAI_API_KEY in continuum/.env"
        )

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.audio.speech.create(
        model=settings.openai_tts_model,
        voice=settings.openai_tts_voice,
        input=text,
        speed=settings.openai_tts_speed,
    )

    safe_title = (chapter_title or "chapter")[:48].replace(" ", "-")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(response.content)
        tmp_path = tmp.name

    try:
        try:
            from videodb import MediaType

            media_type = MediaType.audio
        except ImportError:
            media_type = "audio"

        audio = collection.upload(
            file_path=tmp_path,
            media_type=media_type,
            name=f"continuum-narration-{safe_title}",
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    duration = float(getattr(audio, "length", 0) or 0)
    if duration <= 0:
        duration = audio_duration_seconds(collection, audio.id, text)

    logger.info(
        "Narration [%s] %s (%.1fs) model=%s voice=%s",
        PROVIDER_ID,
        audio.id,
        duration,
        settings.openai_tts_model,
        settings.openai_tts_voice,
    )
    return NarrationAudio(audio_id=audio.id, duration_sec=duration, provider=PROVIDER_ID)
