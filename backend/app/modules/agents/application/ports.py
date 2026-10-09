"""What Agent Builder needs from other modules, phrased as its own business
needs (not as any provider's API). ``app.modules.agents.wiring`` binds
them to the owners' public facades; tests can pass plain fakes, including
a provider that is not Ultravox.

Every DTO is a frozen provider-agnostic value from ``voice_providers.public``
or ``voice_legacy.public`` -- never an SDK/provider object or an ORM row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.modules.voice_legacy.public import LegacyVoiceDefaults
from app.modules.voice_providers.public import (
    ProviderAgentSnapshot,
    ProviderVoiceSelection,
)


class VoiceProviderPort(Protocol):
    """Errors: ``voice_providers.public.VoiceProviderError`` (``.code`` is
    stable and safe to show)."""

    def supports_provider_managed(self, provider: str) -> bool: ...

    def link_provider_agent(self, tenant_id: str, provider: str, agent_ref: str) -> ProviderAgentSnapshot:
        """Draft save of a provider_managed agent: the remote agent must be
        reachable with this tenant's credentials."""
        ...

    def validate_provider_execution(self, tenant_id: str, provider: str, agent_ref: str) -> None:
        """Publish of a provider_managed agent: the remote agent must be
        executable by ServiGlobal (e.g. no client-side tools)."""
        ...

    def validate_voice(self, tenant_id: str, realtime_provider: str, voice: ProviderVoiceSelection) -> None:
        """Publish of a serviglobal_managed agent: the selected voice must be
        usable now. Never generates audio."""
        ...


class LegacyVoicePort(Protocol):
    def get_voice_agent_defaults(self, tenant_id: str, config_id: str) -> LegacyVoiceDefaults | None:
        """None if the legacy config does not exist or belongs to another tenant."""
        ...

    def lock_voice_agent_defaults(self, tenant_id: str, config_id: str) -> LegacyVoiceDefaults | None:
        """Lock the legacy config row while an Agent binding is changed."""
        ...


class IntegrationReadinessPort(Protocol):
    """Whether a platform tool's required integration is operational for a
    tenant -- answered by each integration's own source of truth."""

    def is_configured(self, tenant_id: str, integration: str | None) -> bool: ...


class VoiceSessionsPort(Protocol):
    async def release_sessions_of_deleted_agent(self, tenant_id: str, agent_id: str) -> None:
        """Closes live rooms, cancels and detaches the agent's sessions in the
        caller's transaction (no commit). Raises VoiceSessionsBusyError."""
        ...


@dataclass(frozen=True)
class AgentPorts:
    voice_provider: VoiceProviderPort
    legacy_voice: LegacyVoicePort
    integrations: IntegrationReadinessPort
    voice_sessions: VoiceSessionsPort
