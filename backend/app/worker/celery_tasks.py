# celery_tasks.py
# ---------------------------------------------------------------------------
# THE HEAVY LIFTER — Complete pipeline orchestration.
#
# This module wires together ALL Tier 1, Tier 2, & Tier 3 features into a
# single coherent validation pipeline:
#
#   1.  Self-idempotency check
#   2.  Deduplication — Redis first, DB fallback
#   3.  Distributed lock
#   4.  State → 'processing'
#   5.  Firecrawl competitor discovery
#   6.  RAG: chunk + embed + store (Feature 2)
#   7.  RAG: retrieve grounded context (Feature 2)
#   8.  Parallel AI: Gemini + Groq with self-heal (Features 1 + 3)
#   9.  Consensus merge (Feature 1) → STREAM partial event (Feature 11)
#  10.  Parallel data pipelines with progressive streaming (Features 5–10, 11):
#       pricing, funding, sentiment, patents, jobs, traffic
#       Each pipeline publishes a partial WebSocket event the INSTANT it
#       finishes, so the frontend can render sections live.
#  11.  Temporal version tracking (Feature 4)
#  12.  Write-through to Supabase
#  13.  Cache in Redis
#  14.  Publish final WebSocket event
#
# ALSO INCLUDES:
#   - `rerun_due_validations` periodic task for Celery Beat (Feature 4)
#   - RedBeat schedule configuration
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import redis
from celery import Celery
from celery.exceptions import Retry
from supabase import create_client, Client

from app.core.config import settings
from app.worker.celery_beat import BEAT_SCHEDULE, REDBEAT_CONFIG

# ── Service imports (all Tier 1, 2, & 3 features) ───────────────────
from app.services.ai_pipeline import (
    firecrawl_scrape,
    generate_gemini_report,
    generate_groq_report,
    embed_text,
)
from app.services.consensus import merge_reports
from app.services.rag import chunk_text, embed_and_store_chunks, retrieve_context
from app.services.pricing import run_pricing_pipeline
from app.services.funding import run_funding_pipeline
from app.services.sentiment import run_sentiment_pipeline
from app.services.patents import run_patent_pipeline
from app.services.jobs import run_jobs_pipeline
from app.services.traffic import run_traffic_pipeline
from app.services.temporal import run_temporal_comparison
from app.services.alerts import process_alert
from app.services.webhooks import dispatch_validation_webhook, register_webhook_task
from app.core.telemetry import track_pipeline
from app.services.cost_guard import check_and_charge_limit, reconcile_cost, CostLimitExceeded


# =====================================================================
# 1. INFRASTRUCTURE INITIALIZATION
# =====================================================================

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
    task_time_limit=600,          # Hard kill after 10 minutes (extended for multi-model + data pipelines)
    task_soft_time_limit=540,     # SoftTimeLimitExceeded at 9 minutes
    broker_connection_retry_on_startup=True,

    # ── Feature 17: Priority & Dead Letter Queues ────────────────────
    task_routes={
        "app.worker.celery_tasks.*": {"queue": "default"},
        "app.services.webhooks.*": {"queue": "webhooks"},
    },
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
        "webhooks": {
            "exchange": "webhooks",
            "routing_key": "webhooks",
        },
        "dlq": {
            "exchange": "dlx",
            "routing_key": "dlq",
        },
    },

    # ── Celery Beat (RedBeat) ────────────────────────────────────────
    beat_schedule=BEAT_SCHEDULE,
    **REDBEAT_CONFIG,
)

# Register the webhook task with Celery
deliver_webhook_task = register_webhook_task()

# Synchronous Redis client for the Celery worker process.
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

# Supabase client with service role key (bypasses RLS).
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


# =====================================================================
# 2. HELPERS
# =====================================================================

def _update_validation(validation_id: str, fields: dict) -> None:
    """
    Updates a validation row. Filters out empty vectors to avoid
    Supabase pgvector 'Error 22000' on empty lists.
    """
    filtered_fields = {
        k: v for k, v in fields.items()
        if not (isinstance(v, (list, tuple)) and len(v) == 0)
    }
    filtered_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = (
        supabase.table("validations")
        .update(filtered_fields)
        .eq("id", validation_id)
        .execute()
    )
    if not result.data:
        print(
            f"[Worker] WARNING: update for {validation_id} matched no rows.",
            flush=True,
        )


