"""Voice booking configs (``tenant_voice_booking_configs``) belong to
Scheduling even though they carry "voice" in the name: they say which booking
config / event type / timezone a voice agent's reservations use."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.scheduling.infrastructure.models import TenantVoiceBookingConfig


def find_voice_booking_config_id(db: Session, tenant_id: str, provider_agent_id: str | None) -> str | None:
    if not provider_agent_id:
        return None
    config = db.scalar(
        select(TenantVoiceBookingConfig).where(
            TenantVoiceBookingConfig.tenant_id == tenant_id,
            TenantVoiceBookingConfig.provider_agent_id == provider_agent_id,
            TenantVoiceBookingConfig.status == "active",
        )
    )
    return config.id if config else None
