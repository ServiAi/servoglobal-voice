"""sprint 7a fix identity risk — align uniqueness policy

Revision ID: 202605100002
Revises: 202605100001
Create Date: 2026-05-21 00:00:00

Final policy:
- email: unique for all non-deleted users (partial unique index)
- external_auth_id: unique when NOT NULL (partial unique index)
"""
from alembic import op
import sqlalchemy as sa


revision = "202605100002"
down_revision = "202605100001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop the incorrect partial index from 200001
    #    (it only protected email when external_auth_id IS NOT NULL,
    #     leaving a gap for duplicate emails with NULL external_auth_id)
    op.drop_index("ix_users_email_unique", table_name="users")

    # 2. Create partial unique index for email (non-deleted users only)
    #    This is softer than a full UNIQUE constraint: allows duplicates
    #    for deleted users, which is acceptable for soft-delete semantics.
    op.create_index(
        "ix_users_email_partial_unique",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("status != 'deleted'"),
    )

    # 3. Create partial unique index for external_auth_id (non-NULL only)
    #    Ensures no two active users share the same Auth0 sub.
    op.create_index(
        "ix_users_external_auth_id_partial_unique",
        "users",
        ["external_auth_id"],
        unique=True,
        postgresql_where=sa.text("external_auth_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_external_auth_id_partial_unique", table_name="users")
    op.drop_index("ix_users_email_partial_unique", table_name="users")
    op.create_index(
        "ix_users_email_unique",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("external_auth_id IS NOT NULL"),
    )
