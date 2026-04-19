# export_router.py
# ---------------------------------------------------------------------------
# FEATURE 13: PDF Export REST endpoint
#
# GET /api/v1/export/{validation_id}/pdf
#   → Generates a professional PDF from the completed validation report
#   → Uploads to Supabase Storage
#   → Returns a signed download URL
#
# This is a synchronous endpoint (not async) because WeasyPrint is CPU-bound.
# For high-traffic deployments, this should be offloaded to a Celery task.
# ---------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.export import export_validation_pdf


router = APIRouter(prefix="/api/v1", tags=["PDF Export"])


class ExportResponse(BaseModel):
    """Response containing the signed download URL for the exported PDF."""
    download_url: str = Field(description="Signed URL to download the PDF (1-hour expiry).")
    validation_id: str


@router.get(
    "/export/{validation_id}/pdf",
    response_model=ExportResponse,
    summary="Export a validation report as a professional PDF",
    description=(
        "Feature 13: Generates a premium dark-mode PDF from the completed "
        "validation report, uploads it to Supabase Storage, and returns a "
        "signed download URL (1-hour expiry)."
    ),
)
async def export_pdf(validation_id: str) -> ExportResponse:
    """
    GET /api/v1/export/{validation_id}/pdf

    Generates and returns a signed download URL for the report PDF.
    """
    try:
        url = export_validation_pdf(validation_id)
        return ExportResponse(
            download_url=url,
            validation_id=validation_id,
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        print(f"[Export] PDF generation failed: {e}", flush=True)
        raise HTTPException(
            status_code=500,
            detail=f"PDF export failed: {str(e)[:200]}",
        )
