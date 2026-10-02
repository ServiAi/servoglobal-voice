"""Provider-agnostic values exchanged with Voice Providers. No provider
SDK/DTO, no ORM row, no secret (except ProviderCredential, which only the
runtime credential endpoint ever sees)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class ProviderToolRef:
    name: str
    classification: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "classification": self.classification}


@dataclass(frozen=True)
class ProviderAgentSnapshot:
    provider: str
    agent_ref: str
    revision_ref: str | None
    tools: tuple[ProviderToolRef, ...]
    has_unsupported_client_tools: bool


@dataclass(frozen=True)
class ProviderVoiceSelection:
    mode: str
    provider: str
    voice_id: str
    settings: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class ProviderAgentImport:
    """Everything a provider-side agent contributes to a ServiGlobal draft.
    Values are already sanitized by the provider adapter; no secrets."""

    provider: str
    provider_agent_id: str
    provider_revision_id: str | None
    name: str
    language: str | None
    system_prompt: str
    model: str
    voice_id: str | None
    tools: tuple[ProviderToolRef, ...]
    provider_settings: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class ProviderCredential:
    """A tenant's provider credential, resolved for one VoiceSession. Lives
    in memory only; never persisted, logged or put in a runtime spec."""

    provider: str
    api_key: str = field(repr=False)
    base_url: str | None = None


@dataclass(frozen=True)
class ProviderConfigRef:
    """Identity of a tenant's provider configuration, for modules that only
    need to reference it (e.g. a SIP route belongs to one provider config).
    Never the TenantVoiceProviderConfig row, never a credential."""

    id: str
    tenant_id: str
    provider: str
