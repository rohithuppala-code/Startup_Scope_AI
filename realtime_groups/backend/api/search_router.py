# realtime_groups/backend/api/search_router.py
# ---------------------------------------------------------------------------
# Search & Discovery — Arena Explore
#
# GET /api/v1/arena/search?q=...&type=posts|profiles  — Full-text search
# GET /api/v1/arena/trending                           — Top posts (7 days)
# GET /api/v1/profiles/suggested                       — Suggested founders
# POST /api/v1/follows/{user_id}                       — Follow a founder
# DELETE /api/v1/follows/{user_id}                     — Unfollow a founder
# ---------------------------------------------------------------------------

import asyncio
import logging
import uuid as uuid_module
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from realtime_groups.backend.core.supabase_client import get_supabase
from realtime_groups.backend.schemas.social import (
    SearchResultPost,
    SearchResultProfile,
    TrendingPostResponse,
    FollowResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Search & Discovery"])


async def get_current_user_id(
    x_user_id: Annotated[str, Header(description="Authenticated user UUID")]
) -> str:
    try:
        uuid_module.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-User-Id must be a valid UUID.")
    return x_user_id


# ─── GET /api/v1/arena/search ────────────────────────────────────────────────

@router.get(
    "/api/v1/arena/search",
    summary="Search posts and profiles",
    description="Full-text search across Arena posts (title, content) and founder profiles (username, display_name).",
)
async def search_arena(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    type: str = Query("posts", description="'posts' or 'profiles'"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()
    offset = (page - 1) * page_size
    search_pattern = f"%{q}%"

    if type == "profiles":
        resp = await loop.run_in_executor(
            None,
            lambda: (
                sb.table("profiles")
                .select("id, username, display_name, avatar_url, bio, karma_score, badges")
                .or_(f"username.ilike.{search_pattern},display_name.ilike.{search_pattern}")
                .order("karma_score", desc=True)
                .range(offset, offset + page_size - 1)
                .execute()
            ),
        )
        return [SearchResultProfile(**row) for row in (resp.data or [])]
    else:
        resp = await loop.run_in_executor(
            None,
            lambda: (
                sb.table("posts")
                .select("id, title, content, upvote_count, downvote_count, comment_count, tags, created_at, author_id, profiles!posts_author_id_fkey(username)")
                .or_(f"title.ilike.{search_pattern},content.ilike.{search_pattern}")
                .eq("is_hidden", False)
                .order("upvote_count", desc=True)
                .range(offset, offset + page_size - 1)
                .execute()
            ),
        )
        results = []
        for row in (resp.data or []):
            profile_join = row.pop("profiles", {}) or {}
            row["author_username"] = profile_join.get("username", "unknown")
            results.append(SearchResultPost(**row))
        return results


# ─── GET /api/v1/arena/trending ──────────────────────────────────────────────

@router.get(
    "/api/v1/arena/trending",
    response_model=list[TrendingPostResponse],
    summary="Trending ideas (last 7 days)",
    description="Top 10 Arena posts by upvote count from the last 7 days.",
)
async def trending_ideas(
    limit: int = Query(10, ge=1, le=50),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    resp = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("posts")
            .select("id, title, upvote_count, comment_count, created_at, profiles!posts_author_id_fkey(username)")
            .eq("is_hidden", False)
            .gte("created_at", seven_days_ago)
            .order("upvote_count", desc=True)
            .limit(limit)
            .execute()
        ),
    )

    results = []
    for row in (resp.data or []):
        profile_join = row.pop("profiles", {}) or {}
        row["author_username"] = profile_join.get("username", "unknown")
        results.append(TrendingPostResponse(**row))
    return results


# ─── GET /api/v1/profiles/suggested ──────────────────────────────────────────

@router.get(
    "/api/v1/profiles/suggested",
    response_model=list[SearchResultProfile],
    summary="Suggested founders to follow",
    description="Top 8 founders by karma, excluding the current user.",
)
async def suggested_founders(
    current_user_id: str = Depends(get_current_user_id),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    resp = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("profiles")
            .select("id, username, display_name, avatar_url, bio, karma_score, badges")
            .neq("id", current_user_id)
            .order("karma_score", desc=True)
            .limit(8)
            .execute()
        ),
    )

    return [SearchResultProfile(**row) for row in (resp.data or [])]


# ─── GET /api/v1/arena/suggested-founders ───────────────────────────────────
# No-auth version for sidebar widget (returns random founders)

@router.get(
    "/api/v1/arena/suggested-founders",
    response_model=list[SearchResultProfile],
    summary="Suggested founders (no auth)",
    description="Returns random founders for the sidebar widget.",
)
async def suggested_founders_public(
    limit: int = Query(5, ge=1, le=20),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    resp = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("profiles")
            .select("id, username, display_name, avatar_url, bio, karma_score, badges")
            .order("karma_score", desc=True)
            .limit(limit)
            .execute()
        ),
    )

    return [SearchResultProfile(**row) for row in (resp.data or [])]


# ─── POST /api/v1/follows/{user_id} ─────────────────────────────────────────

@router.post(
    "/api/v1/follows/{user_id}",
    response_model=FollowResponse,
    status_code=201,
    summary="Follow a founder",
)
async def follow_user(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    if user_id == current_user_id:
        raise HTTPException(status_code=400, detail="You cannot follow yourself.")

    sb = get_supabase()
    loop = asyncio.get_running_loop()

    try:
        await loop.run_in_executor(
            None,
            lambda: sb.table("follows").upsert({
                "follower_id": current_user_id,
                "following_id": user_id,
            }).execute(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return FollowResponse(
        follower_id=uuid_module.UUID(current_user_id),
        following_id=uuid_module.UUID(user_id),
        message="Successfully followed.",
    )


# ─── DELETE /api/v1/follows/{user_id} ────────────────────────────────────────

@router.delete(
    "/api/v1/follows/{user_id}",
    response_model=FollowResponse,
    summary="Unfollow a founder",
)
async def unfollow_user(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    try:
        await loop.run_in_executor(
            None,
            lambda: (
                sb.table("follows")
                .delete()
                .eq("follower_id", current_user_id)
                .eq("following_id", user_id)
                .execute()
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return FollowResponse(
        follower_id=uuid_module.UUID(current_user_id),
        following_id=uuid_module.UUID(user_id),
        message="Successfully unfollowed.",
    )
