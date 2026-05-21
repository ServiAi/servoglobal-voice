"""sprint 7a fix identity risk — unique email + nullable external_auth_id

Revision ID: 202605100002
Revises: 202605100001
Create Date: 2026-05-21 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "202605100002"
down_revision = "202605100001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The partial unique index from 202605100001 was incorrect:
    # it only enforced email uniqueness when external_auth_id IS NOT NULL,
    # leaving a gap for duplicate emails with NULL external_auth_id.
    # Drop it and replace with a proper partial unique index that enforces
    # email uniqueness for all non-deleted users (status != 'deleted').
    op.drop_index("ix_users_email_unique", table_name="users")
    op.create_index(
        "ix_users_email_partial_unique",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("status != 'deleted'"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_email_partial_unique", table_name="users")
    op.create_index(
        "ix_users_email_unique",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("external_auth_id IS NOT NULL"),
    )
