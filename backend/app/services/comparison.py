# comparison.py
# ---------------------------------------------------------------------------
# FEATURE 15: Idea Comparison Engine
#
# Accepts a list of validation_ids, fetches their completed reports,
# and passes all of them to Gemini with a structured prompt to generate
# a comparative matrix scoring each idea against the others on:
#
#   - Market Size Potential (0–100)
#   - Technical Difficulty (0–100, lower = easier)
#   - Capital Efficiency (0–100, higher = cheaper to launch)
#   - Competitive Density (0–100, lower = less competition)
#   - Overall Recommendation Score (weighted composite)
#
# OUTPUT: A ComparisonReport with:
#   - Per-idea scores (ComparisonRow)
#   - Head-to-head winner for each dimension
#   - Gemini's strategic narrative comparing all ideas
#
# DESIGN: This is a one-shot Gemini call. We don't use Groq here because
# comparison requires deep reasoning over multiple contexts — Gemini's
# strength. The self-heal pattern from Feature 3 is applied.
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.services.ai_pipeline import _get_gemini, SelfHealParseError
from app.schemas.ai_reports import ReportDetails
from google.genai import types as genai_types
from supabase import create_client, Client

from app.core.config import settings


# =====================================================================
# SCHEMAS
# =====================================================================

class ComparisonRow(BaseModel):
    """Scores for a single idea in the comparison matrix."""
    validation_id: str
    idea_summary: str = Field(default="", description="1-sentence idea summary.")
    market_size: int = Field(ge=0, le=100, description="Market size potential score.")
    technical_difficulty: int = Field(ge=0, le=100, description="Technical difficulty (lower = easier).")
    capital_efficiency: int = Field(ge=0, le=100, description="Capital efficiency (higher = cheaper).")
    competitive_density: int = Field(ge=0, le=100, description="Competitive density (lower = less competition).")
    overall_score: int = Field(ge=0, le=100, description="Weighted composite recommendation score.")


class DimensionWinner(BaseModel):
    """Head-to-head winner for a specific dimension."""
    dimension: str
    winner_id: str
    winner_summary: str = ""
    reasoning: str = ""


class ComparisonReport(BaseModel):
    """Complete comparison output across all submitted ideas."""
    ideas: List[ComparisonRow] = Field(default_factory=list)
    winners: List[DimensionWinner] = Field(default_factory=list)
    narrative: str = Field(
        default="",
        description="Gemini's strategic comparison narrative in markdown.",
    )
    recommendation: str = Field(
        default="",
        description="Which idea Gemini recommends pursuing and why.",
    )


# =====================================================================
# SUPABASE CLIENT
# =====================================================================
_supabase: Client | None = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase


# =====================================================================
# STEP 1: FETCH REPORTS
# =====================================================================

