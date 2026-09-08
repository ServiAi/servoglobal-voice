"""add canonical voice runtime sessions and events

Revision ID: 202609080001
Revises: 202609070001
"""

import sqlalchemy as sa
from alembic import op

revision = "202609080001"
down_revision = "202609070001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("tenant_agents.id"), nullable=False),
        sa.Column("agent_version_id", sa.String(36), sa.ForeignKey("tenant_agent_versions.id"), nullable=False),
        sa.Column("crm_voice_call_id", sa.String(36), sa.ForeignKey("crm_voice_calls.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("direction", sa.String(24), nullable=False),
        sa.Column("runtime_engine", sa.String(32), nullable=False),
        sa.Column("pipeline_type", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_session_id", sa.String(255)),
        sa.Column("livekit_room_name", sa.String(160)),
        sa.Column("livekit_dispatch_id", sa.String(160)),
        sa.Column("livekit_job_id", sa.String(160)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("idempotency_key", sa.String(160)),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("connected_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("end_reason", sa.String(40)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message_sanitized", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_voice_sessions_tenant_idempotency"),
        sa.CheckConstraint("status IN ('requested','dispatching','dispatched','starting','connected','ending','ended','failed','cancelled')", name="ck_voice_sessions_status"),
        sa.CheckConstraint("channel IN ('web','sip','internal_test')", name="ck_voice_sessions_channel"),
        sa.CheckConstraint("direction IN ('inbound','outbound','internal')", name="ck_voice_sessions_direction"),
    )
    op.create_index("ix_voice_sessions_tenant_status", "voice_sessions", ["tenant_id", "status"])
    op.create_index("ix_voice_sessions_agent", "voice_sessions", ["agent_id"])
    op.create_index("ix_voice_sessions_agent_version", "voice_sessions", ["agent_version_id"])
    op.create_index("ix_voice_sessions_created_at", "voice_sessions", ["created_at"])
    op.create_table(
        "voice_session_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(80), nullable=False, unique=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("voice_session_id", sa.String(36), sa.ForeignKey("voice_sessions.id"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("sequence", sa.Integer()),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_voice_session_events_tenant_session", "voice_session_events", ["tenant_id", "voice_session_id"])
    op.create_index("ix_voice_session_events_session_created", "voice_session_events", ["voice_session_id", "created_at"])


def downgrade() -> None:
    op.drop_table("voice_session_events")
    op.drop_table("voice_sessions")
