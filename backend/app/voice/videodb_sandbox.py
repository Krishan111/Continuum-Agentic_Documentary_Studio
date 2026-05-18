"""VideoDB Sandbox OmniVoice — self-hosted TTS on sandbox compute (hackathon path)."""

from __future__ import annotations

import logging
import threading

from videodb.collection import Collection
from videodb.exceptions import VideodbError

from app.config import get_settings
from app.voice.types import NarrationAudio
from app.voice.videodb_common import audio_duration_seconds
from app.videodb_client import get_connection

logger = logging.getLogger(__name__)

PROVIDER_ID = "videodb_sandbox"

_lock = threading.Lock()
_cached_sandbox_id: str | None = None


def _has_sandbox_sdk() -> bool:
    try:
        from videodb import SandboxModel, SandboxTier  # noqa: F401

        return True
    except ImportError:
        return False


def ensure_sandbox_id() -> str:
    global _cached_sandbox_id

    settings = get_settings()
    if settings.video_db_sandbox_id.strip():
        return settings.video_db_sandbox_id.strip()

    if not settings.video_db_sandbox_auto_create:
        raise VideodbError(
            "videodb_sandbox voice provider needs VIDEO_DB_SANDBOX_ID or "
            "VIDEO_DB_SANDBOX_AUTO_CREATE=1. Run scripts/create_sandbox.py — see README."
        )

    if not _has_sandbox_sdk():
        raise VideodbError(
            "Sandbox SDK required. pip install "
            "'git+https://github.com/Video-DB/videodb-python.git@hackathon'"
        )

    with _lock:
        if _cached_sandbox_id:
            return _cached_sandbox_id

        from videodb import SandboxTier

        conn = get_connection()
        tier = settings.video_db_sandbox_tier or SandboxTier.small
        logger.info("Creating VideoDB sandbox (tier=%s) for OmniVoice…", tier)
        sandbox = conn.create_sandbox(tier=tier, name="continuum-voice")
        sandbox.wait_for_ready(timeout=settings.video_db_sandbox_ready_timeout, interval=5)
        if not sandbox.is_active:
            sandbox.refresh()
        if not sandbox.is_active:
            raise VideodbError(
                f"Sandbox {sandbox.id} not active (status={sandbox.status})"
            )
        _cached_sandbox_id = sandbox.id
        logger.info("Sandbox ready: %s", _cached_sandbox_id)
        return _cached_sandbox_id


def generate(collection: Collection, text: str, *, chapter_title: str = "") -> NarrationAudio:
    from videodb.sandbox_models import SandboxModel

    settings = get_settings()
    sandbox_id = ensure_sandbox_id()
    config: dict = {}
    if settings.video_db_voice_instructions.strip():
        config["instructions"] = settings.video_db_voice_instructions.strip()

    audio = collection.generate_voice(
        text=text,
        model_name=SandboxModel.OMNIVOICE,
        sandbox_id=sandbox_id,
        wait=True,
        timeout=settings.video_db_voice_job_timeout,
        poll_interval=5,
        config=config,
    )
    duration = float(getattr(audio, "length", 0) or 0)
    if duration <= 0:
        duration = audio_duration_seconds(collection, audio.id, text)
    logger.info("Narration [%s] %s (%.1fs) sandbox=%s", PROVIDER_ID, audio.id, duration, sandbox_id)
    return NarrationAudio(audio_id=audio.id, duration_sec=duration, provider=PROVIDER_ID)
