"""Shared creative plan types for director → scriptwriter → production."""



from __future__ import annotations



from dataclasses import dataclass, field





@dataclass

class SourceSummary:

    index: int

    title: str

    length_sec: float

    youtube_url: str = ""





@dataclass

class DocumentaryBlueprint:

    """Director's vision for the full film."""



    film_title: str

    logline: str

    tone: str

    narrative_arc: str

    opening_hook: str

    closing_line: str

    audience: str = "general"





@dataclass

class ScriptScene:

    """One scripted scene: VO + visual direction + pacing."""



    scene_number: int

    title: str

    director_note: str

    narration: str

    visual_direction: str

    search_query: str

  # Seconds of intentional quiet B-roll after VO ends (breathing room)

    pause_after_sec: float = 1.2

    target_vo_seconds: float = 18.0
    preferred_source_index: int = 0

    @property

    def search_queries(self) -> list[str]:

        """Primary + fallback search strings for VideoDB."""

        parts = [self.search_query.strip(), self.visual_direction.strip()]

        return [p for p in parts if p]





@dataclass

class ProductionScript:

    blueprint: DocumentaryBlueprint

    scenes: list[ScriptScene] = field(default_factory=list)


