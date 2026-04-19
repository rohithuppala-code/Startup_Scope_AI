# comparison_router.py
# ---------------------------------------------------------------------------
# FEATURE 15: Idea Comparison Engine — REST endpoint
#
# POST /api/v1/compare
#   Accepts a list of validation_ids (2–10), fetches their completed
#   reports, runs Gemini comparative analysis, and returns a structured
#   ComparisonReport with scores, winners, and a recommendation.
# ---------------------------------------------------------------------------

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.comparison import compare_validations, ComparisonReport


router = APIRouter(prefix="/api/v1", tags=["Comparison Engine"])


class CompareRequest(BaseModel):
    """Request body for the comparison endpoint."""
    validation_ids: List[str] = Field(
        ...,
        min_length=2,
        max_length=10,
        description="List of 2–10 validation IDs to compare head-to-head.",
    )


@router.post(
    "/compare",
    response_model=ComparisonReport,
    summary="Compare multiple startup ideas head-to-head",
    description=(
        "Feature 15: Accepts 2–10 validation IDs, fetches their completed "
        "reports, and runs a Gemini-powered comparative analysis scoring "
        "each idea on market size, technical difficulty, capital efficiency, "
        "and competitive density."
    ),
)
async def compare_ideas(request: CompareRequest) -> ComparisonReport:
    """
    POST /api/v1/compare

    Returns a ComparisonReport with per-idea scores, dimension winners,
    strategic narrative, and a recommendation.
    """
    try:
        report = compare_validations(request.validation_ids)
        return report
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(f"[Comparison] Endpoint error: {e}", flush=True)
        raise HTTPException(
            status_code=500,
            detail=f"Comparison failed: {str(e)[:200]}",
        )
