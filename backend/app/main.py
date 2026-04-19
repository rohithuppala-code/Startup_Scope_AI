# main.py
import hashlib
import json
import uuid
import asyncio
from contextlib import asynccontextmanager
from functools import partial
from typing import Any, Dict

import redis as sync_redis
from fastapi import FastAPI, HTTPException, status, Depends
from supabase import create_client, Client

from app.api.auth import router as auth_router
from app.api.dependencies import rate_limit_user
from app.api.ws_router import router as ws_router
from app.api.chat_router import router as chat_router
from app.api.export_router import router as export_router
from app.api.comparison_router import router as comparison_router

# Discord for Founders — Social Pillar
from realtime_groups.backend.social_app import include_social_routers

from app.core.config import settings
from app.schemas.validation import ValidationRequest, ValidationResponse
from app.websockets.manager import manager
from app.websockets.redis_listener import listen_to_redis

# ---------------------------------------------------------------------------
# Celery client (producer only — no worker code here)
# ---------------------------------------------------------------------------
from celery import Celery

import os

celery_app = Celery(
    "startupscope_producer",
    broker="memory://" if os.environ.get("CELERY_TASK_ALWAYS_EAGER", "0") == "1" else settings.CELERY_BROKER_URL,
    backend=None if os.environ.get("CELERY_TASK_ALWAYS_EAGER", "0") == "1" else settings.CELERY_RESULT_BACKEND,
)
celery_app.conf.update(
    task_always_eager=os.environ.get("CELERY_TASK_ALWAYS_EAGER", "0") == "1",
    broker_connection_retry_on_startup=True,
    # ── Queue declarations MUST match the worker's config ─────────────
    # The worker declares the 'default' queue with x-dead-letter-exchange
    # and x-dead-letter-routing-key args. If the producer tries to declare
    # the same queue WITHOUT those args, RabbitMQ returns 406
    # PRECONDITION_FAILED and send_task silently fails.
    task_queues={
        "default": {
            "exchange": "default",
            "routing_key": "default",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlx",
                "x-dead-letter-routing-key": "dlq",
            },
        },
    },
)

import app.worker.celery_tasks # Ensure tasks are registered for eager mode

# ---------------------------------------------------------------------------
# Lifespan: start/stop the Redis Pub/Sub listener
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_task = asyncio.create_task(listen_to_redis(manager))
    yield
    redis_task.cancel()
    try:
        await redis_task
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="StartupScope AI", version="1.0.0", lifespan=lifespan)
app.include_router(ws_router)
app.include_router(auth_router)
app.include_router(chat_router)          # Feature 12: Conversational RAG
app.include_router(export_router)        # Feature 13: PDF Export

app.include_router(comparison_router)    # Feature 15: Idea Comparison Engine

# Phase 1-3: Discord for Founders — Identity Graph, Arena, Community, AI Moderation
include_social_routers(app)

# Service-role client bypasses Row Level Security — never expose to the frontend.
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

# Synchronous Redis client for cache-aside reads in the FastAPI process.
# DB 0 matches the worker's cache layer. DB 1 is reserved for Celery results.
_redis = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)


# ---------------------------------------------------------------------------
# POST /api/v1/validate  — Submit a new validation
# ---------------------------------------------------------------------------
@app.post(
    "/api/v1/validate",
    response_model=ValidationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_validation(
    request: ValidationRequest,
    x_user_id: str = Depends(rate_limit_user),
) -> ValidationResponse:
    """
    Anchor write → RabbitMQ dispatch → instant 202 response.

    UUID format of x_user_id is pre-validated in the rate_limit_user dependency.
    """
    # get_running_loop() is the correct Python 3.10+-safe way to get the loop
    # from inside an async context (get_event_loop() is deprecated there).
    loop = asyncio.get_running_loop()

    idempotency_key = request.idempotency_key or str(uuid.uuid4())
    idea_hash = hashlib.sha256(request.idea_description.encode("utf-8")).hexdigest()

    data_to_insert = {
        "user_id": x_user_id,
        "idea_description": request.idea_description,
        "target_market": request.target_market,
        "budget_constraints": request.budget_constraints,
        "status": "pending",
        "idempotency_key": idempotency_key,
        "idea_hash": idea_hash,
    }

    # Anchor Write — offloaded to a thread so the async event loop is not
    # blocked by the synchronous Supabase HTTP call.
    try:
        response = await loop.run_in_executor(
            None,
            lambda: supabase.table("validations").insert(data_to_insert).execute(),
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database insert returned no data.",
            )

        validation_record = response.data[0]
        validation_id: str = validation_record["id"]

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if (
            "unique constraint" in error_msg
            or "duplicate key" in error_msg
            or "23505" in error_msg
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A validation with this idempotency key already exists for this user.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {e}",
        )

    # Dispatch to RabbitMQ via Celery — also offloaded to a thread.
    # BUG FIX: If send_task() raises (RabbitMQ down, auth error, etc.), the DB
    # row was previously left stuck in 'pending' forever with no worker to pick
    # it up and no failure event written. The client would see 'pending'
    # indefinitely with no way to know something went wrong.
    # We now catch the dispatch failure, update the row to 'failed', and return
    # a 503 Service Unavailable so the client knows to retry later.
    try:
        await loop.run_in_executor(
            None,
            partial(
                app.worker.celery_tasks.process_validation.apply_async,
                kwargs={
                    "validation_id": validation_id,
                    "idea_hash": idea_hash,
                },
                queue="default",
            ),
        )
    except Exception as dispatch_err:
        print(f"[Validation] Dispatch error: {dispatch_err}", flush=True)
        import traceback
        traceback.print_exc()
        # Best-effort: mark the row failed so it doesn't stay stuck in 'pending'.
        try:
            await loop.run_in_executor(
                None,
                lambda: supabase.table("validations").update({
                    "status": "failed",
                    "error_message": f"Task dispatch failed: {dispatch_err}",
                }).eq("id", validation_id).execute(),
            )
        except Exception:
            pass  # DB update is best-effort; the 503 is the critical signal.

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Task queue is temporarily unavailable. "
                "The request has been recorded but not queued. Please retry shortly."
            ),
        )

    return ValidationResponse(
        validation_id=uuid.UUID(validation_id),
        status="pending",
        message="Validation task accepted and queued successfully.",
    )


