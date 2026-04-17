"""Initial schema with validation, competitor, alert, and sentiment tables

Revision ID: 001
Revises: 
Create Date: 2024-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create validation_entries table
    op.create_table(
        'validation_entries',
        sa.Column('validation_id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('timestamp', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.Column('idea_description', sa.Text(), nullable=False),
        sa.Column('target_market', sa.String(length=255), nullable=True),
        sa.Column('business_model', sa.String(length=255), nullable=True),
        sa.Column('budget_constraints', sa.String(length=255), nullable=True),
        sa.Column('feasibility_score', sa.DECIMAL(precision=5, scale=2), nullable=False),
        sa.Column('competitor_analysis', sa.Text(), nullable=True),
        sa.Column('identified_gaps', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('suggested_improvements', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('validation_id')
    )
    op.create_index('idx_user_timestamp', 'validation_entries', ['user_id', sa.text('timestamp DESC')], unique=False)
    op.create_index('idx_timestamp', 'validation_entries', [sa.text('timestamp DESC')], unique=False)

    # Create competitor_snapshots table
    op.create_table(
        'competitor_snapshots',
        sa.Column('competitor_id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('competitor_url', sa.String(length=1024), nullable=False),
        sa.Column('competitor_name', sa.String(length=255), nullable=False),
        sa.Column('initial_content_hash', sa.String(length=64), nullable=False),
        sa.Column('current_content_hash', sa.String(length=64), nullable=False),
        sa.Column('pricing_data', sa.Text(), nullable=True),
        sa.Column('features_list', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_scraped_timestamp', sa.TIMESTAMP(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('competitor_id')
    )
    op.create_index('idx_user_active', 'competitor_snapshots', ['user_id', 'is_active'], unique=False)
    op.create_index('idx_last_scraped', 'competitor_snapshots', ['last_scraped_timestamp'], unique=False)
    op.create_index('idx_user_url_unique', 'competitor_snapshots', ['user_id', 'competitor_url'], unique=True)

    # Create competitor_alerts table
    op.create_table(
        'competitor_alerts',
        sa.Column('alert_id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('competitor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('change_timestamp', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.Column('change_summary', sa.Text(), nullable=False),
        sa.Column('alert_status', sa.String(length=20), nullable=False, server_default=sa.text("'unread'")),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint("alert_status IN ('unread', 'read')", name='check_alert_status'),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitor_snapshots.competitor_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('alert_id')
    )
    op.create_index('idx_user_status', 'competitor_alerts', ['user_id', 'alert_status'], unique=False)
    op.create_index('idx_user_timestamp', 'competitor_alerts', ['user_id', sa.text('change_timestamp DESC')], unique=False)

    # Create sentiment_trends table
    op.create_table(
        'sentiment_trends',
        sa.Column('sentiment_id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('competitor_url', sa.String(length=1024), nullable=False),
        sa.Column('timestamp', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.Column('sentiment_score', sa.DECIMAL(precision=3, scale=2), nullable=False),
        sa.Column('tone', sa.String(length=50), nullable=True),
        sa.Column('messaging_focus', sa.String(length=100), nullable=True),
        sa.Column('confidence_level', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint('sentiment_score >= -1.0 AND sentiment_score <= 1.0', name='check_sentiment_bounds'),
        sa.CheckConstraint("confidence_level IN ('high', 'medium', 'low')", name='check_confidence_level'),
        sa.PrimaryKeyConstraint('sentiment_id')
    )
    op.create_index('idx_competitor_timestamp', 'sentiment_trends', ['competitor_url', sa.text('timestamp DESC')], unique=False)
    op.create_index('idx_timestamp', 'sentiment_trends', [sa.text('timestamp DESC')], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('idx_timestamp', table_name='sentiment_trends')
    op.drop_index('idx_competitor_timestamp', table_name='sentiment_trends')
    op.drop_table('sentiment_trends')
    
    op.drop_index('idx_user_timestamp', table_name='competitor_alerts')
    op.drop_index('idx_user_status', table_name='competitor_alerts')
    op.drop_table('competitor_alerts')
    
    op.drop_index('idx_user_url_unique', table_name='competitor_snapshots')
    op.drop_index('idx_last_scraped', table_name='competitor_snapshots')
    op.drop_index('idx_user_active', table_name='competitor_snapshots')
    op.drop_table('competitor_snapshots')
    
    op.drop_index('idx_timestamp', table_name='validation_entries')
    op.drop_index('idx_user_timestamp', table_name='validation_entries')
    op.drop_table('validation_entries')
