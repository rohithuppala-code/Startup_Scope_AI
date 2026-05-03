# firecrawl_pipeline.py
# ---------------------------------------------------------------------------
# ADVANCED FIRECRAWL PIPELINE — Search → Re-rank → Scrape → Extract → Iterate
#
# Implements the full "Search-then-Scrape" architecture:
#   Phase A: Discovery  — POST /search with markdown format
#   Phase B: Re-ranking — Hybrid scoring (keyword + domain + LLM)
#   Phase C: Deep-Dive  — POST /scrape on high-value competitor pages
#   Phase D: Feature Extraction — Schema-driven JSON extraction
#   Phase E: Iterative Loop — Confidence-aware gap detection → re-search
#
# All results are cached in Redis for cost efficiency.
# Embeddings stored in Redis for future similarity search.
# ---------------------------------------------------------------------------

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeout
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.core.config import settings
from app.services.circuit_breaker import firecrawl_breaker, gemini_breaker

logger = logging.getLogger(__name__)

# Strict timeouts (seconds)
LLM_TIMEOUT = 15
SEARCH_TIMEOUT = 20
SCRAPE_TIMEOUT = 25

# Chunk size for markdown splitting (tokens ≈ chars/4, ~1000 tokens per chunk)
MARKDOWN_CHUNK_CHARS = 4000

# Concurrency guard — max simultaneous Firecrawl API calls
_firecrawl_semaphore = threading.Semaphore(2)


# =====================================================================
# OBSERVABILITY HELPERS  (FIX #10)
# =====================================================================

class _Timer:
    """Simple context-manager timer for latency logging."""
    def __init__(self, label: str):
        self.label = label
        self._start: float = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_):
        elapsed = time.perf_counter() - self._start
        logger.info("[Firecrawl][timing] %s: %.2fs", self.label, elapsed)


_pipeline_metrics: Dict[str, Any] = {
    "llm_calls": 0,
    "search_calls": 0,
    "scrape_calls": 0,
    "cache_hits": 0,
    "errors": 0,
}


def _track(metric: str, delta: int = 1):
    _pipeline_metrics[metric] = _pipeline_metrics.get(metric, 0) + delta


def get_pipeline_metrics() -> Dict[str, Any]:
    """Return a copy of accumulated observability metrics."""
    return dict(_pipeline_metrics)


# =====================================================================
# CLIENT SINGLETONS (lazy init, thread-safe)
# =====================================================================

_firecrawl_app = None
_gemini_client = None
_redis_client = None          # FIX #2: singleton instead of per-call
_redis_lock = threading.Lock()


def _get_firecrawl():
    global _firecrawl_app
    if _firecrawl_app is None:
        from firecrawl import FirecrawlApp
        _firecrawl_app = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)
    return _firecrawl_app


_gemini_clients = {}

def _get_gemini(task: str = "default"):
    global _gemini_clients
    if task not in _gemini_clients:
        from google import genai
        key = settings.GEMINI_API_KEY
        if task == "embedding" and settings.GEMINI_EMBEDDING:
            key = settings.GEMINI_EMBEDDING
        elif task == "reranking" and settings.WEB_RERANKING:
            key = settings.WEB_RERANKING
        elif task == "consensus" and settings.MAIN_Consensus_PIPELINE:
            key = settings.MAIN_Consensus_PIPELINE
        elif task == "patent" and settings.PATENT:
            key = settings.PATENT
        elif task == "temporal" and settings.temporal_memory_comparision:
            key = settings.temporal_memory_comparision
        
        _gemini_clients[task] = genai.Client(api_key=key)
    return _gemini_clients[task]


def _get_redis():
    """FIX #2: Return a module-level Redis singleton (thread-safe, pooled)."""
    global _redis_client
    if _redis_client is None:
        with _redis_lock:
            if _redis_client is None:           # double-checked locking
                import redis as redis_lib
                _redis_client = redis_lib.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    max_connections=10,         # connection pool built-in
                )
    return _redis_client


# =====================================================================
# CONTENT UTILITIES
# =====================================================================

def _content_hash(text: str) -> str:
    """FIX #5: SHA-256 fingerprint for deduplication of page content."""
    return hashlib.sha256(text.encode()).hexdigest()


