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
#   4. The report JSON + RAG chunks are injected as context
#   5. Gemini generates a conversational answer grounded in real data
#   6. The answer is returned with source citations
#
# DESIGN DECISIONS:
#   - REST (POST), not WebSocket — questions are one-shot, not streamed.
#     The frontend can call this on button click or enter keypress.
#   - Stateless — no conversation history stored server-side. The frontend
#     can pass previous Q&A pairs in the request for multi-turn context.
#   - Rate limited by the frontend (no server-side throttle yet, defer to
#     Feature 20: Webhooks tier for that).
# ---------------------------------------------------------------------------

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException
from supabase import create_client, Client

from app.core.config import settings
from app.services.ai_pipeline import embed_text, _get_gemini
from app.services.rag import retrieve_context
from google.genai import types as genai_types


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/api/v1", tags=["Conversational RAG"])


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    """A single message in the conversation history."""
    role: str = Field(description="'user' or 'assistant'.")
    content: str = Field(description="The message text.")


class ChatRequest(BaseModel):
    """Inbound chat request from the frontend."""
    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="The user's question about their validation report.",
    )
    # Optional conversation history for multi-turn context.
    # The frontend manages this — we are stateless server-side.
    history: List[ChatMessage] = Field(
        default_factory=list,
        description="Previous Q&A pairs for multi-turn context (max 10).",
    )


class ChatSource(BaseModel):
    """A RAG source chunk that contributed to the answer."""
    text: str = Field(description="Excerpt from the source chunk.")
    source_url: Optional[str] = Field(default=None)


class ChatResponse(BaseModel):
    """Outbound chat response to the frontend."""
    answer: str = Field(description="Gemini's answer grounded in report + RAG data.")
    sources: List[ChatSource] = Field(
        default_factory=list,
        description="RAG chunks that were used as context.",
    )
    tokens_used: int = Field(default=0)


# ---------------------------------------------------------------------------
# Supabase client (module-level singleton)
# ---------------------------------------------------------------------------
_supabase: Client | None = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase


# ---------------------------------------------------------------------------
# System prompt for conversational RAG
# ---------------------------------------------------------------------------

_CHAT_SYSTEM_PROMPT = (
    "You are StartupScope AI, an expert startup analyst. The user has received "
    "a validation report for their startup idea and is now asking follow-up "
    "questions.\n\n"
    "RULES:\n"
    "1. Answer ONLY using the provided Report Data and RAG Context below. "
    "   Do NOT make up information or hallucinate competitor data.\n"
    "2. If the answer is not in the provided context, say so clearly.\n"
    "3. Use specific numbers, quotes, and data points from the context.\n"
    "4. Format your answer in clean markdown with headers if needed.\n"
    "5. Keep answers concise — 2-4 paragraphs max unless the user asks "
    "   for more detail.\n"
    "6. When referencing competitors, cite the source if available.\n"
)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/chat/{validation_id}",
    response_model=ChatResponse,
    summary="Ask a follow-up question about a validation report",
    description=(
        "Feature 12: Conversational RAG. Embeds the user's question, "
        "retrieves relevant RAG chunks via pgvector, and passes them to "
        "Gemini alongside the report for a grounded answer."
    ),
)
async def chat_with_report(validation_id: str, request: ChatRequest) -> ChatResponse:
    """
    POST /api/v1/chat/{validation_id}

    Takes a user question, retrieves RAG grounding context + the stored
    report, and generates a conversational answer via Gemini.
    """
    supabase = _get_supabase()

    # ── 1. FETCH THE VALIDATION REPORT ───────────────────────────────
    try:
        result = (
            supabase.table("validations")
            .select("report_json, markdown_report, idea_description, status")
            .eq("id", validation_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Validation not found: {e}")

    if not result.data:
        raise HTTPException(status_code=404, detail="Validation not found.")

    row = result.data
    if row.get("status") != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Validation is not yet completed (status: {row.get('status')})."
        )

    report_json = row.get("report_json", {})
    markdown_report = row.get("markdown_report", "")
    idea_description = row.get("idea_description", "")

    # ── 2. RETRIEVE RAG GROUNDING CONTEXT ────────────────────────────
    # Embed the user's question and search for relevant chunks.
    rag_context = retrieve_context(
        query_text=request.question,
        validation_id=validation_id,
        top_k=5,  # Fewer chunks for chat — keep it focused
    )

    # Also fetch the source URLs for citations
    sources: List[ChatSource] = []
    if rag_context:
        # Split context back into chunks for source attribution
        context_chunks = rag_context.split("\n\n---\n\n")
        for chunk in context_chunks[:5]:
            sources.append(ChatSource(
                text=chunk[:300],  # Truncated excerpt
                source_url=None,   # URL attribution would require the RPC to return it
            ))

    # ── 3. BUILD THE GEMINI PROMPT ───────────────────────────────────
    # Inject: report data + RAG chunks + conversation history + question

    context_parts = [
        f"## Report Data (JSON)\n```json\n{_safe_json_dump(report_json)}\n```",
    ]

    # Include a trimmed version of the markdown report for richer context
    if markdown_report:
        context_parts.append(
            f"\n## Report Summary\n{markdown_report[:3000]}"
        )

    if rag_context:
        context_parts.append(
            f"\n## RAG-Retrieved Competitor Data\n{rag_context[:3000]}"
        )

    full_context = "\n\n".join(context_parts)

    # Build the conversation messages
    messages_parts = [full_context]

    # Append conversation history (max 10 turns to save tokens)
    for msg in request.history[-10:]:
        role_label = "User" if msg.role == "user" else "Assistant"
        messages_parts.append(f"\n**{role_label}:** {msg.content}")

    # Append the current question
    messages_parts.append(f"\n**User:** {request.question}")

    user_prompt = "\n".join(messages_parts)

    # ── 4. CALL GEMINI ───────────────────────────────────────────────
    try:
        client = _get_gemini()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=_CHAT_SYSTEM_PROMPT,
                temperature=0.6,
                max_output_tokens=2048,
            ),
        )

        answer = response.text or "I wasn't able to generate an answer. Please try rephrasing."

        # Extract token usage
        usage = response.usage_metadata
        tokens_used = getattr(usage, "total_token_count", 0) or 0

    except Exception as e:
        print(f"[Chat] Gemini call failed: {e}", flush=True)
        raise HTTPException(
            status_code=500,
            detail=f"AI generation failed: {str(e)[:200]}",
        )

    # ── 5. RETURN RESPONSE ───────────────────────────────────────────
    return ChatResponse(
        answer=answer,
        sources=sources,
        tokens_used=tokens_used,
    )


def _safe_json_dump(obj: dict, max_length: int = 2000) -> str:
    """Safely dumps a dict to JSON string, truncated to max_length."""
    try:
        raw = __import__("json").dumps(obj, indent=2)
        if len(raw) > max_length:
            return raw[:max_length] + "\n... (truncated)"
        return raw
    except Exception:
        return str(obj)[:max_length]
