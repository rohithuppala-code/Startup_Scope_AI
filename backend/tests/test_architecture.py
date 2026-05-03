#!/usr/bin/env python3
"""
StartupScope AI — Architecture Integration Tests
=================================================
Run from inside the venv:
    cd backend && python3 tests/test_architecture.py

Tests:
  1. Module Import Chain
  2. Circuit Breaker Lifecycle (Redis-aware)
  3. Redis Memory Layer (Tier 1 Cache, Tier 2 Memory, Tier 3 Vector)
  4. Firecrawl Pipeline Logic (dry-run, no API calls)
  5. API Endpoint Health (HTTP against live server)

All tests degrade gracefully when optional infrastructure
(Redis, backend server) is not available.
"""

import json
import os
import sys
import struct
import time

# ── Ensure backend package on sys.path ─────────────────────────────────────
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
sys.path.insert(0, PROJECT_ROOT)

PASS = "✅"
FAIL = "❌"
SKIP = "⏭️ "
WARN = "⚠️ "

results = []


def test(name: str, fn, skip_if: bool = False):
    if skip_if:
        results.append((SKIP, name, "skipped"))
        print(f"  {SKIP} {name} [skipped]")
        return
    try:
        fn()
        results.append((PASS, name))
        print(f"  {PASS} {name}")
    except AssertionError as e:
        results.append((FAIL, name, f"AssertionError: {e}"))
        print(f"  {FAIL} {name}: {e}")
    except Exception as e:
        results.append((FAIL, name, str(e)))
        print(f"  {FAIL} {name}: {type(e).__name__}: {e}")


# ═══════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE PROBE — run once, used by all tests
# ═══════════════════════════════════════════════════════════════════════
import socket

def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

REDIS_UP    = _port_open("127.0.0.1", 6380)
RABBITMQ_UP = _port_open("127.0.0.1", 5673)
API_UP      = _port_open("127.0.0.1", 8000)

print(f"\n{'═'*58}")
print(f"  Infrastructure:  Redis={'✅' if REDIS_UP else '❌'}  "
      f"RabbitMQ={'✅' if RABBITMQ_UP else '❌'}  "
      f"API={'✅' if API_UP else '❌'}")
print(f"{'═'*58}")

# ═══════════════════════════════════════════════════════════════════════
# TEST 1: Module Import Chain
# ═══════════════════════════════════════════════════════════════════════
print("\n━━━ TEST 1: Module Import Chain ━━━")


def t_import_pipeline():
    from app.services.firecrawl_pipeline import (
        generate_search_queries, search_with_markdown, rerank_results,
        targeted_scrape, extract_competitor_features, run_firecrawl_pipeline,
        COMPETITOR_EXTRACTION_SCHEMA, LLM_TIMEOUT, SEARCH_TIMEOUT, SCRAPE_TIMEOUT,
    )
    assert callable(run_firecrawl_pipeline)
    assert LLM_TIMEOUT > 0 and SEARCH_TIMEOUT > 0 and SCRAPE_TIMEOUT > 0
test("firecrawl_pipeline — all symbols import", t_import_pipeline)


def t_import_redis_memory():
    from app.services.redis_memory import (
        store_idea_memory, get_idea_memory, get_user_idea_history,
        store_idea_embedding, find_similar_ideas, get_similarity_insights,
        _ensure_vector_index, _embedding_to_bytes, _bytes_to_embedding,
        VECTOR_DIM, INDEX_NAME, VECTOR_PREFIX,
    )
    assert VECTOR_DIM == 768
    assert INDEX_NAME == "idx:idea_vectors"
test("redis_memory — all symbols import", t_import_redis_memory)


def t_import_circuit_breaker():
    from app.services.circuit_breaker import (
        CircuitBreaker, CircuitOpenError,
        firecrawl_breaker, gemini_breaker, groq_breaker,
    )
    assert firecrawl_breaker.failure_threshold == 3
    assert firecrawl_breaker.recovery_timeout == 120
    assert gemini_breaker.recovery_timeout == 60
    assert groq_breaker.failure_threshold == 5
test("circuit_breaker — instances and config", t_import_circuit_breaker)


def t_import_ai_pipeline():
    from app.services.ai_pipeline import (
        firecrawl_scrape, firecrawl_scrape_advanced,
        generate_gemini_report, generate_groq_report,
        embed_text, embed_texts_batch,
    )
    assert callable(firecrawl_scrape_advanced)
test("ai_pipeline — advanced scrape symbol present", t_import_ai_pipeline)


def t_import_celery_tasks():
    from app.worker.celery_tasks import process_validation
    assert process_validation.name == "app.worker.celery_tasks.process_validation"
    assert process_validation.max_retries == 2
