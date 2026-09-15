"""add tenant-scoped LiveKit SIP outbound state

Revision ID: 202609140002
Revises: 202609140001
"""

import sqlalchemy as sa
from alembic import op

revision = "202609140002"
down_revision = "202609140001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "tenant_sip_routes_provider_config_id_fkey",
        "tenant_sip_routes",
        type_="foreignkey",
    )
    op.alter_column("tenant_sip_routes", "provider_config_id", nullable=True)
    op.create_foreign_key(
        "tenant_sip_routes_provider_config_id_fkey",
        "tenant_sip_routes",
        "tenant_voice_provider_configs",
        ["provider_config_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("tenant_sip_routes", sa.Column("livekit_outbound_trunk_id", sa.String(160)))
    op.add_column(
        "tenant_sip_routes",
        sa.Column("livekit_provision_status", sa.String(16), nullable=False, server_default="disabled"),
    )
    op.add_column("tenant_sip_routes", sa.Column("livekit_provision_error_code", sa.String(80)))
    op.add_column("tenant_sip_routes", sa.Column("livekit_provisioned_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint(
        "uq_tenant_sip_routes_livekit_trunk",
        "tenant_sip_routes",
        ["livekit_outbound_trunk_id"],
    )
    op.create_check_constraint(
        "ck_tenant_sip_routes_livekit_provision_status",
        "tenant_sip_routes",
        "livekit_provision_status IN ('pending','active','failed','disabled')",
    )
    op.alter_column(
        "tenant_sip_routes", "livekit_provision_status", server_default=None
    )

    op.add_column("voice_sessions", sa.Column("sip_route_id", sa.String(36)))
    op.add_column("voice_sessions", sa.Column("livekit_sip_trunk_id", sa.String(160)))
    op.add_column("voice_sessions", sa.Column("livekit_sip_participant_identity", sa.String(160)))
    op.add_column("voice_sessions", sa.Column("sip_call_id", sa.String(255)))
    op.add_column("voice_sessions", sa.Column("runtime_ready_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "voice_sessions_sip_route_id_fkey",
        "voice_sessions",
        "tenant_sip_routes",
        ["sip_route_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_voice_sessions_crm_voice_call", "voice_sessions", ["crm_voice_call_id"])
    op.create_index("ix_voice_sessions_sip_call", "voice_sessions", ["sip_call_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_sessions_sip_call", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_crm_voice_call", table_name="voice_sessions")
    op.drop_constraint("voice_sessions_sip_route_id_fkey", "voice_sessions", type_="foreignkey")
    for column in (
        "runtime_ready_at",
        "sip_call_id",
        "livekit_sip_participant_identity",
        "livekit_sip_trunk_id",
        "sip_route_id",
    ):
        op.drop_column("voice_sessions", column)

    op.drop_constraint("ck_tenant_sip_routes_livekit_provision_status", "tenant_sip_routes", type_="check")
    op.drop_constraint("uq_tenant_sip_routes_livekit_trunk", "tenant_sip_routes", type_="unique")
    for column in (
        "livekit_provisioned_at",
        "livekit_provision_error_code",
        "livekit_provision_status",
        "livekit_outbound_trunk_id",
    ):
        op.drop_column("tenant_sip_routes", column)
    op.drop_constraint(
        "tenant_sip_routes_provider_config_id_fkey",
        "tenant_sip_routes",
        type_="foreignkey",
    )
    op.alter_column("tenant_sip_routes", "provider_config_id", nullable=False)
    op.create_foreign_key(
        "tenant_sip_routes_provider_config_id_fkey",
        "tenant_sip_routes",
        "tenant_voice_provider_configs",
        ["provider_config_id"],
        ["id"],
        ondelete="CASCADE",
    )
