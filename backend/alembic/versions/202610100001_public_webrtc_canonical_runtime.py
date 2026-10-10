"""Correlate public WebRTC launches with canonical VoiceSessions.

tenant_voice_runtime_calls becomes the public launch ledger; the authoritative
session is voice_sessions. Historical (direct-provider) rows keep NULL.
"""

from alembic import op
import sqlalchemy as sa


revision = "202610100001"
down_revision = "202610090001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rollout discriminator: every row that exists today was launched against the provider directly.
    op.add_column("tenant_voice_runtime_calls", sa.Column("launch_runtime", sa.String(32), nullable=True))
    op.execute("UPDATE tenant_voice_runtime_calls SET launch_runtime = 'legacy_provider'")
    # Conservative default: during a rolling deploy an old replica (PR #134) keeps inserting rows
    # without knowing this column, and those are legacy launches. Canonical writers set it explicitly.
    op.alter_column(
        "tenant_voice_runtime_calls",
        "launch_runtime",
        existing_type=sa.String(32),
        nullable=False,
        server_default=sa.text("'legacy_provider'"),
    )
    op.create_check_constraint(
        "ck_voice_runtime_launch_runtime",
        "tenant_voice_runtime_calls",
        "launch_runtime IN ('legacy_provider', 'canonical_voice_session')",
    )
    op.add_column("tenant_voice_runtime_calls", sa.Column("voice_session_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_voice_runtime_voice_session",
        "tenant_voice_runtime_calls",
        "voice_sessions",
        ["voice_session_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_voice_runtime_voice_session",
        "tenant_voice_runtime_calls",
        ["voice_session_id"],
        unique=True,
        postgresql_where=sa.text("voice_session_id IS NOT NULL"),
        sqlite_where=sa.text("voice_session_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_voice_runtime_voice_session", table_name="tenant_voice_runtime_calls")
    op.drop_constraint("fk_voice_runtime_voice_session", "tenant_voice_runtime_calls", type_="foreignkey")
    op.drop_column("tenant_voice_runtime_calls", "voice_session_id")
    op.drop_constraint("ck_voice_runtime_launch_runtime", "tenant_voice_runtime_calls", type_="check")
    op.drop_column("tenant_voice_runtime_calls", "launch_runtime")
