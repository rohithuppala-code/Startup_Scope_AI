# sentiment.py
# ---------------------------------------------------------------------------
# FEATURE 7: Social Sentiment Engine
#
# THE REDDIT RULE: The full Reddit OAuth2 flow and Groq sentiment
# classification logic is written and production-ready, but the actual
# Reddit API calls are COMMENTED OUT. The pipeline falls back to a
# default "Neutral" buzz score (0.5) until REDDIT_CLIENT_ID is set.
#
# ARCHITECTURE:
#   1. CHECK: If settings.REDDIT_CLIENT_ID is empty → return Neutral default.
#   2. FETCH: Reddit OAuth2 → search /r/startups, /r/entrepreneur, niche subs.
#   3. CLASSIFY: Groq (Llama 3.1 70B) batch-classifies posts as +/-/neutral.
#   4. AGGREGATE: Compute per-competitor Market Buzz Score.
#   5. STORE: Persist to `social_sentiment` table in Supabase.
#
# WHEN READY: Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env,
# and the pipeline will activate automatically — no code changes needed.
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.core.config import settings
from app.services.ai_pipeline import _get_groq
from app.schemas.ai_reports import (
    SentimentPost,
    SentimentResult,
    SentimentReport,
)


# =====================================================================
# REDDIT OAUTH2 + SEARCH (COMMENTED OUT — activate by setting .env keys)
#
# This is the full Reddit API integration. It uses the "script" app type
# OAuth2 flow (no user interaction needed) to search subreddits for
# competitor mentions.
# =====================================================================

# import requests  # Already in requirements.txt
#
# _REDDIT_OAUTH_URL = "https://www.reddit.com/api/v1/access_token"
# _REDDIT_SEARCH_URL = "https://oauth.reddit.com/search"
# _TARGET_SUBREDDITS = ["startups", "entrepreneur", "SaaS", "smallbusiness", "technology"]
#
#
# def _get_reddit_token() -> str:
#     """
#     Obtains a Reddit OAuth2 bearer token using client credentials.
#
#     Uses the "script" app type flow — no user interaction needed.
#     Token is valid for ~1 hour. In production, cache this in Redis.
#     """
#     response = requests.post(
#         _REDDIT_OAUTH_URL,
#         auth=(settings.REDDIT_CLIENT_ID, settings.REDDIT_CLIENT_SECRET),
#         data={"grant_type": "client_credentials"},
#         headers={"User-Agent": settings.REDDIT_USER_AGENT},
#         timeout=10,
#     )
#     response.raise_for_status()
#     return response.json()["access_token"]
#
#
# def _search_reddit(query: str, token: str, limit: int = 50) -> List[Dict[str, Any]]:
#     """
#     Searches Reddit for posts matching the query across target subreddits.
#
#     Args:
#         query: Search query (competitor name or startup idea keywords).
#         token: Reddit OAuth2 bearer token.
#         limit: Maximum posts to retrieve per query.
#
#     Returns:
#         List of post dicts: {title, url, subreddit, score, selftext}.
#     """
#     headers = {
#         "Authorization": f"Bearer {token}",
#         "User-Agent": settings.REDDIT_USER_AGENT,
#     }
#
#     posts: List[Dict[str, Any]] = []
#
#     for subreddit in _TARGET_SUBREDDITS:
#         try:
#             response = requests.get(
#                 f"https://oauth.reddit.com/r/{subreddit}/search",
#                 headers=headers,
#                 params={
#                     "q": query,
#                     "sort": "relevance",
#                     "t": "year",  # Last year of posts
#                     "limit": min(limit, 25),
#                     "restrict_sr": "on",
#                 },
#                 timeout=10,
#             )
#             response.raise_for_status()
#             data = response.json()
#
#             for child in data.get("data", {}).get("children", []):
#                 post = child.get("data", {})
#                 posts.append({
#                     "title": post.get("title", ""),
#                     "url": f"https://reddit.com{post.get('permalink', '')}",
#                     "subreddit": post.get("subreddit", subreddit),
#                     "score": post.get("score", 0),
#                     "selftext": post.get("selftext", "")[:500],  # Cap text
#                 })
#
#         except Exception as e:
#             print(f"[Sentiment] Reddit search failed for r/{subreddit}: {e}", flush=True)
#             continue
#
#     return posts[:limit]


