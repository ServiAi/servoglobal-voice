from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from time import monotonic

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.crm import CrmLead, CrmVoiceCall
from app.models.voice_sessions import VoiceSession
from app.schemas.integrations import VoiceCallActionRequest, VoiceCallActionResponse
from app.services.livekit_runtime_backend import LiveKitRuntimeBackend
from app.services.livekit_sip_service import LiveKitSipDialError, LiveKitSipService
from app.services.voice_capacity_service import VoiceCapacityService
from app.services.voice_phone_service import normalize_outbound_phone
from app.services.voice_runtime_dispatcher import VoiceRuntimeDispatcher
from app.services.voice_session_service import VoiceSessionError, VoiceSessionService
from app.services.voice_sip_route_service import VoiceSipRouteService

logger = logging.getLogger(__name__)


class OutboundVoiceCallService:
    def __init__(
        self,
        db: Session,
        *,
        sip_service: LiveKitSipService | None = None,
        runtime_backend: LiveKitRuntimeBackend | None = None,
    ) -> None:
        self.db = db
        self.sessions = VoiceSessionService(db)
        self.routes = VoiceSipRouteService(db)
        self.capacity = VoiceCapacityService(db)
        self.sip = sip_service or LiveKitSipService()
        self.runtime_backend = runtime_backend or LiveKitRuntimeBackend()

    async def start_call(
        self,
        tenant_id: str,
        lead_id: str,
        body: VoiceCallActionRequest,
    ) -> VoiceCallActionResponse:
        if not body.agent_id:
            raise ValueError("agent_id is required for LiveKit SIP outbound.")
        if not body.idempotency_key:
            raise ValueError("idempotency_key is required for LiveKit SIP outbound.")

        lead = self.db.get(CrmLead, lead_id)
        if lead is None or lead.tenant_id != tenant_id or lead.contact is None:
            raise ValueError("Lead does not exist or does not belong to this tenant.")
        if lead.contact.tenant_id != tenant_id:
            raise ValueError("Contact associated with this lead does not exist.")

        route = self.routes.get_active_route(tenant_id, require_livekit=True)
        number = normalize_outbound_phone(
            body.to_phone or lead.contact.phone or "",
            default_country=route.default_country,
            allowed_countries=set(route.allowed_countries_json),
        )
        try:
            session = self.sessions.create(
                tenant_id,
                body.agent_id,
                channel="sip",
                direction="outbound",
                idempotency_key=body.idempotency_key,
                contact_id=lead.contact.id,
                lead_id=lead.id,
                caller_phone=number.e164,
            )
        except VoiceSessionError as exc:
            raise ValueError(str(exc)) from exc

        session = self.db.scalar(
            select(VoiceSession).where(
                VoiceSession.id == session.id,
                VoiceSession.tenant_id == tenant_id,
            ).with_for_update()
        )
        if session is None:
            raise ValueError("Voice session does not belong to this tenant.")
        if session.crm_voice_call_id:
            call = self.db.get(CrmVoiceCall, session.crm_voice_call_id)
            if call is None or call.tenant_id != tenant_id:
                raise ValueError("Idempotent voice call state is invalid.")
            return self._response(call, session)

        route = self.routes.get_active_route(
            tenant_id,
            for_update=True,
            require_livekit=True,
        )
        active = self.capacity.active_calls(tenant_id=tenant_id, route_id=route.id)
        if active >= route.max_concurrent_calls:
            self.sessions.transition(session, "cancelled", commit=False)
            self.sessions.record_event(
                session,
                "voice.session.cancelled",
                source="control-plane",
                payload={"end_reason": "telephony_capacity_exceeded"},
                commit=False,
            )
            self.db.commit()
            self.capacity.record_capacity_reached(
                tenant_id=tenant_id,
                route_id=route.id,
                active_calls=active,
                max_concurrent_calls=route.max_concurrent_calls,
            )
            raise ValueError("Outbound telephony capacity exceeded.")

        call = CrmVoiceCall(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=lead.contact.id,
            sip_route_id=route.id,
            provider="livekit_sip",
            provider_agent_id=session.agent_version_id,
            direction="outbound",
            status="requested",
            to_phone=number.e164,
            from_number=route.caller_id,
        )
        self.db.add(call)
        self.db.flush()
        session.crm_voice_call_id = call.id
        session.sip_route_id = route.id
        session.livekit_sip_trunk_id = route.livekit_outbound_trunk_id
        self.sessions.record_event(
            session,
            "voice.outbound.requested",
            source="control-plane",
            payload={"sip_route_id": route.id},
            commit=False,
        )
        self.db.commit()
        self.db.refresh(call)
        logger.info(
            "LiveKit SIP outbound requested | tenant_id=%s | crm_voice_call_id=%s | voice_session_id=%s | livekit_sip_trunk_id=%s",
            tenant_id,
            call.id,
            session.id,
            session.livekit_sip_trunk_id,
        )

        session = await VoiceRuntimeDispatcher(
            self.db, backend=self.runtime_backend
        ).dispatch(session)
        if session.status == "failed":
            await self._fail(call, session, "failed", "runtime_dispatch_failed")
            raise ValueError("Voice runtime dispatch failed.")
        try:
            session = await self.wait_until_runtime_ready(session.id, tenant_id)
        except TimeoutError:
            await self._fail(call, session, "failed", "runtime_not_ready")
            raise ValueError("Voice runtime did not become ready before timeout.") from None
        logger.info(
            "Voice runtime ready for SIP | tenant_id=%s | crm_voice_call_id=%s | voice_session_id=%s | livekit_room_name=%s | livekit_dispatch_id=%s",
            tenant_id,
            call.id,
            session.id,
            session.livekit_room_name,
            session.livekit_dispatch_id,
        )

        participant_identity = f"sip-{session.id}"
        call.status = "dialing"
        call.started_at = datetime.now(UTC)
        session.livekit_sip_participant_identity = participant_identity
        self.sessions.record_event(
            session,
            "voice.sip.dial.started",
            source="control-plane",
            payload={"sip_route_id": route.id},
            commit=False,
        )
        self.db.commit()
        logger.info(
            "LiveKit SIP dial started | tenant_id=%s | crm_voice_call_id=%s | voice_session_id=%s | livekit_room_name=%s | livekit_sip_trunk_id=%s | sip_participant_identity=%s",
            tenant_id,
            call.id,
            session.id,
            session.livekit_room_name,
            session.livekit_sip_trunk_id,
            participant_identity,
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
            await self._fail(call, session, exc.call_status, exc.code)
            raise ValueError(exc.code) from None

        session.sip_call_id = result.sip_call_id
        session.livekit_sip_participant_identity = result.participant_identity
        call.provider_call_id = result.sip_call_id
        call.status = "answered"
        call.answered_at = datetime.now(UTC)
        self.sessions.record_event(
            session,
            "voice.sip.answered",
            source="control-plane",
            payload={"sip_call_id": result.sip_call_id},
            commit=False,
        )
        self.db.commit()
        logger.info(
            "LiveKit SIP answered | tenant_id=%s | crm_voice_call_id=%s | voice_session_id=%s | livekit_room_name=%s | sip_participant_identity=%s | sip_call_id=%s",
            tenant_id,
            call.id,
            session.id,
            session.livekit_room_name,
            session.livekit_sip_participant_identity,
            session.sip_call_id,
        )
        return self._response(call, session)

    async def wait_until_runtime_ready(self, session_id: str, tenant_id: str) -> VoiceSession:
        deadline = monotonic() + settings.LIVEKIT_SIP_RUNTIME_READY_TIMEOUT_SECONDS
        while monotonic() < deadline:
            self.db.expire_all()
            session = self.sessions.get(session_id, tenant_id)
            if session.runtime_ready_at is not None:
                return session
            if session.status in {"failed", "ended", "cancelled"}:
                raise TimeoutError
            await asyncio.sleep(0.2)
        raise TimeoutError

    async def _fail(
        self,
        call: CrmVoiceCall,
        session: VoiceSession,
        call_status: str,
        error_code: str,
    ) -> None:
        self.db.refresh(call)
        call.status = call_status
        call.error_message = error_code[:255]
        call.ended_at = datetime.now(UTC)
        logger.warning(
            "LiveKit SIP outbound failed | tenant_id=%s | crm_voice_call_id=%s | voice_session_id=%s | livekit_room_name=%s | livekit_sip_trunk_id=%s | sip_participant_identity=%s | sip_call_id=%s | error_code=%s",
            session.tenant_id,
            call.id,
            session.id,
            session.livekit_room_name,
            session.livekit_sip_trunk_id,
            session.livekit_sip_participant_identity,
            session.sip_call_id,
            error_code,
        )
        if error_code.startswith("livekit_sip"):
            self.sessions.record_event(
                session,
                f"voice.sip.{call_status}",
                source="control-plane",
                payload={"error_code": error_code},
                commit=False,
            )
        if session.status not in {"failed", "ended", "cancelled"}:
            self.sessions.fail(session, error_code, error_code)
        else:
            self.db.commit()
        try:
            await self.runtime_backend.close_session_room(session.id)
        except Exception:
            self.sessions.record_event(
                session,
                "voice.cleanup.failed",
                source="control-plane",
                payload={"error_code": "livekit_room_close_failed"},
            )

    @staticmethod
    def _response(call: CrmVoiceCall, session: VoiceSession) -> VoiceCallActionResponse:
        return VoiceCallActionResponse(
            status=call.status,
            voice_call_id=call.id,
            provider_call_id=call.provider_call_id,
            provider_session_id=session.provider_session_id,
            voice_session_id=session.id,
            sip_call_id=session.sip_call_id,
        )
