# ai_pipeline.py
# ---------------------------------------------------------------------------
# THE INTELLIGENCE LAYER — Production-grade AI pipeline with:
#
# 1. Self-healing structured output (Feature 3):
#    Pydantic v2 enforces strict JSON schema on every response. If a model
#    returns malformed output, tenacity retries up to 3 times, injecting the
#    broken output + the schema back into the prompt so the model corrects
#    itself.
#
# 2. Dual-provider support (Feature 1 prerequisite):
#    - Gemini 1.5 Pro / 2.0 Flash for deep analysis
#    - Groq (Llama 3.1 70B) for speed
#    Both produce the identical AIReportResponse schema.
#
# 3. RAG-ready embeddings (Feature 2 prerequisite):
#    - 768-dimensional native Gemini text-embedding-004 vectors
#    - No zero-padding — pure native dimensions for optimal cosine similarity
#
# 4. Module-level client singletons for connection reuse across Celery tasks.
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from firecrawl import FirecrawlApp
from google import genai
from google.genai import types as genai_types
from groq import Groq
from pydantic import ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
import logging

from app.core.config import settings
from app.schemas.ai_reports import AIReportResponse, ReportDetails
from app.core.telemetry import track_ai_call

logger = logging.getLogger(__name__)


# =====================================================================
# MODULE-LEVEL CLIENT SINGLETONS
#
# One connection pool per Celery worker process. Clients are created
# lazily on first access so the settings object is fully loaded.
# =====================================================================

_firecrawl_app: FirecrawlApp | None = None
_gemini_clients: Dict[str, genai.Client] = {}
_groq_client: Groq | None = None


def _get_firecrawl() -> FirecrawlApp:
    """Returns the module-level FirecrawlApp singleton."""
    global _firecrawl_app
    if _firecrawl_app is None:
        _firecrawl_app = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)
    return _firecrawl_app


def _get_gemini(task: str = "default") -> genai.Client:
    """Returns a module-level Gemini client singleton for the specified task."""
    global _gemini_clients
    if task not in _gemini_clients:
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


def _get_groq() -> Groq:
    """Returns the module-level Groq client singleton."""
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.GROQ_API_KEY)
    return _groq_client


# =====================================================================
# SYSTEM PROMPTS (shared between providers for consistency)
# =====================================================================

_ANALYSIS_SYSTEM_PROMPT = (
    "You are an elite Startup Analyst AI. Analyze the provided startup idea "
    "and any competitor/market data with surgical precision.\n\n"
    "You MUST output valid JSON matching this exact schema:\n"
    f"{json.dumps(AIReportResponse.model_json_schema(), indent=2)}\n\n"
    "The 'markdown' field MUST be a long-form, professional report with "
    "sections for Executive Summary, Market Analysis, Competitive Landscape, "
    "SWOT Analysis, Go-to-Market Strategy, and Risks."
)

_SELF_HEAL_PROMPT_TEMPLATE = (
    "Your previous response was malformed and failed validation.\n\n"
    "--- BROKEN OUTPUT ---\n{broken_output}\n\n"
    "--- VALIDATION ERROR ---\n{error_message}\n\n"
    "--- REQUIRED JSON SCHEMA ---\n{schema}\n\n"
    "Please output ONLY the corrected JSON matching the schema exactly. "
    "Do not include any explanation or markdown fencing."
)


# =====================================================================
# SELF-HEALING JSON PARSER
#
# Feature 3: This is the core self-heal mechanism. It attempts to parse
# raw model output into the strict Pydantic schema. If it fails, the
# caller retries with a correction prompt containing the broken output,
# the error, and the expected schema.
# =====================================================================

class SelfHealParseError(Exception):
    """
    Raised when AI output fails Pydantic validation.

    Carries the broken output and the validation error so the retry loop
    can construct a self-heal correction prompt.
    """
    def __init__(self, broken_output: str, validation_error: str):
        self.broken_output = broken_output
        self.validation_error = validation_error
        super().__init__(f"Self-heal needed: {validation_error[:200]}")


def _parse_ai_response(raw_text: str) -> AIReportResponse:
    """
    Attempts to parse raw AI output into the strict AIReportResponse schema.

    Raises SelfHealParseError if validation fails — this triggers the
    tenacity retry with a correction prompt.
    """
    try:
        # First attempt: direct Pydantic validation from JSON string
        return AIReportResponse.model_validate_json(raw_text)
    except (ValidationError, json.JSONDecodeError):
        pass

    # Second attempt: parse as Python dict first (handles quirky JSON wrapping)
    try:
        data = json.loads(raw_text)
        return AIReportResponse.model_validate(data)
    except (ValidationError, json.JSONDecodeError) as e:
        raise SelfHealParseError(
            broken_output=raw_text[:2000],  # Truncate to save tokens on retry
            validation_error=str(e),
        )