def _split_into_chunks(text: str, chunk_size: int = MARKDOWN_CHUNK_CHARS) -> List[str]:
    """
    FIX #8: Chunk text at paragraph boundaries instead of hard [:N] slicing.
    Preserves all content; callers pick how many chunks they need.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    paragraphs = text.split("\n\n")
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > chunk_size:
            if current:
                chunks.append(current.strip())
            current = para
        else:
            current = (current + "\n\n" + para) if current else para
    if current:
        chunks.append(current.strip())
    return chunks or [text[:chunk_size]]


def _safe_markdown(text: str, max_chars: int = MARKDOWN_CHUNK_CHARS) -> str:
    """Return first chunk of text — safe replacement for hard [:N] slicing."""
    return _split_into_chunks(text, max_chars)[0]


# =====================================================================
# HYBRID RE-RANKING HELPERS  (FIX #3)
# =====================================================================

_GOOD_DOMAINS = {
    "g2.com", "capterra.com", "producthunt.com", "crunchbase.com",
    "techcrunch.com", "getapp.com", "softwareadvice.com",
}
_BAD_PATTERNS = {"blog", "news", "article", "listicle", "forum", "reddit", "quora"}


def _keyword_score(result: Dict[str, Any], idea_description: str) -> float:
    """Quick keyword overlap score (0–4), no LLM required."""
    idea_words = set(idea_description.lower().split())
    text = (
        (result.get("title") or "") + " " +
        (result.get("description") or "") + " " +
        (result.get("url") or "")
    ).lower()
    overlap = sum(1 for w in idea_words if len(w) > 4 and w in text)
    return min(overlap, 4)


def _domain_score(url: str) -> float:
    """Bonus for known high-quality domains; penalty for junk path patterns."""
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        if host in _GOOD_DOMAINS:
            return 2.0
        path = urlparse(url).path.lower()
        if any(p in path for p in _BAD_PATTERNS):
            return -2.0
    except Exception:
        pass
    return 0.0


# =====================================================================
# PHASE A: LLM-GENERATED SEARCH QUERIES
# =====================================================================

def generate_search_queries(idea_description: str, target_market: str = "") -> List[str]:
    """Uses Gemini to generate 3-5 high-intent search queries. Circuit-breaker protected."""
    def _call():
        client = _get_gemini(task="reranking")
        from google.genai import types as genai_types

        prompt = (
            "You are a market research expert. Generate exactly 5 search queries to find "
            "competitors, alternatives, and market data for this startup idea.\n\n"
            f"Startup Idea: {idea_description}\n"
            f"Target Market: {target_market or 'Not specified'}\n\n"
            "Rules:\n"
            "- Query 1: Direct competitors (e.g., 'best alternatives to [concept]')\n"
            "- Query 2: Market size/validation (e.g., '[market] market size 2025')\n"
            "- Query 3: Pricing intelligence (e.g., '[competitor type] pricing comparison')\n"
            "- Query 4: User pain points (e.g., '[problem] solutions reviews')\n"
            "- Query 5: Industry trends (e.g., '[industry] trends funding 2025')\n\n"
            "Output ONLY a JSON array of 5 strings. No explanation."
        )

        _track("llm_calls")
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=256,
                response_mime_type="application/json",
            ),
        )

        queries = json.loads(response.text)
        if isinstance(queries, list) and len(queries) >= 3:
            return queries[:5]
        return None

    short_idea = idea_description[:80]
    fallback = [
        f"competitors alternatives to {short_idea}",
        f"{short_idea} market size analysis",
        f"{short_idea} pricing plans comparison",
    ]

    try:
        with _Timer("generate_search_queries"):
            result = gemini_breaker.call(_call, fallback=lambda: None)
        if result:
            logger.info("[Firecrawl] Generated %d search queries via LLM.", len(result))
            return result
    except Exception as e:
        _track("errors")
        logger.warning("[Firecrawl] LLM query generation failed: %s. Using fallback.", e)

    return fallback


# =====================================================================
# PHASE A.2: SEARCH WITH MARKDOWN
# =====================================================================

def search_with_markdown(queries: List[str], limit_per_query: int = 3) -> List[Dict[str, Any]]:
    """Executes Firecrawl searches. Parallel via ThreadPool + semaphore + content dedup."""
    all_results: List[Dict[str, Any]] = []
    seen_urls: set = set()
    seen_content_hashes: set = set()      # FIX #5: content-level deduplication

    def _search_one(query: str) -> List[Dict[str, Any]]:
        def _call():
            app = _get_firecrawl()
            _track("search_calls")
            return app.search(
                query=query,
                limit=limit_per_query,
                scrape_options={
                    "formats": ["markdown"],
                    "onlyMainContent": True,
                },
            )

        # FIX #6: semaphore guards concurrent API calls
        with _firecrawl_semaphore:
            response = firecrawl_breaker.call(_call, fallback=lambda: None)

        if response is None:
            return []

        results_list = None
        if hasattr(response, "web") and response.web:
            results_list = response.web
        elif hasattr(response, "data") and response.data:
            results_list = response.data
        elif isinstance(response, list):
            results_list = response
        elif isinstance(response, dict):
            results_list = response.get("web") or response.get("data")

        hits = []
        if results_list:
            for result in results_list:
                res = result.model_dump() if hasattr(result, "model_dump") else dict(result)
                url = res.get("url", "")
                if url:
                    markdown_content = res.get("markdown", "") or res.get("content", "")
                    if not markdown_content and hasattr(result, "markdown") and result.markdown:
                        markdown_content = result.markdown

                    hits.append({
                        "url": url,
                        "title": res.get("title", ""),
                        "description": res.get("description", "") or res.get("snippet", ""),
                        "markdown": markdown_content,
                        "query": query,
                    })
        return hits

    with _Timer("search_with_markdown"):
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="fc_search") as pool:
            futures = {pool.submit(_search_one, q): q for q in queries}
            try:
                for f in as_completed(futures, timeout=SEARCH_TIMEOUT):
                    try:
                        for hit in f.result():
                            url = hit["url"]
                            if url in seen_urls:
                                continue
                            seen_urls.add(url)

                            # FIX #5: skip same content from different URLs
                            md = hit.get("markdown", "")
                            if md:
                                h = _content_hash(md[:500])
                                if h in seen_content_hashes:
                                    logger.debug("[Firecrawl] Duplicate content skipped: %s", url)
                                    continue
                                seen_content_hashes.add(h)

                            all_results.append(hit)
                    except Exception as e:
                        _track("errors")
                        logger.warning("[Firecrawl] Search query failed: %s", e)
            except FutureTimeout:
                logger.warning(
                    "[Firecrawl] Search timeout (%ds). Using partial results.", SEARCH_TIMEOUT
                )

    logger.info("[Firecrawl] Search phase complete: %d unique results.", len(all_results))
    return all_results


# =====================================================================
# PHASE B: HYBRID RE-RANKING  (FIX #3)
#
# score = keyword_match (0-4) + domain_score (-2 to +2) + 0.5 × llm_score (0-10)
# LLM only called on top-15 heuristic candidates → ~50% fewer LLM tokens
# =====================================================================

def rerank_results(
    results: List[Dict[str, Any]],
    idea_description: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """FIX #3: Hybrid re-ranking — cheap heuristics first, LLM refines top candidates."""
    if len(results) <= top_k:
        for r in results:
            r["relevance_score"] = round(
                _keyword_score(r, idea_description) + _domain_score(r.get("url", "")), 2
            )
        return results

    # Step 1: cheap heuristic pre-score (no LLM)
    for r in results:
        r["_pre_score"] = _keyword_score(r, idea_description) + _domain_score(r.get("url", ""))

    pre_sorted = sorted(results, key=lambda x: x["_pre_score"], reverse=True)
    candidates = pre_sorted[:15]      # only top-15 go to LLM

    # Step 2: LLM refinement on reduced candidate set
    try:
        client = _get_gemini(task="reranking")
        from google.genai import types as genai_types

        summaries = []
        for i, r in enumerate(candidates):
            summaries.append(
                f"[{i}] URL: {r['url']}\n"
                f"Title: {r['title']}\n"
                f"Description: {r['description'][:200]}"
            )

        prompt = (
            f"You are ranking search results for competitor analysis of this startup idea:\n"
            f"\"{idea_description[:200]}\"\n\n"
            f"Results:\n{'---'.join(summaries)}\n\n"
            f"Score each result 0-10 for relevance as a DIRECT competitor or market data source.\n"
            f"Penalize: blogs, news articles, generic listicles.\n"
            f"Reward: product pages, pricing pages, feature comparisons, market reports.\n\n"
            f"Output ONLY a JSON array of objects: [{{\"index\": 0, \"score\": 8}}, ...]\n"
            f"Include ALL {len(summaries)} results."
        )

        _track("llm_calls")
        with _Timer("rerank_llm"):
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=512,
                    response_mime_type="application/json",
                ),
            )

        scores = json.loads(response.text)
        if isinstance(scores, list):
            scored = []
            for entry in scores:
                idx = entry.get("index", -1)
                llm_score = entry.get("score", 0)
                if 0 <= idx < len(candidates):
                    # FIX #3: blend heuristic + LLM
                    final_score = candidates[idx]["_pre_score"] + llm_score * 0.5
                    candidates[idx]["relevance_score"] = round(final_score, 2)
                    scored.append((final_score, idx))

            scored.sort(key=lambda x: x[0], reverse=True)
            ranked = [candidates[idx] for _, idx in scored[:top_k]]
            logger.info("[Firecrawl] Re-ranked: top %d of %d results.", len(ranked), len(results))
            return ranked

    except Exception as e:
        _track("errors")
        logger.warning("[Firecrawl] Re-ranking LLM failed: %s. Falling back to heuristic.", e)

    for r in pre_sorted[:top_k]:
        r.setdefault("relevance_score", r["_pre_score"])
    return pre_sorted[:top_k]


