"""What a provider adapter must implement to plug into Voice Providers.
Adapters translate their own client errors into VoiceProviderError
(``remote=True``) before returning -- nothing provider-specific may cross
this boundary."""

from __future__ import annotations

from typing import Protocol

from app.modules.voice_providers.domain.contracts import (
    ProviderAgentImport,
    ProviderAgentSnapshot,
    ProviderVoiceSelection,
)


class VoiceProviderAdapter(Protocol):
    def link_agent(self, tenant_id: str, agent_ref: str) -> ProviderAgentSnapshot: ...

    def validate_agent_execution(self, tenant_id: str, agent_ref: str) -> None: ...

    def check_voice(self, tenant_id: str, voice: ProviderVoiceSelection) -> None:
        """Usable now (never generates audio)."""
        ...

    def get_agent_import(self, tenant_id: str, agent_ref: str) -> ProviderAgentImport: ...
