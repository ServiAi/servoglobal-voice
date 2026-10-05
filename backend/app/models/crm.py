"""Legacy CRM-named tables owned by Messaging (not by CRM).

``CrmWhatsAppMessage`` still lives here until the Messaging module is migrated
(see docs/architecture/MODULAR_MONOLITH_MIGRATION.md). Relationships to CRM's
``CrmLead``/``CrmContact`` are resolved by name through the shared registry;
this file must not re-export CRM's models.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, _uuid


class CrmWhatsAppMessage(Base, TimestampMixin):
    __tablename__ = "crm_whatsapp_messages"
    __table_args__ = (
        Index("ix_crm_whatsapp_messages_tenant_lead", "tenant_id", "lead_id"),
        Index("ix_crm_whatsapp_messages_tenant_contact", "tenant_id", "contact_id"),
        Index("ix_crm_whatsapp_messages_tenant_status", "tenant_id", "status"),
        Index("ix_crm_whatsapp_messages_tenant_provider_message", "tenant_id", "provider_message_id"),
        Index("ix_crm_whatsapp_messages_tenant_created_at", "tenant_id", "created_at"),
        Index(
            "ix_crm_whatsapp_messages_tenant_notification_delivery",
            "tenant_id",
            "notification_delivery_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("crm_leads.id"), nullable=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("crm_contacts.id"), nullable=True)
    template_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_whatsapp_templates.id"), nullable=True)
    notification_delivery_id: Mapped[str | None] = mapped_column(
        ForeignKey("notification_deliveries.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="whatsapp_cloud")
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="outbound")
    to_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    from_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    template_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    message_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    lead = relationship("CrmLead")
    contact = relationship("CrmContact")
    template = relationship("TenantWhatsAppTemplate")