# =====================================================================
# PHASE C: TARGETED SCRAPE
# =====================================================================

def targeted_scrape(urls: List[str], max_pages: int = 3) -> List[Dict[str, Any]]:
    """Deep-scrapes with semaphore rate-limiting and content deduplication."""
    scraped: List[Dict[str, Any]] = []
    seen_content_hashes: set = set()      # FIX #5

    def _scrape_one(url: str) -> Optional[Dict[str, Any]]:
        def _call():
            app = _get_firecrawl()
            _track("scrape_calls")
            return app.scrape(
                url=url,
                formats=["markdown"],
                only_main_content=True,
            )

        # FIX #6
        with _firecrawl_semaphore:
            result = firecrawl_breaker.call(_call, fallback=lambda: None)

        if result is None:
            return None

        res = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        markdown = res.get("markdown", "") or res.get("content", "")
        if not markdown and hasattr(result, "markdown") and result.markdown:
            markdown = result.markdown

        if markdown and len(markdown) > 100:
            h = _content_hash(markdown[:500])
            if h in seen_content_hashes:
                logger.debug("[Firecrawl] Duplicate scrape content skipped: %s", url)
                return None
            seen_content_hashes.add(h)

            # FIX #8: chunk instead of hard [:8000]
            return {
                "url": url,
                "markdown": _safe_markdown(markdown, MARKDOWN_CHUNK_CHARS),
                "all_chunks": _split_into_chunks(markdown),   # full content preserved
                "title": (
                    res.get("metadata", {}).get("title", "")
                    if isinstance(res.get("metadata"), dict) else ""
                ),
            }
        return None

    with _Timer("targeted_scrape"):
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="fc_scrape") as pool:
            futures = {pool.submit(_scrape_one, u): u for u in urls[:max_pages]}
            try:
                for f in as_completed(futures, timeout=SCRAPE_TIMEOUT):
                    try:
                        result = f.result()
                        if result:
                            scraped.append(result)
                    except Exception as e:
                        _track("errors")
                        logger.warning("[Firecrawl] Scrape failed: %s", e)
            except FutureTimeout:
                logger.warning("[Firecrawl] Scrape timeout (%ds). Using partial.", SCRAPE_TIMEOUT)

    logger.info("[Firecrawl] Deep scrape complete: %d pages.", len(scraped))
    return scraped


