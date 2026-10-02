from __future__ import annotations

import asyncio
from time import monotonic

from app.core.config import settings
from app.modules.telephony.application.ports import SipTransportPort, VoiceTelephonyPort
from app.modules.telephony.application.route_service import SipRouteService
from app.modules.telephony.domain.capacity import CAPACITY_END_REASON, is_at_capacity
from app.modules.telephony.domain.errors import SipDialError
from app.modules.telephony.domain.phone_numbers import normalize_outbound_phone
from app.modules.telephony.infrastructure.livekit_sip import LiveKitSipDialError
from app.modules.voice.public import TelephonySessionView


class TelephonyDialService:
    """Dials one tenant-scoped SIP VoiceSession without creating CRM records.

    Telephony owns the order of operations; Voice owns every change to the
    session and the runtime/room (VoiceTelephonyPort):

      1. validate the SIP/outbound session
      2. resolve and lock the tenant's route
      3. validate capacity
      4. bind route/trunk to the session            (voice.outbound.requested)
      5. dispatch the voice runtime
      6. wait until the runtime reports ready
      7. create the SIP participant                  (voice.sip.dial.started)
      8. record answered / the SIP error             (voice.sip.answered | voice.sip.<status>)
      9. close the room when the dial fails
    """

    def __init__(self, db, routes: SipRouteService, voice: VoiceTelephonyPort, sip: SipTransportPort) -> None:
        self.db = db
        self.routes = routes
        self.voice = voice
        self.sip = sip

    async def dial(
        self, session_id: str, tenant_id: str, to_phone: str, *, manage_failure: bool = True
    ) -> TelephonySessionView:
        session = self.voice.get_session(session_id, tenant_id)
        if session.channel != "sip" or session.direction != "outbound":
            raise SipDialError("invalid_sip_session")
        if session.status != "requested":
            return session
        route = self.routes.get_active_route(tenant_id, for_update=True, require_livekit=True)
        number = normalize_outbound_phone(
            to_phone,
            default_country=route.default_country,
            allowed_countries=set(route.allowed_countries_json),
        )
        active = self.voice.count_active_telephony_sessions(tenant_id, route.id, exclude_session_id=session.id)
        if is_at_capacity(active, route.max_concurrent_calls):
            self.voice.cancel_session(session.id, tenant_id, end_reason=CAPACITY_END_REASON)
            raise SipDialError(CAPACITY_END_REASON, "cancelled")

        self.voice.bind_sip_route(
            session.id, tenant_id, route_id=route.id, livekit_trunk_id=route.livekit_outbound_trunk_id
        )

        session = await self.voice.dispatch_runtime(session.id, tenant_id)
        if session.status == "failed":
            raise SipDialError("runtime_dispatch_failed")
        try:
            session = await self.wait_until_runtime_ready(session.id, tenant_id)
        except TimeoutError:
            if manage_failure:
                self.voice.fail_session(session.id, tenant_id, code="runtime_not_ready")
                await self.voice.close_runtime_room(session.id, tenant_id)
            raise SipDialError("runtime_not_ready") from None

        participant_identity = f"sip-{session.id}"
        self.voice.begin_sip_dial(
            session.id, tenant_id, route_id=route.id, participant_identity=participant_identity
        )
        try:
            result = await self.sip.dial(
                trunk_id=route.livekit_outbound_trunk_id,
                to_phone=number.e164,
                from_number=route.caller_id,
                room_name=session.livekit_room_name,
                participant_identity=participant_identity,
            )
        except LiveKitSipDialError as exc:
            if manage_failure:
                self.voice.fail_session(
                    session.id, tenant_id, code=exc.code, sip_status_event=exc.call_status
                )
                await self.voice.close_runtime_room(session.id, tenant_id)
            raise SipDialError(exc.code, exc.call_status) from None

        return self.voice.complete_sip_dial(
            session.id,
            tenant_id,
            sip_call_id=result.sip_call_id,
            participant_identity=result.participant_identity,
        )

    async def wait_until_runtime_ready(self, session_id: str, tenant_id: str) -> TelephonySessionView:
        deadline = monotonic() + settings.LIVEKIT_SIP_RUNTIME_READY_TIMEOUT_SECONDS
        while monotonic() < deadline:
            session = self.voice.get_session(session_id, tenant_id, refresh=True)
            if session.runtime_ready_at is not None:
                return session
            if session.is_terminal:
                raise TimeoutError
            await asyncio.sleep(0.2)
        raise TimeoutError
