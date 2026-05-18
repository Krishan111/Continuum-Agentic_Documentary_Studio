"""Index uploaded videos for multimodal search."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from videodb.collection import Collection

from app.pipeline.ingest import IngestedVideo

logger = logging.getLogger(__name__)

VISUAL_PROMPT = (
    "Describe this segment for a documentary editor: setting, subjects, "
    "actions, on-screen text, mood, and why it matters to the topic."
)

AUDIO_PROMPT = (
    "Summarize spoken content: key facts, names, dates, claims, and quotes "
    "useful for documentary narration."
)

# VideoDB requires select_frames as a list of strings (SDK does not default it).
# See https://docs.videodb.io/pages/getting-started/quickstart
VISUAL_BATCH_CONFIG = {
    "type": "time",
    "value": 15,
    "frame_count": 2,
    "select_frames": ["first", "last"],
}


def index_sources(
    collection: Collection,
    sources: list[IngestedVideo],
    *,
    on_progress: Optional[Callable[[str, int, int], None]] = None,
) -> None:
    """Index spoken words and visuals on every source video."""
    total = len(sources)

    for i, source in enumerate(sources, start=1):
        if on_progress:
            on_progress(f"Indexing {i}/{total}: {source.title[:40]}", i, total)

        video = collection.get_video(source.video_id)
        logger.info("Indexing spoken words: %s", video.id)
        video.index_spoken_words(force=True)

        logger.info("Indexing visuals: %s", video.id)
        video.index_visuals(
            prompt=VISUAL_PROMPT,
            name=f"continuum-visual-{video.id}",
            batch_config=VISUAL_BATCH_CONFIG,
        )

        logger.info("Indexing audio semantics: %s", video.id)
        video.index_audio(
            prompt=AUDIO_PROMPT,
            name=f"continuum-audio-{video.id}",
        )
