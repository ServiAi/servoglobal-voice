from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import TenantVoiceProviderConfig
from app.schemas.integrations import VoiceProviderConfigRequest, VoiceProviderConfigResponse
from app.services.secret_manager_service import SecretManager
from app.services.integration_event_service import IntegrationEventService


class VoiceConfigService:
    def __init__(self, db: Session, secret_manager: SecretManager | None = None) -> None:
        self.db = db
        self.secret_manager = secret_manager or SecretManager()
        self.event_service = IntegrationEventService(db)

    def get_provider_config(self, tenant_id: str, provider: str = "ultravox") -> TenantVoiceProviderConfig | None:
        return self.db.scalar(
            select(TenantVoiceProviderConfig).where(
                TenantVoiceProviderConfig.tenant_id == tenant_id,
                TenantVoiceProviderConfig.provider == provider,
            )
        )

    def get_active_provider_config(self, tenant_id: str, provider: str = "ultravox") -> TenantVoiceProviderConfig:
        config = self.get_provider_config(tenant_id, provider)
        if not config or config.status != "active":
            raise ValueError(f"Voice integration '{provider}' is not active for this tenant.")
        if not config.api_key_encrypted:
            raise ValueError(f"Voice provider '{provider}' API key is not configured.")
        return config

    def upsert_provider_config(self, tenant_id: str, body: VoiceProviderConfigRequest) -> TenantVoiceProviderConfig:
        config = self.get_provider_config(tenant_id, body.provider)
        
        is_new = False
        if config is None:
            config = TenantVoiceProviderConfig(tenant_id=tenant_id, provider=body.provider)
            self.db.add(config)
            is_new = True

        if body.api_key:
            config.api_key_encrypted = self.secret_manager.encrypt_secret(body.api_key)
        elif is_new:
            raise ValueError("API key is required for the first integration setup.")

        if body.webhook_secret:
            config.webhook_secret_encrypted = self.secret_manager.encrypt_secret(body.webhook_secret)

        config.status = body.status
        config.display_name = body.display_name or "Voice Integration"
        config.base_url = body.base_url
        config.default_voice_agent_id = body.default_voice_agent_id
        config.default_from_number = body.default_from_number
        config.default_language = body.default_language
        config.default_timezone = body.default_timezone
        config.last_error_message = None

        self.db.commit()
        self.db.refresh(config)

        self.event_service.record_event(
            tenant_id=tenant_id,
            provider=body.provider,
            event_type="config_updated",
            status="success",
            resource_type="config",
            resource_id=config.id,
            metadata={"has_secret": bool(config.api_key_encrypted), "status": config.status},
        )

        return config

    def decrypt_api_key(self, config: TenantVoiceProviderConfig) -> str:
        if not config.api_key_encrypted:
            raise ValueError("API key is not configured for this voice provider.")
        return self.secret_manager.decrypt_secret(config.api_key_encrypted)

    def decrypt_webhook_secret(self, config: TenantVoiceProviderConfig) -> str | None:
        if not config.webhook_secret_encrypted:
            return None
        return self.secret_manager.decrypt_secret(config.webhook_secret_encrypted)

    def test_connection(self, tenant_id: str, provider: str = "ultravox") -> tuple[str, str | None]:
        from app.services.voice_client import VoiceClient, VoiceClientConfig

        config = self.get_active_provider_config(tenant_id, provider)
        client = VoiceClient()
        client_config = VoiceClientConfig(
            provider=config.provider,
            api_key=self.decrypt_api_key(config),
            base_url=config.base_url,
        )

        try:
            headers = {
                "X-API-Key": client_config.api_key,
            }
            base_url = client_config.base_url or "https://api.ultravox.ai"
            url = f"{base_url.rstrip('/')}/api/calls?limit=1"
            import httpx
            with httpx.Client() as client_http:
                response = client_http.get(url, headers=headers, timeout=10.0)
                response.raise_for_status()

            self.mark_health(config, status="active", error_message=None)
            return "active", None
        except Exception as exc:
            message = client.sanitize_voice_error(exc)
            self.mark_health(config, status="error", error_message=message)
            return "error", message

    def mark_health(self, config: TenantVoiceProviderConfig, *, status: str, error_message: str | None = None) -> None:
        config.last_health_check_at = datetime.now(UTC)
        config.last_error_message = error_message
        self.db.commit()

    def get_config_response(self, tenant_id: str, provider: str = "ultravox") -> VoiceProviderConfigResponse:
        config = self.get_provider_config(tenant_id, provider)
        if config is None:
            return VoiceProviderConfigResponse(
                id="",
                provider=provider,
                status="inactive",
                display_name=None,
                base_url=None,
                default_voice_agent_id=None,
                default_from_number=None,
                default_language="es",
                default_timezone="America/Bogota",
                has_secret=False,
                has_webhook_secret=False,
                last_health_check_at=None,
                last_error_message=None,
            )
        return VoiceProviderConfigResponse(
            id=config.id,
            provider=config.provider,
            status=config.status,
            display_name=config.display_name,
            base_url=config.base_url,
            default_voice_agent_id=config.default_voice_agent_id,
            default_from_number=config.default_from_number,
            default_language=config.default_language,
            default_timezone=config.default_timezone,
            has_secret=bool(config.api_key_encrypted),
            has_webhook_secret=bool(config.webhook_secret_encrypted),
            last_health_check_at=config.last_health_check_at,
            last_error_message=config.last_error_message,
        )
