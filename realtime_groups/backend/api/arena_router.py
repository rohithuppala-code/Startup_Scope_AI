# realtime_groups/backend/api/arena_router.py
# ---------------------------------------------------------------------------
# Phase 2: Validation Arena — Publishing, Voting, Poll Voting
#
# POST /api/v1/arena/publish                         — Publish a validation to Arena
# POST /api/v1/arena/posts/{post_id}/vote            — Upvote / downvote a post
# POST /api/v1/arena/posts/{post_id}/polls/vote      — Submit a poll vote
# GET  /api/v1/arena/posts                           — Paginated arena feed
# GET  /api/v1/arena/posts/{post_id}                 — Single post detail
# ---------------------------------------------------------------------------

import asyncio
import logging
import uuid as uuid_module
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status

from realtime_groups.backend.core.supabase_client import get_supabase
from realtime_groups.backend.schemas.social import (
    PublishRequest, PublishResponse,
    VoteRequest, VoteResponse,
    PollVoteRequest, PollVoteResponse,
    ArenaPostSummary,
)
from realtime_groups.backend.services import reputation_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/arena", tags=["Validation Arena"])


async def get_current_user_id(
    x_user_id: Annotated[str, Header(description="Authenticated user UUID")]
) -> str:
    try:
        uuid_module.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-User-Id must be a valid UUID.")
    return x_user_id


@router.post("/publish", response_model=PublishResponse, status_code=201,
             summary="Publish idea to the Validation Arena")
async def publish_idea(body: PublishRequest, current_user_id: str = Depends(get_current_user_id)):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    try:
        val_resp = await loop.run_in_executor(
            None,
            lambda: sb.table("validations").select("id, report_json, status, user_id")
                .eq("id", str(body.validation_id)).single().execute()
        )
    except Exception as e:
        logger.error("[Arena] Failed to fetch validation %s: %s", body.validation_id, e)
        raise HTTPException(404, "Validation report not found.")

    if not val_resp.data:
        raise HTTPException(404, "Validation report not found.")
    validation = val_resp.data
    if validation["user_id"] != current_user_id:
        raise HTTPException(403, "You can only publish your own validation reports.")
    if validation["status"] != "completed":
        raise HTTPException(422, f"Validation must be 'completed' to publish. Status: {validation['status']}")

    existing = await loop.run_in_executor(
        None,
        lambda: sb.table("posts").select("id").eq("validation_id", str(body.validation_id)).execute()
    )
    if existing.data:
        raise HTTPException(409, "This validation has already been published to the Arena.")

    post_id = str(uuid_module.uuid4())
    # posts.content is NOT NULL — seed it from the validation's idea_description or title.
    content_text = (
        validation.get("idea_description")
        or body.title
    )
    try:
        await loop.run_in_executor(
            None,
            lambda: sb.table("posts").insert({
                "id": post_id,
                "user_id": current_user_id,      # posts.user_id FK to profiles
                "author_id": current_user_id,
                "validation_id": str(body.validation_id),
                "title": body.title,
                "content": content_text,         # NOT NULL — required by schema
                "report_json": validation["report_json"],
                "tags": body.tags,
                "upvote_count": 0,
                "downvote_count": 0,
                "comment_count": 0,
                "is_hidden": False,
            }).execute()
        )
    except Exception as e:
        logger.error("[Arena] Failed to insert post for validation %s: %s", body.validation_id, e)
        raise HTTPException(500, f"Failed to create post: {e}")

    asyncio.create_task(reputation_engine.reward_publish(current_user_id))
    logger.info("[Arena] %s published post %s", current_user_id, post_id)
    return PublishResponse(post_id=uuid_module.UUID(post_id))


@router.get("/posts", response_model=list[ArenaPostSummary], summary="Browse the Validation Arena")
async def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tag: Optional[str] = Query(None),
    sort_by: str = Query("recent"),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()
    offset = (page - 1) * page_size
    order_col = "created_at" if sort_by == "recent" else "upvote_count"

    query = (
        sb.table("posts")
        .select("id, title, author_id, upvote_count, downvote_count, comment_count, tags, created_at, profiles!posts_author_id_fkey(username)")
        .order(order_col, desc=True)
        .range(offset, offset + page_size - 1)
    )
    if tag:
        query = query.contains("tags", [tag])

    resp = await loop.run_in_executor(None, lambda: query.execute())
    results = []
    for row in (resp.data or []):
        profile_join = row.pop("profiles", {}) or {}
        row["author_username"] = profile_join.get("username", "unknown")
        row["karma_score"] = row.get("upvote_count", 0) - row.get("downvote_count", 0)
        results.append(ArenaPostSummary(**row))
    return results


