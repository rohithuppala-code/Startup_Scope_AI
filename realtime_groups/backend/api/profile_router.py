# realtime_groups/backend/api/profile_router.py
# ---------------------------------------------------------------------------
# Phase 1: Identity Graph — Profile endpoints
#
# GET  /api/v1/profiles/{username}          — Public founder card + badges
# PUT  /api/v1/profiles/me                  — Update own profile
# GET  /api/v1/profiles/{user_id}/validations — Public "published to Arena" portfolio
# ---------------------------------------------------------------------------

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header, status

from realtime_groups.backend.core.supabase_client import get_supabase
from realtime_groups.backend.schemas.social import (
    ProfileResponse,
    ProfileUpdateRequest,
    ArenaPostSummary,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/profiles", tags=["Profiles / Identity Graph"])


# ─── Auth dependency (shared with main app pattern) ──────────────────────────

async def get_current_user_id(
    x_user_id: Annotated[str, Header(description="Authenticated user UUID")]
) -> str:
    """
    Lightweight auth: extracts user UUID from the X-User-Id header.
    In production this should validate a Supabase JWT. For now it mirrors
    the pattern used in the main StartupScope monolith.
    """
    import uuid
    try:
        uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id must be a valid UUID.",
        )
    return x_user_id


# ─── GET /api/v1/profiles/{username} ─────────────────────────────────────────

# ─── PUT /api/v1/profiles/me ─────────────────────────────────────────────────
# NOTE: /me MUST be registered BEFORE /{username} so FastAPI does not
# treat the literal string "me" as a username path parameter.

@router.put(
    "/me",
    response_model=ProfileResponse,
    summary="Update own profile",
    description="Allows the authenticated founder to update their bio, avatar, and social links.",
)
async def update_my_profile(
    body: ProfileUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> ProfileResponse:
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    # Strip None values — only update provided fields
    update_payload = body.model_dump(exclude_none=True)
    if not update_payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field must be provided for update.",
        )

    try:
        await loop.run_in_executor(
            None,
            lambda: (
                sb.table("profiles")
                .update(update_payload)
                .eq("id", current_user_id)
                .execute()
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # Re-fetch the updated row — Supabase Python SDK may return [] from update()
    # when Prefer: return=representation is not set by the client.
    try:
        fetch_resp = await loop.run_in_executor(
            None,
            lambda: (
                sb.table("profiles")
                .select("id, username, display_name, bio, avatar_url, karma_score, badges, "
                        "twitter_url, linkedin_url, github_url, website_url, created_at")
                .eq("id", current_user_id)
                .single()
                .execute()
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if not fetch_resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Your profile was not found. Ensure your account is fully set up.",
        )

    logger.info("[Profile] Updated profile for user=%s fields=%s", current_user_id, list(update_payload.keys()))
    return ProfileResponse(**fetch_resp.data)


# ─── GET /api/v1/profiles/{username} ─────────────────────────────────────────

@router.get(
    "/{username}",
    response_model=ProfileResponse,
    summary="Get public founder profile",
    description="Returns a founder's public card including bio, karma score, and earned badges.",
)
async def get_profile(username: str) -> ProfileResponse:
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    try:
        resp = await loop.run_in_executor(
            None,
            lambda: (
                sb.table("profiles")
                .select("id, username, display_name, bio, avatar_url, karma_score, badges, "
                        "twitter_url, linkedin_url, github_url, website_url, created_at")
                .eq("username", username)
                .single()
                .execute()
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{username}' not found.",
        )

    if not resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{username}' not found.",
        )

    return ProfileResponse(**resp.data)


# ─── GET /api/v1/profiles/{user_id}/validations ──────────────────────────────

@router.get(
    "/{user_id}/validations",
    response_model=list[ArenaPostSummary],
    summary="Get public Arena portfolio",
    description="Returns all ideas this founder has published to the Validation Arena.",
)
async def get_founder_validations(user_id: str) -> list[ArenaPostSummary]:
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    try:
        resp = await loop.run_in_executor(
            None,
            lambda: (
                sb.table("posts")
                .select("id, title, author_id, upvote_count, downvote_count, "
                        "comment_count, tags, created_at, profiles!posts_author_id_fkey(username)")
                .eq("author_id", user_id)
                .order("created_at", desc=True)
                .execute()
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    results = []
    for row in (resp.data or []):
        profile_join = row.pop("profiles", {}) or {}
        row["author_username"] = profile_join.get("username", "unknown")
        row["karma_score"] = row.get("upvote_count", 0) - row.get("downvote_count", 0)
        results.append(ArenaPostSummary(**row))

    return results
