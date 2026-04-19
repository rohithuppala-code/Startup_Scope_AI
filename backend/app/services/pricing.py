# pricing.py
# ---------------------------------------------------------------------------
# FEATURE 5: Pricing Intelligence Pipeline
#
# For each competitor URL discovered by Firecrawl, this module:
#   1. Appends `/pricing` to the URL and crawls the pricing page.
#   2. Passes the raw page content to Gemini with a structured extraction
#      prompt that returns {tier_name, price, features[]} per tier.
#   3. Runs a cross-competitor gap analysis via Gemini.
#   4. Stores everything in the `pricing_intelligence` table.
#
# DESIGN: Uses the self-heal pattern from Feature 3. If Gemini returns
# malformed pricing data, it retries with the broken output + schema.
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib.parse import urlparse

from app.core.config import settings
from app.services.ai_pipeline import _get_firecrawl, _get_gemini, SelfHealParseError
from app.schemas.ai_reports import CompetitorPricing, PricingTier, PricingIntelligenceReport
from google.genai import types as genai_types


# =====================================================================
# STEP 1: CRAWL PRICING PAGES
#
# Takes competitor URLs from Firecrawl's initial search results and
# attempts to crawl their /pricing pages. Falls back to the base URL
# if /pricing returns nothing.
# =====================================================================

def _build_pricing_url(base_url: str) -> str:
    """
    Constructs a pricing page URL from a base competitor URL.

    Handles edge cases:
      - URLs ending with / → append 'pricing'
      - URLs not ending with / → append '/pricing'
      - URLs already containing '/pricing' → return as-is
    """
    parsed = urlparse(base_url)
    path = parsed.path.rstrip("/")

    if "pricing" in path.lower():
        return base_url

    return f"{parsed.scheme}://{parsed.netloc}{path}/pricing"


def scrape_pricing_pages(competitor_urls: List[str]) -> List[Dict[str, Any]]:
    """
    Crawls the /pricing page for each competitor URL.

    Args:
        competitor_urls: List of competitor base URLs from Firecrawl search.

    Returns:
        List of dicts with keys: {url, pricing_url, content, competitor_name}.
        Only includes URLs where content was successfully scraped.
    """
    if not competitor_urls:
        return []

    firecrawl = _get_firecrawl()
    results: List[Dict[str, Any]] = []

    for base_url in competitor_urls[:5]:  # Cap at 5 competitors to stay within rate limits
        pricing_url = _build_pricing_url(base_url)
        parsed = urlparse(base_url)
        competitor_name = parsed.netloc.replace("www.", "")

        try:
            print(f"[Pricing] Crawling: {pricing_url}", flush=True)

            # Use Firecrawl's scrape_url to get the pricing page content
            response = firecrawl.scrape_url(
                url=pricing_url,
                params={"formats": ["markdown"]},
            )

            # Extract markdown content from the response
            content = ""
            if hasattr(response, "markdown") and response.markdown:
                content = response.markdown
            elif isinstance(response, dict):
                content = response.get("markdown", "") or response.get("content", "")

            if content and len(content) > 100:
                results.append({
                    "url": base_url,
                    "pricing_url": pricing_url,
                    "content": content[:5000],  # Cap content to save tokens
                    "competitor_name": competitor_name,
                })
                print(f"[Pricing] Got {len(content)} chars from {competitor_name}", flush=True)
            else:
                print(f"[Pricing] No meaningful content from {pricing_url}", flush=True)

        except Exception as e:
            print(f"[Pricing] Failed to crawl {pricing_url}: {e}", flush=True)
            continue

    print(f"[Pricing] Successfully scraped {len(results)}/{len(competitor_urls)} pricing pages.", flush=True)
    return results


# =====================================================================
# STEP 2: EXTRACT STRUCTURED PRICING DATA
#
# Uses Gemini with structured output to extract pricing tiers from
# raw page content. Applies self-heal on malformed output.
# =====================================================================

_PRICING_EXTRACTION_PROMPT = (
    "Extract ALL pricing tiers from the following webpage content.\n\n"
    "For each tier, provide:\n"
    "- tier_name: The name of the tier (e.g., 'Free', 'Pro', 'Enterprise')\n"
    "- price: The price string exactly as shown (e.g., '$29/mo', 'Custom', 'Free')\n"
    "- billing_period: 'monthly', 'yearly', 'one-time', or 'custom'\n"
    "- features: List of features included in this tier\n\n"
    "Also determine:\n"
    "- has_free_tier: true if there's a free tier\n"
    "- has_enterprise_tier: true if there's an enterprise/custom tier\n\n"
    "Output valid JSON matching this schema:\n"
    "{\n"
    '  "pricing_tiers": [{...}],\n'
    '  "has_free_tier": boolean,\n'
    '  "has_enterprise_tier": boolean\n'
    "}\n\n"
    "If no pricing information is found, return an empty pricing_tiers array."
)


