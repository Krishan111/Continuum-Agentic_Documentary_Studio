"""Discover YouTube source videos via Data API v3 or demo fallbacks."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class YouTubeCandidate:
    video_id: str
    url: str
    title: str
    channel: str
    duration_sec: Optional[int] = None


def _load_demo_pack(settings: Settings, topic: str) -> Optional[dict]:
    path = settings.demos_path
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    key = topic.strip().lower()
    if key in data:
        return data[key]
    for demo_key, pack in data.items():
        if demo_key in key or key in demo_key:
            return pack
    return None


def demo_urls_for_topic(topic: str) -> list[str]:
    settings = get_settings()
    pack = _load_demo_pack(settings, topic)
    if pack and pack.get("youtube_urls"):
        return list(pack["youtube_urls"])
    return []


def search_youtube(
    query: str,
    *,
    max_results: int = 5,
    api_key: Optional[str] = None,
) -> list[YouTubeCandidate]:
    key = api_key or get_settings().youtube_api_key
    if not key:
        return []

    try:
        youtube = build("youtube", "v3", developerKey=key, cache_discovery=False)
        search_resp = (
            youtube.search()
            .list(
                part="snippet",
                q=query,
                type="video",
                maxResults=max_results,
                videoDuration="medium",
                relevanceLanguage="en",
                safeSearch="moderate",
            )
            .execute()
        )
        ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
        if not ids:
            return []

        details = (
            youtube.videos()
            .list(part="contentDetails,snippet", id=",".join(ids))
            .execute()
        )
        candidates: list[YouTubeCandidate] = []
        for item in details.get("items", []):
            vid = item["id"]
            duration = _parse_iso8601_duration(
                item.get("contentDetails", {}).get("duration", "")
            )
            if duration and duration < 120:
                continue
            if duration and duration > 1200:
                continue
            snippet = item.get("snippet", {})
            candidates.append(
                YouTubeCandidate(
                    video_id=vid,
                    url=f"https://www.youtube.com/watch?v={vid}",
                    title=snippet.get("title", vid),
                    channel=snippet.get("channelTitle", ""),
                    duration_sec=duration,
                )
            )
        return candidates
    except HttpError as exc:
        logger.error("YouTube API error: %s", exc)
        return []


def _parse_iso8601_duration(value: str) -> Optional[int]:
    """Parse PT#H#M#S duration to seconds."""
    if not value or not value.startswith("PT"):
        return None
    value = value[2:]
    hours = minutes = seconds = 0
    num = ""
    for ch in value:
        if ch.isdigit():
            num += ch
        elif ch == "H":
            hours = int(num or 0)
            num = ""
        elif ch == "M":
            minutes = int(num or 0)
            num = ""
        elif ch == "S":
            seconds = int(num or 0)
            num = ""
    return hours * 3600 + minutes * 60 + seconds


def discover_sources(
    topic: str,
    *,
    use_demo: bool = False,
    max_videos: Optional[int] = None,
) -> list[str]:
    """
    Return deduplicated YouTube watch URLs for a documentary topic.
    Priority: demo pack → YouTube API queries → hardcoded fallback URLs.
    """
    settings = get_settings()
    max_videos = max_videos or settings.continuum_max_source_videos
    urls: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        if url not in seen:
            seen.add(url)
            urls.append(url)

    if use_demo:
        for u in demo_urls_for_topic(topic):
            add(u)

    if urls and use_demo:
        return urls[:max_videos]

    pack = _load_demo_pack(settings, topic)
    queries = [topic]
    if pack and pack.get("search_queries"):
        queries = pack["search_queries"]

    if settings.youtube_api_key:
        per_query = max(2, max_videos // len(queries))
        for q in queries:
            for cand in search_youtube(q, max_results=per_query):
                add(cand.url)
            if len(urls) >= max_videos:
                break

    if not urls:
        for u in demo_urls_for_topic(topic):
            add(u)

    if not urls:
        add("https://www.youtube.com/watch?v=WDv4AWk0J3U")

    return urls[:max_videos]
