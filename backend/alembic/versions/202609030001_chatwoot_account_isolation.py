"""chatwoot account isolation

Revision ID: 202609030001
Revises: 202609020003
Create Date: 2026-09-03 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202609030001"
down_revision = "202609020003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # La misma (base_url, account_id) puede pertenecer a un solo tenant. Antes
    # de crear la restriccion, verificar que no haya datos existentes que ya
    # la violen -- si los hay, abortar con un mensaje claro en vez de dejar
    # que el CREATE UNIQUE INDEX falle con un error generico de Postgres, o
    # peor, que corra silenciosamente sobre una base sin datos y deje el
    # problema sin detectar hasta produccion.
    duplicates = bind.execute(
        sa.text(
            """
            SELECT base_url, account_id, COUNT(DISTINCT tenant_id) AS tenant_count
            FROM tenant_chatwoot_configs
            GROUP BY base_url, account_id
            HAVING COUNT(DISTINCT tenant_id) > 1
            """
        )
    ).fetchall()
    if duplicates:
        details = "; ".join(f"{row[0]} account_id={row[1]} ({row[2]} tenants)" for row in duplicates)
        raise RuntimeError(
            "No se puede aplicar UNIQUE(base_url, account_id) en tenant_chatwoot_configs: "
            f"hay Accounts compartidas por mas de un tenant que deben resolverse manualmente antes: {details}"
        )

    op.create_unique_constraint(
        "uq_tenant_chatwoot_configs_base_url_account_id",
        "tenant_chatwoot_configs",
        ["base_url", "account_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_tenant_chatwoot_configs_base_url_account_id",
        "tenant_chatwoot_configs",
        type_="unique",
    )
