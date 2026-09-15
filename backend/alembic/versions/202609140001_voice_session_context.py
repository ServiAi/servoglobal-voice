"""add VoiceSession.session_context_json for Session Context V1

Revision ID: 202609140001
Revises: 202609120001
"""

import sqlalchemy as sa
from alembic import op

revision = "202609140001"
down_revision = "202609120001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("voice_sessions", sa.Column("session_context_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("voice_sessions", "session_context_json")