# ---------------------------------------------------------------------------
# GET /api/v1/validate/{validation_id}  — Cache-Aside read path
#
# BUG FIX: This endpoint was entirely missing. The architecture specifies a
# "Future Reads (Cache-Aside)" path: "Check Redis → if hit → instant response
# → if miss → fetch from DB → cache it." Without this endpoint, a client whose
# WebSocket connection drops after submission has no way to retrieve the result.
# The WebSocket is the real-time push path; this is the reliable fallback.
# ---------------------------------------------------------------------------
@app.get("/api/v1/validate/{validation_id}")
async def get_validation(
    validation_id: str,
    x_user_id: str = Depends(rate_limit_user),
) -> Dict[str, Any]:
    """
    Retrieves a validation result using the Cache-Aside pattern.

    1. Check Redis — instant response on hit (O(1), ~1ms).
    2. Miss → fetch from Supabase — authoritative source of truth.
    3. Cache the DB result in Redis for subsequent reads (24h TTL).

    Used as the fallback read path when the WebSocket connection has dropped.
    """
    # Validate that validation_id is a well-formed UUID before hitting any backend.
    try:
        uuid.UUID(validation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="validation_id must be a valid UUID.",
        )

    loop = asyncio.get_running_loop()
    cache_key = f"validation:result:{validation_id}"

    # ---- Step 1: Redis cache check (synchronous read, offloaded to thread) ----
    try:
        cached_raw = await loop.run_in_executor(None, lambda: _redis.get(cache_key))
        if cached_raw:
            cached = json.loads(cached_raw)
            cached["source"] = "cache"
            return cached
    except Exception as cache_err:
        # Redis is down or cache is corrupt — fall through to DB.
        print(f"[API] Redis cache read failed for {validation_id}: {cache_err}")

    # ---- Step 2: Supabase fetch (cache miss) ----
    try:
        db_response = await loop.run_in_executor(
            None,
            lambda: (
                supabase.table("validations")
                .select(
                    "id, status, report_json, markdown_report, "
                    "tokens_used, estimated_cost, error_message, "
                    "created_at, updated_at"
                )
                .eq("id", validation_id)
                .eq("user_id", x_user_id)   # Enforce ownership — users can only read their own.
                .single()
                .execute()
            ),
        )
    except Exception as db_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {db_err}",
        )

    if not db_response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Validation not found or you do not have access to it.",
        )

    record = db_response.data

    # ---- Step 3: Back-fill Redis cache (only for terminal states) ----
    # Only cache completed/failed rows — 'pending' and 'processing' rows
    # change frequently and should not be cached (stale reads are confusing).
    if record.get("status") in ("completed", "failed"):
        cache_payload = {
            "validation_id": validation_id,
            "status": record.get("status"),
            "report_json": record.get("report_json"),
            "tokens_used": record.get("tokens_used"),
            "estimated_cost": record.get("estimated_cost"),
            "error_message": record.get("error_message"),
        }
        try:
            await loop.run_in_executor(
                None,
                lambda: _redis.setex(cache_key, 86400, json.dumps(cache_payload)),
            )
        except Exception as cache_write_err:
            # Non-fatal — the response is correct, the cache just wasn't warmed.
            print(f"[API] Redis cache write failed for {validation_id}: {cache_write_err}")

    record["source"] = "database"
    return record