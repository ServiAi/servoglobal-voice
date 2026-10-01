"""Provider-agnostic use cases of Voice Providers. Knows adapters only
through VoiceProviderAdapter and errors only as VoiceProviderError."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.voice_providers.domain.contracts import (
    ProviderAgentImport,
    ProviderAgentSnapshot,
    ProviderCredential,
    ProviderVoiceSelection,
)
from app.modules.voice_providers.domain.errors import (
    VoiceProviderError,
    VoiceProviderNotAvailableError,
)
from app.modules.voice_providers.infrastructure import credentials
from app.modules.voice_providers.infrastructure.adapters import get_adapter


class VoiceProviderService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def supports_provider_managed(self, provider: str) -> bool:
        try:
            get_adapter(self.db, provider)
        except VoiceProviderNotAvailableError:
            return False
        return True

    def link_provider_agent(self, tenant_id: str, provider: str, agent_ref: str) -> ProviderAgentSnapshot:
        """Errors surface unchanged (draft save has always let them through)."""
        return get_adapter(self.db, provider).link_agent(tenant_id, agent_ref)

    def validate_provider_execution(self, tenant_id: str, provider: str, agent_ref: str) -> None:
        try:
            get_adapter(self.db, provider).validate_agent_execution(tenant_id, agent_ref)
        except VoiceProviderError:
            raise
        except ValueError as exc:
            raise VoiceProviderError(str(exc)) from exc

    def validate_voice(self, tenant_id: str, realtime_provider: str, voice: ProviderVoiceSelection) -> None:
        try:
            get_adapter(self.db, realtime_provider).check_voice(tenant_id, voice)
        except VoiceProviderError as exc:
            if exc.remote and exc.code == "provider_resource_not_found":
                raise VoiceProviderError("voice_not_accessible") from exc
            raise
        except ValueError as exc:
            raise VoiceProviderError(str(exc)) from exc

    def get_agent_import(self, tenant_id: str, provider: str, agent_ref: str) -> ProviderAgentImport:
        return get_adapter(self.db, provider).get_agent_import(tenant_id, agent_ref)

    def resolve_runtime_credential(self, tenant_id: str, provider: str) -> ProviderCredential:
        """The caller (Voice) has already derived tenant_id from the
        VoiceSession and checked the provider matches it; never pass a
        caller-supplied tenant here. Raises VoiceProviderError
        (``provider_credentials_unavailable``)."""
        return credentials.resolve_credential(self.db, tenant_id, provider)