def _publish_event(validation_id: str, payload: dict) -> None:
    """Publishes a JSON event to Redis Pub/Sub for WebSocket dispatch."""
    redis_client.publish("validation_events", json.dumps(payload))


def _extract_competitor_names(competitor_urls: List[str]) -> List[str]:
    """Extracts clean domain names from competitor URLs."""
    names = []
    for url in competitor_urls:
        try:
            parsed = urlparse(url)
            name = parsed.netloc.replace("www.", "")
            if name and name not in names:
                names.append(name)
        except Exception:
            continue
    return names


# =====================================================================
# 3. MAIN CELERY TASK — THE FULL PIPELINE
# =====================================================================

@celery_app.task(
    bind=True,
    name="app.worker.celery_tasks.process_validation",
    max_retries=2,
    acks_late=True,
)
def process_validation(self, validation_id: str, idea_hash: str) -> dict:
    """
    The full validation pipeline orchestrating all Tier 1 & 2 features.

    Pipeline steps:
      1.  Self-idempotency check
      2.  Deduplication (Redis → DB)
      3.  Distributed lock
      4.  State → 'processing'
      5.  Firecrawl competitor discovery
      6.  RAG: chunk + embed + store
      7.  RAG: retrieve grounded context
      8.  Parallel AI: Gemini + Groq (with self-heal)
      9.  Consensus merge
      10. Parallel data pipelines: pricing + funding + sentiment
      11. Temporal version tracking
      12. Write-through to Supabase
      13. Cache in Redis
      14. Publish WebSocket event
    """
    lock = None

    # Track entire pipeline via OpenTelemetry (Feature 18)
    with track_pipeline(validation_id) as pipeline_span:
        try:
            # ── STEP 1: SELF-IDEMPOTENCY CHECK ───────────────────────────
            own_row = (
                supabase.table("validations")
                .select("status, user_id")
                .eq("id", validation_id)
                .single()
                .execute()
            )
            if not own_row.data:
                print(f"[Worker] Row {validation_id} not found. Aborting.", flush=True)
                return {"status": "aborted", "message": "Validation row not found."}

            if own_row.data.get("status") == "completed":
                print(f"[Worker] Idempotency: {validation_id} already completed.", flush=True)
                return {"status": "skipped", "message": "Already completed."}

            # ── STEP 2: DEDUPLICATION — Redis FIRST, DB fallback ─────────
            hash_cache_key = f"idea_hash:{idea_hash}"
            cached_result_raw = redis_client.get(hash_cache_key)

            if cached_result_raw:
                print(f"[Worker] Redis dedup hit for {idea_hash[:16]}…", flush=True)
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
                    return {"status": "completed", "message": "Deduplicated from Redis."}
                except (json.JSONDecodeError, Exception) as cache_err:
                    print(f"[Worker] Redis cache parse error: {cache_err}. Falling through.", flush=True)

            # DB fallback dedup
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
                    redis_client.setex(hash_cache_key, 86400, json.dumps({
                        "report_json": dup_data.get("report_json"),
                        "markdown_report": dup_data.get("markdown_report"),
                        "tokens_used": dup_data.get("tokens_used", 0),
                        "estimated_cost": dup_data.get("estimated_cost", 0.0),
                    }))
                    _publish_event(validation_id, {
                        "validation_id": validation_id,
                        "status": "completed",
                        "report_json": dup_data.get("report_json"),
                    })
                    return {"status": "completed", "message": "Deduplicated from DB."}
                except Exception as update_err:
                    err_str = str(update_err).lower()
                    if "23505" in err_str or "unique constraint" in err_str:
                        _update_validation(validation_id, {
                            "status": "completed",
                            "idea_hash": f"{idea_hash}:dup:{validation_id[:8]}",
                            "report_json": dup_data.get("report_json"),
                            "markdown_report": dup_data.get("markdown_report"),
                        })
                        _publish_event(validation_id, {
                            "validation_id": validation_id,
                            "status": "completed",
                            "report_json": dup_data.get("report_json"),
                        })
                        return {"status": "completed", "message": "Deduplicated (bypassed conflict)."}
                    raise update_err

            # ── STEP 3: DISTRIBUTED LOCK ─────────────────────────────────
            lock_key = f"lock:validation:{validation_id}"
            lock = redis_client.lock(lock_key, timeout=300)  # Extended for multi-model pipeline

            if not lock.acquire(blocking=False):
                print(f"[Worker] Lock held for {validation_id}. Skipping.", flush=True)
                return {"status": "skipped", "message": "Another worker is processing this."}

            # ── STEP 4: STATE → PROCESSING ───────────────────────────────
            _update_validation(validation_id, {
                "status": "processing",
                "processing_started_at": datetime.now(timezone.utc).isoformat(),
            })
            print(f"[Worker] Pipeline starting for {validation_id}.", flush=True)

            # Fetch idea text
            row = (
                supabase.table("validations")
                .select("idea_description, target_market, budget_constraints")
                .eq("id", validation_id)
                .single()
                .execute()
            )
            if not row.data:
                return {"status": "aborted", "message": "Row deleted before processing."}

            idea_description: str = row.data.get("idea_description", "")
            target_market: str = row.data.get("target_market", "") or ""
            budget_constraints: str = row.data.get("budget_constraints", "") or ""

            # Enrich the idea text with context for better analysis
            enriched_idea = idea_description
            if target_market:
                enriched_idea += f"\nTarget Market: {target_market}"
            if budget_constraints:
                enriched_idea += f"\nBudget Constraints: {budget_constraints}"

            # ── Feature 19: AI COST CONTROL (PRE-FLIGHT CHECK) ───────────
            # Estimate: consensus (Gemini + Groq) + 3 data pipelines (patents, jobs, traffic)
            # Roughly $0.005 estimated cost for the whole flow
            estimated_pipeline_cost = 0.005
            user_id = own_row.data.get("user_id")
            if user_id:
                try:
                    check_and_charge_limit(user_id, estimated_pipeline_cost)
                except CostLimitExceeded as cle:
                    print(f"[Worker] 🛑 Cost limit exceeded for {validation_id}: {cle}", flush=True)
                    _update_validation(validation_id, {
                        "status": "failed",
                        "error_message": str(cle),
                    })
                    _publish_event(validation_id, {
                        "validation_id": validation_id,
                        "status": "failed",
                        "error": str(cle),
                    })
                    return {"status": "failed", "message": "Cost limit exceeded."}

            # ── STEP 5: FIRECRAWL COMPETITOR DISCOVERY ───────────────────
            competitor_data, competitor_urls = firecrawl_scrape(idea_description)
            competitor_names = _extract_competitor_names(competitor_urls)
            print(f"[Worker] Found {len(competitor_urls)} competitor URLs.", flush=True)

            # ── STEP 6: RAG — CHUNK + EMBED + STORE ─────────────────────
            chunks = chunk_text(competitor_data, chunk_size_tokens=500)
            if chunks:
                embed_and_store_chunks(
                    validation_id=validation_id,
                    chunks=chunks,
                    source_urls=competitor_urls,
                )

            # ── STEP 7: RAG — RETRIEVE GROUNDED CONTEXT ─────────────────
            grounding_context = retrieve_context(
                query_text=enriched_idea,
                validation_id=validation_id,
                top_k=10,
            )

            # ── STEP 8: PARALLEL AI — GEMINI + GROQ (with self-heal) ────
            # Both are I/O-bound HTTP calls. Run in parallel via ThreadPool.
            gemini_result: Optional[tuple] = None
            groq_result: Optional[tuple] = None

            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="ai") as executor:
                gemini_future = executor.submit(
                    generate_gemini_report,
                    idea_description=enriched_idea,
                    competitor_data=competitor_data,
                    grounding_context=grounding_context,
                )
                groq_future = executor.submit(
                    generate_groq_report,
                    idea_description=enriched_idea,
                    competitor_data=competitor_data,
                    grounding_context=grounding_context,
                )

                # Wait for both — but don't let one failure kill the other
                try:
                    gemini_result = gemini_future.result(timeout=180)
                except Exception as e:
                    print(f"[Worker] Gemini failed: {e}", flush=True)

                try:
                    groq_result = groq_future.result(timeout=60)
                except Exception as e:
                    print(f"[Worker] Groq failed: {e}", flush=True)

            # At least one model must succeed
            if gemini_result is None and groq_result is None:
                raise RuntimeError("Both Gemini and Groq failed. Cannot produce report.")

            # Unpack results
            gemini_report_json, gemini_markdown, gemini_tokens, gemini_cost, gemini_model = (
                gemini_result if gemini_result else ({}, "", 0, 0.0, "")
            )
            groq_report_json, groq_markdown, groq_tokens, groq_cost, groq_model = (
                groq_result if groq_result else ({}, "", 0, 0.0, "")
            )

            total_tokens = gemini_tokens + groq_tokens
            total_cost = gemini_cost + groq_cost

            # ── STEP 9: CONSENSUS MERGE ──────────────────────────────────
            if gemini_result and groq_result:
                # Both models succeeded — full consensus merge
                consensus = merge_reports(
                    gemini_report=gemini_report_json,
                    gemini_markdown=gemini_markdown,
                    gemini_model=gemini_model,
                    groq_report=groq_report_json,
                    groq_markdown=groq_markdown,
                    groq_model=groq_model,
                )
                final_report_json = consensus.report.model_dump()
                final_markdown = consensus.markdown
                consensus_confidence = consensus.overall_confidence
                model_agreement = [fa.model_dump() for fa in consensus.field_agreement]
                model_version = f"consensus:{gemini_model}+{groq_model}"
            elif gemini_result:
                # Only Gemini succeeded — use it directly
                final_report_json = gemini_report_json
                final_markdown = gemini_markdown
                consensus_confidence = None
                model_agreement = None
                model_version = gemini_model
            else:
                # Only Groq succeeded — use it directly
                final_report_json = groq_report_json
                final_markdown = groq_markdown
                consensus_confidence = None
                model_agreement = None
                model_version = groq_model

            print(
                f"[Worker] AI complete: tokens={total_tokens}, model={model_version}",
                flush=True,
            )

            # ── FEATURE 11: PROGRESSIVE STREAMING — Consensus ready ──────
            # Publish the consensus report immediately so the frontend can
            # start rendering while data pipelines are still running.
            _publish_event(validation_id, {
                "validation_id": validation_id,
                "status": "processing",
                "section": "consensus",
                "data": {
                    "report_json": final_report_json,
                    "consensus_confidence": consensus_confidence,
                    "model_version": model_version,
                },
            })
            print(f"[Worker] ⚡ Streamed 'consensus' section for {validation_id}.", flush=True)

            # ── STEP 10: PARALLEL DATA PIPELINES (Features 5–10) ─────────
            # All 6 data pipelines run in parallel. Each publishes a partial
            # WebSocket event the INSTANT it finishes (Feature 11: Progressive
            # Streaming), so the frontend can render sections live without
            # waiting for the entire pipeline to complete.
            pricing_report = None
            funding_report = None
            sentiment_report = None
            patent_report = None
            jobs_report = None
            traffic_report = None

            with ThreadPoolExecutor(max_workers=6, thread_name_prefix="data") as executor:
                futures = {}

                if competitor_urls:
                    futures["pricing"] = executor.submit(
                        run_pricing_pipeline,
                        competitor_urls=competitor_urls,
                        validation_id=validation_id,
                    )
                    futures["funding"] = executor.submit(
                        run_funding_pipeline,
                        competitor_names=competitor_names,
                        validation_id=validation_id,
                    )

                futures["sentiment"] = executor.submit(
                    run_sentiment_pipeline,
                    competitor_names=competitor_names,
                    idea_description=idea_description,
                    validation_id=validation_id,
                )

                # Feature 8: Patent & IP scan
                futures["patents"] = executor.submit(
                    run_patent_pipeline,
                    idea_description=idea_description,
                    competitor_names=competitor_names,
                    validation_id=validation_id,
                )

                # Feature 9: Job posting signal
                if competitor_names:
                    futures["jobs"] = executor.submit(
                        run_jobs_pipeline,
                        competitor_names=competitor_names,
                        idea_description=idea_description,
                        validation_id=validation_id,
                    )

                # Feature 10: Web traffic intelligence
                if competitor_names:
                    futures["traffic"] = executor.submit(
                        run_traffic_pipeline,
                        competitor_names=competitor_names,
                        idea_description=idea_description,
                        validation_id=validation_id,
                    )

                # ── FEATURE 11: PROGRESSIVE STREAMING ────────────────────
                # Use as_completed() so we publish each section the INSTANT
                # its future resolves, not after all futures finish.
                future_to_name = {v: k for k, v in futures.items()}

                for completed_future in as_completed(futures.values(), timeout=180):
                    name = future_to_name.get(completed_future, "unknown")
                    try:
                        result = completed_future.result()

                        # Store the result in the appropriate variable
                        if name == "pricing":
                            pricing_report = result
                        elif name == "funding":
                            funding_report = result
                        elif name == "sentiment":
                            sentiment_report = result
                        elif name == "patents":
                            patent_report = result
                        elif name == "jobs":
                            jobs_report = result
                        elif name == "traffic":
                            traffic_report = result

                        # ── STREAM THIS SECTION IMMEDIATELY ──────────────
                        # The frontend receives this partial payload and can
                        # render the section before the full pipeline is done.
                        section_data = result.model_dump() if hasattr(result, "model_dump") else {}
                        _publish_event(validation_id, {
                            "validation_id": validation_id,
                            "status": "processing",
                            "section": name,
                            "data": section_data,
                        })
                        print(f"[Worker] ⚡ Streamed '{name}' section for {validation_id}.", flush=True)

                    except Exception as e:
                        print(f"[Worker] {name.title()} pipeline failed (non-fatal): {e}", flush=True)

            # ── STEP 11: TEMPORAL VERSION TRACKING ───────────────────────
            temporal_diff = run_temporal_comparison(
                validation_id=validation_id,
                new_report_json=final_report_json,
                new_markdown=final_markdown,
                idea_description=idea_description,
                tokens_used=total_tokens,
                estimated_cost=total_cost,
                model_version=model_version,
            )

            # ── STEP 11b: SMART ALERTS (Feature 16) ─────────────────────
            # If the temporal diff detected a significant change (> 0.3),
            # dispatch alerts via Redis Pub/Sub + email.
            process_alert(
                validation_id=validation_id,
                temporal_diff=temporal_diff,
                idea_description=idea_description,
            )

            # ── STEP 12: WRITE-THROUGH TO SUPABASE ──────────────────────
            idea_embedding = embed_text(idea_description)

            update_payload: Dict[str, Any] = {
                "status": "completed",
                "report_json": final_report_json,
                "markdown_report": final_markdown,
                "tokens_used": total_tokens,
                "estimated_cost": total_cost,
                "model_version": model_version,
                "idea_embedding": idea_embedding,
                # Consensus fields (Feature 1)
                "gemini_report": gemini_report_json if gemini_result else None,
                "groq_report": groq_report_json if groq_result else None,
                "consensus_confidence": consensus_confidence,
                "model_agreement": model_agreement,
                # Data pipeline summaries (Features 5–10)
                "pricing_data": pricing_report.model_dump() if pricing_report else None,
                "funding_data": funding_report.model_dump() if funding_report else None,
                "sentiment_data": sentiment_report.model_dump() if sentiment_report else None,
                "patent_data": patent_report.model_dump() if patent_report else None,
                "jobs_data": jobs_report.model_dump() if jobs_report else None,
                "traffic_data": traffic_report.model_dump() if traffic_report else None,
            }

            _update_validation(validation_id, update_payload)

            # ── STEP 13: CACHE IN REDIS ──────────────────────────────────
            dedup_payload = json.dumps({
                "report_json": final_report_json,
                "markdown_report": final_markdown,
                "tokens_used": total_tokens,
                "estimated_cost": total_cost,
            })

            redis_client.setex(
                f"validation:result:{validation_id}",
                86400,
                json.dumps({
                    "validation_id": validation_id,
                    "status": "completed",
                    "report_json": final_report_json,
                    "consensus_confidence": consensus_confidence,
                }),
            )
            redis_client.setex(hash_cache_key, 86400, dedup_payload)

            # ── STEP 14: PUBLISH FINAL WEBSOCKET EVENT ───────────────────
            # This is the "all done" signal. The frontend may have already
            # rendered most sections via progressive streaming (Feature 11),
            # but this final event confirms the pipeline is fully complete.
            _publish_event(validation_id, {
                "validation_id": validation_id,
                "status": "completed",
                "report_json": final_report_json,
                "consensus_confidence": consensus_confidence,
                "model_version": model_version,
            })

            # ── Feature 19: RECONCILE COST ───────────────────────────────────
            if user_id:
                reconcile_cost(user_id, estimated_pipeline_cost, total_cost)

            # ── Feature 20: OUTBOUND WEBHOOK DISPATCH ────────────────────────
            dispatch_validation_webhook(
                validation_id=validation_id,
                status="completed",
                report_json=final_report_json,
            )

            print(f"[Worker] ✅ Pipeline complete for {validation_id}.", flush=True)
            return {"status": "completed", "message": "Processed successfully."}

        except CostLimitExceeded:
            # Don't retry if it's a hard cost limit failure
            raise

        except Retry:
            raise

        except Exception as e:
            error_message = str(e)
            retry_count = self.request.retries + 1

            print(
                f"[Worker] Error for {validation_id} "
                f"(attempt {retry_count}/{self.max_retries + 1}): {error_message}",
                flush=True,
            )

            is_final_attempt = self.request.retries >= self.max_retries

            if is_final_attempt:
                try:
                    _update_validation(validation_id, {
                        "status": "failed",
                        "error_message": error_message,
                        "retry_count": retry_count,
                        "last_retry_at": datetime.now(timezone.utc).isoformat(),
                    })
                    _publish_event(validation_id, {
                        "validation_id": validation_id,
                        "status": "failed",
                        "error": error_message,
                    })
                except Exception as cleanup_err:
                    print(f"[Worker] Could not write failure state: {cleanup_err}", flush=True)
            
                # Dispatch failure webhook (Feature 20)
                dispatch_validation_webhook(
                    validation_id=validation_id,
                    status="failed",
                )
            else:
                try:
                    _update_validation(validation_id, {
                        "status": "pending",
                        "retry_count": retry_count,
                        "last_retry_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as reset_err:
                    print(f"[Worker] Could not reset status: {reset_err}", flush=True)

            countdown = 5 * (2 ** self.request.retries)
            if "429" in error_message or "resource_exhausted" in error_message.lower():
                countdown = 30 * (2 ** self.request.retries)

            raise self.retry(exc=e, countdown=countdown)

        finally:
            if lock is not None and lock.owned():
                try:
                    lock.release()
                except Exception as lock_err:
                    print(f"[Worker] Could not release lock: {lock_err}", flush=True)


# =====================================================================
# 4. PERIODIC TASK — TEMPORAL RE-RUNS (Feature 4)
#
# Called by Celery Beat (weekly). Finds all completed validations
# and dispatches them for re-processing to track temporal changes.
# =====================================================================

@celery_app.task(
    name="app.worker.celery_tasks.rerun_due_validations",
    max_retries=1,
)
def rerun_due_validations() -> dict:
    """
    Periodic task: finds completed validations and dispatches re-runs
    for temporal trend tracking.

    This task itself is lightweight — it only queries the DB and
    dispatches individual process_validation tasks. The heavy lifting
    happens in those dispatched tasks.

    Runs weekly via Celery Beat (configured in celery_beat.py).
    """
    print("[Beat] Starting weekly validation re-run scan.", flush=True)

    try:
        # Find all completed validations
        # In production, add filtering:
        #   - Only validations from the last 90 days
        #   - Only validations where the user has opted into monitoring
        #   - Limit to N re-runs per Beat cycle
        result = (
            supabase.table("validations")
            .select("id, idea_hash")
            .eq("status", "completed")
            .limit(50)  # Cap at 50 re-runs per cycle
            .execute()
        )

        if not result.data:
            print("[Beat] No validations due for re-run.", flush=True)
            return {"status": "done", "dispatched": 0}

        dispatched = 0
        for row in result.data:
            v_id = row["id"]
            idea_hash = row.get("idea_hash", "")

            # Don't re-run duplicates (they share the same hash)
            if ":dup:" in idea_hash:
                continue

            # Dispatch with low priority so live requests are served first
            celery_app.send_task(
                "app.worker.celery_tasks.process_validation",
                kwargs={"validation_id": v_id, "idea_hash": idea_hash},
                priority=3,
            )
            dispatched += 1

        print(f"[Beat] Dispatched {dispatched} re-runs.", flush=True)
        return {"status": "done", "dispatched": dispatched}

    except Exception as e:
        print(f"[Beat] Re-run scan failed: {e}", flush=True)
        return {"status": "failed", "error": str(e)}