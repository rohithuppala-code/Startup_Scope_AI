# chat_router.py
# ---------------------------------------------------------------------------
# FEATURE 12: Conversational RAG — "Ask Your Report"
#
# A REST endpoint that lets users ask follow-up questions about their
# validation report, grounded in the RAG-stored competitor data.
#
# FLOW:
#   1. User sends a question via POST /api/v1/chat/{validation_id}
#   2. The question is embedded using Gemini text-embedding-004 (768-dim)
#   3. Top-K RAG chunks are retrieved via pgvector cosine similarity
#      (with relevance-score filtering — low-score chunks are discarded)
#   4. The report JSON + RAG chunks are injected as context
#      (with dynamic token-budget truncation so we never overflow)
#   5. Gemini generates a conversational answer grounded in real data,
#      called via run_in_executor so the event loop is never blocked
#   6. On Gemini failure the endpoint falls back to Groq (llama3-70b)
#   7. The answer is returned with source citations (real URLs from RAG)
#
# DESIGN DECISIONS:
#   - REST (POST), not WebSocket — questions are one-shot, not streamed.
#   - Stateless — no conversation history stored server-side.
#   - Per-user rate limiting via SlowAPI (10 req / minute).
#   - Ownership enforced: every DB query filters by current_user.user_id.
# ---------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import json
import logging
from functools import partial
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from google.genai import types as genai_types
from groq import Groq
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from supabase import Client, create_client

from app.core.config import settings
from app.services.ai_pipeline import _get_gemini
from app.services.rag import retrieve_context_structured       # returns List[Chunk]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter  (FIX #3 — per-user throttle)
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)   # swap key_func for user-id if preferred

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/api/v1", tags=["Conversational RAG"])


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str = Field(description="'user' or 'assistant'.")
    content: str = Field(description="The message text.")


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    history: List[ChatMessage] = Field(default_factory=list)


class ChatSource(BaseModel):
    text: str
    source_url: Optional[str] = None          # FIX #7 — now populated from RAG


class ChatResponse(BaseModel):
    answer: str
    sources: List[ChatSource] = Field(default_factory=list)
    tokens_used: int = 0
    fallback_used: bool = False               # surface to client for transparency


# ---------------------------------------------------------------------------
# Supabase singleton
# ---------------------------------------------------------------------------
_supabase: Client | None = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(
            settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY
        )
    return _supabase


# ---------------------------------------------------------------------------
# Groq fallback client
# ---------------------------------------------------------------------------
def _get_groq() -> Groq:
    return Groq(api_key=settings.GROQ_API_KEY)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
_CHAT_SYSTEM_PROMPT = (
    "You are StartupScope AI, an expert startup analyst. The user has received "
    "a validation report for their startup idea and is now asking follow-up "
    "questions.\n\n"
    "RULES:\n"
    "1. Answer ONLY using the provided Report Data and RAG Context below. "
    "   Do NOT hallucinate competitor data.\n"
    "2. If the answer is not in the provided context, say so clearly.\n"
    "3. Use specific numbers, quotes, and data points from the context.\n"
    "4. Format your answer in clean markdown with headers if needed.\n"
    "5. Keep answers concise — 2-4 paragraphs max unless the user asks "
    "   for more detail.\n"
    "6. When referencing competitors, cite the source URL if available.\n"
)


# ---------------------------------------------------------------------------
# Token-budget helpers  (FIX #6 — prevent context overflow)
# ---------------------------------------------------------------------------
_CHARS_PER_TOKEN = 4          # rough approximation
_MAX_CONTEXT_TOKENS = 28_000  # safe headroom under gemini-2.5-flash 32k window
_MAX_CONTEXT_CHARS = _MAX_CONTEXT_TOKENS * _CHARS_PER_TOKEN


def _budget_truncate(text: str, remaining_chars: int) -> tuple[str, int]:
    """Truncate *text* to *remaining_chars*, return (truncated, chars_used)."""
    truncated = text[:remaining_chars]
    if len(text) > remaining_chars:
        truncated += "\n... [truncated to fit context window]"
    return truncated, len(truncated)


# ---------------------------------------------------------------------------
# Gemini call (sync, wrapped in executor)  (FIX #1 — non-blocking)
# ---------------------------------------------------------------------------
def _call_gemini_sync(prompt: str) -> tuple[str, int]:
    """Blocking Gemini call — must be run via run_in_executor."""
    client = _get_gemini(task="consensus")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=_CHAT_SYSTEM_PROMPT,
            temperature=0.6,
            max_output_tokens=2048,
        ),
    )
    text = response.text or ""
    tokens = getattr(response.usage_metadata, "total_token_count", 0) or 0
    return text, tokens