def extract_pricing(
    page_content: str,
    competitor_name: str,
    competitor_url: str = "",
) -> CompetitorPricing:
    """
    Extracts structured pricing data from a raw pricing page.

    Uses Gemini with self-heal retry (up to 3 attempts).

    Args:
        page_content: Raw markdown content of the pricing page.
        competitor_name: Name of the competitor.
        competitor_url: Original competitor URL.

    Returns:
        CompetitorPricing with extracted tiers.
    """
    client = _get_gemini()

    user_prompt = (
        f"Competitor: {competitor_name}\n"
        f"URL: {competitor_url}\n\n"
        f"--- PAGE CONTENT ---\n{page_content}"
    )

    # Self-heal retry loop
    current_prompt = user_prompt
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=current_prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_PRICING_EXTRACTION_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.3,  # Low temp for extraction accuracy
                ),
            )

            raw = response.text
            data = json.loads(raw)

            # Parse individual tiers
            tiers = []
            for tier_data in data.get("pricing_tiers", []):
                try:
                    tiers.append(PricingTier.model_validate(tier_data))
                except Exception:
                    continue  # Skip malformed individual tiers

            return CompetitorPricing(
                competitor_name=competitor_name,
                competitor_url=competitor_url,
                pricing_tiers=tiers,
                has_free_tier=data.get("has_free_tier", False),
                has_enterprise_tier=data.get("has_enterprise_tier", False),
            )

        except (json.JSONDecodeError, Exception) as e:
            if attempt < 2:
                print(f"[Pricing] Self-heal attempt {attempt + 1}/3 for {competitor_name}: {e}", flush=True)
                current_prompt = (
                    f"Your previous extraction was malformed: {str(e)[:200]}\n\n"
                    f"Please re-extract pricing from this content:\n{page_content[:3000]}"
                )
                continue
            else:
                print(f"[Pricing] Extraction failed for {competitor_name} after 3 attempts: {e}", flush=True)
                return CompetitorPricing(
                    competitor_name=competitor_name,
                    competitor_url=competitor_url,
                )

    return CompetitorPricing(competitor_name=competitor_name, competitor_url=competitor_url)


# =====================================================================
# STEP 3: CROSS-COMPETITOR GAP ANALYSIS
#
# Passes all extracted pricing data to Gemini for a gap analysis:
# - Where is the market underpriced?
# - Where is there room for a new tier?
# - What features are missing across all competitors?
# =====================================================================

def analyze_pricing_gaps(all_pricing: List[CompetitorPricing]) -> str:
    """
    Runs a Gemini-powered gap analysis across all competitor pricing.

    Args:
        all_pricing: List of CompetitorPricing objects.

    Returns:
        Markdown string with the gap analysis.
    """
    if not all_pricing:
        return "No pricing data available for gap analysis."

    client = _get_gemini()

    # Build a structured summary of all pricing data
    pricing_summary = []
    for cp in all_pricing:
        tiers_str = "\n".join(
            f"  - {t.tier_name}: {t.price} ({t.billing_period}) — {len(t.features)} features"
            for t in cp.pricing_tiers
        ) or "  No tiers found"

        pricing_summary.append(
            f"**{cp.competitor_name}** ({cp.competitor_url})\n"
            f"  Free tier: {'Yes' if cp.has_free_tier else 'No'}\n"
            f"  Enterprise: {'Yes' if cp.has_enterprise_tier else 'No'}\n"
            f"{tiers_str}"
        )

    system_prompt = (
        "You are a pricing strategy analyst. Analyze the competitor pricing "
        "data below and provide a detailed gap analysis in markdown format.\n\n"
        "Cover:\n"
        "1. Price positioning gaps (underserved price points)\n"
        "2. Feature gaps across tiers\n"
        "3. Billing model opportunities\n"
        "4. Recommended pricing strategy for a new entrant\n"
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Competitor Pricing Data:\n\n" + "\n\n".join(pricing_summary),
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.5,
            ),
        )
        return response.text or "Gap analysis generation failed."
    except Exception as e:
        print(f"[Pricing] Gap analysis failed: {e}", flush=True)
        return f"Gap analysis unavailable: {e}"


# =====================================================================
# ORCHESTRATOR: Run the full pricing intelligence pipeline
# =====================================================================

def run_pricing_pipeline(
    competitor_urls: List[str],
    validation_id: str,
) -> PricingIntelligenceReport:
    """
    Full pricing intelligence pipeline:
      1. Crawl /pricing pages for each competitor.
      2. Extract structured pricing tiers.
      3. Run cross-competitor gap analysis.
      4. Store results in Supabase.

    Args:
        competitor_urls: URLs discovered by Firecrawl.
        validation_id: The validation this pipeline is part of.

    Returns:
        PricingIntelligenceReport with all extracted data.
    """
    print(f"[Pricing] Starting pipeline for {len(competitor_urls)} competitors.", flush=True)

    # Step 1: Crawl
    scraped_pages = scrape_pricing_pages(competitor_urls)

    # Step 2: Extract
    all_pricing: List[CompetitorPricing] = []
    for page in scraped_pages:
        pricing = extract_pricing(
            page_content=page["content"],
            competitor_name=page["competitor_name"],
            competitor_url=page["url"],
        )
        if pricing.pricing_tiers:  # Only include competitors with actual pricing data
            all_pricing.append(pricing)

    # Step 3: Gap analysis
    gap_analysis = analyze_pricing_gaps(all_pricing) if all_pricing else ""

    report = PricingIntelligenceReport(
        competitors=all_pricing,
        gap_analysis=gap_analysis,
    )

    # Step 4: Store in Supabase
    _store_pricing_data(validation_id, all_pricing, gap_analysis)

    print(
        f"[Pricing] Pipeline complete: {len(all_pricing)} competitors with pricing data.",
        flush=True,
    )
    return report


def _store_pricing_data(
    validation_id: str,
    pricing_data: List[CompetitorPricing],
    gap_analysis: str,
) -> None:
    """Persists pricing intelligence to Supabase."""
    from app.services.rag import _get_supabase
    supabase = _get_supabase()

    for cp in pricing_data:
        try:
            supabase.table("pricing_intelligence").insert({
                "validation_id": validation_id,
                "competitor_name": cp.competitor_name,
                "competitor_url": cp.competitor_url,
                "pricing_tiers": [t.model_dump() for t in cp.pricing_tiers],
                "gap_analysis": gap_analysis,
            }).execute()
        except Exception as e:
            print(f"[Pricing] Failed to store data for {cp.competitor_name}: {e}", flush=True)
