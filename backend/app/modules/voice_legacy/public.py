"""Voice Legacy (direct Ultravox flow) -- public API (minimal).

Not migrated: only exposes what Agent Builder still needs from the legacy
TenantVoiceAgentConfig link. The ORM row never leaves this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

__all__ = ["LegacyVoiceDefaults", "VoiceLegacyFacade"]


# The legacy bridge has always emitted Ultravox catalog voices, whatever
# TenantVoiceAgentConfig.provider says; kept here, with the legacy owner.
_LEGACY_VOICE_PROVIDER = "ultravox"


@dataclass(frozen=True)
class LegacyVoiceDefaults:
    config_id: str
    tenant_id: str
    default_voice: str | None
    voice_provider: str = _LEGACY_VOICE_PROVIDER


class VoiceLegacyFacade:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_voice_agent_defaults(self, tenant_id: str, config_id: str) -> LegacyVoiceDefaults | None:
        """None if the config does not exist or belongs to another tenant."""
        from app.models.integrations import TenantVoiceAgentConfig

        config = self.db.get(TenantVoiceAgentConfig, config_id)
        if config is None or config.tenant_id != tenant_id:
            return None
        return LegacyVoiceDefaults(config_id=config.id, tenant_id=config.tenant_id, default_voice=config.default_voice)
