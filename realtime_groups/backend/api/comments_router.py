# realtime_groups/backend/api/comments_router.py
# ---------------------------------------------------------------------------
# Arena Comments — Create and list comments on Arena posts
#
# POST /api/v1/arena/posts/{post_id}/comments    — Create a comment
# GET  /api/v1/arena/posts/{post_id}/comments    — List comments (paginated)
# ---------------------------------------------------------------------------

import asyncio
import logging
import uuid as uuid_module
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from realtime_groups.backend.core.supabase_client import get_supabase
from realtime_groups.backend.schemas.social import (
    CommentCreateRequest,
    CommentResponse,
)
from realtime_groups.backend.services import reputation_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/arena", tags=["Arena Comments"])


async def get_current_user_id(
    x_user_id: Annotated[str, Header(description="Authenticated user UUID")]
) -> str:
    try:
        uuid_module.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-User-Id must be a valid UUID.")
    return x_user_id


# ─── POST /api/v1/arena/posts/{post_id}/comments ────────────────────────────

@router.post(
    "/posts/{post_id}/comments",
    response_model=CommentResponse,
    status_code=201,
    summary="Comment on an Arena post",
    description="Creates a comment on an Arena post and awards karma to the commenter.",
)
async def create_comment(
    post_id: str,
    body: CommentCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    # Verify the post exists
    try:
        post_resp = await loop.run_in_executor(
            None,
            lambda: (
                sb.table("posts")
                .select("id")
                .eq("id", post_id)
                .eq("is_hidden", False)
                .single()
                .execute()
            ),
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Post not found.")

    if not post_resp.data:
        raise HTTPException(status_code=404, detail="Post not found.")

    # Insert the comment
    comment_id = str(uuid_module.uuid4())
    try:
        comment_resp = await loop.run_in_executor(
            None,
            lambda: sb.table("comments").insert({
                "id": comment_id,
                "post_id": post_id,
                "user_id": current_user_id,
                "author_id": current_user_id,
                "content": body.content,
                "is_hidden": False,
                "upvote_count": 0,
            }).execute(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create comment: {e}")

    # Increment comment_count on the post (best-effort)
    try:
        post_data_resp = await loop.run_in_executor(
            None,
            lambda: sb.table("posts").select("comment_count").eq("id", post_id).single().execute(),
        )
        if post_data_resp.data:
            new_count = (post_data_resp.data.get("comment_count", 0) or 0) + 1
            await loop.run_in_executor(
                None,
                lambda: sb.table("posts").update({"comment_count": new_count}).eq("id", post_id).execute(),
            )
    except Exception:
        pass  # Non-fatal

    # Reward the commenter with karma (async, non-blocking)
    asyncio.create_task(reputation_engine.reward_comment(current_user_id))

    # Fetch author profile for response
    profile_resp = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("profiles")
            .select("username, avatar_url")
            .eq("id", current_user_id)
            .single()
            .execute()
        ),
    )
    profile = profile_resp.data or {}

    logger.info("[Comments] User %s commented on post %s", current_user_id, post_id)

    return CommentResponse(
        id=uuid_module.UUID(comment_id),
        post_id=uuid_module.UUID(post_id),
        author_id=uuid_module.UUID(current_user_id),
        author_username=profile.get("username", "unknown"),
        author_avatar=profile.get("avatar_url"),
        content=body.content,
        upvote_count=0,
        is_hidden=False,
        created_at=None,
    )


# ─── GET /api/v1/arena/posts/{post_id}/comments ─────────────────────────────

@router.get(
    "/posts/{post_id}/comments",
    response_model=list[CommentResponse],
    summary="List comments on a post",
    description="Returns paginated comments on an Arena post, newest first, with author profiles.",
)
async def list_comments(
    post_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()
    offset = (page - 1) * page_size

    resp = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("comments")
            .select("id, post_id, author_id, content, upvote_count, is_hidden, created_at, profiles!comments_author_id_fkey(username, avatar_url)")
            .eq("post_id", post_id)
            .eq("is_hidden", False)
            .order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        ),
    )

    results = []
    for row in (resp.data or []):
        profile_join = row.pop("profiles", {}) or {}
        row["author_username"] = profile_join.get("username", "unknown")
        row["author_avatar"] = profile_join.get("avatar_url")
        results.append(CommentResponse(**row))

    return results
