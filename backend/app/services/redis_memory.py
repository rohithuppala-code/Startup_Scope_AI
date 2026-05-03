# redis_memory.py
# ---------------------------------------------------------------------------
# REDIS MEMORY LAYER — Three-tier Redis architecture:
#
#   1. CACHE LAYER    — Fast response for recent API results (TTL-based)
#   2. MEMORY LAYER   — Persistent idea history with structured JSON
#   3. VECTOR SEARCH  — Native Redis HNSW for O(log N) similarity search
#
# REFINEMENT 1: Vector search uses Redis Stack's native FT.SEARCH with
# HNSW algorithm. The cosine similarity math stays entirely in Redis's
# C-based module — Python only sends the query vector and receives
# results. Memory footprint: O(1) in the application layer.
#
# Falls back to Python brute-force if Redis Stack is not available.
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
import logging
import struct
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None
_hnsw_available: bool | None = None  # Cached module detection

VECTOR_DIM = 768
INDEX_NAME = "idx:idea_vectors"
VECTOR_PREFIX = "vec:"


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)
    return _redis_client


def _get_redis_text() -> redis.Redis:
    """Text-mode Redis client for non-binary operations."""
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _check_hnsw_available() -> bool:
    """Checks if Redis Stack's RediSearch module is loaded (FT.SEARCH support)."""
    global _hnsw_available
    if _hnsw_available is not None:
        return _hnsw_available
    try:
        r = _get_redis()
        modules = r.execute_command("MODULE", "LIST")
        module_names = [m[1] if isinstance(m, (list, tuple)) else b"" for m in modules]
        _hnsw_available = any(b"search" in str(n).lower().encode() for n in module_names)
        if _hnsw_available:
            logger.info("[RedisMemory] ✅ Redis Stack detected — HNSW vector search enabled.")
        else:
            logger.info("[RedisMemory] ⚠️ Redis Stack not found — using Python fallback.")
    except Exception:
        _hnsw_available = False
        logger.info("[RedisMemory] ⚠️ Could not detect Redis modules — using Python fallback.")
    return _hnsw_available


def _ensure_vector_index() -> bool:
    """Creates the HNSW vector index if it doesn't exist."""
    if not _check_hnsw_available():
        return False
    try:
        r = _get_redis()
        # Check if index exists
        try:
            r.execute_command("FT.INFO", INDEX_NAME)
            return True  # Already exists
        except redis.ResponseError:
            pass  # Index doesn't exist, create it

        # Create HNSW index on the vector prefix
        r.execute_command(
            "FT.CREATE", INDEX_NAME,
            "ON", "HASH",
            "PREFIX", "1", VECTOR_PREFIX,
            "SCHEMA",
            "idea", "TEXT",
            "score", "NUMERIC",
            "validation_id", "TAG",
            "embedding", "VECTOR", "HNSW", "6",
            "TYPE", "FLOAT32",
            "DIM", str(VECTOR_DIM),
            "DISTANCE_METRIC", "COSINE",
        )
        logger.info("[RedisMemory] ✅ Created HNSW vector index: %s", INDEX_NAME)
        return True
    except Exception as e:
        logger.warning("[RedisMemory] Failed to create HNSW index: %s", e)
        return False


def _embedding_to_bytes(embedding: List[float]) -> bytes:
    """Converts a float list to a compact binary blob for Redis HNSW."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def _bytes_to_embedding(blob: bytes) -> List[float]:
    """Converts a binary blob back to a float list."""
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


# =====================================================================
# TIER 1: CACHE LAYER — Fast response for recent searches/scrapes
# =====================================================================

def cache_search_results(idea_hash: str, results: Dict[str, Any], ttl: int = 3600) -> None:
    """Cache Firecrawl search results for 1 hour (avoid re-calling API)."""
    try:
        r = _get_redis_text()
        key = f"search:{idea_hash}:results"
        r.setex(key, ttl, json.dumps(results, default=str))
        logger.info("[RedisMemory] Cached search results for %s", idea_hash[:16])
    except Exception as e:
        logger.warning("[RedisMemory] Cache write failed: %s", e)


def get_cached_search(idea_hash: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached search results."""
    try:
        r = _get_redis_text()
        raw = r.get(f"search:{idea_hash}:results")
        if raw:
            logger.info("[RedisMemory] Cache hit for search:%s", idea_hash[:16])
            return json.loads(raw)
    except Exception as e:
        logger.warning("[RedisMemory] Cache read failed: %s", e)
    return None


# =====================================================================
# TIER 2: MEMORY LAYER — Idea History with structured JSON
# =====================================================================

