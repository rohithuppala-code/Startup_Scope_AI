# funding.py
# ---------------------------------------------------------------------------
# FEATURE 6: Funding Intelligence Pipeline
#
# Discovers competitor funding data from FREE public sources:
#   1. TechCrunch.com/tag/funding — every funding round is published publicly.
#   2. YC company directory (ycombinator.com/companies) — public JSON.
#   3. Tracxn/Dealroom public company pages (if accessible via Firecrawl).
#
# NO Crunchbase key needed. All data comes from Firecrawl (already in stack)
# + Gemini structured extraction (free tier).
#
# PIPELINE:
#   1. SEARCH: Use Firecrawl to search for "{competitor} funding round"
#   2. EXTRACT: Gemini extracts structured funding data from raw content.
#   3. SYNTHESIZE: Gemini generates a funding landscape summary.
#   4. STORE: Persist to `funding_intelligence` table in Supabase.
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.core.config import settings
from app.services.ai_pipeline import _get_firecrawl, _get_gemini
from app.schemas.ai_reports import (
    CompetitorFunding,
    FundingRound,
    FundingIntelligenceReport,
)
from google.genai import types as genai_types


# =====================================================================
# STEP 1: SEARCH FOR FUNDING DATA
#
# Uses Firecrawl to search for public funding information. Targets
# TechCrunch funding articles and YC company pages — both are fully
# public and scrapeable without any API key.
# =====================================================================

def search_funding_data(competitor_names: List[str]) -> List[Dict[str, Any]]:
    """
    Searches for public funding data for each competitor.

    Args:
        competitor_names: List of competitor names/domains to search for.

    Returns:
        List of dicts: {competitor_name, search_results_text, source_urls}.
    """
    if not competitor_names:
        return []

    firecrawl = _get_firecrawl()
    results: List[Dict[str, Any]] = []

    for name in competitor_names[:5]:  # Cap at 5 to respect rate limits
        # Clean the name — strip TLDs and www
        clean_name = name.replace("www.", "").split(".")[0]

        search_query = f"{clean_name} startup funding round raised"

        try:
            print(f"[Funding] Searching: {search_query}", flush=True)
            response = firecrawl.search(query=search_query, limit=3)

            search_text_parts: List[str] = []
            source_urls: List[str] = []

            # Extract results from response
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
                        source_urls.append(url)
                    if title or desc:
                        search_text_parts.append(f"Title: {title}\nSnippet: {desc}\nURL: {url}")

            if search_text_parts:
                results.append({
                    "competitor_name": clean_name,
                    "search_results_text": "\n\n".join(search_text_parts),
                    "source_urls": source_urls,
                })
                print(f"[Funding] Found {len(search_text_parts)} results for {clean_name}", flush=True)

        except Exception as e:
            print(f"[Funding] Search failed for {clean_name}: {e}", flush=True)
            continue

    return results


# =====================================================================
# STEP 2: EXTRACT STRUCTURED FUNDING DATA
#
# Gemini extracts funding rounds, amounts, dates, and investors
# from the raw search results. Self-heal retry on malformed output.
# =====================================================================

_FUNDING_EXTRACTION_PROMPT = (
    "Extract funding information from the following search results about a startup.\n\n"
    "For each funding round found, provide:\n"
    "- round_type: e.g., 'Pre-Seed', 'Seed', 'Series A', 'Series B', etc.\n"
    "- amount: The amount raised (e.g., '$5M', '$10M', 'Undisclosed')\n"
    "- date: When the round occurred (YYYY-MM format if known, else 'Unknown')\n"
    "- investors: List of known investors\n\n"
    "Also provide:\n"
    "- total_funding: Estimated total funding across all rounds\n"
    "- last_round_date: Date of the most recent round\n\n"
    "Output valid JSON:\n"
    "{\n"
    '  "funding_rounds": [{...}],\n'
    '  "total_funding": "string",\n'
    '  "last_round_date": "string"\n'
    "}\n\n"
    "If no funding information is found, return empty arrays and 'Unknown' values."
)


