"""Tenant provider credentials (TenantVoiceProviderConfig, encrypted). The
storage is provider-agnostic; this is the only reader for the runtime."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.voice_providers.domain.contracts import ProviderCredential
from app.modules.voice_providers.domain.errors import VoiceProviderError


def resolve_credential(db: Session, tenant_id: str, provider: str) -> ProviderCredential:
    from app.services.voice_provider_config_store import VoiceProviderConfigStore

    config_service = VoiceProviderConfigStore(db)
    try:
        config = config_service.get_active_provider_config(tenant_id, provider)
        api_key = config_service.decrypt_api_key(config)
    except ValueError as exc:
        raise VoiceProviderError("provider_credentials_unavailable") from exc
    return ProviderCredential(provider=provider, api_key=api_key, base_url=None)
