"""CRM-side adapter of an outbound SIP call from a lead.

Translates the HTTP contracts (VoiceCallActionRequest/Response) and gives
Telephony the ledger of this lead's CRM records. Everything else -- route,
capacity, voice session, runtime dispatch and the SIP dial -- is Telephony's
(and, through it, Voice's); this class holds no CRM, Voice or SIP logic.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.crm.public import OutboundCallLedger
from app.modules.telephony.public import PlaceOutboundCallCommand, TelephonyFacade
from app.schemas.integrations import VoiceCallActionRequest, VoiceCallActionResponse


class OutboundVoiceCallService:
    def __init__(self, db: Session, *, telephony: TelephonyFacade | None = None) -> None:
        self.db = db
        self.telephony = telephony or TelephonyFacade(db)

    async def start_call(
        self,
        tenant_id: str,
        lead_id: str,
        body: VoiceCallActionRequest,
    ) -> VoiceCallActionResponse:
        ledger = OutboundCallLedger(self.db, tenant_id, lead_id)
        result = await self.telephony.place_outbound_call(
            PlaceOutboundCallCommand(
                tenant_id=tenant_id,
                agent_id=body.agent_id,
                idempotency_key=body.idempotency_key,
                to_phone=body.to_phone,
            ),
            ledger,
        )
        return VoiceCallActionResponse(
            status=result.status,
            voice_call_id=ledger.call_id,
            provider_call_id=result.provider_call_id,
            provider_session_id=result.provider_session_id,
            voice_session_id=result.voice_session_id,
            sip_call_id=result.sip_call_id,
        )
