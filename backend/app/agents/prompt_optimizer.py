"""Expand user topic into a production-ready documentary brief (max 499 characters)."""

from __future__ import annotations

import logging
import re

from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

# Must fit CreateDocumentaryRequest.topic max_length=500
MAX_OPTIMIZED_CHARS = 499
# Ask the model to stay below this so we rarely need to trim
TARGET_MAX_CHARS = 380

# e.g. "...and the cultural." — has a period but is not a finished thought
_INCOMPLETE_SENTENCE = re.compile(
    r"\b(and|or|but)\s+(?:the\s+|a\s+|an\s+)?[A-Za-z]{2,20}\s*\.?$",
    re.IGNORECASE,
)


def _is_complete_sentence(sentence: str) -> bool:
    s = sentence.strip()
    if not s:
        return False
    if s[-1] not in ".!?":
        return False
    body = s[:-1].strip()
    if _INCOMPLETE_SENTENCE.search(body + "."):
        return False
    if re.search(r",\s+(and|or)\s+", body, re.I) and len(body.split()) < 12:
        tail = body.split(",")[-1].strip()
        if _INCOMPLETE_SENTENCE.search(tail + "."):
            return False
    return True


def _split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries while keeping punctuation on each sentence."""
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _trim_to_complete_sentences(text: str, limit: int = MAX_OPTIMIZED_CHARS) -> str:
    """
    Keep only full sentences that fit within limit.
    Never return a fragment ending mid-clause (e.g. 'and the cultural.').
    Always validates completeness even when the draft is already under the limit.
    """
    text = text.strip()
    if not text:
        return text

    sentences = _split_sentences(text)
    if not sentences:
        return text[:limit].rstrip(".,; ") + "."

    kept: list[str] = []
    length = 0
    for sentence in sentences:
        if not _is_complete_sentence(sentence):
            continue
        add_len = len(sentence) + (1 if kept else 0)
        if length + add_len <= limit:
            kept.append(sentence)
            length += add_len
        else:
            break

    if kept:
        while kept and not _is_complete_sentence(kept[-1]):
            kept.pop()
        result = " ".join(kept)
        if result and result[-1] not in ".!?":
            result += "."
        return result

    # First sentence alone is too long — hard cut at last sentence end before limit
    chunk = text[:limit]
    for end in range(len(chunk) - 1, max(0, limit - 120), -1):
        if chunk[end] in ".!?":
            return chunk[: end + 1].strip()
    # Last resort: cut at last comma or semicolon, then close sentence
    for sep in (", ", "; "):
        idx = chunk.rfind(sep)
        if idx > limit * 0.5:
            return chunk[:idx].rstrip(".,; ") + "."
    return chunk.rstrip(".,; ") + "."


def _fallback_optimize(prompt: str) -> str:
    """Light expansion when OpenAI is unavailable."""
    base = prompt.strip()
    brief = (
        f"A documentary on {base}, tracing the key mission milestones, the science "
        f"and engineering behind them, and why the story matters today—with "
        f"archival launch and mission-control footage in a clear, cinematic tone."
    )
    return _trim_to_complete_sentences(brief)


def _build_user_message(original: str, *, compress: bool = False) -> str:
    original_len = len(original)
    if compress:
        return f"""The draft below is TOO LONG. Shorten it to at most {TARGET_MAX_CHARS} characters.

Rules:
- Keep the same subject and intent as the user's original topic
- Use 2–3 SHORT complete sentences only
- Every sentence must be grammatically complete and end with . ! or ?
- Do NOT trail off or end mid-phrase
- Omit extra detail rather than cutting a sentence in half

User's original topic:
\"\"\"{original}\"\"\"

Draft to shorten:
\"\"\"{{DRAFT}}\"\"\"

Return only the shortened prompt."""

    return f"""Original topic from the user:
\"\"\"{original}\"\"\"

Write a better documentary topic prompt for an AI film pipeline.

Requirements:
- Same subject, angle, and intent as the user (do not change the topic)
- More specific and useful than the original ({original_len} characters) — add timeframe, place, tone, and what viewers should learn
- Use concrete nouns that help find YouTube archival footage
- Write exactly 2–3 COMPLETE sentences as one short paragraph
- CRITICAL: The entire text must be at most {TARGET_MAX_CHARS} characters and must read as a finished thought
- CRITICAL: End on a complete sentence. Never stop mid-clause (bad: "and the cultural." — good: "and its cultural impact.")
- Prefer clarity and completeness over listing every fact. Omit lower-priority details if needed.

Return only the optimized prompt text, nothing else."""


def _call_openai(client: OpenAI, model: str, system: str, user: str) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.45,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^[\"']|[\"']$", "", raw)
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return raw


def optimize_prompt(user_prompt: str) -> str:
    """
    Return a clearer, more detailed topic brief.
    Preserves user intent; never longer than MAX_OPTIMIZED_CHARS; always complete sentences.
    """
    original = user_prompt.strip()
    if len(original) < 3:
        raise ValueError("Enter at least 3 characters before optimizing.")

    settings = get_settings()
    if not settings.has_openai:
        logger.warning("OPENAI_API_KEY not set — using template prompt expansion")
        return _fallback_optimize(original)

    original_len = len(original)
    client = OpenAI(api_key=settings.openai_api_key)
    system = (
        "You refine documentary topic prompts for an AI film pipeline. "
        "You always write grammatically complete sentences. "
        "Output plain text only—no markdown, no labels."
    )

    try:
        user_msg = _build_user_message(original)
        raw = _call_openai(client, settings.openai_model, system, user_msg)
        if not raw:
            return _fallback_optimize(original)

        if len(raw) > MAX_OPTIMIZED_CHARS:
            logger.info(
                "Optimized draft %d chars — asking model to compress", len(raw)
            )
            compress_msg = _build_user_message(original, compress=True).replace(
                "{DRAFT}", raw
            )
            raw = _call_openai(
                client, settings.openai_model, system, compress_msg
            ) or raw

        result = _trim_to_complete_sentences(raw)

        if len(result) > MAX_OPTIMIZED_CHARS:
            result = _trim_to_complete_sentences(result, MAX_OPTIMIZED_CHARS)

        sentences_out = _split_sentences(result)
        if (
            not result
            or not sentences_out
            or any(not _is_complete_sentence(s) for s in sentences_out)
        ):
            result = _fallback_optimize(original)

        logger.info(
            "Optimized prompt: %d → %d chars (%d sentences)",
            original_len,
            len(result),
            len(_split_sentences(result)),
        )
        return result
    except Exception as exc:
        logger.warning("Prompt optimization failed: %s", exc)
        return _fallback_optimize(original)
