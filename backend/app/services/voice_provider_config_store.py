"""Tenant voice-provider configuration lookup and secret decryption.

The light, provider-agnostic half of VoiceConfigService: everything the
provider adapters and the runtime credential resolver need, and nothing about
SIP routes. Kept apart so that provider adapters never depend (even
transitively) on Telephony, Voice or Agent Builder.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import TenantVoiceProviderConfig
from app.services.secret_manager_service import SecretManager


class VoiceProviderConfigStore:
    def __init__(self, db: Session, secret_manager: SecretManager | None = None) -> None:
        self.db = db
        self.secret_manager = secret_manager or SecretManager()

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

    def decrypt_api_key(self, config: TenantVoiceProviderConfig) -> str:
        if not config.api_key_encrypted:
            raise ValueError("API key is not configured for this voice provider.")
        return self.secret_manager.decrypt_secret(config.api_key_encrypted)

    def decrypt_webhook_secret(self, config: TenantVoiceProviderConfig) -> str | None:
        if not config.webhook_secret_encrypted:
            return None
        return self.secret_manager.decrypt_secret(config.webhook_secret_encrypted)
