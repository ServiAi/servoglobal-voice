"""
services/voice_handoff_service.py
==================================
Orquesta el handoff de una llamada de voz a un humano via Chatwoot: crea o
reutiliza el contacto/conversacion de Chatwoot del lead, lo asigna al team
configurado y deja una nota privada explicando el motivo.

No evalua "cuando" disparar el handoff mas alla de lo que el llamador le
pasa explicitamente en `trigger` -- esa decision (tool explicita del agente,
o el chequeo de lead_score) vive en los endpoints de voice tools.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import CrmActivity, CrmContact, CrmLead
from app.models.integrations import TenantVoiceAgentConfig
from app.schemas.integrations import HANDOFF_TRIGGER_LEAD_SCORE
from app.services.chatwoot_client import ChatwootClient
from app.services.chatwoot_config_service import ChatwootConfigService
from app.services.crm_activity_service import CrmActivityService
from app.services.integration_event_service import IntegrationEventService

logger = logging.getLogger(__name__)

_TRIGGER_LABELS = {
    "customer_request": "El cliente solicito hablar con un humano",
    HANDOFF_TRIGGER_LEAD_SCORE: "Lead de alto valor",
}


class VoiceHandoffService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.activities = CrmActivityService(db)
        self.events = IntegrationEventService(db)

    async def maybe_handoff_for_lead_score(
        self, tenant_id: str, *, agent: TenantVoiceAgentConfig, lead: CrmLead
    ) -> dict:
        """Se llama desde cualquier voice tool que ya resolvio el lead; no hay
        analisis en vivo de la llamada fuera de esos puntos de invocacion."""
        if lead.lead_score is None or lead.lead_score < agent.handoff_lead_score_threshold:
            return {"status": "skipped", "reason": "score_below_threshold"}
        return await self.trigger_handoff(tenant_id, agent=agent, lead=lead, trigger=HANDOFF_TRIGGER_LEAD_SCORE)

    async def trigger_handoff(
        self, tenant_id: str, *, agent: TenantVoiceAgentConfig, lead: CrmLead, trigger: str
    ) -> dict:
        if trigger not in (agent.handoff_triggers or []):
            return {"status": "skipped", "reason": "trigger_not_enabled"}
        if not agent.handoff_enabled or not agent.handoff_chatwoot_inbox_id:
            return {"status": "skipped", "reason": "handoff_not_configured"}

        dedup_key = f"handoff:{trigger}:{lead.id}"
        already_handed_off = self.db.scalar(
            select(CrmActivity.id).where(
                CrmActivity.tenant_id == tenant_id,
                CrmActivity.lead_id == lead.id,
                CrmActivity.deduplication_key == dedup_key,
            )
        )
        if already_handed_off is not None:
            return {"status": "skipped", "reason": "already_handed_off"}

        contact = self.db.get(CrmContact, lead.contact_id)
        if contact is None or not contact.phone:
            return {"status": "skipped", "reason": "contact_without_phone"}

        try:
            _, client_config = ChatwootConfigService(self.db).get_active_client_config(tenant_id)
        except ValueError:
            return {"status": "skipped", "reason": "chatwoot_not_configured"}

        client = ChatwootClient(client_config)
        try:
            chatwoot_contact_id = await client.get_or_create_contact(
                contact.phone, name=contact.name, email=contact.email or ""
            )
            if not chatwoot_contact_id:
                return {"status": "failed", "reason": "chatwoot_contact_failed"}

            conversation_id = await client.get_or_create_conversation(
                chatwoot_contact_id, inbox_id=agent.handoff_chatwoot_inbox_id
            )
            if not conversation_id:
                return {"status": "failed", "reason": "chatwoot_conversation_failed"}

            if agent.handoff_chatwoot_team_id:
                await client.assign_team(conversation_id, agent.handoff_chatwoot_team_id)

            note = _TRIGGER_LABELS.get(trigger, trigger)
            if trigger == HANDOFF_TRIGGER_LEAD_SCORE:
                note = f"{note} (score {lead.lead_score})"
            await client.send_message(conversation_id, content=f"[Handoff automatico] {note}", private=True)
        except Exception as exc:
            logger.error("[VoiceHandoff] Error en handoff lead=%s trigger=%s: %s", lead.id, trigger, exc)
            self.events.record_event(
                tenant_id=tenant_id,
                provider="chatwoot",
                event_type="voice_handoff",
                status="failed",
                resource_type="lead",
                resource_id=lead.id,
                message=str(exc)[:500],
            )
            return {"status": "failed", "reason": "chatwoot_error"}

        self.activities.create_activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=contact.id,
            activity_type="chatwoot_handoff",
            title="Handoff a humano solicitado",
            description=note,
            deduplication_key=dedup_key,
        )
        self.events.record_event(
            tenant_id=tenant_id,
            provider="chatwoot",
            event_type="voice_handoff",
            status="success",
            resource_type="conversation",
            resource_id=str(conversation_id),
            metadata={"trigger": trigger},
        )
        return {"status": "success", "conversation_id": conversation_id}