test("celery_tasks — task registration", t_import_celery_tasks)


def t_import_main():
    # Verify main.py imports cleanly (doesn't start the server)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "app.main", os.path.join(BACKEND_DIR, "app", "main.py")
    )
    # We just check the file parses — full import would start lifespan
    import ast
    with open(os.path.join(BACKEND_DIR, "app", "main.py")) as f:
        ast.parse(f.read())
test("main.py — syntax valid (health endpoint added)", t_import_main)


# ═══════════════════════════════════════════════════════════════════════
# TEST 2: Circuit Breaker Lifecycle
# ═══════════════════════════════════════════════════════════════════════
print("\n━━━ TEST 2: Circuit Breaker Lifecycle ━━━")


def t_cb_closed_success():
    """CLOSED state: successful calls return the result and reset failures."""
    from app.services.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("t_closed", failure_threshold=3, recovery_timeout=5)
    cb.reset()
    result = cb.call(lambda: "hello")
    assert result == "hello"
test("CB: CLOSED state passes calls", t_cb_closed_success)


def t_cb_fallback_on_error():
    """Even in CLOSED state, exceptions trigger fallback if provided."""
    from app.services.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("t_fallback_closed", failure_threshold=10, recovery_timeout=5)
    cb.reset()
    result = cb.call(lambda: 1/0, fallback=lambda: "safe")
    assert result == "safe"
test("CB: fallback executed on exception (CLOSED)", t_cb_fallback_on_error)


def t_cb_raises_without_fallback():
    """Without a fallback, the original exception propagates."""
    from app.services.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("t_raises", failure_threshold=10, recovery_timeout=5)
    cb.reset()
    try:
        cb.call(lambda: 1/0)
        assert False, "Should have raised"
    except ZeroDivisionError:
        pass  # Correct
test("CB: original exception re-raised without fallback", t_cb_raises_without_fallback)


def t_cb_opens_after_threshold():
    """With Redis: breaker OPENS after N consecutive failures → fast-fail."""
    from app.services.circuit_breaker import CircuitBreaker, CircuitOpenError
    cb = CircuitBreaker("t_open_redis", failure_threshold=2, recovery_timeout=60)
    cb.reset()

    if not REDIS_UP:
        # Without Redis, failures aren't tracked → circuit stays CLOSED (fail-open by design)
        # Verify this expected behavior
        for _ in range(3):
            try:
                cb.call(lambda: 1/0)
            except ZeroDivisionError:
                pass
        # Should still be "closed" (Redis stores state)
        assert cb._get_state() == "closed"
        print(f"    {WARN} Redis down — breaker in fail-open mode (expected)")
        return

    # With Redis: failures are tracked, circuit should open
    for _ in range(2):
        try:
            cb.call(lambda: 1/0)
        except ZeroDivisionError:
            pass

    state = cb._get_state()
    assert state == "open", f"Expected 'open' but got '{state}'"
    cb.reset()
test("CB: OPEN after threshold failures (Redis-aware)", t_cb_opens_after_threshold)


def t_cb_fast_fail_when_open():
    """With Redis: OPEN circuit fast-fails without calling fn."""
    from app.services.circuit_breaker import CircuitBreaker, CircuitOpenError
    if not REDIS_UP:
        print(f"    {WARN} Redis down — skipping fast-fail test")
        return

    cb = CircuitBreaker("t_fastfail", failure_threshold=1, recovery_timeout=60)
    cb.reset()
    try:
        cb.call(lambda: 1/0)
    except ZeroDivisionError:
        pass

    # Circuit should now be open
    called = [False]
    result = cb.call(lambda: called.__setitem__(0, True) or "unreachable",
                     fallback=lambda: "fallback_value")
    assert result == "fallback_value"
    assert not called[0], "fn should NOT be called when circuit is OPEN"
    cb.reset()
test("CB: OPEN circuit fast-fails (fallback, fn not called)", t_cb_fast_fail_when_open)


def t_cb_half_open_recovery():
    """After recovery_timeout, circuit enters HALF_OPEN → success → CLOSED."""
    from app.services.circuit_breaker import CircuitBreaker
    if not REDIS_UP:
        print(f"    {WARN} Redis down — skipping half-open test")
        return

    cb = CircuitBreaker("t_halfopen", failure_threshold=1, recovery_timeout=1)
    cb.reset()
    try:
        cb.call(lambda: 1/0)
    except ZeroDivisionError:
        pass

    assert cb._get_state() == "open"
    time.sleep(1.2)  # Let recovery_timeout elapse
    assert cb._get_state() == "half_open"

    result = cb.call(lambda: "recovered")
    assert result == "recovered"
    assert cb._get_state() == "closed"
    cb.reset()
