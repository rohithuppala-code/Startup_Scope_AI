# celery_tasks.py
import json
from datetime import datetime, timezone

import redis
from celery import Celery
from celery.exceptions import Retry
from supabase import create_client, Client

from app.core.config import settings
from app.services.ai_pipeline import firecrawl_scrape, generate_ai_report

# ==========================================
# 1. INFRASTRUCTURE INITIALIZATION
# ==========================================

celery_app = Celery(
    "startupscope_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_time_limit=300,        # Hard kill after 5 minutes
    task_soft_time_limit=240,   # SoftTimeLimitExceeded raised at 4 minutes
    broker_connection_retry_on_startup=True,
)

# Synchronous Redis client for the Celery worker process (not async).
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

# Supabase client with service role key (bypasses Row Level Security).
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


# ==========================================
# 2. HELPERS
# ==========================================

def _update_validation(validation_id: str, fields: dict) -> None:
    """
    Updates a validation row and logs a warning if no row was matched.
    Protects against silently continuing on a ghost record that was externally
    deleted between task steps.
    """
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = (
        supabase.table("validations")
        .update(fields)
        .eq("id", validation_id)
        .execute()
    )
    if not result.data:
        print(
            f"[Worker] WARNING: update for {validation_id} matched no rows. "
            "Row may have been deleted externally.",
            flush=True,
        )


def _publish_event(validation_id: str, payload: dict) -> None:
    """Publishes a JSON event to the Redis Pub/Sub channel for WebSocket dispatch."""
    redis_client.publish("validation_events", json.dumps(payload))


# ==========================================
# 3. CELERY TASK
# ==========================================

