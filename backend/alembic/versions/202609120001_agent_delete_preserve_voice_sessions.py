"""allow deletion of archived agents while retaining terminal voice history

Revision ID: 202609120001
Revises: 202609090001
"""

import sqlalchemy as sa
from alembic import op

revision = "202609120001"
down_revision = "202609090001"
branch_labels = None
depends_on = None


def _change_references(*, nullable: bool, ondelete: str | None) -> None:
    inspector = sa.inspect(op.get_bind())
    foreign_keys = {
        tuple(fk["constrained_columns"]): fk["name"]
        for fk in inspector.get_foreign_keys("voice_sessions")
    }
    naming = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
    with op.batch_alter_table("voice_sessions", naming_convention=naming) as batch:
        for column, table in (
            ("agent_id", "tenant_agents"),
            ("agent_version_id", "tenant_agent_versions"),
        ):
            name = foreign_keys[(column,)] or f"fk_voice_sessions_{column}_{table}"
            batch.drop_constraint(name, type_="foreignkey")
            batch.alter_column(column, existing_type=sa.String(36), nullable=nullable)
            batch.create_foreign_key(
                f"fk_voice_sessions_{column}_{table}", table, [column], ["id"], ondelete=ondelete
            )


def upgrade() -> None:
    op.add_column("voice_sessions", sa.Column("deleted_agent_id", sa.String(36), nullable=True))
    op.add_column("voice_sessions", sa.Column("deleted_agent_version_id", sa.String(36), nullable=True))
    _change_references(nullable=True, ondelete="SET NULL")


def downgrade() -> None:
    if op.get_bind().execute(sa.text(
        "SELECT 1 FROM voice_sessions WHERE agent_id IS NULL OR agent_version_id IS NULL LIMIT 1"
    )).first():
        raise RuntimeError("Cannot restore required agent references after agent deletion.")
    _change_references(nullable=False, ondelete=None)
    op.drop_column("voice_sessions", "deleted_agent_version_id")
    op.drop_column("voice_sessions", "deleted_agent_id")
