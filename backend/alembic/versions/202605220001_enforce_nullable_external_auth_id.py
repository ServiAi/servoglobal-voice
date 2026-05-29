"""ensure users.external_auth_id remains nullable in deployed databases

Revision ID: 202605220001
Revises: 202605100002
Create Date: 2026-05-22 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "202605220001"
down_revision = "202605100002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE users ALTER COLUMN external_auth_id DROP NOT NULL")
        op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_users_external_auth_id")
        op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_external_auth_id_key")
        op.execute("DROP INDEX IF EXISTS ix_users_email_unique")
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_partial_unique "
            "ON users (email) WHERE status != 'deleted'"
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_external_auth_id_partial_unique "
            "ON users (external_auth_id) WHERE external_auth_id IS NOT NULL"
        )
        return

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "external_auth_id",
            existing_type=sa.String(length=255),
            nullable=True,
        )


def downgrade() -> None:
    # Intentionally do not restore NOT NULL: deployed tenant-admin users may
    # already exist without an Auth0 subject and should remain linkable by email.
    pass
