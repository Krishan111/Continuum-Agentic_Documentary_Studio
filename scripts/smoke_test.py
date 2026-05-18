"""
Minimal VideoDB spine test: upload one YouTube URL, index, search, compose.

Run from continuum/:
  set VIDEO_DB_API_KEY=...
  python scripts/smoke_test.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.pipeline.compose import ChapterSegment, build_documentary
from app.pipeline.index_media import index_sources
from app.pipeline.ingest import upload_sources
from app.pipeline.search_clips import search_multimodal
from app.videodb_client import create_job_collection, get_connection

TEST_URL = "https://www.youtube.com/watch?v=WDv4AWk0J3U"
TOPIC = "Continuum smoke test"


def main() -> None:
    if not os.getenv("VIDEO_DB_API_KEY"):
        print("ERROR: Set VIDEO_DB_API_KEY in continuum/.env")
        sys.exit(1)

    print("1. Collection + upload")
    coll = create_job_collection(TOPIC, "smoke-test")
    ingest = upload_sources(coll, [TEST_URL], min_distinct=1)
    sources = ingest.sources
    print(f"   Uploaded {sources[0].video_id} ({sources[0].length:.1f}s)")

    print("2. Index")
    index_sources(coll, sources)

    print("3. Search")
    clips = search_multimodal(coll, TOPIC, per_index=2)
    if not clips:
        raise RuntimeError("No search results")
    clip = clips[0]
    print(f"   Clip {clip.video_id} [{clip.start:.1f}-{clip.end:.1f}]")

    print("4. Voice + compose (single chapter)")
    audio = coll.generate_voice(
        text="This is a Continuum smoke test verifying VideoDB timeline assembly.",
        voice_name="Default",
    )
    dur = float(getattr(audio, "length", 0) or 12.0) or 12.0

    conn = get_connection()
    out = build_documentary(
        conn,
        coll,
        TOPIC,
        [
            ChapterSegment(
                title="Smoke Test",
                narration="test",
                narration_audio_id=audio.id,
                narration_duration=dur,
                clip=clip,
            )
        ],
    )
    print("5. Done")
    print(f"   stream: {out['stream_url']}")
    print(f"   player: {out['player_url']}")


if __name__ == "__main__":
    main()
