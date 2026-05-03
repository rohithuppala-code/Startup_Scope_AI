# main.py
import hashlib
import json
import uuid
import asyncio
from contextlib import asynccontextmanager
from functools import partial
from typing import Any, Dict, List, Optional

import redis as sync_redis
from fastapi import FastAPI, HTTPException, status, Depends, Query
from supabase import create_client, Client

from app.api.auth import router as auth_router
from app.api.dependencies import rate_limit_user
from app.api.ws_router import router as ws_router
from app.api.chat_router import router as chat_router
from app.api.export_router import router as export_router
from app.api.comparison_router import router as comparison_router
from app.api.workspace_router import router as workspace_router  # BUG FIX: was never registered

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

from app.worker.celery_tasks import process_validation as _process_validation_task

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

# ── CORS — allow all origins (dev mode) ────────────────────────────────
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ws_router)
app.include_router(auth_router)
app.include_router(chat_router)          # Feature 12: Conversational RAG
app.include_router(export_router)        # Feature 13: PDF Export
app.include_router(comparison_router)    # Feature 15: Idea Comparison Engine
app.include_router(workspace_router)     # BUG FIX: Team collaboration endpoints now reachable

# Phase 1-3: Discord for Founders — Identity Graph, Arena, Community, AI Moderation
include_social_routers(app)

# Service-role client bypasses Row Level Security — never expose to the frontend.
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

# Synchronous Redis client for cache-aside reads in the FastAPI process.
# DB 0 matches the worker's cache layer. DB 1 is reserved for Celery results.
_redis = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)



# ---------------------------------------------------------------------------
# GET /health  — Liveness probe (used by startup.sh, tests, load balancers)
# ---------------------------------------------------------------------------
@app.get("/health", tags=["health"])
@app.get("/api/v1/health", tags=["health"])
async def health_check():
    """Returns service health including Redis connectivity."""
    redis_ok = False
    try:
        redis_ok = _redis.ping()
    except Exception:
        pass
    return {
        "status": "ok",
        "version": "1.0.0",
        "redis": "connected" if redis_ok else "unreachable",
    }


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
                _process_validation_task.apply_async,
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


@app.get("/api/v1/validations")
async def list_validations(
    x_user_id: str = Depends(rate_limit_user),
    status_filter: Optional[str] = Query(None, alias="status")
) -> List[Dict[str, Any]]:
    """
    Retrieves all validations for the current user.
    Used for the "Compare Ideas" history selection modal.
    """
    loop = asyncio.get_running_loop()
    try:
        query = supabase.table("validations").select(
            "id, idea_description, status, created_at, report_json, consensus_confidence"
        ).eq("user_id", x_user_id)
        
        if status_filter:
            query = query.eq("status", status_filter)
            
        query = query.order("created_at", desc=True)
            
        db_response = await loop.run_in_executor(None, lambda: query.execute())
        return db_response.data or []
    except Exception as db_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {db_err}",
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

    # BUG FIX: .single() with .eq("user_id") raises APIError(500) when the row
    # exists but belongs to a different user (0 rows returned) — the client gets
    # a 500 instead of a clean 404. Use .limit(1) + explicit ownership check.
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
                .limit(1)
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

    record = db_response.data[0]  # BUG FIX: was db_response.data (the full list)

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


