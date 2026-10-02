"""Voice Providers -- public API.

Provider registry (realtime providers, models, capabilities, parameters,
voice compatibility), provider-agnostic operations on a tenant's provider,
and runtime credential resolution. A sibling of Voice Orchestration, not
part of it: it depends on neither sessions nor Agent Builder, so provider
adapters can never sit on an import path back into them.

Top-level imports are pure domain only; use cases load lazily. Nothing here
knows a concrete provider or its client errors -- adapters translate those
into VoiceProviderError (app.modules.voice_providers.infrastructure).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.voice_providers.domain.contracts import (
    ProviderAgentImport,
    ProviderAgentSnapshot,
    ProviderConfigRef,
    ProviderCredential,
    ProviderToolRef,
    ProviderVoiceSelection,
)
from app.modules.voice_providers.domain.errors import (
    VoiceProviderError,
    VoiceProviderNotAvailableError,
)
from app.modules.voice_providers.domain.registry import (
    VoiceModel,
    VoiceProvider,
    VoiceRegistryValidationError,
    get_model,
    get_provider,
    list_models,
    list_providers,
    resolve_execution_model_id,
    validate_model_settings,
    validate_runtime_selection,
    validate_voice_compatibility,
)

__all__ = [
    "ProviderAgentImport",
    "ProviderAgentSnapshot",
    "ProviderConfigRef",
    "ProviderCredential",
    "ProviderToolRef",
    "ProviderVoiceSelection",
    "VoiceModel",
    "VoiceProvider",
    "VoiceProviderError",
    "VoiceProviderFacade",
    "VoiceProviderNotAvailableError",
    "VoiceRegistryValidationError",
    "get_model",
    "get_provider",
    "is_known_provider",
    "list_models",
    "list_providers",
    "resolve_execution_model_id",
    "validate_model_settings",
    "validate_runtime_selection",
    "validate_voice_compatibility",
]


def is_known_provider(provider_key: str) -> bool:
    return get_provider(provider_key) is not None


class VoiceProviderFacade:
    """Provider-agnostic operations, routed through the adapter registry."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _service(self):
        from app.modules.voice_providers.application.service import VoiceProviderService

        return VoiceProviderService(self.db)

    def supports_provider_managed(self, provider: str) -> bool:
        return self._service().supports_provider_managed(provider)

    def link_provider_agent(self, tenant_id: str, provider: str, agent_ref: str) -> ProviderAgentSnapshot:
        return self._service().link_provider_agent(tenant_id, provider, agent_ref)

    def validate_provider_execution(self, tenant_id: str, provider: str, agent_ref: str) -> None:
        """Raises VoiceProviderError."""
        self._service().validate_provider_execution(tenant_id, provider, agent_ref)

    def validate_voice(self, tenant_id: str, realtime_provider: str, voice: ProviderVoiceSelection) -> None:
        """Raises VoiceProviderError (``voice_not_accessible`` when the
        provider no longer has the voice)."""
        self._service().validate_voice(tenant_id, realtime_provider, voice)

    def get_agent_import(self, tenant_id: str, provider: str, agent_ref: str) -> ProviderAgentImport:
        """Raises VoiceProviderError (``remote`` for provider-side failures)."""
        return self._service().get_agent_import(tenant_id, provider, agent_ref)

    def resolve_runtime_credential(self, tenant_id: str, provider: str) -> ProviderCredential:
        """For the runtime credential endpoint only, after Voice has bound the
        request to a VoiceSession. Raises VoiceProviderError."""
        return self._service().resolve_runtime_credential(tenant_id, provider)