# =====================================================================
# PHASE D: STRUCTURED FEATURE EXTRACTION
# =====================================================================

COMPETITOR_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "competitors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "url": {"type": "string"},
                    "tagline": {"type": "string"},
                    "features": {"type": "array", "items": {"type": "string"}},
                    "pricing_summary": {"type": "string"},
                    "target_audience": {"type": "string"},
                    "strengths": {"type": "array", "items": {"type": "string"}},
                    "weaknesses": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


def extract_competitor_features(
    search_results: List[Dict[str, Any]],
    scraped_pages: List[Dict[str, Any]],
    idea_description: str,
) -> Dict[str, Any]:
    """Extracts structured competitor features. FIX #8: chunked markdown."""
    try:
        client = _get_gemini(task="reranking")
        from google.genai import types as genai_types

        context_parts = []
        for r in search_results[:5]:
            md = _safe_markdown(r.get("markdown", ""), 2000)   # FIX #8
            if md:
                context_parts.append(f"## {r.get('title', r['url'])}\nURL: {r['url']}\n{md}")

        for s in scraped_pages[:3]:
            md = _safe_markdown(s.get("markdown", ""), 3000)   # FIX #8
            if md:
                context_parts.append(
                    f"## {s.get('title', s['url'])} [DEEP SCRAPE]\nURL: {s['url']}\n{md}"
                )

        context = "\n\n---\n\n".join(context_parts)

        prompt = (
            f"Extract structured competitor data from this market research.\n\n"
            f"Startup Idea: {idea_description[:300]}\n\n"
            f"Research Data:\n{context[:12000]}\n\n"
            f"For each competitor found, extract: name, url, tagline, features, "
            f"pricing_summary, target_audience, strengths, weaknesses.\n\n"
            f"Output JSON matching this schema:\n"
            f"{json.dumps(COMPETITOR_EXTRACTION_SCHEMA, indent=2)}"
        )

        _track("llm_calls")
        with _Timer("extract_competitor_features"):
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=2048,
                    response_mime_type="application/json",
                ),
            )

        extracted = json.loads(response.text)
        competitors = extracted.get("competitors", [])
        logger.info("[Firecrawl] Extracted features for %d competitors.", len(competitors))
        return extracted

    except Exception as e:
        _track("errors")
        logger.warning("[Firecrawl] Feature extraction failed: %s", e)
        return {"competitors": []}


