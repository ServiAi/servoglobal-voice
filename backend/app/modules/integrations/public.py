"""Integrations (WhatsApp) -- public API.

Boundary only: implementation still lives in legacy app.services.whatsapp_*
and app.models.integrations. Services are imported lazily.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class WhatsAppTemplateRef:
    template_key: str
    status: str
    _row: Any = field(repr=False, compare=False)


@dataclass(frozen=True)
class WhatsAppSendOutcome:
    status: str
    provider_message_id: str | None


class WhatsAppFacade:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_template(self, tenant_id: str, template_key: str) -> WhatsAppTemplateRef | None:
        from app.models.integrations import TenantWhatsAppTemplate

        row = self.db.scalar(
            select(TenantWhatsAppTemplate).where(
                TenantWhatsAppTemplate.tenant_id == tenant_id,
                TenantWhatsAppTemplate.template_key == template_key,
            )
        )
        return None if row is None else WhatsAppTemplateRef(template_key=row.template_key, status=row.status, _row=row)

    def approved_parameter_keys(self, template: WhatsAppTemplateRef) -> list[str]:
        """Raises ValueError if the template's parameters are malformed."""
        from app.services.whatsapp_template_service import WhatsAppTemplateService

        return WhatsAppTemplateService(self.db).get_approved_parameter_keys(template._row)

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
