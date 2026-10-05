from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.crm.public import ContactProfile, CrmFacade, LeadProfile
from app.modules.integrations.application.dto import (
    WhatsAppTestMessageCommand,
    WhatsAppTestMessageResult,
)
from app.modules.integrations.application.event_service import IntegrationEventService
from app.modules.integrations.application.ports import (
    NotificationsPort,
    WhatsAppProviderPort,
)
from app.modules.integrations.application.whatsapp.config_service import (
    WhatsAppConfigService,
)
from app.modules.integrations.application.whatsapp.template_service import (
    WhatsAppTemplateService,
)
from app.modules.integrations.domain.errors import ProviderError
from app.modules.integrations.domain.whatsapp import (
    MISSING_PROVIDER_MESSAGE_ID_ERROR,
    WhatsAppInboundMessage,
    WhatsAppStatusUpdate,
    WhatsAppWebhookEvent,
    can_advance_status,
    extract_provider_message_id,
    mask_phone,
    normalize_phone,
    safe_preview,
    sanitize_whatsapp_error,
)
from app.modules.integrations.infrastructure.models import (
    CrmWhatsAppMessage,
    TenantWhatsAppConfig,
)

logger = logging.getLogger(__name__)

_ALLOWED_NOTIFICATION_METADATA_KEYS = {
    "source",
    "notification_delivery_id",
    "domain_event_id",
    "notification_rule_id",
    "template_key",
}

@dataclass
class WhatsAppSendResult:
    status: str
    message: CrmWhatsAppMessage | None = None
    provider_message_id: str | None = None
    preview: dict[str, Any] | None = None
    error_message: str | None = None


