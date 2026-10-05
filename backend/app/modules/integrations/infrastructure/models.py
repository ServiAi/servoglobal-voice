"""ORM models owned by the Integrations / Messaging module.

13 tables: integration catalog + events, WhatsApp (config, templates, flows,
message ledger), Email (config, templates, assets, sends) and Chatwoot.
Cross-module ORM navigation (tenant, lead, contact, user, voice context) is
deliberately absent: only FKs are kept. ``crm_whatsapp_messages`` keeps its
historical CRM-flavoured name but belongs here (see DATA_OWNERSHIP.md).
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, _utcnow, _uuid


class TenantIntegration(Base, TimestampMixin):
    __tablename__ = "tenant_integrations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_integrations_tenant_provider"),
        Index("ix_tenant_integrations_tenant_id", "tenant_id"),
        Index("ix_tenant_integrations_tenant_provider", "tenant_id", "provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    config_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    secrets_json_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class TenantIntegrationEvent(Base):
    __tablename__ = "tenant_integration_events"
    __table_args__ = (
        Index("ix_tenant_integration_events_tenant_provider", "tenant_id", "provider"),
        Index("ix_tenant_integration_events_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class TenantWhatsAppConfig(Base, TimestampMixin):
    __tablename__ = "tenant_whatsapp_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_whatsapp_configs_tenant_provider"),
        Index("ix_tenant_whatsapp_configs_tenant_provider", "tenant_id", "provider"),
        Index("ix_tenant_whatsapp_configs_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_whatsapp_configs_phone_number", "phone_number_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="whatsapp_cloud")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    phone_number_id: Mapped[str] = mapped_column(String(120), nullable=False)
    business_account_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    display_phone_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    default_language: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_verify_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class TenantWhatsAppTemplate(Base, TimestampMixin):
    __tablename__ = "tenant_whatsapp_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "template_key", name="uq_tenant_whatsapp_templates_tenant_key"),
        Index("ix_tenant_whatsapp_templates_tenant_key", "tenant_id", "template_key"),
        Index("ix_tenant_whatsapp_templates_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    template_key: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_template_name: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="transactional")
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Deprecated: kept for backward-compatible reads; approval state now lives in the typed columns below.
    variables_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    # Internal lifecycle: draft | pending | approved | rejected | disabled.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    # Raw status string as returned by Meta: PENDING/APPROVED/REJECTED/PAUSED/DISABLED.
    meta_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_template_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="tenant_authored")
    parameter_format: Mapped[str] = mapped_column(String(16), nullable=False, default="POSITIONAL")
    header_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    footer_text: Mapped[str | None] = mapped_column(String(60), nullable=True)
    buttons_json: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    components_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class TenantWhatsAppFlow(Base, TimestampMixin):
    __tablename__ = "tenant_whatsapp_flows"
    __table_args__ = (
        UniqueConstraint("tenant_id", "flow_key", "version", name="uq_tenant_whatsapp_flows_tenant_key_version"),
        Index("ix_tenant_whatsapp_flows_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_whatsapp_flows_tenant_provider", "tenant_id", "provider_flow_id"),
        Index("ix_tenant_whatsapp_flows_tenant_key", "tenant_id", "flow_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    flow_key: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    parent_flow_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenant_whatsapp_flows.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    categories_json: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    source_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="visual")
    context_schema_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenant_voice_context_schemas.id", ondelete="SET NULL"), nullable=True
    )
    context_schema_snapshot_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    meta_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_flow_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    builder_schema_version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    builder_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    compiled_flow_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    compiled_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synced_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_errors_json: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parent_flow = relationship("TenantWhatsAppFlow", remote_side=[id])


class TenantEmailConfig(Base, TimestampMixin):
    __tablename__ = "tenant_email_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_email_configs_tenant_provider"),
        Index("ix_tenant_email_configs_tenant_provider", "tenant_id", "provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="resend")
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class TenantEmailTemplate(Base, TimestampMixin):
    __tablename__ = "tenant_email_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "template_key", name="uq_tenant_email_templates_tenant_key"),
        Index("ix_tenant_email_templates_tenant_key", "tenant_id", "template_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    template_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    html_body: Mapped[str] = mapped_column(Text, nullable=False)
    text_body: Mapped[str] = mapped_column(Text, nullable=False)
    variables_schema: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_marketing: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)


class TenantEmailAsset(Base, TimestampMixin):
    __tablename__ = "tenant_email_assets"
    __table_args__ = (
        Index("ix_tenant_email_assets_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_email_assets_storage_key", "storage_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")


class TenantEmailSend(Base, TimestampMixin):
    __tablename__ = "tenant_email_sends"
    __table_args__ = (
        Index("ix_tenant_email_sends_tenant_lead", "tenant_id", "lead_id"),
        Index("ix_tenant_email_sends_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_email_sends_tenant_provider_email", "tenant_id", "provider_email_id"),
        Index("ix_tenant_email_sends_tenant_created_at", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("crm_leads.id"), nullable=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("crm_contacts.id"), nullable=True)
    template_id: Mapped[str | None] = mapped_column(ForeignKey("tenant_email_templates.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="resend")
    provider_email_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    from_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    template = relationship("TenantEmailTemplate")


class TenantEmailSendAsset(Base):
    __tablename__ = "tenant_email_send_assets"
    __table_args__ = (
        Index("ix_tenant_email_send_assets_tenant_send", "tenant_id", "email_send_id"),
        UniqueConstraint("email_send_id", "asset_id", name="uq_tenant_email_send_assets_send_asset"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    email_send_id: Mapped[str] = mapped_column(ForeignKey("tenant_email_sends.id"), nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("tenant_email_assets.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    email_send = relationship("TenantEmailSend")
    asset = relationship("TenantEmailAsset")


class TenantChatwootConfig(Base, TimestampMixin):
    __tablename__ = "tenant_chatwoot_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_chatwoot_configs_tenant_provider"),
        UniqueConstraint("webhook_key", name="uq_tenant_chatwoot_configs_webhook_key"),
        # Aislamiento entre tenants: la misma Account de Chatwoot (identificada
        # por su instancia + account_id) no puede pertenecer a mas de un
        # tenant. account_id solo no alcanza porque dos instancias Chatwoot
        # distintas pueden reusar el mismo account_id.
        UniqueConstraint("base_url", "account_id", name="uq_tenant_chatwoot_configs_base_url_account_id"),
        Index("ix_tenant_chatwoot_configs_tenant_provider", "tenant_id", "provider"),
        Index("ix_tenant_chatwoot_configs_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_chatwoot_configs_account_id", "account_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="chatwoot")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="external")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    base_url: Mapped[str] = mapped_column(String(255), nullable=False, default="https://crm.serviglobal-ia.com")
    account_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    default_inbox_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    default_inbox_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    api_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_key: Mapped[str] = mapped_column(String(64), nullable=False)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class TenantChatwootInbox(Base, TimestampMixin):
    __tablename__ = "tenant_chatwoot_inboxes"
    __table_args__ = (
        Index("ix_tenant_chatwoot_inboxes_tenant_config", "tenant_id", "chatwoot_config_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    chatwoot_config_id: Mapped[str] = mapped_column(ForeignKey("tenant_chatwoot_configs.id"), nullable=False)
    chatwoot_inbox_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    channel: Mapped[str | None] = mapped_column(String(80), nullable=True)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_default: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    chatwoot_config = relationship("TenantChatwootConfig")


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

    template = relationship("TenantWhatsAppTemplate")
