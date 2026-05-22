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
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE users ALTER COLUMN external_auth_id DROP NOT NULL")
        op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_users_external_auth_id")
        op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_external_auth_id_key")
        op.execute("DROP INDEX IF EXISTS ix_users_email_unique")
        # Add index on email for fast lookup during link-by-email resolution.
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_unique "
            "ON users (email) WHERE external_auth_id IS NOT NULL"
        )
        return

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "external_auth_id",
            existing_type=sa.String(length=255),
            nullable=True,
        )
    op.create_index("ix_users_email_unique", "users", ["email"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_users_email_unique")
        op.execute(
            "ALTER TABLE users ADD CONSTRAINT uq_users_external_auth_id "
            "UNIQUE (external_auth_id)"
        )
        op.execute("ALTER TABLE users ALTER COLUMN external_auth_id SET NOT NULL")
        return

    op.drop_index("ix_users_email_unique", table_name="users")
    op.create_unique_constraint("uq_users_external_auth_id", "users", ["external_auth_id"])
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "external_auth_id",
            existing_type=sa.String(length=255),
            nullable=False,
        )
