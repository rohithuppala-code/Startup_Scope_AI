# ai_reports.py
# ---------------------------------------------------------------------------
# SINGLE SOURCE OF TRUTH for every AI output schema in the platform.
#
# Both Gemini and Groq must conform to these exact Pydantic v2 models.
# The self-heal retry loop (Feature 3) injects the .model_json_schema()
# output back into the correction prompt on validation failure.
#
# DESIGN RULE: Every model here uses strict Pydantic v2 validation.
# No `Any` types, no `dict` types — everything is typed to the leaf.
# ---------------------------------------------------------------------------

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


# =====================================================================
# CORE REPORT SCHEMA (used by both Gemini and Groq independently)
# =====================================================================

class ReportDetails(BaseModel):
    """
    The structured analysis section of a startup validation report.
    Both AI providers must output this exact shape.
    """
    feasibility_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="0–100 score indicating how feasible the startup idea is.",
    )
    market_viability: str = Field(
        ...,
        min_length=10,
        description="Detailed assessment of market viability (2–4 sentences).",
    )
    gaps_identified: List[str] = Field(
        ...,
        min_length=1,
        description="List of market gaps or unmet needs the idea could exploit.",
    )
    recommended_approach: str = Field(
        ...,
        min_length=10,
        description="Strategic recommendation for how to pursue the idea.",
    )


class AIReportResponse(BaseModel):
    """
    The complete response expected from each AI model.
    `report` is the structured JSON; `markdown` is the long-form analysis.
    """
    report: ReportDetails
    markdown: str = Field(
        ...,
        min_length=50,
        description="Comprehensive markdown analysis report.",
    )


# =====================================================================
# CONSENSUS SCHEMA (Feature 1 — Multi-Model Merge Output)
# =====================================================================

class FieldConfidence(BaseModel):
    """Per-field agreement metadata from the consensus merge."""
    field_name: str
    gemini_value: str = Field(description="Gemini's raw value (stringified).")
    groq_value: str = Field(description="Groq's raw value (stringified).")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="1.0 = perfect agreement, 0.0 = total divergence.",
    )
    status: str = Field(description="'agreed', 'averaged', or 'divergent'.")


class ConsensusReport(BaseModel):
    """
    The merged output of both AI providers.
    Contains the final report, per-field confidence, and overall score.
    """
    report: ReportDetails
    markdown: str
    overall_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Weighted average of all per-field confidence scores.",
    )
    field_agreement: List[FieldConfidence] = Field(
        description="Per-field comparison between Gemini and Groq outputs.",
    )
    gemini_model: str = Field(default="", description="Gemini model version used.")
    groq_model: str = Field(default="", description="Groq model version used.")


# =====================================================================
# PRICING INTELLIGENCE SCHEMA (Feature 5)
# =====================================================================

class PricingTier(BaseModel):
    """A single pricing tier extracted from a competitor's pricing page."""
    tier_name: str = Field(description="Name of the pricing tier (e.g., 'Pro', 'Enterprise').")
    price: str = Field(description="Price string (e.g., '$29/mo', 'Custom', 'Free').")
    billing_period: str = Field(default="monthly", description="'monthly', 'yearly', 'one-time', 'custom'.")
    features: List[str] = Field(
        default_factory=list,
        description="List of features included in this tier.",
    )


class CompetitorPricing(BaseModel):
    """Pricing data for a single competitor."""
    competitor_name: str
    competitor_url: str = ""
    pricing_tiers: List[PricingTier] = Field(
        default_factory=list,
        description="All pricing tiers found on the competitor's pricing page.",
    )
    has_free_tier: bool = Field(default=False)
    has_enterprise_tier: bool = Field(default=False)


class PricingIntelligenceReport(BaseModel):
    """Aggregated pricing intelligence across all competitors."""
    competitors: List[CompetitorPricing] = Field(default_factory=list)
    gap_analysis: str = Field(
        default="",
        description="Gemini-generated analysis of pricing gaps and opportunities.",
    )


