# rag.py
# ---------------------------------------------------------------------------
# FEATURE 2: RAG Grounding Layer
#
# Retrieval-Augmented Generation pipeline that grounds AI analysis in
# verified competitor data rather than relying solely on model knowledge.
#
# PIPELINE:
#   1. CHUNK: Split raw Firecrawl output into ~500-token pieces.
#   2. EMBED: Generate 768-dim vectors via Gemini text-embedding-004.
#   3. STORE: Insert chunks + vectors into the `rag_chunks` pgvector table.
#   4. RETRIEVE: At inference time, embed the user's idea, cosine-search
#      top-K chunks, and inject them into the AI prompt as grounding context.
#
# DESIGN DECISIONS:
#   - 768 native dimensions (no padding) per user directive.
#   - Chunks are ~500 tokens (~375 words) for optimal embedding quality.
#   - We use Supabase RPC for cosine similarity search (pgvector operator).
#   - Chunks are linked to validation_id for per-request isolation.
# ---------------------------------------------------------------------------

from __future__ import annotations

import re
from typing import List, Tuple
from dataclasses import dataclass

@dataclass
class Chunk:
    text: str
    score: float
    source_url: str = ""

from supabase import create_client, Client

from app.core.config import settings
from app.services.ai_pipeline import embed_text, embed_texts_batch


# ---------------------------------------------------------------------------
# Supabase client (service role — bypasses RLS)
# Module-level singleton for connection reuse across Celery task calls.
# ---------------------------------------------------------------------------
_supabase: Client | None = None


def _get_supabase() -> Client:
    """Returns the module-level Supabase client singleton."""
    global _supabase
    if _supabase is None:
        _supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase


# =====================================================================
# STEP 1: CHUNKING
#
# Splits raw text into chunks of approximately `chunk_size` tokens.
# We estimate 1 token ≈ 0.75 words (conservative for English text).
# Chunks are split on paragraph boundaries first, then on sentence
# boundaries, to preserve semantic coherence.
# =====================================================================

