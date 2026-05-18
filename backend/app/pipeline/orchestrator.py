"""End-to-end Continuum documentary pipeline."""

from __future__ import annotations

import logging
import traceback

from app.agents.clip_selector import select_clips_for_chapters
from app.agents.narrator import generate_narration
from app.agents.planner import plan_documentary
from app.discovery.youtube import discover_sources
from app.jobs import JobStore, job_store
from app.models import PipelineStage
from app.pipeline.compose import ChapterSegment, build_documentary
from app.pipeline.index_media import index_sources
from app.pipeline.ingest import upload_sources
from app.videodb_client import create_job_collection, get_connection

logger = logging.getLogger(__name__)


def _progress(job_id: str, store: JobStore, stage: PipelineStage, message: str, pct: float) -> None:
    store.update(job_id, stage=stage, message=message, progress=pct)


def run_documentary_pipeline(job_id: str) -> None:
    record = job_store.get(job_id)
    if not record:
        return

    topic = record.topic
    try:
        # --- Capture session (hackathon: CaptureSession API) ---
        _progress(job_id, job_store, PipelineStage.CAPTURING, "Creating research capture session…", 5)
        collection = create_job_collection(topic, job_id)
        job_store.update(job_id, collection_id=collection.id)

        capture = collection.create_capture_session(
            end_user_id=f"continuum-{job_id[:8]}",
            metadata={"topic": topic, "product": "continuum", "phase": "research"},
        )
        job_store.update(job_id, capture_session_id=capture.id, metadata={"capture_session_id": capture.id})

        # --- Discover ---
        _progress(job_id, job_store, PipelineStage.DISCOVERING, "Finding relevant YouTube sources…", 12)
        urls = discover_sources(topic, use_demo=record.use_demo_sources)

        # --- Upload ---
        def upload_cb(msg: str, i: int, n: int) -> None:
            pct = 15 + (25 * i / max(n, 1))
            _progress(job_id, job_store, PipelineStage.UPLOADING, msg, pct)

        min_sources = min(5, len(urls))
        if min_sources < 2:
            min_sources = min(2, len(urls))
        ingest = upload_sources(
            collection,
            urls,
            on_progress=upload_cb,
            min_distinct=min_sources,
        )
        sources = ingest.sources
        job_store.update(
            job_id,
            metadata={
                "source_urls": urls,
                "ingested_video_ids": [s.video_id for s in sources],
                "failed_uploads": ingest.failed_urls,
            },
        )

        # --- Index ---
        def index_cb(msg: str, i: int, n: int) -> None:
            pct = 40 + (25 * i / max(n, 1))
            _progress(job_id, job_store, PipelineStage.INDEXING, msg, pct)

        try:
            index_sources(collection, sources, on_progress=index_cb)
        except Exception as exc:
            raise RuntimeError(f"Indexing failed: {exc}") from exc

        # --- Director + scriptwriter (after index — scripts reference real sources) ---
        _progress(
            job_id,
            job_store,
            PipelineStage.PLANNING,
            "Director & scriptwriter crafting the documentary vision…",
            68,
        )
        num_chapters = min(5, max(2, len(sources)))
        production_script, chapters = plan_documentary(
            topic, num_chapters=num_chapters, sources=sources
        )
        fresh = job_store.get(job_id)
        job_store.update(
            job_id,
            metadata={
                **(fresh.metadata if fresh else {}),
                "film_title": production_script.blueprint.film_title,
                "logline": production_script.blueprint.logline,
                "tone": production_script.blueprint.tone,
                "scenes": [c.title for c in chapters],
            },
        )

        # --- Select clips ---
        _progress(job_id, job_store, PipelineStage.SELECTING_CLIPS, "Searching archive for best moments…", 75)
        selections = select_clips_for_chapters(
            collection, chapters, sources, topic=topic
        )

        # --- Narrate ---
        segments: list[ChapterSegment] = []
        total = len(selections)
        for i, (chapter, clip) in enumerate(selections, start=1):
            pct = 78 + (12 * i / total)
            _progress(
                job_id,
                job_store,
                PipelineStage.NARRATING,
                f"Generating voiceover {i}/{total}: {chapter.title}",
                pct,
            )
            audio_id, duration = generate_narration(collection, chapter)
            segments.append(
                ChapterSegment(
                    title=chapter.title,
                    narration=chapter.narration,
                    narration_audio_id=audio_id,
                    narration_duration=duration,
                    clip=clip,
                    pause_after_sec=chapter.pause_after_sec,
                )
            )

        # --- Compose ---
        _progress(job_id, job_store, PipelineStage.COMPOSING, "Assembling timeline & rendering stream…", 92)
        conn = get_connection()
        output = build_documentary(
            conn,
            collection,
            topic,
            segments,
            film_title=production_script.blueprint.film_title,
        )

        fresh = job_store.get(job_id)
        job_store.update(
            job_id,
            stage=PipelineStage.READY,
            message="Your documentary is ready to watch.",
            progress=100.0,
            stream_url=output["stream_url"],
            player_url=output["player_url"],
            metadata={
                **(fresh.metadata if fresh else {}),
                "duration_seconds": output["duration_seconds"],
                "chapters": [s.title for s in segments],
                "clips": [
                    {
                        "chapter": s.title,
                        "video_id": s.clip.video_id,
                        "start": s.clip.start,
                        "end": s.clip.end,
                    }
                    for s in segments
                ],
                "distinct_source_videos": output.get(
                    "distinct_source_videos",
                    len({s.clip.video_id for s in segments}),
                ),
                "used_compile_montage": output.get("used_compile_montage", False),
            },
        )
        logger.info("Job %s complete: %s", job_id, output["stream_url"])

    except Exception as exc:
        logger.error("Pipeline failed for %s: %s", job_id, exc)
        logger.debug(traceback.format_exc())
        job_store.update(
            job_id,
            stage=PipelineStage.FAILED,
            message="Documentary pipeline failed",
            error=str(exc),
        )
