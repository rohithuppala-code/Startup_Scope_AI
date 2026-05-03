# realtime_groups/backend/api/comments_router.py
# ---------------------------------------------------------------------------
# Arena Comments — Create and list comments on Arena posts
#
# POST /api/v1/arena/posts/{post_id}/comments    — Create a comment
# GET  /api/v1/arena/posts/{post_id}/comments    — List comments (paginated)
#
# FIX: create_comment previously did a non-atomic read→+1→write for
# comment_count, creating a race condition under concurrent requests, and had
# no transaction wrapping the insert + count update, leaving them out of sync
# on partial failure.
#
# Both issues are resolved by a single Postgres RPC (create_comment_atomic)
# that runs inside one transaction:
#   1. Validates the post exists and is visible
#   2. Inserts the comment row
#   3. Increments comment_count with UPDATE ... SET count = count + 1
#   4. Returns the new comment + author profile in one round-trip
#
# The read-modify-write loop and its race condition are gone entirely.
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
    status_code=status.HTTP_201_CREATED,
    summary="Comment on an Arena post",
    description=(
        "Creates a comment on an Arena post and awards karma to the commenter. "
        "The insert and comment_count increment are atomic via a Postgres RPC."
    ),
)
async def create_comment(
    post_id: str,
    body: CommentCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    # Validate post_id is a real UUID before sending it to the DB.
    try:
        uuid_module.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="post_id must be a valid UUID.")

    # ── ATOMIC RPC ────────────────────────────────────────────────────
    # create_comment_atomic() runs inside a single Postgres transaction:
    #   - Raises an exception (caught below) if the post is missing/hidden
    #   - Inserts the comment row
    #   - Does UPDATE posts SET comment_count = comment_count + 1
    #     (atomic increment — no read-modify-write race)
    #   - Returns the new comment joined with the author's profile
    #
    # See: supabase/migrations/YYYYMMDD_create_comment_atomic.sql
    try:
        rpc_resp = await loop.run_in_executor(
            None,
            lambda: sb.rpc(
                "create_comment_atomic",
                {
                    "p_post_id":   post_id,
                    "p_user_id":   current_user_id,
                    "p_content":   body.content,
                },
            ).execute(),
        )
    except Exception as exc:
        # Postgres will RAISE EXCEPTION with a message we can surface.
        err = str(exc)
        if "post_not_found" in err or "post_hidden" in err:
            raise HTTPException(status_code=404, detail="Post not found.")
        logger.error("[Comments] RPC create_comment_atomic failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create comment.")

    if not rpc_resp.data:
        # Should not happen if the SQL is correct, but guard anyway.
        raise HTTPException(status_code=500, detail="Comment creation returned no data.")

    row = rpc_resp.data[0]

    # Reward the commenter with karma (fire-and-forget, non-blocking).
    asyncio.create_task(reputation_engine.reward_comment(current_user_id))

    logger.info("[Comments] User %s commented on post %s", current_user_id, post_id)

    return CommentResponse(
        id=uuid_module.UUID(row["id"]),
        post_id=uuid_module.UUID(row["post_id"]),
        author_id=uuid_module.UUID(row["author_id"]),
        author_username=row.get("author_username") or "unknown",
        author_avatar=row.get("author_avatar_url"),
        content=row["content"],
        upvote_count=row.get("upvote_count", 0),
        is_hidden=False,
        created_at=row.get("created_at"),
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
            .select(
                "id, post_id, author_id, content, upvote_count, is_hidden, created_at, "
                "profiles!comments_author_id_fkey(username, avatar_url)"
            )
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