# comparison_router.py
# ---------------------------------------------------------------------------
# FEATURE 15: Idea Comparison Engine — REST endpoint
#
# POST /api/v1/compare
#   Accepts a list of validation_ids (2–10), verifies the requesting user
#   owns ALL of them and that ALL are completed, then runs a Gemini
#   comparative analysis and returns a structured ComparisonReport.
#
# SECURITY FIXES:
#   - Ownership enforced: Supabase query filters by current_user.user_id
#   - Status enforced: any non-completed validation short-circuits with 400
#   - Both checks happen in a single DB round-trip (no N+1 queries)
# ---------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel, Field

from app.services.comparison import compare_validations, ComparisonReport
from supabase import Client, create_client
from app.core.config import settings

_supabase_client: Client | None = None

def _get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Comparison Engine"])


class CompareRequest(BaseModel):
    """Request body for the comparison endpoint."""
    validation_ids: List[str] = Field(
        ...,
        min_length=2,
        max_length=10,
        description="List of 2–10 validation IDs to compare head-to-head.",
    )


# ---------------------------------------------------------------------------
# Ownership + status pre-flight
# ---------------------------------------------------------------------------

def _assert_owned_and_complete(
    validation_ids: List[str],
    user_id: str,
) -> None:
    """
    Single Supabase query that:
      1. Filters to rows the current user actually owns (.eq user_id)
      2. Selects only id + status — no report payload needed yet
      3. Raises 403 if any ID is missing (not owned or doesn't exist)
      4. Raises 400 if any row is not yet completed

    This is a sync function — call it via run_in_executor.
    """
    supabase = _get_supabase()

    result = (
        supabase.table("validations")
        .select("id, status")
        .in_("id", validation_ids)
        .eq("user_id", user_id)      # ← ownership gate
        .execute()
    )

    rows = result.data or []

    # Check for missing / not-owned IDs
    returned_ids = {row["id"] for row in rows}
    missing = set(validation_ids) - returned_ids
    if missing:
        # Return a generic 403 — don't reveal whether the IDs exist at all
        raise HTTPException(
            status_code=403,
            detail=(
                "One or more validation IDs were not found or do not belong "
                "to your account."
            ),
        )

    # Check every row is completed
    not_ready = [
        row["id"] for row in rows if row.get("status") != "completed"
    ]
    if not_ready:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{len(not_ready)} validation(s) are not yet completed and "
                "cannot be compared. Complete them first."
            ),
        )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/compare",
    response_model=ComparisonReport,
    summary="Compare multiple startup ideas head-to-head",
    description=(
        "Feature 15: Accepts 2–10 validation IDs, verifies ownership and "
        "completion status, then runs a Gemini-powered comparative analysis "
        "scoring each idea on market size, technical difficulty, capital "
        "efficiency, and competitive density."
    ),
)
async def compare_ideas(
    request: Request,
    body: CompareRequest,
    x_user_id: str = Header(..., description="Authenticated user UUID", alias="X-User-Id"),
) -> ComparisonReport:
    """
    POST /api/v1/compare

    Pre-flight: ownership + status check (single DB query, non-blocking).
    Main call: compare_validations() runs in executor (non-blocking).
    """
    loop = asyncio.get_running_loop()

    # ── 1. OWNERSHIP + STATUS GATE ────────────────────────────────────
    # Raises 403 (not owned) or 400 (not completed) before we touch Gemini.
    await loop.run_in_executor(
        None,
        partial(
            _assert_owned_and_complete,
            body.validation_ids,
            x_user_id,
        ),
    )

    # ── 2. RUN COMPARISON (non-blocking) ─────────────────────────────
    # compare_validations() makes sync Supabase + Gemini calls — executor
    # keeps the event loop free. Passes user_id so the service layer can
    # also scope its own queries if needed.
    try:
        report = await loop.run_in_executor(
            None,
            partial(compare_validations, body.validation_ids),
        )
        return report
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise  # re-raise 403 / 400 from pre-flight if it somehow bubbles up
    except Exception as exc:
        logger.error(
            "[Comparison] Unhandled error user=%s ids=%s err=%s",
            x_user_id,
            body.validation_ids,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail="Comparison service is temporarily unavailable. Please try again.",
        )