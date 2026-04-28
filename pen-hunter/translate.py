"""JP/KR -> EN translation via the Claude API.

Used post-dedup so we only spend tokens on listings we're about to alert
on. Returns a (title_en, description_en) pair: the title is a faithful
English rendering of the original, and the description is one short
sentence summarizing the listing for human triage in the alert.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Tuple

from anthropic import Anthropic, APIError

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

_client: Anthropic | None = None

_SYSTEM = (
    "You translate listing titles from Japanese or Korean into English for "
    "an English-speaking pen collector. Reply with strict JSON only, no "
    "prose, with two keys:\n"
    '  "title": a faithful English title (preserve brand names, models, '
    "colors, sizes; transliterate Japanese/Korean brand names if no English "
    'form exists),\n'
    '  "description": one short English sentence (max 20 words) summarizing '
    "the listing — material, condition hints, anything notable.\n"
    'Example: {"title": "Tactile Turn Slim Bolt Action Pen (Bronze)", '
    '"description": "Sharp pencil version, bronze finish, machined writing instrument."}'
)


def _get_client() -> Anthropic | None:
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            logger.error("ANTHROPIC_API_KEY not set in .env")
            return None
        _client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _parse_response(text: str) -> Tuple[str, str]:
    text = text.strip()
    # Tolerate fenced code blocks if Claude adds them despite instructions.
    fence = re.match(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    obj = json.loads(text)
    return str(obj.get("title", "")).strip(), str(obj.get("description", "")).strip()


def translate(original_title: str, source_hint: str = "") -> Tuple[str | None, str | None]:
    """Translate a listing title. Returns (title_en, description_en) or (None, None) on failure.

    `source_hint` is optional context like "mercari_jp" or "bunjang" that the
    model can use to disambiguate (e.g. JP vs KR script).
    """
    if not original_title.strip():
        return None, None
    client = _get_client()
    if client is None:
        return None, None

    user_msg = f"Source: {source_hint or 'unknown'}\nOriginal title: {original_title}"
    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
    except APIError as e:
        logger.warning("Claude translate API error: %s", e)
        return None, None

    if not resp.content:
        return None, None
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    try:
        title_en, desc_en = _parse_response(text)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Claude returned non-JSON translation (%s): %r", e, text[:200])
        return None, None
    return (title_en or None), (desc_en or None)