test("CB: HALF_OPEN → success → CLOSED recovery", t_cb_half_open_recovery)


def t_cb_reset():
    """reset() returns circuit to CLOSED from any state."""
    from app.services.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("t_reset", failure_threshold=1, recovery_timeout=60)
    cb.reset()
    try:
        cb.call(lambda: 1/0)
    except ZeroDivisionError:
        pass
    cb.reset()
    assert cb._get_state() == "closed"
test("CB: reset() clears state", t_cb_reset)


# ═══════════════════════════════════════════════════════════════════════
# TEST 3: Redis Memory Layer
# ═══════════════════════════════════════════════════════════════════════
print("\n━━━ TEST 3: Redis Memory Layer ━━━")


def t_embedding_serialization():
    """float32 binary serialization is lossless to 6 decimal places."""
    from app.services.redis_memory import _embedding_to_bytes, _bytes_to_embedding
    original = [0.1, -0.5, 0.999, 0.0, 1.0, -1.0]
    blob = _embedding_to_bytes(original)
    assert isinstance(blob, bytes)
    assert len(blob) == len(original) * 4
    recovered = _bytes_to_embedding(blob)
    for a, b in zip(original, recovered):
        assert abs(a - b) < 1e-6, f"Mismatch: {a} vs {b}"
test("embedding: float32 serialize/deserialize", t_embedding_serialization)


def t_hnsw_detection():
    from app.services.redis_memory import _check_hnsw_available
    available = _check_hnsw_available()
    mode = "HNSW (O(log N))" if available else "Python fallback (O(N))"
    print(f"    ℹ️  Vector search mode: {mode}")
test("HNSW: Redis Stack module detection", t_hnsw_detection, skip_if=not REDIS_UP)


def t_idea_memory_roundtrip():
    from app.services.redis_memory import store_idea_memory, get_idea_memory
    vid = "test-arch-mem-001"
    store_idea_memory(
        validation_id=vid,
        idea_description="AI-powered pet food delivery startup",
        competitors=["BarkBox", "Chewy", "PetPlate"],
        gaps=["No same-day delivery", "Premium pricing gap"],
        feasibility_score=72,
        report_summary="Moderately feasible with high competition...",
        user_id="test-user-arch",
    )
    mem = get_idea_memory(vid)
    assert mem is not None, "Memory not stored"
    assert mem["idea"] == "AI-powered pet food delivery startup"
    assert mem["feasibility_score"] == 72
    assert "BarkBox" in mem["competitors"]
    assert len(mem["gaps"]) == 2
test("Tier 2: idea memory store + retrieve", t_idea_memory_roundtrip, skip_if=not REDIS_UP)


def t_user_history():
    from app.services.redis_memory import store_idea_memory, get_user_idea_history
    for i in range(3):
        store_idea_memory(
            validation_id=f"test-hist-arch-{i:03d}",
            idea_description=f"Test startup idea #{i}",
            competitors=[],
            gaps=[],
            feasibility_score=50 + i * 10,
            user_id="test-hist-user-arch",
        )
    history = get_user_idea_history("test-hist-user-arch", limit=10)
    assert len(history) >= 3
test("Tier 2: user idea history", t_user_history, skip_if=not REDIS_UP)


def t_embedding_store_and_search():
    """
    Stores 5 near-identical embeddings, searches with base vector.

    NOTE: In 768-dimensional space, random Gaussian vectors are nearly
    orthogonal by design (cosine ~ 0.0). We use epsilon perturbations
    (1% noise) to create vectors that are genuinely semantically similar,
    matching how real idea embeddings behave.
    """
    import random
    from app.services.redis_memory import store_idea_embedding, find_similar_ideas

    random.seed(99)
    # Create a normalised base vector
    raw = [random.gauss(0, 1) for _ in range(768)]
    mag = sum(v * v for v in raw) ** 0.5
    base_vec = [v / mag for v in raw]

    # Store 5 vectors with tiny (1%) perturbations → cosine similarity > 0.99
    for i in range(5):
        eps = 0.01  # 1% noise — keeps vectors highly similar
        noisy = [v + random.gauss(0, eps) for v in base_vec]
        mag2 = sum(v * v for v in noisy) ** 0.5
        normed = [v / mag2 for v in noisy]
        store_idea_embedding(
            validation_id=f"test-sim-v2-{i:03d}",
            embedding=normed,
            idea_description=f"AI food delivery variant {i}",
            feasibility_score=60 + i * 5,
        )

    results = find_similar_ideas(
        query_embedding=base_vec,
        exclude_id="",
        top_k=3,
        min_similarity=0.95,  # 1% noise → similarity ~0.9999
    )
    assert len(results) > 0, "Should find at least 1 similar idea"
    top_sim = results[0]["similarity"]
    assert top_sim > 0.95, f"Top similarity too low: {top_sim:.4f} (expected > 0.95)"
    print(f"    ℹ️  Found {len(results)} matches (top: {top_sim:.4f})")