# =====================================================================
# FIRECRAWL — Competitor Discovery (Advanced Pipeline)
#
# Delegates to the full Search→Rank→Scrape→Extract→Iterate pipeline
# in firecrawl_pipeline.py. The old signature is preserved for
# backward compatibility with celery_tasks.py.
# =====================================================================

def firecrawl_scrape(idea_description: str) -> Tuple[str, List[str]]:
    """
    Backward-compatible wrapper around the advanced Firecrawl pipeline.

    Returns:
        Tuple of (concatenated_markdown, list_of_competitor_urls).
    """
    try:
        from app.services.firecrawl_pipeline import run_firecrawl_pipeline
        markdown, urls, _features = run_firecrawl_pipeline(idea_description)
        return markdown, urls
    except Exception as e:
        print(f"[Firecrawl] Advanced pipeline failed, using fallback: {e}", flush=True)
        return _firecrawl_scrape_fallback(idea_description)


def firecrawl_scrape_advanced(
    idea_description: str,
    target_market: str = "",
    budget_constraints: str = "",
) -> Tuple[str, List[str], Dict[str, Any]]:
    """
    Full advanced pipeline — returns markdown, URLs, AND extracted features.
    Called directly by the upgraded celery_tasks.py.
    """
    try:
        from app.services.firecrawl_pipeline import run_firecrawl_pipeline
        return run_firecrawl_pipeline(idea_description, target_market, budget_constraints)
    except Exception as e:
        print(f"[Firecrawl] Advanced pipeline failed: {e}", flush=True)
        md, urls = _firecrawl_scrape_fallback(idea_description)
        return md, urls, {"competitors": []}


def _firecrawl_scrape_fallback(idea_description: str) -> Tuple[str, List[str]]:
    """Original single-query Firecrawl search as a fallback."""
    try:
        app = _get_firecrawl()
        search_query = f"competitors alternatives to {idea_description[:100]}"
        print(f"[Firecrawl] Fallback searching: {search_query}", flush=True)
        response = app.search(query=search_query, limit=5)

        competitor_results: List[str] = []
        competitor_urls: List[str] = []

        results_list = None
        if hasattr(response, "data") and response.data:
            results_list = response.data
        elif hasattr(response, "web") and response.web:
            results_list = response.web

        if results_list:
            for result in results_list:
                res_dict = (
                    result.model_dump() if hasattr(result, "model_dump") else dict(result)
                )
                url = res_dict.get("url", "")
                title = res_dict.get("title", "")
                desc = res_dict.get("description", "") or res_dict.get("snippet", "")
                if url:
                    competitor_urls.append(url)
                if url or title:
                    competitor_results.append(
                        f"Source: {url}\nTitle: {title}\nDescription: {desc}"
                    )

        if not competitor_results:
            return "No competitor data found from live search.", []

        return "\n\n---\n\n".join(competitor_results), competitor_urls

    except Exception as e:
        print(f"[Firecrawl] Fallback API error: {e}", flush=True)
        return "Firecrawl search failed or timed out. Competitor data unavailable.", []


# =====================================================================
# EMBEDDINGS — 768-dimensional native Gemini text-embedding-004
#
# Feature 2 prerequisite. Used for:
#   - RAG chunk embeddings (stored in rag_chunks table)
#   - Idea embeddings (stored in validations.idea_embedding)
#   - Query embeddings (for cosine similarity search at inference time)
#
# DESIGN: 768 native dimensions. NO zero-padding. Padding wastes memory
# and degrades cosine similarity accuracy.
# =====================================================================

def embed_text(text: str) -> List[float]:
    """
    Generates a 768-dimensional embedding for a single text string
    using Gemini's text-embedding-004 model.

    Returns an empty list on failure (caller must handle gracefully).
    """
    try:
        client = _get_gemini(task="embedding")
        
        # Feature 18: OpenTelemetry Tracking
        with track_ai_call("gemini-embedding-001", operation="embed") as ai_span:
            response = client.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
                config={"output_dimensionality": 768},
            )
            # Embeddings are cheap, but we still track tokens if available
            # (Note: embedding token usage isn't always returned directly depending on the SDK version)
            
        # google-genai SDK: single content → response.embedding.values
        if hasattr(response, "embedding") and response.embedding:
            return list(response.embedding.values)

        # Fallback: multi-content → response.embeddings[0].values
        if hasattr(response, "embeddings") and response.embeddings:
            return list(response.embeddings[0].values)

        return []
    except Exception as e:
        print(f"[Gemini] Embedding failed: {e}", flush=True)
        return []


