"""WhatsApp message identity: one row per (tenant, provider message id).

Replaces the non-unique ``ix_crm_whatsapp_messages_tenant_provider_message`` with the partial
unique index ``uq_crm_whatsapp_messages_tenant_provider_message`` (``provider_message_id IS NOT
NULL``): rows without a provider id (queued / outcome unknown) may coexist, the same provider id
may exist in different tenants, and a writer that bypasses the service can no longer duplicate it.

The migration never deletes or merges rows. If duplicates already exist it aborts before touching
the schema; run ``backend/scripts/audit_whatsapp_message_duplicates.py`` and resolve them
deliberately (messages may be tied to CRM activity, notification deliveries and the audit trail).

PostgreSQL builds the unique index ``CONCURRENTLY`` (no long write lock) outside a transaction.

Revision ID: 202610050001
Revises: 202609240001
"""

from alembic import op
import sqlalchemy as sa


revision = "202610050001"
down_revision = "202609240001"
branch_labels = None
depends_on = None

TABLE = "crm_whatsapp_messages"
OLD_INDEX = "ix_crm_whatsapp_messages_tenant_provider_message"
UNIQUE_INDEX = "uq_crm_whatsapp_messages_tenant_provider_message"
WHERE = "provider_message_id IS NOT NULL"

DUPLICATE_GROUPS_SQL = """
SELECT tenant_id, provider_message_id, COUNT(*) AS rows_in_group
FROM crm_whatsapp_messages
WHERE provider_message_id IS NOT NULL
GROUP BY tenant_id, provider_message_id
HAVING COUNT(*) > 1
"""


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _assert_no_duplicates() -> None:
    bind = op.get_bind()
    groups = bind.execute(sa.text(DUPLICATE_GROUPS_SQL)).fetchall()
    if not groups:
        return
    rows = sum(group.rows_in_group for group in groups)
    raise RuntimeError(
        f"Cannot enforce WhatsApp provider message identity: {len(groups)} duplicate "
        f"(tenant_id, provider_message_id) group(s) cover {rows} rows in {TABLE}. "
        "No data was changed. Run backend/scripts/audit_whatsapp_message_duplicates.py, resolve the "
        "duplicates deliberately (do not delete blindly: rows may be tied to CRM activity, "
        "notification deliveries and the audit trail), then re-run the migration."
    )


def upgrade() -> None:
    _assert_no_duplicates()
    if _is_postgresql():
        with op.get_context().autocommit_block():
            # A previous attempt interrupted by a concurrent duplicate leaves an INVALID index behind.
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {UNIQUE_INDEX}")
            op.execute(
                f"CREATE UNIQUE INDEX CONCURRENTLY {UNIQUE_INDEX} "
                f"ON {TABLE} (tenant_id, provider_message_id) WHERE {WHERE}"
            )
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {OLD_INDEX}")
        return
    op.create_index(
        UNIQUE_INDEX,
        TABLE,
        ["tenant_id", "provider_message_id"],
        unique=True,
        sqlite_where=sa.text(WHERE),
    )
    op.drop_index(OLD_INDEX, table_name=TABLE)


def downgrade() -> None:
    if _is_postgresql():
        with op.get_context().autocommit_block():
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {OLD_INDEX} ON {TABLE} (tenant_id, provider_message_id)")
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {UNIQUE_INDEX}")
        return
    op.create_index(OLD_INDEX, TABLE, ["tenant_id", "provider_message_id"])
    op.drop_index(UNIQUE_INDEX, table_name=TABLE)
