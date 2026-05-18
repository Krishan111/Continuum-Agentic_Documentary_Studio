"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# continuum/backend/app/config.py -> continuum/
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # VideoDB — video ingest, index, search, voice, timeline (required)
    video_db_api_key: str = ""

    # OpenAI — chapter planning & narration scripts (required for best results)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # YouTube Data API v3 — video discovery (optional)
    youtube_api_key: str = ""

    continuum_host: str = "0.0.0.0"
    continuum_port: int = 8000
    continuum_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    continuum_max_source_videos: int = 8
    continuum_target_duration_sec: int = 300
    continuum_collection_prefix: str = "continuum"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.continuum_cors_origins.split(",") if o.strip()]

    @property
    def demos_path(self) -> Path:
        return ROOT_DIR / "demos" / "topics.json"

    @property
    def has_videodb(self) -> bool:
        return bool(self.video_db_api_key.strip())

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