def store_idea_memory(
    validation_id: str,
    idea_description: str,
    competitors: List[str],
    gaps: List[str],
    feasibility_score: int,
    report_summary: str = "",
    user_id: str = "",
) -> None:
    """Stores a completed idea evaluation in Redis memory."""
    try:
        r = _get_redis_text()
        idea_key = f"idea:{validation_id}"

        memory = {
            "validation_id": validation_id,
            "idea": idea_description[:500],
            "competitors": competitors[:10],
            "gaps": gaps[:10],
            "feasibility_score": feasibility_score,
            "report_summary": report_summary[:1000],
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        r.set(idea_key, json.dumps(memory))

        if user_id:
            r.zadd(f"user:{user_id}:ideas", {validation_id: datetime.now(timezone.utc).timestamp()})

        r.zadd("global:ideas", {validation_id: datetime.now(timezone.utc).timestamp()})
        r.expire(idea_key, 90 * 86400)

        logger.info("[RedisMemory] Stored idea memory for %s (score: %d)", validation_id[:8], feasibility_score)

    except Exception as e:
        logger.warning("[RedisMemory] Failed to store idea memory: %s", e)


def get_idea_memory(validation_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a stored idea evaluation."""
    try:
        r = _get_redis_text()
        raw = r.get(f"idea:{validation_id}")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


def get_user_idea_history(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves the most recent idea evaluations for a user."""
    try:
        r = _get_redis_text()
        ids = r.zrevrange(f"user:{user_id}:ideas", 0, limit - 1)
        return [m for vid in ids if (m := get_idea_memory(vid))]
    except Exception as e:
        logger.warning("[RedisMemory] Failed to get user history: %s", e)
        return []


# =====================================================================
# TIER 3: VECTOR SIMILARITY SEARCH — Native Redis HNSW (O(log N))
#
# REFINEMENT 1: All vector math stays inside Redis's C module.
# Python sends ONE query vector → Redis returns top-K matches.
# Application memory: O(1). Search time: O(log N) via HNSW graph.
#
# Fallback: Python brute-force O(N) if Redis Stack not available.
# =====================================================================

def store_idea_embedding(
    validation_id: str,
    embedding: List[float],
    idea_description: str,
    feasibility_score: int = 0,
) -> None:
    """Stores an idea embedding for similarity search.

    Always writes to the JSON fallback index (embedding:* / embedding:index).
    Additionally writes to the HNSW hash (vec:* prefix) if Redis Stack available.
    This dual-write ensures find_similar_ideas() always has data to search.
    """
    if not embedding or len(embedding) < 10:
        return

    # Truncate/pad to exact VECTOR_DIM
    vec = embedding[:VECTOR_DIM]

    try:
        r_text = _get_redis_text()

        # ── ALWAYS write the JSON fallback (O(N) brute-force path) ──────
        fallback_key = f"embedding:{validation_id}"
        r_text.setex(fallback_key, 90 * 86400, json.dumps({
            "validation_id": validation_id,
            "embedding": vec,
            "idea": idea_description[:300],
            "score": feasibility_score,
        }))
        r_text.sadd("embedding:index", validation_id)

        # ── ALSO write HNSW hash if Redis Stack available ────────────────
        if _ensure_vector_index():
            r = _get_redis()
            hnsw_key = f"{VECTOR_PREFIX}{validation_id}"
            r.hset(hnsw_key, mapping={
                "validation_id": validation_id,
                "idea": idea_description[:300],
                "score": str(feasibility_score),
                "embedding": _embedding_to_bytes(vec),
            })
            r.expire(hnsw_key, 90 * 86400)
            logger.info("[RedisMemory] Stored HNSW + fallback embedding for %s", validation_id[:8])
        else:
            logger.info("[RedisMemory] Stored fallback embedding for %s", validation_id[:8])

    except Exception as e:
        logger.warning("[RedisMemory] Failed to store embedding: %s", e)



def find_similar_ideas(
    query_embedding: List[float],
    exclude_id: str = "",
    top_k: int = 5,
    min_similarity: float = 0.7,
) -> List[Dict[str, Any]]:
    """
    Finds similar past ideas. Uses native HNSW (O(log N)) when available,
    falls back to Python brute-force (O(N)) otherwise.

    Returns list of {validation_id, idea, feasibility_score, similarity}.
    """
    if not query_embedding:
        return []

    vec = query_embedding[:VECTOR_DIM]

    # ── TRY HNSW FIRST ──
    if _check_hnsw_available():
        results = _hnsw_search(vec, exclude_id, top_k, min_similarity)
        if results is not None:
            return results

    # ── FALLBACK: Python brute-force ──
    return _fallback_search(vec, exclude_id, top_k, min_similarity)


def _hnsw_search(
    query_vec: List[float],
    exclude_id: str,
    top_k: int,
    min_similarity: float,
) -> Optional[List[Dict[str, Any]]]:
    """Native Redis HNSW KNN search. Returns None on failure (triggers fallback)."""
    try:
        r = _get_redis()
        query_blob = _embedding_to_bytes(query_vec)

        # FT.SEARCH with KNN — returns top_k * 2 to allow filtering
        fetch_count = top_k * 3

        result = r.execute_command(
            "FT.SEARCH", INDEX_NAME,
            f"*=>[KNN {fetch_count} @embedding $query_vec AS similarity]",
            "PARAMS", "2", "query_vec", query_blob,
            "SORTBY", "similarity",
            "LIMIT", "0", str(fetch_count),
            "RETURN", "4", "validation_id", "idea", "score", "similarity",
            "DIALECT", "2",
        )

        # Parse FT.SEARCH response: [total, key1, [fields...], key2, [fields...], ...]
        if not result or result[0] == 0:
            return []

        results = []
        i = 1
        while i < len(result):
            _key = result[i]
            fields = result[i + 1] if i + 1 < len(result) else []
            i += 2

            # Parse field pairs
            field_dict = {}
            for j in range(0, len(fields), 2):
                fname = fields[j].decode() if isinstance(fields[j], bytes) else str(fields[j])
                fval = fields[j + 1].decode() if isinstance(fields[j + 1], bytes) else str(fields[j + 1])
                field_dict[fname] = fval

            vid = field_dict.get("validation_id", "")
            if vid == exclude_id:
                continue

            # COSINE distance → similarity = 1 - distance
            raw_dist = float(field_dict.get("similarity", "1.0"))
            similarity = 1.0 - raw_dist

            if similarity >= min_similarity:
                results.append({
                    "validation_id": vid,
                    "idea": field_dict.get("idea", ""),
                    "feasibility_score": int(float(field_dict.get("score", "0"))),
                    "similarity": round(similarity, 3),
                })

            if len(results) >= top_k:
                break

        if results:
            logger.info(
                "[RedisMemory] HNSW search: %d matches (top: %.3f)",
                len(results), results[0]["similarity"],
            )
        return results

    except Exception as e:
        logger.warning("[RedisMemory] HNSW search failed: %s. Falling back.", e)
        return None


def _fallback_search(
    query_vec: List[float],
    exclude_id: str,
    top_k: int,
    min_similarity: float,
) -> List[Dict[str, Any]]:
    """Python brute-force cosine similarity. O(N) but works everywhere."""
    try:
        r = _get_redis_text()
        all_ids = r.smembers("embedding:index")
        if not all_ids:
            return []

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for vid in all_ids:
            if vid == exclude_id:
                continue
            raw = r.get(f"embedding:{vid}")
            if not raw:
                continue
            try:
                data = json.loads(raw)
                stored = data.get("embedding", [])
                if not stored:
                    continue
                sim = _cosine_similarity(query_vec, stored)
                if sim >= min_similarity:
                    scored.append((sim, {
                        "validation_id": data["validation_id"],
                        "idea": data.get("idea", ""),
                        "feasibility_score": data.get("score", 0),
                        "similarity": round(sim, 3),
                    }))
            except (json.JSONDecodeError, KeyError):
                continue

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [item for _, item in scored[:top_k]]
        if results:
            logger.info("[RedisMemory] Fallback search: %d matches (top: %.3f)", len(results), results[0]["similarity"])
        return results

    except Exception as e:
        logger.warning("[RedisMemory] Fallback search failed: %s", e)
        return []


def get_similarity_insights(similar_ideas: List[Dict[str, Any]]) -> str:
    """Generates human-readable insight string from similar past ideas."""
    if not similar_ideas:
        return ""

    lines = ["## 🧠 Historical Idea Intelligence\n"]
    lines.append("Similar ideas have been evaluated before:\n")

    for idea in similar_ideas[:3]:
        sim_pct = int(idea["similarity"] * 100)
        score = idea.get("feasibility_score", "?")
        desc = idea.get("idea", "Unknown")
        lines.append(f"- **{sim_pct}% similar**: \"{desc[:100]}\" (Feasibility: {score}/100)")

        memory = get_idea_memory(idea["validation_id"])
        if memory:
            gaps = memory.get("gaps", [])
            if gaps:
                lines.append(f"  - Previous gaps: {', '.join(gaps[:3])}")
            comps = memory.get("competitors", [])
            if comps:
                lines.append(f"  - Known competitors: {', '.join(comps[:3])}")

    lines.append(
        "\n⚠️ Use these historical insights to avoid repeating past failures "
        "and to identify validated market opportunities."
    )
    return "\n".join(lines)


# =====================================================================
# COSINE SIMILARITY (numpy-accelerated fallback only)
# =====================================================================

def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Cosine similarity — only used by the Python fallback path."""
    try:
        import numpy as np
        a = np.array(vec_a[:VECTOR_DIM], dtype=np.float32)
        b = np.array(vec_b[:VECTOR_DIM], dtype=np.float32)
        norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
    except ImportError:
        va, vb = vec_a[:VECTOR_DIM], vec_b[:VECTOR_DIM]
        dot = sum(a * b for a, b in zip(va, vb))
        mag_a = sum(a * a for a in va) ** 0.5
        mag_b = sum(b * b for b in vb) ** 0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
