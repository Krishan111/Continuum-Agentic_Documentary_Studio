"""Shared types for narration / voice generation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NarrationAudio:
    """Audio asset in VideoDB ready for timeline compose."""

    audio_id: str
    duration_sec: float
    provider: str
