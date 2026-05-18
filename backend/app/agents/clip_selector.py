"""Clip selection driven by script visual direction and director source assignment."""

from __future__ import annotations

import logging

from videodb.collection import Collection

from app.agents.planner import ChapterPlan
from app.pipeline.ingest import IngestedVideo
from app.pipeline.search_clips import (
    ClipCandidate,
    fallback_clip_for_source,
    pick_non_overlapping_clip,
    search_in_video,
)

logger = logging.getLogger(__name__)


def _clip_for_chapter(
    collection: Collection,
    chapter: ChapterPlan,
    source: IngestedVideo,
    chapter_index: int,
    used_segments: dict[str, list[tuple[float, float]]],
    topic: str,
) -> ClipCandidate:
    clip = fallback_clip_for_source(source, chapter_index, used_segments)

    queries: list[str] = []
    if chapter.search_query:
        queries.append(chapter.search_query)
    if chapter.visual_direction:
        queries.append(chapter.visual_direction)
    if topic and chapter.search_query != topic:
        queries.append(f"{topic} {chapter.title}")

    candidates: list[ClipCandidate] = []
    for q in queries:
        candidates.extend(
            search_in_video(collection, source.video_id, q, per_index=6)
        )
        if candidates:
            break

    same_source = [c for c in candidates if c.video_id == source.video_id]
    refined = pick_non_overlapping_clip(
        same_source, used_segments, prefer_video_id=source.video_id
    )
    return refined or clip


def select_clips_for_chapters(
    collection: Collection,
    chapters: list[ChapterPlan],
    sources: list[IngestedVideo],
    *,
    topic: str = "",
) -> list[tuple[ChapterPlan, ClipCandidate]]:
    if not sources:
        raise RuntimeError("No source videos ingested")

    num_chapters = len(chapters)
    num_sources = len(sources)
    used_segments: dict[str, list[tuple[float, float]]] = {}
    selections: list[tuple[ChapterPlan, ClipCandidate]] = []

    for i, chapter in enumerate(chapters):
        src_idx = chapter.preferred_source_index % num_sources
        source = sources[src_idx]
        clip = _clip_for_chapter(
            collection,
            chapter,
            source,
            i,
            used_segments,
            topic,
        )
        logger.info(
            "Scene %d %r → source[%d] %s @ %.1f–%.1f s | visual: %s",
            i + 1,
            chapter.title,
            src_idx,
            clip.video_id,
            clip.start,
            clip.end,
            (chapter.visual_direction or "")[:60],
        )
        selections.append((chapter, clip))

    distinct = {c.video_id for _, c in selections}
    logger.info(
        "Clip plan: %d scenes, %d sources, %d distinct video_ids",
        num_chapters,
        num_sources,
        len(distinct),
    )
    return selections
