# ai_pipeline.py
import json
from pydantic import BaseModel
from typing import Dict, Any, Tuple, List

from firecrawl import FirecrawlApp
from google import genai
from google.genai import types as genai_types

from app.core.config import settings


# ==========================================
# OUTPUT SCHEMA
# ==========================================

class ReportDetails(BaseModel):
    feasibility_score: int
    market_viability: str
    gaps_identified: List[str]
    recommended_approach: str


class AIResponseSchema(BaseModel):
    report: ReportDetails
    markdown: str


# ==========================================
# MODULE-LEVEL CLIENT SINGLETONS
#
# BUG FIX: Both FirecrawlApp and genai.Client were previously instantiated
# on every call to firecrawl_scrape() and generate_ai_report() respectively.
# Each instantiation creates a new underlying HTTP client with its own
# connection pool, DNS resolution, and TLS handshake overhead. Under any
# meaningful load (multiple Celery workers, concurrent tasks) this wastes
# file descriptors, memory, and wall-clock time on every request.
#
# Moving both to module-level singletons means:
# - One connection pool per worker process (correct — Celery prefork spawns
#   one process per worker, so there's no cross-process sharing issue).
# - Connections are reused across tasks within the same worker process.
# - The API key is read once at module import time (which happens when the
#   Celery worker starts), not on every task execution.
#
# NOTE: These are created lazily via module-level variables rather than
# at import time to allow the settings object to be fully loaded first.
# They are initialised on first use via the _get_*_client() accessors.
# ==========================================

_firecrawl_app: FirecrawlApp | None = None
_gemini_client: genai.Client | None = None


def _get_firecrawl() -> FirecrawlApp:
    """Returns the module-level FirecrawlApp singleton, creating it on first call."""
    global _firecrawl_app
    if _firecrawl_app is None:
        _firecrawl_app = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)
    return _firecrawl_app


def _get_gemini() -> genai.Client:
    """Returns the module-level Gemini client singleton, creating it on first call."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _gemini_client


# ==========================================
# FIRECRAWL
# ==========================================

def firecrawl_scrape(idea_description: str) -> str:
    """
    Uses the Firecrawl Python SDK to search for competitors and alternatives
    for the given startup idea.

    Uses the module-level FirecrawlApp singleton (connection reuse).
    Checks response.data (Firecrawl v1 SDK) with a response.web fallback
    for older SDK versions.
    """
    try:
        app = _get_firecrawl()
        search_query = f"competitors alternatives to {idea_description[:100]}"

        print(f"[Firecrawl] Searching: {search_query}", flush=True)
        response = app.search(query=search_query, limit=5)
        print("[Firecrawl] Search finished.", flush=True)

        competitor_results = []

        # Firecrawl v1 SDK: results in response.data
        # Older SDK: results in response.web
        results_list = None
        if hasattr(response, "data") and response.data:
            results_list = response.data
        elif hasattr(response, "web") and response.web:
            results_list = response.web

        if results_list:
            for result in results_list:
                res_dict = result.model_dump() if hasattr(result, "model_dump") else dict(result)
                url = res_dict.get("url", "")
                title = res_dict.get("title", "")
                desc = res_dict.get("description", "") or res_dict.get("snippet", "")
                if url or title:
                    competitor_results.append(
                        f"Source: {url}\nTitle: {title}\nDescription: {desc}"
                    )

        if not competitor_results:
            return "No competitor data found from live search."

        return "\n\n---\n\n".join(competitor_results)

    except Exception as e:
        print(f"[Firecrawl] API error: {e}", flush=True)
        return "Firecrawl search failed or timed out. Competitor data unavailable."


# ==========================================
# GEMINI AI REPORT GENERATION
# ==========================================

def generate_ai_report(
    idea_description: str,
    competitor_data: str,
) -> Tuple[Dict[str, Any], str, int, float]:
    """
    Calls Gemini 2.0 Flash with a strict Pydantic response schema.
    Falls back to Gemini 1.5 Flash if 2.0 hits rate limits (429).
    """
    client = _get_gemini()

    system_instruction = (
        "You are an elite Startup Analyst. Analyze the provided startup idea and "
        "competitor data. Provide a professional evaluation, market insights, and a "
        "comprehensive markdown report. The 'markdown' field should contain a "
        "high-quality, long-form analysis report."
    )
    user_prompt = (
        f"Startup Idea: {idea_description}\n\nLive Competitor Data:\n{competitor_data}"
    )

    # Models to try in order
    models_to_try = ["gemini-2.0-flash", "gemini-1.5-flash"]
    
    last_error = None
    
    for model_name in models_to_try:
        print(f"[Gemini] Generation starting with {model_name}...", flush=True)
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=AIResponseSchema,
                    temperature=0.7,
                ),
            )
            print(f"[Gemini] Generation finished with {model_name}.", flush=True)

            raw_content = response.text

            try:
                parsed_data = AIResponseSchema.model_validate_json(raw_content)
            except Exception:
                # Fallback for SDK versions that return slightly different JSON wrapping.
                data = json.loads(raw_content)
                parsed_data = AIResponseSchema.model_validate(data)

            report_json = parsed_data.report.model_dump()
            markdown_report = parsed_data.markdown

            usage = response.usage_metadata
            prompt_tokens: int = getattr(usage, "prompt_token_count", 0) or 0
            completion_tokens: int = getattr(usage, "candidates_token_count", 0) or 0
            total_tokens: int = (
                getattr(usage, "total_token_count", 0)
                or (prompt_tokens + completion_tokens)
            )

            # Pricing estimate (simplified)
            if "2.0" in model_name:
                estimated_cost = (prompt_tokens * 0.0000001) + (completion_tokens * 0.0000004)
            else:
                estimated_cost = (prompt_tokens * 0.000000075) + (completion_tokens * 0.0000003)

            return report_json, markdown_report, total_tokens, estimated_cost

        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            if "429" in error_str or "resource_exhausted" in error_str:
                print(f"[Gemini] {model_name} rate limited (429). Trying next model...", flush=True)
                continue
            else:
                print(f"[Gemini] Generation failed with {model_name}: {e}", flush=True)
                raise

    # If all models fail
    raise last_error