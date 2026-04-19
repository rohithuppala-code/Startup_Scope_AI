# realtime_groups/backend/api/synthesis_router.py
# ---------------------------------------------------------------------------
# Phase 3: AI Synthesis & Database Webhook Bridge
#
# POST /api/v1/arena/posts/{post_id}/synthesize   — Gemini 2.0 Flash synthesis
# POST /api/v1/webhooks/moderation                — Supabase DB webhook → Celery
# ---------------------------------------------------------------------------

import asyncio
import logging
import uuid as uuid_module
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from realtime_groups.backend.core.supabase_client import get_supabase
from realtime_groups.backend.schemas.social import SynthesisResponse, SupabaseWebhookPayload
from realtime_groups.backend.services import synthesis_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["AI Synthesis & Moderation Webhooks"])


async def get_current_user_id(
    x_user_id: Annotated[str, Header(description="Authenticated user UUID")]
) -> str:
    try:
        uuid_module.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-User-Id must be a valid UUID.")
    return x_user_id


# ─── POST /api/v1/arena/posts/{post_id}/synthesize ────────────────────────────

@router.post(
    "/api/v1/arena/posts/{post_id}/synthesize",
    summary="Generate AI thread synthesis",
    description=(
        "Uses Gemini 2.0 Flash (1M token context) to synthesize ALL community comments "
        "under a post into a strategic brief: key themes, sentiment breakdown, and "
        "actionable founder takeaways."
    ),
)
async def synthesize_post_thread(
    post_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    loop = asyncio.get_running_loop()

    try:
        result = await loop.run_in_executor(
            None,
            lambda: synthesis_service.synthesize_thread(post_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("[Synthesis] Unexpected error for post=%s: %s", post_id, e)
        raise HTTPException(status_code=500, detail=f"Internal synthesis error: {e}")

    logger.info("[Synthesis] Completed for post=%s by user=%s", post_id, current_user_id)
    return result


# ─── POST /api/v1/webhooks/moderation ────────────────────────────────────────

@router.post(
    "/api/v1/webhooks/moderation",
    status_code=202,
    summary="Supabase DB webhook → AI moderation",
    description=(
        "This endpoint is called by a Supabase Database Webhook on every INSERT "
        "to the 'messages' or 'comments' table. It immediately drops the payload "
        "into the Celery queue for async AI moderation — the user never waits. "
        "\n\n"
        "⚠️  Configure this URL as a Supabase Database Webhook in your Supabase "
        "dashboard under Database → Webhooks. Select the 'messages' and 'comments' "
        "tables with the INSERT event type."
    ),
)
async def moderation_webhook(payload: SupabaseWebhookPayload) -> dict:
    """
    Receives Supabase Database Webhook POST, validates it, and dispatches a
    Celery moderation task. Returns 202 immediately — the user's critical path
    is completely unaffected.
    """
    record = payload.record
    table  = payload.table

    if table not in ("messages", "comments"):
        # Silently accept but don't process unsupported tables
        return {"status": "ignored", "reason": f"Table '{table}' not moderated."}

    content   = record.get("content", "")
    record_id = record.get("id", "")
    author_id = record.get("author_id") or record.get("user_id") or record.get("sender_id", "")

    if not content or not record_id or not author_id:
        logger.warning("[Webhook] Received incomplete record: %s", record)
        return {"status": "skipped", "reason": "Missing required fields (content, id, author_id)."}

    # Dispatch to Celery — import here to avoid circular dependency
    try:
        from realtime_groups.backend.workers.celery_tasks import moderate_content_task
        moderate_content_task.delay(
            content=content,
            table=table,
            record_id=record_id,
            author_id=author_id,
        )
        logger.info("[Webhook] Queued moderation task for %s record=%s", table, record_id)
    except Exception as e:
        # Fail open — do not block the webhook response. Log and continue.
        logger.error("[Webhook] Failed to queue moderation task: %s", e)

    return {"status": "accepted", "record_id": record_id, "table": table}
