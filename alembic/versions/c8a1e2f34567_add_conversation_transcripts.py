"""add_conversation_transcripts

Revision ID: c8a1e2f34567
Revises: 2b8806bd7f12
Create Date: 2024-12-18 23:30:00.000000

"""
from typing import Sequence, Union
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite
from phone_agent.db.base import UUIDType

# revision identifiers, used by Alembic.
revision: str = 'c8a1e2f34567'
down_revision: Union[str, Sequence[str], None] = '2b8806bd7f12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create conversation_transcripts table."""
    op.create_table('conversation_transcripts',
        # Primary key
        sa.Column('id', UUIDType(), nullable=False),

        # Session identification
        sa.Column('session_id', sa.String(length=100), nullable=False, comment='Voice demo session ID'),

        # Language
        sa.Column('language', sa.String(length=10), nullable=False, server_default='de', comment='Primary language: de, ru, tr, en'),

        # Conversation content
        sa.Column('turns_json', sqlite.JSON(), nullable=False, comment='Conversation turns: [{role, content, timestamp, language}, ...]'),

        # AI-detected information
        sa.Column('urgency_detected', sa.String(length=20), nullable=True, comment='Detected urgency: notfall, dringend, normal, routine'),
        sa.Column('trade_detected', sa.String(length=20), nullable=True, server_default='elektro', comment='Detected trade category'),

        # Metadata
        sa.Column('turn_count', sa.Integer(), nullable=False, server_default='0', comment='Number of conversation turns'),
        sa.Column('duration_seconds', sa.Integer(), nullable=True, comment='Total conversation duration'),

        # Extracted content
        sa.Column('summary', sa.Text(), nullable=True, comment='AI-generated conversation summary'),
        sa.Column('problem_description', sa.Text(), nullable=True, comment='Extracted problem description for job'),

        # Foreign keys
        sa.Column('job_id', UUIDType(), nullable=True, comment='Linked job created from this conversation'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('session_id'),
    )

    # Create indexes
    op.create_index('ix_transcripts_session_id', 'conversation_transcripts', ['session_id'])
    op.create_index('ix_transcripts_job_id', 'conversation_transcripts', ['job_id'])
    op.create_index('ix_transcripts_created', 'conversation_transcripts', ['created_at'])
    op.create_index('ix_transcripts_urgency', 'conversation_transcripts', ['urgency_detected'])


def downgrade() -> None:
    """Drop conversation_transcripts table."""
    op.drop_index('ix_transcripts_urgency', 'conversation_transcripts')
    op.drop_index('ix_transcripts_created', 'conversation_transcripts')
    op.drop_index('ix_transcripts_job_id', 'conversation_transcripts')
    op.drop_index('ix_transcripts_session_id', 'conversation_transcripts')
    op.drop_table('conversation_transcripts')
