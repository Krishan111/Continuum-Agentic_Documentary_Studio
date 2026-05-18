"""Generate chapter narration via the configured voice provider."""

from __future__ import annotations

import logging

from videodb.collection import Collection

from app.agents.planner import ChapterPlan
from app.voice import generate_chapter_narration

logger = logging.getLogger(__name__)


def generate_narration(
    collection: Collection,
    chapter: ChapterPlan,
) -> tuple[str, float]:
    """Return (audio_id, duration_seconds)."""
    result = generate_chapter_narration(
        collection,
        chapter.narration,
        chapter_title=chapter.title,
    )
    return result.audio_id, result.duration_sec
