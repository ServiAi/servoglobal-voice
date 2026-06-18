"""add tenant billing plans, usage alerts, and provider pricing

Revision ID: 202605300001
Revises: 202605220001
Create Date: 2026-05-30 00:00:00
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alembic import op
import sqlalchemy as sa


revision = "202605300001"
down_revision = "202605220001"
branch_labels = None
depends_on = None


def _uuid() -> str:
    return str(uuid.uuid4())


def upgrade() -> None:
    op.create_table(
        "tenant_billing_plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("plan_key", sa.String(length=64), nullable=False),
        sa.Column("plan_name", sa.String(length=120), nullable=False),
        sa.Column("included_minutes", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_per_minute_usd", sa.Numeric(10, 4), nullable=False),
        sa.Column("usage_status", sa.String(length=32), nullable=False),
        sa.Column("billing_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("billing_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("alert_thresholds", sa.JSON(), nullable=False),
        sa.Column("last_usage_recalculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "plan_key in ('web_conversion', 'voice_cloud_pbx', 'enterprise')",
            name="ck_tenant_billing_plans_plan_key",
        ),
        sa.CheckConstraint("included_minutes >= 2000", name="ck_tenant_billing_plans_min_minutes"),
        sa.CheckConstraint("price_per_minute_usd > 0", name="ck_tenant_billing_plans_positive_price"),
        sa.CheckConstraint(
            "plan_key != 'web_conversion' OR price_per_minute_usd = 0.16",
            name="ck_tenant_billing_plans_web_price",
        ),
        sa.CheckConstraint(
            "plan_key != 'voice_cloud_pbx' OR price_per_minute_usd = 0.18",
            name="ck_tenant_billing_plans_voice_price",
        ),
        sa.CheckConstraint(
            "plan_key != 'enterprise' OR "
            "(price_per_minute_usd >= 0.14 AND price_per_minute_usd <= 0.15)",
            name="ck_tenant_billing_plans_enterprise_price",
        ),
        sa.CheckConstraint(
            "usage_status in ("
            "'normal', 'approaching_limit', 'limit_reached', "
            "'over_limit', 'suspended_usage_limit'"
            ")",
            name="ck_tenant_billing_plans_usage_status",
        ),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_billing_plans_tenant_id"),
    )
    op.create_index("ix_tenant_billing_plans_tenant_id", "tenant_billing_plans", ["tenant_id"])
    op.create_index("ix_tenant_billing_plans_usage_status", "tenant_billing_plans", ["usage_status"])

    op.create_table(
        "tenant_usage_alerts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "billing_plan_id",
            sa.String(length=36),
            sa.ForeignKey("tenant_billing_plans.id"),
            nullable=False,
        ),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("threshold_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("billing_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "alert_type in ('warning_80', 'warning_90', 'limit_reached')",
            name="ck_tenant_usage_alerts_alert_type",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "alert_type",
            "billing_period_start",
            name="uq_tenant_usage_alerts_tenant_type_period",
        ),
    )
    op.create_index("ix_tenant_usage_alerts_tenant_id", "tenant_usage_alerts", ["tenant_id"])
    op.create_index("ix_tenant_usage_alerts_created_at", "tenant_usage_alerts", ["created_at"])

    op.create_table(
        "external_provider_pricing",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("provider_key", sa.String(length=80), nullable=False),
        sa.Column("provider_name", sa.String(length=120), nullable=False),
        sa.Column("provider_price_per_minute_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("price_min_per_minute_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("price_max_per_minute_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("price_source", sa.String(length=80), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider_key", name="uq_external_provider_pricing_key"),
    )
    op.create_index(
        "ix_external_provider_pricing_provider_key",
        "external_provider_pricing",
        ["provider_key"],
    )

    bind = op.get_bind()
    now = datetime.now(UTC)
    billing_period_end = now + timedelta(days=30)
    tenants = bind.execute(sa.text("SELECT id FROM tenants")).fetchall()
    tenant_plan_table = sa.table(
        "tenant_billing_plans",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("plan_key", sa.String),
        sa.column("plan_name", sa.String),
        sa.column("included_minutes", sa.Numeric),
        sa.column("price_per_minute_usd", sa.Numeric),
        sa.column("usage_status", sa.String),
        sa.column("billing_period_start", sa.DateTime),
        sa.column("billing_period_end", sa.DateTime),
        sa.column("alert_thresholds", sa.JSON),
        sa.column("last_usage_recalculated_at", sa.DateTime),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    if tenants:
        bind.execute(
            tenant_plan_table.insert(),
            [
                {
                    "id": _uuid(),
                    "tenant_id": tenant.id,
                    "plan_key": "web_conversion",
                    "plan_name": "Plan Web Conversion",
                    "included_minutes": Decimal("2000.00"),
                    "price_per_minute_usd": Decimal("0.1600"),
                    "usage_status": "normal",
                    "billing_period_start": now,
                    "billing_period_end": billing_period_end,
                    "alert_thresholds": [80, 90, 100],
                    "last_usage_recalculated_at": None,
                    "created_at": now,
                    "updated_at": now,
                }
                for tenant in tenants
            ],
        )

    provider_table = sa.table(
        "external_provider_pricing",
        sa.column("id", sa.String),
        sa.column("provider_key", sa.String),
        sa.column("provider_name", sa.String),
        sa.column("provider_price_per_minute_usd", sa.Numeric),
        sa.column("price_min_per_minute_usd", sa.Numeric),
        sa.column("price_max_per_minute_usd", sa.Numeric),
        sa.column("price_source", sa.String),
        sa.column("source_url", sa.Text),
        sa.column("notes", sa.Text),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    op.bulk_insert(
        provider_table,
        [
            {
                "id": _uuid(),
                "provider_key": "retell",
                "provider_name": "Retell",
                "provider_price_per_minute_usd": Decimal("0.1100"),
                "price_min_per_minute_usd": Decimal("0.0700"),
                "price_max_per_minute_usd": Decimal("0.3100"),
                "price_source": "official_estimator",
                "source_url": "https://www.retellai.com/pricing",
                "notes": "Official calculator default; pay-as-you-go range is 0.07-0.31 USD/min.",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": _uuid(),
                "provider_key": "vapi",
                "provider_name": "Vapi",
                "provider_price_per_minute_usd": Decimal("0.0500"),
                "price_min_per_minute_usd": None,
                "price_max_per_minute_usd": None,
                "price_source": "official_base_excludes_provider_costs",
                "source_url": "https://vapi.ai/pricing",
                "notes": "Hosting cost only; STT, LLM and TTS provider costs are extra.",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": _uuid(),
                "provider_key": "dapta",
                "provider_name": "Dapta",
                "provider_price_per_minute_usd": Decimal("0.3300"),
                "price_min_per_minute_usd": None,
                "price_max_per_minute_usd": None,
                "price_source": "official_derived_credits",
                "source_url": "https://dapta.ai/pricing-2/",
                "notes": "Derived from Pro plan 99 USD / 100k credits and 333 credits per effective call minute.",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": _uuid(),
                "provider_key": "openai_realtime",
                "provider_name": "OpenAI Realtime",
                "provider_price_per_minute_usd": Decimal("0.0960"),
                "price_min_per_minute_usd": None,
                "price_max_per_minute_usd": None,
                "price_source": "official_token_estimate",
                "source_url": "https://platform.openai.com/docs/models/gpt-realtime",
                "notes": "Assumes 1 minute user audio input plus 1 minute assistant audio output on gpt-realtime.",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": _uuid(),
                "provider_key": "gemini_live_api",
                "provider_name": "Gemini Realtime / Google Live API",
                "provider_price_per_minute_usd": Decimal("0.0225"),
                "price_min_per_minute_usd": None,
                "price_max_per_minute_usd": None,
                "price_source": "official_token_estimate",
                "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
                "notes": "Assumes Gemini 2.5 Flash Native Audio input and output audio for one minute each.",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": _uuid(),
                "provider_key": "custom",
                "provider_name": "Otros / Custom",
                "provider_price_per_minute_usd": None,
                "price_min_per_minute_usd": None,
                "price_max_per_minute_usd": None,
                "price_source": "manual",
                "source_url": None,
                "notes": "Configure manually for provider-specific contracts.",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_external_provider_pricing_provider_key", table_name="external_provider_pricing")
    op.drop_table("external_provider_pricing")
    op.drop_index("ix_tenant_usage_alerts_created_at", table_name="tenant_usage_alerts")
    op.drop_index("ix_tenant_usage_alerts_tenant_id", table_name="tenant_usage_alerts")
    op.drop_table("tenant_usage_alerts")
    op.drop_index("ix_tenant_billing_plans_usage_status", table_name="tenant_billing_plans")
    op.drop_index("ix_tenant_billing_plans_tenant_id", table_name="tenant_billing_plans")
    op.drop_table("tenant_billing_plans")
