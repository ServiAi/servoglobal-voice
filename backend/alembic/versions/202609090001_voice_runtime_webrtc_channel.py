"""allow the canonical webrtc voice session channel

Revision ID: 202609090001
Revises: 202609080001
"""

from alembic import op

revision = "202609090001"
down_revision = "202609080001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_voice_sessions_channel", "voice_sessions", type_="check")
    op.create_check_constraint(
        "ck_voice_sessions_channel",
        "voice_sessions",
        "channel IN ('web','webrtc','sip','internal_test')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_voice_sessions_channel", "voice_sessions", type_="check")
    op.create_check_constraint(
        "ck_voice_sessions_channel",
        "voice_sessions",
        "channel IN ('web','sip','internal_test')",
    )