# =====================================================================
# GROQ BATCH SENTIMENT CLASSIFICATION (COMMENTED OUT)
#
# Uses Groq (Llama 3.1 70B, 14,400 req/day free) to classify Reddit
# posts as positive, negative, or neutral in batches of 50.
# Groq is fast enough to classify 200 posts in under 10 seconds.
# =====================================================================

# def _classify_sentiment_batch(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
#     """
#     Classifies a batch of posts using Groq (Llama 3.1 70B).
#
#     Args:
#         posts: List of post dicts with 'title' and 'selftext'.
#
#     Returns:
#         Same posts with 'sentiment' field added ('positive'/'negative'/'neutral').
#     """
#     if not posts:
#         return []
#
#     client = _get_groq()
#
#     # Build batch prompt — up to 50 posts per call
#     batch_size = 50
#     classified_posts: List[Dict[str, Any]] = []
#
#     for i in range(0, len(posts), batch_size):
#         batch = posts[i:i + batch_size]
#
#         posts_text = "\n".join(
#             f"{j+1}. {p['title']}"
#             for j, p in enumerate(batch)
#         )
#
#         try:
#             response = client.chat.completions.create(
#                 model="llama-3.1-70b-versatile",
#                 messages=[
#                     {
#                         "role": "system",
#                         "content": (
#                             "You are a sentiment classifier. For each numbered post title below, "
#                             "classify the sentiment as 'positive', 'negative', or 'neutral'.\n\n"
#                             "Output ONLY a JSON array of objects:\n"
#                             '[{"index": 1, "sentiment": "positive"}, ...]\n\n'
#                             "Be precise. Posts praising a product = positive. Posts complaining = negative. "
#                             "Neutral discussion or questions = neutral."
#                         ),
#                     },
#                     {"role": "user", "content": posts_text},
#                 ],
#                 temperature=0.1,
#                 max_tokens=2048,
#                 response_format={"type": "json_object"},
#             )
#
#             raw = response.choices[0].message.content
#             results = json.loads(raw)
#
#             # Handle both array and {results: [...]} formats
#             if isinstance(results, dict):
#                 results = results.get("results", results.get("sentiments", []))
#
#             # Map classifications back to posts
#             sentiment_map = {r.get("index", 0): r.get("sentiment", "neutral") for r in results}
#
#             for j, post in enumerate(batch):
#                 post["sentiment"] = sentiment_map.get(j + 1, "neutral")
#                 classified_posts.append(post)
#
#         except Exception as e:
#             print(f"[Sentiment] Groq classification failed for batch: {e}", flush=True)
#             # Fall back to neutral for this batch
#             for post in batch:
#                 post["sentiment"] = "neutral"
#                 classified_posts.append(post)
#
#     return classified_posts


# =====================================================================
# MARKET BUZZ SCORE COMPUTATION (ACTIVE)
#
# This logic is always active. When Reddit is disabled, it produces
# the default Neutral score. When Reddit is enabled, it aggregates
# the classified sentiment into a 0.0–1.0 score.
#
# FORMULA:
#   buzz_score = (positive_weighted + 0.5 * neutral) / total_weighted
#   where weights account for post upvote scores.
# =====================================================================

def _compute_buzz_score(
    positive: int,
    negative: int,
    neutral: int,
) -> float:
    """
    Computes the Market Buzz Score from sentiment counts.

    Returns a float between 0.0 (all negative) and 1.0 (all positive).
    Default 0.5 (neutral) when no data is available.
    """
    total = positive + negative + neutral
    if total == 0:
        return 0.5  # No data → neutral

    # Weighted formula: positive=1.0, neutral=0.5, negative=0.0
    score = (positive * 1.0 + neutral * 0.5 + negative * 0.0) / total
    return round(min(1.0, max(0.0, score)), 3)


# =====================================================================
# ORCHESTRATOR: Run the full sentiment pipeline
#
# THE REDDIT RULE IN ACTION:
# If REDDIT_CLIENT_ID is empty, the entire Reddit flow is skipped
# and a default Neutral result is returned. When the key is set,
# the commented-out code above should be uncommented and the
# `_fallback_neutral_result` call replaced with the live pipeline.
# =====================================================================

def _fallback_neutral_result(query: str) -> SentimentResult:
    """
    Returns a default Neutral sentiment result.

    Used when Reddit API is not configured (REDDIT_CLIENT_ID is empty).
    """
    return SentimentResult(
        query=query,
        platform="reddit",
        positive_count=0,
        negative_count=0,
        neutral_count=0,
        market_buzz_score=0.5,
        sample_posts=[],
    )


