# realtime_groups/backend/services/ai_moderator.py
# ---------------------------------------------------------------------------
# AI Moderation Service — Groq llama-3.3-70b-versatile
#
# Triggered by Supabase Database Webhooks every time a message or comment
# is INSERTed into the database. The webhook fires an HTTP POST to our
# /api/v1/webhooks/moderation endpoint, which drops the payload into a
# Celery task. This file contains the core analysis logic called by that task.
#
# Decision flow:
#   1. Send content to Groq for toxicity + spam scoring.
#   2. If toxicity_score >= threshold → auto-hide + karma penalty.
#   3. If spam_score >= threshold → auto-hide (no karma penalty).
#   4. Otherwise → no action (content is clean).
# ---------------------------------------------------------------------------

import json
import logging
from enum import Enum
from typing import Any

from groq import Groq

from realtime_groups.backend.core.config import social_settings
from realtime_groups.backend.core.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# ─── Moderation verdict ───────────────────────────────────────────────────────

class ModerationVerdict(str, Enum):
    CLEAN   = "clean"
    SPAM    = "spam"
    TOXIC   = "toxic"


MODERATION_PROMPT = """You are a strict content moderator for a professional founder community.
Analyze the following message and return a JSON object with these fields:
- toxicity_score: float from 0.0 to 1.0 (1.0 = extremely toxic, harmful, or hateful)
- spam_score: float from 0.0 to 1.0 (1.0 = clear spam, promotional noise, or repetitive junk)
- verdict: one of "clean", "spam", or "toxic"
- reason: one sentence explaining the verdict

Message to analyze:
\"\"\"
{content}
\"\"\"

Respond ONLY with valid JSON. No preamble, no explanation outside the JSON."""


def moderate_content(
    content: str,
    table: str,
    record_id: str,
    author_id: str,
) -> dict[str, Any]:
    """
    Runs AI moderation on a piece of content using Groq.

    Args:
        content:   The raw text of the message or comment.
        table:     "messages" or "comments" — determines which table to update.
        record_id: UUID of the row to potentially hide.
        author_id: UUID of the content author (for karma penalties).

    Returns:
        A dict with: verdict, toxicity_score, spam_score, reason, action_taken.
    """
    client = Groq(api_key=social_settings.GROQ_API_KEY)

    try:
        chat_response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": MODERATION_PROMPT.format(content=content[:2000]),  # Guard token limit
                }
            ],
            temperature=0.0,  # Deterministic scoring
            max_tokens=256,
            response_format={"type": "json_object"},
        )
    except Exception as groq_err:
        logger.error("[Moderation] Groq API call failed for record=%s: %s", record_id, groq_err)
        # Fail open — do not hide content if the AI is unavailable
        return {"verdict": ModerationVerdict.CLEAN, "error": str(groq_err), "action_taken": "none"}

    raw_text = chat_response.choices[0].message.content or "{}"

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.error("[Moderation] Failed to parse Groq JSON response: %s", raw_text)
        return {"verdict": ModerationVerdict.CLEAN, "error": "json_parse_error", "action_taken": "none"}

    toxicity_score: float = float(result.get("toxicity_score", 0.0))
    spam_score: float     = float(result.get("spam_score", 0.0))
    verdict: str          = result.get("verdict", ModerationVerdict.CLEAN)
    reason: str           = result.get("reason", "")

    action_taken = "none"

    # ── Auto-hide logic ──────────────────────────────────────────────────────
    if toxicity_score >= social_settings.MODERATION_TOXICITY_THRESHOLD or verdict == ModerationVerdict.TOXIC:
        _hide_content(table, record_id)
        _deduct_karma(author_id)
        action_taken = "hidden_and_penalized"
        logger.warning(
            "[Moderation] TOXIC content hidden. record=%s author=%s score=%.2f reason=%s",
            record_id, author_id, toxicity_score, reason,
        )

    elif spam_score >= 0.85 or verdict == ModerationVerdict.SPAM:
        _hide_content(table, record_id)
        action_taken = "hidden_spam"
        logger.warning(
            "[Moderation] SPAM content hidden. record=%s author=%s score=%.2f",
            record_id, author_id, spam_score,
        )

    return {
        "verdict": verdict,
        "toxicity_score": toxicity_score,
        "spam_score": spam_score,
        "reason": reason,
        "action_taken": action_taken,
        "record_id": record_id,
        "table": table,
    }


def _hide_content(table: str, record_id: str) -> None:
    """Marks a message or comment as hidden in the database."""
    sb = get_supabase()
    try:
        sb.table(table).update({"is_hidden": True}).eq("id", record_id).execute()
    except Exception as e:
        logger.error("[Moderation] Failed to hide %s record=%s: %s", table, record_id, e)


def _deduct_karma(author_id: str) -> None:
    """Applies a karma penalty to the content author."""
    # Import here to avoid circular at module load time
    from realtime_groups.backend.services.reputation_engine import add_karma
    try:
        add_karma(author_id, social_settings.MODERATION_KARMA_PENALTY, "toxic_content_auto_moderated")
    except Exception as e:
        logger.error("[Moderation] Failed to deduct karma for author=%s: %s", author_id, e)
