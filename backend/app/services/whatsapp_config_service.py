from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import TenantWhatsAppConfig
from app.schemas.integrations import (
    WhatsAppConfigRequest,
    WhatsAppConfigResponse,
    WhatsAppTemplateSubmitResponse,
    WhatsAppTemplateSyncResponse,
    WhatsAppTestResponse,
)
from app.services.integration_event_service import IntegrationEventService
from app.services.tenant_feature_service import TenantFeatureService, WHATSAPP_BUSINESS_CALLING
from app.services.whatsapp_template_service import WhatsAppTemplateService
from app.services.secret_manager_service import SecretManager
from app.services.whatsapp_client import (
    WhatsAppClientConfig,
    WhatsAppCloudClient,
    WhatsAppCloudClientError,
    sanitize_whatsapp_error,
)


class WhatsAppConfigService:
    provider = "whatsapp_cloud"

    def __init__(self, db: Session, client: WhatsAppCloudClient | None = None) -> None:
        self.db = db
        self.client = client or WhatsAppCloudClient()
        self.secret_manager = SecretManager()
        self.events = IntegrationEventService(db)

    def get_config(self, tenant_id: str) -> TenantWhatsAppConfig | None:
        return self.db.scalar(
            select(TenantWhatsAppConfig).where(
                TenantWhatsAppConfig.tenant_id == tenant_id,
                TenantWhatsAppConfig.provider == self.provider,
            )
        )

    def get_response(self, tenant_id: str) -> WhatsAppConfigResponse:
        config = self.get_config(tenant_id)
        voice_calling_enabled = TenantFeatureService(self.db).is_enabled(tenant_id, WHATSAPP_BUSINESS_CALLING)
        if config is None:
            return WhatsAppConfigResponse(status="inactive", has_secret=False, voice_calling_enabled=voice_calling_enabled)
        return self.to_response(config, voice_calling_enabled=voice_calling_enabled)

    def to_response(self, config: TenantWhatsAppConfig, voice_calling_enabled: bool | None = None) -> WhatsAppConfigResponse:
        if voice_calling_enabled is None:
            voice_calling_enabled = TenantFeatureService(self.db).is_enabled(config.tenant_id, WHATSAPP_BUSINESS_CALLING)
        return WhatsAppConfigResponse(
            status=config.status,
            phone_number_id=config.phone_number_id,
            business_account_id=config.business_account_id,
            display_phone_number=config.display_phone_number,
            default_language=config.default_language,
            has_secret=bool(config.access_token_encrypted),
            has_webhook_secret=bool(config.webhook_verify_token_encrypted),
            voice_calling_enabled=voice_calling_enabled,
            last_health_check_at=config.last_health_check_at,
            last_error_message=config.last_error_message,
        )

    def upsert_config(self, tenant_id: str, request: WhatsAppConfigRequest) -> WhatsAppConfigResponse:
        config = self.get_config(tenant_id)
        if config is None and not request.access_token:
            raise ValueError("WhatsApp access_token is required for first configuration")

        if config is None:
            config = TenantWhatsAppConfig(tenant_id=tenant_id, provider=self.provider)
            self.db.add(config)

        config.status = request.status
        config.phone_number_id = request.phone_number_id.strip()
        config.business_account_id = request.business_account_id.strip() if request.business_account_id else None
        config.display_phone_number = request.display_phone_number
        config.default_language = request.default_language
        config.last_error_message = None
        if request.access_token:
            config.access_token_encrypted = self.secret_manager.encrypt_secret(request.access_token)
        if request.webhook_verify_token:
            config.webhook_verify_token_encrypted = self.secret_manager.encrypt_secret(request.webhook_verify_token)

        self.db.commit()
        self.db.refresh(config)
        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="whatsapp_config_updated",
            status="success",
            resource_type="tenant_whatsapp_config",
            resource_id=config.id,
        )
        return self.to_response(config)

    def get_active_client_config(self, tenant_id: str) -> tuple[TenantWhatsAppConfig, WhatsAppClientConfig]:
        config = self.get_config(tenant_id)
        if config is None or config.status != "active" or not config.access_token_encrypted:
            raise ValueError("WhatsApp integration is not configured")
        token = self.secret_manager.decrypt_secret(config.access_token_encrypted)
        return config, WhatsAppClientConfig(access_token=token, phone_number_id=config.phone_number_id)

    def test_connection(self, tenant_id: str) -> WhatsAppTestResponse:
        config = self.get_config(tenant_id)
        if config is None or not config.access_token_encrypted:
            return WhatsAppTestResponse(status="failed", error_message="WhatsApp integration is not configured")

        try:
            _, client_config = self.get_active_client_config(tenant_id)
            payload = self.client.get_phone_number_info(client_config)
        except (ValueError, WhatsAppCloudClientError) as exc:
            message = sanitize_whatsapp_error(str(exc)) or "WhatsApp test failed"
            config.last_health_check_at = datetime.now(timezone.utc)
            config.last_error_message = message
            self.db.commit()
            self.events.record_event(
                tenant_id=tenant_id,
                provider=self.provider,
                event_type="whatsapp_test_connection",
                status="failed",
                resource_type="tenant_whatsapp_config",
                resource_id=config.id,
                message=message,
            )
            return WhatsAppTestResponse(status="failed", error_message=message)

        display_phone = payload.get("display_phone_number")
        if isinstance(display_phone, str) and display_phone:
            config.display_phone_number = display_phone
        config.last_health_check_at = datetime.now(timezone.utc)
        config.last_error_message = None
        self.db.commit()
        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="whatsapp_test_connection",
            status="success",
            resource_type="tenant_whatsapp_config",
            resource_id=config.id,
        )
        return WhatsAppTestResponse(
            status="success",
            message=(
                "Conexión exitosa con Meta. Se validó el access token y el Phone Number ID. "
                "Esta prueba no envía mensajes."
            ),
            sends_message=False,
        )

    def sync_templates(self, tenant_id: str) -> WhatsAppTemplateSyncResponse:
        config, client_config = self.get_active_client_config(tenant_id)
        business_account_id = (config.business_account_id or "").strip()
        if not business_account_id:
            raise ValueError("Business Account ID / WABA ID is required to sync templates.")
        try:
            payload = self.client.get_message_templates(
                client_config,
                business_account_id=business_account_id,
            )
            templates = payload.get("data") if isinstance(payload.get("data"), list) else []
            result = WhatsAppTemplateService(self.db).sync_approved_templates_from_meta(tenant_id, templates)
        except WhatsAppCloudClientError as exc:
            message = sanitize_whatsapp_error(str(exc)) or "WhatsApp template sync failed"
            self.events.record_event(
                tenant_id=tenant_id,
                provider=self.provider,
                event_type="whatsapp_templates_sync",
                status="failed",
                resource_type="tenant_whatsapp_config",
                resource_id=config.id,
                message=message,
            )
            return WhatsAppTemplateSyncResponse(status="failed", error_message=message)
        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="whatsapp_templates_sync",
            status="success",
            resource_type="tenant_whatsapp_config",
            resource_id=config.id,
            metadata={
                "fetched_count": result.fetched_count,
                "approved_count": result.approved_count,
                "synced_count": result.synced_count,
                "ignored_count": result.ignored_count,
            },
        )
        return WhatsAppTemplateSyncResponse(status="success", **result.__dict__)

    def submit_template(self, tenant_id: str, template_id: str) -> WhatsAppTemplateSubmitResponse:
        config, client_config = self.get_active_client_config(tenant_id)
        business_account_id = (config.business_account_id or "").strip()
        if not business_account_id:
            raise ValueError("Business Account ID / WABA ID is required to submit templates.")
        templates = WhatsAppTemplateService(self.db)
        template = templates.get_owned(tenant_id, template_id)
        if template.status not in ("draft", "rejected"):
            raise ValueError("Only draft or rejected templates can be submitted")
        components = (template.components_json or {}).get("components") or []

        try:
            if template.provider_template_id:
                payload = self.client.update_message_template(
                    client_config, provider_template_id=template.provider_template_id, components=components
                )
            else:
                payload = self.client.create_message_template(
                    client_config,
                    waba_id=business_account_id,
                    name=template.provider_template_name,
                    category=template.category.upper(),
                    language=template.language,
                    components=components,
                    parameter_format=template.parameter_format,
                )
        except WhatsAppCloudClientError as exc:
            message = sanitize_whatsapp_error(str(exc)) or "WhatsApp template submission failed"
            self.events.record_event(
                tenant_id=tenant_id,
                provider=self.provider,
                event_type="whatsapp_template_submit",
                status="failed",
                resource_type="tenant_whatsapp_template",
                resource_id=template.id,
                message=message,
            )
            return WhatsAppTemplateSubmitResponse(status="failed", error_message=message)

        template.provider_template_id = str(payload.get("id") or template.provider_template_id or "") or None
        template.meta_status = str(payload.get("status") or "PENDING").upper()
        template.status = "pending"
        template.last_synced_at = datetime.now(timezone.utc)
        self.db.commit()
        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="whatsapp_template_submit",
            status="success",
            resource_type="tenant_whatsapp_template",
            resource_id=template.id,
        )
        return WhatsAppTemplateSubmitResponse(
            status="success",
            meta_status=template.meta_status,
            provider_template_id=template.provider_template_id,
        )

    def sync_template_status(self, tenant_id: str, template_id: str) -> WhatsAppTemplateSubmitResponse:
        _, client_config = self.get_active_client_config(tenant_id)
        templates = WhatsAppTemplateService(self.db)
        template = templates.get_owned(tenant_id, template_id)
        if not template.provider_template_id:
            raise ValueError("Template has not been submitted to Meta yet")

        try:
            payload = self.client.get_message_template_status(
                client_config, provider_template_id=template.provider_template_id
            )
        except WhatsAppCloudClientError as exc:
            message = sanitize_whatsapp_error(str(exc)) or "WhatsApp template status sync failed"
            self.events.record_event(
                tenant_id=tenant_id,
                provider=self.provider,
                event_type="whatsapp_template_status_sync",
                status="failed",
                resource_type="tenant_whatsapp_template",
                resource_id=template.id,
                message=message,
            )
            return WhatsAppTemplateSubmitResponse(status="failed", error_message=message)

        meta_status = str(payload.get("status") or "").upper()
        template.meta_status = meta_status or template.meta_status
        if meta_status == "APPROVED":
            template.status = "approved"
            template.rejection_reason = None
        elif meta_status == "REJECTED":
            template.status = "rejected"
            template.rejection_reason = sanitize_whatsapp_error(str(payload.get("rejected_reason") or "")) or None
        else:
            template.status = "pending"
        template.last_synced_at = datetime.now(timezone.utc)
        self.db.commit()
        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="whatsapp_template_status_sync",
            status="success",
            resource_type="tenant_whatsapp_template",
            resource_id=template.id,
            metadata={"meta_status": meta_status, "status": template.status},
        )
        return WhatsAppTemplateSubmitResponse(
            status="success",
            meta_status=template.meta_status,
            provider_template_id=template.provider_template_id,
        )
