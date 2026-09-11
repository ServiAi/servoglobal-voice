from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderCredential:
    """A realtime provider credential resolved for one VoiceSession.

    Provider-agnostic on purpose: today only "ultravox" is produced, but the
    same shape must work for "elevenlabs", "openai", etc. without changes.
    """

    provider: str
    api_key: str
    base_url: str | None = None


class ProviderCredentialError(Exception):
    """Base class for credential resolution failures. Never carries the secret."""


class ProviderCredentialSessionNotFoundError(ProviderCredentialError):
    """The VoiceSession does not exist, or the provider does not match it."""


class ProviderCredentialNotConfiguredError(ProviderCredentialError):
    """The tenant has no active integration or API key for the provider."""


class ProviderCredentialUnsupportedError(ProviderCredentialError):
    """The requested provider is not a valid platform provider."""


class ProviderCredentialUnavailableError(ProviderCredentialError):
    """The Control Plane could not be reached or returned an unexpected error."""


class ProviderCredentialResolver(Protocol):
    async def resolve(self, *, session_id: str, provider: str) -> ProviderCredential: ...


class _CredentialTransport(Protocol):
    async def get_provider_credential(self, *, session_id: str, provider: str) -> ProviderCredential: ...


class ControlPlaneCredentialResolver:
    """Resolves provider credentials through the Control Plane, scoped to a
    VoiceSession so the runtime is never trusted with a bare tenant_id."""

    def __init__(self, transport: _CredentialTransport) -> None:
        self._transport = transport

    async def resolve(self, *, session_id: str, provider: str) -> ProviderCredential:
        return await self._transport.get_provider_credential(session_id=session_id, provider=provider)