# =====================================================================
# PHASE D.5: EMBEDDING STORAGE + HNSW INDEX  (FIX #4 complete)
#
# Batch-embeds all competitors in ONE API call, stores binary vectors
# in Redis hashes, and maintains an HNSW index (idx:competitors) for
# live KNN similarity search.
#
# Key pattern : embedding:<sha256(name+url)[:24]>
# Index name  : idx:competitors
# Vector dim  : 768  (text-embedding-004)
# =====================================================================

# Gemini text-embedding-004 output dimension
_EMBEDDING_DIM = 768
_EMBEDDING_INDEX = "idx:competitors"


def _ensure_hnsw_index() -> None:
    """
    Create the RedisSearch HNSW index if it does not already exist.
    Safe to call repeatedly — silently skips if index is present.
    """
    import struct
    r = _get_redis()
    try:
        r.execute_command("FT.INFO", _EMBEDDING_INDEX)
        return                          # index already exists
    except Exception:
        pass                            # ResponseError → needs creation

    try:
        # FT.CREATE idx:competitors
        #   ON HASH PREFIX 1 embedding:
        #   SCHEMA
        #     name    TEXT
        #     url     TEXT NOSTEM
        #     idea    TEXT
        #     vector  VECTOR HNSW 6
        #               TYPE FLOAT32
        #               DIM 768
        #               DISTANCE_METRIC COSINE
        r.execute_command(
            "FT.CREATE", _EMBEDDING_INDEX,
            "ON", "HASH",
            "PREFIX", "1", "embedding:",
            "SCHEMA",
            "name",   "TEXT",
            "url",    "TEXT", "NOSTEM",
            "idea",   "TEXT",
            "vector", "VECTOR", "HNSW", "6",
                      "TYPE", "FLOAT32",
                      "DIM", str(_EMBEDDING_DIM),
                      "DISTANCE_METRIC", "COSINE",
        )
        logger.info("[Firecrawl] Created HNSW index '%s'.", _EMBEDDING_INDEX)
    except Exception as e:
        logger.warning("[Firecrawl] HNSW index creation failed (non-fatal): %s", e)


def _floats_to_bytes(vector: List[float]) -> bytes:
    """Pack a list of float32 values into a raw bytes blob for Redis."""
    import struct
    return struct.pack(f"{len(vector)}f", *vector)


