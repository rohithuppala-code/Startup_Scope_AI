"""Analytics API Router for dashboard endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime

from .database import get_db
from .validation_service import ValidationService

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# Response Models
class ValidationEntryResponse(BaseModel):
    """Validation entry response model."""
    validation_id: str
    user_id: str
    timestamp: datetime
    idea_description: str
    target_market: str
    business_model: str
    budget_constraints: str
    feasibility_score: float
    identified_gaps: List[str]
    suggested_improvements: List[str]
    competitor_analysis: str
    
    class Config:
        from_attributes = True


class TimelineResponse(BaseModel):
    """Timeline response model."""
    validations: List[ValidationEntryResponse]
    total_count: int
    has_more: bool


class SummaryStatsResponse(BaseModel):
    """Summary statistics response model."""
    total_validations: int


# Timeline Endpoints
@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    user_id: str = Query(..., description="User identifier"),
    limit: int = Query(50, ge=1, le=100, description="Maximum entries to return"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get validation timeline for a user.
    
    Returns validation history in reverse chronological order with pagination.
    """
    if not user_id or len(user_id.strip()) == 0:
        raise HTTPException(status_code=400, detail="Invalid user_id format")
    
    try:
        service = ValidationService(db)
        validations = await service.get_timeline(user_id, limit, offset)
        
        # Convert to response models
        validation_responses = [
            ValidationEntryResponse(
                validation_id=str(v.validation_id),
                user_id=v.user_id,
                timestamp=v.timestamp,
                idea_description=v.idea_description,
                target_market=v.target_market or "",
                business_model=v.business_model or "",
                budget_constraints=v.budget_constraints or "",
                feasibility_score=float(v.feasibility_score),
                identified_gaps=v.identified_gaps or [],
                suggested_improvements=v.suggested_improvements or [],
                competitor_analysis=v.competitor_analysis or ""
            )
            for v in validations
        ]
        
        return TimelineResponse(
            validations=validation_responses,
            total_count=len(validation_responses),
            has_more=len(validation_responses) == limit
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve timeline: {str(e)}")


@router.get("/timeline/{validation_id}", response_model=ValidationEntryResponse)
async def get_validation_detail(
    validation_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information for a specific validation.
    """
    try:
        service = ValidationService(db)
        validation = await service.get_validation_detail(validation_id)
        
        if not validation:
            raise HTTPException(status_code=404, detail="Validation not found")
        
        return ValidationEntryResponse(
            validation_id=str(validation.validation_id),
            user_id=validation.user_id,
            timestamp=validation.timestamp,
            idea_description=validation.idea_description,
            target_market=validation.target_market or "",
            business_model=validation.business_model or "",
            budget_constraints=validation.budget_constraints or "",
            feasibility_score=float(validation.feasibility_score),
            identified_gaps=validation.identified_gaps or [],
            suggested_improvements=validation.suggested_improvements or [],
            competitor_analysis=validation.competitor_analysis or ""
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve validation: {str(e)}")


@router.get("/summary", response_model=SummaryStatsResponse)
async def get_summary_stats(
    user_id: str = Query(..., description="User identifier"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get summary statistics for dashboard.
    """
    if not user_id or len(user_id.strip()) == 0:
        raise HTTPException(status_code=400, detail="Invalid user_id format")
    
    try:
        service = ValidationService(db)
        stats = await service.get_summary_stats(user_id)
        
        return SummaryStatsResponse(
            total_validations=stats["total_validations"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve summary: {str(e)}")
