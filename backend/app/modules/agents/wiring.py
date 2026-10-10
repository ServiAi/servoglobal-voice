"""Composition root of Agent Builder: binds its ports to other modules'
public facades. The only file in app.modules.agents allowed to know which
concrete module serves each port."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.agents.application.compiler import AgentCompilerService
from app.modules.agents.application.ports import AgentPorts
from app.modules.agents.application.service import AgentService
from app.modules.integrations.public import WhatsAppFacade
from app.modules.scheduling.public import SchedulingFacade
from app.modules.voice.public import VoiceSessionFacade
from app.modules.voice_experiences.public import create_agent_reference_reader
from app.modules.voice_legacy.public import VoiceLegacyFacade
from app.modules.voice_providers.public import VoiceProviderFacade


class IntegrationReadiness:
    """IntegrationReadinessPort over each integration's own source of truth."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def is_configured(self, tenant_id: str, integration: str | None) -> bool:
        if integration == "booking":
            return SchedulingFacade(self.db).is_booking_configured(tenant_id)
        if integration == "whatsapp":
            return WhatsAppFacade(self.db).is_configured(tenant_id)
        if integration == "crm":
            # CRM is a first-party, always-on capability -- CrmContactService
            # / CrmLeadService operate on the tenant's own DB-native CRM
            # tables and require no external per-tenant integration to
            # configure. crm.create_lead must never be reported unavailable
            # for lack of something that doesn't exist to configure.
            return True
        return integration is None


def default_agent_ports(db: Session) -> AgentPorts:
    return AgentPorts(
        voice_provider=VoiceProviderFacade(db),
        legacy_voice=VoiceLegacyFacade(db),
        integrations=IntegrationReadiness(db),
        voice_sessions=VoiceSessionFacade(db),
        experience_references=create_agent_reference_reader(db),
    )


def agent_compiler(db: Session) -> AgentCompilerService:
    return AgentCompilerService(db, legacy_voice=VoiceLegacyFacade(db))


def agent_service(db: Session) -> AgentService:
    return AgentService(db, default_agent_ports(db))
