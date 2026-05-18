"""Creative planning: director + scriptwriter → production-ready chapter plans."""



from __future__ import annotations



import logging

from dataclasses import dataclass



from app.agents.creative_types import ProductionScript, SourceSummary

from app.agents.director import create_blueprint

from app.agents.scriptwriter import write_script

from app.pipeline.ingest import IngestedVideo



logger = logging.getLogger(__name__)





@dataclass

class ChapterPlan:

    """One scene in the final documentary (script + search hints)."""



    title: str

    narration: str

    search_query: str

    visual_direction: str = ""

    director_note: str = ""

    pause_after_sec: float = 1.0

    scene_number: int = 0

    preferred_source_index: int = 0



    @classmethod

    def from_scene(cls, scene, *, preferred_source_index: int | None = None) -> ChapterPlan:

        idx = (
            preferred_source_index
            if preferred_source_index is not None
            else scene.preferred_source_index
        )

        return cls(

            title=scene.title,

            narration=scene.narration,

            search_query=scene.search_query,

            visual_direction=scene.visual_direction,

            director_note=scene.director_note,

            pause_after_sec=scene.pause_after_sec,

            scene_number=scene.scene_number,

            preferred_source_index=idx,

        )





def _sources_to_summaries(sources: list[IngestedVideo]) -> list[SourceSummary]:

    return [

        SourceSummary(

            index=i,

            title=s.title,

            length_sec=s.length,

            youtube_url=s.youtube_url,

        )

        for i, s in enumerate(sources)

    ]





def plan_documentary(

    topic: str,

    *,

    num_chapters: int = 5,

    sources: list[IngestedVideo] | None = None,

) -> tuple[ProductionScript, list[ChapterPlan]]:

    """

    Director defines vision → scriptwriter writes scenes → chapter plans for pipeline.

    Planning after ingest/index so scripts reference real uploaded sources.

    """

    summaries = _sources_to_summaries(sources) if sources else None

    blueprint = create_blueprint(topic, sources=summaries)

    script = write_script(

        topic,

        blueprint,

        num_scenes=num_chapters,

        sources=summaries,

    )



    chapters: list[ChapterPlan] = []

    n_src = len(sources) if sources else num_chapters

    for scene in script.scenes:

        pref = scene.preferred_source_index % max(n_src, 1) if n_src else 0
        chapters.append(ChapterPlan.from_scene(scene, preferred_source_index=pref))



    logger.info(

        "Creative plan ready: %r, %d scenes",

        blueprint.film_title,

        len(chapters),

    )

    return script, chapters





def plan_chapters(

    topic: str,

    *,

    num_chapters: int = 5,

    sources: list[IngestedVideo] | None = None,

) -> list[ChapterPlan]:

    """Backward-compatible entry: returns chapter plans only."""

    _, chapters = plan_documentary(

        topic, num_chapters=num_chapters, sources=sources

    )

    return chapters


