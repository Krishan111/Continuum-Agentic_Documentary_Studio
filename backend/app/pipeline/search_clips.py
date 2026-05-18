"""Search VideoDB collections for documentary clip candidates."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from videodb._constants import IndexType
from videodb.collection import Collection
from videodb.exceptions import InvalidRequestError, SearchError, VideodbError
from videodb.shot import Shot
from videodb.video import Video

from app.pipeline.ingest import IngestedVideo

logger = logging.getLogger(__name__)

DEFAULT_CLIP_SECONDS = 22.0
MIN_CLIP_SEC = 6.0
VISUAL_INDEX_NAME_PREFIX = "continuum-visual-"


@dataclass
class ClipCandidate:
    video_id: str
    video_title: str
    start: float
    end: float
    text: str
    score: Optional[float] = None
    index_type: str = "spoken_word"

    @property
    def duration(self) -> float:
        return max(0.5, float(self.end) - float(self.start))


def _shots_from_result(result) -> list[Shot]:
    if hasattr(result, "get_shots"):
        return result.get_shots() or []
    return getattr(result, "shots", []) or []


def _shots_to_clips(shots: list[Shot], index_type: str) -> list[ClipCandidate]:
    clips: list[ClipCandidate] = []
    for shot in shots:
        if shot.start is None or shot.end is None:
            continue
        clips.append(
            ClipCandidate(
                video_id=shot.video_id,
                video_title=shot.video_title or "",
                start=float(shot.start),
                end=float(shot.end),
                text=(shot.text or "")[:500],
                score=float(shot.search_score) if shot.search_score else None,
                index_type=index_type,
            )
        )
    return clips


def _is_benign_search_error(exc: Exception) -> bool:
    """Errors that mean 'no usable hits' rather than a fatal pipeline bug."""
    msg = str(exc).lower()
    patterns = (
        "no results",
        "not found",
        "scene index failed",
        "query scene index failed",
        "query scene",
    )
    return any(p in msg for p in patterns)


def _safe_search(callable_fn, *args, **kwargs) -> list[ClipCandidate]:
    index_type = kwargs.get("index_type", IndexType.spoken_word)
    try:
        result = callable_fn(*args, **kwargs)
        return _shots_to_clips(_shots_from_result(result), index_type)
    except (InvalidRequestError, SearchError, VideodbError) as exc:
        if _is_benign_search_error(exc):
            logger.info("Search skipped (%s): %s", index_type, exc)
            return []
        raise


def _scene_index_ids_for_video(video: Video) -> list[str]:
    """List scene index IDs created for this video (prefer our visual index)."""
    try:
        indexes = video.list_scene_index() or []
    except Exception as exc:
        logger.warning("list_scene_index failed for %s: %s", video.id, exc)
        return []

    visual: list[str] = []
    other: list[str] = []

    for idx in indexes:
        if not isinstance(idx, dict):
            continue
        sid = idx.get("scene_index_id") or idx.get("id")
        if not sid:
            continue
        name = (idx.get("name") or "").lower()
        status = (idx.get("status") or "").lower()
        if status in ("failed", "error"):
            continue
        if VISUAL_INDEX_NAME_PREFIX in name or "visual" in name:
            visual.append(sid)
        else:
            other.append(sid)

    return visual or other


def _search_video_spoken(
    video: Video,
    query: str,
    *,
    result_threshold: int,
    score_threshold: float,
) -> list[ClipCandidate]:
    return _safe_search(
        video.search,
        query,
        index_type=IndexType.spoken_word,
        result_threshold=result_threshold,
        score_threshold=score_threshold,
    )


def _search_video_scenes(
    video: Video,
    query: str,
    *,
    result_threshold: int,
    score_threshold: float,
) -> list[ClipCandidate]:
    """Search each scene index on a video (required for visual index_type=scene)."""
    clips: list[ClipCandidate] = []
    for scene_index_id in _scene_index_ids_for_video(video):
        batch = _safe_search(
            video.search,
            query,
            index_type=IndexType.scene,
            result_threshold=result_threshold,
            score_threshold=score_threshold,
            scene_index_id=scene_index_id,
        )
        clips.extend(batch)
    return clips


def _safe_collection_search(
    collection: Collection,
    query: str,
    *,
    index_type: str,
    result_threshold: int = 5,
    score_threshold: float = 0.05,
) -> list[ClipCandidate]:
    """
    Collection-wide search works reliably for spoken_word only.
    Scene search at collection scope fails without scene_index_id metadata.
    """
    if index_type == IndexType.scene:
        return []

    return _safe_search(
        collection.search,
        query,
        index_type=index_type,
        result_threshold=result_threshold,
        score_threshold=score_threshold,
    )


def _search_each_video(
    collection: Collection,
    query: str,
    *,
    include_scene: bool = True,
    result_threshold: int = 3,
    score_threshold: float = 0.05,
) -> list[ClipCandidate]:
    clips: list[ClipCandidate] = []
    try:
        videos = collection.get_videos()
    except Exception as exc:
        logger.warning("get_videos failed: %s", exc)
        return clips

    for video in videos:
        clips.extend(
            _search_video_spoken(
                video,
                query,
                result_threshold=result_threshold,
                score_threshold=score_threshold,
            )
        )
        if include_scene:
            clips.extend(
                _search_video_scenes(
                    video,
                    query,
                    result_threshold=result_threshold,
                    score_threshold=score_threshold,
                )
            )

    clips.sort(key=lambda c: (c.score or 0), reverse=True)
    return clips


def _segments_overlap(
    video_id: str,
    start: float,
    end: float,
    used: dict[str, list[tuple[float, float]]],
    *,
    margin: float = 3.0,
) -> bool:
    for u_start, u_end in used.get(video_id, []):
        if start < u_end + margin and end > u_start - margin:
            return True
    return False


def _record_segment(
    video_id: str,
    start: float,
    end: float,
    used: dict[str, list[tuple[float, float]]],
) -> None:
    used.setdefault(video_id, []).append((start, end))


def pick_non_overlapping_clip(
    candidates: list[ClipCandidate],
    used_segments: dict[str, list[tuple[float, float]]],
    *,
    prefer_video_id: str | None = None,
) -> ClipCandidate | None:
    """Choose the best-scoring clip that does not reuse the same time range."""
    ordered = sorted(candidates, key=lambda c: (c.score or 0), reverse=True)
    if prefer_video_id:
        preferred = [c for c in ordered if c.video_id == prefer_video_id]
        rest = [c for c in ordered if c.video_id != prefer_video_id]
        ordered = preferred + rest

    for cand in ordered:
        if _segments_overlap(cand.video_id, cand.start, cand.end, used_segments):
            continue
        _record_segment(cand.video_id, cand.start, cand.end, used_segments)
        return cand
    return None


def search_in_video(
    collection: Collection,
    video_id: str,
    query: str,
    *,
    per_index: int = 5,
) -> list[ClipCandidate]:
    """Search spoken words + visual scenes within a single source video."""
    video = collection.get_video(video_id)
    clips: list[ClipCandidate] = []
    clips.extend(
        _search_video_spoken(
            video, query, result_threshold=per_index, score_threshold=0.05
        )
    )
    clips.extend(
        _search_video_scenes(
            video, query, result_threshold=per_index, score_threshold=0.05
        )
    )
    clips.sort(key=lambda c: (c.score or 0), reverse=True)
    return clips


def fallback_clip_for_source(
    source: IngestedVideo,
    chapter_index: int,
    used: dict[str, list[tuple[float, float]]],
    *,
    clip_seconds: float = DEFAULT_CLIP_SECONDS,
) -> ClipCandidate:
    """Pick a non-overlapping timed segment from one specific source video."""
    length = max(source.length, clip_seconds + 1)
    # Staggered offsets so chapters from the same source use different moments
    offsets = [25.0, 55.0, 90.0, 130.0, 175.0, 220.0, 270.0]

    for offset in offsets:
        start = min(
            offset + chapter_index * 8.0,
            max(0.0, length - clip_seconds - 2.0),
        )
        end = min(start + clip_seconds, length)
        if end - start < MIN_CLIP_SEC and length > MIN_CLIP_SEC:
            start = max(0.0, length / 2 - clip_seconds / 2)
            end = min(start + clip_seconds, length)
        if not _segments_overlap(source.video_id, start, end, used):
            _record_segment(source.video_id, start, end, used)
            return ClipCandidate(
                video_id=source.video_id,
                video_title=source.title,
                start=start,
                end=end,
                text=f"Segment from {source.title}",
                score=None,
                index_type="fallback",
            )

    start = min(30.0 + chapter_index * 45.0, max(0.0, length - clip_seconds - 1))
    end = min(start + clip_seconds, length)
    _record_segment(source.video_id, start, end, used)
    return ClipCandidate(
        video_id=source.video_id,
        video_title=source.title,
        start=start,
        end=end,
        text=f"Segment from {source.title}",
        score=None,
        index_type="fallback",
    )


def fallback_clip_from_sources(
    sources: list[IngestedVideo],
    chapter_index: int,
    used: dict[str, list[tuple[float, float]]] | None = None,
    *,
    clip_seconds: float = DEFAULT_CLIP_SECONDS,
) -> ClipCandidate:
    if not sources:
        raise RuntimeError("No source videos available for fallback clips")
    used = used if used is not None else {}
    source = sources[chapter_index % len(sources)]
    return fallback_clip_for_source(
        source, chapter_index, used, clip_seconds=clip_seconds
    )


def search_collection(
    collection: Collection,
    query: str,
    *,
    index_type: str = IndexType.spoken_word,
    result_threshold: int = 5,
    score_threshold: float = 0.05,
) -> list[ClipCandidate]:
    return _safe_collection_search(
        collection,
        query,
        index_type=index_type,
        result_threshold=result_threshold,
        score_threshold=score_threshold,
    )


def search_multimodal(
    collection: Collection,
    query: str,
    *,
    per_index: int = 4,
) -> list[ClipCandidate]:
    queries = [query]
    words = query.split()
    if len(words) > 4:
        queries.append(" ".join(words[:4]))

    seen: set[tuple[str, int, int]] = set()
    merged: list[ClipCandidate] = []

    def add_clips(clips: list[ClipCandidate]) -> None:
        for clip in clips:
            key = (clip.video_id, int(clip.start), int(clip.end))
            if key in seen:
                continue
            seen.add(key)
            merged.append(clip)

    for q in queries:
        add_clips(
            _safe_collection_search(
                collection,
                q,
                index_type=IndexType.spoken_word,
                result_threshold=per_index,
                score_threshold=0.05,
            )
        )
        add_clips(
            _search_each_video(
                collection,
                q,
                include_scene=True,
                result_threshold=per_index,
                score_threshold=0.05,
            )
        )
        if merged:
            break

    merged.sort(key=lambda c: (c.score or 0), reverse=True)
    return merged
