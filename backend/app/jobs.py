"""In-memory job store for documentary pipeline runs."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.models import PipelineStage, STAGE_LABELS, STAGE_ORDER, StageInfo


@dataclass
class JobRecord:
    job_id: str
    topic: str
    stage: PipelineStage = PipelineStage.QUEUED
    message: str = ""
    progress: float = 0.0
    stream_url: Optional[str] = None
    player_url: Optional[str] = None
    collection_id: Optional[str] = None
    capture_session_id: Optional[str] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    use_demo_sources: bool = False


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def create(self, topic: str, use_demo_sources: bool = False) -> JobRecord:
        job_id = str(uuid.uuid4())
        record = JobRecord(
            job_id=job_id,
            topic=topic.strip(),
            use_demo_sources=use_demo_sources,
        )
        with self._lock:
            self._jobs[job_id] = record
        return record

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        stage: Optional[PipelineStage] = None,
        message: str | None = None,
        progress: float | None = None,
        stream_url: str | None = None,
        player_url: str | None = None,
        collection_id: str | None = None,
        capture_session_id: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Optional[JobRecord]:
        with self._lock:
            record = self._jobs.get(job_id)
            if not record:
                return None
            if stage is not None:
                record.stage = stage
            if message is not None:
                record.message = message
            if progress is not None:
                record.progress = progress
            if stream_url is not None:
                record.stream_url = stream_url
            if player_url is not None:
                record.player_url = player_url
            if collection_id is not None:
                record.collection_id = collection_id
            if capture_session_id is not None:
                record.capture_session_id = capture_session_id
            if error is not None:
                record.error = error
            if metadata is not None:
                record.metadata.update(metadata)
            return record

    def build_stage_list(self, record: JobRecord) -> list[StageInfo]:
        stages: list[StageInfo] = []
        failed = record.stage == PipelineStage.FAILED
        if record.stage in STAGE_ORDER:
            current_idx = STAGE_ORDER.index(record.stage)
        elif failed:
            # Mark progress at last known active step from progress heuristic
            current_idx = min(
                len(STAGE_ORDER) - 2,
                max(0, int(record.progress / 12)),
            )
        else:
            current_idx = len(STAGE_ORDER) - 1

        for i, stage in enumerate(STAGE_ORDER):
            if stage == PipelineStage.READY:
                continue
            if failed and i > current_idx:
                status = "pending"
            elif record.stage == PipelineStage.READY:
                status = "done"
            elif i < current_idx:
                status = "done"
            elif i == current_idx and not failed:
                status = "active"
            elif failed and i == current_idx:
                status = "failed"
            else:
                status = "pending"
            stages.append(
                StageInfo(id=stage.value, label=STAGE_LABELS[stage], status=status)
            )

        if record.stage == PipelineStage.READY:
            stages.append(
                StageInfo(
                    id=PipelineStage.READY.value,
                    label=STAGE_LABELS[PipelineStage.READY],
                    status="done",
                )
            )
        else:
            stages.append(
                StageInfo(
                    id=PipelineStage.READY.value,
                    label=STAGE_LABELS[PipelineStage.READY],
                    status="pending",
                )
            )
        return stages

    def to_response(self, record: JobRecord) -> dict:
        return {
            "job_id": record.job_id,
            "topic": record.topic,
            "stage": record.stage.value,
            "stage_label": STAGE_LABELS.get(record.stage, record.stage.value),
            "progress": record.progress,
            "stages": [s.model_dump() for s in self.build_stage_list(record)],
            "message": record.message,
            "stream_url": record.stream_url,
            "player_url": record.player_url,
            "collection_id": record.collection_id,
            "capture_session_id": record.capture_session_id,
            "error": record.error,
            "metadata": record.metadata,
        }


job_store = JobStore()
