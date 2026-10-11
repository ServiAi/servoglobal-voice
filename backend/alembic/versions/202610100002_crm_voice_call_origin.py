"""Explicit origin of a CRM voice call.

``crm_voice_calls.origin`` says who owns the call independently of ``source_submission_id``
(cleared by ON DELETE SET NULL) and of the provider, so the Voice Experience callback worker can
claim its own calls -- and fail closed those whose submission was deleted -- without ever touching
a CRM-initiated outbound call.
"""

from alembic import op
import sqlalchemy as sa


revision = "202610100002"
down_revision = "202610100001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crm_voice_calls", sa.Column("origin", sa.String(40), nullable=True))
    # Conservative backfill: only calls that are provably a Voice Experience callback are classified
    # as one; anything else is a CRM-initiated outbound call.
    op.execute(
        """
        UPDATE crm_voice_calls SET origin = CASE
            WHEN source_submission_id IS NOT NULL AND provider = 'livekit_sip' THEN 'voice_experience_callback'
            WHEN source_submission_id IS NOT NULL THEN 'legacy_voice_experience_callback'
            ELSE 'crm_outbound'
        END
        """
    )
    # A writer that predates this column (rolling deploy) lands on the safe value: never a callback.
    op.alter_column(
        "crm_voice_calls",
        "origin",
        existing_type=sa.String(40),
        nullable=False,
        server_default=sa.text("'crm_outbound'"),
    )
    op.create_check_constraint(
        "ck_crm_voice_calls_origin",
        "crm_voice_calls",
        "origin IN ('crm_outbound', 'voice_experience_callback', 'legacy_voice_experience_callback')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_crm_voice_calls_origin", "crm_voice_calls", type_="check")
    op.drop_column("crm_voice_calls", "origin")