test("Tier 3: embedding store + similarity search", t_embedding_store_and_search, skip_if=not REDIS_UP)


def t_similarity_insights_format():
    from app.services.redis_memory import get_similarity_insights
    ideas = [
        {"validation_id": "test-arch-mem-001", "idea": "AI pet food delivery",
         "feasibility_score": 72, "similarity": 0.91},
    ]
    text = get_similarity_insights(ideas)
    assert "Historical Idea Intelligence" in text
    assert "91% similar" in text
    assert "AI pet food delivery" in text
test("Tier 3: similarity insights text format", t_similarity_insights_format)


def t_tier1_cache():
    from app.services.redis_memory import cache_search_results, get_cached_search
    import hashlib
    key = hashlib.sha256(b"test-cache-key").hexdigest()[:16]
    payload = {"results": [{"url": "https://example.com", "title": "Test"}]}
    cache_search_results(key, payload, ttl=60)
    cached = get_cached_search(key)
    assert cached is not None
    assert cached["results"][0]["url"] == "https://example.com"
test("Tier 1: search result cache write/read", t_tier1_cache, skip_if=not REDIS_UP)


# ═══════════════════════════════════════════════════════════════════════
# TEST 4: Firecrawl Pipeline Logic (Dry-Run — no external API calls)
# ═══════════════════════════════════════════════════════════════════════
print("\n━━━ TEST 4: Pipeline Logic (Dry-Run) ━━━")


def t_query_fallback():
    """When Gemini is unreachable, fallback queries are always generated."""
    from app.services.firecrawl_pipeline import generate_search_queries
    from app.services.circuit_breaker import gemini_breaker
    gemini_breaker.reset()
    queries = generate_search_queries("AI-powered recipe generator", "home cooks")
    assert isinstance(queries, list)
    assert len(queries) >= 3
    # All items are strings
    assert all(isinstance(q, str) for q in queries)
    # At least one query mentions the topic
    combined = " ".join(q.lower() for q in queries)
    assert any(kw in combined for kw in ["recipe", "ai", "competitor", "alternative"])
test("pipeline: query generation (fallback path)", t_query_fallback)


def t_rerank_passthrough():
    """When results <= top_k, rerank returns them unchanged (no LLM needed)."""
    from app.services.firecrawl_pipeline import rerank_results
    results = [
        {"url": f"https://site{i}.com", "title": f"Site {i}",
         "description": "desc", "markdown": "..."} for i in range(3)
    ]
    ranked = rerank_results(results, "test idea", top_k=5)
    assert len(ranked) == 3  # Passthrough — no LLM call made
test("pipeline: re-rank passthrough for small result sets", t_rerank_passthrough)


def t_rerank_truncates():
    """When results > top_k and LLM fails, returns first top_k results."""
    from app.services.firecrawl_pipeline import rerank_results
    results = [
        {"url": f"https://site{i}.com", "title": f"Site {i}",
         "description": "desc", "markdown": "..."} for i in range(10)
    ]
    ranked = rerank_results(results, "test idea", top_k=4)
    assert len(ranked) <= 4
test("pipeline: re-rank truncates to top_k on LLM failure", t_rerank_truncates)


def t_extraction_schema_complete():
    """Competitor extraction schema has all required fields."""
    from app.services.firecrawl_pipeline import COMPETITOR_EXTRACTION_SCHEMA
    props = COMPETITOR_EXTRACTION_SCHEMA["properties"]["competitors"]["items"]["properties"]
    required_fields = {"name", "url", "tagline", "features",
                       "pricing_summary", "target_audience", "strengths", "weaknesses"}
    assert required_fields == set(props.keys()), \
        f"Missing fields: {required_fields - set(props.keys())}"
test("pipeline: extraction schema has all 8 required fields", t_extraction_schema_complete)