def embed_texts_batch(texts: List[str]) -> List[List[float]]:
    """
    Batch-embeds multiple texts. Falls back to sequential embedding
    if the batch API is not available.

    Returns a list of embedding vectors (one per input text).
    Empty vectors are returned for texts that fail to embed.
    """
    embeddings: List[List[float]] = []
    for text in texts:
        embedding = embed_text(text)
        embeddings.append(embedding)
    return embeddings


# =====================================================================
# GEMINI REPORT GENERATION (with self-heal)
#
# Feature 3: Self-healing structured output. If Gemini returns malformed
# JSON, tenacity retries up to 3 times. Each retry injects the broken
# output + the Pydantic schema into a correction prompt.
# =====================================================================

def generate_gemini_report(
    idea_description: str,
    competitor_data: str,
    grounding_context: str = "",
) -> Tuple[Dict[str, Any], str, int, float, str]:
    """
    Calls Gemini with strict Pydantic response schema + self-heal.

    Args:
        idea_description: The startup idea to analyze.
        competitor_data: Raw Firecrawl output (competitor summaries).
        grounding_context: RAG-retrieved chunks for grounding (Feature 2).

    Returns:
        Tuple of (report_json, markdown_report, total_tokens, estimated_cost, model_name).
    """
    client = _get_gemini(task="consensus")

    # Build the user prompt with optional RAG grounding context
    user_prompt_parts = [f"Startup Idea: {idea_description}"]
    if grounding_context:
        user_prompt_parts.append(
            f"\n\n--- RAG-GROUNDED CONTEXT (verified competitor data) ---\n{grounding_context}"
        )
    user_prompt_parts.append(f"\n\nLive Competitor Data:\n{competitor_data}")
    user_prompt = "\n".join(user_prompt_parts)

    # Models to try in order (rate-limit cascade).
    # gemini-1.5-flash was REMOVED — it returns 404 on the v1beta API.
    # gemini-2.0-flash-lite is the valid lightweight fallback on v1beta.
    models_to_try = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]
    last_error: Exception | None = None

    for model_name in models_to_try:
        print(f"[Gemini] Generation starting with {model_name}...", flush=True)

        # ── Self-heal retry loop (Feature 3) ──
        # We use a manual loop instead of @tenacity.retry because the
        # correction prompt changes on each attempt.
        current_prompt = user_prompt
        for attempt in range(3):
            try:
                # Feature 18: OpenTelemetry Tracking
                with track_ai_call(model_name, operation="generate") as ai_span:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=current_prompt,
                        config=genai_types.GenerateContentConfig(
                            system_instruction=_ANALYSIS_SYSTEM_PROMPT,
                            response_mime_type="application/json",
                            response_schema=AIReportResponse,
                            temperature=0.7,
                        ),
                    )

                    raw_content = response.text
                    parsed = _parse_ai_response(raw_content)

                    print(f"[Gemini] Generation complete with {model_name} (attempt {attempt + 1}).", flush=True)

                    # Extract token usage
                    usage = response.usage_metadata
                    prompt_tokens: int = getattr(usage, "prompt_token_count", 0) or 0
                    completion_tokens: int = getattr(usage, "candidates_token_count", 0) or 0
                    total_tokens: int = (
                        getattr(usage, "total_token_count", 0)
                        or (prompt_tokens + completion_tokens)
                    )
                    
                    # Record actual tokens to the telemetry span (Feature 18)
                    ai_span.set_tokens(input_tokens=prompt_tokens, output_tokens=completion_tokens)

                # Cost estimate
                if "2.0" in model_name:
                    estimated_cost = (prompt_tokens * 0.0000001) + (completion_tokens * 0.0000004)
                else:
                    estimated_cost = (prompt_tokens * 0.000000075) + (completion_tokens * 0.0000003)

                return (
                    parsed.report.model_dump(),
                    parsed.markdown,
                    total_tokens,
                    estimated_cost,
                    model_name,
                )

            except SelfHealParseError as heal_err:
                if attempt < 2:
                    # ── SELF-HEAL: inject broken output + schema into correction prompt ──
                    print(
                        f"[Gemini] Self-heal attempt {attempt + 1}/3 for {model_name}: "
                        f"{heal_err.validation_error[:100]}",
                        flush=True,
                    )
                    current_prompt = _SELF_HEAL_PROMPT_TEMPLATE.format(
                        broken_output=heal_err.broken_output,
                        error_message=heal_err.validation_error,
                        schema=json.dumps(AIReportResponse.model_json_schema(), indent=2),
                    )
                    continue
                else:
                    last_error = heal_err
                    break  # All 3 self-heal attempts exhausted for this model

            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "resource_exhausted" in error_str:
                    print(f"[Gemini] {model_name} rate limited (429). Trying next model...", flush=True)
                    last_error = e
                    break  # Break inner loop, try next model
                else:
                    print(f"[Gemini] Generation failed with {model_name}: {e}", flush=True)
                    raise

    # If all models and all self-heal attempts fail
    raise last_error or RuntimeError("All Gemini models exhausted.")


