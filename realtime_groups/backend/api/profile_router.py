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
from realtime_groups.backend.api.profile_utils import ensure_profile_exists

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

# NOTE: /me MUST be registered BEFORE /{username} so FastAPI does not
# treat the literal string "me" as a username path parameter.

@router.get(
    "/me",
    response_model=ProfileResponse,
    summary="Get own profile",
)
async def get_my_profile(
    current_user_id: str = Depends(get_current_user_id),
) -> ProfileResponse:
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    # Ensure profile exists before fetching
    await loop.run_in_executor(None, lambda: ensure_profile_exists(sb, current_user_id))

    try:
        resp = await loop.run_in_executor(
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
    except Exception:
        raise HTTPException(status_code=404, detail="Profile not found.")

    if not resp.data:
        raise HTTPException(status_code=404, detail="Profile not found.")

    return ProfileResponse(**resp.data)

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

    # Ensure profile exists before updating (auto-create if missing)
    try:
        existing = await loop.run_in_executor(
            None,
            lambda: sb.table("profiles").select("id").eq("id", current_user_id).execute()
        )
        if not existing.data or len(existing.data) == 0:
            # Auto-create a minimal profile
            import uuid as uuid_module
            username = update_payload.get("display_name", f"user_{str(uuid_module.uuid4())[:6]}").lower().replace(" ", "_")
            await loop.run_in_executor(
                None,
                lambda: sb.table("profiles").insert({
                    "id": current_user_id,
                    "username": username,
                    "display_name": update_payload.get("display_name", username),
                    "karma_score": 0,
                    "badges": [],
                }).execute()
            )
    except Exception:
        pass  # Best-effort

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

    # Re-fetch the updated row
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
            detail="Your profile was not found. Please log out and log in again.",
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

# ─── POST /api/v1/profiles/{user_id}/follow ───────────────────────────────────

@router.post(
    "/{user_id}/follow",
    summary="Toggle follow for a user",
    description="Follows or unfollows the specified user.",
)
async def toggle_follow_user(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    if user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself.")

    sb = get_supabase()
    loop = asyncio.get_running_loop()

    # Check if already following
    resp = await loop.run_in_executor(
        None,
        lambda: sb.table("follows")
            .select("*")
            .eq("follower_id", current_user_id)
            .eq("following_id", user_id)
            .execute()
    )

    is_following = bool(resp.data and len(resp.data) > 0)

    try:
        if is_following:
            # Unfollow
            await loop.run_in_executor(
                None,
                lambda: sb.table("follows")
                    .delete()
                    .eq("follower_id", current_user_id)
                    .eq("following_id", user_id)
                    .execute()
            )
            return {"status": "unfollowed"}
        else:
            # Follow
            await loop.run_in_executor(
                None,
                lambda: sb.table("follows")
                    .insert({
                        "follower_id": current_user_id,
                        "following_id": user_id
                    })
                    .execute()
            )
            return {"status": "followed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/{user_id}/is_following",
    summary="Check if following a user",
)
async def check_is_following(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    if user_id == current_user_id:
        return {"is_following": False}

    sb = get_supabase()
    loop = asyncio.get_running_loop()

    resp = await loop.run_in_executor(
        None,
        lambda: sb.table("follows")
            .select("*")
            .eq("follower_id", current_user_id)
            .eq("following_id", user_id)
            .execute()
    )

    return {"is_following": bool(resp.data and len(resp.data) > 0)}

@router.get(
    "/{user_id}/followers/count",
    summary="Get follower count",
)
async def get_follower_count(
    user_id: str,
) -> dict:
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    # We only need the count.
    # In python supabase client, count='exact' allows returning the count.
    resp = await loop.run_in_executor(
        None,
        lambda: sb.table("follows")
            .select("follower_id", count="exact")
            .eq("following_id", user_id)
            .execute()
    )

    count = resp.count if resp.count is not None else len(resp.data or [])
    return {"follower_count": count}