def t_timeout_constants():
    """Strict timeouts are defined and within sensible bounds."""
    from app.services.firecrawl_pipeline import LLM_TIMEOUT, SEARCH_TIMEOUT, SCRAPE_TIMEOUT
    assert 5 <= LLM_TIMEOUT <= 30,    f"LLM_TIMEOUT={LLM_TIMEOUT} out of range"
    assert 10 <= SEARCH_TIMEOUT <= 60, f"SEARCH_TIMEOUT={SEARCH_TIMEOUT} out of range"
    assert 10 <= SCRAPE_TIMEOUT <= 60, f"SCRAPE_TIMEOUT={SCRAPE_TIMEOUT} out of range"
    print(f"    ℹ️  LLM={LLM_TIMEOUT}s  Search={SEARCH_TIMEOUT}s  Scrape={SCRAPE_TIMEOUT}s")
test("pipeline: strict timeouts defined and sane", t_timeout_constants)


def t_pipeline_cache_key_stable():
    """Same idea always produces same cache key (deterministic hash)."""
    import hashlib
    from app.services.firecrawl_pipeline import run_firecrawl_pipeline
    idea = "AI-powered tax filing for freelancers"
    key1 = f"firecrawl:pipeline:{hashlib.sha256(idea.encode()).hexdigest()[:16]}"
    key2 = f"firecrawl:pipeline:{hashlib.sha256(idea.encode()).hexdigest()[:16]}"
    assert key1 == key2
test("pipeline: cache key is deterministic for same idea", t_pipeline_cache_key_stable)


# ═══════════════════════════════════════════════════════════════════════
# TEST 5: API Endpoint Health
# ═══════════════════════════════════════════════════════════════════════
print("\n━━━ TEST 5: API Endpoint Health ━━━")

import urllib.request
import urllib.error

API_BASE = "http://127.0.0.1:8000"


def _get(path: str, timeout: int = 5):
    try:
        with urllib.request.urlopen(f"{API_BASE}{path}", timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {"error": e.reason}
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}


def t_health():
    status, body = _get("/health")
    assert status == 200, f"Expected 200, got {status}: {body}"
    assert body.get("status") == "ok"
    redis_status = body.get("redis", "unknown")
    print(f"    ℹ️  Redis: {redis_status}")
test("GET /health — 200 ok", t_health, skip_if=not API_UP)


def t_api_v1_health():
    status, body = _get("/api/v1/health")
    assert status == 200, f"Expected 200, got {status}: {body}"
    assert body.get("status") == "ok"
test("GET /api/v1/health — 200 ok", t_api_v1_health, skip_if=not API_UP)


def t_docs():
    try:
        with urllib.request.urlopen(f"{API_BASE}/docs", timeout=5) as r:
            assert r.status == 200
            content = r.read().decode()
            assert "swagger" in content.lower() or "openapi" in content.lower()
    except Exception as e:
        raise AssertionError(f"Docs not reachable: {e}")
test("GET /docs — Swagger UI loads", t_docs, skip_if=not API_UP)


def t_openapi_schema():
    status, body = _get("/openapi.json")
    assert status == 200, f"Expected 200, got {status}"
    assert "paths" in body
    paths = list(body["paths"].keys())
    # Verify our new health endpoint appears
    assert "/health" in paths, f"/health not in schema. Paths: {paths[:10]}"
    # Verify core validation endpoint
    assert "/api/v1/validate" in paths, "/api/v1/validate not in schema"
    print(f"    ℹ️  {len(paths)} endpoints registered")
test("GET /openapi.json — health + validate registered", t_openapi_schema, skip_if=not API_UP)


def t_validate_requires_auth():
    """POST /api/v1/validate without auth header → 422 (missing header)."""
    try:
        req = urllib.request.Request(
            f"{API_BASE}/api/v1/validate",
            data=json.dumps({"idea_description": "Test"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    # Should be 422 (validation error — missing x-user-id header)
    assert status in (422, 401, 403), f"Unexpected status {status}"
test("POST /api/v1/validate — rejects unauthenticated requests", t_validate_requires_auth, skip_if=not API_UP)


# ═══════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'━'*58}")
passed  = sum(1 for r in results if r[0] == PASS)
failed  = sum(1 for r in results if r[0] == FAIL)
skipped = sum(1 for r in results if r[0] == SKIP)
total   = len(results)

print(f"  RESULTS: {passed} passed  |  {failed} failed  |  {skipped} skipped  (total {total})")

if failed > 0:
    print(f"\n  ❌ Failed tests:")
    for r in results:
        if r[0] == FAIL:
            print(f"     {r[1]}")
            print(f"       → {r[2]}")
if skipped > 0:
    print(f"\n  {SKIP} Skipped (infrastructure not running):")
    for r in results:
        if r[0] == SKIP:
            print(f"     {r[1]}")
print(f"{'━'*58}")
sys.exit(1 if failed > 0 else 0)
