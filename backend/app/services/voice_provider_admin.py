from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy.orm import Session

from app.modules.voice_providers.public import (
    VoiceProviderNotAvailableError,
    get_provider,
)
from app.schemas.ultravox_admin import (
    UltravoxAgentDetail,
    UltravoxAgentImport,
    UltravoxAgentPage,
    UltravoxVoicePage,
    UltravoxVoiceSummary,
)
from app.services.ultravox_admin_service import UltravoxAdminService
from app.services.ultravox_provider_client import VoicePreviewAudio

if TYPE_CHECKING:  # annotations only: no runtime path back into app.modules
    from app.modules.voice_providers.public import ProviderVoiceSelection


class VoiceProviderAdminService(Protocol):
    """Contract a provider's admin catalog client must implement to plug into
    the /integrations/voice/providers/{provider} routes and the Ultravox
    Admin Workspace UI. Ultravox is the only implementation today; see
    app.modules.voice_providers.domain.registry for the list of providers still pending a
    real adapter."""

    def list_agents(self, tenant_id: str, **filters) -> UltravoxAgentPage: ...
    def get_agent(self, tenant_id: str, agent_id: str) -> UltravoxAgentDetail: ...
    def get_agent_import(self, tenant_id: str, agent_id: str) -> UltravoxAgentImport: ...
    def validate_provider_agent_link(self, tenant_id: str, agent_id: str) -> UltravoxAgentDetail: ...
    def validate_execution_preflight(self, tenant_id: str, agent_id: str) -> UltravoxAgentDetail: ...
    def list_voices(self, tenant_id: str, **filters) -> UltravoxVoicePage: ...
    def get_voice(self, tenant_id: str, voice_id: str) -> UltravoxVoiceSummary: ...
    def preview(self, tenant_id: str, voice_id: str) -> VoicePreviewAudio: ...
    def ensure_external_voice_supported(self, voice: ProviderVoiceSelection) -> None: ...
    def preview_external_voice(self, tenant_id: str, voice: ProviderVoiceSelection) -> VoicePreviewAudio: ...
    def validate_external_voice_credentials(self, tenant_id: str, provider: str) -> None: ...


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
