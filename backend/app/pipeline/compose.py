"""Assemble documentary timeline — sequential scenes, no overlapping narration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from videodb.collection import Collection
from videodb.editor import (
    AudioAsset,
    Clip,
    Fit,
    Font,
    Position,
    TextAsset,
    Timeline,
    Track,
    Transition,
    VideoAsset,
)

from app.pipeline.search_clips import ClipCandidate

logger = logging.getLogger(__name__)

TITLE_SEC = 4.0
OUTRO_SEC = 4.0
FADE = Transition(in_="fade", out="fade", duration=0.5)
MAX_CLIP_SEC = 28.0
MIN_CLIP_SEC = 6.0
MEDIA_LENGTH_PAD = 0.1

# Scene rhythm: b-roll before VO, after VO, then quiet gap before next scene.
BROLL_LEAD_SEC = 1.5
BROLL_TAIL_SEC = 0.7
MIN_PAUSE_BETWEEN_SCENES = 0.8


@dataclass
class ChapterSegment:
    title: str
    narration: str
    narration_audio_id: str
    narration_duration: float
    clip: ClipCandidate
    pause_after_sec: float = 1.0
    broll_lead_sec: float = BROLL_LEAD_SEC
    broll_tail_sec: float = BROLL_TAIL_SEC


def _round_sec(value: float) -> float:
    return round(max(0.0, value), 3)


def _safe_clip_duration(
    requested: float,
    media_length: float,
    *,
    trim_start: float = 0.0,
    floor: float = MIN_CLIP_SEC,
) -> float:
    requested = max(floor, requested)
    if media_length <= 0:
        return _round_sec(requested)
    available = media_length - trim_start - MEDIA_LENGTH_PAD
    if available < floor:
        available = max(0.5, media_length - trim_start - 0.01)
    return _round_sec(min(requested, available))


def _video_length(collection: Collection, video_id: str) -> float:
    try:
        return float(collection.get_video(video_id).length or 0)
    except Exception as exc:
        logger.warning("Could not read length for %s: %s", video_id, exc)
        return 0.0


def _audio_length(collection: Collection, audio_id: str) -> float:
    try:
        data = collection._connection.get(
            path=f"audio/{audio_id}",
            params={"collection_id": collection.id},
        )
        return float(data.get("length", 0) or 0)
    except Exception as exc:
        logger.warning("Could not read length for %s: %s", audio_id, exc)
        return 0.0


def _narration_duration(collection: Collection, audio_id: str, fallback: float) -> float:
    audio_len = _audio_length(collection, audio_id)
    if audio_len > 0:
        return _safe_clip_duration(fallback, audio_len, trim_start=0.0, floor=1.0)
    return _round_sec(fallback)


def scene_block_duration(segment: ChapterSegment, narr_dur: float) -> float:
    """Total timeline length for one scene (no overlap with the next)."""
    pause = max(MIN_PAUSE_BETWEEN_SCENES, segment.pause_after_sec)
    return _round_sec(
        segment.broll_lead_sec + narr_dur + segment.broll_tail_sec + pause
    )


def _chapter_title_asset(title: str) -> TextAsset:
    return TextAsset(
        text=title.upper(),
        font=Font(family="Clear Sans", size=72, color="#FFFFFF", opacity=1.0),
    )


def build_documentary(
    conn,
    collection: Collection,
    topic: str,
    chapters: list[ChapterSegment],
    *,
    film_title: str | None = None,
) -> dict:
    """
    One scene per timeline block:
    [lead b-roll][narration][tail b-roll][pause] — narrations never overlap.
    """
    display_title = film_title or topic
    video_ids = [ch.clip.video_id for ch in chapters]
    distinct = len(set(video_ids))

    timeline = Timeline(conn)
    timeline.background = "#0a0f1a"
    timeline.resolution = "1920x1080"

    video_track = Track()
    text_track = Track()
    narration_track = Track()

    t = 0.0
    text_track.add_clip(
        0,
        Clip(
            asset=_chapter_title_asset(display_title),
            duration=TITLE_SEC,
            position=Position.center,
        ),
    )
    t = TITLE_SEC

    scene_timings: list[dict] = []

    for idx, chapter in enumerate(chapters):
        narr_dur = _narration_duration(
            collection, chapter.narration_audio_id, chapter.narration_duration
        )
        block_dur = scene_block_duration(chapter, narr_dur)
        source_len = _video_length(collection, chapter.clip.video_id)
        trim_start = float(chapter.clip.start)

        video_dur = _safe_clip_duration(
            block_dur, source_len, trim_start=trim_start, floor=MIN_CLIP_SEC
        )
        if video_dur < block_dur - 0.5:
            block_dur = video_dur

        narr_start = t + chapter.broll_lead_sec
        label_dur = min(2.5, max(1.5, narr_dur * 0.12))

        video_track.add_clip(
            int(t),
            Clip(
                asset=VideoAsset(
                    id=chapter.clip.video_id,
                    start=trim_start,
                    volume=0.0,
                ),
                duration=video_dur,
                fit=Fit.crop,
                position=Position.center,
                transition=FADE if idx > 0 else None,
            ),
        )

        text_track.add_clip(
            int(t + 0.2),
            Clip(
                asset=_chapter_title_asset(chapter.title),
                duration=label_dur,
                position=Position.center,
            ),
        )

        narration_track.add_clip(
            int(narr_start),
            Clip(
                asset=AudioAsset(id=chapter.narration_audio_id, volume=1.0),
                duration=narr_dur,
            ),
        )

        scene_timings.append(
            {
                "scene": chapter.title,
                "block_start": round(t, 2),
                "narration_start": round(narr_start, 2),
                "narration_duration": narr_dur,
                "block_duration": block_dur,
                "video_id": chapter.clip.video_id,
            }
        )

        logger.info(
            "Scene %d %r: block@%.1fs (%.1fs) narr@%.1fs (%.1fs)",
            idx + 1,
            chapter.title,
            t,
            block_dur,
            narr_start,
            narr_dur,
        )
        t += block_dur

    text_track.add_clip(
        int(t),
        Clip(
            asset=_chapter_title_asset("Continuum · Powered by VideoDB"),
            duration=OUTRO_SEC,
            position=Position.center,
        ),
    )
    total_dur = t + OUTRO_SEC

    timeline.add_track(video_track)
    timeline.add_track(text_track)
    timeline.add_track(narration_track)

    logger.info("Generating stream (%.1fs, %d scenes)", total_dur, len(chapters))
    stream_url = timeline.generate_stream()
    player_url = f"https://console.videodb.io/player?url={stream_url}"

    return {
        "stream_url": stream_url,
        "player_url": player_url,
        "duration_seconds": round(total_dur, 1),
        "timeline_video_ids": video_ids,
        "distinct_source_videos": distinct,
        "used_compile_montage": False,
        "scene_timings": scene_timings,
    }
