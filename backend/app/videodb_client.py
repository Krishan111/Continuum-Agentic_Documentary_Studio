"""VideoDB connection helpers."""

from __future__ import annotations

import re
import time
import uuid
from typing import TYPE_CHECKING

import videodb
from videodb.exceptions import VideodbError

from app.config import get_settings

if TYPE_CHECKING:
    from videodb.collection import Collection
    from videodb.video import Video


def get_connection():
    settings = get_settings()
    if not settings.video_db_api_key:
        raise VideodbError(
            "VIDEO_DB_API_KEY is not set. Copy continuum/.env.example to continuum/.env"
        )
    return videodb.connect(api_key=settings.video_db_api_key)


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "documentary"


def create_job_collection(topic: str, job_id: str) -> "Collection":
    """
    Create a fresh isolated collection per documentary job.
    Never silently reuse the account 'default' collection (avoids stale / wrong videos).
    """
    conn = get_connection()
    settings = get_settings()
    suffix = job_id.replace("-", "")[:8] or uuid.uuid4().hex[:8]
    name = f"{settings.continuum_collection_prefix}-{slugify(topic)}-{suffix}"
    collection = conn.create_collection(
        name=name,
        description=f"Continuum job {suffix}: {topic[:180]}",
        is_public=False,
    )
    return collection


def wait_for_video_ready(
    collection: "Collection",
    video: "Video",
    *,
    timeout_sec: int = 600,
    poll_interval: float = 5.0,
) -> "Video":
    """Poll until VideoDB reports a non-zero duration (upload transcoded)."""
    deadline = time.time() + timeout_sec
    last = video
    while time.time() < deadline:
        refreshed = collection.get_video(video.id)
        length = float(getattr(refreshed, "length", 0) or 0)
        if length > 0:
            return refreshed
        time.sleep(poll_interval)
        last = refreshed
    return last