def _embed_and_store(competitors: List[Dict[str, Any]]) -> None:
    """
    FIX #4 (complete): Batch-embed all competitors in ONE API call,
    then store binary FLOAT32 vectors in Redis for HNSW KNN search.
    """
    if not competitors:
        return

    try:
        client = _get_gemini(task="embedding")
        r = _get_redis()

        # ── Build texts + keys, skip already-cached entries ──
        texts: List[str] = []
        meta: List[Dict[str, Any]] = []

        for comp in competitors:
            name = comp.get("name", "")
            url = comp.get("url", "")
            if not name:
                continue

            emb_key = (
                f"embedding:{hashlib.sha256((name + url).encode()).hexdigest()[:24]}"
            )
            try:
                if r.exists(emb_key):
                    continue            # already stored — skip
            except Exception:
                pass

            text = (
                f"{name}. {comp.get('tagline', '')}. "
                f"Features: {', '.join(comp.get('features', [])[:10])}. "
                f"Pricing: {comp.get('pricing_summary', '')}."
            )
            texts.append(text)
            meta.append({"key": emb_key, "name": name, "url": url, "text": text})

        if not texts:
            logger.debug("[Firecrawl] All embeddings already cached — skipping.")
            return

        # ── ONE batch API call for all texts (FIX #3 for embeddings) ──
        _track("llm_calls")
        with _Timer("batch_embed"):
            embedding_response = client.models.embed_content(
                model="text-embedding-004",
                contents=texts,         # list → batch call
            )

        vectors = [e.values for e in embedding_response.embeddings]

        # ── Ensure HNSW index exists before writing ──
        _ensure_hnsw_index()

        # ── Store each vector as binary FLOAT32 blob in Redis hash ──
        pipe = r.pipeline(transaction=False)
        for m, vector in zip(meta, vectors):
            blob = _floats_to_bytes(vector)
            pipe.hset(m["key"], mapping={
                "name":   m["name"],
                "url":    m["url"],
                "idea":   m["text"],
                "vector": blob,         # binary FLOAT32 — indexed by HNSW
            })
            pipe.expire(m["key"], 86400 * 7)    # 7-day TTL
        pipe.execute()

        logger.info(
            "[Firecrawl] Batch-stored %d competitor embeddings in Redis.", len(meta)
        )

    except Exception as e:
        logger.warning("[Firecrawl] Embedding storage failed (non-fatal): %s", e)