@celery_app.task(
    bind=True,
    name="app.worker.celery_tasks.process_validation",
    max_retries=2,
    acks_late=True,  # Only ack after the task finishes — safe at-least-once delivery.
)
def process_validation(self, validation_id: str, idea_hash: str) -> dict:
    """
    The async 'heavy lifter' for startup idea validation.

    Execution order (matches the architecture design doc exactly):
      1. Self-idempotency check  — stop if this row is already completed
      2. Deduplication           — Redis cache FIRST, then DB fallback
      3. Distributed lock        — prevent concurrent workers on same task
      4. State → 'processing'
      5. AI pipeline             — Firecrawl + Gemini
      6. Write-through to DB     — Supabase is source of truth
      7. Cache in Redis          — result + idea_hash for future dedup
      8. Publish WebSocket event — includes full report_json
    """
    lock = None  # Initialised here so the finally block can always reference it safely.

    try:
        # ------------------------------------------------------------------
        # STEP 1: SELF-IDEMPOTENCY CHECK
        # Guards against broker redelivery after a successful task. Without
        # this, acks_late + a broker hiccup would re-run the full AI pipeline
        # on an already-completed row, wasting money and crashing on the DB
        # write (the row is already in 'completed' state).
        # ------------------------------------------------------------------
        own_row = (
            supabase.table("validations")
            .select("status")
            .eq("id", validation_id)
            .single()
            .execute()
        )
        # BUG FIX: Explicit None guard before .get(). If the row was deleted
        # before this task ran, .single() raises a PostgREST 406 — but if it
        # returns empty data for any other reason, .get() on None crashes.
        # We now handle both cases with a clear abort message.
        if not own_row.data:
            print(f"[Worker] Row {validation_id} not found. Aborting.", flush=True)
            return {"status": "aborted", "message": "Validation row not found."}

        if own_row.data.get("status") == "completed":
            print(f"[Worker] Idempotency: {validation_id} already completed. Skipping.", flush=True)
            return {"status": "skipped", "message": "Already completed."}

        # ------------------------------------------------------------------
        # STEP 2: DEDUPLICATION — Redis FIRST, then DB fallback
        #
        # BUG FIX: The previous version skipped the Redis idea_hash cache and
        # went directly to Supabase for deduplication. The cache written in
        # Step 7 was never read, defeating its purpose entirely and adding an
        # unnecessary DB round-trip on every duplicate idea submission.
        #
        # Architecture spec: "Check idea_hash:<hash> — If exists → reuse result"
        # This must consult Redis before hitting the DB.
        # ------------------------------------------------------------------
        hash_cache_key = f"idea_hash:{idea_hash}"
        cached_result_raw = redis_client.get(hash_cache_key)

        if cached_result_raw:
            # Redis cache HIT — reuse the cached result immediately.
            print(f"[Worker] Redis dedup hit for idea_hash {idea_hash[:16]}…", flush=True)
            try:
                cached = json.loads(cached_result_raw)
                _update_validation(validation_id, {
                    "status": "completed",
                    "report_json": cached.get("report_json"),
                    "markdown_report": cached.get("markdown_report"),
                    "tokens_used": cached.get("tokens_used", 0),
                    "estimated_cost": cached.get("estimated_cost", 0.0),
                })
                _publish_event(validation_id, {
                    "validation_id": validation_id,
                    "status": "completed",
                    "report_json": cached.get("report_json"),
                })
                return {"status": "completed", "message": "Deduplicated from Redis cache."}
            except (json.JSONDecodeError, Exception) as cache_err:
                # Corrupt/stale cache entry — log and fall through to DB.
                print(
                    f"[Worker] Redis cache parse error for {hash_cache_key}: {cache_err}. "
                    "Falling through to DB dedup.",
                    flush=True,
                )

        # Redis MISS — check Supabase for a completed row with the same hash.
        dup = (
            supabase.table("validations")
            .select("report_json, markdown_report, tokens_used, estimated_cost")
            .eq("idea_hash", idea_hash)
            .eq("status", "completed")
            .neq("id", validation_id)
            .limit(1)
            .execute()
        )

        if dup.data:
            dup_data = dup.data[0]
            print(f"[Worker] DB dedup hit for {validation_id}.", flush=True)
            try:
                _update_validation(validation_id, {
                    "status": "completed",
                    "report_json": dup_data.get("report_json"),
                    "markdown_report": dup_data.get("markdown_report"),
                    "tokens_used": dup_data.get("tokens_used", 0),
                    "estimated_cost": dup_data.get("estimated_cost", 0.0),
                })
                # Back-fill the Redis cache so the NEXT duplicate hits Redis, not DB.
                redis_client.setex(
                    hash_cache_key,
                    86400,
                    json.dumps({
                        "report_json": dup_data.get("report_json"),
                        "markdown_report": dup_data.get("markdown_report"),
                        "tokens_used": dup_data.get("tokens_used", 0),
                        "estimated_cost": dup_data.get("estimated_cost", 0.0),
                    }),
                )
                _publish_event(validation_id, {
                    "validation_id": validation_id,
                    "status": "completed",
                    "report_json": dup_data.get("report_json"),
                })
                return {"status": "completed", "message": "Deduplicated from DB."}
            except Exception as update_err:
                err_str = str(update_err).lower()
                if "23505" in err_str or "unique constraint" in err_str:
                    print(f"[Worker] Unique constraint on dedup for {validation_id}.", flush=True)
                    _update_validation(validation_id, {
                        "status": "failed",
                        "error_message": (
                            "A completed validation for this idea already exists. "
                            "Database policy prevents duplicate completed records."
                        ),
                    })
                    _publish_event(validation_id, {
                        "validation_id": validation_id,
                        "status": "failed",
                        "error": "Duplicate validation detected.",
                    })
                    return {"status": "failed", "message": "Unique constraint on deduplication."}
                raise update_err

        # ------------------------------------------------------------------
        # STEP 3: ACQUIRE DISTRIBUTED LOCK
        # Created inside the try block so a Redis failure here triggers a
        # clean Celery retry rather than an unrecoverable NameError in finally.
        # Non-blocking: if another worker holds the lock for this validation_id,
        # this instance returns immediately instead of queuing behind it.
        # ------------------------------------------------------------------
        lock_key = f"lock:validation:{validation_id}"
        lock = redis_client.lock(lock_key, timeout=120)

        if not lock.acquire(blocking=False):
            print(f"[Worker] Lock held for {validation_id}. Skipping duplicate.", flush=True)
            return {"status": "skipped", "message": "Another worker is processing this."}

        # ------------------------------------------------------------------
        # STEP 4: MARK AS PROCESSING
        # ------------------------------------------------------------------
        processing_started_at = datetime.now(timezone.utc).isoformat()
        _update_validation(validation_id, {
            "status": "processing",
            "processing_started_at": processing_started_at,
        })
        print(f"[Worker] AI pipeline starting for {validation_id}.", flush=True)

        # Fetch idea text from DB — Supabase is the single source of truth.
        # BUG FIX: Added explicit `row.data` guard. If the row was deleted
        # between Step 4 and here, .single() raises a PostgREST 406 whose
        # error message is opaque in logs. The guard provides a clear abort.
        row = (
            supabase.table("validations")
            .select("idea_description")
            .eq("id", validation_id)
            .single()
            .execute()
        )
        if not row.data:
            print(f"[Worker] Row {validation_id} deleted before AI pipeline. Aborting.", flush=True)
            return {"status": "aborted", "message": "Row deleted before processing."}

        idea_description: str = row.data.get("idea_description", "")

        # ------------------------------------------------------------------
        # STEP 5: AI PIPELINE
        # ------------------------------------------------------------------
        competitor_data = firecrawl_scrape(idea_description)
        report_json, markdown_report, tokens, cost = generate_ai_report(
            idea_description, competitor_data
        )
        print(f"[Worker] AI pipeline complete for {validation_id}. tokens={tokens}", flush=True)

        # ------------------------------------------------------------------
        # STEP 6: WRITE-THROUGH — persist to Supabase (source of truth)
        # ------------------------------------------------------------------
        _update_validation(validation_id, {
            "status": "completed",
            "report_json": report_json,
            "markdown_report": markdown_report,
            "tokens_used": tokens,
            "estimated_cost": cost,
        })

        # ------------------------------------------------------------------
        # STEP 7: CACHE IN REDIS (write-through, TTL = 24 hours)
        # Two keys:
        #   validation:result:<id>  — per-request result cache
        #   idea_hash:<hash>        — cross-request dedup cache (read in Step 2)
        # ------------------------------------------------------------------
        dedup_payload = json.dumps({
            "report_json": report_json,
            "markdown_report": markdown_report,
            "tokens_used": tokens,
            "estimated_cost": cost,
        })

        redis_client.setex(
            f"validation:result:{validation_id}",
            86400,
            json.dumps({
                "validation_id": validation_id,
                "status": "completed",
                "report_json": report_json,
            }),
        )
        redis_client.setex(hash_cache_key, 86400, dedup_payload)

        # ------------------------------------------------------------------
        # STEP 8: PUBLISH WEBSOCKET EVENT
        # BUG FIX: The previous version sent only {"validation_id", "status"}.
        # The architecture spec says the push must include `data: report` so
        # the frontend updates immediately without a separate HTTP round-trip.
        # report_json is now included in the event payload.
        # ------------------------------------------------------------------
        _publish_event(validation_id, {
            "validation_id": validation_id,
            "status": "completed",
            "report_json": report_json,
        })
        print(f"[Worker] Completion event published for {validation_id}.", flush=True)
        return {"status": "completed", "message": "Processed successfully."}

    except Retry:
        raise  # Celery's own Retry signal — never intercept it.

    except Exception as e:
        error_message = str(e)
        print(
            f"[Worker] Error for {validation_id} "
            f"(attempt {self.request.retries + 1}/{self.max_retries + 1}): {error_message}",
            flush=True,
        )

        is_final_attempt = self.request.retries >= self.max_retries

        if is_final_attempt:
            try:
                _update_validation(validation_id, {
                    "status": "failed",
                    "error_message": error_message,
                })
                _publish_event(validation_id, {
                    "validation_id": validation_id,
                    "status": "failed",
                    "error": error_message,
                })
            except Exception as cleanup_err:
                print(f"[Worker] Could not write failure state for {validation_id}: {cleanup_err}", flush=True)
        else:
            # Reset to 'pending' so the retry sees a clean slate.
            try:
                _update_validation(validation_id, {"status": "pending"})
            except Exception as reset_err:
                print(f"[Worker] Could not reset status for {validation_id}: {reset_err}", flush=True)

        # Exponential backoff: 30s, 60s for 429s, otherwise 5s, 10s
        countdown = 5 * (2 ** self.request.retries)
        if "429" in error_message or "resource_exhausted" in error_message.lower():
            countdown = 30 * (2 ** self.request.retries)
            
        raise self.retry(exc=e, countdown=countdown)

    finally:
        # Release the distributed lock in ALL exit paths: success, retry, final failure.
        # `lock` is None if Redis was unavailable before the lock could be created.
        if lock is not None and lock.owned():
            try:
                lock.release()
            except Exception as lock_err:
                print(f"[Worker] Could not release lock for {validation_id}: {lock_err}", flush=True)