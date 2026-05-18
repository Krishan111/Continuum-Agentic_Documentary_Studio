"""Upload source videos to VideoDB from YouTube URLs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from videodb.collection import Collection
from videodb.video import Video

from app.videodb_client import wait_for_video_ready

logger = logging.getLogger(__name__)


@dataclass
class IngestedVideo:
    video_id: str
    youtube_url: str
    title: str
    length: float


@dataclass
class IngestResult:
    sources: list[IngestedVideo] = field(default_factory=list)
    failed_urls: list[str] = field(default_factory=list)

    @property
    def unique_video_ids(self) -> set[str]:
        return {s.video_id for s in self.sources}


def upload_sources(
    collection: Collection,
    urls: list[str],
    *,
    on_progress: Optional[Callable[[str, int, int], None]] = None,
    min_distinct: int = 2,
) -> IngestResult:
    """Upload each YouTube URL; dedupe by VideoDB media id."""
    result = IngestResult()
    seen_media_ids: set[str] = set()
    total = len(urls)

    for i, url in enumerate(urls, start=1):
        if on_progress:
            on_progress(f"Uploading video {i}/{total}", i, total)

        logger.info("Uploading %s", url)
        try:
            video: Video = collection.upload(url=url, name=f"continuum-source-{i}")
        except Exception as exc:
            logger.error("Upload failed for %s: %s", url, exc)
            result.failed_urls.append(url)
            continue

        if video is None:
            logger.warning("Upload returned None for %s", url)
            result.failed_urls.append(url)
            continue

        if video.id in seen_media_ids:
            logger.warning(
                "Skipping duplicate media id %s for %s (VideoDB deduped URL)",
                video.id,
                url,
            )
            continue

        video = wait_for_video_ready(collection, video)
        length = float(getattr(video, "length", 0) or 0)
        if length <= 0:
            logger.warning("Video %s has zero length after upload", video.id)
            result.failed_urls.append(url)
            continue

        title = getattr(video, "name", None) or f"source-{i}"
        seen_media_ids.add(video.id)
        result.sources.append(
            IngestedVideo(
                video_id=video.id,
                youtube_url=url,
                title=title,
                length=length,
            )
        )
        logger.info("Ready: %s (%.1fs) ← %s", video.id, length, url)

    if len(result.sources) < min_distinct:
        raise RuntimeError(
            f"Need at least {min_distinct} distinct source videos; "
            f"got {len(result.sources)} from {total} URLs. "
            f"Failed: {result.failed_urls}"
        )

    logger.info(
        "Ingested %d distinct videos (failed %d URLs)",
        len(result.sources),
        len(result.failed_urls),
    )
    return result
