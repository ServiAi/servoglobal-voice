"""Add explicit production/QA purpose to voice sessions.

Revision ID: 202609230001
Revises: 202609220001
"""

from alembic import op
import sqlalchemy as sa


revision = "202609230001"
down_revision = "202609220001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "voice_sessions",
        sa.Column("purpose", sa.String(24), nullable=False, server_default="production"),
    )
    op.create_check_constraint(
        "ck_voice_sessions_purpose",
        "voice_sessions",
        "purpose IN ('production','qa')",
    )
    op.alter_column("voice_sessions", "purpose", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_voice_sessions_purpose", "voice_sessions", type_="check")
    op.drop_column("voice_sessions", "purpose")
