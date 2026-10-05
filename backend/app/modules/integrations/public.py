"""Integrations (WhatsApp) -- public API.

Boundary only: implementation still lives in legacy app.services.whatsapp_*
and app.models.integrations. Services are imported lazily.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

__all__ = [
    "IntegrationsFacade",
    "WhatsAppDeliveryEvidence",
    "WhatsAppFacade",
    "WhatsAppMessageReceipt",
    "WhatsAppSendOutcome",
    "WhatsAppTransportPort",
    "WhatsAppTemplateContract",
]


@dataclass(frozen=True)
class WhatsAppTemplateContract:
    """What a caller may rely on about a tenant's template. Parameter keys
    are only resolved for approved templates (empty otherwise)."""

    template_key: str
    status: str
    approved_parameter_keys: tuple[str, ...]
    body: str = ""

    @property
    def is_approved(self) -> bool:
        return self.status == "approved"

    @property
    def required_variables(self) -> tuple[str, ...]:
        return self.approved_parameter_keys


@dataclass(frozen=True)
class WhatsAppMessageReceipt:
    id: str
    tenant_id: str
    template_id: str | None
    status: str
    metadata_json: dict[str, Any]
    lead_id: str | None
    contact_id: str | None
    error_message: str | None
    notification_delivery_id: str | None
    delivered_at: datetime | None
    read_at: datetime | None


class WhatsAppTransportPort(Protocol):
    def send_template_message(
        self, config: object, *, to_phone: str, template_name: str, language: str, components: list[dict[str, Any]]
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class WhatsAppSendOutcome:
    status: str
    provider_message_id: str | None
    message_id: str | None = None
    message: WhatsAppMessageReceipt | None = None


@dataclass(frozen=True)
class WhatsAppDeliveryEvidence:
    id: str
    status: str
    provider_message_id: str | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    created_at: datetime | None = None


class WhatsAppFacade:
    def __init__(self, db: Session, *, transport: WhatsAppTransportPort | None = None) -> None:
        self.db = db
        self._transport = transport

    def is_configured(self, tenant_id: str) -> bool:
        """Same resolution WhatsApp sends use at call time."""
        from app.services.whatsapp_config_service import WhatsAppConfigService

        try:
            WhatsAppConfigService(self.db).get_active_client_config(tenant_id)
            return True
        except ValueError:
            return False

    def get_approved_template_contract(self, tenant_id: str, template_key: str) -> WhatsAppTemplateContract | None:
        """None if the tenant has no such template. Raises ValueError if an
        approved template's parameters are malformed."""
        from app.models.integrations import TenantWhatsAppTemplate
        from app.services.whatsapp_template_service import WhatsAppTemplateService

        row = self.db.scalar(
            select(TenantWhatsAppTemplate).where(
                TenantWhatsAppTemplate.tenant_id == tenant_id,
                TenantWhatsAppTemplate.template_key == template_key,
            )
        )
        if row is None:
            return None
        keys = WhatsAppTemplateService(self.db).get_approved_parameter_keys(row) if row.status == "approved" else []
        return WhatsAppTemplateContract(
            template_key=row.template_key,
            status=row.status,
            approved_parameter_keys=tuple(keys),
            body=row.body or "",
        )

    def send_template(
        self,
        *,
        tenant_id: str,
        to_phone: str,
        template_key: str,
        variables: dict[str, str],
        metadata: dict[str, Any],
        lead_id: str | None,
        contact_id: str | None,
        notification_delivery_id: str | None = None,
    ) -> WhatsAppSendOutcome:
        """Raises ValueError on configuration/provider failures."""
        from app.services.whatsapp_message_service import WhatsAppMessageService

        result = WhatsAppMessageService(self.db, client=self._transport).send_template_notification(
            tenant_id=tenant_id,
            to_phone=to_phone,
            template_key=template_key,
            variables=variables,
            metadata=metadata,
            notification_delivery_id=notification_delivery_id,
            lead_id=lead_id,
            contact_id=contact_id,
        )
        return WhatsAppSendOutcome(
            status=result.status,
            provider_message_id=result.provider_message_id,
            message_id=result.message.id if result.message else None,
            message=(
                WhatsAppMessageReceipt(
                    id=result.message.id,
                    tenant_id=result.message.tenant_id,
                    template_id=result.message.template_id,
                    status=result.message.status,
                    metadata_json=dict(result.message.metadata_json or {}),
                    lead_id=result.message.lead_id,
                    contact_id=result.message.contact_id,
                    error_message=result.message.error_message,
                    notification_delivery_id=result.message.notification_delivery_id,
                    delivered_at=result.message.delivered_at,
                    read_at=result.message.read_at,
                )
                if result.message
                else None
            ),
        )


class IntegrationsFacade:
    """Which integrations a tenant has enabled (the on/off switch only)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def is_enabled(self, tenant_id: str, provider: str) -> bool:
        from app.services.integration_service import IntegrationService

        return IntegrationService(self.db).is_enabled(tenant_id, provider)


def get_whatsapp_template(*, tenant_id: str, template_key: str | None):
    from app.db.session import SessionLocal
    from app.modules.integrations.public import WhatsAppFacade

    db = SessionLocal()
    try:
        if not template_key:
            raise ValueError("template_key_required")
        contract = WhatsAppFacade(db).get_approved_template_contract(tenant_id, template_key)
        if contract is None or not contract.is_approved:
            raise ValueError("approved_template_not_found")
        return contract
    finally:
        db.close()


def find_whatsapp_delivery_evidence(
    *, tenant_id: str, delivery_id: str, fallback_message_id: str | None = None
):
    from app.db.session import SessionLocal
    from app.models.crm import CrmWhatsAppMessage
    from app.modules.integrations.public import WhatsAppDeliveryEvidence

    db = SessionLocal()
    try:
        message = db.scalar(
            select(CrmWhatsAppMessage)
            .where(
                CrmWhatsAppMessage.tenant_id == tenant_id,
                CrmWhatsAppMessage.notification_delivery_id == delivery_id,
            )
            .order_by(CrmWhatsAppMessage.created_at.desc(), CrmWhatsAppMessage.id.desc())
        )
        if message is None and fallback_message_id:
            message = db.scalar(
                select(CrmWhatsAppMessage).where(
                    CrmWhatsAppMessage.tenant_id == tenant_id,
                    CrmWhatsAppMessage.id == fallback_message_id,
                )
            )
        if message is None:
            return None
        return WhatsAppDeliveryEvidence(
            id=message.id,
            status=message.status,
            provider_message_id=message.provider_message_id,
            sent_at=message.sent_at,
            delivered_at=message.delivered_at,
            read_at=message.read_at,
            created_at=message.created_at,
        )
    finally:
        db.close()


def sanitize_whatsapp_error(value: str | None) -> str | None:
    from app.services.whatsapp_client import sanitize_whatsapp_error as sanitize

    return sanitize(value)
