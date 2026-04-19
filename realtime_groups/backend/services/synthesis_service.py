# realtime_groups/backend/services/synthesis_service.py
# ---------------------------------------------------------------------------
# Thread Synthesis Service — Gemini 2.0 Flash (google-genai SDK)
# ---------------------------------------------------------------------------

import json
import logging
from typing import Any

from google import genai
from google.genai import types

from realtime_groups.backend.core.config import social_settings
from realtime_groups.backend.core.supabase_client import get_supabase

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """You are an elite startup strategy analyst.
You have been given ALL community comments on a founder's idea in the Validation Arena.
Synthesize them into a structured strategic brief.

Return a JSON object with EXACTLY these fields:
- summary: string (3-5 sentence executive summary of community sentiment)
- key_themes: list of strings (top 3-5 recurring themes)
- sentiment_breakdown: object with keys "positive", "negative", "neutral" (ints summing to 100)
- founder_takeaways: list of 3 actionable strings
- most_upvoted_criticism: string
- strongest_validation: string

Respond ONLY with valid JSON. No markdown, no preamble."""


def synthesize_thread(post_id: str) -> dict[str, Any]:
    """
    Fetches all visible comments for a post and generates a Gemini synthesis.
    Raises ValueError if post not found or has no visible comments.
    Raises RuntimeError if the Gemini API call fails.
    """
    sb = get_supabase()

    # 1. Fetch post metadata
    post_resp = (
        sb.table("posts")
        .select("id, title, report_json")
        .eq("id", post_id)
        .single()
        .execute()
    )
    if not post_resp.data:
        raise ValueError(f"Post {post_id} not found.")

    post = post_resp.data

    # 2. Fetch all visible comments
    comments_resp = (
        sb.table("comments")
        .select("content, upvote_count, author_id, created_at")
        .eq("post_id", post_id)
        .eq("is_hidden", False)
        .order("upvote_count", desc=True)
        .execute()
    )

    comments = comments_resp.data or []
    if not comments:
        raise ValueError(f"Post {post_id} has no visible comments to synthesize.")

    # 3. Format thread for Gemini
    formatted = "\n".join(
        f"[Upvotes: {c.get('upvote_count', 0)}] {c.get('content', '').strip()}"
        for c in comments
    )
    user_prompt = (
        f"Post Title: {post.get('title', 'Untitled Idea')}\n"
        f"Total Comments: {len(comments)}\n\n"
        f"--- BEGIN COMMENTS ---\n{formatted}\n--- END COMMENTS ---\n\n"
        "Generate the strategic synthesis JSON now."
    )

    # 4. Gemini 2.0 Flash API call via new google-genai SDK
    try:
        client = genai.Client(api_key=social_settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYNTHESIS_SYSTEM_PROMPT,
                temperature=0.3,
                response_mime_type="application/json",
            ),
        )
        raw_json = response.text
    except Exception as gemini_err:
        logger.error("[Synthesis] Gemini API call failed for post=%s: %s", post_id, gemini_err)
        raise RuntimeError(f"Synthesis AI unavailable: {gemini_err}") from gemini_err

    # 5. Parse and return
    try:
        synthesis = json.loads(raw_json)
    except json.JSONDecodeError as e:
        logger.error("[Synthesis] Malformed JSON from Gemini for post=%s: %s | raw=%s", post_id, e, raw_json[:200])
        raise RuntimeError("Synthesis AI returned malformed JSON.") from e

    logger.info("[Synthesis] Completed for post=%s with %d comments.", post_id, len(comments))

    return {
        "post_id": post_id,
        "summary": synthesis.get("summary", ""),
        "comment_count": len(comments),
        "key_themes": synthesis.get("key_themes", []),
        "sentiment_breakdown": synthesis.get("sentiment_breakdown", {}),
        "founder_takeaways": synthesis.get("founder_takeaways", []),
        "most_upvoted_criticism": synthesis.get("most_upvoted_criticism", ""),
        "strongest_validation": synthesis.get("strongest_validation", ""),
    }
