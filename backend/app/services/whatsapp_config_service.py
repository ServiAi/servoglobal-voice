from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import TenantWhatsAppConfig
from app.schemas.integrations import WhatsAppConfigRequest, WhatsAppConfigResponse, WhatsAppTestResponse
from app.services.integration_event_service import IntegrationEventService
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
        if config is None:
            return WhatsAppConfigResponse(status="inactive", has_secret=False)
        return self.to_response(config)

    def to_response(self, config: TenantWhatsAppConfig) -> WhatsAppConfigResponse:
        return WhatsAppConfigResponse(
            status=config.status,
            phone_number_id=config.phone_number_id,
            business_account_id=config.business_account_id,
            display_phone_number=config.display_phone_number,
            default_language=config.default_language,
            has_secret=bool(config.access_token_encrypted),
            has_webhook_secret=bool(config.webhook_verify_token_encrypted),
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
        config.phone_number_id = request.phone_number_id
        config.business_account_id = request.business_account_id
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
        return WhatsAppTestResponse(status="success")
