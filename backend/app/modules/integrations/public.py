"""Integrations (WhatsApp) -- public API.

Boundary only: implementation still lives in legacy app.services.whatsapp_*
and app.models.integrations. Services are imported lazily.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

__all__ = ["IntegrationsFacade", "WhatsAppFacade", "WhatsAppSendOutcome", "WhatsAppTemplateContract"]


@dataclass(frozen=True)
class WhatsAppTemplateContract:
    """What a caller may rely on about a tenant's template. Parameter keys
    are only resolved for approved templates (empty otherwise)."""

    template_key: str
    status: str
    approved_parameter_keys: tuple[str, ...]

    @property
    def is_approved(self) -> bool:
        return self.status == "approved"


@dataclass(frozen=True)
class WhatsAppSendOutcome:
    status: str
    provider_message_id: str | None


class WhatsAppFacade:
    def __init__(self, db: Session) -> None:
        self.db = db

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
            template_key=row.template_key, status=row.status, approved_parameter_keys=tuple(keys)
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
    ) -> WhatsAppSendOutcome:
        """Raises ValueError on configuration/provider failures."""
        from app.services.whatsapp_message_service import WhatsAppMessageService

        result = WhatsAppMessageService(self.db).send_template_notification(
            tenant_id=tenant_id,
            to_phone=to_phone,
            template_key=template_key,
            variables=variables,
            metadata=metadata,
            lead_id=lead_id,
            contact_id=contact_id,
        )
        return WhatsAppSendOutcome(status=result.status, provider_message_id=result.provider_message_id)


class IntegrationsFacade:
    """Which integrations a tenant has enabled (the on/off switch only)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def is_enabled(self, tenant_id: str, provider: str) -> bool:
        from app.services.integration_service import IntegrationService

        return IntegrationService(self.db).is_enabled(tenant_id, provider)
