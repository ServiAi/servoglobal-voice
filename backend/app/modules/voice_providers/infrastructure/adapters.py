"""Adapter registry: one VoiceProviderAdapter per provider with a real
implementation. Adding a provider means writing its adapter, registering it
here and marking it active in domain/registry.py; nothing else changes."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.voice_providers.application.ports import VoiceProviderAdapter
from app.modules.voice_providers.domain.errors import VoiceProviderNotAvailableError
from app.modules.voice_providers.domain.registry import get_provider
from app.modules.voice_providers.infrastructure.ultravox import UltravoxProviderAdapter

ADAPTERS: dict[str, type] = {
    "ultravox": UltravoxProviderAdapter,
}


def get_adapter(db: Session, provider_key: str) -> VoiceProviderAdapter:
    provider = get_provider(provider_key)
    adapter = ADAPTERS.get(provider_key)
    if provider is None or provider.status != "active" or adapter is None:
        raise VoiceProviderNotAvailableError(provider_key)
    return adapter(db)
