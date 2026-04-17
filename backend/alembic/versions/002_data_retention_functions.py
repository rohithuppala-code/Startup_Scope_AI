"""Add data retention cleanup functions

Revision ID: 002
Revises: 001
Create Date: 2024-01-15 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create cleanup function for old alerts (90 days retention)
    op.execute("""
        CREATE OR REPLACE FUNCTION cleanup_old_alerts()
        RETURNS void AS $$
        BEGIN
            DELETE FROM competitor_alerts
            WHERE created_at < NOW() - INTERVAL '90 days';
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create cleanup function for old sentiment trends (365 days retention)
    op.execute("""
        CREATE OR REPLACE FUNCTION cleanup_old_sentiment()
        RETURNS void AS $$
        BEGIN
            DELETE FROM sentiment_trends
            WHERE created_at < NOW() - INTERVAL '365 days';
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Drop cleanup functions
    op.execute("DROP FUNCTION IF EXISTS cleanup_old_sentiment();")
    op.execute("DROP FUNCTION IF EXISTS cleanup_old_alerts();")