def extract_funding(
    search_results_text: str,
    competitor_name: str,
    source_urls: List[str],
) -> CompetitorFunding:
    """
    Extracts structured funding data from search results.

    Args:
        search_results_text: Raw text from Firecrawl search results.
        competitor_name: Name of the competitor.
        source_urls: List of source URLs where data was found.

    Returns:
        CompetitorFunding with extracted rounds.
    """
    client = _get_gemini()

    user_prompt = (
        f"Competitor: {competitor_name}\n\n"
        f"--- SEARCH RESULTS ---\n{search_results_text}"
    )

    current_prompt = user_prompt
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=current_prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_FUNDING_EXTRACTION_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.3,
                ),
            )

            raw = response.text
            data = json.loads(raw)

            rounds = []
            for round_data in data.get("funding_rounds", []):
                try:
                    rounds.append(FundingRound.model_validate(round_data))
                except Exception:
                    continue

            return CompetitorFunding(
                competitor_name=competitor_name,
                funding_rounds=rounds,
                total_funding=data.get("total_funding", "Unknown"),
                last_round_date=data.get("last_round_date", "Unknown"),
                source_url=source_urls[0] if source_urls else "",
            )

        except (json.JSONDecodeError, Exception) as e:
            if attempt < 2:
                print(f"[Funding] Self-heal attempt {attempt + 1}/3 for {competitor_name}: {e}", flush=True)
                current_prompt = (
                    f"Your previous extraction was malformed: {str(e)[:200]}\n\n"
                    f"Please re-extract funding data:\n{search_results_text[:3000]}"
                )
                continue
            else:
                print(f"[Funding] Extraction failed for {competitor_name}: {e}", flush=True)
                return CompetitorFunding(competitor_name=competitor_name)

    return CompetitorFunding(competitor_name=competitor_name)


# =====================================================================
# STEP 3: SYNTHESIZE FUNDING LANDSCAPE
# =====================================================================

def synthesize_funding_landscape(all_funding: List[CompetitorFunding]) -> str:
    """
    Generates a Gemini-powered summary of the overall funding landscape.

    Returns markdown analysis covering:
      - Total capital in the market
      - Most active investors
      - Stage distribution (Seed vs. Series A vs. later)
      - Funding velocity trends
    """
    if not all_funding:
        return "No funding data available for landscape analysis."

    client = _get_gemini()

    summary_parts = []
    for cf in all_funding:
        rounds_str = ", ".join(
            f"{r.round_type}: {r.amount} ({r.date})" for r in cf.funding_rounds
        ) or "No rounds found"
        summary_parts.append(
            f"**{cf.competitor_name}**: Total: {cf.total_funding}. "
            f"Rounds: {rounds_str}"
        )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=(
                "Analyze this competitive funding landscape and provide insights:\n\n"
                + "\n".join(summary_parts)
            ),
            config=genai_types.GenerateContentConfig(
                system_instruction=(
                    "You are a venture capital analyst. Analyze the funding data "
                    "and provide a concise markdown report on the competitive funding "
                    "landscape. Cover: total market capital, investor patterns, stage "
                    "distribution, and what this means for a new entrant."
                ),
                temperature=0.5,
            ),
        )
        return response.text or "Landscape synthesis failed."
    except Exception as e:
        print(f"[Funding] Landscape synthesis failed: {e}", flush=True)
        return f"Funding landscape analysis unavailable: {e}"


# =====================================================================
# ORCHESTRATOR: Run the full funding intelligence pipeline
# =====================================================================

def run_funding_pipeline(
    competitor_names: List[str],
    validation_id: str,
) -> FundingIntelligenceReport:
    """
    Full funding intelligence pipeline:
      1. Search for public funding data via Firecrawl.
      2. Extract structured funding rounds via Gemini.
      3. Synthesize landscape summary.
      4. Store results in Supabase.

    Args:
        competitor_names: Competitor names/domains from Firecrawl search.
        validation_id: The validation this pipeline is part of.

    Returns:
        FundingIntelligenceReport with all extracted data.
    """
    print(f"[Funding] Starting pipeline for {len(competitor_names)} competitors.", flush=True)

    # Step 1: Search
    search_results = search_funding_data(competitor_names)

    # Step 2: Extract
    all_funding: List[CompetitorFunding] = []
    for sr in search_results:
        funding = extract_funding(
            search_results_text=sr["search_results_text"],
            competitor_name=sr["competitor_name"],
            source_urls=sr.get("source_urls", []),
        )
        if funding.funding_rounds:
            all_funding.append(funding)

    # Step 3: Synthesize
    landscape = synthesize_funding_landscape(all_funding) if all_funding else ""

    report = FundingIntelligenceReport(
        competitors=all_funding,
        landscape_summary=landscape,
    )

    # Step 4: Store
    _store_funding_data(validation_id, all_funding)

    print(
        f"[Funding] Pipeline complete: {len(all_funding)} competitors with funding data.",
        flush=True,
    )
    return report


def _store_funding_data(
    validation_id: str,
    funding_data: List[CompetitorFunding],
) -> None:
    """Persists funding intelligence to Supabase."""
    from app.services.rag import _get_supabase
    supabase = _get_supabase()

    for cf in funding_data:
        try:
            supabase.table("funding_intelligence").insert({
                "validation_id": validation_id,
                "competitor_name": cf.competitor_name,
                "funding_rounds": [r.model_dump() for r in cf.funding_rounds],
                "total_funding": cf.total_funding,
                "last_round_date": cf.last_round_date,
                "source_url": cf.source_url,
            }).execute()
        except Exception as e:
            print(f"[Funding] Failed to store data for {cf.competitor_name}: {e}", flush=True)
