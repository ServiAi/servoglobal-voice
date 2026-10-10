"""Voice Legacy (direct Ultravox flow) -- public API (minimal).

Not migrated: only exposes what Agent Builder still needs from the legacy
TenantVoiceAgentConfig link. The ORM row never leaves this module.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["LegacyVoiceAgentRuntimeConfig", "LegacyVoiceDefaults", "VoiceLegacyFacade"]


# The legacy bridge has always emitted Ultravox catalog voices, whatever
# TenantVoiceAgentConfig.provider says; kept here, with the legacy owner.
_LEGACY_VOICE_PROVIDER = "ultravox"


@dataclass(frozen=True)
class LegacyVoiceDefaults:
    config_id: str
    tenant_id: str
    default_voice: str | None
    agent_provider: str
    voice_provider: str = _LEGACY_VOICE_PROVIDER


@dataclass(frozen=True)
class LegacyVoiceAgentRuntimeConfig:
    config_id: str
    tenant_id: str
    provider: str
    provider_config_id: str | None
    provider_agent_id: str | None
    status: str
    default_voice: str | None


class VoiceLegacyFacade:
    def __init__(self, db: object) -> None:
        self.db = db

    def get_voice_agent_defaults(self, tenant_id: str, config_id: str) -> LegacyVoiceDefaults | None:
        """None if the config does not exist or belongs to another tenant."""
        from app.models.integrations import TenantVoiceAgentConfig

        config = self.db.get(TenantVoiceAgentConfig, config_id)
        if config is None or config.tenant_id != tenant_id:
            return None
        return LegacyVoiceDefaults(
            config_id=config.id,
            tenant_id=config.tenant_id,
            default_voice=config.default_voice,
            agent_provider=config.provider,
        )

    def lock_voice_agent_defaults(
        self, tenant_id: str, config_id: str
    ) -> LegacyVoiceDefaults | None:
        """Serialize changes that could bind one legacy config to two Agents."""
        from sqlalchemy import select

        from app.models.integrations import TenantVoiceAgentConfig

        config = self.db.scalar(
            select(TenantVoiceAgentConfig)
            .where(
                TenantVoiceAgentConfig.id == config_id,
                TenantVoiceAgentConfig.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if config is None:
            return None
        return LegacyVoiceDefaults(
            config_id=config.id,
            tenant_id=config.tenant_id,
            default_voice=config.default_voice,
            agent_provider=config.provider,
        )

    def require_voice_agent_defaults(self, tenant_id: str, config_id: str) -> LegacyVoiceDefaults:
        result = self.get_voice_agent_defaults(tenant_id, config_id)
        if result is None:
            raise ValueError("Voice agent config does not exist or does not belong to this tenant.")
        return result

    def get_runtime_config(
        self, tenant_id: str, config_id: str
    ) -> LegacyVoiceAgentRuntimeConfig | None:
        """Return only the provider-neutral launch fields required by legacy adapters."""
        from app.models.integrations import TenantVoiceAgentConfig

        config = self.db.get(TenantVoiceAgentConfig, config_id)
        if config is None or config.tenant_id != tenant_id:
            return None
        return LegacyVoiceAgentRuntimeConfig(
            config_id=config.id,
            tenant_id=config.tenant_id,
            provider=config.provider,
            provider_config_id=config.provider_config_id,
            provider_agent_id=config.provider_agent_id,
            status=config.status,
            default_voice=config.default_voice,
        )

    def require_runtime_config(
        self, tenant_id: str, config_id: str
    ) -> LegacyVoiceAgentRuntimeConfig:
        config = self.get_runtime_config(tenant_id, config_id)
        if config is None:
            raise ValueError("Voice agent config does not exist or does not belong to this tenant.")
        return config

    def require_active_runtime_config(
        self, tenant_id: str, config_id: str
    ) -> LegacyVoiceAgentRuntimeConfig:
        """Tenant-safe runtime config that must also be ``active`` (public launch paths)."""
        config = self.require_runtime_config(tenant_id, config_id)
        if config.status != "active":
            raise ValueError("Voice agent config is not active.")
        return config