# ---------------------------------------------------------------------------
# GET /api/v1/validate/{validation_id}/status  — Public status check (no auth)
# Used by group-chat members polling for AI validation results.
# ---------------------------------------------------------------------------
@app.get("/api/v1/validate/{validation_id}/status")
async def get_validation_status(validation_id: str) -> Dict[str, Any]:
    """Public read-only status endpoint — no user auth required.
    Returns only: validation_id, status, report_json.
    Suitable for group-chat members who are not the owner."""
    try:
        uuid.UUID(validation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="validation_id must be a valid UUID.")

    loop = asyncio.get_running_loop()
    cache_key = f"validation:result:{validation_id}"

    # Try Redis cache first
    try:
        cached_raw = await loop.run_in_executor(None, lambda: _redis.get(cache_key))
        if cached_raw:
            cached = json.loads(cached_raw)
            return {"validation_id": validation_id, "status": cached.get("status"), "report_json": cached.get("report_json")}
    except Exception:
        pass

    # DB lookup (no user_id filter — public)
    try:
        db_resp = await loop.run_in_executor(
            None,
            lambda: supabase.table("validations")
                .select("id, status, report_json")
                .eq("id", validation_id)
                .limit(1)  # BUG FIX: .single() raised APIError on missing row → 500
                .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not db_resp.data:
        raise HTTPException(status_code=404, detail="Validation not found.")

    rec = db_resp.data[0]  # BUG FIX: was db_resp.data (the full list)
    return {"validation_id": validation_id, "status": rec["status"], "report_json": rec.get("report_json")}


# ---------------------------------------------------------------------------
# POST /api/v1/validate/{validation_id}/summarize  — AI-generated Idea Summary
# Uses Gemini to produce a rich summary from report_json + markdown_report.
# ---------------------------------------------------------------------------
@app.post("/api/v1/validate/{validation_id}/summarize")
async def summarize_validation(validation_id: str) -> Dict[str, Any]:
    """Generate a rich AI summary of the validation report using Gemini."""
    try:
        uuid.UUID(validation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="validation_id must be a valid UUID.")

    loop = asyncio.get_running_loop()

    # Fetch report_json + markdown_report
    # BUG FIX: .single() returns APIError(500) when validation doesn't exist;
    # the try/except catches it but raises 500 instead of 404. Use .limit(1).
    try:
        db_resp = await loop.run_in_executor(
            None,
            lambda: supabase.table("validations")
                .select("id, status, report_json, markdown_report, idea_description")
                .eq("id", validation_id)
                .limit(1)
                .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not db_resp.data:
        raise HTTPException(status_code=404, detail="Validation not found.")

    rec = db_resp.data[0]
    if rec["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Validation not completed yet (status: {rec['status']})")

    report_json = rec.get("report_json") or {}
    markdown_report = rec.get("markdown_report") or ""
    idea_desc = rec.get("idea_description") or ""

    # Build context for Gemini
    context_parts = []
    if idea_desc:
        context_parts.append(f"## Original Idea\n{idea_desc}")
    if markdown_report:
        context_parts.append(f"## Full Report\n{markdown_report[:4000]}")
    if report_json:
        context_parts.append(f"## Report Data\n```json\n{json.dumps(report_json, indent=2)[:3000]}\n```")

    if not context_parts:
        return {"summary": f"**Idea:** {idea_desc}\n\nNo detailed report available yet."}

    context = "\n\n".join(context_parts)

    prompt = (
        "You are StartupScope AI. The user wants a clear, actionable summary of this startup idea validation report.\n\n"
        "Based on the report data below, produce a well-structured summary that covers:\n"
        "1. 💡 **The Idea** — What the startup is about (1-2 sentences)\n"
        "2. 📊 **Feasibility Score** — The numerical score and what it means\n"
        "3. 🌍 **Market Analysis** — Key market insights\n"
        "4. ⚔️ **Competition** — Main competitors and positioning\n"
        "5. ⚠️ **Key Risks** — Top risks identified\n"
        "6. 🚀 **Recommendation** — What the founder should do next\n\n"
        "Use emojis as section headers. Be concise but insightful. Use bullet points where appropriate.\n"
        "Do NOT make up data — only use what's in the report.\n\n"
        f"{context}"
    )

    try:
        from app.services.ai_pipeline import _get_gemini
        from google.genai import types as genai_types

        client = _get_gemini()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.5,
                    max_output_tokens=1024,
                ),
            )
        )
        summary = response.text or "Summary generation failed."
    except Exception as e:
        print(f"[Summarize] Gemini error: {e}", flush=True)
        # Fallback: return a structured summary from the JSON fields
        lines = [f"**💡 Idea:** {idea_desc}"]
        if isinstance(report_json, dict):
            score = report_json.get("feasibility_score") or report_json.get("consensus_confidence")
            if score:
                lines.append(f"**📊 Feasibility:** {score}")
            mv = report_json.get("market_viability")
            if mv:
                lines.append(f"**🌍 Market:** {str(mv)[:300]}")
            rec_approach = report_json.get("recommended_approach")
            if rec_approach:
                lines.append(f"**🚀 Recommendation:** {str(rec_approach)[:300]}")
        summary = "\n\n".join(lines)

    return {"summary": summary, "validation_id": validation_id}