class WhatsAppMessageService:
    provider = "whatsapp_cloud"

    def __init__(
        self,
        db: Session,
        client: WhatsAppProviderPort | None = None,
        *,
        notifications: NotificationsPort | None = None,
    ) -> None:
        from app.modules.integrations import wiring

        self.db = db
        self.client = client or wiring.default_whatsapp_provider()
        self.configs = WhatsAppConfigService(db, client=self.client)
        self.templates = WhatsAppTemplateService(db)
        self.events = IntegrationEventService(db)
        self.crm = CrmFacade(db)
        self.notifications = notifications or wiring.default_notifications()

    def _get_lead(self, tenant_id: str, lead_id: str) -> LeadProfile:
        lead = self.crm.get_lead_profile(tenant_id, lead_id)
        if lead is None:
            raise ValueError("Lead not found")
        return lead

    def _lead_variables(self, lead: LeadProfile, variables: dict[str, Any]) -> dict[str, Any]:
        contact = lead.contact
        return {
            "contact_name": contact.name,
            "agent_name": "ServiGlobal AI",
            "interest": lead.interest or lead.use_case or "nuestros servicios",
            **variables,
        }

    def preview_lead_whatsapp(
        self, tenant_id: str, lead_id: str, *, template_key: str, message_text: str | None = None, variables: dict[str, Any] | None = None
    ) -> WhatsAppSendResult:
        lead = self._get_lead(tenant_id, lead_id)
        phone = lead.contact.phone or lead.contact.phone_normalized
        if not phone:
            raise ValueError("Lead contact does not have a phone number")
        template = self.templates.get_template(tenant_id, template_key)
        rendered_variables = self._lead_variables(lead, variables or {})
        body = message_text or self.templates.render_template(template, rendered_variables)
        return WhatsAppSendResult(
            status="preview",
            preview={
                "to_phone": phone,
                "template_key": template.template_key,
                "provider_template_name": template.provider_template_name,
                "message": body,
                "variables": rendered_variables,
            },
        )

    def send_lead_whatsapp(
        self, tenant_id: str, lead_id: str, *, template_key: str, message_text: str | None = None, variables: dict[str, Any] | None = None
    ) -> WhatsAppSendResult:
        lead = self._get_lead(tenant_id, lead_id)
        contact = lead.contact
        phone = contact.phone or contact.phone_normalized
        if not phone:
            raise ValueError("Lead contact does not have a phone number")

        config, client_config = self.configs.get_active_client_config(tenant_id)
        template = self.templates.get_template(tenant_id, template_key)
        rendered_variables = self._lead_variables(lead, variables or {})
        body = message_text or self.templates.render_template(template, rendered_variables)
        now = datetime.now(timezone.utc)

        message = CrmWhatsAppMessage(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=contact.id,
            template_id=template.id,
            template_key=template.template_key,
            direction="outbound",
            to_phone=phone,
            from_phone=config.display_phone_number,
            message_preview=safe_preview(body),
            status="queued",
            metadata_json={"template_key": template.template_key},
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="whatsapp_message_requested",
            status="queued",
            resource_type="crm_whatsapp_message",
            resource_id=message.id,
        )

        try:
            if message_text:
                payload = self.client.send_text_message(client_config, to_phone=phone, message=body)
            else:
                payload = self.client.send_template_message(
                    client_config,
                    to_phone=phone,
                    template_name=template.provider_template_name,
                    language=template.language or config.default_language,
                    components=self.templates.build_components(template, rendered_variables),
                )
            provider_message_id = extract_provider_message_id(payload)
        except ProviderError as exc:
            error_message = sanitize_whatsapp_error(str(exc)) or "WhatsApp send failed"
            message.status = "failed"
            message.error_message = error_message
            message.failed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.crm.record_activity(
                tenant_id=tenant_id,
                lead_id=lead.id,
                contact_id=contact.id,
                activity_type="whatsapp_message_failed",
                title="WhatsApp no enviado",
                outcome="failed",
                deduplication_key=f"whatsapp_failed:{message.id}",
                payload={"message_id": message.id, "status": "failed"},
            )
            self.events.record_event(
                tenant_id=tenant_id,
                provider=self.provider,
                event_type="whatsapp_message_failed",
                status="failed",
                resource_type="crm_whatsapp_message",
                resource_id=message.id,
                message=error_message,
            )
            return WhatsAppSendResult(status="failed", message=message, error_message=error_message)

        message.provider_message_id = provider_message_id
        message.status = "sent"
        message.sent_at = now
        self.db.commit()
        self.db.refresh(message)
        self.crm.record_activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=contact.id,
            activity_type="whatsapp_template_sent",
            title="WhatsApp enviado",
            description=f"Plantilla: {template.name}",
            outcome="sent",
            deduplication_key=f"whatsapp_sent:{message.id}",
            payload={"message_id": message.id, "template_key": template.template_key, "status": "sent"},
        )
        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="whatsapp_message_sent",
            status="success",
            resource_type="crm_whatsapp_message",
            resource_id=message.id,
            metadata={"message_id": provider_message_id},
        )
        return WhatsAppSendResult(status="sent", message=message, provider_message_id=provider_message_id)

    def _sanitize_notification_metadata(self, metadata: dict[str, Any] | None, *, template_key: str) -> dict[str, Any]:
        safe = {
            key: value
            for key, value in (metadata or {}).items()
            if key in _ALLOWED_NOTIFICATION_METADATA_KEYS and isinstance(value, (str, int, float, bool))
        }
        safe["template_key"] = template_key
        return safe

    def send_template_notification(
        self,
        *,
        tenant_id: str,
        to_phone: str,
        template_key: str,
        variables: dict[str, str],
        metadata: dict[str, Any],
        notification_delivery_id: str | None = None,
        lead_id: str | None = None,
        contact_id: str | None = None,
    ) -> WhatsAppSendResult:
        # This method only creates the CrmWhatsAppMessage, calls the provider,
        # and reports the outcome. It must never mutate NotificationDelivery
        # (status/claim_token/claimed_at/claim_expires_at/next_attempt_at):
        # finalizing the delivery is WhatsAppNotificationExecutor's job,
        # since only it knows and can validate the current claim token.
        if notification_delivery_id:
            if not self.notifications.delivery_exists(tenant_id=tenant_id, delivery_id=notification_delivery_id):
                raise ValueError("Notification delivery not found for tenant")

        config, client_config = self.configs.get_active_client_config(tenant_id)
        template = self.templates.get_synced_template(
            tenant_id, template_key=template_key, provider_template_name=None
        )
        components = self.templates.build_approved_template_components(template, variables)

        lead: LeadProfile | None = None
        if lead_id:
            lead = self.crm.get_lead_profile(tenant_id, lead_id)
            if lead is None:
                raise ValueError("Lead not found")

        contact: ContactProfile | None = None
        if contact_id:
            contact = self.crm.get_contact_profile(tenant_id, contact_id)
            if contact is None:
                raise ValueError("Contact not found")

        normalized_phone = normalize_phone(to_phone)
        if not normalized_phone or len(normalized_phone) < 8 or len(normalized_phone) > 32:
            raise ValueError("A valid destination phone is required")

        safe_metadata = self._sanitize_notification_metadata(metadata, template_key=template.template_key)
        body_preview = safe_preview(self.templates.render_template(template, variables))

        message = CrmWhatsAppMessage(
            tenant_id=tenant_id,
            lead_id=lead.id if lead else None,
            contact_id=contact.id if contact else None,
            template_id=template.id,
            template_key=template.template_key,
            direction="outbound",
            to_phone=normalized_phone,
            from_phone=config.display_phone_number,
            message_preview=body_preview,
            status="queued",
            metadata_json=safe_metadata,
            notification_delivery_id=notification_delivery_id,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="whatsapp_notification_requested",
            status="queued",
            resource_type="crm_whatsapp_message",
            resource_id=message.id,
        )

        try:
            payload = self.client.send_template_message(
                client_config,
                to_phone=normalized_phone,
                template_name=template.provider_template_name,
                language=template.language or config.default_language,
                components=components,
            )
            provider_message_id = extract_provider_message_id(payload)
        except ProviderError as exc:
            error_message = sanitize_whatsapp_error(str(exc)) or "WhatsApp send failed"
            message.status = "failed"
            message.error_message = error_message
            message.failed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(message)
            self.events.record_event(
                tenant_id=tenant_id,
                provider=self.provider,
                event_type="whatsapp_notification_failed",
                status="failed",
                resource_type="crm_whatsapp_message",
                resource_id=message.id,
                message=error_message,
            )
            return WhatsAppSendResult(status="failed", message=message, error_message=error_message)

        if not provider_message_id:
            # Meta answered successfully but did not return a usable message
            # id: we cannot tell whether the send actually happened, so the
            # message stays queued and we report manual_review. The caller
            # (executor) decides what that means for the delivery.
            self.db.commit()
            self.db.refresh(message)
            return WhatsAppSendResult(
                status="manual_review", message=message, error_message=MISSING_PROVIDER_MESSAGE_ID_ERROR
            )

        message.provider_message_id = provider_message_id
        message.status = "sent"
        message.sent_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(message)

        if message.lead_id and message.contact_id:
            self.crm.record_activity(
                tenant_id=tenant_id,
                lead_id=message.lead_id,
                contact_id=message.contact_id,
                activity_type="whatsapp_notification_sent",
                title="WhatsApp enviado",
                description=f"Plantilla: {template.name}",
                outcome="sent",
                deduplication_key=f"whatsapp_notification_sent:{message.id}",
                payload={"message_id": message.id, "template_key": template.template_key, "status": "sent"},
            )

        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="whatsapp_notification_sent",
            status="success",
            resource_type="crm_whatsapp_message",
            resource_id=message.id,
            metadata={"message_id": provider_message_id},
        )
        return WhatsAppSendResult(status="sent", message=message, provider_message_id=provider_message_id)

    def send_test_template_message(
        self,
        tenant_id: str,
        request: WhatsAppTestMessageCommand,
    ) -> WhatsAppTestMessageResult:
        phone = normalize_phone(request.to_phone)
        if not phone or len(phone) < 8:
            raise ValueError("A valid destination phone is required")
        config, client_config = self.configs.get_active_client_config(tenant_id)
        template = self.templates.get_synced_template(
            tenant_id,
            template_key=request.template_key,
            provider_template_name=request.provider_template_name,
        )
        parameter_defs = (template.variables_json or {}).get("parameters") or []
        required_keys = [str(item.get("key")) for item in parameter_defs if isinstance(item, dict) and item.get("key")]
        missing = [key for key in required_keys if not request.variables.get(key)]
        if missing:
            raise ValueError(f"Missing template variables: {', '.join(missing)}")
        components = []
        if required_keys:
            components = [{
                "type": "body",
                "parameters": [{"type": "text", "text": request.variables[key]} for key in required_keys],
            }]
        try:
            payload = self.client.send_template_message(
                client_config,
                to_phone=phone,
                template_name=template.provider_template_name,
                language=request.language or template.language or config.default_language,
                components=components,
            )
            provider_message_id = extract_provider_message_id(payload)
        except ProviderError as exc:
            error_message = sanitize_whatsapp_error(str(exc)) or "WhatsApp test message failed"
            self.events.record_event(
                tenant_id=tenant_id,
                provider=self.provider,
                event_type="whatsapp_test_message",
                status="failed",
                message=error_message,
            )
            return WhatsAppTestMessageResult(status="failed", error_message=error_message, to_phone_masked=mask_phone(phone))
        message = CrmWhatsAppMessage(
            tenant_id=tenant_id,
            template_id=template.id,
            template_key=template.template_key,
            direction="outbound",
            to_phone=phone,
            from_phone=config.display_phone_number,
            provider_message_id=provider_message_id,
            status="sent",
            metadata_json={
                "test_message": True,
                "template_key": template.template_key,
                "source": "integration_test_message",
            },
            sent_at=datetime.now(timezone.utc),
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="whatsapp_test_message",
            status="success",
            resource_type="crm_whatsapp_message",
            resource_id=message.id,
            metadata={"template_key": template.template_key, "provider_message_id": provider_message_id},
        )
        return WhatsAppTestMessageResult(
            status="sent",
            whatsapp_message_id=message.id,
            provider_message_id=provider_message_id,
            template_key=template.template_key,
            to_phone_masked=mask_phone(phone),
            message="Mensaje de prueba enviado. El estado final se actualizará por webhook.",
        )

    def list_lead_messages(self, tenant_id: str, lead_id: str) -> list[CrmWhatsAppMessage]:
        self._get_lead(tenant_id, lead_id)
        return self.db.scalars(
            select(CrmWhatsAppMessage)
            .where(CrmWhatsAppMessage.tenant_id == tenant_id, CrmWhatsAppMessage.lead_id == lead_id)
            .order_by(CrmWhatsAppMessage.created_at.desc())
        ).all()

    def handle_events(self, events: Sequence[WhatsAppWebhookEvent]) -> dict[str, int]:
        """Process provider events already parsed by the provider adapter. Events whose
        ``phone_number_id`` matches no tenant are ignored (logged by count, never by content)."""
        configs: dict[str | None, TenantWhatsAppConfig | None] = {}
        ignored = {"status": 0, "inbound": 0}
        statuses = 0
        inbound = 0
        for event in events:
            if event.phone_number_id not in configs:
                configs[event.phone_number_id] = self._config_by_phone_number_id(event.phone_number_id)
            config = configs[event.phone_number_id]
            kind = "status" if isinstance(event, WhatsAppStatusUpdate) else "inbound"
            if config is None:
                ignored[kind] += 1
                continue
            if isinstance(event, WhatsAppStatusUpdate):
                statuses += self._handle_status(config, event)
            else:
                inbound += self._handle_inbound(config, event)
        if ignored["status"]:
            logger.info("WhatsApp status webhook ignored tenant_unresolved count=%s", ignored["status"])
        if ignored["inbound"]:
            logger.info("WhatsApp inbound webhook ignored tenant_unresolved count=%s", ignored["inbound"])
        return {"statuses": statuses, "inbound": inbound}

    def _handle_status(self, config: TenantWhatsAppConfig, event: WhatsAppStatusUpdate) -> int:
        provider_message_id = event.provider_message_id
        status = event.status
        if not provider_message_id or not status:
            return 0
        # FOR UPDATE: two webhooks for the same message (e.g. "delivered" and "read") are serialized, so
        # the loser re-reads the winner's status and cannot move the message backwards.
        message = self.db.scalar(
            select(CrmWhatsAppMessage)
            .where(
                CrmWhatsAppMessage.tenant_id == config.tenant_id,
                CrmWhatsAppMessage.provider_message_id == provider_message_id,
            )
            .with_for_update()
        )
        if message is None:
            return 0
        if not can_advance_status(message.status, status):
            # Out-of-order webhook (a late "delivered" after "read", a late "failed" after "sent") or a status
            # Meta may add that we do not model: ignore it and end the transaction to release the row lock now.
            self.db.commit()
            return 0
        now = datetime.now(timezone.utc)
        message.status = status
        status_error_message = None
        if status == "delivered":
            message.delivered_at = now
        elif status == "read":
            message.read_at = now
        elif status == "failed":
            message.failed_at = now
            status_error_message = sanitize_whatsapp_error(event.error) if event.error else "WhatsApp delivery failed"
            message.error_message = status_error_message
        self.db.commit()
        self.notifications.report_delivery_status(
            tenant_id=config.tenant_id,
            provider_message_id=provider_message_id,
            status=status,
            occurred_at=now,
            error_message=status_error_message,
        )
        self.events.record_event(
            tenant_id=message.tenant_id,
            provider=self.provider,
            event_type=f"whatsapp_status_{status}",
            status="success" if status != "failed" else "failed",
            resource_type="crm_whatsapp_message",
            resource_id=message.id,
        )
        if message.lead_id and message.contact_id:
            self.crm.record_activity(
                tenant_id=message.tenant_id,
                lead_id=message.lead_id,
                contact_id=message.contact_id,
                activity_type=f"whatsapp_status_{status}",
                title=f"WhatsApp {status}",
                outcome=status,
                deduplication_key=f"whatsapp_status:{provider_message_id}:{status}",
                payload={"message_id": message.id, "status": status},
            )
        return 1

    def _handle_inbound(self, config: TenantWhatsAppConfig, event: WhatsAppInboundMessage) -> int:
        from_phone = event.from_phone
        provider_message_id = event.provider_message_id
        contact = self._find_contact(config.tenant_id, from_phone)
        lead = self._find_open_lead(config.tenant_id, contact.id) if contact else None
        if contact is None or lead is None:
            self.events.record_event(
                tenant_id=config.tenant_id,
                provider=self.provider,
                event_type="whatsapp_inbound_unmatched",
                status="ignored",
                resource_type="webhook",
                resource_id=(provider_message_id or "")[:80],
            )
            return 0

        if provider_message_id:
            self._lock_inbound(config.tenant_id, provider_message_id)
        if provider_message_id and self.db.scalar(
            select(CrmWhatsAppMessage.id).where(
                CrmWhatsAppMessage.tenant_id == config.tenant_id,
                CrmWhatsAppMessage.provider_message_id == provider_message_id,
                CrmWhatsAppMessage.direction == "inbound",
            )
        ):
            # Meta retries webhooks: an inbound message already stored is not stored (nor logged) twice.
            # End the transaction so the advisory lock is released immediately.
            self.db.commit()
            return 0

        message = CrmWhatsAppMessage(
            tenant_id=config.tenant_id,
            lead_id=lead.id,
            contact_id=contact.id,
            provider_message_id=provider_message_id,
            direction="inbound",
            from_phone=from_phone,
            to_phone=config.display_phone_number,
            message_preview=safe_preview(event.body),
            status="received",
            metadata_json={},
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        self.crm.record_activity(
            tenant_id=config.tenant_id,
            lead_id=lead.id,
            contact_id=contact.id,
            activity_type="whatsapp_inbound_received",
            title="WhatsApp recibido",
            outcome="received",
            deduplication_key=f"whatsapp_inbound:{provider_message_id or message.id}",
            payload={"message_id": message.id, "status": "received"},
        )
        self.events.record_event(
            tenant_id=config.tenant_id,
            provider=self.provider,
            event_type="whatsapp_inbound_received",
            status="success",
            resource_type="crm_whatsapp_message",
            resource_id=message.id,
        )
        return 1

    def _lock_inbound(self, tenant_id: str, provider_message_id: str) -> None:
        """Serialize concurrent deliveries of the same inbound message until our commit (PostgreSQL only;
        there is no unique constraint on provider_message_id and this change adds no DDL)."""
        if self.db.get_bind().dialect.name != "postgresql":
            return
        self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"wa-inbound:{tenant_id}:{provider_message_id}"},
        )

    def _find_contact(self, tenant_id: str, phone: str | None) -> ContactProfile | None:
        return self.crm.find_contact_by_phone_digits(tenant_id, phone)

    def _config_by_phone_number_id(self, phone_number_id: str | None) -> TenantWhatsAppConfig | None:
        if not phone_number_id:
            return None
        return self.db.scalar(
            select(TenantWhatsAppConfig).where(TenantWhatsAppConfig.phone_number_id == str(phone_number_id))
        )

    def _find_open_lead(self, tenant_id: str, contact_id: str) -> LeadProfile | None:
        return self.crm.get_open_lead_for_contact(tenant_id, contact_id)
