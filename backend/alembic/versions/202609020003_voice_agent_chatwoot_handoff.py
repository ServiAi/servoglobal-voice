"""voice agent chatwoot handoff

Revision ID: 202609020003
Revises: 202609020002
Create Date: 2026-09-02 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202609020003"
down_revision = "202609020002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_voice_agent_configs",
        sa.Column("handoff_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "tenant_voice_agent_configs",
        sa.Column("handoff_chatwoot_inbox_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tenant_voice_agent_configs",
        sa.Column("handoff_chatwoot_team_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tenant_voice_agent_configs",
        sa.Column("handoff_triggers", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "tenant_voice_agent_configs",
        sa.Column("handoff_lead_score_threshold", sa.Integer(), nullable=False, server_default="80"),
    )


def downgrade() -> None:
    op.drop_column("tenant_voice_agent_configs", "handoff_lead_score_threshold")
    op.drop_column("tenant_voice_agent_configs", "handoff_triggers")
    op.drop_column("tenant_voice_agent_configs", "handoff_chatwoot_team_id")
    op.drop_column("tenant_voice_agent_configs", "handoff_chatwoot_inbox_id")
    op.drop_column("tenant_voice_agent_configs", "handoff_enabled")
