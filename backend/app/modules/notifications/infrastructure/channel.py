from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.integrations.public import WhatsAppFacade, WhatsAppTransportPort
from app.modules.notifications.ports import NotificationChannelPort
from app.modules.notifications.public import (
    NotificationMessageReceipt,
    NotificationSendResult,
    NotificationTemplate,
)


class IntegrationsWhatsAppChannel(NotificationChannelPort):
    def __init__(self, db: Session, *, transport: WhatsAppTransportPort | None = None) -> None:
        self._facade = WhatsAppFacade(db, transport=transport)

    def get_template(self, *, tenant_id: str, template_key: str | None) -> NotificationTemplate:
        if not template_key:
            raise ValueError("template_key_required")
        contract = self._facade.get_approved_template_contract(tenant_id, template_key)
        if contract is None or not contract.is_approved:
            raise ValueError("approved_template_not_found")
        return NotificationTemplate(
            template_key=contract.template_key,
            body=contract.body,
            required_variables=contract.required_variables,
        )

    def send_template(
        self,
        *,
        tenant_id: str,
        to_phone: str,
        template_key: str,
        variables: dict[str, str],
        metadata: dict[str, str],
        notification_delivery_id: str,
        lead_id: str | None,
        contact_id: str | None,
    ) -> NotificationSendResult:
        outcome = self._facade.send_template(
            tenant_id=tenant_id,
            to_phone=to_phone,
            template_key=template_key,
            variables=variables,
            metadata=metadata,
            notification_delivery_id=notification_delivery_id,
            lead_id=lead_id,
            contact_id=contact_id,
        )
        return NotificationSendResult(
            status=outcome.status,
            message_id=outcome.message_id,
            provider_message_id=outcome.provider_message_id,
            message=(
                NotificationMessageReceipt(
                    id=outcome.message.id,
                    tenant_id=outcome.message.tenant_id,
                    template_id=outcome.message.template_id,
                    status=outcome.message.status,
                    metadata_json=outcome.message.metadata_json,
                    lead_id=outcome.message.lead_id,
                    contact_id=outcome.message.contact_id,
                    error_message=outcome.message.error_message,
                    notification_delivery_id=outcome.message.notification_delivery_id,
                    delivered_at=outcome.message.delivered_at,
                    read_at=outcome.message.read_at,
                )
                if outcome.message
                else None
            ),
        )
