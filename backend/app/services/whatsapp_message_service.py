from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.crm import CrmActivity, CrmContact, CrmLead, CrmWhatsAppMessage
from app.models.integrations import TenantWhatsAppConfig
from app.schemas.crm import WhatsAppActionRequest, WhatsAppActionResponse
from app.schemas.integrations import WhatsAppTestMessageRequest, WhatsAppTestMessageResponse
from app.services.crm_activity_service import CrmActivityService
from app.services.integration_event_service import IntegrationEventService
from app.services.whatsapp_client import WhatsAppCloudClient, WhatsAppCloudClientError, sanitize_whatsapp_error
from app.services.whatsapp_config_service import WhatsAppConfigService
from app.services.whatsapp_template_service import WhatsAppTemplateService


logger = logging.getLogger(__name__)


@dataclass
class WhatsAppSendResult:
    status: str
    message: CrmWhatsAppMessage | None = None
    provider_message_id: str | None = None
    preview: dict[str, Any] | None = None
    error_message: str | None = None


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits or None


def safe_preview(value: str | None) -> str | None:
    if value is None:
        return None
    return value.replace("\r", " ").replace("\n", " ")[:240]


def mask_phone(phone: str) -> str:
    digits = normalize_phone(phone) or ""
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"


def extract_provider_message_id(payload: dict[str, Any]) -> str | None:
    messages = payload.get("messages")
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        value = messages[0].get("id")
        return value if isinstance(value, str) else None
    return None


