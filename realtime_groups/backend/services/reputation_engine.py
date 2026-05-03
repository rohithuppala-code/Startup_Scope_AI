# realtime_groups/backend/services/reputation_engine.py
# ---------------------------------------------------------------------------
# Reputation Engine — karma scoring and badge assignment.
#
# This is the single authoritative place where karma mutations happen.
# All callers (arena_router, ai_moderator, etc.) import from here.
#
# IMPORTANT: All Supabase calls are synchronous (the SDK is sync-only).
# Callers from async FastAPI handlers MUST wrap calls with:
#   asyncio.get_running_loop().run_in_executor(None, some_reputation_fn, ...)
# Or use the provided async wrappers at the bottom of this file.
# ---------------------------------------------------------------------------

import asyncio
import logging
from typing import Optional

from realtime_groups.backend.core.config import social_settings
from realtime_groups.backend.core.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# ─── Badge definitions ───────────────────────────────────────────────────────
# Each badge is a tuple: (badge_id, label, condition_description)
# Conditions are checked after every karma mutation.
BADGE_DEFINITIONS = [
    ("serial_builder", "🏗️ Serial Builder", "Published 5+ ideas to the Arena"),
    ("karma_100",      "⚡ Rising Star",     "Reached 100 karma points"),
    ("karma_500",      "🚀 Thought Leader",  "Reached 500 karma points"),
    ("first_post",     "🌱 First Post",      "Published first idea to the Arena"),
    ("helpful_voter",  "👍 Helpful Voter",   "Cast 10+ votes on Arena ideas"),
]


# ─── Core karma mutation ─────────────────────────────────────────────────────

def add_karma(user_id: str, delta: int, reason: str) -> dict:
    """
    Atomically increments/decrements a user's karma_score in the profiles table.

    Args:
        user_id: UUID string of the target profile.
        delta:   Integer to add (use negatives for penalties).
        reason:  Human-readable audit string (logged, not stored).

    Returns:
        The updated profile row dict.

    Raises:
        ValueError: If the profile doesn't exist.
    """
    sb = get_supabase()

    # BUG FIX: .single() raises APIError when the profile row doesn't exist,
    # crashing the entire karma reward/penalty pipeline (arena voting, comments,
    # moderation all call this). Use .limit(1) for safe zero-row handling.
    fetch_resp = (
        sb.table("profiles")
        .select("id, karma_score, badges, username")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if not fetch_resp.data:
        logger.warning("[ReputationEngine] Profile not found for user_id=%s — skipping karma mutation.", user_id)
        return {"karma_score": 0, "badges": [], "id": user_id}

    profile = fetch_resp.data[0]
    current_karma: int = profile.get("karma_score", 0) or 0
    new_karma = max(0, current_karma + delta)  # Floor at 0; no negative karma

    update_resp = (
        sb.table("profiles")
        .update({"karma_score": new_karma})
        .eq("id", user_id)
        .execute()
    )

    logger.info(
        "[ReputationEngine] user=%s karma %d → %d (delta=%+d, reason=%s)",
        user_id, current_karma, new_karma, delta, reason,
    )

    # Run badge checks after every mutation
    updated_profile = update_resp.data[0] if update_resp.data else profile
    updated_profile["karma_score"] = new_karma
    _check_and_award_badges(user_id, updated_profile)

    return updated_profile


def _check_and_award_badges(user_id: str, profile: dict) -> None:
    """
    Inspects the current profile state and awards any newly-earned badges.
    Idempotent — re-awarding an already-held badge is a no-op.
    """
    sb = get_supabase()
    current_badges: list = profile.get("badges") or []
    new_badges = list(current_badges)
    karma = profile.get("karma_score", 0)

    # Count public posts for Serial Builder
    post_count_resp = (
        sb.table("posts")
        .select("id", count="exact")
        .eq("author_id", user_id)
        .execute()
    )
    post_count = post_count_resp.count or 0

    # Badge: First Post
    if post_count >= 1 and "first_post" not in new_badges:
        new_badges.append("first_post")
        logger.info("[ReputationEngine] Awarded badge 'first_post' to user=%s", user_id)

    # Badge: Serial Builder
    if post_count >= social_settings.SERIAL_BUILDER_THRESHOLD and "serial_builder" not in new_badges:
        new_badges.append("serial_builder")
        logger.info("[ReputationEngine] Awarded badge 'serial_builder' to user=%s", user_id)

    # Badge: Rising Star (100 karma)
    if karma >= 100 and "karma_100" not in new_badges:
        new_badges.append("karma_100")
        logger.info("[ReputationEngine] Awarded badge 'karma_100' to user=%s", user_id)

    # Badge: Thought Leader (500 karma)
    if karma >= 500 and "karma_500" not in new_badges:
        new_badges.append("karma_500")
        logger.info("[ReputationEngine] Awarded badge 'karma_500' to user=%s", user_id)

    if new_badges != current_badges:
        sb.table("profiles").update({"badges": new_badges}).eq("id", user_id).execute()


# ─── Async wrappers (for use inside FastAPI async handlers) ──────────────────

async def async_add_karma(user_id: str, delta: int, reason: str) -> dict:
    """Async wrapper around add_karma for use in async FastAPI route handlers."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, add_karma, user_id, delta, reason)


# ─── Convenience helpers (used by routers) ───────────────────────────────────

async def reward_upvote(author_id: str) -> None:
    """Reward the post author when their post receives an upvote."""
    await async_add_karma(author_id, social_settings.KARMA_UPVOTE, "post_upvoted")


async def reward_comment(commenter_id: str) -> None:
    """Reward a user for leaving a comment."""
    await async_add_karma(commenter_id, social_settings.KARMA_COMMENT, "comment_posted")


async def reward_publish(author_id: str) -> None:
    """Reward a user for publishing their first/nth idea to the Arena."""
    await async_add_karma(author_id, social_settings.KARMA_POST, "idea_published")


async def penalize_toxic(user_id: str) -> None:
    """Deduct karma from a user whose content was flagged as highly toxic."""
    await async_add_karma(user_id, social_settings.MODERATION_KARMA_PENALTY, "toxic_content")
