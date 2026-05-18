"""Continuum API — AI Documentary Engine."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

from app.config import ROOT_DIR

# continuum/.env — must load before videodb (tqdm) and logging setup
load_dotenv(ROOT_DIR / ".env")

from app.runtime import bootstrap_runtime

bootstrap_runtime()

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.jobs import job_store
from app.agents.prompt_optimizer import optimize_prompt
from app.models import (
    CreateDocumentaryRequest,
    DocumentaryJobResponse,
    OptimizePromptRequest,
    OptimizePromptResponse,
    PipelineStage,
)
from app.pipeline.orchestrator import run_documentary_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("continuum")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    if not settings.video_db_api_key:
        logger.warning("VIDEO_DB_API_KEY is not set — video pipeline will fail")
    if not settings.openai_api_key:
        logger.warning(
            "OPENAI_API_KEY is not set — using rule-based chapter plans only"
        )
    yield


app = FastAPI(
    title="Continuum",
    description="AI Documentary Engine powered by VideoDB",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_pipeline_thread(job_id: str) -> None:
    run_documentary_pipeline(job_id)


@app.get("/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        "service": "continuum",
        "videodb_configured": s.has_videodb,
        "openai_configured": s.has_openai,
        "openai_model": s.openai_model,
    }


@app.post("/api/optimize-prompt", response_model=OptimizePromptResponse)
def optimize_user_prompt(body: OptimizePromptRequest):
    original = body.prompt.strip()
    try:
        optimized = optimize_prompt(original)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("optimize-prompt failed")
        raise HTTPException(
            status_code=500,
            detail="Could not optimize prompt. Try again.",
        ) from exc
    return OptimizePromptResponse(
        original=original,
        optimized=optimized,
        word_count=len(optimized.split()),
        char_count=len(optimized),
    )


@app.post("/api/documentaries", response_model=DocumentaryJobResponse)
def create_documentary(body: CreateDocumentaryRequest, background_tasks: BackgroundTasks):
    record = job_store.create(body.topic, use_demo_sources=body.use_demo_sources)
    background_tasks.add_task(_run_pipeline_thread, record.job_id)
    return DocumentaryJobResponse(**job_store.to_response(record))


@app.get("/api/documentaries/{job_id}", response_model=DocumentaryJobResponse)
def get_documentary(job_id: str):
    record = job_store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    return DocumentaryJobResponse(**job_store.to_response(record))


@app.post("/api/documentaries/{job_id}/retry", response_model=DocumentaryJobResponse)
def retry_documentary(job_id: str, background_tasks: BackgroundTasks):
    record = job_store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    job_store.update(
        job_id,
        stage=PipelineStage.QUEUED,
        message="Retrying…",
        progress=0,
        error=None,
        stream_url=None,
        player_url=None,
    )
    background_tasks.add_task(_run_pipeline_thread, job_id)
    record = job_store.get(job_id)
    return DocumentaryJobResponse(**job_store.to_response(record))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.continuum_host,
        port=settings.continuum_port,
        reload=True,
    )
