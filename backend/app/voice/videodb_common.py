"""Helpers shared by VideoDB-hosted voice providers."""

from __future__ import annotations

import logging
import time

from videodb.collection import Collection

logger = logging.getLogger(__name__)


def audio_duration_seconds(collection: Collection, audio_id: str, text: str) -> float:
    """Poll VideoDB until audio length is known; estimate from word count if needed."""
    duration = 0.0
    for _ in range(30):
        try:
            data = collection._connection.get(
                path=f"audio/{audio_id}",
                params={"collection_id": collection.id},
            )
            duration = float(data.get("length", 0) or 0)
        except Exception as exc:
            logger.debug("Audio length poll failed for %s: %s", audio_id, exc)
        if duration > 0:
            break
        time.sleep(2)

    if duration <= 0:
        duration = max(8.0, len(text.split()) * 0.45)

    return round(min(duration, 120.0), 3)
