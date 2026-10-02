from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.modules.telephony.application.capacity_service import CapacityService
from app.modules.telephony.application.dial_service import TelephonyDialService
from app.modules.telephony.application.ports import OutboundCallLedger, TelephonyPorts
from app.modules.telephony.application.route_service import SipRouteService
from app.modules.telephony.domain.capacity import CAPACITY_END_REASON, is_at_capacity
from app.modules.telephony.domain.errors import SipDialError
from app.modules.telephony.domain.phone_numbers import normalize_outbound_phone
from app.modules.telephony.domain.views import (
    OutboundCallResult,
    PlaceOutboundCallCommand,
)
from app.modules.voice.public import (
    TelephonySessionView,
    VoiceSessionError,
    VoiceSessionNotFoundError,
)

logger = logging.getLogger(__name__)


class OutboundCallService:
    """Telephony's half of an outbound call. The caller's record of the call
    (CRM's lead/contact/call) is reached only through ``ledger``; the session
    only through VoiceTelephonyPort. Request-level idempotency is the
    (tenant, idempotency_key) of the VoiceSession plus the call already
    correlated to it: a retry never creates a second session, call or dial.
    """

    def __init__(self, db: Session, ports: TelephonyPorts, routes: SipRouteService | None = None) -> None:
        self.db = db
        self.ports = ports
        self.routes = routes or SipRouteService(db)
        self.capacity = CapacityService(db, ports.call_load)
        self.dialer = TelephonyDialService(db, self.routes, ports.voice, ports.sip)

    async def place_outbound_call(
        self, command: PlaceOutboundCallCommand, ledger: OutboundCallLedger
    ) -> OutboundCallResult:
        voice = self.ports.voice
        tenant_id = command.tenant_id
        if not command.agent_id:
            raise ValueError("agent_id is required for LiveKit SIP outbound.")
        if not command.idempotency_key:
            raise ValueError("idempotency_key is required for LiveKit SIP outbound.")

        target = ledger.resolve_target()

        route = self.routes.get_active_route(tenant_id, require_livekit=True)
        number = normalize_outbound_phone(
            command.to_phone or target.phone or "",
            default_country=route.default_country,
            allowed_countries=set(route.allowed_countries_json),
        )
        try:
            session = voice.create_outbound_sip_session(
                tenant_id,
                command.agent_id,
                idempotency_key=command.idempotency_key,
                contact_id=target.contact_id,
                lead_id=target.lead_id,
                caller_phone=number.e164,
            )
        except VoiceSessionError as exc:
            raise ValueError(str(exc)) from exc

        try:
            session = voice.lock_session(session.id, tenant_id)
        except VoiceSessionNotFoundError:
            raise ValueError("Voice session does not belong to this tenant.") from None
        if session.crm_voice_call_id:
            state = ledger.call_state(session.crm_voice_call_id)
            return OutboundCallResult(
                voice_session_id=session.id,
                status=state.status,
                sip_call_id=session.sip_call_id,
                provider_call_id=state.provider_call_id,
                provider_session_id=session.provider_session_id,
            )

        route = self.routes.get_active_route(tenant_id, for_update=True, require_livekit=True)
        active = self.capacity.callbacks_in_flight(tenant_id=tenant_id, route_id=route.id)
        if is_at_capacity(active, route.max_concurrent_calls):
            voice.cancel_session(session.id, tenant_id, end_reason=CAPACITY_END_REASON)
            self.capacity.record_capacity_reached(
                tenant_id=tenant_id,
                route_id=route.id,
                active_calls=active,
                max_concurrent_calls=route.max_concurrent_calls,
            )
            raise ValueError("Outbound telephony capacity exceeded.")

        call_id = ledger.open_call(
            sip_route_id=route.id,
            agent_version_id=session.agent_version_id,
            to_phone=number.e164,
            from_number=route.caller_id,
        )
        voice.correlate_crm_call(session.id, tenant_id, call_id)
        self.ports.projection.project_session(session.id, tenant_id, commit=False)
        self.db.commit()
        logger.info(
            "LiveKit SIP outbound requested | tenant_id=%s | crm_voice_call_id=%s | voice_session_id=%s | livekit_sip_trunk_id=%s",
            tenant_id,
            call_id,
            session.id,
            session.livekit_sip_trunk_id,
        )

        ledger.mark_dialing(call_id)
        try:
            session = await self.dialer.dial(session.id, tenant_id, number.e164, manage_failure=False)
        except SipDialError as exc:
            await self._fail(ledger, call_id, session, exc.call_status, exc.code)
            if exc.code == "runtime_not_ready":
                raise ValueError("Voice runtime did not become ready before timeout.") from None
            raise ValueError(exc.code) from None

        ledger.mark_answered(call_id, session.sip_call_id)
        self.ports.projection.project_session(session.id, tenant_id, commit=False)
        self.db.commit()
        logger.info(
            "LiveKit SIP answered | tenant_id=%s | crm_voice_call_id=%s | voice_session_id=%s | livekit_room_name=%s | sip_participant_identity=%s | sip_call_id=%s",
            tenant_id,
            call_id,
            session.id,
            session.livekit_room_name,
            session.livekit_sip_participant_identity,
            session.sip_call_id,
        )
        return OutboundCallResult(
            voice_session_id=session.id,
            status="answered",
            sip_call_id=session.sip_call_id,
            provider_call_id=session.sip_call_id,
            provider_session_id=session.provider_session_id,
        )

    async def _fail(
        self,
        ledger: OutboundCallLedger,
        call_id: str,
        session: TelephonySessionView,
        call_status: str,
        error_code: str,
    ) -> None:
        voice = self.ports.voice
        tenant_id = session.tenant_id
        ledger.mark_failed(call_id, call_status, error_code)
        # Snapshot after the dial attempt: the old code read the live session
        # row, which the dial had already updated.
        latest = voice.get_session(session.id, tenant_id)
        logger.warning(
            "LiveKit SIP outbound failed | tenant_id=%s | crm_voice_call_id=%s | voice_session_id=%s | livekit_room_name=%s | livekit_sip_trunk_id=%s | sip_participant_identity=%s | sip_call_id=%s | error_code=%s",
            tenant_id,
            call_id,
            latest.id,
            latest.livekit_room_name,
            latest.livekit_sip_trunk_id,
            latest.livekit_sip_participant_identity,
            latest.sip_call_id,
            error_code,
        )
        voice.fail_session(
            latest.id,
            tenant_id,
            code=error_code,
            sip_status_event=call_status if error_code.startswith("livekit_sip") else None,
            skip_if_terminal=True,
        )
        self.ports.projection.project_session(latest.id, tenant_id, commit=True)
        await voice.close_runtime_room(latest.id, tenant_id)