# =====================================================================
# FUNDING INTELLIGENCE SCHEMA (Feature 6)
# =====================================================================

class FundingRound(BaseModel):
    """A single funding round for a competitor."""
    round_type: str = Field(description="e.g., 'Seed', 'Series A', 'Series B'.")
    amount: str = Field(default="Undisclosed", description="e.g., '$5M', 'Undisclosed'.")
    date: str = Field(default="Unknown", description="Date of the round (YYYY-MM or descriptive).")
    investors: List[str] = Field(
        default_factory=list,
        description="List of known investors in this round.",
    )


class CompetitorFunding(BaseModel):
    """Funding data for a single competitor."""
    competitor_name: str
    funding_rounds: List[FundingRound] = Field(default_factory=list)
    total_funding: str = Field(default="Unknown")
    last_round_date: str = Field(default="Unknown")
    source_url: str = Field(default="")


class FundingIntelligenceReport(BaseModel):
    """Aggregated funding intelligence across all competitors."""
    competitors: List[CompetitorFunding] = Field(default_factory=list)
    landscape_summary: str = Field(
        default="",
        description="Gemini-generated summary of the funding landscape.",
    )


# =====================================================================
# SOCIAL SENTIMENT SCHEMA (Feature 7)
# =====================================================================

class SentimentPost(BaseModel):
    """A single social media post with classified sentiment."""
    title: str = Field(default="")
    url: str = Field(default="")
    subreddit: str = Field(default="")
    sentiment: str = Field(
        default="neutral",
        description="'positive', 'negative', or 'neutral'.",
    )
    score: int = Field(default=0, description="Reddit upvote score.")


class SentimentResult(BaseModel):
    """Aggregated sentiment for a single competitor or the idea itself."""
    query: str = Field(description="The search query used.")
    platform: str = Field(default="reddit")
    positive_count: int = Field(default=0)
    negative_count: int = Field(default=0)
    neutral_count: int = Field(default=0)
    market_buzz_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="0.0 = extremely negative, 0.5 = neutral, 1.0 = extremely positive.",
    )
    sample_posts: List[SentimentPost] = Field(default_factory=list)


class SentimentReport(BaseModel):
    """Aggregated sentiment across all queries."""
    results: List[SentimentResult] = Field(default_factory=list)
    overall_buzz_score: float = Field(default=0.5)
    summary: str = Field(default="Sentiment analysis not yet available.")


# =====================================================================
# TEMPORAL TRACKING SCHEMA (Feature 4)
# =====================================================================

class FieldChange(BaseModel):
    """A single field that changed between report versions."""
    field_path: str = Field(description="Dot-notation path, e.g. 'report.feasibility_score'.")
    old_value: str = Field(default="")
    new_value: str = Field(default="")
    change_type: str = Field(description="'value_changed', 'item_added', 'item_removed'.")


class TemporalDiff(BaseModel):
    """Structured diff between two report versions."""
    validation_id: str
    old_version: int
    new_version: int
    changes: List[FieldChange] = Field(default_factory=list)
    change_narrative: str = Field(
        default="",
        description="Gemini-generated natural-language summary of what changed and why.",
    )
    significance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="0.0 = trivial changes, 1.0 = fundamental shift.",
    )


# =====================================================================
# PATENT & IP SCHEMA (Feature 8)
# =====================================================================

class PatentResult(BaseModel):
    """A single patent from USPTO PatentsView."""
    patent_number: str = Field(default="", description="USPTO patent number.")
    title: str = Field(default="", description="Patent title.")
    abstract: str = Field(default="", description="Patent abstract (truncated).")
    filing_date: str = Field(default="", description="Filing or grant date.")
    assignee: str = Field(default="", description="Assignee organization.")
    inventors: List[str] = Field(default_factory=list, description="Inventor names.")
    source: str = Field(default="USPTO PatentsView")
    url: str = Field(default="", description="Link to patent on Google Patents.")


