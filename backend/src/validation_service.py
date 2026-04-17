"""Validation Service for historical tracking."""
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from .models import ValidationEntry
from .input_parser import StartupIdea, ValidationReport

logger = logging.getLogger(__name__)


class ValidationService:
    """Service for storing and retrieving validation history."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def store_validation(
        self,
        user_id: str,
        idea: StartupIdea,
        report: ValidationReport
    ) -> ValidationEntry:
        """
        Store validation result in database.
        
        Args:
            user_id: User identifier
            idea: Startup idea input
            report: Validation report output
            
        Returns:
            Stored ValidationEntry
        """
        try:
            entry = ValidationEntry(
                user_id=user_id,
                timestamp=datetime.utcnow(),
                idea_description=idea.description,
                target_market=idea.target_market or "",
                business_model=idea.business_model or "",
                budget_constraints=idea.budget_constraints or "",
                feasibility_score=float(report.feasibility_score),
                competitor_analysis=report.competitor_analysis,
                identified_gaps=report.identified_gaps,
                suggested_improvements=report.suggested_improvements
            )
            
            self.db.add(entry)
            await self.db.commit()
            await self.db.refresh(entry)
            
            logger.info(f"Stored validation {entry.validation_id} for user {user_id}")
            return entry
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to store validation for user {user_id}: {e}")
            raise
    
    async def get_timeline(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[ValidationEntry]:
        """
        Retrieve validation history for user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of entries to return (default 50)
            offset: Number of entries to skip (for pagination)
            
        Returns:
            List of ValidationEntry records in reverse chronological order
        """
        try:
            query = (
                select(ValidationEntry)
                .where(ValidationEntry.user_id == user_id)
                .order_by(desc(ValidationEntry.timestamp))
                .limit(limit)
                .offset(offset)
            )
            
            result = await self.db.execute(query)
            entries = result.scalars().all()
            
            logger.info(f"Retrieved {len(entries)} validations for user {user_id}")
            return list(entries)
            
        except Exception as e:
            logger.error(f"Failed to retrieve timeline for user {user_id}: {e}")
            raise
    
    async def get_validation_detail(
        self,
        validation_id: str
    ) -> Optional[ValidationEntry]:
        """
        Get full details of a specific validation.
        
        Args:
            validation_id: Validation identifier
            
        Returns:
            ValidationEntry or None if not found
        """
        try:
            query = select(ValidationEntry).where(
                ValidationEntry.validation_id == validation_id
            )
            
            result = await self.db.execute(query)
            entry = result.scalar_one_or_none()
            
            if entry:
                logger.info(f"Retrieved validation detail {validation_id}")
            else:
                logger.warning(f"Validation {validation_id} not found")
                
            return entry
            
        except Exception as e:
            logger.error(f"Failed to retrieve validation {validation_id}: {e}")
            raise
    
    async def get_summary_stats(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get aggregate statistics for dashboard summary.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dictionary with total_validations count
        """
        try:
            query = select(func.count(ValidationEntry.validation_id)).where(
                ValidationEntry.user_id == user_id
            )
            
            result = await self.db.execute(query)
            total_count = result.scalar() or 0
            
            logger.info(f"Retrieved summary stats for user {user_id}: {total_count} validations")
            
            return {
                "total_validations": total_count
            }
            
        except Exception as e:
            logger.error(f"Failed to retrieve summary stats for user {user_id}: {e}")
            raise