class WhatsAppMessageService:
    provider = "whatsapp_cloud"

    def __init__(self, db: Session, client: WhatsAppCloudClient | None = None) -> None:
        self.db = db
        self.client = client or WhatsAppCloudClient()
        self.configs = WhatsAppConfigService(db, client=self.client)
        self.templates = WhatsAppTemplateService(db)
        self.events = IntegrationEventService(db)
        self.activities = CrmActivityService(db)

    def _get_lead(self, tenant_id: str, lead_id: str) -> CrmLead:
        lead = self.db.scalar(
            select(CrmLead)
            .options(joinedload(CrmLead.contact))
            .where(CrmLead.tenant_id == tenant_id, CrmLead.id == lead_id)
        )
        if lead is None:
            raise ValueError("Lead not found")
        return lead

    def _lead_variables(self, lead: CrmLead, request: WhatsAppActionRequest) -> dict[str, Any]:
        contact = lead.contact
        return {
            "contact_name": contact.name,
            "agent_name": "ServiGlobal AI",
            "interest": lead.interest or lead.use_case or "nuestros servicios",
            **request.variables,
        }

    def preview_lead_whatsapp(self, tenant_id: str, lead_id: str, request: WhatsAppActionRequest) -> WhatsAppSendResult:
        lead = self._get_lead(tenant_id, lead_id)
        phone = lead.contact.phone or lead.contact.phone_normalized
        if not phone:
            raise ValueError("Lead contact does not have a phone number")
        template = self.templates.get_template(tenant_id, request.template_key)
        variables = self._lead_variables(lead, request)
        body = request.message or self.templates.render_template(template, variables)
        return WhatsAppSendResult(
            status="preview",
            preview={
                "to_phone": phone,
                "template_key": template.template_key,
                "provider_template_name": template.provider_template_name,
                "message": body,
                "variables": variables,
            },
        )

    def send_lead_whatsapp(self, tenant_id: str, lead_id: str, request: WhatsAppActionRequest) -> WhatsAppSendResult:
        lead = self._get_lead(tenant_id, lead_id)
        contact = lead.contact
        phone = contact.phone or contact.phone_normalized
        if not phone:
            raise ValueError("Lead contact does not have a phone number")

        config, client_config = self.configs.get_active_client_config(tenant_id)
        template = self.templates.get_template(tenant_id, request.template_key)
        variables = self._lead_variables(lead, request)
        body = request.message or self.templates.render_template(template, variables)
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
            if request.message:
                payload = self.client.send_text_message(client_config, to_phone=phone, message=body)
            else:
                payload = self.client.send_template_message(
                    client_config,
                    to_phone=phone,
                    template_name=template.provider_template_name,
                    language=template.language or config.default_language,
                    components=self.templates.build_components(template, variables),
                )
            provider_message_id = extract_provider_message_id(payload)
        except WhatsAppCloudClientError as exc:
            error_message = sanitize_whatsapp_error(str(exc)) or "WhatsApp send failed"
            message.status = "failed"
            message.error_message = error_message
            message.failed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.activities.create_activity(
                tenant_id=tenant_id,
                lead_id=lead.id,
                contact_id=contact.id,
                activity_type="whatsapp_message_failed",
                title="WhatsApp no enviado",
                outcome="failed",
                deduplication_key=f"whatsapp_failed:{message.id}",
                payload_json={"message_id": message.id, "status": "failed"},
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
        self.activities.create_activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=contact.id,
            activity_type="whatsapp_template_sent",
            title="WhatsApp enviado",
            description=f"Plantilla: {template.name}",
            outcome="sent",
            deduplication_key=f"whatsapp_sent:{message.id}",
            payload_json={"message_id": message.id, "template_key": template.template_key, "status": "sent"},
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

    def send_test_template_message(
        self,
        tenant_id: str,
        request: WhatsAppTestMessageRequest,
    ) -> WhatsAppTestMessageResponse:
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
        except WhatsAppCloudClientError as exc:
            error_message = sanitize_whatsapp_error(str(exc)) or "WhatsApp test message failed"
            self.events.record_event(
                tenant_id=tenant_id,
                provider=self.provider,
                event_type="whatsapp_test_message",
                status="failed",
                message=error_message,
            )
            return WhatsAppTestMessageResponse(status="failed", error_message=error_message, to_phone_masked=mask_phone(phone))
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
        return WhatsAppTestMessageResponse(
            status="sent",
            whatsapp_message_id=message.id,
            provider_message_id=provider_message_id,
            template_key=template.template_key,
            to_phone_masked=mask_phone(phone),
            message="Mensaje de prueba enviado. El estado final se actualizará por webhook.",
        )

    def action_response(self, result: WhatsAppSendResult) -> WhatsAppActionResponse:
        return WhatsAppActionResponse(
            status=result.status,
            whatsapp_message_id=result.message.id if result.message else None,
            provider_message_id=result.provider_message_id,
            preview=result.preview,
            error_message=result.error_message,
        )

    def list_lead_messages(self, tenant_id: str, lead_id: str) -> list[CrmWhatsAppMessage]:
        self._get_lead(tenant_id, lead_id)
        return self.db.scalars(
            select(CrmWhatsAppMessage)
            .where(CrmWhatsAppMessage.tenant_id == tenant_id, CrmWhatsAppMessage.lead_id == lead_id)
            .order_by(CrmWhatsAppMessage.created_at.desc())
        ).all()

    def handle_webhook_payload(self, payload: dict[str, Any]) -> dict[str, int]:
        statuses = 0
        inbound = 0
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                statuses += self._handle_statuses(value)
                inbound += self._handle_inbound(value)
        return {"statuses": statuses, "inbound": inbound}

    def _handle_statuses(self, value: dict[str, Any]) -> int:
        config = self._config_from_value(value)
        if config is None:
            statuses = value.get("statuses") or []
            if statuses:
                logger.info("WhatsApp status webhook ignored tenant_unresolved count=%s", len(statuses))
            return 0

        count = 0
        for item in value.get("statuses") or []:
            provider_message_id = item.get("id")
            status = item.get("status")
            if not provider_message_id or not status:
                continue
            message = self.db.scalar(
                select(CrmWhatsAppMessage).where(
                    CrmWhatsAppMessage.tenant_id == config.tenant_id,
                    CrmWhatsAppMessage.provider_message_id == provider_message_id,
                )
            )
            if message is None:
                continue
            now = datetime.now(timezone.utc)
            message.status = status
            if status == "delivered":
                message.delivered_at = now
            elif status == "read":
                message.read_at = now
            elif status == "failed":
                message.failed_at = now
                error = item.get("errors")
                message.error_message = sanitize_whatsapp_error(str(error)) if error else "WhatsApp delivery failed"
            self.db.commit()
            self.events.record_event(
                tenant_id=message.tenant_id,
                provider=self.provider,
                event_type=f"whatsapp_status_{status}",
                status="success" if status != "failed" else "failed",
                resource_type="crm_whatsapp_message",
                resource_id=message.id,
            )
            if message.lead_id and message.contact_id:
                self.activities.create_activity(
                    tenant_id=message.tenant_id,
                    lead_id=message.lead_id,
                    contact_id=message.contact_id,
                    activity_type=f"whatsapp_status_{status}",
                    title=f"WhatsApp {status}",
                    outcome=status,
                    deduplication_key=f"whatsapp_status:{provider_message_id}:{status}",
                    payload_json={"message_id": message.id, "status": status},
                )
            count += 1
        return count

    def _handle_inbound(self, value: dict[str, Any]) -> int:
        config = self._config_from_value(value)
        if config is None:
            messages = value.get("messages") or []
            if messages:
                logger.info("WhatsApp inbound webhook ignored tenant_unresolved count=%s", len(messages))
            return 0

        count = 0
        for item in value.get("messages") or []:
            from_phone = item.get("from")
            provider_message_id = item.get("id")
            body = ((item.get("text") or {}).get("body")) if isinstance(item.get("text"), dict) else None
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
                continue

            message = CrmWhatsAppMessage(
                tenant_id=config.tenant_id,
                lead_id=lead.id,
                contact_id=contact.id,
                provider_message_id=provider_message_id,
                direction="inbound",
                from_phone=from_phone,
                to_phone=config.display_phone_number,
                message_preview=safe_preview(body),
                status="received",
                metadata_json={},
            )
            self.db.add(message)
            self.db.commit()
            self.db.refresh(message)
            self.activities.create_activity(
                tenant_id=config.tenant_id,
                lead_id=lead.id,
                contact_id=contact.id,
                activity_type="whatsapp_inbound_received",
                title="WhatsApp recibido",
                outcome="received",
                deduplication_key=f"whatsapp_inbound:{provider_message_id or message.id}",
                payload_json={"message_id": message.id, "status": "received"},
            )
            self.events.record_event(
                tenant_id=config.tenant_id,
                provider=self.provider,
                event_type="whatsapp_inbound_received",
                status="success",
                resource_type="crm_whatsapp_message",
                resource_id=message.id,
            )
            count += 1
        return count

    def _find_contact(self, tenant_id: str, phone: str | None) -> CrmContact | None:
        normalized = normalize_phone(phone)
        if not normalized:
            return None
        contacts = self.db.scalars(select(CrmContact).where(CrmContact.tenant_id == tenant_id)).all()
        for contact in contacts:
            if normalize_phone(contact.phone_normalized) == normalized or normalize_phone(contact.phone) == normalized:
                return contact
        return None

    def _config_from_value(self, value: dict[str, Any]) -> TenantWhatsAppConfig | None:
        metadata = value.get("metadata") or {}
        phone_number_id = metadata.get("phone_number_id")
        if not phone_number_id:
            return None
        return self.db.scalar(
            select(TenantWhatsAppConfig).where(TenantWhatsAppConfig.phone_number_id == str(phone_number_id))
        )

    def _find_open_lead(self, tenant_id: str, contact_id: str) -> CrmLead | None:
        return self.db.scalar(
            select(CrmLead)
            .where(CrmLead.tenant_id == tenant_id, CrmLead.contact_id == contact_id, CrmLead.status == "open")
            .order_by(CrmLead.created_at.desc())
        )
