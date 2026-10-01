"""Ultravox implementation of VoiceProviderAdapter.

The only Voice Providers file that knows Ultravox: it wraps the legacy
UltravoxAdminService (also used by the Ultravox admin workspace API) and
translates UltravoxProviderError into VoiceProviderError before anything
leaves this adapter.
"""

from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import TypeVar

from sqlalchemy.orm import Session

from app.modules.voice_providers.domain.contracts import (
    ProviderAgentImport,
    ProviderAgentSnapshot,
    ProviderToolRef,
    ProviderVoiceSelection,
)
from app.modules.voice_providers.domain.errors import VoiceProviderError

PROVIDER = "ultravox"
T = TypeVar("T")


class UltravoxProviderAdapter:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _call(operation: Callable[[], T]) -> T:
        from app.services.ultravox_provider_client import UltravoxProviderError

        try:
            return operation()
        except UltravoxProviderError as exc:
            raise VoiceProviderError(exc.code, remote=True, reason=exc.reason) from exc

    def _admin(self):
        from app.services.ultravox_admin_service import UltravoxAdminService

        return UltravoxAdminService(self.db)

    @staticmethod
    def _tools(tools) -> tuple[ProviderToolRef, ...]:
        return tuple(ProviderToolRef(name=t.name, classification=t.classification) for t in tools)

    def link_agent(self, tenant_id: str, agent_ref: str) -> ProviderAgentSnapshot:
        remote = self._call(lambda: self._admin().validate_provider_agent_link(tenant_id, agent_ref))
        return ProviderAgentSnapshot(
            provider=PROVIDER,
            agent_ref=remote.agent_id,
            revision_ref=remote.published_revision_id,
            tools=self._tools(remote.tools),
            has_unsupported_client_tools=bool(remote.has_unsupported_client_tools),
        )

    def validate_agent_execution(self, tenant_id: str, agent_ref: str) -> None:
        self._call(lambda: self._admin().validate_execution_preflight(tenant_id, agent_ref))

    def check_voice(self, tenant_id: str, voice: ProviderVoiceSelection) -> None:
        admin = self._admin()
        if voice.mode == "provider":
            self._call(lambda: admin.get_voice(tenant_id, voice.voice_id))
        else:
            self._call(lambda: admin.validate_external_voice_credentials(tenant_id, voice.provider))

    def get_agent_import(self, tenant_id: str, agent_ref: str) -> ProviderAgentImport:
        remote = self._call(lambda: self._admin().get_agent_import(tenant_id, agent_ref))
        return ProviderAgentImport(
            provider=PROVIDER,
            provider_agent_id=remote.provider_agent_id,
            provider_revision_id=remote.provider_revision_id,
            name=remote.name,
            language=remote.language,
            system_prompt=remote.system_prompt,
            model=remote.model,
            voice_id=remote.voice_id,
            tools=self._tools(remote.tools),
            provider_settings=MappingProxyType(dict(remote.provider_settings)),
        )
