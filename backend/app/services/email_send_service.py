from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.crm import CrmLead
from app.models.integrations import TenantEmailSend
from app.services.crm_activity_service import CrmActivityService
from app.services.email_asset_service import EmailAssetService
from app.services.email_config_service import EmailConfigService, validate_email
from app.services.email_template_service import EmailTemplateService, RenderedEmailTemplate
from app.services.integration_event_service import IntegrationEventService
from app.services.integration_service import IntegrationService
from app.services.resend_service import ResendService, ResendServiceError, _sanitize_resend_error


@dataclass(frozen=True)
class EmailActionResult:
    status: str
    email_send_id: str | None = None
    provider_email_id: str | None = None
    preview: dict | None = None
    error_message: str | None = None


class EmailSendService:
    def __init__(
        self,
        db: Session,
        resend_service: ResendService | None = None,
    ) -> None:
        self.db = db
        self.resend_service = resend_service or ResendService()
        self.integration_service = IntegrationService(db)
        self.config_service = EmailConfigService(db)
        self.template_service = EmailTemplateService(db)
        self.asset_service = EmailAssetService(db)
        self.event_service = IntegrationEventService(db)
        self.activity_service = CrmActivityService(db)

    def preview_lead_email(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        template_key: str,
        subject: str | None,
        message: str | None,
        asset_ids: list[str] | None,
    ) -> EmailActionResult:
        lead = self._get_lead(tenant_id, lead_id)
        self._require_contact_email(lead)
        self.config_service.get_active_config(tenant_id, "resend")
        self.asset_service.validate_assets(tenant_id, asset_ids)
        rendered = self._render(tenant_id, lead, template_key, subject, message)
        return EmailActionResult(
            status="preview",
            preview={
                "to_email": lead.contact.email,
                "subject": rendered.subject,
                "html": rendered.html,
                "text": rendered.text,
            },
        )

    def send_lead_email(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        template_key: str,
        subject: str | None,
        message: str | None,
        asset_ids: list[str] | None,
    ) -> EmailActionResult:
        lead = self._get_lead(tenant_id, lead_id)
        self._require_contact_email(lead)
        self.activity_service.create_activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            activity_type="email_action_requested",
            title="Email solicitado",
            description="El usuario intento enviar un resumen por email desde el CRM.",
        )
        config = self.config_service.get_active_config(tenant_id, "resend")
        integration = self.integration_service.get_integration(tenant_id, "resend")
        if integration is None or integration.status != "active":
            raise ValueError("Email integration is not configured for this tenant.")
        api_key = self.integration_service.get_secret_value(integration, "api_key")
        assets = self.asset_service.validate_assets(tenant_id, asset_ids)
        attachments = self.asset_service.build_resend_attachments(assets)
        rendered = self._render(tenant_id, lead, template_key, subject, message)
        idempotency_key = f"lead-email:{tenant_id}:{lead_id}:{uuid.uuid4().hex}"
        email_send = TenantEmailSend(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            template_id=rendered.template.id,
            provider="resend",
            to_email=lead.contact.email,
            from_email=config.sender_email,
            subject=rendered.subject,
            status="pending",
            idempotency_key=idempotency_key,
            metadata_json={"template_key": template_key, "attachment_count": len(assets)},
        )
        self.db.add(email_send)
        self.db.commit()
        self.db.refresh(email_send)
        self._record_activity(lead, "email_send_requested", "Email solicitado", email_send.id)

        try:
            provider_email_id = self.resend_service.send_email(
                api_key=api_key,
                from_email=self._format_sender(config.sender_name, config.sender_email),
                to_email=lead.contact.email,
                subject=rendered.subject,
                html=rendered.html,
                text=rendered.text,
                reply_to=config.reply_to,
                attachments=attachments,
                idempotency_key=idempotency_key,
                tenant_id=tenant_id,
                lead_id=lead_id,
                template_key=template_key,
            )
        except ResendServiceError as exc:
            error_message = _sanitize_resend_error(str(exc))
            email_send.status = "failed"
            email_send.error_message = error_message
            self.db.commit()
            self._record_activity(lead, "email_failed", "Email fallido", email_send.id, error_message)
            self.event_service.record_event(
                tenant_id=tenant_id,
                provider="resend",
                event_type="email_send",
                status="failed",
                resource_type="email_send",
                resource_id=email_send.id,
                message=error_message,
                metadata={"template_key": template_key, "attachment_count": len(assets)},
            )
            return EmailActionResult(status="failed", email_send_id=email_send.id, error_message=error_message)

        email_send.status = "sent"
        email_send.provider_email_id = provider_email_id
        email_send.sent_at = datetime.now(UTC)
        self.db.commit()
        self._record_activity(lead, "email_sent", "Email enviado", email_send.id)
        self.event_service.record_event(
            tenant_id=tenant_id,
            provider="resend",
            event_type="email_send",
            status="success",
            resource_type="email_send",
            resource_id=email_send.id,
            metadata={"template_key": template_key, "attachment_count": len(assets)},
        )
        return EmailActionResult(
            status="sent",
            email_send_id=email_send.id,
            provider_email_id=provider_email_id,
        )

    def send_test_email(self, *, tenant_id: str, to_email: str) -> EmailActionResult:
        to_email = validate_email(to_email, "to_email")
        config = self.config_service.get_active_config(tenant_id, "resend")
        integration = self.integration_service.get_integration(tenant_id, "resend")
        if integration is None or integration.status != "active":
            raise ValueError("Email integration is not configured for this tenant.")
        api_key = self.integration_service.get_secret_value(integration, "api_key")
        try:
            provider_email_id = self.resend_service.send_test_email(
                api_key=api_key,
                from_email=self._format_sender(config.sender_name, config.sender_email),
                to_email=to_email,
                reply_to=config.reply_to,
                tenant_id=tenant_id,
            )
        except ResendServiceError as exc:
            error_message = _sanitize_resend_error(str(exc))
            self.config_service.mark_health(config, status="error", error_message=error_message)
            self.integration_service.mark_health(integration, status="error", error_message=error_message)
            self.event_service.record_event(
                tenant_id=tenant_id,
                provider="resend",
                event_type="test_email",
                status="failed",
                resource_type="config",
                resource_id=integration.id,
                message=error_message,
            )
            return EmailActionResult(status="failed", provider_email_id=None, error_message=error_message)
        self.config_service.mark_health(config, status="active")
        self.integration_service.mark_health(integration, status="active")
        self.event_service.record_event(
            tenant_id=tenant_id,
            provider="resend",
            event_type="test_email",
            status="success",
            resource_type="config",
            resource_id=integration.id,
        )
        return EmailActionResult(status="sent", provider_email_id=provider_email_id)

    def _get_lead(self, tenant_id: str, lead_id: str) -> CrmLead:
        lead = self.db.scalar(
            select(CrmLead)
            .options(joinedload(CrmLead.contact))
            .where(CrmLead.tenant_id == tenant_id, CrmLead.id == lead_id)
        )
        if lead is None:
            raise ValueError("Lead not found")
        return lead

    def _require_contact_email(self, lead: CrmLead) -> None:
        if not lead.contact or not (lead.contact.email or "").strip():
            raise ValueError("Lead does not have an email address.")

    def _render(
        self,
        tenant_id: str,
        lead: CrmLead,
        template_key: str,
        subject: str | None,
        message: str | None,
    ) -> RenderedEmailTemplate:
        return self.template_service.render_template(
            tenant_id=tenant_id,
            template_key=template_key,
            lead=lead,
            subject_override=subject,
            message_override=message,
        )

    def _record_activity(
        self,
        lead: CrmLead,
        activity_type: str,
        title: str,
        email_send_id: str,
        description: str | None = None,
    ) -> None:
        self.activity_service.create_activity(
            tenant_id=lead.tenant_id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            activity_type=activity_type,
            title=title,
            description=description,
            payload_json={"email_send_id": email_send_id, "provider": "resend"},
        )

    def _format_sender(self, sender_name: str | None, sender_email: str) -> str:
        if sender_name:
            return f"{sender_name} <{sender_email}>"
        return sender_email
