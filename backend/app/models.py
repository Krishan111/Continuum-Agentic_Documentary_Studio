"""Shared API and pipeline data models."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class PipelineStage(str, Enum):
    QUEUED = "queued"
    CAPTURING = "capturing"
    DISCOVERING = "discovering"
    UPLOADING = "uploading"
    INDEXING = "indexing"
    PLANNING = "planning"
    SELECTING_CLIPS = "selecting_clips"
    NARRATING = "narrating"
    COMPOSING = "composing"
    READY = "ready"
    FAILED = "failed"


STAGE_ORDER: list[PipelineStage] = [
    PipelineStage.QUEUED,
    PipelineStage.CAPTURING,
    PipelineStage.DISCOVERING,
    PipelineStage.UPLOADING,
    PipelineStage.INDEXING,
    PipelineStage.PLANNING,
    PipelineStage.SELECTING_CLIPS,
    PipelineStage.NARRATING,
    PipelineStage.COMPOSING,
    PipelineStage.READY,
]


STAGE_LABELS: dict[PipelineStage, str] = {
    PipelineStage.QUEUED: "Queued",
    PipelineStage.CAPTURING: "Starting research capture",
    PipelineStage.DISCOVERING: "Discovering source videos",
    PipelineStage.UPLOADING: "Uploading to VideoDB",
    PipelineStage.INDEXING: "Indexing visuals & speech",
    PipelineStage.PLANNING: "Director & scriptwriter",
    PipelineStage.SELECTING_CLIPS: "Selecting best clips",
    PipelineStage.NARRATING: "Generating narration",
    PipelineStage.COMPOSING: "Composing timeline",
    PipelineStage.READY: "Documentary ready",
    PipelineStage.FAILED: "Failed",
}


class CreateDocumentaryRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500)
    use_demo_sources: bool = Field(
        default=False,
        description="Use pre-validated demo URLs when available for this topic",
    )


class OptimizePromptRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000)


class OptimizePromptResponse(BaseModel):
    original: str
    optimized: str
    word_count: int
    char_count: int


class StageInfo(BaseModel):
    id: str
    label: str
    status: str  # pending | active | done | failed


class DocumentaryJobResponse(BaseModel):
    job_id: str
    topic: str
    stage: PipelineStage
    stage_label: str
    progress: float
    stages: list[StageInfo]
    message: str = ""
    stream_url: Optional[str] = None
    player_url: Optional[str] = None
    collection_id: Optional[str] = None
    capture_session_id: Optional[str] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