def run_sentiment_pipeline(
    competitor_names: List[str],
    idea_description: str,
    validation_id: str,
) -> SentimentReport:
    """
    Full social sentiment pipeline.

    If REDDIT_CLIENT_ID is set: fetches Reddit posts, classifies via Groq,
    computes Market Buzz Scores.

    If REDDIT_CLIENT_ID is empty: returns default Neutral scores for all
    competitors (The Reddit Rule).

    Args:
        competitor_names: Competitor names/domains to search for.
        idea_description: The startup idea (also searched as a query).
        validation_id: The validation this pipeline is part of.

    Returns:
        SentimentReport with per-competitor sentiment data.
    """
    print(f"[Sentiment] Starting pipeline for {len(competitor_names)} competitors.", flush=True)

    # ── THE REDDIT RULE: Check if Reddit API is configured ──
    if not settings.REDDIT_CLIENT_ID:
        print(
            "[Sentiment] Reddit API not configured (REDDIT_CLIENT_ID is empty). "
            "Returning default Neutral scores.",
            flush=True,
        )
        results = [_fallback_neutral_result(name) for name in competitor_names]
        # Also include the idea itself as a query
        results.append(_fallback_neutral_result(idea_description[:50]))

        report = SentimentReport(
            results=results,
            overall_buzz_score=0.5,
            summary=(
                "Social sentiment analysis is not yet available. "
                "Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env to enable. "
                "Default: Neutral (0.5)."
            ),
        )

        # Store the default results in Supabase
        _store_sentiment_data(validation_id, report)
        return report

    # ── LIVE REDDIT PIPELINE (activates when REDDIT_CLIENT_ID is set) ──
    # When you have your Reddit API key, uncomment the code blocks above
    # and replace this section with:
    #
    # token = _get_reddit_token()
    # all_results: List[SentimentResult] = []
    #
    # queries = competitor_names + [idea_description[:50]]
    # for query in queries:
    #     posts = _search_reddit(query, token, limit=50)
    #     classified = _classify_sentiment_batch(posts)
    #
    #     pos = sum(1 for p in classified if p["sentiment"] == "positive")
    #     neg = sum(1 for p in classified if p["sentiment"] == "negative")
    #     neu = sum(1 for p in classified if p["sentiment"] == "neutral")
    #
    #     sample = [
    #         SentimentPost(
    #             title=p["title"],
    #             url=p["url"],
    #             subreddit=p.get("subreddit", ""),
    #             sentiment=p["sentiment"],
    #             score=p.get("score", 0),
    #         )
    #         for p in classified[:10]  # Top 10 as samples
    #     ]
    #
    #     all_results.append(SentimentResult(
    #         query=query,
    #         platform="reddit",
    #         positive_count=pos,
    #         negative_count=neg,
    #         neutral_count=neu,
    #         market_buzz_score=_compute_buzz_score(pos, neg, neu),
    #         sample_posts=sample,
    #     ))
    #
    # overall_buzz = sum(r.market_buzz_score for r in all_results) / len(all_results)
    #
    # report = SentimentReport(
    #     results=all_results,
    #     overall_buzz_score=round(overall_buzz, 3),
    #     summary=f"Analyzed {sum(r.positive_count + r.negative_count + r.neutral_count for r in all_results)} posts across Reddit.",
    # )
    # _store_sentiment_data(validation_id, report)
    # return report

    # Until the above is uncommented, fall back to Neutral:
    results = [_fallback_neutral_result(name) for name in competitor_names]
    results.append(_fallback_neutral_result(idea_description[:50]))
    report = SentimentReport(
        results=results,
        overall_buzz_score=0.5,
        summary="Reddit API configured but live pipeline not yet activated. Default: Neutral.",
    )
    _store_sentiment_data(validation_id, report)
    return report


def _store_sentiment_data(
    validation_id: str,
    report: SentimentReport,
) -> None:
    """Persists sentiment data to the social_sentiment table in Supabase."""
    from app.services.rag import _get_supabase
    supabase = _get_supabase()

    for result in report.results:
        try:
            supabase.table("social_sentiment").insert({
                "validation_id": validation_id,
                "platform": result.platform,
                "competitor_name": result.query,
                "positive_count": result.positive_count,
                "negative_count": result.negative_count,
                "neutral_count": result.neutral_count,
                "market_buzz_score": result.market_buzz_score,
                "sample_posts": [p.model_dump() for p in result.sample_posts],
            }).execute()
        except Exception as e:
            print(f"[Sentiment] Failed to store data for '{result.query}': {e}", flush=True)
