from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.modules.analytics.public import AnalyticsAgentDirectory, AnalyticsError
from app.modules.crm.public import CrmFacade
from app.modules.scheduling.public import SchedulingFacade


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
            crm = CrmFacade(self.db)
            context = crm.find_call_context(call_context_id)
            if context:
                lead = crm.get_lead_profile_for_context(context.tenant_id, context.context_id)
                return VoiceBookingContext(
                    tenant_id=context.tenant_id,
                    lead_id=lead.id if lead else None,
                    contact_id=lead.contact_id if lead else None,
                    booking_config_id=self._voice_config_id(context.tenant_id, agent_id),
                )
        if agent_id:
            try:
                agent = AnalyticsAgentDirectory(self.db).resolve_unique_external_agent(agent_id)
            except AnalyticsError:
                agent = None  # no match or ambiguous across tenants: fail closed below
            if agent:
                return VoiceBookingContext(
                    tenant_id=agent.tenant_id,
                    booking_config_id=self._voice_config_id(agent.tenant_id, agent_id),
                )
        if did:
            raise ValueError("DID tenant resolution is not configured yet.")
        raise ValueError("Unable to resolve tenant for voice booking tool.")

    def _voice_config_id(self, tenant_id: str, agent_id: str | None) -> str | None:
        return SchedulingFacade(self.db).find_voice_booking_config_id(tenant_id, agent_id)