def chunk_text(
    text: str,
    chunk_size_tokens: int = 500,
    overlap_tokens: int = 50,
) -> List[str]:
    """
    Splits text into chunks of approximately `chunk_size_tokens` tokens.

    Uses a two-pass approach:
      1. Split on double-newlines (paragraph boundaries).
      2. If a paragraph exceeds chunk_size, split on sentence boundaries.
      3. Merge small consecutive paragraphs into a single chunk.

    Args:
        text: Raw text to chunk (typically from Firecrawl).
        chunk_size_tokens: Target size per chunk in tokens (~0.75 words/token).
        overlap_tokens: Number of tokens to overlap between chunks for context.

    Returns:
        List of text chunks, each approximately chunk_size_tokens long.
    """
    if not text or not text.strip():
        return []

    # Estimate word count target from token count (1 token ≈ 0.75 words)
    target_words = int(chunk_size_tokens * 0.75)
    overlap_words = int(overlap_tokens * 0.75)

    # Pass 1: Split on paragraph boundaries (double newlines)
    paragraphs = re.split(r"\n\s*\n", text.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    # Pass 2: Split oversized paragraphs on sentence boundaries
    segments: List[str] = []
    for para in paragraphs:
        words = para.split()
        if len(words) <= target_words:
            segments.append(para)
        else:
            # Split on sentence boundaries (period + space + capital letter)
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current_segment: List[str] = []
            current_word_count = 0

            for sentence in sentences:
                sentence_words = len(sentence.split())
                if current_word_count + sentence_words > target_words and current_segment:
                    segments.append(" ".join(current_segment))
                    # Keep overlap from the end of the previous segment
                    overlap_text = " ".join(current_segment)
                    overlap_start = overlap_text.split()[-overlap_words:] if overlap_words > 0 else []
                    current_segment = overlap_start + [sentence]
                    current_word_count = len(" ".join(current_segment).split())
                else:
                    current_segment.append(sentence)
                    current_word_count += sentence_words

            if current_segment:
                segments.append(" ".join(current_segment))

    # Pass 3: Merge small consecutive segments
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_word_count = 0

    for segment in segments:
        segment_words = len(segment.split())
        if current_word_count + segment_words > target_words and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [segment]
            current_word_count = segment_words
        else:
            current_chunk.append(segment)
            current_word_count += segment_words

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    print(f"[RAG] Chunked text into {len(chunks)} chunks (target: {chunk_size_tokens} tokens each).", flush=True)
    return chunks


# =====================================================================
# STEP 2 + 3: EMBED AND STORE
#
# Embeds each chunk via Gemini text-embedding-004 (768 dims) and
# inserts into the `rag_chunks` table in Supabase (pgvector).
# =====================================================================

def embed_and_store_chunks(
    validation_id: str,
    chunks: List[str],
    source_urls: List[str] | None = None,
) -> int:
    """
    Embeds each text chunk and stores it in the rag_chunks table.

    Args:
        validation_id: The validation this data belongs to.
        chunks: List of text chunks from chunk_text().
        source_urls: Optional list of source URLs (mapped by index).

    Returns:
        Number of chunks successfully stored.
    """
    if not chunks:
        return 0

    supabase = _get_supabase()

    # Batch embed all chunks
    embeddings = embed_texts_batch(chunks)

    # Build insert payload — skip chunks with failed embeddings
    rows_to_insert: List[dict] = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        if not embedding:
            print(f"[RAG] Skipping chunk {i} — embedding failed.", flush=True)
            continue

        source_url = source_urls[i] if source_urls and i < len(source_urls) else None
        rows_to_insert.append({
            "validation_id": validation_id,
            "source_url": source_url,
            "chunk_index": i,
            "chunk_text": chunk,
            "embedding": embedding,
        })

    if not rows_to_insert:
        print("[RAG] No chunks with valid embeddings to store.", flush=True)
        return 0

    # Batch insert into Supabase (pgvector handles the vector column)
    try:
        result = supabase.table("rag_chunks").insert(rows_to_insert).execute()
        stored_count = len(result.data) if result.data else 0
        print(f"[RAG] Stored {stored_count}/{len(chunks)} chunks for {validation_id}.", flush=True)
        return stored_count
    except Exception as e:
        print(f"[RAG] Failed to store chunks: {e}", flush=True)
        return 0


# =====================================================================
# STEP 4: RETRIEVE GROUNDING CONTEXT
#
# At inference time, embed the user's query/idea, run cosine similarity
# search against the stored chunks, and return the top-K most relevant
# chunks as grounding context for the AI prompt.
#
# IMPLEMENTATION NOTE: Supabase does not have a built-in vector search
# RPC out of the box. We use a raw SQL query via the Supabase RPC
# mechanism. The SQL function must be created in Supabase first
# (see migration script below).
#
# FALLBACK: If the RPC function doesn't exist yet, we fall back to
# fetching all chunks for the validation and doing a brute-force
# cosine similarity in Python. This is slower but works without
# any database setup.
# =====================================================================

def retrieve_context(
    query_text: str,
    validation_id: str,
    top_k: int = 10,
) -> str:
    """
    Retrieves the top-K most relevant RAG chunks for the given query.

    Strategy:
      1. Embed the query text using Gemini text-embedding-004.
      2. Attempt RPC-based vector search (fast, requires DB function).
      3. Fallback: fetch all chunks for validation_id, compute cosine
         similarity in Python, return top-K.

    Args:
        query_text: The text to search for (typically the startup idea).
        validation_id: Scope the search to chunks from this validation.
        top_k: Number of top chunks to retrieve.

    Returns:
        Concatenated text of the top-K most relevant chunks.
        Empty string if no chunks are found or embedding fails.
    """
    # Step 1: Embed the query
    query_embedding = embed_text(query_text)
    if not query_embedding:
        print("[RAG] Query embedding failed — skipping RAG grounding.", flush=True)
        return ""

    supabase = _get_supabase()

    # Step 2: Try RPC-based vector search (requires match_rag_chunks function)
    try:
        result = supabase.rpc("match_rag_chunks", {
            "query_embedding": query_embedding,
            "match_validation_id": validation_id,
            "match_count": top_k,
        }).execute()

        if result.data:
            chunks = [row["chunk_text"] for row in result.data if row.get("chunk_text")]
            if chunks:
                print(f"[RAG] Retrieved {len(chunks)} grounding chunks via RPC.", flush=True)
                return "\n\n---\n\n".join(chunks)
    except Exception as rpc_err:
        print(f"[RAG] RPC search failed (function may not exist yet): {rpc_err}", flush=True)

    # Step 3: Fallback — brute-force cosine similarity in Python
    try:
        all_chunks = (
            supabase.table("rag_chunks")
            .select("chunk_text, embedding")
            .eq("validation_id", validation_id)
            .execute()
        )

        if not all_chunks.data:
            print("[RAG] No chunks found for this validation.", flush=True)
            return ""

        # Compute cosine similarity for each chunk
        scored_chunks: List[Tuple[float, str]] = []
        for row in all_chunks.data:
            chunk_embedding = row.get("embedding")
            chunk_text = row.get("chunk_text", "")

            if isinstance(chunk_embedding, str):
                import json
                try:
                    chunk_embedding = json.loads(chunk_embedding)
                except Exception:
                    chunk_embedding = None

            if not chunk_embedding or not chunk_text:
                continue

            # Cosine similarity
            similarity = _cosine_similarity(query_embedding, chunk_embedding)
            scored_chunks.append((similarity, chunk_text))

        # Sort by similarity (descending) and take top-K
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [text for _, text in scored_chunks[:top_k]]

        if top_chunks:
            print(f"[RAG] Retrieved {len(top_chunks)} grounding chunks via fallback.", flush=True)
            return "\n\n---\n\n".join(top_chunks)

    except Exception as fallback_err:
        print(f"[RAG] Fallback search failed: {fallback_err}", flush=True)

    return ""


def retrieve_context_structured(
    query_text: str,
    user_id: str,
    top_k: int = 10,
) -> List[Chunk]:
    """
    Retrieves the top-K most relevant RAG chunks for the given query.
    Returns a list of Chunk objects instead of a concatenated string.
    """
    query_embedding = embed_text(query_text)
    if not query_embedding:
        print("[RAG] Query embedding failed — skipping RAG grounding.", flush=True)
        return []

    supabase = _get_supabase()
    chunks_result: List[Chunk] = []

    try:
        # Fetch all validation IDs owned by this user
        user_validations = supabase.table("validations").select("id").eq("user_id", user_id).execute()
        user_validation_ids = [row["id"] for row in user_validations.data] if user_validations.data else []

        if not user_validation_ids:
            print("[RAG] No validations found for this user.", flush=True)
            return []

        # Fallback: brute-force cosine similarity in Python across ALL user data
        all_chunks = (
            supabase.table("rag_chunks")
            .select("chunk_text, embedding, source_url")
            .in_("validation_id", user_validation_ids)
            .execute()
        )

        if not all_chunks.data:
            print("[RAG] No chunks found for this validation.", flush=True)
            return []

        scored_chunks: List[Tuple[float, str, str]] = []
        for row in all_chunks.data:
            chunk_embedding = row.get("embedding")
            chunk_text = row.get("chunk_text", "")
            source_url = row.get("source_url") or ""

            if isinstance(chunk_embedding, str):
                import json
                try:
                    chunk_embedding = json.loads(chunk_embedding)
                except Exception:
                    chunk_embedding = None

            if not chunk_embedding or not chunk_text:
                continue

            similarity = _cosine_similarity(query_embedding, chunk_embedding)
            scored_chunks.append((similarity, chunk_text, source_url))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        
        for sim, text, url in scored_chunks[:top_k]:
            chunks_result.append(Chunk(text=text, score=sim, source_url=url))
            
        print(f"[RAG] Retrieved {len(chunks_result)} structured chunks via fallback.", flush=True)
    except Exception as fallback_err:
        print(f"[RAG] Structured search failed: {fallback_err}", flush=True)

    return chunks_result

def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Computes cosine similarity between two vectors.

    PERFORMANCE FIX: The original pure Python implementation used a list
    comprehension over 768 dimensions — ~50x slower than numpy for the
    fallback RAG path which must score ALL stored chunks. We now use numpy
    for the vectorized dot product and norms. Numpy is already transitively
    available via google-generativeai (it depends on numpy internally).

    Falls back to pure Python if numpy is not available.
    """
    try:
        import numpy as np
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)

        # Handle dimension mismatch by truncating to the shorter vector
        if len(a) != len(b):
            min_len = min(len(a), len(b))
            a = a[:min_len]
            b = b[:min_len]

        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    except ImportError:
        # Pure Python fallback (no numpy)
        if len(vec_a) != len(vec_b):
            min_len = min(len(vec_a), len(vec_b))
            vec_a = vec_a[:min_len]
            vec_b = vec_b[:min_len]

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        magnitude_a = sum(a * a for a in vec_a) ** 0.5
        magnitude_b = sum(b * b for b in vec_b) ** 0.5

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0
        return dot_product / (magnitude_a * magnitude_b)


# =====================================================================
# SUPABASE RPC FUNCTION (run this in the SQL Editor)
#
# This function must be created in Supabase for the fast RPC search
# path to work. The Python fallback works without it.
#
# CREATE OR REPLACE FUNCTION match_rag_chunks(
#     query_embedding vector(768),
#     match_validation_id UUID,
#     match_count INT DEFAULT 10
# )
# RETURNS TABLE (
#     id UUID,
#     chunk_text TEXT,
#     source_url TEXT,
#     chunk_index INT,
#     similarity FLOAT
# )
# LANGUAGE plpgsql
# AS $$
# BEGIN
#     RETURN QUERY
#     SELECT
#         rc.id,
#         rc.chunk_text,
#         rc.source_url,
#         rc.chunk_index,
#         1 - (rc.embedding <=> query_embedding) AS similarity
#     FROM rag_chunks rc
#     WHERE rc.validation_id = match_validation_id
#     ORDER BY rc.embedding <=> query_embedding
#     LIMIT match_count;
# END;
# $$;
# =====================================================================
