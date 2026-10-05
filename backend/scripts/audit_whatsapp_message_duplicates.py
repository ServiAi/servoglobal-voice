"""Read-only audit of duplicate WhatsApp provider message ids.

Lists ``(tenant_id, provider_message_id)`` groups with more than one row in
``crm_whatsapp_messages`` -- the groups that make migration 202610050001 abort. Prints only
technical identifiers (row ids, direction, status, timestamps, link ids): never message bodies,
phones, emails, tokens, template variables or provider payloads. It never writes or deletes.

    DATABASE_URL=postgresql+psycopg://... python scripts/audit_whatsapp_message_duplicates.py

Exit code: 0 = no duplicates, 1 = duplicates found, 2 = could not run.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text

GROUPS_SQL = text(
    """
    SELECT tenant_id, provider_message_id, COUNT(*) AS rows_in_group
    FROM crm_whatsapp_messages
    WHERE provider_message_id IS NOT NULL
    GROUP BY tenant_id, provider_message_id
    HAVING COUNT(*) > 1
    ORDER BY rows_in_group DESC, tenant_id, provider_message_id
    """
)
ROWS_SQL = text(
    """
    SELECT id, direction, status, created_at, notification_delivery_id, lead_id, contact_id
    FROM crm_whatsapp_messages
    WHERE tenant_id = :tenant_id AND provider_message_id = :provider_message_id
    ORDER BY created_at, id
    """
)


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    engine = create_engine(url)
    with engine.connect() as conn:  # read-only: only SELECTs are issued
        groups = conn.execute(GROUPS_SQL).fetchall()
        affected = sum(group.rows_in_group for group in groups)
        print(f"duplicate groups: {len(groups)}")
        print(f"affected rows:    {affected}")
        for group in groups:
            print(f"\ntenant_id={group.tenant_id} provider_message_id={group.provider_message_id} rows={group.rows_in_group}")
            for row in conn.execute(
                ROWS_SQL, {"tenant_id": group.tenant_id, "provider_message_id": group.provider_message_id}
            ):
                print(
                    f"  id={row.id} direction={row.direction} status={row.status} created_at={row.created_at} "
                    f"notification_delivery_id={row.notification_delivery_id} lead_id={row.lead_id} contact_id={row.contact_id}"
                )
    if groups:
        print("\nResolve these deliberately (do not delete blindly), then re-run the migration.")
        return 1
    print("no duplicates: the unique index can be created")
    return 0


if __name__ == "__main__":
    sys.exit(main())