def find_similar_competitors(
    query_text: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    FIX #1: Active KNN vector search against the HNSW index.

    Returns the top-k most semantically similar competitors to
    `query_text` — e.g., the startup idea description — using
    cosine distance on the stored FLOAT32 embeddings.

    Usage example (called from anywhere after pipeline runs):
        similar = find_similar_competitors(idea_description, top_k=3)
    """
    try:
        client = _get_gemini(task="embedding")
        r = _get_redis()

        # Embed the query
        _track("llm_calls")
        q_response = client.models.embed_content(
            model="text-embedding-004",
            contents=query_text,
        )
        q_vector = q_response.embeddings[0].values
        q_blob = _floats_to_bytes(q_vector)

        # KNN search via RedisSearch
        # FT.SEARCH idx:competitors
        #   *=>[KNN 5 @vector $vec AS score]
        #   PARAMS 2 vec <blob>
        #   SORTBY score
        #   RETURN 3 name url score
        #   DIALECT 2
        results = r.execute_command(
            "FT.SEARCH", _EMBEDDING_INDEX,
            f"*=>[KNN {top_k} @vector $vec AS score]",
            "PARAMS", "2", "vec", q_blob,
            "SORTBY", "score",
            "RETURN", "3", "name", "url", "score",
            "DIALECT", "2",
        )

        # RedisSearch returns: [total_count, key, [field, val, ...], key, ...]
        hits: List[Dict[str, Any]] = []
        if results and len(results) > 1:
            i = 1
            while i < len(results):
                key = results[i]
                fields = results[i + 1] if i + 1 < len(results) else []
                field_dict: Dict[str, str] = {}
                for j in range(0, len(fields) - 1, 2):
                    field_dict[fields[j]] = fields[j + 1]
                hits.append({
                    "key":   key,
                    "name":  field_dict.get("name", ""),
                    "url":   field_dict.get("url", ""),
                    "score": float(field_dict.get("score", 1.0)),   # cosine distance
                })
                i += 2

        logger.info(
            "[Firecrawl] KNN search returned %d similar competitors for query: %.60s…",
            len(hits), query_text,
        )
        return hits

    except Exception as e:
        logger.warning("[Firecrawl] KNN search failed (non-fatal): %s", e)
        return []


# =====================================================================
# PHASE E: CONFIDENCE-AWARE ITERATIVE SEARCH  (FIX #7)
# =====================================================================

def _compute_confidence(extracted_features: Dict[str, Any]) -> float:
    """
    FIX #7: Returns 0.0–1.0 confidence based on data completeness.
    Removes blind reliance on LLM self-assessment.
    """
    competitors = extracted_features.get("competitors", [])
    n = len(competitors)
    if n == 0:
        return 0.0

    has_pricing = sum(1 for c in competitors if c.get("pricing_summary"))
    has_features = sum(1 for c in competitors if c.get("features"))

    score = 0.0
    score += min(n / 3, 1.0) * 0.40         # 40 pts: having ≥3 competitors
    score += (has_pricing / n) * 0.35        # 35 pts: pricing coverage
    score += (has_features / n) * 0.25       # 25 pts: feature coverage
    return round(score, 3)


def iterative_gap_search(
    idea_description: str,
    existing_data: str,
    extracted_features: Dict[str, Any],
    max_iterations: int = 1,
    confidence_threshold: float = 0.75,
) -> Tuple[str, List[str]]:
    """
    FIX #7: Confidence-aware iterative search.
    Stops early when data meets quality threshold; iterates when it doesn't.
    """
    additional_data = ""
    additional_urls: List[str] = []

    for iteration in range(max_iterations):
        confidence = _compute_confidence(extracted_features)
        logger.info(
            "[Firecrawl] Iterative loop %d/%d — confidence=%.2f (threshold=%.2f).",
            iteration + 1, max_iterations, confidence, confidence_threshold,
        )

        if confidence >= confidence_threshold:
            logger.info("[Firecrawl] Confidence threshold met. Skipping gap search.")
            break

        try:
            client = _get_gemini(task="consensus")
            from google.genai import types as genai_types

            competitors = extracted_features.get("competitors", [])
            competitor_names = [c.get("name", "") for c in competitors if c.get("name")]

            prompt = (
                f"You are analyzing competitor data for: {idea_description[:200]}\n\n"
                f"Competitors found: {', '.join(competitor_names) or 'None yet'}\n\n"
                f"Current data quality:\n"
                f"- Competitors: {len(competitors)}\n"
                f"- Have pricing: {sum(1 for c in competitors if c.get('pricing_summary'))}\n"
                f"- Have features: {sum(1 for c in competitors if c.get('features'))}\n"
                f"- Confidence: {confidence:.2f}/1.00\n\n"
                f"Generate 1-2 additional search queries to fill gaps. Focus on:\n"
                f"- Pricing information\n- Feature comparisons\n- Market size data\n\n"
                f"Output JSON: {{\"sufficient\": true/false, \"queries\": [\"...\"], \"reason\": \"...\"}}"
            )

            _track("llm_calls")
            with _Timer(f"iterative_gap_iter{iteration+1}"):
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.2,
                        max_output_tokens=256,
                        response_mime_type="application/json",
                    ),
                )

            result = json.loads(response.text)
            if result.get("sufficient", True):
                logger.info("[Firecrawl] LLM confirms data sufficient. Stopping.")
                break

            gap_queries = result.get("queries", [])
            if gap_queries:
                logger.info("[Firecrawl] Gap queries iter %d: %s", iteration + 1, gap_queries)
                gap_results = search_with_markdown(gap_queries, limit_per_query=2)
                for r in gap_results:
                    md = r.get("markdown", "")
                    if md:
                        additional_data += f"\n\n---\n\n{_safe_markdown(md, 2000)}"  # FIX #8
                    url = r.get("url", "")
                    if url:
                        additional_urls.append(url)

        except Exception as e:
            _track("errors")
            logger.warning("[Firecrawl] Iterative search failed: %s", e)
            break

    return additional_data, additional_urls


# =====================================================================
# MASTER ORCHESTRATOR
# =====================================================================

def run_firecrawl_pipeline(
    idea_description: str,
    target_market: str = "",
    budget_constraints: str = "",
) -> Tuple[str, List[str], Dict[str, Any]]:
    """
    Runs the full Firecrawl intelligence pipeline.

    Returns:
        Tuple of (competitor_markdown, competitor_urls, extracted_features).
    """
    pipeline_start = time.perf_counter()
    r = _get_redis()

    # ── Check Redis cache ──
    idea_key = (
        f"firecrawl:pipeline:{hashlib.sha256(idea_description.encode()).hexdigest()[:16]}"
    )
    try:
        cached = r.get(idea_key)
        if cached:
            data = json.loads(cached)
            _track("cache_hits")
            logger.info("[Firecrawl] Pipeline cache hit.")
            return data["markdown"], data["urls"], data["features"]
    except Exception:
        pass

    # ── Phase A: Generate search queries ──
    queries = generate_search_queries(idea_description, target_market)

    # ── Phase A.2: Search with markdown ──
    search_results = search_with_markdown(queries)

    if not search_results:
        return "No competitor data found from live search.", [], {"competitors": []}

    # ── Phase B: Hybrid re-rank ──
    ranked_results = rerank_results(search_results, idea_description, top_k=5)

    # ── Phase C: Deep scrape top 2 ──
    top_urls = [r["url"] for r in ranked_results[:2] if r.get("url")]
    scraped_pages = targeted_scrape(top_urls, max_pages=2)

    # ── Phase D: Feature extraction ──
    extracted_features = extract_competitor_features(
        ranked_results, scraped_pages, idea_description
    )

    # ── Phase D.5: Batch-embed + store HNSW vectors ──
    _embed_and_store(extracted_features.get("competitors", []))

    # ── Phase D.6: KNN similarity search ──
    # Runs immediately after embedding so results are available
    # for the feature matrix and downstream LLM context.
    similar_hits = find_similar_competitors(idea_description, top_k=5)
    if similar_hits:
        extracted_features["_similar_competitors"] = similar_hits
        logger.info(
            "[Firecrawl] KNN found %d similar competitors (top: %s, dist=%.3f).",
            len(similar_hits),
            similar_hits[0].get("name", "?"),
            similar_hits[0].get("score", 0),
        )

    # ── Build competitor markdown ──
    markdown_parts = []
    for r in ranked_results:
        md = r.get("markdown", "")
        if md:
            markdown_parts.append(
                f"## {r.get('title', 'Competitor')}\n"
                f"URL: {r['url']}\n"
                f"Relevance Score: {r.get('relevance_score', 'N/A')}\n\n"
                f"{_safe_markdown(md, 3000)}"     # FIX #8
            )

    for s in scraped_pages:
        md = s.get("markdown", "")
        if md:
            markdown_parts.append(
                f"## {s.get('title', 'Deep Scrape')} [DEEP DIVE]\n"
                f"URL: {s['url']}\n\n{_safe_markdown(md, 4000)}"     # FIX #8
            )

    # ── Phase E: Confidence-aware iterative gap search ──
    competitor_markdown = "\n\n---\n\n".join(markdown_parts)
    all_urls = [r["url"] for r in ranked_results if r.get("url")]

    gap_data, gap_urls = iterative_gap_search(
        idea_description, competitor_markdown, extracted_features
    )
    if gap_data:
        competitor_markdown += gap_data
    all_urls.extend(gap_urls)

    # ── Add structured feature matrix ──
    competitors = extracted_features.get("competitors", [])
    if competitors:
        feature_summary = "\n\n## 📊 Extracted Competitor Matrix\n\n"
        for c in competitors:
            feature_summary += f"### {c.get('name', 'Unknown')}\n"
            feature_summary += f"- **URL:** {c.get('url', 'N/A')}\n"
            feature_summary += f"- **Tagline:** {c.get('tagline', 'N/A')}\n"
            feature_summary += f"- **Target:** {c.get('target_audience', 'N/A')}\n"
            feature_summary += f"- **Pricing:** {c.get('pricing_summary', 'N/A')}\n"
            features = c.get("features", [])
            if features:
                feature_summary += f"- **Features:** {', '.join(features[:8])}\n"
            strengths = c.get("strengths", [])
            if strengths:
                feature_summary += f"- **Strengths:** {', '.join(strengths[:5])}\n"
            weaknesses = c.get("weaknesses", [])
            if weaknesses:
                feature_summary += f"- **Weaknesses:** {', '.join(weaknesses[:5])}\n"
            feature_summary += "\n"
        competitor_markdown += feature_summary

    # ── Attach confidence score to output ──
    final_confidence = _compute_confidence(extracted_features)
    extracted_features["_confidence"] = final_confidence

    # ── Cache result (1 hour TTL) ──
    try:
        r.setex(idea_key, 3600, json.dumps({
            "markdown": competitor_markdown[:50000],
            "urls": all_urls[:20],
            "features": extracted_features,
        }))
    except Exception:
        pass

    elapsed = time.perf_counter() - pipeline_start
    logger.info(
        "[Firecrawl] Pipeline complete in %.2fs | urls=%d competitors=%d chars=%d "
        "confidence=%.2f | metrics=%s",
        elapsed,
        len(all_urls),
        len(competitors),
        len(competitor_markdown),
        final_confidence,
        get_pipeline_metrics(),
    )
    return competitor_markdown, all_urls, extracted_features