def _fetch_reports(validation_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Fetches completed reports for all given validation IDs.

    Returns a list of dicts with: {validation_id, idea_description, report_json, ...}.
    Skips validations that are not completed.
    """
    supabase = _get_supabase()
    reports: List[Dict[str, Any]] = []

    for v_id in validation_ids:
        try:
            result = (
                supabase.table("validations")
                .select(
                    "id, idea_description, report_json, consensus_confidence, "
                    "pricing_data, funding_data, patent_data, traffic_data, status"
                )
                .eq("id", v_id)
                .single()
                .execute()
            )
            if result.data and result.data.get("status") == "completed":
                reports.append(result.data)
            else:
                print(f"[Comparison] Skipping {v_id}: not completed.", flush=True)
        except Exception as e:
            print(f"[Comparison] Failed to fetch {v_id}: {e}", flush=True)

    return reports


# =====================================================================
# STEP 2: GEMINI COMPARATIVE ANALYSIS
# =====================================================================

_COMPARISON_SYSTEM_PROMPT = (
    "You are a strategic startup advisor comparing multiple startup ideas.\n\n"
    "For EACH idea, score it on these dimensions (0–100):\n"
    "1. market_size: How large is the addressable market?\n"
    "2. technical_difficulty: How hard is this to build? (100 = extremely hard)\n"
    "3. capital_efficiency: How cheaply can this be launched? (100 = very cheap)\n"
    "4. competitive_density: How crowded is the market? (100 = very crowded)\n"
    "5. overall_score: Your weighted recommendation (consider all factors)\n\n"
    "Output valid JSON matching this EXACT schema:\n"
    "{\n"
    '  "ideas": [\n'
    "    {\n"
    '      "validation_id": "uuid",\n'
    '      "idea_summary": "one-sentence summary",\n'
    '      "market_size": 75,\n'
    '      "technical_difficulty": 60,\n'
    '      "capital_efficiency": 80,\n'
    '      "competitive_density": 45,\n'
    '      "overall_score": 72\n'
    "    }\n"
    "  ],\n"
    '  "winners": [\n'
    '    {"dimension": "market_size", "winner_id": "uuid", "winner_summary": "...", "reasoning": "..."}\n'
    "  ],\n"
    '  "narrative": "multi-paragraph markdown comparison",\n'
    '  "recommendation": "which idea to pursue and why"\n'
    "}\n\n"
    "Be rigorous. Use data from the reports. Don't inflate scores."
)


def _run_comparison(reports: List[Dict[str, Any]]) -> ComparisonReport:
    """
    Passes all reports to Gemini for comparative scoring.

    Uses self-heal retry (3 attempts) on malformed output.
    """
    client = _get_gemini()

    # Build the comparison prompt with all reports
    ideas_text_parts = []
    for i, report in enumerate(reports):
        v_id = report.get("id", "unknown")
        idea = report.get("idea_description", "No description")
        report_json = report.get("report_json", {})
        confidence = report.get("consensus_confidence")

        # Include key data points for richer comparison
        pricing_summary = ""
        pricing_data = report.get("pricing_data")
        if pricing_data and isinstance(pricing_data, dict):
            competitors = pricing_data.get("competitors", [])
            pricing_summary = f"\n  Competitor pricing: {len(competitors)} competitors analyzed"

        patent_summary = ""
        patent_data = report.get("patent_data")
        if patent_data and isinstance(patent_data, dict):
            patent_count = patent_data.get("total_found", 0)
            patent_summary = f"\n  Patents in space: {patent_count}"

        ideas_text_parts.append(
            f"### Idea {i + 1} (validation_id: {v_id})\n"
            f"Description: {idea}\n"
            f"Feasibility Score: {report_json.get('feasibility_score', 'N/A')}\n"
            f"Market Viability: {report_json.get('market_viability', 'N/A')}\n"
            f"Gaps: {report_json.get('gaps_identified', [])}\n"
            f"Approach: {report_json.get('recommended_approach', 'N/A')}\n"
            f"Consensus Confidence: {confidence or 'N/A'}"
            f"{pricing_summary}{patent_summary}"
        )

    user_prompt = (
        f"Compare these {len(reports)} startup ideas head-to-head:\n\n"
        + "\n\n---\n\n".join(ideas_text_parts)
    )

    # Self-heal retry loop
    current_prompt = user_prompt
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=current_prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_COMPARISON_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.5,
                ),
            )

            raw = response.text
            data = json.loads(raw)

            # Parse into schema
            ideas = []
            for idea_data in data.get("ideas", []):
                try:
                    ideas.append(ComparisonRow.model_validate(idea_data))
                except Exception:
                    continue

            winners = []
            for w_data in data.get("winners", []):
                try:
                    winners.append(DimensionWinner.model_validate(w_data))
                except Exception:
                    continue

            report = ComparisonReport(
                ideas=ideas,
                winners=winners,
                narrative=data.get("narrative", ""),
                recommendation=data.get("recommendation", ""),
            )

            print(
                f"[Comparison] Generated comparison for {len(ideas)} ideas.",
                flush=True,
            )
            return report

        except Exception as e:
            if attempt < 2:
                print(f"[Comparison] Self-heal attempt {attempt + 1}/3: {e}", flush=True)
                current_prompt = (
                    f"Your previous comparison output was malformed: {str(e)[:200]}\n\n"
                    f"Re-generate the comparison for these ideas:\n{user_prompt[:4000]}"
                )
                continue
            print(f"[Comparison] Comparison failed after 3 attempts: {e}", flush=True)
            return ComparisonReport(
                narrative=f"Comparison generation failed: {e}",
                recommendation="Unable to generate recommendation due to an error.",
            )

    return ComparisonReport()


# =====================================================================
# ORCHESTRATOR
# =====================================================================

def compare_validations(validation_ids: List[str]) -> ComparisonReport:
    """
    Complete idea comparison pipeline:
      1. Fetch completed reports for all validation IDs.
      2. Pass to Gemini for comparative scoring.
      3. Return structured ComparisonReport.

    Args:
        validation_ids: List of 2–10 validation IDs to compare.

    Returns:
        ComparisonReport with per-idea scores, dimension winners,
        narrative, and recommendation.

    Raises:
        ValueError: If fewer than 2 completed validations are found.
    """
    if len(validation_ids) < 2:
        raise ValueError("At least 2 validation IDs are required for comparison.")
    if len(validation_ids) > 10:
        raise ValueError("Maximum 10 ideas can be compared at once.")

    print(f"[Comparison] Starting comparison of {len(validation_ids)} ideas.", flush=True)

    # Step 1: Fetch
    reports = _fetch_reports(validation_ids)

    if len(reports) < 2:
        raise ValueError(
            f"Only {len(reports)} completed validations found. "
            f"Need at least 2 for comparison."
        )

    # Step 2: Compare
    comparison = _run_comparison(reports)

    print(f"[Comparison] Complete. Recommendation: {comparison.recommendation[:100]}", flush=True)
    return comparison