@router.get("/posts/{post_id}", summary="Get Arena post detail")
async def get_post(post_id: str):
    sb = get_supabase()
    loop = asyncio.get_running_loop()
    try:
        resp = await loop.run_in_executor(
            None,
            lambda: sb.table("posts").select("*, profiles!posts_author_id_fkey(username, avatar_url, karma_score, badges)")
                .eq("id", post_id).single().execute()
        )
    except Exception:
        raise HTTPException(404, "Post not found.")
    if not resp.data:
        raise HTTPException(404, "Post not found.")
    return resp.data


@router.post("/posts/{post_id}/vote", response_model=VoteResponse, summary="Vote on an Arena post")
async def vote_on_post(
    post_id: str,
    body: VoteRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    existing_vote_resp = await loop.run_in_executor(
        None,
        lambda: sb.table("post_votes").select("direction")
            .eq("post_id", post_id).eq("user_id", current_user_id).execute()
    )
    existing_votes = existing_vote_resp.data or []
    if any(v["direction"] == body.direction for v in existing_votes):
        raise HTTPException(409, "You have already voted in that direction on this post.")

    await loop.run_in_executor(
        None,
        lambda: sb.table("post_votes").upsert({
            "post_id": post_id, "user_id": current_user_id, "direction": body.direction
        }).execute()
    )

    all_votes = (await loop.run_in_executor(
        None,
        lambda: sb.table("post_votes").select("direction").eq("post_id", post_id).execute()
    )).data or []
    upvotes   = sum(1 for v in all_votes if v["direction"] == 1)
    downvotes = sum(1 for v in all_votes if v["direction"] == -1)
    new_score = upvotes - downvotes

    await loop.run_in_executor(
        None,
        lambda: sb.table("posts").update({"upvote_count": upvotes, "downvote_count": downvotes})
            .eq("id", post_id).execute()
    )

    if body.direction == 1:
        try:
            post_resp = await loop.run_in_executor(
                None,
                lambda: sb.table("posts").select("author_id").eq("id", post_id).single().execute()
            )
            if post_resp.data:
                asyncio.create_task(reputation_engine.reward_upvote(post_resp.data["author_id"]))
        except Exception:
            pass  # Non-fatal: karma reward is best-effort

    return VoteResponse(post_id=uuid_module.UUID(post_id), new_score=new_score,
                        message=f"Vote recorded. Post score is now {new_score:+d}.")


@router.post("/posts/{post_id}/polls/vote", response_model=PollVoteResponse, summary="Submit a poll vote")
async def vote_on_poll(
    post_id: str,
    body: PollVoteRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    try:
        poll_resp = await loop.run_in_executor(
            None,
            lambda: sb.table("polls").select("id, options")
                .eq("id", str(body.poll_id)).eq("post_id", post_id).single().execute()
        )
    except Exception:
        raise HTTPException(404, "Poll not found for this post.")
    if not poll_resp.data:
        raise HTTPException(404, "Poll not found for this post.")

    options = poll_resp.data.get("options", [])
    valid_option_ids = {opt["id"] for opt in options}
    if body.option_id not in valid_option_ids:
        raise HTTPException(400, f"Invalid option_id. Valid options: {list(valid_option_ids)}")

    try:
        await loop.run_in_executor(
            None,
            lambda: sb.table("poll_votes").insert({
                "poll_id": str(body.poll_id),
                "user_id": current_user_id,
                "option_id": body.option_id,
            }).execute()
        )
    except Exception as e:
        err_str = str(e).lower()
        if "unique" in err_str or "duplicate" in err_str or "23505" in err_str:
            raise HTTPException(409, "You have already voted in this poll.")
        raise HTTPException(500, str(e))

    return PollVoteResponse(poll_id=body.poll_id, option_id=body.option_id)
