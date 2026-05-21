"""sprint 7a allow nullable external_auth_id for email-first onboarding

Revision ID: 202605100001
Revises: 202605020001
Create Date: 2026-05-10 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "202605100001"
down_revision = "202605020001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make external_auth_id nullable and remove unique constraint
    # so users can be provisioned by email before their Auth0 sub is known.
    op.alter_column("users", "external_auth_id", nullable=True)
    op.drop_constraint("uq_users_external_auth_id", "users", type_="unique")
    # Add index on email for fast lookup during link-by-email resolution
    op.create_index(
        "ix_users_email_unique", "users", ["email"], unique=True,
        postgresql_where=sa.text("external_auth_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_email_unique", table_name="users")
    op.create_unique_constraint("uq_users_external_auth_id", "users", ["external_auth_id"])
    op.alter_column("users", "external_auth_id", nullable=False)