# =====================================================================
# GROQ REPORT GENERATION (with self-heal)
#
# Feature 1 prerequisite: Groq provides the "speed" model in the
# multi-model consensus engine. Uses Llama 3.1 70B Versatile.
#
# Feature 3: Same self-heal pattern as Gemini — inject broken output +
# schema into a correction prompt on validation failure.
# =====================================================================

def generate_groq_report(
    idea_description: str,
    competitor_data: str,
    grounding_context: str = "",
) -> Tuple[Dict[str, Any], str, int, float, str]:
    """
    Calls Groq (Llama 3.1 70B) with strict JSON output + self-heal.

    Args:
        idea_description: The startup idea to analyze.
        competitor_data: Raw Firecrawl output (competitor summaries).
        grounding_context: RAG-retrieved chunks for grounding (Feature 2).

    Returns:
        Tuple of (report_json, markdown_report, total_tokens, estimated_cost, model_name).
    """
    client = _get_groq()
    model_name = "llama-3.3-70b-versatile"

    # Build user prompt with optional RAG grounding
    user_prompt_parts = [f"Startup Idea: {idea_description}"]
    if grounding_context:
        user_prompt_parts.append(
            f"\n\n--- RAG-GROUNDED CONTEXT (verified competitor data) ---\n{grounding_context}"
        )
    user_prompt_parts.append(f"\n\nLive Competitor Data:\n{competitor_data}")
    user_prompt = "\n".join(user_prompt_parts)

    # ── Self-heal retry loop (Feature 3) ──
    current_user_prompt = user_prompt
    last_error: Exception | None = None

    for attempt in range(3):
        try:
            print(f"[Groq] Generation starting with {model_name} (attempt {attempt + 1})...", flush=True)

            # Feature 18: OpenTelemetry Tracking
            with track_ai_call(model_name, operation="generate") as ai_span:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": _ANALYSIS_SYSTEM_PROMPT},
                        {"role": "user", "content": current_user_prompt},
                    ],
                    temperature=0.7,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )

                raw_content = response.choices[0].message.content
                parsed = _parse_ai_response(raw_content)

                print(f"[Groq] Generation complete with {model_name} (attempt {attempt + 1}).", flush=True)

                # Extract token usage
                usage = response.usage
                prompt_tokens: int = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens: int = getattr(usage, "completion_tokens", 0) or 0
                total_tokens: int = getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)

                # Record actual tokens to the telemetry span (Feature 18)
                ai_span.set_tokens(input_tokens=prompt_tokens, output_tokens=completion_tokens)

            # Groq free tier: effectively $0 cost, but we track for accounting
            estimated_cost = 0.0

            return (
                parsed.report.model_dump(),
                parsed.markdown,
                total_tokens,
                estimated_cost,
                model_name,
            )

        except SelfHealParseError as heal_err:
            if attempt < 2:
                print(
                    f"[Groq] Self-heal attempt {attempt + 1}/3: "
                    f"{heal_err.validation_error[:100]}",
                    flush=True,
                )
                current_user_prompt = _SELF_HEAL_PROMPT_TEMPLATE.format(
                    broken_output=heal_err.broken_output,
                    error_message=heal_err.validation_error,
                    schema=json.dumps(AIReportResponse.model_json_schema(), indent=2),
                )
                continue
            else:
                last_error = heal_err

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate_limit" in error_str:
                print(f"[Groq] Rate limited. Attempt {attempt + 1}/3.", flush=True)
                last_error = e
                # For rate limits, don't self-heal — just raise to let Celery retry
                if attempt == 2:
                    raise
                import time
                time.sleep(2 ** attempt)  # Brief backoff within the self-heal loop
                current_user_prompt = user_prompt  # Reset to original prompt
                continue
            else:
                print(f"[Groq] Generation failed: {e}", flush=True)
                raise

    raise last_error or RuntimeError("All Groq self-heal attempts exhausted.")


# =====================================================================
# BACKWARD COMPATIBILITY ALIASES
#
# The existing celery_tasks.py imports these names. We keep them as
# thin wrappers so the old code doesn't break during the transition.
# They will be removed once celery_tasks.py is fully rewritten.
# =====================================================================

def get_idea_embedding(text: str) -> List[float]:
    """Legacy alias for embed_text(). Delegates to the new 768-dim function."""
    return embed_text(text)


def generate_ai_report(
    idea_description: str,
    competitor_data: str,
) -> Tuple[Dict[str, Any], str, int, float, str]:
    """Legacy alias for generate_gemini_report(). No RAG grounding."""
    return generate_gemini_report(idea_description, competitor_data)