class PatentReport(BaseModel):
    """Aggregated patent/IP intelligence."""
    patents: List[PatentResult] = Field(default_factory=list)
    keywords_searched: List[str] = Field(default_factory=list)
    total_found: int = Field(default=0)
    ip_analysis: str = Field(
        default="",
        description="Gemini-generated IP landscape analysis.",
    )


# =====================================================================
# JOB POSTING SIGNAL SCHEMA (Feature 9)
# =====================================================================

class JobDepartment(BaseModel):
    """Job openings for a single department within a competitor."""
    department: str = Field(default="Other", description="Department name.")
    role_count: int = Field(default=0, description="Number of open roles.")
    sample_titles: List[str] = Field(
        default_factory=list, description="Sample job titles."
    )


class CompetitorJobs(BaseModel):
    """Job posting data for a single competitor."""
    competitor_name: str
    total_open_roles: int = Field(default=0)
    departments: List[JobDepartment] = Field(default_factory=list)
    hiring_velocity: str = Field(
        default="unknown",
        description="'aggressive', 'moderate', 'minimal', or 'unknown'.",
    )
    notable_roles: List[str] = Field(
        default_factory=list,
        description="Notable senior/strategic hires (e.g., 'VP of AI').",
    )


class JobsReport(BaseModel):
    """Aggregated job posting intelligence across competitors."""
    competitors: List[CompetitorJobs] = Field(default_factory=list)
    landscape_analysis: str = Field(
        default="",
        description="Gemini-generated hiring landscape analysis.",
    )


# =====================================================================
# WEB TRAFFIC INTELLIGENCE SCHEMA (Feature 10)
# =====================================================================

class CompetitorTraffic(BaseModel):
    """Web traffic proxy data for a single competitor domain."""
    domain: str = Field(description="Competitor domain (e.g., 'notion.so').")
    total_snapshots: int = Field(
        default=0, description="Total Wayback Machine snapshots."
    )
    yearly_snapshots: dict = Field(
        default_factory=dict,
        description="Snapshots per year: {'2024': 150, '2025': 230}.",
    )
    traffic_tier: str = Field(
        default="Unknown",
        description="'Very High', 'High', 'Medium', 'Low', 'Very Low', 'Unknown'.",
    )
    growth_trend: str = Field(
        default="unknown",
        description="'growing', 'stable', 'declining', or 'unknown'.",
    )
    first_seen: Optional[str] = Field(
        default=None, description="Earliest Wayback snapshot timestamp."
    )
    last_seen: Optional[str] = Field(
        default=None, description="Most recent Wayback snapshot timestamp."
    )
    source: str = Field(default="Wayback Machine CDX API")


class TrafficReport(BaseModel):
    """Aggregated web traffic intelligence across competitors."""
    competitors: List[CompetitorTraffic] = Field(default_factory=list)
    landscape_analysis: str = Field(
        default="",
        description="Gemini-generated traffic landscape analysis.",
    )


# =====================================================================
# ENRICHED VALIDATION RESULT (combines ALL pipeline outputs)
# =====================================================================

class EnrichedValidationResult(BaseModel):
    """
    The complete output of a validation pipeline run, combining:
    - Consensus AI report (Feature 1)
    - Pricing intelligence (Feature 5)
    - Funding intelligence (Feature 6)
    - Social sentiment (Feature 7)
    - Patent/IP scan (Feature 8)
    - Job posting signal (Feature 9)
    - Web traffic intelligence (Feature 10)

    This is what gets stored in Supabase and pushed over WebSocket.
    """
    consensus: Optional[ConsensusReport] = None
    pricing: Optional[PricingIntelligenceReport] = None
    funding: Optional[FundingIntelligenceReport] = None
    sentiment: Optional[SentimentReport] = None
    patents: Optional[PatentReport] = None
    jobs: Optional[JobsReport] = None
    traffic: Optional[TrafficReport] = None
