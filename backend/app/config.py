"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# continuum/backend/app/config.py -> continuum/
ROOT_DIR = Path(__file__).resolve().parents[2]

# Set CONTINUUM_VOICE_PROVIDER in .env (see README)
VALID_VOICE_PROVIDERS = frozenset(
    {"videodb_default", "videodb_sandbox", "openai_tts"}
)


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

    # Voice provider — single switch for judges (see README)
    # videodb_default | videodb_sandbox | openai_tts
    continuum_voice_provider: str = ""

    # VideoDB hosted voice (CONTINUUM_VOICE_PROVIDER=videodb_default)
    video_db_default_voice_name: str = "Default"

    # OpenAI TTS (CONTINUUM_VOICE_PROVIDER=openai_tts) — recommended for evaluation without VideoDB voice credits
    openai_tts_model: str = "tts-1-hd"
    openai_tts_voice: str = "onyx"
    openai_tts_speed: float = 1.0

    # VideoDB Sandbox OmniVoice (CONTINUUM_VOICE_PROVIDER=videodb_sandbox)
    video_db_sandbox_id: str = ""
    video_db_sandbox_auto_create: bool = False
    video_db_sandbox_tier: str = "small"
    video_db_sandbox_ready_timeout: int = 300
    video_db_voice_job_timeout: int = 900
    video_db_voice_instructions: str = (
        "Clear, warm documentary narrator voice, moderate pace, authoritative and engaging"
    )

    # Deprecated — use CONTINUUM_VOICE_PROVIDER=videodb_sandbox instead
    video_db_use_sandbox_voice: bool = False

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

    @property
    def resolved_voice_provider(self) -> str:
        """
        Active narration backend.
        Priority: CONTINUUM_VOICE_PROVIDER → legacy VIDEO_DB_USE_SANDBOX_VOICE → openai_tts.
        """
        explicit = (self.continuum_voice_provider or "").strip().lower()
        if explicit:
            return explicit
        if self.video_db_use_sandbox_voice:
            return "videodb_sandbox"
        return "openai_tts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
