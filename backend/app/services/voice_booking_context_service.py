from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import Agent
from app.models.crm import CrmCallContext, CrmLead
from app.models.integrations import TenantVoiceBookingConfig


@dataclass(frozen=True)
class VoiceBookingContext:
    tenant_id: str
    lead_id: str | None = None
    contact_id: str | None = None
    booking_config_id: str | None = None


class VoiceBookingContextService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve(
        self,
        *,
        call_context_id: str | None = None,
        agent_id: str | None = None,
        did: str | None = None,
    ) -> VoiceBookingContext:
        if call_context_id:
            context = self.db.scalar(
                select(CrmCallContext).where(
                    (CrmCallContext.id == call_context_id) | (CrmCallContext.context_id == call_context_id)
                )
            )
            if context:
                lead = self.db.scalar(
                    select(CrmLead).where(
                        CrmLead.tenant_id == context.tenant_id,
                        CrmLead.context_id == context.context_id,
                    )
                )
                return VoiceBookingContext(
                    tenant_id=context.tenant_id,
                    lead_id=lead.id if lead else None,
                    contact_id=lead.contact_id if lead else None,
                    booking_config_id=self._voice_config_id(context.tenant_id, agent_id),
                )
        if agent_id:
            agent = self.db.scalar(
                select(Agent).where(
                    Agent.external_agent_id == agent_id,
                    Agent.status == "active",
                )
            )
            if agent:
                return VoiceBookingContext(
                    tenant_id=agent.tenant_id,
                    booking_config_id=self._voice_config_id(agent.tenant_id, agent_id),
                )
        if did:
            raise ValueError("DID tenant resolution is not configured yet.")
        raise ValueError("Unable to resolve tenant for voice booking tool.")

    def _voice_config_id(self, tenant_id: str, agent_id: str | None) -> str | None:
        if not agent_id:
            return None
        config = self.db.scalar(
            select(TenantVoiceBookingConfig).where(
                TenantVoiceBookingConfig.tenant_id == tenant_id,
                TenantVoiceBookingConfig.provider_agent_id == agent_id,
                TenantVoiceBookingConfig.status == "active",
            )
        )
        return config.id if config else None
