"""Voice Providers -- public API (provider registry + provider-agnostic
operations on a tenant's realtime voice provider).

Separate from Voice Orchestration on purpose: it must not depend on
sessions or on Agent Builder, so provider adapters (Ultravox today) can
never sit on an import path back into Agent Builder. Boundary only: the
implementation still lives in app.domain.voice_registry,
app.services.voice_provider_admin and the Ultravox adapter.
Nothing returned here is a provider SDK/DTO, an ORM row or a secret.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from sqlalchemy.orm import Session

from app.domain.voice_registry import (
    VoiceRegistryValidationError,
    resolve_execution_model_id,
    validate_model_settings,
    validate_runtime_selection,
    validate_voice_compatibility,
)

__all__ = [
    "ProviderAgentImport",
    "ProviderAgentSnapshot",
    "ProviderToolRef",
    "ProviderVoiceSelection",
    "VoiceProviderError",
    "VoiceProviderFacade",
    "VoiceRegistryValidationError",
    "resolve_execution_model_id",
    "validate_model_settings",
    "validate_runtime_selection",
    "validate_voice_compatibility",
]


class VoiceProviderError(ValueError):
    """Provider-agnostic failure; ``.code`` (== ``str(exc)``) is stable."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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


def _tool_refs(tools: Any) -> tuple[ProviderToolRef, ...]:
    return tuple(ProviderToolRef(name=t.name, classification=t.classification) for t in tools)


def _provider_error(exc: Exception) -> VoiceProviderError:
    code = getattr(exc, "code", None)
    return VoiceProviderError(code if isinstance(code, str) else str(exc))


class VoiceProviderFacade:
    """Provider-agnostic operations, routed through the provider registry
    (one adapter per active provider)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _adapter(self, provider: str):
        from app.services.voice_provider_admin import get_provider_admin_service

        return get_provider_admin_service(self.db, provider)

    @staticmethod
    def _errors() -> tuple[type[Exception], ...]:
        from app.services.ultravox_provider_client import UltravoxProviderError

        return (ValueError, UltravoxProviderError)

    def supports_provider_managed(self, provider: str) -> bool:
        from app.services.voice_provider_admin import VoiceProviderNotAvailableError

        try:
            self._adapter(provider)
        except VoiceProviderNotAvailableError:
            return False
        return True

    def link_provider_agent(self, tenant_id: str, provider: str, agent_ref: str) -> ProviderAgentSnapshot:
        """Raises the adapter's own errors unchanged: draft save has always
        surfaced them as-is."""
        remote = self._adapter(provider).validate_provider_agent_link(tenant_id, agent_ref)
        return ProviderAgentSnapshot(
            provider=provider,
            agent_ref=remote.agent_id,
            revision_ref=remote.published_revision_id,
            tools=_tool_refs(remote.tools),
            has_unsupported_client_tools=bool(remote.has_unsupported_client_tools),
        )

    def validate_provider_execution(self, tenant_id: str, provider: str, agent_ref: str) -> None:
        try:
            self._adapter(provider).validate_execution_preflight(tenant_id, agent_ref)
        except self._errors() as exc:
            raise _provider_error(exc) from exc

    def validate_voice(self, tenant_id: str, realtime_provider: str, voice: ProviderVoiceSelection) -> None:
        try:
            adapter = self._adapter(realtime_provider)
            if voice.mode == "provider":
                adapter.get_voice(tenant_id, voice.voice_id)
            else:
                adapter.validate_external_voice_credentials(tenant_id, voice.provider)
        except self._errors() as exc:
            error = _provider_error(exc)
            if not isinstance(exc, ValueError) and error.code == "provider_resource_not_found":
                error = VoiceProviderError("voice_not_accessible")
            raise error from exc

    def get_agent_import(self, tenant_id: str, provider: str, agent_ref: str) -> ProviderAgentImport:
        """Raises the adapter's own errors unchanged (the HTTP adapter maps them)."""
        remote = self._adapter(provider).get_agent_import(tenant_id, agent_ref)
        return ProviderAgentImport(
            provider=provider,
            provider_agent_id=remote.provider_agent_id,
            provider_revision_id=remote.provider_revision_id,
            name=remote.name,
            language=remote.language,
            system_prompt=remote.system_prompt,
            model=remote.model,
            voice_id=remote.voice_id,
            tools=_tool_refs(remote.tools),
            provider_settings=MappingProxyType(dict(remote.provider_settings)),
        )
