"""Scriptwriter agent — scene-by-scene VO and visual direction from director brief."""



from __future__ import annotations



import json

import logging



from openai import OpenAI



from app.agents.creative_types import (

    DocumentaryBlueprint,

    ProductionScript,

    ScriptScene,

    SourceSummary,

)

from app.config import get_settings



logger = logging.getLogger(__name__)



WORDS_PER_SECOND = 2.35

MAX_WORDS_PER_SCENE = 52  # ~22s VO max





def _fallback_scenes(topic: str, n: int, blueprint: DocumentaryBlueprint) -> list[ScriptScene]:

    templates = [

        ("The Stakes", blueprint.opening_hook, "wide establishing shots, tension"),

        ("How We Got Here", "To understand the present, we trace the forces that set this in motion.", "archive timeline context"),

        ("What the Evidence Shows", "Cameras and data tell a story words alone cannot.", "maps charts on-site footage"),

        ("Lives on the Line", "Behind every statistic is a community living the consequences.", "people places emotion"),

        ("What Comes Next", blueprint.closing_line, "forward-looking horizon reflection"),

    ]

    scenes: list[ScriptScene] = []

    for i in range(n):

        title, narr, visual = templates[i % len(templates)]

        scenes.append(

            ScriptScene(

                scene_number=i + 1,

                title=title,

                director_note=f"Scene {i + 1} of arc for {topic}",

                narration=narr if i == 0 or i == n - 1 else f"{narr} This defines our chapter on {topic}.",

                visual_direction=visual,

                search_query=f"{topic} {title} documentary",

                pause_after_sec=1.0 if i < n - 1 else 1.5,

                target_vo_seconds=18.0,

            )

        )

    return scenes





def _trim_narration(text: str, max_words: int = MAX_WORDS_PER_SCENE) -> str:

    words = text.split()

    if len(words) <= max_words:

        return text.strip()

    return " ".join(words[:max_words]).rstrip(".,;") + "."





def write_script(

    topic: str,

    blueprint: DocumentaryBlueprint,

    *,

    num_scenes: int,

    sources: list[SourceSummary] | None = None,

) -> ProductionScript:

    """Write ordered scenes aligned to director blueprint."""

    settings = get_settings()

    if not settings.has_openai:

        scenes = _fallback_scenes(topic, num_scenes, blueprint)

        return ProductionScript(blueprint=blueprint, scenes=scenes)



    source_block = ""

    if sources:

        source_block = "\nAssign each scene a preferred_source_index (0-based) rotating through:\n"

        source_block += "\n".join(

            f"  [{s.index}] {s.title[:90]}" for s in sources

        )



    client = OpenAI(api_key=settings.openai_api_key)

    prompt = f"""You are a documentary scriptwriter. Director's brief:



Film title: {blueprint.film_title}

Logline: {blueprint.logline}

Tone: {blueprint.tone}

Narrative arc: {blueprint.narrative_arc}

Opening hook (use for scene 1): {blueprint.opening_hook}

Closing line (use for final scene): {blueprint.closing_line}

Topic: {topic}

{source_block}



Write exactly {num_scenes} scenes as JSON array. Each scene object:

- scene_number: int (1..{num_scenes})

- title: short scene title (max 5 words)

- director_note: 1 sentence — purpose in the arc (for editor)

- narration: voiceover ONLY, 35–48 words (complete sentences; no stage directions). Scene 1 must open with the hook. Final scene must end on the closing line.

- visual_direction: what the viewer should SEE (concrete b-roll: locations, subjects, actions)

- search_query: one line for archival search (nouns, verbs, places)

- pause_after_sec: 0.8–1.5 seconds of quiet after VO (number)

- target_vo_seconds: 14–20 (number)

- preferred_source_index: int 0..{max(0, (len(sources) or num_scenes) - 1)} — which upload fits this scene best



Rules:

- ONE narrator voice throughout; scenes must flow when read back-to-back.

- No repeated opening phrases between scenes.

- Visual direction must match narration (don't narrate X while direction says unrelated Y).

- Build tension then release; no generic filler.



JSON only, no markdown."""



    try:

        resp = client.chat.completions.create(

            model=settings.openai_model,

            messages=[{"role": "user", "content": prompt}],

            temperature=0.72,

        )

        raw = (resp.choices[0].message.content or "[]").strip()

        if raw.startswith("```"):

            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        data = json.loads(raw)

        if isinstance(data, dict) and "scenes" in data:

            data = data["scenes"]



        scenes: list[ScriptScene] = []

        for item in data[:num_scenes]:

            narr = _trim_narration(str(item.get("narration", "")))

            scenes.append(

                ScriptScene(

                    scene_number=int(item.get("scene_number", len(scenes) + 1)),

                    title=str(item.get("title", f"Scene {len(scenes) + 1}"))[:80],

                    director_note=str(item.get("director_note", ""))[:300],

                    narration=narr,

                    visual_direction=str(item.get("visual_direction", ""))[:400],

                    search_query=str(item.get("search_query", topic))[:200],

                    pause_after_sec=float(item.get("pause_after_sec", 1.0)),

                    target_vo_seconds=float(item.get("target_vo_seconds", 18.0)),
                    preferred_source_index=max(
                        0,
                        min(
                            int(item.get("preferred_source_index", len(scenes))),
                            max((len(sources) if sources else num_scenes), 1) - 1,
                        ),
                    ),
                )

            )

        if scenes:

            scenes[0].narration = _trim_narration(

                scenes[0].narration or blueprint.opening_hook

            )

            scenes[-1].narration = _trim_narration(

                scenes[-1].narration or blueprint.closing_line

            )

            logger.info("Scriptwriter produced %d scenes", len(scenes))

            return ProductionScript(blueprint=blueprint, scenes=scenes)

    except Exception as exc:

        logger.warning("Scriptwriter failed, using fallback: %s", exc)



    return ProductionScript(

        blueprint=blueprint,

        scenes=_fallback_scenes(topic, num_scenes, blueprint),

    )


