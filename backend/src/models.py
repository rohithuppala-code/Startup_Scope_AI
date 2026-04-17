"""Database models for Advanced Analytics Dashboard."""
from datetime import datetime
from typing import List
from sqlalchemy import (
    Column, String, Text, DECIMAL, TIMESTAMP, Boolean, 
    ForeignKey, Index, CheckConstraint, UUID
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
import uuid

from .database import Base


class ValidationEntry(Base):
    """Validation history table."""
    __tablename__ = "validation_entries"
    
    validation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False)
    timestamp = Column(TIMESTAMP, nullable=False, default=func.now())
    idea_description = Column(Text, nullable=False)
    target_market = Column(String(255))
    business_model = Column(String(255))
    budget_constraints = Column(String(255))
    feasibility_score = Column(DECIMAL(5, 2), nullable=False)
    competitor_analysis = Column(Text)
    identified_gaps = Column(JSONB)  # Array of strings
    suggested_improvements = Column(JSONB)  # Array of strings
    created_at = Column(TIMESTAMP, nullable=False, default=func.now())
    
    __table_args__ = (
        Index('idx_user_timestamp', 'user_id', timestamp.desc()),
        Index('idx_timestamp', timestamp.desc()),
    )


class CompetitorSnapshot(Base):
    """Competitor snapshots table."""
    __tablename__ = "competitor_snapshots"
    
    competitor_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False)
    competitor_url = Column(String(1024), nullable=False)
    competitor_name = Column(String(255), nullable=False)
    initial_content_hash = Column(String(64), nullable=False)
    current_content_hash = Column(String(64), nullable=False)
    pricing_data = Column(Text)
    features_list = Column(JSONB)  # Array of strings
    last_scraped_timestamp = Column(TIMESTAMP, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, nullable=False, default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_user_active', 'user_id', 'is_active'),
        Index('idx_last_scraped', 'last_scraped_timestamp'),
        Index('idx_user_url_unique', 'user_id', 'competitor_url', unique=True),
    )


class CompetitorAlert(Base):
    """Competitor alerts table."""
    __tablename__ = "competitor_alerts"
    
    alert_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(
        UUID(as_uuid=True), 
        ForeignKey('competitor_snapshots.competitor_id', ondelete='CASCADE'),
        nullable=False
    )
    user_id = Column(String(255), nullable=False)
    change_timestamp = Column(TIMESTAMP, nullable=False, default=func.now())
    change_summary = Column(Text, nullable=False)
    alert_status = Column(String(20), nullable=False, default='unread')
    created_at = Column(TIMESTAMP, nullable=False, default=func.now())
    
    __table_args__ = (
        Index('idx_user_status', 'user_id', 'alert_status'),
        Index('idx_user_timestamp', 'user_id', change_timestamp.desc()),
        CheckConstraint("alert_status IN ('unread', 'read')", name='check_alert_status'),
    )


class SentimentTrend(Base):
    """Sentiment trends table."""
    __tablename__ = "sentiment_trends"
    
    sentiment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_url = Column(String(1024), nullable=False)
    timestamp = Column(TIMESTAMP, nullable=False, default=func.now())
    sentiment_score = Column(DECIMAL(3, 2), nullable=False)
    tone = Column(String(50))
    messaging_focus = Column(String(100))
    confidence_level = Column(String(20))
    created_at = Column(TIMESTAMP, nullable=False, default=func.now())
    
    __table_args__ = (
        Index('idx_competitor_timestamp', 'competitor_url', timestamp.desc()),
        Index('idx_timestamp', timestamp.desc()),
        CheckConstraint(
            "sentiment_score >= -1.0 AND sentiment_score <= 1.0", 
            name='check_sentiment_bounds'
        ),
        CheckConstraint(
            "confidence_level IN ('high', 'medium', 'low')", 
            name='check_confidence_level'
        ),
    )
