"""Backward-compatible shim — use app.voice.videodb_sandbox instead."""

from app.voice.videodb_sandbox import ensure_sandbox_id, generate as generate_voice_on_sandbox

__all__ = ["ensure_sandbox_id", "generate_voice_on_sandbox"]
