from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.domain.voice_registry import get_provider
from app.schemas.ultravox_admin import (
    UltravoxAgentDetail,
    UltravoxAgentPage,
    UltravoxImportResponse,
    UltravoxVoicePage,
    UltravoxVoiceSummary,
)
from app.services.ultravox_admin_service import UltravoxAdminService


class VoiceProviderNotAvailableError(ValueError):
    """Raised when a provider is unknown or not yet wired with a real adapter."""

    def __init__(self, provider_key: str) -> None:
        self.provider_key = provider_key
        super().__init__(f"Voice provider '{provider_key}' is not available.")


class VoiceProviderAdminService(Protocol):
    """Contract a provider's admin catalog client must implement to plug into
    the /integrations/voice/providers/{provider} routes and the Ultravox
    Admin Workspace UI. Ultravox is the only implementation today; see
    app.domain.voice_registry for the list of providers still pending a
    real adapter."""

    def list_agents(self, tenant_id: str, **filters) -> UltravoxAgentPage: ...
    def get_agent(self, tenant_id: str, agent_id: str) -> UltravoxAgentDetail: ...
    def import_agent(self, tenant_id: str, agent_id: str, user_id: str | None) -> UltravoxImportResponse: ...
    def list_voices(self, tenant_id: str, **filters) -> UltravoxVoicePage: ...
    def get_voice(self, tenant_id: str, voice_id: str) -> UltravoxVoiceSummary: ...
    def preview(self, tenant_id: str, voice_id: str) -> bytes: ...


# Add an entry here once a provider has a real adapter backing it (see the
# warning in voice_registry.py about not flipping a provider to "active"
# without one).
_ADAPTERS: dict[str, type[UltravoxAdminService]] = {
    "ultravox": UltravoxAdminService,
}


def get_provider_admin_service(db: Session, provider_key: str) -> VoiceProviderAdminService:
    provider = get_provider(provider_key)
    adapter = _ADAPTERS.get(provider_key)
    if provider is None or provider.status != "active" or adapter is None:
        raise VoiceProviderNotAvailableError(provider_key)
    return adapter(db)