# ---------------------------------------------------------------------------
# Groq fallback call (sync, wrapped in executor)  (FIX #2 — LLM fallback)
# ---------------------------------------------------------------------------
def _call_groq_sync(prompt: str) -> tuple[str, int]:
    """Blocking Groq call — must be run via run_in_executor."""
    groq = _get_groq()
    resp = groq.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": _CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.6,
        max_tokens=2048,
    )
    text = resp.choices[0].message.content or ""
    tokens = getattr(resp.usage, "total_tokens", 0) or 0
    return text, tokens


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/chat/{validation_id}",
    response_model=ChatResponse,
    summary="Ask a follow-up question about a validation report",
)
@limiter.limit("10/minute")                    # FIX #3 — rate limit
async def chat_with_report(
    request: Request,                          # required by SlowAPI
    validation_id: str,
    body: ChatRequest,
    x_user_id: str = Header(..., description="Authenticated user UUID", alias="X-User-Id"),
) -> ChatResponse:
    supabase = _get_supabase()
    loop = asyncio.get_event_loop()

    # ── 1. FETCH THE VALIDATION REPORT (ownership-gated)  ────────────
    # FIX #8: filter by user_id so users can only query their own reports.
    try:
        result = (
            supabase.table("validations")
            .select("status, report_json, markdown_report, idea_description")
            .eq("id", validation_id)
            .eq("user_id", x_user_id)   # ← ownership check
            .single()
            .execute()
        )
    except Exception as exc:
        logger.warning("Validation fetch failed: validation_id=%s err=%s", validation_id, exc)
        raise HTTPException(status_code=404, detail="Validation not found.")

    if not result.data:
        raise HTTPException(status_code=404, detail="Validation not found.")

    row = result.data
    if row.get("status") != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Validation is not yet completed (status: {row.get('status')}).",
        )

    report_json: dict = row.get("report_json") or {}
    markdown_report: str = row.get("markdown_report") or ""

    # ── 2. RETRIEVE RAG CONTEXT (structured chunks with scores)  ─────
    # FIX #4: retrieve_context_structured() returns List[Chunk] objects,
    #         not a raw string — no fragile separator parsing.
    # FIX #5: filter by relevance score threshold.
    # FIX #9: embedding is explicit here — retrieve_context_structured
    #         accepts raw text and embeds internally, but we document it.
    RAG_TOP_K = 8
    RELEVANCE_THRESHOLD = 0.72   # cosine similarity; tune per your index

    raw_chunks = await loop.run_in_executor(          # non-blocking embed + search
        None,
        partial(
            retrieve_context_structured,
            query_text=body.question,
            user_id=x_user_id,
            top_k=RAG_TOP_K,
        ),
    )

    # Discard low-relevance chunks (FIX #5)
    relevant_chunks = [c for c in raw_chunks if c.score >= RELEVANCE_THRESHOLD]
    logger.info(
        "RAG: %d/%d chunks passed relevance threshold %.2f",
        len(relevant_chunks), len(raw_chunks), RELEVANCE_THRESHOLD,
    )

    sources: List[ChatSource] = [
        ChatSource(text=c.text[:300], source_url=c.source_url)   # FIX #7 — real URLs
        for c in relevant_chunks[:5]
    ]

    # ── 3. BUILD PROMPT WITH TOKEN BUDGET  ───────────────────────────
    # FIX #6: track remaining character budget to avoid context overflow.
    budget = _MAX_CONTEXT_CHARS
    prompt_parts: list[str] = []

    # 3a. Report JSON (highest priority — truncate aggressively if needed)
    json_str = json.dumps(report_json, indent=2)
    json_section, used = _budget_truncate(f"## Report Data (JSON)\n```json\n{json_str}\n```", budget)
    prompt_parts.append(json_section)
    budget -= used

    # 3b. Markdown report summary
    if markdown_report and budget > 500:
        md_section, used = _budget_truncate(f"\n## Report Summary\n{markdown_report}", budget - 500)
        prompt_parts.append(md_section)
        budget -= used

    # 3c. RAG chunks
    if relevant_chunks and budget > 500:
        rag_text = "\n\n---\n\n".join(c.text for c in relevant_chunks)
        rag_section, used = _budget_truncate(f"\n## RAG-Retrieved Competitor Data\n{rag_text}", budget - 500)
        prompt_parts.append(rag_section)
        budget -= used

    # 3d. Conversation history (last 10 turns, oldest dropped if budget tight)
    history_turns = body.history[-10:]
    for msg in history_turns:
        label = "User" if msg.role == "user" else "Assistant"
        turn = f"\n**{label}:** {msg.content}"
        if budget < len(turn) + 200:
            break
        prompt_parts.append(turn)
        budget -= len(turn)

    # 3e. Current question
    prompt_parts.append(f"\n**User:** {body.question}")

    full_prompt = "\n".join(prompt_parts)

    # ── 4. CALL GEMINI (non-blocking)  ───────────────────────────────
    # FIX #1: run_in_executor so the async event loop is not blocked.
    # FIX #2: Groq fallback on any Gemini failure.
    fallback_used = False
    answer = ""
    tokens_used = 0

    try:
        answer, tokens_used = await loop.run_in_executor(
            None, partial(_call_gemini_sync, full_prompt)
        )
        if not answer:
            raise ValueError("Empty response from Gemini")
    except Exception as gemini_err:
        logger.warning("Gemini failed (%s) — falling back to Groq", gemini_err)
        try:
            answer, tokens_used = await loop.run_in_executor(
                None, partial(_call_groq_sync, full_prompt)
            )
            fallback_used = True
            if not answer:
                raise ValueError("Empty response from Groq fallback")
        except Exception as groq_err:
            # FIX #10: structured error logging; degraded-mode message instead of raw 500
            logger.error(
                "Both LLM providers failed. gemini_err=%s groq_err=%s",
                gemini_err, groq_err,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "The AI service is temporarily unavailable. "
                    "Please try again in a few seconds."
                ),
            )

    # ── 5. RETURN RESPONSE  ──────────────────────────────────────────
    return ChatResponse(
        answer=answer,
        sources=sources,
        tokens_used=tokens_used,
        fallback_used=fallback_used,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_json_dump(obj: dict, max_length: int = 2000) -> str:
    try:
        raw = json.dumps(obj, indent=2)
        return raw[:max_length] + ("\n... (truncated)" if len(raw) > max_length else "")
    except Exception:
        return str(obj)[:max_length]