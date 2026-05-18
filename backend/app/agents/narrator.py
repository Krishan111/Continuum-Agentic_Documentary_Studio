"""Generate chapter narration with VideoDB voice API."""

from __future__ import annotations

import logging
import time

from videodb.collection import Collection

from app.agents.planner import ChapterPlan

logger = logging.getLogger(__name__)


def generate_narration(
    collection: Collection,
    chapter: ChapterPlan,
) -> tuple[str, float]:
    """Return (audio_id, duration_seconds)."""
    audio = collection.generate_voice(text=chapter.narration, voice_name="Default")
    duration = float(getattr(audio, "length", 0) or 0)

    if duration <= 0:
        for _ in range(30):
            time.sleep(2)
            refreshed = collection._connection.get(
                path=f"audio/{audio.id}",
                params={"collection_id": collection.id},
            )
            duration = float(refreshed.get("length", 0) or 0)
            if duration > 0:
                break

    if duration <= 0:
        duration = max(8.0, len(chapter.narration.split()) * 0.45)

    # Slight downward round — compose clamps to media length; avoid float overshoot.
    duration = round(min(duration, 120.0), 3)

    logger.info("Narration ready %s (%.1fs)", audio.id, duration)
    return audio.id, duration
