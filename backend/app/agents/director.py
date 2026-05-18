"""Documentary director agent — defines narrative vision before scripting."""

from __future__ import annotations

import json
import logging

from openai import OpenAI

from app.agents.creative_types import DocumentaryBlueprint, SourceSummary
from app.config import get_settings

logger = logging.getLogger(__name__)


def _fallback_blueprint(topic: str) -> DocumentaryBlueprint:
    return DocumentaryBlueprint(
        film_title=topic[:80],
        logline=f"An investigative documentary exploring {topic}.",
        tone="authoritative, cinematic, human",
        narrative_arc=(
            "Open with stakes → establish context → show evidence and lived experience → "
            "explain mechanisms → close with implications and a forward-looking question."
        ),
        opening_hook=f"What is really happening with {topic}—and why does it matter now?",
        closing_line="The story is still being written. What we do next will define the chapter after this one.",
    )


def create_blueprint(
    topic: str,
    *,
    sources: list[SourceSummary] | None = None,
) -> DocumentaryBlueprint:
    """Craft director's vision; uses source titles when available (post-ingest)."""
    settings = get_settings()
    if not settings.has_openai:
        logger.warning("OPENAI_API_KEY not set — using template director blueprint")
        return _fallback_blueprint(topic)

    source_lines = ""
    if sources:
        lines = [
            f"  - Source {s.index}: {s.title[:100]} ({s.length_sec:.0f}s)"
            for s in sources
        ]
        source_lines = "\nArchival sources already ingested:\n" + "\n".join(lines)

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = f"""You are an award-winning documentary director (Ken Burns meets modern explainer).

Topic: "{topic}"
{source_lines}

Create the CREATIVE BRIEF for a 4–6 minute short documentary built from YouTube archival footage plus AI narration.

Return JSON object with:
- film_title: compelling title (max 10 words)
- logline: one sentence pitch
- tone: 3–5 adjectives/phrases for voice and editing
- narrative_arc: 3–5 sentences describing act structure (hook → context → evidence → human stakes → resolution)
- opening_hook: first sentence the narrator will speak (grab attention, no clichés)
- closing_line: final sentence of the film (memorable, not cheesy)
- audience: who this is for

Rules:
- Must feel like ONE coherent film, not a list of facts.
- Arc should guide which footage belongs in each act.
- Do NOT write full scene scripts here — only vision.

JSON only, no markdown."""

    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.65,
        )
        raw = (resp.choices[0].message.content or "{}").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        blueprint = DocumentaryBlueprint(
            film_title=str(data.get("film_title", topic))[:120],
            logline=str(data.get("logline", ""))[:500],
            tone=str(data.get("tone", "cinematic"))[:200],
            narrative_arc=str(data.get("narrative_arc", ""))[:1500],
            opening_hook=str(data.get("opening_hook", ""))[:500],
            closing_line=str(data.get("closing_line", ""))[:500],
            audience=str(data.get("audience", "general"))[:120],
        )
        logger.info("Director blueprint: %r", blueprint.film_title)
        return blueprint
    except Exception as exc:
        logger.warning("Director agent failed, using fallback: %s", exc)
        return _fallback_blueprint(topic)
